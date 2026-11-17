"""Business Health's history, and what each of its findings was counted from.

The six questions and Control Health are worked out by the KPI engine and the live reads
(kpi/sales.py, kpi/stock.py, kpi/live_governance.py), exactly as before. This module only
remembers them and says where they came from:

    parts(keys)               the engine figures a question's "counted from" needs
    annotate(figures)         adds `counted_from` to each question's figure: the records it
                              was counted from, with the count the figure itself carries
                              (its denominator), or, where there is no count, what it was
                              read from -- never a number made up
    snapshot(code, figures)   today's Control Health and each question's score and state,
                              one row per business per day (Command Center Health
                              Snapshot); the latest complete read of the day wins
    weeks(code)               the last eight ISO weeks, the last snapshot in each; a week
                              with none is empty, never filled in
    week_on_week(code)        the latest snapshot against the one nearest seven days before
                              it (5 to 9 days), over the questions scored in both
    record_vitals(code, figs) the Executive Summary's vital signs on the day -- what is owed
                              to us, what we owe, the stock held -- on the same row
                              (`vitals`), so the summary can say what changed on last week
    week_ago(code)            each vital sign as stored about seven days ago (5 to 9 days),
                              the reading nearest seven; nothing when none was kept
    record_all()              daily: a snapshot for every loaded business, so a day nobody
                              looked still has one
    prune(days)               nightly (insights/core/maintenance.py): about 400 days kept

Nothing here is estimated: every value stored is one the screen showed.
"""

from __future__ import annotations

import datetime as _dt
import json

import frappe

from command_center.kpi.live_governance import QUESTIONS, WATCH

DOCTYPE = "Command Center Health Snapshot"
KEEP_DAYS = 400
WEEKS = 8
CONTROL = "control_score"
# A read that failed, or found the business's ERPNext away, says nothing about the
# business: it never replaces an earlier read of the same day.
PASSING = ("unreachable", "failed")
PARTIAL = PASSING + ("not_loaded",)
# The Executive Summary's vital signs kept daily (summary.py): the positions that exist only
# now. Money in has its own months and Overall Business Health its own history above.
VITALS = ("ar_total", "ap_total", "stock_value")
# A vital sign is kept only when the screen showed a figure for it.
NOT_SHOWN = PASSING + ("no_access", "not_loaded", "needs_setup")
WEEK_AGO = (5, 9)         # "about seven days ago": the stored reading nearest seven, in this range

# What each question was counted from: the figure that carries its count (an engine
# denominator, or the live read's own `counted`), the words for one and for many, and what
# it was read from when there is no count to give.
COUNTED = {
    "score_deliver": ("stock_lines_promised", "promised stock line", "promised stock lines",
                      "the stock balance and the sales orders"),
    "score_paid": (None, None, None, "what customers owe by the ledger"),
    "score_paperwork": ("invoices_written", "sales invoice written", "sales invoices written",
                        "the sales invoices"),
    "score_approvals": ("counted", "approved purchase order or payment",
                        "approved purchase orders and payments",
                        "the approval history of purchase orders and payments"),
    "score_records": ("counted", "invoice or stock line", "invoice and stock lines",
                      "the invoice lines and the stock balance"),
    "score_access": ("counted", "active user account", "active user accounts",
                     "the user accounts and their roles"),
}


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _concrete(code) -> bool:
    return bool(code) and code != "__all__"


# --------------------------------------------------------------------------- counted from
def parts(keys) -> set:
    """The engine figures the questions asked for need for their counts."""
    out = set()
    for key in keys or ():
        src = COUNTED.get(key, (None,))[0]
        if src and src != "counted":
            out.add(src)
    return out


def counted_from(key: str, figure: dict | None, figures: dict | None = None) -> str | None:
    """"counted from 60 promised stock lines in ERPNext": the count is the one the figure
    itself was divided by. Without one -- nothing to divide by, the read refused or not
    answered, or a figure that is an amount rather than a count -- what it was read from,
    and no number."""
    spec = COUNTED.get(key)
    if not spec:
        return None
    src, one, many, source = spec
    n = None
    if figure is not None and figure.get("value") is not None and src:
        n = _num(figure.get("counted")) if src == "counted" else _num(
            ((figures or {}).get(src) or {}).get("value"))
    if n is not None and n > 0 and float(n).is_integer():
        n = int(n)
        return f"counted from {n:,} {one if n == 1 else many} in ERPNext"
    return f"read from {source} in ERPNext"


