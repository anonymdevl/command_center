"""Check Figures: what the platform holds, line by line, against the business's ERPNext now.

    manage.py execute command_center.api.audit.reconcile --kwargs '{"business_code": "..."}'

prints the table; Settings -> Businesses -> Check Figures shows the same lines
(insights/core/platform_settings.check_figures, through figures() below).

Each line is one figure the screens rest on, worked out twice by the same rule: once
from the platform's loaded facts, once from ERPNext directly (api/ingest.source_figures,
read with the business's read-only service account, as every load is). A line that
differs says why when the records can say it -- documents changed in ERPNext since the
last load -- and says plainly when they cannot.

The ledger lines are the ones that matter most since 15 Nov 2026: what is owed is the
General Ledger's balance per party, and its total must be ERPNext's own.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Sum

from command_center.api.businesses import default_business_code, require_manager
from command_center.facts.schema import FACTS

# (key, what it is, unit, the fact it comes from, the ERPNext doctypes behind it)
LINES = (
    ("si_unpaid_count", "Unpaid Sales Invoices", "count", "fact_sales_invoice", ("Sales Invoice",)),
    ("si_unpaid_sum", "Unpaid Sales Invoices, Outstanding Amount", "money", "fact_sales_invoice",
     ("Sales Invoice",)),
    ("si_over_90", "Sales Invoice Outstanding Over 90 Days", "money", "fact_sales_invoice", ("Sales Invoice",)),
    ("customer_ledger", "Customer Ledger Balance (General Ledger)", "money", "fact_party_balance",
     ("GL Entry",)),
    ("customer_unmatched", "Unreconciled Customer Payments", "money",
     "fact_party_balance", ("Payment Entry",)),
    ("customer_unmatched_count", "Unreconciled Customer Payments, Count", "count",
     "fact_party_balance", ("Payment Entry",)),
    ("pi_unpaid_count", "Unpaid Purchase Invoices", "count", "fact_purchase_invoice",
     ("Purchase Invoice",)),
    ("pi_unpaid_sum", "Unpaid Purchase Invoices, Outstanding Amount", "money", "fact_purchase_invoice",
     ("Purchase Invoice",)),
    ("supplier_ledger", "Supplier Ledger Balance (General Ledger)", "money", "fact_party_balance",
     ("GL Entry",)),
    ("supplier_unmatched", "Unreconciled Supplier Payments", "money", "fact_party_balance",
     ("Payment Entry",)),
    ("supplier_unmatched_count", "Unreconciled Supplier Payments, Count", "count",
     "fact_party_balance", ("Payment Entry",)),
    ("si_count", "Submitted Sales Invoices", "count", "fact_sales_invoice", ("Sales Invoice",)),
    ("si_total", "Submitted Sales Invoices, Grand Total", "money", "fact_sales_invoice",
     ("Sales Invoice",)),
    ("si_net", "Sales Invoice Lines Against Net Total", "money",
     "fact_sales_invoice_line", ("Sales Invoice",)),
    ("order_book", "Open Sales Orders, Value To Deliver", "money", "fact_sales_order",
     ("Sales Order",)),
    ("order_book_count", "Open Sales Orders", "count", "fact_sales_order", ("Sales Order",)),
    ("pe_received", "Payments Received, Allocated", "money", "fact_payment_allocation",
     ("Payment Entry",)),
    ("stock_value", "Stock Value", "money", "fact_stock_balance", ("Bin",)),
    ("stock_lines", "Bin Records (Item and Warehouse)", "count", "fact_stock_balance", ("Bin",)),
    ("employees_active", "Active Employees", "count", "fact_person", ("Employee",)),
    ("tasks", "Tasks", "count", "fact_task", ("Task",)),
    ("cases", "Customer issues", "count", "fact_case", ("Issue",)),
)
# Money agrees to the cent; the ledger lines are a sum of per-party balances each kept to
# the cent, so they may differ by half a cent a party.
CENT = 0.01


def _q(fact, select, *where):
    t = frappe.qb.DocType(FACTS[fact])
    q = frappe.qb.from_(t).select(*select(t))
    for w in where:
        q = q.where(w(t))
    row = q.run()
    return row[0] if row else (None,)


def platform_figures(code: str) -> dict:
    """The same figures from the platform's loaded facts, by the screens' own rules."""
    b = lambda t: t.business_code == code  # noqa: E731
    sub = lambda t: t.src_docstatus == 1  # noqa: E731
    unpaid = lambda t: t.outstanding_amount > 0  # noqa: E731
    n = lambda v: float(v or 0)  # noqa: E731
    out = {}
    c, s = _q("fact_sales_invoice", lambda t: [Count(t.name), Sum(t.outstanding_amount)], b, sub, unpaid)
    out["si_unpaid_count"], out["si_unpaid_sum"] = int(c or 0), n(s)
    out["si_over_90"] = n(_q("fact_sales_invoice", lambda t: [Sum(t.outstanding_amount)], b, sub,
                             unpaid, lambda t: t.ageing_bucket == "90+")[0])
    c, s = _q("fact_purchase_invoice", lambda t: [Count(t.name), Sum(t.outstanding_amount)], b, sub, unpaid)
    out["pi_unpaid_count"], out["pi_unpaid_sum"] = int(c or 0), n(s)
    for party_type in ("Customer", "Supplier"):
        is_pt = lambda t, pt=party_type: t.party_type == pt  # noqa: E731
        led, um, umn, parties = _q("fact_party_balance", lambda t: [
            Sum(t.ledger_balance), Sum(t.unmatched_payments), Sum(t.unmatched_payment_count),
            Count(t.name)], b, is_pt)
        out[f"{party_type.lower()}_ledger"] = n(led)
        out[f"{party_type.lower()}_unmatched"] = n(um)
        out[f"{party_type.lower()}_unmatched_count"] = int(umn or 0)
        out[f"_{party_type.lower()}_parties"] = int(parties or 0)
    c, s = _q("fact_sales_invoice", lambda t: [Count(t.name), Sum(t.base_grand_total)], b, sub)
    out["si_count"], out["si_total"] = int(c or 0), n(s)
    out["si_net"] = n(_q("fact_sales_invoice_line", lambda t: [Sum(t.base_net_amount)], b, sub)[0])
    s, c = _q("fact_sales_order", lambda t: [Sum(t.undelivered_value), Count(t.name)], b, sub,
              lambda t: t.is_open == 1)
    out["order_book"], out["order_book_count"] = n(s), int(c or 0)
    out["pe_received"] = n(_q("fact_payment_allocation", lambda t: [Sum(t.allocated_amount)], b, sub,
                              lambda t: t.payment_type == "Receive")[0])
    s, c = _q("fact_stock_balance", lambda t: [Sum(t.stock_value), Count(t.name)], b)
    out["stock_value"], out["stock_lines"] = n(s), int(c or 0)
    out["employees_active"] = int(_q("fact_person", lambda t: [Count(t.name)], b,
                                     lambda t: t.is_active == 1)[0] or 0)
    out["tasks"] = int(_q("fact_task", lambda t: [Count(t.name)], b)[0] or 0)
    out["cases"] = int(_q("fact_case", lambda t: [Count(t.name)], b)[0] or 0)
    return out


def _loads(code) -> dict:
    """Each fact's last load, for "changed since the last load at 10:42"."""
    return {s.fact: s for s in frappe.get_all(
        "Command Center Ingest State", filters={"business_code": code},
        fields=["fact", "last_run", "status", "as_of_date"])}


