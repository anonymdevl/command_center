"""Turning a definition into a figure, with everything needed to trust it.

A value on its own is not enough to act on. Every result carries what it was
measured against, what it is a subset of if it is one, how fresh the underlying
load is, and where its records are — so a screen never has to add those itself
and cannot forget to.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Avg, Count, Max, Sum

from command_center.api.businesses import currency_for
from command_center.facts.schema import FACTS, condition
from command_center.kpi.registry import (
    Kpi, dependencies, get, load_all, value_dependencies, _resolve_token)


def evaluate(key: str, business_code: str | None = None) -> dict:
    """One KPI. Goes through evaluate_set so a ratio or a note still gets its parts."""
    return evaluate_set([key], business_code)[key]


def _evaluate_one(kpi: Kpi, business_code, resolved: dict) -> dict:
    period = _period(kpi, business_code)
    filters = dict(kpi.filters or {})
    drill = dict(kpi.drill_filters or {})
    if period:
        span = ["between", [period["from"], period["to"]]]
        filters[period["field"]] = span
        drill[period["field"]] = span

    group = None
    if kpi.agg == "ratio":
        value = _ratio(kpi, resolved)
    elif period and not period["from"]:
        value = None              # no dated rows at all: nothing to measure, not zero
    elif kpi.agg == "top":
        value, group = _top(kpi, business_code, filters)
        if group and group.get("drill"):
            drill.update(group.pop("drill"))
    else:
        value = _aggregate(kpi, business_code, filters)
    state = _load_state(kpi.fact, business_code)
    currency = currency_for(business_code) if kpi.unit == "currency" else None

    return {
        "key": kpi.key,
        "label": kpi.label,
        "value": value,
        "unit": kpi.unit,
        "direction": kpi.direction,
        "currency": currency,
        "mixed_currency": kpi.unit == "currency" and currency is None
                          and (not business_code or business_code == "__all__"),
        "scope": business_code or "__all__",
        "as_of": _as_of(kpi, state),
        "basis": kpi.subset_of,
        "drill": ({"kpis": [kpi.numerator, kpi.denominator]} if kpi.agg == "ratio"
                  else {"fact": kpi.fact, "filters": drill}),
        "data_status": _status(state),
        "period": period,
        "group": group,
    }


def _ratio(kpi: Kpi, resolved: dict):
    """A percentage is only as honest as its denominator, so the denominator is named.

    None rather than zero when there is nothing to divide by: a margin of 0% and a
    margin that cannot be computed are different statements, and showing the first
    when you mean the second is a lie the interface would repeat.
    """
    bottom = resolved.get(kpi.denominator, {}).get("value") or 0
    if not bottom:
        return None
    top = resolved.get(kpi.numerator, {}).get("value") or 0
    return round(top / bottom * (100 if kpi.unit == "percent" else 1), 4)


def evaluate_set(keys: list[str], business_code: str | None = None) -> dict:
    """Several KPIs together, with notes resolved against each other.

    A note like "{ar_over_90_share} of the balance" needs the balance, so notes
    are rendered once the whole set is known. Rendering them one at a time is how
    a share and its total end up disagreeing.
    """
    load_all()

    # A note may need a figure the screen did not ask for. Evaluate those too and
    # drop them before returning, rather than rendering an em dash where a
    # percentage belongs.
    asked = list(dict.fromkeys(keys))
    needed = set(asked)
    frontier = set(asked)
    while frontier:
        nxt = set()
        for key in frontier:
            for dep in dependencies(key):
                if dep not in needed:
                    needed.add(dep)
                    nxt.add(dep)
        frontier = nxt

    # Ratios read values rather than tables, so their parts must be evaluated
    # first. A proper dependency order, not a guess based on how many dependencies
    # each one has -- that happens to work for one level and stops being true the
    # moment anything nests.
    results: dict = {}
    for key in _in_dependency_order(needed):
        results[key] = _evaluate_one(get(key), business_code, results)

    values = {k: r["value"] for k, r in results.items()}
    for key, result in results.items():
        result["note"] = _render_note(get(key), values, results)
    return {k: results[k] for k in asked}


# ---------------------------------------------------------------------------
def _in_dependency_order(keys: set) -> list:
    """Ratio parts before the ratios that divide them.

    Only value dependencies order this. Notes are rendered afterwards, so two KPIs
    quoting each other is not a cycle and must not be treated as one.

    A genuine cycle -- a ratio of a ratio of itself -- cannot be ordered. The
    remainder is appended rather than looped over, so the ratio inside it reads a
    missing value and reports that it cannot be computed instead of a wrong number.
    preflight fails the build on one, so this path should not run in a live site.
    """
    remaining = {k: value_dependencies(k) & keys for k in keys}
    ordered = []
    while remaining:
        ready = sorted(k for k, deps in remaining.items()
                       if not deps - set(ordered))
        if not ready:
            ordered.extend(sorted(remaining))
            break
        ordered.extend(ready)
        for k in ready:
            remaining.pop(k)
    return ordered


def _table(kpi: Kpi):
    target = FACTS.get(kpi.fact)
    if not target:
        frappe.throw(f"KPI {kpi.key}: unknown fact {kpi.fact!r}")
    return frappe.qb.DocType(target)


def _scoped(q, t, business_code, filters):
    if business_code and business_code != "__all__":
        q = q.where(t.business_code == business_code)
    for field, rule in (filters or {}).items():
        q = q.where(condition(t[field], rule))
    return q


def _aggregate(kpi: Kpi, business_code: str | None, filters: dict):
    t = _table(kpi)
    q = frappe.qb.from_(t)
    if kpi.agg == "count":
        q = q.select(Count(t.name))
    elif kpi.agg == "count_distinct":
        q = q.select(Count(t[kpi.distinct_on]).distinct())
    elif kpi.agg == "avg":
        q = q.select(Avg(t[kpi.measure]))
    elif kpi.agg == "max":
        q = q.select(Max(t[kpi.measure]))
    else:
        q = q.select(Sum(t[kpi.measure]))

    row = _scoped(q, t, business_code, filters).run()
    value = row[0][0] if row and row[0] else None
    # An average or a maximum of nothing is unknown; a sum or a count of nothing is 0.
    if kpi.agg in ("avg", "max"):
        return None if value is None else round(float(value), 4)
    return value or 0


def _top(kpi: Kpi, business_code: str | None, filters: dict):
    """The leading group or groups: "Best month", "Top supplier", "Worst shortfall".

    Totals per group come from the database; months are formed here from per-day
    totals, so nothing depends on a date function that MariaDB and Postgres spell
    differently. Returns the value and the group -- its label, and the filter that
    narrows the drill to it, so "Best month" opens June's invoices and not all of them.
    """
    t = _table(kpi)
    by_month = kpi.group_by.startswith("month:")
    col = kpi.group_by[6:] if by_month else kpi.group_by
    inner = {"sum": lambda: Sum(t[kpi.measure]), "max": lambda: Max(t[kpi.measure]),
             "count": lambda: Count(t.name)}[kpi.group_agg]()
    q = frappe.qb.from_(t).select(t[col], inner).groupby(t[col])
    rows = _scoped(q, t, business_code, filters).run()

    totals: dict = {}
    for key, total in rows:
        if key in (None, ""):
            continue
        if by_month:
            d = frappe.utils.getdate(key)
            key = (d.year, d.month)
        total = float(total or 0)
        if key in totals and kpi.group_agg == "max":
            totals[key] = max(totals[key], total)
        else:
            totals[key] = totals.get(key, 0) + total
    if not totals:
        return None, None

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=kpi.order == "desc")
    lead = ranked[: kpi.top_n]
    value = sum(v for _, v in lead)
    if kpi.as_share:
        whole = sum(totals.values())
        value = round(value / whole * 100, 4) if whole else None
    elif kpi.negate:
        value = -value

    if by_month:
        y, m = lead[0][0]
        first = frappe.utils.getdate(f"{y}-{m:02d}-01")
        label = first.strftime("%B %Y")
        span = ["between", [str(first), str(frappe.utils.get_last_day(first))]]
        narrow = {col: span}
    else:
        names = [str(k) for k, _ in lead]
        label = " and ".join(names)
        narrow = {col: names[0] if len(names) == 1 else ["in", names]}
    return value, {"label": label, "drill": narrow}


def _period(kpi: Kpi, business_code: str | None) -> dict | None:
    """The window a dated KPI covers, counted back from the last date in its own data.

    Not from today: this dataset ends in 2025, and a month measured from today is a
    month with nothing in it. "Last full month" is the latest calendar month the data
    covers to its final day -- if the data stops on 12 August, that is July.
    """
    if not kpi.period:
        return None
    field, window = kpi.period["field"], kpi.period["window"]
    t = _table(kpi)
    q = frappe.qb.from_(t).select(Max(t[field]))
    row = _scoped(q, t, business_code, kpi.filters).run()
    horizon = row[0][0] if row and row[0] else None
    if not horizon:
        return {"field": field, "from": None, "to": None, "label": "no dated records"}

    u = frappe.utils
    horizon = u.getdate(horizon)
    if window.startswith("last_days_"):
        n = int(window.rsplit("_", 1)[1])
        start, end = u.add_days(horizon, -(n - 1)), horizon
        label = f"the {n} days to {horizon.day} {horizon:%b %Y}"
    else:
        n = 1 if window == "last_full_month" else int(window.rsplit("_", 1)[1])
        end = (horizon if horizon == u.getdate(u.get_last_day(horizon))
               else u.getdate(u.add_days(u.get_first_day(horizon), -1)))
        start = u.getdate(u.get_first_day(u.add_months(end, -(n - 1))))
        label = (f"{end:%B %Y}" if n == 1 else
                 f"{start:%b} – {end:%b %Y}" if start.year == end.year else
                 f"{start:%b %Y} – {end:%b %Y}")
    return {"field": field, "from": str(u.getdate(start)), "to": str(u.getdate(end)),
            "label": label}



def _load_state(fact: str, business_code: str | None):
    filters = {"fact": fact}
    if business_code and business_code != "__all__":
        filters["business_code"] = business_code
    rows = frappe.get_all("Command Center Ingest State", filters=filters,
                          fields=["as_of_date", "last_run", "status", "rows_loaded"],
                          limit=1)
    return rows[0] if rows else None


def _as_of(kpi: Kpi, state) -> dict | None:
    """The point in time the figure describes.

    `data_horizon` means the latest date the data covers, which on a restored or
    archived dataset is not today. Saying so on every figure is the whole defence
    against reading a stale snapshot as a current one.
    """
    if kpi.as_of_basis == "none":
        return None
    if kpi.as_of_basis == "today":
        return {"date": frappe.utils.today(), "basis": "today"}
    if not state or not state.get("as_of_date"):
        return None
    return {
        "date": str(state["as_of_date"]),
        "basis": "the latest date the data covers",
        "last_read": str(state.get("last_run")) if state.get("last_run") else None,
    }


def _status(state) -> dict:
    if not state:
        return {"state": "not_loaded", "days_behind": None,
                "message": "These facts have never been loaded."}
    if state.get("status") == "Failed":
        return {"state": "failed",
                "message": "The last load failed, so this figure may be out of date."}
    days = None
    if state.get("as_of_date"):
        days = frappe.utils.date_diff(frappe.utils.today(), state["as_of_date"])
    if days is not None and days > 45:
        return {"state": "stale", "days_behind": days,
                "message": f"The data covers up to {state['as_of_date']}, "
                           f"{days} days ago."}
    return {"state": "live", "days_behind": days, "message": None}




def _render_note(kpi: Kpi, values: dict, results: dict) -> str:
    if not kpi.note:
        return ""
    import re

    def substitute(match):
        token = match.group(1)
        if token == "period":
            return (results.get(kpi.key, {}).get("period") or {}).get("label") or "—"
        if token == "group":
            return (results.get(kpi.key, {}).get("group") or {}).get("label") or "—"
        referenced, wants_share = _resolve_token(token)
        if referenced not in results:
            return match.group(0)
        if not wants_share:
            return _plain(results[referenced])
        whole_key = get(referenced).share_of
        whole = values.get(whole_key) or 0
        if not whole or values.get(referenced) is None:
            return "—"
        pct = values[referenced] / whole * 100
        # 99.94% must not be written "100%". A share that rounds to the whole reads
        # as "all of it", which is the opposite of what revenue_uncosted exists to
        # say. Extra precision only where rounding would mislead.
        if pct not in (0, 100) and round(pct) in (0, 100):
            return f"{pct:.2f}%"
        return f"{pct:.0f}%"

    return re.sub(r"\{([a-z0-9_]+)\}", substitute, kpi.note)


def _plain(result: dict) -> str:
    if result["value"] is None:
        return "—"
    value = result["value"]
    if result["unit"] == "percent":
        return f"{value:.1f}%"
    if result["unit"] == "currency":
        return f"{result.get('currency') or ''} {value:,.2f}".strip()
    if result["unit"] == "count":
        return f"{int(value):,}"
    if result["unit"] == "quantity":
        return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"
    if result["unit"] == "days":
        return f"{value:,.0f} days"
    return str(value)
