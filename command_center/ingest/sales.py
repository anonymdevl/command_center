"""Sales and receivables facts.

Three grains, deliberately separate, because mixing them is how a receivable gets
double counted:

*   **Invoice** — one row per invoice. Outstanding lives here and only here.
*   **Invoice line** — one row per item line. Revenue, cost and margin.
*   **Payment allocation** — one row per payment applied to one invoice.

A document-level amount repeated onto every line is the classic way an AR total
comes out inflated by the number of items sold. Keeping outstanding at invoice
grain makes that mistake unavailable rather than merely discouraged.
"""

from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, getdate

from command_center.ingest.base import Ingestor, ageing_bucket, require_fields

PAGE = 2000


class SalesInvoiceIngestor(Ingestor):
    fact = "fact_sales_invoice"
    target = "Command Center Fact Sales Invoice"
    source_doctype = "Sales Invoice"

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        # Resolved by the caller normally; recomputed only if called directly.
        as_of = as_of or resolve_as_of(conn)
        filters = {"docstatus": ["<", 2]}
        if since:
            filters["modified"] = [">", since]

        rows, start = [], 0
        while True:
            batch = conn.get_list(
                "Sales Invoice", filters=filters,
                fields=["name", "modified", "docstatus", "posting_date", "due_date",
                        "status", "is_return", "customer", "customer_group",
                        "territory", "currency", "base_grand_total",
                        "outstanding_amount"],
                order_by="modified asc", limit=min(PAGE, limit or PAGE),
            )
            if not batch:
                break
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
                    "customer": d.get("customer"),
                    "customer_group": d.get("customer_group"),
                    "territory": d.get("territory"),
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


class SalesInvoiceLineIngestor(Ingestor):
    fact = "fact_sales_invoice_line"
    target = "Command Center Fact Sales Invoice Line"
    source_doctype = "Sales Invoice Item"

    def extract(self, conn, since=None, limit=None, as_of=None):
        """Lines, with the parent's party context carried down.

        Cost comes from `incoming_rate`, which is what ERPNext valued the stock at
        when the invoice posted. Where it is zero the line is marked
        `has_cost = 0` rather than being reported as pure margin — a missing
        valuation is a data-quality fact, and a margin KPI that treats it as free
        stock is worse than no margin KPI.
        """
        filters = {"docstatus": ["<", 2]}
        if since:
            filters["modified"] = [">", since]

        parents = conn.get_list(
            "Sales Invoice", filters=filters,
            fields=["name", "modified", "docstatus", "posting_date", "customer",
                    "customer_group", "territory"],
            order_by="modified asc", limit=limit or 100000,
        )
        if not parents:
            return []
        by_name = {p["name"]: p for p in parents}

        rows, names = [], list(by_name)
        for i in range(0, len(names), 200):
            chunk = names[i:i + 200]
            line_fields = ["name", "parent", "item_code", "item_group",
                           "warehouse", "qty", "stock_qty", "uom",
                           "base_net_amount", "incoming_rate", "sales_order"]
            lines = require_fields(
                conn.get_list(
                    "Sales Invoice Item",
                    filters={"parent": ["in", chunk],
                             "parenttype": "Sales Invoice"},
                    fields=line_fields,
                    limit=100000,
                    parent_doctype="Sales Invoice",
                ),
                line_fields, "Sales Invoice Item")
            for l in lines:
                p = by_name.get(l["parent"])
                if not p:
                    continue
                stock_qty = flt(l.get("stock_qty"))
                rate = flt(l.get("incoming_rate"))
                cost = rate * stock_qty
                revenue = flt(l.get("base_net_amount"))
                rows.append({
                    "src_name": l["parent"],
                    "src_row_name": l["name"],
                    "src_modified": p["modified"],
                    "src_docstatus": p["docstatus"],
                    "posting_date": p["posting_date"],
                    "customer": p.get("customer"),
                    "customer_group": p.get("customer_group"),
                    "territory": p.get("territory"),
                    "item_code": l.get("item_code"),
                    "item_group": l.get("item_group"),
                    "warehouse": l.get("warehouse"),
                    "qty": flt(l.get("qty")),
                    "stock_qty": stock_qty,
                    "uom": l.get("uom"),
                    "base_net_amount": revenue,
                    "base_cost_amount": cost,
                    "base_margin_amount": revenue - cost if rate else 0,
                    "has_cost": 1 if rate else 0,
                    "sales_order": l.get("sales_order"),
                })
        return rows


class PaymentAllocationIngestor(Ingestor):
    fact = "fact_payment_allocation"
    target = "Command Center Fact Payment Allocation"
    source_doctype = "Payment Entry Reference"

    def extract(self, conn, since=None, limit=None, as_of=None):
        """Cash, and what it was matched against.

        `unallocated_amount` belongs to the payment, not the allocation, so it is
        repeated across a payment's rows. Summing it over allocations overstates
        unmatched cash; the field's own description says so, and any KPI over it
        must aggregate over distinct payments.
        """
        filters = {"docstatus": 1}
        if since:
            filters["modified"] = [">", since]

        pays = conn.get_list(
            "Payment Entry", filters=filters,
            fields=["name", "modified", "docstatus", "posting_date", "party_type",
                    "party", "payment_type", "base_paid_amount",
                    "unallocated_amount"],
            order_by="modified asc", limit=limit or 100000,
        )
        if not pays:
            return []
        by_name = {p["name"]: p for p in pays}

        # Due dates for days-to-pay. One lookup, not one per allocation.
        rows, names = [], list(by_name)
        for i in range(0, len(names), 200):
            chunk = names[i:i + 200]
            ref_fields = ["name", "parent", "reference_doctype",
                          "reference_name", "allocated_amount"]
            refs = require_fields(
                conn.get_list(
                    "Payment Entry Reference",
                    filters={"parent": ["in", chunk],
                             "parenttype": "Payment Entry"},
                    fields=ref_fields,
                    limit=100000,
                    parent_doctype="Payment Entry",
                ),
                ref_fields, "Payment Entry Reference")
            inv_names = [r["reference_name"] for r in refs
                         if r.get("reference_doctype") == "Sales Invoice"]
            due = {}
            for j in range(0, len(inv_names), 300):
                for d in conn.get_list("Sales Invoice",
                                       filters={"name": ["in", inv_names[j:j + 300]]},
                                       fields=["name", "due_date"], limit=100000):
                    due[d["name"]] = d.get("due_date")

            for r in refs:
                p = by_name.get(r["parent"])
                if not p:
                    continue
                d = due.get(r.get("reference_name"))
                rows.append({
                    "src_name": r["parent"],
                    "src_row_name": r["name"],
                    "src_modified": p["modified"],
                    "src_docstatus": p["docstatus"],
                    "posting_date": p["posting_date"],
                    "party_type": p.get("party_type"),
                    "party": p.get("party"),
                    "payment_type": p.get("payment_type"),
                    "against_doctype": r.get("reference_doctype"),
                    "against_name": r.get("reference_name"),
                    "allocated_amount": flt(r.get("allocated_amount")),
                    "base_paid_amount": flt(p.get("base_paid_amount")),
                    "unallocated_amount": flt(p.get("unallocated_amount")),
                    "days_to_pay": date_diff(p["posting_date"], d) if d else None,
                })
        return rows


INGESTORS = {
    "fact_sales_invoice": SalesInvoiceIngestor,
    "fact_sales_invoice_line": SalesInvoiceLineIngestor,
    "fact_payment_allocation": PaymentAllocationIngestor,
}
