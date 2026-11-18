"""Order book, work, people and cases.

Four facts over data ERPNext already holds. Nothing here is invented: the order book
is Sales Order, work is Task, people are Employee, cases are Issue.

Every one of them measures time against the data horizon rather than today, for the
reason that cost a wrong finding on the receivable: on a restored dataset, "days
late" measured against the current date says how old the snapshot is, not how the
business performs.
"""

from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, getdate

from command_center.ingest import order_lines
from command_center.ingest.base import Ingestor, lateness_bucket, require_fields

# Every row: the connector reads it page by page (connectors/remote.py).
ALL = 10_000_000

# ERPNext statuses that mean the document is finished with. Read as a set rather than
# a string comparison, because an installation can add its own.
CLOSED_ORDER = {"Completed", "Closed", "Cancelled"}
CLOSED_TASK = {"Completed", "Cancelled", "Template"}
# A project closed with a task still open: the work is finished with as far as the
# business has said, so the task is not counted as open work (Project Insights lists such
# projects among the records to tidy).
CLOSED_PROJECT = {"Completed", "Cancelled"}
CLOSED_CASE = {"Closed", "Resolved"}


def _paged(conn, doctype, fields, filters, limit=None, order_by="modified asc"):
    """Every row of a doctype the filters match, in one read the connector pages itself
    -- by key, so a document saved while the walk is under way is never skipped
    (connectors/remote.py). Paging here by "modified > the page's last" skipped any
    document sharing the boundary's timestamp (17 Nov 2026).

    The rows are checked for the fields that were asked for. Frappe does not always
    report an unknown field: asking Issue for resolution_date -- which v16 calls
    sla_resolution_date -- returned rows carrying only name and modified, with no
    error. Sixty cases loaded with a blank status and no opening date, every one
    of them counted as open, and the screen looked plausible.

    A fact table that quietly loses a column is worse than one that fails to build.
    """
    return require_fields(conn.get_list(doctype, filters=dict(filters), fields=fields,
                                        order_by=order_by, limit=limit or ALL), fields, doctype)


def late_age(due, is_open, as_of, field="days_late", bucket="lateness_bucket") -> dict:
    """How late, as at the as-of date. Lateness applies only to what is still owed: a
    completed order or task that was once late is a fact about the past, and the screens
    are about exposure now. One definition for the extract and the re-ageing."""
    days = date_diff(as_of, due) if (due and is_open) else None
    return {field: days, bucket: lateness_bucket(days) if is_open else "Closed"}


class SalesOrderIngestor(Ingestor):
    fact = "fact_sales_order"
    source_doctype = "Sales Order"
    cancellable = "Sales Order"
    aged_by = ("delivery_date", "is_open")

    def age(self, row, as_of):
        return late_age(row.get("delivery_date"), row.get("is_open"), as_of)

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = as_of or resolve_as_of(conn)
        filters = {"docstatus": 1}
        if since:
            filters["modified"] = [">", since]

        orders = _paged(conn, "Sales Order",
                        ["name", "modified", "docstatus", "transaction_date",
                         "delivery_date", "status", "customer", "customer_group",
                         "territory", "currency", "base_grand_total", "base_net_total",
                         "per_delivered", "per_billed"],
                        filters, limit)
        # What is left on each order, line by line (ingest/order_lines.py): never the
        # order's value times ERPNext's delivered or billed percentage.
        left = order_lines.order_values(conn, order_lines.SALES, orders, "per_delivered")

        rows = []
        for d in orders:
            status = d.get("status") or ""
            is_open = 0 if status in CLOSED_ORDER else 1
            delivered = flt(d.get("per_delivered"))
            billed = flt(d.get("per_billed"))
            value = flt(d.get("base_grand_total"))
            owed = left[d["name"]]
            promised = d.get("delivery_date")
            rows.append({
                "src_name": d["name"],
                "src_modified": d["modified"],
                "src_docstatus": d["docstatus"],
                "transaction_date": d.get("transaction_date"),
                "delivery_date": promised,
                "status": status,
                "customer": d.get("customer"),
                "customer_group": d.get("customer_group"),
                "territory": d.get("territory"),
                "currency": d.get("currency"),
                "base_grand_total": value,
                "undelivered_value": owed["left"],
                "unbilled_value": owed["unbilled"],
                "delivered_unbilled_value": owed["delivered_unbilled"],
                "per_delivered": delivered,
                "per_billed": billed,
                "as_of_date": getdate(as_of),
                **late_age(promised, is_open, as_of),
                "is_open": is_open,
            })
        return rows


