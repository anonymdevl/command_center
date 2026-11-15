"""The history of a business's key figures, from which its normal range is learned.

Two kinds of figure (Command Center Metric Point, one row per business, figure and
period):

  monthly   rebuilt from the loaded facts, so the history goes back as far as the
            invoices and payments do: sales, gross margin, sales with no cost, losses on
            lines sold below cost, purchases, money received, days to pay, and the
            share of the five largest customers and two largest suppliers over the
            twelve months to each month's end. Only full months before the data's last
            date. Rebuilt once a day per business (source "facts").
  daily     a position that only exists now -- what is owed by the ledger, payments not
            matched, orders late, stock held -- so its history is the platform's own
            daily snapshots (source "snapshot"), plus what three rules measured that the
            facts do not hold (slow stock, discounting, approvals waiting; source
            "rule": the rule's money at stake, 0 when it ran and found nothing).

Nothing is invented for a figure without enough history: baselines.baseline() says how
much more it needs. Every value is the business's own; nothing here names a business.

    capture(code)           refresh()'s first step: today's snapshot, and the monthly
                            rebuild when due
    capture_measured(...)   its last: the rule-measured figures from this pass
    history(code)           {metric: [(date, value)]}, read only
    assess(code, hist)      {metric: baseline} for every figure, read only
    why_now(m, b, cur)      the one sentence a recommendation shows about its figure
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections import defaultdict
from dataclasses import dataclass

import frappe

from command_center.recommend import baselines

DOCTYPE = "Command Center Metric Point"
MONTHS_KEY = "cc:metrics:months:{}:{}"


@dataclass(frozen=True)
class Metric:
    key: str
    label: str            # Title Case, as Settings and the evidence pack show it
    unit: str             # money | percent | days
    grain: str            # month | day
    direction: str        # up_bad | down_bad | either
    rules: tuple = ()     # the recommendation rules that watch this figure
    phrase: str = ""      # "is", "are": how the sentence reads


METRICS = (
    # monthly, from the facts
    Metric("revenue", "Sales Invoiced", "money", "month", "down_bad",
           ("sales_falling", "customers_gone_quiet")),
    Metric("gross_margin_pct", "Gross Margin", "percent", "month", "down_bad",
           ("margin_shrinking",)),
    Metric("uncosted_share", "Sales With No Cost Recorded", "percent", "month", "up_bad",
           ("lines_without_cost",)),
    Metric("below_cost_loss", "Losses on Sales Below Cost", "money", "month", "up_bad",
           ("sold_below_cost",), "are"),
    Metric("purchases", "Purchases Invoiced", "money", "month", "either", (), "are"),
    Metric("cash_received", "Customer Payments Matched to Invoices", "money", "month",
           "down_bad", (), "are"),
    Metric("days_to_pay", "Days Customers Take to Pay", "days", "month", "up_bad",
           ("days_to_pay_worsening",), "are"),
    Metric("customer_top5_share", "Five Largest Customers' Share of Sales", "percent",
           "month", "up_bad", ("customer_concentration",)),
    Metric("supplier_top2_share", "Two Largest Suppliers' Share of Purchases", "percent",
           "month", "up_bad", ("supplier_concentration",)),
    # daily snapshots of positions
    Metric("ar_ledger", "Customers Owe, by the Ledger", "money", "day", "up_bad", ()),
    Metric("ar_over_90", "Owed More Than 90 Days Late", "money", "day", "up_bad",
           ("overdue_customers", "credit_hold")),
    Metric("ap_ledger", "Owed to Suppliers, by the Ledger", "money", "day", "up_bad",
           ("supplier_payments_due", "long_unpaid_bills")),
    Metric("unmatched_receipts", "Customer Payments Not Matched", "money", "day", "up_bad",
           ("unmatched_receipts",), "are"),
    Metric("unmatched_supplier_payments", "Supplier Payments Not Matched", "money", "day",
           "up_bad", ("unmatched_supplier_payments",), "are"),
    Metric("customers_in_credit", "Customer Credit Held", "money", "day", "up_bad",
           ("customers_in_credit",)),
    Metric("overdue_deliveries", "Orders Past Their Promised Date", "money", "day", "up_bad",
           ("late_orders",), "are"),
    Metric("delivered_unbilled", "Delivered but Not Invoiced", "money", "day", "up_bad",
           ("delivered_unbilled",)),
    Metric("order_book", "Orders Still to Deliver", "money", "day", "either", (), "are"),
    Metric("stock_value", "Stock Held, at Cost", "money", "day", "either", ()),
    # daily, as the rules measured them
    Metric("slow_stock", "Stock Not Moving", "money", "day", "up_bad", ("stock_not_moving",)),
    Metric("discounting", "Discounts Outside the Price List", "money", "day", "up_bad",
           ("discounts_outside_price_list",), "are"),
    Metric("approvals_waiting", "Approvals Waiting at One Step", "money", "day", "up_bad",
           ("approvals_bottleneck",), "are"),
)
BY_KEY = {mt.key: mt for mt in METRICS}
RULE_MEASURED = {"slow_stock": "stock_not_moving", "discounting": "discounts_outside_price_list",
                 "approvals_waiting": "approvals_bottleneck"}
# rule -> the figure it watches (the first metric naming it)
RULE_METRIC = {}
for _mt in METRICS:
    for _r in _mt.rules:
        RULE_METRIC.setdefault(_r, _mt.key)


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- the facts
def _t(fact):
    from command_center.facts.schema import FACTS
    return frappe.qb.DocType(FACTS[fact])


def _by_day(code, fact, date_col, measure, where=None, by=None):
    """{(group, date): sum} or {date: sum}: per-day totals from the database, folded to
    months here (no date function differs between MariaDB and SQLite)."""
    from frappe.query_builder.functions import Sum
    t = _t(fact)
    cols = ([t[by]] if by else []) + [t[date_col]]
    q = frappe.qb.from_(t).select(*cols, Sum(t[measure])).where(t.business_code == code)
    for cond in (where(t) if where else []):
        q = q.where(cond)
    q = q.groupby(*cols)
    out = defaultdict(float)
    for row in q.run():
        *g, d, v = row
        if d is None:
            continue
        m = _first(frappe.utils.getdate(d))
        out[(g[0], m) if by else m] += _num(v)
    return out


def _first(d) -> _dt.date:
    return _dt.date(d.year, d.month, 1)


def _full_months(as_of) -> _dt.date:
    """The first day of the month the data ends in: months before it are complete."""
    return _first(as_of)


def _share(top_n, by_group_month, months):
    """For each month, the top_n groups' share of the twelve months to its end."""
    out = {}
    ordered = sorted(months)
    for i, m in enumerate(ordered):
        if i < 11:
            continue
        window = set(ordered[i - 11:i + 1])
        totals = defaultdict(float)
        for (g, mm), v in by_group_month.items():
            if mm in window and g:
                totals[g] += v
        whole = sum(v for v in totals.values() if v > 0)
        if whole <= 0 or len(totals) <= top_n:
            continue
        top = sum(sorted((v for v in totals.values() if v > 0), reverse=True)[:top_n])
        out[m] = 100.0 * top / whole
    return out


