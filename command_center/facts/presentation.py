"""How a set of fact rows is presented to someone deciding something.

The drawer used to show src_name, src_row_name and src_modified: an invoice code,
an internal row hash and a timestamp. That is provenance, and provenance was the
engineering requirement -- prove the figure traces to a document. It is not
information. A manager opening "Invoiced revenue" and finding a hundred rows of
"ACC-SINV-2025-00814 / 8f3a91c / 2025-08-19" learns nothing, cannot act, and
reasonably concludes the platform is for someone else.

What a manager needs from a figure is: who, what, how much, how old, and what to do
about it. All of that is already on the fact rows -- customer, item, amount,
days_overdue, days_to_pay. It simply was not being asked for.

So the presentation of each fact is declared here, once, server-side: which columns
are worth showing, what they are called in plain words, which one to sort by so the
largest exposure is first, and which dimension to concentrate on -- because "three
customers are half of it" is the sentence that changes a decision, and no list of a
hundred rows says it.

Provenance is not lost. It becomes useful instead: each row carries a link that
opens the actual document in ERPNext.
"""

from __future__ import annotations

# Column types the interface knows how to format. Anything else is written as text.
# currency | number | date | days | percent | text | doc

PRESENTATION = {
    "fact_sales_invoice": {
        "noun": "invoice",
        "order_by": "outstanding_amount",
        "total": ("outstanding_amount", "outstanding"),
        "concentrate_on": ("customer", "customer"),
        "columns": [
            {"key": "customer", "label": "Customer", "type": "text"},
            {"key": "src_name", "label": "Invoice", "type": "doc"},
            {"key": "posting_date", "label": "Raised", "type": "date"},
            {"key": "due_date", "label": "Was due", "type": "date"},
            {"key": "days_overdue", "label": "Days late", "type": "days"},
            {"key": "outstanding_amount", "label": "Still owed", "type": "currency"},
            {"key": "base_grand_total", "label": "Invoice total", "type": "currency"},
        ],
    },
    "fact_sales_invoice_line": {
        "noun": "invoice line",
        "order_by": "base_net_amount",
        "total": ("base_net_amount", "revenue"),
        "concentrate_on": ("customer", "customer"),
        "columns": [
            {"key": "customer", "label": "Customer", "type": "text"},
            {"key": "item_code", "label": "Item", "type": "text"},
            {"key": "item_group", "label": "Group", "type": "text"},
            {"key": "qty", "label": "Qty", "type": "number"},
            {"key": "base_net_amount", "label": "Revenue", "type": "currency"},
            {"key": "base_margin_amount", "label": "Margin", "type": "currency"},
            {"key": "margin_pct", "label": "Margin %", "type": "percent",
             "derived": True},
            {"key": "src_name", "label": "Invoice", "type": "doc"},
            {"key": "posting_date", "label": "Date", "type": "date"},
        ],
    },
    "fact_payment_allocation": {
        "noun": "payment",
        "order_by": "allocated_amount",
        "total": ("allocated_amount", "applied"),
        "concentrate_on": ("party", "customer"),
        "columns": [
            {"key": "party", "label": "Paid by", "type": "text"},
            {"key": "posting_date", "label": "Received", "type": "date"},
            {"key": "payment_type", "label": "Type", "type": "text"},
            {"key": "against_name", "label": "Applied to", "type": "text"},
            {"key": "allocated_amount", "label": "Amount", "type": "currency"},
            {"key": "days_to_pay", "label": "Days to pay", "type": "days"},
            {"key": "src_name", "label": "Payment", "type": "doc"},
        ],
    },
}

# Always fetched, whether shown or not: the link back to ERPNext needs them.
ALWAYS = ["src_doctype", "src_name", "business_code"]


def spec(fact: str) -> dict:
    return PRESENTATION.get(fact) or {}


def select_fields(fact: str) -> list[str]:
    """Columns to read. Derived ones are computed, not selected."""
    s = spec(fact)
    fields = [c["key"] for c in s.get("columns", []) if not c.get("derived")]
    for extra in ALWAYS:
        if extra not in fields:
            fields.append(extra)
    # A derived margin percentage needs both sides of the division.
    if fact == "fact_sales_invoice_line":
        for needed in ("base_net_amount", "base_margin_amount"):
            if needed not in fields:
                fields.append(needed)
    return fields


def derive(fact: str, row: dict) -> dict:
    """Row-level figures that are a ratio of two columns on the same row.

    Computed here rather than in the browser for the same reason the KPI engine
    exists: one definition. A margin percentage worked out in JavaScript on one
    screen and in Python on another is two figures with one name.
    """
    if fact == "fact_sales_invoice_line":
        net = row.get("base_net_amount") or 0
        row["margin_pct"] = (row.get("base_margin_amount") or 0) / net * 100 if net else None
    return row
