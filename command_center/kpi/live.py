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
# The pairs of duties one account should not hold together, and how a screen says so.
# The first is the "Role conflicts" card's own test, so the card and the table beside it
# can never disagree about it.
CONFLICTS = (
    (BUY_ROLES, PAY_ROLES, "can raise a purchase and approve its payment"),
    (("Stock User", "Stock Manager"), PAY_ROLES, "can adjust stock and post the accounting for it"),
    (("HR User", "HR Manager"), PAY_ROLES, "can change pay and approve the payment of it"),
)
# The roles that say what an account can do in the business, as the access tables list
# them. ERPNext gives every account a dozen others (Employee, Desk User, ...) that say
# nothing about it.
KEY_ROLES = ("System Manager", "Accounts Manager", "Accounts User", "Purchase Manager",
             "Purchase User", "Sales Manager", "Sales User", "Stock Manager", "Stock User",
             "HR Manager", "HR User", "Projects Manager", "Manufacturing Manager",
             "Maintenance Manager", "Quality Manager", "Auditor")
BUSINESS_DOCTYPES = ("Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order",
                     "Payment Entry", "Journal Entry", "Delivery Note", "Purchase Receipt",
                     "Stock Entry", "Quotation")


class NeedsSetup(Exception):
    """Raised by a figure when the business's ERPNext records nothing behind it yet:
    the card shows the guide (command_center/guides.needs_setup) instead of a figure."""

    def __init__(self, status: dict):
        super().__init__(status.get("message") or "needs setup")
        self.status = status


@dataclass(frozen=True)
class Live:
    key: str
    label: str
    unit: str
    fn: Callable          # (reader) -> (value, note) or (value, note, drill[, status[, counted]])
    href: str
    # What a figure over a ranked or limited set is a subset of, as on a Kpi.
    subset_of: str | None = None
    # "erp" reads the business's ERPNext now. A fact name means the figure is worked out
    # from that loaded fact (matched against another), so it carries the fact's as-of
    # date and load state rather than "read just now".
    source: str = "erp"
    # False for a figure worked out from this platform's own tables alone (the loads,
    # the alerts, the loaded facts): it is cheap, and it is worked out at every look
    # rather than kept with the figures that wait on the business's ERPNext (speed.py).
    reads_erp: bool = True


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
            from command_center.ingest.company import scoped
            # The business's company only, where its ERPNext keeps several.
            self.conn = scoped(connector_for(self.code))

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
# Read behind the screens and kept (kpi/history.py): the change log is the largest table
# on a site, and these figures are stated as at the time it was read.
def _history(r):
    from command_center.kpi import history
    got = history.summary(r)
    return got["data"], history.status(got)


def versions_total(r):
    import frappe
    h, st = _history(r)
    first = h["first"]
    return h["total"], (f"since {frappe.utils.format_date(first, 'd MMMM yyyy')}"
                        if first else "nothing recorded"), None, st


def versions_business(r):
    h, st = _history(r)
    return h["business"], "invoices, orders, payments, stock", None, st


def versions_earliest(r):
    import frappe
    h, st = _history(r)
    first = h["first"]
    if not first:
        return None, "nothing recorded", None, st
    months = frappe.utils.month_diff(frappe.utils.today(), first)
    return str(first)[:10], f"{months} months of history", None, st


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
            f"{len(rows)} Purchase Orders in Draft")


def po_drafts_oldest(r):
    import frappe
    rows = _po(r, {"docstatus": 0}, ["transaction_date"])
    dates = [x["transaction_date"] for x in rows if x.get("transaction_date")]
    if not dates:
        return None, "no drafts"
    oldest = min(str(d) for d in dates)
    return (frappe.utils.date_diff(_po_horizon(r), oldest),
            f"since {frappe.utils.format_date(oldest, 'MMMM yyyy')}")


def amended(r, doctype) -> set:
    """The documents that were cancelled only to be amended: every name another document
    of the doctype names as `amended_from`. ERPNext amends by cancelling the original and
    making "-1", "-2" from it, so a cancelled original is a correction, not a withdrawal:
    on Gigmann's site 132 purchase orders worth GHS 19.46M were cancelled, and 127 of
    them were amended -- 5, worth GHS 569,924, were really withdrawn (17 Nov 2026)."""
    return {x.get("amended_from") for x in r.all(doctype, filters={"amended_from": ["is", "set"]},
                                                  fields=["amended_from"], limit=500000)
            if x.get("amended_from")}