class TaskIngestor(Ingestor):
    fact = "fact_task"
    source_doctype = "Task"
    deletable = ("Task", {}, {})
    aged_by = ("exp_end_date", "is_open")

    def age(self, row, as_of):
        return late_age(row.get("exp_end_date"), row.get("is_open"), as_of)

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = as_of or resolve_as_of(conn)
        filters = {}
        if since:
            filters["modified"] = [">", since]

        fields = ["name", "modified", "subject", "status", "priority", "project", "owner",
                  "exp_start_date", "exp_end_date", "completed_on", "_assign"]
        tasks = _paged(conn, "Task", fields, filters, limit)
        if since:
            # A project closed, reopened or moved to another customer changes what its
            # tasks say without saving them: their rows are read again with it.
            moved = [p["name"] for p in conn.get_list(
                "Project", filters={"modified": [">", since]}, fields=["name"], limit=ALL)]
            seen = {t["name"] for t in tasks}
            for part in _chunks(moved):
                tasks += [t for t in _paged(conn, "Task", fields, {"project": ["in", part]})
                          if t["name"] not in seen]

        projects = _projects(conn, {t.get("project") for t in tasks})
        engineers = _engineers(conn, tasks, whole=not since)

        rows = []
        for t in tasks:
            status = t.get("status") or ""
            project = projects.get(t.get("project")) or {}
            is_open = 0 if (status in CLOSED_TASK
                            or project.get("status") in CLOSED_PROJECT) else 1
            due = t.get("exp_end_date")
            who = _first_assignee(t.get("_assign"))
            names = engineers.get(t["name"]) or []
            rows.append({
                "src_name": t["name"],
                "src_modified": t["modified"],
                "src_docstatus": 0,
                "subject": (t.get("subject") or "")[:140],
                "status": status,
                "priority": t.get("priority"),
                "project": t.get("project"),
                "project_name": project.get("project_name"),
                "customer": project.get("customer"),
                "project_type": project.get("project_type"),
                "project_status": project.get("status"),
                "owner_user": t.get("owner"),
                "assigned_to": who,
                "engineers": ", ".join(names) or None,
                "exp_start_date": t.get("exp_start_date"),
                "exp_end_date": due,
                "completed_on": t.get("completed_on"),
                "as_of_date": getdate(as_of),
                **late_age(due, is_open, as_of),
                "is_open": is_open,
                "is_assigned": 1 if names else 0,
            })
        return rows


class PersonIngestor(Ingestor):
    fact = "fact_person"
    source_doctype = "Employee"
    deletable = ("Employee", {}, {})
    aged_by = ("date_of_joining", "relieving_date")

    def age(self, row, as_of):
        return tenure(row.get("date_of_joining"), row.get("relieving_date"), as_of)

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = as_of or resolve_as_of(conn)
        filters = {}
        if since:
            filters["modified"] = [">", since]

        people = _paged(conn, "Employee",
                        ["name", "modified", "employee_name", "status", "gender",
                         "department", "designation", "branch", "employment_type",
                         "date_of_joining", "relieving_date", "user_id"],
                        filters, limit)

        rows = []
        for e in people:
            joined = e.get("date_of_joining")
            rows.append({
                "src_name": e["name"],
                "src_modified": e["modified"],
                "src_docstatus": 0,
                "employee_name": e.get("employee_name"),
                "status": e.get("status"),
                "gender": e.get("gender"),
                "department": e.get("department"),
                "designation": e.get("designation"),
                "branch": e.get("branch"),
                "employment_type": e.get("employment_type"),
                "date_of_joining": joined,
                "relieving_date": e.get("relieving_date"),
                "as_of_date": getdate(as_of),
                **tenure(joined, e.get("relieving_date"), as_of),
                "is_active": 1 if (e.get("status") or "") == "Active" else 0,
                "has_user": 1 if e.get("user_id") else 0,
            })
        return rows


