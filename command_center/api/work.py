"""What is waiting on the manager, and what they have handed out.

Today, Approvals and Outstanding Tasks were drawn with sample requests and sample
tasks because nothing behind them existed. Nothing new needs to: ERPNext already
holds both halves.

    Waiting on you   documents whose workflow has a step this person may take now --
                     asked of ERPNext's own workflow engine (get_transitions), so the
                     roles, the self-approval rule and any transition conditions are
                     the site's, not a copy of them here.
    Handed out       the To-Dos this person assigned (assigned_by): what the Assign
                     button on every alert leaves, by ERPNext's own assignment on the
                     document it concerns, or as a To-Do of its own (api/actions).
                     Open ones are the work in flight; ones the assignee has closed in
                     the last fortnight are the delegated tasks done, awaiting review.

Reading is all this module does, apart from review(): the manager's verdict on work
they handed out, which tags the To-Do Accepted or reopens it with their reason. The
assistant never calls either; approving a document is api/actions.apply_workflow_action,
pressed by a person.

For a business on another site (the hosted service, 14 Nov 2026) the same reads go to
that site under the manager's own API key there (credentials.link_account): "waiting on
you" only means something for the person's own account on that ERPNext, so it is never
read with the platform's shared service account. Without a linked key the screens say
what to do rather than showing someone else's queue under their name.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, date_diff, getdate, today

from command_center.api.businesses import require_manager

ACCEPTED_TAG = "Accepted"
CHECK_DAYS = 14
VALUE_FIELDS = ("base_grand_total", "grand_total", "base_total", "total", "amount",
                "total_amount", "paid_amount")


def _source(business_code):
    """Where the work is read: this site, or the business's own site as this manager.

    Returns (source, guide): a _Local or _Remote, or None with the guide the screen
    shows when it cannot be read (guides.guide)."""
    from command_center.api.businesses import default_business_code
    code = business_code if business_code and business_code != "__all__" else default_business_code()
    if not code or frappe.db.get_value("Connected Business", {"business_code": code}, "is_local"):
        return _Local(), None
    from command_center.api.credentials import credential_for
    if not credential_for(code):
        name = frappe.db.get_value("Connected Business", {"business_code": code},
                                   "business_name") or code
        return None, _key_guide(code, name)
    from command_center.connectors.registry import connector_for
    return _Remote(connector_for(code)), None


def _key_guide(code, name) -> dict:
    """What a manager does when their own ERPNext key is not linked yet: the screens show
    this in place of any request or task, never someone else's queue or a sample."""
    from command_center.guides import guide
    return guide(code,
                 f"Approvals and tasks are read from {name}'s ERPNext under your own account "
                 f"there, so that what is waiting on you is yours. Your ERPNext key is not "
                 f"linked yet.",
                 ["In ERPNext, open your own user (your picture, top right, then My Settings) "
                  "and under API Access press Generate Keys. Copy the API Key and the API "
                  "Secret shown; the secret is shown only once.",
                  "Give both to a platform administrator, who adds them for you under "
                  "Settings → Personal ERPNext Keys.",
                  "Open this screen again: what is waiting on you appears here."],
                 "/app/user", label="Open your user in ERPNext")


def _unreachable(code, e) -> dict:
    name = frappe.db.get_value("Connected Business", {"business_code": code},
                               "business_name") if code else None
    return {"available": False, "unreachable": True,
            "reason": f"Can't reach {name or 'the business'}'s ERPNext just now, so what is "
                      f"waiting on you cannot be read. It is read again when it answers."}


@frappe.whitelist()
def summary(business_code: str | None = None):
    require_manager()
    src, guide_ = _source(business_code)
    if not src:
        return {"available": False, "reason": guide_["text"], "guide": guide_}
    from command_center.connectors.base import BusinessUnreachable
    try:
        return _summary(src, business_code)
    except BusinessUnreachable as e:
        return _unreachable(getattr(getattr(src, "conn", None), "code", None) or business_code, e)


