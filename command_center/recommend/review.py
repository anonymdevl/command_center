"""The daily AI review: Claude reads the business's evidence and finds what no single rule
covers.

    run_reviews()       06:15 (hooks.scheduler_events), after the morning's loads and before
                        the Daily Brief: for each loaded business with the review switched on
                        (on by default where a Claude key is set), ONE request.
    review(code)        one business: refresh, the evidence pack, Claude, validation, storage.

The evidence pack (pack()) is compact, structured JSON: the open findings (F1..), every
figure with its recent history and usual range (M:<figure>), the figures out of range
(A1..), what managers' decisions taught each rule (L:<rule>) and the outcomes of advice
already acted on (O1..). Each item has a key. Claude is asked, tool-free and answering in
the JSON schema SCHEMA, to (a) name cross-signal patterns no single rule covers, (b)
propose recommendations -- title, why, evidence keys, steps, owner, timeframe, money at
stake, confidence -- and (c) re-prioritise the open findings.

Validation is strict (validate()), and what is discarded is kept with the reason:
  - every evidence key must exist in the pack, and a recommendation needs at least two
    (one piece of evidence is a single rule's finding, already shown);
  - every number it writes must appear in the pack (the Daily Brief's grounding check,
    extended to the pack's values in their usual roundings and short forms);
  - its money at stake must be 0 or one of the pack's own amounts;
  - the area, timeframe and confidence must be from the lists given.
Accepted recommendations are stored as Command Center Recommendation rows with rule
"ai_review" and source AI-found: the same Done / Not Relevant / Snooze lifecycle, the
same outcome tracking (by the first figure they cite), the evidence listed on the card.
One not proposed again by the next successful review is closed (Resolved).

Cost: the instructions are fixed and carry the cache marker (claude.complete); one
request per business per day, metered as "ai_review" (insights/core/plans.py) and gated
like every AI feature (a lapsed licence or an exhausted allowance skips it, with the
reason kept). The model is claude.model_for("analyst"), the configured everyday model.
State per business is a stored value (frappe.defaults, REVIEW_PARENT).
"""

from __future__ import annotations

import json
import re

import frappe
from frappe.utils import now_datetime, today

from command_center.recommend import adaptive, engine, learning, metrics

REVIEW_PARENT = "__cc_ai_review"
METER = "ai_review"
MAX_FINDINGS = 15
MAX_ACCEPTED = 5
TIMEFRAMES = ("This Week", "Within Two Weeks", "This Month", "This Quarter")
CONFIDENCE = ("high", "medium", "low")
SEVERITY = {"high": "high", "medium": "med", "low": "info"}
PRIORITY_BOOST = 1.1
COST_NOTE = ("One Claude request per business per day at 06:15, from a compact evidence "
             "pack (about 6,000 tokens in, 2,000-5,000 out with its reasoning); metered as "
             "AI Reviews.")

SYSTEM = """You review one business's management evidence every morning for its chief \
executive. The evidence pack is JSON. Every item in it has a key: open findings from the \
platform's rules (F1, F2, ...), the business's figures with their recent history and usual \
range ("M:" then the figure), figures out of their usual range (A1, A2, ...), what managers' \
decisions taught each rule ("L:" then the rule), and outcomes of advice already acted on \
(O1, O2, ...).

Your job:
1. patterns: name connections between several pieces of evidence that no single finding \
states -- for example a fall in money received alongside a rise in customers paying late \
and new credit to the same customers. Each pattern cites at least two keys.
2. recommendations: propose at most five new actions that follow from those patterns. Each \
must cite at least two evidence keys, must not repeat an open finding's own advice, and must \
say plainly what to do: two to four short steps, an owner (a role, such as Finance or \
Sales), a timeframe from the allowed list, the money at stake and your confidence. If \
nothing new follows, return an empty list -- that is a good answer.
3. priorities: rank the open findings (by their F keys) in the order the chief executive \
should take them today, each with a one-sentence reason, at most eight.

Rules you must keep:
- Use only numbers that appear in the pack, written as they appear there or as the same \
value rounded (for example 7254533.12 may be written 7,254,533 or 7.25M). Never add up, \
subtract, estimate or introduce any other number, date or percentage.
- money_at_stake is 0, or exactly one of the amounts in the pack (the "money" of a finding, \
or the "latest_value" of a money figure) -- never a sum you worked out.
- Cite evidence only by the keys given. Do not mention keys in titles or steps.
- A figure whose status is "learning" has no usual range yet: do not call it unusual.
- Plain business English, formal and short. No markdown. Never name a field, a table or \
a tool.
- area is one of: cash, sales, margin, stock, buying, control, data. timeframe is one of: \
This Week, Within Two Weeks, This Month, This Quarter. confidence is high, medium or low."""

