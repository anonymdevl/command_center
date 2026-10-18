"""The analyst, asked eight real questions on a live site, with the answers printed.

    bench --site biomed.ultrasoft-systems.com execute command_center.ask.selftest.run

The offline tests prove the loop; only a live site proves the judgement. This asks
questions across every area -- including ones the loaded data cannot answer without
ERPNext's own reports or documents -- and prints, for each: whether the analyst answered
or fell back (and why), how long it took, every lookup it made, and how the answer
opens. Paste the output back to whoever is tuning the analyst.

Read-only, like everything the analyst does. Runs as the bench user (Administrator).
"""

from __future__ import annotations

import time

import frappe

QUESTIONS = [
    "How did sales trend over the last 12 months, and where are we heading?",
    "Which suppliers do we depend on most?",
    "What was our profit and loss for July 2025?",
    "Show our open quotations and their total value.",
    "What stock is promised to customers but not on the shelves?",
    "Which installation jobs are running late, and who has them?",
    "Which customers buy the most from us, and what do they buy?",
    "How many people work here, by department?",
]


def run(questions=None, business_code: str | None = None):
    from command_center.ask import engine

    qs = questions or QUESTIONS
    if isinstance(qs, str):
        qs = [qs]
    print(f"\nAnalyst self-test on {frappe.local.site} -- mode: "
          f"{'analyst' if engine.analyst_enabled() else 'ROUTER (no key, or set to router)'}\n")
    ok = 0
    for i, q in enumerate(qs, 1):
        steps = []
        t0 = time.time()
        try:
            r = engine.answer(q, business_code, on_step=steps.append) or {}
        except Exception as e:
            r = {"answered": False, "analyst_error": f"raised: {e}"}
        secs = time.time() - t0
        by = r.get("mode") or r.get("planner") or "?"
        good = r.get("answered") and r.get("mode") == "analyst"
        ok += bool(good)
        print(f"{i}. {q}")
        print(f"   {'OK' if good else 'NOT ANSWERED BY THE ANALYST'} · {by} · {secs:.1f}s")
        if r.get("analyst_error"):
            print(f"   why: {r['analyst_error'][:300]}")
        for s in steps:
            print(f"   - {s}")
        for c in (r.get("checked") or [])[:12]:
            print(f"     {c[:160]}")
        opening = " ".join((r.get("answer") or "").split())[:260]
        print(f"   answer: {opening}\n")
    print(f"{ok} of {len(qs)} answered by the analyst.\n")
    return {"answered_by_analyst": ok, "asked": len(qs)}
