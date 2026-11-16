"""The "Understanding This Figure" section of a figure's drawer, from data alone.

    understand(key, business_code) -> {
        figure      the figure itself, as the card has it
        what        {text, how}: what it is, and how it is worked out (from the definition)
        expected    {text, checks}: the expected position, and how the data compares
        trend       {title, mode, points, compare, typical, text} or None
        diagnosis   {sentences, chips, bridge, contributors, unmatched, ageing, credit,
                     tables}: what is driving it now, with numbers (diagnose.py)
        resolution  {owner, order, steps, guide}
        prevention  [{text, href, label, state}]
        related     [figure ...] that open their own drawers
        open_items  [{kind, title, why, money}] alerts and recommendations about it
        guide       what to record when nothing is behind it, or None
    }

Deterministic: no AI is involved, and every number is computed here or by the engine.
A KPI with no deep Spec (specs.py) gets the generic section: what it is and how it is
worked out from its definition, its trend, its related figures and how to improve it.

Figures are kept day by day (history), so a balance -- which has no history in the
facts -- can be compared with a month ago once the platform has watched it that long.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from statistics import median

import frappe
from frappe.utils import flt, getdate

from command_center.insight.diagnose import (
    _label, _month, _prev, _r, check, last_full_month, money, pct)
from command_center.insight.specs import RECONCILE, SPECS

HISTORY_PARENT = "__cc_figure_history"
HISTORY_DAYS = 400

# Facts whose rows are events in time (a sale, a payment, a purchase line): a figure over
# them has a real month-by-month history in the facts themselves.
FLOW_FACTS = {"fact_sales_invoice_line", "fact_payment_allocation", "fact_purchase_invoice_line"}
FACT_WORDS = {
    "fact_sales_invoice": "the business's Sales Invoices",
    "fact_sales_invoice_line": "the item lines of the business's Sales Invoices",
    "fact_payment_allocation": "the business's Payment Entries, as matched to documents",
    "fact_purchase_invoice": "the business's Purchase Invoices (supplier bills)",
    "fact_purchase_invoice_line": "the item lines of the business's Purchase Invoices",
    "fact_stock_balance": "ERPNext's stock balance per item and warehouse",
    "fact_sales_order": "the business's Sales Orders",
    "fact_task": "the business's Tasks",
    "fact_person": "the business's Employees",
    "fact_case": "the business's Issues (customer cases)",
    "fact_party_balance": "the General Ledger per customer and supplier, beside their open "
                          "invoices, payments and journals",
}
MEASURE_WORDS = {
    "base_net_amount": "net amount (before tax, in the company's currency)",
    "base_grand_total": "grand total (in the company's currency)",
    "base_margin_amount": "margin (net amount less the cost of what was sold)",
    "outstanding_amount": "outstanding amount", "allocated_amount": "amount allocated",
    "owed": "balance owed by the ledger", "d90_plus": "amount over 90 days late",
    "inside_90": "amount inside 90 days", "undated": "amount with no date",
    "in_credit": "credit balance", "unmatched_payments": "amount not matched",
    "unmatched_payment_count": "number of payments not matched",
    "stock_value": "stock value at cost", "available_qty": "quantity free to sell",
    "reserved_qty": "quantity reserved", "ordered_qty": "quantity on order",
    "undelivered_value": "value still to deliver", "unbilled_value": "value still to invoice",
    "days_to_pay": "days paid after the due date", "days_late": "days late",
    "days_open": "days open", "tenure_days": "days employed",
}
AGG_WORDS = {"sum": "the total", "count": "the number of", "count_distinct": "the number of "
             "distinct", "avg": "the average", "max": "the largest", "top": "the leading"}
OPS = {">": "above", ">=": "at least", "<": "below", "<=": "at most", "=": "", "!=": "not",
       "in": "one of", "not in": "not one of", "like": "like", "between": "between"}
FLAG_WORDS = {("src_docstatus", 1): "submitted", ("src_docstatus", 0): "still draft",
              ("has_cost", 1): "with a cost recorded", ("has_cost", 0): "with no cost recorded",
              ("has_valuation", 1): "carrying a valuation",
              ("has_valuation", 0): "with no valuation", ("is_open", 1): "still open"}


# --------------------------------------------------------------------------- definitions
def _human(field: str) -> str:
    return MEASURE_WORDS.get(field) or field.replace("_", " ")


def filter_words(filters: dict) -> str:
    parts = []
    for f, rule in (filters or {}).items():
        if not isinstance(rule, (list, tuple)):
            parts.append(FLAG_WORDS.get((f, rule)) or f"{_human(f)} {rule}")
            continue
        op, val = rule[0], rule[1] if len(rule) > 1 else None
        if f == "src_docstatus" and op == "in":
            parts.append("submitted or draft")
            continue
        if op == "between" and isinstance(val, (list, tuple)):
            parts.append(f"{_human(f)} from {val[0]} to {val[1]}")
            continue
        if isinstance(val, (list, tuple)):
            val = ", ".join(str(v) for v in val[:6])
        parts.append(f"{_human(f)} {OPS.get(op, op)} {val}".replace("  ", " "))
    return "; ".join(parts)


def _source(fact):
    try:
        from command_center.ingest.registry import get
        return get(fact).source_doctype
    except Exception:
        return None


def definition(k) -> dict:
    """What it is and how it is worked out, from an engine KPI's own definition."""
    if k.agg == "ratio":
        from command_center.kpi.registry import get
        top, bottom = get(k.numerator), get(k.denominator)
        how = (f"{top.label} divided by {bottom.label}"
               + (" , as a percentage" if k.unit == "percent" else "") + ".")
        return {"text": f"{k.label}: {top.label.lower()} as a share of {bottom.label.lower()}.",
                "how": how.replace(" ,", ","), "source": None}
    noun = (AGG_WORDS.get(k.agg, "the") + " " + ("records" if k.measure == "*" else
            (k.distinct_on.replace("_", " ") + "s" if k.agg == "count_distinct" and k.distinct_on
             else _human(k.measure))))
    scope = filter_words({f: v for f, v in (k.filters or {}).items()
                          if not (k.period and f == k.period.get("field"))})
    how = f"{noun[0].upper()}{noun[1:]} of {FACT_WORDS.get(k.fact, k.fact)}"
    if scope:
        how += f", counting only those {scope}"
    if k.period:
        how += f", over {k.period['window'].replace('_', ' ')} by {_human(k.period['field'])}"
    if k.agg == "top":
        how += f", per {k.group_by.replace('month:', 'month of ').replace('_', ' ')}"
    how += ". Loaded from the business's ERPNext and refreshed as it changes."
    text = f"{k.label}" + (f": {k.note.split('{')[0].strip().rstrip(',;')}" if k.note
                           and not k.note.startswith("{") else "") + "."
    if k.subset_of:
        text += f" A subset of {k.subset_of}."
    return {"text": text, "how": how, "source": _source(k.fact)}


