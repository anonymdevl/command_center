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

from contextlib import contextmanager

import frappe

from command_center.api.businesses import require_manager
from command_center.connectors.registry import connector_for

ALL = "__all__"


class NotConfirmed(frappe.ValidationError):
    """A write ERPNext did not confirm: it may have gone through. The dialogs recognise
    this exc_type and say "check before trying again" (ActionDialog.jsx)."""


class MovedOn(frappe.ValidationError):
    """A decision on a card the document has moved on from (DocumentChanged): nothing was
    done. The dialog reads the queue again when it sees this exc_type."""


def _conn(business_code: str):
    require_manager()
    return connector_for(_business(business_code), acting_user=frappe.session.user)


def _business(business_code: str | None) -> str:
    """The one business a write goes to: the business of the record it acts on.

    Every action names it -- the alert's, the task row's, the approval card's, the
    drawer's (legacy/alerts.js, legacy/work.js, TaskDrawer.jsx) -- because "All
    businesses" is a view, not a place to put work. It used to mean the default business,
    so an alert of business B assigned from "All businesses" put B's document name on A's
    ERPNext and recorded A's To-Do on B's alert (17 Nov 2026). Now it is refused, with a
    reason, and the screen's scope is never used in its place. Only when no business is
    named and exactly one is registered is that one meant: there is nothing to confuse."""
    if business_code and business_code != ALL:
        return business_code
    if not business_code:
        codes = frappe.get_all("Connected Business", pluck="business_code", limit=2)
        if len(codes) == 1:
            return codes[0]
        if not codes:
            frappe.throw("No business is registered, so there is nowhere to put the work.")
    frappe.throw("This changes a record in one business’s ERPNext, and “All businesses” is "
                 "not one. Open it from the business it belongs to, or choose that business "
                 "at the top, then try again.")


def _unsure(e) -> bool:
    """Whether a failed write may still have been made: a lost answer (WriteNotConfirmed,
    by name, so the transport's own copy is caught too) or any other failure short of a
    definite refusal -- a timeout or 5xx can follow a write the far site made. A 4xx
    refusal (RequestRefused, RemotePermissionDenied) or a validation error is definite."""
    from command_center.connectors.base import (BusinessUnreachable, RequestRefused,
                                                WriteUnconfirmed)
    if isinstance(e, WriteUnconfirmed):
        return True
    return isinstance(e, BusinessUnreachable) and not isinstance(e, RequestRefused)


@contextmanager
def _says_why():
    """The edge of every write: a connector's failure in words, never "Something went
    wrong on the platform" (a ConnectorError is not a Frappe error, so the web layer would
    hide it). A write that may have gone through says so (NotConfirmed); a card the
    document has moved on from says where it is now (MovedOn)."""
    from command_center.connectors.base import ConnectorError, DocumentChanged
    try:
        yield
    except DocumentChanged as e:
        frappe.throw(str(e), MovedOn)
    except ConnectorError as e:
        if _unsure(e):
            frappe.throw(f"ERPNext did not confirm it ({_plain_error(e)}). It may have gone "
                         f"through: check in ERPNext before trying again.", NotConfirmed)
        frappe.throw(_plain_error(e))


@frappe.whitelist()
def people(business_code: str | None = None):
    """Who work can be put on: the enabled staff accounts of the business, by name.

    Names and logins only. For this site read as the system -- a manager may not hold
    read on User, and an assignment form with nobody in it helps no one; for a peer,
    through that site's own API, so its permissions decide. The business is the record's
    (_business): the picker never lists another business's people.
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
    conn = _conn(business_code)
    with _says_why():
        return conn.insert(doc)


@frappe.whitelist()
def update_document(business_code: str, doctype: str, name: str,
                    changes: dict | str):
    """Apply field changes one at a time, each permission-checked."""
    changes = frappe.parse_json(changes) if isinstance(changes, str) else dict(changes)
    conn = _conn(business_code)
    result = None
    with _says_why():
        for fieldname, value in changes.items():
            result = conn.set_value(doctype, name, fieldname, value)
    return result


@frappe.whitelist()
def submit_document(business_code: str, doctype: str, name: str):
    conn = _conn(business_code)
    with _says_why():
        return conn.submit(doctype, name)


@frappe.whitelist()
def cancel_document(business_code: str, doctype: str, name: str):
    conn = _conn(business_code)
    with _says_why():
        return conn.cancel(doctype, name)


# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@frappe.whitelist()
def apply_workflow_action(business_code: str, doctype: str, name: str,
                          action: str, expected_state: str | None = None,
                          expected_modified: str | None = None,
                          state_field: str | None = None):
    """Drive a document through its workflow — approve, reject, return.

    ERPNext decides whether this person holds the role the transition requires.
    The platform's contribution is that they saw it needed doing.

    The card sends the workflow state it showed (`expected_state`, required) and the
    document's modified stamp then (`expected_modified`). ERPNext applies an action to
    the document's CURRENT state, so on a stale card "Approve" pressed at L1, after
    someone else had approved L1, would perform L2. The document is read fresh and the
    action refused when it has moved on (connectors' apply_workflow, base.check_unchanged):
    "This was already moved to <state> by someone else".
    """
    if not (expected_state or "").strip():
        frappe.throw("This approval card does not say which step it showed, so it cannot be "
                     "checked against ERPNext. Refresh the screen and decide again.")
    conn = _conn(business_code)
    expected = {"field": state_field or _state_field(conn, doctype),
                "state": expected_state, "modified": expected_modified or None}
    with _says_why():
        return conn.apply_workflow(doctype, name, action, expected=expected)


def _state_field(conn, doctype) -> str:
    """The field the document's active workflow keeps its state in (workflow_state
    unless the workflow names another), read as the manager."""
    try:
        rows = conn.get_list("Workflow", filters={"document_type": doctype, "is_active": 1},
                             fields=["name", "workflow_state_field"], limit=1)
    except Exception:
        rows = []
    return (rows[0].get("workflow_state_field") if rows else None) or "workflow_state"


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
    conn = _conn(business_code)
    with _says_why():
        return _assign(conn, doctype, name, to_user, description or f"{doctype} {name}",
                       due_date, priority)


@frappe.whitelist()
def add_comment(business_code: str, doctype: str, name: str, text: str):
    """Leave a note on the record, attributed to the acting user.

    Through the form's own comment endpoint: anyone who may read the record may comment
    on it, where inserting a Comment directly needs System Manager. The text is the
    person's own words, so it is escaped (_note_html): never markup of theirs."""
    conn = _conn(business_code)
    with _says_why():
        return conn.comment(doctype, name, _note_html(text))


