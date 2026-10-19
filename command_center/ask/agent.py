"""The analyst: Gemini, reading the business through tools, answering in full.

This replaces "Gemini routes; the facts answer" (Michael's decision, 18 Oct 2026). The
model now reads whatever figures and records a question needs -- within the asking
person's own permissions -- and reasons over them: explains, compares, projects and
recommends. What it cannot do is change anything. That is enforced in tools.py, by
there being no write tool at all, and here, by rolling back any write that happens
while a question is answered.

The loop is plain: send the conversation and the tool catalogue, run whatever tools
the model asks for, send their results back, repeat until it answers or the step budget
runs out -- at which point it is told to answer from what it has. Every tool call is
recorded and shown under the answer as "what it checked", so a reader can see what the
answer rests on.

If the model cannot be reached, returns nothing, or a key is not configured, this
returns None and engine.py falls back to the pattern answers. The question box never
goes dark because a third party is having a bad afternoon.
"""

from __future__ import annotations

import json

import frappe

from command_center.ask import gemini, tools

MAX_STEPS = 12           # rounds of tool use; the deadline below is what really bounds it
MAX_CALLS_PER_STEP = 6   # parallel tool calls honoured in one round
MAX_RESULT_CHARS = 12000 # one tool result, as sent back to the model: big ones slow every round
# A question runs inside the web request, which the server ends at 120 seconds. The
# analyst keeps inside 100: each Gemini call gets what is left (at most 60), and with
# 30 seconds to go it stops looking things up and answers from what it has, so a
# question ends in an answer rather than a timeout.
DEADLINE = 100
WRAP_UP_AT = 30