def monthly(code, as_of) -> dict:
    """{metric: {month_first: value}} for every complete month the facts hold."""
    from command_center.kpi.sales import RECEIVED
    end = _full_months(as_of)
    live = lambda t: [t.src_docstatus == 1]  # noqa: E731
    net = _by_day(code, "fact_sales_invoice_line", "posting_date", "base_net_amount", live)
    costed = _by_day(code, "fact_sales_invoice_line", "posting_date", "base_net_amount",
                     lambda t: [t.src_docstatus == 1, t.has_cost == 1])
    margin = _by_day(code, "fact_sales_invoice_line", "posting_date", "base_margin_amount",
                     lambda t: [t.src_docstatus == 1, t.has_cost == 1])
    below = _by_day(code, "fact_sales_invoice_line", "posting_date", "base_margin_amount",
                    lambda t: [t.src_docstatus == 1, t.has_cost == 1, t.base_margin_amount < 0])
    bought = _by_day(code, "fact_purchase_invoice_line", "posting_date", "base_net_amount", live)
    by_cust = _by_day(code, "fact_sales_invoice_line", "posting_date", "base_net_amount", live,
                      by="customer")
    by_supp = _by_day(code, "fact_purchase_invoice_line", "posting_date", "base_net_amount",
                      live, by="supplier")
    t = _t("fact_payment_allocation")
    q = (frappe.qb.from_(t).select(t.posting_date, t.days_to_pay, t.allocated_amount)
         .where(t.business_code == code).where(t.payment_type == RECEIVED["payment_type"])
         .where(t.against_doctype == RECEIVED["against_doctype"]))
    paid, weighted, weights = defaultdict(float), defaultdict(float), defaultdict(float)
    for d, days, amt in q.run():
        if d is None:
            continue
        m = _first(frappe.utils.getdate(d))
        paid[m] += _num(amt)
        if days is not None and _num(amt) > 0:
            weighted[m] += _num(days) * _num(amt)
            weights[m] += _num(amt)

    def done(series):
        return {m: v for m, v in series.items() if m < end}
    sales_months = sorted(m for m in net if m < end)
    # A month with no sales at all inside the span is a real zero, not a gap.
    span = _span(sales_months)
    out = {
        "revenue": {m: net.get(m, 0.0) for m in span},
        # A margin outside -100%..100% is a cost recorded wrongly, not a margin (as
        # rules.margin_shrinking judges it): that month is left out, not learned from.
        "gross_margin_pct": {m: 100.0 * margin[m] / costed[m] for m in done(costed)
                             if costed[m] > 0 and -100 <= 100.0 * margin[m] / costed[m] <= 100},
        "uncosted_share": {m: 100.0 * max(0.0, net.get(m, 0.0) - costed.get(m, 0.0)) / net[m]
                           for m in span if net.get(m, 0.0) > 0},
        "below_cost_loss": {m: -below.get(m, 0.0) for m in span},
        "purchases": {m: bought.get(m, 0.0) for m in _span(sorted(m for m in bought if m < end))},
        "cash_received": {m: paid.get(m, 0.0) for m in _span(sorted(m for m in paid if m < end))},
        "days_to_pay": {m: weighted[m] / weights[m] for m in done(weights) if weights[m] > 0},
        "customer_top5_share": _share(5, {k: v for k, v in by_cust.items() if k[1] < end}, span),
        "supplier_top2_share": _share(2, {k: v for k, v in by_supp.items() if k[1] < end},
                                      _span(sorted({k[1] for k in by_supp if k[1] < end}))),
    }
    return {k: v for k, v in out.items() if v}