@frappe.whitelist()
def create_task(business_code: str, subject: str, description: str = "",
                allocated_to: str | None = None, due_date: str | None = None,
                project: str | None = None, priority: str | None = None,
                reference_type: str | None = None, reference_name: str | None = None,
                alert: str | None = None, escalate_of: str | None = None,
                escalate_todo: str | None = None):
    """Hand a piece of work to a colleague in the business's ERPNext, as the manager.

    `reference_type`/`reference_name` name the ERPNext document it concerns, if any;
    `alert` the platform alert it was raised from, whose records decide the document
    when they are exactly one (facts.single_document). Work in a project becomes a Task
    there. Each case and what ERPNext does is set out above.

    `escalate_of` makes it an escalation of that person's work to `allocated_to` -- their
    manager in ERPNext (manager_of), or whoever the sender chose instead -- by the same
    paths, High unless said otherwise; the description says whose work it is and who
    escalated it; and the person whose work it is is told, by a mention in a comment on
    the document, else on their own To-Do (`escalate_todo`), else on the new one. They
    are never unassigned. See "Escalation" below.

    Returns the To-Do (`name`, `url`), the document or Task, and in plain words what was
    done (`said`) and whether the person was notified (`notified`: True; False, with the
    reason in `notice`; None when they are the sender). A refused notification is
    reported, never raised: the To-Do stands either way. An escalation also returns
    `escalation`: whose work it was, whether it went to their manager in ERPNext, and
    whether they were told (`told`, `told_notice`: the same three values).
    """
    if not allocated_to and not project:
        frappe.throw("Choose who this goes to.")
    conn = _conn(business_code)
    with _says_why():
        esc = None
        if escalate_of:
            esc = _escalation(conn, escalate_of, allocated_to)
            if not subject.startswith(ESCALATED):
                subject = ESCALATED + subject
            priority = priority or "High"
            description = esc["line"] + (f"\n\n{description}" if description else "")
        out = _hand_out(conn, subject, description, allocated_to, due_date, project, priority,
                        reference_type, reference_name, alert)
        if esc:
            _tell_escalated(conn, out, esc, subject, escalate_todo)
        return out


def _hand_out(conn, subject, description, allocated_to, due_date, project, priority,
              reference_type, reference_name, alert):
    body = subject if not description else f"{subject}\n\n{description}"
    if _platform_doctype(reference_type):
        # An older screen passed the alert as the reference; it is the source, not a link.
        alert, reference_type, reference_name = alert or reference_name, None, None
    _own_alert(alert, conn)
    source = _alert_source(alert, conn.code)
    document = None
    if source:
        body += f"\n\nFrom {_product()}: the alert “{source['title']}”."
        document = source["document"]
    elif reference_type and reference_name:
        document = {"doctype": reference_type, "name": reference_name}

    if project:
        # A Task an earlier try made (its answer lost) is used, not made again.
        task_name = _recent_task(conn, project, subject)
        if not task_name:
            task = {"doctype": "Task", "subject": subject, "description": description,
                    "project": project, "exp_end_date": due_date, "status": "Open"}
            if priority in TASK_PRIORITIES:
                task["priority"] = priority
            task_name = conn.insert(task)["name"]
        if not allocated_to:
            return {"name": None, "task": task_name, "url": None,
                    "document": _doc(conn, "Task", task_name), "notified": None,
                    "said": f"Task {task_name} is in project {project}, assigned to no one.",
                    "notice": "No one was chosen, so no one was told."}
        task = {"name": task_name}
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
    """A To-Do about no single document, from the manager, and a mention to tell them.

    Idempotent, because a write whose answer is lost may still have been made
    (WriteNotConfirmed) and the person is then told to check and try again: an open To-Do
    from this manager to this person with the same text, made since yesterday, is the
    earlier try's and is used (`reused`), and the mention is sent only if that To-Do does
    not already carry one for them (_mentioned)."""
    me = conn.whoami()
    who, mentionable = _person(conn, user)
    name = _recent_todo(conn, me, user, body)
    reused = bool(name)
    if not reused:
        # assigned_by is what puts it on the sender's Outstanding Tasks (api/work.py).
        todo = {"doctype": "ToDo", "description": body, "allocated_to": user,
                "date": due_date, "status": "Open", "assigned_by": me}
        if priority in TODO_PRIORITIES:
            todo["priority"] = priority
        name = conn.insert(todo).get("name")
    out = {"to": user, "to_name": who, "document": None, "task": None, "already": False,
           "reused": reused, **_todo_link(conn, name),
           "said": (f"It was already on {who}’s To-Do list in ERPNext, from you ({name}): an "
                    f"earlier try had made it, so no second one was made." if reused else
                    f"It is on {who}’s To-Do list in ERPNext{_due(due_date)}, from you.")}
    if user == me:
        return {**out, "notified": None,
                "notice": "It is on your own list, so there was no one to notify."}
    if reused and _mentioned(conn, "ToDo", name, user):
        return {**out, "notified": True,
                "notice": f"ERPNext notified {who} when the earlier try mentioned them on it, "
                          f"so they were not notified again."}
    reason, unsure = None, False
    if mentionable is False:
        reason = ("their ERPNext user has Allowed In Mentions switched off, and a mention "
                  "is how ERPNext tells someone about a To-Do that is not on a document")
    else:
        try:
            conn.comment("ToDo", name, _mention(user, who, subject, due_date,
                                                frappe.session.user))
        except Exception as e:
            unsure = _unsure(e)
            reason = (f"ERPNext did not confirm the mention that tells them "
                      f"({_plain_error(e)})" if unsure else
                      f"ERPNext refused the mention that tells them ({_plain_error(e)})")
    if unsure:
        return {**out, "notified": None,
                "notice": f"{who} may not have been notified: {reason}. The To-Do stands; "
                          f"check with them."}
    if reason:
        return {**out, "notified": False,
                "notice": f"{who} could not be notified: {reason}. The To-Do stands; tell "
                          f"them yourself."}
    if mentionable is None:
        return {**out, "notified": None,
                "notice": f"ERPNext was asked to notify {who} by a mention on the To-Do, but "
                          f"their ERPNext user could not be read to check that mentions reach "
                          f"them, so they may not have been notified. Check with them."}
    return {**out, "notified": True,
            "notice": f"ERPNext has notified {who} by mentioning them on the To-Do: under "
                      f"the bell in ERPNext, and by email if their notification settings "
                      f"allow."}