def tenure(joined, left, as_of) -> dict:
    """Tenure ends when someone leaves, not at the data horizon. Counting a leaver's
    service up to today would keep growing after they had gone."""
    return {"tenure_days": date_diff(left or as_of, joined) if joined else None}


def wait(opened, resolved, is_open, as_of) -> dict:
    """An open case has waited until the horizon; a closed one until it closed."""
    until = as_of if is_open else (resolved or as_of)
    days = date_diff(until, opened) if opened else None
    return {"days_open": max(days, 0) if days is not None else None,
            "wait_bucket": lateness_bucket(days) if is_open else "Closed"}


class CaseIngestor(Ingestor):
    fact = "fact_case"
    source_doctype = "Issue"
    deletable = ("Issue", {}, {})
    aged_by = ("opening_date", "resolution_date", "is_open")

    def age(self, row, as_of):
        return wait(row.get("opening_date"), row.get("resolution_date"), row.get("is_open"),
                    as_of)

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = as_of or resolve_as_of(conn)
        filters = {}
        if since:
            filters["modified"] = [">", since]

        # When it was resolved has two names: sla_resolution_date on v15/v16 (Biomed),
        # resolution_date on v14 (Gigmann's live site, checked 14 Nov 2026 -- v14
        # rejects the other name with "Field not permitted in query"). Asked for by the
        # newer name first, and by the older one if the site does not know it.
        base = ["name", "modified", "subject", "status", "priority", "issue_type",
                "customer", "raised_by", "opening_date", "_assign"]
        resolved_field = "sla_resolution_date"
        try:
            cases = _paged(conn, "Issue", base + [resolved_field], filters, limit)
        except Exception as e:
            if "sla_resolution_date" not in str(e):
                raise
            resolved_field = "resolution_date"
            cases = _paged(conn, "Issue", base + [resolved_field], filters, limit)

        rows = []
        for c in cases:
            status = c.get("status") or ""
            is_open = 0 if status in CLOSED_CASE else 1
            opened = c.get("opening_date")
            resolved = c.get(resolved_field)
            who = _first_assignee(c.get("_assign"))
            rows.append({
                "src_name": c["name"],
                "src_modified": c["modified"],
                "src_docstatus": 0,
                "subject": (c.get("subject") or "")[:140],
                "status": status,
                "priority": c.get("priority"),
                "issue_type": c.get("issue_type"),
                "customer": c.get("customer"),
                "raised_by": c.get("raised_by"),
                "assigned_to": who,
                "opening_date": opened,
                "resolution_date": getdate(resolved) if resolved else None,
                "as_of_date": getdate(as_of),
                **wait(opened, getdate(resolved) if resolved else None, is_open, as_of),
                "is_open": is_open,
                "is_assigned": 1 if who else 0,
            })
        return rows


def _chunks(names, size=300):
    names = sorted(n for n in names if n)
    return [names[i:i + size] for i in range(0, len(names), size)]


def _projects(conn, projects) -> dict:
    """Project -> its name, customer, type and status."""
    out = {}
    for part in _chunks(projects):
        for d in conn.get_list("Project", filters={"name": ["in", part]},
                               fields=["name", "project_name", "customer", "project_type",
                                       "status"], limit=ALL):
            out[d["name"]] = d
    return out


def _fields_of(conn, doctype) -> list[dict]:
    """A doctype's fields as the site defines them, its custom fields included."""
    if hasattr(conn, "get_meta"):
        return conn.get_meta(doctype).get("fields") or []
    return [{"fieldname": f.fieldname, "fieldtype": f.fieldtype, "options": f.options}
            for f in frappe.get_meta(doctype).fields]