def answer(question: str, business_code: str | None = None, history=None,
           max_steps: int = MAX_STEPS, on_step=None, deadline: int = DEADLINE,
           resume: dict | None = None) -> dict | None:
    """max_steps: rounds of tool use. A question gets twelve; a report (api/reports.py)
    gathers across every area and gets more. on_step(text) is told each lookup, in plain
    words, as it starts -- the live "what it is doing" under the question bar.

    resume: the conversation a cut-short answer stopped at ({"contents", "checked"}),
    to carry on from exactly there in a background job (api/ask.py) rather than start
    again. A cut-short answer -- the budget ran out while the analyst still wanted to
    look further -- comes back with cut_short and _resume for that purpose."""
    system = _system(business_code)
    if resume:
        contents = list(resume.get("contents") or [])
        checked = list(resume.get("checked") or [])
    else:
        contents = _history(history) + [{"role": "user", "parts": [{"text": question}]}]
        checked = []
    errors, drill = [], None
    text, steps, cut_short, snapshot = None, 0, False, None
    writes_before = _writes()
    import time
    started = time.monotonic()
    # One deadline for the whole question, which gemini.py and the lookups below also
    # read: the budget used to be checked only between rounds, so a slow reply, a run of
    # retries or a heavy report inside one round could take minutes. On 18 Oct 2026 a
    # question ran for eleven minutes until the connection dropped.
    frappe.local.cc_deadline = started + deadline
    # gemini.py says here when a model is slow and it turns to another.
    frappe.local.cc_on_step = on_step
    frappe.local.cc_gemini_slow = False

    def left():
        return deadline - (time.monotonic() - started)

    for steps in range(1, max_steps + 2):
        remaining = left()
        if remaining < 8:
            # Not even time to ask for an answer: stop, and say so.
            errors.append("it ran out of time before it could answer")
            cut_short = cut_short or bool(checked)
            break
        out_of_time = steps > 1 and remaining < WRAP_UP_AT and steps <= max_steps
        final = steps > max_steps or out_of_time
        if out_of_time and not cut_short:
            # Where it got to, before being told to answer -- a deeper look resumes here.
            cut_short, snapshot = True, json.loads(json.dumps(contents, default=str))
        if final:
            # Out of budget: answer from what has been gathered, and say if incomplete.
            contents.append({"role": "user", "parts": [{"text": (
                "Answer now from what you have gathered. If it is incomplete, say what "
                "you could not check.")}]})
        # The first round must look something up: an answer is only as good as what it
        # read, and a model left free to answer at once can answer from memory.
        content, err = gemini.chat(contents, None if final else tools.declarations(), system,
                                   timeout=int(max(5, min(60, left() - 3))),
                                   mode="ANY" if steps == 1 and not resume else "AUTO")
        if err:
            errors.append(err)
            # Refused part-way, after lookups were made: what was gathered is not thrown
            # away. One last turn asks for the answer from it (gemini falls over to
            # another model if this one is out of allowance).
            if checked and not final:
                contents.append({"role": "user", "parts": [{"text": (
                    "Answer now from what you have gathered. If it is incomplete, say "
                    "what you could not check.")}]})
                content, err2 = gemini.chat(contents, None, system,
                                            timeout=int(max(5, min(60, left() - 3))))
                if not err2 and content:
                    contents.append(content)
                    text = "".join(p.get("text", "") for p in (content.get("parts") or [])
                                   if not p.get("thought")).strip()
            break
        contents.append(content)
        parts = content.get("parts") or []
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not calls:
            text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            break

        responses = []
        # Every call gets a response, in order: Gemini refuses the next turn if the counts
        # differ. Beyond the cap, the response says to ask for it again.
        for n, call in enumerate(calls):
            name, args = call.get("name", ""), call.get("args") or {}
            if n >= MAX_CALLS_PER_STEP:
                responses.append({"functionResponse": {"name": name, "response": {"result": {
                    "error": f"Only {MAX_CALLS_PER_STEP} lookups run at once. Ask for this "
                             f"one again in the next round."}}}})
                continue
            # A lookup started with too little time left would run past the deadline, and
            # an ERPNext report can take a minute on its own.
            need = 45 if name == "run_report" else 12
            if left() < need:
                responses.append({"functionResponse": {"name": name, "response": {"result": {
                    "error": "Out of time for more lookups. Answer from what you have, and "
                             "say what you could not check."}}}})
                continue
            if on_step:
                try:
                    on_step(tools.describe(name, args))
                except Exception:
                    pass  # progress is a courtesy; it never stops an answer
            try:
                with _statement_limit(max(3, min(25, int(left() - 8)))):
                    result = tools.run(name, args, business_code)
                checked.append(tools.summary(name, args))
                if name in ("query_data", "list_records") and isinstance(result, dict):
                    drill = {"fact": result.get("data_set"), "filters": result.get("filters")}
            except tools.ToolError as e:
                result = {"error": str(e)}
                checked.append(tools.summary(name, args) + " -- refused: " + str(e)[:120])
            except Exception:
                errors.append(f"tool {name} failed: {frappe.get_traceback()[:1500]}")
                result = {"error": "That lookup failed. Try a different way to answer, or "
                                   "say the figure could not be checked."}
                checked.append(tools.summary(name, args) + " -- failed")
            responses.append({"functionResponse": {"name": name,
                                                   "response": {"result": _fit(result)}}})
        contents.append({"role": "user", "parts": responses})

    frappe.local.cc_deadline = None
    frappe.local.cc_on_step = None
    # The guard. Nothing above can write -- tools.py has no write path and preflight
    # holds it that way -- so a write here means something changed underneath us, and
    # it is undone before anyone can rely on it.
    if _writes() > writes_before:
        frappe.db.rollback()
        errors.append("A database write happened while answering a question and was "
                      "rolled back. The assistant is read-only; this needs looking at.")
    for e in errors:
        frappe.log_error(title="Command Center analyst", message=f"Q: {question}\n\n{e}")

    if not text:
        # Not None: engine.py falls back to the patterns, and says why the analyst
        # did not answer instead of letting the fallback pass for the analyst.
        return {"answered": False, "analyst_error": (errors[-1] if errors else
                "the model returned no answer")[:400]}
    return {
        "answered": True,
        "answer": text,
        "format": "markdown",
        "question": question,
        "checked": checked or ["nothing -- answered from the conversation so far"],
        "planner": "gemini",
        "mode": "analyst",
        "model": gemini.analyst_model(),
        "steps": steps,
        "records": drill,
        "figures": [],
        "degraded": errors or None,
        "cut_short": cut_short,
        "_resume": {"contents": snapshot, "checked": checked} if cut_short else None,
    }