def live_definition(spec) -> dict:
    doc = (spec.fn.__doc__ or "").strip()
    first = re.split(r"\n\s*\n", doc)[0] if doc else ""
    first = " ".join(first.split())
    return {"text": f"{spec.label}." + (f" {first}" if first else ""),
            "how": ("Read from the business's ERPNext when the screen opens." if spec.reads_erp
                    else "Worked out from the data loaded from the business's ERPNext."),
            "source": None}


def _related_keys(k) -> list:
    """Figures the definition itself ties this one to."""
    if k is None:
        return []
    from command_center.kpi.registry import REGISTRY, _resolve_token, _tokens
    out = list(k.components) + [k.numerator, k.denominator, k.share_of]
    out += [_resolve_token(t)[0] for t in _tokens(k.note) if t not in ("period", "group")]
    # Figures that divide or are made of this one.
    out += [o.key for o in REGISTRY.values() if k.key in (o.numerator, o.denominator)
            or k.key in o.components]
    return [x for x in dict.fromkeys(out) if x and x != k.key and x in REGISTRY]


# --------------------------------------------------------------------------- history
def _hkey(code, key) -> str:
    return f"{code or '__all__'}::{key}"


def history(code, key) -> list:
    try:
        raw = (frappe.defaults.get_defaults_for(HISTORY_PARENT) or {}).get(_hkey(code, key))
        return json.loads(raw) if raw else []
    except (ValueError, TypeError):
        return []


def record(code, key, value, on=None):
    """Keep today's value of a figure (once a day; the latest of the day wins)."""
    if value is None or isinstance(value, str):
        return
    day = str(getdate(on or frappe.utils.today()))
    pts = [p for p in history(code, key) if p[0] != day] + [[day, round(flt(value), 4)]]
    pts = sorted(pts)[-HISTORY_DAYS:]
    try:
        frappe.defaults.set_default(_hkey(code, key), json.dumps(pts), parent=HISTORY_PARENT)
    except Exception:
        frappe.log_error(title="Command Center insight: history not kept",
                         message=frappe.get_traceback())


