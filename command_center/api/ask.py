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
def answer(question: str, business_code: str | None = None, history=None, ask_id=None):
    """history: the last few [{"q": ..., "a": ...}] turns, so a follow-up has context.

    ask_id: when the page passes one, each lookup is written to the cache as it starts,
    and the page reads them with poll() while this request is still working -- the
    live steps under the question. No background worker is involved: on the live site
    the job queue was not serving, and steps that depended on it never appeared.
    """
    require_manager()
    if isinstance(history, str):
        history = frappe.parse_json(history)
    on_step = None
    if ask_id:
        key, state = _ask_key(str(ask_id)[:40]), {"state": "running", "steps": []}
        frappe.cache().set_value(key, state, expires_in_sec=ASK_KEEP)

        def on_step(text):
            if not state["steps"] or state["steps"][-1] != text:
                state["steps"].append(text)
                frappe.cache().set_value(key, state, expires_in_sec=ASK_KEEP)
    result = engine.answer(question, business_code, history, on_step=on_step)
    resume = result.pop("_resume", None) if isinstance(result, dict) else None
    if resume and result.get("cut_short") and ask_id:
        _start_deep(str(ask_id)[:40], question, business_code, resume)
        result["deep"] = {"ask_id": str(ask_id)[:40]}
    return result


# ---------------------------------------------------------------------------
# A deeper look. A big question can need more lookups than a web request has time
# for -- the server ends it at 120 seconds. Then the request answers with what it has,
# and a job carries on from exactly where it stopped, with forty rounds and twenty
# minutes (raised 18 Oct 2026: big questions may take as long as they need); the page
# follows its steps and swaps in the fuller answer. If no worker picks the job up, the
# first answer stands and the page says why.
# ---------------------------------------------------------------------------
DEEP_STEPS = 40
DEEP_DEADLINE = 1200


def _start_deep(ask_id: str, question: str, business_code, resume: dict):
    base = _ask_key(ask_id)
    frappe.cache().set_value(base + "::resume", resume, expires_in_sec=ASK_KEEP)
    frappe.cache().set_value(base + "::deep", {"state": "queued", "steps": []}, expires_in_sec=ASK_KEEP)
    # ask_id as a keyword is fine; job_id would be swallowed by frappe.enqueue.
    frappe.enqueue("command_center.api.ask._deep", queue="long", timeout=1500,
                   ask_id=ask_id, question=question, business_code=business_code,
                   user=frappe.session.user, enqueue_after_commit=False)


def _deep(ask_id: str, question: str, business_code, user: str):
    frappe.set_user(user)  # reads with the asker's own permissions
    from command_center.ask import agent
    base = _ask_key(ask_id)
    state = {"state": "running", "steps": []}
    frappe.cache().set_value(base + "::deep", state, expires_in_sec=ASK_KEEP)

    def step(text):
        if not state["steps"] or state["steps"][-1] != text:
            state["steps"].append(text)
            frappe.cache().set_value(base + "::deep", state, expires_in_sec=ASK_KEEP)

    try:
        resume = frappe.cache().get_value(base + "::resume")
        if not resume:
            raise RuntimeError("the conversation to continue had expired")
        result = agent.answer(question, business_code, resume=resume, max_steps=DEEP_STEPS,
                              deadline=DEEP_DEADLINE, on_step=step)
        if not result or not result.get("answered"):
            raise RuntimeError((result or {}).get("analyst_error") or "no answer came back")
        result.pop("_resume", None)
        result["deepened"] = True
        frappe.cache().set_value(base + "::deep", {"state": "done", "steps": state["steps"],
                                                   "result": result}, expires_in_sec=ASK_KEEP)
    except Exception as e:
        frappe.log_error(title="Command Center deeper look", message=frappe.get_traceback())
        frappe.cache().set_value(base + "::deep", {"state": "failed", "steps": state["steps"],
                                                   "error": str(e)[:300]}, expires_in_sec=ASK_KEEP)


# ---------------------------------------------------------------------------
# Live steps: answer() records each lookup under an id the page chose; poll() reads it.
# ---------------------------------------------------------------------------
ASK_KEEP = 1800


def _ask_key(ask_id: str) -> str:
    return f"cc_ask::{frappe.session.user}::{ask_id}"


@frappe.whitelist()
def poll(ask_id: str, deep=0):
    """The steps so far -- of the question, or (deep=1) of its deeper look."""
    require_manager()
    key = _ask_key(str(ask_id)[:40]) + ("::deep" if frappe.utils.cint(deep) else "")
    return frappe.cache().get_value(key) or {"state": "unknown", "steps": []}


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
