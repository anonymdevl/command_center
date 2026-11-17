"""Stock Balance and Stock Movements, the two record tabs on Stock & Warehouses.

    balance(business_code, q, warehouse, page)
        one row per item and warehouse from the loaded Bin (fact_stock_balance): quantity,
        valuation rate and value, searched by item, filtered by warehouse, a page at a
        time, with the totals of everything the search and filter match
    movements(business_code, q, warehouse, from_date, to_date, before, skip)
        the Stock Ledger Entry, newest first, read live from the business's ERPNext a
        page at a time over a date range (cancelled entries left out)
    balance_xlsx / movements_xlsx
        the same rows as an Excel workbook (api/export.py), every row the filters match
        (the ledger up to MOVEMENTS_EXPORT_CAP)

Fields read, all present on ERPNext v14, v15 and v16:
    Bin (through the fact)  item_code, warehouse, stock_uom, actual_qty, valuation_rate,
                            stock_value
    Stock Ledger Entry      name, posting_date, posting_time, item_code, warehouse,
                            actual_qty, qty_after_transaction, voucher_type, voucher_no,
                            is_cancelled (filter only)
    Item                    name, item_name

Items are shown by name, with the code beside it where the two differ. A line holding no
quantity and no value is not listed: Bin keeps one for every item a warehouse ever
touched.

The ledger is paged by position within a date, never by reading it whole: each page asks
for the entries on or before the last date already shown and leaves out the ones of that
date already shown (`before`, `skip`), so a page costs one request however far back the
range goes.
"""

from __future__ import annotations

import datetime as dt

import frappe

from command_center.api.businesses import require_manager

BALANCE_PAGE = 50
MOVEMENTS_PAGE = 100
MOVEMENTS_EXPORT_CAP = 5000
DEFAULT_DAYS = 30
NAMES_SECONDS = 900
# Newest first, as ERPNext's own Stock Ledger report; name last, so the order is total.
LEDGER_ORDER = "posting_date desc, posting_time desc, creation desc, name desc"
LEDGER_FIELDS = ["name", "posting_date", "posting_time", "item_code", "warehouse",
                 "actual_qty", "qty_after_transaction", "voucher_type", "voucher_no"]
BALANCE_FIELDS = ["item_code", "warehouse", "stock_uom", "actual_qty", "valuation_rate",
                  "stock_value"]


