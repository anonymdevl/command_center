"""Demonstration data, clearly marked as such.

Why this exists: the restored extract is thin in one place. There are eleven support
cases, which is too few to show what the complaints screen is for. Everything else --
1,405 sales orders, 806 unpaid invoices, 475 supplier invoices, 2,375 stock lines, 70
tasks, 35 people -- is real restored data and is left alone.

Two rules this module follows without exception.

**Nothing it creates can pass for real data.** Every seeded document carries the
marker below in a field the platform can filter on, and `remove()` deletes exactly
what `run()` created and nothing else. A demonstration that leaves unremovable
fabricated records in a client's site is a liability, not a demo.

**It never touches money.** No invoices, payments, orders, stock movements or ledger
entries. Those are the figures a manager would act on, and a fabricated receivable is
indistinguishable from a real one once it is in the table. Cases and their
assignments are operational records: they demonstrate the workflow without putting a
number on a screen that someone might take to a bank.

It is idempotent. Run it twice and the second run creates nothing.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate

# Written into the subject of everything created here. Visible to anyone reading the
# record in ERPNext, and the handle remove() uses.
MARKER = "[DEMO]"

TARGET_CASES = 60

# Deliberately mundane complaints for a medical supplies distributor. Nothing
# alarming, nothing that names a real person.
COMPLAINTS = [
    ("Delivery arrived two days after the agreed date", "Delivery", "Medium"),
    ("Short shipment: eight units invoiced, six received", "Delivery", "High"),
    ("Packaging damaged in transit, seals broken", "Quality", "High"),
    ("Wrong item code supplied against the order", "Order", "Medium"),
    ("Invoice shows a price different from the quotation", "Billing", "Medium"),
    ("Requested a credit note, no response yet", "Billing", "High"),
    ("Batch number missing from the delivery note", "Documentation", "Low"),
    ("Certificate of analysis not supplied with the batch", "Documentation", "Medium"),
    ("Cold chain indicator showed an excursion on arrival", "Quality", "High"),
    ("Order acknowledged but no delivery date confirmed", "Order", "Medium"),
    ("Replacement promised on a call, nothing in writing", "Service", "Medium"),
    ("Account statement does not agree with our records", "Billing", "Medium"),
    ("Item discontinued without notice to us", "Order", "Low"),
    ("Driver could not find the ward, delivery returned", "Delivery", "Low"),
    ("Expiry date shorter than the agreed minimum shelf life", "Quality", "High"),
]

STATUSES = [("Open", 0.45), ("Replied", 0.2), ("Resolved", 0.2), ("Closed", 0.15)]


def run(business_code: str | None = None, dry_run: bool = False) -> dict:
    """Top complaints up to TARGET_CASES. Everything else is left alone."""
    from command_center.api.businesses import require_manager

    require_manager()
    dry_run = frappe.parse_json(dry_run) if isinstance(dry_run, str) else bool(dry_run)

    existing = frappe.db.count("Issue")
    seeded = frappe.db.count("Issue", {"subject": ["like", f"%{MARKER}%"]})
    needed = max(TARGET_CASES - existing, 0)

    plan = {
        "cases_present": existing,
        "of_which_seeded": seeded,
        "target": TARGET_CASES,
        "to_create": needed,
        "marker": MARKER,
        "untouched": ["Sales Invoice", "Purchase Invoice", "Payment Entry",
                      "Sales Order", "Stock Ledger Entry", "Employee", "Task"],
    }
    if dry_run or not needed:
        plan["created"] = 0
        return plan

    customers = _customers()
    users = _users()
    horizon = _horizon()
    types = _ensure_issue_types()
    plan["issue_types_present"] = sorted(types)

    created = []
    for i in range(needed):
        subject, issue_type, priority = COMPLAINTS[i % len(COMPLAINTS)]
        status = _status_for(i)
        # Spread across the fifteen months before the data horizon, so the waiting
        # bands on the screen have something in each of them.
        opened = add_days(horizon, -((i * 9) % 450) - 1)
        doc = frappe.get_doc({
            "doctype": "Issue",
            "subject": f"{subject} {MARKER}",
            "status": status,
            "priority": priority,
            # issue_type was being unpacked and then not written, which would have
            # left every row blank on a screen that groups by it.
            "issue_type": issue_type if issue_type in types else None,
            "customer": customers[i % len(customers)] if customers else None,
            "opening_date": opened,
            "raised_by": "demo@example.invalid",
        })
        # No ignore_permissions. require_manager() has already established who is
        # calling, and a seeder that bypasses permissions is a seeder that can
        # write into a site the caller has no business writing to.
        doc.insert()

        if status in ("Resolved", "Closed"):
            # Set after insert: ERPNext manages resolution on status change, and
            # writing it in the payload can be overwritten.
            frappe.db.set_value("Issue", doc.name, "resolution_date",
                                add_days(opened, 3 + (i % 21)), update_modified=False)

        # Two in three get an owner. The rest are the "nobody assigned" finding, which
        # is the most actionable thing on the complaints screen and has to be real for
        # the screen to be worth showing.
        if users and i % 3 != 2:
            frappe.db.set_value("Issue", doc.name, "_assign",
                                frappe.as_json([users[i % len(users)]]),
                                update_modified=False)
        created.append(doc.name)

    frappe.db.commit()
    plan["created"] = len(created)
    plan["first"], plan["last"] = (created[0], created[-1]) if created else (None, None)
    return plan


def remove() -> dict:
    """Delete exactly what run() created.

    Matches on the marker, so a record someone added by hand is never caught by it.
    """
    from command_center.api.businesses import require_manager

    require_manager()
    names = [r.name for r in frappe.get_all(
        "Issue", filters={"subject": ["like", f"%{MARKER}%"]}, fields=["name"])]
    for name in names:
        frappe.delete_doc("Issue", name, force=True)
    frappe.db.commit()
    return {"removed": len(names), "marker": MARKER}


# ---------------------------------------------------------------------------
def _ensure_issue_types() -> set[str]:
    """Issue Type is a Link, so the values have to exist as records.

    Created only if absent, and only the ones the seeded complaints use. Any type the
    site already has is left exactly as it is.
    """
    wanted = {t for _, t, _ in COMPLAINTS}
    present = {r.name for r in frappe.get_all("Issue Type", fields=["name"])}
    for name in sorted(wanted - present):
        try:
            frappe.get_doc({"doctype": "Issue Type", "name": name}).insert()
            present.add(name)
        except Exception:
            # An installation may restrict this doctype. A complaint without a type is
            # still a usable complaint, so this is not worth failing the seed over.
            pass
    return present


def _customers() -> list[str]:
    """Real customers, so a complaint sits against a name the screens already show."""
    return [r.name for r in frappe.get_all(
        "Customer", filters={"disabled": 0}, fields=["name"],
        order_by="modified desc", limit=25)]


def _users() -> list[str]:
    return [r.name for r in frappe.get_all(
        "User", filters={"enabled": 1, "user_type": "System User"},
        fields=["name"], limit=8) if r.name not in ("Administrator", "Guest")]


def _horizon():
    """The latest date the data covers, so seeded cases sit inside it.

    Cases opened after the horizon would be the only records in the site newer than
    everything else, which is exactly the kind of tell that makes a demo look staged.
    """
    row = frappe.get_all("Command Center Ingest State",
                         filters={"fact": "fact_sales_invoice"},
                         fields=["as_of_date"], limit=1)
    if row and row[0].as_of_date:
        return getdate(row[0].as_of_date)
    latest = frappe.get_all("Sales Invoice", filters={"docstatus": 1},
                            fields=["posting_date"],
                            order_by="posting_date desc", limit=1)
    return getdate(latest[0].posting_date) if latest else getdate(frappe.utils.today())


def _status_for(i: int) -> str:
    """Deterministic spread across the statuses, in the declared proportions.

    Deterministic rather than random so two runs of the seeder describe the same
    business, and so a figure quoted in a rehearsal is the same one shown on the day.
    """
    position = (i % 20) / 20.0
    running = 0.0
    for status, weight in STATUSES:
        running += weight
        if position < running:
            return status
    return STATUSES[-1][0]