class _statement_limit:
    """Stop any single database query a lookup runs after `seconds` (MariaDB's
    max_statement_time, for this connection only, put back afterwards). A query that
    would run on past the question's deadline is ended by the database, and the lookup
    returns an error the model can work around."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.on = False

    def __enter__(self):
        try:
            if getattr(frappe.db, "db_type", "mariadb") == "mariadb":
                frappe.db.sql("SET SESSION max_statement_time = %s", (self.seconds,))
                self.on = True
        except Exception:
            self.on = False
        return self

    def __exit__(self, *exc):
        if self.on:
            try:
                frappe.db.sql("SET SESSION max_statement_time = 0")
            except Exception:
                pass
        return False


def _writes() -> int:
    # Frappe counts write queries per transaction; it is what raises "too many writes".
    return int(getattr(frappe.db, "transaction_writes", 0) or 0)


def _fit(result) -> dict:
    """A tool result small enough to send back, trimmed by rows rather than mid-JSON."""
    raw = json.dumps(result, default=str)
    if len(raw) <= MAX_RESULT_CHARS:
        return result if isinstance(result, dict) else {"value": result}
    if isinstance(result, dict) and isinstance(result.get("rows"), list):
        rows = result["rows"]
        while rows and len(json.dumps({**result, "rows": rows}, default=str)) > MAX_RESULT_CHARS:
            rows = rows[: max(1, len(rows) * 2 // 3)] if len(rows) > 1 else []
        return {**result, "rows": rows, "trimmed": f"showing {len(rows)} of {len(result['rows'])} rows"}
    return {"value": raw[:MAX_RESULT_CHARS], "trimmed": "the result was cut to fit"}


def _history(history) -> list:
    """The last few turns, so "and last month?" means something."""
    out = []
    for turn in (history or [])[-4:]:
        q, a = (turn or {}).get("q"), (turn or {}).get("a")
        if q and a:
            out.append({"role": "user", "parts": [{"text": str(q)[:2000]}]})
            out.append({"role": "model", "parts": [{"text": str(a)[:4000]}]})
    return out


def _system(business_code) -> str:
    from command_center.facts.schema import DIMENSIONS, FACTS, MEASURES
    from command_center.kpi.registry import load_all

    as_of = _as_of(business_code)
    business = _business_name(business_code)
    data_sets = "\n".join(
        f"- {f} ({tools.FACT_WORDS.get(f, f)}): breakdowns {', '.join(DIMENSIONS.get(f, []))}; "
        f"amounts {', '.join(MEASURES.get(f, []))}; dates {', '.join(_dates(f)) or 'none'}"
        for f in FACTS)
    figures = _definitions(load_all())
    return SYSTEM.format(today=frappe.utils.today(), as_of=as_of or "unknown",
                         business=business, data_sets=data_sets, figures=figures)


def _definitions(registry) -> str:
    """Every defined figure with the exact rule behind it, generated from the registry.

    The model used to be told only each figure's name, so when it broke a figure down it
    made up its own filters -- 888 "unpaid invoices" in a table under a headline of 806,
    because it counted drafts. Given the rule, its own query agrees with the card.
    """
    from command_center.kpi.live import LIVE

    def rule(f):
        parts = []
        for col, val in (f or {}).items():
            if isinstance(val, (list, tuple)) and len(val) == 2 and isinstance(val[0], str) \
                    and val[0] in (">", ">=", "<", "<=", "=", "!=", "like", "between", "in", "not in"):
                parts.append(f"{col} {val[0]} {val[1]}")
            elif isinstance(val, (list, tuple)):
                parts.append(f"{col} in {list(val)}")
            else:
                parts.append(f"{col} = {val}")
        return " and ".join(parts) or "all rows"

    out = []
    for k, v in sorted(registry.items(), key=lambda kv: (kv[1].fact, kv[0])):
        if v.agg == "ratio":
            what = f"{v.numerator} / {v.denominator} as a percentage"
        else:
            what = {"count": "count of rows", "count_distinct": f"count of distinct {v.distinct_on}",
                    "avg": f"average {v.measure}", "max": f"largest {v.measure}",
                    "top": f"leading {v.group_by} by {v.group_agg} of {v.measure}"}.get(
                v.agg, f"sum of {v.measure}")
            what += f" in {v.fact} where {rule(v.filters)}"
            if v.period:
                what += f", over the {v.period['window'].replace('_', ' ')} by {v.period['field']}"
        out.append(f"- {k}: {v.label} = {what}")
    for k, v in sorted(LIVE.items()):
        out.append(f"- {k}: {v.label} (read straight from ERPNext)")
    return "\n".join(out)


def _dates(fact: str) -> list:
    """The date columns of a fact, so a trend or a period is asked on the right one."""
    from command_center.facts.schema import FACTS
    try:
        meta = frappe.get_meta(FACTS[fact])
        return [x.fieldname for x in meta.fields if x.fieldtype in ("Date", "Datetime")
                and x.fieldname not in ("src_modified", "ingested_at", "as_of_date")]
    except Exception:
        return []


def _as_of(business_code):
    try:
        from command_center.www.command_center import _as_of as boot_as_of
        d = boot_as_of()
        return (d or {}).get("date") if isinstance(d, dict) else d
    except Exception:
        return None


def _business_name(business_code) -> str:
    if business_code and business_code != "__all__":
        return frappe.db.get_value("Connected Business", {"business_code": business_code}, "business_name") or business_code
    return "all connected businesses"


SYSTEM = """You are the analyst inside the Command Center, the executive platform over \
Gigmann Medical Supplies' ERPNext. The people asking are directors and senior managers. \
They want straight answers, the reasons behind them, and what to do next.

