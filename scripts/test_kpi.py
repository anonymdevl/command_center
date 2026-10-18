"""The KPI engine's windows, leaders and averages, tested without a site.

    python3 scripts/test_kpi.py

Frappe's query builder is stood in for by a small in-memory one that evaluates the same
expressions over Python rows, so what is under test is engine.py's own logic: that a
window is measured back from the last date in the data (not from today), that "last full
month" skips a month the data stops part-way through, that a leader is chosen, named and
narrowed in the drill, that a share is of every group together, that an average of
nothing is unknown rather than zero, and that notes carry {period} and {group}. What it
cannot test is MariaDB's SQL; the expressions used are plain comparisons, SUM, COUNT,
AVG, MAX and GROUP BY on a column, which is all of it.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


# --- an in-memory query builder -------------------------------------------------
class Pred:
    def __init__(self, fn):
        self.fn = fn

    def __and__(self, other):
        return Pred(lambda r: self.fn(r) and other.fn(r))


def _cmp(a, b, op):
    if a is None:
        return False
    if isinstance(a, dt.date) and isinstance(b, str):
        b = dt.date.fromisoformat(b)
    return op(a, b)


class Col:
    def __init__(self, name):
        self.name = name

    def _p(self, other, op):
        return Pred(lambda r: _cmp(r.get(self.name), other, op))

    def __eq__(self, o): return self._p(o, lambda a, b: a == b)
    def __ne__(self, o): return self._p(o, lambda a, b: a != b)
    def __gt__(self, o): return self._p(o, lambda a, b: a > b)
    def __ge__(self, o): return self._p(o, lambda a, b: a >= b)
    def __lt__(self, o): return self._p(o, lambda a, b: a < b)
    def __le__(self, o): return self._p(o, lambda a, b: a <= b)
    __hash__ = object.__hash__

    def isin(self, vals): return Pred(lambda r: r.get(self.name) in vals)
    def notin(self, vals): return Pred(lambda r: r.get(self.name) not in vals)

    def like(self, pat):
        import re
        rx = re.compile("^" + re.escape(pat).replace("%", ".*") + "$", re.I)
        return Pred(lambda r: bool(rx.match(str(r.get(self.name) or ""))))


class Agg:
    def __init__(self, kind, col):
        self.kind, self.col, self.uniq = kind, col, False

    def distinct(self):
        self.uniq = True
        return self

    def over(self, rows):
        vals = [r.get(self.col.name) for r in rows] if self.col is not None else rows
        if self.kind == "count":
            vals = [v for v in vals if v is not None]
            return len(set(vals)) if self.uniq else len(vals)
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        if self.kind == "sum":
            return sum(vals)
        if self.kind == "avg":
            return sum(vals) / len(vals)
        return max(vals)


class Table:
    def __init__(self, name):
        self._name = name

    def __getitem__(self, k): return Col(k)
    def __getattr__(self, k):
        if k.startswith("_"):
            raise AttributeError(k)
        return Col(k)


DATA: dict = {}


class Q:
    def __init__(self, t):
        self.t, self.sel, self.preds, self.group = t, [], [], None

    def select(self, *exprs):
        self.sel += exprs
        return self

    def where(self, p):
        self.preds.append(p)
        return self

    def groupby(self, col):
        self.group = col
        return self

    def run(self):
        rows = [r for r in DATA.get(self.t._name, []) if all(p.fn(r) for p in self.preds)]
        if self.group is None:
            return [tuple(e.over(rows) for e in self.sel)]
        groups: dict = {}
        for r in rows:
            groups.setdefault(r.get(self.group.name), []).append(r)
        return [tuple(k if isinstance(e, Col) else e.over(g) for e in self.sel)
                for k, g in groups.items()]


# --- frappe ---------------------------------------------------------------------
def _d(x):
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def _last_day(x):
    x = _d(x)
    nxt = (x.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return nxt - dt.timedelta(days=1)


def _add_months(x, n):
    x = _d(x)
    m = x.month - 1 + n
    y, m = x.year + m // 12, m % 12 + 1
    return x.replace(year=y, month=m, day=min(x.day, _last_day(dt.date(y, m, 1)).day))


frappe = types.ModuleType("frappe")
frappe.utils = types.SimpleNamespace(
    getdate=_d, today=lambda: "2026-10-18", get_first_day=lambda x: _d(x).replace(day=1),
    get_last_day=_last_day, add_days=lambda x, n: _d(x) + dt.timedelta(days=n),
    add_months=_add_months, date_diff=lambda a, b: (_d(a) - _d(b)).days)
frappe.qb = types.SimpleNamespace(DocType=Table, from_=Q)
frappe.get_all = lambda *a, **k: []


def _throw(msg):
    raise RuntimeError(msg)


frappe.throw = _throw
sys.modules["frappe"] = frappe
qb = types.ModuleType("frappe.query_builder")
fns = types.ModuleType("frappe.query_builder.functions")
fns.Sum = lambda c: Agg("sum", c)
fns.Avg = lambda c: Agg("avg", c)
fns.Max = lambda c: Agg("max", c)
fns.Count = lambda c: Agg("count", c)
sys.modules["frappe.query_builder"] = qb
sys.modules["frappe.query_builder.functions"] = fns
biz = types.ModuleType("command_center.api.businesses")
biz.currency_for = lambda code: "GHS"
sys.modules["command_center.api.businesses"] = biz

from command_center.facts.schema import FACTS  # noqa: E402
from command_center.kpi import engine  # noqa: E402


def rows(fact, *items):
    DATA[FACTS[fact]] = [dict(r, business_code="GIG", name=f"{fact}-{i}")
                         for i, r in enumerate(items)]


D = dt.date

# Payments: May to 12 August 2025. The data stops part-way through August, so the last
# full month is July -- and today (2026) has nothing to do with it.
rows("fact_payment_allocation",
     {"posting_date": D(2025, 5, 3), "payment_type": "Receive", "against_doctype": "Sales Invoice",
      "allocated_amount": 100, "days_to_pay": 10},
     {"posting_date": D(2025, 6, 9), "payment_type": "Receive", "against_doctype": "Sales Invoice",
      "allocated_amount": 200, "days_to_pay": 20},
     {"posting_date": D(2025, 7, 1), "payment_type": "Receive", "against_doctype": "Sales Invoice",
      "allocated_amount": 300, "days_to_pay": 30},
     {"posting_date": D(2025, 7, 31), "payment_type": "Receive", "against_doctype": "Sales Invoice",
      "allocated_amount": 50, "days_to_pay": 0},
     {"posting_date": D(2025, 7, 15), "payment_type": "Pay", "against_doctype": "Purchase Invoice",
      "allocated_amount": 9999, "days_to_pay": 999},
     {"posting_date": D(2025, 8, 12), "payment_type": "Receive", "against_doctype": "Sales Invoice",
      "allocated_amount": 70, "days_to_pay": 5})

rows("fact_sales_invoice_line",
     {"posting_date": D(2025, 6, 2), "base_net_amount": 1000, "src_docstatus": 1},
     {"posting_date": D(2025, 6, 28), "base_net_amount": 2190, "src_docstatus": 1},
     {"posting_date": D(2025, 7, 10), "base_net_amount": 1550, "src_docstatus": 1},
     {"posting_date": D(2025, 7, 11), "base_net_amount": 5000, "src_docstatus": 0},
     {"posting_date": D(2025, 7, 31), "base_net_amount": 1, "src_docstatus": 1})

rows("fact_sales_invoice",
     {"customer": "HAIRASH", "outstanding_amount": 700, "src_docstatus": 1, "base_grand_total": 700},
     {"customer": "HAIRASH", "outstanding_amount": 37, "src_docstatus": 1, "base_grand_total": 37},
     {"customer": "UBUNTU", "outstanding_amount": 600, "src_docstatus": 1, "base_grand_total": 600},
     {"customer": "PAID", "outstanding_amount": 0, "src_docstatus": 1, "base_grand_total": 900},
     {"customer": "DRAFT", "outstanding_amount": 5000, "src_docstatus": 0, "base_grand_total": 5000})

rows("fact_purchase_invoice_line",
     {"supplier": "CYNSEL", "base_net_amount": 57, "src_docstatus": 1},
     {"supplier": "MEDI", "base_net_amount": 38, "src_docstatus": 1},
     {"supplier": "SMALL", "base_net_amount": 5, "src_docstatus": 1},
     {"supplier": "SMALL", "base_net_amount": 500, "src_docstatus": 0})

rows("fact_stock_balance",
     {"item_code": "SYR-5ML", "warehouse": "A", "available_qty": -30000, "reserved_qty": 30000},
     {"item_code": "SYR-5ML", "warehouse": "B", "available_qty": -9941, "reserved_qty": 9941},
     {"item_code": "GLOVE", "warehouse": "A", "available_qty": -10, "reserved_qty": 10},
     {"item_code": "MASK", "warehouse": "A", "available_qty": 400, "reserved_qty": 0})

rows("fact_task",
     {"project_name": "Samkwarth lab", "is_open": 1, "days_late": 850},
     {"project_name": "Samkwarth lab", "is_open": 1, "days_late": 20},
     {"project_name": "UBUNTU", "is_open": 1, "days_late": 570},
     {"project_name": "Closed one", "is_open": 0, "days_late": 2000})

rows("fact_person",
     {"status": "Active", "is_active": 1, "designation": "Field Engineer"},
     {"status": "Active", "is_active": 1, "designation": "Biomedical engineer"},
     {"status": "Active", "is_active": 1, "designation": "Accountant"},
     {"status": "Left", "is_active": 0, "designation": "Engineer", "tenure_days": 200},
     {"status": "Left", "is_active": 0, "designation": "Driver", "tenure_days": 220})

rows("fact_case",
     {"is_open": 1, "days_open": 10}, {"is_open": 1, "days_open": 14}, {"is_open": 0, "days_open": 3})

KEYS = ["cash_in_month", "days_to_pay", "revenue_last_month", "revenue_best_month",
        "largest_debt", "invoices_draft", "supplier_top_share", "supplier_top2_share",
        "stock_worst_shortfall", "stock_lines_promised", "tasks_longest_wait", "engineers",
        "people_left", "cases_closed", "cases_avg_wait"]
r = engine.evaluate_set(KEYS, "GIG")

# Windows, from the end of the data.
c = r["cash_in_month"]
check(c["value"] == 350, f"cash_in_month: July receipts are 300+50, got {c['value']}")
check(c["period"]["from"] == "2025-07-01" and c["period"]["to"] == "2025-07-31",
      f"cash_in_month: last full month should be July 2025, got {c['period']}")
check(c["note"] == "July 2025, matched to invoices", f"cash_in_month note: {c['note']!r}")
check(c["drill"]["filters"]["posting_date"] == ["between", ["2025-07-01", "2025-07-31"]],
      f"cash_in_month: the drill must carry the window, got {c['drill']['filters']}")

p = r["days_to_pay"]
check(p["period"]["from"] == "2025-05-01" and p["period"]["to"] == "2025-07-31",
      f"days_to_pay: three full months is May-July, got {p['period']}")
check(p["value"] == 15, f"days_to_pay: mean of 10,20,30,0 is 15, got {p['value']}")
check(p["note"] == "after the due date, on average, May – Jul 2025", f"days_to_pay note: {p['note']!r}")

check(r["revenue_last_month"]["value"] == 1551,
      f"revenue_last_month: submitted July is 1550+1, got {r['revenue_last_month']['value']}")

b = r["revenue_best_month"]
check(b["value"] == 3190 and b["note"] == "June 2025",
      f"revenue_best_month: June 2025 at 3190, got {b['value']} / {b['note']!r}")
check(b["drill"]["filters"].get("posting_date") == ["between", ["2025-06-01", "2025-06-30"]],
      f"revenue_best_month: drill should open June only, got {b['drill']['filters']}")

d = r["largest_debt"]
check(d["value"] == 737 and d["note"] == "HAIRASH" and d["drill"]["filters"]["customer"] == "HAIRASH",
      f"largest_debt: HAIRASH 737, got {d['value']} / {d['note']!r} / {d['drill']['filters']}")
check(r["invoices_draft"]["value"] == 1 and "5,000.00" in r["invoices_draft"]["note"],
      f"invoices_draft: {r['invoices_draft']}")

s1, s2 = r["supplier_top_share"], r["supplier_top2_share"]
check(abs(s1["value"] - 57) < 1e-9 and s1["note"] == "CYNSEL, of all supplier spend",
      f"supplier_top_share: CYNSEL 57%, got {s1['value']} / {s1['note']!r}")
check(abs(s2["value"] - 95) < 1e-9 and s2["note"] == "CYNSEL and MEDI"
      and s2["drill"]["filters"]["supplier"] == ["in", ["CYNSEL", "MEDI"]],
      f"supplier_top2_share: 95% CYNSEL and MEDI, got {s2['value']} / {s2['note']!r}")

w = r["stock_worst_shortfall"]
check(w["value"] == 39941 and w["note"] == "SYR-5ML",
      f"stock_worst_shortfall: SYR-5ML 39,941 short, got {w['value']} / {w['note']!r}")
check(r["stock_lines_promised"]["value"] == 3, f"stock_lines_promised: {r['stock_lines_promised']['value']}")

t = r["tasks_longest_wait"]
check(t["value"] == 850 and t["note"] == "Samkwarth lab",
      f"tasks_longest_wait: Samkwarth lab 850 (max, not 870 summed), got {t['value']} / {t['note']!r}")
check(r["engineers"]["value"] == 2, f"engineers: two active by title, got {r['engineers']['value']}")
check(r["people_left"]["value"] == 2 and r["people_left"]["note"] == "average stay 210 days",
      f"people_left: {r['people_left']['value']} / {r['people_left']['note']!r}")
check(r["cases_closed"]["value"] == 1, f"cases_closed: {r['cases_closed']['value']}")
check(r["cases_avg_wait"]["value"] == 12, f"cases_avg_wait: {r['cases_avg_wait']['value']}")

# Nothing to measure is unknown, not zero.
for fact in ("fact_payment_allocation", "fact_task", "fact_purchase_invoice_line"):
    DATA[FACTS[fact]] = []
e = engine.evaluate_set(["cash_in_month", "days_to_pay", "tasks_longest_wait",
                         "supplier_top_share"], "GIG")
for k in e:
    check(e[k]["value"] is None, f"{k} over no rows should be unknown, got {e[k]['value']}")
check(e["cash_in_month"]["note"] == "—, matched to invoices" or "no dated" in e["cash_in_month"]["note"],
      f"cash_in_month with no data: {e['cash_in_month']['note']!r}")

# A month the data covers to its last day counts as full.
DATA[FACTS["fact_payment_allocation"]] = [
    {"business_code": "GIG", "name": "x1", "posting_date": D(2025, 8, 31), "payment_type": "Receive",
     "against_doctype": "Sales Invoice", "allocated_amount": 5, "days_to_pay": 1}]
f = engine.evaluate_set(["cash_in_month"], "GIG")["cash_in_month"]
check(f["period"]["label"] == "August 2025" and f["value"] == 5,
      f"data ending 31 Aug: last full month is August, got {f['period']} / {f['value']}")

# Another business's rows never leak in.
DATA[FACTS["fact_payment_allocation"]].append(
    {"business_code": "OTHER", "name": "x2", "posting_date": D(2025, 8, 20), "payment_type": "Receive",
     "against_doctype": "Sales Invoice", "allocated_amount": 1000, "days_to_pay": 1})
f = engine.evaluate_set(["cash_in_month"], "GIG")["cash_in_month"]
check(f["value"] == 5, f"another business's payment leaked into GIG: {f['value']}")

print(f"test_kpi: {len(KEYS) + 12} cases")
if failures:
    print(f"\n{len(failures)} failure(s):")
    for x in failures:
        print("  -", x)
    sys.exit(1)
print("all passed")
