"""Starter questions: what a director would ask first, chosen from their role and from
what the figures are saying today.

"Who owes us the most?" is a fine question on any day. "GHS 6.78M has been owed for
more than three months -- 74% of what customers owe. Who should we chase first?" is the
one worth asking today, and it teaches what the assistant can do with the business's
own numbers. So the questions offered under the bar and on the Ask AI screen are built
from the KPI engine's figures -- the same numbers as the cards, and nothing else: every
number in a starter is an engine figure, or a change between two engine figures worked
out by the analyst's own compare tool (ask/tools.compare_periods). No figure, no starter
about it: a business with nothing loaded gets the plain questions instead.

The role decides the order: a finance manager sees money owed and cash first, a sales
manager sales and orders, stock and buying people the shelves and the suppliers. Anyone
else (directors, System Managers) gets the spread. Kept for ten minutes per business and
role mix: the figures move every fifteen minutes at most.

Reads only. It calls the engine and the compare tool, both on the analyst's read path,
which preflight scans for writes.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager

KEEP = 600
MIN, MAX = 4, 6

# Words in a role's name -> the areas it cares about, in order.
ROLE_AREAS = [
    (("account", "financ", "audit", "treasur", "payroll"), ["money", "cash", "payables", "sales"]),
    (("sales", "selling", "customer", "crm"), ["sales", "money", "orders", "customers"]),
    (("stock", "purchase", "buying", "warehouse", "item", "manufactur", "supply"),
     ["stock", "orders", "suppliers", "payables"]),
    (("project", "engineer", "install"), ["projects", "orders", "cases"]),
    (("support", "service", "quality"), ["cases", "customers", "projects"]),
    (("hr", "human", "employee", "people"), ["people", "projects"]),
]
# Directors and anyone whose role names no area: the spread, most telling first.
EVERYONE = ["money", "sales", "orders", "stock", "customers", "projects", "suppliers",
            "cash", "cases", "payables", "people"]
AREA_WORDS = {"money": "Accounts Receivable", "cash": "Payments Received", "payables": "Accounts Payable",
              "sales": "Sales", "orders": "Sales Orders", "customers": "Customers",
              "stock": "Stock", "suppliers": "Buying", "projects": "Projects",
              "cases": "Customer issues", "people": "People"}
# The plain questions (ask/engine.ANALYST_EXAMPLES), by the area each belongs to.
EXAMPLE_AREAS = {"Accounts Receivable": "money", "Sales": "sales", "Buying": "suppliers",
                 "Stock": "stock", "Projects": "projects", "Customers": "customers"}

FIGURES = ["ar_over_90", "ar_over_90_pct", "largest_debt", "order_book_late_count",
           "order_book_late", "stock_short_products", "tasks_overdue", "supplier_top_share",
           "ap_over_90", "cases_over_30", "headcount", "departments"]


@frappe.whitelist()
def starters(business_code: str | None = None):
    """Four to six questions to start with, for this person and this business."""
    require_manager()
    areas = areas_for(frappe.get_roles())
    from command_center.api.businesses import scope_tag
    key = f"cc_starters::{scope_tag(business_code)}::{'.'.join(areas)}"
    cached = frappe.cache().get_value(key)
    if cached:
        return cached
    out = build(business_code, areas)
    frappe.cache().set_value(key, out, expires_in_sec=KEEP)
    return out


def areas_for(roles) -> list:
    """The areas in the order this person's roles put them."""
    order = []
    for role in roles or []:
        low = str(role).lower()
        for words, areas in ROLE_AREAS:
            if any(w in low.split() or (len(w) > 3 and w in low) for w in words):
                order += [a for a in areas if a not in order]
    return order + [a for a in EVERYONE if a not in order]


def build(business_code, areas) -> dict:
    live = {}
    try:
        live = _live(business_code)
    except Exception:
        frappe.log_error(title="Command Center starter questions", message=frappe.get_traceback())
    picked = [dict(live[a], area=AREA_WORDS[a], live=True) for a in areas if a in live][:MAX]
    if len(picked) < MIN:
        from command_center.ask.engine import ANALYST_EXAMPLES
        rank = {a: i for i, a in enumerate(areas)}
        plain = sorted(ANALYST_EXAMPLES, key=lambda e: rank.get(EXAMPLE_AREAS.get(e["area"]), 99))
        # An area the live questions already cover is offered last.
        taken = {p["area"] for p in picked}
        plain = [e for e in plain if e["area"] not in taken] + [e for e in plain if e["area"] in taken]
        for e in plain[:MIN - len(picked)]:
            picked.append({"q": e["q"], "area": e["area"], "figures": {}, "live": False})
    return {"starters": picked, "live": any(p["live"] for p in picked)}


