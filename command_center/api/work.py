"""What is waiting on the manager, and what they have handed out.

Today, Approvals and Outstanding Tasks were drawn with sample requests and sample
tasks because nothing behind them existed. Nothing new needs to: ERPNext already
holds both halves.

    Waiting on you   documents whose workflow has a step this person may take now --
                     asked of ERPNext's own workflow engine (get_transitions), so the
                     roles, the self-approval rule and any transition conditions are
                     the site's, not a copy of them here.
    Handed out       the To-Dos this person assigned (assigned_by), which is what the
                     Assign button on every alert creates. Open ones are the work in
                     flight; ones the assignee has closed in the last fortnight are
                     the evidence to check.

Reading is all this module does, apart from review(): the manager's verdict on work
they handed out, which tags the To-Do Accepted or reopens it with their reason. The
assistant never calls either; approving a document is api/actions.apply_workflow_action,
pressed by a person.

This site's own business only. A connected peer's workflows run on that site under the
manager's credential there, which is the multi-site work not yet tried with a real
second site; the screens say so rather than showing this site's queue under its name.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, date_diff, getdate, today

from command_center.api.businesses import require_manager

ACCEPTED_TAG = "Accepted"
CHECK_DAYS = 14
VALUE_FIELDS = ("base_grand_total", "grand_total", "base_total", "total", "amount",
                "total_amount", "paid_amount")


def _local(business_code):
    if business_code and business_code != "__all__":
        is_local = frappe.db.get_value("Connected Business", {"business_code": business_code},
                                       "is_local")
        if not is_local:
            return False
    return True


@frappe.whitelist()
def summary(business_code: str | None = None):
    require_manager()
    if not _local(business_code):
        return {"available": False,
                "reason": "Approvals and tasks are read from this site's own ERPNext. "
                          "For a connected business they will come from that site, which "
                          "is not switched on yet."}
    user = frappe.session.user
    approvals = _approvals(user)
    handed = _handed_out(user)
    mine = _mine(user)
    now = getdate(today())

    open_ = [t for t in handed if t["status"] == "Open"]
    late = [t for t in open_ if t["late_days"] > 0]
    check = [t for t in handed if t["status"] == "Closed" and not t["accepted"]]
    high = [t for t in open_ if t["priority"] == "High"]
    due_today = [t for t in mine if t["date"] and getdate(t["date"]) <= now]
    value = sum(a["value"] or 0 for a in approvals)
    oldest = max((t["late_days"] for t in late), default=0)
    currency = frappe.defaults.get_global_default("currency") or ""

    figures = {
        "work_awaiting": _fig("work_awaiting", "Awaiting you", len(approvals),
                              f"{currency} {value:,.0f} involved".strip() if value else
                              "nothing with a value on it",
                              "/app/workflow-action?status=Open"),
        "work_due_today": _fig("work_due_today", "Due today", len(due_today),
                               "on your own list, today or earlier",
                               f"/app/todo?status=Open&allocated_to={user}"),
        "work_to_check": _fig("work_to_check", "Evidence to check", len(check),
                              f"marked done in the last {CHECK_DAYS} days",
                              f"/app/todo?status=Closed&assigned_by={user}"),
        "work_unkept": _fig("work_unkept", "Promises unkept", len(late),
                            f"oldest is {_age(oldest)} late" if late else "none past its date",
                            f"/app/todo?status=Open&assigned_by={user}"),
        "work_open": _fig("work_open", "Still open", len(open_), "work you handed out",
                          f"/app/todo?status=Open&assigned_by={user}"),
        "work_late": _fig("work_late", "Late", len(late), "past the date you set",
                          f"/app/todo?status=Open&assigned_by={user}"),
        "work_high": _fig("work_high", "High risk", len(high), "marked high priority",
                          f"/app/todo?status=Open&priority=High&assigned_by={user}"),
    }
    return {"available": True, "user": user, "today": str(now), "currency": currency,
            "approvals": approvals, "open": open_, "late": late, "check": check,
            "mine": mine, "figures": figures}


@frappe.whitelist()
def review(todo: str, verdict: str, note: str = ""):
    """The manager's verdict on work they handed out and the assignee closed.

    accept   tags the To-Do Accepted, so it leaves "Evidence to check", and records a
             comment saying so.
    return   reopens it, with the manager's reason as a comment the assignee sees.
    """
    require_manager()
    doc = frappe.get_doc("ToDo", todo)
    if doc.assigned_by != frappe.session.user:
        frappe.throw("Only the person who handed this out can accept it or send it back.",
                     frappe.PermissionError)
    doc.check_permission("write")
    who = frappe.utils.get_fullname(frappe.session.user)
    if verdict == "accept":
        from frappe.desk.doctype.tag.tag import add_tag
        add_tag(ACCEPTED_TAG, "ToDo", doc.name)
        doc.add_comment("Comment", f"Accepted by {who}." + (f" {note}" if note else ""))
        return {"ok": True, "status": doc.status}
    if verdict == "return":
        if not (note or "").strip():
            frappe.throw("Say what is still needed, so they know what to do.")
        doc.status = "Open"
        doc.save()
        doc.add_comment("Comment", f"Sent back by {who}: {note.strip()}")
        return {"ok": True, "status": doc.status}
    frappe.throw("The verdict is accept or return.")


# ---------------------------------------------------------------------------
def _approvals(user):
    from frappe.model.workflow import get_transitions

    out = []
    roles = set(frappe.get_roles(user))
    for wf in frappe.get_all("Workflow", filters={"is_active": 1},
                             fields=["name", "document_type", "workflow_state_field"]):
        field = wf.workflow_state_field or "workflow_state"
        states = {t.state for t in frappe.get_all(
            "Workflow Transition", filters={"parent": wf.name},
            fields=["state", "allowed"]) if t.allowed in roles}
        if not states:
            continue
        meta = frappe.get_meta(wf.document_type)
        vfield = next((f for f in VALUE_FIELDS if meta.has_field(f)), None)
        tfield = meta.title_field if meta.title_field and meta.has_field(meta.title_field) else None
        fields = ["name", "owner", "creation", "modified", field] + [f for f in (vfield, tfield) if f]
        try:
            docs = frappe.get_list(wf.document_type,
                                   filters={field: ["in", list(states)], "docstatus": ["<", 2]},
                                   fields=fields, order_by="creation asc", limit=100)
        except frappe.PermissionError:
            continue
        for d in docs:
            try:
                actions = [t.action for t in get_transitions(frappe.get_doc(wf.document_type, d.name))]
            except Exception:
                actions = []
            if not actions:
                continue
            out.append({
                "doctype": wf.document_type,
                "name": d.name,
                "title": (d.get(tfield) if tfield else None) or d.name,
                "state": d.get(field),
                "actions": list(dict.fromkeys(actions)),
                "value": float(d.get(vfield) or 0) if vfield else None,
                "raised_by": frappe.utils.get_fullname(d.owner),
                "raised": str(d.creation)[:10],
                "waiting_days": date_diff(today(), d.modified),
                "url": f"/app/{frappe.scrub(wf.document_type).replace('_', '-')}/{d.name}",
            })
    out.sort(key=lambda a: -(a["waiting_days"] or 0))
    return out


def _todos(filters, limit=200):
    rows = frappe.get_list("ToDo", filters=filters,
                           fields=["name", "description", "status", "priority", "date",
                                   "allocated_to", "assigned_by", "reference_type",
                                   "reference_name", "modified", "creation", "_user_tags"],
                           order_by="date asc", limit=limit)
    now = getdate(today())
    out = []
    for r in rows:
        text = frappe.utils.strip_html(r.description or "").strip()
        first, _, rest = text.partition("\n")
        out.append({
            "name": r.name,
            "title": first.strip()[:160] or r.name,
            "detail": rest.strip()[:400],
            "status": r.status,
            "priority": r.priority or "Medium",
            "date": str(r.date) if r.date else None,
            "late_days": max(date_diff(now, r.date), 0) if r.date and r.status == "Open" else 0,
            "to": r.allocated_to,
            "to_name": frappe.utils.get_fullname(r.allocated_to) if r.allocated_to else "",
            "reference": ({"doctype": r.reference_type, "name": r.reference_name}
                          if r.reference_type and r.reference_name else None),
            "closed_on": str(r.modified)[:10] if r.status == "Closed" else None,
            "accepted": ACCEPTED_TAG in (r._user_tags or ""),
            "url": f"/app/todo/{r.name}",
        })
    return out


def _handed_out(user):
    since = add_days(today(), -CHECK_DAYS)
    open_ = _todos({"assigned_by": user, "status": "Open", "allocated_to": ["!=", user]})
    closed = _todos({"assigned_by": user, "status": "Closed", "allocated_to": ["!=", user],
                     "modified": [">=", since]})
    return open_ + closed


def _mine(user):
    return _todos({"allocated_to": user, "status": "Open"}, limit=100)


def _fig(key, label, value, note, href):
    # The shape of a KPI result, so the designed tiles hydrate through the same renderer.
    return {"key": key, "label": label, "value": value, "unit": "count",
            "direction": "neutral", "currency": None, "note": note,
            "as_of": {"date": today(), "basis": "today"}, "basis": None,
            "drill": {"href": href}, "data_status": {"state": "live"}}


def _age(days):
    if days >= 60:
        return f"{round(days / 30.4)} months"
    return f"{days} day" + ("" if days == 1 else "s")
