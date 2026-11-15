"""Evaluating the recommendation rules, ranking what they find, and keeping its state.

    compute(code)       every enabled rule against one business, ranked by money at stake
                        times urgency. Reads only: the analyst may call it.
    refresh(code)       compute, then write each recommendation's state
                        (Command Center Recommendation):
                          new                  a row, Open
                          still there          refreshed; a Snoozed one whose date has come
                                               is Open again; one marked Done that is still
                                               there a week later is Open again, and says so
                          gone (its rule ran)  Resolved and closed off, kept as history; a
                                               Not Relevant one keeps that word
                        A rule that could not run (its data unreadable, the business not
                        answering) resolves nothing: not knowing is not "cleared".
    ensure_fresh(code)  refresh when the last one is more than fifteen minutes old, one
                        pass at a time per business (as the alerts do)
    visible(code)       what a manager sees: Open, and Snoozed past its date, of rules
                        switched on, ranked
    act(...)            Done, Not Relevant (with an optional reason), Snooze 7 or 30 days

Settings per business (Settings -> Recommendations, administrators only) are one stored
value per business (frappe.defaults, parent SETTINGS_PARENT): which rules are on, their
thresholds and mode (Fixed or Adaptive, adaptive.py), the unusual-movement findings, the
daily email digest, the Daily Brief by Claude and the daily AI review (review.py).

The adaptive layer (adaptive.py, metrics.py, learning.py) runs inside compute(): learned
thresholds, why-now, the learned weight in the score. Should it fail, the rules run on
their fixed thresholds as before -- it can make them better, never stop them. refresh()
also captures today's figures, judges the outcomes that are due, and keeps every
decision act() records.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

from command_center.recommend.rules import (AREAS, BY_ID, RULES, SEVERITY_RANK,
                                            SEVERITY_WEIGHT)

DOCTYPE = "Command Center Recommendation"
OPEN = ("Open", "Snoozed", "Done")
FRESH_SECONDS = 15 * 60
DONE_GRACE_DAYS = 7
SNOOZE_DAYS = (7, 30)
SETTINGS_PARENT = "__cc_recommend"
RUN_KEY = "cc:recommend:run:{}"


# --------------------------------------------------------------------------- settings
def _stored(code) -> dict:
    try:
        raw = (frappe.defaults.get_defaults_for(SETTINGS_PARENT) or {}).get(code)
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def settings(code) -> dict:
    """{"rules": {rule_id: {"enabled", "params", "mode"}}, "digest", "brief", "anomalies",
    "ai_review"}, defaults filled. The AI review is on by default where a Claude key is
    set (None stored means "the default")."""
    from command_center.recommend.adaptive import ADAPTIVE
    got = _stored(code)
    rules = {}
    for rule in RULES:
        mine = (got.get("rules") or {}).get(rule.rule_id) or {}
        params = {}
        for p in rule.params:
            v = (mine.get("params") or {}).get(p.key)
            try:
                params[p.key] = float(v) if v not in (None, "") else float(p.default)
            except (TypeError, ValueError):
                params[p.key] = float(p.default)
        rules[rule.rule_id] = {"enabled": bool(mine.get("enabled", True)), "params": params}
        if rule.rule_id in ADAPTIVE:
            rules[rule.rule_id]["mode"] = ("fixed" if mine.get("mode") == "fixed"
                                           else "adaptive")
    review = got.get("ai_review")
    if review is None:
        try:
            from command_center.ask import claude
            review = claude.configured()
        except Exception:
            review = False
    return {"rules": rules, "digest": bool(got.get("digest", True)),
            "brief": bool(got.get("brief", False)),
            "anomalies": bool(got.get("anomalies", True)),
            "ai_review": bool(review), "ai_review_set": got.get("ai_review") is not None}


def save_settings(code, value: dict):
    value = dict(value)
    if not value.pop("ai_review_set", True):
        value.pop("ai_review", None)          # still the default: follows the Claude key
    frappe.defaults.set_default(code, json.dumps(value, default=str), parent=SETTINGS_PARENT)
    frappe.cache().delete_value(RUN_KEY.format(code))


# --------------------------------------------------------------------------- computing
def _context(code):
    from command_center.api.panels import _Ctx
    from command_center.kpi.engine import evaluate_set

    class Ctx(_Ctx):
        def figures(self, keys):
            cache = self.__dict__.setdefault("_figs", {})
            missing = [k for k in keys if k not in cache]
            if missing:
                cache.update(evaluate_set(missing, self.code))
            return {k: cache[k] for k in keys}

    return Ctx(code)


def _finish(rule, g, ctx) -> dict:
    sev = g.get("severity") or rule.severity
    money = round(float(g.get("money") or 0), 2)
    key = str(g.get("key") or "")
    return {
        "id": f"{rule.rule_id}:{key}" if key else rule.rule_id,
        "rule": rule.rule_id, "rule_title": rule.title,
        "area": rule.area, "area_label": AREAS[rule.area],
        "severity": sev, "money_at_stake": money, "currency": ctx.cur,
        "count": g.get("count"), "unit": g.get("unit"),
        "title": g["title"], "why": g["why"], "what_to_do": list(g.get("what_to_do") or []),
        "how_in_erpnext": g.get("how"), "ask": g.get("ask"), "drill": g.get("drill") or {},
        "owner_role": rule.owner,
        "score": round(money * SEVERITY_WEIGHT.get(sev, 0.2), 2),
        "source": "rule", "source_label": "Rule",
    }


def rank(recs: list) -> list:
    recs.sort(key=lambda r: (-(r.get("score") or 0), SEVERITY_RANK.get(r.get("severity"), 9),
                             -(r.get("count") or 0), r.get("id") or ""))
    return recs


def compute(code: str, conf: dict | None = None) -> dict:
    """Every enabled rule for one business. Reads only."""
    from command_center.kpi.live_departments import is_down
    conf = conf or settings(code)
    ctx = _context(code)
    learn = _learned(code, conf, ctx.cur)
    out, ran, failed, down = [], [], {}, False
    for rule in RULES:
        mine = conf["rules"][rule.rule_id]
        if not mine["enabled"]:
            continue
        params = mine["params"]
        if learn is not None:
            try:
                params = learn.params(rule, mine)
            except Exception:
                frappe.log_error(title=f"Command Center adaptive threshold {rule.rule_id}",
                                 message=frappe.get_traceback())
        try:
            got = rule.fn(ctx, params) or []
        except Exception as e:
            if is_down(e):
                down = True
                failed[rule.rule_id] = "The business's ERPNext did not answer."
            else:
                failed[rule.rule_id] = "Its data could not be read."
                frappe.log_error(title=f"Command Center recommendation {rule.rule_id}",
                                 message=frappe.get_traceback())
            continue
        ran.append(rule.rule_id)
        out += [_finish(rule, g, ctx) for g in got]
    if learn is not None:
        try:
            out = [learn.enrich(r) for r in out]
            if conf.get("anomalies", True):
                out += learn.anomalies(out, ran)
        except Exception:
            frappe.log_error(title="Command Center adaptive recommendations",
                             message=frappe.get_traceback())
    return {"recs": rank(out), "ran": ran, "failed": failed, "unreachable": down,
            "currency": ctx.cur, "as_of": str(ctx.as_of), "at": str(now_datetime())[:19]}


def _learned(code, conf, cur):
    """The adaptive layer for one pass, or None when it cannot be read (the rules then
    run as they always did)."""
    try:
        from command_center.recommend.adaptive import Learned
        return Learned(code, conf, cur)
    except Exception:
        frappe.log_error(title="Command Center adaptive layer unavailable",
                         message=frappe.get_traceback())
        return None


def _step(title, fn, *a, **kw):
    """A refresh step that may fail without failing the refresh."""
    try:
        return fn(*a, **kw)
    except Exception:
        frappe.log_error(title=title, message=frappe.get_traceback())
        return None


# --------------------------------------------------------------------------- state
def _payload(doc) -> dict:
    try:
        return json.loads(doc.get("payload") or "{}")
    except ValueError:
        return {}


def refresh(code: str) -> dict:
    from command_center.recommend import learning, metrics
    _step("Command Center metrics not captured", metrics.capture, code)
    result = compute(code)
    _step("Command Center metrics not captured", metrics.capture_measured, code, result)
    now = now_datetime()
    have = {r.rec_key: r for r in frappe.get_all(
        DOCTYPE, filters={"business_code": code, "resolved_on": ["is", "not set"]},
        fields=["name", "rec_key", "rule", "status", "first_seen"], limit=5000)}
    seen = set()
    for rec in result["recs"]:
        seen.add(rec["id"])
        values = {"rule": rec["rule"], "area": rec["area"], "severity": rec["severity"],
                  "title": rec["title"][:255], "money_at_stake": rec["money_at_stake"],
                  "currency": rec["currency"], "last_seen": now}
        row = have.get(rec["id"])
        _fresh(rec, row.first_seen if row is not None else now, now)
        if row is None:
            frappe.get_doc({"doctype": DOCTYPE, "business_code": code, "rec_key": rec["id"],
                            "status": "Open", "first_seen": now,
                            "payload": json.dumps(rec, default=str), **values}
                           ).insert(ignore_permissions=True)
            continue
        doc = frappe.get_doc(DOCTYPE, row.name)
        old = _payload(doc)
        if old.get("reopened_after_done"):
            rec["reopened_after_done"] = old["reopened_after_done"]
        doc.update(values)
        if doc.status == "Snoozed" and (not doc.snoozed_until
                                        or getdate(doc.snoozed_until) <= getdate(today())):
            doc.status, doc.snoozed_until = "Open", None
        if doc.status == "Done" and doc.acted_on and (
                now - get_datetime(doc.acted_on)).days >= DONE_GRACE_DAYS:
            doc.status = "Open"
            rec["reopened_after_done"] = str(doc.acted_on)[:10]
        doc.payload = json.dumps(rec, default=str)
        doc.save(ignore_permissions=True)
    ran = set(result["ran"])
    for key, row in have.items():
        if key in seen or row.rule not in ran:
            continue
        doc = frappe.get_doc(DOCTYPE, row.name)
        if doc.status in OPEN:
            doc.status = "Resolved"
        doc.resolved_on = now
        doc.save(ignore_permissions=True)
    _step("Command Center outcomes not checked", learning.evaluate, code)
    run = {k: result[k] for k in ("ran", "failed", "unreachable", "currency", "as_of", "at")}
    frappe.cache().set_value(RUN_KEY.format(code), run, expires_in_sec=FRESH_SECONDS)
    return run


def _fresh(rec, first_seen, now):
    """The stored score: money at stake x severity x learned weight x freshness."""
    from command_center.recommend.learning import freshness
    f = freshness(first_seen, now)
    rec["freshness"] = f
    rec["score"] = round((rec.get("score") or 0) * f, 2)


def last_run(code) -> dict | None:
    return frappe.cache().get_value(RUN_KEY.format(code))


def ensure_fresh(code: str, force: bool = False):
    if not force and last_run(code):
        return
    lock = frappe.cache().lock(f"cc:recommend:refreshing:{code}", timeout=600)
    if not lock.acquire(blocking=False):
        return
    try:
        refresh(code)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Command Center: recommendations failed",
                         message=frappe.get_traceback())
    finally:
        try:
            lock.release()
        except Exception:
            pass


def scheduled():
    """Hourly, like the alerts: every loaded business's recommendations made fresh."""
    from command_center.api.businesses import loaded_codes
    for code in loaded_codes():
        ensure_fresh(code, force=True)