Today is {today}. The loaded data runs up to {as_of}. Measure ageing, "this month", \
"recent" and "overdue" against {as_of} unless the person says otherwise, and say so when \
it matters -- a restored snapshot measured against today produces false findings.
Scope: {business}. Amounts are in Ghana cedis (GHS) unless a result says otherwise.

WHERE THE DATA IS
1. Loaded data sets -- fast, complete, for totals, breakdowns and trends:
{data_sets}
   Call describe_data for the full columns and date fields of any of them.
2. The platform's defined figures (get_figures), the same numbers its cards show, each \
with the exact rule behind it. Reuse these rules as your filters when you break a figure \
down, so your totals agree with the screens:
{figures}
3. Live ERPNext, through erpnext_fields / erpnext_list / erpnext_count / erpnext_document: \
any doctype the person asking may read -- quotations, leads, opportunities, journal entries, \
projects, assets, employees, issues and the rest. Use it for anything the loaded sets do \
not hold, and for the detail behind a figure.
4. Six ready analyses: who_owes_most, has_party_ever_paid, why_order_open, \
supplier_concentration, owes_and_waiting, party_brief.
5. ERPNext's own standard reports, through report_filters / run_report: profit and loss, \
balance sheet, cash flow, trial balance, general ledger, receivables and payables, gross \
profit, sales and purchase analytics, purchase order analysis, stock balance, ledger and \
ageing. Use them for finance, purchase orders and stock movements -- the loaded sets do \
not hold the ledger. Date filters must fall within the data, which ends {as_of}.

HOW TO FIND THE ANSWER -- in this order, stopping as soon as you have it
1. A defined figure answers it: get_figures, one call with every key you need.
2. A breakdown, ranking, comparison or period: ONE query_data call that makes the \
database do the work -- conditions in filters, the split in group_by (up to two \
columns), the period and date range, the order and a limit. Use the same rules as the \
figure definitions above. Never fetch rows to count or add them up yourself.
3. Individual records (the largest, latest, most overdue): list_records with filters, \
order_by and a small limit.
4. A name you are not sure of: find first, then filter on the exact name it returns.
5. Something the loaded sets do not hold: erpnext_count, or erpnext_list with filters, \
only the fields you need and a limit; erpnext_document for one document.
6. Ledger, profit and loss, balance sheet, cash flow, stock movements: run_report. It is \
slow; use it only for these.
Put independent lookups in the same round. Most questions need one or two rounds; once \
you can answer, stop looking and answer.
The loaded sets count submitted documents only, as the screens do. For drafts or \
cancelled documents, filter src_docstatus yourself (0 draft, 2 cancelled).

