"""A scorecard for the assistant: fifteen real questions, checked against the figures.

    bench --site <site> execute command_center.ask.evaluate.run
    bench --site <site> execute command_center.ask.evaluate.run --kwargs "{'limit': 5}"

"Is it smarter?" has to be answerable with numbers, before and after a change of model,
prompt or tools. Each question here has a known right answer -- the platform's own
figure for it -- and the scorecard says, per question, whether the answer contains that
figure, how long it took, whether the instant path or the analyst answered, how many
lookups it made, and why it failed if it did. The same fifteen, run on two models, is
the comparison.

Each question costs model requests (the instant ones cost none). On a free-tier key,
run a few at a time with limit.
"""

from __future__ import annotations

import time

import frappe

# (question, figures the answer must contain, what it must do)
QUESTIONS = [
    ("How many unpaid invoices do we have?", ["ar_count"], "figure"),
    ("How much do customers owe us?", ["ar_total"], "figure"),
    ("How much do we owe suppliers?", ["ap_total"], "figure"),
    ("What is our stock worth?", ["stock_value"], "figure"),
    ("Who owes us the most, and how long have they owed it?", ["largest_debt"], "analysis"),
    ("What was our best month for invoiced sales?", ["revenue_best_month"], "analysis"),
    ("Which suppliers do we depend on most?", ["supplier_top_share"], "analysis"),
    ("What stock is promised to customers but not on the shelves?", ["stock_short_products"], "analysis"),
    ("How many sales orders are past their promised date?", ["order_book_late_count"], "analysis"),
    ("Which installation jobs are running late, and who has them?", ["tasks_overdue"], "analysis"),
    ("How many open customer complaints are there?", ["cases_open"], "figure"),
    ("How many people do we employ, and in which departments?", ["headcount"], "analysis"),
    ("How did invoiced sales trend over the last 12 months?", [], "analysis"),
    ("Show our open quotations and their total value.", [], "analysis"),
    ("Issue a credit note for A1 Medicalsupplies.", [], "refusal"),
]


def run(limit: int | None = None, business_code: str | None = None) -> dict:
    from command_center.ask import engine
    from command_center.kpi.engine import evaluate_set

    if not business_code:
        business_code = frappe.db.get_value("Connected Business", {"is_local": 1}, "business_code")
    keys = sorted({k for _, ks, _ in QUESTIONS for k in ks})
    truth = evaluate_set(keys, business_code)

    rows = []
    for question, want, kind in QUESTIONS[: int(limit) if limit else None]:
        t0 = time.monotonic()
        try:
            r = engine.answer(question, business_code)
        except Exception as e:  # a crash is a result too
            r = {"answered": False, "analyst_error": f"raised {type(e).__name__}: {e}"}
        seconds = round(time.monotonic() - t0, 1)
        text = (r or {}).get("answer") or ""
        missing = [k for k in want if not _mentions(text, truth[k])]
        ok = bool(r and r.get("answered")) and not missing and not r.get("analyst_error")
        if kind == "refusal":
            ok = bool(text) and any(w in text.lower() for w in ("cannot", "can't", "can not", "not able"))
        rows.append({
            "question": question, "ok": ok, "seconds": seconds,
            "how": (r or {}).get("mode") or "basic",
            "model": (r or {}).get("model"), "lookups": len((r or {}).get("checked") or []),
            "missing": [f"{k}={_forms(truth[k])[0]}" for k in missing],
            "error": (r or {}).get("analyst_error"),
        })
        print(f"{'PASS' if ok else 'FAIL'} {seconds:6.1f}s {rows[-1]['how']:8} "
              f"{rows[-1]['lookups']:2} lookups  {question}"
              + (f"  -- missing {', '.join(rows[-1]['missing'])}" if missing else "")
              + (f"  -- {rows[-1]['error'][:120]}" if rows[-1]["error"] else ""))
    passed = sum(1 for x in rows if x["ok"])
    total_s = sum(x["seconds"] for x in rows)
    print(f"\n{passed}/{len(rows)} passed, {total_s:.0f}s in all, "
          f"median {sorted(x['seconds'] for x in rows)[len(rows) // 2] if rows else 0}s")
    return {"passed": passed, "of": len(rows), "rows": rows}


def _forms(fig) -> list:
    """The ways a figure may be written in an answer: 806; 9,177,569; 9.18M; 9.2M ..."""
    v = fig.get("value")
    if v is None:
        return ["—"]
    v = float(v)
    forms = {f"{v:,.0f}", f"{v:.0f}", f"{v:,.2f}"}
    if fig.get("unit") == "percent":
        forms |= {f"{v:.0f}%", f"{v:.1f}%"}
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k"), (1e3, "K")):
        if abs(v) >= div:
            forms |= {f"{v / div:.2f}{suf}", f"{v / div:.1f}{suf}", f"{v / div:,.0f}{suf}"}
            break
    return sorted(forms, key=len, reverse=True)


def _mentions(text: str, fig) -> bool:
    flat = (text or "").replace(" ", "").replace(" M", "M").replace(" k", "k")
    return any(f in flat for f in _forms(fig))
