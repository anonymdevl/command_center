"""The adaptive layer over the rules: thresholds learned from the business's own history,
what managers taught it, and the figures that moved out of their usual range.

The rules stay exact sensors (rules.py); this decides how sensitive they are and adds
what they cannot see. It never invents a baseline: with too little history a rule runs
on its fixed threshold and says the baseline is still learning.

Adaptive thresholds (Settings -> Recommendations, per rule: Fixed or Adaptive; Adaptive
by default). For the rules whose threshold is relative -- a fall, a change in points, a
share -- the adaptive threshold is what is unusual for THIS business:

    a change (sales_falling, margin_shrinking, days_to_pay_worsening)
        its typical move against the same month a year earlier (or the month before,
        under a year of history) plus two spreads -- baselines.change_band
    a level (customer_concentration, supplier_concentration, lines_without_cost)
        its own usual level plus two spreads -- baselines.level_band

then times the learned sensitivity (learning.py: managers marking it Not Relevant make
it less sensitive), and bounded: never below the fixed value (the administrator's
setting is the floor: adaptive never recommends on a smaller move than Fixed would), and
never above CAP_FACTOR times it (or 95 for a share), so a volatile business is never
silenced altogether.

Unusual movements (rule id "adaptive_anomaly", source Adaptive, on by default): a
figure whose latest value is Z_ANOMALY robust spreads out of its usual range in its bad
direction, or has shifted level for several periods running, when no rule watching that
figure has a recommendation open in the same pass -- so one issue is never said twice.

Every recommendation also carries: its source (Rule / Adaptive / AI-found), "why now"
(its figure against its usual range), the figure's recent points and band for the
small chart, and the learned weight with its explanation; the ranking score is money at
stake x severity x learned weight (x freshness, set when stored).
"""

from __future__ import annotations

from command_center.recommend import baselines, metrics

ANOMALY_RULE = "adaptive_anomaly"
AI_RULE = "ai_review"
SOURCES = {"rule": "Rule", "adaptive": "Adaptive", "ai": "AI-found"}
CAP_FACTOR = 2.0
SHARE_CAP = 95.0
Z_STRONG = 5.0

# rule -> the threshold it learns, from which figure, and how
ADAPTIVE = {
    "sales_falling": {"param": "pct", "metric": "revenue", "kind": "pct",
                      "words": "a fall this business rarely sees"},
    "margin_shrinking": {"param": "points", "metric": "gross_margin_pct", "kind": "points",
                         "words": "a drop in margin this business rarely sees"},
    "days_to_pay_worsening": {"param": "days", "metric": "days_to_pay", "kind": "points",
                              "words": "a slowdown this business rarely sees"},
    "customer_concentration": {"param": "pct", "metric": "customer_top5_share", "kind": "level",
                               "words": "above this business's usual share"},
    "supplier_concentration": {"param": "pct", "metric": "supplier_top2_share", "kind": "level",
                               "words": "above this business's usual share"},
    "lines_without_cost": {"param": "pct", "metric": "uncosted_share", "kind": "level",
                           "words": "above this business's usual share"},
}
AREA = {"revenue": "sales", "gross_margin_pct": "margin", "uncosted_share": "margin",
        "below_cost_loss": "margin", "purchases": "buying", "cash_received": "cash",
        "days_to_pay": "cash", "customer_top5_share": "sales", "supplier_top2_share": "buying",
        "ar_ledger": "cash", "ar_over_90": "cash", "ap_ledger": "cash",
        "unmatched_receipts": "cash", "unmatched_supplier_payments": "cash",
        "customers_in_credit": "cash", "overdue_deliveries": "sales",
        "delivered_unbilled": "sales", "order_book": "sales", "stock_value": "stock",
        "slow_stock": "stock", "discounting": "sales", "approvals_waiting": "control"}
OWNER = {"sales": "Sales", "margin": "Sales", "buying": "Purchasing", "cash": "Finance",
         "stock": "Stock Manager", "control": "Directors", "data": "Finance"}
