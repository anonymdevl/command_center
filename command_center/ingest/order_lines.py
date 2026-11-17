"""What is still to come on an order, valued line by line.

ERPNext's `per_delivered` and `per_received` are shares of QUANTITY (the sum of what was
delivered, capped at each line's quantity, over the sum of the quantities), and
`per_billed` is a share of the lines' amounts. Multiplying an order's value by any of
them values money by a count: GMS SAL-ORD-2025-00942 is worth GHS 746,980 and 86.14%
delivered, which said GHS 103,541.78 was still to deliver; line by line it is GHS 16,290
(eighty of its 81 lines delivered, the cheap ones counting as much as the oven).

So every money figure on what is left of an order is worked out here, from its lines,
and nowhere else (preflight fails a per_* percentage multiplied into money):

    left_value         (qty - delivered or received qty) x the line's base net rate
    unbilled_value     the part of the line's amount not yet invoiced (billed_amt is
                       kept by ERPNext against `amount`), at the line's base net amount
    delivered_unbilled the part delivered and not yet invoiced, the same way

each grossed up by the order's taxes in proportion (base grand total over base net
total), so the pieces of an order add up to its value -- as coverage.py values a
promised line.
"""

from __future__ import annotations

from frappe.utils import flt

from command_center.ingest.base import require_fields

# The child table, its parent, and the quantity that says how much of a line has been
# done: delivered to the customer, or received from the supplier.
SALES = ("Sales Order Item", "Sales Order", "delivered_qty")
BUYING = ("Purchase Order Item", "Purchase Order", "received_qty")
FIELDS = ["name", "parent", "qty", "base_net_rate", "base_net_amount", "amount", "billed_amt"]
CHUNK = 200


def factor(order: dict) -> float:
    """The order's taxes, as a multiplier on its lines' net amounts."""
    net = flt(order.get("base_net_total"))
    return flt(order.get("base_grand_total")) / net if net > 0 else 1.0


def left_value(line: dict, order: dict, done: str) -> float:
    """What is still to come on one line, in the business's currency."""
    left = max(flt(line.get("qty")) - flt(line.get(done)), 0.0)
    return left * flt(line.get("base_net_rate")) * factor(order)


def _billed_share(line: dict, upto: float) -> float:
    """Of the line's amount, the share between what is billed and `upto` (a share)."""
    amount = flt(line.get("amount"))
    if amount <= 0:
        return 0.0
    return max(upto * amount - flt(line.get("billed_amt")), 0.0) / amount


def unbilled_value(line: dict, order: dict) -> float:
    return _billed_share(line, 1.0) * flt(line.get("base_net_amount")) * factor(order)


def delivered_unbilled_value(line: dict, order: dict, done: str) -> float:
    qty = flt(line.get("qty"))
    delivered = min(flt(line.get(done)), qty) / qty if qty > 0 else 0.0
    return _billed_share(line, delivered) * flt(line.get("base_net_amount")) * factor(order)


def values(order: dict, lines: list, done: str) -> dict:
    """{"left", "unbilled", "delivered_unbilled"} for one order, to the cent."""
    return {
        "left": round(sum(left_value(x, order, done) for x in lines), 2),
        "unbilled": round(sum(unbilled_value(x, order) for x in lines), 2),
        "delivered_unbilled": round(sum(delivered_unbilled_value(x, order, done)
                                        for x in lines), 2),
    }


def has_more(order: dict, done_pct: str) -> bool:
    """Whether anything can be left on an order by ERPNext's own percentages: both at
    100 means every line is done and invoiced, and its lines need not be read. Used as
    a filter only, never to value anything."""
    return flt(order.get(done_pct)) < 100 or flt(order.get("per_billed")) < 100


def read(conn, kind, names) -> dict:
    """{order: [its lines]} for the named orders, from the business's ERPNext."""
    child, parent, done = kind
    fields = FIELDS + [done]
    out = {}
    names = sorted(set(names))
    for i in range(0, len(names), CHUNK):
        chunk = names[i:i + CHUNK]
        filters = {"parent": ["in", chunk], "parenttype": parent}
        # A connector (ingest) or a screen's reader (kpi/live._Reader: .all).
        got = (conn.get_list(child, filters=filters, fields=fields, limit=100000,
                             parent_doctype=parent) if hasattr(conn, "get_list") else
               conn.all(child, filters=filters, fields=fields, limit=100000, parent=parent))
        rows = require_fields(got, fields, child)
        for x in rows:
            out.setdefault(x["parent"], []).append(x)
    return out


def order_values(conn, kind, orders: list, done_pct: str) -> dict:
    """{order name: values()} for every order given (header rows with base_grand_total,
    base_net_total and the two percentages); an order with nothing left by ERPNext's own
    percentages is all zero without reading its lines."""
    want = [o["name"] for o in orders if has_more(o, done_pct)]
    lines = read(conn, kind, want) if want else {}
    zero = {"left": 0.0, "unbilled": 0.0, "delivered_unbilled": 0.0}
    return {o["name"]: (values(o, lines.get(o["name"], []), kind[2])
                        if o["name"] in lines else dict(zero))
            for o in orders}