RECENT_DAYS = 1


def _recent_todo(conn, me, user, body):
    """The open To-Do an earlier try left: from this manager (assigned_by, their login
    there), to this person, on no document, with the same text, made since yesterday in
    the business's time zone. A day, not minutes: the far site stamps `creation` in its
    own time zone, which the platform cannot always know, and an identical open To-Do
    from the same manager to the same person is never wanted twice."""
    from command_center.api.work import business_today
    since = str(frappe.utils.add_days(business_today(conn.code), -RECENT_DAYS))
    try:
        rows = conn.get_list("ToDo", filters={"allocated_to": user, "assigned_by": me,
                                              "status": "Open", "creation": [">=", since]},
                             fields=["name", "description", "reference_type",
                                     "reference_name"],
                             order_by="creation desc", limit=50)
    except Exception:
        return None
    want = _same_text(body)
    return next((r.get("name") for r in rows or []
                 if not r.get("reference_type") and not r.get("reference_name")
                 and _same_text(r.get("description")) == want), None)


def _recent_task(conn, project, subject):
    """The open Task an earlier try made in this project, with this subject, by this
    manager (owner, their login there), since yesterday: used rather than made again."""
    from command_center.api.work import business_today
    since = str(frappe.utils.add_days(business_today(conn.code), -RECENT_DAYS))
    try:
        rows = conn.get_list("Task", filters={"project": project, "owner": conn.whoami(),
                                              "status": "Open", "creation": [">=", since]},
                             fields=["name", "subject"], order_by="creation desc", limit=50)
    except Exception:
        return None
    want = _same_text(subject)
    return next((r.get("name") for r in rows or [] if _same_text(r.get("subject")) == want),
                None)


def _same_text(text) -> str:
    """Text as ERPNext may hand it back: markup stripped, spacing collapsed."""
    return " ".join(frappe.utils.strip_html(str(text or "")).split())


def _mentioned(conn, doctype, name, user, phrase: str | None = None):
    """Whether a comment on the record already mentions this person (and, given a
    phrase, says it): True, False, or None when the comments cannot be read (the form's
    own load, getdoc -> docinfo.comments, which anyone who may read the record may
    call)."""
    from html import escape
    needle = f'data-id="{escape(user)}"'
    try:
        if conn.is_local:
            rows = conn.get_list("Comment", filters={"reference_doctype": doctype,
                                                     "reference_name": name,
                                                     "comment_type": "Comment"},
                                 fields=["content"], limit=200)
        else:
            got = conn._call("frappe.desk.form.load.getdoc",
                             {"doctype": doctype, "name": name}, whole=True)
            info = got.get("docinfo") if isinstance(got, dict) else None
            rows = info.get("comments") if isinstance(info, dict) else None
            if not isinstance(rows, list):
                return None
    except Exception:
        return None
    return any(needle in str(r.get("content") or "")
               and (not phrase or phrase in str(r.get("content") or "")) for r in rows)


# ---------------------------------------------------------------------------
# Managing work already handed out: reassign, withdraw, change its date or priority
# ---------------------------------------------------------------------------
#
# Only on an open To-Do this manager handed out (assigned_by = their login there), and
# only through the front door, as them:
#
#   reassign   GIVE FIRST, REMOVE AFTER (17 Nov 2026). On a document: assign_to.add for
#              the new person (connectors' assign()), and only once that has worked
#              assign_to.remove for the old one (unassign()), so ERPNext moves Assigned
#              To, cancels the old To-Do and notifies both. A To-Do of its own: a new
#              To-Do with the same subject and details plus a mention for the new person,
#              and only then the old one's status Cancelled (frappe.client.set_value).
#              If the giving fails nothing has been taken from anyone and the error says
#              so; if the removing fails, both have it and the answer says so. Either way
#              a comment on the document (else the old To-Do) mentions the person it was
#              taken from: who moved it, from whom, to whom. (It used to remove first: a
#              refused add left the work with nobody, and a retry was refused because the
#              old To-Do was no longer open.)
#   cancel     on a document: assign_to.remove; a To-Do of its own: status Cancelled.
#              A mention in a comment tells them it was withdrawn.
#   close      finished, or no longer needed: status Closed (frappe.client.set_value) and
#              a plain comment on the To-Do, "Closed by <name>" and the note. No mention,
#              so no notification, and no assign_to.remove on a linked document.
#   bulk       bulk_tasks: close or cancel each of up to BULK_LIMIT, one by one, through
#              the same paths and checks, as a background job the dialog follows
#              (bulk_status): 200 tasks at about four calls each outlast a web request.
#              One that fails is reported and the rest go on; the summary says how many
#              were told and who was not, and why.
#   edit       the To-Do's date and priority (frappe.client.set_value), and a mention
#              on it telling them what changed.

@frappe.whitelist()
def reassign_task(business_code: str, todo: str, to_user: str, note: str = ""):
    """Move open work this manager handed out to someone else, without escalating."""
    if not to_user:
        frappe.throw("Choose who it goes to now.")
    conn = _conn(business_code)
    with _says_why():
        return _reassign(conn, todo, to_user, note)