def _hm(when) -> str:
    when = frappe.utils.get_datetime(when)
    today = frappe.utils.getdate(frappe.utils.today())
    return when.strftime("%H:%M") if when.date() == today else when.strftime("%-d %b %H:%M")


def figures(business_code: str | None = None) -> dict:
    """Every line: platform, ERPNext, difference, agrees, and why when it does not."""
    from command_center.api import ingest

    code = business_code or default_business_code()
    if not code:
        frappe.throw("No business is registered yet.")
    loads = _loads(code)
    inv = loads.get("fact_sales_invoice")
    as_of = frappe.utils.getdate((inv or {}).get("as_of_date") or frappe.utils.today())
    mine = platform_figures(code)
    theirs = ingest.source_figures(code, as_of)
    lines, asked = [], {}
    for key, label, unit, fact, doctypes in LINES:
        p, e = mine.get(key), theirs.get(key)
        diff = (p or 0) - (e or 0)
        tol = 0.0 if unit == "count" else CENT
        if key in ("customer_ledger", "supplier_ledger"):
            tol = max(CENT, 0.005 * mine.get(f"_{key.split('_')[0]}_parties", 0))
        ok = abs(diff) <= tol + 1e-9
        line = {"key": key, "check": label, "unit": unit, "platform": p, "erpnext": e,
                "difference": round(diff, 2), "ok": ok, "reason": ""}
        if not ok:
            state = loads.get(fact)
            if not state or not state.get("last_run"):
                line["reason"] = "Not loaded yet: reload the business, then check again."
            else:
                since = state["last_run"]
                for dt in doctypes:
                    if (dt, str(since)) not in asked:
                        asked[(dt, str(since))] = ingest.changed_since(code, [dt], since).get(dt)
                changed = sum(asked[(dt, str(since))] or 0 for dt in doctypes)
                if state.get("status") == "Failed":
                    line["reason"] = (f"The last load of these records failed ({_hm(since)}); "
                                      f"see the error log.")
                elif changed:
                    line["reason"] = (f"Changed in ERPNext since the last load at {_hm(since)} "
                                      f"({changed:,} record{'s' if changed != 1 else ''}); the "
                                      f"next load takes it in.")
                else:
                    line["reason"] = (f"Not explained by any change since the last load at "
                                      f"{_hm(since)}. A record deleted in ERPNext leaves only at "
                                      f"the weekly full reload: press Reload Everything and check "
                                      f"again. If it persists, the load is missing something.")
        lines.append(line)
    return {"business": code, "as_of": str(as_of), "checked_at": str(frappe.utils.now_datetime()),
            "all_ok": all(x["ok"] for x in lines), "lines": lines}


