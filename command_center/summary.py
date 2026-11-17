"""The Executive Summary's memo (16 Nov 2026, the approved mockup-exec-summary.html).

A board memo with vital signs, at the top of the Executive Summary. Everything that was
on the screen stays below it, unchanged: the recommendations with their actions, What
Worked, the alerts, the PDF and Excel buttons. The memo reads what those already read;
nothing here decides what a figure means.

    memo(code)        the header, the five vital signs and their changes, the short
                      version, the three decisions, the risks and what is going well
    waiting(code)     Waiting On You: three counts from api/work.summary, or why they
                      cannot be read (the person's own ERPNext key is not linked)
    write(code)       today's short version by the AI, when it is not written yet
    write_all()       06:45 (hooks.scheduler_events): the same for every loaded business

The vital signs are the figures the cards show, with the same drawers:
    Money In          cash_in_month, against the month before (ask/tools.compare_periods,
                      the figure's own queries: the change is shown only when its current
                      side is the very figure shown)
    Owed to Us        ar_total     } against the reading kept about a week ago
    We Owe            ap_total     } (health.record_vitals / week_ago); "Change from next
    Stock Held        stock_value  } week" until one is
    Overall Business  control_score, against last week (health.history's delta)
      Health
A change is never worked out from anything else, and never filled in.

The short version is one paragraph. The AI writes it once a day per business -- at 06:45,
or when the screen is opened and today's is not written -- from what the memo shows
(given()), through ask/claude.complete, as the Daily Brief and the daily AI review do.
Every number in it must be one of those it was given, as written or rounded
(recommend/numbers.py); one that is not, a reply that is not one short
paragraph, an AI that is off, not set up, paused by the licence or out of reach -- each
leaves the deterministic paragraph built from the same figures (fallback()), which is
also what the screen shows while the AI writes, so the page never waits on it. Kept per
business per day (frappe.defaults, SUMMARY_PARENT); read again, it is checked against
the figures of the moment, and one they no longer bear out is not shown.

Metering: one request, through metering.event("ai_review", ..., count=False) -- the
daily AI review's meter, so its tokens and estimated cost are on the usage ledger with
the review's, under the note "Executive Summary", but it is not counted as a review,
nor as anyone's question or report. Gated as the review is (metering.gate).

Reads only, apart from the paragraph kept here and the vital signs kept by health.py.
Nothing is written to any business's ERPNext.
"""

from __future__ import annotations

import datetime as _dt
import json
import re

import frappe
from frappe.utils import getdate, now_datetime, today

from command_center import health
from command_center.kpi.live_governance import HEALTHY, QUESTIONS

SUMMARY_PARENT = "__cc_exec_summary"
METER = "ai_review"                  # the daily AI review's meter (recommend/review.py)
NOTE = "Executive Summary"
TOP_DECISIONS = 3
TOP_RISKS = 3
MAX_ATTEMPTS = 3                     # AI attempts a business a day, at most
RETRY_MINUTES = 60                   # between a failed attempt and the next
MAX_WORDS = 130
LOCK = "cc:summary:writing:{}"

VITALS = (("cash_in_month", "Money In"),
          ("ar_total", "Owed to Us"),
          ("ap_total", "We Owe"),
          ("stock_value", "Stock Held"),
          (health.CONTROL, "Overall Business Health"))
QUESTION_KEYS = tuple(k for k, _q in QUESTIONS)
FIGURE_KEYS = tuple(k for k, _l in VITALS) + QUESTION_KEYS
SEVERITY_WORDS = {"crit": "Critical", "high": "High", "med": "Medium", "info": "For information"}
NOTHING_WELL = "Nothing to report as going well yet"


def _concrete(code) -> bool:
    return bool(code) and code != "__all__"


def _short(value, currency) -> str:
    from command_center.ask.quick import _short as short
    return short({"value": value, "unit": "currency", "currency": currency})


def _exact(value, currency) -> str:
    return f"{currency or ''} {float(value):,.0f}".strip()


def _state(f) -> str | None:
    return ((f or {}).get("data_status") or {}).get("state")


def _shown(f) -> bool:
    return isinstance(f, dict) and f.get("value") is not None and _state(f) not in health.NOT_SHOWN


def _arrow(d) -> str:
    return "up" if d > 0 else "down" if d < 0 else "flat"


