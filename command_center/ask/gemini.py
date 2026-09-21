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