def annotate(figures: dict) -> dict:
    """Each question's figure gains `counted_from` (in place)."""
    for key, _q in QUESTIONS:
        f = figures.get(key)
        if isinstance(f, dict):
            f["counted_from"] = counted_from(key, f, figures)
    return figures


# --------------------------------------------------------------------------- snapshot
def _entry(figure: dict | None) -> dict:
    value = _num((figure or {}).get("value"))
    state = ((figure or {}).get("data_status") or {}).get("state")
    if not state:
        state = "live" if value is not None else "failed"
    return {"value": None if value is None else round(value, 4), "state": state}


def _name(code, day) -> str:
    return f"{code}::{day}"


def snapshot(code, figures: dict, today=None) -> bool:
    """Today's Business Health for one business, as the screen just worked it out.

    One row per business per day, named "<business>::<day>" so there can never be two.
    The latest complete read of the day replaces the earlier one; a read in which a
    question failed or found ERPNext away does not replace a day already stored.
    Returns whether anything was written."""
    if not _concrete(code) or not isinstance((figures or {}).get(CONTROL), dict):
        return False
    day = frappe.utils.getdate(today or frappe.utils.today())
    questions = {key: _entry(figures.get(key)) for key, _q in QUESTIONS if key in figures}
    control = _entry(figures.get(CONTROL))
    # A read in which a question could not be read this time (ERPNext away, a failure,
    # the facts still loading) is partial: it never replaces the day's fuller read. A
    # question that needs setting up, or that ERPNext refuses, is a real state and does.
    transient = control["state"] in PARTIAL or any(
        e["state"] in PARTIAL for e in questions.values())
    name = _name(code, day)
    have = frappe.get_all(DOCTYPE, filters={"name": name},
                          fields=["name", "control_score", "questions"], limit=1)
    body = json.dumps(questions, sort_keys=True)
    now = frappe.utils.now_datetime()
    if have:
        old = have[0]
        # A row holding only the day's vital signs has no Business Health to protect yet.
        if transient and old.questions:
            return False
        if _num(old.control_score) == control["value"] and (old.questions or "") == body:
            return False

        frappe.db.set_value(DOCTYPE, name, {"control_score": control["value"],
                                            "questions": body, "captured_at": now})
        return True
    frappe.db.bulk_insert(DOCTYPE, ["name", "business_code", "day", "control_score",
                                    "questions", "captured_at"],
                          [(name, code, day, control["value"], body, now)],
                          ignore_duplicates=True)
    return True


def observe(code, figures: dict) -> None:
    """snapshot(), from a screen's read: a snapshot that cannot be kept is recorded and
    never fails the figures it was taken from."""
    # Only a read of the whole of Business Health: a screen showing Control Health alone
    # (a card elsewhere) must not replace the day's questions with nothing.
    if any(k not in (figures or {}) for k in [CONTROL] + [q for q, _ in QUESTIONS]):
        return
    try:
        snapshot(code, figures)
    except Exception:
        frappe.log_error(title="Business Health: snapshot not kept",
                         message=frappe.get_traceback())


# --------------------------------------------------------------------------- vital signs
def record_vitals(code, figures: dict, today=None) -> bool:
    """Today's vital signs for one business, on its day's row (made if the day has none
    yet). Only a figure the screen showed is kept; one not read, refused or away leaves the
    day's earlier reading of it as it was. Returns whether anything was written."""
    if not _concrete(code):
        return False
    got = {}
    for key in VITALS:
        f = (figures or {}).get(key)
        if not isinstance(f, dict):
            continue
        e = _entry(f)
        if e["value"] is None or e["state"] in NOT_SHOWN:
            continue
        got[key] = e
    if not got:
        return False
    day = frappe.utils.getdate(today or frappe.utils.today())
    name = _name(code, day)
    have = frappe.get_all(DOCTYPE, filters={"name": name}, fields=["name", "vitals"], limit=1)
    if have:
        try:
            kept = json.loads(have[0].vitals) if have[0].vitals else {}
        except ValueError:
            kept = {}
        merged = {**kept, **got}
        if merged == kept:
            return False
        frappe.db.set_value(DOCTYPE, name, "vitals", json.dumps(merged, sort_keys=True))
        return True
    frappe.db.bulk_insert(DOCTYPE, ["name", "business_code", "day", "control_score", "questions",
                                    "vitals", "captured_at"],
                          [(name, code, day, None, None, json.dumps(got, sort_keys=True),
                            frappe.utils.now_datetime())],
                          ignore_duplicates=True)
    return True


