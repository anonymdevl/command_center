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
                     the last fortnight are the delegated tasks done, awaiting review
                     (not ones the manager closed: actions.close_task).

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
SEND_BACK = "Command Center Task Send Back"
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
                  "Settings → ERPNext API Keys.",
                  "Open this screen again: what is waiting on you appears here."],
                 "/app/user", label="Open your user in ERPNext")


def _unreachable(code, e) -> dict:
    name = frappe.db.get_value("Connected Business", {"business_code": code},
                               "business_name") if code else None
    from command_center.kpi.live_departments import waiting_words
    return {"available": False, "unreachable": True,
            "reason": f"{waiting_words(name or 'The business')}, so what is waiting on you "
                      f"appears as soon as it does."}


@frappe.whitelist()
def summary(business_code: str | None = None):
    require_manager()
    src, guide_ = _source(business_code)
    if not src:
        return {"available": False, "reason": guide_["text"], "guide": guide_}
    from command_center.connectors.base import BusinessUnreachable
    try:
        return _summary(src, _code(business_code))
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
    times = _sent_back(open_, src, business_code)
    for t in open_:
        t["sent_back"] = times.get(t["name"], 0)
    reopened = [t for t in open_ if t["sent_back"] >= 2]
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
        "work_open": _fig("work_open", "Still Open", len(open_), "work you handed out",
                          f"{site}/app/todo?status=Open&assigned_by={user}"),
        "work_late": _fig("work_late", "Late", len(late), "past the date you set",
                          f"{site}/app/todo?status=Open&assigned_by={user}"),
        "work_high": _fig("work_high", "High Priority", len(high), "marked high priority",
                          f"{site}/app/todo?status=Open&priority=High&assigned_by={user}"),
        "work_reopened": _fig("work_reopened", "Sent Back More Than Once", len(reopened),
                              "you rejected the work twice or more",
                              f"{site}/app/todo?status=Open&assigned_by={user}"),
    }
    # Each tile filters the list on Outstanding Tasks (legacy/work.js), and Today's two
    # open it filtered the same way.
    for key, f in TILE_FILTERS.items():
        figures[key]["filter"] = f
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
        out = _review_remote(src, todo, verdict, note)
    else:
        out = _review_local(todo, verdict, note)
    if verdict == "return":
        out["sent_back"] = _record_send_back(_code(business_code), todo, note)
    return out


def _review_local(todo, verdict, note):
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


@frappe.whitelist()
def task(todo: str, business_code: str | None = None):
    """One task handed out, for its drawer: what it is, who has it, who gave it, its
    dates, priority and status, the document it is about, how often it was sent back,
    and ERPNext's comments on the To-Do and the document -- when the manager may read
    them there (`comments` None when not). Only for the person who handed it out."""
    require_manager()
    src, guide_ = _source(business_code)
    if not src:
        frappe.throw(guide_["text"])
    me = src.me()
    rows = _todos({"name": todo}, src, limit=1, extra=["assigned_by"])
    if not rows or rows[0].get("assigned_by") != me:
        frappe.throw("Only the person who handed this out can open it here.",
                     frappe.PermissionError)
    t = rows[0]
    t["assigned_by_name"] = src.fullname(me)
    t["sent_back"] = _sent_back([t], src, _code(business_code)).get(t["name"], 0)
    t["document"] = ({**t["reference"], "url": src.url(t["reference"]["doctype"],
                                                       t["reference"]["name"])}
                     if t["reference"] else None)
    t["text"] = frappe.utils.strip_html(t.pop("_description", "") or "").strip()
    places = [("ToDo", t["name"])] + ([(t["reference"]["doctype"], t["reference"]["name"])]
                                      if t["reference"] else [])
    got, readable = [], False
    for doctype, name in places:
        c = src.comments(doctype, name)
        if c is None:
            continue
        readable = True
        got += [{**x, "on": doctype} for x in c]
    got.sort(key=lambda c: str(c.get("when") or ""), reverse=True)
    t["comments"] = got[:100] if readable else None
    return t


