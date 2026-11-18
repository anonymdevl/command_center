"""The recommendation rules.

Each rule reads one business -- the loaded facts (the ledger balances above all: what is
owed is the ledger, never the open invoices), the KPI engine's figures, or a light
read of the business's own ERPNext through its connector -- and returns zero or more
recommendations. A rule whose data is not there returns nothing: a recommendation is a
finding about the business, never about what the platform could not read.

A rule returns a list of dicts:

    key          what makes this one distinct within the rule ("" for one per rule,
                 a customer's name for one per customer); the state is kept against it
    title        one plain sentence
    why          the evidence: the numbers that made the rule fire, from the data
    what_to_do   two to four short steps
    how          a guide (command_center/guides.py) to doing it in ERPNext, with a link
    ask          a question for the analyst
    drill        {"fact", "filters"} for the records drawer, or {"href"} into ERPNext
    money        the money at stake, in the business's currency (0 when there is none)
    count        how many (customers, documents, products) -- shown when money is 0
    unit         what count counts
    severity     only when it differs from the rule's

Thresholds are the rule's params, with defaults here; a business's administrator can
change them (Settings -> Recommendations), which reach the rule as `p`.

Importing this module touches no frappe, so preflight can read the catalogue.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from command_center.coverage import AFTER_DAYS, WINDOW_DAYS

AREAS = {
    "cash": "Accounts Receivable and Payable",
    "sales": "Sales",
    "margin": "Gross Profit",
    "stock": "Stock",
    "buying": "Buying",
    "control": "Approvals and Staff",
    "data": "Incomplete Records",
}
SEVERITY_WEIGHT = {"crit": 1.0, "high": 0.7, "med": 0.4, "info": 0.2}
SEVERITY_RANK = {"crit": 0, "high": 1, "med": 2, "info": 3}


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    default: float
    unit: str = "amount"          # amount | days | percent | count | points


@dataclass(frozen=True)
class Rule:
    rule_id: str
    area: str
    title: str                    # what it watches, for Settings
    severity: str
    owner: str
    fn: Callable
    params: tuple = field(default_factory=tuple)
    # The alert rule (alerts/rules.py) that watches the same thing: the bell shows the
    # alert and leaves this out, so one issue is never shown twice.
    twin_alert: str | None = None


# --------------------------------------------------------------------------- helpers
def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def m(ctx, v) -> str:
    """GHS 7,254,533."""
    return f"{ctx.cur} {_num(v):,.0f}".strip()


def ms(ctx, v) -> str:
    """GHS 7.25M -- the short form, for titles."""
    v = _num(v)
    for div, suf, dp in ((1e9, "B", 2), (1e6, "M", 2), (1e3, "k", 0)):
        if abs(v) >= div:
            return f"{ctx.cur} {v / div:,.{dp}f}{suf}".strip()
    return f"{ctx.cur} {v:,.0f}".strip()


def pct(a, b) -> float:
    return 100.0 * a / b if b else 0.0


def plural(n, word, many=None) -> str:
    return f"{n:,} {word if n == 1 else (many or word + 's')}"


def names(items, n=3) -> str:
    items = [str(x) for x in items if x][:n]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def date(v) -> str:
    import frappe
    return frappe.utils.getdate(v).strftime("%-d %b %Y") if v else ""


def month_label(d) -> str:
    return d.strftime("%B %Y")


def how(ctx, text, steps, path=None, label="Open in ERPNext", href=None):
    from command_center.guides import guide
    g = guide(ctx.code, text, steps, path, label=label)
    if href:
        g["href"], g["label"] = href, label
    return g


def _slug(doctype: str) -> str:
    return doctype.lower().replace(" ", "-")


def positions(ctx, party_type):
    from command_center.api.panels import _positions
    key = f"_pos_{party_type}"
    if key not in ctx.__dict__:
        ctx.__dict__[key] = _positions(ctx, party_type)
    return ctx.__dict__[key]


def since(ctx, days):
    import frappe
    return frappe.utils.getdate(frappe.utils.add_days(ctx.as_of, -int(days)))


def today(ctx):
    import frappe
    return frappe.utils.getdate(frappe.utils.today())


def held(ctx):
    """Per product: quantity held, value, reserved, on order, valuation rate."""
    if "_held" not in ctx.__dict__:
        out = defaultdict(lambda: {"qty": 0.0, "value": 0.0, "reserved": 0.0, "ordered": 0.0,
                                   "valued": True})
        for r in ctx.rows("fact_stock_balance", ["item_code", "actual_qty", "stock_value",
                                                 "reserved_qty", "ordered_qty", "has_valuation"]):
            x = out[r["item_code"]]
            x["qty"] += _num(r["actual_qty"])
            x["value"] += _num(r["stock_value"])
            x["reserved"] += _num(r["reserved_qty"])
            x["ordered"] += _num(r["ordered_qty"])
            if _num(r["actual_qty"]) > 0 and not r["has_valuation"]:
                x["valued"] = False
        for x in out.values():
            x["rate"] = x["value"] / x["qty"] if x["qty"] > 0 and x["value"] > 0 else 0.0
        ctx.__dict__["_held"] = dict(out)
    return ctx.__dict__["_held"]


def grouped(ctx, doctype, filters, group_by, aggs, parent=None):
    """kpi/live_departments.grouped through the screen's guarded reader: once the
    business has not answered, the next read gives up at once rather than waiting out
    the retries again (a grouped read goes to the connector itself)."""
    from command_center.kpi.live_departments import grouped as _grouped, is_down
    r = ctx.reader()
    down = getattr(r, "_down", None)
    if down is not None:
        raise down
    try:
        return _grouped(r, doctype, filters, group_by, aggs, parent=parent)
    except Exception as e:
        if is_down(e):
            try:
                r._down = e
            except AttributeError:
                pass
        raise


# What takes stock out of the business: a sale (its delivery or an invoice that updates
# stock). A Stock Entry counts only for what it consumed -- its net for an item, so a
# Material Transfer, which takes from one warehouse and puts into another, nets to nothing
# and is no sale (17 Nov 2026: transfers kept slow stock "moving"). A Stock
# Reconciliation's correction, a return to a supplier and a stock receipt are not use.
SOLD_VOUCHERS = ("Delivery Note", "Sales Invoice", "POS Invoice")


def outflow(ctx, days):
    """Per product, what was sold or consumed in the last `days` days, read from the
    business's Stock Ledger: {item: (quantity, movements)}. Sums and counts only -- v14
    refuses min()/max() in a list read."""
    import frappe
    key = f"_out_{days}"
    if key not in ctx.__dict__:
        frm = str(frappe.utils.add_days(frappe.utils.today(), -int(days)))
        ctx.__dict__[key] = stock_used(ctx, frm)
    return ctx.__dict__[key]


def stock_used(ctx, frm=None, last=False) -> dict:
    """{item: (quantity sold or consumed, movements[, latest date])} since `frm` (or ever):
    the one definition of stock going out for good (SOLD_VOUCHERS above)."""
    base = {"is_cancelled": 0}
    if frm:
        base["posting_date"] = [">=", str(frm)]
    aggs = [("sum", "actual_qty", "out_qty"), ("count", "name", "moves")]
    if last:
        aggs.append(("max", "posting_date", "last_date"))
    out = {}

    def add(item, qty, moves, day):
        q, n, d = out.get(item, (0.0, 0, None))
        d = max([x for x in (d, str(day) if day else None) if x], default=None)
        out[item] = (q + qty, n + moves, d)
    for r in grouped(ctx, "Stock Ledger Entry",
                     {**base, "actual_qty": ["<", 0], "voucher_type": ["in", list(SOLD_VOUCHERS)]},
                     "item_code", aggs):
        if r.get("item_code"):
            add(r["item_code"], abs(_num(r.get("out_qty"))), int(_num(r.get("moves"))),
                r.get("last_date"))
    # A Stock Entry, per item and entry: what it took out net of what it put back.
    for r in grouped(ctx, "Stock Ledger Entry", {**base, "voucher_type": "Stock Entry"},
                     "item_code, voucher_no", aggs):
        net = _num(r.get("out_qty"))
        if r.get("item_code") and net < 0:
            add(r["item_code"], -net, 1, r.get("last_date"))
    return {k: (v[0], v[1], v[2]) if last else (v[0], v[1]) for k, v in out.items()}


def _rec(**kw):
    kw.setdefault("key", "")
    kw.setdefault("money", 0.0)
    return kw


# =========================================================================== cash and credit
def unmatched_receipts(ctx, p):
    rows = positions(ctx, "Customer")
    paid = sum(r["unmatched_payments"] for r in rows)
    n = int(sum(r["unmatched_payment_count"] for r in rows))
    if paid <= p["amount"] or not n:
        return []
    from command_center.guides import payment_reconciliation
    top = sorted([r for r in rows if r["unmatched_payments"] > 0],
                 key=lambda r: -r["unmatched_payments"])
    owed, on_docs = sum(r["owed"] for r in rows), sum(r["open_invoices"] for r in rows)
    largest = "; ".join(f"{r['party']} {m(ctx, r['unmatched_payments'])}" for r in top[:3])
    return [_rec(
        title=f"Match {ms(ctx, paid)} of customer payments to the invoices they pay.",
        why=(f"{m(ctx, paid)} received in {plural(n, 'payment')} from "
             f"{plural(len(top), 'customer')} is not reconciled. Until it is, "
             f"Sales Invoice Outstanding is {m(ctx, on_docs)} where the Customer Ledger Balance is "
             f"{m(ctx, owed)}, and every reminder drawn from the invoices is wrong. "
             f"Largest: {largest}."),
        what_to_do=[f"Start with the largest: {top[0]['party']}.",
                    "Reconcile each payment in Payment Reconciliation.",
                    "Ask whoever records receipts to allocate each one to its invoice when "
                    "it is entered."],
        how=payment_reconciliation(ctx.code, f"Match the {plural(n, 'payment')} to their "
                                             f"invoices in ERPNext:"),
        ask="Which customers have unreconciled payments, and what is each "
            "Customer Ledger Balance?",
        drill={"fact": "fact_party_balance",
               "filters": {"party_type": "Customer", "unmatched_payments": [">", 0]}},
        money=paid, count=n, unit="payments")]


def customers_in_credit(ctx, p):
    rows = [r for r in positions(ctx, "Customer") if r["in_credit"] > 0]
    total = sum(r["in_credit"] for r in rows)
    if total <= p["amount"]:
        return []
    rows.sort(key=lambda r: -r["in_credit"])
    largest = "; ".join(f"{r['party']} {m(ctx, r['in_credit'])}" for r in rows[:3])
    return [_rec(
        title=f"{plural(len(rows), 'customer')} {'holds' if len(rows) == 1 else 'hold'} "
              f"{ms(ctx, total)} in credit: refund it or use it.",
        why=(f"On the Customer Ledger {plural(len(rows), 'customer')} have paid {m(ctx, total)} more than "
             f"they were billed. Largest: {largest}. Money held for customers is owed back "
             f"to them unless it is an advance for an order still to come."),
        what_to_do=["Ask each of the largest whether the credit is an advance for an order.",
                    "If it is not, refund it or set it against their next invoice.",
                    "Send each a statement so both sides agree the balance."],
        how=how(ctx, "To use a customer's credit in ERPNext:",
                ["Accounts, Payment Reconciliation: choose the customer and set the credit "
                 "against an open invoice.",
                 "To refund it: Payment Entry, Payment Type Pay, Party Type Customer, the "
                 "customer, and the amount; submit once approved.",
                 "Accounts, Statement of Accounts, to send the customer their balance."],
                "/app/payment-reconciliation", "Open Payment Reconciliation"),
        ask="Which customers are in credit with us, by how much, and since when?",
        drill={"fact": "fact_party_balance",
               "filters": {"party_type": "Customer", "in_credit": [">", 0]}},
        money=total, count=len(rows), unit="customers")]


def overdue_customers(ctx, p):
    from command_center.api.panels import _ledger_href
    rows = sorted([r for r in positions(ctx, "Customer") if r["d90_plus"] > p["amount"]],
                  key=lambda r: -r["d90_plus"])
    out = []
    for r in rows[:int(p["max_items"])]:
        party, late = r["party"], r["d90_plus"]
        since_txt = (f", the oldest due {date(r['oldest_due_after_matching'])}"
                     if r.get("oldest_due_after_matching") else "")
        out.append(_rec(
            key=party,
            title=f"Get a payment date from {party} for {ms(ctx, late)} more than 90 days late.",
            why=(f"{party} owes {m(ctx, r['owed'])} on the Customer Ledger; {m(ctx, late)} of it is more "
                 f"than 90 days past due once unreconciled payments are set against the "
                 f"oldest invoices{since_txt}."),
            what_to_do=[f"Call {party} this week and agree a date for the {ms(ctx, late)}.",
                        "Send the statement of account so both sides work from the Customer Ledger.",
                        "If no date is agreed, stop new credit until it is paid."],
            how=how(ctx, f"{party}'s account in the General Ledger, to send with the call:",
                    ["Open the General Ledger report for the customer (the link below).",
                     "Print or email it as their statement (Menu, Print or Email).",
                     "Record the date agreed as a comment on the customer, or a To-Do."],
                    href=_ledger_href(ctx, "Customer", party), label="Open General Ledger"),
            ask=f"What should I say to {party} about what they owe?",
            drill={"fact": "fact_party_balance", "filters": {"party_type": "Customer",
                                                             "party": party}},
            money=late, severity="crit" if late >= p["crit_amount"] else None))
    return out


def credit_hold(ctx, p):
    late = {r["party"]: r["d90_plus"] for r in positions(ctx, "Customer")
            if r["d90_plus"] > p["amount"]}
    if not late:
        return []
    frm = since(ctx, p["days"])
    sold = defaultdict(float)
    for r in ctx.rows("fact_sales_invoice", ["customer", "base_grand_total"],
                      lambda t: [t.src_docstatus == 1, t.is_return == 0, t.posting_date >= frm,
                                 t.customer.isin(sorted(late))]):
        sold[r["customer"]] += _num(r["base_grand_total"])
    who = sorted([c for c in sold if sold[c] > 0], key=lambda c: -late[c])
    if not who:
        return []
    at_stake = sum(late[c] for c in who)
    listed = "; ".join(f"{c}: {m(ctx, late[c])} over 90 days late, {m(ctx, sold[c])} invoiced "
                       f"since {date(frm)}" for c in who[:3])
    from urllib.parse import quote
    return [_rec(
        title=f"Stop new credit to {plural(len(who), 'customer')} still buying while "
              f"{ms(ctx, at_stake)} is over 90 days late.",
        why=(f"{plural(len(who), 'customer')} were invoiced again in the last "
             f"{int(p['days'])} days while owing more than {m(ctx, p['amount'])} over 90 "
             f"days late on the Customer Ledger. {listed}."),
        what_to_do=[f"Agree with sales that {names(who)} buy for cash or not at all until "
                    f"they pay.",
                    "Set a credit limit on each so new orders stop for approval.",
                    "Call each with the statement and agree a payment date."],
        how=how(ctx, "To set a credit limit in ERPNext:",
                ["Open the Customer, section Credit Limit and Payment Terms.",
                 "Add a row: the Company and the Credit Limit (zero allows no credit).",
                 "Leave Bypass Credit Limit Check at Sales Order unticked, then save."],
                f"/app/customer/{quote(who[0])}", "Open the Customer"),
        ask="Which customers are we still selling to while they owe us money over 90 days "
            "old?",
        drill={"fact": "fact_sales_invoice",
               "filters": {"customer": ["in", who], "posting_date": [">=", str(frm)],
                           "src_docstatus": 1}},
        money=at_stake, count=len(who), unit="customers")]


def days_to_pay_worsening(ctx, p):
    from command_center.kpi.sales import RECEIVED
    now_from, before_from = since(ctx, 90), since(ctx, 180)
    rows = ctx.rows("fact_payment_allocation",
                    ["posting_date", "days_to_pay", "allocated_amount"],
                    lambda t: [t.payment_type == RECEIVED["payment_type"],
                               t.against_doctype == RECEIVED["against_doctype"],
                               t.posting_date >= before_from, t.posting_date <= ctx.as_of])
    import frappe

    def avg(part):
        w = sum(_num(r["allocated_amount"]) for r in part)
        return (sum(_num(r["days_to_pay"]) * _num(r["allocated_amount"]) for r in part) / w
                if w else None)
    recent = [r for r in rows if frappe.utils.getdate(r["posting_date"]) >= now_from
              and r["days_to_pay"] is not None]
    before = [r for r in rows if frappe.utils.getdate(r["posting_date"]) < now_from
              and r["days_to_pay"] is not None]
    if len(recent) < p["count"] or len(before) < p["count"]:
        return []
    a, b = avg(recent), avg(before)
    if a is None or b is None or a - b < p["days"]:
        return []
    owed = sum(r["owed"] for r in positions(ctx, "Customer"))
    return [_rec(
        title=f"Customers are paying {a - b:.0f} days later than three months ago.",
        why=(f"Payments matched to invoices in the 90 days to {date(ctx.as_of)} came "
             f"{a:.0f} days after the due date on average (weighted by amount, "
             f"{plural(len(recent), 'payment')}), against {b:.0f} days in the 90 days before "
             f"({plural(len(before), 'payment')}). Customers owe {m(ctx, owed)} on the Customer Ledger "
             f"now; the later they pay, the longer it waits."),
        what_to_do=["Find which customers slowed down: open the payments behind it.",
                    "Send reminders before the due date, not after it.",
                    "Agree the terms again with the slowest, or ask for part payment upfront."],
        how=how(ctx, "ERPNext's own view of who is late:",
                ["Open Accounts Receivable (the link below), ageing by due date.",
                 "Set Dunning Types and send Dunning to customers past due."],
                "/app/query-report/Accounts%20Receivable", "Open Accounts Receivable"),
        ask="Which customers are paying more slowly than three months ago?",
        drill={"fact": "fact_payment_allocation",
               "filters": {**RECEIVED, "posting_date": ["between", [str(now_from),
                                                                     str(ctx.as_of)]]}},
        money=owed)]


def _cash(ctx):
    """What the bank and cash accounts hold, as the ledger has them."""
    from command_center.api.panels import _guarded
    accounts = _guarded(ctx, "Account", {"account_type": ["in", ["Bank", "Cash"]], "is_group": 0},
                        ["name"], limit=500)
    if not accounts:
        return None
    rows = grouped(ctx, "GL Entry", {"account": ["in", [a["name"] for a in accounts]],
                                     "is_cancelled": 0}, "account",
                   [("sum", "debit", "debit_total"), ("sum", "credit", "credit_total")])
    return sum(_num(r.get("debit_total")) - _num(r.get("credit_total")) for r in rows)


def supplier_payments_due(ctx, p):
    import frappe

    from command_center.api.panels import _ahead
    rows = [r for r in positions(ctx, "Supplier") if r["owed"] > 0]
    if not rows:
        return []
    edge = frappe.utils.add_days(ctx.as_of, int(p["days"]))
    week = frappe.utils.add_days(ctx.as_of, 7)
    overdue = sum(r["overdue"] for r in rows)
    ahead = _ahead(ctx, "Supplier", rows)
    soon = sum(a for d, a in ahead if d <= frappe.utils.getdate(edge))
    in_week = sum(a for d, a in ahead if d <= frappe.utils.getdate(week))
    due = overdue + soon
    if due <= 0:
        return []
    cash = _cash(ctx)
    if cash is None or due <= cash * p["pct"] / 100.0:
        return []
    customers = [r for r in positions(ctx, "Customer") if r["owed"] > 0]
    coming = sum(a for d, a in _ahead(ctx, "Customer", customers)
                 if d <= frappe.utils.getdate(edge))
    days = int(p["days"])
    held_short = (f"the bank and cash accounts hold {ms(ctx, cash)}" if cash >= 0 else
                  f"the bank and cash accounts are {ms(ctx, -cash)} overdrawn")
    held_long = (f"The bank and cash accounts hold {m(ctx, cash)} per the General Ledger."
                 if cash >= 0 else
                 f"The bank and cash accounts are {m(ctx, -cash)} overdrawn per the General Ledger"
                 f"; if that is not so, the bank reconciliation is behind.")
    return [_rec(
        title=f"{ms(ctx, due)} is due to suppliers within {days} days; {held_short}.",
        why=(f"On the Supplier Ledger {m(ctx, overdue)} is already overdue to suppliers and "
             f"{m(ctx, soon)} more falls due by {date(edge)} ({m(ctx, in_week)} of it within "
             f"7 days). {held_long} "
             f"Customers are due to pay {m(ctx, coming)} in the same {days} days."),
        what_to_do=["Decide today which Purchase Invoices are paid first: the suppliers you cannot be "
                    "without.",
                    f"Chase the {ms(ctx, coming)} customers are due to pay in the same days.",
                    "Agree new dates with the other suppliers before their Purchase Invoices fall due."],
        how=how(ctx, "What is due to whom, in ERPNext:",
                ["Open Accounts Payable (the link below) and sort by due date.",
                 "Mark the Purchase Invoices to pay this week; record each payment as a Payment Entry "
                 "against its Purchase Invoice so the Purchase Invoice shows paid."],
                "/app/query-report/Accounts%20Payable", "Open Accounts Payable"),
        ask=f"Which Purchase Invoices fall due in the next {days} days, and can we pay them "
            f"from the bank?",
        drill={"fact": "fact_party_balance", "filters": {"party_type": "Supplier",
                                                         "owed": [">", 0]}},
        money=due, severity="crit" if due > cash else None)]


def unmatched_supplier_payments(ctx, p):
    rows = positions(ctx, "Supplier")
    paid = sum(r["unmatched_payments"] for r in rows)
    n = int(sum(r["unmatched_payment_count"] for r in rows))
    if paid <= p["amount"] or not n:
        return []
    from command_center.guides import payment_reconciliation
    top = sorted([r for r in rows if r["unmatched_payments"] > 0],
                 key=lambda r: -r["unmatched_payments"])
    largest = "; ".join(f"{r['party']} {m(ctx, r['unmatched_payments'])}" for r in top[:3])
    ahead = [r for r in rows if r["in_credit"] > 0]
    ahead_txt = (f" On the Supplier Ledger {m(ctx, sum(r['in_credit'] for r in ahead))} of it is really "
                 f"paid ahead of the Purchase Invoices ({plural(len(ahead), 'supplier')} in credit); the "
                 f"rest pays Purchase Invoices it was never matched to." if ahead else "")
    return [_rec(
        title=f"Match {ms(ctx, paid)} paid to suppliers to their Purchase Invoices before the next "
              f"payment run.",
        why=(f"{m(ctx, paid)} paid in {plural(n, 'payment')} is unreconciled, so the "
             f"Purchase Invoices show {m(ctx, sum(r['open_invoices'] for r in rows))} to pay where the "
             f"Supplier Ledger Balance is {m(ctx, sum(r['owed'] for r in rows))}. A payment run drawn from "
             f"the Purchase Invoices would pay some twice. Largest: {largest}.{ahead_txt}"),
        what_to_do=[f"Start with {top[0]['party']}.",
                    "Reconcile each payment in Payment Reconciliation.",
                    "Pay from the Supplier Ledger Balance, not from the list of open Purchase Invoices, until done."],
        how=payment_reconciliation(ctx.code, f"Match the {plural(n, 'payment')} to their Purchase Invoices "
                                             f"in ERPNext:"),
        ask="Which suppliers have unreconciled payments, and what is"
            " each Supplier Ledger Balance?",
        drill={"fact": "fact_party_balance",
               "filters": {"party_type": "Supplier", "unmatched_payments": [">", 0]}},
        money=paid, count=n, unit="payments")]


# =========================================================================== sales
def _months(ctx):
    """The last full month before the data's end, the one before it, and a year earlier:
    [(label, first, last)]."""
    import datetime as dt
    end = ctx.as_of.replace(day=1) - dt.timedelta(days=1)
    cur = (end.replace(day=1), end)
    prev_end = cur[0] - dt.timedelta(days=1)
    prev = (prev_end.replace(day=1), prev_end)
    import calendar
    try:
        first = cur[0].replace(year=cur[0].year - 1)
        ly = (first, first.replace(day=calendar.monthrange(first.year, first.month)[1]))
    except ValueError:
        ly = None
    return cur, prev, ly


def sales_falling(ctx, p):
    cur, prev, ly = _months(ctx)
    frm = ly[0] if ly else prev[0]
    rows = ctx.rows("fact_sales_invoice_line", ["posting_date", "item_group", "base_net_amount"],
                    lambda t: [t.src_docstatus == 1, t.posting_date >= frm,
                               t.posting_date <= cur[1]])
    import frappe
    by = defaultdict(lambda: [0.0, 0.0, 0.0])
    for r in rows:
        d = frappe.utils.getdate(r["posting_date"])
        g = r["item_group"] or "No Item Group"
        for i, span in enumerate((cur, prev, ly)):
            if span and span[0] <= d <= span[1]:
                by[g][i] += _num(r["base_net_amount"])
    out = []
    for g, (now, before, last_year) in by.items():
        base, base_span = (last_year, ly) if last_year > 0 else (before, prev)
        drop = base - now
        if base <= 0 or drop < p["amount"] or pct(drop, base) < p["pct"]:
            continue
        vs = "the same month last year" if base_span is ly else "the month before"
        out.append(_rec(
            key=g,
            title=f"Find out why {g} sales fell {pct(drop, base):.0f}% in "
                  f"{month_label(cur[0])}.",
            why=(f"{g} sold {m(ctx, now)} in {month_label(cur[0])}, against {m(ctx, base)} in "
                 f"{month_label(base_span[0])} ({vs}), {m(ctx, drop)} less. The month before "
                 f"it sold {m(ctx, before)}."),
            what_to_do=[f"Ask whoever sells {g} what changed: a lost customer, stock, or price.",
                        f"Check {g} was in stock through {month_label(cur[0])}.",
                        f"Call the customers who bought {g} in {month_label(base_span[0])} and "
                        f"not since."],
            how=how(ctx, "ERPNext's own comparison, by Item Group:",
                    ["Open Sales Analytics (the link below).",
                     "Set Tree Type to Item Group, Value or Qty to Value, Range Monthly."],
                    "/app/query-report/Sales%20Analytics", "Open Sales Analytics"),
            ask=f"Why did sales of {g} fall in {month_label(cur[0])} compared with "
                f"{month_label(base_span[0])}?",
            drill={"fact": "fact_sales_invoice_line",
                   "filters": {"item_group": g if g != "No product group" else ["is", "not set"],
                               "src_docstatus": 1,
                               "posting_date": ["between", [str(base_span[0]), str(base_span[1])]]}},
            money=drop))
    out.sort(key=lambda x: -x["money"])
    return out[:int(p["max_items"])]


def _sales_by_customer(ctx, frm, to):
    by = defaultdict(float)
    for r in ctx.rows("fact_sales_invoice_line", ["customer", "base_net_amount"],
                      lambda t: [t.src_docstatus == 1, t.posting_date >= frm,
                                 t.posting_date <= to]):
        by[r["customer"]] += _num(r["base_net_amount"])
    return by


def customer_concentration(ctx, p):
    frm = since(ctx, 365)
    by = _sales_by_customer(ctx, frm, ctx.as_of)
    total = sum(v for v in by.values() if v > 0)
    if total <= 0 or len(by) < 6:
        return []
    ranked = sorted([kv for kv in by.items() if kv[1] > 0], key=lambda kv: -kv[1])
    five = sum(v for _, v in ranked[:5])
    one = ranked[0][1]
    if pct(five, total) < p["pct"] and pct(one, total) < p["one_pct"]:
        return []
    shares = "; ".join(f"{c} {pct(v, total):.0f}%" for c, v in ranked[:3])
    return [_rec(
        title=f"Five customers bring {pct(five, total):.0f}% of sales: widen the base.",
        why=(f"In the year to {date(ctx.as_of)} the five largest customers bought "
             f"{m(ctx, five)} of {m(ctx, total)} sold ({len(ranked):,} customers bought). "
             f"{shares}. Losing one of them would show at once."),
        what_to_do=["Give each of the five a named account owner and meet them this quarter.",
                    "Pick the next ten customers to grow, and what to offer them.",
                    "Check the payment terms of the largest: are we financing them?"],
        how=how(ctx, "ERPNext's view of who buys what:",
                ["Open Sales Analytics (the link below), Tree Type Customer, Range Yearly."],
                "/app/query-report/Sales%20Analytics", "Open Sales Analytics"),
        ask="How dependent are we on our five largest customers, and how has it changed?",
        drill={"fact": "fact_sales_invoice_line",
               "filters": {"customer": ["in", [c for c, _ in ranked[:5]]],
                           "posting_date": [">=", str(frm)], "src_docstatus": 1}},
        money=five)]


def customers_gone_quiet(ctx, p):
    import frappe
    quiet = since(ctx, p["days"])
    frm = frappe.utils.getdate(frappe.utils.add_days(quiet, -365))
    months = defaultdict(set)
    bought = defaultdict(float)
    last = {}
    recent = set()
    for r in ctx.rows("fact_sales_invoice", ["customer", "posting_date", "base_grand_total"],
                      lambda t: [t.src_docstatus == 1, t.is_return == 0, t.posting_date >= frm]):
        d = frappe.utils.getdate(r["posting_date"])
        c = r["customer"]
        if d >= quiet:
            recent.add(c)
            continue
        months[c].add((d.year, d.month))
        bought[c] += _num(r["base_grand_total"])
        last[c] = max(last.get(c, d), d)
    gone = sorted([c for c in months if c not in recent and len(months[c]) >= p["count"]
                   and bought[c] >= p["amount"]], key=lambda c: -bought[c])
    if not gone:
        return []
    total = sum(bought[c] for c in gone)
    top = gone[0]
    return [_rec(
        title=f"Call {plural(len(gone), 'regular customer')} who stopped buying "
              f"{int(p['days'])} days ago.",
        why=(f"{plural(len(gone), 'customer')} who bought in at least {int(p['count'])} months "
             f"of the year to {date(quiet)} have bought nothing since. Between them they "
             f"bought {m(ctx, total)} that year. The largest is {top} ({m(ctx, bought[top])}, "
             f"last invoiced {date(last[top])})."),
        what_to_do=[f"Call {names(gone)} this week.",
                    "Find out why: price, service, a competitor, or the buyer moved on.",
                    "Offer a reason to come back: a visit, or a quote on what they used to buy."],
        how=how(ctx, "Who stopped buying, in ERPNext:",
                ["Open Inactive Customers (the link below), set Days Since Last Order.",
                 "Open each customer to see what they bought and who looked after them."],
                "/app/query-report/Inactive%20Customers", "Open Inactive Customers"),
        ask="Which regular customers have stopped buying from us, and what did they buy?",
        drill={"fact": "fact_sales_invoice",
               "filters": {"customer": ["in", gone[:200]], "src_docstatus": 1}},
        money=total, count=len(gone), unit="customers")]


def discounts_outside_price_list(ctx, p):
    from command_center.api.panels import _guarded
    import frappe
    frm = str(frappe.utils.add_days(frappe.utils.today(), -int(p["days"])))
    lines = _guarded(ctx, "Sales Invoice Item",
                     {"docstatus": 1, "discount_amount": [">", 0], "creation": [">=", frm]},
                     ["parent", "item_code", "qty", "price_list_rate", "rate", "pricing_rules"],
                     parent="Sales Invoice", limit=20000)
    loose = [x for x in lines if not (x.get("pricing_rules") or "").strip()
             and _num(x.get("price_list_rate")) > _num(x.get("rate"))]
    for x in loose:
        x["given"] = (_num(x["price_list_rate"]) - _num(x["rate"])) * _num(x.get("qty"))
    total = sum(x["given"] for x in loose)
    if total <= p["amount"]:
        return []
    loose.sort(key=lambda x: -x["given"])
    big = loose[0]
    from command_center.api.panels import PRICE_STEPS
    return [_rec(
        title=f"Put the {ms(ctx, total)} of discounts given outside the price list under a "
              f"rule.",
        why=(f"{plural(len(loose), 'invoice line')} in the last {int(p['days'])} days "
             f"{'was' if len(loose) == 1 else 'were'} sold below the Price List Rate with no "
             f"pricing rule behind them: {m(ctx, total)} below list. The largest is "
             f"{big['parent']}, {big.get('item_code') or 'one product'}, {m(ctx, big['given'])}."),
        what_to_do=["Decide which discounts are allowed, and record them as Pricing Rules.",
                    f"Ask who agreed the largest, on {big['parent']}.",
                    "Limit who may change the rate on an invoice."],
        how=how(ctx, "Allowed discounts belong in a Pricing Rule:", PRICE_STEPS,
                "/app/pricing-rule", "Open Pricing Rule"),
        ask="Which customers got discounts outside the price list, and who gave them?",
        drill={"href": f"{ctx.site()}/app/sales-invoice/{big['parent']}"},
        money=total, count=len(loose), unit="lines")]


LATE_BUCKETS = ["0-30", "31-60", "61-90", "90+"]   # kpi/operations.py order_book_late


def late_orders(ctx, p):
    f = ctx.figures(["order_book_late", "order_book_late_count"])
    value, n = _num(f["order_book_late"].get("value")), int(_num(f["order_book_late_count"].get("value")))
    if n <= p["count"] or value <= p["amount"]:
        return []
    by = defaultdict(float)
    for r in ctx.rows("fact_sales_order", ["customer", "undelivered_value"],
                      lambda t: [t.is_open == 1, t.lateness_bucket.isin(LATE_BUCKETS)]):
        by[r["customer"]] += _num(r["undelivered_value"])
    top = sorted(by, key=lambda c: -by[c])
    return [_rec(
        title=f"Agree new dates on {plural(n, 'order')} worth {ms(ctx, value)} past the date "
              f"promised.",
        why=(f"{plural(n, 'open order')} with {m(ctx, value)} still to deliver "
             f"{'is' if n == 1 else 'are'} past the delivery date given to the customer. "
             f"Most is for {names(top)}."),
        what_to_do=["Call the customers before they call you, and agree new dates.",
                    "Find what holds each order: stock, approval or transport.",
                    "Invoice whatever has already gone out."],
        how=how(ctx, "The late orders in ERPNext:",
                ["Open Sales Order, filter Status To Deliver and Bill, sort by Delivery Date.",
                 "Change the Delivery Date on each once the customer agrees (Update Items)."],
                "/app/sales-order?status=To%20Deliver%20and%20Bill", "Open the Orders"),
        ask="Which orders are past their promised delivery date, and what is holding them?",
        drill=f["order_book_late"].get("drill") or {},
        money=value, count=n, unit="orders")]


def delivered_unbilled(ctx, p):
    f = ctx.figures(["order_delivered_unbilled", "order_delivered_unbilled_count"])
    value = _num(f["order_delivered_unbilled"].get("value"))
    n = int(_num(f["order_delivered_unbilled_count"].get("value")))
    if value <= p["amount"] or not n:
        return []
    return [_rec(
        title=f"Invoice {ms(ctx, value)} of goods already delivered.",
        why=(f"{plural(n, 'open order')} {'has' if n == 1 else 'have'} goods delivered and "
             f"not yet invoiced, {m(ctx, value)} line by line. Until it is invoiced, it is in "
             f"nobody's receivables and nobody chases it."),
        what_to_do=["Raise the invoices this week.",
                    "Where one should not be billed, close the order with the reason."],
        how=how(ctx, "To invoice a delivered order in ERPNext:",
                ["Open Sales Order, filter Status To Bill.",
                 "Open each, click Create, then Sales Invoice; check and submit it."],
                "/app/sales-order?status=To%20Bill", "Open the Orders"),
        ask="Which orders were delivered but never invoiced?",
        drill=f["order_delivered_unbilled"].get("drill") or {},
        money=value, count=n, unit="orders")]


# =========================================================================== margin
def _margin_by_group(ctx, frm, to):
    by = defaultdict(lambda: [0.0, 0.0])
    for r in ctx.rows("fact_sales_invoice_line",
                      ["item_group", "base_net_amount", "base_margin_amount"],
                      lambda t: [t.src_docstatus == 1, t.has_cost == 1, t.posting_date >= frm,
                                 t.posting_date <= to]):
        g = by[r["item_group"] or "No Item Group"]
        g[0] += _num(r["base_net_amount"])
        g[1] += _num(r["base_margin_amount"])
    return by


def margin_shrinking(ctx, p):
    import datetime as dt
    cur, _, _ = _months(ctx)
    recent_from = (cur[0].replace(day=1) - dt.timedelta(days=62)).replace(day=1)
    before_to = recent_from - dt.timedelta(days=1)
    before_from = recent_from.replace(year=recent_from.year - 1)
    recent = _margin_by_group(ctx, recent_from, cur[1])
    before = _margin_by_group(ctx, before_from, before_to)
    out = []
    for g, (net, mar) in recent.items():
        bnet, bmar = before.get(g, (0.0, 0.0))
        if net < p["amount"] or bnet < p["amount"]:
            continue
        now_pct, then_pct = pct(mar, net), pct(bmar, bnet)
        # A margin outside -100%..100% is a cost recorded wrongly, not a margin that moved
        # (lines_without_cost and sold_below_cost speak to those).
        if not (0 < then_pct <= 100 and -100 <= now_pct <= 100):
            continue
        if then_pct - now_pct < p["points"]:
            continue
        lost = net * (then_pct - now_pct) / 100.0
        out.append(_rec(
            key=g,
            title=f"Margin on {g} fell from {then_pct:.0f}% to {now_pct:.0f}%: check prices "
                  f"and costs.",
            why=(f"{g} made {now_pct:.1f}% on {m(ctx, net)} sold from "
                 f"{date(recent_from)} to {date(cur[1])}, against {then_pct:.1f}% in the year "
                 f"before. At the old margin those sales would have made {m(ctx, lost)} more "
                 f"({m(ctx, net)} x {then_pct - now_pct:.1f} points). Lines without a cost are "
                 f"left out."),
            what_to_do=[f"Compare what {g} costs to buy now with a year ago.",
                        "Raise the price list where costs went up.",
                        "Check which discounts were given on it."],
            how=how(ctx, "ERPNext's own margin by product:",
                    ["Open Gross Profit (the link below), Group By Item Group, for the months "
                     "above.", "Update selling prices in Item Price where costs rose."],
                    "/app/query-report/Gross%20Profit", "Open Gross Profit"),
            ask=f"Why has the margin on {g} fallen, and which products drove it?",
            drill={"fact": "fact_sales_invoice_line",
                   "filters": {"item_group": g if g != "No product group" else ["is", "not set"],
                               "has_cost": 1, "src_docstatus": 1,
                               "posting_date": ["between", [str(recent_from), str(cur[1])]]}},
            money=lost))
    out.sort(key=lambda x: -x["money"])
    return out[:int(p["max_items"])]


def sold_below_cost(ctx, p):
    frm = since(ctx, p["days"])
    rows = ctx.rows("fact_sales_invoice_line", ["item_code", "base_margin_amount", "src_name"],
                    lambda t: [t.src_docstatus == 1, t.has_cost == 1,
                               t.base_margin_amount < 0, t.posting_date >= frm])
    loss = -sum(_num(r["base_margin_amount"]) for r in rows)
    if loss <= p["amount"]:
        return []
    by = defaultdict(float)
    for r in rows:
        by[r["item_code"]] -= _num(r["base_margin_amount"])
    top = sorted(by, key=lambda i: -by[i])
    return [_rec(
        title=f"Stop selling below cost: {ms(ctx, loss)} lost in {int(p['days'])} days.",
        why=(f"{plural(len(rows), 'invoice line')} since {date(frm)} sold for less than the "
             f"product cost, {m(ctx, loss)} below cost in all, on {plural(len(by), 'product')}. "
             f"Most on {top[0]} ({m(ctx, by[top[0]])})."),
        what_to_do=[f"Check the cost of {names(top)}: is its valuation right?",
                    "If it is, raise the selling price or stop the discount.",
                    "Ask who approved the prices on the largest lines."],
        how=how(ctx, "ERPNext's margin by invoice line:",
                ["Open Gross Profit (the link below), Group By Invoice, for the dates above.",
                 "Correct a wrong cost on the Item (Valuation Rate) or the purchase it came "
                 "from."], "/app/query-report/Gross%20Profit", "Open Gross Profit"),
        ask="Which products have we sold below cost recently, and to whom?",
        drill={"fact": "fact_sales_invoice_line",
               "filters": {"has_cost": 1, "base_margin_amount": ["<", 0], "src_docstatus": 1,
                           "posting_date": [">=", str(frm)]}},
        money=loss, count=len(rows), unit="lines")]


def lines_without_cost(ctx, p):
    frm = since(ctx, 365)
    rows = ctx.rows("fact_sales_invoice_line", ["has_cost", "base_net_amount", "item_code"],
                    lambda t: [t.src_docstatus == 1, t.posting_date >= frm])
    total = sum(_num(r["base_net_amount"]) for r in rows)
    blind = [r for r in rows if not r["has_cost"]]
    value = sum(_num(r["base_net_amount"]) for r in blind)
    if total <= 0 or pct(value, total) < p["pct"] or value <= 0:
        return []
    items = len({r["item_code"] for r in blind})
    return [_rec(
        title=f"Give {plural(items, 'product')} a cost: margin is unknown on "
              f"{pct(value, total):.0f}% of sales.",
        why=(f"In the year to {date(ctx.as_of)}, {m(ctx, value)} of {m(ctx, total)} sold "
             f"carries no cost, on {plural(len(blind), 'line')} for {plural(items, 'product')}, "
             f"so the margin on it cannot be worked out and is left out of every margin "
             f"figure."),
        what_to_do=["Find the products with no cost (the records list them).",
                    "Set a valuation rate on each, or receive them through a purchase receipt.",
                    "Services you sell: decide whether they have a cost to record."],
        how=how(ctx, "To give a product its cost in ERPNext:",
                ["Open the Item and set Valuation Rate (Inventory section).",
                 "Better: receive stock through a Purchase Receipt, which records the cost."],
                "/app/item", "Open Item"),
        ask="Which products have no cost recorded, and how much did we sell of them?",
        drill={"fact": "fact_sales_invoice_line",
               "filters": {"has_cost": 0, "src_docstatus": 1, "posting_date": [">=", str(frm)]}},
        money=value, severity=None)]


# =========================================================================== stock
def stock_not_moving(ctx, p):
    have = {i: x for i, x in held(ctx).items() if x["qty"] > 0 and x["value"] > 0}
    if not have:
        return []
    days = int(p["days"])
    moved = outflow(ctx, days)
    idle = sorted([i for i in have if i not in moved], key=lambda i: -have[i]["value"])
    value = sum(have[i]["value"] for i in idle)
    if value <= p["amount"]:
        return []
    moved2 = outflow(ctx, 2 * days)
    long_idle = [i for i in idle if i not in moved2]
    long_value = sum(have[i]["value"] for i in long_idle)
    total = sum(x["value"] for x in have.values())
    return [_rec(
        title=f"Clear {ms(ctx, value)} of stock that has not moved in {days} days.",
        why=(f"{plural(len(idle), 'product')} holding {m(ctx, value)} "
             f"({pct(value, total):.0f}% of all stock by value) had nothing sold or issued in "
             f"{days} days; {plural(len(long_idle), 'product')} ({m(ctx, long_value)}) in "
             f"{2 * days} days. The largest: {idle[0]} ({m(ctx, have[idle[0]]['value'])})."),
        what_to_do=["Agree a plan for the largest five: a price that sells them, a customer, "
                    "or a return to the supplier.",
                    "Buy no more of them until they move.",
                    "Write off what has expired or cannot be sold."],
        how=how(ctx, "ERPNext's own view of slow stock:",
                ["Open Stock Ageing (the link below) to see how old each holding is.",
                 "Sell or return it; write off with a Stock Entry of type Material Issue."],
                "/app/query-report/Stock%20Ageing", "Open Stock Ageing"),
        ask=f"Which stock has not moved in {days} days, and what is it worth?",
        drill={"fact": "fact_stock_balance", "filters": {"item_code": ["in", idle[:200]],
                                                         "actual_qty": [">", 0]}},
        money=value, count=len(idle), unit="products")]


def fast_movers_running_out(ctx, p):
    lookback = 90
    out90 = outflow(ctx, lookback)
    have = held(ctx)
    short = []
    for item, (qty, moves) in out90.items():
        if moves < p["count"] or qty <= 0:
            continue
        daily = qty / lookback
        x = have.get(item) or {"qty": 0.0, "reserved": 0.0, "ordered": 0.0, "rate": 0.0}
        left = max(x["qty"] - x["reserved"], 0.0) + max(x["ordered"], 0.0)
        cover = left / daily
        if cover < p["days"]:
            short.append((item, cover, daily, x))
    if not short:
        return []
    short.sort(key=lambda s: -(s[2] * 30 * s[3]["rate"]))
    money = sum(s[2] * 30 * s[3]["rate"] for s in short)
    item, cover, daily, x = short[0]
    return [_rec(
        title=f"Reorder {plural(len(short), 'fast-moving product')} before "
              f"{'it runs' if len(short) == 1 else 'they run'} out.",
        why=(f"At the last {lookback} days' pace, {plural(len(short), 'product')} that "
             f"{'sells' if len(short) == 1 else 'sell'} steadily will run out within "
             f"{int(p['days'])} days, counting what is on order. {item}: "
             f"{max(x['qty'] - x['reserved'], 0):,.0f} free to sell and {max(x['ordered'], 0):,.0f} "
             f"on order against {daily:,.1f} a day. A month of their sales is about "
             f"{m(ctx, money)} at cost."),
        what_to_do=[f"Raise purchase orders for {names([s[0] for s in short])} today.",
                    "Set a re-order level on each so ERPNext asks for it in time."],
        how=how(ctx, "So ERPNext reorders on its own:",
                ["Open the Item, section Auto Re-order: add the warehouse, Re-order Level and "
                 "Re-order Qty.",
                 "Stock Settings: tick Raise Material Request When Stock Reaches Re-order "
                 "Level.", "Now: Material Request, New, for the products above."],
                "/app/material-request/new", "New Material Request"),
        ask="Which products will run out soon at the current pace of sales?",
        drill={"fact": "fact_stock_balance",
               "filters": {"item_code": ["in", [s[0] for s in short][:200]]}},
        money=money, count=len(short), unit="products")]


def reserved_over_available(ctx, p):
    gaps = [(i, x["reserved"] - x["qty"], x) for i, x in held(ctx).items()
            if x["reserved"] > max(x["qty"], 0)]
    if len(gaps) <= p["count"]:
        return []
    gaps.sort(key=lambda g: -(g[1] * g[2]["rate"]))
    money = sum(g[1] * g[2]["rate"] for g in gaps)
    item, gap, x = gaps[0]
    return [_rec(
        title=f"Stop promising stock we do not have: {plural(len(gaps), 'product')} "
              f"short.",
        why=(f"{plural(len(gaps), 'product')} {'is' if len(gaps) == 1 else 'are'} reserved for "
             f"customers beyond Actual Qty. Worst: {item}, {x['reserved']:,.0f} reserved, "
             f"{max(x['qty'], 0):,.0f} on hand. The shortfall is worth about {m(ctx, money)} at "
             f"cost."),
        what_to_do=[f"Freeze new orders for {names([g[0] for g in gaps])} until stock arrives.",
                    "Buy or transfer stock for the orders already taken.",
                    "Tell the customers whose orders cannot be met on time."],
        how=how(ctx, "What is reserved against what is there, in ERPNext:",
                ["Open Stock Projected Qty (the link below), filter Reserved Qty.",
                 "Raise a Material Request for the shortfall."],
                "/app/query-report/Stock%20Projected%20Qty", "Open Stock Projected Qty"),
        ask="Which products have we promised to customers beyond what we hold?",
        drill={"fact": "fact_stock_balance",
               "filters": {"item_code": ["in", [g[0] for g in gaps][:200]]}},
        money=money, count=len(gaps), unit="products")]


def promised_not_ordered(ctx, p):
    """Lines promised to customers that nothing covers -- not stock, not a purchase order,
    linked or likely, not a request (command_center/coverage.py). Only Not Ordered and
    Partly Covered: what is on its way is not a finding."""
    from command_center import coverage
    got = coverage.get(ctx.code)
    if got.get("kind") != "cover":
        raise RuntimeError("the business's ERPNext did not answer")
    lines = [l for l in got["lines"] if l["state"] in coverage.NEEDS_ACTION]
    money = sum(l["parts"]["missing"] for l in lines)
    if not lines or money <= p["amount"]:
        return []
    by = defaultdict(float)
    for l in lines:
        by[l["order"]] += l["parts"]["missing"]
    orders = sorted(by, key=lambda o: -by[o])
    customers = defaultdict(float)
    for l in lines:
        customers[l["customer"]] += l["parts"]["missing"]
    stale = [l for l in lines if l["days_late"] > coverage.STALE_DAYS]
    stale_money = sum(l["parts"]["missing"] for l in stale)
    recent = [l for l in lines if l["days_late"] <= coverage.STALE_DAYS]
    top = max(lines, key=lambda l: l["parts"]["missing"])
    why = (f"{plural(len(lines), 'order line')} on {plural(len(by), 'open order')} "
           f"{'is' if len(lines) == 1 else 'are'} promised to customers with {m(ctx, money)} "
           f"of goods not in stock and not on any purchase order or request. Largest: "
           f"{top['order']} for {top['customer']}, {coverage.qty(top['missing'])} "
           f"{top['uom'] or ''} of {top['item_name']}.".replace("  ", " "))
    if stale_money >= 0.5:
        why += (f" {m(ctx, stale_money)} of it, on {plural(len({l['order'] for l in stale}), 'order')}, "
                f"was due more than a year ago and may no longer stand.")
    todo = [f"Order or source what the recent ones need first: "
            f"{plural(len({l['order'] for l in recent}), 'order')} due within the last year.",
            "Raise the purchase from each Sales Order (Create, Purchase Order or Material "
            "Request) so it is linked to the order.",
            "Tell the customers whose goods cannot come on time."]
    if stale:
        todo.insert(1, "Confirm the older orders with the customers; close those that no "
                       "longer stand (Sales Order, Status, Close).")
    return [_rec(
        title=f"Order or source {ms(ctx, money)} of goods promised to customers that nothing "
              f"covers.",
        why=why, what_to_do=todo[:4],
        how=how(ctx, "To buy for an order so the link is exact:", coverage.LINK_STEPS,
                "/app/sales-order?status=To%20Deliver%20and%20Bill", "Open the Sales Orders"),
        ask="Which promised orders have nothing in stock or on order to cover them?",
        drill={"fact": "fact_sales_order", "filters": {"src_name": ["in", orders[:200]]}},
        money=money, count=len(lines), unit="order lines")]


def near_expiry(ctx, p):
    import frappe

    from command_center.api.panels import _guarded
    batches = _guarded(ctx, "Batch", {"expiry_date": ["is", "set"], "batch_qty": [">", 0]},
                       ["name", "item", "expiry_date", "batch_qty"])
    if not batches:
        return []
    edge = frappe.utils.getdate(frappe.utils.add_days(frappe.utils.today(), int(p["days"])))
    have = held(ctx)
    soon = [b for b in batches if frappe.utils.getdate(b["expiry_date"]) <= edge]
    if not soon:
        return []
    now = today(ctx)
    gone = [b for b in soon if frappe.utils.getdate(b["expiry_date"]) < now]
    value = sum(_num(b["batch_qty"]) * (have.get(b.get("item")) or {}).get("rate", 0.0)
                for b in soon)
    return [_rec(
        title=f"Sell or return {plural(len(soon), 'batch', 'batches')} expiring within "
              f"{int(p['days'])} days.",
        why=(f"{plural(len(soon), 'batch', 'batches')} still holding stock expire by "
             f"{date(edge)}" + (f"; {len(gone)} already have" if gone else "") +
             f". At each product's valuation that stock is worth about {m(ctx, value)}."),
        what_to_do=["Offer the soonest to expire to customers who use them, at a price "
                    "that sells.", "Ask the suppliers whether they take back short-dated stock.",
                    "Write off and dispose of what has expired."],
        how=how(ctx, "Batches by expiry in ERPNext:",
                ["Open Batch-Wise Balance History or the Batch list sorted by Expiry Date.",
                 "Write off expired stock with a Stock Entry, type Material Issue."],
                "/app/batch?disabled=0", "Open Batch"),
        ask="Which batches expire in the next 90 days, and what are they worth?",
        drill={"href": f"{ctx.site()}/app/batch?disabled=0"},
        money=value, count=len(soon), unit="batches")]


def _open_pos(ctx):
    from command_center.api.panels import _pos
    return [x for x in _pos(ctx) if _num(x.get("per_received")) < 100
            and (x.get("status") or "") not in ("Closed", "Completed", "On Hold")]


def po_for_slow_items(ctx, p):
    have = {i for i, x in held(ctx).items() if x["qty"] > 0 and x["value"] > 0}
    idle = have - set(outflow(ctx, int(p["days"])))
    pos = {x["name"]: x for x in _open_pos(ctx)}
    if not idle or not pos:
        return []
    from command_center.kpi.live_departments import child_rows
    lines = child_rows(ctx.reader(), "Purchase Order Item", "Purchase Order", pos,
                       ["parent", "item_code", "qty", "received_qty", "base_net_amount"])
    hit = [x for x in lines if x.get("item_code") in idle
           and _num(x.get("qty")) > _num(x.get("received_qty"))]
    for x in hit:
        q = _num(x.get("qty"))
        x["pending"] = _num(x.get("base_net_amount")) * (q - _num(x.get("received_qty"))) / q if q else 0
    value = sum(x["pending"] for x in hit)
    if value <= p["amount"]:
        return []
    orders = sorted({x["parent"] for x in hit})
    items = sorted({x["item_code"] for x in hit})
    return [_rec(
        title=f"Hold {ms(ctx, value)} still on order for products that are not selling.",
        why=(f"{plural(len(orders), 'open purchase order')} still {'has' if len(orders) == 1 else 'have'} "
             f"{m(ctx, value)} to come of {plural(len(items), 'product')} already in stock that "
             f"had nothing sold or issued in {int(p['days'])} days: {names(items)}."),
        what_to_do=["Ask the suppliers to hold or cancel what has not shipped.",
                    "Close the order lines no longer wanted.",
                    "Agree who signs off buying a product that is not moving."],
        how=how(ctx, "To stop the rest of an order in ERPNext:",
                ["Open the Purchase Order, click Status, then Close (or Update Items to reduce "
                 "the quantity)."], "/app/purchase-order?status=To%20Receive%20and%20Bill",
                "Open the Orders"),
        ask="Which open purchase orders are for products that are not selling?",
        drill={"href": f"{ctx.site()}/app/purchase-order?name=" + orders[0]},
        money=value, count=len(orders), unit="orders")]


# =========================================================================== buying
def supplier_concentration(ctx, p):
    frm = since(ctx, 365)
    by = defaultdict(float)
    for r in ctx.rows("fact_purchase_invoice_line", ["supplier", "base_net_amount"],
                      lambda t: [t.src_docstatus == 1, t.posting_date >= frm]):
        by[r["supplier"]] += _num(r["base_net_amount"])
    ranked = sorted([kv for kv in by.items() if kv[1] > 0], key=lambda kv: -kv[1])
    total = sum(v for _, v in ranked)
    if len(ranked) < 3 or total <= 0:
        return []
    two = ranked[0][1] + ranked[1][1]
    if pct(two, total) < p["pct"]:
        return []
    a, b = ranked[0][0], ranked[1][0]
    return [_rec(
        title=f"Line up a second source: two suppliers take {pct(two, total):.0f}% of buying.",
        why=(f"In the year to {date(ctx.as_of)}, {a} ({m(ctx, ranked[0][1])}) and {b} "
             f"({m(ctx, ranked[1][1])}) billed {m(ctx, two)} of {m(ctx, total)} bought from "
             f"{plural(len(ranked), 'supplier')}. If either stops or a shipment is held, there "
             f"may be no second source ready."),
        what_to_do=[f"List what only {a} or {b} supply.",
                    "Get a quote from another supplier for the largest of those.",
                    "Agree a stock buffer for anything with a single source."],
        how=how(ctx, "To ask another supplier for prices in ERPNext:",
                ["Request for Quotation, New: add the items and the suppliers, then send it.",
                 "Compare the answers in Supplier Quotation Comparison."],
                "/app/request-for-quotation/new", "New Request for Quotation"),
        ask=f"What happens if {a} stops supplying?",
        drill={"fact": "fact_purchase_invoice_line",
               "filters": {"supplier": ["in", [a, b]], "src_docstatus": 1,
                           "posting_date": [">=", str(frm)]}},
        money=two)]


def late_suppliers(ctx, p):
    import frappe
    edge = frappe.utils.getdate(frappe.utils.add_days(frappe.utils.today(), -int(p["days"])))
    late = [x for x in _open_pos(ctx) if x.get("schedule_date")
            and frappe.utils.getdate(x["schedule_date"]) < edge]
    if len(late) < p["count"]:
        return []
    # Still to receive, line by line (ingest/order_lines.py): never the order's value
    # times ERPNext's received percentage, which is a share of quantity.
    from command_center.ingest import order_lines
    left = order_lines.order_values(ctx.reader(), order_lines.BUYING, late, "per_received")
    for x in late:
        x["pending"] = left[x["name"]]["left"]
    value = sum(x["pending"] for x in late)
    if value <= 0:
        return []
    oldest = min(late, key=lambda x: str(x["schedule_date"]))
    by = defaultdict(float)
    for x in late:
        by[x.get("supplier")] += x["pending"]
    top = sorted(by, key=lambda s: -by[s])
    return [_rec(
        title=f"Chase {plural(len(late), 'purchase order')} past the date the supplier "
              f"promised.",
        why=(f"{plural(len(late), 'open purchase order')} with about {m(ctx, value)} still to "
             f"receive {'is' if len(late) == 1 else 'are'} more than {int(p['days'])} days past "
             f"the Required By date. The oldest, {oldest['name']} from {oldest.get('supplier')}, "
             f"was due {date(oldest['schedule_date'])}. Most is with {names(top)}."),
        what_to_do=[f"Call {names(top, 2)} for firm dates.",
                    "Tell the customers waiting on those goods.",
                    "Close orders that will never arrive, so they stop counting."],
        how=how(ctx, "The late orders in ERPNext:",
                ["Open Purchase Order, filter To Receive, sort by Required By.",
                 "Update the Required By date once the supplier confirms."],
                "/app/purchase-order?status=To%20Receive%20and%20Bill", "Open the Orders"),
        ask="Which purchase orders are past their Required By date, and from whom?",
        drill={"href": f"{ctx.site()}/app/purchase-order/{oldest['name']}"},
        money=value, count=len(late), unit="orders")]


def bills_not_matching(ctx, p):
    from command_center.api.panels import _guarded
    owed = {r["party"]: r["owed"] for r in positions(ctx, "Supplier") if r["owed"] > 0}
    unpaid = ctx.rows("fact_purchase_invoice", ["src_name", "supplier", "outstanding_amount"],
                      lambda t: [t.src_docstatus == 1, t.outstanding_amount > 0])
    unpaid = [u for u in unpaid if u["supplier"] in owed]
    if not unpaid:
        return []
    names_ = sorted({u["src_name"] for u in unpaid})
    lines, heads = [], {}
    for i in range(0, len(names_), 200):
        part = names_[i:i + 200]
        lines += _guarded(ctx, "Purchase Invoice Item", {"parent": ["in", part]},
                          ["parent", "purchase_order", "purchase_receipt"],
                          parent="Purchase Invoice", limit=100000)
        heads.update({h["name"]: h for h in _guarded(
            ctx, "Purchase Invoice", {"name": ["in", part]}, ["name", "update_stock"])})
    gaps = set()
    for x in lines:
        if not x.get("purchase_order") or (not x.get("purchase_receipt") and not int(
                (heads.get(x["parent"]) or {}).get("update_stock") or 0)):
            gaps.add(x["parent"])
    flagged = [u for u in unpaid if u["src_name"] in gaps]
    by = defaultdict(float)
    for u in flagged:
        by[u["supplier"]] += _num(u["outstanding_amount"])
    # What is really owed is the ledger: no more than each supplier's balance.
    value = sum(min(v, owed[s]) for s, v in by.items())
    if value <= p["amount"]:
        return []
    return [_rec(
        title=f"Check {plural(len(flagged), 'unpaid Purchase Invoice')} with no order or Purchase Receipt "
              f"before paying.",
        why=(f"{plural(len(flagged), 'unpaid Purchase Invoice')} from "
             f"{plural(len(by), 'supplier')} {'does' if len(flagged) == 1 else 'do'} not rest on "
             f"both a purchase order and a Purchase Receipt. Against what the Supplier Ledger says is owed "
             f"to those suppliers, {m(ctx, value)} is at stake. Most with "
             f"{names(sorted(by, key=lambda s: -by[s]))}."),
        what_to_do=["Before paying, confirm each was ordered and the goods arrived.",
                    "Record the missing receipt, or ask why there was no order.",
                    "Ask that every Purchase Invoice be made from its order or receipt (Create, Purchase "
                    "Invoice)."],
        how=how(ctx, "Purchase Invoices against their orders and receipts in ERPNext:",
                ["Open Purchase Invoice Trends or each Purchase Invoice's Purchase Order and Purchase "
                 "Receipt fields.", "Make new Purchase Invoices from the receipt: Purchase Receipt, Create, "
                 "Purchase Invoice."], "/app/purchase-invoice?status=Unpaid", "Open the Purchase Invoices"),
        ask="Which unpaid Purchase Invoices have no purchase order or Purchase Receipt behind them?",
        drill={"fact": "fact_purchase_invoice",
               "filters": {"src_name": ["in", sorted(gaps)[:200]]}},
        money=value, count=len(flagged), unit="bills")]


def long_unpaid_bills(ctx, p):
    rows = sorted([r for r in positions(ctx, "Supplier") if r["d90_plus"] > 0],
                  key=lambda r: -r["d90_plus"])
    total = sum(r["d90_plus"] for r in rows)
    if total <= p["amount"]:
        return []
    largest = "; ".join(f"{r['party']} {m(ctx, r['d90_plus'])}" for r in rows[:3])
    return [_rec(
        title=f"Agree a plan for {ms(ctx, total)} owed to suppliers over 90 days.",
        why=(f"On the Supplier Ledger, once unreconciled payments are set against the oldest Purchase Invoices, "
             f"{m(ctx, total)} owed to {plural(len(rows), 'supplier')} is more than 90 days "
             f"past due. Largest: {largest}. Suppliers this far behind start holding "
             f"deliveries."),
        what_to_do=["Call the largest and agree a payment plan in writing.",
                    "Check first that the debt is real: unreconciled payments make Purchase Invoices look "
                    "unpaid.", "Put the plan's dates in the payment schedule."],
        how=how(ctx, "What is owed to whom, in ERPNext:",
                ["Open Accounts Payable (the link below), ageing by due date.",
                 "Match payments to Purchase Invoices first (Payment Reconciliation) so only real debts "
                 "remain."], "/app/query-report/Accounts%20Payable", "Open Accounts Payable"),
        ask="Which suppliers have we owed for more than 90 days, and how much?",
        drill={"fact": "fact_party_balance",
               "filters": {"party_type": "Supplier", "d90_plus": [">", 0]}},
        money=total, count=len(rows), unit="suppliers")]


# =========================================================================== people and control
# The amount on each kind of document that waits for approval.
APPROVAL_VALUE = {"Purchase Order": "base_grand_total", "Payment Entry": "base_paid_amount",
                  "Sales Invoice": "base_grand_total", "Purchase Invoice": "base_grand_total",
                  "Sales Order": "base_grand_total", "Journal Entry": "total_debit",
                  "Quotation": "base_grand_total", "Expense Claim": "total_claimed_amount",
                  "Material Request": None, "Stock Reconciliation": None}


def _idx(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _pending_states(r):
    """{doctype: (state field, [states waiting on someone])}: the active workflows'
    draft states other than the first (where a document starts) and the rejections."""
    import re
    flows = r.all("Workflow", {"is_active": 1}, ["name", "document_type", "workflow_state_field"])
    if not flows:
        return {}
    states = r.all("Workflow Document State", {"parent": ["in", [f["name"] for f in flows]]},
                   ["parent", "idx", "state", "doc_status"], parent="Workflow", limit=2000)
    by = defaultdict(list)
    for s in states:
        by[s["parent"]].append(s)
    out = {}
    skip = re.compile(r"draft|reject|cancel", re.I)
    for f in flows:
        rows = sorted(by.get(f["name"], []), key=lambda s: _idx(s.get("idx")))
        if not rows:
            continue
        first = rows[0]["state"]
        wait = sorted({s["state"] for s in rows if str(s.get("doc_status")) == "0"
                       and s["state"] != first and not skip.search(s["state"] or "")})
        if wait:
            out[f["document_type"]] = (f.get("workflow_state_field") or "workflow_state", wait)
    return out


def approvals_bottleneck(ctx, p):
    import frappe
    from urllib.parse import quote

    from command_center.api.panels import _guarded
    r = ctx.reader()
    now = frappe.utils.now_datetime()
    out = []
    for doctype, (field_, states) in _pending_states(r).items():
        value = APPROVAL_VALUE.get(doctype)
        fields = ["name", field_, "creation"] + ([value] if value else [])
        try:
            docs = _guarded(ctx, doctype, {"docstatus": 0, field_: ["in", states]}, fields)
        except Exception as e:
            from command_center.kpi.live_departments import is_down
            if is_down(e):
                raise
            docs = _guarded(ctx, doctype, {"docstatus": 0, field_: ["in", states]},
                            ["name", field_, "creation"])
            value = None
        by = defaultdict(list)
        for d in docs:
            by[d.get(field_)].append(d)
        for state, rows in by.items():
            ages = [(now - frappe.utils.get_datetime(d["creation"])).days for d in rows
                    if d.get("creation")]
            oldest = max(ages) if ages else 0
            if len(rows) < p["count"] and oldest < p["days"]:
                continue
            total = sum(_num(d.get(value)) for d in rows) if value else 0.0
            word = doctype.lower()
            amount = f", {m(ctx, total)} between them" if value else ""
            out.append(_rec(
                key=f"{doctype}:{state}",
                title=f"Clear {plural(len(rows), word)} waiting at {state}, the oldest "
                      f"{oldest} days.",
                why=(f"{plural(len(rows), word)} {'is' if len(rows) == 1 else 'are'} waiting "
                     f"at {state}{amount}. The oldest was raised {oldest} days ago. Until "
                     f"decided, {'they are' if len(rows) != 1 else 'it is'} in no figure: not "
                     f"paid, not owed, not ordered."),
                what_to_do=[f"Ask whoever approves at {state} to clear the queue, oldest first.",
                            "Reject what is no longer needed, so it leaves the queue.",
                            "If one approver holds everything up, agree a stand-in."],
                how=how(ctx, f"The documents waiting at {state} in ERPNext:",
                        ["Open the list (the link below); each shows the approval actions to "
                         "whoever may take them.",
                         "Approve or reject each one from its Actions menu."],
                        f"/app/{_slug(doctype)}?{quote(field_)}={quote(state)}",
                        "Open the Queue"),
                ask=f"Which {word}s are waiting at {state}, for how long, and who raised them?",
                drill={"href": f"{ctx.site()}/app/{_slug(doctype)}?{quote(field_)}={quote(state)}"},
                money=total, count=len(rows), unit=word + ("" if len(rows) == 1 else "s"),
                severity=("crit" if oldest >= p["crit_days"] and total >= p["crit_amount"]
                          else None)))
    return out


def overdue_tasks_by_owner(ctx, p):
    rows = ctx.rows("fact_task", ["engineers", "days_late"],
                    lambda t: [t.is_open == 1, t.days_late > 0])
    if len(rows) <= p["count"]:
        return []
    by = defaultdict(list)
    for r in rows:
        for who in (r["engineers"] or "Nobody").split(","):
            by[who.strip() or "Nobody"].append(int(_num(r["days_late"])))
    top = sorted(by, key=lambda w: -len(by[w]))
    listed = "; ".join(f"{w}: {len(by[w])}, the oldest {max(by[w])} days late" for w in top[:3])
    return [_rec(
        title=f"Give each of {plural(len(rows), 'late job')} an owner and a new date.",
        why=(f"{plural(len(rows), 'open job')} {'is' if len(rows) == 1 else 'are'} past the "
             f"expected end date. By who holds them: {listed}."),
        what_to_do=[f"Go through the list with {names([w for w in top if w != 'Nobody'], 2) or 'the team'} "
                    f"and set new dates.", "Give every job with no one on it an owner.",
                    "Close jobs that are finished but never marked done."],
        how=how(ctx, "The late jobs in ERPNext:",
                ["Open Task, filter Status Overdue, group by Assigned To.",
                 "Assign each (the Assigned To field) and update Expected End Date."],
                "/app/task?status=Overdue", "Open the Tasks"),
        ask="Who holds the jobs past their date, and how late are they?",
        drill={"fact": "fact_task", "filters": {"is_open": 1, "days_late": [">", 0]}},
        count=len(rows), unit="jobs")]


def self_approvals(ctx, p):
    from command_center.kpi.live import self_approved
    n = self_approved(ctx.reader())[0]
    if not n or n <= p["count"]:
        return []
    what, whats = ("submitted purchase order or payment",
                   "submitted purchase orders and payments")
    return [_rec(
        title=f"Review {plural(int(n), 'document')} approved by the person who raised "
              f"{'it' if n == 1 else 'them'}.",
        why=(f"In the change history, every approval step on {plural(int(n), what, whats)} was "
             f"taken by the account that raised it. An approval by the person asking is no "
             f"approval."),
        what_to_do=["Look at each: was the purchase or payment genuine?",
                    "Make sure the approval steps ask someone other than the person raising.",
                    "Where the team is too small for that, have a director review them weekly."],
        how=how(ctx, "Who did what is in ERPNext's change history:",
                ["Open the document and its Activity at the foot: each approval shows who took "
                 "it.", "An administrator can untick Allow Self Approval on the workflow's "
                 "transitions."], "/app/version", "Open the Change History"),
        ask="Which purchase orders and payments were approved by the person who raised them?",
        drill={"href": f"{ctx.site()}/app/version"},
        count=int(n), unit="documents")]


def leavers_trend(ctx, p):
    import frappe
    now_from, before_from = since(ctx, 180), since(ctx, 360)
    rows = ctx.rows("fact_person", ["department", "relieving_date", "status"],
                    lambda t: [t.status == "Left"])
    recent = [r for r in rows if r["relieving_date"]
              and now_from <= frappe.utils.getdate(r["relieving_date"]) <= ctx.as_of]
    before = [r for r in rows if r["relieving_date"]
              and before_from <= frappe.utils.getdate(r["relieving_date"]) < now_from]
    if len(recent) < p["count"] or len(recent) <= len(before):
        return []
    by = defaultdict(int)
    for r in recent:
        by[r["department"] or "No department"] += 1
    dept = max(by, key=by.get)
    return [_rec(
        title=f"Find out why {plural(len(recent), 'person', 'people')} left in six months.",
        why=(f"{plural(len(recent), 'person', 'people')} left in the six months to "
             f"{date(ctx.as_of)}, against {len(before)} in the six months before. Most from "
             f"{dept} ({by[dept]})."),
        what_to_do=[f"Talk to the head of {dept}: workload, pay or management?",
                    "Hold an exit conversation with each leaver from now on.",
                    "Check who covers the work they left."],
        how=how(ctx, "Leavers in ERPNext:",
                ["Open Employee, filter Status Left, sort by Relieving Date.",
                 "Record the reason on each (Exit section: Reason for Leaving)."],
                "/app/employee?status=Left", "Open Employee"),
        ask="Who has left in the last six months, from which departments, and how long had "
            "they stayed?",
        drill={"fact": "fact_person", "filters": {"status": "Left",
                                                  "relieving_date": [">=", str(now_from)]}},
        count=len(recent), unit="leavers")]


# =========================================================================== data hygiene
def draft_documents(ctx, p):
    old = since(ctx, p["days"])
    drafts = ctx.rows("fact_sales_invoice", ["src_name", "base_grand_total", "posting_date"],
                      lambda t: [t.src_docstatus == 0, t.posting_date < old])
    value = sum(_num(d["base_grand_total"]) for d in drafts)
    if len(drafts) <= p["count"] or value <= 0:
        return []
    oldest = min(str(d["posting_date"]) for d in drafts if d["posting_date"]) if drafts else None
    return [_rec(
        title=f"Issue or cancel {plural(len(drafts), 'invoice')} left as drafts.",
        why=(f"{plural(len(drafts), 'sales invoice')} worth {m(ctx, value)} "
             f"{'was' if len(drafts) == 1 else 'were'} saved more than {int(p['days'])} days "
             f"ago and left in Draft" + (f", the oldest dated {date(oldest)}" if oldest else "") +
             ". A draft is in no figure: not owed, not sold, not chased."),
        what_to_do=["Submit the ones that were really sold.",
                    "Cancel or delete the rest, so the list holds only real work."],
        how=how(ctx, "The drafts in ERPNext:",
                ["Open Sales Invoice, filter Status Draft, sort by Posting Date.",
                 "Open each: Submit it, or Delete it if it was never a sale."],
                "/app/sales-invoice?docstatus=0", "Open the Drafts"),
        ask="Which Sales Invoices are still Draft, and who created them?",
        drill={"fact": "fact_sales_invoice", "filters": {"src_docstatus": 0,
                                                         "posting_date": ["<", str(old)]}},
        money=value, count=len(drafts), unit="invoices")]


def duplicate_departments(ctx, p):
    from command_center.api.panels import _dept_key, _guarded, _people
    people = [x for x in _people(ctx) if x["is_active"]]
    rows = _guarded(ctx, "Department", {"is_group": 0}, ["name"], limit=2000)
    all_ = sorted({d["name"] for d in rows} | {x["department"] for x in people if x["department"]})
    groups = defaultdict(list)
    for n in all_:
        if _dept_key(n):
            groups[_dept_key(n)].append(n)
    dup = [sorted(v) for v in groups.values() if len(v) > 1]
    if len(dup) < p["count"]:
        return []
    example = " and ".join(f"\u201c{x}\u201d" for x in dup[0])
    return [_rec(
        title=f"Merge {plural(len(dup), 'department')} recorded under more than one name.",
        why=(f"{plural(len(dup), 'department')} {'appears' if len(dup) == 1 else 'appear'} "
             f"twice or more, for example {example}. "
             f"Headcount and cost by department cannot be counted reliably until they are "
             f"merged."),
        what_to_do=["Choose one name for each.",
                    "Move the people to it, then disable the other."],
        how=how(ctx, "Departments in ERPNext:",
                ["Open Employee, filter by the old department, and change Department on each.",
                 "Open the old Department and tick Disabled."], "/app/department",
                "Open Department"),
        ask="Which departments are recorded more than once?",
        drill={"href": f"{ctx.site()}/app/department"},
        count=len(dup), unit="departments", severity=None)]


def missing_valuations(ctx, p):
    rows = ctx.rows("fact_stock_balance", ["item_code", "actual_qty"],
                    lambda t: [t.has_valuation == 0, t.actual_qty > 0])
    if len(rows) <= p["count"]:
        return []
    items = sorted({r["item_code"] for r in rows})
    return [_rec(
        title=f"Value {plural(len(items), 'product')} held with no cost recorded.",
        why=(f"{plural(len(rows), 'stock line')} for {plural(len(items), 'product')} "
             f"{'is' if len(rows) == 1 else 'are'} held with no valuation, so the stock figure "
             f"understates what is held by an unknown amount and their sales carry no margin. "
             f"For example {names(items)}."),
        what_to_do=["Set a valuation rate for each from its last purchase price.",
                    "Make sure stock always arrives through a purchase receipt."],
        how=how(ctx, "To value stock in ERPNext:",
                ["Stock Reconciliation, New: list the products with their Valuation Rate, "
                 "keeping the quantity, and submit.",
                 "Or set Valuation Rate on each Item."], "/app/stock-reconciliation/new",
                "New Stock Reconciliation"),
        ask="Which products do we hold with no value recorded?",
        drill={"fact": "fact_stock_balance", "filters": {"has_valuation": 0,
                                                         "actual_qty": [">", 0]}},
        count=len(items), unit="products")]


# =========================================================================== the catalogue
A, D, C, PCT, PTS = "amount", "days", "count", "percent", "points"
RULES = (
    # cash and credit
    Rule("unmatched_receipts", "cash", "Unreconciled Customer Payments", "high",
         "Finance", unmatched_receipts,
         (Param("amount", "Recommend when more than", 1000, A),),
         twin_alert="Customer payments not matched"),
    Rule("customers_in_credit", "cash", "Customers in Credit, to Refund or Use", "med",
         "Finance", customers_in_credit, (Param("amount", "Recommend when more than", 1000, A),)),
    Rule("overdue_customers", "cash", "Customer Ledger Balance Over 90 Days", "high",
         "Finance", overdue_customers,
         (Param("amount", "Per customer, more than", 10000, A),
          Param("crit_amount", "Critical from", 100000, A),
          Param("max_items", "Show at most", 3, C)),
         twin_alert="Overdue receivables"),
    Rule("credit_hold", "cash", "Customers Still Invoiced While Over 90 Days", "high",
         "Finance", credit_hold,
         (Param("amount", "Over 90 days late by more than", 5000, A),
          Param("days", "Invoiced within the last", 30, D))),
    Rule("days_to_pay_worsening", "cash", "Customers Paying More Slowly", "med", "Finance",
         days_to_pay_worsening,
         (Param("days", "Later by at least", 10, D),
          Param("count", "Payments needed in each period", 20, C))),
    Rule("supplier_payments_due", "cash", "Purchase Invoices Due Against Bank and Cash",
         "high", "Finance", supplier_payments_due,
         (Param("days", "Falling due within", 14, D),
          Param("pct", "When due exceeds this share of bank and cash", 100, PCT))),
    Rule("unmatched_supplier_payments", "cash", "Unreconciled Supplier Payments",
         "med", "Finance", unmatched_supplier_payments,
         (Param("amount", "Recommend when more than", 1000, A),),
         twin_alert="Supplier payments not matched"),
    # sales
    Rule("sales_falling", "sales", "Sales Falling, by Item Group", "high", "Sales",
         sales_falling,
         (Param("pct", "Down by at least", 25, PCT), Param("amount", "And by more than", 10000, A),
          Param("max_items", "Show at most", 3, C))),
    Rule("customer_concentration", "sales", "Customer Concentration", "med", "Sales",
         customer_concentration,
         (Param("pct", "Five largest customers' share from", 40, PCT),
          Param("one_pct", "Or one customer's share from", 25, PCT))),
    Rule("customers_gone_quiet", "sales", "Inactive Customers", "med", "Sales",
         customers_gone_quiet,
         (Param("days", "Nothing bought for", 90, D),
          Param("count", "Bought in at least (months of the year before)", 3, C),
          Param("amount", "And bought more than", 10000, A))),
    Rule("discounts_outside_price_list", "sales", "Discounts Outside Pricing Rules", "med",
         "Sales", discounts_outside_price_list,
         (Param("amount", "Recommend when more than", 5000, A),
          Param("days", "Over the last", 90, D))),
    Rule("late_orders", "sales", "Sales Orders Past Delivery Date", "high", "Sales",
         late_orders, (Param("count", "More than (orders)", 0, C),
                       Param("amount", "And worth more than", 0, A)),
         twin_alert="Orders past their promised date"),
    Rule("delivered_unbilled", "sales", "To Bill", "high", "Finance",
         delivered_unbilled, (Param("amount", "Recommend when more than", 0, A),),
         twin_alert="Delivered but not invoiced"),
    # margin
    Rule("margin_shrinking", "margin", "Item Groups with Shrinking Margin", "med", "Sales",
         margin_shrinking,
         (Param("points", "Margin down by at least (points)", 5, PTS),
          Param("amount", "On sales of at least", 20000, A),
          Param("max_items", "Show at most", 3, C))),
    Rule("sold_below_cost", "margin", "Sold Below Valuation Rate", "high", "Sales", sold_below_cost,
         (Param("amount", "Loss more than", 1000, A), Param("days", "Over the last", 90, D))),
    Rule("lines_without_cost", "margin", "Sales with No Valuation Rate", "med", "Finance",
         lines_without_cost, (Param("pct", "Share of sales from", 5, PCT),)),
    # stock
    Rule("stock_not_moving", "stock", "Stock Ageing, No Movement", "med", "Stock Manager",
         stock_not_moving,
         (Param("days", "Nothing out for", 90, D), Param("amount", "Worth more than", 10000, A))),
    Rule("fast_movers_running_out", "stock", "Fast Movers About to Run Out", "high",
         "Stock Manager", fast_movers_running_out,
         (Param("days", "Running out within", 21, D),
          Param("count", "Moved out at least (times, 90 days)", 3, C))),
    Rule("reserved_over_available", "stock", "Reserved Qty Above Actual Qty", "high",
         "Stock Manager", reserved_over_available, (Param("count", "More than (products)", 0, C),),
         twin_alert="Stock promised but not there"),
    Rule("promised_not_ordered", "stock", "Sales Orders Not Covered by a Purchase Order", "high",
         "Purchasing", promised_not_ordered,
         (Param("amount", "Recommend when more than", 0, A),
          Param("window", "Likely cover: purchase orders raised up to (days before the order)",
                WINDOW_DAYS, D),
          Param("after", "Likely cover: and up to (days after the order)", AFTER_DAYS, D))),
    Rule("near_expiry", "stock", "Batches Near Expiry", "high", "Stock Manager", near_expiry,
         (Param("days", "Expiring within", 90, D),)),
    Rule("po_for_slow_items", "stock", "Purchase Orders for Items Not Selling", "med",
         "Purchasing", po_for_slow_items,
         (Param("days", "Not moved for", 90, D), Param("amount", "Still to come, more than", 1000, A))),
    # buying
    Rule("supplier_concentration", "buying", "Supplier Concentration", "med", "Purchasing",
         supplier_concentration, (Param("pct", "Two largest suppliers' share from", 60, PCT),)),
    Rule("late_suppliers", "buying", "Purchase Orders Past Required By", "med", "Purchasing",
         late_suppliers,
         (Param("days", "Late by more than", 7, D), Param("count", "At least (orders)", 1, C))),
    Rule("bills_not_matching", "buying", "Purchase Invoices Without PO or Purchase Receipt", "med",
         "Finance", bills_not_matching, (Param("amount", "Recommend when more than", 1000, A),)),
    Rule("long_unpaid_bills", "buying", "Supplier Ledger Balance Over 90 Days", "med",
         "Finance", long_unpaid_bills, (Param("amount", "Recommend when more than", 10000, A),),
         twin_alert="Overdue supplier invoices"),
    # people and control
    Rule("approvals_bottleneck", "control", "Approvals Waiting at One Workflow State", "high",
         "Directors", approvals_bottleneck,
         (Param("count", "At least (documents)", 3, C),
          Param("days", "Or the oldest waiting at least", 14, D),
          Param("crit_days", "Critical when the oldest waits", 60, D),
          Param("crit_amount", "And is worth at least", 50000, A))),
    Rule("overdue_tasks_by_owner", "control", "Late jobs, by who holds them", "med",
         "Operations", overdue_tasks_by_owner, (Param("count", "More than (jobs)", 0, C),),
         twin_alert="Jobs past their date"),
    Rule("self_approvals", "control", "Approved by Their Owner", "high", "Directors",
         self_approvals, (Param("count", "More than (documents)", 0, C),)),
    Rule("leavers_trend", "control", "More People Leaving", "med", "HR", leavers_trend,
         (Param("count", "At least (leavers in six months)", 3, C),)),
    # data hygiene
    Rule("draft_documents", "data", "Draft Sales Invoices", "med", "Finance",
         draft_documents,
         (Param("days", "Older than", 7, D), Param("count", "More than (invoices)", 0, C)),
         twin_alert="Invoices never issued"),
    Rule("duplicate_departments", "data", "Duplicate Departments", "info", "HR",
         duplicate_departments, (Param("count", "At least (departments)", 1, C),)),
    Rule("missing_valuations", "data", "Stock with No Valuation Rate", "med", "Stock Manager",
         missing_valuations, (Param("count", "More than (stock lines)", 0, C),)),
)
BY_ID = {r.rule_id: r for r in RULES}
