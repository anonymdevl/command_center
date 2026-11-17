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


# ---------------------------------------------------------------------------
# Managing work already handed out: reassign, withdraw, change its date or priority
# ---------------------------------------------------------------------------
#
# Only on an open To-Do this manager handed out (assigned_by = their login there), and
# only through the front door, as them:
#
#   reassign   on a document: frappe.desk.form.assign_to.remove(doctype, name, old) then
#              assign_to.add for the new person (connectors' unassign() and assign()), so
#              ERPNext cancels the old To-Do, moves Assigned To and notifies both; a To-Do
#              of its own: status Cancelled (frappe.client.set_value), and a new To-Do
#              with the same subject and details plus a mention for the new person.
#              Either way a comment on the document (else the old To-Do) mentions the
#              person it was taken from: who moved it, from whom, to whom.
#   cancel     on a document: assign_to.remove; a To-Do of its own: status Cancelled.
#              A mention in a comment tells them it was withdrawn.
#   edit       the To-Do's date and priority (frappe.client.set_value), and a mention
#              on it telling them what changed.

@frappe.whitelist()
def reassign_task(business_code: str, todo: str, to_user: str, note: str = ""):
    """Move open work this manager handed out to someone else, without escalating."""
    if not to_user:
        frappe.throw("Choose who it goes to now.")
    conn = _conn(business_code)
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
    if doctype and name:
        conn.unassign(doctype, name, old)
        out = _assign(conn, doctype, name, to_user, body, row.get("date"), row.get("priority"))
        where = {"doctype": doctype, "name": name}
        label = f"{doctype} {name}"
    else:
        conn.set_value("ToDo", todo, "status", "Cancelled")
        out = _todo(conn, to_user, subject, body, row.get("date"), row.get("priority"))
        where = {"doctype": "ToDo", "name": todo}
        label = f"their To-Do {todo}"
    line = f"Reassigned by {sender} from {old_name} to {new_name}"
    told, told_notice = _tell(conn, where, old, old_name, old_ok,
                              f"{line}: {subject}.", label, "it was moved")
    out.update(reassigned_from=old, reassigned_from_name=old_name, told=told,
               told_notice=told_notice,
               said=f"{line}. {out.get('said') or ''}".strip())
    return out


@frappe.whitelist()
def cancel_task(business_code: str, todo: str, reason: str = ""):
    """Withdraw open work this manager handed out -- the wrong person, by mistake."""
    conn = _conn(business_code)
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
def update_task(business_code: str, todo: str, due_date: str | None = None,
                priority: str | None = None):
    """Change the date and priority of open work this manager handed out."""
    if priority and priority not in TODO_PRIORITIES:
        frappe.throw("Priority is Low, Medium or High.")
    conn = _conn(business_code)
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
    """Tell someone by a mention in a comment on `where`; (notified, notice)."""
    from html import escape

    if user == conn.whoami():
        return None, "It was your own work, so there was no one else to tell."
    html = (f'<p><span class="mention" data-id="{escape(user)}" data-value="{escape(who)}" '
            f'data-denotation-char="@">@{escape(who)}</span> {escape(text)}</p>')
    try:
        conn.comment(where["doctype"], where["name"], html)
    except Exception as e:
        return False, (f"{who} could not be told {what}: ERPNext refused the comment on "
                       f"{label} ({_plain_error(e)}). Tell them yourself.")
    if mentionable is False:
        return False, (f"A comment on {label} says so, but {who}’s ERPNext user has Allowed "
                       f"In Mentions switched off, so ERPNext did not notify them. Tell them "
                       f"yourself.")
    return True, (f"ERPNext has told {who} {what}, by mentioning them in a comment on "
                  f"{label}: under the bell in ERPNext, and by email if their notification "
                  f"settings allow.")


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
                      "Link your ERPNext key under Settings → Personal ERPNext Keys, or "
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
    try:
        conn.comment(where["doctype"], where["name"], _escalation_note(esc, subject))
    except Exception as e:
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
    info.update(told=True,
                told_notice=f"ERPNext has told {of_name} it was escalated, by mentioning them "
                            f"in a comment on {label}: under the bell in ERPNext, and by "
                            f"email if their notification settings allow.")


def _escalation_note(esc, subject):
    """The comment that tells them: a mention, as the desk writes one."""
    from html import escape

    what = subject[len(ESCALATED):] if subject.startswith(ESCALATED) else subject
    whom = (f"{esc['to_name']}, your manager in ERPNext" if esc["to_manager"]
            else esc["to_name"])
    return (f'<p><span class="mention" data-id="{escape(esc["of"])}" '
            f'data-value="{escape(esc["of_name"])}" data-denotation-char="@">'
            f'@{escape(esc["of_name"])}</span> {escape(esc["sender"])} has escalated this to '
            f'{escape(whom)}: {escape(what)}. It is still on your list.</p>')


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