# --------------------------------------------------------------------------- the changes
def money_change(code, fig) -> dict | None:
    """Money in against the month before, from the figure's own queries -- only when the
    current side is the very figure shown (same month, same amount)."""
    if not _shown(fig) or not (fig.get("period") or {}).get("label"):
        return None
    from command_center.ask import tools
    try:
        c = tools.compare_periods(figure="cash_in_month", compare="month_vs_previous",
                                  business_code=code)
    except tools.ToolError:
        return None
    now, then = c.get("current") or {}, c.get("earlier") or {}
    if (now.get("period") != fig["period"]["label"] or now.get("value") is None
            or abs(float(now["value"]) - float(fig["value"])) > 0.5):
        return None
    pct = c.get("change_pct")
    if pct is None:
        return None
    month = (then.get("period") or "").split(" ")[0]
    d = _arrow(pct)
    word = {"up": "▲", "down": "▼"}.get(d)
    text = (f"{word} {abs(pct):.0f}% on {month[:3]}" if word and round(abs(pct)) else
            f"No change on {month[:3]}")
    return {"kind": "month", "dir": d, "pct": pct, "against": then.get("period"),
            "against_value": then.get("value"), "text": text}


def week_change(code, key, fig, ago: dict) -> dict | None:
    """Against the reading kept about a week ago (health.week_ago)."""
    if not _shown(fig):
        return None
    if not _concrete(code):
        return {"kind": "pending", "text": "Week on week is kept for each business"}
    got = ago["readings"].get(key)
    if not got:
        return {"kind": "pending",
                "text": "No reading kept from last week" if ago.get("older") else "Change from next week"}
    delta = round(float(fig["value"]) - got["value"], 2)
    d = _arrow(delta)
    cur = fig.get("currency") or ""
    text = ("No change on last week" if d == "flat" else
            f"{'▲' if d == 'up' else '▼'} {_short(abs(delta), cur)} on last week")
    return {"kind": "week", "dir": d, "amount": abs(delta), "base_day": got["day"],
            "base_value": got["value"], "text": text}


def health_change(code, fig, hist: dict) -> dict | None:
    """Overall Business Health against last week, in whole points (health.history)."""
    if not _shown(fig):
        return None
    if not hist.get("kept"):
        return {"kind": "pending", "text": "Week on week is kept for each business"}
    d = hist.get("delta")
    if d is None:
        return {"kind": "pending", "text": "Change from next week"}
    text = ("No change on last week" if d == 0 else
            f"{'▲' if d > 0 else '▼'} {abs(d)} on last week")
    # Measured over the questions scored both times (health.week_on_week): said when that
    # is not every question.
    over = hist.get("delta_questions") or {}
    if over and over.get("questions") and over["questions"] < over.get("of", 0):
        text += f", on the {over['questions']} questions scored both times"
    return {"kind": "week", "dir": _arrow(d), "points": abs(d),
            "base_day": (hist.get("last_week") or {}).get("day"), "text": text}


def vitals(code, figs: dict, hist: dict, ago: dict | None = None) -> list:
    """The five vital signs: the figure (as the cards have it, for its drawer), its label
    and its change, or none."""
    ago = ago if ago is not None else health.week_ago(code)
    out = []
    for key, label in VITALS:
        f = figs.get(key)
        if key == "cash_in_month":
            month = ((f or {}).get("period") or {}).get("label") or ""
            label = f"{label}, {month.split(' ')[0][:3]}" if month else f"{label}, Last Full Month"
            change = money_change(code, f)
        elif key == health.CONTROL:
            change = health_change(code, f, hist)
        else:
            change = week_change(code, key, f, ago)
        if change and change.get("kind") in ("month", "week"):
            change["tone"] = _tone(change["dir"], key, f)
        out.append({"key": key, "label": label, "figure": f, "shown": _shown(f),
                    "change": change})
    return out


def _tone(d, key, fig) -> str:
    """good, bad or flat: a rise in what customers owe is not good news, a rise in the
    health score is (its live figure carries no direction of its own)."""
    direction = "higher_is_better" if key == health.CONTROL else (fig or {}).get("direction")
    if d == "flat" or direction not in ("higher_is_better", "higher_is_worse"):
        return "flat"
    return "good" if (d == "up") == (direction == "higher_is_better") else "bad"