# --------------------------------------------------------------------------- the API
@frappe.whitelist()
def balance(business_code: str | None = None, q: str | None = None,
            warehouse: str | None = None, page: int | str = 1) -> dict:
    """One row per item and warehouse, searched and filtered, a page at a time."""
    require_manager(business_code)
    ctx = _ctx(business_code)
    try:
        rows, warehouses = _balance_rows(ctx, q, warehouse)
    except Exception as e:
        from command_center.api.people import _failed
        return _failed(ctx, e)
    size = BALANCE_PAGE
    pages = max(1, -(-len(rows) // size))
    page = min(max(1, frappe.utils.cint(page) or 1), pages)
    return {"kind": "stock_balance", "business_code": ctx.code,
            "currency": _currency(ctx.code), "warehouses": warehouses,
            "rows": rows[(page - 1) * size:page * size], "page": page, "pages": pages,
            "totals": _totals(rows), "as_of": ctx.business().get("last_loaded")}


@frappe.whitelist()
def movements(business_code: str | None = None, q: str | None = None,
              warehouse: str | None = None, from_date: str | None = None,
              to_date: str | None = None, before: str | None = None,
              skip: int | str = 0) -> dict:
    """The stock ledger, newest first, one page; `next` asks for the page after it."""
    require_manager(business_code)
    ctx = _ctx(business_code)
    start, end = _range(from_date, to_date)
    filters = _ledger_filters(ctx, q, warehouse, start, end)
    cursor = _cursor(before, skip, start, end)
    try:
        rows, nxt = _ledger_page(ctx, filters, cursor, MOVEMENTS_PAGE)
        total = ctx.r.count("Stock Ledger Entry", filters) if not cursor["skip"] and \
            cursor["before"] == str(end) else None
        names = _names(ctx, {r["item_code"] for r in rows})
    except Exception as e:
        from command_center.api.people import _failed
        return _failed(ctx, e)
    return {"kind": "stock_movements", "business_code": ctx.code,
            "from_date": str(start), "to_date": str(end), "warehouses": _warehouses(ctx=ctx),
            "rows": [_movement(r, names) for r in rows], "next": nxt, "total": total}


@frappe.whitelist()
def balance_xlsx(business_code: str | None = None, q: str | None = None,
                 warehouse: str | None = None):
    """Every row the search and filter match, with the totals, as an Excel workbook."""
    require_manager(business_code)
    from command_center.api.export import _send_xlsx
    ctx = _ctx(business_code)
    rows, _ = _balance_rows(ctx, q, warehouse)
    cur = _currency(ctx.code)
    head = ["Item", "Item Code", "Warehouse", "Quantity", "Unit", "Valuation Rate",
            f"Value {cur}".strip()]
    body = [[r["item_name"], r["item_code"], r["warehouse"], r["qty"], r["uom"] or "",
             r["valuation_rate"], r["value"]] for r in rows]
    t = _totals(rows)
    body.append([f"Total ({t['lines']:,} lines)", "", "", t["qty"] if t["qty"] is not None
                 else "", t["uom"] or "", "", t["value"]])
    _send_xlsx("Stock Balance", [("Stock Balance", head, body)], ctx.code,
               note=_filter_note(q, warehouse))


@frappe.whitelist()
def movements_xlsx(business_code: str | None = None, q: str | None = None,
                   warehouse: str | None = None, from_date: str | None = None,
                   to_date: str | None = None):
    """The ledger over the range, newest first, up to MOVEMENTS_EXPORT_CAP entries."""
    require_manager(business_code)
    from command_center.api.export import _send_xlsx
    ctx = _ctx(business_code)
    start, end = _range(from_date, to_date)
    filters = _ledger_filters(ctx, q, warehouse, start, end)
    rows, _ = _ledger_page(ctx, filters, _cursor(None, 0, start, end), MOVEMENTS_EXPORT_CAP)
    names = _names(ctx, {r["item_code"] for r in rows})
    head = ["Date", "Item", "Item Code", "Warehouse", "In", "Out", "Balance After",
            "Voucher Type", "Voucher No"]
    body = []
    for r in map(lambda x: _movement(x, names), rows):
        body.append([r["date"], r["item_name"], r["item_code"], r["warehouse"],
                     r["in_qty"] or "", r["out_qty"] or "", r["balance_qty"],
                     r["voucher_type"], r["voucher_no"]])
    note = f"{_pretty(start)} to {_pretty(end)}"
    if len(rows) >= MOVEMENTS_EXPORT_CAP:
        note += f" · the newest {MOVEMENTS_EXPORT_CAP:,} entries"
    extra = _filter_note(q, warehouse)
    _send_xlsx("Stock Movements", [("Stock Movements", head, body)], ctx.code,
               note=f"{note} · {extra}" if extra else note)


# --------------------------------------------------------------------------- balance
def _ctx(business_code):
    from command_center.api.people import _Ctx
    return _Ctx(business_code)


def _currency(code) -> str:
    from command_center.api.businesses import currency_for
    return currency_for(code) or ""


def _balance_rows(ctx, q, warehouse):
    """The fact's lines for the business, named, searched, filtered and ranked by value
    (largest first); and every warehouse the business keeps stock lines in."""
    from command_center.kpi.live_departments import facts
    lines = facts(ctx.r, "fact_stock_balance", {}, BALANCE_FIELDS)
    warehouses = _warehouses(lines)
    held = [x for x in lines if _num(x.get("actual_qty")) or _num(x.get("stock_value"))]
    names = _names(ctx, {x.get("item_code") for x in held})
    rows = [{"item_code": x.get("item_code") or "",
             "item_name": names.get(x.get("item_code")) or x.get("item_code") or "",
             "warehouse": x.get("warehouse") or "", "uom": x.get("stock_uom") or "",
             "qty": _num(x.get("actual_qty")), "valuation_rate": _num(x.get("valuation_rate")),
             "value": round(_num(x.get("stock_value")), 2)} for x in held]
    if warehouse:
        rows = [r for r in rows if r["warehouse"] == warehouse]
    words = (q or "").lower().split()
    if words:
        rows = [r for r in rows
                if all(w in f"{r['item_name']} {r['item_code']}".lower() for w in words)]
    rows.sort(key=lambda r: (-r["value"], r["item_name"].lower(), r["warehouse"]))
    return rows, warehouses


def _warehouses(lines=None, ctx=None) -> list:
    """Every warehouse the business keeps a stock line in (Bin has one for each warehouse
    an item ever moved through)."""
    if lines is None:
        from command_center.kpi.live_departments import facts
        lines = facts(ctx.r, "fact_stock_balance", {}, ["warehouse"])
    return sorted({x.get("warehouse") for x in lines if x.get("warehouse")})


def _totals(rows) -> dict:
    """Lines and value; a quantity only where every line is in the same unit (adding
    boxes to litres is not a quantity)."""
    units = {r["uom"] for r in rows}
    one = len(units) == 1
    return {"lines": len(rows), "value": round(sum(r["value"] for r in rows), 2),
            "qty": round(sum(r["qty"] for r in rows), 6) if one and rows else None,
            "uom": next(iter(units)) if one and rows else None}


def _names(ctx, codes) -> dict:
    """Item name by item code, kept per business for NAMES_SECONDS. A code the business's
    ERPNext could not be asked about (it is away) is shown by its code."""
    from command_center.kpi.live_departments import chunks
    codes = {c for c in codes if c}
    key = f"cc:stock:names:{ctx.code}"
    cache = frappe.cache()
    known = cache.get_value(key) or {}
    missing = sorted(codes - set(known))
    if missing:
        try:
            for part in chunks(missing, 300):
                for d in ctx.read("Item", {"name": ["in", part]}, ["name", "item_name"],
                                  limit=len(part)):
                    known[d["name"]] = d.get("item_name") or d["name"]
        except Exception as e:
            from command_center.kpi.live_departments import is_down
            if not is_down(e):
                raise
            return known
        for c in missing:
            known.setdefault(c, c)
        cache.set_value(key, known, expires_in_sec=NAMES_SECONDS)
    return known


# --------------------------------------------------------------------------- the ledger
def _range(from_date, to_date):
    """The date range asked for; the last DEFAULT_DAYS days to today when none is."""
    today = frappe.utils.getdate(frappe.utils.today())
    end = _date(to_date) or today
    start = _date(from_date) or end - dt.timedelta(days=DEFAULT_DAYS)
    return (start, end) if start <= end else (end, start)


def _date(v):
    if not v:
        return None
    try:
        return frappe.utils.getdate(str(v)[:10])
    except Exception:
        frappe.throw(f"{str(v)[:20]!r} is not a date.")


def _ledger_filters(ctx, q, warehouse, start, end):
    """The ledger's filters. A search matching an item asks for its entries, otherwise
    for vouchers whose number holds it. A warehouse must be one the business keeps
    stock in."""
    filters = [["is_cancelled", "=", 0], ["posting_date", ">=", str(start)],
               ["posting_date", "<=", str(end)]]
    if warehouse:
        if warehouse not in _warehouses(ctx=ctx):
            frappe.throw("That warehouse is not one of this business's.")
        filters.append(["warehouse", "=", warehouse])
    words = (q or "").lower().split()
    if words:
        from command_center.kpi.live_departments import facts
        codes = {x.get("item_code") for x in facts(ctx.r, "fact_stock_balance", {},
                                                     ["item_code"]) if x.get("item_code")}
        names = _names(ctx, codes)
        hits = sorted(c for c in codes
                      if all(w in f"{names.get(c) or ''} {c}".lower() for w in words))
        if hits:
            filters.append(["item_code", "in", hits[:500]])
        else:
            # No item answers to it: a voucher number, then.
            filters.append(["voucher_no", "like", f"%{q.strip()}%"])
    return filters


def _cursor(before, skip, start, end) -> dict:
    day = _date(before) or end
    day = min(max(day, start), end)
    return {"before": str(day), "skip": max(0, frappe.utils.cint(skip))}


def _ledger_page(ctx, filters, cursor, size):
    """`size` entries on or before cursor["before"], after the first cursor["skip"] of that
    date already shown; and the cursor for the page after, or None at the end."""
    skip = cursor["skip"]
    asked = [f for f in filters if not (f[0] == "posting_date" and f[1] == "<=")]
    asked.append(["posting_date", "<=", cursor["before"]])
    got = ctx.read("Stock Ledger Entry", asked, LEDGER_FIELDS, limit=skip + size + 1,
                   order_by=LEDGER_ORDER)
    rows = got[skip:skip + size]
    if len(got) <= skip + size or not rows:
        return rows, None
    last = str(rows[-1].get("posting_date"))[:10]
    seen = sum(1 for r in got[:skip + size] if str(r.get("posting_date"))[:10] == last)
    return rows, {"before": last, "skip": seen}


def _movement(r, names) -> dict:
    q = _num(r.get("actual_qty"))
    code = r.get("item_code") or ""
    return {"id": r.get("name"), "date": str(r.get("posting_date") or "")[:10],
            "time": str(r.get("posting_time") or "")[:5],
            "item_code": code, "item_name": names.get(code) or code,
            "warehouse": r.get("warehouse") or "",
            "in_qty": q if q > 0 else 0, "out_qty": -q if q < 0 else 0,
            "balance_qty": _num(r.get("qty_after_transaction")),
            "voucher_type": r.get("voucher_type") or "", "voucher_no": r.get("voucher_no") or ""}


# --------------------------------------------------------------------------- small
def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _pretty(d) -> str:
    d = frappe.utils.getdate(d)
    return f"{d.day} {d:%b %Y}"


def _filter_note(q, warehouse) -> str:
    bits = []
    if warehouse:
        bits.append(f"warehouse {warehouse}")
    if (q or "").strip():
        bits.append(f"search \"{q.strip()[:60]}\"")
    return " · ".join(bits)