def observe_vitals(code, figures: dict) -> None:
    """record_vitals(), from a screen's read: never fails the figures it was taken from."""
    if not any(k in (figures or {}) for k in VITALS):
        return
    try:
        record_vitals(code, figures)
    except Exception:
        frappe.log_error(title="Executive Summary: vital signs not kept",
                         message=frappe.get_traceback())


def week_ago(code, today=None) -> dict:
    """{"readings": {key: {"value", "day"}}, "older": bool}: each vital sign as stored
    about a week ago -- the reading nearest seven days back, between five and nine -- and
    whether anything older than that is kept (so "no reading last week" is told apart from
    "not kept long enough yet"). Nothing is filled in."""
    out = {"readings": {}, "older": False}
    if not _concrete(code):
        return out
    today = frappe.utils.getdate(today or frappe.utils.today())
    lo, hi = WEEK_AGO
    rows = frappe.get_all(DOCTYPE, filters={"business_code": code,
                                            "day": ["<=", today - _dt.timedelta(days=lo)]},
                          fields=["day", "vitals"], order_by="day desc", limit=60)
    best = {}
    for r in rows:
        if not r.vitals:
            continue
        d = frappe.utils.getdate(r.day)
        age = (today - d).days
        if age > hi:
            out["older"] = True
            continue
        try:
            vit = json.loads(r.vitals)
        except ValueError:
            continue
        for key, e in vit.items():
            if key not in VITALS or not isinstance(e, dict) or e.get("value") is None:
                continue
            # nearest to seven days; between two as near, the older (a full week)
            rank = (abs(age - 7), -age)
            if key not in best or rank < best[key][0]:
                best[key] = (rank, {"value": float(e["value"]), "day": str(d)})
    out["readings"] = {k: v for k, (_r, v) in best.items()}
    return out


# --------------------------------------------------------------------------- history
def _monday(day):
    return day - _dt.timedelta(days=day.weekday())


def weeks(code, n: int = WEEKS, today=None) -> list:
    """The last `n` ISO weeks, oldest first, each the last snapshot taken in it:
    {week, start, day, control_score, questions}. A week with no snapshot has day None and
    nothing else: it is shown empty, never filled in."""
    today = frappe.utils.getdate(today or frappe.utils.today())
    first = _monday(today) - _dt.timedelta(weeks=n - 1)
    rows = (frappe.get_all(DOCTYPE, filters={"business_code": code, "day": [">=", first]},
                           fields=["day", "control_score", "questions"], order_by="day asc",
                           limit=n * 7 + 7) if _concrete(code) else [])
    last = {}
    for r in rows:
        d = frappe.utils.getdate(r.day)
        # A day with only the Executive Summary's vital signs has no Business Health.
        if not r.questions:
            continue
        if d <= today:
            last[d.isocalendar()[:2]] = r     # ascending, so the week's last one stays
    out = []
    for i in range(n):
        start = first + _dt.timedelta(weeks=i)
        year, week = start.isocalendar()[:2]
        r = last.get((year, week))
        try:
            qs = json.loads(r.questions) if r and r.questions else {}
        except ValueError:
            qs = {}
        out.append({"week": f"{year}-W{week:02d}", "start": str(start),
                    "day": str(frappe.utils.getdate(r.day)) if r else None,
                    "control_score": _num(r.control_score) if r else None,
                    "questions": qs})
    return out


