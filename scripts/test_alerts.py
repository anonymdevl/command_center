"""The alert rules, tested without a site.

    python3 scripts/test_alerts.py

Each rule is a function of KPI results and its thresholds, so it is tested by handing
it KPI results: that it raises above the threshold and not at or below it, that an
unknown or empty figure raises nothing rather than failing, that the sentence carries
the figure and the group the KPI named, and that every KPI a rule reads is registered.
The engine's writes (raise, age, resolve) need a site and are checked there.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

fr = types.ModuleType("frappe")
fr.utils = types.SimpleNamespace(
    getdate=lambda x: x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10]),
    today=lambda: "2026-10-18", now_datetime=dt.datetime.now)
sys.modules["frappe"] = fr
sys.modules["frappe.utils"] = fr.utils

from command_center.alerts import rules as R  # noqa: E402
from command_center.alerts.engine import elapsed  # noqa: E402
from command_center.kpi import buying, operations, registry, sales, stock  # noqa: E402,F401

failures = []


def check(ok, what):
    if not ok:
        failures.append(what)


def fig(value, unit="currency", group=None, label="x"):
    return {"value": value, "unit": unit, "currency": "GHS" if unit == "currency" else None,
            "group": {"label": group} if group else None, "label": label,
            "drill": {"fact": "fact_sales_invoice", "filters": {"ageing_bucket": "90+"}}}


P = lambda **k: {"threshold_amount": 0, "threshold_days": 0, "threshold_count": 0, **k}  # noqa: E731

for rule in R.RULES:
    for k in rule.kpis:
        check(k in registry.REGISTRY, f"rule {rule.rule_id!r} reads KPI {k!r}, which is not registered")
    check(rule.severity in R.SEVERITY_RANK, f"rule {rule.rule_id!r}: severity {rule.severity!r}")
    # Nothing at all: no finding, no exception.
    empty = {k: {"value": None, "unit": "count"} for k in rule.kpis}
    try:
        check(rule.fn(empty, P()) is None, f"{rule.rule_id}: raised on unknown figures")
    except Exception as e:  # pragma: no cover
        check(False, f"{rule.rule_id}: failed on unknown figures: {e!r}")
    # Empty thresholds (an administrator cleared the field) behave as zero.
    try:
        rule.fn(empty, {"threshold_amount": None, "threshold_count": None})
    except Exception as e:  # pragma: no cover
        check(False, f"{rule.rule_id}: failed on an empty threshold: {e!r}")

ar = {"ar_over_90": fig(6777143), "ar_total": fig(9177569),
      "largest_debt": fig(737544, group="HAIRASH ENTERPRISE")}
f = R.ar_overdue(ar, P(threshold_amount=50000))
check(f and f["title"] == "GHS 6.78M of the GHS 9.18M owed is more than three months late",
      f"ar_overdue title: {f and f['title']!r}")
check(f and "74%" in f["why"] and "HAIRASH ENTERPRISE" in f["why"], f"ar_overdue why: {f and f['why']!r}")
check(f and f["drill"]["filters"] == {"ageing_bucket": "90+"}, "ar_overdue must open the 90+ invoices")
check(R.ar_overdue(ar, P(threshold_amount=7_000_000)) is None, "ar_overdue raised below its threshold")
check(R.ar_overdue(ar, P(threshold_amount=6777143)) is None, "ar_overdue raised at exactly its threshold")

st = {"stock_short_products": fig(491, "count"), "stock_worst_shortfall": fig(39941, "quantity", group="SYR-5ML")}
f = R.stock_shortfall(st, P())
check(f and "491 products" in f["title"] and "SYR-5ML, 39,941 short" in f["why"],
      f"stock_shortfall: {f}")
check(R.stock_shortfall({**st, "stock_short_products": fig(0, "count")}, P()) is None,
      "stock_shortfall raised with nothing short")

jobs = {"tasks_overdue": fig(6, "count"), "tasks_longest_wait": fig(850, "days", group="Samkwarth lab")}
f = R.tasks_overdue(jobs, P())
check(f and f["title"] == "6 jobs are past their date" and "28 months" in f["why"], f"tasks_overdue: {f}")
check(R.tasks_overdue(jobs, P(threshold_count=6)) is None, "tasks_overdue raised at its count")

check(elapsed("2025-05-01", "2025-08-12") == "over 3 months", elapsed("2025-05-01", "2025-08-12"))
check(elapsed("2025-08-01", "2025-08-12") == "11 days", elapsed("2025-08-01", "2025-08-12"))
check(elapsed("2023-01-01", "2025-08-12") == "over 2 years", elapsed("2023-01-01", "2025-08-12"))
check(elapsed(None) == "—", "elapsed of nothing")

print(f"test_alerts: {len(R.RULES)} rules")
if failures:
    print(f"\n{len(failures)} failure(s):")
    for x in failures:
        print("  -", x)
    sys.exit(1)
print("all passed")