# ---------------------------------------------------------------------------
def _approvals(user, src):
    out = []
    roles = src.roles(user)
    for wf in src.workflows():
        field = wf.get("workflow_state_field") or "workflow_state"
        # A document waits on this person only where they can move it forward. A step
        # whose only way on is Cancel (an approved, submitted document: "Approved by
        # CEO" -> Cancelled) is finished, not waiting -- every approver who may cancel
        # would otherwise see every approved document as theirs to decide.
        ends = _cancel_states(src.states(wf["name"]))
        states = {t["state"] for t in src.transitions(wf["name"])
                  if (roles is None or t["allowed"] in roles)
                  and not _cancels(t.get("action"), t.get("next_state"), ends)}
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
            actions = [a for a, nxt in src.actions(wf["document_type"], d)
                       if not _cancels(a, nxt, ends)]
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


def _cancel_states(states):
    """The workflow's states that cancel the document (Document Status 2)."""
    return {name for name, ds in (states or {}).items() if str(ds) == "2"}


def _cancels(action, next_state, ends):
    """A transition that only cancels the document: it leads to a cancelled state, or
    (when the states could not be read) is the action named Cancel."""
    if next_state and next_state in ends:
        return True
    return not ends and (action or "").strip().lower() == "cancel"


# Tile figure -> the filter it puts on Outstanding Tasks' list (legacy/work.js).
TILE_FILTERS = {"work_open": "open", "work_late": "late", "work_high": "high",
                "work_reopened": "sent_back", "work_to_check": "check",
                "work_unkept": "late"}


def _code(business_code):
    """The business a task belongs to: the one asked for, else the default."""
    from command_center.api.businesses import default_business_code
    return business_code if business_code and business_code != "__all__" \
        else default_business_code()


def _record_send_back(code, todo, note) -> int:
    """Keep this Send Back on the platform, and say how many times this To-Do has now
    been sent back. The doctype by name: it is the app's own (preflight)."""
    frappe.get_doc({
        "doctype": "Command Center Task Send Back", "business_code": code or "",
        "todo": todo, "sent_by": frappe.session.user, "sent_at": frappe.utils.now_datetime(),
        "note": (note or "").strip()[:1000],
    }).insert(ignore_permissions=True)
    return frappe.db.count(SEND_BACK, {"business_code": code or "", "todo": todo})


def _sent_back(open_, src, code) -> dict:
    """How many times each open To-Do was sent back: {todo: n}.

    Counted from the platform's own record of every Send Back (review keeps one). Work
    sent back before that record existed shows only in ERPNext's Comments ("Sent back
    by ..."), which ordinary users usually may not read: they are counted too when they
    can be read, and silently left out when they cannot -- never a failure.
    """
    names = [t["name"] for t in open_]
    if not names:
        return {}
    times = {}
    for r in frappe.get_all(SEND_BACK, filters={"business_code": code or "",
                                                "todo": ["in", names]},
                            fields=["todo"], limit=100000):
        times[r["todo"]] = times.get(r["todo"], 0) + 1
    try:
        rows = src.list("Comment", filters={"reference_doctype": "ToDo",
                                            "reference_name": ["in", names],
                                            "comment_type": "Comment",
                                            "content": ["like", "Sent back by %"]},
                        fields=["reference_name"], limit=5000)
    except Exception:
        rows = []
    seen = {}
    for r in rows or []:
        if "reference_name" not in r:
            seen = {}
            break   # the reply lost the column: unreadable, so not counted
        seen[r["reference_name"]] = seen.get(r["reference_name"], 0) + 1
    for name, n in seen.items():
        times[name] = max(times.get(name, 0), n)
    return times


def _todos(filters, src, limit=200, extra=None):
    rows = src.list("ToDo", filters=filters,
                    fields=["name", "description", "status", "priority", "date",
                            "allocated_to", "assigned_by", "reference_type",
                            "reference_name", "modified", "modified_by", "creation",
                            "_user_tags"],
                    order_by="date asc", limit=limit)
    now = getdate(today())
    me = src.me() if rows else None
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
            "closed_by_you": r.status == "Closed" and bool(me) and r.modified_by == me,
            "url": src.url("ToDo", r.name),
            "created": str(r.creation)[:10] if r.creation else None,
            "modified": str(r.modified)[:16] if r.modified else None,
            **({"assigned_by": r.assigned_by, "_description": r.description or ""}
               if extra else {}),
        })
    return out