def record_all():
    """Daily: every figure the engine computes, for every loaded business, kept for the
    drawers' "a month ago" comparison."""
    from command_center.api.businesses import loaded_codes
    from command_center.kpi.engine import evaluate_set
    from command_center.kpi.registry import load_all
    keys = sorted(load_all())
    for code in loaded_codes():
        try:
            for k, f in evaluate_set(keys, code).items():
                record(code, k, f.get("value"))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Command Center insight: daily history failed",
                             message=frappe.get_traceback())


# --------------------------------------------------------------------------- trend
def _mode(k) -> str | None:
    from command_center.facts.schema import DATE_FIELDS
    if k is None:
        return "snapshot"
    if k.agg == "ratio":
        from command_center.kpi.registry import get
        modes = {_mode(get(k.numerator)), _mode(get(k.denominator))}
        return "flow" if modes == {"flow"} else "snapshot"
    if not DATE_FIELDS.get(k.fact) or k.fact in ("fact_party_balance",):
        return "snapshot"
    unpaid = k.measure == "outstanding_amount" or "outstanding_amount" in (k.filters or {})
    if k.fact in ("fact_sales_invoice", "fact_purchase_invoice") and unpaid:
        return "raised"
    if k.fact in FLOW_FACTS or k.period or k.fact in ("fact_sales_invoice", "fact_purchase_invoice"):
        return "flow"
    return "snapshot"


def _monthly(ctx, k, months=24) -> tuple:
    """{(y, m): value} of one KPI's measure, by month of its date, and the last full month."""
    from command_center.facts.schema import DATE_FIELDS, condition
    field = (k.period or {}).get("field") or DATE_FIELDS[k.fact][0]
    filters = {f: v for f, v in (k.filters or {}).items() if f != field}
    cols = [field] + ([k.measure] if k.measure != "*" else []) + (
        [k.distinct_on] if k.agg == "count_distinct" else [])
    rows = ctx.rows(k.fact, list(dict.fromkeys(cols)),
                    lambda t: [condition(t[f], v) for f, v in filters.items()])
    rows = [r for r in rows if r.get(field)]
    if not rows:
        return {}, None
    last = last_full_month(max(getdate(r[field]) for r in rows))
    acc = defaultdict(list)
    for r in rows:
        acc[_month(r[field])].append(r)
    out = {}
    for ym, rs in acc.items():
        vals = [flt(r.get(k.measure)) for r in rs] if k.measure != "*" else []
        out[ym] = (len(rs) if k.agg == "count" else
                   len({r.get(k.distinct_on) for r in rs}) if k.agg == "count_distinct" else
                   (sum(vals) / len(vals) if vals else None) if k.agg == "avg" else
                   (max(vals) if vals else None) if k.agg == "max" else sum(vals))
    return out, last