# --------------------------------------------------------------------------- the lists
def decisions(code) -> list:
    """The top three open recommendations, in the order of the list below them (the same
    call: api/recommend.current), each with its owner."""
    from command_center.api import recommend
    recs = recommend.current(code).get("recommendations") or []
    return [{"name": r.get("name"), "title": r.get("title"), "owner": r.get("owner_role"),
             "area": r.get("area_label"), "severity": r.get("severity"),
             "money": r.get("money_at_stake") or 0, "currency": r.get("currency") or ""}
            for r in recs[:TOP_DECISIONS]]


def risks(code) -> list:
    """The top open alerts, most severe first (the same call as the alerts below them)."""
    from command_center.api import alerts
    got = alerts.open_alerts(code).get("alerts") or []
    return [{"name": a.get("name"), "title": a.get("title"), "severity": a.get("severity"),
             "severity_word": SEVERITY_WORDS.get(a.get("severity"), a.get("severity") or ""),
             "owner": a.get("owner_label")}
            for a in got[:TOP_RISKS]]


def going_well(figs: dict, hist: dict) -> list:
    """Business Health questions scoring Healthy (80% and over), in their own notes'
    words, and Overall Business Health's rise on last week when it rose."""
    out = []
    for key, question in QUESTIONS:
        f = figs.get(key)
        if not _shown(f) or float(f["value"]) < HEALTHY:
            continue
        score = round(float(f["value"]))
        note = (f.get("note") or "").strip()
        out.append({"key": key, "question": question, "score": score,
                    "text": f"{score}% {note}".strip()})
    d = hist.get("delta")
    if d is not None and d > 0 and _shown(figs.get(health.CONTROL)):
        out.append({"key": health.CONTROL, "question": "Overall Business Health",
                    "text": f"Overall Business Health up {d} on last week"})
    return out


def waiting_counts(w: dict) -> dict:
    """api/work.summary's queue as Waiting On You's three counts, each with the screen it
    opens -- or, when it cannot be read as this person, the reason (the guide's words)."""
    if not w or not w.get("available"):
        return {"available": False, "unreachable": bool((w or {}).get("unreachable")),
                "reason": (w or {}).get("reason") or "Your approvals and tasks could not be read just now.",
                "items": []}
    items = (("approvals", len(w.get("approvals") or []), "Approvals Awaiting You", "approvals"),
             ("to_review", len(w.get("check") or []), "Delegated Tasks Done", "delegation"),
             ("overdue", len(w.get("late") or []), "Overdue Delegated Tasks", "delegation"))
    return {"available": True, "items": [{"key": k, "count": n, "label": label, "opens": view}
                                         for k, n, label, view in items]}


def waiting(code) -> dict:
    from command_center.api import work
    try:
        return waiting_counts(work.summary(code))
    except Exception:
        frappe.log_error(title="Executive Summary: Waiting On You not read",
                         message=frappe.get_traceback())
        return waiting_counts({})


# --------------------------------------------------------------------------- the header
def _names(code):
    if _concrete(code):
        name = frappe.db.get_value("Connected Business", {"business_code": code},
                                   "business_name") or code
        return name, [name]
    from command_center.api.businesses import loaded_codes
    names = [frappe.db.get_value("Connected Business", {"business_code": c}, "business_name") or c
             for c in loaded_codes()]
    return None, names


def header(code, figs: dict, user=None, now=None) -> dict:
    now = now or now_datetime()
    user = user or frappe.session.user
    person = frappe.utils.get_fullname(user) or user
    name, names = _names(code)
    # The oldest read among the vital signs shown: "read from ERPNext at 09:40" must hold
    # for every figure under it, so a stale one is never dated by a fresh one beside it
    # (17 Nov 2026: the newest was taken).
    vital = {k for k, _l in VITALS}
    reads = sorted(str((f.get("as_of") or {}).get("last_read") or "")[:16]
                   for k, f in figs.items() if k in vital and _shown(f)
                   and (f.get("as_of") or {}).get("last_read"))
    read = reads[0] if reads else None
    day = getdate(now)
    dateline = f"Week to {day.strftime('%A')} {day.day} {day.strftime('%B %Y')}"
    if read:
        at = read[11:16]
        on = getdate(read[:10])
        dateline += f" · read from ERPNext at {at}" + ("" if on == day else
                                                       f" on {on.day} {on.strftime('%b %Y')}")
    else:
        dateline += " · not read from ERPNext yet"
    if name:
        who = f"For {person}, {name}"
    else:
        n = len(names)
        who = f"For {person}, all {n} businesses together" if n != 1 else f"For {person}, all businesses ({names[0]})"
    return {"title": "Executive Summary", "dateline": dateline,
            "for": f"{who} · every figure counted from your own ERPNext records",
            "person": person, "business": name, "all_businesses": not name,
            "businesses": names, "read_at": read, "week_to": str(day)}


