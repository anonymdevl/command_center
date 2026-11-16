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
    """"All businesses" is a view, not a place to put work: that means the default one."""
    from command_center.api.businesses import default_business_code
    if business_code and business_code != "__all__":
        return business_code
    code = default_business_code()
    if not code:
        frappe.throw("No business is registered, so there is nowhere to put the work.")
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

# Handing out work. Every path ends with the person told, in their own ERPNext:
#
#   about one ERPNext document   ERPNext's own assignment (frappe.desk.form.assign_to.add,
#                                connectors' assign()): the To-Do with assigned_by = the
#                                manager, the document's Assigned To, the "assigned"
#                                comment on it, and the Assignment notification (bell,
#                                and email if their Notification Settings allow).
#   in a project                 a Task in that project, assigned to them the same way.
#   about no single document     a To-Do from the manager, then a mention of them on it
#                                (frappe.desk.form.utils.add_comment), which is how
#                                ERPNext notifies anyone of anything not assigned on a
#                                document. A Notification Log cannot be written instead:
#                                no role has create on it (v14-v16), only Administrator.
#
# An inserted ToDo on its own notifies nobody, which is what this replaced (16 Nov 2026).
# A ToDo never references one of the platform's own doctypes: "Command Center Alert" is
# not a doctype on a business's ERPNext, so the link would not validate there. The alert
# is named in the description instead, and the alert records the To-Do (alerts.act).

TODO_PRIORITIES = ("Low", "Medium", "High")
TASK_PRIORITIES = ("Low", "Medium", "High", "Urgent")


@frappe.whitelist()
def assign_to(business_code: str, doctype: str, name: str, to_user: str,
              description: str | None = None, due_date: str | None = None,
              priority: str | None = None):
    """Put a record on somebody's desk with ERPNext's own assignment, so they are told."""
    return _assign(_conn(business_code), doctype, name, to_user,
                   description or f"{doctype} {name}", due_date, priority)


@frappe.whitelist()
def add_comment(business_code: str, doctype: str, name: str, text: str):
    """Leave a note on the record, attributed to the acting user.

    Through the form's own comment endpoint: anyone who may read the record may comment
    on it, where inserting a Comment directly needs System Manager."""
    return _conn(business_code).comment(doctype, name, text)


@frappe.whitelist()
def create_task(business_code: str, subject: str, description: str = "",
                allocated_to: str | None = None, due_date: str | None = None,
                project: str | None = None, priority: str | None = None,
                reference_type: str | None = None, reference_name: str | None = None,
                alert: str | None = None):
    """Hand a piece of work to a colleague in the business's ERPNext, as the manager.

    `reference_type`/`reference_name` name the ERPNext document it concerns, if any;
    `alert` the platform alert it was raised from, whose records decide the document
    when they are exactly one (facts.single_document). Work in a project becomes a Task
    there. Each case and what ERPNext does is set out above.

    Returns the To-Do (`name`, `url`), the document or Task, and in plain words what was
    done (`said`) and whether the person was notified (`notified`: True; False, with the
    reason in `notice`; None when they are the sender). A refused notification is
    reported, never raised: the To-Do stands either way.
    """
    if not allocated_to and not project:
        frappe.throw("Choose who this goes to.")
    conn = _conn(business_code)
    body = subject if not description else f"{subject}\n\n{description}"
    if _platform_doctype(reference_type):
        # An older screen passed the alert as the reference; it is the source, not a link.
        alert, reference_type, reference_name = alert or reference_name, None, None
    source = _alert_source(alert, conn.code)
    document = None
    if source:
        body += f"\n\nFrom {_product()}: the alert “{source['title']}”."
        document = source["document"]
    elif reference_type and reference_name:
        document = {"doctype": reference_type, "name": reference_name}

    if project:
        task = {"doctype": "Task", "subject": subject, "description": description,
                "project": project, "exp_end_date": due_date, "status": "Open"}
        if priority in TASK_PRIORITIES:
            task["priority"] = priority
        task = conn.insert(task)
        if not allocated_to:
            return {"name": None, "task": task["name"], "url": None,
                    "document": _doc(conn, "Task", task["name"]), "notified": None,
                    "said": f"Task {task['name']} is in project {project}, assigned to no one.",
                    "notice": "No one was chosen, so no one was told."}
        out = _assign(conn, "Task", task["name"], allocated_to, body, due_date, priority)
        out["task"] = task["name"]
        if not out.get("already"):
            out["said"] = (f"Task {task['name']} is in project {project}, assigned to "
                           f"{out['to_name']}{_due(due_date)}, and on their To-Do list.")
        return out
    if document:
        return _assign(conn, document["doctype"], document["name"], allocated_to, body,
                       due_date, priority)
    return _todo(conn, allocated_to, subject, body, due_date, priority)


