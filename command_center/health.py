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
    transient = control["state"] in PASSING or any(
        e["state"] in PASSING for e in questions.values())
    name = _name(code, day)
    have = frappe.get_all(DOCTYPE, filters={"name": name},
                          fields=["name", "control_score", "questions"], limit=1)
    body = json.dumps(questions, sort_keys=True)
    now = frappe.utils.now_datetime()
    if have:
        old = have[0]
        if transient:
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


def delta(series: list) -> int | None:
    """This week's Control Health against last week's, in whole points, from what was
    stored; None unless both weeks have a score."""
    if len(series) < 2:
        return None
    now, before = series[-1].get("control_score"), series[-2].get("control_score")
    if now is None or before is None:
        return None
    return round(now) - round(before)


def history(code, today=None) -> dict:
    series = weeks(code, today=today)
    last = series[-2] if len(series) > 1 else None
    return {
        "business_code": code,
        "kept": _concrete(code),
        "weeks": series,
        "last_week": ({"week": last["week"], "day": last["day"],
                       "control_score": last["control_score"]}
                      if last and last["control_score"] is not None else None),
        "delta": delta(series),
        "watch": WATCH,
    }


# --------------------------------------------------------------------------- scheduled
def record_all():
    """Daily: today's snapshot for every loaded business, worked out as the screen does."""
    from command_center.api.businesses import loaded_codes
    from command_center.api.kpi import figures
    keys = [k for k, _q in QUESTIONS] + [CONTROL]
    for code in loaded_codes():
        try:
            snapshot(code, annotate(figures(keys, code)))
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
