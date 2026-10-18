"""The alert rules: material exceptions, stated in the six parts §9 asks for.

Each rule reads KPIs from the engine rather than querying for itself, so an alert and
the card beside it can never disagree about a number -- "GHS 6.78M is more than three
months late" on Home is the same figure as the receivables card, computed once.

A rule returns None (nothing to raise) or one finding:

    title       what happened, in a sentence
    why         why it matters
    next        the decision available ("Pick the three largest...")
    figure      the number, with its unit and currency
    drill       the records behind it (fact and filters), so the alert opens to them
    owner       who would normally act
    since       when the condition began, as a date, for "elapsed"

Thresholds are not here. Each rule's defaults seed a Command Center Alert Rule record
the site's administrators can change without a release (AL-05); `p` is that record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str
    description: str
    kpis: tuple
    fn: Callable
    threshold_amount: float = 0
    threshold_days: int = 0
    threshold_count: int = 0
    since: tuple | None = None        # (kpi key, date field) for "elapsed"


def money(fig) -> str:
    v = fig.get("value") or 0
    cur = fig.get("currency") or ""
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(v) >= div:
            return f"{cur} {v / div:,.2f}{suf}".strip()
    return f"{cur} {v:,.0f}".strip()


def _t(p, name) -> float:
    """A threshold from the rule's record; an empty field means none (zero)."""
    return float(p.get(name) or 0)


def _n(fig) -> int:
    return int(fig.get("value") or 0)


def _finding(title, why, next_, fig, owner, drill_from=None, unit=None):
    src = drill_from or fig
    return {"title": title, "why": why, "next": next_, "figure": fig.get("value"),
            "unit": unit or fig.get("unit"), "currency": fig.get("currency"),
            "drill": src.get("drill") or {}, "owner": owner,
            "source": src.get("label") or ""}


# ---------------------------------------------------------------------------
def ar_overdue(f, p):
    late, whole = f["ar_over_90"], f["ar_total"]
    if (late.get("value") or 0) <= _t(p, 'threshold_amount'):
        return None
    top = f["largest_debt"]
    share = (late["value"] / whole["value"] * 100) if whole.get("value") else 0
    return _finding(
        f"{money(late)} of the {money(whole)} owed is more than three months late",
        f"{share:.0f}% of everything owed. The largest single debtor is "
        f"{(top.get('group') or {}).get('label') or 'unknown'}, at {money(top)}.",
        "Pick the three largest and agree payment dates this week.",
        late, "Finance")


def stock_shortfall(f, p):
    short = f["stock_short_products"]
    if _n(short) <= _t(p, 'threshold_count'):
        return None
    worst = f["stock_worst_shortfall"]
    return _finding(
        f"We have promised customers stock we do not physically have, across "
        f"{_n(short):,} products",
        f"Any of those orders can fail the moment the warehouse goes to pick it. The "
        f"worst is {(worst.get('group') or {}).get('label') or 'one product'}, "
        f"{(worst.get('value') or 0):,.0f} short.",
        "Freeze new commitments on the worst lines until a count is done.",
        short, "Stock Manager", unit="products")


def orders_late(f, p):
    n, value = f["order_book_late_count"], f["order_book_late"]
    if _n(n) <= _t(p, 'threshold_count') or (value.get("value") or 0) <= _t(p, 'threshold_amount'):
        return None
    return _finding(
        f"{_n(n):,} orders worth {money(value)} are past the delivery date we promised",
        "Every day past the promise is a customer deciding whether to order again.",
        "Call the customers before they call you, and agree new dates.",
        value, "Sales")


def delivered_unbilled(f, p):
    value, n = f["order_delivered_unbilled"], f["order_delivered_unbilled_count"]
    if (value.get("value") or 0) <= _t(p, 'threshold_amount') or _n(n) <= _t(p, 'threshold_count'):
        return None
    return _finding(
        f"{_n(n):,} orders were delivered but not invoiced, worth {money(value)}",
        "Goods that have left and are not billed are not owed to us, so nobody is "
        "chasing them.",
        "Raise the invoices, or say why each is not to be billed.",
        value, "Finance")


def tasks_overdue(f, p):
    n = f["tasks_overdue"]
    if _n(n) <= _t(p, 'threshold_count'):
        return None
    oldest = f["tasks_longest_wait"]
    days = oldest.get("value") or 0
    age = f"{days / 30.4:.0f} months" if days >= 60 else f"{days:.0f} days"
    return _finding(
        f"{_n(n):,} jobs are past their date",
        f"The longest wait is {(oldest.get('group') or {}).get('label') or 'one job'}, "
        f"{age} late. Late jobs are usually money held up as well.",
        "Give each one an owner and a new date.",
        n, "Engineering", unit="jobs")


def invoices_draft(f, p):
    n, value = f["invoices_draft"], f["invoices_draft_value"]
    if _n(n) <= _t(p, 'threshold_count'):
        return None
    return _finding(
        f"{_n(n):,} invoices were written but never issued, worth {money(value)}",
        "A draft is in nobody's figures: not owed, not revenue, not chased.",
        "Issue them or cancel them.",
        value, "Finance")


def ap_overdue(f, p):
    late = f["ap_over_90"]
    if (late.get("value") or 0) <= _t(p, 'threshold_amount'):
        return None
    return _finding(
        f"{money(late)} we owe suppliers is more than three months overdue",
        f"Of {money(f['ap_total'])} owed to suppliers in all. Suppliers this far "
        f"behind start holding deliveries.",
        "Agree a payment plan with the largest before supply is held.",
        late, "Finance")


RULES = (
    Rule("Overdue receivables", "crit",
         "Money owed to us more than three months late, above the amount set here.",
         ("ar_over_90", "ar_total", "largest_debt"), ar_overdue,
         threshold_amount=50000, since=("ar_over_90", "due_date")),
    Rule("Stock promised but not there", "crit",
         "Products reserved for customers beyond what is physically on hand.",
         ("stock_short_products", "stock_worst_shortfall"), stock_shortfall),
    Rule("Orders past their promised date", "high",
         "Open sales orders whose delivery date has passed.",
         ("order_book_late_count", "order_book_late"), orders_late,
         since=("order_book_late", "delivery_date")),
    Rule("Delivered but not invoiced", "high",
         "Sales orders fully delivered with value still unbilled.",
         ("order_delivered_unbilled", "order_delivered_unbilled_count"), delivered_unbilled,
         since=("order_delivered_unbilled", "transaction_date")),
    Rule("Jobs past their date", "high",
         "Open tasks and installation jobs whose expected end date has passed.",
         ("tasks_overdue", "tasks_longest_wait"), tasks_overdue,
         since=("tasks_overdue", "exp_end_date")),
    Rule("Invoices never issued", "med",
         "Sales invoices saved as drafts and never submitted.",
         ("invoices_draft", "invoices_draft_value"), invoices_draft,
         since=("invoices_draft", "posting_date")),
    Rule("Overdue supplier invoices", "med",
         "What we owe suppliers more than three months overdue, above the amount set here.",
         ("ap_over_90", "ap_total"), ap_overdue,
         threshold_amount=50000, since=("ap_over_90", "due_date")),
)

SEVERITY_RANK = {"crit": 0, "high": 1, "med": 2, "info": 3}