def _assign(conn, doctype, name, user, body, due_date, priority):
    """ERPNext's own assignment of one document (see above), and what came of it."""
    me = conn.whoami()
    who, _mentionable = _person(conn, user)
    prio = priority if priority in TODO_PRIORITIES else None
    mine = _todo_from(conn, me, user, doctype, name)
    out = {"to": user, "to_name": who, "document": _doc(conn, doctype, name), "task": None,
           "already": False}
    if mine:
        # assign_to.add would decline the duplicate and tell no one.
        return {**out, **_todo_link(conn, mine), "already": True, "notified": False,
                "said": f"{doctype} {name} was already on {who}’s To-Do list, from you.",
                "notice": f"ERPNext does not assign the same document to someone twice, so "
                          f"{who} was not notified again."}
    answer = conn.assign(doctype, name, [user], description=body, date=due_date,
                         priority=prio)
    mine = _todo_from(conn, me, user, doctype, name)
    if not mine:
        # Already theirs from someone else: ERPNext kept that one and told no one.
        theirs = next((a.get("name") for a in answer or [] if a.get("owner") == user), None)
        return {**out, **_todo_link(conn, theirs), "already": True, "notified": False,
                "said": f"{doctype} {name} was already assigned to {who} by someone else.",
                "notice": f"ERPNext does not assign the same document to someone twice, so "
                          f"{who} was not notified again, and it is not on your Outstanding "
                          f"Tasks."}
    said = (f"{doctype} {name} is assigned to {who} in ERPNext, and is on their To-Do "
            f"list{_due(due_date)}, from you.")
    if user == me:
        return {**out, **_todo_link(conn, mine), "notified": None, "said": said,
                "notice": "It is on your own list, so there was no one to notify."}
    return {**out, **_todo_link(conn, mine), "notified": True, "said": said,
            "notice": f"ERPNext has notified {who}: under the bell in ERPNext, and by "
                      f"email if their notification settings allow."}


def _todo(conn, user, subject, body, due_date, priority):
    """A To-Do about no single document, from the manager, and a mention to tell them."""
    me = conn.whoami()
    who, mentionable = _person(conn, user)
    # assigned_by is what puts it on the sender's Outstanding Tasks (api/work.py).
    todo = {"doctype": "ToDo", "description": body, "allocated_to": user, "date": due_date,
            "status": "Open", "assigned_by": me}
    if priority in TODO_PRIORITIES:
        todo["priority"] = priority
    todo = conn.insert(todo)
    out = {"to": user, "to_name": who, "document": None, "task": None, "already": False,
           **_todo_link(conn, todo.get("name")),
           "said": f"It is on {who}’s To-Do list in ERPNext{_due(due_date)}, from you."}
    if user == me:
        return {**out, "notified": None,
                "notice": "It is on your own list, so there was no one to notify."}
    reason = None
    if mentionable is False:
        reason = ("their ERPNext user has Allowed In Mentions switched off, and a mention "
                  "is how ERPNext tells someone about a To-Do that is not on a document")
    else:
        try:
            conn.comment("ToDo", todo["name"],
                         _mention(user, who, subject, due_date, frappe.session.user))
        except Exception as e:
            reason = f"ERPNext refused the mention that tells them ({_plain_error(e)})"
    if reason:
        return {**out, "notified": False,
                "notice": f"{who} could not be notified: {reason}. The To-Do stands; tell "
                          f"them yourself."}
    return {**out, "notified": True,
            "notice": f"ERPNext has notified {who} by mentioning them on the To-Do: under "
                      f"the bell in ERPNext, and by email if their notification settings "
                      f"allow."}


