"""Figures read straight from ERPNext, for what the facts do not hold.

The facts cover trading: invoices, payments, orders, stock, work, people, cases. Some
designed cards measure the system itself -- who has an account, who holds which roles,
how much the change log records -- or documents no fact loads yet (purchase orders).
Rather than leave those cards illustrative, each is one small read-only query against
this site's own ERPNext, returned in the same shape as an engine figure so the card,
its note and its drill are handled the same way. The drill opens the matching list in
ERPNext itself.

Each figure reads the business it is asked about: this site's own tables for the local
business, and for a business on another site (the hosted service) the same reads over
its API through its connector, so the counts are that site's. A source that will not
answer a read -- the change log is often readable by System Managers only -- shows as
"could not be read" on its card, never as zero.

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
    fn: Callable          # (reader) -> (value, note)
    href: str


# --------------------------------------------------------------------------- reading
class _Reader:
    """The three reads the figures need, against one business.

    Local: frappe.get_all and frappe.db.count, unfiltered as before -- a manager may
    not hold read on User, and a count of accounts must not depend on who looks.
    Remote: the business's connector, which reads with the asker's own key there or
    the platform's read-only account, so that site's permissions decide.
    """

    def __init__(self, business_code=None):
        import frappe

        from command_center.api.businesses import default_business_code
        self.code = (business_code if business_code and business_code != "__all__"
                     else default_business_code())
        self.local = not self.code or bool(frappe.db.get_value(
            "Connected Business", {"business_code": self.code}, "is_local"))
        self.conn = None
        if not self.local:
            from command_center.connectors.registry import connector_for
            self.conn = connector_for(self.code)

    def all(self, doctype, filters=None, fields=None, limit=100000, parent=None,
            order_by=None):
        import frappe
        if self.local:
            return [dict(r) for r in frappe.get_all(doctype, filters=filters or {},
                                                    fields=fields or ["name"], limit=limit,
                                                    order_by=order_by)]
        return self.conn.get_list(doctype, filters=filters or {}, fields=fields or ["name"],
                                  limit=limit, parent_doctype=parent, order_by=order_by)

    def count(self, doctype, filters=None):
        import frappe
        if self.local:
            return frappe.db.count(doctype, filters or {})
        return int(self.conn.get_count(doctype, filters or {}) or 0)

    def edge(self, doctype, field, filters=None, last=True):
        """The largest (or smallest) value of a field, or None."""
        rows = self.all(doctype, filters=filters, fields=[field], limit=1,
                        order_by=f"{field} {'desc' if last else 'asc'}")
        return rows[0].get(field) if rows else None

    def has(self, doctype):
        import frappe
        if self.local:
            return bool(frappe.db.exists("DocType", doctype))
        try:
            self.count(doctype)
            return True
        except Exception:
            return False


# --------------------------------------------------------------------------- users
def _staff(r):
    return [u for u in r.all("User", filters={"user_type": "System User"},
                             fields=["name", "enabled"])
            if u["name"] not in ("Administrator", "Guest")]


def _holders(r, roles):
    rows = r.all("Has Role", filters={"parenttype": "User", "role": ["in", list(roles)]},
                 fields=["parent", "role"], limit=10000, parent="User")
    enabled = {u["name"] for u in _staff(r) if u["enabled"]}
    out = {}
    for row in rows:
        if row["parent"] in enabled:
            out.setdefault(row["parent"], set()).add(row["role"])
    return out


def users_active(r):
    n = sum(1 for u in _staff(r) if u["enabled"])
    return n, "active in ERPNext"


def users_disabled(r):
    n = sum(1 for u in _staff(r) if not u["enabled"])
    return n, "cannot sign in"


def users_manager_roles(r):
    total = sum(1 for u in _staff(r) if u["enabled"])
    n = len(_holders(r, MANAGER_ROLES))
    return n, f"of {total} accounts hold one of the five"


def users_role_conflicts(r):
    buy, pay = _holders(r, BUY_ROLES), _holders(r, PAY_ROLES)
    n = len(set(buy) & set(pay))
    return n, "can both raise a purchase and pay for it"


def departments_erp(r):
    n = r.count("Department", {"is_group": 0})
    branches = r.count("Branch") if r.has("Branch") else 0
    return n, (f"across {branches} branches" if branches else "in ERPNext")


def last_refreshed(r):
    import frappe
    from frappe.query_builder.functions import Max
    t = frappe.qb.DocType("Command Center Ingest State")
    q = frappe.qb.from_(t).select(Max(t.last_run))
    if r.code:
        q = q.where(t.business_code == r.code)
    row = q.run()
    when = row[0][0] if row and row[0] else None
    if not when:
        return None, "never loaded"
    return str(when), f"on {frappe.utils.format_date(when, 'd MMM yyyy')}"


# --------------------------------------------------------------------------- change log
def versions_total(r):
    import frappe
    first = _first_version(r)
    return r.count("Version"), (f"since {frappe.utils.format_date(first, 'd MMMM yyyy')}"
                                if first else "nothing recorded")


def versions_business(r):
    return (r.count("Version", {"ref_doctype": ["in", list(BUSINESS_DOCTYPES)]}),
            "invoices, orders, payments, stock")


def _first_version(r):
    return r.edge("Version", "creation", last=False)


def versions_earliest(r):
    import frappe
    first = _first_version(r)
    if not first:
        return None, "nothing recorded"
    months = frappe.utils.month_diff(frappe.utils.today(), first)
    return str(first)[:10], f"{months} months of history"


# --------------------------------------------------------------------------- purchase orders
def _po(r, filters, fields):
    return r.all("Purchase Order", filters=filters, fields=fields, limit=100000)


def _po_horizon(r):
    """The last date the purchase orders cover. Waits are measured to here, not today:
    on a dataset that ends in 2025, every open order measured from today is years late."""
    import frappe
    return (r.edge("Purchase Order", "transaction_date", {"docstatus": ["<", 2]})
            or frappe.utils.today())


def po_count(r):
    return r.count("Purchase Order", {"docstatus": 1}), "submitted, all time"


def po_drafts_value(r):
    rows = _po(r, {"docstatus": 0}, ["base_grand_total"])
    return (sum(float(x.get("base_grand_total") or 0) for x in rows),
            f"{len(rows)} purchase orders never submitted")


def po_drafts_oldest(r):
    import frappe
    rows = _po(r, {"docstatus": 0}, ["transaction_date"])
    dates = [x["transaction_date"] for x in rows if x.get("transaction_date")]
    if not dates:
        return None, "no drafts"
    oldest = min(str(d) for d in dates)
    return (frappe.utils.date_diff(_po_horizon(r), oldest),
            f"since {frappe.utils.format_date(oldest, 'MMMM yyyy')}")


def po_cancelled(r):
    from command_center.api.businesses import currency_for
    rows = _po(r, {"docstatus": 2}, ["base_grand_total"])
    total = sum(float(x.get("base_grand_total") or 0) for x in rows)
    cur = currency_for(r.code) or ""
    return len(rows), f"worth {cur} {total:,.0f} between them".replace("  ", " ")


def po_longest_wait(r):
    import frappe
    rows = _po(r, {"docstatus": 1, "per_received": ["<", 100], "base_grand_total": [">", 0],
                   "status": ["not in", ["Closed", "Completed", "On Hold"]]},
               ["name", "supplier", "transaction_date", "schedule_date"])
    rows = [x for x in rows if x.get("transaction_date")]
    if not rows:
        return None, "nothing waiting"
    x = min(rows, key=lambda y: str(y["transaction_date"]))
    days = frappe.utils.date_diff(_po_horizon(r), x["transaction_date"])
    due = (f", due {frappe.utils.format_date(x['schedule_date'], 'MMM yyyy')}"
           if x.get("schedule_date") else "")
    return days, (f"{x['supplier']} · ordered "
                  f"{frappe.utils.format_date(x['transaction_date'], 'MMM yyyy')}{due}")


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

    wanted = [k for k in keys if k in LIVE]
    if not wanted:
        return {}
    reader = None
    try:
        reader = _Reader(business_code)
    except Exception:
        frappe.log_error(title="Command Center live figures", message=frappe.get_traceback())
    out = {}
    for key in wanted:
        spec = LIVE[key]
        try:
            if reader is None:
                raise RuntimeError("no business to read")
            value, note = spec.fn(reader)
            state = {"state": "live", "message": None}
        except Exception:
            frappe.log_error(title=f"Command Center live figure {key}", message=frappe.get_traceback())
            value, note, state = None, "could not be read", {"state": "failed",
                                                            "message": "This figure could not be read."}
        site = "" if not reader or reader.local else (reader.conn.base_url or "")
        out[key] = {
            "key": key, "label": spec.label, "value": value, "unit": spec.unit,
            "direction": "neutral",
            "currency": currency_for(reader.code if reader else business_code)
            if spec.unit == "currency" else None,
            "mixed_currency": False, "scope": business_code or "__all__",
            "as_of": {"date": frappe.utils.today(), "basis": "read from ERPNext just now"},
            "basis": None, "note": note,
            # The ERPNext list itself: on this site, or on the business's own site.
            # (The load history is this platform's own list, wherever the business is.)
            "drill": {"href": spec.href if key == "last_refreshed" else site + spec.href},
            "data_status": state, "period": None, "group": None,
        }
    return out