def _summary(src, business_code):
    user = src.me()
    approvals = _approvals(user, src)
    handed = _handed_out(user, src)
    mine = _mine(user, src)
    now = getdate(today())

    open_ = [t for t in handed if t["status"] == "Open"]
    late = [t for t in open_ if t["late_days"] > 0]
    check = [t for t in handed if t["status"] == "Closed" and not t["accepted"]]
    high = [t for t in open_ if t["priority"] == "High"]
    reopened = _sent_back_twice(open_, src)
    due_today = [t for t in mine if t["date"] and getdate(t["date"]) <= now]
    value = sum(a["value"] or 0 for a in approvals)
    oldest = max((t["late_days"] for t in late), default=0)
    currency = src.currency(business_code)

    site = src.site()
    figures = {
        "work_awaiting": _fig("work_awaiting", "Awaiting you", len(approvals),
                              f"{currency} {value:,.0f} involved".strip() if value else
                              "nothing with a value on it",
                              site + "/app/workflow-action?status=Open"),
        "work_due_today": _fig("work_due_today", "Due today", len(due_today),
                               "on your own list, today or earlier",
                               f"{site}/app/todo?status=Open&allocated_to={user}"),
        "work_to_check": _fig("work_to_check", "Delegated Tasks Done", len(check),
                              f"awaiting your review · done in the last {CHECK_DAYS} days",
                              f"{site}/app/todo?status=Closed&assigned_by={user}"),
        "work_unkept": _fig("work_unkept", "Overdue Delegated Tasks", len(late),
                            f"assigned by you · oldest {_age(oldest)} late" if late
                            else "assigned by you · none past its date",
                            f"{site}/app/todo?status=Open&assigned_by={user}"),
        "work_open": _fig("work_open", "Still open", len(open_), "work you handed out",
                          f"{site}/app/todo?status=Open&assigned_by={user}"),
        "work_late": _fig("work_late", "Late", len(late), "past the date you set",
                          f"{site}/app/todo?status=Open&assigned_by={user}"),
        "work_high": _fig("work_high", "High risk", len(high), "marked high priority",
                          f"{site}/app/todo?status=Open&priority=High&assigned_by={user}"),
        "work_reopened": _fig("work_reopened", "Reopened twice+", len(reopened or []),
                              "sent back more than once",
                              f"{site}/app/todo?status=Open&assigned_by={user}"),
    }
    if reopened is None:
        # The comments could not be read: the tile says so, rather than saying nothing
        # was ever sent back.
        figures["work_reopened"].update(value=None, note="could not be read", data_status={
            "state": "failed", "message": "The comments on these To-Dos could not be read."})
    return {"available": True, "user": user, "today": str(now), "currency": currency,
            "approvals": approvals, "open": open_, "late": late, "check": check,
            "mine": mine, "figures": figures}


@frappe.whitelist()
def review(todo: str, verdict: str, note: str = "", business_code: str | None = None):
    """The manager's verdict on work they handed out and the assignee closed.

    accept   tags the To-Do Accepted, so it leaves "Delegated Tasks Done", and records a
             comment saying so.
    return   reopens it, with the manager's reason as a comment the assignee sees.

    On a business on another site, made there under the manager's own key, so that
    site records them as the person who did it.
    """
    require_manager()
    if verdict not in ("accept", "return"):
        frappe.throw("The verdict is accept or return.")
    if verdict == "return" and not (note or "").strip():
        frappe.throw("Say what is still needed, so they know what to do.")
    src, guide_ = _source(business_code)
    if not src:
        frappe.throw(guide_["text"])
    if isinstance(src, _Remote):
        return _review_remote(src, todo, verdict, note)
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
    doc.status = "Open"
    doc.save()
    doc.add_comment("Comment", f"Sent back by {who}: {note.strip()}")
    return {"ok": True, "status": doc.status}