def trend(ctx, k, key, figure) -> dict | None:
    code = ctx.code
    mode = _mode(k)
    if mode in ("flow", "raised") and k is not None:
        try:
            if k.agg == "ratio":
                from command_center.kpi.registry import get
                top, last = _monthly(ctx, get(k.numerator))
                bottom, _ = _monthly(ctx, get(k.denominator))
                series = {m: (round(flt(top.get(m)) / flt(v) * (100 if k.unit == "percent" else 1), 2)
                              if flt(v) else None) for m, v in bottom.items()}
            else:
                series, last = _monthly(ctx, k)
        except Exception:
            frappe.log_error(title=f"Command Center insight: trend for {key}",
                             message=frappe.get_traceback())
            return None
        if not series or last is None:
            return None
        if mode == "raised":
            # Open items are raised up to the data's own date, the current month included.
            last = max([_month(ctx.as_of)] + list(series))
            months = [_prev(last, i) for i in range(11, -1, -1)]
            earlier = sum(flt(v) for m, v in series.items() if m < months[0])
            pts = ([{"label": "Earlier", "value": _r(earlier)}] if earlier else []) + [
                {"label": _label(m), "value": _r(series.get(m, 0.0))} for m in months]
            whole = sum(p["value"] for p in pts)
            text = (f"{pct(earlier, whole) or 0}% of it was raised before {_label(months[0])}: "
                    f"the older the invoice, the less likely it is still really unpaid."
                    if earlier else "All of it was raised in the last twelve months.")
            return {"title": "Where it comes from, by the month each invoice was raised",
                    "mode": mode, "points": pts, "unit": k.unit, "text": text,
                    "compare": [], "typical": None}
        months = [_prev(last, i) for i in range(11, -1, -1)]
        vals = [series.get(m) for m in months]
        known = [v for v in vals if v is not None]
        if not known:
            return None
        a, b, ly = series.get(last), series.get(_prev(last)), series.get(_prev(last, 12))
        typical = {"low": _r(min(known)), "median": _r(median(known)), "high": _r(max(known))}
        compare = [{"label": _label(last), "value": None if a is None else _r(a)},
                   {"label": _label(_prev(last)), "value": None if b is None else _r(b)}]
        if ly is not None:
            compare.append({"label": _label(_prev(last, 12)), "value": _r(ly)})
        inside = a is not None and typical["low"] <= a <= typical["high"]
        text = (f"{_label(last)} is {'inside' if inside else 'outside'} the range of the twelve "
                f"months to it." if a is not None else "")
        return {"title": "By month, the last twelve full months", "mode": mode, "unit": k.unit,
                "points": [{"label": _label(m), "value": None if v is None else _r(v)}
                           for m, v in zip(months, vals)],
                "compare": compare, "typical": typical, "text": text, "inside": inside}
    # A balance: the platform's own daily record of it.
    pts = history(code, key)
    value = (figure or {}).get("value")
    if not pts or len(pts) < 2:
        return {"title": "Its history", "mode": "snapshot", "points": [], "compare": [],
                "typical": None, "unit": (figure or {}).get("unit"),
                "text": "A balance has no history in the records themselves, so the platform "
                        "keeps one: this figure is recorded every day from now on, and the "
                        "comparison with a month ago appears here once there is one."}
    today = getdate(frappe.utils.today())
    month_ago = [p for p in pts if (today - getdate(p[0])).days >= 28]
    was = month_ago[-1] if month_ago else None
    vals = [p[1] for p in pts]
    compare = [{"label": "Now", "value": value}]
    if was:
        compare.append({"label": f"On {getdate(was[0]).strftime('%-d %b %Y')}", "value": was[1]})
    return {"title": "Its history, as the platform has recorded it", "mode": "snapshot",
            "unit": (figure or {}).get("unit"),
            "points": [{"label": getdate(d).strftime("%-d %b %Y"), "value": v} for d, v in pts[-60:]],
            "compare": compare, "typical": {"low": min(vals), "median": median(vals), "high": max(vals)},
            "text": (f"Recorded on {len(pts)} days since {getdate(pts[0][0]).strftime('%-d %b %Y')}."
                     + ("" if was else " The comparison with a month ago appears once the record "
                                       "is a month old."))}


# --------------------------------------------------------------------------- the section
def _figures(keys, code) -> dict:
    from command_center.kpi.engine import evaluate_set
    from command_center.kpi.live import LIVE, evaluate as evaluate_live
    from command_center.kpi.registry import REGISTRY
    eng = [k for k in keys if k in REGISTRY]
    out = evaluate_set(eng, code) if eng else {}
    lv = [k for k in keys if k in LIVE and k not in out]
    if lv:
        out.update(evaluate_live(lv, code))
    return out


def _prevention(ctx, spec) -> list:
    from command_center.guides import site_url
    site = site_url(ctx.code)
    out = []
    for text, path, label in spec.prevention:
        item = {"text": text, "href": site + path, "label": label}
        if text == "__auto_reconcile__":
            item.update(auto_reconcile(ctx))
        out.append(item)
    return out


def auto_reconcile(ctx) -> dict:
    """Whether the business's ERPNext can reconcile payments by itself (Accounts Settings'
    Auto Reconcile Payments, which came with a later version than some sites run), and
    whether it is on. Read from the site's own definition, never assumed from a version."""
    base = ("Let ERPNext match payments by itself: Accounts Settings, Auto Reconcile "
            "Payments")
    if not ctx.code or ctx.code == "__all__":
        return {"text": base + ", where the version offers it.", "state": "info"}
    try:
        r = ctx.reader()
        if getattr(r, "_down", None) is not None:
            return {"text": base + ", where the version offers it.", "state": "info"}
        conn = getattr(r, "conn", None)
        have = conn.fieldnames("Accounts Settings") if conn is not None and hasattr(conn, "fieldnames") else None
        if have is None:
            return {"text": base + ", where the version offers it.", "state": "info"}
        if "auto_reconcile_payments" not in have:
            return {"text": "This ERPNext version has no automatic reconciliation of payments "
                            "(Auto Reconcile Payments came with a later version), so the "
                            "month-end routine below is the safeguard.", "state": "info"}
        on = conn.get_value("Accounts Settings", "Accounts Settings", "auto_reconcile_payments")
        on = (on or {}).get("auto_reconcile_payments") if isinstance(on, dict) else on
        return ({"text": base + " is on: ERPNext matches payments to invoices in the "
                                "background.", "state": "ok"} if flt(on) else
                {"text": base + " is available on this ERPNext and is off. Switching it on "
                                "matches payments to invoices in the background.",
                 "state": "warn"})
    except Exception:
        return {"text": base + ", where the version offers it.", "state": "info"}


