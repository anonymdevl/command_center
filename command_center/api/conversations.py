"""A person's conversations with the AI, kept so they are there next time.

Until 18 Oct 2026 the conversation lived only in the page and was gone on a refresh or a
sign-out -- not what anyone expects of an assistant. Now each conversation is a
Command Center Conversation owned by the person who had it: they see their own and no
one else's (the doctype's if_owner permission, and owner filters here as well).

What is stored is what the screen needs to show the turn again -- the question, the
answer text, what it checked, the records behind it and which model answered -- never
the analyst's working. The assistant does not read or write these; the page does.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import now_datetime

from command_center.api.businesses import require_manager

DOCTYPE = "Command Center Conversation"
MAX_TURNS = 60
KEEP = ("answer", "format", "checked", "records", "model", "mode", "planner", "notice",
        "analyst_error", "answered", "figures", "suggestions", "table")


@frappe.whitelist()
def recent(business_code: str | None = None, limit: int = 20):
    """This person's conversations, newest first."""
    require_manager()
    filters = {"owner": frappe.session.user}
    if business_code:
        filters["business_code"] = business_code
    return frappe.get_all(DOCTYPE, filters=filters,
                          fields=["name", "title", "business_code", "last_at", "turn_count"],
                          order_by="last_at desc", limit=max(1, min(int(limit or 20), 100)))


@frappe.whitelist()
def load(name: str):
    doc = _mine(name)
    return {"name": doc.name, "title": doc.title, "business_code": doc.business_code,
            "turns": json.loads(doc.turns or "[]")}


@frappe.whitelist(methods=["POST"])
def add(question: str, payload, business_code: str | None = None, name: str | None = None,
        replace: int = 0):
    """Add a turn (or, with replace, swap in a deeper look's fuller answer for the last
    turn with this question). Starts a conversation when there is no name."""
    require_manager()
    payload = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    turn = {"q": (question or "").strip()[:2000],
            "payload": {k: payload.get(k) for k in KEEP if payload.get(k) is not None},
            "at": str(now_datetime())[:19]}
    if name:
        doc = _mine(name)
    else:
        doc = frappe.get_doc({"doctype": DOCTYPE, "business_code": business_code or "__all__",
                              "title": turn["q"][:140] or "Conversation", "turns": "[]"})
    turns = json.loads(doc.turns or "[]")
    if int(replace or 0):
        for i in range(len(turns) - 1, -1, -1):
            if turns[i].get("q") == turn["q"]:
                turns[i] = turn
                break
        else:
            turns.append(turn)
    else:
        turns.append(turn)
    doc.turns = json.dumps(turns[-MAX_TURNS:], default=str)
    doc.turn_count = len(turns[-MAX_TURNS:])
    doc.last_at = now_datetime()
    doc.save() if not doc.is_new() else doc.insert()
    return {"name": doc.name, "title": doc.title}


@frappe.whitelist(methods=["POST"])
def remove(name: str):
    doc = _mine(name)
    frappe.delete_doc(DOCTYPE, doc.name)
    return {"removed": name}


def _mine(name: str):
    require_manager()
    doc = frappe.get_doc(DOCTYPE, name)
    if doc.owner != frappe.session.user:
        frappe.throw("That conversation belongs to someone else.", frappe.PermissionError)
    return doc