_STR = {"type": "string"}
_KEYS = {"type": "array", "items": {"type": "string"}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["patterns", "recommendations", "priorities"],
    "properties": {
        "patterns": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "explanation", "evidence"],
            "properties": {"title": _STR, "explanation": _STR, "evidence": _KEYS}}},
        "recommendations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["key", "title", "why", "evidence", "steps", "owner", "timeframe",
                         "money_at_stake", "confidence", "area"],
            "properties": {
                "key": {"type": "string", "description": "a short snake_case name for it"},
                "title": _STR, "why": _STR, "evidence": _KEYS,
                "steps": {"type": "array", "items": _STR}, "owner": _STR,
                "timeframe": {"type": "string", "enum": list(TIMEFRAMES)},
                "money_at_stake": {"type": "number"},
                "confidence": {"type": "string", "enum": list(CONFIDENCE)},
                "area": {"type": "string", "enum": ["cash", "sales", "margin", "stock", "buying",
                                                    "control", "data"]}}}},
        "priorities": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["finding", "rank", "reason"],
            "properties": {"finding": _STR, "rank": {"type": "integer"}, "reason": _STR}}},
    },
}


# --------------------------------------------------------------------------- state
def _get(code) -> dict:
    try:
        raw = (frappe.defaults.get_defaults_for(REVIEW_PARENT) or {}).get(code)
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def _put(code, value: dict):
    frappe.defaults.set_default(code, json.dumps(value, default=str), parent=REVIEW_PARENT)


def state(code) -> dict:
    return _get(code)


# --------------------------------------------------------------------------- the pack
def _r(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, 2)


def pack(code) -> tuple:
    """(the pack as a dict, {key: what the key stands for}). Reads only."""
    from command_center.api.businesses import currency_for
    from command_center.recommend.daily import _name
    cur = currency_for(code) or ""
    recs = [r for r in engine.visible(code) if r.get("rule") != adaptive.AI_RULE]
    hist = metrics.history(code)
    assessed = metrics.assess(code, hist)
    taught = learning.weights(code)
    refs = {}
    findings = []
    for i, r in enumerate(recs[:MAX_FINDINGS], 1):
        k = f"F{i}"
        refs[k] = {"kind": "finding", "rec_key": r.get("id"), "name": r.get("name"),
                   "text": r["title"], "money": _r(r.get("money_at_stake")) or 0.0}
        findings.append({"key": k, "rule": r.get("rule_title") or r.get("rule"),
                         "area": r.get("area"), "severity": r.get("severity"),
                         "source": r.get("source_label") or "Rule", "title": r["title"],
                         "why": r.get("why"),
                         "money": _r(r.get("money_at_stake")) or 0.0,
                         "money_text": metrics.fmt(cur, "money", r.get("money_at_stake")),
                         "why_now": r.get("why_now")})
    figures, anomalies = [], []
    for mt in metrics.METRICS:
        pts = hist.get(mt.key) or []
        if not pts:
            continue
        b = assessed.get(mt.key) or {}
        k = f"M:{mt.key}"
        if mt.grain == "month":
            sample = pts[-13:]
            period = pts[-1][0].strftime("%B %Y")
        else:
            sample = pts[::-1][::7][:8][::-1]
            period = str(pts[-1][0])
        item = {"key": k, "label": mt.label, "unit": mt.unit, "grain": mt.grain,
                "latest_value": _r(pts[-1][1]), "latest": metrics.fmt(cur, mt.unit, pts[-1][1]),
                "period": period, "worse_when": {"up_bad": "higher", "down_bad": "lower"}.get(
                    mt.direction, "either"),
                "history": [[str(d), _r(v)] for d, v in sample]}
        if b.get("status") == "ready":
            item.update(status="ready", method=b["method"], usual_low=_r(b["low"]),
                        usual_high=_r(b["high"]), z=b.get("z"),
                        usual=metrics.band_words(mt, b, cur))
        else:
            item.update(status="learning", usual=b.get("says"))
        figures.append(item)
        refs[k] = {"kind": "figure", "metric": mt.key, "text": f"{mt.label}: {item['latest']}"}
        why = metrics.why_now(mt, b, cur)
        if why:
            ak = f"A{len(anomalies) + 1}"
            anomalies.append({"key": ak, "figure": k, "text": why})
            refs[ak] = {"kind": "anomaly", "metric": mt.key, "text": why}
    feedback = []
    for rule, w in sorted(taught.items()):
        k = f"L:{rule}"
        feedback.append({"key": k, "rule": rule, "weight": w["weight"], "text": w["explain"]})
        refs[k] = {"kind": "feedback", "text": w["explain"]}
    outcomes = []
    for i, o in enumerate(learning.recent_outcomes(code, limit=8), 1):
        k = f"O{i}"
        outcomes.append({"key": k, "title": o["title"], "outcome": o["outcome"],
                         "note": o["note"]})
        refs[k] = {"kind": "outcome", "text": f"{o['title']} {o['outcome']}"}
    out = {"business": _name(code), "today": str(today()), "currency": cur,
           "findings": findings, "figures": figures, "anomalies": anomalies,
           "feedback": feedback, "outcomes": outcomes}
    return out, refs


