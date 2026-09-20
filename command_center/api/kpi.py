"""KPIs, as the interface asks for them.

A screen names the figures it wants and gets them evaluated together, so a share
and its total cannot disagree. Definitions live in command_center/kpi; nothing
here decides what a figure means.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager
from command_center.kpi.engine import evaluate_set
from command_center.kpi.registry import load_all


@frappe.whitelist()
def get(keys, business_code: str | None = None):
    """Evaluate a set of KPIs for one business, or across all of them."""
    require_manager()
    keys = frappe.parse_json(keys) if isinstance(keys, str) else list(keys)

    known = load_all()
    unknown = [k for k in keys if k not in known]
    if unknown:
        frappe.throw(f"Unknown KPI(s): {', '.join(unknown)}. "
                     f"Known: {', '.join(sorted(known))}")

    return evaluate_set(keys, business_code)


@frappe.whitelist()
def catalogue():
    """Every KPI this platform can compute, and what each one is.

    Useful on its own: it is the list a client can be shown when agreeing what
    the platform reports, without reading any code.
    """
    require_manager()
    return [
        {
            "key": k.key,
            "label": k.label,
            "fact": k.fact,
            "measure": k.measure,
            "agg": k.agg,
            "unit": k.unit,
            "direction": k.direction,
            "subset_of": k.subset_of,
            "as_of_basis": k.as_of_basis,
            "opens_to_records": k.drill_filters is not None,
        }
        for k in sorted(load_all().values(), key=lambda x: x.key)
    ]


@frappe.whitelist()
def verify(business_code: str | None = None):
    """Check every declared identity against the data.

    ar_total says it is ar_over_90 plus ar_inside_90. That was true when the ageing
    buckets were written, and it stops being true the moment a bucket is added that
    belongs to neither -- at which point the receivable silently under-reports and
    every figure on the screen still looks reasonable.

    So the claim is checked rather than trusted. This is the same discipline as
    ingest.reconcile(), one layer up: reconcile proves the facts match the source,
    this proves the figures match the facts.
    """
    require_manager()
    registry = load_all()

    declared = [k for k in registry.values() if k.components]
    keys = {k.key for k in declared} | {p for k in declared for p in k.components}
    results = evaluate_set(sorted(keys), business_code)

    checks = []
    for kpi in declared:
        whole = results[kpi.key]["value"] or 0
        parts = {p: results[p]["value"] or 0 for p in kpi.components}
        total = sum(parts.values())
        # Money is stored to two decimal places and summed in the database, but the
        # comparison happens in Python floats. One pesewa of drift on nine million is
        # arithmetic, not a missing component -- and a check that cries wolf at that
        # scale stops being read.
        gap = round(whole - total, 2)
        tolerance = 0.01
        checks.append({
            "kpi": kpi.key,
            "label": kpi.label,
            "whole": whole,
            "components": parts,
            "component_total": round(total, 2),
            "difference": gap,
            "ok": abs(gap) <= tolerance,
            "means": (None if abs(gap) <= tolerance else
                      f"{abs(gap):,.2f} of {kpi.label.lower()} belongs to no "
                      f"component, so it is missing from every breakdown of it."),
        })

    return {
        "scope": business_code or "__all__",
        "checked": len(checks),
        "all_ok": all(c["ok"] for c in checks),
        "checks": checks,
    }