def _open_items(code, keys: set, recs: tuple) -> list:
    """Open alerts about these figures, and open recommendations of these rules."""
    if not code or code == "__all__":
        return []
    out = []
    try:
        from command_center.alerts.engine import DOCTYPE, OPEN
        from command_center.alerts.rules import RULES
        rules = {r.rule_id for r in RULES if set(r.kpis) & keys}
        if rules:
            for a in frappe.get_all(DOCTYPE, filters={"business_code": code, "status": ["in", list(OPEN)],
                                                      "resolved_on": ["is", "not set"],
                                                      "rule": ["in", sorted(rules)]},
                                    fields=["title", "why", "next_step", "figure", "currency",
                                            "severity"], limit=20):
                out.append({"kind": "Alert", "title": a.title, "why": a.why,
                            "next": a.next_step, "severity": a.severity})
    except Exception:
        frappe.log_error(title="Command Center insight: alerts", message=frappe.get_traceback())
    if recs:
        try:
            from command_center.recommend.engine import visible
            for r in visible(code):
                if r.get("rule") in recs:
                    out.append({"kind": "Recommendation", "title": r.get("title"),
                                "why": r.get("why"),
                                "next": (r.get("what_to_do") or [None])[0],
                                "money": r.get("money_at_stake"), "severity": r.get("severity")})
        except Exception:
            frappe.log_error(title="Command Center insight: recommendations",
                             message=frappe.get_traceback())
    return out[:12]


def _steps(ctx, spec) -> tuple:
    from command_center.guides import RECONCILE_STEPS, payment_reconciliation
    steps, guide = [], None
    for s in spec.resolution:
        if s == RECONCILE:
            steps += RECONCILE_STEPS
            guide = payment_reconciliation(ctx.code, "Match payments to invoices in ERPNext:")
        else:
            steps.append(s)
    return steps, guide


def _rows_in(k, code) -> int | None:
    """How many rows of the KPI's fact the business has at all (None for a live figure)."""
    if k is None:
        return None
    from command_center.facts.schema import FACTS
    f = {"business_code": code} if code and code != "__all__" else {}
    return frappe.db.count(FACTS[k.fact], f)


def improve(k, figure, code) -> list:
    """How to improve it, from its definition: which way is better, and where to act."""
    from command_center.guides import site_url
    direction = (k.direction if k is not None else (figure or {}).get("direction")) or "neutral"
    steps = [{"higher_is_worse": "Lower is better. Start with the largest records below: "
                                 "they move the figure most.",
              "higher_is_better": "Higher is better. Compare it with its own history above, "
                                  "and look for the largest records that have fallen.",
              "neutral": "There is no right level for it on its own: read it beside the "
                         "related figures and its own history."}[direction]]
    href = None
    if k is not None and _source(k.fact):
        src = _source(k.fact).replace(" Item", "").replace(" Reference", "")
        src = {"Bin": "Item", "GL Entry": "General Ledger"}.get(src, src)
        path = "/app/query-report/General%20Ledger" if src == "General Ledger" else \
            "/app/" + src.lower().replace(" ", "-")
        steps.append(f"Act on the records in ERPNext ({src}); this platform reports on them "
                     f"and shows the change at its next load.")
        href = site_url(code) + path
    elif figure and (figure.get("drill") or {}).get("href"):
        href = figure["drill"]["href"]
        steps.append("Act on the records in ERPNext; the figure is read from there each time "
                     "the screen opens.")
    return [{"text": s, "href": href if i == len(steps) - 1 else None,
             "label": "Open in ERPNext" if href and i == len(steps) - 1 else None}
            for i, s in enumerate(steps)]