def _review_remote(src, todo, verdict, note):
    conn = src.conn
    me = src.me()
    row = conn.get_list("ToDo", filters={"name": todo}, fields=["name", "assigned_by", "status"],
                        limit=1)
    if not row or row[0].get("assigned_by") != me:
        frappe.throw("Only the person who handed this out can accept it or send it back.",
                     frappe.PermissionError)
    who = src.fullname(me)
    if verdict == "accept":
        conn._call("frappe.desk.doctype.tag.tag.add_tag",
                   {"tag": ACCEPTED_TAG, "dt": "ToDo", "dn": todo}, write=True)
        text, status = f"Accepted by {who}." + (f" {note}" if note else ""), row[0].get("status")
    else:
        conn.set_value("ToDo", todo, "status", "Open")
        text, status = f"Sent back by {who}: {note.strip()}", "Open"
    # Through the form's own comment endpoint: inserting a Comment needs System Manager.
    conn.comment("ToDo", todo, text)
    return {"ok": True, "status": status}


# ---------------------------------------------------------------------------
def _approvals(user, src):
    out = []
    roles = src.roles(user)
    for wf in src.workflows():
        field = wf.get("workflow_state_field") or "workflow_state"
        states = {t["state"] for t in src.transitions(wf["name"])
                  if roles is None or t["allowed"] in roles}
        if not states:
            continue
        has, title_field = src.fields(wf["document_type"])
        vfield = next((f for f in VALUE_FIELDS if f in has), None)
        tfield = title_field if title_field and title_field in has else None
        fields = ["name", "owner", "creation", "modified", "docstatus", field] + \
            [f for f in (vfield, tfield) if f]
        try:
            docs = src.list(wf["document_type"],
                            filters={field: ["in", list(states)], "docstatus": ["<", 2]},
                            fields=fields, order_by="creation asc", limit=100)
        except Exception:
            continue  # not readable by this person
        for d in docs:
            actions = src.actions(wf["document_type"], d)
            if not actions:
                continue
            out.append({
                "doctype": wf["document_type"],
                "name": d["name"],
                "title": (d.get(tfield) if tfield else None) or d["name"],
                "state": d.get(field),
                "actions": list(dict.fromkeys(actions)),
                "value": float(d.get(vfield) or 0) if vfield else None,
                "raised_by": src.fullname(d.get("owner")),
                "raised": str(d.get("creation"))[:10],
                "waiting_days": date_diff(today(), d.get("modified")),
                "url": src.url(wf["document_type"], d["name"]),
            })
    out.sort(key=lambda a: -(a["waiting_days"] or 0))
    return out


def _sent_back_twice(open_, src):
    """Open work handed out that has been sent back more than once.

    "Send it back" (review) reopens the To-Do and leaves a comment beginning "Sent back
    by", so the comments are the record of each return. None when they cannot be read.
    """
    names = [t["name"] for t in open_]
    if not names:
        return []
    try:
        rows = src.list("Comment", filters={"reference_doctype": "ToDo",
                                            "reference_name": ["in", names],
                                            "comment_type": "Comment",
                                            "content": ["like", "Sent back by %"]},
                        fields=["reference_name"], limit=5000)
    except Exception:
        return None
    times = {}
    for r in rows:
        if "reference_name" not in r:
            return None   # the reply lost the column: unreadable, not "none"
        times[r["reference_name"]] = times.get(r["reference_name"], 0) + 1
    return [t for t in open_ if times.get(t["name"], 0) >= 2]


def _todos(filters, src, limit=200):
    rows = src.list("ToDo", filters=filters,
                    fields=["name", "description", "status", "priority", "date",
                            "allocated_to", "assigned_by", "reference_type",
                            "reference_name", "modified", "creation", "_user_tags"],
                    order_by="date asc", limit=limit)
    now = getdate(today())
    out = []
    for r in rows:
        r = frappe._dict(r)
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
            "to_name": src.fullname(r.allocated_to) if r.allocated_to else "",
            "reference": ({"doctype": r.reference_type, "name": r.reference_name}
                          if r.reference_type and r.reference_name else None),
            "closed_on": str(r.modified)[:10] if r.status == "Closed" else None,
            "accepted": ACCEPTED_TAG in (r._user_tags or ""),
            "url": src.url("ToDo", r.name),
        })
    return out


