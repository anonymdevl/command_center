"""Report schedules: when each one is next due, and how it is described.

    python3 scripts/test_schedule.py

next_run() is the whole of "when does this go out", so it is tested against a fixed
clock: a daily, weekly and monthly schedule, each before and after its hour on the day,
and the month end. The sending itself (the analyst, the PDF, the email) needs a site.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m)


fr = types.ModuleType("frappe")
fr.utils = types.SimpleNamespace(
    get_datetime=lambda x: x if isinstance(x, dt.datetime) else dt.datetime.fromisoformat(str(x)),
    now_datetime=lambda: dt.datetime(2026, 10, 18, 9, 30), add_months=_add_months)
fr.whitelist = lambda *a, **k: (lambda f: f)
sys.modules["frappe"] = fr
sys.modules["frappe.utils"] = fr.utils
biz = types.ModuleType("command_center.api.businesses")
biz.require_manager = lambda: None
sys.modules["command_center.api.businesses"] = biz

from command_center.api import reports  # noqa: E402

failures = []
S = lambda **k: types.SimpleNamespace(**{"hour": 7, "weekday": "Monday", "day_of_month": 1,  # noqa: E731
                                          "recipients": "a@x\nb@x", **k})
now = dt.datetime(2026, 10, 18, 9, 30)  # a Sunday


def check(ok, what):
    if not ok:
        failures.append(what)


cases = [
    (S(frequency="Daily"), dt.datetime(2026, 10, 19, 7), "daily, after today's hour: tomorrow 07:00"),
    (S(frequency="Daily", hour=18), dt.datetime(2026, 10, 18, 18), "daily, before its hour: today"),
    (S(frequency="Weekly"), dt.datetime(2026, 10, 19, 7), "weekly Monday from a Sunday: tomorrow"),
    (S(frequency="Weekly", weekday="Sunday"), dt.datetime(2026, 10, 25, 7), "weekly Sunday, past its hour: next week"),
    (S(frequency="Weekly", weekday="Sunday", hour=10), dt.datetime(2026, 10, 18, 10), "weekly Sunday, before its hour: today"),
    (S(frequency="Monthly"), dt.datetime(2026, 11, 1, 7), "monthly on the 1st: next month"),
    (S(frequency="Monthly", day_of_month=28), dt.datetime(2026, 10, 28, 7), "monthly on the 28th: this month"),
]
for sched, want, what in cases:
    got = reports.next_run(sched, now)
    check(got == want, f"{what}: wanted {want}, got {got}")
    check(got > now, f"{what}: next run {got} is not after now")

check(reports.describe(S(frequency="Weekly")) == "Mondays at 07:00 · 2 people",
      reports.describe(S(frequency="Weekly")))
check(reports.describe(S(frequency="Monthly", day_of_month=2, recipients="a@x")) ==
      "the 2nd of each month at 07:00 · 1 person", reports.describe(S(frequency="Monthly", day_of_month=2, recipients="a@x")))
check(reports._recipients("a@x, b@x\n\na@x;c@x") == ["a@x", "b@x", "c@x"], "recipients parse")
check("rp04" in reports.UNSCHEDULABLE, "the board report must not be schedulable")

print(f"test_schedule: {len(cases)} schedules")
if failures:
    print(f"\n{len(failures)} failure(s):")
    for x in failures:
        print("  -", x)
    sys.exit(1)
print("all passed")