# --------------------------------------------------------------------------- the paragraph
SYSTEM = """You write "the short version" at the top of a chief executive's weekly \
board memo: one paragraph that says what the week's figures mean for the business, from \
the figures, decisions and risks given below and nothing else. The reader is busy and is \
not an accountant.

Write one paragraph of three or four sentences, no more than about 90 words: what the \
vital signs say together, then what most needs deciding and the most serious risk.

Rules you must keep:
- Use only the numbers given below, written as they are given or as the same value \
rounded (GHS 7,254,533 may be written GHS 7.25M). Never add up, subtract, work out a \
percentage, estimate or introduce any other number, date or percentage.
- Name only customers, suppliers, products and documents that appear below.
- Formal, plain business English. No headings, no lists, no markdown, no greeting. Never \
name a field, a table or a tool."""


def given(head: dict, vit: list, decs: list, rsk: list, well: list) -> tuple:
    """(the text the AI is given, the same as data): every number in either is one the
    memo shows. The fallback paragraph and the check both use the data."""
    cur = next((v["figure"].get("currency") for v in vit
                if v["shown"] and v["figure"].get("currency")), "") or ""
    figures = []
    for v in vit:
        f = v["figure"]
        if not v["shown"]:
            continue
        if f.get("unit") == "currency":
            text = _exact(f["value"], f.get("currency") or cur)
        elif f.get("unit") == "percent":
            text = f"{round(float(f['value']))}%"
        else:
            text = f"{f['value']:,}"
        ch = v.get("change") or {}
        change = None
        if ch.get("kind") == "month":
            change = (f"{'up' if ch['dir'] == 'up' else 'down' if ch['dir'] == 'down' else 'unchanged'} "
                      f"{abs(ch['pct']):.0f}% on {ch['against']}" if ch["dir"] != "flat"
                      else f"unchanged on {ch['against']}")
        elif ch.get("kind") == "week" and "points" in ch:
            change = (f"{'up' if ch['dir'] == 'up' else 'down'} {ch['points']} points on last week"
                      if ch["dir"] != "flat" else "unchanged on last week")
        elif ch.get("kind") == "week":
            change = (f"{'up' if ch['dir'] == 'up' else 'down'} "
                      f"{_exact(ch['amount'], f.get('currency') or cur)} on last week"
                      if ch["dir"] != "flat" else "unchanged on last week")
        what = f.get("label") or v["label"]
        if f.get("period") and (f["period"] or {}).get("label"):
            what = f"{what} ({f['period']['label']})"
        figures.append({"key": v["key"], "label": v["label"], "what": what, "value": f["value"],
                        "text": text, "note": f.get("note") or "", "change": change})
    data = {"business": head.get("business") or "all businesses together",
            "week_to": head["dateline"].split(" · ")[0],
            "currency": cur, "figures": figures,
            "decisions": [{"title": d["title"], "owner": d.get("owner") or "",
                           "money": d.get("money") or 0,
                           "money_text": _exact(d["money"], d.get("currency") or cur) if d.get("money") else ""}
                          for d in decs],
            "risks": [{"title": r["title"], "severity": r["severity_word"]} for r in rsk],
            "going_well": [w["text"] for w in well]}
    lines = [f"Business: {data['business']}", data["week_to"], "", "VITAL SIGNS"]
    for x in figures:
        lines.append(f"- {x['what']}: {x['text']}" + (f", {x['note']}" if x["note"] else "")
                     + (f" ({x['change']})" if x["change"] else ""))
    lines += ["", "DECISIONS FOR THE CHIEF EXECUTIVE THIS WEEK, most important first"]
    for d in data["decisions"]:
        lines.append(f"- {d['title']} Owner: {d['owner'] or 'not named'}."
                     + (f" Money at stake: {d['money_text']}." if d["money_text"] else ""))
    if not data["decisions"]:
        lines.append("- None open.")
    lines += ["", "RISKS, most severe first"]
    for r in data["risks"]:
        lines.append(f"- {r['severity']}: {r['title']}")
    if not data["risks"]:
        lines.append("- None open.")
    if data["going_well"]:
        lines += ["", "GOING WELL"] + [f"- {t}" for t in data["going_well"]]
    return "\n".join(lines), data