def _reassign(conn, todo, to_user, note=""):
    row = _handed_out_todo(conn, todo)
    old = row.get("allocated_to")
    if to_user == old:
        frappe.throw("It is already with them. Choose someone else.")
    old_name, old_ok = _person(conn, old)
    new_name = _person(conn, to_user)[0]
    sender = _sender()
    body = (row.get("description") or "").strip()
    subject = _subject(body) or todo
    if note.strip():
        body = f"{body}\n\n{note.strip()}" if body else note.strip()
    doctype, name = row.get("reference_type"), row.get("reference_name")
    on_doc = bool(doctype and name)

    # 1. Give it to the new person. Nothing is taken from anyone until this has worked.
    try:
        if on_doc:
            out = _assign(conn, doctype, name, to_user, body, row.get("date"),
                          row.get("priority"))
        else:
            out = _todo(conn, to_user, subject, body, row.get("date"), row.get("priority"))
    except Exception as e:
        if _unsure(e):
            frappe.throw(f"ERPNext did not confirm giving it to {new_name} "
                         f"({_plain_error(e)}). It may have gone through: check "
                         f"{_first(new_name)}’s To-Do list in ERPNext before trying again. "
                         f"Nothing was taken off {old_name}, and trying again here will not "
                         f"give it to {_first(new_name)} twice.", NotConfirmed)
        frappe.throw(f"ERPNext did not give it to {new_name} ({_plain_error(e)}). Nothing "
                     f"changed: it is still with {old_name}.")

    # 2. Only now take it off the person it was with.
    if on_doc:
        where, label = {"doctype": doctype, "name": name}, f"{doctype} {name}"
    else:
        where, label = {"doctype": "ToDo", "name": todo}, f"their To-Do {todo}"
    removed, removed_notice = True, None
    try:
        if on_doc:
            conn.unassign(doctype, name, old)
        else:
            conn.set_value("ToDo", todo, "status", "Cancelled")
    except Exception as e:
        fix = (f"take {_first(old_name)} off Assigned To on {label} in ERPNext" if on_doc
               else f"cancel {label} in ERPNext")
        if _unsure(e):
            removed = None
            removed_notice = (f"{new_name} has it now, but ERPNext did not confirm taking it "
                              f"off {old_name} ({_plain_error(e)}), so {_first(old_name)} may "
                              f"still have it. Check, and if so {fix}.")
        else:
            removed = False
            removed_notice = (f"{new_name} has it now, but ERPNext did not take it off "
                              f"{old_name} ({_plain_error(e)}): both have it. To finish, "
                              f"{fix}.")

    line = f"Reassigned by {sender} from {old_name} to {new_name}"
    told, told_notice = _tell(conn, where, old, old_name, old_ok,
                              f"{line}: {subject}.", label, "it was moved")
    out.update(reassigned_from=old, reassigned_from_name=old_name, told=told,
               told_notice=told_notice, removed=removed, removed_notice=removed_notice,
               said=f"{line}. {out.get('said') or ''}".strip())
    return out


@frappe.whitelist()
def cancel_task(business_code: str, todo: str, reason: str = ""):
    """Withdraw open work this manager handed out -- the wrong person, by mistake."""
    conn = _conn(business_code)
    with _says_why():
        return _cancel(conn, todo, reason)


def _cancel(conn, todo, reason=""):
    row = _handed_out_todo(conn, todo)
    user = row.get("allocated_to")
    who, ok = _person(conn, user)
    subject = _subject(row.get("description")) or todo
    doctype, name = row.get("reference_type"), row.get("reference_name")
    if doctype and name:
        conn.unassign(doctype, name, user)
        where, label = {"doctype": doctype, "name": name}, f"{doctype} {name}"
        said = (f"{doctype} {name} is no longer assigned to {who}: ERPNext has cancelled "
                f"their To-Do and taken them off Assigned To.")
    else:
        conn.set_value("ToDo", todo, "status", "Cancelled")
        where, label = {"doctype": "ToDo", "name": todo}, f"their To-Do {todo}"
        said = f"{who}’s To-Do {todo} is cancelled in ERPNext."
    why = f" {reason.strip()}" if (reason or "").strip() else ""
    notified, notice = _tell(conn, where, user, who, ok,
                             f"{_sender()} has withdrawn this: {subject}. You no longer need "
                             f"to do it.{why}", label, "it was withdrawn")
    return {"ok": True, "name": todo, "status": "Cancelled", "to": user, "to_name": who,
            "said": said, "notified": notified, "notice": notice}


@frappe.whitelist()
def close_task(business_code: str, todo: str, note: str = ""):
    """Close open work this manager handed out: finished, or no longer needed.

    Not Cancel ("withdrawn"): the To-Do's status becomes Closed through the front door
    (frappe.client.set_value), and a short comment on the To-Do says who closed it, with
    the note if one is given. Nobody is mentioned, so nobody is notified, and the person
    is not taken off a linked document with assign_to.remove (which would send them ERPNext's
    "assignment removed" notification). A To-Do the manager closed is not "Delegated Tasks
    Done" (api/work: its modified_by is the manager's own login there)."""
    conn = _conn(business_code)
    with _says_why():
        return _close(conn, todo, note)


def _close(conn, todo, note=""):
    row = _handed_out_todo(conn, todo)
    user = row.get("allocated_to")
    who = _person(conn, user)[0]
    conn.set_value("ToDo", todo, "status", "Closed")
    note = (note or "").strip()
    text = f"Closed by {_sender()}." + (f" {note}" if note else "")
    try:
        conn.comment("ToDo", todo, _note_html(text))
        commented, notice = True, (f"A comment on the To-Do says you closed it. {who} was not "
                                   f"mentioned, so ERPNext did not notify them.")
    except Exception as e:
        commented, notice = False, (f"It is closed, but ERPNext refused the comment on the "
                                    f"To-Do ({_plain_error(e)}). {who} was not notified.")
    return {"ok": True, "name": todo, "status": "Closed", "to": user, "to_name": who,
            "said": f"{who}’s To-Do {todo} is closed in ERPNext.",
            "commented": commented, "notified": None, "notice": notice}


BULK_LIMIT = 200
BULK_ACTIONS = {"close": (_close, "closed"), "cancel": (_cancel, "cancelled")}
BULK_KEEP = 3600     # seconds a batch's progress is kept to be read
BULK_STALE = 180     # seconds without progress before a batch is said to have stopped


