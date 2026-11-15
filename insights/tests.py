"""The platform end to end, against a fake ERPNext:

    .venv-platform/bin/python manage.py test insights

A fake ERPNext answers the platform's API reads with plausible rows for whatever fields
it is asked for (and the parents it names), so what is under test is the whole data
path on the platform's own database: registering a business (its secret stored
encrypted), the full load of every fact (bulk writes, purges, watermarks), the figures'
cross-checks, an incremental reload, and the screens' calls through the web layer with
a signed-in manager. What it cannot test is a real ERPNext's answers -- those are
checked on the server against Gigmann's live site.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import random
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TransactionTestCase

TODAY = dt.date.today()
N = 60
# The department screens: every figure, panel and finding on them is the business's own.
DEPARTMENT_VIEWS = ("sales", "proc", "inv", "eng", "cx", "fin", "hr")


class _R:
    def __init__(self, status, body):
        self.status_code, self._body, self.ok, self.headers = status, body, 200 <= status < 300, {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _value(field: str, i: int, doctype: str):
    rnd = random.Random(f"{doctype}:{field}:{i}")
    f = field.lower()
    if f in ("name",):
        return f"{''.join(w[0] for w in doctype.split())}-{i:05d}"
    if f in ("modified", "creation"):
        return (dt.datetime.now() - dt.timedelta(days=rnd.randint(0, 300))).strftime("%Y-%m-%d %H:%M:%S.%f")
    if f == "docstatus":
        return 1
    if f in ("resolution_by", "response_by", "last_active", "last_login"):
        return (dt.datetime.now() - dt.timedelta(days=rnd.randint(-20, 200))).strftime("%Y-%m-%d %H:%M:%S")
    if "date" in f or "deadline" in f or f in ("exp_end_date", "completed_on", "opening_date",
                                                "completion_by"):
        return str(TODAY - dt.timedelta(days=rnd.randint(-30, 300)))
    if f in ("is_stock_item",):
        return 1
    if f.endswith("exchange_rate") or f == "conversion_factor":
        return 1.0
    if f in ("sales_order", "against_sales_order"):
        return f"SO-{rnd.randint(0, N - 1):05d}"
    if f == "purchase_order":
        return f"PO-{rnd.randint(0, N - 1):05d}"
    if f.startswith(("is_", "has_")) or f in ("enabled", "disabled", "is_return"):
        return 0
    if f.startswith("per_"):
        return rnd.choice([0, 50, 100])
    if any(k in f for k in ("amount", "total", "value", "rate", "qty", "outstanding",
                            "paid", "allocated", "cost", "price", "valuation")):
        return round(rnd.uniform(100, 20000), 2)
    if f in ("status",):
        return rnd.choice({"Sales Invoice": ["Unpaid", "Overdue", "Paid"],
                           "Purchase Invoice": ["Unpaid", "Overdue", "Paid"],
                           "Sales Order": ["To Deliver and Bill", "To Bill", "Completed"],
                           "Task": ["Open", "Working", "Completed", "Overdue"],
                           "Issue": ["Open", "Replied", "Closed"],
                           "Employee": ["Active"]}.get(doctype, ["Open"]))
    if f in ("customer", "party") or "customer" in f:
        return rnd.choice(["Ubuntu Ltd", "Ejura Clinic", "Korle Bu", "Ridge Hospital"])
    if "supplier" in f:
        return rnd.choice(["Min-Medical", "CT Consult", "Chunjee"])
    if "item" in f:
        return rnd.choice(["ITM-001", "ITM-002", "ITM-003"])
    if "warehouse" in f:
        return rnd.choice(["Stores - GMS", "Kumasi - GMS"])
    if f in ("company",):
        return "Test Medical Ltd"
    if "currency" in f:
        return "GHS"
    if f in ("party_type",):
        return "Customer"
    if f in ("payment_type",):
        return "Receive"
    if f in ("reference_doctype", "against_doctype"):
        return "Sales Invoice"
    if f in ("reference_name", "against_name"):
        return f"SI-{rnd.randint(0, N - 1):05d}"
    if "user" in f or "owner" in f or "email" in f or f == "assigned_to" or f == "_assign":
        return "clerk@test.com"
    if f in ("priority",):
        return rnd.choice(["Low", "Medium", "High"])
    if f.endswith("_days") or f in ("days",):
        return rnd.randint(0, 120)
    return f"{field}-{rnd.randint(1, 5)}"


# The fake's ledger, so the ledger balances, their explanation and the matched ageing are
# exercised on numbers that mean something: per party and kind of entry, (debit, credit).
# Ridge Hospital paid more than it was billed and is in credit.
LEDGER = {
    ("Customer", "Ubuntu Ltd"): {"Sales Invoice": (90000, 2000), "Payment Entry": (0, 61000),
                                 "Journal Entry": (5000, 1000)},
    ("Customer", "Ejura Clinic"): {"Sales Invoice": (40000, 0), "Payment Entry": (0, 15000)},
    ("Customer", "Korle Bu"): {"Sales Invoice": (25000, 0), "Journal Entry": (7000, 0)},
    ("Customer", "Ridge Hospital"): {"Sales Invoice": (10000, 0), "Payment Entry": (0, 13000)},
    ("Supplier", "Min-Medical"): {"Purchase Invoice": (0, 70000), "Payment Entry": (52000, 0),
                                  "Journal Entry": (0, 3000)},
    ("Supplier", "CT Consult"): {"Purchase Invoice": (0, 12000), "Payment Entry": (12000, 0)},
}
# Payments never matched (party_type, party, payment_type, amount), and journal lines
# (party_type, party, debit, credit, reference_type).
UNMATCHED = [("Customer", "Ubuntu Ltd", "Receive", 20000), ("Customer", "Ridge Hospital", "Receive", 3000),
             ("Supplier", "Min-Medical", "Pay", 30000)]
JOURNALS = [("Customer", "Ubuntu Ltd", 5000, 0, None), ("Customer", "Ubuntu Ltd", 0, 1000, None),
            ("Customer", "Korle Bu", 7000, 0, None), ("Supplier", "Min-Medical", 0, 3000, None)]


# The fake's chart of accounts and its four financial statements, shaped as ERPNext 14
# answers frappe.desk.query_report.run (checked against Gigmann's live site, 15 Nov 2026):
# account rows with parent_account, indent, account_type, is_group and one key per period;
# each side's total row (no indent); a blank row; the profit or provisional line quoted.
# Per month: income 12,000 (sales 10,000, services 2,000), cost of goods 7,000 (purchases
# 6,000; freight 1,000, an expense account inside the cost-of-goods group), other expenses
# 3,000 -- gross profit 5,000, net profit 2,000. A year earlier every flow is 80% of that.
CHART = [  # account, parent, root type, account type, is group, per month or balances
    ("Income - TML", "", "Income", "", 1, None),
    ("Sales - TML", "Income - TML", "Income", "Income Account", 0, 10000),
    ("Service Income - TML", "Income - TML", "Income", "Income Account", 0, 2000),
    ("Expenses - TML", "", "Expense", "", 1, None),
    ("Cost of Goods Sold - TML", "Expenses - TML", "Expense", "Cost of Goods Sold", 1, None),
    ("Purchases - TML", "Cost of Goods Sold - TML", "Expense", "Cost of Goods Sold", 0, 6000),
    ("Freight - TML", "Cost of Goods Sold - TML", "Expense", "Expense Account", 0, 1000),
    ("Indirect Expenses - TML", "Expenses - TML", "Expense", "", 1, None),
    ("Salaries - TML", "Indirect Expenses - TML", "Expense", "Expense Account", 0, 2500),
    ("Rent - TML", "Indirect Expenses - TML", "Expense", "Expense Account", 0, 500),
    # balances: (as at the last period, as at the earlier ones)
    ("Application of Funds (Assets) - TML", "", "Asset", "", 1, None),
    ("Current Assets - TML", "Application of Funds (Assets) - TML", "Asset", "", 1, None),
    ("Debtors - TML", "Current Assets - TML", "Asset", "Receivable", 0, (30000, 30000)),
    ("Bank - TML", "Current Assets - TML", "Asset", "Bank", 0, (20000, 18000)),
    ("Stock In Hand - TML", "Current Assets - TML", "Asset", "Stock", 0, (10000, 10000)),
    ("Fixed Assets - TML", "Application of Funds (Assets) - TML", "Asset", "", 1, None),
    ("Equipment - TML", "Fixed Assets - TML", "Asset", "Fixed Asset", 0, (40000, 40000)),
    ("Source of Funds (Liabilities) - TML", "", "Liability", "", 1, None),
    ("Current Liabilities - TML", "Source of Funds (Liabilities) - TML", "Liability", "", 1, None),
    ("Creditors - TML", "Current Liabilities - TML", "Liability", "Payable", 0, (25000, 23000)),
    ("Long Term Loans - TML", "Source of Funds (Liabilities) - TML", "Liability", "", 0, (15000, 15000)),
    ("Equity - TML", "", "Equity", "", 1, None),
    ("Capital Stock - TML", "Equity - TML", "Equity", "Equity", 0, (50000, 50000)),
]
PROVISIONAL = 10000  # assets 100,000 = liabilities 40,000 + equity 50,000 + 10,000
FS_SCRIPT = ('frappe.require("assets/erpnext/js/financial_statements.js", function() {\n'
             '  frappe.query_reports["X"] = $.extend({}, erpnext.financial_statements);\n'
             '  frappe.query_reports["X"]["filters"].push({"fieldname": "include_default_book_entries",'
             ' "fieldtype": "Check", "default": 1});\n});')
TB_SCRIPT = ("frappe.query_reports['Trial Balance'] = {filters: [" + ", ".join(
    f'{{"fieldname": "{f}"}}' for f in (
        "company", "fiscal_year", "from_date", "to_date", "cost_center", "project", "finance_book",
        "presentation_currency", "with_period_closing_entry", "show_zero_values",
        "show_unclosed_fy_pl_balances", "include_default_book_entries", "show_net_values")) + "]}")


def _month_keys(a: dt.date, b: dt.date, periodicity: str):
    """ERPNext's period columns for a date range: (fieldname, label, months in it)."""
    months = []
    d = a.replace(day=1)
    while d <= b:
        months.append(d)
        d = (d + dt.timedelta(days=32)).replace(day=1)
    if periodicity == "Monthly":
        return [(m.strftime("%b_%Y").lower(), m.strftime("%b %Y"), 1) for m in months]
    return [(b.strftime("%b_%Y").lower(), str(b.year), len(months))]


def fake_statement(report: str, f: dict) -> dict:
    if report == "Trial Balance":
        return _fake_tb(f)
    a = dt.date.fromisoformat(f.get("period_start_date"))
    b = dt.date.fromisoformat(f.get("period_end_date"))
    cols = _month_keys(a, b, f.get("periodicity") or "Yearly")
    scale = 0.8 if b.year < TODAY.year else 1.0
    columns = [{"fieldname": "account", "label": "Account", "fieldtype": "Link"},
               {"fieldname": "currency", "label": "Currency", "fieldtype": "Link", "hidden": 1}] + [
        {"fieldname": k, "label": lab, "fieldtype": "Currency"} for k, lab, _ in cols]
    if report == "Cash Flow":
        return {"columns": columns, "result": _fake_cf(cols, scale), "message": None}
    balance = report == "Balance Sheet"
    sides = ("Asset", "Liability", "Equity") if balance else ("Income", "Expense")
    by = {name: (parent, rt, at, g, v) for name, parent, rt, at, g, v in CHART}

    def amount(name, i):
        parent, rt, at, g, v = by[name]
        if g:
            return sum(amount(c, i) for c, (p, *_r) in by.items() if p == name)
        if balance:
            return v[0] if i == len(cols) - 1 else v[1]
        return v * cols[i][2] * scale

    def depth(name):
        return 0 if not by[name][0] else 1 + depth(by[name][0])
    out = []
    for side in sides:
        names = [n for n, (p, rt, *_r) in by.items() if rt == side]
        for n in names:
            parent, rt, at, g, v = by[n]
            row = {"account": n, "parent_account": parent, "indent": depth(n),
                   "account_name": n.rsplit(" - ", 1)[0], "account_type": at, "is_group": g,
                   "include_in_gross": 0, "currency": "GHS", "opening_balance": 0, "has_value": True}
            for i, (k, _l, _m) in enumerate(cols):
                row[k] = amount(n, i)
            # ERPNext's own "total" adds the periods, which means nothing on a balance sheet
            row["total"] = sum(row[k] for k, _l, _m in cols)
            out.append(row)
        label = f"Total {side} ({'Debit' if side in ('Asset', 'Expense') else 'Credit'})"
        tot = {"account_name": label, "account": label, "currency": "GHS"}
        for i, (k, _l, _m) in enumerate(cols):
            tot[k] = sum(amount(r, i) for r in names if not by[r][0])
        out += [tot, {}]
    last = {"currency": "GHS", "warn_if_negative": True}
    name = "'Provisional Profit / Loss (Credit)'" if balance else "'Profit for the year'"
    last.update(account_name=name, account=name)
    for i, (k, _l, _m) in enumerate(cols):
        last[k] = PROVISIONAL if balance else amount("Income - TML", i) - amount("Expenses - TML", i)
    out.append(last)
    return {"columns": columns, "result": out, "message": None, "report_summary": [],
            "add_total_row": 0}


def _fake_cf(cols, scale):
    """ERPNext 14's own cash flow: a header per section, its lines, a quoted total."""
    out = []
    lines = {"Operations": [("'Profit for the year'", 2000), ("Net Change in Accounts Receivable", -1000)],
             "Investing": [("Net Change in Fixed Asset", -3000)],
             "Financing": [("Net Change in Equity", 500)]}
    for section, items in lines.items():
        head = f"Cash Flow from {section}"
        out.append({"account_name": head, "parent_account": None, "indent": 0.0, "account": head})
        total = {"account_name": f"'Net Cash from {section}'", "account": f"'Net Cash from {section}'",
                 "currency": "GHS"}
        for label, per in items:
            row = {"account_name": label, "account": label, "indent": 1, "parent_account": head,
                   "currency": "GHS", "total": -123}  # a wrong own total: never read
            for k, _l, m in cols:
                row[k] = per * m * scale
                total[k] = total.get(k, 0) + row[k]
            out.append(row)
        out += [total, {}]
    change = {"account_name": "'Net Change in Cash'", "account": "'Net Change in Cash'", "currency": "GHS"}
    for k, _l, m in cols:
        change[k] = -1500 * m * scale
    return out + [change, {}]


def _fake_tb(f):
    """Balanced: opening 98,000 a side; the period's 12,000 a month of income against 10,000
    of expenses, through the bank."""
    m = len(_month_keys(dt.date.fromisoformat(f["from_date"]), dt.date.fromisoformat(f["to_date"]),
                        "Monthly"))
    K = ("opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit")
    rows = []
    for name, parent, indent, v in (
            ("Application of Funds (Assets) - TML", None, 0, (98000, 0, 12000 * m, 10000 * m, 98000 + 2000 * m, 0)),
            ("Bank - TML", "Application of Funds (Assets) - TML", 1, (98000, 0, 12000 * m, 10000 * m, 98000 + 2000 * m, 0)),
            ("Source of Funds (Liabilities) - TML", None, 0, (0, 38000, 0, 0, 0, 38000)),
            ("Creditors - TML", "Source of Funds (Liabilities) - TML", 1, (0, 38000, 0, 0, 0, 38000)),
            ("Equity - TML", None, 0, (0, 60000, 0, 0, 0, 60000)),
            ("Capital Stock - TML", "Equity - TML", 1, (0, 60000, 0, 0, 0, 60000)),
            ("Income - TML", None, 0, (0, 0, 0, 12000 * m, 0, 12000 * m)),
            ("Sales - TML", "Income - TML", 1, (0, 0, 0, 12000 * m, 0, 12000 * m)),
            ("Expenses - TML", None, 0, (0, 0, 10000 * m, 0, 10000 * m, 0)),
            ("Salaries - TML", "Expenses - TML", 1, (0, 0, 10000 * m, 0, 10000 * m, 0))):
        rows.append({"account": name, "parent_account": parent, "indent": indent,
                     "account_name": name.rsplit(" - ", 1)[0], "currency": "GHS",
                     "has_value": True, **dict(zip(K, v))})
    total = {"account": "'Total'", "account_name": "'Total'", "parent_account": None, "indent": 0,
             "warn_if_negative": True, "currency": "GHS",
             **{k: sum(r[k] for r in rows if r["indent"] == 0) for k in K}}
    return {"columns": [{"fieldname": k, "label": k, "fieldtype": "Currency"} for k in K],
            "result": rows + [{}, total], "message": None}


def _wanted(filters, field, value) -> bool:
    rule = (filters or {}).get(field) if isinstance(filters, dict) else None
    if rule is None:
        return True
    if isinstance(rule, list) and rule and rule[0] in ("in", "not in"):
        return (value in rule[1]) == (rule[0] == "in")
    return value == rule


class FakeERPNext:
    """GET/POST /api/method/frappe.client.* and the few others the platform calls."""

    def __init__(self, hr=None):
        self.calls = []
        # People and leave (api/people.py): with an HR set (hr_dataset), the HR doctypes
        # are answered from it -- filtered, paged and counted as ERPNext would -- and
        # every read of them is kept in hr_reads as (doctype, fields).
        self.hr = hr
        self.hr_reads = []
        self.reports = []
        self.fiscal_years = True

    def __call__(self, method_name):
        def call(url, headers=None, params=None, data=None, json=None, timeout=None):
            body = json if json is not None else (data if data is not None else params) or {}
            m = url.split("/api/method/", 1)[1]
            self.calls.append(m)
            return self.answer(m, body)
        return call

    def answer(self, m, p):
        if m == "frappe.desk.query_report.get_script":
            name = p.get("report_name")
            return _R(200, {"message": {"script": TB_SCRIPT if name == "Trial Balance" else FS_SCRIPT,
                                        "filters": []}})
        if m == "frappe.desk.query_report.run":
            f = p.get("filters") or {}
            f = json.loads(f) if isinstance(f, str) else f
            self.reports.append((p.get("report_name"), f))
            return _R(200, {"message": fake_statement(p.get("report_name"), f)})
        if m == "frappe.auth.get_logged_user":
            return _R(200, {"message": "reader@test.com"})
        if self.hr is not None and p.get("doctype") in HR_DOCTYPES and m in (
                "frappe.client.get_count", "frappe.client.get_list"):
            return self.hr_answer(m, p)
        if m == "frappe.client.get_count":
            return _R(200, {"message": N})
        if m in ("frappe.client.get_list",):
            return _R(200, {"message": self.rows(p)})
        if m == "frappe.desk.form.load.getdoctype":
            doc = {"name": p.get("doctype"), "fields": []}
            if p.get("doctype") == "Version":
                # ERPNext's own rules for the change log: System Manager reads, nobody deletes
                doc["permissions"] = [{"role": "System Manager", "read": 1, "delete": 0}]
            return _R(200, {"docs": [doc]})
        return _R(200, {"message": {}})

    def ledger(self, doctype, fields, filters, group_by, start, n):
        """The ledger, the unmatched payments and the journal lines, from LEDGER above:
        grouped sums for the General Ledger, plain rows for the rest."""
        if doctype == "GL Entry":
            groups = [g.strip() for g in (group_by or "").split(",") if g.strip()]
            sums = {}
            for (pt, party), kinds in LEDGER.items():
                if not _wanted(filters, "party_type", pt):
                    continue
                for vt, (d, c) in kinds.items():
                    row = {"party_type": pt, "party": party, "voucher_type": vt, "docstatus": 1}
                    key = tuple(row[g] for g in groups)
                    got = sums.setdefault(key, {g: row[g] for g in groups} | {"d": 0, "c": 0})
                    got["d"] += d
                    got["c"] += c
            out = []
            for got in sums.values():
                row = {g: got[g] for g in groups}
                for f in fields:
                    m = re.match(r"\s*sum\((debit|credit)\)\s+as\s+(\w+)", str(f))
                    if m:
                        row[m.group(2)] = got["d" if m.group(1) == "debit" else "c"]
                out.append(row)
            return out
        if doctype == "Payment Entry":
            rows = [{"name": f"PE-U-{i:03d}", "party_type": pt, "party": party, "payment_type": ptype,
                     "posting_date": str(TODAY - dt.timedelta(days=40 + 10 * i)),
                     "unallocated_amount": amt, "source_exchange_rate": 1, "target_exchange_rate": 1,
                     "docstatus": 1}
                    for i, (pt, party, ptype, amt) in enumerate(UNMATCHED)
                    if _wanted(filters, "party_type", pt) and _wanted(filters, "payment_type", ptype)]
            if group_by:
                return [{"docstatus": 1, **{re.split(r"\s+as\s+", f)[-1]: sum(
                    r["unallocated_amount"] for r in rows) for f in fields if " as " in str(f)}}]
            return rows[start:start + n]
        rows = [{"name": f"JEA-{i:03d}", "parent": f"JE-{i:03d}", "party_type": pt, "party": party,
                 "debit": d, "credit": c, "reference_type": ref, "reference_name": None}
                for i, (pt, party, d, c, ref) in enumerate(JOURNALS)
                if _wanted(filters, "party_type", pt)]
        return rows[start:start + n]

    def rows(self, p):
        doctype = p.get("doctype")
        fields = p.get("fields") or ["name"]
        fields = json.loads(fields) if isinstance(fields, str) else fields
        filters = p.get("filters") or {}
        filters = json.loads(filters) if isinstance(filters, str) else filters
        start = int(p.get("limit_start") or 0)
        n = int(p.get("limit_page_length") or 20)
        if isinstance(filters, dict) and (
                (doctype == "GL Entry" and "party_type" in str(p.get("group_by") or ""))
                or (doctype == "Payment Entry" and "unallocated_amount" in filters)
                or doctype == "Journal Entry Account"):
            return self.ledger(doctype, fields, filters, p.get("group_by"), start, n)
        if doctype == "Company":
            return [{"name": "Test Medical Ltd", "default_currency": "GHS"}][:n]
        if doctype == "Fiscal Year":
            return [{"name": str(y), "year_start_date": f"{y}-01-01", "year_end_date": f"{y}-12-31"}
                    for y in range(TODAY.year - 3, TODAY.year + 1)] if self.fiscal_years else []
        if doctype == "Account" and "root_type" in fields:
            return [{"name": a, "parent_account": p or None, "root_type": rt, "account_type": at,
                     "is_group": g} for a, p, rt, at, g, _v in CHART][start:start + n]
        parents = names = None
        if isinstance(filters, dict):
            if isinstance(filters.get("parent"), list) and filters["parent"][0] == "in":
                parents = filters["parent"][1]
            if isinstance(filters.get("name"), list) and filters["name"][0] == "in":
                names = filters["name"][1]
            ds = filters.get("docstatus")
            if ds == 2 or (isinstance(ds, list) and ds[0] in ("=", "in") and 2 in (
                    ds[1] if isinstance(ds[1], list) else [ds[1]])):
                return []  # the cancellation sweep: nothing was cancelled
        out = []
        cols = [re.split(r"\s+as\s+", str(f))[-1].strip() for f in fields]
        if names is not None:
            idxs = [int(x.split("-")[-1]) for x in names if x.split("-")[-1].isdigit()]
        elif parents is not None:
            idxs = list(range(len(parents)))
        else:
            idxs = list(range(start, min(start + n, N)))
        for i in idxs:
            row = {c: _value(c, i, doctype) for c in cols}
            if names is not None and "name" in cols:
                row["name"] = names[idxs.index(i)]
            if parents is not None:
                row["parent"] = parents[i]
                row["name"] = f"row-{doctype[:4]}-{i}"
            out.append(row)
        return out[:n]


    def hr_answer(self, m, p):
        doctype = p["doctype"]
        if not self.hr.get("installed", True) and doctype in HRMS_DOCTYPES:
            return _R(404, {"exc_type": "DoesNotExistError",
                            "_server_messages": json.dumps([json.dumps(
                                {"message": f"DocType {doctype} not found"})])})
        filters = p.get("filters") or {}
        filters = json.loads(filters) if isinstance(filters, str) else filters
        rows = [r for r in self.hr.get(doctype, []) if _hr_match(r, filters)]
        if m == "frappe.client.get_count":
            return _R(200, {"message": len(rows)})
        fields = p.get("fields") or ["name"]
        fields = json.loads(fields) if isinstance(fields, str) else fields
        self.hr_reads.append((doctype, list(fields)))
        start = int(p.get("limit_start") or 0)
        n = int(p.get("limit_page_length") or 20)
        cols = [re.split(r"\s+as\s+", str(f))[-1].strip() for f in fields]
        return _R(200, {"message": [{c: r.get(c) for c in cols} for r in rows[start:start + n]]})


# Doctypes the HR set answers; those that only exist with the HR app (HRMS) installed.
HR_DOCTYPES = {"Employee", "Leave Type", "Leave Allocation", "Leave Application",
               "Leave Ledger Entry", "Attendance", "Holiday", "Holiday List", "ToDo",
               "Appraisal", "Training Event", "Training Event Employee", "Asset",
               "Salary Slip", "Salary Structure Assignment"}