def _span(months) -> list:
    if not months:
        return []
    out, m = [], months[0]
    while m <= months[-1]:
        out.append(m)
        m = _dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out


def positions(code) -> dict:
    """Today's positions, from the loaded facts: {metric: value}."""
    from frappe.query_builder.functions import Sum
    out = {}
    t = _t("fact_party_balance")
    for party_type, cols in (("Customer", {"ar_ledger": "owed", "ar_over_90": "d90_plus",
                                           "unmatched_receipts": "unmatched_payments",
                                           "customers_in_credit": "in_credit"}),
                             ("Supplier", {"ap_ledger": "owed",
                                           "unmatched_supplier_payments": "unmatched_payments"})):
        q = (frappe.qb.from_(t).select(*[Sum(t[c]) for c in cols.values()])
             .where(t.business_code == code).where(t.party_type == party_type))
        row = (q.run() or [[None] * len(cols)])[0]
        if row and any(v is not None for v in row):
            out.update({k: _num(v) for k, v in zip(cols, row)})
    so = _t("fact_sales_order")
    rows = (frappe.qb.from_(so).select(so.undelivered_value, so.unbilled_value, so.days_late,
                                       so.per_delivered)
            .where(so.business_code == code).where(so.is_open == 1).run())
    if rows:
        out["order_book"] = sum(_num(r[0]) for r in rows)
        out["overdue_deliveries"] = sum(_num(r[0]) for r in rows if _num(r[2]) > 0)
        out["delivered_unbilled"] = sum(_num(r[1]) for r in rows if _num(r[3]) >= 100)
    sb = _t("fact_stock_balance")
    got = (frappe.qb.from_(sb).select(Sum(sb.stock_value)).where(sb.business_code == code).run()
           or [[None]])[0][0]
    if got is not None:
        out["stock_value"] = _num(got)
    return out