def withdrawn(r, doctype, rows) -> list:
    """Of docstatus-2 rows (each with its name), those really withdrawn: not amended.
    Every count of cancelled documents goes through here (preflight)."""
    gone = amended(r, doctype)
    return [x for x in rows if x.get("name") not in gone]


def po_cancelled(r):
    from command_center.api.businesses import currency_for
    rows = withdrawn(r, "Purchase Order",
                     _po(r, {"docstatus": 2}, ["name", "base_grand_total"]))
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


# --------------------------------------------------------------------------- guards
def _read(r, doctype, filters, fields, **kw):
    """r.all, refusing a reply that lost a column.

    A doctype the key may list but not read field by field (Issue on Gigmann's site has
    Custom DocPerms granting read to no role) comes back with name and modified only, and
    Frappe says nothing. Reading "no resolution date" off such a row would turn an
    unreadable source into a finding, so the card says "could not be read" instead.
    """
    from command_center.ingest.base import require_fields
    return require_fields(r.all(doctype, filters=filters, fields=fields, **kw),
                          [f for f in fields if " as " not in f], doctype)


def _cur(r):
    from command_center.api.businesses import currency_for
    return currency_for(r.code) or ""


# --------------------------------------------------------------------------- buying, more
def po_spend_top14(r):
    """The fourteen largest submitted purchase orders, as the panel beside it shows them."""
    rows = _read(r, "Purchase Order", {"docstatus": 1}, ["supplier", "base_grand_total"],
                 limit=14, order_by="base_grand_total desc")
    total = sum(float(x.get("base_grand_total") or 0) for x in rows)
    if not rows:
        return None, "no Purchase Order submitted"
    by = {}
    for x in rows:
        by[x.get("supplier")] = by.get(x.get("supplier"), 0.0) + float(x.get("base_grand_total") or 0)
    ranked = sorted(by.values(), reverse=True)
    if len(ranked) == 1:
        return total, "one supplier, all of it"
    two = sum(ranked[:2])
    return total, f"2 suppliers are {round(100 * two / total) if total else 0}% of it"


def _no_due_date(r):
    rows = _read(r, "Purchase Order", {"docstatus": 1},
                 ["name", "transaction_date", "schedule_date", "base_grand_total"])
    return [x for x in rows if not x.get("schedule_date")
            or str(x["schedule_date"])[:10] == str(x.get("transaction_date") or "")[:10]]


def po_no_due_date(r):
    rows = _no_due_date(r)
    total = sum(float(x.get("base_grand_total") or 0) for x in rows)
    return len(rows), (f"{_cur(r)} {total:,.0f}".strip() if rows else "every order has a date")


# --------------------------------------------------------------------------- money in & out
def postings_count(r):
    pay = r.count("Payment Entry", {"docstatus": 1})
    jour = r.count("Journal Entry", {"docstatus": 1})
    return pay + jour, f"{pay:,} payments and {jour:,} journals"


# --------------------------------------------------------------------------- projects
PROJECT_COSTS = ("total_costing_amount", "total_expense_claim", "total_purchase_cost",
                 "total_consumed_material_cost")


def tasks_costed(r):
    """Open jobs that carry any cost: hours or expenses booked to the job, or any cost
    (hours, expenses, purchases, materials issued) booked to its project -- parts can
    only be issued to a project in ERPNext, never to one task."""
    from command_center.ingest.operations import CLOSED_TASK
    tasks = _read(r, "Task", {}, ["name", "status", "project", "total_costing_amount",
                                  "total_expense_claim"])
    open_ = [t for t in tasks if (t.get("status") or "") not in CLOSED_TASK]
    if not open_:
        return 0, "no open jobs"
    projects = sorted({t["project"] for t in open_ if t.get("project")})
    costed_projects = set()
    if projects:
        for p in _read(r, "Project", {"name": ["in", projects]}, ["name", *PROJECT_COSTS]):
            if any(float(p.get(f) or 0) > 0 for f in PROJECT_COSTS):
                costed_projects.add(p["name"])
    n = sum(1 for t in open_
            if float(t.get("total_costing_amount") or 0) > 0
            or float(t.get("total_expense_claim") or 0) > 0
            or t.get("project") in costed_projects)
    return n, f"of {len(open_)}"


