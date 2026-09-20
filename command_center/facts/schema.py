"""What the facts are, in one place.

The fact-to-doctype map existed twice -- once in api/facts.py as ALLOWED, once in
kpi/engine.py as FACTS. Two copies of one truth is the same fault that made cards
differ between screens: nothing goes wrong until they drift, and then the
difference is invisible in both files.

Filter translation lives here for the same reason. api/facts.py read ["90+", "61-90"]
as the operator "90+", because it assumed any two-element list was an operator and
a value. Fixing that in the engine alone would have left the API wrong.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
FACTS = {
    "fact_sales_invoice": "Command Center Fact Sales Invoice",
    "fact_sales_invoice_line": "Command Center Fact Sales Invoice Line",
    "fact_payment_allocation": "Command Center Fact Payment Allocation",
    "fact_purchase_invoice": "Command Center Fact Purchase Invoice",
    "fact_purchase_invoice_line": "Command Center Fact Purchase Invoice Line",
    "fact_stock_balance": "Command Center Fact Stock Balance",
}

# What each fact may be grouped by. An allow-list, because a group_by taken from a
# request is a SQL injection surface however carefully it is escaped.
DIMENSIONS = {
    "fact_sales_invoice": ["customer", "customer_group", "territory",
                           "ageing_bucket", "status", "posting_date", "business_code"],
    "fact_sales_invoice_line": ["customer", "customer_group", "territory",
                                "item_code", "item_group", "warehouse",
                                "posting_date", "business_code"],
    "fact_payment_allocation": ["party", "payment_type", "against_doctype",
                                "posting_date", "business_code"],
    "fact_purchase_invoice": ["supplier", "supplier_group", "ageing_bucket",
                              "status", "posting_date", "business_code"],
    "fact_purchase_invoice_line": ["supplier", "supplier_group", "item_code",
                                   "item_group", "warehouse", "posting_date",
                                   "business_code"],
    "fact_stock_balance": ["warehouse", "item_code", "item_group", "business_code"],
}

MEASURES = {
    "fact_sales_invoice": ["outstanding_amount", "base_grand_total"],
    "fact_sales_invoice_line": ["base_net_amount", "base_cost_amount",
                                "base_margin_amount", "qty", "stock_qty"],
    "fact_payment_allocation": ["allocated_amount", "base_paid_amount"],
    "fact_purchase_invoice": ["outstanding_amount", "base_grand_total"],
    "fact_purchase_invoice_line": ["base_net_amount", "qty", "stock_qty"],
    "fact_stock_balance": ["stock_value", "actual_qty", "reserved_qty",
                           "available_qty", "ordered_qty", "projected_qty"],
}

# Columns every fact carries, which a filter may name even though they are neither
# a dimension to group by nor a measure to add up.
LINEAGE = ["src_doctype", "src_name", "src_row_name", "src_docstatus",
           "src_modified", "ingested_at", "fact_key"]

# Scoping columns that are not free-text dimensions.
FLAGS = ["ageing_bucket", "has_cost", "has_valuation", "src_docstatus"]

OPERATORS = (">", ">=", "<", "<=", "=", "!=", "in", "not in", "like")


def doctype(fact: str) -> str | None:
    return FACTS.get(fact)


def filterable(fact: str) -> list[str]:
    return DIMENSIONS.get(fact, []) + MEASURES.get(fact, []) + LINEAGE + FLAGS


def condition(column, value):
    """Translate one filter value into a query-builder condition.

    ["=", 0] is an operator and a value. ["90+", "61-90"] is two values. Reading
    the first element as an operator unconditionally turned the second form into a
    filter on the operator "90+", which matches nothing and raises nothing.
    """
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and value[0] in OPERATORS:
            op, val = value
        else:
            op, val = "in", list(value)

        if op in ("in", "not in"):
            values = val if isinstance(val, (list, tuple)) else [val]
            return column.isin(values) if op == "in" else column.notin(values)
        if op == "like":
            return column.like(val)
        return {">": lambda: column > val, ">=": lambda: column >= val,
                "<": lambda: column < val, "<=": lambda: column <= val,
                "=": lambda: column == val, "!=": lambda: column != val}[op]()
    return column == value
