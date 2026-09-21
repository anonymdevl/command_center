"""The question box, as an endpoint.

Read-only by construction: it reaches ask/engine.py, which reaches the fact tables.
There is no path from here to actions.py, so no phrasing of a question can change a
record. require_manager() still runs first, because the facts are management-only.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager
from command_center.ask import engine


@frappe.whitelist()
def answer(question: str, business_code: str | None = None):
    require_manager()
    return engine.answer(question, business_code)


@frappe.whitelist()
def answerable():
    """What this screen can answer today.

    Useful on its own: it is the list to show a client when agreeing what the
    assistant covers, without anyone reading code.
    """
    require_manager()
    from command_center.ask import gemini
    return {
        "questions": engine.ANSWERABLE,
        "planner": "gemini" if gemini.configured() else "patterns",
        "model": gemini.DEFAULT_MODEL if gemini.configured() else None,
        # Said plainly because someone will ask what the model is given. It is the
        # question, the handler list, and names found in the question. No figures.
        "sent_to_model": ["the question as typed",
                          "the list of handler names and their descriptions",
                          "entity names found in the question itself"],
    }