def allowed(data: dict):
    """The figures the memo gave the AI, for the one check of an AI's numbers
    (recommend/numbers.py): each vital sign with its note and its change on one line (so
    "rose" is checked against the change beside it), the decisions, risks and what is
    going well -- the dateline and the periods as dates only, never as numbers."""
    from command_center.recommend import numbers
    g = numbers.Given().date(data.get("week_to"))
    for x in data.get("figures") or []:
        g.date(x.get("what"))
        g.text(f"{x.get('text') or ''}, {x.get('note') or ''}"
               + (f" ({x['change']})" if x.get("change") else ""))
    for d in data.get("decisions") or []:
        g.text(f"{d.get('title') or ''} {d.get('money_text') or ''}")
    for r in data.get("risks") or []:
        g.text(r.get("title"))
    for w in data.get("going_well") or []:
        g.text(w)
    return g


def check(paragraph: str, text: str, data: dict) -> str | None:
    """None when the paragraph may be shown; else why not. Every figure in it must be one
    of those it was given -- the same value with its unit, as written or rounded to what
    it shows, in the direction it was given (recommend/numbers.py)."""
    from command_center.recommend import numbers
    p = (paragraph or "").strip()
    if not p:
        return "It was empty."
    stray = numbers.problems(p, allowed(data))
    if stray:
        return f"It gave {', '.join(stray[:3])}, which is not among the figures it was given."
    if "\n" in p or re.search(r"(^|\s)(#|\*\*|- )", p):
        return "It was not one plain paragraph."
    if len(p.split()) > MAX_WORDS:
        return f"It ran to {len(p.split())} words."
    return None


def fallback(data: dict) -> str:
    """The short version worked out from the same figures, with no AI: what the screen
    shows while the AI writes, and whenever it cannot."""
    by = {x["key"]: x for x in data["figures"]}
    out = []
    m = by.get("cash_in_month")
    if m:
        period = m["what"].split("(")[-1].rstrip(")") if "(" in m["what"] else "the last full month"
        out.append(f"Money in came to {m['text']} in {period}" + (f", {m['change']}" if m["change"] else "")
                   + ".")
    pos = []
    if by.get("ar_total"):
        pos.append(f"customers owe {by['ar_total']['text']}")
    if by.get("ap_total"):
        pos.append(f"we owe suppliers {by['ap_total']['text']}")
    if pos:
        out.append(("On the Customer and Supplier Ledgers, " + " and ".join(pos)) + (
            f"; stock held is {by['stock_value']['text']} at cost." if by.get("stock_value") else "."))
    elif by.get("stock_value"):
        out.append(f"Stock held is {by['stock_value']['text']} at cost.")
    h = by.get(health.CONTROL)
    if h:
        out.append(f"Overall Business Health is {h['text']}" + (f", {h['change']}" if h["change"] else "")
                   + ".")
    if data["decisions"]:
        d = data["decisions"][0]
        out.append(f"First to decide: {d['title'].rstrip('.')}"
                   + (f" ({d['owner']})" if d["owner"] else "") + ".")
    if data["risks"]:
        r = data["risks"][0]
        out.append(f"The most serious risk: {r['title'].rstrip('.')} ({r['severity']}).")
    if not out:
        return "Not enough has been read from ERPNext yet to summarise the week."
    return " ".join(s[0].upper() + s[1:] for s in out)


# --------------------------------------------------------------------------- kept per day
def _get(code) -> dict:
    try:
        raw = (frappe.defaults.get_defaults_for(SUMMARY_PARENT) or {}).get(code)
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def _put(code, value: dict):
    frappe.defaults.set_default(code, json.dumps(value, default=str), parent=SUMMARY_PARENT)


def _today_state(code) -> dict:
    s = _get(code)
    return s if s.get("date") == str(today()) else {}


