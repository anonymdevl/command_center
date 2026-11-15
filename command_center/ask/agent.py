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
           resume: dict | None = None, deep: bool = False, should_stop=None) -> dict | None:
    """max_steps: rounds of tool use. A question gets twelve; a report (api/reports.py)
    gathers across every area and gets more. on_step(text) is told each lookup, in plain
    words, as it starts -- the live "what it is doing" under the question bar.

    resume: the conversation a cut-short answer stopped at ({"contents", "checked"}),
    to carry on from exactly there in a background job (api/ask.py) rather than start
    again. A cut-short answer -- the budget ran out while the analyst still wanted to
    look further -- comes back with cut_short and _resume for that purpose.

    deep: the deeper look and the reports, which run on the provider's deeper model
    (Claude Opus rather than Sonnet; Gemini has one model for both).

    should_stop(): true once the person has pressed Stop (api/ask.py keeps the flag in
    the cache). It is asked between rounds and before each lookup -- a model call
    already under way is not interrupted -- and a stopped question ends at once, with
    no further model call, in a partial answer built from what had been gathered.
    Unset, api/ask.py's flag for this request is read from frappe.local."""
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
    should_stop = should_stop or getattr(frappe.local, "cc_should_stop", None)
    stopped, gathered, drafts = False, [], []

    def halted():
        nonlocal stopped
        if not stopped and should_stop:
            try:
                stopped = bool(should_stop())
            except Exception:
                pass  # a flag that cannot be read never stops an answer
        return stopped

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
        if halted():
            break
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
        if halted():
            # Stopped while the model was choosing its next lookups: they are not run.
            drafts.append(ad.text(reply))
            break
        drafts.append(ad.text(reply))  # words written alongside the lookups, if any

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
            if halted():
                break
            if left() < need:
                results.append((call_id, name, {
                    "error": "Out of time for more lookups. Answer from what you have, and "
                             "say what you could not check."}))
                continue
            if on_step:
                try:
                    on_step(tools.step(name, args))
                except Exception:
                    pass  # progress is a courtesy; it never stops an answer
            try:
                with _statement_limit(max(3, min(25, int(left() - 8)))):
                    result = tools.run(name, args, business_code)
                checked.append(tools.summary(name, args))
                if name in ("query_data", "list_records", "compare_periods") \
                        and isinstance(result, dict) and result.get("data_set"):
                    drill = {"fact": result.get("data_set"), "filters": result.get("filters")}
                gathered.append((name, result))
            except tools.ToolError as e:
                result = {"error": str(e)}
                checked.append(tools.summary(name, args) + " -- refused: " + str(e)[:120])
            except Exception:
                errors.append(f"tool {name} failed: {frappe.get_traceback()[:1500]}")
                result = {"error": "That lookup failed. Try a different way to answer, or "
                                   "say the figure could not be checked."}
                checked.append(tools.summary(name, args) + " -- failed")
            results.append((call_id, name, _fit(result)))
        if stopped:
            break
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

    if stopped and not text:
        text = _partial(drafts, gathered)
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
        "cut_short": cut_short and not stopped,
        "stopped": stopped or None,
        "_resume": ({"contents": snapshot, "checked": checked, "provider": ad.name}
                    if cut_short and not stopped else None),
    }


STOPPED = "Stopped — here is what I had so far."