# --------------------------------------------------------------------------- service
def cases_past_due(r):
    """Open cases past the resolution time their service level promised."""
    import frappe
    from command_center.ingest.operations import CLOSED_CASE
    rows = _read(r, "Issue", {"status": ["not in", sorted(CLOSED_CASE)]},
                 ["name", "status", "resolution_by"])
    if not rows:
        return 0, "no open cases"
    promised = [x for x in rows if x.get("resolution_by")]
    if not promised:
        from command_center.guides import needs_setup
        return None, "no response time set on any open case", None, needs_setup(
            r.code, "No open case carries a promised resolution time.",
            ["Open Service Level Agreement, click New, and set the response and resolution "
             "time for each priority.",
             "Tick Default Service Level Agreement so every new Issue gets it.",
             "Open cases already raised: open each one and choose the agreement."],
            "/app/service-level-agreement")
    now = frappe.utils.now_datetime()
    late = [frappe.utils.get_datetime(x["resolution_by"]) for x in promised
            if frappe.utils.get_datetime(x["resolution_by"]) < now]
    if not late:
        return 0, "every open case within its promise"
    worst = max((now - d).days for d in late)
    return len(late), f"up to {worst} day{'' if worst == 1 else 's'}"


def cases_owing(r):
    """Open cases from customers who also owe the business money: two loaded facts,
    matched by customer."""
    import frappe

    from command_center.facts.schema import FACTS
    scope = {"business_code": r.code} if r.code else {}
    cases = frappe.get_all(FACTS["fact_case"], filters={**scope, "is_open": 1},
                           fields=["customer"], limit=100000)
    if not cases:
        return 0, "no open cases", {"fact": "fact_case", "filters": {"is_open": 1}}
    # Owing by the ledger, not by open invoices a payment may already have settled.
    owing = {x["party"] for x in frappe.get_all(
        FACTS["fact_party_balance"],
        filters={**scope, "party_type": "Customer", "owed": [">", 0]},
        fields=["party"], limit=100000) if x.get("party")}
    both = sorted({c["customer"] for c in cases if c.get("customer") in owing})
    n = sum(1 for c in cases if c.get("customer") in owing)
    return n, f"of {len(cases)} open", {"fact": "fact_case", "filters": (
        {"is_open": 1, "customer": ["in", both]} if both else {"is_open": 1})}


# --------------------------------------------------------------------------- stock
EXPIRY_DAYS = 90


def batches_near_expiry(r):
    """Batches still holding stock whose expiry date falls in the next ninety days."""
    import frappe
    rows = _read(r, "Batch", {"expiry_date": ["is", "set"], "batch_qty": [">", 0]},
                 ["name", "expiry_date", "batch_qty"])
    if not rows and not r.count("Batch", {"expiry_date": ["is", "set"]}):
        from command_center.guides import needs_setup
        return None, "no expiry dates recorded", None, needs_setup(
            r.code, "No batch in ERPNext carries an expiry date yet.",
            ["Open each Item that expires, tick Has Batch No and Has Expiry Date, and save.",
             "When goods arrive (Purchase Receipt), enter the Batch No and its Expiry Date "
             "on each line.",
             "Stock already in stock: give it a batch with its expiry date through a "
             "Stock Reconciliation."], "/app/item")
    today = frappe.utils.getdate(frappe.utils.today())
    edge = frappe.utils.getdate(frappe.utils.add_days(today, EXPIRY_DAYS))
    dates = [frappe.utils.getdate(x["expiry_date"]) for x in rows if x.get("expiry_date")]
    soon = sum(1 for d in dates if today <= d <= edge)
    gone = sum(1 for d in dates if d < today)
    return soon, (f"within {EXPIRY_DAYS} days" + (f" · {gone} already past expiry" if gone else ""))


# --------------------------------------------------------------------------- approvals
APPROVED_DOCTYPES = ("Purchase Order", "Payment Entry")