def _fmt(v, unit) -> str:
    if v is None:
        return "—"
    return f"{int(v):,}" if unit == "count" else f"{float(v):,.2f}"


def table(result: dict) -> str:
    """The lines as a plain table, for the command line."""
    head = ("Check", "Platform", "ERPNext", "Difference", "")
    rows = [(x["check"], _fmt(x["platform"], x["unit"]), _fmt(x["erpnext"], x["unit"]),
             _fmt(x["difference"], x["unit"]), "✓" if x["ok"] else "✗")
            for x in result["lines"]]
    w = [max(len(r[i]) for r in rows + [head]) for i in range(5)]
    out = [f"{result['business']}: figures as at {result['as_of']}, checked {result['checked_at'][:16]}",
           "  ".join(h.ljust(w[i]) if i == 0 else h.rjust(w[i]) for i, h in enumerate(head))]
    for r, x in zip(rows, result["lines"]):
        out.append("  ".join(c.ljust(w[i]) if i == 0 else c.rjust(w[i]) for i, c in enumerate(r)))
        if x["reason"]:
            out.append(" " * 4 + x["reason"])
    bad = sum(1 for x in result["lines"] if not x["ok"])
    out.append("Every line agrees." if not bad else f"{bad} of {len(result['lines'])} lines differ.")
    return "\n".join(out)


@frappe.whitelist()
def reconcile(business_code: str | None = None):
    """Print the check as a table (manage.py execute ...). Returns nothing, so the command
    line shows the table alone; figures() returns the same lines for a screen."""
    require_manager()
    print(table(figures(business_code)))