HRMS_DOCTYPES = HR_DOCTYPES - {"Employee", "ToDo", "Asset", "Holiday", "Holiday List"}


def _hr_cmp(a, b):
    try:
        return float(a), float(b)
    except (TypeError, ValueError):
        return str(a if a is not None else ""), str(b if b is not None else "")


def _hr_match(row, filters) -> bool:
    for field, rule in (filters.items() if isinstance(filters, dict) else
                        ((f[-3], f[-2:]) for f in filters)):
        op, val = (rule[0], rule[1]) if isinstance(rule, list) and len(rule) == 2 \
            and isinstance(rule[0], str) and rule[0] in (
                "=", "!=", "<", "<=", ">", ">=", "in", "not in", "between", "is", "like") \
            else ("=", rule)
        v = row.get(field)
        if op == "in" and v not in val:
            return False
        if op == "not in" and v in val:
            return False
        if op == "between" and not (_hr_cmp(val[0], v)[0] <= _hr_cmp(val[0], v)[1]
                                     and _hr_cmp(v, val[1])[0] <= _hr_cmp(v, val[1])[1]):
            return False
        if op == "is" and (val == "set") != bool(v):
            return False
        if op in ("=", "!=", "<", "<=", ">", ">="):
            a, b = _hr_cmp(v, val)
            ok = {"=": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b,
                  ">=": a >= b}[op]
            if not ok:
                return False
    return True


def _day(n):
    return str(TODAY + dt.timedelta(days=n))


def hr_dataset(installed=True, allocations=True) -> dict:
    """A small business's people and leave, with dates around today.

    The hand-worked leave (LeaveArithmetic), with P = the leave period in force, from 100
    days ago to 200 days ahead, and HL a holiday list holding two dates:

      Ama Mensah, Annual Leave: 20 new + 3 carried forward = 23 allocated. Taken: 5 days
        on a seven-day application with HL's two holidays inside it; 1.5 days with a half
        day; a five-day application that began two days before P, of which three days
        fall inside it; and 1 day encashed = 10.5. An expired entry from her last
        allocation is ignored. Remaining 23 - 10.5 = 12.5. Pending: an Open application
        for 2 days. Sick Leave: 5 allocated, none taken, 1 day pending.
      Kofi Boateng, Annual Leave: 10 new + 4 carried forward whose carry-forward expired
        thirty days into P, after he had taken 3 days. HRMS then keeps the new leave
        only: remaining 10, taken 3, expired 14 - (10 + 3) = 1.
      Esi Owusu: active, no leave allocated. Yaw Darko: has left.
    """
    p_from, p_to = _day(-100), _day(200)
    hl = "HL"
    emp = [
        {"name": "HR-EMP-001", "employee_name": "Ama Mensah", "status": "Active",
         "department": "Sales", "designation": "Sales Lead", "branch": "North",
         "employment_type": "Full-time", "date_of_joining": _day(-800), "relieving_date": None,
         "reports_to": "HR-EMP-002", "company_email": "ama@test.example", "cell_number": "0200000001",
         "user_id": "ama@test.example", "image": "/files/ama.jpg", "holiday_list": hl,
         "company": "Test Medical Ltd", "ctc": 99999.5, "bank_ac_no": "0123456789",
         "salary_mode": "Bank", "date_of_birth": "1990-01-01"},
        {"name": "HR-EMP-002", "employee_name": "Kofi Boateng", "status": "Active",
         "department": "Stores", "designation": "Store Manager", "branch": "South",
         "employment_type": "Full-time", "date_of_joining": _day(-2000), "relieving_date": None,
         "reports_to": None, "company_email": None, "cell_number": None, "user_id": None,
         "image": "/private/files/kofi.jpg", "holiday_list": hl, "company": "Test Medical Ltd",
         "ctc": 88888.25, "bank_ac_no": "9876543210"},
        {"name": "HR-EMP-003", "employee_name": "Esi Owusu", "status": "Active",
         "department": "Sales", "designation": "Sales Officer", "branch": "North",
         "employment_type": "Intern", "date_of_joining": _day(-40), "relieving_date": None,
         "reports_to": "HR-EMP-001", "company_email": None, "cell_number": None, "user_id": None,
         "image": None, "holiday_list": hl, "company": "Test Medical Ltd"},
        {"name": "HR-EMP-004", "employee_name": "Yaw Darko", "status": "Left",
         "department": "Stores", "designation": "Driver", "branch": "South",
         "employment_type": "Full-time", "date_of_joining": _day(-900),
         "relieving_date": _day(-30), "reports_to": "HR-EMP-002", "company_email": None,
         "cell_number": None, "user_id": None, "image": None, "holiday_list": hl,
         "company": "Test Medical Ltd"},
    ]
    if not installed:
        return {"installed": False, "Employee": emp}

    def led(name, e, lt, kind, tn, leaves, frm, to, cf=0, expired=0):
        return {"name": name, "employee": e, "leave_type": lt, "transaction_type": kind,
                "transaction_name": tn, "leaves": leaves, "from_date": frm, "to_date": to,
                "is_carry_forward": cf, "is_expired": expired, "is_lwp": 0, "holiday_list": hl,
                "docstatus": 1}
    A, L, ENC = "Leave Allocation", "Leave Application", "Leave Encashment"
    allocs = [
        {"name": "LA-1", "employee": "HR-EMP-001", "leave_type": "Annual Leave",
         "from_date": p_from, "to_date": p_to, "docstatus": 1},
        {"name": "LA-2", "employee": "HR-EMP-001", "leave_type": "Sick Leave",
         "from_date": p_from, "to_date": p_to, "docstatus": 1},
        {"name": "LA-3", "employee": "HR-EMP-002", "leave_type": "Annual Leave",
         "from_date": p_from, "to_date": p_to, "docstatus": 1},
        {"name": "LA-0", "employee": "HR-EMP-001", "leave_type": "Annual Leave",
         "from_date": _day(-465), "to_date": _day(-101), "docstatus": 1},
    ] if allocations else []
    ledger = [
        led("LLE-01", "HR-EMP-001", "Annual Leave", A, "LA-1", 20, p_from, p_to),
        led("LLE-02", "HR-EMP-001", "Annual Leave", A, "LA-1", 3, p_from, p_to, cf=1),
        led("LLE-03", "HR-EMP-001", "Annual Leave", L, "LAP-1", -5, _day(-60), _day(-54)),
        led("LLE-04", "HR-EMP-001", "Annual Leave", L, "LAP-2", -1.5, _day(-30), _day(-29)),
        led("LLE-05", "HR-EMP-001", "Annual Leave", L, "LAP-3", -5, _day(-102), _day(-98)),
        led("LLE-06", "HR-EMP-001", "Annual Leave", ENC, "ENC-1", -1, _day(-20), _day(-20)),
        led("LLE-07", "HR-EMP-001", "Annual Leave", A, "LA-0", 20, _day(-465), _day(-101)),
        led("LLE-08", "HR-EMP-001", "Annual Leave", A, "LA-0", -2, _day(-101), _day(-101),
            expired=1),
        led("LLE-09", "HR-EMP-001", "Sick Leave", A, "LA-2", 5, p_from, p_to),
        led("LLE-10", "HR-EMP-002", "Annual Leave", A, "LA-3", 10, p_from, p_to),
        led("LLE-11", "HR-EMP-002", "Annual Leave", A, "LA-3", 4, p_from, _day(-70), cf=1),
        led("LLE-12", "HR-EMP-002", "Annual Leave", L, "LAP-4", -3, _day(-95), _day(-93)),
    ] if allocations else []

    def app(name, e, who, lt, frm, to, days, status, docstatus, posted, half=0, hd=None):
        return {"name": name, "employee": e, "employee_name": who, "leave_type": lt,
                "from_date": frm, "to_date": to, "total_leave_days": days, "half_day": half,
                "half_day_date": hd, "status": status, "docstatus": docstatus,
                "posting_date": posted, "leave_approver": "boss@test.example",
                "leave_approver_name": "The Boss", "department": None,
                "description": "a private reason never shown"}
    apps = [
        app("LAP-1", "HR-EMP-001", "Ama Mensah", "Annual Leave", _day(-60), _day(-54), 5,
            "Approved", 1, _day(-70)),
        app("LAP-2", "HR-EMP-001", "Ama Mensah", "Annual Leave", _day(-30), _day(-29), 1.5,
            "Approved", 1, _day(-35), half=1, hd=_day(-29)),
        app("LAP-3", "HR-EMP-001", "Ama Mensah", "Annual Leave", _day(-102), _day(-98), 5,
            "Approved", 1, _day(-110)),
        app("LAP-4", "HR-EMP-002", "Kofi Boateng", "Annual Leave", _day(-95), _day(-93), 3,
            "Approved", 1, _day(-99)),
        app("LAP-5", "HR-EMP-001", "Ama Mensah", "Annual Leave", _day(10), _day(11), 2,
            "Open", 0, _day(-4)),
        app("LAP-6", "HR-EMP-001", "Ama Mensah", "Sick Leave", _day(3), _day(3), 1,
            "Open", 0, _day(-1)),
        app("LAP-7", "HR-EMP-003", "Esi Owusu", "Leave Without Pay", _day(0), _day(0), 1,
            "Approved", 1, _day(-2)),
        app("LAP-8", "HR-EMP-001", "Ama Mensah", "Annual Leave", _day(-300), _day(-299), 2,
            "Cancelled", 2, _day(-305)),
    ]
    return {
        "installed": True, "Employee": emp,
        "Leave Type": [{"name": "Annual Leave", "include_holiday": 0, "is_lwp": 0},
                       {"name": "Sick Leave", "include_holiday": 0, "is_lwp": 0},
                       {"name": "Leave Without Pay", "include_holiday": 1, "is_lwp": 1}],
        "Leave Allocation": allocs, "Leave Ledger Entry": ledger, "Leave Application": apps,
        "Holiday List": [{"name": hl}],
        "Holiday": [{"name": "H-1", "parent": hl, "holiday_date": _day(-58)},
                    {"name": "H-2", "parent": hl, "holiday_date": _day(-57)},
                    {"name": "H-3", "parent": hl, "holiday_date": _day(-200)}],
        "Attendance": [{"name": f"ATT-{i}", "employee": "HR-EMP-001", "docstatus": 1,
                        "attendance_date": str(TODAY.replace(day=1) + dt.timedelta(days=i)),
                        "status": "Present" if i else "Absent", "late_entry": 1 if i == 1 else 0,
                        "early_exit": 0} for i in range(min(3, TODAY.day))],
        "ToDo": [{"name": "TD-1", "allocated_to": "ama@test.example", "status": "Open",
                  "description": "<p>Call <b>Ridge Hospital</b> about the order</p>",
                  "reference_type": "Sales Order", "reference_name": "SO-00001",
                  "date": _day(2), "priority": "High"}],
        "Appraisal": [{"name": "APR-1", "employee": "HR-EMP-001", "start_date": _day(-365),
                       "end_date": _day(-1), "status": "Completed", "docstatus": 1,
                       "final_score": 4.2, "total_score": None}],
        "Training Event": [{"name": "TE-1", "event_name": "Equipment Safety",
                            "start_time": _day(-50) + " 09:00:00", "docstatus": 1}],
        "Training Event Employee": [{"name": "TEE-1", "parent": "TE-1",
                                     "employee": "HR-EMP-001", "status": "Completed",
                                     "attendance": "Present"}],
        "Asset": [{"name": "AST-1", "asset_name": "Laptop", "custodian": "HR-EMP-001",
                   "status": "In Location", "location": "Head Office", "docstatus": 1,
                   "gross_purchase_amount": 7777.77}],
        "Salary Slip": [{"name": "SS-1", "employee": "HR-EMP-001", "docstatus": 1,
                         "start_date": _day(-45), "end_date": _day(-15), "gross_pay": 4321.0,
                         "net_pay": 3210.0}],
        "Salary Structure Assignment": [{"name": "SSA-1", "employee": "HR-EMP-001",
                                         "docstatus": 1, "base": 55555.0}],
    }