def self_approved(r):
    """Submitted purchase orders and payments whose every recorded approval step was
    taken by the account that raised them.

    The change log records each step as a change to workflow_state, with who made it.
    A document whose steps are not in the log (no workflow, or the log not kept for that
    doctype) is not counted either way. Worked out behind the screens (kpi/history.py)."""
    h, st = _history(r)
    return h["alone"], "found in the change history", None, st


# --------------------------------------------------------------------------- bank
def bank_payments(banks) -> list:
    """The Payment Entry filters that find each payment through a bank account once: paid
    from one, or paid into one from somewhere that is not. A transfer between two bank
    accounts is paid from one and into the other, and counting both sides counted it
    twice (17 Nov 2026)."""
    return [{"docstatus": 1, "paid_from": ["in", banks]},
            {"docstatus": 1, "paid_to": ["in", banks], "paid_from": ["not in", banks]}]


def bank_cleared_pct(r):
    """Of the payments made through a bank account, how many carry a clearance date --
    the date ERPNext's bank reconciliation records when a payment is matched to the
    statement."""
    banks = [a["name"] for a in r.all("Account", filters={"account_type": "Bank", "is_group": 0},
                                      fields=["name"], limit=500)]
    if not banks:
        from command_center.guides import needs_setup
        return None, "no Account with Account Type Bank", None, needs_setup(
            r.code, "No Account in ERPNext has Account Type Bank.",
            ["Open Chart of Accounts and click each bank account.",
             "Set Account Type to Bank and save.",
             "Match payments to each statement in Bank Reconciliation Tool; that records "
             "the clearance date this card counts."], "/app/account/view/tree")
    total = cleared = 0
    for base in bank_payments(banks):
        total += r.count("Payment Entry", base)
        cleared += r.count("Payment Entry", {**base, "clearance_date": ["is", "set"]})
    if not total:
        return None, "no Payment Entry through a Bank Account"
    return round(100 * cleared / total, 4), f"of {total:,} bank payments have a Clearance Date"


# --------------------------------------------------------------------------- payroll
def payroll_last_run(r):
    """When pay was last run: the latest pay period a submitted salary slip covers.
    Dates and a count only -- no amount is read."""
    from command_center.guides import needs_setup
    steps = ["Open Payroll Entry, choose the company, the pay period and the employees, "
             "and click Get Employees.",
             "Click Create Salary Slips, check them, then Submit Salary Slip."]
    if not r.has("Salary Slip"):
        return None, "payroll is not in this ERPNext", None, needs_setup(
            r.code, "Payroll is not set up in this ERPNext (the HR and payroll app is not "
                    "installed).", ["Ask your ERPNext administrator to install the HRMS "
                                    "app, then set up Salary Structures."] + steps, "/app")
    last = r.edge("Salary Slip", "end_date", {"docstatus": 1})
    if not last:
        return None, "no pay run submitted", None, needs_setup(
            r.code, "No pay run has been submitted in ERPNext yet.", steps,
            "/app/payroll-entry/new")
    n = r.count("Salary Slip", {"docstatus": 1, "end_date": str(last)[:10]})
    return str(last)[:10], f"{n:,} slip{'s' if n != 1 else ''} for that period"