# --------------------------------------------------------------------------- grounding
_KEY_MENTION = re.compile(r"\b(?:[FAO]\d+|M:[a-z0-9_]+|L:[a-z0-9_]+)\b")


def _norm(n: str) -> str:
    n = n.replace(",", "").rstrip(".")
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    return n or "0"


def numbers_in(text: str) -> set:
    from command_center.recommend.daily import NUMBER
    return {_norm(n) for n in NUMBER.findall(_KEY_MENTION.sub(" ", text or ""))}


def _walk(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from _walk(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _walk(x)
    else:
        yield v


def allowed_numbers(p: dict) -> set:
    """Every number the pack states, as written and in the usual roundings: 7254533.12 is
    also 7254533, 7254533.1, 7255k, 7.25M, 7.3M and 7M."""
    out = set()
    for v in _walk(p):
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, str):
            out |= numbers_in(v)
            continue
        if not isinstance(v, (int, float)):
            continue
        a = abs(float(v))
        for dp in (0, 1, 2):
            out.add(_norm(f"{a:.{dp}f}"))
        for div in (1e3, 1e6, 1e9):
            if a >= div:
                for dp in (0, 1, 2):
                    out.add(_norm(f"{a / div:.{dp}f}"))
    return out


def _money_values(p: dict) -> list:
    vals = [f["money"] for f in p["findings"] if f.get("money")]
    vals += [x["latest_value"] for x in p["figures"] if x["unit"] == "money" and x.get("latest_value")]
    return [abs(float(v)) for v in vals]


def validate(got, p: dict, refs: dict) -> dict:
    """{"recommendations", "patterns", "priorities", "rejected": [{"title", "why"}]}."""
    allowed = allowed_numbers(p)
    money = _money_values(p)
    out = {"recommendations": [], "patterns": [], "priorities": [], "rejected": []}
    if not isinstance(got, dict):
        out["rejected"].append({"title": "The whole reply", "why": "It was not the JSON asked for."})
        return out

    def stray(*texts):
        found = set()
        for t in texts:
            found |= numbers_in(t if isinstance(t, str) else " ".join(map(str, t or [])))
        return sorted(found - allowed)

    def bad_keys(keys):
        return [k for k in (keys or []) if k not in refs]

    for item in got.get("patterns") or []:
        title = str(item.get("title") or "")[:200]
        unknown, extra = bad_keys(item.get("evidence")), stray(title, item.get("explanation"))
        if unknown or extra or len(item.get("evidence") or []) < 2:
            out["rejected"].append({"title": title or "A pattern", "why": _why(unknown, extra, item)})
            continue
        out["patterns"].append({"title": title, "explanation": str(item.get("explanation"))[:600],
                                "evidence": list(item["evidence"])})
    seen = set()
    for item in got.get("recommendations") or []:
        title = str(item.get("title") or "").strip()[:240]
        ev = list(item.get("evidence") or [])
        steps = [str(s).strip()[:300] for s in (item.get("steps") or []) if str(s).strip()]
        unknown = bad_keys(ev)
        extra = stray(title, item.get("why"), steps, item.get("owner"))
        why = None
        if unknown or extra:
            why = _why(unknown, extra, item)
        elif len(set(ev)) < 2:
            why = "It cites one piece of evidence: that is a single rule's finding, already shown."
        elif not 2 <= len(steps) <= 4:
            why = "It does not give two to four steps."
        elif item.get("timeframe") not in TIMEFRAMES or item.get("confidence") not in CONFIDENCE:
            why = "Its timeframe or confidence is not one of those allowed."
        elif item.get("area") not in adaptive.OWNER:
            why = "Its area is not one of those allowed."
        elif not title or not str(item.get("why") or "").strip():
            why = "It has no title or no reason."
        else:
            amt = abs(float(item.get("money_at_stake") or 0))
            if amt and not any(abs(amt - v) <= max(1.0, 0.005 * v) for v in money):
                why = "Its money at stake is not one of the amounts in the evidence."
        key = re.sub(r"[^a-z0-9_]+", "_", str(item.get("key") or title).lower()).strip("_")[:60]
        if not why and (not key or key in seen):
            why = "It repeats another recommendation in the same review."
        if why:
            out["rejected"].append({"title": title or "A recommendation", "why": why})
            continue
        if len(out["recommendations"]) >= MAX_ACCEPTED:
            out["rejected"].append({"title": title, "why": f"More than {MAX_ACCEPTED} were proposed."})
            continue
        seen.add(key)
        out["recommendations"].append({**item, "key": key, "title": title, "steps": steps,
                                       "evidence": ev, "owner": str(item["owner"])[:60],
                                       "money_at_stake": abs(float(item.get("money_at_stake") or 0))})
    for item in got.get("priorities") or []:
        k = item.get("finding")
        if k not in refs or refs[k]["kind"] != "finding" or stray(item.get("reason")):
            continue
        out["priorities"].append({"rec_key": refs[k]["rec_key"], "rank": int(item.get("rank") or 99),
                                  "reason": str(item.get("reason") or "")[:300]})
    out["priorities"].sort(key=lambda x: x["rank"])
    out["priorities"] = out["priorities"][:8]
    return out


def _why(unknown, extra, item) -> str:
    if unknown:
        return f"It cites evidence that is not in the pack: {', '.join(map(str, unknown[:3]))}."
    if extra:
        return f"It gives {', '.join(extra[:3])}, which is not in the evidence it was given."
    return "It cites fewer than two pieces of evidence."


# --------------------------------------------------------------------------- storing
def store(code, accepted: list, p: dict, refs: dict, model: str) -> dict:
    """Accepted recommendations as AI-found rows; open ones not proposed again close."""
    from command_center.recommend.rules import AREAS, SEVERITY_WEIGHT
    DOCTYPE = engine.DOCTYPE
    now = now_datetime()
    have = {r.rec_key: r for r in frappe.get_all(
        DOCTYPE, filters={"business_code": code, "rule": adaptive.AI_RULE,
                          "resolved_on": ["is", "not set"]},
        fields=["name", "rec_key", "status", "first_seen"], limit=500)}
    keep = set()
    weight = (learning.weights(code).get(adaptive.AI_RULE) or {})
    assessed = metrics.assess(code)
    for item in accepted:
        rec_key = f"{adaptive.AI_RULE}:{item['key']}"
        keep.add(rec_key)
        sev = SEVERITY[item["confidence"]]
        first_metric = next((refs[k]["metric"] for k in item["evidence"]
                             if refs[k].get("metric")), None)
        rec = {"id": rec_key, "rule": adaptive.AI_RULE, "rule_title": "Daily AI review",
               "area": item["area"], "area_label": AREAS[item["area"]], "severity": sev,
               "money_at_stake": round(item["money_at_stake"], 2), "currency": p["currency"],
               "count": None, "unit": None, "title": item["title"], "why": item["why"],
               "what_to_do": item["steps"], "how_in_erpnext": None,
               "ask": f"{item['title']} What should we do, and what is the evidence?",
               "drill": {}, "owner_role": item["owner"], "timeframe": item["timeframe"],
               "confidence": item["confidence"], "source": "ai", "source_label": "AI-found",
               "evidence": [{"key": k, "text": refs[k]["text"], "kind": refs[k]["kind"]}
                            for k in item["evidence"]],
               "metric": first_metric, "model": model, "reviewed_on": str(today()),
               "learned": {"weight": weight.get("weight", 1.0),
                           "explain": weight.get("explain") or "No recent decisions: ranked "
                                                              "by money at stake and severity alone."}}
        rec["base_score"] = round(rec["money_at_stake"] * SEVERITY_WEIGHT.get(sev, 0.2), 2)
        rec["score"] = round(rec["base_score"] * rec["learned"]["weight"], 2)
        if first_metric:
            mt = metrics.BY_KEY[first_metric]
            b = assessed.get(first_metric)
            rec["why_now"] = metrics.why_now(mt, b, p["currency"])
            rec["baseline"] = {"label": mt.label, "says": metrics.band_words(mt, b, p["currency"]),
                               "status": (b or {}).get("status", "learning"),
                               "chart": metrics.spark(mt, b)}
        values = {"rule": adaptive.AI_RULE, "area": rec["area"], "severity": sev,
                  "title": rec["title"][:255], "money_at_stake": rec["money_at_stake"],
                  "currency": rec["currency"], "last_seen": now}
        row = have.get(rec_key)
        engine._fresh(rec, row.first_seen if row else now, now)
        if row is None:
            frappe.get_doc({"doctype": DOCTYPE, "business_code": code, "rec_key": rec_key,
                            "status": "Open", "first_seen": now,
                            "payload": json.dumps(rec, default=str), **values}
                           ).insert(ignore_permissions=True)
        else:
            doc = frappe.get_doc(DOCTYPE, row.name)
            doc.update(values)
            doc.payload = json.dumps(rec, default=str)
            doc.save(ignore_permissions=True)
    closed = 0
    for key, row in have.items():
        if key in keep:
            continue
        doc = frappe.get_doc(DOCTYPE, row.name)
        if doc.status in engine.OPEN:
            doc.status = "Resolved"
        doc.resolved_on = now
        doc.save(ignore_permissions=True)
        closed += 1
    return {"stored": len(keep), "closed": closed}


def priorities(code) -> dict:
    """rec_key -> {"rank", "reason"} from today's (or yesterday's) review."""
    s = _get(code)
    if not s.get("ok") or not s.get("date"):
        return {}
    if (frappe.utils.getdate(today()) - frappe.utils.getdate(s["date"])).days > 1:
        return {}
    return {x["rec_key"]: {"rank": x["rank"], "reason": x["reason"]}
            for x in (s.get("priorities") or []) if x.get("rec_key")}


def apply_priorities(code, recs: list) -> list:
    """The review's order, as a bounded lift (x1.1 for its first three) and its reason."""
    order = priorities(code)
    for r in recs:
        p = order.get(r.get("id"))
        if not p:
            continue
        r["ai_priority"] = p
        if p["rank"] <= 3:
            r["score"] = round((r.get("score") or 0) * PRIORITY_BOOST, 2)
    return recs


# --------------------------------------------------------------------------- running
def review(code) -> dict:
    """One business's review: at most one successful request a day."""
    from command_center import metering
    from command_center.ask import claude, llm
    conf = engine.settings(code)
    prev = _get(code)
    out = {"date": str(today()), "at": str(now_datetime())[:16], "ok": False, "error": None,
           "model": None, "accepted": 0, "rejected": [], "patterns": [], "priorities": []}
    if not conf.get("ai_review"):
        out["error"] = "The AI review is switched off for this business (Settings, Recommendations)."
        return out
    if prev.get("ok") and prev.get("date") == str(today()):
        return {**prev, "skipped": "Already reviewed today: one review a day per business."}
    if llm.provider() != "claude" or not claude.configured():
        out["error"] = "The AI review needs the Claude key (Settings, Claude)."
        _put(code, out)
        return out
    blocked = metering.gate(METER, code)
    if blocked:
        out["error"] = f"Skipped: {blocked}"
        _put(code, out)
        return out
    engine.ensure_fresh(code, force=True)
    p, refs = pack(code)
    if not p["findings"] and not p["anomalies"] and not p["figures"]:
        out["error"] = "Nothing to review yet: no findings and no figures with history."
        _put(code, out)
        return out
    text = ("EVIDENCE PACK (JSON). Review it as instructed.\n\n"
            + json.dumps(p, ensure_ascii=False, separators=(",", ":")))
    model = claude.model_for("analyst")
    frappe.local.cc_claude_usage = None        # this request's tokens only
    with metering.event(METER, code, note="Daily AI review") as ev:
        got, err = claude.complete(SYSTEM, text, kind="analyst", max_tokens=16000, schema=SCHEMA)
        ev["ok"] = bool(got and not err)
    out["model"] = model
    out["tokens"] = claude.usage()
    if err:
        out["error"] = f"Claude could not review it: {err}"
        _put(code, out)
        return out
    try:
        reply = json.loads(got)
    except ValueError:
        reply = None
    checked = validate(reply, p, refs)
    saved = store(code, checked["recommendations"], p, refs, model)
    out.update(ok=True, accepted=len(checked["recommendations"]), rejected=checked["rejected"],
               patterns=checked["patterns"], priorities=checked["priorities"], **saved,
               findings=len(p["findings"]), figures=len(p["figures"]))
    if checked["rejected"]:
        frappe.log_error(title="Command Center: AI review items not used",
                         message=json.dumps(checked["rejected"], indent=1)[:4000])
    _put(code, out)
    return out


def run_reviews():
    from command_center.api.businesses import loaded_codes
    for code in loaded_codes():
        if not engine.settings(code).get("ai_review"):
            continue
        try:
            review(code)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Command Center: AI review failed",
                             message=frappe.get_traceback())
