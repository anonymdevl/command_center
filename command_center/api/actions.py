"""What a manager can do from the platform.

The answer is: whatever their ERPNext account already lets them do, in whichever
business they hold an account. This module adds no restriction of its own and is
not meant to.

That matters because the platform's value is that a decision can be made where it
is noticed. A CEO who sees an approval sitting unattended for nine days should be
able to act on it there, not be told to go and log in somewhere else. Every call
below runs as that person — locally through `frappe.set_user`, remotely through
their own API credential on the owning site — so the site holding the record
validates it, applies its permissions, fires its own hooks, and writes its own
Version record naming them.

There is exactly one thing this module will not do: reach past ERPNext. No raw
SQL, no `ignore_permissions`, no `ignore_validate`, no direct `db.set_value` on a
business document. Everything goes through the front door, which is the only way
the numbers stay trustworthy and the history stays complete.

The assistant does not call this module. See ai_tools.py.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager
from command_center.connectors.registry import connector_for


def _conn(business_code: str):
    require_manager()
    return connector_for(_business(business_code), acting_user=frappe.session.user)


def _business(business_code: str | None) -> str:
    """"All businesses" is a view, not a place to put work: that means this site's own."""
    if business_code and business_code != "__all__":
        return business_code
    code = frappe.db.get_value("Connected Business", {"is_local": 1}, "business_code")
    if not code:
        frappe.throw("No business on this site is marked as local, so there is nowhere to put the work.")
    return code


@frappe.whitelist()
def people(business_code: str | None = None):
    """Who work can be put on: the enabled staff accounts of the business, by name.

    Names and logins only. For this site read as the system -- a manager may not hold
    read on User, and an assignment form with nobody in it helps no one; for a peer,
    through that site's own API, so its permissions decide.
    """
    require_manager()
    code = _business(business_code)
    filters = {"enabled": 1, "user_type": "System User",
               "name": ["not in", ["Administrator", "Guest"]]}
    if frappe.db.get_value("Connected Business", {"business_code": code}, "is_local"):
        rows = frappe.get_all("User", filters=filters, fields=["name", "full_name"],
                              order_by="full_name asc", limit=500)
    else:
        rows = _conn(code).get_list("User", filters=filters, fields=["name", "full_name"], limit=500)
    return [{"user": r["name"], "name": r.get("full_name") or r["name"]} for r in rows]


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@frappe.whitelist()
def create_document(business_code: str, doctype: str, doc: dict | str):
    """Create anything the acting user is permitted to create."""
    doc = frappe.parse_json(doc) if isinstance(doc, str) else dict(doc)
    doc["doctype"] = doctype
    return _conn(business_code).insert(doc)


@frappe.whitelist()
def update_document(business_code: str, doctype: str, name: str,
                    changes: dict | str):
    """Apply field changes one at a time, each permission-checked."""
    changes = frappe.parse_json(changes) if isinstance(changes, str) else dict(changes)
    conn = _conn(business_code)
    result = None
    for fieldname, value in changes.items():
        result = conn.set_value(doctype, name, fieldname, value)
    return result


@frappe.whitelist()
def submit_document(business_code: str, doctype: str, name: str):
    return _conn(business_code).submit(doctype, name)


@frappe.whitelist()
def cancel_document(business_code: str, doctype: str, name: str):
    return _conn(business_code).cancel(doctype, name)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@frappe.whitelist()
def apply_workflow_action(business_code: str, doctype: str, name: str,
                          action: str):
    """Drive a document through its workflow — approve, reject, return.

    ERPNext decides whether this person holds the role the transition requires.
    The platform's contribution is that they saw it needed doing.
    """
    return _conn(business_code).apply_workflow(doctype, name, action)


# ---------------------------------------------------------------------------
# Delegation and correspondence
# ---------------------------------------------------------------------------

@frappe.whitelist()
def assign_to(business_code: str, doctype: str, name: str, to_user: str,
              description: str | None = None, due_date: str | None = None):
    """Put a record on somebody's desk, using ERPNext's own assignment."""
    conn = _conn(business_code)
    return conn.insert({
        "doctype": "ToDo",
        "allocated_to": to_user,
        "reference_type": doctype,
        "reference_name": name,
        "description": description or f"{doctype} {name}",
        "date": due_date,
        "status": "Open",
    })


@frappe.whitelist()
def add_comment(business_code: str, doctype: str, name: str, text: str):
    """Leave a note on the record, attributed to the acting user."""
    conn = _conn(business_code)
    return conn.insert({
        "doctype": "Comment",
        "comment_type": "Comment",
        "reference_doctype": doctype,
        "reference_name": name,
        "content": text,
    })


@frappe.whitelist()
def create_task(business_code: str, subject: str, description: str = "",
                allocated_to: str | None = None, due_date: str | None = None,
                project: str | None = None, priority: str | None = None,
                reference_type: str | None = None, reference_name: str | None = None):
    """Work attached to a job becomes a Task where the engineers already look.
    Work belonging to nothing becomes a ToDo."""
    conn = _conn(business_code)
    if project:
        return conn.insert({
            "doctype": "Task", "subject": subject, "description": description,
            "project": project, "exp_end_date": due_date, "status": "Open",
        })
    body = subject if not description else f"{subject}\n\n{description}"
    # assigned_by is what puts it on the sender's Outstanding Tasks (api/work.py).
    todo = {"doctype": "ToDo", "description": body, "allocated_to": allocated_to,
            "date": due_date, "status": "Open", "assigned_by": frappe.session.user}
    if priority in ("Low", "Medium", "High"):
        todo["priority"] = priority
    # Work raised from an alert points back at it, so the alert shows who has it.
    if reference_type and reference_name:
        todo["reference_type"], todo["reference_name"] = reference_type, reference_name
    return conn.insert(todo)
