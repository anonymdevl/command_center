"""Answering a question, and being honest when it cannot.

First, the analyst (agent.py): Gemini reading the business through read-only tools and
answering in full -- figures, reasons, projections, recommendations. That is the
decision of 18 Oct 2026, which replaced "the model routes and never states a number":
the model is used to its full capacity for anything informational and can change
nothing, which tools.py enforces by having no write path at all.

Below it, the floor: the original planner and intents. If there is no key, the site
is set to router mode, or the analyst cannot be reached, a question is answered the
old way -- six careful analyses, routed by Gemini if it is reachable and by patterns
if not.

`suggest` exists because a question that matches nothing should say what the platform
can answer, not "no results". A blank screen teaches nobody what to ask next.
"""

from __future__ import annotations

import frappe

from command_center.ask import agent, gemini, intents, planner_llm, resolve

# What a manager can ask today, in their words. Shown when nothing matches, and it is
# also the list a client can be given when agreeing what the assistant covers.
ANSWERABLE = [
    "Who owes us the most?",
    "Has UBUNTU ever paid us?",
    "Why is the Ejura order still open?",
    "What should I say to UBUNTU?",
    "Which customers owe us money and are also waiting on us?",
    "What happens if SICHUAN stops supplying?",
]


def plan(question: str, business_code: str | None = None) -> tuple:
    """Pick the intent that applies, and report anything that broke trying.

    The first intent that claims the question wins, and `refuses` is first in the list,
    so a request to change something is never answered by accident.

    Failures are returned, not swallowed. The first version of this logged the error and
    moved on, which meant a bug inside an intent came out as "I recognise that customer
    but not what you are asking" -- a crash wearing the costume of a limitation. That is
    the same fault as the field drop that emptied sixty complaints: the system appeared
    to work and quietly did not.
    """
    failures = []
    note = {"router": "not configured" if not gemini.configured() else "consulted"}

    # Gemini first, if a key is configured. It only names an intent and a subject; the
    # figures come from the intent itself. A route it invents, a slow reply, no key or
    # no network all fall through to the patterns below, so the patterns are the floor
    # rather than the ceiling.
    routed = None
    try:
        routed = planner_llm.route(question, business_code)
    except Exception:
        frappe.log_error(title="Command Center ask: router",
                         message=frappe.get_traceback())
        note["router"] = "errored"
    if gemini.configured() and not routed:
        # Either it declined, invented a handler, or could not be reached. In every case
        # the patterns are what decide from here, and saying "gemini" would claim a
        # routing that did not happen.
        note["router"] = note.get("router") if note["router"] == "errored" else "no usable route"
    if routed:
        by_name = {f.__name__: f for f in intents.INTENTS}
        chosen = by_name.get(routed["intent"])
        if chosen:
            # The subject is put back into the question so the intent resolves the same
            # entity the router meant. The intent still does its own resolution -- the
            # model is not trusted to hand over a name that the facts contain.
            asked = question
            if routed.get("subject") and routed["subject"].lower() not in question.lower():
                asked = f"{question} ({routed['subject']})"
            try:
                result = chosen(asked, business_code)
            except Exception:
                frappe.log_error(title=f"Command Center ask: {chosen.__name__}",
                                 message=frappe.get_traceback())
                result = None
                failures.append(chosen.__name__)
            if result:
                result["planner"] = "gemini"
                result["routed"] = routed
                return result, failures, note
            # The router chose a handler that then declined. That is worth recording:
            # it is the signal that a description is misleading the model.
            failures.append(f"{routed['intent']} (routed but declined)")
            note["router"] = f"chose {routed['intent']}, which declined"

    # The fallback: match on phrasing, then answer. The matcher is consulted here and
    # only here -- an intent itself never checks the wording, so a route the model chose
    # from an unfamiliar phrasing is not overruled by the patterns it was meant to
    # replace.
    for intent in intents.INTENTS:
        name = intent.__name__
        matcher = intents.MATCHERS.get(name)
        if not matcher or not matcher(question):
            continue
        try:
            result = intent(question, business_code)
        except Exception:
            frappe.log_error(title=f"Command Center ask: {name}",
                             message=frappe.get_traceback())
            failures.append(name)
            continue
        if result:
            return result, failures, note
    return None, failures, note


def analyst_enabled() -> bool:
    """On unless a site opts out: bench --site <site> set-config command_center_ai_mode router"""
    return gemini.configured() and (frappe.conf.get("command_center_ai_mode") or "analyst") != "router"


def answer(question: str, business_code: str | None = None, history=None) -> dict:
    question = (question or "").strip()
    if not question:
        return _cannot("Ask a question and I will look it up.", [])

    if analyst_enabled():
        try:
            result = agent.answer(question, business_code, history)
        except Exception:
            frappe.log_error(title="Command Center analyst", message=frappe.get_traceback())
            result = None
        if result:
            return result

    result, failures, note = plan(question, business_code)
    if result:
        result.setdefault("figures", [])
        result.setdefault("checked", [])
        result["question"] = question
        result["answered"] = True
        result.setdefault("planner", "patterns")
        if failures:
            result["degraded"] = failures
        result["router"] = note["router"]
        return result

    # Something broke rather than nothing matching. Say so: a failure that reads as a
    # limitation is worse than an error, because nobody goes looking for it.
    if failures:
        return {
            "answered": False,
            "failed": True,
            "intent": None,
            # The patterns had the last word, so they are the planner of record. Naming
            # gemini here would claim a route it did not produce.
            "planner": "patterns",
            "router": note["router"],
            "answer": (
                "Something went wrong working that out, so I am not going to guess. "
                f"{len(failures)} of the ways I try to answer this raised an error and "
                "the details are in the error log. This is a fault, not a limit of what "
                "the platform can be asked."
            ),
            "checked": [f"attempted: {', '.join(failures)}"],
            "figures": [], "records": None, "entities": [],
            "suggestions": ANSWERABLE,
        }

    # Nothing matched. Say whether the question named something real, because "I do
    # not know that customer" and "I cannot answer that kind of question" are
    # different problems and lead to different next moves.
    found = resolve.resolve(question, business_code)[:3]
    if found:
        names = ", ".join(f"{m['name']} ({m['kind']})" for m in found)
        return _cannot(
            f"I recognise {names}, but not what you are asking about them. "
            f"Try one of these phrasings.", found, note)
    return _cannot(
        "I could not match that to anything in the loaded records — neither a "
        "customer, supplier, item or warehouse, nor a question I know how to "
        "answer. These are the ones I can answer today.", [], note)


def _cannot(message: str, found: list, note: dict | None = None) -> dict:
    return {
        "answered": False,
        "intent": None,
        # Nothing answered, so the patterns were the last word. Reporting gemini would
        # suggest it routed successfully when it did not.
        "planner": "patterns",
        "router": (note or {}).get("router", "not configured"),
        "answer": message,
        "checked": ["the names in the loaded facts",
                    "the list of questions this screen can answer"],
        "figures": [],
        "records": None,
        "entities": found,
        "suggestions": ANSWERABLE,
    }