def _why_not(code, st: dict) -> str | None:
    """None if the AI may write today's paragraph now; else why not, in words."""
    from command_center import metering
    from command_center.ask import claude, llm
    if not _concrete(code):
        return "The AI writes it for one business at a time."
    if llm.provider() != "claude" or not claude.configured():
        return "The AI is not set up on this platform (Settings, Claude)."
    if (st.get("attempts") or 0) >= MAX_ATTEMPTS:
        return "The AI's version did not pass the figure check today."
    last = st.get("last_try")
    if last and (now_datetime() - frappe.utils.get_datetime(last)) < _dt.timedelta(minutes=RETRY_MINUTES):
        return st.get("error") or "The AI's version is not ready yet."
    blocked = metering.gate(METER, code)
    if blocked:
        return blocked
    return None


def short_version(code, text: str, data: dict) -> dict:
    """What the memo shows: today's AI paragraph when it is kept and still matches the
    figures, else the fallback -- with `pending` when the AI may write one now."""
    st = _today_state(code)
    if st.get("text") and not check(st["text"], text, data):
        return {"text": st["text"], "source": "ai", "model": st.get("model"), "at": st.get("at"),
                "pending": False}
    why = None if not st.get("text") else "The figures have changed since the AI wrote this morning's."
    blocked = _why_not(code, st)
    if blocked:
        why = why or blocked
    return {"text": fallback(data), "source": "fallback", "pending": not blocked,
            "why": why or (st.get("error") if st else None)}


def _compose(code, user=None) -> dict:
    from command_center.api.kpi import figures as read
    figs = read(list(FIGURE_KEYS), code)
    # The memo shows the whole of Business Health and the vital signs: keep today's reading.
    health.observe(code, figs)
    health.observe_vitals(code, figs)
    hist = health.history(code)
    vit = vitals(code, figs, hist)
    decs, rsk = decisions(code), risks(code)
    well = going_well(figs, hist)
    head = header(code, figs, user=user)
    text, data = given(head, vit, decs, rsk, well)
    return {"header": head, "vitals": vit, "decisions": decs, "risks": rsk,
            "going_well": well, "nothing_well": NOTHING_WELL, "_given": (text, data)}


def memo(code) -> dict:
    out = _compose(code)
    text, data = out.pop("_given")
    out["short"] = short_version(code, text, data)
    return out


def write(code, user=None) -> dict:
    """Today's short version by the AI, unless it is kept already or the AI may not write
    now: the paragraph to show, as short_version() says it."""
    out = _compose(code, user=user)
    text, data = out.pop("_given")
    shown = short_version(code, text, data)
    if not shown["pending"]:
        return shown
    cache = frappe.cache()
    lock = LOCK.format(code)
    if cache.get_value(lock):
        return shown            # another request is writing it; the screen asks again later
    cache.set_value(lock, 1, expires_in_sec=180)
    try:
        return _ask(code, text, data)
    finally:
        cache.delete_value(lock)


def _ask(code, text: str, data: dict) -> dict:
    from command_center import metering
    from command_center.ask import claude
    st = _today_state(code)
    st = {"date": str(today()), "attempts": (st.get("attempts") or 0) + 1,
          "last_try": str(now_datetime())[:19], "text": None, "error": None, "model": None}
    frappe.local.cc_claude_usage = None
    with metering.event(METER, code, note=NOTE, count=False) as ev:
        got, err = claude.complete(SYSTEM, text, kind="analyst", timeout=60, max_tokens=2000)
        bad = check(got, text, data) if got and not err else None
        ev["ok"] = bool(got and not err and not bad)
    st["model"] = claude.model_for("analyst")
    st["tokens"] = claude.usage()
    if err:
        st["error"] = "The AI could not be reached, so this version is worked out from the figures."
        frappe.log_error(title="Executive Summary: short version not written", message=str(err)[:2000])
    elif bad:
        st["error"] = "The AI's version did not pass the figure check, so this one is shown."
        frappe.log_error(title="Executive Summary: short version not used",
                         message=f"{bad}\n\n{got}")
    else:
        st["text"] = got.strip()
        st["at"] = str(now_datetime())[11:16]
    _put(code, st)
    if st["text"]:
        return {"text": st["text"], "source": "ai", "model": st["model"], "at": st["at"],
                "pending": False}
    return {"text": fallback(data), "source": "fallback", "pending": False, "why": st["error"]}


def write_all():
    """06:45, after the AI review and the Daily Brief: today's short version for every
    loaded business, so the first person to look in the morning finds it written."""
    from command_center.api.businesses import loaded_codes
    for code in loaded_codes():
        try:
            write(code)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Executive Summary: morning paragraph failed",
                             message=frappe.get_traceback())