def understand(key: str, business_code: str | None = None) -> dict:
    from command_center.api.businesses import default_business_code
    from command_center.guides import guide as make_guide
    from command_center.kpi.live import LIVE
    from command_center.kpi.registry import REGISTRY, load_all
    from command_center.recommend.engine import _context

    load_all()
    if key not in REGISTRY and key not in LIVE:
        frappe.throw(f"No figure {key!r}.")
    code = business_code or default_business_code()
    k = REGISTRY.get(key)
    spec = SPECS.get(key)
    related = list(dict.fromkeys(list(spec.related if spec else ()) + _related_keys(k)))
    related = [r for r in related if r != key and (r in REGISTRY or r in LIVE)][:8]
    figs = _figures([key] + related, code)
    figure = figs.get(key) or {}
    if figure.get("value") is not None and figure.get("unit") not in ("time", "date"):
        record(code, key, figure.get("value"))

    ctx = _context(code)
    base = definition(k) if k is not None else live_definition(LIVE[key])
    what = {"text": spec.what if spec else base["text"], "how": base["how"],
            "definition": base["text"] if spec else None}
    section = {
        "key": key, "label": figure.get("label") or (k.label if k else LIVE[key].label),
        "figure": figure, "currency": figure.get("currency") or ctx.cur,
        "as_of": figure.get("as_of"), "what": what, "depth": "deep" if spec and not spec.light
        else "light" if spec else "basic",
        "expected": {"text": spec.expected if spec else None, "checks": []},
        "trend": None, "diagnosis": None, "resolution": None, "prevention": [],
        "related": [figs[r] for r in related if r in figs],
        "open_items": [], "guide": None, "link": spec.link if spec else None,
    }

    # Nothing behind it: say what to record, not a blank.
    state = (figure.get("data_status") or {}).get("state")
    rows = _rows_in(k, code)
    if state in ("needs_setup", "no_access") and (figure.get("data_status") or {}).get("guide"):
        section["guide"] = figure["data_status"]["guide"]
    elif rows == 0:
        text, steps, path = (spec.empty if spec and spec.empty else (
            f"Nothing is recorded behind this figure yet"
            + (f" ({_source(k.fact)} in ERPNext)." if k is not None and _source(k.fact) else "."),
            ["Record the documents in ERPNext and submit them.",
             "The platform reads them at its next load (or Settings, Businesses, Manage, "
             "Reload Everything)."], None))
        if state == "not_loaded":
            steps = ["Settings, Businesses, Manage, Reload Everything loads it from the "
                     "business's ERPNext."] + list(steps)
        section["guide"] = make_guide(code, text, steps, path)

    if not section["guide"]:
        section["trend"] = trend(ctx, k, key, figure)
        if spec and spec.diagnose and not spec.light:
            try:
                d = spec.diagnose(ctx, key) or {}
            except Exception as e:
                from command_center.kpi.live_departments import is_down
                if is_down(e):
                    d = {"diagnosis": ["The business's ERPNext is not answering just now, so "
                                       "the breakdown read from it is not shown."]}
                else:
                    frappe.log_error(title=f"Command Center insight: diagnosis of {key}",
                                     message=frappe.get_traceback())
                    d = {"diagnosis": ["The breakdown could not be worked out just now; it "
                                       "has been recorded for the administrator."]}
            if d.get("empty") and spec.empty:
                section["guide"] = make_guide(code, *spec.empty)
            else:
                section["expected"]["checks"] = d.pop("checks", [])
                d["sentences"] = d.pop("diagnosis", [])
                section["diagnosis"] = d
        t = section["trend"]
        if t and t.get("typical") and t["mode"] == "flow" and t.get("compare"):
            a = t["compare"][0]["value"]
            if a is not None:
                section["expected"]["checks"].append(check(
                    "Inside its own usual range", "ok" if t.get("inside") else "warn",
                    f"{t['compare'][0]['label']}: {_fmt(a, k.unit, ctx.cur)}; the twelve months to "
                    f"it ran from {_fmt(t['typical']['low'], k.unit, ctx.cur)} to "
                    f"{_fmt(t['typical']['high'], k.unit, ctx.cur)}."))
    if not section["expected"]["text"]:
        section["expected"]["text"] = {
            "higher_is_worse": "As low as the business can hold it; read it against its own "
                               "history and the related figures.",
            "higher_is_better": "As high as the business can make it, and steady or rising "
                                "against its own history.",
        }.get((k.direction if k else "neutral"), "No right level on its own: it is read "
                                                 "beside the related figures and its history.")

    if spec and not spec.light:
        steps, guide = _steps(ctx, spec)
        section["resolution"] = {"owner": spec.owner, "order": spec.order, "steps": steps,
                                 "guide": guide}
        section["prevention"] = _prevention(ctx, spec)
    else:
        section["resolution"] = {"owner": spec.owner if spec else None, "order": None,
                                 "steps": [], "guide": None, "improve": improve(k, figure, code)}
    section["open_items"] = _open_items(code, {key} | set(related[:4]),
                                        spec.recs if spec else ())
    section["status"] = status(section["expected"]["checks"])
    section["headline"] = headline(section)
    return section