class PlatformEndToEnd(TransactionTestCase):
    databases = {"default", "aux"}

    def setUp(self):
        from django.conf import settings
        from cryptography.fernet import Fernet
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        self.fake = FakeERPNext()
        self.patches = [mock.patch("requests.get", self.fake("GET")),
                        mock.patch("requests.post", self.fake("POST")),
                        mock.patch("time.sleep", lambda s: None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_register_load_figures_screens(self):
        from command_center import install
        from command_center.api import ingest, kpi
        from insights.compat import documents, run_as
        from insights.core.models import Secret

        with run_as("Administrator"):
            out = install.register_business("Test Medical Ltd", "https://erp.test", "key",
                                            "s3cret")
        self.assertEqual(out["code"], "test_medical_ltd")
        self.assertEqual(out["currency"], "GHS")
        # the secret is stored encrypted, and reads back
        row = Secret.objects.get(doctype="Connected Business", fieldname="api_secret")
        self.assertNotIn("s3cret", row.value)
        self.assertEqual(documents.get_password("Connected Business", "Test Medical Ltd",
                                                "api_secret"), "s3cret")

        with run_as("Administrator"):
            result = ingest.run_all(full=True)
        loaded = result[0]["loaded"]
        failed = [f["fact"] for f in loaded if f.get("failed")]
        self.assertEqual(failed, [], f"facts that failed to load: {failed}")
        rows = {f["fact"]: f.get("rows") for f in loaded}
        for fact in ("fact_sales_invoice", "fact_sales_invoice_line", "fact_payment_allocation",
                     "fact_purchase_invoice", "fact_sales_order", "fact_stock_balance"):
            self.assertGreater(rows.get(fact) or 0, 0, f"{fact} loaded no rows: {rows}")

        with run_as("Administrator"):
            check = kpi.verify()
        self.assertTrue(check["all_ok"], json.dumps(check, default=str)[:800])
        self._ledger_positions()

        # an incremental reload is harmless (watermarks, upserts)
        with run_as("Administrator"):
            again = ingest.run_all(full=False)
        self.assertFalse([f for f in again[0]["loaded"] if f.get("failed")])

        # the screens' calls, through the web layer, as a signed-in manager
        U = get_user_model()
        m = U.objects.create_user("manager@test.com", "manager@test.com", "a-long-test-pass-9")
        m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        c = Client()
        self.assertTrue(c.login(username="manager@test.com", password="a-long-test-pass-9"))
        # the 15-minute refresh stamps last_sync (a datetime) -- the page must still build
        from insights.core.models import ConnectedBusiness
        ConnectedBusiness.objects.update(last_sync=dt.datetime.now())
        page = c.get("/command-center").content.decode()
        self.assertIn("Test Medical Ltd", page)
        for method, args in [
            ("command_center.api.kpi.get", {"keys": ["ar_total", "revenue_invoiced", "ap_total",
                                                     "order_book"]}),
            ("command_center.api.home.debtors", {}),
            ("command_center.api.home.top_customers", {}),
            ("command_center.api.facts.records", {"fact": "fact_sales_invoice", "limit": 5}),
            ("command_center.api.ingest.status", {}),
            ("command_center.api.alerts.open_alerts", {}),
            ("command_center.api.ingest.history", {}),
        ]:
            r = c.post(f"/api/method/{method}", json.dumps(args), content_type="application/json")
            self.assertEqual(r.status_code, 200, f"{method}: {r.content[:400]!r}")
        figures = c.post("/api/method/command_center.api.kpi.get",
                         json.dumps({"keys": ["ar_total"]}), content_type="application/json").json()
        self.assertGreater(figures["message"]["ar_total"]["value"] or 0, 0)

        # every figure read live from the business's ERPNext, and the order-book boxes,
        # come back read -- never "could not be read" -- with somewhere to open
        from command_center.kpi.live import LIVE
        keys = sorted(LIVE) + ["order_awaiting_despatch", "order_awaiting_invoice"]
        got = c.post("/api/method/command_center.api.kpi.get",
                     json.dumps({"keys": keys, "business_code": "test_medical_ltd"}),
                     content_type="application/json").json()["message"]
        for key in keys:
            self.assertNotEqual(got[key]["data_status"]["state"], "failed",
                                f"{key}: {got[key]}")
            self.assertTrue(got[key]["drill"], f"{key} opens to nothing")

        # every designed screen's charts and tables answer from the loaded records
        from command_center.api import panels as panels_api
        for view, builders in panels_api.SCREENS.items():
            r = c.post("/api/method/command_center.api.panels.get",
                       json.dumps({"view": view, "business_code": "test_medical_ltd"}),
                       content_type="application/json")
            self.assertEqual(r.status_code, 200, f"panels {view}: {r.content[:300]!r}")
            got = r.json()["message"]["panels"]
            self.assertEqual(sorted(got), sorted(builders), f"panels {view} answered {sorted(got)}")
            bad = {t: p for t, p in got.items() if p.get("kind") in ("failed", "unreachable")}
            self.assertFalse(bad, f"panels {view} could not be read: {bad}")
            if view in DEPARTMENT_VIEWS:
                self.assertTrue(r.json()["message"].get("when"), f"{view}: no line under the heading")

        # the administration, with a loaded business in it: every list and the first
        # record of each opens for the platform's administrator
        from django.contrib import admin as dj_admin
        boss = U.objects.create_superuser("boss@test.com", "boss@test.com", "a-long-test-pass-7")
        ca = Client(raise_request_exception=True)
        self.assertEqual(ca.post("/admin/login/?next=/admin/", {
            "username": "boss@test.com", "password": "a-long-test-pass-7"}).status_code, 302)
        self.assertEqual(ca.get("/admin/").status_code, 200)
        for model in dj_admin.site._registry:
            base = f"/admin/{model._meta.app_label}/{model._meta.model_name}/"
            self.assertEqual(ca.get(base).status_code, 200, base)
            first = model.objects.first()
            if first is not None:
                page = f"{base}{first.pk}/change/"
                self.assertEqual(ca.get(page).status_code, 200, page)
        boss.delete()

        # the business's ERPNext stops answering: the panels that read it live say so,
        # the ones drawn from the loaded facts still show them, and a live figure reads
        # "can't reach" -- never a guide, never "could not be read"
        import requests as _rq
        from django.core.cache import cache

        def down(*a, **k):
            raise _rq.ConnectionError("connection refused")
        cache.clear()
        with mock.patch("requests.get", down), mock.patch("requests.post", down):
            for view in DEPARTMENT_VIEWS:
                msg = c.post("/api/method/command_center.api.panels.get",
                             json.dumps({"view": view, "business_code": "test_medical_ltd"}),
                             content_type="application/json").json()["message"]
                kinds = {t: p.get("kind") for t, p in msg["panels"].items()}
                self.assertEqual(sorted(kinds), sorted(panels_api.SCREENS[view]), view)
                self.assertNotIn("failed", kinds.values(), f"{view}: {kinds}")
                if "unreachable" in kinds.values():
                    self.assertTrue(msg.get("unreachable"), view)
                    self.assertEqual(msg.get("business"), "Test Medical Ltd")
            sales = c.post("/api/method/command_center.api.panels.get",
                           json.dumps({"view": "sales", "business_code": "test_medical_ltd"}),
                           content_type="application/json").json()["message"]
            self.assertEqual(sales["panels"]["Largest balances owed"]["kind"], "bars")
            self.assertEqual(sales["panels"]["From enquiry to order"]["kind"], "unreachable")
            self.assertTrue(sales["unreachable"])
            live = c.post("/api/method/command_center.api.kpi.get",
                          json.dumps({"keys": ["po_count", "order_awaiting_stock"],
                                      "business_code": "test_medical_ltd"}),
                          content_type="application/json").json()["message"]
            for key, fig in live.items():
                self.assertEqual(fig["data_status"]["state"], "unreachable", f"{key}: {fig}")
                self.assertIsNone(fig["value"])
        cache.clear()

        # someone without the role is turned away from the interface
        U.objects.create_user("clerk@test.com", "clerk@test.com", "a-long-test-pass-8")
        c2 = Client()
        c2.login(username="clerk@test.com", password="a-long-test-pass-8")
        r = c2.get("/command-center")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/management-only", r["Location"])


    def _ledger_positions(self):
        """Owed is the ledger, the explanation adds up, the ageing is the balance, and the
        reconciliation check agrees with the fake ERPNext on the ledger."""
        from command_center.api import audit
        from command_center.kpi.engine import evaluate_set
        from insights.compat import run_as
        from insights.core.models import CommandCenterFactPartyBalance as PB

        rows = list(PB.objects.filter(business_code="test_medical_ltd").values())
        self.assertTrue(rows, "no ledger balances were loaded")
        for pt in ("Customer", "Supplier"):
            want = sum(LEDGER_SIGN[pt] * (d - c) for (t, _), kinds in LEDGER.items() if t == pt
                       for d, c in kinds.values())
            got = sum(float(r["ledger_balance"]) for r in rows if r["party_type"] == pt)
            self.assertAlmostEqual(got, want, places=2, msg=f"{pt} ledger")
        for r in rows:
            f = {k: float(v or 0) for k, v in r.items() if k in (
                "open_invoices", "unmatched_payments", "unlinked_journals", "unlinked_credit_notes",
                "other_unlinked", "invoices_not_updated", "unexplained", "unlinked_debits",
                "ledger_balance", "owed", "in_credit", "not_due", "d0_30", "d31_60", "d61_90",
                "d90_plus", "undated")}
            explained = (f["open_invoices"] - f["unmatched_payments"] - f["unlinked_journals"]
                         - f["unlinked_credit_notes"] - f["other_unlinked"] - f["invoices_not_updated"]
                         - f["unexplained"] + f["unlinked_debits"])
            self.assertAlmostEqual(explained, f["ledger_balance"], places=2, msg=r["party"])
            aged = sum(f[k] for k in ("not_due", "d0_30", "d31_60", "d61_90", "d90_plus", "undated"))
            self.assertAlmostEqual(aged, f["owed"], places=2, msg=f"{r['party']} ageing")
            self.assertEqual(f["owed"] * f["in_credit"], 0)
        ridge = next(r for r in rows if r["party"] == "Ridge Hospital")
        self.assertEqual(float(ridge["owed"]), 0)
        self.assertEqual(float(ridge["in_credit"]), 3000)
        self.assertEqual(float(ridge["unmatched_payments"]), 3000)
        ubuntu = next(r for r in rows if r["party"] == "Ubuntu Ltd")
        self.assertEqual(float(ubuntu["unlinked_debits"]), 5000)   # the opening balance
        self.assertEqual(float(ubuntu["unlinked_journals"]), 1000)

        # the figures are the ledger's; the invoices' own figure is kept beside them
        figs = evaluate_set(["ar_total", "ap_total", "ar_open_invoices", "ar_in_credit",
                             "ar_unmatched", "ap_unmatched"], "test_medical_ltd")
        self.assertAlmostEqual(float(figs["ar_total"]["value"]),
                               sum(float(r["owed"]) for r in rows if r["party_type"] == "Customer"), 2)
        self.assertEqual(float(figs["ar_in_credit"]["value"]), 3000)
        self.assertEqual(float(figs["ar_unmatched"]["value"]), 23000)
        self.assertEqual(float(figs["ap_unmatched"]["value"]), 30000)
        self.assertEqual(figs["ar_total"]["drill"]["fact"], "fact_party_balance")

        with run_as("Administrator"):
            check = audit.figures("test_medical_ltd")
        lines = {x["key"]: x for x in check["lines"]}
        for key in ("customer_ledger", "supplier_ledger", "customer_unmatched", "supplier_unmatched"):
            self.assertTrue(lines[key]["ok"], f"{key}: {lines[key]}")
        self.assertEqual(len(check["lines"]), len(audit.LINES))
        for x in check["lines"]:
            self.assertTrue(x["ok"] or x["reason"], f"{x['key']} differs and says nothing")
        self.assertIn("Customer ledger balance", audit.table(check))


LEDGER_SIGN = {"Customer": 1, "Supplier": -1}


class LedgerArithmetic(TransactionTestCase):
    """The matching and ageing, by hand. As at 30 Jun 2026 a customer has three open
    invoices (1,000 due 10 Jan, 500 due 20 May, 800 due 10 Jul), an opening balance of
    300 put in by journal on 31 Dec 2025, a payment of 1,300 never matched and a journal
    credit of 100 not linked. The ledger: 2,300 + 300 - 1,300 - 100 = 1,200. The 1,400 of
    credits (2,600 open less 1,200 owed) clear the opening balance (300), the January
    invoice (1,000) and 100 of May's: 400 of May's is left, 41 days overdue, and July's
    800 is not yet due."""

    AS_OF = "2026-06-30"

    def test_hand_worked(self):
        from command_center.ingest.ledger import position, row_for
        gl = {"Sales Invoice": (2300, 0), "Payment Entry": (0, 1300), "Journal Entry": (300, 100)}
        invoices = [("2026-01-10", "2025-12-11", 1000), ("2026-05-20", "2026-04-20", 500),
                    ("2026-07-10", "2026-06-10", 800)]
        journals = [("2025-12-31", 300, 0, None), ("2026-03-01", 0, 100, None)]
        pos = position("Customer", gl, invoices, {}, [("Receive", "2026-02-01", 1300)], journals)
        for key, want in (("ledger_balance", 1200), ("open_invoices", 2300), ("open_invoice_count", 3),
                          ("unmatched_payments", 1300), ("unmatched_payment_count", 1),
                          ("unlinked_journals", 100), ("unlinked_debits", 300),
                          ("unlinked_credit_notes", 0), ("other_unlinked", 0),
                          ("invoices_not_updated", 0), ("unexplained", 0)):
            self.assertAlmostEqual(pos[key], want, places=2, msg=key)
        row = row_for("Customer", "A", pos, self.AS_OF)
        self.assertEqual((row["not_due"], row["d0_30"], row["d31_60"], row["d61_90"], row["d90_plus"],
                          row["undated"]), (800, 0, 400, 0, 0, 0))
        self.assertEqual(str(row["oldest_due_after_matching"]), "2026-05-20")
        self.assertEqual(row["days_overdue"], 41)
        self.assertEqual((row["owed"], row["in_credit"], row["inside_90"], row["overdue"]),
                         (1200, 0, 1200, 400))

    def test_in_credit_owes_nothing(self):
        """Billed 500, paid 800 of which 500 matched to the invoice: in credit by 300."""
        from command_center.ingest.ledger import position, row_for
        pos = position("Customer", {"Sales Invoice": (500, 0), "Payment Entry": (0, 800)}, [],
                       {("Receive", "Sales Invoice"): 500}, [("Receive", "2026-03-01", 300)], [])
        row = row_for("Customer", "B", pos, self.AS_OF)
        self.assertEqual((row["ledger_balance"], row["owed"], row["in_credit"]), (-300, 0, 300))
        self.assertEqual(sum(row[k] for k in ("not_due", "d0_30", "d31_60", "d61_90", "d90_plus",
                                              "undated")), 0)
        self.assertEqual((row["unmatched_payments"], row["unexplained"]), (300, 0))
        self.assertIsNone(row["oldest_due_after_matching"])

    def test_ledger_beyond_the_items_is_undated(self):
        """A supplier's bill the ledger holds but whose own outstanding was cleared: owed
        by the ledger, on no open item, so undated -- never guessed into a bucket."""
        from command_center.ingest.ledger import position, row_for
        pos = position("Supplier", {"Purchase Invoice": (0, 1000)}, [], {}, [], [])
        self.assertEqual((pos["ledger_balance"], pos["invoices_not_updated"], pos["unexplained"]),
                         (1000, -1000, 0))
        row = row_for("Supplier", "C", pos, self.AS_OF)
        self.assertEqual((row["owed"], row["undated"], row["d90_plus"]), (1000, 1000, 0))

    def test_what_the_records_do_not_explain(self):
        """The ledger has 1,000 of payments; the payments' own records account for 900."""
        from command_center.ingest.ledger import position
        pos = position("Customer", {"Sales Invoice": (1000, 0), "Payment Entry": (0, 1000)},
                       [("2026-05-01", None, 100)], {("Receive", "Sales Invoice"): 900}, [], [])
        self.assertEqual((pos["ledger_balance"], pos["invoices_not_updated"], pos["unexplained"]),
                         (0, 0, 100))

    def test_panels_say_why(self):
        from command_center.api.panels import _why
        r = {"unmatched_payments": 700003, "invoices_not_updated": 496719, "unlinked_journals": 0,
             "unlinked_credit_notes": 0, "other_unlinked": 0, "unlinked_debits": 462067.85,
             "unexplained": 0}
        text = _why(r, "XYZ", "Customer")
        self.assertTrue(text.startswith("XYZ 700,003 received but never matched to invoices"), text)
        self.assertIn("XYZ 462,068 owed on journal entries", text)
        self.assertNotIn("disagree", text)
        self.assertIn("disagree by XYZ 5", _why({**r, "unexplained": 5}, "XYZ", "Customer"))


class CommandLine(TransactionTestCase):
    """The management commands as the install script runs them: through manage.py's
    argument parsing (call_command skips that, which hid a clash with --args)."""

    databases = {"default", "aux"}

    def test_execute_from_the_command_line(self):
        import io
        from contextlib import redirect_stdout
        from django.core.management import ManagementUtility
        out = io.StringIO()
        with redirect_stdout(out):
            ManagementUtility(["manage.py", "execute", "command_center.api.kpi.verify",
                               "--kwargs", "{}", "--args", "[]"]).execute()
        self.assertIn('"all_ok"', out.getvalue())


class Upkeep(TransactionTestCase):
    """The nightly upkeep: old errors pruned, a backup written and old ones dropped."""

    databases = {"default", "aux"}

    def test_daily(self):
        import os
        import tempfile
        import time
        from pathlib import Path
        from django.conf import settings
        from insights.core import maintenance
        from insights.core.models import ErrorLog
        old = ErrorLog.objects.using("aux").create(title="old", error="x")
        ErrorLog.objects.using("aux").filter(pk=old.pk).update(
            creation=dt.datetime.now() - dt.timedelta(days=90))
        ErrorLog.objects.using("aux").create(title="recent", error="y")
        import shutil
        from django.db import connection
        if connection.vendor == "mysql" and not (shutil.which("mariadb-dump")
                                                 or shutil.which("mysqldump")):
            self.skipTest("no mariadb-dump on this machine to back MariaDB up with")
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(
                settings.CONFIG, {"backup_dir": d}):
            stale = Path(d, "insights-20200101-000000.sqlite3")
            stale.write_text("old")
            os.utime(stale, (time.time() - 30 * 86400,) * 2)
            out = maintenance.daily()
            self.assertEqual(out["error_log_pruned"], 1)
            self.assertTrue(Path(out["backup"]).exists(), out)
            self.assertFalse(stale.exists())
        titles = set(ErrorLog.objects.using("aux").values_list("title", flat=True))
        self.assertIn("recent", titles)
        self.assertNotIn("old", titles)


class SignInLimits(TransactionTestCase):
    """Wrong passwords are limited -- on the platform's sign-in and the administration's
    -- and a made-up X-Forwarded-For does not get round the limit."""

    databases = {"default", "aux"}

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        get_user_model().objects.create_superuser("boss@test.com", "boss@test.com",
                                                  "a-long-test-pass-1")

    def _api(self, c, pwd, fake_ip):
        return c.post("/api/method/login", json.dumps({"usr": "boss@test.com", "pwd": pwd}),
                      content_type="application/json", REMOTE_ADDR="127.0.0.1",
                      HTTP_X_FORWARDED_FOR=f"{fake_ip}, 41.66.1.1")

    def test_sign_out_ends_the_session(self):
        # The Sign Out menu (Topbar.jsx) posts to logout; afterwards the session is gone
        # and the screens' data is refused until the person signs in again.
        c = Client(enforce_csrf_checks=False)
        self.assertEqual(self._api(c, "a-long-test-pass-1", "41.66.1.1").status_code, 200)
        self.assertEqual(c.post("/api/method/command_center.api.businesses.get_visible_businesses",
                                "{}", content_type="application/json").status_code, 200)
        r = c.post("/api/method/logout", "{}", content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", c.session)
        r = c.post("/api/method/command_center.api.businesses.get_visible_businesses", "{}",
                   content_type="application/json")
        self.assertIn(r.status_code, (401, 403))

    def test_spoofed_forwarded_for_is_not_a_fresh_address(self):
        c = Client()
        codes = [self._api(c, "wrong-password-x", f"10.0.0.{i}").status_code for i in range(7)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5:], [429, 429])
        # the right password is refused too while locked
        self.assertEqual(self._api(c, "a-long-test-pass-1", "10.9.9.9").status_code, 429)

    def test_admin_sign_in_is_limited(self):
        c = Client()
        codes = [c.post("/admin/login/?next=/admin/", {"username": "boss@test.com",
                                                       "password": "wrong-password-x"}).status_code
                 for _ in range(6)]
        self.assertEqual(codes[:5], [200] * 5)   # the form again, with its error
        self.assertEqual(codes[5], 429)

    def test_admin_sign_in_works(self):
        r = Client().post("/admin/login/?next=/admin/", {"username": "boss@test.com",
                                                         "password": "a-long-test-pass-1"})
        self.assertEqual(r.status_code, 302)


class PanelHeadings(TransactionTestCase):
    """Every panel api/panels.py answers is a heading on that screen, word for word --
    a heading that does not match would leave the designed sample in place."""

    def test_headings_exist(self):
        import html as _html
        from pathlib import Path
        from django.conf import settings
        from command_center.api.panels import SCREENS
        views = json.loads(Path(settings.BASE_DIR, "frontend/src/legacy/views.json").read_text())
        for view, builders in SCREENS.items():
            markup = _html.unescape(views[view])
            for title in builders:
                self.assertIn(f"<b>{title}</b>", markup, f"{view}: no panel headed {title!r}")


class SettingsPage(TransactionTestCase):
    """The Settings screen's calls (insights/core/platform_settings.py): for the platform's
    administrator only, refused to a manager by the server; people, businesses, the
    Claude key and personal ERPNext keys; no call ever returns a secret; refusals and
    password rules come back as plain sentences; every change is in the audit trail."""

    databases = {"default", "aux"}
    MOD = "insights.core.platform_settings"
    SECRET = "biz-secret-value-71x"
    PERSONAL = "personal-secret-value-93q"

    def setUp(self):
        import os
        import tempfile
        from django.conf import settings
        from django.core.cache import cache
        from cryptography.fernet import Fernet
        cache.clear()
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        self.fake = FakeERPNext()
        self.enqueued = []
        fd, self.cfg = tempfile.mkstemp(suffix=".json")
        os.write(fd, b"{}")
        os.close(fd)
        import frappe
        self.patches = [mock.patch("requests.get", self.fake("GET")),
                        mock.patch("requests.post", self.fake("POST")),
                        mock.patch("time.sleep", lambda s: None),
                        mock.patch.object(settings, "CONFIG_PATH", self.cfg),
                        mock.patch.dict(settings.CONFIG),
                        mock.patch.dict(frappe.conf),
                        mock.patch("insights.compat.enqueue",
                                   lambda fn, **kw: self.enqueued.append((fn, kw)))]
        for p in self.patches:
            p.start()
        U = get_user_model()
        self.boss = U.objects.create_superuser("boss@test.com", "boss@test.com", "a-long-test-pass-5")
        mgr = U.objects.create_user("manager@test.com", "manager@test.com", "a-long-test-pass-6")
        mgr.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        self.admin, self.manager = Client(), Client()
        self.assertTrue(self.admin.login(username="boss@test.com", password="a-long-test-pass-5"))
        self.assertTrue(self.manager.login(username="manager@test.com", password="a-long-test-pass-6"))
        self.bodies = []

    def tearDown(self):
        import os
        for p in reversed(self.patches):
            p.stop()
        os.unlink(self.cfg)

    def _call(self, client, fn, **args):
        r = client.post(f"/api/method/{self.MOD}.{fn}", json.dumps(args),
                        content_type="application/json")
        self.bodies.append(r.content.decode())
        return r

    def _ok(self, fn, **args):
        r = self._call(self.admin, fn, **args)
        self.assertEqual(r.status_code, 200, f"{fn}: {r.content[:400]!r}")
        return r.json()["message"]

    def _refused(self, fn, **args) -> str:
        r = self._call(self.admin, fn, **args)
        self.assertEqual(r.status_code, 417, f"{fn} was not refused: {r.content[:300]!r}")
        msgs = [json.loads(m)["message"] for m in json.loads(r.json()["_server_messages"])]
        text = " ".join(msgs)
        self.assertNotIn("Traceback", text)
        return text

    def test_a_manager_is_refused_every_call(self):
        from insights.compat import WHITELIST
        names = [k.rsplit(".", 1)[1] for k in WHITELIST if k.startswith(self.MOD + ".")]
        self.assertGreaterEqual(len(names), 20)
        for fn in names:
            r = self._call(self.manager, fn, username="boss@test.com", name="x")
            self.assertEqual(r.status_code, 403, f"{fn} answered a manager: {r.status_code}")
            self.assertEqual(self._call(Client(), fn).status_code, 401, fn)
        # and nothing was changed by trying
        self.assertTrue(get_user_model().objects.get(username="boss@test.com").is_superuser)

    def test_people(self):
        listed = {p["username"]: p for p in self._ok("people")}
        self.assertTrue(listed["boss@test.com"]["is_admin"])
        self.assertTrue(listed["manager@test.com"]["is_manager"])
        self.assertFalse(listed["manager@test.com"]["is_admin"])
        # password rules, in Django's own plain sentences
        self.assertIn("not the same", self._refused(
            "add_person", email="new@test.com", full_name="Ama Mensah",
            password="a-long-test-pass-1", password2="a-long-test-pass-2"))
        self.assertIn("too short", self._refused(
            "add_person", email="new@test.com", full_name="Ama Mensah",
            password="short1", password2="short1"))
        self.assertIn("too common", self._refused(
            "add_person", email="new@test.com", full_name="Ama Mensah",
            password="password123", password2="password123"))
        self.assertIn("not an email", self._refused("add_person", email="nobody", set_later=1))
        p = self._ok("add_person", email="New@Test.com", full_name="Ama Mensah",
                     password="a-long-test-pass-3", password2="a-long-test-pass-3", manager=1)
        self.assertEqual((p["username"], p["full_name"], p["is_manager"], p["has_password"]),
                         ("new@test.com", "Ama Mensah", True, True))
        self.assertIn("already", self._refused("add_person", email="new@test.com", set_later=1))
        self.assertTrue(Client().login(username="new@test.com", password="a-long-test-pass-3"))
        later = self._ok("add_person", email="later@test.com", full_name="Kofi Boateng",
                         set_later=1, manager=0)
        self.assertFalse(later["has_password"])
        self.assertFalse(later["is_manager"])
        # make / unmake manager and administrator, deactivate / reactivate
        self.assertTrue(self._ok("set_manager", username="later@test.com", on=1)["is_manager"])
        self.assertTrue(self._ok("set_admin", username="later@test.com", on=1)["is_admin"])
        self.assertFalse(self._ok("set_admin", username="later@test.com", on=0)["is_admin"])
        off = self._ok("set_active", username="new@test.com", on=0)
        self.assertFalse(off["active"])
        self.assertFalse(get_user_model().objects.get(username="new@test.com").is_active)
        self.assertFalse(Client().login(username="new@test.com", password="a-long-test-pass-3"))
        self.assertTrue(self._ok("set_active", username="new@test.com", on=1)["active"])
        # a new password, validated the same way
        self.assertIn("too short", self._refused("reset_password", username="new@test.com",
                                                 password="tiny", password2="tiny"))
        self._ok("reset_password", username="new@test.com", password="another-long-pass-4",
                 password2="another-long-pass-4")
        self.assertTrue(Client().login(username="new@test.com", password="another-long-pass-4"))
        # never a password, in any form
        for body in self.bodies:
            self.assertNotIn("pbkdf2", body)
            self.assertNotIn("a-long-test-pass-3", body)
            self.assertNotIn("another-long-pass-4", body)
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        for phrase in ("added new@test.com as manager", "deactivated new@test.com",
                       "set a new password for new@test.com", "made later@test.com an administrator"):
            self.assertIn(phrase, whats)
        self.assertNotIn("another-long-pass-4", whats)

    def test_the_last_administrator_stays(self):
        self.assertIn("yourself", self._refused("set_admin", username="boss@test.com", on=0))
        self.assertIn("yourself", self._refused("set_active", username="boss@test.com", on=0))
        self.assertIn("own password", self._refused("reset_password", username="boss@test.com",
                                                    set_later=1))
        boss = get_user_model().objects.get(username="boss@test.com")
        self.assertTrue(boss.is_superuser and boss.is_active)
        # with a second administrator, one may be removed -- but never the last active one
        self._ok("add_person", email="second@test.com", full_name="Second Admin", set_later=1,
                 admin=1)
        self.assertFalse(self._ok("set_active", username="second@test.com", on=0)["active"])
        from insights.compat import run_as
        from insights.compat.state import ValidationError
        from insights.core import platform_settings as ps
        get_user_model().objects.filter(username="second@test.com").update(is_active=True)
        with run_as("second@test.com"):
            ps.set_active("boss@test.com", 0)       # two active: allowed
        get_user_model().objects.filter(username="boss@test.com").update(is_active=True)
        get_user_model().objects.filter(username="second@test.com").update(is_superuser=False)
        U = get_user_model()
        self.assertEqual(U.objects.filter(is_superuser=True, is_active=True).count(), 1)
        with mock.patch.object(ps, "_require_admin", lambda: U.objects.get(username="second@test.com")):
            with run_as("second@test.com"), self.assertRaises(ValidationError) as e:
                ps.set_admin("boss@test.com", 0)
        self.assertIn("last active administrator", str(e.exception))

    def test_businesses_and_keys(self):
        from insights.compat import documents
        out = self._ok("add_business", business_name="Test Medical Ltd",
                       site_url="https://erp.test/", api_key="key-abcd1234", api_secret=self.SECRET)
        self.assertEqual(out["access"]["reads_as"], "reader@test.com")
        self.assertEqual(out["currency"], "GHS")
        self.assertTrue(out["access"]["read_only"])
        self.assertFalse(out["access"]["unreadable"])
        row = out["business"]
        self.assertEqual((row["site_url"], row["api_key"], row["has_secret"]),
                         ("https://erp.test", "…1234", True))
        self.assertIn("connected already", self._refused(
            "add_business", business_name="Test Medical Ltd", site_url="https://erp.test",
            api_key="k", api_secret="s"))
        self.assertIn("https://", self._refused(
            "add_business", business_name="Other Ltd", site_url="erp.other", api_key="k",
            api_secret="s"))
        # a business whose ERPNext refuses the key is not kept
        refuse = lambda *a, **k: _R(401, {"exc_type": "AuthenticationError"})  # noqa: E731
        with mock.patch("requests.get", refuse), mock.patch("requests.post", refuse):
            msg = self._refused("add_business", business_name="Refusing Ltd",
                                site_url="https://erp.refuse", api_key="k", api_secret="s")
        self.assertIn("was not connected", msg)
        from insights.core.models import ConnectedBusiness, Secret
        self.assertFalse(ConnectedBusiness.objects.filter(pk="Refusing Ltd").exists())
        self.assertFalse(Secret.objects.filter(docname="Refusing Ltd").exists())

        # edit: a blank secret keeps the stored one, a new one replaces it
        self._ok("update_business", name="Test Medical Ltd", site_url="https://erp2.test")
        self.assertEqual(documents.get_password("Connected Business", "Test Medical Ltd",
                                                "api_secret"), self.SECRET)
        self._ok("update_business", name="Test Medical Ltd", api_secret=self.SECRET + "-new")
        self.assertEqual(documents.get_password("Connected Business", "Test Medical Ltd",
                                                "api_secret"), self.SECRET + "-new")
        self.assertIn("Nothing was changed", self._refused("update_business", name="Test Medical Ltd"))
        tested = self._ok("test_business", name="Test Medical Ltd")
        self.assertTrue(tested["ok"], tested)
        self.assertIn("reader@test.com", tested["says"])
        self.assertEqual(self._ok("set_paused", name="Test Medical Ltd", paused=1)["status"], "Paused")
        self.assertIn("paused", self._refused("reload_business", name="Test Medical Ltd"))
        self.assertEqual(self._ok("set_paused", name="Test Medical Ltd", paused=0)["status"], "Active")
        # Reload Everything starts a background job and returns at once
        started = self._ok("reload_business", name="Test Medical Ltd")
        self.assertEqual(len(self.enqueued), 1)
        self.assertEqual(self.enqueued[0][1]["code"], "test_medical_ltd")
        self.assertEqual(started["reload"]["state"], "queued")
        listed = self._ok("businesses")[0]
        self.assertEqual(listed["reload"]["state"], "queued")
        self.assertEqual(listed["reload"]["total"], listed["facts_total"])

        # personal ERPNext keys
        self.assertIn("both", self._refused("set_credential", user="manager@test.com",
                                            business_code="test_medical_ltd", api_key="pk"))
        cred = self._ok("set_credential", user="manager@test.com", business_code="test_medical_ltd",
                        api_key="pkey-5678", api_secret=self.PERSONAL)
        self.assertEqual((cred["api_key"], cred["has_secret"]), ("…5678", True))
        self.assertEqual(len(self._ok("credentials")), 1)
        self.assertTrue(self._ok("test_credential", name=cred["name"])["ok"])
        self._ok("set_credential", user="manager@test.com", business_code="test_medical_ltd",
                 api_key="pkey-9999")
        self.assertEqual(documents.get_password("Command Center Site Credential", cred["name"],
                                                "api_secret"), self.PERSONAL)
        self.assertTrue(self._ok("remove_credential", name=cred["name"])["removed"])
        self.assertEqual(self._ok("credentials"), [])

        # the Claude key: replaced, shown only masked
        self.assertFalse(self._ok("claude")["set"])
        self.assertIn("whole key", self._refused("set_claude_key", key="sk-ant-short"))
        claude_key = "sk-ant-test-0000wxyz"
        shown = self._ok("set_claude_key", key=claude_key)
        self.assertEqual((shown["set"], shown["masked"]), (True, "sk-ant-…wxyz"))
        self.assertEqual(json.load(open(self.cfg))["command_center_anthropic_key"], claude_key)
        with mock.patch("command_center.api.ask.check_analyst",
                        lambda: {"ok": True, "provider": "claude", "model": "m-1",
                                 "deep_model": "m-2", "cache": {"working": True}}):
            checked = self._ok("check_claude")
        self.assertTrue(checked["ok"])
        self.assertIn("m-1", checked["says"])

        # no call returned a secret, a key in full, or the Claude key
        self._ok("businesses")
        self._ok("changes")
        for body in self.bodies:
            for secret in (self.SECRET, self.PERSONAL, "key-abcd1234", "pkey-5678", claude_key):
                self.assertNotIn(secret, body)
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        for phrase in ("connected Test Medical Ltd", "API secret", "paused Test Medical Ltd",
                       "started a full reload", "replaced the Claude key",
                       "removed the ERPNext key of manager@test.com"):
            self.assertIn(phrase, whats)


class PagesNotStored(TransactionTestCase):
    """The pages carry the person's details and their session's request token: the
    browser must never keep them, or a stale token refuses every request after sign-in."""

    databases = {"default", "aux"}

    def test_no_store(self):
        U = get_user_model()
        u = U.objects.create_user("m@test.com", "m@test.com", "a-long-test-pass-5")
        u.groups.add(Group.objects.get_or_create(name="Insights Dashboard Manager")[0])
        c = Client()
        self.assertEqual(c.get("/command-center-login")["Cache-Control"], "no-store")
        c.login(username="m@test.com", password="a-long-test-pass-5")
        self.assertEqual(c.get("/command-center")["Cache-Control"], "no-store")


class KpiCatalogueThreads(TransactionTestCase):
    """The figure catalogue is complete for every request, however many arrive at once."""

    def test_concurrent_load(self):
        import threading
        from command_center.kpi import registry
        saved = dict(registry.REGISTRY)
        registry.REGISTRY.clear()
        registry._LOADED = False
        import sys
        import command_center.kpi as kpi_pkg
        for m in ("buying", "operations", "sales", "stock"):
            sys.modules.pop(f"command_center.kpi.{m}", None)
            if hasattr(kpi_pkg, m):
                delattr(kpi_pkg, m)
        seen, errors = [], []

        def worker():
            try:
                seen.append(len(registry.load_all()))
            except Exception as e:  # pragma: no cover - would be the failure
                errors.append(e)
        threads = [threading.Thread(target=worker) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        try:
            self.assertFalse(errors, errors)
            self.assertEqual(len(set(seen)), 1, f"some requests saw a partial catalogue: {seen}")
            self.assertIn("revenue_12m", registry.REGISTRY)
        finally:
            registry.REGISTRY.clear()
            registry.REGISTRY.update(saved)
            registry._LOADED = True


class SettingsDelegation(TransactionTestCase):
    """Settings sections the administrator gives a manager (Businesses, People, Personal
    ERPNext Keys): a delegate can do exactly their sections, never anything that makes
    or changes an administrator or gives Settings access; the boot payload says which
    sections to show; every grant is audited. And Email: the password is never
    returned, and the test email and scheduled reports use the saved settings."""

    databases = {"default", "aux"}
    MOD = SettingsPage.MOD
    MAIL_PW = "mail-pass-xyz-77"
    setUp = SettingsPage.setUp
    tearDown = SettingsPage.tearDown
    _call = SettingsPage._call
    _ok = SettingsPage._ok

    def _as(self, client, fn, status=200, **args):
        r = self._call(client, fn, **args)
        self.assertEqual(r.status_code, status, f"{fn}: {r.content[:400]!r}")
        return r.json().get("message") if status == 200 else r.json()

    def _boot(self, client) -> dict:
        page = client.get("/command-center").content.decode()
        return json.loads(re.search(r"window\.CC_BOOT = (.*?);\s*$", page, re.M).group(1))

    def _grant(self, *sections, who="manager@test.com"):
        return self._ok("set_settings_access", username=who, sections=list(sections))

    def test_boot_and_a_plain_manager(self):
        self.assertEqual(self._boot(self.admin)["settings_sections"],
                         ["people", "businesses", "customers", "claude", "email", "branding",
                          "keys", "recommend", "changes"])
        self.assertEqual(self._boot(self.manager)["settings_sections"], [])
        for fn in ("people", "businesses", "credentials", "email", "notifications",
                   "set_email", "test_email", "set_settings_access", "changes"):
            self._as(self.manager, fn, 403, username="manager@test.com", sections=["people"])
        self._grant("businesses", "keys")
        self.assertEqual(self._boot(self.manager)["settings_sections"], ["businesses", "keys"])
        # no longer a manager: no Settings, and the grants are gone for good
        self._ok("set_manager", username="manager@test.com", on=0)
        self.assertEqual(self._boot(self.admin)["settings_sections"][0], "people")
        self._ok("set_manager", username="manager@test.com", on=1)
        self.assertEqual(self._boot(self.manager)["settings_sections"], [])

    def test_a_businesses_delegate(self):
        self._grant("businesses")
        out = self._as(self.manager, "add_business", business_name="Test Medical Ltd",
                       site_url="https://erp.test", api_key="key-abcd1234",
                       api_secret="biz-secret-value-71x")
        self.assertEqual(out["access"]["reads_as"], "reader@test.com")
        self.assertTrue(self._as(self.manager, "test_business", name="Test Medical Ltd")["ok"])
        self.assertEqual(self._as(self.manager, "set_paused", name="Test Medical Ltd",
                                  paused=1)["status"], "Paused")
        self._as(self.manager, "set_paused", name="Test Medical Ltd", paused=0)
        self._as(self.manager, "reload_business", name="Test Medical Ltd")
        self.assertEqual(len(self._as(self.manager, "businesses")), 1)
        refused = [("people", {}), ("add_person", {"email": "x@test.com", "set_later": 1}),
                   ("claude", {}), ("set_claude_key", {"key": "sk-ant-" + "x" * 30}),
                   ("email", {}), ("set_email", {"host": "smtp.test.com", "sender": "a@test.com"}),
                   ("test_email", {"to": "a@test.com"}), ("notifications", {}),
                   ("set_settings_access", {"username": "manager@test.com",
                                            "sections": ["people"]}),
                   ("credentials", {}), ("changes", {})]
        for fn, args in refused:
            body = self._as(self.manager, fn, 403, **args)
            self.assertNotIn("Traceback", json.dumps(body))
        self.assertNotIn("command_center_anthropic_key", json.load(open(self.cfg)))
        self.assertNotIn("mail", json.load(open(self.cfg)))
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        self.assertIn("connected Test Medical Ltd", whats)

    def test_a_people_delegate(self):
        U = get_user_model()
        self._grant("people")
        # adds managers, but never an administrator
        self._as(self.manager, "add_person", 403, email="boss2@test.com", full_name="B Two",
                 set_later=1, admin=1)
        self.assertFalse(U.objects.filter(username="boss2@test.com").exists())
        p = self._as(self.manager, "add_person", email="ama@test.com", full_name="Ama Mensah",
                     password="a-long-test-pass-3", password2="a-long-test-pass-3", manager=1)
        self.assertTrue(p["is_manager"] and not p["is_admin"])
        # changes managers: deactivate, reactivate, reset the password, rename
        self.assertFalse(self._as(self.manager, "set_active", username="ama@test.com", on=0)["active"])
        self.assertTrue(self._as(self.manager, "set_active", username="ama@test.com", on=1)["active"])
        self._as(self.manager, "reset_password", username="ama@test.com",
                 password="another-long-pass-4", password2="another-long-pass-4")
        self.assertTrue(Client().login(username="ama@test.com", password="another-long-pass-4"))
        # never: make an administrator, give Settings access, touch an administrator
        self._as(self.manager, "set_admin", 403, username="ama@test.com", on=1)
        self._as(self.manager, "set_settings_access", 403, username="ama@test.com",
                 sections=["people"])
        for fn, args in (("set_active", {"on": 0}), ("set_manager", {"on": 0}),
                         ("reset_password", {"password": "hijack-long-pass-9",
                                             "password2": "hijack-long-pass-9"}),
                         ("reset_password", {"set_later": 1}),
                         ("update_person", {"full_name": "Someone Else"})):
            self._as(self.manager, fn, 403, username="boss@test.com", **args)
        boss = U.objects.get(username="boss@test.com")
        self.assertTrue(boss.is_superuser and boss.is_active and boss.check_password("a-long-test-pass-5"))
        self.assertEqual(boss.first_name, "")
        self.assertFalse(U.objects.get(username="ama@test.com").is_superuser)
        # nor anyone else with Settings access (that would reach past what was given)
        self._grant("businesses", who="ama@test.com")
        self._as(self.manager, "set_active", 403, username="ama@test.com", on=0)
        self._as(self.manager, "reset_password", 403, username="ama@test.com",
                 password="hijack-long-pass-9", password2="hijack-long-pass-9")
        self.assertTrue(U.objects.get(username="ama@test.com").is_active)
        # nor their own access; their own password, yes
        self._as(self.manager, "set_manager", 403, username="manager@test.com", on=0)
        self._as(self.manager, "reset_password", username="manager@test.com",
                 password="my-own-long-pass-8", password2="my-own-long-pass-8")
        listed = {x["username"]: x for x in self._as(self.manager, "people")}
        self.assertTrue(listed["boss@test.com"]["protected"])
        self.assertEqual(listed["ama@test.com"]["settings_access"], ["businesses"])
        self._as(self.manager, "businesses", 403)
        self._as(self.manager, "claude", 403)
        self._as(self.manager, "email", 403)
        for body in self.bodies:
            self.assertNotIn("pbkdf2", body)

    def test_a_keys_delegate(self):
        self._ok("add_business", business_name="Test Medical Ltd", site_url="https://erp.test",
                 api_key="key-abcd1234", api_secret="biz-secret-value-71x")
        boss_key = self._ok("set_credential", user="boss@test.com", business_code="test_medical_ltd",
                            api_key="bkey-1111", api_secret="boss-secret-1")
        self._grant("keys")
        mine = self._as(self.manager, "set_credential", user="manager@test.com",
                        business_code="test_medical_ltd", api_key="pkey-5678",
                        api_secret="personal-secret-2")
        self.assertEqual([c["user"] for c in self._as(self.manager, "credentials")],
                         ["manager@test.com"])
        self.assertEqual(len(self._ok("credentials")), 2)
        self._as(self.manager, "set_credential", 403, user="boss@test.com",
                 business_code="test_medical_ltd", api_key="evil", api_secret="evil")
        self._as(self.manager, "remove_credential", 403, name=boss_key["name"])
        self._as(self.manager, "test_credential", 403, name=boss_key["name"])
        self.assertTrue(self._as(self.manager, "test_credential", name=mine["name"])["ok"])
        self._as(self.manager, "add_business", 403, business_name="Other Ltd",
                 site_url="https://erp.other", api_key="k", api_secret="s")
        self._as(self.manager, "add_person", 403, email="x@test.com", set_later=1)

    def test_grants_by_the_administrator_are_audited(self):
        p = self._grant("businesses", "keys")
        self.assertEqual(p["settings_access"], ["businesses", "keys"])
        p = self._grant("businesses")
        self.assertEqual(p["settings_access"], ["businesses"])
        self.assertIn("Nothing was changed", self._call(
            self.admin, "set_settings_access", username="manager@test.com",
            sections=["businesses"]).content.decode())
        self.assertIn("Only Businesses", self._call(
            self.admin, "set_settings_access", username="manager@test.com",
            sections=["claude"]).content.decode())
        self.assertIn("administrator", self._call(
            self.admin, "set_settings_access", username="boss@test.com",
            sections=["people"]).content.decode())
        self._ok("add_person", email="plain@test.com", full_name="Not Manager", set_later=1, manager=0)
        self.assertIn("not a manager", self._call(
            self.admin, "set_settings_access", username="plain@test.com",
            sections=["people"]).content.decode())
        self.assertEqual(self._grant(who="manager@test.com")["settings_access"], [])
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        for phrase in ("gave manager@test.com access to Settings: Businesses",
                       "gave manager@test.com access to Settings: Personal ERPNext Keys",
                       "took away manager@test.com's access to Settings: Personal ERPNext Keys",
                       "took away manager@test.com's access to Settings: Businesses"):
            self.assertIn(phrase, whats)
        from django.contrib.admin.models import LogEntry
        e = LogEntry.objects.filter(change_message__contains="gave manager@test.com").first()
        self.assertEqual(e.user.username, "boss@test.com")

    def test_email_settings_and_test_email(self):
        import smtplib
        from insights.core.models import ErrorLog
        n = self._ok("notifications")
        self.assertFalse(n["email_configured"])
        self.assertIsNone(n["last_attempt"])
        self.assertFalse(self._ok("test_email", to="boss@test.com")["ok"])
        self.assertIn("Type the password", self._call(
            self.admin, "set_email", host="smtp.test.com", port=587, security="starttls",
            user="reports@test.com").content.decode())
        self.assertIn("mail server", self._call(
            self.admin, "set_email", host="smtp test", sender="a@test.com").content.decode())
        shown = self._ok("set_email", host="smtp.test.com", port="587", security="starttls",
                         user="reports@test.com", password=self.MAIL_PW,
                         sender="reports@test.com", sender_name="Reports")
        self.assertTrue(shown["configured"] and shown["has_password"])
        self.assertNotIn("password", shown)
        stored = json.load(open(self.cfg))["mail"]
        self.assertEqual((stored["host"], stored["port"], stored["user"], stored["password"],
                          stored["tls"]), ("smtp.test.com", 587, "reports@test.com",
                                           self.MAIL_PW, True))
        # a blank password keeps the stored one
        self._ok("set_email", host="smtp.test.com", port=587, security="starttls",
                 user="reports@test.com", sender="reports@test.com", sender_name="Board Reports")
        self.assertEqual(json.load(open(self.cfg))["mail"]["password"], self.MAIL_PW)
        self._ok("email")
        for body in self.bodies:
            self.assertNotIn(self.MAIL_PW, body)
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        self.assertIn("set up email: server smtp.test.com on port 587 (STARTTLS)", whats)
        self.assertNotIn(self.MAIL_PW, whats)

        # the test email goes out with exactly the stored settings
        with mock.patch("smtplib.SMTP") as smtp:
            out = self._ok("test_email", to="boss@test.com")
        self.assertTrue(out["ok"], out)
        smtp.assert_called_once_with("smtp.test.com", 587, timeout=30)
        s = smtp.return_value
        s.starttls.assert_called_once()
        s.login.assert_called_once_with("reports@test.com", self.MAIL_PW)
        sent = s.send_message.call_args[0][0]
        self.assertEqual((sent["To"], sent["From"]), ("boss@test.com",
                                                      "Board Reports <reports@test.com>"))
        self.assertTrue(self._ok("notifications")["last_attempt"]["ok"])
        # SSL on 465
        self._ok("set_email", host="smtp.test.com", port=465, security="ssl",
                 user="reports@test.com", sender="reports@test.com", sender_name="Board Reports")
        with mock.patch("smtplib.SMTP_SSL") as ssl_smtp, mock.patch("smtplib.SMTP") as plain:
            self.assertTrue(self._ok("test_email", to="boss@test.com")["ok"])
        self.assertEqual(ssl_smtp.call_args[0], ("smtp.test.com", 465))
        plain.assert_not_called()
        # failures in plain words, in the error log, and as the last attempt
        with mock.patch("smtplib.SMTP_SSL") as ssl_smtp:
            ssl_smtp.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"no")
            out = self._ok("test_email", to="boss@test.com")
        self.assertFalse(out["ok"])
        self.assertIn("refused the username or password", out["says"])
        with mock.patch("smtplib.SMTP_SSL", side_effect=ConnectionRefusedError(61, "refused")):
            out = self._ok("test_email", to="boss@test.com")
        self.assertIn("Could not connect to the mail server at smtp.test.com on port 465", out["says"])
        self.assertTrue(ErrorLog.objects.filter(title__startswith="Email not sent").exists())
        last = self._ok("notifications")["last_attempt"]
        self.assertFalse(last["ok"])
        self.assertIn("Could not connect", last["error"])

    def test_scheduled_reports_use_the_email_settings(self):
        import frappe
        from insights.compat import run_as
        from insights.compat.runtime import MailNotConfigured
        from insights.core.models import CommandCenterReportSchedule, ErrorLog
        # not set up: never silently dropped -- raised, logged, and the schedule says so
        with run_as("boss@test.com"), self.assertRaises(MailNotConfigured):
            frappe.sendmail(recipients=["a@test.com"], subject="Weekly", message="<p>x</p>")
        self.assertTrue(ErrorLog.objects.filter(title="Email not sent: email is not set up").exists())
        sched = CommandCenterReportSchedule.objects.create(
            name="rs-1", report="rp01", business_code="test_medical_ltd", enabled=1,
            recipients="a@test.com", run_as="boss@test.com")
        stub = {"answer": "All is well.\n\nMore.", "checked": [], "model": "m"}
        with mock.patch("command_center.ask.engine.analyst_enabled", lambda: True), \
                mock.patch("command_center.ask.agent.answer", lambda *a, **k: stub), \
                mock.patch("command_center.api.export.pdf_bytes", lambda *a, **k: b"%PDF"), \
                mock.patch("command_center.api.export._business", lambda c: "Test Medical Ltd"), \
                mock.patch("command_center.api.export._as_of", lambda: "15 Nov 2026"):
            from command_center.api import reports
            with run_as("boss@test.com"):
                reports.send_scheduled("rs-1")
            sched.refresh_from_db()
            self.assertTrue(sched.last_status.startswith("Failed"), sched.last_status)
            self.assertIn("Email is not set up", sched.last_status)
            failing = self._ok("notifications")["failing"]
            self.assertEqual(failing[0]["report"], "Executive Summary")
            # set up: the same schedule goes out through the stored server
            self._ok("set_email", host="smtp.test.com", port=587, security="starttls",
                     user="reports@test.com", password=self.MAIL_PW, sender="reports@test.com")
            with mock.patch("smtplib.SMTP") as smtp, run_as("boss@test.com"):
                reports.send_scheduled("rs-1")
        smtp.assert_called_once_with("smtp.test.com", 587, timeout=30)
        smtp.return_value.login.assert_called_once_with("reports@test.com", self.MAIL_PW)
        self.assertEqual(smtp.return_value.send_message.call_args[0][0]["To"], "a@test.com")
        sched.refresh_from_db()
        self.assertTrue(sched.last_status.startswith("Sent to 1"), sched.last_status)
        n = self._ok("notifications")
        self.assertEqual((n["schedules_on"], n["failing"]), (1, []))


class DocumentLinks(TransactionTestCase):
    """A record opens in its own business's ERPNext, at the document -- never at this
    platform's administration (which sent every link to <business>/admin/, a 404)."""

    databases = {"default", "aux"}

    def test_links(self):
        from command_center.api.facts import _document_url
        from insights.compat.utils import get_url_to_form
        sites = {"gms": "https://erp.example.com"}
        self.assertEqual(
            _document_url(sites, {"business_code": "gms", "src_doctype": "Sales Invoice",
                                  "src_name": "ACC-SINV-2026-00012"}),
            "https://erp.example.com/app/sales-invoice/ACC-SINV-2026-00012")
        self.assertEqual(
            _document_url(sites, {"business_code": "gms", "src_doctype": "Purchase Order",
                                  "src_name": "PUR-ORD 2026/7"}),
            "https://erp.example.com/app/purchase-order/PUR-ORD%202026%2F7")
        # the platform's own records still open in its administration
        self.assertIn("/admin/core/connectedbusiness/", get_url_to_form("Connected Business", "X"))
        self.assertNotIn("/admin", _document_url(sites, {"business_code": "gms",
                                                          "src_doctype": "Task", "src_name": "T-1"}))


class NothingIllustrative(TransactionTestCase):
    """The department screens carry nothing that is not the business's own: every card
    and tile names a figure, every panel has a builder, every finding box is filled by
    the screen's findings, and the markup and explainers name no customer, supplier,
    person, place, year or currency of any one business."""

    NAMES = ("UBUNTU", "HAIRASH", "SICHUAN", "CYNSEL", "EJURA", "SUNYANI", "KUMASI", "ACCRA",
             "SAMUEL", "SIMON", "GIGMANN", "SAMKWARTH", "AGAHF", "QINGDAO", "ROSSY", "LILIAN",
             "VINEYARD", "KING JO", "ILEE", "ST JOHN", "KORLE", "GMSL", "HITECH", "OSEIKOJOKROM")

    def _load(self):
        import html as _html
        from pathlib import Path
        from django.conf import settings
        base = Path(settings.BASE_DIR, "frontend/src/legacy")
        views = json.loads((base / "views.json").read_text())
        extras = json.loads((base / "extras.json").read_text())
        hydrate = (base / "hydrate.js").read_text()
        return views, extras, hydrate, _html

    @staticmethod
    def _js_map(src, name, tiles=False):
        body = src[src.index(f"export const {name} = {{"):]
        body = body[:body.index("\n};")]
        out = {}
        for m in re.finditer(r"^  (\w+): \{$(.*?)^  \},?$", body, re.S | re.M):
            pat = (r'(?:"([^"]+)"|(\w+)):\s*\{\s*key:\s*"(\w+)"' if tiles
                   else r'(?:"([^"]+)"|(\w+)):\s*"(\w+)"')
            out[m.group(1)] = {(a or b): k for a, b, k in re.findall(pat, m.group(2))}
        for m in re.finditer(r"^  (\w+): \{\},?$", body, re.M):
            out[m.group(1)] = {}
        return out

    def test_every_card_tile_and_panel_is_answered(self):
        from command_center.api.panels import FINDINGS, SCREENS
        from command_center.kpi.live import LIVE
        from command_center.kpi.registry import load_all
        views, _, hydrate, _html = self._load()
        cards = self._js_map(hydrate, "CARD_KPIS")
        tiles = self._js_map(hydrate, "TILE_KPIS", tiles=True)
        known = set(load_all()) | set(LIVE)
        for view in DEPARTMENT_VIEWS:
            markup = _html.unescape(views[view])
            for label in re.findall(r'<div class="lab">([^<]+)</div>', markup):
                key = cards.get(view, {}).get(label.strip())
                self.assertTrue(key, f"{view}: card {label!r} has no figure")
                self.assertIn(key, known, f"{view}: card {label!r} names unknown figure {key}")
            for label in re.findall(r'<div class="l">([^<]+)</div>', markup):
                key = tiles.get(view, {}).get(label.strip())
                self.assertTrue(key, f"{view}: tile {label!r} has no figure")
                self.assertIn(key, known, f"{view}: tile {label!r} names unknown figure {key}")
            for block in markup.split('<div class="panel">')[1:]:
                title = re.search(r"<b>([^<]+)</b>", block).group(1).strip()
                if 'class="bk' in block:
                    continue   # a panel of tiles: the tiles are its figures
                self.assertIn(title, SCREENS.get(view, {}), f"{view}: panel {title!r} has no builder")
            if 'class="warn"' in markup:
                self.assertIn(view, FINDINGS, f"{view} has finding boxes and no findings")

    def test_no_business_of_its_own_in_the_markup(self):
        views, extras, _, _html = self._load()
        bad = re.compile(r"demo|illustrative|sample|seeded|extract|this copy|\b(?:19|20)\d\d\b|GHS|"
                         + "|".join(map(re.escape, self.NAMES)), re.I)
        for view in DEPARTMENT_VIEWS:
            markup = _html.unescape(views[view])
            hit = bad.search(markup)
            self.assertIsNone(hit, f"{view} markup says {hit and markup[max(0, hit.start() - 60):hit.end() + 20]!r}")
            self.assertNotIn("openDrawer(", markup, f"{view} opens a static drawer")
            for key in set(re.findall(r"explain\('([a-z0-9_]+)'\)", markup)):
                text = _html.unescape(extras["explainers"].get(key, ""))
                self.assertTrue(text, f"{view}: explainer {key} is missing")
                hit = bad.search(text)
                self.assertIsNone(hit, f"{view}: explainer {key} says "
                                       f"{hit and text[max(0, hit.start() - 60):hit.end() + 20]!r}")


# ---------------------------------------------------------------------------------------
# The management screens: Home, Executive Summary, Today, Business Overview, Business
# Health, Approvals, Outstanding Tasks, Risk and Compliance, Systems and Access, Internal
# Audit, Reports, Ask AI and the access-denied page. Nothing on them may be a sample.
# ---------------------------------------------------------------------------------------
CORE_VIEWS = ("command", "brief", "myday", "ops", "health", "approvals", "delegation", "risk",
              "it", "aud", "reports", "ask", "denied")
# A business's own names, figures and dates never sit in the markup: they are read.
NOT_IN_MARKUP = re.compile(
    r"Gigmann|Biomed|Samuel|Simon|Moses|Nketiah|UBUNTU|Ubuntu|HAIRASH|Sunyani|Kumasi|Accra|"
    r"SICHUAN|CYNSEL|Ejura|EJURA|A1 MEDICAL|PUR-ORD|ACC-PAY|SAL-ORD|PROJ-\d|"
    r"[Dd]emo|[Ii]llustrative|[Ss]eeded|prototype|\bGHS\b|\b(19|20)\d{2}\b")


def _js_map(src: str, name: str) -> dict:
    """view -> its slice of one exported label map in a legacy/*.js file."""
    body = re.search(r"export const %s = \{(.*?)\n\};" % name, src, re.S)
    body = body.group(1) if body else ""
    starts = [(m.group(1), m.end()) for m in re.finditer(r"^  (\w+): \{", body, re.M)]
    out = {}
    for i, (view, frm) in enumerate(starts):
        to = starts[i + 1][1] - len(f"  {starts[i + 1][0]}: {{") if i + 1 < len(starts) else len(body)
        out[view] = {html_unescape(l.strip()) for l in re.findall(
            r'^\s*"?([^":\n/]+?)"?:\s*(?:"[a-z0-9_]+"|\{\s*key:)', body[frm:to], re.M)}
    return out


def html_unescape(s):
    import html
    return html.unescape(s)


class ManagementScreens(TransactionTestCase):
    databases = {"default", "aux"}

    def _legacy(self, name):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "frontend" / "src" / "legacy" / name).read_text()

    def test_markup_holds_no_sample(self):
        views = json.loads(self._legacy("views.json"))
        extras = json.loads(self._legacy("extras.json"))
        nav = json.loads(self._legacy("nav.json"))
        hyd, work, home = self._legacy("hydrate.js"), self._legacy("work.js"), self._legacy("home.js")
        cards, tiles, work_tiles = _js_map(hyd, "CARD_KPIS"), _js_map(hyd, "TILE_KPIS"), _js_map(work, "WORK_TILES")
        questions = set(re.findall(r'\["score_\w+", "[^"]+", "([^"]+)"\]', home))
        self.assertEqual(len(questions), 6, "home.js names the six Business Health questions")
        self.assertIn("score_approvals", home, "Were the right people asked? feeds Home's gauge")
        for view in CORE_VIEWS:
            page = views[view]
            # every card and tile has a figure or a guide behind it
            for label in re.findall(r'class="lab">(.*?)</div>', page):
                self.assertIn(html_unescape(label), cards.get(view, set()),
                              f"{view}: card {label!r} has no figure behind it")
            for block in re.split(r'(?=<div class="bk)', page)[1:]:
                label = re.search(r'class="l">(.*?)</div>', block, re.S)
                self.assertTrue(label, f"{view}: a tile with no label")
                label = html_unescape(label.group(1)).strip()
                self.assertTrue(label in tiles.get(view, set()) or label in work_tiles.get(view, set())
                                or (view == "health" and label in questions),
                                f"{view}: tile {label!r} has no figure behind it")
            # no designed alert, request or task, and no sample rows in a table
            self.assertNotIn('class="alert ', page, f"{view} carries a designed alert")
            if view not in ("reports", "it"):
                self.assertNotRegex(page, r"<tbody>\s*<tr", f"{view} carries sample table rows")
            # nothing about one business, no sample wording, no year, no currency
            hit = NOT_IN_MARKUP.search(page)
            self.assertIsNone(hit, f"{view} names {hit and hit.group(0)!r}: "
                                   f"{hit and page[max(0, hit.start() - 80):hit.end() + 40]!r}")
            for key in set(re.findall(r"explain\((?:'|&#39;)(\w+)", page)):
                text = extras["explainers"].get(key, "")
                hit = NOT_IN_MARKUP.search(text)
                self.assertIsNone(hit, f"explainer {key!r} (on {view}) names "
                                       f"{hit and hit.group(0)!r}")
        # the static drills and canned answers are gone, and these screens open no drawer
        self.assertEqual((extras["drill"], extras["brain"]), ({}, []))
        for view in CORE_VIEWS:
            self.assertNotRegex(views[view], r"openDrawer\((?:'|&#39;)\w", f"{view} opens a static drawer")
        # nav badges are never typed in: a number in the sidebar must be counted
        for group in nav["groups"]:
            for item in group["items"]:
                self.assertEqual(item["badge"], "", f"nav {item['key']} carries a typed badge")
        # the check can fail: a typed name, a sample alert, an unmapped card
        self.assertIsNotNone(NOT_IN_MARKUP.search('<b>UBUNTU</b> owes <span class="cx">GHS</span>'))
        self.assertIsNone(NOT_IN_MARKUP.search(views["ops"]))
        self.assertNotIn("Not a real label", cards.get("aud", set()))

    def test_live_figures_guides_and_unreachable(self):
        import requests

        from command_center import install
        from command_center.api import ingest
        from insights.compat import run_as

        Group.objects.get_or_create(name="Insights Dashboard Manager")
        fake = FakeERPNext()
        answer = fake.answer

        def no_findings(m, p):
            # Nothing recorded as a finding or an obligation on this ERPNext yet.
            if m == "frappe.client.get_count" and p.get("doctype") in ("Non Conformance", "Contract"):
                return _R(200, {"message": 0})
            return answer(m, p)
        fake.answer = no_findings
        from django.conf import settings
        from cryptography.fernet import Fernet
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        up = [mock.patch("requests.get", fake("GET")), mock.patch("requests.post", fake("POST")),
              mock.patch("time.sleep", lambda s: None)]
        for p in up:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in up])
        with run_as("Administrator"):
            install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
            ingest.run_all(full=True)
        U = get_user_model()
        m = U.objects.create_user("boss@test.com", "boss@test.com", "a-long-test-pass-9")
        m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        c = Client()
        self.assertTrue(c.login(username="boss@test.com", password="a-long-test-pass-9"))

        def post(method, **args):
            r = c.post(f"/api/method/{method}", json.dumps(args), content_type="application/json")
            self.assertEqual(r.status_code, 200, f"{method}: {r.content[:300]!r}")
            return r.json()["message"]

        from command_center.kpi.live_governance import LIVE as GOV
        got = post("command_center.api.kpi.get", keys=sorted(GOV), business_code="test_medical_ltd")
        for key, fig in got.items():
            self.assertIn(fig["data_status"]["state"], ("live", "needs_setup", "stale"), f"{key}: {fig}")
        # nothing recorded: a guide naming the ERPNext page, never a figure
        for key, path in (("findings_open", "/app/non-conformance"), ("deadlines_overdue", "/app/contract")):
            st = got[key]["data_status"]
            self.assertEqual(st["state"], "needs_setup", key)
            self.assertIsNone(got[key]["value"])
            self.assertIn(path, st["guide"]["href"])
            self.assertTrue(st["guide"]["steps"])
        self.assertEqual(got["score_access"]["note"], "no active accounts")  # the fake has none
        self.assertIsNotNone(got["control_score"]["value"])
        self.assertEqual(got["versions_deletable"]["value"], 0)
        # the risk table is a guide too, and the platform's own people are listed
        risk = post("command_center.api.panels.get", view="risk", business_code="test_medical_ltd")
        self.assertEqual(risk["panels"]["Obligations and deadlines"]["kind"], "guide")
        it = post("command_center.api.panels.get", view="it", business_code="test_medical_ltd")
        people = it["panels"]["Who can sign in to this platform"]["rows"]
        self.assertIn("boss@test.com", [r["cells"][0]["sub"] for r in people])
        # no personal key linked: the work screens get a guide, not someone else's queue
        work = post("command_center.api.work.summary", business_code="test_medical_ltd")
        self.assertFalse(work["available"])
        self.assertIn("Personal ERPNext Keys", " ".join(work["guide"]["steps"]))
        # alerts raised for the first time are emailed once; without mail it is recorded
        alerts = post("command_center.api.alerts.open_alerts", business_code="test_medical_ltd")
        loud = [a for a in alerts["alerts"] if a["severity"] in ("crit", "high")]
        if loud:
            self.assertTrue(all((a["emailed"] or "").startswith("Not emailed") for a in loud), loud)
        self.assertTrue(post("command_center.api.reach.status",
                             business_code="test_medical_ltd")["reachable"])

        # the business's ERPNext stops answering
        def down(*a, **k):
            raise requests.ConnectionError("no route to host")
        with mock.patch("requests.get", down), mock.patch("requests.post", down):
            from django.core.cache import cache
            cache.clear()
            got = post("command_center.api.kpi.get", keys=["users_active", "users_disabled"],
                       business_code="test_medical_ltd")
            self.assertEqual(got["users_active"]["data_status"]["state"], "unreachable")
            self.assertEqual(got["users_disabled"]["data_status"]["state"], "unreachable")
            st = post("command_center.api.reach.status", business_code="test_medical_ltd")
            self.assertFalse(st["reachable"])
            self.assertEqual(st["name"], "Test Medical Ltd")
            self.assertTrue(st["since"])
            from command_center.api import work as work_api
            from command_center.connectors.registry import connector_for
            with mock.patch.object(work_api, "_source", lambda code: (
                    work_api._Remote(connector_for("test_medical_ltd")), None)):
                w = post("command_center.api.work.summary", business_code="test_medical_ltd")
            self.assertTrue(w["unreachable"])
            self.assertIn("Can't reach", w["reason"])
            self.assertFalse(post("command_center.api.reach.retry",
                                  business_code="test_medical_ltd")["reachable"])
        # it answers again: Retry finds it, and the status recovers by itself
        st = post("command_center.api.reach.retry", business_code="test_medical_ltd")
        self.assertTrue(st["reachable"])
        self.assertIsNone(st["since"])