# --------------------------------------------------------------------------- storing
def _upsert(code, grain, values: dict, source: str, now):
    """One row per (business, metric, grain, period): updated if there, else inserted."""
    if not values:
        return
    keys = {(mt, p) for mt, series in values.items() for p in series}
    have = {}
    for r in frappe.get_all(DOCTYPE, filters={"business_code": code, "grain": grain,
                                              "metric": ["in", sorted({k[0] for k in keys})]},
                            fields=["name", "metric", "period", "value"], limit=100000):
        have[(r.metric, frappe.utils.getdate(r.period))] = r
    new = []
    for mt, series in values.items():
        for period, v in series.items():
            v = round(float(v), 6)
            row = have.get((mt, period))
            if row is None:
                new.append((uuid.uuid4().hex, code, mt, grain, period, v, source, now))
            elif abs(_num(row.value) - v) > 1e-6:
                frappe.db.set_value(DOCTYPE, row.name, {"value": v, "source": source,
                                                        "captured_at": now})
    if new:
        frappe.db.bulk_insert(DOCTYPE, ["name", "business_code", "metric", "grain", "period",
                                        "value", "source", "captured_at"], new)


def capture(code, as_of=None, today=None, force_months=False):
    """refresh()'s first step (writes): today's positions, and the monthly rebuild once a
    day (or when forced)."""
    now = frappe.utils.now_datetime()
    day = frappe.utils.getdate(today or frappe.utils.today())
    if as_of is None:
        from command_center.api.panels import _as_of
        as_of = _as_of(code)
    key = MONTHS_KEY.format(code, day)
    if force_months or not frappe.cache().get_value(key):
        _upsert(code, "month", monthly(code, frappe.utils.getdate(as_of)), "facts", now)
        frappe.cache().set_value(key, 1, expires_in_sec=26 * 3600)
    _upsert(code, "day", {k: {day: v} for k, v in positions(code).items()}, "snapshot", now)


def capture_measured(code, result, today=None):
    """refresh()'s last step (writes): what three rules measured in this pass (compute()'s
    output) -- their money at stake, 0 when the rule ran and found nothing."""
    now = frappe.utils.now_datetime()
    day = frappe.utils.getdate(today or frappe.utils.today())
    ran = set(result.get("ran") or [])
    measured = {}
    for metric, rule in RULE_MEASURED.items():
        if rule in ran:
            measured[metric] = {day: sum(_num(r.get("money_at_stake")) for r in result["recs"]
                                         if r.get("rule") == rule)}
    _upsert(code, "day", measured, "rule", now)


# --------------------------------------------------------------------------- reading
def history(code) -> dict:
    """{metric: [(date, value)]}, each in its grain, oldest first. Reads only."""
    out = defaultdict(list)
    for r in frappe.get_all(DOCTYPE, filters={"business_code": code},
                            fields=["metric", "grain", "period", "value"],
                            order_by="period asc", limit=200000):
        mt = BY_KEY.get(r.metric)
        if mt is None or mt.grain != r.grain:
            continue
        out[r.metric].append((frappe.utils.getdate(r.period), _num(r.value)))
    return dict(out)


def assess(code, hist=None) -> dict:
    """{metric: baseline} for every figure in the catalogue (learning where too short)."""
    hist = history(code) if hist is None else hist
    return {mt.key: baselines.baseline(hist.get(mt.key) or [], mt.grain, mt.direction)
            for mt in METRICS}