def _live(business_code) -> dict:
    """area -> {"q", "figures"}: a question for each area whose figures say something."""
    from command_center.ask.quick import _short
    from command_center.kpi.engine import evaluate_set

    f = evaluate_set(FIGURES, business_code)

    def has(k, at_least=0):
        v = (f.get(k) or {}).get("value")
        return v is not None and v > at_least

    def w(k):
        return _short(f[k])

    out = {}
    if has("ar_over_90"):
        share = f" — {w('ar_over_90_pct')} of Accounts Receivable" if has("ar_over_90_pct") else ""
        out["money"] = _q(f"{w('ar_over_90')} of Accounts Receivable is over 90 days{share}. "
                          f"Who should we chase first?", f, "ar_over_90", "ar_over_90_pct")
    lead = (f.get("largest_debt") or {}).get("group") or {}
    if has("largest_debt") and lead.get("label"):
        out["customers"] = _q(f"{lead['label']} owes us {w('largest_debt')}, our largest receivable"
                              f". How long has it been owed, and are they paying?",
                              f, "largest_debt")
    if has("order_book_late_count"):
        n = f["order_book_late_count"]["value"]
        worth = f", with {w('order_book_late')} still to deliver" if has("order_book_late") else ""
        out["orders"] = _q(f"{w('order_book_late_count')} sales order{_s(n)} {_are(n)} past the "
                           f"promised date{worth}. Which are furthest behind, and why?",
                           f, "order_book_late_count", "order_book_late")
    if has("stock_short_products"):
        n = f["stock_short_products"]["value"]
        out["stock"] = _q(f"{w('stock_short_products')} product{_s(n)} {_are(n)} promised to "
                          f"customers but not in stock. Which orders are at risk?",
                          f, "stock_short_products")
    if has("tasks_overdue"):
        n = f["tasks_overdue"]["value"]
        out["projects"] = _q(f"{w('tasks_overdue')} job{_s(n)} {_are(n)} past {_their(n)} due "
                             f"date. Which are late, and who has them?", f, "tasks_overdue")
    top = (f.get("supplier_top_share") or {}).get("group") or {}
    if has("supplier_top_share", 25) and top.get("label"):
        out["suppliers"] = _q(f"{w('supplier_top_share')} of our supplier spend goes to "
                              f"{top['label']}. What happens if they stop supplying?",
                              f, "supplier_top_share")
    if has("ap_over_90"):
        out["payables"] = _q(f"{w('ap_over_90')} of Accounts Payable is "
                             f"over 90 days. Which Purchase Invoices, and to whom?", f, "ap_over_90")
    if has("cases_over_30"):
        n = f["cases_over_30"]["value"]
        out["cases"] = _q(f"{w('cases_over_30')} customer complaint{_s(n)} {_have(n)} waited over "
                          f"a month. Which, and why?", f, "cases_over_30")
    if has("headcount") and has("departments"):
        out["people"] = _q(f"{w('headcount')} people work here across {w('departments')} "
                           f"departments. How is that split, and who has left lately?",
                           f, "headcount", "departments")

    sales = _change("revenue_last_month", business_code)
    if sales:
        pct, cur, old, texts = sales
        if pct <= -5:
            q = f"Invoiced sales fell {abs(pct):.0f}% in {cur} against {old}. Why?"
        elif pct >= 5:
            q = f"Invoiced sales rose {pct:.0f}% in {cur} against {old}. What drove it?"
        else:
            q = (f"Invoiced sales were {texts['current']} in {cur}, much the same as {old}. "
                 f"What is selling, and to whom?")
        out["sales"] = {"q": q, "figures": texts}
    cash = _change("cash_in_month", business_code)
    if cash and cash[0] <= -10:
        pct, cur, old, texts = cash
        out["cash"] = {"q": f"Payments received fell {abs(pct):.0f}% in {cur} against {old}. "
                            f"Who has stopped paying?", "figures": texts}
    return out


def _change(key, business_code):
    """(change %, current period, earlier period, the figures as written) for a figure's
    latest full month against the month before, by the analyst's own compare tool."""
    from command_center.ask import tools
    try:
        c = tools.compare_periods(figure=key, compare="month_vs_previous",
                                  business_code=business_code)
    except tools.ToolError:
        return None
    pct = c.get("change_pct")
    if pct is None or not c["current"].get("value"):
        return None
    texts = {"current": c["current"].get("text"), "earlier": c["earlier"].get("text"),
             "change_pct": f"{abs(pct):.0f}%", "current_period": c["current"]["period"],
             "earlier_period": c["earlier"]["period"]}
    return pct, c["current"]["period"], c["earlier"]["period"], texts


def _q(text, f, *keys) -> dict:
    from command_center.ask.quick import _short
    return {"q": text, "figures": {k: _short(f[k]) for k in keys
                                   if (f.get(k) or {}).get("value") is not None}}


def _s(n):
    return "" if n == 1 else "s"


def _are(n):
    return "is" if n == 1 else "are"


def _have(n):
    return "has" if n == 1 else "have"


def _their(n):
    return "its" if n == 1 else "their"