def _partial(drafts: list, gathered: list) -> str:
    """The answer to a question stopped part-way: no further model call, only what was
    already in hand -- anything the model had written, and the figures its lookups had
    returned, stated exactly as the tools gave them."""
    from command_center.kpi.engine import _plain

    lines = []
    for name, res in gathered:
        if not isinstance(res, dict) or res.get("error"):
            continue
        if name == "get_figures":
            for f in res.values():
                if isinstance(f, dict) and f.get("value") is not None and f.get("unit"):
                    lines.append(f"- {f.get('label')}: {_plain(f)}"
                                 + (f" ({f['note']})" if f.get("note") else ""))
        elif name == "compare_periods" and res.get("current"):
            cur, old = res["current"], res.get("earlier") or {}
            pct = res.get("change_pct")
            lines.append(f"- {res.get('what')}: {cur.get('text', cur.get('value'))} in "
                         f"{cur.get('period')}, against {old.get('text', old.get('value'))} "
                         f"in {old.get('period')}"
                         + (f" ({pct:+.1f}%)" if isinstance(pct, (int, float)) else ""))
    said = "\n\n".join(d for d in drafts if d).strip()
    out = [f"**{STOPPED}**"]
    if said:
        out.append(said)
    if lines:
        out.append("Figures it had read:\n" + "\n".join(lines))
    if not said and not lines:
        out.append("It stopped before it had found anything worth reporting. "
                   + ("The lookups it made are listed under what it checked."
                      if gathered else "Nothing had been looked up yet."))
    else:
        out.append("This is incomplete: it stopped before it could finish working it out.")
    return "\n\n".join(out)


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
    dynamic = CONTEXT.format(today=_today(),
                             as_of=_as_of(business_code) or "unknown",
                             business=_business_name(business_code),
                             currency=_currency(business_code))
    return static, dynamic


def _today() -> str:
    """Today as a person writes it, with the weekday ("Sunday 15 November 2026,
    2026-11-15"), so "this week" and "yesterday" need no working out. It is sent after
    the cache marker (CONTEXT), so a new day never rewrites the cached opening."""
    d = frappe.utils.getdate(frappe.utils.today())
    return f"{d:%A} {d.day} {d:%B %Y}, {d.isoformat()}"


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

