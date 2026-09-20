"""Reading facts, always within a business scope.

There is deliberately no method here that accepts a table name and arbitrary
filters from the browser. That would be a database connection with extra steps,
and it would make every permission decision below it advisory.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import frappe
from frappe.query_builder.functions import Count, Sum
from pypika import Order

from command_center.api.businesses import currency_for, require_manager
from command_center.facts.schema import (
    DIMENSIONS, FACTS, MEASURES, condition, filterable)
from command_center.facts import presentation





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
def records(fact: str, filters=None, business_code: str = None, limit: int = 100):
    """The records behind a figure, as something to decide on.

    Three things come back, and the first two are the point:

      summary     what these records add up to, and how concentrated they are. "Three
                  customers are half of it" is the sentence that changes a decision;
                  a hundred rows never says it.

      columns     declared server-side per fact, in plain words, so every drawer on
                  every screen describes the same fact the same way.

      rows        ordered largest first, each carrying a link that opens the document
                  in ERPNext.

    This replaces lineage(), which returned src_name, src_row_name and src_modified.
    That proved the figure traced to a document, which was the engineering
    requirement and is not information a manager can use.
    """
    require_manager()

    target = FACTS.get(fact)
    if not target:
        frappe.throw(f"Unknown fact '{fact}'. Known: {', '.join(sorted(FACTS))}")
    spec = presentation.spec(fact)
    if not spec:
        frappe.throw(f"No presentation is declared for '{fact}'.")

    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    if business_code and business_code != "__all__":
        filters["business_code"] = business_code

    allowed = filterable(fact)
    for field in filters:
        if field not in allowed:
            frappe.throw(f"Cannot filter {fact} on '{field}'.")

    t = frappe.qb.DocType(target)

    # ---- the whole set, before any limit. A summary over the first hundred rows
    # would describe the page rather than the figure.
    measure, measure_word = spec["total"]
    totals = frappe.qb.from_(t).select(Sum(t[measure]), Count(t.name))
    for field, rule in filters.items():
        totals = totals.where(condition(t[field], rule))
    total_value, total_count = (totals.run() or [(0, 0)])[0]

    # ---- concentration: where the weight sits
    dimension, dimension_word = spec["concentrate_on"]
    conc = frappe.qb.from_(t).select(t[dimension], Sum(t[measure]).as_("v"),
                                     Count(t.name).as_("n"))
    for field, rule in filters.items():
        conc = conc.where(condition(t[field], rule))
    conc = conc.groupby(t[dimension]).orderby("v", order=Order.desc).limit(5)
    top = conc.run(as_dict=True)

    # ---- the rows themselves
    rows = frappe.db.get_all(
        target, filters=filters,
        fields=presentation.select_fields(fact),
        order_by=f"{spec['order_by']} desc",
        limit=min(int(limit), 500))

    sites = _site_urls()
    for row in rows:
        presentation.derive(fact, row)
        row["open_url"] = _document_url(sites, row)

    whole = total_value or 0
    return {
        "fact": fact,
        "noun": spec["noun"],
        "scope": business_code or "__all__",
        "currency": currency_for(business_code),
        "columns": spec["columns"],
        "rows": rows,
        "summary": {
            "count": total_count or 0,
            "shown": len(rows),
            "total": whole,
            "measure_word": measure_word,
            "dimension_word": dimension_word,
            "concentration": [
                {
                    "label": c.get(dimension) or "not stated",
                    "value": c["v"],
                    "count": c["n"],
                    "share": round((c["v"] or 0) / whole * 100, 1) if whole else None,
                }
                for c in top
            ],
            "top_share": (round(sum(c["v"] or 0 for c in top) / whole * 100, 1)
                          if whole and top else None),
        },
    }


def _site_urls() -> dict:
    """Where each business's ERPNext lives, so a row can be opened in it.

    The local business is this site; a connected one is its own URL. Read once per
    request rather than per row.
    """
    urls = {}
    for b in frappe.get_all("Connected Business",
                            filters={"status": "Active"},
                            fields=["business_code", "is_local", "site_url"]):
        urls[b.business_code] = "" if b.is_local else (b.site_url or "").rstrip("/")
    return urls


def _document_url(sites, row) -> str | None:
    """A link to the document itself.

    Built with Frappe's own get_url_to_form rather than assembling /app/<slug>/<name>
    by hand. My hand-built version produced links that 404'd: the desk route for a
    doctype is not always its lowercased name, and guessing it is not something this
    app should be doing when the framework knows the answer.

    A connected business is on another site, so its path is taken from the local
    answer and prefixed with that site's URL -- the route is the same in every Frappe.
    """
    doctype, name = row.get("src_doctype"), row.get("src_name")
    if not doctype or not name:
        return None

    try:
        url = frappe.utils.get_url_to_form(doctype, str(name))
    except Exception:
        return None

    base = sites.get(row.get("business_code")) or ""
    if not base:
        return url
    # Keep only the path, so the peer's own host is used rather than this one's.
    path = urlsplit(url).path
    return f"{base}{path}"