def _todo_from(conn, me, user, doctype, name):
    """The open To-Do this manager gave this person on this document, if any. Only
    ones the manager assigned: an ordinary user cannot read anyone else's."""
    rows = conn.get_list("ToDo", filters={"reference_type": doctype, "reference_name": name,
                                          "allocated_to": user, "assigned_by": me,
                                          "status": "Open"},
                         fields=["name"], order_by="creation desc", limit=1)
    return rows[0]["name"] if rows else None


def _todo_link(conn, todo):
    return {"name": todo, "url": conn.desk_url("ToDo", todo) if todo else None}


def _doc(conn, doctype, name):
    return {"doctype": doctype, "name": name, "url": conn.desk_url(doctype, name)}


def _person(conn, user):
    """Their name, and whether ERPNext lets them be mentioned (None: not known)."""
    try:
        rows = conn.get_list("User", filters={"name": user},
                             fields=["name", "full_name", "allowed_in_mentions"], limit=1)
    except Exception:
        rows = []
    row = rows[0] if rows else {}
    flag = row.get("allowed_in_mentions")
    mentionable = None if flag is None else str(flag) not in ("0", "False", "false")
    return row.get("full_name") or frappe.utils.get_fullname(user) or user, mentionable


def _mention(user, who, subject, due_date, sender):
    """The comment that tells them: a mention, as the desk writes one."""
    from html import escape

    by = f" by {_day(due_date)}" if due_date else ""
    return (f'<p><span class="mention" data-id="{escape(user)}" data-value="{escape(who)}" '
            f'data-denotation-char="@">@{escape(who)}</span> '
            f'{escape(frappe.utils.get_fullname(sender) or sender)} has put this on your '
            f'To-Do list{by}: {escape(subject)}</p>')


def _alert_source(alert, code):
    """The platform alert work was raised from: its title, and the one ERPNext document
    behind it, if its records are exactly one."""
    if not alert:
        return None
    import json

    from command_center.alerts.engine import DOCTYPE
    from command_center.api.facts import single_document
    try:
        doc = frappe.get_doc(DOCTYPE, alert)
    except frappe.DoesNotExistError:
        return None
    if doc.business_code != code:
        return None   # another business's alert says nothing about this one
    try:
        filters = json.loads(doc.drill_filters or "{}")
    except ValueError:
        filters = {}
    return {"title": doc.title, "document": single_document(doc.drill_fact, filters, code)}


def _platform_doctype(doctype) -> bool:
    """One of the platform's own doctypes, which a business's ERPNext does not have."""
    return bool(doctype) and doctype in _own_doctypes()


def _own_doctypes() -> frozenset:
    global _OWN
    if _OWN is None:
        import glob
        import json
        import os
        folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "command_center", "doctype")
        _OWN = frozenset(json.load(open(p))["name"]
                         for p in glob.glob(os.path.join(folder, "*", "*.json")))
    return _OWN


_OWN = None


def _product() -> str:
    from command_center.branding import branding
    return branding().get("product") or "the platform"


def _day(date) -> str:
    from frappe.utils import getdate
    d = getdate(date)
    return f"{d.day} {d:%b %Y}"


def _due(date) -> str:
    return f", due {_day(date)}" if date else ""


def _plain_error(e) -> str:
    text = " ".join(str(e).split())
    return text[:300] or type(e).__name__
