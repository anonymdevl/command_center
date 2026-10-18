"""Home's two lists: who owes us the most, and who buys the most.

Both read the facts, scoped to the business, and both say what they are a subset of:
the debtors are the largest five of every unpaid invoice (with the count of all of
them), the customers are the largest five of the last twelve full months of invoiced
sales, each as a share of that whole. Nothing is ranked in the browser, so the list and
the figure above it come from the same query.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Max, Min, Sum
from pypika import Order

from command_center.api.businesses import currency_for, require_manager
from command_center.facts.schema import FACTS

MODES = {
    "all": {},
    "overdue": {"days_overdue": [">", 0]},
    "over90": {"ageing_bucket": "90+"},
}


@frappe.whitelist()
def debtors(business_code: str | None = None, mode: str = "all", limit: int = 5):
    require_manager()
    if mode not in MODES:
        frappe.throw("mode is all, overdue or over90")
    limit = max(1, min(int(limit or 5), 20))
    t = frappe.qb.DocType(FACTS["fact_sales_invoice"])
    owed = Sum(t.outstanding_amount).as_("owed")
    q = (frappe.qb.from_(t)
         .select(t.customer, Count(t.name), owed, Sum(t.base_grand_total),
                 Max(t.days_overdue), Min(t.due_date))
         .where(t.outstanding_amount > 0).where(t.src_docstatus == 1))
    q = _scope(q, t, business_code)
    if mode == "overdue":
        q = q.where(t.days_overdue > 0)
    elif mode == "over90":
        q = q.where(t.ageing_bucket == "90+")
    rows = q.groupby(t.customer).orderby("owed", order=Order.desc).limit(limit).run()

    totals = _scope(frappe.qb.from_(t).select(Count(t.name), Sum(t.outstanding_amount),
                                              Count(t.customer).distinct())
                    .where(t.outstanding_amount > 0).where(t.src_docstatus == 1), t, business_code)
    if mode == "overdue":
        totals = totals.where(t.days_overdue > 0)
    elif mode == "over90":
        totals = totals.where(t.ageing_bucket == "90+")
    n_inv, n_owed, n_cust = (totals.run() or [(0, 0, 0)])[0]

    names = [r[0] for r in rows if r[0]]
    paid = _last_paid(names, business_code)
    return {
        "mode": mode, "currency": currency_for(business_code),
        "invoices": n_inv or 0, "owed": float(n_owed or 0), "customers": n_cust or 0,
        "rows": [{
            "customer": c, "invoices": n, "owed": float(o or 0), "invoiced": float(i or 0),
            "days": int(d or 0), "oldest_due": str(due) if due else None,
            "last_paid": paid.get(c),
            "drill": {"fact": "fact_sales_invoice",
                      "filters": {"customer": c, "outstanding_amount": [">", 0],
                                  "src_docstatus": 1, **MODES[mode]}},
        } for c, n, o, i, d, due in rows if c],
    }


@frappe.whitelist()
def top_customers(business_code: str | None = None, limit: int = 5):
    require_manager()
    from command_center.kpi.engine import evaluate

    limit = max(1, min(int(limit or 5), 20))
    whole = evaluate("revenue_12m", business_code)
    period = whole.get("period") or {}
    if not period.get("from") or not whole.get("value"):
        return {"currency": currency_for(business_code), "period": period, "total": 0, "rows": []}
    t = frappe.qb.DocType(FACTS["fact_sales_invoice_line"])
    q = (frappe.qb.from_(t).select(t.customer, Sum(t.base_net_amount).as_("sold"))
         .where(t.src_docstatus == 1)
         .where(t.posting_date >= period["from"]).where(t.posting_date <= period["to"]))
    rows = _scope(q, t, business_code).groupby(t.customer).orderby("sold", order=Order.desc).limit(limit).run()
    total = float(whole["value"])
    return {
        "currency": currency_for(business_code), "period": period, "total": total,
        "rows": [{"customer": c, "sold": float(v or 0), "share": round(float(v or 0) / total * 100, 1),
                  "drill": {"fact": "fact_sales_invoice_line",
                            "filters": {"customer": c, "src_docstatus": 1,
                                        "posting_date": ["between", [period["from"], period["to"]]]}}}
                 for c, v in rows if c],
    }


def _scope(q, t, business_code):
    if business_code and business_code != "__all__":
        q = q.where(t.business_code == business_code)
    return q


def _last_paid(customers, business_code):
    if not customers:
        return {}
    t = frappe.qb.DocType(FACTS["fact_payment_allocation"])
    q = (frappe.qb.from_(t).select(t.party, Max(t.posting_date))
         .where(t.party.isin(customers)).where(t.payment_type == "Receive"))
    return {p: str(d) for p, d in _scope(q, t, business_code).groupby(t.party).run() if d}