ASK = {"cash": "Why has {label} moved out of its usual range, and which customers or "
               "suppliers are behind it?",
       "sales": "Why has {label} moved out of its usual range, and what is behind it?",
       "margin": "Why has {label} moved out of its usual range, and which products drove it?",
       "buying": "Why has {label} moved out of its usual range, and which suppliers are "
                 "behind it?",
       "stock": "Why has {label} moved out of its usual range, and which products are "
                "behind it?",
       "control": "Why has {label} moved out of its usual range?",
       "data": "Why has {label} moved out of its usual range?"}


def _n(v) -> str:
    """43.79 -> 43.8; 30.0 -> 30."""
    return f"{float(v):,.1f}".rstrip("0").rstrip(".")


def threshold(rule_id: str, fixed: float, hist: dict, sensitivity: float = 1.0) -> dict:
    """The adaptive threshold for one rule's relative parameter, with how it was found.
    {"status": "ready"|"learning", "value", "learned", "fixed", "says", ...}."""
    spec = ADAPTIVE[rule_id]
    mt = metrics.BY_KEY[spec["metric"]]
    pts = hist.get(mt.key) or []
    if spec["kind"] == "level":
        band = baselines.level_band(pts, mt.grain)
    else:
        band = baselines.change_band(pts, spec["kind"], mt.grain)
    unit = {"pct": "%", "points": " points", "days": " days"}[spec["param"]]
    out = {"status": band["status"], "fixed": float(fixed), "param": spec["param"],
           "metric": mt.key, "sensitivity": round(sensitivity, 3), "unit": unit}
    if band["status"] != "ready":
        out.update(value=float(fixed), learned=None,
                   says=f"{band['says']} Using the fixed threshold until then.")
        return out
    learned = band["unusual_from"] * sensitivity
    cap = fixed * CAP_FACTOR if fixed > 0 else learned
    if spec["kind"] == "level":
        cap = min(cap, SHARE_CAP)
    cap = max(cap, float(fixed))
    value = min(max(learned, float(fixed)), cap)
    if learned < fixed:
        bound = "the fixed value is the floor"
    elif value < learned:
        bound = f"capped at {_n(cap)}{unit}"
    else:
        bound = ""
    if spec["kind"] == "level":
        basis = (f"usual level {_n(band['typical'])}{unit} (spread {_n(band['scale'])}) over "
                 f"{band['basis']}")
    else:
        basis = (f"usual move {_n(band['typical'])}{unit} (spread {_n(band['scale'])}) against "
                 f"{band['basis']}, over {band['changes']} months")
    sens = (f"; made less sensitive by managers' decisions (x{sensitivity:g})"
            if sensitivity > 1.0 else "")
    out.update(value=round(value, 2), learned=round(learned, 2), band=band,
               says=(f"Adaptive: {value:.1f}{unit} ({spec['words']}: {basis}{sens}"
                     f"{'; ' + bound if bound else ''}). Fixed: {_n(fixed)}{unit}."))
    return out