@frappe.whitelist()
def bulk_tasks(business_code: str, action: str, todos, note: str = ""):
    """Close or cancel many tasks this manager handed out, one by one, in the background.

    Each goes through the same path and the same checks as the single action (close_task,
    cancel_task: only open To-Dos this manager handed out), so Cancel tells each person the
    work was withdrawn and Close tells nobody. A task that fails is reported with the
    reason and does not stop the others. At most BULK_LIMIT in one call.

    Sent as a job (frappe.enqueue, as the reports and the deeper look are), because 200
    tasks at about four ERPNext calls each outlast nginx's 300-second wait on one request.
    Returns the batch as it starts ({bulk_id, state: "queued", total}); bulk_status says how
    far it has got, and at the end how many were told and who was not, and why."""
    import json

    if action not in BULK_ACTIONS:
        frappe.throw("The action is close or cancel.")
    if isinstance(todos, str):
        try:
            todos = json.loads(todos)
        except ValueError:
            todos = [t for t in todos.split(",")]
    if not isinstance(todos, list):
        frappe.throw("Send the tasks as a list.")
    todos = list(dict.fromkeys(str(t).strip() for t in todos if str(t or "").strip()))
    if not todos:
        frappe.throw("Choose at least one task.")
    if len(todos) > BULK_LIMIT:
        frappe.throw(f"{len(todos)} tasks were chosen; at most {BULK_LIMIT} can be changed "
                     f"at once. Choose fewer, or filter the list first.")
    conn = _conn(business_code)   # the business and the manager are checked before queuing
    bulk_id = frappe.generate_hash(length=16)
    state = {"bulk_id": bulk_id, "state": "queued", "action": action,
             "business_code": conn.code, "total": len(todos), "done": [], "failed": [],
             "updated": _clock()}
    _bulk_put(state)
    frappe.enqueue("command_center.api.actions._bulk_run", queue="long", timeout=1500,
                   bulk_id=bulk_id, business_code=conn.code, action=action, todos=todos,
                   note=note, user=frappe.session.user, enqueue_after_commit=False)
    return _bulk_view(_bulk_get(bulk_id) or state)


@frappe.whitelist()
def bulk_status(bulk_id: str):
    """How far a batch from bulk_tasks has got, read by the person who sent it: done and
    failed so far, and when it has finished, the summary (bulk_tasks). A batch that has
    made no progress for BULK_STALE seconds has stopped (the server restarted under it):
    it says how many were done, and that the rest were not changed."""
    require_manager()
    state = _bulk_get(bulk_id)
    if not state:
        return {"bulk_id": bulk_id, "state": "unknown", "done": [], "failed": [],
                "said": "This batch is no longer known here: it finished over an hour ago, "
                        "or the server restarted before it began. Look at the list to see "
                        "what changed."}
    if state["state"] in ("queued", "running") and \
            _clock() - float(state.get("updated") or 0) > BULK_STALE:
        state = {**state, "state": "stalled"}
    return _bulk_view(state)


def _bulk_run(bulk_id, business_code, action, todos, note, user):
    """The batch itself, as the person who sent it, one To-Do after another."""
    frappe.set_user(user)
    state = _bulk_get(bulk_id) or {"bulk_id": bulk_id, "action": action,
                                   "business_code": business_code, "total": len(todos),
                                   "done": [], "failed": []}
    state.update(state="running", updated=_clock())
    _bulk_put(state)
    try:
        conn = _conn(business_code)
        fn = BULK_ACTIONS[action][0]
        for todo in todos:
            try:
                res = fn(conn, todo, note)
            except Exception as e:
                state["failed"].append({"todo": todo, "reason": _plain_error(e),
                                        "unsure": _unsure(e)})
            else:
                state["done"].append({"todo": todo, "to": res.get("to"),
                                      "to_name": res.get("to_name"),
                                      "notified": res.get("notified"),
                                      "notice": res.get("notice")})
            state["updated"] = _clock()
            _bulk_put(state)
        state["state"] = "done"
    except Exception as e:
        frappe.log_error(title="Command Center bulk tasks", message=frappe.get_traceback())
        state.update(state="failed", error=_plain_error(e))
    state["updated"] = _clock()
    _bulk_put(state)


def _bulk_view(state) -> dict:
    """A batch in words: how many were done, which could not be and why, and -- for
    Cancel, which tells each person -- how many were told and who was not, and why."""
    action = state.get("action")
    word = BULK_ACTIONS.get(action, (None, "changed"))[1]
    done, failed = state.get("done") or [], state.get("failed") or []
    finished = state.get("state") in ("done", "failed", "stalled")
    told = [d for d in done if d.get("notified") is True]
    not_told = [{"todo": d["todo"], "to": d.get("to"), "to_name": d.get("to_name"),
                 "reason": d.get("notice") or ""} for d in done if d.get("notified") is not True]
    said = f"{len(done)} {word}"
    if failed:
        reasons = "; ".join(dict.fromkeys(f["reason"] for f in failed))
        said += f", {len(failed)} could not be: {reasons}"
    if action == "cancel" and done:
        said = said.rstrip(".") + (f". All {len(done)} were told." if not not_told else
                                   f". {len(told)} of {len(done)} were told; the others may "
                                   f"not know (listed below).")
    elif action == "close" and done:
        said = said.rstrip(".") + ". No one was mentioned, so no one was notified."
    if not finished:
        said = (f"Working: {len(done) + len(failed)} of {state.get('total') or '?'} so far. "
                f"It carries on if you close this.")
    elif state.get("state") == "stalled":
        said = (f"It stopped part-way: {said.rstrip('.')}. The other "
                f"{max((state.get('total') or 0) - len(done) - len(failed), 0)} were not "
                f"changed; select them again to finish.")
    elif state.get("state") == "failed":
        said = f"It stopped: {(state.get('error') or 'an error').rstrip('.')}. {said.rstrip('.')}."
    return {"bulk_id": state.get("bulk_id"), "state": state.get("state"), "action": action,
            "total": state.get("total"), "done": done, "failed": failed,
            "told": len(told) if action == "cancel" else None,
            "not_told": not_told if action == "cancel" else [], "said": said,
            "finished": finished}


def _bulk_key(bulk_id) -> str:
    return f"cc_bulk::{frappe.session.user}::{str(bulk_id)[:40]}"


def _bulk_put(state):
    frappe.cache().set_value(_bulk_key(state["bulk_id"]), state, expires_in_sec=BULK_KEEP)


def _bulk_get(bulk_id):
    return frappe.cache().get_value(_bulk_key(bulk_id))


