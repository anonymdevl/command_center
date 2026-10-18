"""Raising, ageing and resolving alerts.

One pass per business: every enabled rule is evaluated against the KPI engine, and
each finding is written to its Command Center Alert --

    new condition            a new alert, Raised
    condition persists       the same alert, figures refreshed and last_seen moved on;
                             a Deferred one whose date has come is Raised again
    condition clears         open alerts for it are Resolved; Dismissed and False
                             Positive ones keep their status (the outcome is the
                             point of keeping them, AL-06) and are closed off with
                             resolved_on, so a later recurrence raises afresh

Run from the scheduler hourly and, because a site's workers are not always running,
also on demand when the alerts are read and the last pass is more than fifteen
minutes old. A pass is a handful of aggregate queries, so either is cheap.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import getdate, now_datetime, today

from command_center.alerts.rules import RULES

DOCTYPE = "Command Center Alert"
RULE_DOCTYPE = "Command Center Alert Rule"
OPEN = ("Raised", "Acknowledged", "Actioned", "Deferred")
FRESH_SECONDS = 15 * 60


def rule_settings() -> dict:
    """Each rule's record, created with the defaults the first time it is needed."""
    have = {r.rule_id: r for r in frappe.get_all(
        RULE_DOCTYPE, fields=["rule_id", "enabled", "severity", "threshold_amount",
                              "threshold_days", "threshold_count"])}
    for rule in RULES:
        if rule.rule_id not in have:
            frappe.get_doc({
                "doctype": RULE_DOCTYPE, "rule_id": rule.rule_id, "enabled": 1,
                "severity": rule.severity, "threshold_amount": rule.threshold_amount,
                "threshold_days": rule.threshold_days,
                "threshold_count": rule.threshold_count,
                "description": rule.description,
            }).insert(ignore_permissions=True)
            have[rule.rule_id] = frappe._dict(
                rule_id=rule.rule_id, enabled=1, severity=rule.severity,
                threshold_amount=rule.threshold_amount, threshold_days=rule.threshold_days,
                threshold_count=rule.threshold_count)
    return have


def evaluate(business_code: str) -> dict:
    from command_center.kpi.engine import evaluate_set

    settings = rule_settings()
    keys = sorted({k for r in RULES for k in r.kpis})
    figures = evaluate_set(keys, business_code)
    seen, raised = set(), 0
    for rule in RULES:
        p = settings[rule.rule_id]
        if not p.enabled:
            continue
        finding = rule.fn(figures, p)
        if not finding:
            continue
        since = _since(rule, business_code)
        horizon = _horizon(figures, rule)
        _upsert(rule, p, business_code, "all", finding, since, horizon)
        seen.add((rule.rule_id, "all"))
        raised += 1
    _clear(business_code, seen)
    frappe.cache().set_value(f"cc:alerts:evaluated:{business_code}", str(now_datetime()),
                             expires_in_sec=FRESH_SECONDS)
    return {"business_code": business_code, "raised": raised}


def ensure_fresh(business_code: str):
    if frappe.cache().get_value(f"cc:alerts:evaluated:{business_code}"):
        return
    try:
        evaluate(business_code)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Command Center: alert evaluation failed",
                         message=frappe.get_traceback())


def scheduled():
    for code in frappe.get_all("Connected Business", filters={"is_local": 1},
                               pluck="business_code"):
        try:
            evaluate(code)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"Command Center: alert evaluation failed for {code}",
                             message=frappe.get_traceback())


# ---------------------------------------------------------------------------
def _upsert(rule, p, business_code, key, f, since, horizon):
    existing = frappe.get_all(DOCTYPE, filters={
        "rule": rule.rule_id, "business_code": business_code, "dedupe_key": key,
        "resolved_on": ["is", "not set"]},
        fields=["name", "status", "deferred_until"], order_by="creation desc", limit=1)
    values = {
        "severity": p.severity or rule.severity, "title": f["title"][:255], "why": f["why"],
        "next_step": f["next"], "figure": f["figure"], "figure_unit": f["unit"],
        "currency": f["currency"], "owner_label": f["owner"], "source_label": f["source"],
        "drill_fact": (f["drill"] or {}).get("fact"),
        "drill_filters": json.dumps((f["drill"] or {}).get("filters") or {}),
        "elapsed_from": since or horizon, "measured_to": horizon, "last_seen": now_datetime(),
    }
    if existing:
        doc = frappe.get_doc(DOCTYPE, existing[0].name)
        doc.update(values)
        if doc.status == "Deferred" and doc.deferred_until and getdate(doc.deferred_until) <= getdate(today()):
            doc.status = "Raised"
        doc.save(ignore_permissions=True)
        return doc
    doc = frappe.get_doc({"doctype": DOCTYPE, "rule": rule.rule_id,
                          "business_code": business_code, "dedupe_key": key,
                          "status": "Raised", "first_raised": now_datetime(), **values})
    doc.insert(ignore_permissions=True)
    return doc


def _clear(business_code, seen):
    for a in frappe.get_all(DOCTYPE, filters={"business_code": business_code,
                                              "resolved_on": ["is", "not set"]},
                            fields=["name", "rule", "dedupe_key", "status"]):
        if (a.rule, a.dedupe_key) in seen:
            continue
        doc = frappe.get_doc(DOCTYPE, a.name)
        if doc.status in OPEN:
            doc.status = "Resolved"
        doc.resolved_on = now_datetime()
        doc.save(ignore_permissions=True)


def _since(rule, business_code):
    """When the condition began: the oldest date among the records behind it."""
    if not rule.since:
        return None
    from command_center.facts.schema import FACTS, condition
    from command_center.kpi.registry import get
    from frappe.query_builder.functions import Min

    kpi = get(rule.since[0])
    t = frappe.qb.DocType(FACTS[kpi.fact])
    q = frappe.qb.from_(t).select(Min(t[rule.since[1]]))
    if business_code and business_code != "__all__":
        q = q.where(t.business_code == business_code)
    for field, value in (kpi.filters or {}).items():
        q = q.where(condition(t[field], value))
    row = q.run()
    return row[0][0] if row and row[0] and row[0][0] else None


def _horizon(figures, rule):
    for k in rule.kpis:
        d = (figures.get(k) or {}).get("as_of") or {}
        if d.get("date"):
            return d["date"]
    return today()


def elapsed(since, until=None) -> str:
    """'over 3 months', '12 days' -- measured to the data's own horizon, not today."""
    if not since:
        return "—"
    days = (getdate(until or today()) - getdate(since)).days
    if days < 0:
        return "not yet"
    if days >= 730:
        return f"over {days // 365} years"
    if days >= 60:
        return f"over {days // 30} months"
    return f"{days} day" + ("" if days == 1 else "s")

