"""Talking to Gemini, and being fine when we cannot.

The key is read from site_config.json and never from the repository. There is a
preflight check that fails the build if anything that looks like a Google API key
appears in a tracked file, because a key in git is a key that has leaked.

    bench --site <site> set-config command_center_gemini_key "AIza..."

Everything here is optional by design. No key, no network, a slow reply, a malformed
reply -- each returns None, and the caller falls back to pattern matching. The screen
must never go dark because a third party is having a bad afternoon.
"""

from __future__ import annotations

import json

import frappe

# Pinned, not "-latest". A floating model name changes the behaviour of a deployed
# demonstration without anybody deploying anything, which is the opposite of what a
# demonstration needs. Overridable per site.
DEFAULT_MODEL = "gemini-2.5-flash-lite"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT = 8


def configured() -> bool:
    return bool(_key())


def _key() -> str | None:
    return frappe.conf.get("command_center_gemini_key")


def _model() -> str:
    return frappe.conf.get("command_center_gemini_model") or DEFAULT_MODEL


def analyst_model() -> str:
    """The model for the analyst, which reasons over many tool calls.

    flash-lite is right for picking a route and wrong for this: multi-step analysis
    with tools is exactly where the smaller model loses the thread. Pinned for the
    same reason as the router's, and overridable per site.
    """
    return frappe.conf.get("command_center_analyst_model") or "gemini-2.5-flash"


def chat(contents: list, tools: list, system: str, timeout: int = 40, mode: str = "AUTO") -> tuple:
    """One turn of a tool-using conversation: (content, error).

    The caller owns the loop: it appends the model's content unchanged (thinking
    models attach signatures to their parts that must come back verbatim), runs any
    function calls, and appends their responses.

    Errors are returned rather than logged here. The analyst rolls back any write made
    while it worked, and an error logged mid-conversation would be rolled back with it
    -- the one record of what went wrong, erased by the guard.
    """
    key = _key()
    if not key:
        return None, "no Gemini key configured"

    import requests

    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        # A bounded budget for the model's private reasoning: enough to plan the lookups,
        # not so much that a question waits, or the reasoning eats the answer's tokens.
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192,
                             "thinkingConfig": {"thinkingBudget": 2048}},
    }
    if tools:  # None for the final turn: answer from what has been gathered
        body["tools"] = [{"functionDeclarations": tools}]
        body["toolConfig"] = {"functionCallingConfig": {"mode": mode}}
    try:
        r = requests.post(ENDPOINT.format(model=analyst_model()),
                          params={"key": key}, json=body, timeout=timeout)
        # Busy or a passing fault on Google's side: one retry, a moment later, before a
        # question falls back to the basic engine.
        if r.status_code in (429, 500, 502, 503, 504):
            import time
            time.sleep(1.5)
            r = requests.post(ENDPOINT.format(model=analyst_model()),
                              params={"key": key}, json=body, timeout=timeout)
        if r.status_code != 200:
            return None, f"Gemini refused: {r.status_code} {r.text[:900]}"
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
    key = _key()
    if not key:
        return None

    import requests

    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,          # routing, not writing: same question, same route
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "maxOutputTokens": 256,
        },
    }
    try:
        r = requests.post(ENDPOINT.format(model=_model()),
                          params={"key": key}, json=body, timeout=TIMEOUT)
        if r.status_code != 200:
            frappe.log_error(title="Command Center: Gemini refused",
                             message=f"{r.status_code} {r.text[:900]}")
            return None
        payload = r.json()
        text = (payload["candidates"][0]["content"]["parts"][0]["text"])
        return json.loads(text)
    except Exception:
        frappe.log_error(title="Command Center: Gemini unreachable",
                         message=frappe.get_traceback())
        return None
