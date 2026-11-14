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
import re

import frappe

from command_center.ask import claude, gemini, tools

MAX_STEPS = 12           # rounds of tool use; the deadline below is what really bounds it
MAX_CALLS_PER_STEP = 6   # parallel tool calls honoured in one round
MAX_RESULT_CHARS = 12000 # one tool result, as sent back to the model: big ones slow every round
# A question runs inside the web request, which the server ends at 120 seconds. The
# analyst keeps inside 100: each Gemini call gets what is left (at most 60), and with
# 30 seconds to go it stops looking things up and answers from what it has, so a
# question ends in an answer rather than a timeout.
DEADLINE = 100
WRAP_UP_AT = 30
# A figure in a reply: a money amount, a percentage, a k/M/B amount or a number of three
# or more digits. A reply carrying one with nothing looked up came from memory.
_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:%|[kKMB]\b)|\b(?:GHS|USD|EUR|GBP)\s?\d|\d{3,}")


def answer(question: str, business_code: str | None = None, history=None,
           max_steps: int = MAX_STEPS, on_step=None, deadline: int = DEADLINE,
           resume: dict | None = None, deep: bool = False) -> dict | None:
    """max_steps: rounds of tool use. A question gets twelve; a report (api/reports.py)
    gathers across every area and gets more. on_step(text) is told each lookup, in plain
    words, as it starts -- the live "what it is doing" under the question bar.

    resume: the conversation a cut-short answer stopped at ({"contents", "checked"}),
    to carry on from exactly there in a background job (api/ask.py) rather than start
    again. A cut-short answer -- the budget ran out while the analyst still wanted to
    look further -- comes back with cut_short and _resume for that purpose.

    deep: the deeper look and the reports, which run on the provider's deeper model
    (Claude Opus rather than Sonnet; Gemini has one model for both)."""
    ad = _adapter(deep)
    if ad is None:
        return {"answered": False, "analyst_error": "no AI model is configured on this site"}
    static, dynamic = _system_parts(business_code)
    if resume and resume.get("provider", "gemini") == ad.name:
        contents = list(resume.get("contents") or [])
        checked = list(resume.get("checked") or [])
    else:
        # A conversation in one provider's shape cannot be carried on by the other.
        contents = ad.history(history) + [ad.user(question)]
        checked = []
    errors, drill = [], None
    text, steps, cut_short, snapshot = None, 0, False, None
    force = None  # "ANY" when the model must look something up this round (Gemini only)
    writes_before = _writes()
    import time
    started = time.monotonic()
    # One deadline for the whole question, which the model clients and the lookups
    # below also read: the budget used to be checked only between rounds, so a slow
    # reply, a run of retries or a heavy report inside one round could take minutes. On
    # 18 Oct 2026 a question ran for eleven minutes until the connection dropped.
    frappe.local.cc_deadline = started + deadline
    # gemini.py says here when a model is slow and it turns to another.
    frappe.local.cc_on_step = on_step
    frappe.local.cc_gemini_slow = False
    frappe.local.cc_claude_usage = None
    # One model call may take this long: a minute inside a web request, longer in a
    # background job where a long report is written in one go.
    call_cap = 60 if deadline <= DEADLINE else 240

    def left():
        return deadline - (time.monotonic() - started)

    def call_time():
        return int(max(5, min(call_cap, left() - 3)))

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
            ad.say(contents, ANSWER_NOW)
        # The model chooses whether to look anything up: "Hi" deserves a reply, not a
        # receivables summary (19 Oct 2026 -- every first round used to be forced to
        # call a tool). What it may not do is state figures it has not read; that is
        # caught below and sent back.
        reply, err = ad.chat(contents, static, dynamic, timeout=call_time(), final=final,
                             force=force)
        force = None
        if err:
            errors.append(err)
            # Refused part-way, after lookups were made: what was gathered is not thrown
            # away. One last turn asks for the answer from it (gemini falls over to
            # another model if this one is out of allowance).
            if checked and not final:
                ad.say(contents, ANSWER_NOW)
                reply, err2 = ad.chat(contents, static, dynamic, timeout=call_time(),
                                      final=True)
                if not err2 and reply:
                    contents.append(ad.message(reply))
                    text = ad.text(reply)
            break
        contents.append(ad.message(reply))
        calls = ad.calls(reply)
        if not calls:
            text = ad.text(reply)
            if not checked and not final and steps <= max_steps and _FIGURE.search(text or ""):
                # Figures, and nothing looked up: from memory. Once, it is sent back to
                # look them up, and must call a tool this time.
                ad.say(contents, ("You gave figures without looking anything up. Look them "
                                  "up with the tools first, then answer. Never state a "
                                  "figure from memory."))
                force, text = "ANY", None
                continue
            break

        results = []
        # Every call gets a result, in order: both providers refuse the next turn if a
        # call goes unanswered. Beyond the cap, the result says to ask for it again.
        for n, (call_id, name, args) in enumerate(calls):
            if n >= MAX_CALLS_PER_STEP:
                results.append((call_id, name, {
                    "error": f"Only {MAX_CALLS_PER_STEP} lookups run at once. Ask for this "
                             f"one again in the next round."}))
                continue
            # A lookup started with too little time left would run past the deadline, and
            # an ERPNext report can take a minute on its own.
            need = 45 if name == "run_report" else 12
            if left() < need:
                results.append((call_id, name, {
                    "error": "Out of time for more lookups. Answer from what you have, and "
                             "say what you could not check."}))
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
            results.append((call_id, name, _fit(result)))
        contents.append(ad.results(results))

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
    used = ad.used()
    return {
        "answered": True,
        "answer": text,
        "format": "markdown",
        "question": question,
        "checked": checked or ["nothing -- answered from the conversation so far"],
        "planner": ad.name,
        "mode": "analyst",
        "model": used.get("model") or ad.model(),
        "usage": used.get("usage"),
        "steps": steps,
        "records": drill,
        "figures": [],
        "degraded": errors or None,
        "cut_short": cut_short,
        "_resume": ({"contents": snapshot, "checked": checked, "provider": ad.name}
                    if cut_short else None),
    }