class Learned:
    """Everything adaptive about one business, read once per pass (reads only)."""

    def __init__(self, code, conf, cur=""):
        from command_center.recommend import learning
        self.code, self.conf, self.cur = code, conf, cur
        self.hist = metrics.history(code)
        self.assessed = metrics.assess(code, self.hist)
        self.weights = learning.weights(code)
        self.thresholds = {}

    # ------------------------------------------------------------ thresholds
    def params(self, rule, mine) -> dict:
        """The parameters the rule runs with: its own, with the adaptive one swapped in."""
        params = dict(mine["params"])
        spec = ADAPTIVE.get(rule.rule_id)
        if spec is None or mine.get("mode", "adaptive") != "adaptive":
            return params
        sens = (self.weights.get(rule.rule_id) or {}).get("sensitivity", 1.0)
        t = threshold(rule.rule_id, params[spec["param"]], self.hist, sens)
        self.thresholds[rule.rule_id] = t
        params[spec["param"]] = t["value"]
        return params

    # ------------------------------------------------------------ each recommendation
    def enrich(self, rec: dict) -> dict:
        rule = rec["rule"]
        key = rec.get("metric") or metrics.RULE_METRIC.get(rule)
        mt = metrics.BY_KEY.get(key) if key else None
        b = self.assessed.get(key) if mt else None
        t = self.thresholds.get(rule)
        if rule == ANOMALY_RULE:
            src = "adaptive"
        elif rule == AI_RULE:
            src = "ai"
        else:
            src = "adaptive" if t and t["status"] == "ready" else "rule"
        rec["source"], rec["source_label"] = src, SOURCES[src]
        if mt is not None:
            rec["metric"] = mt.key
            rec.setdefault("why_now", metrics.why_now(mt, b, self.cur))
            rec["baseline"] = {"label": mt.label, "says": metrics.band_words(mt, b, self.cur),
                               "status": (b or {}).get("status", "learning"),
                               "chart": metrics.spark(mt, b)}
        if t:
            rec["threshold"] = {k: t.get(k) for k in ("status", "value", "fixed", "learned",
                                                       "says", "param")}
        w = self.weights.get(rule) or {}
        rec["learned"] = {"weight": w.get("weight", 1.0),
                          "explain": w.get("explain") or "No recent decisions: ranked by "
                                                         "money at stake and severity alone."}
        rec["base_score"] = rec.get("base_score", rec.get("score") or 0)
        rec["score"] = round(rec["base_score"] * rec["learned"]["weight"], 2)
        return rec

    # ------------------------------------------------------------ unusual movements
    def anomalies(self, recs: list, ran: list) -> list:
        """Figures out of their usual range that no firing rule already speaks to."""
        from command_center.recommend.rules import AREAS, SEVERITY_WEIGHT
        covered = {r.get("metric") or metrics.RULE_METRIC.get(r["rule"]) for r in recs}
        out = []
        for mt in metrics.METRICS:
            b = self.assessed.get(mt.key) or {}
            if b.get("status") != "ready" or mt.key in covered:
                continue
            shift = b.get("shift") or {}
            if not (b.get("anomaly") or (shift and shift.get("bad"))):
                continue
            if mt.direction == "either":
                continue
            why = metrics.why_now(mt, b, self.cur)
            if not why:
                continue
            area = AREA.get(mt.key, "data")
            excess = abs(b["latest"] - b["centre"]) if mt.unit == "money" else 0.0
            sev = "high" if abs(b.get("z") or 0) >= Z_STRONG else "med"
            when = (f"in {metrics._when(mt, b)}" if mt.grain == "month" else "now")
            rec = {
                "id": f"{ANOMALY_RULE}:{mt.key}", "rule": ANOMALY_RULE,
                "rule_title": "Unusual movements in the business's own figures",
                "area": area, "area_label": AREAS[area], "severity": sev,
                "money_at_stake": round(excess, 2), "currency": self.cur,
                "count": None, "unit": None,
                "title": f"Look into {mt.label}: out of {'their' if mt.phrase == 'are' else 'its'} "
                         f"usual range {when}.",
                "why": why + " " + metrics.band_words(mt, b, self.cur),
                "what_to_do": [f"Open the records behind {mt.label} and find what changed.",
                               "Decide whether it is a one-off or the start of a trend.",
                               "If it is a fault in the records, correct it at the source."],
                "how_in_erpnext": None, "ask": ASK[area].format(label=mt.label),
                "drill": {}, "owner_role": OWNER.get(area, "Finance"), "metric": mt.key,
                "why_now": why,
                "score": round(excess * SEVERITY_WEIGHT.get(sev, 0.2), 2),
            }
            out.append(self.enrich(rec))
        ran.append(ANOMALY_RULE)        # it ran: one no longer out of range resolves
        return out


def rule_modes(conf) -> dict:
    """{rule_id: "adaptive"|"fixed"} for the rules that can learn."""
    return {k: conf["rules"][k].get("mode", "adaptive") for k in ADAPTIVE if k in conf["rules"]}