class RefusedIsNotUnreachable(TransactionTestCase):
    """A business that answers but refuses one request (a field its version lacks,
    HTTP 417) stays Active -- no "can't reach" banner -- while one that does not answer,
    or keeps failing with 5xx, is marked Unreachable."""

    databases = {"default", "aux"}

    def test_refused_vs_down(self):
        from cryptography.fernet import Fernet
        from django.conf import settings
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        from command_center import install
        from command_center.connectors.base import BusinessUnreachable, RequestRefused
        from command_center.connectors.registry import connector_for
        from insights.compat import run_as
        from insights.core.models import ConnectedBusiness
        fake = FakeERPNext()
        with mock.patch("requests.get", fake("GET")), mock.patch("requests.post", fake("POST")), \
                mock.patch("time.sleep", lambda s: None):
            with run_as("Administrator"):
                install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
        code = ConnectedBusiness.objects.get().business_code

        def reply(status):
            def call(*a, **k):
                return _R(status, {"exc": "x"})
            return call
        for status, expect, kind in ((417, "Active", RequestRefused),
                                     (503, "Unreachable", BusinessUnreachable)):
            ConnectedBusiness.objects.update(status="Active")
            with mock.patch("requests.get", reply(status)), mock.patch("requests.post", reply(status)), \
                    mock.patch("time.sleep", lambda s: None):
                with run_as("Administrator"):
                    conn = connector_for(code)
                    with self.assertRaises(kind) as caught:
                        conn.get_list("Sales Invoice", fields=["name"], limit=1)
                    if status == 503:
                        self.assertNotIsInstance(caught.exception, RequestRefused)
            self.assertEqual(ConnectedBusiness.objects.get().status, expect, f"after HTTP {status}")