STATUS = {"bad": ("attention", "Needs Attention"), "warn": ("watch", "Watch"),
          "ok": ("on_target", "On Target")}


def status(checks) -> dict | None:
    """The drawer's status chip, from the expected-position checks: the worst of them.
    None when nothing was checked (or only stated for information) -- never On Target by
    default."""
    states = {c.get("state") for c in checks or []}
    for s in ("bad", "warn", "ok"):
        if s in states:
            return {"state": STATUS[s][0], "label": STATUS[s][1]}
    return None


def headline(section) -> str | None:
    """One plain sentence for the top of the drawer, taken from what was worked out:
    the diagnosis's own headline, else its first sentence, else the worst check's."""
    d = section.get("diagnosis") or {}
    if d.get("headline"):
        return d["headline"]
    if d.get("sentences"):
        return d["sentences"][0]
    for want in ("bad", "warn"):
        for c in section["expected"]["checks"]:
            if c.get("state") == want and c.get("text"):
                return c["text"]
    return None


def _fmt(v, unit, cur) -> str:
    if v is None:
        return "—"
    if isinstance(v, str) or unit in ("date", "time", "text"):
        return str(v)
    if unit == "currency":
        return money(cur, v)
    if unit == "percent":
        return f"{flt(v):.1f}%"
    if unit == "days":
        return f"{flt(v):,.0f} days"
    return f"{flt(v):,.0f}" if float(v).is_integer() else f"{flt(v):,.2f}"


# --------------------------------------------------------------------------- the words
def as_text(s: dict) -> str:
    """Every figure in the section, in words: what the analyst is given for Explain This,
    and the Excel sheet's content. Numbers are written once, here."""
    cur = s.get("currency") or ""
    f = s.get("figure") or {}
    lines = [f"FIGURE: {s['label']}: {_fmt(f.get('value'), f.get('unit'), cur)}"
             + (f" ({f.get('note')})" if f.get("note") else ""),
             f"As at: {(s.get('as_of') or {}).get('date') or 'not stated'}",
             f"WHAT IT IS: {s['what']['text']}", f"HOW IT IS WORKED OUT: {s['what']['how']}",
             f"EXPECTED POSITION: {s['expected']['text']}"]
    for c in s["expected"]["checks"]:
        lines.append(f"- CHECK ({c['state']}): {c['label']}. {c['text']}")
    d = s.get("diagnosis") or {}
    for c in d.get("chips") or []:
        lines.append(f"- {c['label']}: {_fmt(c.get('value'), c.get('unit'), cur)}")
    b = (d.get("bridge") or {})
    if b.get("steps"):
        lines.append("RECONCILIATION BRIDGE:")
        for st in b["steps"]:
            lines.append(f"- {st['label']}: {_fmt(st['value'], 'currency', cur)}"
                         + (f" ({st['count']:,} {st['count_word']})" if st.get("count") else "")
                         + (f" [{st['kind']}]" if st["kind"] != "total" else ""))
    for sent in d.get("sentences") or []:
        lines.append(f"DIAGNOSIS: {sent}")
    c = d.get("contributors")
    if c:
        lines.append("LARGEST CONTRIBUTORS:")
        for r in c["rows"]:
            lines.append(f"- {r['party']}: {_fmt(r['value'], 'currency', cur)} ({r['share']}%)")
    u = d.get("unmatched")
    if u and u.get("oldest"):
        lines.append("OLDEST UNMATCHED PAYMENTS:")
        for i in u["oldest"]:
            lines.append(f"- {i['name']} {i['party']} {i['date']}: {_fmt(i['amount'], 'currency', cur)}")
    for t in d.get("tables") or []:
        lines.append(f"{t['title'].upper()}:")
        units = [u_ for _, u_ in t["columns"]]
        for r in t["rows"]:
            lines.append("- " + "; ".join(_fmt(v, u_, cur) if u_ != "text" else str(v)
                                          for v, u_ in zip(r["cells"], units)))
    t = s.get("trend")
    if t and t.get("points"):
        lines.append(f"TREND ({t['title']}): " + "; ".join(
            f"{p['label']} {_fmt(p['value'], t.get('unit'), cur)}" for p in t["points"]))
    for r in s.get("related") or []:
        lines.append(f"RELATED: {r.get('label')}: {_fmt(r.get('value'), r.get('unit'), cur)}")
    res = s.get("resolution") or {}
    if res.get("owner"):
        lines.append(f"OWNER: {res['owner']}")
    if res.get("order"):
        lines.append(f"ORDER: {res['order']}")
    for i, st in enumerate(res.get("steps") or [], 1):
        lines.append(f"STEP {i}: {st}")
    for p in s.get("prevention") or []:
        lines.append(f"PREVENTION: {p['text']}")
    for o in s.get("open_items") or []:
        lines.append(f"OPEN {o['kind'].upper()}: {o['title']} {o.get('why') or ''}")
    if s.get("guide"):
        lines.append(f"NOTHING RECORDED: {s['guide']['text']}")
    return "\n".join(lines)


