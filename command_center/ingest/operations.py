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

from command_center.ingest.base import Ingestor, lateness_bucket, require_fields

PAGE = 2000

# ERPNext statuses that mean the document is finished with. Read as a set rather than
# a string comparison, because an installation can add its own.
CLOSED_ORDER = {"Completed", "Closed", "Cancelled"}
CLOSED_TASK = {"Completed", "Cancelled", "Template"}
CLOSED_CASE = {"Closed", "Resolved"}


def _paged(conn, doctype, fields, filters, limit=None, order_by="modified asc"):
    """Walk a doctype in pages by its modified watermark.

    Every page is checked for the fields that were asked for. Frappe does not always
    report an unknown field: asking Issue for resolution_date -- which this ERPNext
    calls sla_resolution_date -- returned rows carrying only name and modified, with
    no error. Sixty cases loaded with a blank status and no opening date, every one
    of them counted as open, and the screen looked plausible.

    A fact table that quietly loses a column is worse than one that fails to build.
    """
    out = []
    filters = dict(filters)
    while True:
        batch = require_fields(
            conn.get_list(doctype, filters=filters, fields=fields,
                          order_by=order_by, limit=min(PAGE, limit or PAGE)),
            fields, doctype)
        if not batch:
            break
        out.extend(batch)
        if limit and len(out) >= limit:
            return out[:limit]
        if len(batch) < PAGE:
            break
        filters["modified"] = [">", batch[-1]["modified"]]
    return out


class SalesOrderIngestor(Ingestor):
    fact = "fact_sales_order"
    source_doctype = "Sales Order"

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = as_of or resolve_as_of(conn)
        filters = {"docstatus": 1}
        if since:
            filters["modified"] = [">", since]

        orders = _paged(conn, "Sales Order",
                        ["name", "modified", "docstatus", "transaction_date",
                         "delivery_date", "status", "customer", "customer_group",
                         "territory", "currency", "base_grand_total",
                         "per_delivered", "per_billed"],
                        filters, limit)

        rows = []
        for d in orders:
            status = d.get("status") or ""
            is_open = 0 if status in CLOSED_ORDER else 1
            delivered = flt(d.get("per_delivered"))
            billed = flt(d.get("per_billed"))
            value = flt(d.get("base_grand_total"))
            promised = d.get("delivery_date")
            # Lateness applies only to what is still owed. A completed order that was
            # once late is a fact about the past; this screen is about exposure now.
            days = date_diff(as_of, promised) if (promised and is_open) else None
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
                # Percentages can exceed 100 on over-delivery, which would otherwise
                # make the undelivered value negative and understate the order book.
                # Rounded here: a derived money column carried float noise into every
                # total that summed it.
                "undelivered_value": round(
                    max(value * (1 - min(delivered, 100.0) / 100.0), 0), 2),
                "unbilled_value": round(
                    max(value * (1 - min(billed, 100.0) / 100.0), 0), 2),
                "per_delivered": delivered,
                "per_billed": billed,
                "as_of_date": getdate(as_of),
                "days_late": days,
                "lateness_bucket": lateness_bucket(days) if is_open else "Closed",
                "is_open": is_open,
            })
        return rows


class TaskIngestor(Ingestor):
    fact = "fact_task"
    source_doctype = "Task"

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = as_of or resolve_as_of(conn)
        filters = {}
        if since:
            filters["modified"] = [">", since]

        tasks = _paged(conn, "Task",
                       ["name", "modified", "subject", "status", "priority",
                        "project", "owner", "exp_start_date", "exp_end_date",
                        "completed_on", "_assign"],
                       filters, limit)

        projects = _project_names(conn, {t.get("project") for t in tasks})

        rows = []
        for t in tasks:
            status = t.get("status") or ""
            is_open = 0 if status in CLOSED_TASK else 1
            due = t.get("exp_end_date")
            days = date_diff(as_of, due) if (due and is_open) else None
            who = _first_assignee(t.get("_assign"))
            rows.append({
                "src_name": t["name"],
                "src_modified": t["modified"],
                "src_docstatus": 0,
                "subject": (t.get("subject") or "")[:140],
                "status": status,
                "priority": t.get("priority"),
                "project": t.get("project"),
                "project_name": projects.get(t.get("project")),
                "owner_user": t.get("owner"),
                "assigned_to": who,
                "exp_start_date": t.get("exp_start_date"),
                "exp_end_date": due,
                "completed_on": t.get("completed_on"),
                "as_of_date": getdate(as_of),
                "days_late": days,
                "lateness_bucket": lateness_bucket(days) if is_open else "Closed",
                "is_open": is_open,
                "is_assigned": 1 if who else 0,
            })
        return rows


class PersonIngestor(Ingestor):
    fact = "fact_person"
    source_doctype = "Employee"

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
            # Tenure ends when someone leaves, not at the data horizon. Counting a
            # leaver's service up to today would keep growing after they had gone.
            ended = e.get("relieving_date") or as_of
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
                "tenure_days": date_diff(ended, joined) if joined else None,
                "is_active": 1 if (e.get("status") or "") == "Active" else 0,
                "has_user": 1 if e.get("user_id") else 0,
            })
        return rows


class CaseIngestor(Ingestor):
    fact = "fact_case"
    source_doctype = "Issue"

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = as_of or resolve_as_of(conn)
        filters = {}
        if since:
            filters["modified"] = [">", since]

        cases = _paged(conn, "Issue",
                       ["name", "modified", "subject", "status", "priority",
                        "issue_type", "customer", "raised_by", "opening_date",
                        # sla_resolution_date, not resolution_date: the latter does
                        # not exist on Issue in ERPNext v16.
                        "sla_resolution_date", "_assign"],
                       filters, limit)

        rows = []
        for c in cases:
            status = c.get("status") or ""
            is_open = 0 if status in CLOSED_CASE else 1
            opened = c.get("opening_date")
            # An open case has waited until the horizon; a closed one until it closed.
            resolved = c.get("sla_resolution_date")
            until = as_of if is_open else (resolved or as_of)
            days = date_diff(until, opened) if opened else None
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
                "days_open": max(days, 0) if days is not None else None,
                "wait_bucket": lateness_bucket(days) if is_open else "Closed",
                "is_open": is_open,
                "is_assigned": 1 if who else 0,
            })
        return rows


def _project_names(conn, projects) -> dict:
    names = [p for p in projects if p]
    out = {}
    for i in range(0, len(names), 300):
        for d in conn.get_list("Project",
                               filters={"name": ["in", names[i:i + 300]]},
                               fields=["name", "project_name"], limit=100000):
            out[d["name"]] = d.get("project_name")
    return out


def _first_assignee(assign) -> str | None:
    """Frappe stores assignments as a JSON list in _assign.

    Several people can be assigned. The first is taken as the owner rather than
    inventing a rule about which of them is accountable -- and is_assigned records
    only whether anyone is, which is the question the screens actually ask.
    """
    if not assign:
        return None
    try:
        users = frappe.parse_json(assign)
    except Exception:
        return None
    if isinstance(users, str):
        users = [users]
    return users[0] if users else None


INGESTORS = {
    "fact_sales_order": SalesOrderIngestor,
    "fact_task": TaskIngestor,
    "fact_person": PersonIngestor,
    "fact_case": CaseIngestor,
}