class KnownDownFailsFast(TransactionTestCase):
    """A business already marked Unreachable costs a screen no network wait: its live
    reads give up at once (the banner says why), while loaded-data panels still answer."""

    databases = {"default", "aux"}

    def test_no_network_call(self):
        from cryptography.fernet import Fernet
        from django.conf import settings
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        from command_center import install
        from command_center.api import panels
        from insights.compat import run_as
        from insights.core.models import ConnectedBusiness
        fake = FakeERPNext()
        with mock.patch("requests.get", fake("GET")), mock.patch("requests.post", fake("POST")), \
                mock.patch("time.sleep", lambda s: None):
            with run_as("Administrator"):
                code = install.register_business("Test Medical Ltd", "https://erp.test", "key",
                                                 "s3cret")["code"]
        ConnectedBusiness.objects.update(status="Unreachable")

        def no_network(*a, **k):
            raise AssertionError("a known-down business was contacted")
        with mock.patch("requests.get", no_network), mock.patch("requests.post", no_network):
            with run_as("Administrator"):
                out = panels.get("proc", code)
        # the purchase-order panels read ERPNext live: they say so, without waiting
        for title in ("Where the money goes", "How long each supplier takes", "Orders still open"):
            self.assertEqual(out["panels"][title]["kind"], "unreachable", title)


class EveryErpnextVersion(TransactionTestCase):
    """One platform for ERPNext 14, 15 and 16. Reads are fitted to the site's own
    definition: a renamed field is asked for by the site's name and handed back under
    the asked-for one; an optional column the site lacks comes back empty instead of
    failing the read; a filter on a field the site lacks is never dropped."""

    databases = {"default", "aux"}

    def test_v16_shaped_site(self):
        from cryptography.fernet import Fernet
        from django.conf import settings
        from django.core.cache import cache
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        from command_center import install
        from command_center.connectors.base import RequestRefused
        from command_center.connectors.registry import connector_for
        from insights.compat import run_as
        cache.clear()
        fake = FakeERPNext()
        with mock.patch("requests.get", fake("GET")), mock.patch("requests.post", fake("POST")), \
                mock.patch("time.sleep", lambda s: None):
            with run_as("Administrator"):
                code = install.register_business("Test Medical Ltd", "https://erp.test", "k",
                                                 "s")["code"]
        site = {"Issue": ["subject", "status", "sla_resolution_by", "sla_resolution_date"],
                "Employee": ["employee_name", "department", "status"],
                "Budget": ["cost_center", "account", "budget_amount", "from_fiscal_year"]}
        asked = []

        def answer(m, p):
            if m == "frappe.desk.form.load.getdoctype":
                dt = p.get("doctype")
                return _R(200, {"docs": [{"name": dt, "fields": [
                    {"fieldname": f} for f in site.get(dt, [])]}]})
            if m == "frappe.client.get_list":
                f = json.loads(p["fields"]) if isinstance(p["fields"], str) else p["fields"]
                flt = p.get("filters") or {}
                flt = json.loads(flt) if isinstance(flt, str) else flt
                asked.append((p["doctype"], list(f), flt))
                known = set(site.get(p["doctype"], [])) | {"name"}
                keys = flt.keys() if isinstance(flt, dict) else [x[0] for x in flt]
                if any(k not in known for k in list(f) + list(keys)):
                    return _R(417, {"exc": "Field not permitted in query"})
                return _R(200, {"message": [{c: f"{c}-1" for c in f}]})
            return fake.answer(m, p)
        fake.answer = answer
        with mock.patch("requests.get", fake("GET")), mock.patch("requests.post", fake("POST")), \
                mock.patch("time.sleep", lambda s: None):
            with run_as("Administrator"):
                conn = connector_for(code)
                # renamed: asked as sla_resolution_by, handed back as resolution_by
                rows = conn.get_list("Issue", fields=["name", "resolution_by", "resolution_date"],
                                     filters={"resolution_by": ["is", "set"]}, limit=5)
                self.assertEqual(rows[0]["resolution_by"], "sla_resolution_by-1")
                self.assertEqual(rows[0]["resolution_date"], "sla_resolution_date-1")
                self.assertIn("sla_resolution_by", asked[-1][2])
                # optional column the site lacks: empty, the read still succeeds
                rows = conn.get_list("Employee", fields=["name", "employee_name", "employment_type"],
                                     limit=5)
                self.assertIsNone(rows[0]["employment_type"])
                self.assertEqual(rows[0]["employee_name"], "employee_name-1")
                # a filter on a field the site lacks is never dropped: it still fails
                with self.assertRaises(RequestRefused):
                    conn.get_list("Budget", fields=["name"], filters={"fiscal_year": "2026"})


class SettingsReachEveryProcess(TransactionTestCase):
    """A setting changed in one process (Settings -> Claude key) is what every other
    process -- the other web workers, the scheduler -- uses from its next unit of work,
    without a restart."""

    databases = {"default", "aux"}

    def test_key_change_seen_without_restart(self):
        import os
        import tempfile
        import time
        from django.conf import settings
        import insights.compat as compat
        from insights.compat import run_as
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "insights.json")
            with open(path, "w") as fh:
                json.dump({**settings.CONFIG, "command_center_anthropic_key": "sk-ant-old"}, fh)
            saved = dict(settings.CONFIG)
            with mock.patch.object(settings, "CONFIG_PATH", path):
                compat._config_stamp[0] = None
                with run_as("Administrator"):
                    pass  # first look: remembers the file as it is
                # "another process" writes a new key
                time.sleep(0.01)
                with open(path, "w") as fh:
                    json.dump({**saved, "command_center_anthropic_key": "sk-ant-new"}, fh)
                os.utime(path, None)
                with run_as("Administrator"):
                    self.assertEqual(compat.conf.get("command_center_anthropic_key"), "sk-ant-new")
            settings.CONFIG.clear(); settings.CONFIG.update(saved)
            compat.conf.clear(); compat.conf.update(saved)
            compat._config_stamp[0] = None


class LeaveArithmetic(TransactionTestCase):
    """People Lookup and Leave (api/people.py) against a fake ERPNext with HR records:
    the directory's search, filters and paging; the leave balances worked by hand
    (hr_dataset), carry-forward and a pending application included; no pay or bank
    detail ever asked for or returned; guides where the HR app or the allocations are
    missing; "can't reach" when the business does not answer; and the analyst's tools.

    The same arithmetic was checked against HRMS's own Employee Leave Balance report on
    Gigmann's ERPNext (v14, HRMS 14), read-only, on 15 Nov 2026: for HR-EMP-00018,
    -00023 and -00036 every leave type's closing balance and leave taken agreed --
    including a maternity leave running from December into the year, of which the
    report counts the 62 days inside the year and the balance the whole 84."""

    databases = {"default", "aux"}

    def setUp(self):
        from django.conf import settings
        from django.core.cache import cache
        from cryptography.fernet import Fernet
        from command_center import install
        from insights.compat import run_as
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        cache.clear()
        self.fake = FakeERPNext(hr=hr_dataset())
        up = [mock.patch("requests.get", self.fake("GET")),
              mock.patch("requests.post", self.fake("POST")),
              mock.patch("time.sleep", lambda s: None)]
        for p in up:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in up])
        self.addCleanup(cache.clear)
        with run_as("Administrator"):
            install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
        U = get_user_model()
        m = U.objects.create_user("boss@test.com", "boss@test.com", "a-long-test-pass-9")
        m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        self.c = Client()
        self.assertTrue(self.c.login(username="boss@test.com", password="a-long-test-pass-9"))

    def post(self, fn, **args):
        r = self.c.post(f"/api/method/command_center.api.people.{fn}",
                        json.dumps({"business_code": "test_medical_ltd", **args}),
                        content_type="application/json")
        self.assertEqual(r.status_code, 200, f"{fn}: {r.content[:400]!r}")
        return r.json()["message"]

    def _reset(self, hr):
        from django.core.cache import cache
        cache.clear()
        self.fake.hr = hr

    def test_directory_search_filters_paging(self):
        d = self.post("directory")
        self.assertEqual(d["kind"], "directory")
        self.assertEqual((d["total"], d["on_books"]), (4, 4))
        # active people first, by name; the leaver last
        self.assertEqual([r["name"] for r in d["rows"]],
                         ["Ama Mensah", "Esi Owusu", "Kofi Boateng", "Yaw Darko"])
        ama = d["rows"][0]
        self.assertEqual(ama["reports_to_name"], "Kofi Boateng")
        self.assertTrue(ama["has_user"])
        self.assertEqual(ama["photo"], "https://erp.test/files/ama.jpg")
        self.assertEqual(d["rows"][2]["photo"], "")       # a private file is not offered
        self.assertEqual(d["rows"][3]["tenure"], "2 years 4 months")  # ends when they left
        self.assertNotIn("_user", ama)
        self.assertEqual(d["filters"]["departments"], ["Sales", "Stores"])
        self.assertEqual([r["employee"] for r in self.post("directory", q="mensah")["rows"]],
                         ["HR-EMP-001"])
        self.assertEqual(self.post("directory", q="sales north")["total"], 2)
        self.assertEqual(self.post("directory", q="HR-EMP-004")["rows"][0]["status"], "Left")
        self.assertEqual(self.post("directory", department="Stores", status="Active")["total"], 1)
        self.assertEqual(self.post("directory", status="Active")["total"], 3)
        self.assertEqual(self.post("directory", q="nobody at all")["rows"], [])
        p2 = self.post("directory", page=2, page_size=3)
        self.assertEqual((p2["page"], p2["pages"], len(p2["rows"])), (2, 2, 1))
        self.assertEqual(self.post("directory", page=9, page_size=3)["page"], 2)

    def test_leave_by_hand(self):
        from command_center.api import people as P
        prof = self.post("profile", employee="HR-EMP-001")
        self.assertEqual(prof["kind"], "profile")
        self.assertEqual(prof["leave"]["state"], "ok")
        got = {t["leave_type"]: t for t in prof["leave"]["types"]}
        self.assertEqual({k: got["Annual Leave"][k] for k in
                          ("allocated", "carried_forward", "new", "taken", "pending",
                           "remaining", "expired")},
                         {"allocated": 23, "carried_forward": 3, "new": 20, "taken": 10.5,
                          "pending": 2, "remaining": 12.5, "expired": 0})
        self.assertEqual({k: got["Sick Leave"][k] for k in ("allocated", "taken", "pending",
                                                            "remaining")},
                         {"allocated": 5, "taken": 0, "pending": 1, "remaining": 5})
        kofi = self.post("profile", employee="HR-EMP-002")["leave"]["types"][0]
        self.assertEqual({k: kofi[k] for k in ("allocated", "taken", "remaining", "expired")},
                         {"allocated": 14, "taken": 3, "remaining": 10, "expired": 1})
        # the pieces, alone: a half day, holidays out, clipping to the period
        self.assertEqual(P.leave_days(TODAY, TODAY + dt.timedelta(days=1), True,
                                      TODAY + dt.timedelta(days=1)), 1.5)
        self.assertEqual(P.leave_days(TODAY, TODAY + dt.timedelta(days=6), holidays=2), 5)
        self.assertEqual(P.leave_days(TODAY, TODAY + dt.timedelta(days=6), include_holiday=True,
                                      holidays=2), 7)
        self.assertEqual(P.leave_days(TODAY, TODAY, True), 0.5)

        # the rest of the profile
        self.assertEqual(prof["manager"]["name"], "Kofi Boateng")
        self.assertEqual([r["name"] for r in prof["reports"]], ["Esi Owusu"])
        self.assertEqual(len(prof["applications"]["items"]), 6)
        self.assertEqual(prof["attendance"]["marked"], min(3, TODAY.day))
        self.assertEqual(prof["todos"]["open"], 1)
        self.assertEqual(prof["todos"]["items"][0]["text"], "Call Ridge Hospital about the order")
        self.assertEqual(prof["todos"]["items"][0]["href"], "https://erp.test/app/sales-order/SO-00001")
        self.assertEqual(prof["appraisals"]["items"][0]["score"], 4.2)
        self.assertEqual(prof["training"]["items"][0]["event"], "Equipment Safety")
        self.assertEqual(prof["assets"]["items"][0]["asset"], "Laptop")
        self.assertEqual(prof["payroll"], {"state": "ok", "structure": True, "last_slip": _day(-15)})
        self.assertEqual(self.post("profile", employee="HR-EMP-002")["todos"]["state"], "no_user")
        self.assertEqual(self.post("profile", employee="HR-EMP-999")["kind"], "missing")

        # the overview: everyone active, who is away, what is waiting
        lv = self.post("leave_overview")
        self.assertEqual(lv["kind"], "leave")
        self.assertEqual([t["name"] for t in lv["types"]], ["Annual Leave", "Sick Leave"])
        rows = {r["employee"]: r for r in lv["rows"]}
        self.assertEqual(sorted(rows), ["HR-EMP-001", "HR-EMP-002", "HR-EMP-003"])  # no leaver
        self.assertEqual(rows["HR-EMP-001"]["balances"]["Annual Leave"]["remaining"], 12.5)
        self.assertEqual(rows["HR-EMP-002"]["balances"]["Annual Leave"]["remaining"], 10)
        self.assertEqual(lv["without"], 1)
        self.assertEqual([a["name"] for a in lv["away_today"]], ["LAP-7"])
        self.assertEqual([a["name"] for a in lv["pending"]], ["LAP-5", "LAP-6"])  # longest wait first
        self.assertEqual(lv["pending"][0]["waiting_days"], 4)
        self.assertEqual(lv["pending"][0]["approver"], "The Boss")
        self.assertEqual(sum(d["people"] for d in lv["departments"]), 3)
        # leave taken over a window, for the by-department table
        with mock.patch.object(P, "require_manager", lambda: None):
            from insights.compat import run_as
            with run_as("Administrator"):
                ctx = P._Ctx("test_medical_ltd")
                book = P._LeaveBook(ctx, ["HR-EMP-001"])
                self.assertEqual(book.taken("HR-EMP-001", TODAY - dt.timedelta(days=100), TODAY, "HL"),
                                 10.5)

    def test_no_pay_ever(self):
        # written out here, not imported: a field added to the reads must be argued for
        allowed = {"name", "employee_name", "status", "department", "designation", "branch",
                   "employment_type", "date_of_joining", "relieving_date", "reports_to",
                   "company_email", "cell_number", "user_id", "image", "holiday_list",
                   "company"}
        out = json.dumps([self.post("directory"), self.post("profile", employee="HR-EMP-001"),
                          self.post("profile", employee="HR-EMP-002"), self.post("leave_overview")])
        for secret in ("99999", "88888", "0123456789", "9876543210", "4321", "3210", "55555",
                       "7777", "private reason", "1990-01-01", "salary_mode"):
            self.assertNotIn(secret, out)
        asked = defaultdict_list(self.fake.hr_reads)
        self.assertTrue(set().union(*asked["Employee"]) <= allowed, asked["Employee"])
        self.assertEqual(set().union(*asked["Salary Slip"]), {"end_date"})
        self.assertNotIn("Salary Structure Assignment", asked)   # counted, never listed
        self.assertNotIn("gross_purchase_amount", set().union(*asked["Asset"]))
        self.assertNotIn("description", set().union(*asked["Leave Application"]))

    def test_guides_without_hrms_or_allocations(self):
        self._reset(hr_dataset(installed=False))
        self.assertEqual(self.post("directory")["total"], 4)   # Employee is ERPNext's own
        lv = self.post("leave_overview")
        self.assertEqual(lv["kind"], "guide")
        self.assertIn("HR app", lv["guide"]["text"])
        self.assertIn("Leave Type", " ".join(lv["guide"]["steps"]))
        self.assertIn("Holiday List", " ".join(lv["guide"]["steps"]))
        self.assertTrue(lv["guide"]["href"].startswith("https://erp.test/"))
        prof = self.post("profile", employee="HR-EMP-001")
        self.assertEqual(prof["leave"]["state"], "guide")
        for part in ("applications", "attendance", "appraisals", "training", "payroll"):
            self.assertEqual(prof[part]["state"], "not_installed", part)

        self._reset(hr_dataset(allocations=False))
        lv = self.post("leave_overview")
        self.assertEqual(lv["kind"], "guide")
        self.assertIn("No one has leave allocated", lv["guide"]["text"])
        self.assertIn("Leave Allocation", " ".join(lv["guide"]["steps"]))
        self.assertEqual(self.post("profile", employee="HR-EMP-001")["leave"]["state"], "none")

        self._reset({"installed": True, "Employee": []})
        self.assertEqual(self.post("directory")["kind"], "guide")

    def test_analyst_tools(self):
        from command_center.ask import tools
        from insights.compat import run_as
        with run_as("boss@test.com"):
            one = tools.run("leave", {"person": "ama"}, "test_medical_ltd")
            self.assertTrue(one["answered"])
            annual = [t for t in one["leave"]["types"] if t["leave_type"] == "Annual Leave"][0]
            self.assertEqual(annual["remaining"], 12.5)
            everyone = tools.run("leave", {}, "test_medical_ltd")
            self.assertEqual([a["employee_name"] for a in everyone["away_this_week"]], ["Esi Owusu"])
            self.assertEqual(len(everyone["pending_approval"]), 2)
            found = tools.run("people", {"text": "kofi"}, "test_medical_ltd")
            self.assertEqual(found["people"][0]["designation"], "Store Manager")
            self.assertNotIn("0200000001", json.dumps(tools.run("people", {}, "test_medical_ltd")))
            self.assertFalse(tools.run("leave", {"person": "nobody"}, "test_medical_ltd")["answered"])
        self.assertIn("leave", [d["name"] for d in tools.declarations()])

    def test_managers_only_and_unreachable(self):
        import requests
        U = get_user_model()
        U.objects.create_user("clerk@test.com", "clerk@test.com", "a-long-test-pass-8")
        c2 = Client()
        c2.login(username="clerk@test.com", password="a-long-test-pass-8")
        r = c2.post("/api/method/command_center.api.people.directory", "{}",
                    content_type="application/json")
        self.assertNotEqual(r.status_code, 200)

        def down(*a, **k):
            raise requests.ConnectionError("no route to host")
        from django.core.cache import cache
        cache.clear()
        with mock.patch("requests.get", down), mock.patch("requests.post", down):
            for fn, args in (("directory", {}), ("profile", {"employee": "HR-EMP-001"}),
                             ("leave_overview", {})):
                got = self.post(fn, **args)
                self.assertEqual(got["kind"], "unreachable", fn)
                self.assertEqual(got["business"], "Test Medical Ltd", fn)


def defaultdict_list(reads):
    """(doctype, fields) reads -> doctype: [set of fields asked, per read]."""
    out = {}
    for doctype, fields in reads:
        out.setdefault(doctype, []).append(set(fields))
    return out