def _row(r) -> dict:
    p = _payload(r)
    p.update({"name": r.name, "status": r.status, "business_code": r.business_code,
              "first_seen": str(r.first_seen)[:16] if r.first_seen else None,
              "snoozed_until": str(r.snoozed_until) if r.snoozed_until else None,
              "acted_by": r.acted_by, "reason": r.reason,
              "resolved_on": str(r.resolved_on)[:16] if r.resolved_on else None})
    return p


FIELDS = ["name", "business_code", "rec_key", "rule", "status", "payload", "first_seen",
          "snoozed_until", "acted_by", "acted_on", "reason", "resolved_on"]


def visible(code: str) -> list:
    """Open recommendations, and Snoozed ones whose date has come, of rules switched on
    (the unusual movements and the AI review's findings, while they are switched on)."""
    conf = settings(code)
    on = {k for k, v in conf["rules"].items() if v["enabled"]}
    from command_center.recommend.adaptive import AI_RULE, ANOMALY_RULE
    if conf.get("anomalies", True):
        on.add(ANOMALY_RULE)
    if conf.get("ai_review"):
        on.add(AI_RULE)
    now = getdate(today())
    out = []
    for r in frappe.get_all(DOCTYPE, filters={"business_code": code,
                                              "resolved_on": ["is", "not set"],
                                              "status": ["in", ["Open", "Snoozed"]]},
                            fields=FIELDS, limit=2000):
        if r.rule not in on:
            continue
        if r.status == "Snoozed" and r.snoozed_until and getdate(r.snoozed_until) > now:
            continue
        out.append(_row(r))
    if AI_RULE in on:
        from command_center.recommend.review import apply_priorities
        _step("Command Center AI priorities not applied", apply_priorities, code, out)
    return rank(out)


