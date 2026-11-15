"""What a business's managers taught the recommendations, and whether the advice worked.

Every decision on a recommendation (engine.act: Done, Not Relevant, Snooze, Reopen) is
kept as a row of Command Center Recommendation Feedback. From them, per business and
rule:

  weight        how prominently the rule's recommendations rank, from 0.4 to 1.5:
                  Not Relevant            -0.15 each
                  Snoozed                 -0.05 each
                  Done                    +0.05 each
                  Done, and it improved   +0.15 more
                  Done, no change         -0.05
                  Done, and it got worse  -0.10
                each scaled by 0.5 ** (age in days / 30), so a decision counts half after a
                month and is ignored after HORIZON_DAYS. Explained in words.
  sensitivity   for a rule in adaptive mode, a factor of 1.0 to 1.5 on its learned
                threshold: +0.1 per (decayed) Not Relevant -- "managers say this is too
                sensitive" -- never past the rule's sanity cap (adaptive.py).

Outcomes. A Done keeps the recommendation's money at stake and its figure's value
(metrics.RULE_METRIC) at that moment, and a date to look again: REVIEW_DAYS (14) for a
daily figure, 30 for a monthly one. On that date (evaluate(), part of every refresh) the
same recommendation is looked for: gone, or at stake down by IMPROVED_SHARE or more, is
Improved; up by as much is Worse; otherwise No Change. Without a money figure, the
watched figure's own movement decides, in its bad direction. The outcome feeds the
weight above, and "What Worked" on the Executive Summary sums a month of them.
"""

from __future__ import annotations

import calendar
import datetime as _dt

import frappe

DOCTYPE = "Command Center Recommendation Feedback"
HALF_LIFE_DAYS = 30.0
HORIZON_DAYS = 120
W_MIN, W_MAX = 0.4, 1.5
S_MAX = 1.5
DELTA = {"Not Relevant": -0.15, "Snoozed": -0.05, "Done": 0.05}
OUTCOME_DELTA = {"Improved": 0.15, "No Change": -0.05, "Worse": -0.10}
REVIEW_DAYS = {"day": 14, "month": 30}
IMPROVED_SHARE = 0.10
ACTIONS = {"done": "Done", "not_relevant": "Not Relevant", "snooze": "Snoozed",
           "reopen": "Reopened"}


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _decay(age_days: float) -> float:
    return 0.5 ** (max(0.0, age_days) / HALF_LIFE_DAYS)


# --------------------------------------------------------------------------- recording
def record(doc, action: str, payload: dict):
    """Keep a manager's decision (engine.act). For Done: the figures to judge it by."""
    from command_center.recommend import metrics
    word = ACTIONS.get(action)
    if not word:
        return None
    now = frappe.utils.now_datetime()
    row = {"doctype": DOCTYPE, "business_code": doc.business_code, "recommendation": doc.name,
           "rec_key": doc.rec_key, "rule": doc.rule, "source": payload.get("source") or "rule",
           "action": word, "acted_by": frappe.session.user, "acted_on": now,
           "title": (doc.title or "")[:255]}
    if word == "Done":
        key = payload.get("metric") or metrics.RULE_METRIC.get(doc.rule)
        mt = metrics.BY_KEY.get(key) if key else None
        value = None
        if mt is not None:
            series = metrics.history(doc.business_code).get(mt.key) or []
            value = series[-1][1] if series else None
        days = REVIEW_DAYS[mt.grain] if mt else REVIEW_DAYS["day"]
        row.update(metric=mt.key if mt else None, value_at=value,
                   money_at=_num(doc.money_at_stake),
                   review_on=frappe.utils.add_days(frappe.utils.today(), days))
    return frappe.get_doc(row).insert(ignore_permissions=True)


def _rows(code, since_days=HORIZON_DAYS):
    since = frappe.utils.add_days(frappe.utils.now_datetime(), -since_days)
    return frappe.get_all(DOCTYPE, filters={"business_code": code, "acted_on": [">=", since]},
                          fields=["name", "rule", "action", "acted_on", "outcome", "outcome_on",
                                  "source"], limit=20000)


# --------------------------------------------------------------------------- weights
def weights(code, now=None, rows=None) -> dict:
    """{rule: {"weight", "sensitivity", "explain", "counts"}} for every rule with recent
    decisions. A rule with none is weight 1.0 and is not listed."""
    now = now or frappe.utils.now_datetime()
    rows = _rows(code) if rows is None else rows
    by = {}
    for r in rows:
        age = (now - frappe.utils.get_datetime(r.acted_on)).total_seconds() / 86400.0
        if age > HORIZON_DAYS:
            continue
        x = by.setdefault(r.rule, {"sum": 0.0, "nr": 0.0, "counts": {}, "recent": {},
                                   "outcomes": {}})
        f = _decay(age)
        x["sum"] += DELTA.get(r.action, 0.0) * f
        if r.action == "Not Relevant":
            x["nr"] += f
        x["counts"][r.action] = x["counts"].get(r.action, 0) + 1
        if age <= 30:
            x["recent"][r.action] = x["recent"].get(r.action, 0) + 1
        if r.action == "Done" and r.outcome in OUTCOME_DELTA:
            x["sum"] += OUTCOME_DELTA[r.outcome] * f
            x["outcomes"][r.outcome] = x["outcomes"].get(r.outcome, 0) + 1
    out = {}
    for rule, x in by.items():
        w = max(W_MIN, min(W_MAX, 1.0 + x["sum"]))
        s = max(1.0, min(S_MAX, 1.0 + 0.1 * x["nr"]))
        out[rule] = {"weight": round(w, 3), "sensitivity": round(s, 3),
                     "counts": x["counts"], "outcomes": x["outcomes"],
                     "explain": explain(w, x["recent"], x["counts"], x["outcomes"])}
    return out