# ---------------------------------------------------------------------------------------
# Recommendations (command_center/recommend/): every rule on crafted data, the ranking,
# the lifecycle, the bell, Settings, the Daily Brief and the digest.
# ---------------------------------------------------------------------------------------
REC_CODE = "test_medical_ltd"


class _RecReader:
    """The business's ERPNext as the recommendation rules read it, answering from a table
    of rows per doctype (each row cut to the fields asked for)."""

    local = False

    def __init__(self, live, fail=()):
        self.live, self.fail, self.code = live, set(fail), REC_CODE
        self.conn = self

    base_url = "https://erp.test"

    def get_list(self, doctype, filters=None, fields=None, group_by=None, limit=None,
                 parent_doctype=None, order_by=None, **kw):
        if doctype in self.fail:
            raise RuntimeError(f"{doctype} refused")
        rows = self.live.get(doctype) or []
        rows = rows(filters or {}) if callable(rows) else rows
        cols = [re.split(r"\s+as\s+", str(f))[-1].strip() for f in (fields or ["name"])]
        return [{c: r.get(c) for c in cols} for r in rows]

    def all(self, doctype, filters=None, fields=None, limit=100000, parent=None, order_by=None):
        return self.get_list(doctype, filters, fields)

    def count(self, doctype, filters=None):
        return len(self.get_list(doctype, filters))

    def get_count(self, doctype, filters=None):
        return self.count(doctype, filters)

    def has(self, doctype):
        return True


class Recommendations(TransactionTestCase):
    databases = {"default", "aux"}
    MOD = "command_center.api.recommend"
    setUp_settings = SettingsPage.setUp
    tearDown = SettingsPage.tearDown
    _call = SettingsPage._call
    _ok = SettingsPage._ok
    _refused = SettingsPage._refused

    def setUp(self):
        self.setUp_settings()
        from command_center import install
        from insights.compat import run_as
        with run_as("Administrator"):
            install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
        self.live = self._live()
        self.reader = _RecReader(self.live)
        from command_center.recommend import engine
        real = engine._context

        def ctx(code):
            c = real(code)
            c._reader = self.reader
            return c
        p = mock.patch.object(engine, "_context", ctx)
        p.start()
        self.patches.append(p)
        self._rich()

    # ------------------------------------------------------------------ the crafted data
    def _fact(self, model, **kw):
        import uuid
        key = uuid.uuid4().hex
        kw.setdefault("src_docstatus", 1)
        if hasattr(model, "as_of_date"):
            kw.setdefault("as_of_date", TODAY)
        return model.objects.create(name=key, fact_key=key, business_code=REC_CODE, **kw)

    def _rich(self):
        from insights.core import models as M
        d = lambda n: TODAY - dt.timedelta(days=n)  # noqa: E731
        PB = M.CommandCenterFactPartyBalance
        self._fact(PB, party_type="Customer", party="Alpha Clinic", ledger_balance=150000,
                   owed=150000, open_invoices=160000, unmatched_payments=10000,
                   unmatched_payment_count=2, overdue=130000, d90_plus=120000, not_due=20000,
                   oldest_due_after_matching=d(200))
        self._fact(PB, party_type="Customer", party="Beta Hospital", ledger_balance=-5000,
                   in_credit=5000)
        self._fact(PB, party_type="Supplier", party="Sup One", ledger_balance=200000,
                   owed=200000, open_invoices=208000, unmatched_payments=8000,
                   unmatched_payment_count=1, overdue=150000, d90_plus=50000, not_due=50000)
        self._fact(PB, party_type="Supplier", party="Sup Two", ledger_balance=-1000, in_credit=1000)
        SI, SL = M.CommandCenterFactSalesInvoice, M.CommandCenterFactSalesInvoiceLine
        self._fact(SI, src_name="SI-NEW", customer="Alpha Clinic", posting_date=d(5),
                   base_grand_total=2000, outstanding_amount=2000)
        for i, n in enumerate((450, 400, 330, 250, 120)):
            self._fact(SI, src_name=f"SI-G{i}", customer="Gamma Labs", posting_date=d(n),
                       base_grand_total=8000)
        for i in range(2):
            self._fact(SI, src_name=f"SI-D{i}", customer="Delta", posting_date=d(30),
                       base_grand_total=1500, src_docstatus=0)
        last_month_end = TODAY.replace(day=1) - dt.timedelta(days=1)
        last_month = last_month_end.replace(day=10)
        ly = last_month.replace(year=last_month.year - 1)
        line = lambda **kw: self._fact(SL, src_name=kw.pop("inv", "SI-L"), **kw)  # noqa: E731
        line(posting_date=last_month, item_group="Monitors", item_code="MON-1", customer="C1",
             base_net_amount=5000, base_margin_amount=1000, has_cost=1)
        line(posting_date=ly, item_group="Monitors", item_code="MON-1", customer="C1",
             base_net_amount=50000, base_margin_amount=10000, has_cost=1)
        for i, c in enumerate(("C1", "C2", "C3", "C4", "C5", "C6")):
            line(posting_date=d(40), item_group="Consumables", item_code="CON-1", customer=c,
                 base_net_amount=1000 * (i + 1), base_margin_amount=200, has_cost=1)
        line(posting_date=last_month, item_group="Beds", item_code="BED-1", customer="C2",
             base_net_amount=30000, base_margin_amount=3000, has_cost=1)
        line(posting_date=last_month.replace(year=last_month.year - 1) - dt.timedelta(days=40),
             item_group="Beds", item_code="BED-1", customer="C2", base_net_amount=30000,
             base_margin_amount=9000, has_cost=1)
        line(posting_date=d(20), item_group="Beds", item_code="BED-2", customer="C3",
             base_net_amount=1000, base_margin_amount=-2000, has_cost=1)
        line(posting_date=d(60), item_group="Services", item_code="SRV-1", customer="C4",
             base_net_amount=20000, base_margin_amount=0, has_cost=0)
        PA = M.CommandCenterFactPaymentAllocation
        for i in range(20):
            self._fact(PA, payment_type="Receive", against_doctype="Sales Invoice",
                       posting_date=d(10 + i), days_to_pay=40, allocated_amount=100)
            self._fact(PA, payment_type="Receive", against_doctype="Sales Invoice",
                       posting_date=d(100 + i), days_to_pay=10, allocated_amount=100)
        SO = M.CommandCenterFactSalesOrder
        self._fact(SO, src_name="SO-LATE", customer="Alpha Clinic", is_open=1, days_late=10,
                   lateness_bucket="0-30", undelivered_value=7000, base_grand_total=7000)
        self._fact(SO, src_name="SO-DONE", customer="C2", is_open=1, per_delivered=100,
                   unbilled_value=4000, base_grand_total=4000, lateness_bucket="Not due")
        SB = M.CommandCenterFactStockBalance
        self._fact(SB, item_code="ITEM-SLOW", warehouse="Stores", actual_qty=10,
                   stock_value=20000, has_valuation=1)
        self._fact(SB, item_code="ITEM-FAST", warehouse="Stores", actual_qty=5,
                   stock_value=500, has_valuation=1)
        self._fact(SB, item_code="ITEM-RES", warehouse="Stores", actual_qty=2, reserved_qty=10,
                   stock_value=200, has_valuation=1)
        self._fact(SB, item_code="ITEM-NOVAL", warehouse="Stores", actual_qty=3,
                   stock_value=0, has_valuation=0)
        self._fact(M.CommandCenterFactTask, src_name="T-1", is_open=1, days_late=12,
                   assigned_to="eng@test.com", exp_end_date=d(12))
        for i in range(3):
            self._fact(M.CommandCenterFactPerson, src_name=f"E-{i}", status="Left",
                       department="Sales", relieving_date=d(20 + i), is_active=0)
        self._fact(M.CommandCenterFactPerson, src_name="E-9", status="Active",
                   department="Sales Dept", is_active=1)
        self._fact(M.CommandCenterFactPurchaseInvoice, src_name="PINV-1", supplier="Sup One",
                   outstanding_amount=5000, base_grand_total=5000, posting_date=d(30))
        PL = M.CommandCenterFactPurchaseInvoiceLine
        for s, v in (("Sup One", 80000), ("Sup Two", 10000), ("Sup Three", 5000)):
            self._fact(PL, src_name="PINV-L", supplier=s, posting_date=d(50), base_net_amount=v)

    def _live(self):
        d = lambda n: str(TODAY - dt.timedelta(days=n))  # noqa: E731
        now = dt.datetime.now()

        def pos(f):
            if f.get("docstatus") == 0:
                return [{"name": f"PO-W{i}", "workflow_state": "Pending DIR Approval",
                         "creation": (now - dt.timedelta(days=70)).strftime("%Y-%m-%d %H:%M:%S"),
                         "base_grand_total": 30000} for i in range(3)]
            if "name" in f:
                return [{"name": "PO-1", "owner": "a@test.com"}]
            return [{"name": "PO-1", "supplier": "Sup One", "base_grand_total": 9000,
                     "transaction_date": d(60), "schedule_date": d(30), "per_received": 0,
                     "per_billed": 0, "status": "To Receive and Bill"}]
        return {
            "Stock Ledger Entry": [{"item_code": "ITEM-FAST", "out_qty": -90, "moves": 9}],
            "Account": [{"name": "Bank - T"}],
            "GL Entry": [{"account": "Bank - T", "debit_total": 30000, "credit_total": 10000}],
            "Sales Invoice Item": [{"parent": "SI-X", "item_code": "CON-1", "qty": 200,
                                    "price_list_rate": 100, "rate": 50, "pricing_rules": ""}],
            "Batch": [{"name": "B1", "item": "ITEM-FAST", "expiry_date": str(TODAY + dt.timedelta(days=10)),
                       "batch_qty": 5}],
            "Purchase Order": pos,
            "Purchase Order Item": [{"parent": "PO-1", "item_code": "ITEM-SLOW", "qty": 10,
                                     "received_qty": 0, "base_net_amount": 9000}],
            "Purchase Invoice Item": [{"parent": "PINV-1", "purchase_order": None,
                                       "purchase_receipt": None}],
            "Purchase Invoice": [{"name": "PINV-1", "update_stock": 0}],
            "Workflow": [{"name": "PO WF", "document_type": "Purchase Order",
                          "workflow_state_field": "workflow_state"}],
            "Workflow Document State": [
                {"parent": "PO WF", "idx": 1, "state": "Draft", "doc_status": "0"},
                {"parent": "PO WF", "idx": 2, "state": "Pending DIR Approval", "doc_status": "0"},
                {"parent": "PO WF", "idx": 3, "state": "Approved", "doc_status": "1"},
                {"parent": "PO WF", "idx": 4, "state": "Rejected by DIR", "doc_status": "0"}],
            "Version": [{"ref_doctype": "Purchase Order", "docname": "PO-1", "owner": "a@test.com"}],
            "Department": [{"name": "Sales Dept"}, {"name": "Sales"}],
        }

    def _quiet(self):
        from django.core.cache import cache
        from insights.core import models as M
        for name in dir(M):
            model = getattr(M, name)
            if name.startswith("CommandCenterFact"):
                model.objects.filter(business_code=REC_CODE).delete()
        self.live.clear()
        cache.clear()

    def _compute(self):
        from command_center.recommend import engine
        from insights.compat import run_as
        with run_as("Administrator"):
            return engine.compute(REC_CODE)

    # ------------------------------------------------------------------ the tests
    def test_every_rule_fires_and_stays_silent(self):
        from command_center.recommend.rules import RULES
        out = self._compute()
        self.assertEqual(out["failed"], {}, out["failed"])
        fired = {r["rule"] for r in out["recs"]}
        missing = [r.rule_id for r in RULES if r.rule_id not in fired]
        self.assertEqual(missing, [], f"rules that did not fire on crafted data: {missing}")
        for r in out["recs"]:
            for k in ("id", "rule", "area", "severity", "title", "why", "what_to_do",
                      "how_in_erpnext", "ask", "drill", "owner_role", "money_at_stake"):
                self.assertIn(k, r, f"{r['rule']} has no {k}")
            self.assertIsInstance(r["money_at_stake"], float)
            self.assertTrue(2 <= len(r["what_to_do"]) <= 4, r["rule"])
            self.assertTrue(r["how_in_erpnext"].get("steps"), r["rule"])
            self.assertTrue(r["title"].endswith("."), r["title"])
            self.assertEqual(r["currency"], "GHS")
            self.assertNotRegex(r["why"] + r["title"], r"\bnan\b|None|\{", r["rule"])
        by = {}
        for r in out["recs"]:
            by.setdefault(r["rule"], r)        # ranked: the largest of each rule first
        self.assertTrue(by["unmatched_receipts"]["how_in_erpnext"]["href"].endswith(
            "/app/payment-reconciliation"))
        self.assertEqual(by["unmatched_receipts"]["money_at_stake"], 10000)
        self.assertEqual(by["customers_in_credit"]["money_at_stake"], 5000)
        self.assertEqual(by["overdue_customers"]["severity"], "crit")
        self.assertEqual(by["supplier_payments_due"]["severity"], "crit")   # due > bank 20,000
        self.assertIn("GHS 20,000", by["supplier_payments_due"]["why"])
        self.assertEqual(by["approvals_bottleneck"]["money_at_stake"], 90000)
        self.assertIn("Pending DIR Approval", by["approvals_bottleneck"]["title"])
        self.assertEqual(by["discounts_outside_price_list"]["money_at_stake"], 10000)
        self.assertEqual(by["sales_falling"]["money_at_stake"], 45000)
        # what is owed is the ledger: the unmatched customer's rec says both figures
        self.assertIn("GHS 160,000", by["unmatched_receipts"]["why"])
        self.assertIn("GHS 150,000", by["unmatched_receipts"]["why"])

        self._quiet()
        out = self._compute()
        self.assertEqual((out["recs"], out["failed"]), ([], {}))

    def test_thresholds_and_switches(self):
        from command_center.recommend import engine
        conf = engine.settings(REC_CODE)
        conf["rules"]["unmatched_receipts"]["params"]["amount"] = 10000   # not more than
        conf["rules"]["customers_in_credit"]["enabled"] = False
        engine.save_settings(REC_CODE, conf)
        fired = {r["rule"] for r in self._compute()["recs"]}
        self.assertNotIn("unmatched_receipts", fired)
        self.assertNotIn("customers_in_credit", fired)
        self.assertIn("overdue_customers", fired)

    def test_ranking(self):
        from command_center.recommend.engine import rank
        recs = rank([{"id": "a", "score": 100, "severity": "med"},
                     {"id": "b", "score": 700, "severity": "high"},
                     {"id": "c", "score": 0, "severity": "crit", "count": 4},
                     {"id": "d", "score": 0, "severity": "info", "count": 9}])
        self.assertEqual([r["id"] for r in recs], ["b", "a", "c", "d"])
        out = self._compute()["recs"]
        scores = [r["score"] for r in out]
        self.assertEqual(scores, sorted(scores, reverse=True))
        top = out[0]
        self.assertEqual(top["rule"], "supplier_payments_due")   # 200k at stake, critical

    def test_lifecycle(self):
        from command_center.api import recommend as api
        from command_center.recommend import engine
        from insights.compat import run_as
        from insights.core.models import CommandCenterRecommendation as R

        with run_as("boss@test.com"):
            engine.refresh(REC_CODE)
            shown = {r["id"]: r for r in engine.visible(REC_CODE)}
            self.assertIn("unmatched_receipts", shown)
            n = R.objects.count()
            engine.refresh(REC_CODE)                          # the same condition: no new rows
            self.assertEqual(R.objects.count(), n)
            api.act(shown["unmatched_receipts"]["name"], "done")
            api.act(shown["customers_in_credit"]["name"], "snooze", days=7)
            api.act(shown["credit_hold"]["name"], "not_relevant", reason="cash customers")
            with self.assertRaises(Exception):
                api.act(shown["late_orders"]["name"], "snooze", days=3)
            ids = {r["id"] for r in engine.visible(REC_CODE)}
            self.assertFalse({"unmatched_receipts", "customers_in_credit", "credit_hold"} & ids)
            # a snooze whose date has come is open again; Done still there after a week is too
            R.objects.filter(rec_key="customers_in_credit").update(snoozed_until=TODAY - dt.timedelta(days=1))
            R.objects.filter(rec_key="unmatched_receipts").update(
                acted_on=dt.datetime.now() - dt.timedelta(days=8))
            engine.refresh(REC_CODE)
            again = {r["id"]: r for r in engine.visible(REC_CODE)}
            self.assertIn("customers_in_credit", again)
            self.assertEqual(again["unmatched_receipts"]["reopened_after_done"],
                             str((dt.datetime.now() - dt.timedelta(days=8)).date()))
            # a rule that cannot be read resolves nothing
            self.reader.fail.add("Workflow")
            engine.refresh(REC_CODE)
            self.assertTrue(R.objects.filter(rule="approvals_bottleneck", resolved_on__isnull=True).exists())
            self.reader.fail.clear()
            # the condition clears: Resolved, kept as history; Not Relevant keeps its word
            from insights.core.models import CommandCenterFactPartyBalance as PB
            PB.objects.filter(party="Alpha Clinic").update(unmatched_payments=0,
                                                           unmatched_payment_count=0, d90_plus=0)
            engine.refresh(REC_CODE)
            gone = R.objects.get(rec_key="unmatched_receipts")
            self.assertEqual(gone.status, "Resolved")
            self.assertIsNotNone(gone.resolved_on)
            self.assertEqual(R.objects.get(rec_key="credit_hold").status, "Not Relevant")
            self.assertIn("unmatched_receipts", {r["id"] for r in engine.history(REC_CODE)})
            # it comes back: a new row, Open
            PB.objects.filter(party="Alpha Clinic").update(unmatched_payments=10000,
                                                           unmatched_payment_count=2)
            engine.refresh(REC_CODE)
            self.assertEqual(R.objects.filter(rec_key="unmatched_receipts").count(), 2)
            # Not Relevant twice for one rule: the administrator is told to raise it
            self.assertEqual(engine.suggestions(REC_CODE), {})
            api.act(R.objects.get(rec_key="unmatched_receipts", resolved_on__isnull=True).name,
                    "not_relevant")
            api.act(R.objects.get(rec_key="unmatched_supplier_payments").name, "not_relevant")
            R.objects.filter(rec_key="unmatched_supplier_payments").update(rule="unmatched_receipts")
            self.assertEqual(engine.suggestions(REC_CODE), {"unmatched_receipts": 2})
        view = self._ok_settings("recommendations")
        rule = next(r for r in view["rules"] if r["rule_id"] == "unmatched_receipts")
        self.assertIn("consider raising", rule["suggestion"])

    def test_screens_and_bell(self):
        from command_center.alerts.engine import DOCTYPE
        import frappe
        from insights.compat import run_as
        r = self._call(self.manager, "current", business_code=REC_CODE)
        self.assertEqual(r.status_code, 200, r.content[:300])
        got = r.json()["message"]
        self.assertTrue(got["recommendations"])
        self.assertIsNone(got["brief"])                     # off by default
        crit = {x["rule"] for x in self._call(self.manager, "critical",
                                              business_code=REC_CODE).json()["message"]["recommendations"]}
        self.assertIn("overdue_customers", crit)
        self.assertIn("supplier_payments_due", crit)
        # an open alert on the same issue: the bell shows the alert, not this too
        with run_as("Administrator"):
            frappe.get_doc({"doctype": DOCTYPE, "rule": "Overdue receivables",
                            "business_code": REC_CODE, "dedupe_key": "all", "status": "Raised",
                            "severity": "crit", "title": "x"}).insert(ignore_permissions=True)
        crit = {x["rule"] for x in self._call(self.manager, "critical",
                                              business_code=REC_CODE).json()["message"]["recommendations"]}
        self.assertNotIn("overdue_customers", crit)
        self.assertIn("supplier_payments_due", crit)
        # the finding boxes: the area's largest first, the screen's own where it has none
        from command_center.api.panels import FINDINGS, _Ctx
        with run_as("manager@test.com"):
            proc = FINDINGS["proc"](_Ctx(REC_CODE))
            self.assertEqual(len(proc), 2)
            self.assertTrue(all(f["title"] and f["text"] and f["ask"] for f in proc))
            names = [f["title"] for f in proc]
            self.assertTrue(all("buying" in t or "bill" in t or "suppliers" in t
                                or "purchase order" in t for t in names), names)
            self.assertFalse(hasattr(FINDINGS["cx"], "fallback"))
        # an area with nothing open: the screen's own findings, as before
        from command_center.recommend import engine
        from command_center.recommend.rules import RULES
        conf = engine.settings(REC_CODE)
        for rule in RULES:
            if rule.area == "buying":
                conf["rules"][rule.rule_id]["enabled"] = False
        engine.save_settings(REC_CODE, conf)
        with run_as("manager@test.com"):
            proc = FINDINGS["proc"](_Ctx(REC_CODE))
            self.assertEqual(proc, [f for f in FINDINGS["proc"].fallback(_Ctx(REC_CODE)) if f][:2])
        # someone without the role is refused
        self.assertEqual(self._call(Client(), "current").status_code, 401)

    def _ok_settings(self, fn, **args):
        r = self.admin.post(f"/api/method/insights.core.platform_settings.{fn}", json.dumps(args),
                            content_type="application/json")
        self.assertEqual(r.status_code, 200, f"{fn}: {r.content[:400]!r}")
        return r.json()["message"]

    def test_settings(self):
        view = self._ok_settings("recommendations")
        self.assertEqual(view["business_code"], REC_CODE)
        self.assertTrue(view["digest"])
        self.assertFalse(view["brief"])
        self.assertIn("one Claude request per business per day", view["brief_cost"])
        for fn in ("recommendations", "set_recommendations", "write_brief_now"):
            r = self.manager.post(f"/api/method/insights.core.platform_settings.{fn}", "{}",
                                  content_type="application/json")
            self.assertEqual(r.status_code, 403, fn)
        r = self.admin.post("/api/method/insights.core.platform_settings.set_recommendations",
                            json.dumps({"business_code": REC_CODE, "rules": json.dumps(
                                {"unmatched_receipts": {"params": {"amount": "lots"}}})}),
                            content_type="application/json")
        self.assertEqual(r.status_code, 417)
        view = self._ok_settings("set_recommendations", business_code=REC_CODE, brief=1,
                                 rules=json.dumps({"unmatched_receipts": {"params": {"amount": 50000}},
                                                   "leavers_trend": {"enabled": False}}))
        rule = {r["rule_id"]: r for r in view["rules"]}
        self.assertEqual(rule["unmatched_receipts"]["params"][0]["value"], 50000)
        self.assertFalse(rule["leavers_trend"]["enabled"])
        self.assertTrue(view["brief"])
        fired = {r["rule"] for r in self._compute()["recs"]}
        self.assertNotIn("unmatched_receipts", fired)
        self.assertNotIn("leavers_trend", fired)
        whats = " | ".join(c["what"] for c in self._ok_settings("changes"))
        self.assertIn("Daily Brief by Claude on", whats)

    def test_daily_brief_uses_only_engine_numbers(self):
        from command_center.recommend import daily, engine
        from insights.compat import run_as
        conf = engine.settings(REC_CODE)
        conf["brief"] = True
        engine.save_settings(REC_CODE, conf)
        seen = {}

        def fake(static, text, kind="analyst", **kw):
            seen.update(static=static, text=text, kind=kind)
            return seen.get("reply"), None
        with run_as("Administrator"):
            engine.refresh(REC_CODE)
            recs = engine.visible(REC_CODE)
            with mock.patch("command_center.ask.claude.configured", lambda: True), \
                    mock.patch("command_center.ask.llm.provider", lambda: "claude"), \
                    mock.patch("command_center.ask.claude.complete", fake):
                seen["reply"] = "Little changed.\n1. Pay GHS 999,999 to the bank."
                bad = daily.write_brief(REC_CODE)
                self.assertIsNone(bad["text"])
                self.assertIn("999999", bad["error"])
                first = recs[0]
                money = f"GHS {first['money_at_stake']:,.0f}"
                seen["reply"] = f"This is the first brief.\n1. {first['title']} {money}."
                good = daily.write_brief(REC_CODE)
        self.assertEqual(good["text"], seen["reply"])
        self.assertEqual(seen["kind"], "analyst")
        self.assertIn("Use only the numbers given", seen["static"])
        # every number in what Claude was given came from the engine or the figures
        from command_center.kpi.engine import evaluate_set
        figs = evaluate_set([k for k, _ in daily.BRIEF_FIGURES], REC_CODE)
        source = " ".join([r["title"] + " " + r["why"] + " " + " ".join(r["what_to_do"])
                           + f" GHS {r['money_at_stake']:,.0f}" for r in recs]
                          + [f"GHS {float(f['value']):,.0f}" for f in figs.values()
                             if f.get("value") is not None]
                          + [TODAY.strftime("%-d %B %Y")])
        stray = daily._numbers(seen["text"]) - daily._numbers(source)
        self.assertEqual(stray, set(), f"numbers given to Claude that the engine did not make: {stray}")
        shown = self._call(self.manager, "current", business_code=REC_CODE).json()["message"]["brief"]
        self.assertEqual(shown["text"], seen["reply"])

    def test_digest_email(self):
        import smtplib  # noqa: F401
        from command_center.recommend import daily, engine
        from insights.compat import run_as
        with run_as("Administrator"):
            engine.refresh(REC_CODE)
            # not set up: recorded, not raised
            state = daily.send_digest(REC_CODE)
            self.assertFalse(state["ok"])
            self.assertIn("Email is not set up", state["says"])
            mail = {"host": "smtp.test.com", "port": 587, "security": "starttls",
                    "user": "reports@test.com", "password": "pw-12345", "sender": "reports@test.com"}
            with mock.patch("insights.compat.runtime.mail_config", lambda: dict(mail)), \
                    mock.patch("smtplib.SMTP") as smtp:
                state = daily.send_digest(REC_CODE)
            self.assertTrue(state["ok"], state)
            sent = smtp.return_value.send_message.call_args[0][0]
            self.assertIn("manager@test.com", sent["To"])
            self.assertIn("new recommendation", sent["Subject"])
            body = sent.get_body(("html",)).get_content()
            self.assertIn("New since the last digest", body)
            self.assertIn(engine.visible(REC_CODE)[0]["title"].replace("'", "&#x27;")[:30], body)
            # switched off: nothing is sent by the daily run
            conf = engine.settings(REC_CODE)
            conf["digest"] = False
            engine.save_settings(REC_CODE, conf)
            with mock.patch("insights.compat.runtime.mail_config", lambda: dict(mail)), \
                    mock.patch("smtplib.SMTP") as smtp:
                daily.send_digests()
            smtp.assert_not_called()

    def test_analyst_reads_them_without_writing(self):
        from command_center.ask import tools
        from insights.compat import run_as
        from insights.core.models import CommandCenterRecommendation as R
        with run_as("manager@test.com"):
            got = tools.run("current_recommendations", {}, REC_CODE)
        self.assertEqual(R.objects.count(), 0)
        self.assertTrue(got["recommendations"])
        self.assertIn("current_recommendations", [d["name"] for d in tools.declarations()])
        money = [r.get("money_at_stake") or 0 for r in got["recommendations"]]
        self.assertEqual(money, sorted(money, reverse=True))

    def test_home_and_summary_have_their_slots(self):
        from pathlib import Path
        views = json.loads((Path(__file__).resolve().parent.parent / "frontend" / "src" / "legacy"
                            / "views.json").read_text())
        self.assertIn('data-rec="top"', views["command"])
        self.assertIn('data-rec="all"', views["brief"])
        self.assertIn('id="rec-brief"', views["brief"])