def history(code: str, limit: int = 20) -> list:
    """Recently closed: resolved by the data, or marked done or not relevant."""
    from command_center.recommend.learning import outcomes_for
    rows = frappe.get_all(DOCTYPE, filters={"business_code": code,
                                            "status": ["in", ["Resolved", "Done", "Not Relevant"]]},
                          fields=FIELDS, order_by="modified desc", limit=limit)
    out = [_row(r) for r in rows]
    try:
        seen = outcomes_for([r["name"] for r in out])
    except Exception:
        frappe.log_error(title="Command Center outcomes not read", message=frappe.get_traceback())
        seen = {}
    for r in out:
        if r["name"] in seen:
            r["outcome"] = seen[r["name"]]
    return out


def act(name: str, action: str, reason: str = "", days=None) -> dict:
    doc = frappe.get_doc(DOCTYPE, name)
    reason = (reason or "").strip()[:500]
    if doc.resolved_on:
        frappe.throw("This recommendation has already cleared.")
    if action == "done":
        doc.status = "Done"
    elif action == "not_relevant":
        doc.status = "Not Relevant"
        doc.reason = reason or None
    elif action == "snooze":
        try:
            days = int(days or 0)
        except (TypeError, ValueError):
            days = 0
        if days not in SNOOZE_DAYS:
            frappe.throw("Snooze for 7 or 30 days.")
        doc.status, doc.snoozed_until = "Snoozed", add_days(today(), days)
    elif action == "reopen":
        doc.status, doc.snoozed_until = "Open", None
    else:
        frappe.throw("Unknown action.")
    doc.acted_by, doc.acted_on = frappe.session.user, now_datetime()
    doc.save(ignore_permissions=True)
    from command_center.recommend import learning
    _step("Command Center decision not learned from", learning.record, doc, action, _payload(doc))
    return {"name": doc.name, "status": doc.status,
            "snoozed_until": str(doc.snoozed_until) if doc.snoozed_until else None}