HOW TO WORK
- Look before you answer.
- Check your totals before you answer. A table's total, or a count beside a defined \
figure, must equal that figure: invoices behind GHS 9.18M owed are the unpaid ones \
(ar_count), not every invoice. If they differ, your query is missing one of the \
figure's rules -- fix it and look again rather than print both.
- Never show a field, column, table or tool name (base_discount_amount, src_docstatus, \
fact_sales_invoice, query_data). Say what it means in plain words.
- Answer the question that was asked. Do not widen it to other areas (supplier bills \
when asked about invoices, say); offer those as follow-up questions instead.
- Every figure you state must come from a tool result, or be calculated from tool results \
with the calculation made plain. Never estimate a number you could have looked up, and \
never invent one.
- If a figure covers part of something (the top ten, one warehouse, one year), say what it \
is part of.
- If the data to answer is not loaded or not readable, say exactly what is missing and \
answer what you can.
- Projections: use the trend tool, label them "Projection", give the range and the method, \
and say they assume the recent pattern continues.
- Advice: label each "Recommendation", make it specific (who, what, by when), and tie it to \
the figures that justify it.
- Personal and payroll data: give it only when it is asked for and the tools return it.

YOU CANNOT CHANGE ANYTHING
You can read; you cannot create, edit, submit, cancel, delete, approve, pay or send \
anything in ERPNext, whoever asks and whatever they authorise. If asked, say so plainly, \
say where in ERPNext and by whom it would be done, and offer to draft the wording or \
prepare the figures for the person who will do it.

HOW TO ANSWER
Answer like a sharp analyst briefing a director, not like a form. No "Answer:" label, no \
restating the question.

FIRST, MATCH THE SHAPE TO THE QUESTION. Most questions are not analysis.
- A lookup, a count, a yes/no, a list or a document ("how many users are active", "who \
is our biggest supplier", "show the open quotations", "what is on order SO-123"): one or \
two sentences that answer it, then a table or list if there are rows to show. No \
figures block, no chart, no recommendations unless something is plainly wrong.
- A question about how the business is doing -- money, performance, trend, comparison, \
risk, what to do: the fuller shape below.
Never pad: a short question deserves a short answer.

THE FULLER SHAPE, for analysis:
1. Open with the answer itself in one or two plain sentences -- the number and what it \
means. This line is shown as the headline.
2. When the answer turns on two to four headline numbers, put them right after the \
opening in a figures block (JSON, exactly this shape; tone is good, bad, warn or omitted):
```figures
[{{"label": "Owed to us", "value": "GHS 9.18M", "note": "806 unpaid invoices", "tone": "bad"}}]
```
3. When a picture says it faster, add a chart block -- bar to compare up to twelve names \
(largest first), line for change over time, donut for shares of a whole:
```chart
{{"type": "bar", "title": "Spend by supplier, last 12 months", "unit": "GHS", \
"labels": ["A", "B"], "series": [{{"name": "Spend", "values": [1200.5, 900]}}]}}
```
Values are plain numbers, not text. Use at most two charts; skip them for one-number \
answers.
4. Then the detail: short headings, bullets, and a markdown table for any list of more \
than three items (the reader likes tables). Plain words, no jargon, no field names.
5. Close with Recommendations when there is something worth doing, each on its own \
bullet starting "Recommendation:".
(For every answer, short or full:)
6. End with two or three follow-up questions the person is likely to ask next -- short, \
specific to this answer, answerable from the data -- as a followups block:
```followups
["Which of these customers has not paid in 90 days?", "How does this compare with last year?"]
```
Every number in a figures or chart block must come from a tool result, exactly like a \
number in the text. Keep it under about 300 words of prose unless a report is asked for.
"""