def _scores(questions) -> dict:
    """{question: value} for the questions a snapshot scored."""
    try:
        qs = json.loads(questions) if isinstance(questions, str) else (questions or {})
    except ValueError:
        return {}
    return {k: float(e["value"]) for k, e in qs.items()
            if isinstance(e, dict) and e.get("value") is not None}


def compare(now: dict, before: dict) -> dict | None:
    """Overall Business Health now against before, over the questions scored both times:
    {"delta" (whole points), "now", "before" (each the average of those questions),
    "questions" (how many), "of"}. A question that entered or left between the two is
    not a change in the business, so it moves nothing. None when none is common."""
    common = sorted(set(now) & set(before))
    if not common:
        return None
    a = sum(now[k] for k in common) / len(common)
    b = sum(before[k] for k in common) / len(common)
    return {"delta": round(a - b), "now": round(a, 4), "before": round(b, 4),
            "questions": len(common), "of": len(QUESTIONS)}


def week_on_week(code, today=None) -> dict | None:
    """The latest snapshot against the one nearest seven days before it (five to nine
    days, as the vital signs are: health.week_ago), over the questions scored in both.

    Not this ISO week's last snapshot against last week's: on a Monday that compared
    Monday with Sunday, one day apart (17 Nov 2026). None when there is no snapshot five
    to nine days before the latest."""
    if not _concrete(code):
        return None
    today = frappe.utils.getdate(today or frappe.utils.today())
    lo, hi = WEEK_AGO
    rows = [r for r in frappe.get_all(
        DOCTYPE, filters={"business_code": code, "day": [">=", today - _dt.timedelta(days=hi + 7)],
                          "questions": ["is", "set"]},
        fields=["day", "control_score", "questions"], order_by="day desc", limit=40)
        if r.questions and frappe.utils.getdate(r.day) <= today]
    if not rows:
        return None
    latest = rows[0]
    day = frappe.utils.getdate(latest.day)
    best = None
    for r in rows[1:]:
        age = (day - frappe.utils.getdate(r.day)).days
        if lo <= age <= hi:
            rank = (abs(age - 7), -age)
            if best is None or rank < best[0]:
                best = (rank, r)
    if not best:
        return None
    got = compare(_scores(latest.questions), _scores(best[1].questions))
    if not got:
        return None
    base = best[1]
    return {**got, "day": str(day), "base_day": str(frappe.utils.getdate(base.day)),
            "base_control_score": _num(base.control_score)}


def history(code, today=None) -> dict:
    series = weeks(code, today=today)
    wow = week_on_week(code, today=today)
    return {
        "business_code": code,
        "kept": _concrete(code),
        "weeks": series,
        # The reading compared with, about a week before the latest: its day and its
        # score over the questions scored both times (what the delta is measured from).
        "last_week": ({"week": "{}-W{:02d}".format(*frappe.utils.getdate(
                           wow["base_day"]).isocalendar()[:2]),
                       "day": wow["base_day"], "control_score": wow["before"]}
                      if wow else None),
        "delta": wow["delta"] if wow else None,
        # How many questions the change is over, of how many: said beside it when fewer
        # than every question scored now.
        "delta_questions": ({"questions": wow["questions"], "of": wow["of"]} if wow else None),
        "watch": WATCH,
    }


# --------------------------------------------------------------------------- scheduled
def record_all():
    """Daily: today's snapshot and vital signs for every loaded business, worked out as
    the screens do."""
    from command_center.api.businesses import loaded_codes
    from command_center.api.kpi import figures
    keys = [k for k, _q in QUESTIONS] + [CONTROL] + list(VITALS)
    for code in loaded_codes():
        try:
            figs = annotate(figures(keys, code))
            snapshot(code, figs)
            record_vitals(code, figs)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Business Health: daily snapshot failed",
                             message=frappe.get_traceback())


def prune(days: int = KEEP_DAYS) -> int:
    """Snapshots older than `days` (default 400) are dropped."""
    cutoff = frappe.utils.getdate(frappe.utils.today()) - _dt.timedelta(days=int(days))
    old = frappe.get_all(DOCTYPE, filters={"day": ["<", cutoff]}, pluck="name", limit=100000)
    if old:
        frappe.db.delete(DOCTYPE, {"name": ["in", old]})
        frappe.db.commit()
    return len(old)