ANSWER_NOW = ("Answer now from what you have gathered. If it is incomplete, say what you "
              "could not check.")


# ---------------------------------------------------------------------------
# The two providers. The loop above is one loop; these turn its rounds into each
# provider's message shapes. Neither can reach anything but tools.declarations() and
# the replies' own text and tool calls.
# ---------------------------------------------------------------------------
def _adapter(deep: bool = False):
    from command_center.ask import llm
    p = llm.provider()
    if p == "claude":
        return _Claude(deep)
    if p == "gemini":
        return _Gemini()
    return None


class _Gemini:
    name = "gemini"

    def model(self):
        return gemini.analyst_model()

    def used(self):
        return {"model": getattr(frappe.local, "cc_gemini_used", None)}

    def user(self, text):
        return {"role": "user", "parts": [{"text": text}]}

    def say(self, contents, text):
        contents.append(self.user(text))

    def history(self, turns):
        return _history(turns)

    def chat(self, contents, static, dynamic, timeout, final=False, force=None):
        system = static + ("\n\n" + dynamic if dynamic else "")
        return gemini.chat(contents, None if final else tools.declarations(), system,
                           timeout=timeout, mode=force or "AUTO")

    def message(self, reply):
        return reply  # Gemini's content, unchanged (thinking signatures must come back)

    def calls(self, reply):
        return [(None, p["functionCall"].get("name", ""), p["functionCall"].get("args") or {})
                for p in (reply.get("parts") or []) if "functionCall" in p]

    def text(self, reply):
        return "".join(p.get("text", "") for p in (reply.get("parts") or [])
                       if not p.get("thought")).strip()

    def results(self, results):
        return {"role": "user", "parts": [
            {"functionResponse": {"name": name, "response": {"result": result}}}
            for _, name, result in results]}