def _times(n) -> str:
    return "once" if n == 1 else "twice" if n == 2 else f"{n} times"


def explain(w, recent, counts, outcomes) -> str:
    """Why a rule ranks where it does, in one or two plain sentences."""
    parts = []
    nr30 = recent.get("Not Relevant", 0)
    nr = counts.get("Not Relevant", 0)
    if nr30:
        parts.append(f"managers marked it Not Relevant {_times(nr30)} in the last 30 days")
    elif nr:
        parts.append(f"managers marked it Not Relevant {_times(nr)} in the last "
                     f"{HORIZON_DAYS} days (counting less as it ages)")
    sn = recent.get("Snoozed", 0)
    if sn:
        parts.append(f"it was snoozed {_times(sn)} in the last 30 days")
    done = counts.get("Done", 0)
    judged = sum(outcomes.values())
    if judged:
        better = outcomes.get("Improved", 0)
        parts.append(f"{better} of {judged} times it was done, the figure improved")
    elif done:
        parts.append(f"it was marked done {_times(done)}")
    if not parts:
        return "No recent decisions: ranked by money at stake and severity alone."
    text = "; ".join(parts)
    if w < 0.98:
        lead = "Shown less prominently because"
    elif w > 1.02:
        lead = "Ranked higher because"
    else:
        lead = "Ranked as usual:"
    return f"{lead} {text}."


def freshness(first_seen, now=None) -> float:
    """1.0 for a recommendation's first 14 days, easing to 0.85 by 90 days open: an
    old, unacted finding gives way a little to a new one of the same size."""
    if not first_seen:
        return 1.0
    now = now or frappe.utils.now_datetime()
    days = (now - frappe.utils.get_datetime(first_seen)).total_seconds() / 86400.0
    if days <= 14:
        return 1.0
    return round(max(0.85, 1.0 - 0.15 * (days - 14) / 76.0), 3)


# --------------------------------------------------------------------------- outcomes
def judge(money_at, money_after, value_at, value_after, direction, cleared) -> str:
    """Improved / No Change / Worse / Unknown, from what was at stake when done and now."""
    if cleared:
        return "Improved"
    if money_at and money_at > 0 and money_after is not None:
        change = (money_after - money_at) / money_at
        if change <= -IMPROVED_SHARE:
            return "Improved"
        if change >= IMPROVED_SHARE:
            return "Worse"
        return "No Change"
    if value_at is None or value_after is None or direction not in ("up_bad", "down_bad"):
        return "Unknown"
    base = abs(value_at) or 1.0
    change = (value_after - value_at) / base
    if direction == "down_bad":
        change = -change
    if change <= -IMPROVED_SHARE:
        return "Improved"
    if change >= IMPROVED_SHARE:
        return "Worse"
    return "No Change"


def evaluate(code, today=None) -> int:
    """Judge every Done whose look-again date has come. Writes; part of refresh()."""
    from command_center.recommend import metrics
    from command_center.recommend.engine import DOCTYPE as REC
    today = frappe.utils.getdate(today or frappe.utils.today())
    due = frappe.get_all(DOCTYPE, filters={"business_code": code, "action": "Done",
                                           "outcome": ["is", "not set"],
                                           "review_on": ["<=", today]},
                         fields=["name", "rec_key", "rule", "metric", "value_at", "money_at",
                                 "recommendation", "source"], limit=500)
    if not due:
        return 0
    hist = metrics.history(code)
    n = 0
    for f in due:
        open_row = frappe.get_all(REC, filters={"business_code": code, "rec_key": f.rec_key,
                                                "resolved_on": ["is", "not set"]},
                                  fields=["name", "money_at_stake", "status"], limit=1)
        if f.source == "ai":
            # An AI-found recommendation is judged by the figure it cites: the review
            # words its findings afresh each day, so its absence proves nothing.
            cleared, money_after = False, None
        else:
            cleared = not open_row
            money_after = _num(open_row[0].money_at_stake) if open_row else 0.0
        mt = metrics.BY_KEY.get(f.metric) if f.metric else None
        series = hist.get(f.metric) or [] if mt else []
        value_after = series[-1][1] if series else None
        value_at = None if f.value_at is None else _num(f.value_at)
        outcome = judge(_num(f.money_at), money_after, value_at, value_after,
                        mt.direction if mt else None, cleared)
        note = _note(outcome, cleared, _num(f.money_at), money_after, mt, value_at, value_after,
                     code)
        frappe.db.set_value(DOCTYPE, f.name, {"outcome": outcome, "money_after": money_after,
                                              "value_after": value_after,
                                              "outcome_on": frappe.utils.now_datetime(),
                                              "outcome_note": note})
        n += 1
    return n


