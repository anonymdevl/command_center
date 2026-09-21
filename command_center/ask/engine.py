"""Answering a question, and being honest when it cannot.

Two layers, deliberately separated:

    a planner   decides which intent applies and what it is about
    the intents compute the answer from the facts

Today the planner is pattern matching. When Claude is wired in, it replaces the
planner and nothing else: it will choose an intent and its subject, and the figures
will still come out of intents.py, which reads the facts. The model will never state
a number. That is not caution for its own sake -- every honesty rule this platform
has depends on the figure and the sentence coming from different places, so that a
model being confidently wrong cannot change what the number says.

`suggest` exists because a question that matches nothing should say what the platform
can answer, not "no results". A blank screen teaches nobody what to ask next.
"""

from __future__ import annotations

import frappe

from command_center.ask import intents, resolve

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
    for intent in intents.INTENTS:
        try:
            result = intent(question, business_code)
        except Exception:
            frappe.log_error(title=f"Command Center ask: {intent.__name__}",
                             message=frappe.get_traceback())
            failures.append(intent.__name__)
            continue
        if result:
            return result, failures
    return None, failures


def answer(question: str, business_code: str | None = None) -> dict:
    question = (question or "").strip()
    if not question:
        return _cannot("Ask a question and I will look it up.", [])

    result, failures = plan(question, business_code)
    if result:
        result.setdefault("figures", [])
        result.setdefault("checked", [])
        result["question"] = question
        result["answered"] = True
        result["planner"] = "patterns"
        if failures:
            result["degraded"] = failures
        return result

    # Something broke rather than nothing matching. Say so: a failure that reads as a
    # limitation is worse than an error, because nobody goes looking for it.
    if failures:
        return {
            "answered": False,
            "failed": True,
            "intent": None,
            "planner": "patterns",
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
            f"Try one of these phrasings.", found)
    return _cannot(
        "I could not match that to anything in the loaded records — neither a "
        "customer, supplier, item or warehouse, nor a question I know how to "
        "answer. These are the ones I can answer today.", [])


def _cannot(message: str, found: list) -> dict:
    return {
        "answered": False,
        "intent": None,
        "planner": "patterns",
        "answer": message,
        "checked": ["the names in the loaded facts",
                    "the list of questions this screen can answer"],
        "figures": [],
        "records": None,
        "entities": found,
        "suggestions": ANSWERABLE,
    }