def _handed_out(user, src):
    since = add_days(today(), -CHECK_DAYS)
    open_ = _todos({"assigned_by": user, "status": "Open", "allocated_to": ["!=", user]}, src)
    closed = _todos({"assigned_by": user, "status": "Closed", "allocated_to": ["!=", user],
                     "modified": [">=", since]}, src)
    # Closed by the manager (actions.close_task) is not done by the assignee, so it is
    # not work to check. ERPNext's own record says who closed it: modified_by, the
    # manager's login there (src.me()), the same on v14, v15 and v16.
    return open_ + [t for t in closed if not t["closed_by_you"]]


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
                              fields=["state", "allowed", "action", "next_state"])

    def states(self, workflow):
        rows = frappe.get_all("Workflow Document State", filters={"parent": workflow},
                              fields=["state", "doc_status"])
        return {r["state"]: r["doc_status"] for r in rows}

    def fields(self, doctype):
        meta = frappe.get_meta(doctype)
        return {f.fieldname for f in meta.fields}, meta.title_field

    def list(self, doctype, **kw):
        return [dict(r) for r in frappe.get_list(doctype, **kw)]

    def actions(self, doctype, row):
        from frappe.model.workflow import get_transitions
        try:
            return [(t.action, t.next_state)
                    for t in get_transitions(frappe.get_doc(doctype, row["name"]))]
        except Exception:
            return []

    def fullname(self, user):
        return frappe.utils.get_fullname(user)

    def comments(self, doctype, name):
        try:
            rows = frappe.get_list("Comment", filters={"reference_doctype": doctype,
                                                       "reference_name": name},
                                   fields=COMMENT_FIELDS, order_by="creation desc", limit=100)
        except Exception:
            return None
        return _comments(rows, self)

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
                                      fields=["state", "allowed", "action", "next_state"],
                                      limit=500, parent_doctype="Workflow")
        except Exception:
            return []

    def states(self, workflow):
        try:
            rows = self.conn.get_list("Workflow Document State", filters={"parent": workflow},
                                      fields=["state", "doc_status"], limit=500,
                                      parent_doctype="Workflow")
            return {r.get("state"): r.get("doc_status") for r in rows}
        except Exception:
            return {}

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
            return [(t.get("action"), t.get("next_state")) for t in res or [] if t.get("action")]
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

    def comments(self, doctype, name):
        """The record's comments as the desk shows them: the form's own load
        (frappe.desk.form.load.getdoc -> docinfo.comments), which anyone who may read the
        record may call, where listing Comment needs a role most people do not hold.
        Then Comment itself; None when neither answers."""
        try:
            got = self.conn._call("frappe.desk.form.load.getdoc",
                                  {"doctype": doctype, "name": name}, whole=True) or {}
            info = got.get("docinfo") if isinstance(got, dict) else None
            if isinstance(info, dict) and isinstance(info.get("comments"), list):
                return _comments(info["comments"], self)
        except Exception:
            pass
        try:
            rows = self.conn.get_list("Comment", filters={"reference_doctype": doctype,
                                                          "reference_name": name},
                                      fields=COMMENT_FIELDS, order_by="creation desc", limit=100)
        except Exception:
            return None
        if rows and "content" not in rows[0]:
            return None
        return _comments(rows, self)

    def url(self, doctype, name):
        return self.conn.desk_url(doctype, name)


COMMENT_FIELDS = ["name", "comment_type", "content", "comment_email", "owner", "creation"]
SHOWN_COMMENTS = {None, "", "Comment", "Info", "Assigned", "Assignment Completed", "Edit",
                  "Attachment", "Shared", "Workflow"}


def _comments(rows, src):
    out = []
    for r in rows or []:
        kind = r.get("comment_type")
        if kind not in SHOWN_COMMENTS:
            continue
        text = frappe.utils.strip_html(r.get("content") or "").strip()
        if not text:
            continue
        by = r.get("comment_email") or r.get("owner") or ""
        out.append({"by": src.fullname(by) if by else "", "when": str(r.get("creation") or "")[:16],
                    "text": text[:2000], "kind": kind or "Comment"})
    return out


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