def _clock() -> float:
    import time
    return time.time()


@frappe.whitelist()
def update_task(business_code: str, todo: str, due_date: str | None = None,
                priority: str | None = None):
    """Change the date and priority of open work this manager handed out."""
    if priority and priority not in TODO_PRIORITIES:
        frappe.throw("Priority is Low, Medium or High.")
    conn = _conn(business_code)
    with _says_why():
        return _update(conn, todo, due_date, priority)


def _update(conn, todo, due_date, priority):
    row = _handed_out_todo(conn, todo)
    changed = []
    if due_date is not None and str(due_date or "") != str(row.get("date") or ""):
        conn.set_value("ToDo", todo, "date", due_date or None)
        changed.append(f"due {_day(due_date)}" if due_date else "no due date")
    if priority and priority != (row.get("priority") or "Medium"):
        conn.set_value("ToDo", todo, "priority", priority)
        changed.append(f"priority {priority}")
    user = row.get("allocated_to")
    who, ok = _person(conn, user)
    if not changed:
        return {"ok": True, "name": todo, "changed": [], "said": "Nothing changed.",
                "notified": None, "notice": "Nothing changed, so no one was told."}
    what = " and ".join(changed)
    subject = _subject(row.get("description")) or todo
    notified, notice = _tell(conn, {"doctype": "ToDo", "name": todo}, user, who, ok,
                             f"{_sender()} has changed this to {what}: {subject}.",
                             f"their To-Do {todo}", "what changed")
    return {"ok": True, "name": todo, "changed": changed, "notified": notified,
            "notice": notice, "said": f"{who}’s To-Do {todo} is now {what}."}


def _handed_out_todo(conn, todo):
    """The open To-Do, if this manager handed it out; refused otherwise."""
    if not todo:
        frappe.throw("Which task?")
    rows = conn.get_list("ToDo", filters={"name": todo},
                         fields=["name", "status", "allocated_to", "assigned_by", "description",
                                 "reference_type", "reference_name", "date", "priority"],
                         limit=1)
    if not rows or rows[0].get("assigned_by") != conn.whoami():
        frappe.throw("Only the person who handed this out can change it.",
                     frappe.PermissionError)
    if rows[0].get("status") != "Open":
        frappe.throw(f"This task is {(rows[0].get('status') or 'not open').lower()} in "
                     f"ERPNext, so it can no longer be changed here.")
    return rows[0]


def _tell(conn, where, user, who, mentionable, text, label, what):
    """Tell someone by a mention in a comment on `where`; (notified, notice).

    notified is True when ERPNext was asked and will tell them; False when it was refused
    or ERPNext will not mention them; None when it is not known -- their user could not
    be read to check Allowed In Mentions, or ERPNext did not confirm the comment -- and
    for the manager's own work, where there is no one else to tell."""
    if user == conn.whoami():
        return None, "It was your own work, so there was no one else to tell."
    try:
        conn.comment(where["doctype"], where["name"], _mention_html(user, who, text))
    except Exception as e:
        if _unsure(e):
            return None, (f"{who} may not have been told {what}: ERPNext did not confirm the "
                          f"comment on {label} ({_plain_error(e)}). Check, or tell them "
                          f"yourself.")
        return False, (f"{who} could not be told {what}: ERPNext refused the comment on "
                       f"{label} ({_plain_error(e)}). Tell them yourself.")
    if mentionable is False:
        return False, (f"A comment on {label} says so, but {who}’s ERPNext user has Allowed "
                       f"In Mentions switched off, so ERPNext did not notify them. Tell them "
                       f"yourself.")
    if mentionable is None:
        return None, (f"A comment on {label} mentions {who}, but their ERPNext user could not "
                      f"be read to check that mentions reach them, so they may not have been "
                      f"notified. Check with them.")
    return True, (f"ERPNext has told {who} {what}, by mentioning them in a comment on "
                  f"{label}: under the bell in ERPNext, and by email if their notification "
                  f"settings allow.")


# Every comment written to a business's ERPNext is built by one of these two, and every
# value in it is escaped: a note, a subject, a name are the person's own words, never
# markup (preflight holds every comment() call to them).
def _mention_html(user, who, text) -> str:
    """A mention of `user`, as the desk writes one, then the text."""
    from html import escape

    return (f'<p><span class="mention" data-id="{escape(user)}" data-value="{escape(who)}" '
            f'data-denotation-char="@">@{escape(who)}</span> {escape(text)}</p>')


def _note_html(text) -> str:
    """A plain comment: no one mentioned, so no one notified."""
    from html import escape

    return f"<p>{escape(str(text or ''))}</p>"


def _subject(description) -> str:
    text = frappe.utils.strip_html(description or "").strip()
    return text.partition("\n")[0].strip()[:140]


def _sender() -> str:
    return frappe.utils.get_fullname(frappe.session.user) or frappe.session.user


# ---------------------------------------------------------------------------
# Escalation: up the line, to the manager ERPNext names
# ---------------------------------------------------------------------------
#
# Escalate asks whose work it is (whose_work pre-fills it: the To-Do's allocated_to, else
# the document's Assigned To), then reads that person's manager from ERPNext's own org
# chart: the Employee whose User ID is them, its Reports To (an Employee), and that
# Employee's User ID and name (manager_of). Every read goes through the acting manager's
# connector -- on another site under their OWN key, never the platform's service account
# -- so their ERPNext permissions decide what can be seen. When ERPNext names no manager,
# the answer says why and how to fix it there, and the sender picks someone by hand; the
# escalation then says it was chosen by hand. Nothing is ever sent to a guess.
#
# Sending is create_task(escalate_of=...): the manager gets it by the same paths as any
# assignment (document -> assign_to.add, else a To-Do and a mention), and the person whose
# work it is is told by a mention in a comment: on the document, else on their own To-Do,
# else on the manager's new one. They stay assigned.

ESCALATED = "Escalated: "


