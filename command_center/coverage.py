"""What covers each line promised to a customer and not yet delivered.

"Promised, not delivered" (the order_book figure) read on its own as stock promised and
not there. Most of it is not: the goods are on the shelf, on their way from a supplier,
or already received and waiting to go out. This module says, line by line, which -- and
leaves alarming only what nothing covers.

For every open sales-order line (a submitted order not completed or closed, with
quantity still to deliver), in stock units:

  1. Received for it.   A purchase order linked to the line (below) whose goods have been
                        received, and are still in stock: ready to deliver.
  2. In stock.          What its own warehouse holds, then any other warehouse goods are
                        sold from (to be moved first). Stock is shared out oldest promise
                        first, so two orders never count the same units.
  3. On order, linked.  Purchase Order Item rows that name the line (sales_order_item,
                        or sales_order and the same item), and those raised from a
                        Material Request that names it (material_request_item).
  4. Requested.         A Material Request (Purchase) that names the line and is not yet
                        ordered in full.
  5. On order, likely.  Open purchase-order lines for the same item, linked to no order,
                        raised from `before` days before the order date to `after` days
                        after it (14 and 90 unless Settings say otherwise: a purchase order
                        raised a year after an order was not raised for it). Each one's
                        open quantity is shared out oldest promise first,
                        so one purchase order is never counted twice. Said with its reason:
                        "same item, raised 2 days after the order, 50 on order".
  6. Requested, likely. Open purchase Material Requests for the same item on the same
                        terms.

What is left is missing. Each line is then in one state:

  in_stock      can be delivered from stock now
  received      received against its own purchase order, ready to deliver
  on_order      everything not in stock is on order (expected date; supplier late when
                the order is past the date asked for)
  requested     the rest is asked of buying, not yet ordered
  partly        something covers it, and some is still missing
  not_ordered   nothing covers it: needs action
  non_stock     a service or other item not kept in stock, with nothing ordered for it

and carries "late to customer" when its delivery date has passed, and "likely" when the
cover is inferred rather than linked. Each line also gets the chain -- purchase order,
goods receipts, supplier invoices -- with dates, and a sentence: "ST JOHN ordered 60 on
3 Nov 2025; 20 can go from stock in Main Store. 40 on order from ACME on PO-00412 (5 Nov
2025), expected 22 Nov 2025."

Reads, all through the business's connector with filters always applied and paged;
sums and counts only where grouped (v14 refuses min()/max() in a list read): open sales
orders and their lines, the items not kept in stock, warehouses, purchase-order and
material-request lines linked to those orders, the open purchase orders and purchase
requests, and the receipts and invoices against the purchase orders found. Stock is the
loaded stock position (fact_stock_balance, read from Bin), as the Stock screen shows it.
No pay, no ledger. The answer is kept per business (speed.py, kind "cover").

Importing this module touches no frappe.
"""

from __future__ import annotations

from collections import defaultdict

CLOSED_ORDER = ("Completed", "Closed", "Cancelled")
# A purchase order or request that will bring nothing more.
CLOSED_PO = ("Completed", "Closed", "Cancelled", "Delivered")
CLOSED_MR = ("Stopped", "Cancelled", "Ordered", "Received", "Transferred", "Issued",
             "Manufactured")
WINDOW_DAYS = 14      # a likely purchase order may be raised this long before the order
AFTER_DAYS = 90       # ... and this long after it
STALE_DAYS = 365      # promised this long ago and still open: worth asking if it stands
RULE_ID = "promised_not_ordered"   # recommend/rules.py: its params are the setting

# key, label, tone (a token colour), tag class, rank (most in need of action first)
STATES = (
    ("not_ordered", "Not Ordered", "crit", "t-od"),
    ("partly", "Partly Covered", "high", "t-wt"),
    ("requested", "Requested, Not Yet Ordered", "med", "t-rq"),
    ("on_order", "On Order", "accent", "t-oo"),
    ("received", "Received – Ready to Deliver", "ok", "t-ok"),
    ("in_stock", "In Stock", "ok", "t-ok"),
    ("non_stock", "Not a Stock Item", "dim", "t-dr"),
)
STATE = {k: {"key": k, "label": l, "tone": t, "tag": g, "rank": i}
         for i, (k, l, t, g) in enumerate(STATES)}
NEEDS_ACTION = ("not_ordered", "partly")
# The parts of the value promised, split by what covers each unit (they add up to it).
PARTS = (("stock", "Can go from stock"), ("received", "Received, ready to deliver"),
         ("linked", "On order (linked)"), ("likely", "On order (likely)"),
         ("requested", "Requested from buying"), ("missing", "Not ordered"),
         ("non_stock", "Not a stock item"))

SO_FIELDS = ["name", "customer", "customer_name", "transaction_date", "delivery_date",
             "status", "base_grand_total", "base_net_total", "per_delivered"]
