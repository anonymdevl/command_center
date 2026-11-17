"""Promised orders and what covers them (command_center/coverage.py), for the screens.

    panel(ctx, view)   the "Promised Orders — Cover" panel on Sales, Stock and Buying
    summary(...)       "Promised, not delivered" split by what covers it, for the figure's
                       drawer (Records.jsx, when the figure says explained_by "order_cover")
    lines(...)         more rows of one state, for the panel's Show More

Managers only, as every screen call. The rows are cut to what the table and its drawer
draw; the coverage itself is kept per business (speed.py, kind "cover").
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager

HEADING = "Promised Orders — Cover"
PER_STATE = 25
MAX_PAGE = 100
# What a row carries to the screen: the table's cells and the drawer's chain.
ROW_KEYS = ("id", "order", "order_href", "customer", "item_code", "item_name", "item_href",
            "warehouse", "uom", "ordered_on", "deliver_by", "order_status", "ordered",
            "delivered", "pending", "value", "state", "state_label", "basis",
            "late_to_customer", "days_late", "supplier_late", "from_stock", "elsewhere",
            "received", "on_order", "requested", "missing", "covers", "requests", "narrative")
# The screen each panel opens on: Buying is where the ones not ordered are acted on.
DEFAULT_FILTER = {"proc": "needs"}


def _rows(lines):
    return [{k: l.get(k) for k in ROW_KEYS} for l in lines]


def _ranked(lines):
    from command_center.coverage import STATE
    return sorted(lines, key=lambda l: (STATE[l["state"]]["rank"], -l["value"], l["order"]))


def _money(cur, v) -> str:
    from command_center.api.panels import _short
    return f"{cur} {_short(v)}".strip()


def reading(got) -> str:
    """The panel's sentence: what of the promise is covered, and what is not."""
    s, cur = got["summary"], got.get("currency") or ""
    parts = {p["key"]: p["value"] for p in s["parts"]}
    on_order = parts["linked"] + parts["likely"]
    bits = [f"{_money(cur, parts['stock'] + parts['received'])} can go from stock"]
    if on_order >= 0.5:
        bits.append(f"{_money(cur, on_order)} is on order")
    if parts["requested"] >= 0.5:
        bits.append(f"{_money(cur, parts['requested'])} is requested from buying")
    text = (f"Of the {_money(cur, s['value'])} promised and not delivered, " + ", ".join(bits)
            + f" and {_money(cur, parts['missing'])} is not ordered.")
    if s["stale"]["value"] >= 0.5:
        text += (f" {_money(cur, s['stale']['value'])} of what is not ordered, on "
                 f"{s['stale']['orders']:,} order{'s' if s['stale']['orders'] != 1 else ''}, "
                 f"was due more than a year ago: confirm those orders with the customers or "
                 f"close them.")
    if s["lines"] and not s["linked_lines"] and s["likely_lines"]:
        text += (" No purchase order names the sales order it is for, so what is on order "
                 "is inferred from the items and dates and marked Likely.")
    return text


def panel(ctx, view: str) -> dict:
    """The panel's answer: the states with their counts and amounts, and the rows of
    each (largest first, PER_STATE of each), each with its chain for the drawer."""
    from command_center import coverage
    from command_center.connectors.base import BusinessUnreachable
    down = getattr(ctx.reader(), "_down", None)
    if down is not None:
        raise down   # known not to answer: the screen says so at once
    got = coverage.get(ctx.code)
    if got.get("kind") != "cover":
        raise BusinessUnreachable("The business did not answer.")
    s = got["summary"]
    if not s["lines"]:
        from command_center.api.panels import SO_STEPS, _guide
        if not _orders_on_record(ctx):
            return _guide(ctx, "No submitted Sales Order is recorded in ERPNext yet.",
                          SO_STEPS, "/app/sales-order")
        return {"kind": "cover", "states": s["states"], "rows": [], "summary": s,
                "empty": "Every submitted Sales Order has been delivered in full.", "note": ""}
    by = {}
    for l in _ranked(got["lines"]):
        by.setdefault(l["state"], []).append(l)
    rows = [r for st in by.values() for r in st[:PER_STATE]]
    out = {
        "kind": "cover",
        "states": s["states"], "summary": s, "rows": _rows(rows),
        "per_state": PER_STATE, "default": DEFAULT_FILTER.get(view, "all"),
        "subtitle": (f"{s['lines']:,} line{'s' if s['lines'] != 1 else ''} on "
                     f"{s['orders']:,} open order{'s' if s['orders'] != 1 else ''}, "
                     f"read from ERPNext now"),
        "note": reading(got), "read_at": got.get("read_at"),
        "stock_as_of": got.get("stock_as_of"),
        "window": got.get("window"), "after": got.get("after"),
    }
    if not s["linked_lines"]:
        out["guide"] = coverage.guide(ctx.code)
    return out


def _orders_on_record(ctx) -> bool:
    try:
        return bool(ctx.reader().count("Sales Order", {"docstatus": 1}))
    except Exception:
        return True


def _business(business_code):
    from command_center import coverage
    from command_center.kpi.live_departments import is_down
    try:
        got = coverage.get(business_code)
    except Exception as e:
        if is_down(e):
            return None
        raise
    return got if got.get("kind") == "cover" else None


@frappe.whitelist()
def summary(business_code: str | None = None, late_only=0):
    """The promise split by what covers it -- for "Promised, not delivered" and "Past the
    promised date" (late_only: lines whose delivery date has passed)."""
    require_manager()
    from command_center import coverage
    got = _business(business_code)
    if got is None:
        return {"kind": "unreachable"}
    lines = got["lines"]
    if frappe.utils.cint(late_only):
        lines = [l for l in lines if l["late_to_customer"]]
    s = coverage.summarise(lines)
    return {"kind": "cover", "currency": got.get("currency") or "", "summary": s,
            "note": reading({**got, "summary": s}), "read_at": got.get("read_at"),
            "late_only": bool(frappe.utils.cint(late_only))}


@frappe.whitelist()
def lines(business_code: str | None = None, state: str = "all", start=0, limit=PER_STATE):
    """More rows for the panel's table: one state ("needs" for Not Ordered and Partly
    Covered, "all" for every one), ranked as the panel ranks them."""
    require_manager()
    from command_center import coverage
    got = _business(business_code)
    if got is None:
        return {"kind": "unreachable"}
    rows = _ranked(got["lines"])
    if state == "needs":
        rows = [l for l in rows if l["state"] in coverage.NEEDS_ACTION]
    elif state in coverage.STATE:
        rows = [l for l in rows if l["state"] == state]
    elif state != "all":
        frappe.throw(f"Unknown state {state!r}.")
    start = max(0, frappe.utils.cint(start))
    limit = min(MAX_PAGE, max(1, frappe.utils.cint(limit) or PER_STATE))
    return {"kind": "cover", "rows": _rows(rows[start:start + limit]), "total": len(rows),
            "start": start}
