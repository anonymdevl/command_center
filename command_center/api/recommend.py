"""The recommendations a manager sees, and what they decide about each.

    current    the open recommendations for a business (or every business), made fresh
               first when the last pass is more than fifteen minutes old, ranked by money
               at stake times urgency; with the Daily Brief when one is written, and what
               cleared recently
    critical   the critical ones the alerts do not already show, for the bell
    act        Done, Not Relevant (an optional reason), Snooze 7 or 30 days, Reopen

Only the recommendation's own state changes here. Nothing is written to any business's
ERPNext, and the analyst reaches none of this (it reads recommend.engine.snapshot).
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager
from command_center.recommend import engine


def _codes(business_code):
    if business_code and business_code != "__all__":
        return [business_code]
    from command_center.api.businesses import loaded_codes
    return loaded_codes()


@frappe.whitelist()
def current(business_code: str | None = None):
    require_manager()
    codes = _codes(business_code)
    recs, failed, unreachable, history, runs = [], {}, False, [], []
    for code in codes:
        engine.ensure_fresh(code)
        recs += engine.visible(code)
        history += engine.history(code, limit=10)
        run = engine.last_run(code) or {}
        runs.append(run)
        failed.update(run.get("failed") or {})
        unreachable = unreachable or bool(run.get("unreachable"))
    engine.rank(recs)
    brief = None
    if len(codes) == 1:
        from command_center.recommend.daily import brief_for
        brief = brief_for(codes[0])
    from command_center.recommend.rules import AREAS, BY_ID
    return {"recommendations": recs, "areas": AREAS,
            "failed": [{"rule": BY_ID[k].title, "why": v} for k, v in failed.items() if k in BY_ID],
            "unreachable": unreachable, "brief": brief,
            "history": sorted(history, key=lambda r: r.get("resolved_on") or "", reverse=True)[:10],
            "checked_at": max((r.get("at") or "" for r in runs), default="") or None,
            "can_tune": "System Manager" in frappe.get_roles()}


@frappe.whitelist()
def critical(business_code: str | None = None):
    require_manager()
    out = []
    for code in _codes(business_code):
        engine.ensure_fresh(code)
        out += engine.critical(code)
    return {"recommendations": engine.rank(out)[:8]}


@frappe.whitelist(methods=["POST"])
def act(name: str, action: str, reason: str = "", days=None):
    require_manager()
    doc = frappe.get_doc(engine.DOCTYPE, name)
    doc.check_permission("write")
    return engine.act(name, action, reason=reason, days=days)