SO_LINE_FIELDS = ["parent", "name", "idx", "item_code", "item_name", "warehouse", "qty",
                  "delivered_qty", "conversion_factor", "stock_uom", "base_net_rate",
                  "delivery_date", "delivered_by_supplier"]
PO_FIELDS = ["name", "supplier", "transaction_date", "schedule_date", "status",
             "per_received"]
PO_LINE_FIELDS = ["parent", "name", "item_code", "warehouse", "qty", "received_qty",
                  "conversion_factor", "schedule_date", "sales_order", "sales_order_item",
                  "material_request", "material_request_item"]
PO_LINE_OPTIONAL = ["expected_delivery_date"]
MR_FIELDS = ["name", "transaction_date", "schedule_date", "status", "material_request_type"]
MR_LINE_FIELDS = ["parent", "name", "item_code", "warehouse", "stock_qty", "ordered_qty",
                  "schedule_date", "sales_order", "sales_order_item"]
PR_LINE_FIELDS = ["parent", "name", "purchase_order", "purchase_order_item", "stock_qty"]
PI_LINE_FIELDS = ["parent", "name", "purchase_order", "po_detail", "stock_qty"]


# --------------------------------------------------------------------------- small helpers
def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _d(v):
    """A date from what ERPNext sends ("2025-11-03" or a date), or None."""
    import datetime as dt
    if not v:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def qty(v) -> str:
    v = round(_num(v), 3)
    return f"{v:,.0f}" if v == int(v) else f"{v:,.3f}".rstrip("0").rstrip(".")


def day(v) -> str:
    v = _d(v)
    return f"{v.day} {v.strftime('%b %Y')}" if v else ""


def _days(n: int) -> str:
    return f"{n} day{'s' if n != 1 else ''}"