class _Claude:
    name = "claude"

    def __init__(self, deep=False):
        self.kind = "deep" if deep else "analyst"

    def model(self):
        return claude.model_for(self.kind)

    def used(self):
        u = claude.usage()
        return {"model": (u or {}).get("model"), "usage": u}

    def user(self, text):
        return {"role": "user", "content": [{"type": "text", "text": text}]}

    def say(self, contents, text):
        # An instruction after the tool results goes in the same user turn, as a text
        # block after them: that turn has not been sent yet, so nothing sent is edited.
        last = contents[-1] if contents else None
        if last and last.get("role") == "user" and isinstance(last.get("content"), list):
            last["content"].append({"type": "text", "text": text})
        else:
            contents.append(self.user(text))

    def history(self, turns):
        out = []
        for turn in (turns or [])[-4:]:
            q, a = (turn or {}).get("q"), (turn or {}).get("a")
            if q and a:
                out.append({"role": "user", "content": str(q)[:2000]})
                out.append({"role": "assistant", "content": str(a)[:4000]})
        return out

    def chat(self, contents, static, dynamic, timeout, final=False, force=None):
        # The tool list goes on every round, the last one too: changing it would edit the
        # conversation's history. tool_choice "none" asks for the answer instead.
        return claude.chat(contents, tools.declarations(), static, dynamic, kind=self.kind,
                           timeout=timeout, final=final)

    def message(self, reply):
        return {"role": "assistant", "content": reply}  # unchanged, thinking included

    def calls(self, reply):
        return [(b.get("id"), b.get("name", ""), b.get("input") or {})
                for b in reply if b.get("type") == "tool_use"]

    def text(self, reply):
        return "".join(b.get("text", "") for b in reply if b.get("type") == "text").strip()

    def results(self, results):
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call_id,
             "content": json.dumps(result, default=str),
             **({"is_error": True} if isinstance(result, dict) and result.get("error") else {})}
            for call_id, _, result in results]}


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
    """The whole system prompt as one text (Gemini, and anyone reading it)."""
    static, dynamic = _system_parts(business_code)
    return static + "\n\n" + dynamic


def _system_parts(business_code) -> tuple:
    """(fixed, dated): the instructions, data sets and figure rules, which are the same
    on every request of every question -- Claude caches them, so they must not contain
    a date, a name or anything else that varies -- and the few lines that do vary,
    sent after them."""
    from command_center.facts.schema import DIMENSIONS, FACTS, MEASURES
    from command_center.kpi.registry import load_all

    data_sets = "\n".join(
        f"- {f} ({tools.FACT_WORDS.get(f, f)}): breakdowns {', '.join(DIMENSIONS.get(f, []))}; "
        f"amounts {', '.join(MEASURES.get(f, []))}; dates {', '.join(_dates(f)) or 'none'}"
        for f in FACTS)
    figures = _definitions(load_all())
    static = SYSTEM.format(data_sets=data_sets, figures=figures)
    dynamic = CONTEXT.format(today=frappe.utils.today(),
                             as_of=_as_of(business_code) or "unknown",
                             business=_business_name(business_code),
                             currency=_currency(business_code))
    return static, dynamic


def _currency(business_code) -> str:
    from command_center.api.businesses import currency_for
    return currency_for(business_code) or "GHS"


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


# The dated part, sent after the fixed instructions (see _system_parts).
CONTEXT = """TODAY AND SCOPE
Today is {today}. The loaded data runs up to {as_of} -- that is the data horizon.
Scope: {business}. Amounts are in {currency} unless a result says otherwise."""

SYSTEM = """You are the analyst inside the Command Center, the executive platform over \
the ERPNext of Gigmann Medical Supplies and its connected businesses. The people asking \
are directors and senior managers. They want straight answers, the reasons behind them, \
and what to do next.

Today's date, the data horizon (the last date the loaded data runs to) and the business \
in scope are given at the end of these instructions. Measure ageing, "this month", \
"recent" and "overdue" against the data horizon unless the person says otherwise, and say \
so when it matters -- a restored snapshot measured against today produces false findings.

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
not hold the ledger. Date filters must fall within the data, which ends at the data \
horizon.

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
- Look before you answer a question about the business: every figure you give comes \
from a lookup. A greeting, thanks or small talk needs no lookup -- reply naturally and \
briefly, as a colleague would, and offer a question or two you could answer.
- Check your totals before you answer. A table's total, or a count beside a defined \
figure, must equal that figure: the invoices behind the amount owed are the unpaid ones \
(ar_count), not every invoice. If they differ, your query is missing one of the \
figure's rules -- fix it and look again rather than print both.
- Never show a field, column, table or tool name (base_discount_amount, src_docstatus, \
fact_sales_invoice, query_data). Say what it means in plain words.
- Undelivered orders are goods still to deliver, not money we owe. Call them "goods \
still to deliver" or "undelivered orders", never "we owe them". "We owe" is only for \
supplier bills not yet paid.
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
[{{"label": "Owed to us", "value": "GHS 1.25M", "note": "120 unpaid invoices", "tone": "bad"}}]
(The numbers in these examples are made up; yours come from the tools.)
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