LIVE = {k.key: k for k in (
    Live("users_active", "Staff accounts", "count", users_active, "/app/user?enabled=1"),
    Live("users_disabled", "Disabled accounts", "count", users_disabled, "/app/user?enabled=0"),
    Live("users_manager_roles", "Accounts with a manager role", "count", users_manager_roles, "/app/user?enabled=1"),
    Live("users_role_conflicts", "Can buy and pay", "count", users_role_conflicts, "/app/user?enabled=1"),
    Live("departments_erp", "Departments", "count", departments_erp, "/app/department"),
    Live("last_refreshed", "Last refreshed", "time", last_refreshed, "/app/command-center-ingest-state",
         reads_erp=False),
    Live("versions_total", "Changes logged", "count", versions_total, "/app/version"),
    Live("versions_business", "Changes on business documents", "count", versions_business, "/app/version"),
    Live("versions_earliest", "Earliest change logged", "date", versions_earliest, "/app/version?order_by=creation%20asc"),
    Live("po_count", "Purchase Orders", "count", po_count, "/app/purchase-order?docstatus=1"),
    Live("po_drafts_value", "Purchase orders never submitted", "currency", po_drafts_value, "/app/purchase-order?docstatus=0"),
    Live("po_drafts_oldest", "Oldest unsubmitted purchase order", "days", po_drafts_oldest, "/app/purchase-order?docstatus=0"),
    Live("po_cancelled", "Purchase orders withdrawn", "count", po_cancelled, "/app/purchase-order?docstatus=2"),
    Live("po_longest_wait", "Oldest Purchase Order To Receive", "days", po_longest_wait, "/app/purchase-order?docstatus=1"),
    Live("po_spend_top14", "Top 14 Purchase Orders, Grand Total", "currency", po_spend_top14,
         "/app/purchase-order?docstatus=1", subset_of="the 14 largest submitted Purchase Orders"),
    Live("po_no_due_date", "Purchase Orders with No Required By", "count", po_no_due_date, "/app/purchase-order?docstatus=1"),
    Live("postings_count", "Payment Entries and Journal Entries", "count", postings_count, "/app/payment-entry?docstatus=1"),
    Live("tasks_costed", "Open jobs with a cost", "count", tasks_costed, "/app/task"),
    Live("cases_past_due", "Cases past their promised time", "count", cases_past_due, "/app/issue"),
    Live("cases_owing", "Open cases from customers who owe us", "count", cases_owing, "",
         source="fact_case", reads_erp=False),
    Live("batches_near_expiry", "Batches Near Expiry", "count", batches_near_expiry,
         "/app/batch?disabled=0"),
    Live("self_approved", "Approved by whoever raised them", "count", self_approved, "/app/version"),
    Live("bank_cleared_pct", "Bank Reconciled Payments", "percent", bank_cleared_pct,
         "/app/payment-entry?docstatus=1"),
    Live("payroll_last_run", "Last pay run", "date", payroll_last_run,
         "/app/salary-slip?docstatus=1"),
)}


# Figures defined in sibling modules, registered into the one map.
from command_center.kpi import live_governance as _governance  # noqa: E402

LIVE.update(_governance.LIVE)


def evaluate(keys, business_code=None) -> dict:
    """The live figures asked for, in the engine's shape. Unknown keys are left out.

    Kept for a short while per business and whose view of its ERPNext (speed.py), and
    read side by side when they are read (speed.parallel), so a screen waits for its
    slowest figure rather than for all of them one after another."""
    wanted = [k for k in keys if k in LIVE]
    if not wanted:
        return {}
    from command_center import speed
    remote = sorted(k for k in wanted if LIVE[k].reads_erp)
    out = (speed.cached("live", business_code, {"keys": remote}, compute,
                        {"keys": remote, "business_code": business_code}, complete=complete)
           if remote else {})
    here = [k for k in wanted if not LIVE[k].reads_erp]
    if here:
        out.update(compute(here, business_code, side_by_side=False))
    return {k: out[k] for k in wanted if k in out}


def complete(out) -> bool:
    """Only an answer whose every figure was read is kept. A refused read is asked again
    too, so access granted in ERPNext shows at the next look."""
    return all((f.get("data_status") or {}).get("state") not in ("failed", "unreachable",
                                                                 "no_access")
               for f in (out or {}).values())


def _refused(error) -> bool:
    """A read the business's ERPNext refused by permission (connectors' RemotePermissionDenied)."""
    from command_center.connectors.base import RemotePermissionDenied
    return isinstance(error, RemotePermissionDenied)


