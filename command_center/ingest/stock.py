"""Stock balances.

Read from Bin, which is ERPNext's own running balance per item per warehouse. Not
recomputed from the stock ledger: Bin is what ERPNext itself believes, and a second
opinion computed here would eventually disagree with the system of record, at which
point nobody could say which was right.

Two things are stored rather than derived at read time:

  available_qty   on hand less reserved. That difference is what a manager means by
                  "stock", and every screen must agree on it. Left to each screen to
                  subtract, they eventually would not.

  has_valuation   zero where ERPNext holds no valuation. Stock with no value is a
                  data-quality fact, not free stock -- the same discipline as
                  has_cost on the sales side, where 206 lines would otherwise have
                  reported as pure margin.
"""

from __future__ import annotations

from frappe.utils import flt

from command_center.ingest.base import Ingestor, require_fields

PAGE = 2000


class StockBalanceIngestor(Ingestor):
    fact = "fact_stock_balance"
    source_doctype = "Bin"

    def extract(self, conn, since=None, limit=None, as_of=None):
        filters = {}
        if since:
            filters["modified"] = [">", since]

        bin_fields = ["name", "modified", "warehouse", "item_code", "stock_uom",
                      "actual_qty", "reserved_qty", "ordered_qty",
                      "projected_qty", "valuation_rate", "stock_value"]

        rows, seen_items = [], set()
        raw = []
        while True:
            # Guarded: a field the source drops without complaint becomes a silently
            # blank fact column, which is how sixty cases loaded with no status.
            batch = require_fields(
                conn.get_list("Bin", filters=filters, fields=bin_fields,
                              order_by="modified asc",
                              limit=min(PAGE, limit or PAGE)),
                bin_fields, "Bin")
            if not batch:
                break
            raw.extend(batch)
            seen_items.update(b.get("item_code") for b in batch)
            if limit and len(raw) >= limit:
                raw = raw[:limit]
                break
            if len(batch) < PAGE:
                break
            filters["modified"] = [">", batch[-1]["modified"]]

        groups = _item_groups(conn, seen_items)

        for b in raw:
            on_hand = flt(b.get("actual_qty"))
            reserved = flt(b.get("reserved_qty"))
            rate = flt(b.get("valuation_rate"))
            rows.append({
                # Bin is not a submittable document, so there is no docstatus to
                # carry. Recording 1 would imply a submission that never happened.
                "src_name": b["name"],
                "src_modified": b["modified"],
                "src_docstatus": 0,
                "warehouse": b.get("warehouse"),
                "item_code": b.get("item_code"),
                "item_group": groups.get(b.get("item_code")),
                "stock_uom": b.get("stock_uom"),
                "actual_qty": on_hand,
                "reserved_qty": reserved,
                "available_qty": on_hand - reserved,
                "ordered_qty": flt(b.get("ordered_qty")),
                "projected_qty": flt(b.get("projected_qty")),
                "valuation_rate": rate,
                "stock_value": flt(b.get("stock_value")),
                "has_valuation": 1 if rate else 0,
            })
        return rows


def _item_groups(conn, items) -> dict:
    """Item group per item, in one read. Bin does not carry it."""
    names = [i for i in items if i]
    out = {}
    for i in range(0, len(names), 300):
        for d in require_fields(
                conn.get_list("Item", filters={"name": ["in", names[i:i + 300]]},
                              fields=["name", "item_group"], limit=100000),
                ["name", "item_group"], "Item"):
            out[d["name"]] = d.get("item_group")
    return out


INGESTORS = {
    "fact_stock_balance": StockBalanceIngestor,
}