def _handed_out(user, src):
    since = add_days(today(), -CHECK_DAYS)
    open_ = _todos({"assigned_by": user, "status": "Open", "allocated_to": ["!=", user]}, src)
    closed = _todos({"assigned_by": user, "status": "Closed", "allocated_to": ["!=", user],
                     "modified": [">=", since]}, src)
    return open_ + closed


def _mine(user, src):
    return _todos({"allocated_to": user, "status": "Open"}, src, limit=100)


# ---------------------------------------------------------------------------
# The two places work is read from. Same questions, asked of this site's Frappe or of
# the business's own site over its API.
# ---------------------------------------------------------------------------
class _Local:
    def site(self):
        return ""

    def me(self):
        return frappe.session.user

    def roles(self, user):
        return set(frappe.get_roles(user))

    def currency(self, business_code):
        return frappe.defaults.get_global_default("currency") or ""

    def workflows(self):
        return frappe.get_all("Workflow", filters={"is_active": 1},
                              fields=["name", "document_type", "workflow_state_field"])

    def transitions(self, workflow):
        return frappe.get_all("Workflow Transition", filters={"parent": workflow},
                              fields=["state", "allowed"])

    def fields(self, doctype):
        meta = frappe.get_meta(doctype)
        return {f.fieldname for f in meta.fields}, meta.title_field

    def list(self, doctype, **kw):
        return [dict(r) for r in frappe.get_list(doctype, **kw)]

    def actions(self, doctype, row):
        from frappe.model.workflow import get_transitions
        try:
            return [t.action for t in get_transitions(frappe.get_doc(doctype, row["name"]))]
        except Exception:
            return []

    def fullname(self, user):
        return frappe.utils.get_fullname(user)

    def url(self, doctype, name):
        from command_center.connectors.base import desk_path
        return desk_path(doctype, name)


class _Remote:
    """The business's own site, read under this manager's own key there."""

    def __init__(self, conn):
        self.conn = conn
        self._names = {}

    def site(self):
        return self.conn.base_url

    def me(self):
        return self.conn.whoami()

    def roles(self, user):
        # The person's roles there, when that site lets them read their own; None means
        # "not known", and the far site's own get_transitions then decides per document.
        try:
            rows = self.conn.get_list("Has Role", filters={"parent": user, "parenttype": "User"},
                                      fields=["role"], limit=500, parent_doctype="User")
            return {r["role"] for r in rows} or None
        except Exception:
            return None

    def currency(self, business_code):
        from command_center.api.businesses import currency_for
        return currency_for(self.conn.code) or ""

    def workflows(self):
        try:
            return self.conn.get_list("Workflow", filters={"is_active": 1},
                                      fields=["name", "document_type", "workflow_state_field"],
                                      limit=100)
        except Exception:
            return []

    def transitions(self, workflow):
        try:
            return self.conn.get_list("Workflow Transition", filters={"parent": workflow},
                                      fields=["state", "allowed"], limit=500,
                                      parent_doctype="Workflow")
        except Exception:
            return []

    def fields(self, doctype):
        meta = self.conn.get_meta(doctype)
        return {f.get("fieldname") for f in meta.get("fields") or []}, meta.get("title_field")

    def list(self, doctype, filters=None, fields=None, order_by=None, limit=100):
        return self.conn.get_list(doctype, filters=filters, fields=fields,
                                  order_by=order_by, limit=limit)

    def actions(self, doctype, row):
        try:
            res = self.conn._call("frappe.model.workflow.get_transitions",
                                  {"doc": {**row, "doctype": doctype}})
            return [t.get("action") for t in res or [] if t.get("action")]
        except Exception:
            return []

    def fullname(self, user):
        if not user:
            return ""
        if user not in self._names:
            try:
                row = self.conn.get_list("User", filters={"name": user},
                                         fields=["full_name"], limit=1)
                self._names[user] = (row[0].get("full_name") if row else None) or user
            except Exception:
                self._names[user] = user
        return self._names[user]

    def url(self, doctype, name):
        return self.conn.desk_url(doctype, name)


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