SYSTEM = """You are the analyst inside an executive intelligence platform over the \
ERPNext of the businesses connected to it. Refer to yourself, when you need to, as "the \
analyst". The people asking are directors and senior managers. They want straight answers, the reasons behind them, \
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
4. compare_periods: one figure (by key) or one measure of a data set in two periods -- \
the latest full month against the month before or the same month last year, the latest \
full quarter against the one before or a year earlier, twelve months against the twelve \
before, or two date ranges you give -- with both values, the change and the % change, by \
the same rules as the figures.
5. Six ready analyses: who_owes_most, has_party_ever_paid, why_order_open, \
supplier_concentration, owes_and_waiting, party_brief.
5a. current_recommendations: the platform's own recommendations for the business, ranked \
by money at stake, each with its evidence and steps -- the list the screens show as Top \
actions.
5b. order_cover: sales-order lines promised and not delivered, and what covers each -- \
stock (and in which warehouse), goods received for it, purchase orders linked to it or \
likely to be for it, requests -- with the receipts and supplier invoices, and the totals \
by state, read live. "Likely" is inferred from the item and dates, not linked in ERPNext: \
say so whenever you rely on it.
6. ERPNext's own standard reports, through report_filters / run_report: profit and loss, \
balance sheet, cash flow, trial balance, general ledger, receivables and payables, gross \
profit, sales and purchase analytics, purchase order analysis, stock balance, ledger and \
ageing. Use them for finance, purchase orders and stock movements -- the loaded sets do \
not hold the ledger. Date filters must fall within the data, which ends at the data \
horizon.
7. People and leave, read live from ERPNext as the HR screen reads them: people (find \
employees by name or ID, department or status -- job, department, branch, manager, \
joining date, length of service) and leave (one person's balance by leave type -- \
allocated, taken, pending approval, remaining -- and their recent leave; or, with no \
person, who is on approved leave today and this week, requests waiting for approval, \
everyone's balances, and days taken this year by department). Leave is counted as \
ERPNext's own leave balance counts it, and is measured against today, not the data \
horizon. Neither returns contact details or pay.

HOW TO FIND THE ANSWER -- in this order, stopping as soon as you have it
0. "What should I focus on", "what needs my attention", "what should we do": \
current_recommendations first, then the figures or records behind the ones that matter; \
build the answer on them, largest money at stake first, and say where you disagree.
1. A defined figure answers it: get_figures, one call with every key you need.
2. Up or down against an earlier period ("than last month", "against last year", "why \
did it fall"): compare_periods, one call per number. Use its change and % change as \
given; do not work them out again. A figure that is a position now (owed, stock, open \
orders) has no history -- say so; compare it only with a date_column, and then say it \
counts the records dated in each period.
3. A breakdown, ranking or period: ONE query_data call that makes the \
database do the work -- conditions in filters, the split in group_by (up to two \
columns), the period and date range, the order and a limit. Use the same rules as the \
figure definitions above. Never fetch rows to count or add them up yourself.
4. Individual records (the largest, latest, most overdue): list_records with filters, \
order_by and a small limit.
5. A name you are not sure of: find first, then filter on the exact name it returns.
6. Something the loaded sets do not hold: erpnext_count, or erpnext_list with filters, \
only the fields you need and a limit; erpnext_document for one document.
7. Ledger, profit and loss, balance sheet, cash flow, stock movements: run_report. It is \
slow; use it only for these.
7a. Orders promised and not delivered -- can we deliver, what is on order for them, what \
nobody has ordered, what is holding an order: order_cover (with the order, customer or item \
when the question names one). Undelivered value is not a stock shortage until order_cover \
says nothing covers it.
8. Who is on leave, who is away this week, leave waiting for approval, or how many days \
someone has left: leave (with the person's name or ID for one person). Who someone is, \
who they report to, who is in a department: people. Do not rebuild a leave balance from \
erpnext_list rows -- the leave tool already counts it as ERPNext does.
9. Profit (gross or net), margins, revenue for a period as the accounts state it, assets, \
liabilities, equity, cash and bank, working capital and the trial balance: ERPNext's own \
statements, through run_report -- "Profit and Loss Statement", "Balance Sheet", "Cash Flow" \
(filters company, filter_based_on Date Range, period_start_date, period_end_date, \
from_fiscal_year and to_fiscal_year, periodicity) and "Trial Balance" (company, fiscal_year, \
from_date, to_date). Never rebuild a statement from invoices or the loaded sets: the \
statements carry the business's own accounting -- opening entries, journals, finance books. \
Gross profit is income less the accounts of type Cost of Goods Sold (count a cost-of-sales \
group once, not its children again); net profit is the report's profit line. Read the \
period columns: on the balance sheet the last period column is the position, and its \
"total" column adds periods together and means nothing; on a cash flow, add the period \
columns. If the balance sheet does not balance, or the trial balance's debits and credits \
differ, say so with the difference. These are the same statements the Finances screen \
shows under Financial Statements.
Put independent lookups in the same round. Most questions need one or two rounds; once \
you can answer, stop looking and answer.
The loaded sets count submitted documents only, as the screens do. For drafts or \
cancelled documents, filter src_docstatus yourself (0 draft, 2 cancelled).

HOW TO WORK
- Look before you answer a question about the business: every figure you give comes \
from a lookup. A greeting, thanks or small talk needs no lookup -- reply naturally and \
briefly, as a colleague would, and offer a question or two you could answer.
- Check your totals before you answer. A table's total, or a count beside a defined \
figure, must equal that figure: the customers behind the amount owed are the ledger \
balances with something owed (ar_owing_count), and the invoices behind the open-invoice \
figure are the unpaid ones (ar_count), not every invoice. If they differ, your query is missing one of the \
figure's rules -- fix it and look again rather than print both.
- Never show a field, column, table or tool name (base_discount_amount, src_docstatus, \
fact_sales_invoice, query_data). Say what it means in plain words.
- Money owed -- by customers to us, or by us to suppliers -- is the ledger balance: the \
figures ar_total and ap_total, and per customer or supplier the owed column of the ledger \
balances data set (party_type Customer or Supplier). Never total open invoices for "how \
much are we owed" or "how much do we owe": where payments are not matched to invoices the \
invoices overstate it. Give the open invoices' figure beside it (ar_open_invoices, \
ap_open_invoices) with the reason for any difference, in the data set's own terms -- \
payments received or made but not matched, payments and credit notes the invoices do not \
show, journal entries and credit notes not linked, amounts owed on no invoice, and any \
remainder the records do not explain. Ageing ("overdue", "over 90 days") is the ledger \
balances' matched ageing. A party in credit owes nothing: say they are in credit.
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
3. When a picture says it faster, add a chart block. Choose the type by the question \
the reader is asking, not for variety; when two charts would show the same thing, use \
one. The reader can switch a chart to another view or a table, so pick the clearest:
- bar: compare up to twelve short names, largest first.
- hbar: a ranking where the names are long (customers, suppliers, items) -- up to \
twelve, one series; it is drawn largest first with each rank numbered.
- line: change over time, one to three series, up to 36 points. area: the same for one \
to three series where the size under the line matters (cash, sales). stacked_area: up \
to four parts of a total over time, no negatives.
- pie or donut: shares of ONE whole, at most seven parts, none negative (beyond seven \
the smallest are combined as Other). Never for a top-ten of a larger whole, for \
changes, or to compare two wholes. rose: the same, when the parts differ a lot.
- stacked: what a total is made of, over months or across groups -- up to four series \
that add up to the total, up to 24 labels; no negative values. percentage: the same \
drawn as 100% columns, when the mix matters more than the size (up to six series).
- grouped: two to four series side by side for each label, e.g. this year against \
last year by branch -- up to twelve labels.
- combo: an amount with a rate, e.g. sales with gross margin % -- exactly two series: \
the first drawn as bars in "unit", the second as a line in "unit2", up to 24 labels.
- waterfall: a bridge from one level to another, e.g. opening cash, receipts, \
payments, closing cash -- one series; "totals" lists the indexes of the levels \
(default: the first and the last), every other value is a movement (+ or -). Each \
level must equal the one before plus the movements between, or it is not drawn.
- funnel: drop-off through stages in order, e.g. enquiries, quotations, orders, \
invoices -- one series of counts, up to eight stages.
- gauge: ONE ratio against its target, e.g. "collected inside 90 days" -- not labels \
and series but "value", optional "target", "min" (default 0) and "max" (default 100 \
when unit is "%", otherwise required), "label", and "better": "lower" when lower is \
good.
- heatmap: one measure across two categories, e.g. month by product group, weekday \
by hour -- labels are the columns, each series is one row (its name is the row), up \
to 31 columns and 24 rows.
- treemap: how a whole breaks down in two levels, e.g. spend by supplier then item \
group -- "items": [{{"name", "value", "children": [{{"name", "value"}}]}}]; a parent's \
value may be left out, and its children may not add up to more than it.
- radar: three to ten dimensions of one thing on one scale, e.g. the business health \
ratios, one to four series; values from zero, "max" optional (100 for "%").
- scatter: two measures for each name, e.g. sales against days overdue by customer -- \
exactly two series: the first is across in "unit", the second up in "unit2"; one \
label per dot, up to 40. bubble: the same with a third series (in "unit3") as the \
size of each dot, none negative.
```chart
{{"type": "bar", "title": "Spend by supplier, last 12 months", "unit": "GHS", \
"labels": ["A", "B"], "series": [{{"name": "Spend", "values": [1200.5, 900]}}]}}
```
```chart
{{"type": "combo", "title": "Sales and gross margin by month", "unit": "GHS", \
"unit2": "%", "labels": ["Jan", "Feb"], "series": [{{"name": "Sales", "values": \
[120000, 98000]}}, {{"name": "Gross margin", "values": [31.5, 28]}}]}}
```
```chart
{{"type": "waterfall", "title": "Cash, opening to closing", "unit": "GHS", "labels": \
["Opening", "Receipts", "Payments", "Closing"], "series": [{{"name": "Cash", "values": \
[410000, 1250000, -1100000, 560000]}}]}}
```
```chart
{{"type": "gauge", "title": "Owed that is inside 90 days", "unit": "%", "value": 26.2, \
"target": 80, "label": "of all money owed"}}
```
Values are plain numbers, not text. Every series has exactly one value per label, \
in the label order; a block that breaks these rules is not drawn at all. Every axis \
starts at zero, so do not pick a type to make a small change look large. Use at most \
two charts; skip them for one-number answers.
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
