"""Questions the platform already knows the answer to, answered at once.

"How many unpaid invoices do we have?" is a figure on the Sales card. Sending it to the
analyst cost four rounds of Gemini on 18 Oct 2026 -- seventy-one seconds on the free
tier, and a table that contradicted its own headline because the model forgot to leave
out drafts. The card's figure was right all along.

So a plain question about a figure the KPI engine defines is answered from that engine:
the same number as the card, the same note, the same records behind it, in about a
second and without spending any of the model's allowance. Anything that asks why, how
it changed, what to do, or for a breakdown is left to the analyst -- this only takes the
questions it can answer completely, and says where the answer came from.
"""

from __future__ import annotations

import re

# Words that mean the person wants analysis, not a figure. Any of them sends the question
# on to the analyst.
ANALYSIS = re.compile(
    r"\b(why|how come|trend|trending|change|changed|compare|compared|versus|vs|forecast|"
    r"project|predict|should|recommend|advise|explain|breakdown|break down|by|per|each|"
    r"rank|top|best|worst|largest|biggest|smallest|list|show me|which|who|whom|when|"
    r"growth|grow|month|year|quarter|week|daily|history|over time|last|since|between)\b",
    re.I)

# (pattern, KPI keys in the order they are reported, one-line lead). Patterns are tried
# in order, so the more specific comes first.
RULES = [
    (r"\b(unpaid|outstanding|open)\b.*\b(supplier|purchase|vendor)\b.*\b(invoices?|bills?)\b|"
     r"\b(supplier|purchase|vendor)\b.*\b(invoices?|bills?)\b.*\b(unpaid|outstanding|open)\b|"
     r"\bunpaid bills?\b",
     ["ap_count", "ap_total"], "{ap_count} supplier invoices are unpaid, worth {ap_total}."),
    (r"\b(unpaid|outstanding|open)\b.*\binvoices?\b|\binvoices?\b.*\b(unpaid|outstanding|not paid)\b",
     ["ar_count", "ar_total", "ar_over_90"],
     "{ar_count} customer invoices are unpaid, worth {ar_total}; {ar_over_90} of it is more "
     "than three months late."),
    (r"\b(how much|what)\b.*\b(we owe|do we owe|owed to suppliers|payables?)\b",
     ["ap_total", "ap_count"], "We owe suppliers {ap_total}, across {ap_count} unpaid invoices."),
    (r"\b(how much|what)\b.*\b(owed to us|owe us|receivables?|outstanding|owed)\b",
     ["ar_total", "ar_over_90", "ar_count"],
     "Customers owe us {ar_total} across {ar_count} unpaid invoices; {ar_over_90} of it is "
     "more than three months late."),
    (r"\b(stock|inventory)\b.*\b(worth|value|valued|hold|have)\b|\b(value|worth)\b.*\b(stock|inventory)\b",
     ["stock_value", "stock_lines"], "We hold stock worth {stock_value}, across {stock_lines} "
     "item and warehouse lines."),
    (r"\b(open|undelivered|pending)\b.*\b(sales )?orders?\b|\borders?\b.*\b(not|un)\s*delivered\b",
     ["order_book_count", "order_book", "order_book_late"],
     "{order_book_count} sales orders are still open, with {order_book} to deliver; "
     "{order_book_late} of that is past the promised date."),
    (r"\b(never issued|draft|unsubmitted)\b.*\binvoices?\b|\binvoices?\b.*\b(never issued|draft)\b",
     ["invoices_draft", "invoices_draft_value"],
     "{invoices_draft} invoices were written but never issued, worth {invoices_draft_value}."),
    (r"\b(open|outstanding)\b.*\b(jobs?|tasks?|installations?)\b|\b(jobs?|tasks?)\b.*\b(open|overdue|late)\b",
     ["tasks_open", "tasks_overdue"], "{tasks_open} jobs are open; {tasks_overdue} are past "
     "their date."),
    (r"\b(open|unresolved|outstanding)\b.*\b(cases?|complaints?|issues?|tickets?)\b|"
     r"\b(cases?|complaints?|tickets?)\b.*\bopen\b",
     ["cases_open", "cases_avg_wait"], "{cases_open} customer issues are open, waiting "
     "{cases_avg_wait} on average."),
    (r"\b(how many)\b.*\b(employees?|staff|people|headcount|workers?)\b|\bheadcount\b",
     ["headcount", "people_total", "departments"], "{headcount} people are employed now, of "
     "{people_total} on the books, across {departments} departments."),
]
_COMPILED = [(re.compile(p, re.I), keys, lead) for p, keys, lead in RULES]