class FinancialStatements(TransactionTestCase):
    """The Finances screen's statements: ERPNext's own Profit and Loss Statement, Balance
    Sheet, Trial Balance and Cash Flow, read from the business's site and added up the way
    their trees say -- gross and net profit, the balance check, the ratios -- with a guide
    where a report cannot run and the "can't reach" state where the site does not answer."""

    databases = {"default", "aux"}

    def setUp(self):
        from cryptography.fernet import Fernet
        from django.conf import settings
        from django.core.cache import cache
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        cache.clear()
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        self.fake = FakeERPNext()
        self.patches = [mock.patch("requests.get", self.fake("GET")),
                        mock.patch("requests.post", self.fake("POST")),
                        mock.patch("time.sleep", lambda s: None)]
        for p in self.patches:
            p.start()
        from command_center import install
        from insights.compat import run_as
        with run_as("Administrator"):
            self.code = install.register_business("Test Medical Ltd", "https://erp.test", "key",
                                                  "s3cret")["code"]

    def tearDown(self):
        from django.core.cache import cache
        for p in self.patches:
            p.stop()
        cache.clear()

    def _get(self, **kw):
        from command_center.api import statements
        from insights.compat import run_as
        with run_as("Administrator"):
            return statements.get(self.code, **kw)

    def test_profit_and_loss_balance_sheet_and_ratios(self):
        out = self._get(period="ytd")
        self.assertEqual(out["state"], "ok", out)
        self.assertEqual(out["currency"], "GHS")
        m = TODAY.month
        pl = out["pl"]["figures"]
        self.assertAlmostEqual(pl["income"], 12000 * m)
        # the cost-of-goods group counts once, with the expense account inside it
        self.assertAlmostEqual(pl["cogs"], 7000 * m)
        self.assertAlmostEqual(pl["gross_profit"], 5000 * m)
        self.assertAlmostEqual(pl["other_expenses"], 3000 * m)
        self.assertAlmostEqual(pl["net_profit"], 2000 * m)
        self.assertAlmostEqual(pl["gross_margin"], 5 / 12)
        self.assertAlmostEqual(pl["net_margin"], 1 / 6)
        self.assertAlmostEqual(out["pl"]["compare_figures"]["net_profit"], 2000 * m * 0.8)
        self.assertEqual(out["pl"]["notes"], [])
        # the company comes from the platform's Connected Business, never from the markup
        runs = [f for r, f in self.fake.reports if r == "Profit and Loss Statement"]
        self.assertTrue(runs and all(f["company"] == "Test Medical Ltd" for f in runs))
        # both spellings of the period, for every version
        f = runs[0]
        for k in ("filter_based_on", "period_start_date", "period_end_date", "from_fiscal_year",
                  "to_fiscal_year", "periodicity"):
            self.assertIn(k, f)
        self.assertEqual(f["from_fiscal_year"], str(TODAY.year))
        # twelve months' trend and the four periods at a glance
        trend = out["pl"]["trend"]
        self.assertEqual(len(trend), 12)
        self.assertTrue(all(abs(t["revenue"] - 12000) < 0.01 and abs(t["net_profit"] - 2000) < 0.01
                            for t in trend), trend)
        self.assertEqual(trend[-1]["from"], str(TODAY.replace(day=1)))
        glance = out["pl"]["glance"]
        self.assertEqual(glance["columns"], ["This Month", "Last Month", "Year to Date",
                                             "Same Period Last Year"])
        self.assertAlmostEqual(glance["rows"][0]["values"][2], 12000 * m)
        # the balance sheet: as at today against the end of last month
        bs = out["bs"]["figures"]
        for key, want in (("assets", 100000), ("current_assets", 60000), ("fixed_assets", 40000),
                          ("liabilities", 40000), ("current_liabilities", 25000),
                          ("long_term_liabilities", 15000), ("equity", 50000),
                          ("provisional_profit", PROVISIONAL), ("cash", 20000), ("inventory", 10000)):
            self.assertAlmostEqual(bs[key], want, msg=key)
        self.assertTrue(bs["balances"])
        self.assertAlmostEqual(out["bs"]["compare_figures"]["cash"], 18000)
        self.assertEqual(out["balance_dates"]["at"], str(TODAY))
        r = {x["key"]: x["value"] for x in out["ratios"]}
        self.assertAlmostEqual(r["current_ratio"], 2.4)
        self.assertAlmostEqual(r["quick_ratio"], 2.0)
        self.assertAlmostEqual(r["debt_to_equity"], 40000 / 60000)
        self.assertAlmostEqual(r["working_capital"], 35000)
        self.assertTrue(all(x["meaning"] and x["reading"] for x in out["ratios"]))
        c = out["cards"]
        self.assertAlmostEqual(c["revenue"]["value"], 12000 * m)
        self.assertAlmostEqual(c["revenue"]["change_pct"], 0.25)
        self.assertAlmostEqual(c["cash"]["value"], 20000)
        self.assertAlmostEqual(c["current_ratio"]["value"], 2.4)
        # an account row opens the General Ledger on the business's own ERPNext
        drill = next(x["drill"] for x in out["pl"]["rows"] if x.get("account") == "Sales - TML")
        self.assertTrue(drill.startswith("https://erp.test/app/query-report/General%20Ledger?"), drill)
        self.assertIn("account=Sales%20-%20TML", drill)
        self.assertIn(f"from_date={TODAY.year}-01-01", drill)
        # kept five minutes: the same question asks ERPNext nothing new
        before = len(self.fake.reports)
        self._get(period="ytd")
        self.assertEqual(len(self.fake.reports), before)

    def test_trial_balance_and_cash_flow(self):
        out = self._get(period="this_month", section="tb")
        self.assertEqual(out["state"], "ok", out)
        tb = out["tb"]
        self.assertTrue(tb["balanced"], tb)
        self.assertEqual(tb["fiscal_year"], str(TODAY.year))
        self.assertAlmostEqual(tb["total"][0], 98000)
        self.assertEqual({r["account"] for r in tb["rows"]} >= {"Bank - TML", "Sales - TML"}, True)
        sent = [f for r, f in self.fake.reports if r == "Trial Balance"][0]
        self.assertEqual(sent["show_unclosed_fy_pl_balances"], 1)
        self.assertEqual(sent["fiscal_year"], str(TODAY.year))
        cf = self._get(period="ytd", section="cf")
        self.assertEqual(cf["state"], "ok", cf)
        m = TODAY.month
        lines = {s["key"]: s["values"][0] for s in cf["cf"]["summary"]}
        self.assertAlmostEqual(lines["operating"], 1000 * m)
        self.assertAlmostEqual(lines["investing"], -3000 * m)
        self.assertAlmostEqual(lines["financing"], 500 * m)
        self.assertAlmostEqual(lines["net_change"], -1500 * m)
        self.assertEqual(cf["cf"]["notes"], [])
        # ERPNext's own (wrong) total key is never read
        self.assertNotIn(-123, [v for r in cf["cf"]["rows"] for v in r["values"]])

    def test_a_statement_that_does_not_balance_says_so(self):
        with mock.patch(f"{__name__}.PROVISIONAL", 9000):
            out = self._get(period="ytd")
        self.assertFalse(out["bs"]["figures"]["balances"])
        self.assertAlmostEqual(out["bs"]["figures"]["difference"], 1000)
        self.assertTrue(any("does not balance" in n for n in out["bs"]["notes"]), out["bs"]["notes"])

    def test_guides_when_not_set_up(self):
        # no fiscal year: the trial balance says how to add one
        self.fake.fiscal_years = False
        out = self._get(period="ytd", section="tb")
        self.assertEqual(out["state"], "needs_setup", out)
        self.assertIn("/app/fiscal-year/new", out["guide"]["href"])
        self.assertTrue(out["guide"]["href"].startswith("https://erp.test"))
        self.assertNotIn("tb", out)
        # the platform's account may not run the reports: who to give which role
        from django.core.cache import cache
        cache.clear()
        self.fake.fiscal_years = True
        real = self.fake.answer

        def refuse(m, p):
            return _R(403, {"exc": "PermissionError"}) if m == "frappe.desk.query_report.run" else real(m, p)
        self.fake.answer = refuse
        out = self._get(period="ytd")
        self.assertEqual(out["state"], "needs_setup", out)
        self.assertIn("/app/user", out["guide"]["href"])
        self.assertTrue(out["guide"]["steps"])
        self.assertNotIn("cards", out)

    def test_cannot_reach(self):
        import requests as _rq
        from insights.core.models import ConnectedBusiness

        def down(*a, **k):
            raise _rq.ConnectionError("connection refused")
        with mock.patch("requests.get", down), mock.patch("requests.post", down):
            out = self._get(period="ytd")
        self.assertEqual(out["state"], "unreachable", out)
        self.assertEqual(out["business"], "Test Medical Ltd")
        self.assertNotIn("cards", out)
        # already known to be down: no network wait at all
        ConnectedBusiness.objects.update(status="Unreachable")

        def no_network(*a, **k):
            raise AssertionError("a known-down business was contacted")
        with mock.patch("requests.get", no_network), mock.patch("requests.post", no_network):
            self.assertEqual(self._get(period="last_month", section="cf")["state"], "unreachable")

    def test_through_the_web_and_the_pdf_body(self):
        from command_center.api import statements
        U = get_user_model()
        m = U.objects.create_user("cfo@test.com", "cfo@test.com", "a-long-test-pass-9")
        m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        c = Client()
        self.assertTrue(c.login(username="cfo@test.com", password="a-long-test-pass-9"))
        parts = {}
        for section in statements.SECTIONS:
            r = c.post("/api/method/command_center.api.statements.get",
                       json.dumps({"business_code": self.code, "period": "custom",
                                   "from_date": f"{TODAY.year}-01-01", "to_date": str(TODAY),
                                   "section": section}), content_type="application/json")
            self.assertEqual(r.status_code, 200, r.content[:300])
            parts[section] = r.json()["message"]
            self.assertEqual(parts[section]["state"], "ok", parts[section])
        html = statements.pdf_body(parts)
        for heading in ("Profit and Loss", "Balance Sheet", "Key Ratios", "Cash Flow", "Trial Balance"):
            self.assertIn(f"<h2>{heading}", html)
        self.assertIn("Gross Profit", html)
        # a clerk is refused
        U.objects.create_user("clerk@test.com", "clerk@test.com", "a-long-test-pass-8")
        c2 = Client()
        c2.login(username="clerk@test.com", password="a-long-test-pass-8")
        r = c2.post("/api/method/command_center.api.statements.get",
                    json.dumps({"business_code": self.code}), content_type="application/json")
        self.assertNotEqual(r.status_code, 200)

    def test_the_screen_has_the_statements(self):
        import html as _html
        from pathlib import Path
        from django.conf import settings
        views = json.loads(Path(settings.BASE_DIR, "frontend/src/legacy/views.json").read_text())
        fin = _html.unescape(views["fin"])
        self.assertIn('id="fs"', fin)
        # first thing under the heading, before the screen's own cards and tabs
        self.assertLess(fin.index('id="fs"'), fin.index('class="kpis'))
        for heading in ("Financial Statements", "Profit and Loss", "Balance Sheet", "Trial Balance",
                        "Cash Flow", "Key Ratios"):
            self.assertIn(heading, fin, heading)
        for period in ("This Month", "Last Month", "This Quarter", "Year to Date", "Last Year", "Custom"):
            self.assertIn(f">{period}<", fin, period)


def _png(w=4, h=2) -> bytes:
    """A real, tiny PNG."""
    import struct
    import zlib

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _data_url(raw: bytes, mime="image/png") -> str:
    import base64
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


