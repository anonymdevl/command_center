"""The department screens' finding boxes, fed from the recommendations.

Each screen's designed finding boxes (the .warn boxes, filled by api/panels.py FINDINGS)
show first the largest open recommendations of the screen's own area, then -- where the
area has fewer than the screen has boxes -- the screen's own findings as before. A box
with nothing to say stays hidden, as it always has.

Wrapping is done where FINDINGS is registered (api/panels.py, api/panels_core.py); the
panel builders and the screens' drawing are untouched.
"""

from __future__ import annotations

# view -> (areas, the rules of those areas that belong on it; None for all of them)
VIEWS = {
    "sales": (("sales", "cash"), None),
    "fin": (("cash",), None),
    "proc": (("buying",), None),
    "inv": (("stock",), None),
    "eng": (("control",), {"overdue_tasks_by_owner"}),
    "hr": (("control", "data"), {"leavers_trend", "duplicate_departments"}),
    "aud": (("control", "data"), {"approvals_bottleneck", "self_approvals", "draft_documents"}),
    "it": (("control",), {"self_approvals"}),
    "ops": (None, None),
}
# How many finding boxes each screen was designed with (views.json).
BOXES = {"sales": 2, "fin": 2, "proc": 2, "aud": 2}


def finding(r) -> dict:
    first = (r.get("what_to_do") or [""])[0]
    return {"title": r["title"], "text": f"{r['why']} First: {first}".strip(),
            "ask": r.get("ask") or r["title"], "ask_label": "Ask About It"}


def for_view(view, code) -> list:
    from command_center.recommend import engine
    areas, rules = VIEWS.get(view, ((), set()))
    if code and code != "__all__":
        codes = [code]
    else:
        from command_center.api.businesses import loaded_codes
        codes = loaded_codes()
    recs = []
    for c in codes:
        engine.ensure_fresh(c)
        recs += engine.visible(c)
    engine.rank(recs)
    return [r for r in recs if (areas is None or r.get("area") in areas)
            and (rules is None or r.get("rule") in rules)]


def with_recommendations(view, fallback):
    def findings(ctx):
        import frappe
        boxes = BOXES.get(view, 1)
        try:
            recs = [finding(r) for r in for_view(view, ctx.code)[:boxes]]
        except Exception:
            frappe.log_error(title=f"Command Center recommendations for {view}",
                             message=frappe.get_traceback())
            recs = []
        if len(recs) >= boxes:
            return recs
        return recs + [f for f in (fallback(ctx) or []) if f][:boxes - len(recs)]
    findings.__name__ = getattr(fallback, "__name__", "findings")
    findings.fallback = fallback
    return findings


def wrap(table: dict, views=None):
    for view in list(views or table):
        if view in VIEWS and not hasattr(table[view], "fallback"):
            table[view] = with_recommendations(view, table[view])