def sheet(s: dict) -> tuple:
    """The section as one worksheet: (name, header, rows), money as numbers."""
    cur = s.get("currency") or ""
    rows = []
    add = lambda part, item, amount="", count="", detail="": rows.append(  # noqa: E731
        [part, item, amount, count, detail])
    f = s.get("figure") or {}
    add("Figure", s["label"], f.get("value") if f.get("value") is not None else "", "",
        f.get("note") or "")
    add("What it is", s["what"]["text"])
    add("How it is worked out", s["what"]["how"])
    add("Expected position", s["expected"]["text"])
    for c in s["expected"]["checks"]:
        add("Check", c["label"], "", "", f"{c['state'].upper()}: {c['text']}")
    d = s.get("diagnosis") or {}
    for c in d.get("chips") or []:
        add("Figures", c["label"], c.get("value") if c.get("value") is not None else "")
    for st in ((d.get("bridge") or {}).get("steps") or []):
        add("Reconciliation", st["label"], st["value"], st.get("count") or "",
            {"total": "level", "process": "process", "timing": "timing",
             "position": "position", "unexplained": "unexplained"}[st["kind"]])
    for sent in d.get("sentences") or []:
        add("What is driving it", sent)
    c = d.get("contributors")
    for r in (c or {}).get("rows") or []:
        add("Largest contributors", r["party"], r["value"], r.get("unmatched_count") or "",
            f"{r['share']}% of {money(cur, c['total'])}")
    u = d.get("unmatched") or {}
    for i in u.get("oldest") or []:
        add("Oldest unmatched", f"{i['name']} · {i['party']}", i["amount"], "",
            f"{i['date']} ({i['days']} days)" if i.get("days") is not None else i["date"])
    for t in d.get("tables") or []:
        for r in t["rows"]:
            cells = r["cells"]
            add(t["title"], str(cells[0]), cells[1] if len(cells) > 1 else "",
                cells[2] if len(cells) > 2 else "", "; ".join(str(x) for x in cells[3:]))
    tr = s.get("trend") or {}
    for p in tr.get("points") or []:
        add(tr.get("title") or "Trend", p["label"], p["value"] if p["value"] is not None else "")
    res = s.get("resolution") or {}
    if res.get("owner"):
        add("Who owns it", res["owner"])
    if res.get("order"):
        add("Order to tackle", res["order"])
    for i, st in enumerate(res.get("steps") or [], 1):
        add("Resolution", f"Step {i}", "", "", st)
    for st in res.get("improve") or []:
        add("How to improve", st["text"], "", "", st.get("href") or "")
    for p in s.get("prevention") or []:
        add("Prevention", p["text"], "", "", p.get("href") or "")
    for r in s.get("related") or []:
        add("Related", r.get("label"), r.get("value") if r.get("value") is not None else "")
    for o in s.get("open_items") or []:
        add(o["kind"], o["title"], o.get("money") or "", "", o.get("why") or "")
    if s.get("guide"):
        add("Nothing recorded", s["guide"]["text"], "", "", " ".join(s["guide"].get("steps") or []))
    return ("Understanding", ["Part", "Item", f"Amount {cur}".strip(), "Count", "Detail"], rows)
