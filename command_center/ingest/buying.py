"""Buying and payables facts.

Two grains, separated for the same reason the sales side is: the payable lives at
invoice grain, the spend at line grain. A document total repeated onto every item
line is how a payable comes out multiplied by the number of things bought.

Ageing is measured against the data horizon, never today — see resolve_as_of. On
this dataset that distinction is the difference between "everything is overdue" and
the truth.
"""

from __future__ import annotations

from frappe.utils import date_diff, flt, getdate

from command_center.ingest.base import Ingestor, ageing_bucket, require_fields

PAGE = 2000


class PurchaseInvoiceIngestor(Ingestor):
    fact = "fact_purchase_invoice"
    source_doctype = "Purchase Invoice"

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = as_of or resolve_as_of(conn)
        filters = {"docstatus": ["<", 2]}
        if since:
            filters["modified"] = [">", since]

        rows = []
        while True:
            batch = conn.get_list(
                "Purchase Invoice", filters=filters,
                fields=["name", "modified", "docstatus", "posting_date", "due_date",
                        "status", "is_return", "supplier", "currency",
                        "base_grand_total", "outstanding_amount"],
                order_by="modified asc", limit=min(PAGE, limit or PAGE),
            )
            if not batch:
                break
            groups = _supplier_groups(conn, {d.get("supplier") for d in batch})
            for d in batch:
                due = d.get("due_date")
                days = date_diff(as_of, due) if due else None
                rows.append({
                    "src_name": d["name"],
                    "src_modified": d["modified"],
                    "src_docstatus": d["docstatus"],
                    "posting_date": d["posting_date"],
                    "due_date": due,
                    "status": d.get("status"),
                    "is_return": d.get("is_return") or 0,
                    "supplier": d.get("supplier"),
                    "supplier_group": groups.get(d.get("supplier")),
                    "currency": d.get("currency"),
                    "base_grand_total": flt(d.get("base_grand_total")),
                    "outstanding_amount": flt(d.get("outstanding_amount")),
                    "as_of_date": getdate(as_of),
                    "days_overdue": days,
                    "ageing_bucket": ageing_bucket(days),
                })
            if limit and len(rows) >= limit:
                return rows[:limit]
            if len(batch) < PAGE:
                break
            filters["modified"] = [">", batch[-1]["modified"]]
        return rows


class PurchaseInvoiceLineIngestor(Ingestor):
    fact = "fact_purchase_invoice_line"
    source_doctype = "Purchase Invoice Item"

    def extract(self, conn, since=None, limit=None, as_of=None):
        """Lines, with the supplier carried down from the parent.

        There is no cost-versus-revenue question here: a purchase line's amount is
        the spend. So unlike the sales side there is no has_cost flag, and nothing
        is silently excluded.
        """
        filters = {"docstatus": ["<", 2]}
        if since:
            filters["modified"] = [">", since]

        parents = conn.get_list(
            "Purchase Invoice", filters=filters,
            fields=["name", "modified", "docstatus", "posting_date", "supplier"],
            order_by="modified asc", limit=limit or 100000,
        )
        if not parents:
            return []
        by_name = {p["name"]: p for p in parents}
        groups = _supplier_groups(conn, {p.get("supplier") for p in parents})

        rows, names = [], list(by_name)
        for i in range(0, len(names), 200):
            chunk = names[i:i + 200]
            line_fields = ["name", "parent", "item_code", "item_group", "warehouse",
                           "qty", "stock_qty", "uom", "base_net_amount",
                           "purchase_order"]
            lines = require_fields(
                conn.get_list(
                    "Purchase Invoice Item",
                    filters={"parent": ["in", chunk],
                             "parenttype": "Purchase Invoice"},
                    fields=line_fields,
                    limit=100000,
                    parent_doctype="Purchase Invoice",
                ),
                line_fields, "Purchase Invoice Item")
            for l in lines:
                p = by_name.get(l["parent"])
                if not p:
                    continue
                rows.append({
                    "src_name": l["parent"],
                    "src_row_name": l["name"],
                    "src_modified": p["modified"],
                    "src_docstatus": p["docstatus"],
                    "posting_date": p["posting_date"],
                    "supplier": p.get("supplier"),
                    "supplier_group": groups.get(p.get("supplier")),
                    "item_code": l.get("item_code"),
                    "item_group": l.get("item_group"),
                    "warehouse": l.get("warehouse"),
                    "qty": flt(l.get("qty")),
                    "stock_qty": flt(l.get("stock_qty")),
                    "uom": l.get("uom"),
                    "base_net_amount": flt(l.get("base_net_amount")),
                    "purchase_order": l.get("purchase_order"),
                })
        return rows


def _supplier_groups(conn, suppliers) -> dict:
    """Supplier group per supplier, in one read rather than one per invoice.

    Purchase Invoice does not carry the group, and fetching it per row would turn
    475 invoices into 475 queries.
    """
    names = [s for s in suppliers if s]
    out = {}
    for i in range(0, len(names), 300):
        for d in conn.get_list("Supplier",
                               filters={"name": ["in", names[i:i + 300]]},
                               fields=["name", "supplier_group"], limit=100000):
            out[d["name"]] = d.get("supplier_group")
    return out


INGESTORS = {
    "fact_purchase_invoice": PurchaseInvoiceIngestor,
    "fact_purchase_invoice_line": PurchaseInvoiceLineIngestor,
}