@frappe.whitelist()
def whose_work(business_code: str, doctype: str | None = None, name: str | None = None,
               todo: str | None = None, alert: str | None = None):
    """Who the work is with now, to pre-fill Escalate's "Whose work is this?".

    In order: the To-Do it was handed out as (`todo`, or the alert's), its allocated_to;
    else the document's Assigned To (`doctype`/`name`, or the alert's one document), the
    latest assignee who is not the sender. Read as the manager, so a To-Do they cannot
    see pre-fills nothing. Returns {user, name, via, todo}; user None when not known,
    which leaves the choice to the sender rather than guessing.
    """
    conn = _conn(business_code)
    if _platform_doctype(doctype):
        alert, doctype, name = alert or name, None, None
    if alert:
        todo = todo or _alert_todo(alert, conn.code)
        source = _alert_source(alert, conn.code)
        if source and source["document"] and not (doctype and name):
            doctype, name = source["document"]["doctype"], source["document"]["name"]
    if todo:
        user = _todo_of(conn, todo)
        if user:
            return {"user": user, "name": _person(conn, user)[0], "todo": todo,
                    "via": "the To-Do it was given out as"}
    if doctype and name:
        try:
            rows = conn.get_list(doctype, filters={"name": name}, fields=["name", "_assign"],
                                 limit=1)
        except Exception:
            rows = []
        assigned = _users(rows[0].get("_assign")) if rows else []
        me = conn.whoami()
        others = [u for u in assigned if u != me] or assigned
        if others:
            user = others[-1]
            return {"user": user, "name": _person(conn, user)[0], "todo": None,
                    "via": f"Assigned To on {doctype} {name}"}
    return {"user": None, "name": None, "via": None, "todo": None}


@frappe.whitelist()
def manager_of(business_code: str, user: str):
    """The person's manager in ERPNext: Employee (User ID = them) -> Reports To -> that
    Employee's User ID and name. Read as the acting manager.

    Found: {found: True, manager_user, manager_name, employee, manager_employee, via}.
    Not: {found: False, code, reason, fix}, code one of no_key (their own ERPNext key is
    not linked, so ERPNext cannot be asked as them), no_permission (Employee, its Reports
    To, or the manager's record is not readable by them), no_employee, no_reports_to,
    no_manager_user, unreadable (ERPNext did not answer). Both carry user and user_name.
    """
    if not user:
        frappe.throw("Choose whose work this is.")
    return _manager_of(_conn(business_code), user)


def _manager_of(conn, user):
    from command_center.connectors.base import BusinessUnreachable, RemotePermissionDenied

    who = _person(conn, user)[0]
    first = _first(who)
    out = {"found": False, "user": user, "user_name": who, "manager_user": None,
           "manager_name": None, "employee": None, "manager_employee": None,
           "via": None, "code": None, "reason": None, "fix": None}

    def no(code, reason, fix, **kw):
        return {**out, "code": code, "reason": reason, "fix": fix, **kw}

    def cannot(reason=None):
        return no("no_permission",
                  reason or f"You may not read Employee records in ERPNext, so {first}’s "
                            f"manager cannot be looked up as you.",
                  "Ask your ERPNext administrator to give your user read access to Employee "
                  "(the HR User role has it), or choose who it goes to yourself.")

    if not conn.is_local:
        from command_center.api.credentials import credential_for
        if not credential_for(conn.code, user=conn.acting_user):
            return no("no_key",
                      f"Your own ERPNext key is not linked, so ERPNext cannot be asked who "
                      f"{first}’s manager is as you.",
                      "Link your ERPNext key under Settings → ERPNext API Keys, or "
                      "choose who it goes to yourself.")
    try:
        rows = conn.get_list("Employee", filters={"user_id": user},
                             fields=["name", "employee_name", "reports_to", "status"],
                             order_by="modified desc", limit=5)
        if not rows:
            return no("no_employee",
                      f"No Employee record in ERPNext has {who}’s user ({user}) as its User "
                      f"ID, or none that you may see.",
                      f"In ERPNext, open {first}’s Employee record and set User ID to {user}, "
                      f"then set Reports To. Or choose who it goes to yourself.")
        row = next((r for r in rows if r.get("status") == "Active"), rows[0])
        out["employee"] = row.get("name")
        if "reports_to" not in row:
            # Frappe drops a field the acting roles may not read rather than refusing.
            return cannot(f"ERPNext lets you see {first}’s Employee record ({row.get('name')}) "
                          f"but not its Reports To.")
        if not row.get("reports_to"):
            return no("no_reports_to",
                      f"{first}’s Employee record ({row['name']}) has no Reports To.",
                      f"Open {first}’s Employee record ({row['name']}) in ERPNext and set "
                      f"Reports To. Or choose who it goes to yourself.")
        boss = conn.get_list("Employee", filters={"name": row["reports_to"]},
                             fields=["name", "employee_name", "user_id"], limit=1)
    except (frappe.PermissionError, RemotePermissionDenied):
        return cannot()
    except BusinessUnreachable as e:
        return no("unreadable",
                  f"ERPNext did not answer who {first}’s manager is ({_plain_error(e)}).",
                  "Try again in a moment, or choose who it goes to yourself.")
    if not boss or "user_id" not in boss[0]:
        return cannot(f"{first} reports to {row['reports_to']}, an Employee record you may "
                      f"not read in ERPNext.")
    boss = boss[0]
    name = boss.get("employee_name") or boss["name"]
    out.update(manager_employee=boss["name"], manager_name=name)
    if not boss.get("user_id"):
        return no("no_manager_user",
                  f"{first} reports to {name} ({boss['name']}), who has no user account in "
                  f"ERPNext: their Employee record has no User ID.",
                  f"Open {name}’s Employee record ({boss['name']}) in ERPNext and set User ID "
                  f"to their ERPNext user. Or choose who it goes to yourself.")
    return {**out, "found": True, "manager_user": boss["user_id"], "via": "Reports To"}


