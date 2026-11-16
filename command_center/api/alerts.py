"""The alerts a manager sees, and what they do with them.

    open_alerts  the open alerts for a business (or every business), evaluated first if the
           last pass is more than fifteen minutes old, most severe first
    act    acknowledge, record the To-Do an alert was assigned as, defer to a date,
           dismiss, or mark as not a real problem -- the last three with a reason,
           kept so the rules can be tuned (AL-06)

Only the alert itself changes here. Assigning, requesting evidence and escalating are
handed out in the business's ERPNext by api/actions.create_task, as the manager: assigned
on the one document behind the alert when its records are exactly one (`document` below),
otherwise a To-Do of its own with a mention that notifies the person. act("actioned")
just records which To-Do it became, and `todo_url` opens it in that ERPNext. The
assistant reaches neither.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import getdate, now_datetime, today

from command_center.alerts.engine import DOCTYPE, OPEN, elapsed, ensure_fresh
from command_center.alerts.rules import SEVERITY_RANK
from command_center.api.businesses import require_manager

FIELDS = ["name", "rule", "business_code", "severity", "status", "title", "why",
          "next_step", "figure", "figure_unit", "currency", "owner_label", "source_label",
          "drill_fact", "drill_filters", "elapsed_from", "measured_to", "first_raised",
          "deferred_until", "todo"]


@frappe.whitelist()
def open_alerts(business_code: str | None = None):
    require_manager()
    codes = _codes(business_code)
    for code in codes:
        ensure_fresh(code)
    rows = frappe.get_all(DOCTYPE, filters={"business_code": ["in", codes],
                                            "status": ["in", OPEN],
                                            "resolved_on": ["is", "not set"]},
                          fields=FIELDS, limit=200)
    now = getdate(today())
    from command_center.api.facts import _site_urls, single_document
    from command_center.connectors.base import desk_path
    sites = _site_urls()
    out = []
    for r in rows:
        if r.status == "Deferred" and r.deferred_until and getdate(r.deferred_until) > now:
            continue
        filters = json.loads(r.drill_filters or "{}")
        out.append({
            **{k: r.get(k) for k in FIELDS if k not in ("drill_filters",)},
            "drill_filters": filters,
            "elapsed": elapsed(r.elapsed_from, r.measured_to),
            "first_raised": str(r.first_raised)[:16] if r.first_raised else None,
            "url": f"/app/command-center-alert/{r.name}",
            # The To-Do it became, in the business's own ERPNext (not this platform).
            "todo_url": (sites.get(r.business_code) or "") + desk_path("ToDo", r.todo)
            if r.todo else None,
            # The one ERPNext document behind it, when there is exactly one: Assign
            # assigns that document (api/actions.create_task), and the dialog says so.
            "document": single_document(r.drill_fact, filters, r.business_code),
        })
    from command_center.alerts.notify import recorded
    mailed = recorded([a["name"] for a in out])
    for a in out:
        a["emailed"] = mailed.get(a["name"])
    out.sort(key=lambda a: (SEVERITY_RANK.get(a["severity"], 9), -(a["figure"] or 0)))
    return {"alerts": out, "new": sum(1 for a in out if a["status"] == "Raised"),
            "can_tune": "System Manager" in frappe.get_roles()}


@frappe.whitelist()
def act(name: str, action: str, reason: str = "", until: str | None = None,
        todo: str | None = None):
    require_manager()
    doc = frappe.get_doc(DOCTYPE, name)
    doc.check_permission("write")
    who = frappe.utils.get_fullname(frappe.session.user)
    reason = (reason or "").strip()
    if action == "acknowledge":
        if doc.status == "Raised":
            doc.status = "Acknowledged"
    elif action == "actioned":
        doc.status = "Actioned"
        if todo:
            doc.todo = todo
    elif action in ("defer", "dismiss", "false_positive"):
        if not reason:
            frappe.throw("Give a reason. It is kept so the rule can be tuned.")
        if action == "defer":
            if not until or getdate(until) <= getdate(today()):
                frappe.throw("Choose a date after today to bring it back.")
            doc.status, doc.deferred_until = "Deferred", until
        else:
            doc.status = "Dismissed" if action == "dismiss" else "False Positive"
        doc.reason = reason
    else:
        frappe.throw("Unknown action.")
    doc.acted_by = frappe.session.user
    doc.save()
    if action != "acknowledge":
        label = {"actioned": "Assigned", "defer": f"Deferred to {until}",
                 "dismiss": "Dismissed", "false_positive": "Marked not a real problem"}[action]
        # The record itself keeps who acted and why (acted_by, reason); a comment as well
        # where the runtime keeps comments.
        if callable(getattr(doc, "add_comment", None)):
            doc.add_comment("Comment", f"{label} by {who}." + (f" {reason}" if reason else ""))
    return {"name": doc.name, "status": doc.status, "at": str(now_datetime())[:16]}


def _codes(business_code):
    if business_code and business_code != "__all__":
        return [business_code]
    from command_center.api.businesses import loaded_codes
    return loaded_codes()