class Branding(TransactionTestCase):
    """Settings -> Branding (command_center/branding.py, platform_settings): the product's
    name, tagline, logos and the vendor's footer are the administrator's alone; uploads
    are PNG, JPEG or WebP by content, at most 1 MB, never SVG, stored under a name made
    from the content and served with a long cache; the sign-in page, the boot payload,
    answer and report PDFs and the workbooks all carry the configured brand; a
    business's co-brand ("Prepared for") is set from Businesses."""

    databases = {"default", "aux"}
    MOD = SettingsPage.MOD
    SECRET = SettingsPage.SECRET
    _call = SettingsPage._call
    _ok = SettingsPage._ok
    _refused = SettingsPage._refused

    def setUp(self):
        import tempfile
        from django.conf import settings
        SettingsPage.setUp(self)
        self.files = tempfile.TemporaryDirectory()
        settings.CONFIG["files_root"] = self.files.name  # undone by SettingsPage's patch.dict

    def tearDown(self):
        SettingsPage.tearDown(self)
        self.files.cleanup()

    def _boot(self, client) -> dict:
        page = client.get("/command-center").content.decode()
        return json.loads(re.search(r"window\.CC_BOOT = (.*?);\s*$", page, re.M).group(1))

    def test_only_the_administrator(self):
        for fn, args in (("brand", {}), ("set_brand", {"product_name": "X"}),
                         ("upload_brand_logo", {"kind": "logo_light", "data": _data_url(_png())}),
                         ("remove_brand_logo", {"kind": "logo_light"})):
            r = self._call(self.manager, fn, **args)
            self.assertEqual(r.status_code, 403, f"{fn} answered a manager")
        # a Businesses delegate may set a business's co-brand, never the product's brand
        self._ok("set_settings_access", username="manager@test.com", sections=["businesses"])
        self.assertEqual(self._call(self.manager, "set_brand", product_name="X").status_code, 403)
        self.assertNotIn("branding", self._boot(self.manager)["settings_sections"])
        self.assertIn("branding", self._boot(self.admin)["settings_sections"])
        shipped = self._ok("brand")
        self.assertEqual((shipped["product_name"], shipped["tagline"], shipped["company"]),
                         ("Ultrasoft Insights", "Advanced AI-Powered Business Intelligence for ERPNext",
                          "Ultrasoft Systems"))

    def test_name_everywhere(self):
        out = self._ok("set_brand", product_name="Acme Insight", tagline="Board Intelligence",
                       company="Acme Systems", person="A. Person, Director",
                       email="hello@acme.test", phone="+233 20 000 0000", website="www.acme.test")
        self.assertEqual(out["preview"]["footer"],
                         "Acme Insight · built by Acme Systems — A. Person, Director · "
                         "hello@acme.test · +233 20 000 0000 · www.acme.test")
        self.assertIn("Nothing was changed", self._refused("set_brand", product_name="Acme Insight",
                      tagline="Board Intelligence", company="Acme Systems",
                      person="A. Person, Director", email="hello@acme.test",
                      phone="+233 20 000 0000", website="www.acme.test"))
        self.assertIn("not an email", self._refused("set_brand", product_name="Acme Insight",
                                                     email="nope"))
        self.assertIn("cannot contain", self._refused("set_brand", product_name="<b>x</b>"))
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        self.assertIn("changed the branding: product name, tagline, company", whats)
        # the sign-in page, the app page and the boot payload
        login = Client().get("/command-center-login").content.decode()
        self.assertIn("<title>Sign in · Acme Insight</title>", login)
        self.assertIn("<b>Acme Insight</b>", login)
        self.assertIn("Acme Insight · built by Acme Systems", login)
        self.assertNotIn("AI Business Intelligence", login)
        app = self.admin.get("/command-center").content.decode()
        self.assertIn("<title>Acme Insight</title>", app)
        boot = self._boot(self.manager)
        self.assertEqual((boot["brand"]["product"], boot["brand"]["tagline"]),
                         ("Acme Insight", "Board Intelligence"))
        # a blank name goes back to the default
        self._ok("set_brand", product_name="", company="")
        self.assertEqual(self._boot(self.manager)["brand"]["product"], "Ultrasoft Insights")

    def test_uploads(self):
        from command_center import branding
        png = _png()
        out = self._ok("upload_brand_logo", kind="logo_light", data=_data_url(png))
        url = out["logo_light_url"]
        self.assertRegex(url, r"^/branding/logo_light-[0-9a-f]{16}\.png$")
        got = Client().get(url)
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got["Content-Type"], "image/png")
        self.assertIn("immutable", got["Cache-Control"])
        self.assertEqual(got["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(got.streaming_content), png)
        self.assertEqual(self._boot(self.manager)["brand"]["logo_dark_url"], url,
                         "one logo serves both backgrounds")
        # refused: SVG (whatever it is called), too large, not an image, a damaged PNG
        svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.assertIn("SVG images are not accepted",
                      self._refused("upload_brand_logo", kind="logo_dark", data=_data_url(svg)))
        self.assertIn("SVG images are not accepted",
                      self._refused("upload_brand_logo", kind="logo_dark", data=_data_url(b"  <svg/>")))
        big = png + b"\x00" * (branding.MAX_BYTES + 10)
        self.assertIn("too large", self._refused("upload_brand_logo", kind="logo_dark", data=_data_url(big)))
        self.assertIn("not a PNG, JPEG or WebP",
                      self._refused("upload_brand_logo", kind="logo_dark",
                                    data=_data_url(b"MZ\x90\x00 plainly not a picture")))
        self.assertIn("damaged", self._refused("upload_brand_logo", kind="logo_dark",
                                               data=_data_url(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)))
        self.assertIn("Choose which logo", self._refused("upload_brand_logo", kind="../../x",
                                                          data=_data_url(png)))
        # nothing but the platform's own names is served
        for bad in ("/branding/../insights.json", "/branding/logo_light-zz.png",
                    "/branding/x.svg", "/branding/logo_light-0123456789abcdef.svg"):
            self.assertEqual(Client().get(bad).status_code, 404, bad)
        # replaced: the old file goes; removed: back to the mark
        jpg = b"\xff\xd8\xff\xe0" + b"\x00\x10JFIF\x00" + b"\xff\xc0\x00\x11\x08\x00\x02\x00\x04" + b"\x00" * 20 + b"\xff\xd9"
        out = self._ok("upload_brand_logo", kind="logo_light", data=_data_url(jpg, "image/jpeg"))
        self.assertTrue(out["logo_light_url"].endswith(".jpg"))
        self.assertEqual(Client().get(url).status_code, 404, "the replaced logo is deleted")
        self._ok("remove_brand_logo", kind="logo_light")
        self.assertIsNone(self._boot(self.manager)["brand"]["logo_light_url"])

    def test_outputs_carry_the_brand(self):
        import io
        import sys

        from openpyxl import load_workbook
        self._ok("set_brand", product_name="Acme Insight", company="Acme Systems",
                 email="hello@acme.test")
        self._ok("upload_brand_logo", kind="logo_light", data=_data_url(_png()))
        b = self._ok("add_business", business_name="Test Medical Ltd", site_url="https://erp.test/",
                     api_key="key-abcd1234", api_secret=self.SECRET)["business"]
        # co-brand, from Businesses
        row = self._ok("set_business_brand", name=b["name"], display_name="Test Medical Group")
        self.assertEqual(row["client_name"], "Test Medical Group")
        row = self._ok("upload_business_logo", name=b["name"], data=_data_url(_png(3, 3)))
        self.assertRegex(row["client_logo_url"], r"^/branding/client-[0-9a-f]{16}\.png$")
        self.assertEqual(self._boot(self.manager)["clients"][b["business_code"]]["display_name"],
                         "Test Medical Group")

        seen = []
        pdfmod = sys.modules["frappe.utils.pdf"]
        report = ("# Executive Summary: Test Medical Ltd\n\nSales rose to GHS 1.2M.\n\n"
                  "## cash and receivables\n\n| Customer | Owed |\n|---|---|\n| UBUNTU | 636675 |\n\n"
                  "## Recommendations\n\n- **Recommendation:** Reconcile the receipts by 30 November.\n")
        with mock.patch.object(pdfmod, "get_pdf", lambda html, options=None: (seen.append((html, options)), b"%PDF")[1]), \
                mock.patch("command_center.api.export._ensure_fonts", lambda: None):
            for kind in ("answer", "report"):
                r = self.manager.post("/api/method/command_center.api.export.answer_pdf", json.dumps(
                    {"question": "Executive Summary", "answer": report, "business_code": b["business_code"],
                     "model": "m", "kind": kind}), content_type="application/json")
                self.assertEqual(r.status_code, 200, r.content[:300])
        for (html, options), kind in zip(seen, ("answer", "report")):
            self.assertIn("data:image/png;base64,", html, f"{kind}: the product's logo is in the PDF")
            self.assertIn('class="hd-client"', html, f"{kind}: and the client's")
            self.assertIn("Prepared for <b>Test Medical Group</b>", html)
            self.assertIn("Acme Insight · built by Acme Systems · hello@acme.test", html)
            self.assertEqual(options["footer-left"], "Acme Insight · built by Acme Systems · hello@acme.test")
            self.assertEqual(options["footer-right"], "Page [page] of [topage]")
            self.assertNotIn("AI Business Intelligence", html)
        html = seen[1][0]
        self.assertIn("Management Report", html)
        self.assertEqual(html.count("Executive Summary"), 1, "the repeated title is dropped")
        self.assertIn("Cash and Receivables</h2>", html)
        self.assertIn('<ol class="recs">', html)
        self.assertIn("<li>Reconcile the receipts by 30 November.</li>", html)
        self.assertIn('<td class="n">636,675</td>', html)

        r = self.manager.post("/api/method/command_center.api.export.tables_xlsx", json.dumps(
            {"title": "Who owes us", "business_code": b["business_code"],
             "tables": [{"name": "T", "columns": ["A", "B"], "rows": [["x", "1"]]}]}),
            content_type="application/json")
        ws = load_workbook(io.BytesIO(r.content)).active
        self.assertTrue(ws["A2"].value.startswith("Acme Insight · Test Medical Group · figures as at"))
        self.assertEqual(ws.cell(row=ws.max_row, column=1).value,
                         "Prepared with Acme Insight by Acme Systems · hello@acme.test")
        # removing the co-brand puts the business's own name back
        self._ok("set_business_brand", name=b["name"], display_name="")
        self._ok("remove_business_logo", name=b["name"])
        self.assertNotIn(b["business_code"], self._boot(self.manager)["clients"])


# ------------------------------------------------------------------------------------------
# Plans, licences and usage (insights/core/plans.py)
# ------------------------------------------------------------------------------------------
class _Usage:
    def __init__(self, i, o, r, w):
        self.input_tokens, self.output_tokens = i, o
        self.cache_read_input_tokens, self.cache_creation_input_tokens = r, w


class _Text:
    type = "text"

    def __init__(self, text):
        self.text = text

    def to_dict(self, mode="json"):
        return {"type": "text", "text": self.text}


class _Reply:
    def __init__(self, text="Sales rose.", stop="end_turn", model="claude-sonnet-5-5",
                 usage=(1000, 200, 5000, 300)):
        self.model, self.stop_reason, self.stop_details = model, stop, None
        self.usage = _Usage(*usage)
        self.content = [_Text(text)]


class _FakeAnthropic:
    """The SDK client claude.py makes: with_options(...).beta.messages.create(**body)."""

    def __init__(self, replies):
        self.replies, self.sent = list(replies), []

    def with_options(self, **kw):
        return self

    @property
    def beta(self):
        return self

    @property
    def messages(self):
        return self

    def create(self, **body):
        self.sent.append(body)
        return self.replies.pop(0)


class PlansAndUsage(TransactionTestCase):
    """The product a client bought: the plan badge and Plan & Usage for a customer's
    Account Managers (counts only), Settings -> Customers for the administrator (rates,
    costs, statements), the usage ledger written where Claude replies, the monthly reset,
    the statement's arithmetic, the 80% / 100% behaviour, seats, the licence and its grace,
    and the rule that a business on no plan keeps working exactly as before."""

    databases = {"default", "aux"}
    MOD = "insights.core.plans"

    def setUp(self):
        import frappe
        SettingsPage.setUp(self)
        from insights.core.models import ConnectedBusiness
        for code, name in (("biz_a", "Alpha Medical Ltd"), ("biz_b", "Beta Trading Ltd"),
                           ("biz_c", "Gamma Supplies Ltd")):
            ConnectedBusiness.objects.create(name=name, business_name=name, business_code=code,
                                             status="Active", is_local=0, currency="GHS",
                                             site_url=f"https://{code}.test")
        frappe.conf["command_center_anthropic_key"] = "test-key-not-real"
        U = get_user_model()
        mgr = Group.objects.get(name="Insights Dashboard Manager")
        self.users = {}
        for who in ("ama@a.test", "kofi@a.test", "bea@b.test"):
            u = U.objects.create_user(who, who, "a-long-test-pass-7")
            u.groups.add(mgr)
            c = Client()
            self.assertTrue(c.login(username=who, password="a-long-test-pass-7"))
            self.users[who] = c

    def tearDown(self):
        SettingsPage.tearDown(self)

    # helpers
    def _call(self, client, fn, **args):
        r = client.post(f"/api/method/{self.MOD}.{fn}", json.dumps(args),
                        content_type="application/json")
        return r

    def _ok(self, fn, client=None, **args):
        r = self._call(client or self.admin, fn, **args)
        self.assertEqual(r.status_code, 200, f"{fn}: {r.content[:500]!r}")
        return r.json()["message"]

    def _refused(self, fn, client=None, **args) -> str:
        r = self._call(client or self.admin, fn, **args)
        self.assertEqual(r.status_code, 417, f"{fn} was not refused: {r.content[:300]!r}")
        return " ".join(json.loads(m)["message"] for m in json.loads(r.json()["_server_messages"]))

    def _customer(self, name="Alpha Group", plan="essentials", businesses=("biz_a",), **kw):
        args = {"name": name, "licensed_to": kw.pop("licensed_to", name + " Ltd"), "plan": plan,
                "businesses": list(businesses), **kw}
        for k in ("limits", "rates"):
            if isinstance(args.get(k), dict):
                args[k] = json.dumps(args[k])
        return self._ok("save_customer", **args)

    def _member(self, cid, who, role="manager", **kw):
        return self._ok("set_member", id=cid, username=who, role=role, **kw)

    def _boot(self, client) -> dict:
        page = client.get("/command-center").content.decode()
        return json.loads(re.search(r"window\.CC_BOOT = (.*?);\s*$", page, re.M).group(1))

    def _ask(self, client, question="How are sales going?", code="biz_a"):
        r = client.post("/api/method/command_center.api.ask.answer",
                        json.dumps({"question": question, "business_code": code}),
                        content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content[:400])
        return r.json()["message"]

    def _events(self, **f):
        from insights.core.models import UsageEvent
        return list(UsageEvent.objects.filter(**f).order_by("id"))

    def _fake_analyst(self, fake):
        """agent.answer replaced by one round through the real claude.chat, whose SDK
        client is the fake: what is under test is the metering where Claude replies."""
        from command_center.ask import claude

        def answer(question, business_code=None, history=None, **kw):
            content, err = claude.chat([{"role": "user", "content": question}], [], "S", "D")
            if err:
                return {"answered": False, "analyst_error": err}
            return {"answered": True, "answer": "Sales rose.", "model": "claude-sonnet-5-5",
                    "checked": ["x"]}
        return [mock.patch("command_center.ask.claude._client", lambda: fake),
                mock.patch("command_center.ask.agent.answer", answer),
                mock.patch("command_center.ask.quick.answer", lambda *a, **k: None)]

    # --- metering --------------------------------------------------------------------
    def test_metering_at_the_claude_call_site(self):
        from insights.core.models import UsageEvent
        c = self._customer()
        self._member(c["id"], "ama@a.test")
        fake = _FakeAnthropic([_Reply(), _Reply(stop="refusal", usage=(400, 0, 0, 0)),
                               _Reply(usage=(10, 5, 0, 0))])
        with contextlib.ExitStack() as stack:
            for p in self._fake_analyst(fake):
                stack.enter_context(p)
            ok = self._ask(self.users["ama@a.test"])
            self.assertTrue(ok["answered"])
            refused = self._ask(self.users["ama@a.test"])
            self.assertFalse(refused.get("allowance"))
            # Claude called outside any question (a connection check): still on record
            from command_center.ask import claude
            from insights.compat import run_as
            with run_as("boss@test.com"):
                claude.chat([{"role": "user", "content": "OK?"}], [], "S", "")
        self.assertEqual(len(fake.sent), 3, "every request went through the one client")
        q = self._events(meter="ai_questions")
        self.assertEqual([(e.quantity, e.outcome) for e in q], [(1, "ok"), (0, "failed")],
                         "a refused question keeps its tokens and is not counted")
        first = q[0]
        self.assertEqual((first.client_id, first.business_code, first.user, first.model),
                         (c["id"], "biz_a", "ama@a.test", "claude-sonnet-5-5"))
        self.assertEqual((first.input_tokens, first.output_tokens, first.cache_read_tokens,
                          first.cache_write_tokens, first.requests), (1000, 200, 5000, 300, 1))
        # cost by the (editable) default price table: 1000x2 + 200x10 + 5000x0.10 + 300x4 per M
        self.assertEqual(str(first.est_cost), "0.005700")
        self.assertEqual(q[1].input_tokens, 400)
        loose = self._events(meter="ai_tokens")
        self.assertEqual([(e.quantity, e.input_tokens, e.client_id) for e in loose], [(0, 10, None)])
        # the ledger is never edited or deleted from
        with self.assertRaises(PermissionError):
            first.quantity = 5
            first.save()
        with self.assertRaises(PermissionError):
            UsageEvent.objects.filter(pk=first.pk).update(quantity=9)
        with self.assertRaises(PermissionError):
            UsageEvent.objects.all().delete()
        with self.assertRaises(PermissionError):
            first.delete()
        # a price change applies from now on; the past keeps its cost
        self._ok("save_prices", prices=json.dumps({"claude-sonnet-5-5": {
            "input": 100, "output": 100, "cache_read": 100, "cache_write": 100}}))
        self.assertEqual(str(UsageEvent.objects.get(pk=first.pk).est_cost), "0.005700")
        # the boot payload's badge, for this Account Manager
        badge = self._boot(self.users["ama@a.test"])["plan"]
        self.assertEqual((badge["plan"], badge["licensed_to"], badge["no_expiry"], badge["can_view"]),
                         ("Essentials", "Alpha Group Ltd", True, True))

    def test_monthly_reset(self):
        from insights.core import plans
        c = self._customer(limits={"ai_questions": 10})
        cust = plans._client(c["id"])
        from insights.compat import run_as
        with run_as("boss@test.com"):
            with mock.patch.object(plans, "now", lambda: dt.datetime(2026, 10, 31, 23, 59, 30)):
                for _ in range(4):
                    plans.record("ai_questions", 1, "biz_a")
                self.assertEqual(plans.used(cust)["ai_questions"], 4)
                self.assertEqual(plans.resets_on(), "1 November 2026")
            with mock.patch.object(plans, "now", lambda: dt.datetime(2026, 11, 1, 0, 0, 5)):
                plans.record("ai_questions", 1, "biz_a")
                self.assertEqual(plans.used(cust)["ai_questions"], 1, "a new month starts at 0")
                self.assertEqual(plans.used(cust, "2026-10")["ai_questions"], 4)
                self.assertEqual(plans.resets_on(), "1 December 2026")

    def test_statement_maths(self):
        from insights.core import plans
        from insights.compat import run_as
        c = self._customer(limits={"ai_questions": 10, "seats": 1, "ai_reports": None},
                           rates={"currency": "GHS", "base_fee": "100",
                                  "overage": {"ai_questions": "2.5", "seats": "20", "ai_reports": "50"}})
        self._member(c["id"], "ama@a.test")
        self._member(c["id"], "kofi@a.test", role="user", override_seats=1)
        with run_as("ama@a.test"):
            for _ in range(13):
                plans.record("ai_questions", 1, "biz_a")
            for _ in range(7):
                plans.record("ai_reports", 1, "biz_a")
        st = self._ok("billing_statement", id=c["id"], period=plans.period_of())
        lines = {ln["key"]: ln for ln in st["lines"]}
        self.assertEqual((lines["ai_questions"]["used"], lines["ai_questions"]["over"],
                          lines["ai_questions"]["amount"]), (13, 3, 7.5))
        self.assertEqual((lines["seats"]["used"], lines["seats"]["over"], lines["seats"]["amount"]),
                         (2, 1, 20.0))
        self.assertEqual((lines["ai_reports"]["included"], lines["ai_reports"]["over"],
                          lines["ai_reports"]["amount"]), (None, 0, 0.0), "unlimited: nothing over")
        self.assertEqual((st["currency"], st["base_fee"], st["total"]), ("GHS", 100.0, 127.5))
        # a correction is a new row, and the statement follows it
        st = self._ok("record_correction", id=c["id"], period=plans.period_of(),
                      meter="ai_questions", quantity=-2, note="Two test questions on go-live day")
        self.assertEqual(st["total"], 122.5)
        self.assertIn("Say why", self._refused("record_correction", id=c["id"], meter="ai_questions",
                                               quantity=1, note=""))
        # the plan's default rates apply where the customer has none
        self._ok("save_plan", code="essentials", name="Essentials", features="One\nTwo",
                 limits=json.dumps({"ai_questions": 200}), currency="USD", base_fee="10",
                 overage=json.dumps({"ai_reports": "1"}))
        d = self._customer(name="Delta Group", businesses=("biz_c",), limits={"ai_reports": 5})
        with run_as("boss@test.com"):
            for _ in range(6):
                plans.record("ai_reports", 1, "biz_c")
        st = self._ok("billing_statement", id=d["id"])
        self.assertEqual((st["currency"], st["base_fee"], st["total"]), ("USD", 10.0, 11.0))

    def test_allowance_at_80_and_100(self):
        from insights.core import plans
        from insights.core.models import PlanNotice
        from insights.compat import run_as
        c = self._customer(limits={"ai_questions": 5}, allow_overage=0)
        self._member(c["id"], "ama@a.test")
        self._member(c["id"], "kofi@a.test", role="user")
        with run_as("ama@a.test"):
            for _ in range(3):
                plans.record("ai_questions", 1, "biz_a")
            self.assertFalse(PlanNotice.objects.exists(), "nothing at 60%")
            plans.record("ai_questions", 1, "biz_a")
        n = list(PlanNotice.objects.all())
        self.assertEqual([(x.recipient, x.kind) for x in n], [("ama@a.test", "allowance_80")],
                         "80%: the customer's Account Managers, not its Users")
        page = self._ok("my_plan", client=self.users["ama@a.test"])
        q = next(m for m in page["meters"] if m["key"] == "ai_questions")
        self.assertEqual((q["used"], q["included"], q["pct"], q["warn"], q["full"]), (4, 5, 80.0, True, False))
        self.assertEqual(page["resets_on"], plans.resets_on())
        with run_as("ama@a.test"):
            plans.record("ai_questions", 1, "biz_a")
            self.assertEqual(plans.gate("ai_questions", "biz_a"), plans.ALLOWANCE_USED)
        kinds = sorted(PlanNotice.objects.values_list("recipient", "kind"))
        self.assertIn(("ama@a.test", "allowance_full"), kinds)
        self.assertIn(("boss@test.com", "allowance_full"), kinds)
        # the analyst says so politely, and calls no model; the rest keeps working
        fake = _FakeAnthropic([])
        with contextlib.ExitStack() as stack:
            for p in self._fake_analyst(fake):
                stack.enter_context(p)
            out = self._ask(self.users["ama@a.test"])
        self.assertTrue(out["allowance"])
        self.assertEqual(out["answer"], "This month's AI allowance is used up — your administrator can extend it.")
        self.assertEqual(fake.sent, [])
        r = self.users["ama@a.test"].post("/api/method/command_center.api.businesses.get_visible_businesses",
                                          "{}", content_type="application/json")
        self.assertEqual(r.status_code, 200)
        r = self.users["ama@a.test"].post("/api/method/command_center.api.reports.generate",
                                          json.dumps({"code": "rp01", "business_code": "biz_a"}),
                                          content_type="application/json")
        self.assertEqual(r.status_code, 200, "reports have their own allowance")
        # overage allowed (the default): it keeps working, billed as overage
        self._customer(id=c["id"], limits={"ai_questions": 5}, allow_overage=1)
        with run_as("ama@a.test"):
            self.assertIsNone(plans.gate("ai_questions", "biz_a"))
        # the analyst's own read-only tool answers from the meters
        from command_center.ask import tools
        with run_as("ama@a.test"):
            got = tools.run("ai_allowance", {}, "biz_a")
        q = next(m for m in got["meters"] if m["label"] == "AI Analyst Questions")
        self.assertEqual((got["plan"], q["used"], q["included"]), ("Essentials", 5, 5))
        self.assertNotIn("rate", json.dumps(got))

    def test_seats(self):
        c = self._customer(limits={"seats": 1})
        r = self.admin.post("/api/method/insights.core.platform_settings.add_person", json.dumps(
            {"email": "new1@a.test", "full_name": "New One", "set_later": 1, "client_id": c["id"]}),
            content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content[:300])
        r = self.admin.post("/api/method/insights.core.platform_settings.add_person", json.dumps(
            {"email": "new2@a.test", "full_name": "New Two", "set_later": 1, "client_id": c["id"]}),
            content_type="application/json")
        self.assertEqual(r.status_code, 417)
        self.assertIn("has used all 1 of its user seats on the Essentials plan", r.content.decode())
        self.assertFalse(get_user_model().objects.filter(username="new2@a.test").exists())
        # the administrator can override
        r = self.admin.post("/api/method/insights.core.platform_settings.add_person", json.dumps(
            {"email": "new2@a.test", "full_name": "New Two", "set_later": 1, "client_id": c["id"],
             "override_seats": 1}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content[:300])
        row = next(x for x in self._ok("customers")["customers"] if x["id"] == c["id"])
        self.assertEqual(row["seats_used"], 2)
        # reactivating someone takes their seat again: refused while full
        U = get_user_model()
        U.objects.filter(username="new1@a.test").update(is_active=False)
        self._ok("save_customer", id=c["id"], name="Alpha Group", plan="essentials",
                 businesses=["biz_a"], limits=json.dumps({"seats": 1}))
        r = self.admin.post("/api/method/insights.core.platform_settings.set_active",
                            json.dumps({"username": "new1@a.test", "on": 1}),
                            content_type="application/json")
        self.assertEqual(r.status_code, 417)
        self.assertIn("user seats", r.content.decode())
        # naming someone from Customers is held to the seats too
        self.assertIn("user seats", self._refused("set_member", id=c["id"], username="ama@a.test"))

    def test_licence_states(self):
        from insights.core import plans
        from insights.compat import run_as
        today = dt.date.today()
        # a business on no customer: no plan, no gate, no badge -- exactly as before
        with run_as("bea@b.test"):
            self.assertIsNone(plans.gate("ai_questions", "biz_b"))
        self.assertIsNone(self._boot(self.users["bea@b.test"])["plan"])
        # a customer with no renewal date: no expiry
        c = self._customer()
        self._member(c["id"], "ama@a.test")
        self.assertEqual(self._boot(self.users["ama@a.test"])["plan"]["state"], "active")
        cases = [(today + dt.timedelta(days=90), "active", None),
                 (today + dt.timedelta(days=10), "due", None),
                 (today - dt.timedelta(days=5), "grace", "grace period"),
                 (today - dt.timedelta(days=31), "lapsed", "paused")]
        for end, state, words in cases:
            self._customer(id=c["id"], renewal_date=end.isoformat(), grace_days=30)
            badge = self._boot(self.users["ama@a.test"])["plan"]
            self.assertEqual(badge["state"], state, end)
            if words:
                self.assertIn(words, badge["banner"])
            else:
                self.assertIsNone(badge["banner"])
        # lapsed: the AI, the reports and the scheduled sends pause; the screens do not
        with run_as("ama@a.test"):
            why = plans.gate("ai_questions", "biz_a")
            self.assertIn("Your screens and data remain available", why)
            self.assertEqual(why, plans.gate("scheduled_reports", "biz_a"))
            self.assertEqual(why, plans.gate("daily_briefs", "biz_a"))
        r = self.users["ama@a.test"].post("/api/method/command_center.api.reports.generate",
                                          json.dumps({"code": "rp01", "business_code": "biz_a"}),
                                          content_type="application/json")
        self.assertEqual(r.status_code, 417)
        self.assertIn("paused", r.content.decode())
        r = self.users["ama@a.test"].post("/api/method/command_center.api.businesses.get_visible_businesses",
                                          "{}", content_type="application/json")
        self.assertEqual(r.status_code, 200, "the screens stay readable")
        self.assertTrue(self._ok("my_plan", client=self.users["ama@a.test"])["licence"]["paused"])
        # extended at once by the administrator
        row = self._ok("extend_licence", id=c["id"], days=365)
        self.assertEqual(row["licence"]["state"], "active")
        with run_as("ama@a.test"):
            self.assertIsNone(plans.gate("ai_questions", "biz_a"))
        # reminders at 60/30/7 days, to the administrator and the Account Managers, once
        self._customer(id=c["id"], renewal_date=(today + dt.timedelta(days=30)).isoformat())
        from insights.core.models import PlanNotice, UsageEvent
        with run_as("Administrator"):
            plans.daily()
            plans.daily()
        got = sorted(PlanNotice.objects.filter(kind="renewal").values_list("recipient", flat=True))
        self.assertEqual(got, ["ama@a.test", "boss@test.com"])
        self.assertEqual(UsageEvent.objects.filter(meter="seats", outcome="snapshot").count(), 1,
                         "one snapshot a day")
        bell = self._ok("notices", client=self.users["ama@a.test"])
        self.assertIn("renews in 30 days", bell[0]["title"])
        self._ok("dismiss_notice", client=self.users["ama@a.test"], id=bell[0]["id"])
        self.assertEqual(self._ok("notices", client=self.users["ama@a.test"]), [])
        # month end: the administrator is told the statements are ready, nothing is sent
        with mock.patch.object(plans, "now", lambda: dt.datetime(2026, 12, 1, 0, 30)), \
                run_as("Administrator"):
            plans.daily()
        ready = PlanNotice.objects.get(kind="statements", dedupe="statements:2026-11")
        self.assertEqual(ready.recipient, "boss@test.com")
        self.assertIn("November 2026", ready.title)

    def test_access_control(self):
        a = self._customer(rates={"currency": "GHS", "base_fee": "999"})
        b = self._customer(name="Beta Group", businesses=("biz_b",))
        self._member(a["id"], "ama@a.test")
        self._member(a["id"], "kofi@a.test", role="user")
        self._member(b["id"], "bea@b.test")
        ama, kofi, bea = (self.users[k] for k in ("ama@a.test", "kofi@a.test", "bea@b.test"))
        mine = self._ok("my_plan", client=ama)
        self.assertEqual(mine["client"], "Alpha Group")
        text = json.dumps(mine)
        for word in ("base_fee", "999", "rate", "est_cost", "overage\": {"):
            self.assertNotIn(word, text, "no money on a customer's own page")
        self.assertEqual(self._call(ama, "my_plan", client_id=b["id"]).status_code, 403,
                         "a manager of A never sees B")
        self.assertEqual(self._call(ama, "usage_statement", client_id=b["id"]).status_code, 403)
        self.assertEqual(self._call(kofi, "my_plan").status_code, 403, "a User sees the badge only")
        badge = self._boot(kofi)["plan"]
        self.assertEqual((badge["plan"], badge["can_view"]), ("Essentials", False))
        self.assertEqual(self._call(self.manager, "my_plan").status_code, 403, "no customer")
        self.assertIsNone(self._boot(self.manager)["plan"])
        self.assertEqual(self._ok("my_plan", client=bea)["client"], "Beta Group")
        # the administrator's calls, refused to every manager, delegates included
        self.admin.post("/api/method/insights.core.platform_settings.set_settings_access",
                        json.dumps({"username": "ama@a.test", "sections": ["people", "businesses"]}),
                        content_type="application/json")
        for fn in ("customers", "save_customer", "extend_licence", "remove_customer", "set_member",
                   "record_correction", "billing_statement", "plan_settings", "save_plan",
                   "save_prices"):
            self.assertEqual(self._call(ama, fn, id=a["id"]).status_code, 403, fn)
            self.assertEqual(self._call(Client(), fn).status_code, 401, fn)
        self.assertNotIn("customers", self._boot(ama)["settings_sections"])
        self.assertIn("customers", self._boot(self.admin)["settings_sections"])
        # View Plans: every tier by features and limits, never a price
        tiers = self._ok("plans", client=kofi)
        self.assertEqual([p["name"] for p in tiers["plans"]],
                         ["Essentials", "Professional", "Enterprise", "Custom"])
        self.assertNotIn("base_fee", json.dumps(tiers))
        # Request a Quotation, with no email set up: the vendor's contact instead
        self._ok_settings("set_brand", product_name="Acme Insight", company="Acme Systems",
                          email="sales@acme.test")
        out = self._ok("request_quote", client=ama, plan="professional", message="We are growing.")
        self.assertFalse(out["sent"])
        self.assertEqual(out["contact"]["email"], "sales@acme.test")
        self.assertEqual(self._call(kofi, "request_quote", plan="professional").status_code, 403)

    def _ok_settings(self, fn, **args):
        r = self.admin.post(f"/api/method/insights.core.platform_settings.{fn}", json.dumps(args),
                            content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()["message"]

    def test_statements_carry_the_brand(self):
        import io
        import sys

        from openpyxl import load_workbook
        from insights.core import plans
        from insights.compat import run_as
        self._ok_settings("set_brand", product_name="Acme Insight", company="Acme Systems",
                          email="hello@acme.test")
        c = self._customer(rates={"currency": "GHS", "base_fee": "100"}, limits={"ai_questions": 1},
                           licensed_to="Alpha Holdings Ltd")
        self._member(c["id"], "ama@a.test")
        with run_as("ama@a.test"):
            plans.record("ai_questions", 1, "biz_a")
            plans.record("ai_questions", 1, "biz_a")
        seen = []
        pdfmod = sys.modules["frappe.utils.pdf"]
        with mock.patch.object(pdfmod, "get_pdf", lambda html, options=None: (seen.append((html, options)), b"%PDF")[1]), \
                mock.patch("command_center.api.export._ensure_fonts", lambda: None):
            r = self._call(self.users["ama@a.test"], "usage_statement", format="pdf")
            self.assertEqual(r.status_code, 200, r.content[:300])
            self.assertEqual(r.content, b"%PDF")
            r = self._call(self.admin, "billing_statement", id=c["id"], format="pdf")
            self.assertEqual(r.status_code, 200, r.content[:300])
        label = plans.period_label(plans.period_of())
        for (html, options), money in zip(seen, (False, True)):
            self.assertIn("Usage Statement", html)
            self.assertIn("Prepared for <b>Alpha Holdings Ltd</b>", html)
            self.assertIn(label, html)
            self.assertNotIn("Figures as at", html)
            self.assertIn("Acme Insight · built by Acme Systems · hello@acme.test", html)
            self.assertEqual(options["footer-left"], "Acme Insight · built by Acme Systems · hello@acme.test")
            self.assertEqual("Total for the month" in html, money)
            self.assertEqual("GHS" in html, money, "money only on the administrator's")
        self.assertIn("not an invoice and has not been sent", seen[1][0])
        r = self._call(self.users["ama@a.test"], "usage_statement", format="xlsx")
        wb = load_workbook(io.BytesIO(r.content))
        ws = wb["Usage"]
        self.assertTrue(ws["A2"].value.startswith(f"Acme Insight · Alpha Holdings Ltd · {label}"))
        self.assertEqual(ws.cell(row=ws.max_row, column=1).value,
                         "Prepared with Acme Insight by Acme Systems · hello@acme.test")
        self.assertEqual(wb.sheetnames, ["Usage"], "no ledger, no money for the customer")
        r = self._call(self.admin, "billing_statement", id=c["id"], format="xlsx")
        wb = load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ["Usage", "Ledger"])
        rows = [[c.value for c in row] for row in wb["Usage"].iter_rows()]
        self.assertIn(["Total for the month", None, None, None, None, None, 100], rows)
