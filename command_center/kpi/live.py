"""Figures read straight from ERPNext, for what the facts do not hold.

The facts cover trading: invoices, payments, orders, stock, work, people, cases. Some
designed cards measure the system itself -- who has an account, who holds which roles,
how much the change log records -- or documents no fact loads yet (purchase orders).
Rather than leave those cards illustrative, each is one small read-only query against
this site's own ERPNext, returned in the same shape as an engine figure so the card,
its note and its drill are handled the same way. The drill opens the matching list in
ERPNext itself.

This site's business only: a peer's users and change log are that site's to report.

Importing this module touches no frappe, so preflight can check the keys a screen names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

MANAGER_ROLES = ("System Manager", "Accounts Manager", "Purchase Manager", "Sales Manager",
                 "Stock Manager")
BUY_ROLES = ("Purchase User", "Purchase Manager")
PAY_ROLES = ("Accounts User", "Accounts Manager")
BUSINESS_DOCTYPES = ("Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order",
                     "Payment Entry", "Journal Entry", "Delivery Note", "Purchase Receipt",
                     "Stock Entry", "Quotation")


@dataclass(frozen=True)
class Live:
    key: str
    label: str
    unit: str
    fn: Callable          # () -> (value, note)
    href: str


# --------------------------------------------------------------------------- users
def _staff():
    import frappe
    return [u for u in frappe.get_all("User", filters={"user_type": "System User"},
                                      fields=["name", "enabled"])
            if u.name not in ("Administrator", "Guest")]


def _holders(roles):
    import frappe
    rows = frappe.get_all("Has Role", filters={"parenttype": "User", "role": ["in", list(roles)]},
                          fields=["parent", "role"], limit=10000)
    enabled = {u.name for u in _staff() if u.enabled}
    out = {}
    for r in rows:
        if r.parent in enabled:
            out.setdefault(r.parent, set()).add(r.role)
    return out


def users_active():
    n = sum(1 for u in _staff() if u.enabled)
    return n, "active in ERPNext"


def users_disabled():
    n = sum(1 for u in _staff() if not u.enabled)
    return n, "cannot sign in"


def users_manager_roles():
    total = sum(1 for u in _staff() if u.enabled)
    n = len(_holders(MANAGER_ROLES))
    return n, f"of {total} accounts hold one of the five"


def users_role_conflicts():
    buy, pay = _holders(BUY_ROLES), _holders(PAY_ROLES)
    n = len(set(buy) & set(pay))
    return n, "can both raise a purchase and pay for it"


def departments_erp():
    import frappe
    n = frappe.db.count("Department", {"is_group": 0})
    branches = frappe.db.count("Branch") if frappe.db.exists("DocType", "Branch") else 0
    return n, (f"across {branches} branches" if branches else "in ERPNext")


def last_refreshed():
    import frappe
    from frappe.query_builder.functions import Max
    t = frappe.qb.DocType("Command Center Ingest State")
    row = frappe.qb.from_(t).select(Max(t.last_run)).run()
    when = row[0][0] if row and row[0] else None
    if not when:
        return None, "never loaded"
    return str(when), f"on {frappe.utils.format_date(when, 'd MMM yyyy')}"


# --------------------------------------------------------------------------- change log
def versions_total():
    import frappe
    first = _first_version()
    return frappe.db.count("Version"), (f"since {frappe.utils.format_date(first, 'd MMMM yyyy')}"
                                        if first else "nothing recorded")


def versions_business():
    import frappe
    return (frappe.db.count("Version", {"ref_doctype": ["in", list(BUSINESS_DOCTYPES)]}),
            "invoices, orders, payments, stock")


def _first_version():
    import frappe
    from frappe.query_builder.functions import Min
    t = frappe.qb.DocType("Version")
    row = frappe.qb.from_(t).select(Min(t.creation)).run()
    return row[0][0] if row and row[0] else None


def versions_earliest():
    import frappe
    first = _first_version()
    if not first:
        return None, "nothing recorded"
    months = frappe.utils.month_diff(frappe.utils.today(), first)
    return str(first)[:10], f"{months} months of history"


# --------------------------------------------------------------------------- purchase orders
def _po(filters, fields):
    import frappe
    return frappe.get_all("Purchase Order", filters=filters, fields=fields, limit=100000)


def _po_horizon():
    """The last date the purchase orders cover. Waits are measured to here, not today:
    on a dataset that ends in 2025, every open order measured from today is years late."""
    import frappe
    from frappe.query_builder.functions import Max
    t = frappe.qb.DocType("Purchase Order")
    row = frappe.qb.from_(t).select(Max(t.transaction_date)).where(t.docstatus < 2).run()
    return (row[0][0] if row and row[0] and row[0][0] else None) or frappe.utils.today()


def po_count():
    import frappe
    return frappe.db.count("Purchase Order", {"docstatus": 1}), "submitted, all time"


def po_drafts_value():
    rows = _po({"docstatus": 0}, ["base_grand_total"])
    return sum(float(r.base_grand_total or 0) for r in rows), f"{len(rows)} purchase orders never submitted"


def po_drafts_oldest():
    import frappe
    rows = _po({"docstatus": 0}, ["transaction_date"])
    dates = [r.transaction_date for r in rows if r.transaction_date]
    if not dates:
        return None, "no drafts"
    oldest = min(dates)
    return frappe.utils.date_diff(_po_horizon(), oldest), f"since {frappe.utils.format_date(oldest, 'MMMM yyyy')}"


def po_cancelled():
    import frappe
    rows = _po({"docstatus": 2}, ["base_grand_total"])
    total = sum(float(r.base_grand_total or 0) for r in rows)
    cur = frappe.db.get_value("Connected Business", {"is_local": 1}, "currency") or ""
    return len(rows), f"worth {cur} {total:,.0f} between them".replace("  ", " ")


def po_longest_wait():
    import frappe
    rows = _po({"docstatus": 1, "per_received": ["<", 100], "base_grand_total": [">", 0],
                "status": ["not in", ["Closed", "Completed", "On Hold"]]},
               ["name", "supplier", "transaction_date", "schedule_date"])
    rows = [r for r in rows if r.transaction_date]
    if not rows:
        return None, "nothing waiting"
    r = min(rows, key=lambda x: x.transaction_date)
    days = frappe.utils.date_diff(_po_horizon(), r.transaction_date)
    due = f", due {frappe.utils.format_date(r.schedule_date, 'MMM yyyy')}" if r.schedule_date else ""
    return days, f"{r.supplier} · ordered {frappe.utils.format_date(r.transaction_date, 'MMM yyyy')}{due}"


LIVE = {k.key: k for k in (
    Live("users_active", "Staff accounts", "count", users_active, "/app/user?enabled=1"),
    Live("users_disabled", "Disabled accounts", "count", users_disabled, "/app/user?enabled=0"),
    Live("users_manager_roles", "Accounts with a manager role", "count", users_manager_roles, "/app/user?enabled=1"),
    Live("users_role_conflicts", "Can buy and pay", "count", users_role_conflicts, "/app/user?enabled=1"),
    Live("departments_erp", "Departments", "count", departments_erp, "/app/department"),
    Live("last_refreshed", "Last refreshed", "time", last_refreshed, "/app/command-center-ingest-state"),
    Live("versions_total", "Changes logged", "count", versions_total, "/app/version"),
    Live("versions_business", "Changes on business documents", "count", versions_business, "/app/version"),
    Live("versions_earliest", "Earliest change logged", "date", versions_earliest, "/app/version?order_by=creation%20asc"),
    Live("po_count", "Purchase orders", "count", po_count, "/app/purchase-order?docstatus=1"),
    Live("po_drafts_value", "Purchase orders never submitted", "currency", po_drafts_value, "/app/purchase-order?docstatus=0"),
    Live("po_drafts_oldest", "Oldest unsubmitted purchase order", "days", po_drafts_oldest, "/app/purchase-order?docstatus=0"),
    Live("po_cancelled", "Purchase orders withdrawn", "count", po_cancelled, "/app/purchase-order?docstatus=2"),
    Live("po_longest_wait", "Longest wait for a purchase order", "days", po_longest_wait, "/app/purchase-order?docstatus=1"),
)}


def evaluate(keys, business_code=None) -> dict:
    """The live figures asked for, in the engine's shape. Unknown keys are left out."""
    import frappe

    from command_center.api.businesses import currency_for

    local = True
    if business_code and business_code != "__all__":
        local = bool(frappe.db.get_value("Connected Business", {"business_code": business_code},
                                         "is_local"))
    out = {}
    for key in keys:
        spec = LIVE.get(key)
        if not spec:
            continue
        try:
            value, note = spec.fn() if local else (None, "read on that business's own site")
            state = {"state": "live", "message": None}
        except Exception:
            frappe.log_error(title=f"Command Center live figure {key}", message=frappe.get_traceback())
            value, note, state = None, "could not be read", {"state": "failed",
                                                            "message": "This figure could not be read."}
        out[key] = {
            "key": key, "label": spec.label, "value": value, "unit": spec.unit,
            "direction": "neutral",
            "currency": (currency_for(business_code) or frappe.db.get_value(
                "Connected Business", {"is_local": 1}, "currency")) if spec.unit == "currency" else None,
            "mixed_currency": False, "scope": business_code or "__all__",
            "as_of": {"date": frappe.utils.today(), "basis": "read from ERPNext just now"},
            "basis": None, "note": note, "drill": {"href": spec.href}, "data_status": state,
            "period": None, "group": None,
        }
    return out