def compute(keys, business_code=None, side_by_side: bool = True) -> dict:
    """The live figures, read now."""
    import frappe

    from command_center import speed
    from command_center.api.businesses import currency_for

    wanted = [k for k in keys if k in LIVE]
    reader = None
    try:
        # Guarded: once the business has not answered, the other figures give up at once
        # instead of each waiting out the retries (figures worked out from the loaded
        # facts alone still answer).
        from command_center.api.panels import _Guarded
        reader = _Guarded(_Reader(business_code))
    except Exception:
        frappe.log_error(title="Command Center live figures", message=frappe.get_traceback())

    def read(spec):
        if reader is None:
            raise RuntimeError("no business to read")
        return spec.fn(reader)

    with speed.interactive():
        jobs = [(lambda spec=LIVE[k]: read(spec)) for k in wanted]
        answers = speed.parallel(jobs) if side_by_side else [speed.attempt(j) for j in jobs]
    now_at = frappe.utils.now_datetime().strftime("%H:%M")
    out = {}
    for key, (ok, got) in zip(wanted, answers):
        spec = LIVE[key]
        drill = None
        counted = None
        read_at = None
        if ok:
            value, note = got[0], got[1]
            drill = got[2] if len(got) > 2 else None
            # A fourth element is the figure's own status: needs_setup (guides.py) when
            # nothing behind it is recorded in ERPNext yet.
            state = (got[3] if len(got) > 3 and got[3] else {"state": "live", "message": None})
            # A figure read behind the screens (kpi/history.py) says when it was read.
            read_at = state.get("read_at")
            state = {k: v for k, v in state.items() if k != "read_at"}
            # A fifth is how many records a share was counted over (Business Health's
            # "counted from", command_center/health.py).
            counted = got[4] if len(got) > 4 else None
        elif isinstance(got, NeedsSetup):
            value, note, state = None, got.status.get("message"), got.status
        elif _refused(got):
            # The business's ERPNext refused the read (HTTP 401/403): not a failure but an
            # access to grant there, named with the record type refused (guides.no_access).
            from command_center.guides import no_access
            state = no_access(reader.code if reader else business_code, got)
            value, note = None, f"no access to {state['doctype']}" if state.get("doctype") \
                else "no access in ERPNext"
        else:
            from command_center.kpi.live_departments import is_down, unreachable_status
            if is_down(got):
                # The business's ERPNext did not answer: once is enough for this screen
                # (the guarded reader fails the others at once), and the card says so
                # rather than "could not be read".
                value, note, state = None, "waiting for ERPNext", unreachable_status(got)
                from command_center.connectors.base import NotWorkedOut
                if isinstance(got, NotWorkedOut):
                    state["pending"] = True  # worked out behind the screens, started now
            else:
                frappe.log_error(title=f"Command Center live figure {key}",
                                 message=getattr(got, "__cc_traceback__", "") or repr(got))
                value, note, state = None, "could not be read", {"state": "failed",
                                                                "message": "This figure could not be read."}
        site = "" if not reader or reader.local else (reader.conn.base_url or "")
        as_of = ({"date": read_at[:10], "basis": f"read from ERPNext at {read_at[11:16]}"}
                 if read_at else
                 {"date": frappe.utils.today(), "basis": f"read from ERPNext at {now_at}"})
        if spec.source != "erp":
            # Worked out from loaded facts: as of the data they cover, and as fresh as
            # their last load -- the same statement an engine figure makes.
            from command_center.kpi.engine import _load_state, _status
            loaded = _load_state(spec.source, reader.code if reader else business_code)
            as_of = ({"date": str(loaded["as_of_date"]),
                      "basis": "the latest date the data covers"}
                     if loaded and loaded.get("as_of_date") else None)
            if state["state"] == "live":
                state = _status(loaded)
        if drill is None:
            # The ERPNext list itself: on this site, or on the business's own site.
            # (The load history is this platform's own list, wherever the business is.)
            drill = {"href": spec.href if key == "last_refreshed" else site + spec.href}
        elif drill.get("href"):
            drill = {"href": site + drill["href"]}
        out[key] = {
            "key": key, "label": spec.label, "value": value, "unit": spec.unit,
            "direction": "neutral",
            "currency": currency_for(reader.code if reader else business_code)
            if spec.unit == "currency" else None,
            "mixed_currency": False, "scope": business_code or "__all__",
            "as_of": as_of, "basis": spec.subset_of, "note": note,
            "drill": drill, "data_status": state, "period": None, "group": None,
        }
        if counted is not None:
            out[key]["counted"] = counted
    return out


# The department screens' figures (kpi/live_departments.py) join these.
from command_center.kpi.live_departments import FIGURES as _DEPARTMENTS  # noqa: E402
LIVE.update(_DEPARTMENTS)