def engineer_fields(conn) -> list[tuple[str, str, str]]:
    """The site's own engineer field on Task, where it has one: each table on Task whose
    rows link an Employee (Gigmann's "Service Engineers"), as (table field, child doctype,
    link field). None on a site that keeps no such table, or whose Task cannot be read."""
    try:
        task = _fields_of(conn, "Task")
    except Exception:
        return []
    out = []
    for f in task:
        if f.get("fieldtype") not in ("Table", "Table MultiSelect") or not f.get("options"):
            continue
        try:
            child = _fields_of(conn, f["options"])
        except Exception:
            continue
        out += [(f["fieldname"], f["options"], c["fieldname"]) for c in child
                if c.get("fieldtype") == "Link" and c.get("options") == "Employee"]
    return out


def _engineers(conn, tasks, whole=True) -> dict:
    """Task -> the names of the people doing it, in order.

    The task's own engineer field first (employees, named as their Employee record names
    them). Where a task has none there, the people it is assigned to: each as the
    employee whose account they sign in with, or by their account's name when no employee
    is linked to it. A task naming nobody either way has no entry; it is reported as
    not assigned, never guessed from notes or descriptions."""
    def clean(name):
        return " ".join(str(name or "").split())

    try:
        staff = conn.get_list("Employee", fields=["name", "employee_name", "user_id"],
                              limit=ALL)
    except Exception:
        staff = []
    by_id = {e["name"]: clean(e.get("employee_name")) or e["name"] for e in staff}
    by_user = {e["user_id"]: by_id[e["name"]] for e in staff if e.get("user_id")}

    linked = {}
    for table, child, link in engineer_fields(conn):
        filters = {"parenttype": "Task", "parentfield": table}
        parts = [None] if whole else _chunks(t["name"] for t in tasks)
        for part in parts:
            if part is not None:
                filters["parent"] = ["in", part]
            for row in conn.get_list(child, filters=dict(filters), fields=["parent", link],
                                     limit=ALL, parent_doctype="Task", order_by="idx asc"):
                if row.get(link):
                    linked.setdefault(row["parent"], []).append(
                        by_id.get(row[link]) or row[link])

    users = {}
    for t in tasks:
        if t["name"] not in linked:
            users[t["name"]] = _assignees(t.get("_assign"))
    unknown = sorted({u for us in users.values() for u in us if u not in by_user})
    account = {}
    for part in _chunks(unknown):
        try:
            account.update({u["name"]: clean(u.get("full_name")) or u["name"] for u in
                            conn.get_list("User", filters={"name": ["in", part]},
                                          fields=["name", "full_name"], limit=ALL)})
        except Exception:
            pass

    out = {}
    for t in tasks:
        names = linked.get(t["name"]) or [by_user.get(u) or account.get(u) or u
                                          for u in users.get(t["name"], [])]
        if names:
            out[t["name"]] = list(dict.fromkeys(names))
    return out


def _assignees(assign) -> list[str]:
    """Everyone a task is assigned to (Frappe keeps them as a JSON list in _assign)."""
    if not assign:
        return []
    try:
        users = frappe.parse_json(assign)
    except Exception:
        return []
    if isinstance(users, str):
        users = [users]
    return [u for u in (users or []) if u]


def _first_assignee(assign) -> str | None:
    """Frappe stores assignments as a JSON list in _assign.

    Several people can be assigned. The first is taken as the owner rather than
    inventing a rule about which of them is accountable -- and is_assigned records
    only whether anyone is, which is the question the screens actually ask.
    """
    users = _assignees(assign)
    return users[0] if users else None


INGESTORS = {
    "fact_sales_order": SalesOrderIngestor,
    "fact_task": TaskIngestor,
    "fact_person": PersonIngestor,
    "fact_case": CaseIngestor,
}