def _chunks(seq, n=200):
    seq = sorted(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# --------------------------------------------------------------------------- reading
def _read(r, doctype, filters, fields, optional=(), **kw):
    """One guarded read (kpi/live._read: a reply that lost a column is refused). Fields
    in `optional` are asked for too; a version that refuses them is asked again without
    them, and they come back empty."""
    from command_center.kpi.live import _read as read
    from command_center.kpi.live_departments import is_down
    if optional:
        try:
            return read(r, doctype, filters, list(fields) + list(optional), **kw)
        except Exception as e:
            if is_down(e):
                raise
    rows = read(r, doctype, filters, list(fields), **kw)
    for row in rows:
        for f in optional:
            row.setdefault(f, None)
    return rows


def _children(r, doctype, parent, key, names, fields, extra=None, optional=()):
    out = []
    for part in _chunks(names):
        out += _read(r, doctype, {key: ["in", part], **(extra or {})}, fields,
                     optional=optional, parent=parent, limit=100000)
    return out


def gather(r) -> dict:
    """Everything the coverage needs, read from the business (r: kpi/live._Reader, or
    the screen's guarded one). Plain rows, so work_out() can be run on anything."""
    from command_center.kpi.live_departments import NOT_FOR_SALE, facts, off_warehouses, is_down
    orders = _read(r, "Sales Order", {"docstatus": 1, "status": ["not in", list(CLOSED_ORDER)],
                                      "per_delivered": ["<", 100]}, SO_FIELDS, limit=500000)
    names = {o["name"] for o in orders}
    lines = _children(r, "Sales Order Item", "Sales Order", "parent", names, SO_LINE_FIELDS,
                      extra={"docstatus": 1}) if names else []
    lines = [x for x in lines if _num(x.get("qty")) - _num(x.get("delivered_qty")) > 1e-9]
    items = {x.get("item_code") for x in lines if x.get("item_code")}
    non_stock = set()
    for part in _chunks(items):
        non_stock |= {i["name"] for i in _read(r, "Item", {"name": ["in", part],
                                                         "is_stock_item": 0}, ["name"])}
    stock = defaultdict(float)
    for b in facts(r, "fact_stock_balance", {"actual_qty": [">", 0]},
                   ["item_code", "warehouse", "actual_qty"]):
        if b["item_code"] in items:
            stock[(b["item_code"], b["warehouse"])] += _num(b["actual_qty"])
    try:
        off, _ = off_warehouses(r)
    except Exception as e:
        if is_down(e):
            raise
        off = set()   # cannot tell which are switched off: the names still say
    import re
    odd = re.compile(NOT_FOR_SALE, re.I)
    off = set(off) | {wh for _, wh in stock if odd.search(wh or "")}

    # Purchase-order and request lines that name these orders.
    open_names = sorted({x["parent"] for x in lines})
    po_lines = _children(r, "Purchase Order Item", "Purchase Order", "sales_order", open_names,
                         PO_LINE_FIELDS, extra={"docstatus": 1}, optional=PO_LINE_OPTIONAL)
    mr_lines = _children(r, "Material Request Item", "Material Request", "sales_order",
                         open_names, MR_LINE_FIELDS, extra={"docstatus": 1})
    linked_mrs = {x["parent"] for x in mr_lines}
    seen = {x["name"] for x in po_lines}
    po_lines += [x for x in _children(r, "Purchase Order Item", "Purchase Order",
                                      "material_request", linked_mrs, PO_LINE_FIELDS,
                                      extra={"docstatus": 1}, optional=PO_LINE_OPTIONAL)
                 if x["name"] not in seen]
    # Open purchase orders and purchase requests, for what is likely to cover the rest.
    open_pos = _read(r, "Purchase Order", {"docstatus": 1, "status": ["not in", list(CLOSED_PO) + ["On Hold"]],
                                           "per_received": ["<", 100]}, PO_FIELDS, limit=100000)
    seen = {x["name"] for x in po_lines}
    po_lines += [x for x in _children(r, "Purchase Order Item", "Purchase Order", "parent",
                                      {p["name"] for p in open_pos}, PO_LINE_FIELDS,
                                      extra={"docstatus": 1}, optional=PO_LINE_OPTIONAL)
                 if x["name"] not in seen and x.get("item_code") in items]
    pos = {p["name"]: p for p in open_pos}
    missing = {x["parent"] for x in po_lines} - set(pos)
    for part in _chunks(missing):
        pos.update({p["name"]: p for p in _read(r, "Purchase Order", {"name": ["in", part]},
                                                PO_FIELDS, limit=100000)})
    open_mrs = _read(r, "Material Request", {"docstatus": 1, "material_request_type": "Purchase",
                                             "status": ["not in", list(CLOSED_MR)]},
                     MR_FIELDS, limit=100000)
    seen = {x["name"] for x in mr_lines}
    mr_lines += [x for x in _children(r, "Material Request Item", "Material Request", "parent",
                                      {m["name"] for m in open_mrs}, MR_LINE_FIELDS,
                                      extra={"docstatus": 1})
                 if x["name"] not in seen and x.get("item_code") in items]
    mrs = {m["name"]: m for m in open_mrs}
    missing = ({x["parent"] for x in mr_lines} | {x.get("material_request") for x in po_lines
                                                  if x.get("material_request")}) - set(mrs)
    for part in _chunks(missing):
        mrs.update({m["name"]: m for m in _read(r, "Material Request", {"name": ["in", part]},
                                                MR_FIELDS, limit=100000)})
    # What has been received and billed against those purchase orders.
    po_names = {x["parent"] for x in po_lines}
    receipts = _children(r, "Purchase Receipt Item", "Purchase Receipt", "purchase_order",
                         po_names, PR_LINE_FIELDS, extra={"docstatus": 1})
    invoices = _children(r, "Purchase Invoice Item", "Purchase Invoice", "purchase_order",
                         po_names, PI_LINE_FIELDS, extra={"docstatus": 1})
    # A supplier invoice with Update Stock ticked receives the goods itself (some
    # businesses never raise a Purchase Receipt).
    heads = {}
    for doctype, rows, fields in (("Purchase Receipt", receipts, ["name", "posting_date"]),
                                  ("Purchase Invoice", invoices,
                                   ["name", "posting_date", "update_stock"])):
        for part in _chunks({x["parent"] for x in rows}):
            for h in _read(r, doctype, {"name": ["in", part]}, fields, limit=100000):
                heads[(doctype, h["name"])] = h
    return {"orders": orders, "lines": lines, "non_stock": non_stock, "stock": dict(stock),
            "off": off, "po_lines": po_lines, "pos": pos, "mr_lines": mr_lines,
            "mrs": mrs, "receipts": receipts, "invoices": invoices, "heads": heads}


# --------------------------------------------------------------------------- working it out
def work_out(data: dict, today, window: int = WINDOW_DAYS, after: int = AFTER_DAYS) -> dict:
    """The coverage of every open line, from gather()'s rows. Pure: no reads."""
    from command_center.ingest import order_lines
    today = _d(today)
    orders = {o["name"]: o for o in data["orders"]}
    stock = defaultdict(float, data.get("stock") or {})
    off = set(data.get("off") or ())
    by_item_wh = defaultdict(list)
    for (item, wh), q in stock.items():
        by_item_wh[item].append(wh)

    # -- the sales-order lines, oldest promise first
    lines = []
    for x in data["lines"]:
        o = orders.get(x["parent"])
        if not o:
            continue
        cf = _num(x.get("conversion_factor")) or 1.0
        left = max(_num(x.get("qty")) - _num(x.get("delivered_qty")), 0.0)
        item = x.get("item_code")
        lines.append({
            "id": x["name"], "order": x["parent"], "idx": int(_num(x.get("idx"))),
            "customer": o.get("customer_name") or o.get("customer") or "",
            "customer_id": o.get("customer") or "",
            "ordered_on": str(_d(o.get("transaction_date")) or ""),
            "deliver_by": str(_d(x.get("delivery_date")) or _d(o.get("delivery_date")) or ""),
            "order_status": o.get("status") or "",
            "item_code": item or "", "item_name": x.get("item_name") or item or "",
            "warehouse": x.get("warehouse") or "", "uom": x.get("stock_uom") or "",
            "ordered": round(_num(x.get("qty")) * cf, 6),
            "delivered": round(_num(x.get("delivered_qty")) * cf, 6),
            "pending": round(left * cf, 6),
            # The one valuation of what is left on a line (ingest/order_lines.py).
            "value": round(order_lines.left_value(x, o, "delivered_qty"), 2),
            "stocked": item not in data.get("non_stock", set()),
            "drop_ship": bool(int(_num(x.get("delivered_by_supplier")))),
            "need": round(left * cf, 6),
            "from_stock": 0.0, "elsewhere": [], "received": 0.0, "covers": [], "requests": [],
        })
    lines.sort(key=lambda l: (l["deliver_by"] or "9999", l["ordered_on"] or "9999", l["order"],
                              l["idx"]))

    # -- purchase-order lines, in stock units, with what is left of each to share out
    pos = data.get("pos") or {}
    po_lines = {}
    for x in data.get("po_lines") or []:
        h = pos.get(x["parent"]) or {}
        cf = _num(x.get("conversion_factor")) or 1.0
        ordered = _num(x.get("qty")) * cf
        recd = _num(x.get("received_qty")) * cf
        status = h.get("status") or ""
        po_lines[x["name"]] = {
            **x, "supplier": h.get("supplier") or "", "raised": str(_d(h.get("transaction_date")) or ""),
            "expected": str(_d(x.get("expected_delivery_date")) or _d(x.get("schedule_date"))
                            or _d(h.get("schedule_date")) or ""),
            "status": status, "on_hold": status == "On Hold",
            "ordered_qty": ordered, "received_qty": recd,
            "open_qty": 0.0 if status in CLOSED_PO else max(ordered - recd, 0.0),
            "recv_left": recd, "open_left": 0.0 if status in CLOSED_PO else max(ordered - recd, 0.0),
        }
    mrs = data.get("mrs") or {}
    mr_lines = {}
    for x in data.get("mr_lines") or []:
        h = mrs.get(x["parent"]) or {}
        open_ = ((h.get("status") or "") not in CLOSED_MR
                 and (h.get("material_request_type") or "Purchase") == "Purchase")
        left = max(_num(x.get("stock_qty")) - _num(x.get("ordered_qty")), 0.0) if open_ else 0.0
        mr_lines[x["name"]] = {**x, "raised": str(_d(h.get("transaction_date")) or ""),
                               "required_by": str(_d(x.get("schedule_date")) or _d(h.get("schedule_date")) or ""),
                               "open_qty": left, "open_left": left}

    # -- what links to what
    by_so_item, by_so_and_item = defaultdict(list), defaultdict(list)
    for p in po_lines.values():
        if p.get("sales_order_item"):
            by_so_item[p["sales_order_item"]].append(p["name"])
        elif p.get("sales_order"):
            by_so_and_item[(p["sales_order"], p.get("item_code"))].append(p["name"])
    mr_by_so_item, mr_by_so_and_item = defaultdict(list), defaultdict(list)
    for m in mr_lines.values():
        if m.get("sales_order_item"):
            mr_by_so_item[m["sales_order_item"]].append(m["name"])
        elif m.get("sales_order"):
            mr_by_so_and_item[(m["sales_order"], m.get("item_code"))].append(m["name"])
    po_by_mr_item, po_by_mr_and_item = defaultdict(list), defaultdict(list)
    for p in po_lines.values():
        if p.get("material_request_item"):
            po_by_mr_item[p["material_request_item"]].append(p["name"])
        elif p.get("material_request"):
            po_by_mr_and_item[(p["material_request"], p.get("item_code"))].append(p["name"])
    claimed_mr = set()   # requests that name an order: never "likely" for another one
    claimed_po = set()   # purchase-order lines that name an order, or come from one's request
    for l in lines:
        mr = list(dict.fromkeys(mr_by_so_item.get(l["id"], []) +
                                mr_by_so_and_item.get((l["order"], l["item_code"]), [])))
        po = by_so_item.get(l["id"], []) + by_so_and_item.get((l["order"], l["item_code"]), [])
        for m in mr:
            mline = mr_lines[m]
            po += po_by_mr_item.get(m, []) + po_by_mr_and_item.get((mline["parent"], l["item_code"]), [])
        l["_po"] = list(dict.fromkeys(po))
        l["_mr"] = mr
    for l in lines:
        claimed_po |= set(l["_po"])
        claimed_mr |= set(l["_mr"])
    claimed_mr |= {m["name"] for m in mr_lines.values() if m.get("sales_order")}
    for p in po_lines.values():
        # Linked to an order -- any order, open or not -- directly or through its request.
        if p.get("sales_order") or p.get("material_request_item") in claimed_mr:
            claimed_po.add(p["name"])

    def cover(l, p, kind, part, n, reason=""):
        c = next((c for c in l["covers"] if c["po_item"] == p["name"]), None)
        if c is None:
            c = {"kind": kind, "po": p["parent"], "po_item": p["name"], "supplier": p["supplier"],
                 "raised": p["raised"], "expected": p["expected"], "status": p["status"],
                 "po_qty": p["ordered_qty"], "po_received": p["received_qty"],
                 "po_open": p["open_qty"], "received": 0.0, "on_order": 0.0, "reason": reason,
                 "request": p.get("material_request") or "", "late": False}
            l["covers"].append(c)
        c[part] += n
        if part == "on_order" and c["expected"] and _d(c["expected"]) < today:
            c["late"] = True

    # 1. received against its own purchase order, while still in stock
    for l in lines:
        for name in l["_po"]:
            p = po_lines[name]
            take = min(l["need"], p["recv_left"])
            if take <= 1e-9:
                continue
            p["recv_left"] -= take
            wh = p.get("warehouse") if stock.get((l["item_code"], p.get("warehouse")), 0) > 0 \
                else l["warehouse"]
            take = min(take, stock.get((l["item_code"], wh), 0.0)) if l["stocked"] else take
            if take <= 1e-9:
                continue
            if l["stocked"]:
                stock[(l["item_code"], wh)] -= take
            l["need"] -= take
            l["received"] += take
            cover(l, p, "linked", "received", take)
    # 2. stock, its own warehouse first, then wherever else goods are sold from
    for l in lines:
        if not l["stocked"] or l["drop_ship"] or l["need"] <= 1e-9:
            continue
        key = (l["item_code"], l["warehouse"])
        take = min(l["need"], stock.get(key, 0.0))
        if take > 1e-9:
            stock[key] -= take
            l["need"] -= take
            l["from_stock"] += take
        for wh in sorted(by_item_wh.get(l["item_code"], []),
                         key=lambda w: -stock.get((l["item_code"], w), 0.0)):
            if l["need"] <= 1e-9:
                break
            if wh == l["warehouse"] or wh in off:
                continue
            take = min(l["need"], stock.get((l["item_code"], wh), 0.0))
            if take > 1e-9:
                stock[(l["item_code"], wh)] -= take
                l["need"] -= take
                l["elsewhere"].append({"warehouse": wh, "qty": take})
    # 3. on order against the line's own purchase orders
    for l in lines:
        for name in l["_po"]:
            p = po_lines[name]
            take = min(l["need"], p["open_left"])
            if take > 1e-9:
                p["open_left"] -= take
                l["need"] -= take
                cover(l, p, "linked", "on_order", take)
    # 4. requested from buying, against its own requests
    for l in lines:
        for name in l["_mr"]:
            m = mr_lines[name]
            take = min(l["need"], m["open_left"])
            if take > 1e-9:
                m["open_left"] -= take
                l["need"] -= take
                l["requests"].append(_request(m, "linked", take))
    # 5. likely: open purchase orders for the same item, linked to no order
    candidates = defaultdict(list)
    for p in po_lines.values():
        if p["name"] in claimed_po or p["on_hold"] or p["open_left"] <= 1e-9:
            continue
        candidates[p.get("item_code")].append(p)
    for ps in candidates.values():
        ps.sort(key=lambda p: (p["raised"] or "9999", p["parent"], p["name"]))
    for l in lines:
        if l["need"] <= 1e-9:
            continue
        so_day = _d(l["ordered_on"])
        for p in candidates.get(l["item_code"], []):
            if l["need"] <= 1e-9:
                break
            raised = _d(p["raised"])
            if not _in_window(so_day, raised, window, after):
                continue
            take = min(l["need"], p["open_left"])
            if take <= 1e-9:
                continue
            shared = p["open_qty"] - p["open_left"]
            p["open_left"] -= take
            l["need"] -= take
            cover(l, p, "likely", "on_order", take, _reason(so_day, raised, p["open_qty"], shared,
                                                             l["uom"]))
    # 6. likely: open purchase requests for the same item, naming no order
    reqs = defaultdict(list)
    for m in mr_lines.values():
        if m["name"] not in claimed_mr and m["open_left"] > 1e-9:
            reqs[m.get("item_code")].append(m)
    for ms in reqs.values():
        ms.sort(key=lambda m: (m["raised"] or "9999", m["parent"]))
    for l in lines:
        so_day = _d(l["ordered_on"])
        for m in reqs.get(l["item_code"], []):
            if l["need"] <= 1e-9:
                break
            raised = _d(m["raised"])
            if not _in_window(so_day, raised, window, after):
                continue
            take = min(l["need"], m["open_left"])
            if take > 1e-9:
                m["open_left"] -= take
                l["need"] -= take
                l["requests"].append(_request(m, "likely", take, _reason(
                    so_day, raised, m["open_qty"], 0, l["uom"], "requested")))

    # -- the chain behind each purchase order line: receipts and invoices
    heads = data.get("heads") or {}
    got_pr, got_pi = defaultdict(list), defaultdict(list)
    for x in data.get("receipts") or []:
        h = heads.get(("Purchase Receipt", x["parent"])) or {}
        got_pr[x.get("purchase_order_item")].append(
            {"name": x["parent"], "date": str(_d(h.get("posting_date")) or ""),
             "qty": _num(x.get("stock_qty"))})
    for x in data.get("invoices") or []:
        h = heads.get(("Purchase Invoice", x["parent"])) or {}
        got_pi[x.get("po_detail")].append(
            {"name": x["parent"], "date": str(_d(h.get("posting_date")) or ""),
             "qty": _num(x.get("stock_qty")),
             "received_on_it": bool(int(_num(h.get("update_stock"))))})

    out = []
    for l in lines:
        for c in l["covers"]:
            c["receipts"] = sorted(got_pr.get(c["po_item"], []), key=lambda r: r["date"])
            c["invoices"] = sorted(got_pi.get(c["po_item"], []), key=lambda r: r["date"])
        out.append(_finish(l, today))
    return {"lines": out, "summary": summarise(out), "today": str(today),
            "window": int(window), "after": int(after)}


def _in_window(so_day, raised, before, after) -> bool:
    if not (so_day and raised):
        return False
    gap = (raised - so_day).days
    return -int(before) <= gap <= int(after)


def _request(m, kind, n, reason="") -> dict:
    return {"kind": kind, "request": m["parent"], "request_item": m["name"],
            "raised": m["raised"], "required_by": m["required_by"], "qty": n,
            "open": m["open_qty"], "reason": reason}


def _reason(so_day, raised, open_qty, shared, uom, verb="on order") -> str:
    if so_day and raised:
        gap = (raised - so_day).days
        when = ("raised the same day as the order" if gap == 0 else
                f"raised {_days(gap)} after the order" if gap > 0 else
                f"raised {_days(-gap)} before the order")
    else:
        when = "no date to compare"
    unit = f" {uom}" if uom else ""
    text = f"Same item, {when}, {qty(open_qty)}{unit} {verb}"
    if shared > 1e-9:
        text += f" ({qty(shared)} of them counted for earlier orders)"
    return text


def _finish(l, today) -> dict:
    stock_here = l["from_stock"] + sum(e["qty"] for e in l["elsewhere"])
    on_linked = sum(c["on_order"] for c in l["covers"] if c["kind"] == "linked")
    on_likely = sum(c["on_order"] for c in l["covers"] if c["kind"] == "likely")
    requested = sum(r["qty"] for r in l["requests"])
    missing = max(l["need"], 0.0)
    covered = stock_here + l["received"] + on_linked + on_likely + requested
    if missing <= 1e-9:
        missing = 0.0
        state = ("on_order" if on_linked + on_likely > 1e-9 else
                 "requested" if requested > 1e-9 else
                 "received" if l["received"] > 1e-9 else "in_stock")
    elif covered > 1e-9:
        state = "partly"
    elif not l["stocked"] and not l["drop_ship"]:
        state = "non_stock"
    else:
        state = "not_ordered"
    due = _d(l["deliver_by"])
    days_late = (today - due).days if due and due < today else 0
    linked = any(c["kind"] == "linked" for c in l["covers"]) or any(
        r["kind"] == "linked" for r in l["requests"])
    likely = any(c["kind"] == "likely" for c in l["covers"]) or any(
        r["kind"] == "likely" for r in l["requests"])
    per = l["value"] / l["pending"] if l["pending"] > 0 else 0.0
    parts = {"stock": stock_here * per, "received": l["received"] * per,
             "linked": on_linked * per, "likely": on_likely * per,
             "requested": requested * per,
             "missing": 0.0 if state == "non_stock" else missing * per,
             "non_stock": missing * per if state == "non_stock" else 0.0}
    row = {k: v for k, v in l.items() if not k.startswith("_") and k != "need"}
    row.update({
        "state": state, "state_label": STATE[state]["label"],
        "in_stock": stock_here, "on_order": on_linked + on_likely, "requested": requested,
        "missing": missing, "basis": "linked" if linked else "likely" if likely else "",
        "late_to_customer": days_late > 0, "days_late": days_late,
        "supplier_late": any(c["late"] for c in l["covers"]),
        "parts": {k: round(v, 2) for k, v in parts.items()},
    })
    row["narrative"] = narrative(row)
    return row


def narrative(l) -> str:
    """The line in words, as a manager would say it."""
    unit = f" {l['uom']}" if l.get("uom") else ""
    s = f"{l['customer']} ordered {qty(l['ordered'])}{unit} of {l['item_name']}"
    if l.get("ordered_on"):
        s += f" on {day(l['ordered_on'])}"
    if l.get("delivered"):
        s += f"; {qty(l['delivered'])} delivered, {qty(l['pending'])} still to deliver"
    s += "."
    bits = []
    if l["from_stock"] > 1e-9:
        bits.append(f"{qty(l['from_stock'])} can go from stock in {l['warehouse']}.")
    for e in l["elsewhere"]:
        bits.append(f"{qty(e['qty'])} {'is' if e['qty'] == 1 else 'are'} held in {e['warehouse']} "
                    f"and must be moved first.")
    for c in l["covers"]:
        if c["received"] > 1e-9:
            got = ([x for x in c.get("receipts") or []] +
                   [x for x in c.get("invoices") or [] if x.get("received_on_it")])
            got = max(got, key=lambda x: x["date"]) if got else None
            bits.append(f"{qty(c['received'])} received against {c['po']} from {c['supplier']}"
                        + (f" on {got['name']} ({day(got['date'])})" if got else "")
                        + ", ready to deliver.")
        if c["on_order"] > 1e-9:
            t = (f"{qty(c['on_order'])} on order from {c['supplier']} on {c['po']}"
                 + (f" ({day(c['raised'])})" if c["raised"] else ""))
            if c["expected"]:
                t += (f", expected {day(c['expected'])}" if not c["late"] else
                      f", due {day(c['expected'])} and not yet received")
            t += "."
            if c["kind"] == "likely":
                t += f" Likely, not linked: {c['reason'][0].lower()}{c['reason'][1:]}."
            bits.append(t)
    for r in l["requests"]:
        t = (f"{qty(r['qty'])} requested from buying on {r['request']}"
             + (f" ({day(r['raised'])})" if r["raised"] else "") + ", not yet ordered.")
        if r["kind"] == "likely":
            t += f" Likely, not linked: {r['reason'][0].lower()}{r['reason'][1:]}."
        bits.append(t)
    if l["missing"] > 1e-9:
        bits.append(f"{qty(l['missing'])} {'is' if l['missing'] == 1 else 'are'} "
                    + ("a service or item not kept in stock, with nothing ordered."
                       if l["state"] == "non_stock" else
                       "not in stock and not on any purchase order or request."))
    if l["days_late"]:
        bits.append(f"Delivery to the customer was due {day(l['deliver_by'])}, "
                    f"{_days(l['days_late'])} ago.")
    return " ".join([s] + bits)


def summarise(lines) -> dict:
    states = {k: {"key": k, "label": STATE[k]["label"], "tone": STATE[k]["tone"],
                  "tag": STATE[k]["tag"], "count": 0, "value": 0.0, "orders": set()}
              for k in STATE}
    parts = {k: 0.0 for k, _ in PARTS}
    late = {"count": 0, "value": 0.0}
    supplier_late = 0
    for l in lines:
        s = states[l["state"]]
        s["count"] += 1
        s["value"] += l["value"]
        s["orders"].add(l["order"])
        for k, v in l["parts"].items():
            parts[k] += v
        if l["late_to_customer"]:
            late["count"] += 1
            late["value"] += l["value"]
        supplier_late += 1 if l["supplier_late"] else 0
    for s in states.values():
        s["orders"] = len(s["orders"])
        s["value"] = round(s["value"], 2)
    stale = [l for l in lines if l["state"] in NEEDS_ACTION and l["days_late"] > STALE_DAYS]
    return {
        "lines": len(lines), "orders": len({l["order"] for l in lines}),
        "value": round(sum(l["value"] for l in lines), 2),
        "states": [states[k] for k, *_ in STATES],
        "parts": [{"key": k, "label": lab, "value": round(parts[k], 2)} for k, lab in PARTS],
        "linked_lines": sum(1 for l in lines if l["basis"] == "linked"),
        "likely_lines": sum(1 for l in lines if l["basis"] == "likely"),
        "late_to_customer": {"count": late["count"], "value": round(late["value"], 2)},
        "supplier_late": supplier_late,
        "needs_action": {"count": sum(states[k]["count"] for k in NEEDS_ACTION),
                         "value": round(sum(states[k]["value"] for k in NEEDS_ACTION), 2)},
        # Of what needs action, promised more than a year ago: orders to confirm or close
        # rather than to buy for.
        "stale": {"count": len(stale), "orders": len({l["order"] for l in stale}),
                  "value": round(sum(l["parts"]["missing"] for l in stale), 2),
                  "days": STALE_DAYS},
    }


# --------------------------------------------------------------------------- the business
def window_for(code) -> tuple:
    """(before, after): the days before and after an order a purchase order may be raised
    and still count as likely cover -- the recommendation rule's settings (Settings ->
    Recommendations, "Promised to customers, not ordered")."""
    try:
        from command_center.recommend.engine import settings
        p = settings(code)["rules"][RULE_ID]["params"]
        return int(p.get("window", WINDOW_DAYS)), int(p.get("after", AFTER_DAYS))
    except Exception:
        return WINDOW_DAYS, AFTER_DAYS


def compute(business_code=None, reader=None) -> dict:
    """The coverage of one business, read now: work_out() plus the links into its ERPNext
    ({"kind": "cover", ...}). A business that does not answer raises, as every live read
    does (kpi/live_departments.is_down tells the callers)."""
    import frappe

    from command_center.api.businesses import currency_for
    from command_center.api.panels import _Guarded
    from command_center.kpi.live import _Reader
    # Guarded as a screen's reads are: once the business has not answered (or is marked
    # unreachable), the rest give up at once instead of each waiting out the retries.
    r = reader or _Guarded(_Reader(business_code))
    code = getattr(r, "code", None) or business_code
    data = gather(r)
    got = work_out(data, frappe.utils.today(), *window_for(code))
    site = "" if getattr(r, "local", True) else (getattr(r.conn, "base_url", "") or "")
    links(got["lines"], code, site)
    got.update({"kind": "cover", "currency": currency_for(code) or "", "business_code": code,
                "read_at": str(frappe.utils.now_datetime())[:16],
                "stock_as_of": _stock_as_of(code)})
    return got


def complete(answer) -> bool:
    return isinstance(answer, dict) and answer.get("kind") == "cover"


def get(business_code=None, reader=None) -> dict:
    """compute(), kept per business and per whose view of its ERPNext (speed.py)."""
    from command_center import speed
    from command_center.api.businesses import default_business_code
    code = (business_code if business_code and business_code != "__all__"
            else default_business_code())
    if reader is not None:
        return compute(code, reader)
    return speed.cached("cover", code, {"window": list(window_for(code))}, compute,
                        {"business_code": code}, complete=complete)


def links(lines, code, site):
    """Each document's address on the business's own ERPNext (api/facts._document_url)."""
    from command_center.api.facts import _document_url
    sites = {code: site} if site else {}

    def href(doctype, name):
        return _document_url(sites, {"business_code": code, "src_doctype": doctype,
                                     "src_name": name}) if name else None
    for l in lines:
        l["order_href"] = href("Sales Order", l["order"])
        l["item_href"] = href("Item", l["item_code"])
        for c in l["covers"]:
            c["po_href"] = href("Purchase Order", c["po"])
            if c.get("request"):
                c["request_href"] = href("Material Request", c["request"])
            for x in c["receipts"]:
                x["href"] = href("Purchase Receipt", x["name"])
            for x in c["invoices"]:
                x["href"] = href("Purchase Invoice", x["name"])
        for x in l["requests"]:
            x["href"] = href("Material Request", x["request"])


def _stock_as_of(code):
    import frappe
    try:
        row = frappe.get_all("Command Center Ingest State",
                             filters={"fact": "fact_stock_balance", "business_code": code},
                             fields=["last_run"], limit=1)
        return str(row[0]["last_run"])[:16] if row and row[0].get("last_run") else None
    except Exception:
        return None


def guide(code) -> dict:
    """Where nothing links an order to its purchase: how to make the links exact."""
    from command_center.guides import guide as g
    return g(code, "No purchase order or material request in ERPNext names the sales order "
                   "it is for, so what covers each order is inferred from the items and dates. "
                   "Raise them from the sales order and the link is exact:", LINK_STEPS,
             "/app/sales-order?status=To%20Deliver%20and%20Bill", label="Open the Sales Orders")


LINK_STEPS = [
    "Open the Sales Order that needs goods you do not hold.",
    "Click Create, then Purchase Order (choose the supplier; tick the items to buy) -- or "
    "Create, then Material Request, for buying to order it.",
    "Check the quantities and the Required By date, save and submit it. Each line now "
    "carries the sales order it is for.",
    "A Purchase Order made from that Material Request (Create, Purchase Order) keeps the link.",
    "Receive and bill against that Purchase Order as usual; this platform follows it from "
    "order to receipt to invoice.",
]
