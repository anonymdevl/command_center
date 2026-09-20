"""Turning a definition into a figure, with everything needed to trust it.

A value on its own is not enough to act on. Every result carries what it was
measured against, what it is a subset of if it is one, how fresh the underlying
load is, and where its records are — so a screen never has to add those itself
and cannot forget to.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Sum

from command_center.api.businesses import currency_for
from command_center.facts.schema import FACTS, condition
from command_center.kpi.registry import (
    Kpi, dependencies, get, load_all, value_dependencies, _resolve_token)


def evaluate(key: str, business_code: str | None = None) -> dict:
    """One KPI. Goes through evaluate_set so a ratio or a note still gets its parts."""
    return evaluate_set([key], business_code)[key]


def _evaluate_one(kpi: Kpi, business_code, resolved: dict) -> dict:
    value = (_ratio(kpi, resolved) if kpi.agg == "ratio"
             else _aggregate(kpi, business_code))
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
                  else {"fact": kpi.fact, "filters": kpi.drill_filters}),
        "data_status": _status(state),
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


def _aggregate(kpi: Kpi, business_code: str | None):
    target = FACTS.get(kpi.fact)
    if not target:
        frappe.throw(f"KPI {kpi.key}: unknown fact {kpi.fact!r}")

    t = frappe.qb.DocType(target)
    q = frappe.qb.from_(t)
    q = q.select(Count(t.name) if kpi.agg == "count" else Sum(t[kpi.measure]))

    if business_code and business_code != "__all__":
        q = q.where(t.business_code == business_code)

    for field, rule in (kpi.filters or {}).items():
        q = q.where(condition(t[field], rule))

    row = q.run()
    return (row[0][0] or 0) if row and row[0] else 0



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
        referenced, wants_share = _resolve_token(match.group(1))
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
    return str(value)
