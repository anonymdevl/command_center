"""Aggregating a fact for the assistant, the same way the rest of the app does.

Written because the first draft of intents.py aggregated with field strings like
`"sum(outstanding_amount) as owed"`. That does not work on this Frappe version -- v16
rejects SQL function strings in a select list -- and api/facts.py already knew it, using
frappe.qb with Sum and Count for precisely that reason. Writing a new module beside an
existing one without carrying over what it had already learned is the mistake this file
exists to stop repeating.

Filter translation comes from facts.schema.condition, so a filter means the same thing
here as it does in the KPI engine and the records drawer. One definition.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Max, Min, Sum
from pypika import Order

from command_center.facts.schema import FACTS, condition

FUNCS = {"sum": Sum, "count": Count, "max": Max, "min": Min}


def _table(fact: str):
    doctype = FACTS.get(fact)
    if not doctype:
        frappe.throw(f"Unknown fact {fact!r}")
    return frappe.qb.DocType(doctype)


def _where(q, t, filters):
    for field, rule in (filters or {}).items():
        q = q.where(condition(t[field], rule))
    return q


def totals(fact: str, filters: dict | None = None, measures=()) -> dict:
    """One row of aggregates over the whole filtered set.

    `measures` is a sequence of (func, column, alias). A count of rows is
    ("count", "name", "rows").
    """
    t = _table(fact)
    q = _where(frappe.qb.from_(t), t, filters)
    aliases = []
    for func, column, alias in measures:
        q = q.select(FUNCS[func](t[column]).as_(alias))
        aliases.append(alias)
    rows = q.run(as_dict=True)
    return dict(rows[0]) if rows else {a: None for a in aliases}


def grouped(fact: str, group_by: str, filters: dict | None = None, measures=(),
            order_by: str | None = None, limit: int = 10) -> list[dict]:
    """Aggregates per value of one column, largest first by default."""
    t = _table(fact)
    q = _where(frappe.qb.from_(t), t, filters)
    q = q.select(t[group_by]).groupby(t[group_by])
    aliases = []
    for func, column, alias in measures:
        q = q.select(FUNCS[func](t[column]).as_(alias))
        aliases.append(alias)
    if aliases:
        q = q.orderby(order_by or aliases[0], order=Order.desc)
    q = q.limit(min(int(limit), 500))
    return [dict(r) for r in q.run(as_dict=True)]


def distinct_count(fact: str, column: str, filters: dict | None = None) -> int:
    t = _table(fact)
    q = _where(frappe.qb.from_(t), t, filters)
    q = q.select(Count(t[column]).distinct())
    rows = q.run()
    return (rows[0][0] or 0) if rows else 0


def single_supplier_items(supplier: str, filters: dict | None = None) -> int:
    """How many of a supplier's items have been bought from nobody else.

    Two grouped queries rather than raw SQL: the items this supplier has supplied,
    and the items that have exactly one supplier in the loaded records. The overlap
    is the exposure, and it is the figure worth knowing before anyone says "we are
    dependent on them".
    """
    t = _table("fact_purchase_invoice_line")

    theirs = _where(frappe.qb.from_(t).select(t.item_code).distinct(),
                    t, {**(filters or {}), "supplier": supplier})
    their_items = {r[0] for r in theirs.run() if r[0]}
    if not their_items:
        return 0

    single = _where(frappe.qb.from_(t).select(t.item_code), t, filters or {})
    single = (single.groupby(t.item_code)
                    .having(Count(t.supplier).distinct() == 1))
    only_one = {r[0] for r in single.run() if r[0]}
    return len(their_items & only_one)