def _note(outcome, cleared, money_at, money_after, mt, value_at, value_after, code) -> str:
    from command_center.api.businesses import currency_for
    from command_center.recommend.metrics import fmt
    cur = currency_for(code) or ""
    if cleared:
        return "It cleared in the data after it was marked done."
    if money_at and money_after is not None:
        return (f"At stake {fmt(cur, 'money', money_at)} when marked done, "
                f"{fmt(cur, 'money', money_after)} when checked.")
    if mt and value_at is not None and value_after is not None:
        return (f"{mt.label}: {fmt(cur, mt.unit, value_at)} when marked done, "
                f"{fmt(cur, mt.unit, value_after)} when checked.")
    return "Not enough of the figure's history to judge it."


def outcomes_for(names) -> dict:
    """recommendation name -> its latest Done's outcome, for Recently Closed."""
    if not names:
        return {}
    out = {}
    for r in frappe.get_all(DOCTYPE, filters={"recommendation": ["in", list(names)],
                                              "action": "Done"},
                            fields=["recommendation", "outcome", "outcome_note", "review_on",
                                    "acted_on"], order_by="acted_on asc", limit=2000):
        out[r.recommendation] = {"outcome": r.outcome or None, "note": r.outcome_note,
                                 "review_on": str(r.review_on) if r.review_on else None}
    return out


def recent_outcomes(code, limit=10) -> list:
    rows = frappe.get_all(DOCTYPE, filters={"business_code": code, "action": "Done",
                                            "outcome": ["in", list(OUTCOME_DELTA)]},
                          fields=["rule", "title", "outcome", "outcome_note", "outcome_on",
                                  "source"],
                          order_by="outcome_on desc", limit=limit)
    return [{"rule": r.rule, "title": r.title, "outcome": r.outcome, "note": r.outcome_note,
             "checked_on": str(r.outcome_on)[:10] if r.outcome_on else None,
             "source": r.source} for r in rows]


def what_worked(code, period=None) -> dict:
    """A month's outcomes, summed: the Executive Summary's What Worked. `period` is
    YYYY-MM; by default the last full month, or this month when that one has none."""
    from command_center.api.businesses import currency_for
    from command_center.recommend.metrics import fmt
    today = frappe.utils.getdate(frappe.utils.today())

    def bounds(y, m):
        return _dt.date(y, m, 1), _dt.date(y, m, calendar.monthrange(y, m)[1])
    if period:
        y, m = (int(x) for x in period.split("-"))
        spans = [bounds(y, m)]
    else:
        first = today.replace(day=1)
        last = first - _dt.timedelta(days=1)
        spans = [bounds(last.year, last.month), (first, today)]
    cur = currency_for(code) or ""
    for frm, to in spans:
        rows = frappe.get_all(DOCTYPE, filters={"business_code": code, "action": "Done",
                                                "outcome": ["in", list(OUTCOME_DELTA)],
                                                "outcome_on": ["between", [str(frm), f"{to} 23:59:59"]]},
                              fields=["rule", "title", "outcome", "money_at", "money_after",
                                      "outcome_note", "source"], limit=2000)
        if rows:
            break
    else:
        return {"period": spans[0][0].strftime("%B %Y"), "judged": 0,
                "says": "No recommendation marked done has reached its check yet: each one is "
                        "checked 14 or 30 days after it is marked done."}
    better = [r for r in rows if r.outcome == "Improved"]
    worse = [r for r in rows if r.outcome == "Worse"]
    freed = sum(max(0.0, _num(r.money_at) - _num(r.money_after)) for r in better)
    by_rule = {}
    for r in rows:
        x = by_rule.setdefault(r.rule, {"rule": r.rule, "title": r.title, "judged": 0,
                                        "improved": 0, "source": r.source})
        x["judged"] += 1
        x["improved"] += r.outcome == "Improved"
    label = frm.strftime("%B %Y")
    says = (f"In {label}, {len(rows)} recommendation{'s' if len(rows) != 1 else ''} marked "
            f"done reached {'their' if len(rows) != 1 else 'its'} check: {len(better)} improved "
            f"the figure, {len(worse)} got worse, {len(rows) - len(better) - len(worse)} "
            f"showed no change.")
    if freed:
        says += f" Money at stake fell by {fmt(cur, 'money', freed)} on those that improved."
    return {"period": label, "judged": len(rows), "improved": len(better), "worse": len(worse),
            "money_freed": round(freed, 2), "currency": cur, "says": says,
            "rules": sorted(by_rule.values(), key=lambda x: (-x["improved"], -x["judged"]))[:6]}