# --------------------------------------------------------------------------- words
def fmt(cur, unit, v) -> str:
    v = _num(v)
    if unit == "percent":
        return f"{v:.1f}%"
    if unit == "days":
        return f"{v:.0f} days"
    for div, suf, dp in ((1e9, "B", 2), (1e6, "M", 2), (1e3, "k", 0)):
        if abs(v) >= div:
            return f"{cur} {v / div:,.{dp}f}{suf}".strip()
    return f"{cur} {v:,.0f}".strip()


def _when(mt, b) -> str:
    d = frappe.utils.getdate(b.get("latest_on"))
    if mt.grain == "month":
        return d.strftime("%B %Y")
    return "today"


def why_now(mt: Metric, b: dict, cur: str) -> str | None:
    """'Customer Payments Not Matched are 2.4x their usual level (GHS 3.0M, against a usual
    GHS 1.2M-1.3M over the last 90 days).' None when the figure is within its range, has
    moved the harmless way, or is still learning."""
    if not b or b.get("status") != "ready":
        return None
    z, ratio = b.get("z") or 0, b.get("ratio")
    shift = b.get("shift")
    now = fmt(cur, mt.unit, b["latest"])
    usual = f"{fmt(cur, mt.unit, max(b['low'], 0) if mt.unit != 'percent' else b['low'])}" \
            f"–{fmt(cur, mt.unit, b['high'])}"
    if b["method"] == "seasonal":
        basis = f"for {frappe.utils.getdate(b['latest_on']).strftime('%B')}, allowing for the " \
                f"same month last year and the trend since"
    else:
        basis = f"over the last {b.get('window')} {'months' if mt.grain == 'month' else 'days'}"
    verb = mt.phrase or "is"
    # Only a movement the wrong way is a reason to act now: losses falling is not.
    worse = {"up_bad": z > 0, "down_bad": z < 0}.get(mt.direction, True)
    if abs(z) >= 2 and worse:
        if ratio and mt.unit == "money" and (ratio >= 1.5 or 0 < ratio <= 0.67):
            return (f"{mt.label} {verb} {ratio:g}× {'their' if verb == 'are' else 'its'} usual "
                    f"level {basis} ({now} {_when(mt, b)}, against a usual {usual}).")
        word = "above" if z > 0 else "below"
        return (f"{mt.label} {verb} {word} {'their' if verb == 'are' else 'its'} usual range "
                f"{basis}: {now} {_when(mt, b)}, against a usual {usual}.")
    if shift and shift.get("bad", True):
        return (f"{mt.label} {verb} {'up' if shift['direction'] == 'up' else 'down'} for "
                f"{shift['points']} {'months' if mt.grain == 'month' else 'days'} running: "
                f"{fmt(cur, mt.unit, shift['level'])} against "
                f"{fmt(cur, mt.unit, shift['before'])} before.")
    return None


def band_words(mt: Metric, b: dict, cur: str) -> str:
    """The baseline in words, for Settings and the expanded card."""
    if not b or b.get("status") != "ready":
        return (b or {}).get("says") or baselines._needs(mt.grain, 0)
    how = ("seasonal: the same month last year and the trend since"
           if b["method"] == "seasonal" else
           f"the last {b.get('window')} {'months' if mt.grain == 'month' else 'days'}")
    low = max(b["low"], 0) if mt.unit != "percent" else b["low"]
    return (f"Usual range {fmt(cur, mt.unit, low)}–{fmt(cur, mt.unit, b['high'])} ({how}); "
            f"now {fmt(cur, mt.unit, b['latest'])}.")


def spark(mt: Metric, b: dict) -> dict | None:
    """What the card's small chart draws: the figure's recent points and its usual band."""
    if not b or not b.get("spark") or len(b["spark"]) < 2:
        return None
    out = {"metric": mt.key, "label": mt.label, "unit": mt.unit, "grain": mt.grain,
           "points": b["spark"]}
    if b.get("status") == "ready":
        out.update(low=b["low"], high=b["high"], centre=b["centre"])
    return out