def _escalation(conn, of, to):
    """Whose work it is, who it goes to, and whether that is their manager in ERPNext."""
    if not to:
        frappe.throw("Choose who this is escalated to.")
    if of == to:
        frappe.throw("That is the person whose work it is. An escalation goes to someone "
                     "else: their manager.")
    of_name, mentionable = _person(conn, of)
    to_name = _person(conn, to)[0]
    found = _manager_of(conn, of)
    to_manager = bool(found["found"]) and found["manager_user"] == to
    sender = frappe.utils.get_fullname(frappe.session.user) or frappe.session.user
    if to_manager:
        tail = f"to {to_name}, their manager in ERPNext (Reports To)."
    elif found["found"]:
        tail = (f"to {to_name}, chosen by hand (ERPNext names {found['manager_name']} as "
                f"their manager).")
    else:
        tail = f"to {to_name}, chosen by hand: ERPNext names no manager for them."
    return {"of": of, "of_name": of_name, "mentionable": mentionable, "to": to,
            "to_name": to_name, "to_manager": to_manager, "sender": sender,
            "manager": {k: found[k] for k in ("found", "manager_user", "manager_name",
                                              "code", "reason")},
            "line": f"{of_name}’s work, escalated by {sender} {tail}"}


def _tell_escalated(conn, out, esc, subject, escalate_todo):
    """Tell the person whose work it was, by a mention in a comment; say whether it went."""
    of, of_name = esc["of"], esc["of_name"]
    info = {"of": of, "of_name": of_name, "to_manager": esc["to_manager"],
            "manager": esc["manager"], "comment_on": None}
    out["escalation"] = info
    if out.get("already"):
        info.update(told=False, told_notice=f"Nothing new was sent, so {of_name} was not "
                                            f"told again.")
        return
    if of == conn.whoami():
        info.update(told=None, told_notice="It was your own work, so there was no one else "
                                           "to tell.")
        return
    where, label = out.get("document"), None
    if where:
        label = f"{where['doctype']} {where['name']}"
    elif escalate_todo and _todo_of(conn, escalate_todo) == of:
        where, label = _doc(conn, "ToDo", escalate_todo), f"their To-Do {escalate_todo}"
    elif out.get("name"):
        where = _doc(conn, "ToDo", out["name"])
        label = f"{esc['to_name']}’s new To-Do {out['name']}"
    if not where:
        info.update(told=False, told_notice=f"There was no record to tell {of_name} on. "
                                            f"Tell them yourself.")
        return
    if out.get("reused") and _mentioned(conn, where["doctype"], where["name"], of,
                                        ESCALATED_NOTE):
        # An earlier try (its answer lost) already told them: not twice.
        info.update(told=True, comment_on=where,
                    told_notice=f"{of_name} was told it was escalated by the earlier try, in a "
                                f"comment on {label}, so not again.")
        out["said"] = f"{out.get('said') or ''} {of_name} stays on it.".strip()
        return
    try:
        conn.comment(where["doctype"], where["name"], _escalation_note(esc, subject))
    except Exception as e:
        if _unsure(e):
            info.update(told=None,
                        told_notice=f"{of_name} may not have been told: ERPNext did not "
                                    f"confirm the comment on {label} ({_plain_error(e)}). "
                                    f"They are still on it; check, or tell them yourself.")
            return
        info.update(told=False,
                    told_notice=f"{of_name} could not be told: ERPNext refused the comment on "
                                f"{label} ({_plain_error(e)}). They are still on it; tell "
                                f"them yourself.")
        return
    info["comment_on"] = where
    out["said"] = f"{out.get('said') or ''} {of_name} stays on it.".strip()
    if esc["mentionable"] is False:
        info.update(told=False,
                    told_notice=f"A comment on {label} says it was escalated, but {of_name}’s "
                                f"ERPNext user has Allowed In Mentions switched off, so "
                                f"ERPNext did not notify them. Tell them yourself.")
        return
    if esc["mentionable"] is None:
        info.update(told=None,
                    told_notice=f"A comment on {label} says it was escalated and mentions "
                                f"{of_name}, but their ERPNext user could not be read to check "
                                f"that mentions reach them, so they may not have been "
                                f"notified. Check with them.")
        return
    info.update(told=True,
                told_notice=f"ERPNext has told {of_name} it was escalated, by mentioning them "
                            f"in a comment on {label}: under the bell in ERPNext, and by "
                            f"email if their notification settings allow.")


ESCALATED_NOTE = "has escalated this to"


def _escalation_note(esc, subject):
    """The comment that tells them: a mention, as the desk writes one."""
    what = subject[len(ESCALATED):] if subject.startswith(ESCALATED) else subject
    whom = (f"{esc['to_name']}, your manager in ERPNext" if esc["to_manager"]
            else esc["to_name"])
    return _mention_html(esc["of"], esc["of_name"],
                         f"{esc['sender']} {ESCALATED_NOTE} {whom}: {what}. It is still on "
                         f"your list.")


def _todo_of(conn, todo):
    """Who a To-Do is allocated to, if the manager may read it."""
    try:
        rows = conn.get_list("ToDo", filters={"name": todo}, fields=["name", "allocated_to"],
                             limit=1)
    except Exception:
        return None
    return (rows[0].get("allocated_to") or None) if rows else None


def _alert_todo(alert, code):
    """The To-Do a platform alert was handed out as, if it belongs to this business."""
    from command_center.alerts.engine import DOCTYPE
    try:
        doc = frappe.get_doc(DOCTYPE, alert)
    except frappe.DoesNotExistError:
        return None
    return doc.todo if doc.business_code == code else None


def _users(value) -> list:
    """A document's _assign: the logins it is assigned to, as a JSON list."""
    if isinstance(value, list):
        return [u for u in value if u]
    try:
        import json
        got = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [u for u in got if u] if isinstance(got, list) else []


def _first(name: str) -> str:
    return name.split()[0] if (name or "").strip() else (name or "")


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
    by = f" by {_day(due_date)}" if due_date else ""
    return _mention_html(user, who, f"{frappe.utils.get_fullname(sender) or sender} has put "
                                    f"this on your To-Do list{by}: {subject}")


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


def _own_alert(alert, conn):
    """An alert is acted on in its own business, never another's: B's alert assigned
    through A's connector would name B's document on A's site and record A's To-Do on B's
    alert (17 Nov 2026)."""
    if not alert:
        return
    from command_center.alerts.engine import DOCTYPE
    code = frappe.db.get_value(DOCTYPE, alert, "business_code")
    if code and code != conn.code:
        name = frappe.db.get_value("Connected Business", {"business_code": code},
                                   "business_name") or code
        frappe.throw(f"This alert belongs to {name}, not {conn.name}, so it was not handed "
                     f"out. Open it from {name} and try again.")


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