def match(question: str):
    """The rule for a plain figure question, or None. Short questions only: a long one is
    almost always asking for more than a figure."""
    q = (question or "").strip()
    if not q or len(q.split()) > 14 or ANALYSIS.search(q):
        return None
    for rx, keys, lead in _COMPILED:
        if rx.search(q):
            return keys, lead
    return None


def answer(question: str, business_code: str | None = None) -> dict | None:
    found = match(question)
    if not found:
        return None
    keys, lead = found
    from command_center.kpi.engine import _plain, evaluate_set

    figs = evaluate_set(keys, business_code)
    if any(figs[k].get("value") is None for k in keys[:1]):
        return None  # nothing loaded: let the analyst say what it can
    words = {k: _short(figs[k]) for k in keys}
    head = lead.format(**words)
    as_of = (figs[keys[0]].get("as_of") or {}).get("date")
    import json
    cards = [{"label": figs[k]["label"], "value": _short(figs[k]), "note": figs[k].get("note") or ""}
             for k in keys]
    follow = FOLLOWUPS.get(keys[0], [])
    text = "\n\n".join([
        f"**{head}**" + (f" As at {as_of}, the last date the data covers." if as_of else ""),
        "```figures\n" + json.dumps(cards) + "\n```",
        "These are the same figures as the cards on your screens, read straight from the "
        "records -- the AI was not needed for this one.",
    ] + (["```followups\n" + json.dumps(follow) + "\n```"] if follow else []))
    first = figs[keys[0]]
    drill = first.get("drill") or {}
    return {
        "answered": True, "answer": text, "format": "markdown", "question": question,
        "mode": "figures", "planner": "figures", "model": None,
        "checked": [f"{figs[k]['label']}: {_plain(figs[k])}" for k in keys],
        "records": {"fact": drill.get("fact"), "filters": drill.get("filters")} if drill.get("fact") else None,
        "figures": [], "steps": 0, "cut_short": False,
    }


FOLLOWUPS = {
    "ar_count": ["Who owes us the most, and how long have they owed it?",
                 "How has the amount owed changed over the last six months?"],
    "ap_count": ["Which suppliers do we owe the most, and how late are we?"],
    "ar_total": ["Who owes us the most, and how long have they owed it?"],
    "ap_total": ["Which suppliers do we owe the most, and how late are we?"],
    "stock_value": ["What stock is promised to customers but not on the shelves?"],
    "order_book_count": ["Which open orders are furthest past their promised date?"],
    "invoices_draft": ["Which of the invoices never issued are the largest?"],
    "tasks_open": ["Which installation jobs are running late, and who has them?"],
    "cases_open": ["Which customer issues have waited longest?"],
    "headcount": ["How is headcount split across departments?"],
}


def _short(fig) -> str:
    v = fig.get("value")
    if v is None:
        return "—"
    if fig.get("unit") == "currency":
        cur = fig.get("currency") or ""
        for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
            if abs(v) >= div:
                return f"{cur} {v / div:,.2f}{suf}".strip()
        return f"{cur} {v:,.0f}".strip()
    if fig.get("unit") == "days":
        return f"{v:,.0f} days"
    if fig.get("unit") == "percent":
        return f"{v:.1f}%"
    return f"{v:,.0f}"
