"""Talking to Gemini, and being fine when we cannot.

The key is read from site_config.json and never from the repository. There is a
preflight check that fails the build if anything that looks like a Google API key
appears in a tracked file, because a key in git is a key that has leaked.

    bench --site <site> set-config command_center_gemini_key "AIza..."

Everything here is optional by design. No key, no network, a slow reply, a malformed
reply -- each returns an error the caller reports, and the question falls back to the
basic engine. The screen must never go dark because a third party is having a bad
afternoon.

Models. A named model, pinned, so a deployed demonstration does not change behaviour
with nobody deploying anything -- but models are retired: on 18 Oct 2026 Google stopped
serving gemini-2.5-flash to new keys and every analyst call returned 404. So when
Google says a model is not available, this asks Google which models the key may use,
takes the newest suitable Flash, retries once, and remembers the choice for a day. A
model named in site_config is never second-guessed:

    bench --site <site> set-config command_center_analyst_model "gemini-3.8-flash"
"""

from __future__ import annotations

import json
import re

import frappe

# The models used when site_config names none. Google's own 404 named 3.8 Flash as the
# replacement for 2.5 Flash.
PREFERRED = {"analyst": "gemini-3.8-flash", "router": "gemini-3.8-flash"}
DEFAULT_MODEL = PREFERRED["router"]  # kept: api/ask.answerable reports it
CONF_KEY = {"analyst": "command_center_analyst_model", "router": "command_center_gemini_model"}
BASE = "https://generativelanguage.googleapis.com/v1beta"
ENDPOINT = BASE + "/models/{model}:generateContent"
TIMEOUT = 8
CHOSEN_FOR = 24 * 3600


def configured() -> bool:
    return bool(_key())


def _key() -> str | None:
    return frappe.conf.get("command_center_gemini_key")


def model_for(kind: str) -> str:
    """The model in use: the site's own choice, else one found working, else preferred."""
    return (frappe.conf.get(CONF_KEY[kind])
            or frappe.cache().get_value(f"cc_gemini_model::{kind}")
            or PREFERRED[kind])


def analyst_model() -> str:
    return model_for("analyst")


def _model() -> str:
    return model_for("router")


def choose_model(listed: list, kind: str) -> str | None:
    """The newest suitable model from Google's list for this key, or None.

    Suitable: serves generateContent, is a Flash model, and is a stable name -- not an
    image, audio, live, embedding or experimental variant, and not a floating "-latest"
    alias. The analyst avoids "lite" (multi-step tool use is where the small model loses
    the thread); the router prefers it when there is one.
    """
    skip = ("image", "tts", "audio", "live", "embedding", "native", "exp", "preview",
            "latest", "learnlm", "vision")
    found = []
    for m in listed or []:
        name = str(m.get("name", "")).removeprefix("models/")
        if "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        if not name.startswith("gemini-") or "flash" not in name or any(s in name for s in skip):
            continue
        v = re.match(r"gemini-(\d+)(?:\.(\d+))?", name)
        if not v:
            continue
        version = (int(v.group(1)), int(v.group(2) or 0))
        lite = "lite" in name
        if kind == "analyst" and lite:
            continue
        rank = (version, lite if kind == "router" else False, -len(name))
        found.append((rank, name))
    return max(found)[1] if found else None


def _discover(kind: str) -> str | None:
    import requests
    try:
        r = requests.get(f"{BASE}/models", params={"key": _key(), "pageSize": 200}, timeout=10)
        if r.status_code != 200:
            return None
        name = choose_model(r.json().get("models") or [], kind)
        if name:
            frappe.cache().set_value(f"cc_gemini_model::{kind}", name, expires_in_sec=CHOSEN_FOR)
        return name
    except Exception:
        return None


def _post(kind: str, body: dict, timeout: int):
    """POST to the model for this kind, with one retry for a passing fault and one
    re-choice of model when Google has retired the one in use. Returns the response."""
    import time

    import requests

    model = model_for(kind)
    r = requests.post(ENDPOINT.format(model=model), params={"key": _key()}, json=body,
                      timeout=timeout)
    if r.status_code in (429, 500, 502, 503, 504):
        time.sleep(1.5)
        r = requests.post(ENDPOINT.format(model=model), params={"key": _key()}, json=body,
                          timeout=timeout)
    if r.status_code == 404 and not frappe.conf.get(CONF_KEY[kind]):
        frappe.cache().delete_value(f"cc_gemini_model::{kind}")
        replacement = _discover(kind)
        if replacement and replacement != model:
            r = requests.post(ENDPOINT.format(model=replacement), params={"key": _key()},
                              json=body, timeout=timeout)
    return r


def chat(contents: list, tools: list, system: str, timeout: int = 40, mode: str = "AUTO") -> tuple:
    """One turn of a tool-using conversation: (content, error).

    The caller owns the loop: it appends the model's content unchanged (thinking
    models attach signatures to their parts that must come back verbatim), runs any
    function calls, and appends their responses.

    Errors are returned rather than logged here. The analyst rolls back any write made
    while it worked, and an error logged mid-conversation would be rolled back with it
    -- the one record of what went wrong, erased by the guard.
    """
    if not _key():
        return None, "no Gemini key configured"

    # No temperature: Gemini 3 models are tuned for their default, and Google warns a
    # lowered one can make them loop. Thinking set low: by default Gemini 3 reasons at
    # length before every step, which made "how many users are active" take as long as
    # a board report. The tools do the work; the model only has to choose them well.
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": 8192, "thinkingConfig": {"thinkingLevel": "low"}},
    }
    if tools:  # None for the final turn: answer from what has been gathered
        body["tools"] = [{"functionDeclarations": tools}]
        body["toolConfig"] = {"functionCallingConfig": {"mode": mode}}
    try:
        r = _post("analyst", body, timeout)
        if r.status_code == 400 and "thinking" in r.text.lower():
            # A model that does not know thinkingLevel: ask again without it.
            body["generationConfig"].pop("thinkingConfig", None)
            r = _post("analyst", body, timeout)
        if r.status_code != 200:
            return None, f"Gemini refused ({analyst_model()}): {r.status_code} {r.text[:900]}"
        payload = r.json()
        candidates = payload.get("candidates") or []
        if not candidates or "content" not in candidates[0]:
            reason = (candidates[0].get("finishReason") if candidates else None) or "no candidates"
            return None, f"Gemini returned no content ({reason}): {json.dumps(payload)[:700]}"
        return candidates[0]["content"], None
    except Exception:
        return None, f"Gemini unreachable: {frappe.get_traceback()[:1500]}"


def ask_json(prompt: str, schema: dict) -> dict | None:
    """One call, expecting JSON back. None on any problem at all.

    responseSchema makes Gemini return parseable JSON rather than prose containing
    JSON, which removes a whole class of "strip the markdown fence" parsing bugs.
    """
    if not _key():
        return None

    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            # Room for a thinking model's reasoning as well as the small JSON reply.
            "maxOutputTokens": 1024,
        },
    }
    try:
        r = _post("router", body, TIMEOUT)
        if r.status_code != 200:
            frappe.log_error(title="Command Center: Gemini refused",
                             message=f"{r.status_code} {r.text[:900]}")
            return None
        payload = r.json()
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        return json.loads(text)
    except Exception:
        frappe.log_error(title="Command Center: Gemini unreachable",
                         message=frappe.get_traceback())
        return None
