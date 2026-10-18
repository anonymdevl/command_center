"""The question box, as an endpoint.

Read-only by construction: it reaches ask/engine.py, whose analyst can call only the
read tools in ask/tools.py, and which rolls back any write made while answering. There
is no path from here to actions.py, so no phrasing of a question can change a record.
require_manager() runs first, because the facts are management-only.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager
from command_center.ask import engine


@frappe.whitelist()
def answer(question: str, business_code: str | None = None, history=None):
    """history: the last few [{"q": ..., "a": ...}] turns, so a follow-up has context."""
    require_manager()
    if isinstance(history, str):
        history = frappe.parse_json(history)
    return engine.answer(question, business_code, history)


@frappe.whitelist()
def check_analyst():
    """Is the analyst working on this site? Open in a browser while signed in:
    /api/method/command_center.api.ask.check_analyst

    Sends Gemini the real tool catalogue and a one-line question, so a declaration
    Gemini will not accept, a wrong key or a retired model shows up here, in words.
    """
    require_manager()
    from command_center.ask import gemini, tools
    if not gemini.configured():
        return {"ok": False, "why": "No Gemini key on this site. bench --site <site> "
                "set-config command_center_gemini_key \"...\""}
    content, err = gemini.chat([{"role": "user", "parts": [{"text": "Reply with the word OK."}]}],
                               tools.declarations(), "You are a connectivity check.", timeout=30)
    if err:
        return {"ok": False, "model": gemini.analyst_model(), "why": err[:900]}
    text = "".join(p.get("text", "") for p in (content or {}).get("parts", []))
    return {"ok": True, "model": gemini.analyst_model(), "tools": len(tools.declarations()),
            "reply": text[:80], "mode": "analyst" if engine.analyst_enabled() else "router"}


@frappe.whitelist()
def answerable():
    """What this screen can answer today.

    Useful on its own: it is the list to show a client when agreeing what the
    assistant covers, without anyone reading code.
    """
    require_manager()
    from command_center.ask import gemini
    if engine.analyst_enabled():
        # Said plainly because someone will ask what the model is given -- and SE-07
        # requires it to be disclosed.
        return {
            "questions": [e["q"] for e in engine.ANALYST_EXAMPLES],
            "examples": engine.ANALYST_EXAMPLES,
            "planner": "gemini",
            "mode": "analyst",
            "model": gemini.analyst_model(),
            "sent_to_model": [
                "the question as typed, and the last few questions and answers",
                "totals, breakdowns and records from the loaded data that the question needs",
                "ERPNext documents the person asking is permitted to read, when needed",
                "nothing from credential or system-configuration doctypes",
            ],
            "can_change_records": False,
        }
    return {
        "questions": engine.ANSWERABLE,
        "examples": [{"q": q, "area": ""} for q in engine.ANSWERABLE],
        "planner": "gemini" if gemini.configured() else "patterns",
        "mode": "router",
        "model": gemini.DEFAULT_MODEL if gemini.configured() else None,
        "sent_to_model": ["the question as typed",
                          "the list of handler names and their descriptions",
                          "entity names found in the question itself"],
        "can_change_records": False,
    }