def suggestions(code: str) -> dict:
    """rule_id -> how often managers marked it Not Relevant, when twice or more: the
    sign that its threshold is too low for this business."""
    count = {}
    for r in frappe.get_all(DOCTYPE, filters={"business_code": code, "status": "Not Relevant"},
                            fields=["rule"], limit=5000):
        count[r.rule] = count.get(r.rule, 0) + 1
    return {k: v for k, v in count.items() if v >= 2 and k in BY_ID}


# --------------------------------------------------------------------------- the bell
def open_alert_rules(code: str) -> set:
    from command_center.alerts.engine import DOCTYPE as ALERT, OPEN as ALERT_OPEN
    return {a.rule for a in frappe.get_all(ALERT, filters={
        "business_code": code, "status": ["in", list(ALERT_OPEN)],
        "resolved_on": ["is", "not set"]}, fields=["rule"], limit=500)}


def critical(code: str) -> list:
    """Critical recommendations the alerts do not already show: one whose rule watches the
    same thing as an open alert (Rule.twin_alert) is left to the alert."""
    alerts = open_alert_rules(code)
    return [r for r in visible(code) if r.get("severity") == "crit"
            and (BY_ID.get(r["rule"]) and BY_ID[r["rule"]].twin_alert) not in alerts]


# --------------------------------------------------------------------------- the analyst
def snapshot(code: str, limit: int = 15) -> dict:
    """For the analyst: the current recommendations, read only -- the stored ones when a
    pass has run, otherwise worked out now without writing anything."""
    run = last_run(code)
    recs = visible(code) if run else compute(code)["recs"]
    keep = ("title", "why", "what_to_do", "money_at_stake", "currency", "area_label",
            "severity", "owner_role", "count", "unit", "status", "ask", "source_label",
            "why_now", "timeframe", "confidence")
    out = []
    for r in recs[:limit]:
        x = {k: r.get(k) for k in keep if r.get(k) not in (None, "", [])}
        if (r.get("learned") or {}).get("weight", 1.0) != 1.0:
            x["learned"] = r["learned"]["explain"]
        if (r.get("baseline") or {}).get("says"):
            x["baseline"] = r["baseline"]["says"]
        if r.get("evidence"):
            x["evidence"] = [e.get("text") for e in r["evidence"] if e.get("text")][:6]
        out.append(x)
    from command_center.recommend import learning
    try:
        outcomes = learning.recent_outcomes(code, limit=8)
    except Exception:
        outcomes = []
    return {"recommendations": out, "recent_outcomes": outcomes,
            "total": len(recs), "worked_out": (run or {}).get("at") or "just now"}
