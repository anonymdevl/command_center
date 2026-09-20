"""Reading facts, always within a business scope.

There is deliberately no method here that accepts a table name and arbitrary
filters from the browser. That would be a database connection with extra steps,
and it would make every permission decision below it advisory.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Sum
from pypika import Order

from command_center.api.businesses import require_manager
from command_center.facts.schema import (
    DIMENSIONS, FACTS, MEASURES, condition, filterable)





@frappe.whitelist()
def query(fact: str, measures=None, group_by=None, filters=None,
          business_code: str = None, limit: int = 200):
    """Aggregate one fact within one business, or across all of them."""
    require_manager()

    target = FACTS.get(fact)
    if not target:
        frappe.throw(f"Unknown fact '{fact}'. Known: {', '.join(sorted(FACTS))}")

    measures = frappe.parse_json(measures) if isinstance(measures, str) else (measures or MEASURES[fact][:1])
    group_by = frappe.parse_json(group_by) if isinstance(group_by, str) else (group_by or [])
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})

    bad = [m for m in measures if m not in MEASURES[fact]]
    if bad:
        frappe.throw(f"Not a measure of {fact}: {', '.join(bad)}")
    bad = [g for g in group_by if g not in DIMENSIONS[fact]]
    if bad:
        frappe.throw(f"Not a dimension of {fact}: {', '.join(bad)}")

    if business_code and business_code != "__all__":
        filters["business_code"] = business_code

    # Built with frappe.qb rather than a select list of "sum(x) as y" strings:
    # v16 rejects SQL function strings in a select list, and the dimension and
    # measure allow-lists above mean nothing reaches the builder that a request
    # chose freely.
    t = frappe.qb.DocType(target)
    q = frappe.qb.from_(t)
    for g in group_by:
        q = q.select(t[g]).groupby(t[g])
    for m in measures:
        q = q.select(Sum(t[m]).as_(m))
    q = q.select(Count(t.name).as_("rows"))

    allowed = filterable(fact)
    for field, rule in (filters or {}).items():
        if field not in allowed:
            frappe.throw(f"Cannot filter {fact} on '{field}'.")
        q = q.where(condition(t[field], rule))

    if measures:
        q = q.orderby(measures[0], order=Order.desc)
    q = q.limit(min(int(limit), 2000))

    return {
        "fact": fact,
        "scope": business_code or "__all__",
        "measures": measures,
        "group_by": group_by,
        "rows": q.run(as_dict=True),
    }


@frappe.whitelist()
def lineage(fact: str, filters=None, business_code: str = None, limit: int = 100):
    """Which records produced a figure.

    Drill-down is not a separate feature. Every fact row carries its source, so
    this selects the contributing rows and hands back their document identity.
    """
    require_manager()
    target = FACTS.get(fact)
    if not target:
        frappe.throw(f"Unknown fact '{fact}'.")

    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    if business_code and business_code != "__all__":
        filters["business_code"] = business_code

    return frappe.db.get_all(
        target, filters=filters,
        fields=["business_code", "src_doctype", "src_name", "src_row_name",
                "src_docstatus", "src_modified", "ingested_at"],
        order_by="src_modified desc", limit=min(int(limit), 500))
