"""The designed screens' charts and tables, from the business's own records.

The department screens were designed with charts and tables drawn from a 2025 extract.
This module answers, for one screen, the data behind each of its panels -- keyed by the
panel's own heading, so the screen keeps its design and its wording and only the
figures, names and dates in it change (legacy/panels.js draws them).

A panel this module does not answer stays as designed and is marked illustrative on
the screen. A panel answered with nothing (no open cases, say) says so rather than
keeping the sample.

Shapes (all numbers plain, all text plain -- the screen never treats any of it as HTML):

    bars   {"kind": "bars", "rows": [{"label", "value", "display", "note", "tone", "drill"}]}
    trend  {"kind": "trend", "labels": [...], "values": [...], "peak": "peak GHS 3,187,600"}
    stack  {"kind": "stack", "parts": [{"label", "value", "display"}]}
    table  {"kind": "table", "rows": [{"cells": [{"text", "num", "tone", "tag", "drill",
                                                   "ask", "nowrap", "bold", "small", "dot",
                                                   "sub", "sub_tone"}], "rule"}],
            "empty": "..."}
           (sub is the cell's small second line; dot a coloured bullet before the text;
           rule a line above the row, for a subtotal)
    funnel {"kind": "funnel", "stages": [{"label", "count", "display", "note", "drill"}]}
           (one per designed stage, in order)

and on any of them "subtitle" (the line under the heading) and "note" (the short
reading under the chart; "" hides the designed one, which was written about the old
figures). A drill is {"fact", "filters"} for the records drawer or {"href"} for a page
on the business's ERPNext.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from urllib.parse import quote

import frappe

from command_center.api.businesses import currency_for, require_manager
from command_center.facts.schema import FACTS

WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen", "twenty")


@frappe.whitelist()
def get(view: str, business_code: str | None = None) -> dict:
    require_manager()
    builders = SCREENS.get(view) or {}
    key = f"cc:panels:{view}:{business_code or '__all__'}"
    cached = frappe.cache().get_value(key)
    if cached:
        return cached
    ctx = _Ctx(business_code)
    panels = {}
    failed = False
    for title, fn in builders.items():
        try:
            out = fn(ctx)
        except Exception:
            failed = True
            # One panel that cannot be read must not cost the screen its others; it
            # stays as designed, marked illustrative.
            frappe.log_error(title=f"Command Center panel {view}: {title}",
                             message=frappe.get_traceback())
            continue
        if out is not None:
            panels[title] = out
    out = {"view": view, "currency": ctx.cur, "as_of": str(ctx.as_of), "panels": panels}
    # The screen's live findings, filling its designed finding boxes in order (a box
    # with none is hidden on the screen). [{"title", "text", "ask"?} or {"guide": ...}]
    if view in FINDINGS:
        try:
            out["findings"] = FINDINGS[view](ctx) or []
        except Exception:
            failed = True
            frappe.log_error(title=f"Command Center findings {view}",
                             message=frappe.get_traceback())
    # The facts change every fifteen minutes and the buying panels read the business's
    # ERPNext live, so ten minutes keeps a busy screen light on their site.
    # Only a complete answer is kept: a panel that failed (the business's ERPNext did
    # not answer, say) is asked again next time rather than staying blank for ten
    # minutes.
    if not failed:
        frappe.cache().set_value(key, out, expires_in_sec=600)
    return out


# --------------------------------------------------------------------------- helpers
class _Ctx:
    def __init__(self, business_code):
        self.code = business_code
        self.cur = currency_for(business_code) or ""
        self.as_of = _as_of(business_code)
        self._reader = None

    def rows(self, fact, fields, where=None):
        t = frappe.qb.DocType(FACTS[fact])
        q = frappe.qb.from_(t).select(*[getattr(t, f) for f in fields])
        if self.code and self.code != "__all__":
            q = q.where(t.business_code == self.code)
        for cond in (where(t) if where else []):
            q = q.where(cond)
        return [dict(zip(fields, r)) for r in q.run()]

    def kpi(self, key):
        from command_center.kpi.engine import evaluate
        return evaluate(key, self.code)

    def reader(self):
        if self._reader is None:
            from command_center.kpi.live import _Reader
            self._reader = _Guarded(_Reader(self.code))
        return self._reader

    def site(self):
        r = self.reader()
        return "" if r.local else (r.conn.base_url or "")


class _Guarded:
    """The live reader, for one screen's panels. Once the business has not answered,
    the screen's other panels give up at once instead of each waiting out the retries
    (Internal Audit took 73 s to fail with Gigmann's ERPNext down; now one wait)."""

    def __init__(self, reader):
        self._r = reader
        self._down = None

    def __getattr__(self, name):
        attr = getattr(self._r, name)
        if not callable(attr):
            return attr

        def call(*a, **k):
            from command_center.connectors.base import BusinessUnreachable
            if self._down is not None:
                raise self._down
            try:
                return attr(*a, **k)
            except BusinessUnreachable as e:
                self._down = e
                raise
        return call


def _as_of(business_code):
    t = frappe.qb.DocType(FACTS["fact_sales_invoice"])
    from frappe.query_builder.functions import Max
    q = frappe.qb.from_(t).select(Max(t.as_of_date))
    if business_code and business_code != "__all__":
        q = q.where(t.business_code == business_code)
    got = (q.run() or [[None]])[0][0]
    return frappe.utils.getdate(got) if got else frappe.utils.getdate(frappe.utils.today())


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _money(v) -> str:
    return f"{_num(v):,.0f}"


def _short(v) -> str:
    v = _num(v)
    if abs(v) >= 1e6:
        return f"{v / 1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f}k"
    return f"{v:,.0f}"


def _word(n: int) -> str:
    return WORDS[n] if 0 <= n < len(WORDS) else f"{n:,}"


def _late(days) -> str:
    d = int(days or 0)
    if d < 60:
        return f"{d} day{'s' if d != 1 else ''}"
    m = round(d / 30.4)
    return f"{m} months"


def _date(v) -> str:
    if not v:
        return ""
    return frappe.utils.getdate(v).strftime("%-d %b %Y")


def _tone_days(days) -> str:
    d = int(days or 0)
    return "crit" if d > 90 else "high" if d > 60 else "med" if d > 30 else "accent"


def _bars(rows, top=None):
    """rows: dicts with label/value/display(/note/tone/drill); widths are the screen's."""
    rows = [r for r in rows if r.get("label")]
    return {"kind": "bars", "rows": rows[:top] if top else rows}


def _months_back(as_of, n=12):
    """The n full months before the as-of month, oldest first, as (year, month)."""
    y, m = as_of.year, as_of.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append((y, m))
    return out[::-1]


def _month_labels(months):
    labels = []
    for i, (y, m) in enumerate(months):
        name = dt.date(y, m, 1).strftime("%b")
        labels.append(f"{name} {str(y)[2:]}" if i == 0 or m == 1 else name)
    return labels


def _trend(ctx, fact, date_field, amount_field, where=None):
    months = _months_back(ctx.as_of)
    first = dt.date(*months[0], 1)
    sums = defaultdict(float)
    for r in ctx.rows(fact, [date_field, amount_field],
                      lambda t: [getattr(t, date_field) >= first] + (where(t) if where else [])):
        d = frappe.utils.getdate(r[date_field]) if r[date_field] else None
        if d:
            sums[(d.year, d.month)] += _num(r[amount_field])
    values = [round(sums.get(k, 0.0), 2) for k in months]
    if not any(values):
        return None
    last = dt.date(*months[-1], 1)
    return {"kind": "trend", "labels": _month_labels(months), "values": values,
            "peak": f"peak {ctx.cur} {_money(max(values))}".strip(),
            "period": f"{_word(len(months))} months to {last.strftime('%B %Y')}"}


# --------------------------------------------------------------------------- sales
def sales_trend(ctx):
    return _trend(ctx, "fact_sales_order", "transaction_date", "base_grand_total",
                  lambda t: [t.src_docstatus == 1])


def _owed_by_customer(ctx):
    rows = ctx.rows("fact_sales_invoice", ["customer", "outstanding_amount", "days_overdue",
                                           "ageing_bucket"],
                    lambda t: [t.outstanding_amount > 0, t.src_docstatus == 1])
    by = defaultdict(lambda: {"owed": 0.0, "days": 0, "n": 0, "buckets": defaultdict(float)})
    for r in rows:
        c = by[r["customer"]]
        c["owed"] += _num(r["outstanding_amount"])
        c["days"] = max(c["days"], int(r["days_overdue"] or 0))
        c["n"] += 1
        c["buckets"][r["ageing_bucket"]] += _num(r["outstanding_amount"])
    ranked = sorted(by.items(), key=lambda kv: -kv[1]["owed"])
    return ranked, sum(v["owed"] for v in by.values()), len(rows)


def sales_largest_owed(ctx):
    ranked, total, _ = _owed_by_customer(ctx)
    top = ranked[:10]
    if not top:
        return {"kind": "bars", "rows": [], "empty": "Nobody owes the business anything."}
    held = sum(v["owed"] for _, v in top)
    share = round(100 * held / total) if total else 0
    if len(top) == len(ranked):
        out = _bars([{
            "label": c, "value": v["owed"], "display": _money(v["owed"]),
            "tone": _tone_days(v["days"]),
            "drill": {"fact": "fact_sales_invoice",
                      "filters": {"customer": c, "outstanding_amount": [">", 0],
                                  "src_docstatus": 1}},
        } for c, v in top])
        out["subtitle"] = (f"{ctx.cur} · {'the only customer' if len(top) == 1 else f'all {_word(len(top))} customers'} "
                           f"who owe us, {ctx.cur} {_money(held)} between them")
        return out
    out = _bars([{
        "label": c, "value": v["owed"], "display": _money(v["owed"]),
        "tone": _tone_days(v["days"]),
        "drill": {"fact": "fact_sales_invoice",
                  "filters": {"customer": c, "outstanding_amount": [">", 0], "src_docstatus": 1}},
    } for c, v in top])
    out["subtitle"] = (f"{ctx.cur} · the {_word(len(top))} largest hold {ctx.cur} {_money(held)}, "
                       f"{share}% of all money owed")
    return out


def sales_ageing(ctx):
    ranked, _, _ = _owed_by_customer(ctx)
    top = ranked[:10]
    if not top:
        return None
    b = defaultdict(float)
    for _, v in top:
        for k, amt in v["buckets"].items():
            b[k] += amt
    under1 = b["Not yet due"] + b["0-30"] + b["Unknown"]
    parts = [("Under 1 month", under1), ("1–2 months", b["31-60"]),
             ("2–3 months", b["61-90"]), ("Over 3 months", b["90+"])]
    total = sum(v for _, v in parts) or 1
    over = b["90+"]
    # Inside ninety days across every unpaid invoice, as the designed reading had it.
    inside = ctx.rows("fact_sales_invoice", ["outstanding_amount"],
                      lambda t: [t.outstanding_amount > 0, t.src_docstatus == 1,
                                 t.ageing_bucket != "90+"])
    inside_amt = sum(_num(r["outstanding_amount"]) for r in inside)
    note = (f"{round(100 * over / total)}% of what the ten largest owe is beyond three months. "
            f"{ctx.cur} {_short(inside_amt)} across {len(inside):,} invoices is still inside "
            f"ninety days.")
    return {"kind": "stack", "parts": [{"label": l, "value": v, "display": _money(v)}
                                       for l, v in parts], "note": note}


def sales_not_despatched(ctx):
    rows = ctx.rows("fact_sales_order", ["src_name", "customer", "undelivered_value",
                                         "per_delivered", "days_late"],
                    lambda t: [t.src_docstatus == 1, t.is_open == 1, t.per_delivered < 100,
                               t.undelivered_value > 0])
    rows.sort(key=lambda r: -_num(r["undelivered_value"]))
    out = []
    for r in rows[:8]:
        pct = _num(r["per_delivered"])
        out.append({"cells": [
            {"text": r["src_name"], "drill": {"fact": "fact_sales_order",
                                              "filters": {"src_name": r["src_name"]}}},
            {"text": r["customer"] or ""},
            {"text": _money(r["undelivered_value"]), "num": True},
            {"text": "None of it" if pct <= 0 else f"{pct:.0f}%", "tone": "dim"},
            {"ask": f"Why is the {r['customer']} order {r['src_name']} still open?",
             "text": "Ask why"},
        ]})
    return {"kind": "table", "rows": out, "empty": "Every order taken has been despatched."}


# --------------------------------------------------------------------------- buying (read live)
def _pos(ctx):
    """Submitted purchase orders, read once per screen. A failed read is remembered too,
    so an unreachable business costs one wait, not one per panel."""
    if not hasattr(ctx, "_pos"):
        try:
            ctx._pos = ctx.reader().all(
                "Purchase Order", filters={"docstatus": 1},
                fields=["name", "supplier", "base_grand_total", "transaction_date",
                        "schedule_date", "per_received", "per_billed", "status"])
        except Exception as e:
            ctx._pos = e
    if isinstance(ctx._pos, Exception):
        raise ctx._pos
    return ctx._pos


def proc_money(ctx):
    top = sorted(_pos(ctx), key=lambda r: -_num(r.get("base_grand_total")))[:14]
    if not top:
        return None
    by = defaultdict(lambda: [0.0, 0])
    for r in top:
        by[r.get("supplier")][0] += _num(r.get("base_grand_total"))
        by[r.get("supplier")][1] += 1
    ranked = sorted(by.items(), key=lambda kv: -kv[1][0])
    first = ranked[0][1][0] if ranked else 0
    site = ctx.site()
    out = _bars([{
        "label": s, "value": v, "display": _money(v),
        "note": f"{n} order{'s' if n != 1 else ''}",
        "tone": "crit" if v == first and len(ranked) > 1 and v > 0.5 * sum(x[0] for _, x in ranked)
        else "accent",
        "drill": {"href": f"{site}/app/purchase-order?supplier={quote(s or '')}"},
    } for s, (v, n) in ranked])
    out["subtitle"] = f"{ctx.cur}, {_word(len(top))} largest orders"
    return out


def proc_lead(ctx):
    by = defaultdict(list)
    undated = defaultdict(int)
    for r in _pos(ctx):
        if not r.get("transaction_date"):
            continue
        if not r.get("schedule_date"):
            undated[r.get("supplier")] += 1
            continue
        d = frappe.utils.date_diff(r["schedule_date"], r["transaction_date"])
        by[r.get("supplier")].append(max(0, d))
    if not by:
        return None
    ranked = sorted(by.items(), key=lambda kv: -len(kv[1]))[:8]
    site = ctx.site()
    rows = []
    for s, days in ranked:
        avg = round(sum(days) / len(days))
        note = f"{len(days)} order{'s' if len(days) != 1 else ''}"
        if len(days) > 1:
            note += f" · longest {max(days)} days"
        if undated.get(s):
            note += f" · {undated[s]} with no date set"
        rows.append({"label": s, "value": avg, "display": f"{avg} days", "note": note,
                     "tone": "crit" if avg > 60 else "high" if avg > 30 else "accent",
                     "drill": {"href": f"{site}/app/purchase-order?supplier={quote(s or '')}"}})
    return _bars(rows)


def proc_open(ctx):
    top = sorted(_pos(ctx), key=lambda r: -_num(r.get("base_grand_total")))[:14]
    if not top:
        return None
    still = [r for r in top if (r.get("status") not in ("Completed", "Closed"))
             and (_num(r.get("per_received")) < 100 or _num(r.get("per_billed")) < 100)]
    site = ctx.site()
    rows = []
    for r in still:
        where = ("Still to receive" if _num(r.get("per_received")) < 100 else "Still to bill")
        rows.append({"cells": [
            {"text": r["name"], "drill": {"href": f"{site}/app/purchase-order/{r['name']}"}},
            {"text": r.get("supplier") or ""},
            {"text": _money(r.get("base_grand_total")), "num": True},
            {"text": where, "tag": "t-wt"},
        ]})
    n = len(top)
    note = (f"{_word(len(still)).capitalize()} of the {_word(n)} largest "
            f"{'is' if len(still) == 1 else 'are'} still open."
            + (" The rest are complete." if still and len(still) < n else ""))
    return {"kind": "table", "rows": rows, "empty": f"All {_word(n)} of the largest are complete.",
            "note": note if still else ""}


# --------------------------------------------------------------------------- stock
def inv_where(ctx):
    rows = ctx.rows("fact_stock_balance", ["warehouse", "stock_value"])
    by = defaultdict(float)
    for r in rows:
        by[r["warehouse"]] += _num(r["stock_value"])
    ranked = [kv for kv in sorted(by.items(), key=lambda kv: -kv[1]) if kv[1] > 0]
    if not ranked:
        return None
    top, rest = ranked[:6], ranked[6:]
    out = [{"label": w, "value": v, "display": _money(v), "tone": "accent",
            "drill": {"fact": "fact_stock_balance", "filters": {"warehouse": w}}}
           for w, v in top]
    if rest:
        v = sum(x for _, x in rest)
        out.append({"label": "Other locations", "value": v, "display": _money(v), "tone": "dim",
                    "note": f"{len(rest)} more"})
    return _bars(out)


def inv_reserved(ctx):
    rows = ctx.rows("fact_stock_balance", ["item_code", "warehouse", "reserved_qty",
                                           "actual_qty"],
                    lambda t: [t.reserved_qty > 0])
    short = []
    for r in rows:
        gap = _num(r["reserved_qty"]) - _num(r["actual_qty"])
        if gap > 0:
            short.append((gap, r))
    short.sort(key=lambda x: -x[0])
    out = [{"cells": [
        {"text": r["item_code"] or ""},
        {"text": r["warehouse"] or "", "tone": "mut"},
        {"text": f"{_num(r['reserved_qty']):,.0f}", "num": True},
        {"text": f"{_num(r['actual_qty']):,.0f}", "num": True},
        {"text": f"{gap:,.0f}", "num": True, "tone": "crit"},
    ]} for gap, r in short[:8]]
    res = {"kind": "table", "rows": out,
           "empty": "Nothing is reserved beyond what is in stock."}
    if short:
        res["subtitle"] = f"Worst {_word(min(8, len(short)))} of {len(short):,}"
    return res


# --------------------------------------------------------------------------- projects (tasks)
def _tasks(ctx):
    return ctx.rows("fact_task", ["src_name", "subject", "project", "project_name", "status",
                                  "assigned_to", "exp_end_date", "days_late", "is_open",
                                  "is_assigned"])


def eng_capacity(ctx):
    tasks = _tasks(ctx)
    open_ = [t for t in tasks if t["is_open"]]
    if not tasks:
        return None
    assigned = [t for t in open_ if t["is_assigned"]]
    people = ctx.rows("fact_person", ["designation", "is_active"], lambda t: [t.is_active == 1])
    engineers = [p for p in people if "engineer" in (p["designation"] or "").lower()]
    top = max(len(open_), 1)
    rows = [{"label": "Open jobs", "value": len(open_), "display": str(len(open_)), "tone": "high",
             "drill": {"fact": "fact_task", "filters": {"is_open": 1}}},
            {"label": "Jobs with someone on them", "value": len(assigned),
             "display": str(len(assigned)), "tone": "accent",
             "drill": {"fact": "fact_task", "filters": {"is_open": 1, "is_assigned": 1}}},
            {"label": "Engineers available", "value": len(engineers),
             "display": str(len(engineers)), "tone": "accent",
             "drill": {"fact": "fact_person", "filters": {"is_active": 1,
                                                          "designation": ["like", "%ngineer%"]}}}]
    for r in rows:
        r["value"] = min(r["value"], top) if r["label"] != "Open jobs" else r["value"]
    nobody = len(open_) - len(assigned)
    who = ("every one of them assigned" if nobody == 0 else
           f"{_word(nobody)} of them with nobody assigned")
    note = (f"{_word(len(engineers)).capitalize()} engineer{'s' if len(engineers) != 1 else ''}, "
            f"{_word(len(open_))} open job{'s' if len(open_) != 1 else ''}, {who}."
            ) if open_ else ""
    out = _bars(rows)
    out["note"] = note
    return out


def eng_late(ctx):
    late = [t for t in _tasks(ctx) if t["is_open"] and int(t["days_late"] or 0) > 0]
    late.sort(key=lambda t: -int(t["days_late"] or 0))
    rows = [{"cells": [
        {"text": t["subject"] or t["src_name"],
         "drill": {"fact": "fact_task", "filters": {"src_name": t["src_name"]}}},
        {"text": t["project_name"] or "—"},
        {"text": _date(t["exp_end_date"]), "nowrap": True},
        {"text": _late(t["days_late"]), "tone": "crit", "nowrap": True},
        {"text": t["status"] or ""},
        {"text": t["assigned_to"] or "Nobody", "tone": "" if t["assigned_to"] else "high"},
        {"ask": f"Why is the {t['subject'] or t['src_name']} job still open?", "text": "Ask why"},
    ]} for t in late[:12]]
    return {"kind": "table", "rows": rows, "empty": "No open job is past its promised date."}


def eng_open(ctx):
    tasks = _tasks(ctx)
    open_ = [t for t in tasks if t["is_open"]]
    open_.sort(key=lambda t: -int(t["days_late"] or 0))
    rows = []
    for t in open_[:15]:
        d = int(t["days_late"] or 0)
        rows.append({"cells": [
            {"text": t["subject"] or t["src_name"]},
            {"text": t["project_name"] or "—"},
            {"text": t["status"] or "", "tone": "mut"},
            {"text": f"{_late(d)} late" if d > 0 else "On time",
             "tag": "t-od" if d > 0 else "t-ok"},
        ]})
    res = {"kind": "table", "rows": rows, "empty": "No open jobs."}
    if tasks:
        res["subtitle"] = f"{len(open_):,} open of {len(tasks):,} in total"
    return res


# --------------------------------------------------------------------------- service (cases)
def cx_open(ctx):
    cases = ctx.rows("fact_case", ["subject", "customer", "days_open", "priority", "src_name"],
                     lambda t: [t.is_open == 1])
    cases.sort(key=lambda c: -int(c["days_open"] or 0))
    rows = [{"cells": [
        {"text": c["subject"] or c["src_name"],
         "drill": {"fact": "fact_case", "filters": {"src_name": c["src_name"]}}},
        {"text": c["customer"] or "—"},
        {"text": f"{int(c['days_open'] or 0)} days",
         "tone": "crit" if int(c["days_open"] or 0) > 14 else ""},
        {"text": c["priority"] or "", "tag": "t-od" if (c["priority"] or "") in ("High", "Urgent")
         else "t-wt"},
        {"ask": f"Tell me about the {c['customer'] or c['subject']} case", "text": "Ask"},
    ]} for c in cases[:10]]
    return {"kind": "table", "rows": rows, "empty": "No open cases in ERPNext."}


def cx_causes(ctx):
    cases = ctx.rows("fact_case", ["issue_type"])
    by = defaultdict(int)
    for c in cases:
        by[c["issue_type"] or "Not given"] += 1
    ranked = sorted(by.items(), key=lambda kv: -kv[1])
    res = _bars([{"label": k, "value": n, "display": str(n), "tone": "accent",
                  "drill": {"fact": "fact_case", "filters": {"issue_type": k}}
                  if k != "Not given" else None} for k, n in ranked[:8]])
    res["subtitle"] = f"All {_word(len(cases))} cases" if cases else "No cases recorded"
    res["empty"] = "No cases recorded in ERPNext."
    if ranked:
        k, n = ranked[0]
        res["note"] = (f"{_word(n).capitalize()} of {_word(len(cases))} "
                       f"{'is' if n == 1 else 'are'} {k.lower()}.")
    else:
        res["note"] = ""
    return res


# --------------------------------------------------------------------------- finances
def fin_money_in(ctx):
    out = _trend(ctx, "fact_payment_allocation", "posting_date", "allocated_amount",
                 lambda t: [t.payment_type == "Receive", t.src_docstatus == 1])
    if out:
        out["subtitle"] = f"Monthly, {out['period']}"
    return out


def fin_working_capital(ctx):
    rows = []
    for key, label, tone in (("ar_over_90", "Owed to us, over 3 months", "crit"),
                             ("stock_value", "Stock in warehouses", "accent"),
                             ("order_book", "Orders taken, not despatched", "accent")):
        f = ctx.kpi(key)
        if f.get("value") is None:
            continue
        rows.append({"label": label, "value": _num(f["value"]), "display": _money(f["value"]),
                     "tone": tone, "drill": f.get("drill")})
    if not rows:
        return None
    out = _bars(rows)
    owed = rows[0]["value"] if rows[0]["label"].startswith("Owed") else 0
    stock = next((r["value"] for r in rows if r["label"] == "Stock in warehouses"), 0)
    out["note"] = (f"{ctx.cur} {_short(owed)} is owed to the business for over three months, "
                   f"against {ctx.cur} {_short(stock)} held in stock." if owed and stock else "")
    return out


# --------------------------------------------------------------------------- people
def _people(ctx):
    return ctx.rows("fact_person", ["department", "branch", "status", "is_active"])


def hr_departments(ctx):
    by = defaultdict(int)
    for p in _people(ctx):
        if p["is_active"]:
            by[p["department"] or "No department"] += 1
    if not by:
        return None
    ranked = sorted(by.items(), key=lambda kv: -kv[1])
    return _bars([{"label": d, "value": n, "display": str(n), "tone": "accent",
                   "drill": {"fact": "fact_person", "filters": {"department": d, "is_active": 1}}
                   if d != "No department" else None} for d, n in ranked[:12]])


def hr_where(ctx):
    people = _people(ctx)
    if not people:
        return None
    by = defaultdict(int)
    for p in people:
        if p["is_active"]:
            by[p["branch"] or "No branch"] += 1
    ranked = sorted(by.items(), key=lambda kv: -kv[1])
    status = defaultdict(int)
    for p in people:
        status[p["status"] or "Active"] += 1
    out = _bars([{"label": b, "value": n, "display": str(n), "tone": "accent",
                  "drill": {"fact": "fact_person", "filters": {"branch": b, "is_active": 1}}
                  if b != "No branch" else None} for b, n in ranked[:8]])
    out["stack"] = [{"label": s, "value": status.get(s, 0), "display": str(status.get(s, 0))}
                    for s in ("Active", "Inactive", "Left")]
    return out


# --------------------------------------------------------------------------- read live, shared
def _guarded(ctx, doctype, filters, fields, **kw):
    """A live read that refuses a reply missing a column (see kpi/live._read)."""
    from command_center.kpi.live import _read
    return _read(ctx.reader(), doctype, filters, fields, **kw)


def _names(ctx, users):
    """Account -> the person's name, in one read."""
    users = sorted({u for u in users if u})
    if not users:
        return {}
    rows = ctx.reader().all("User", filters={"name": ["in", users]},
                            fields=["name", "full_name"], limit=len(users))
    got = {r["name"]: r.get("full_name") or r["name"] for r in rows}
    return {u: got.get(u, u) for u in users}


def _month(v) -> str:
    return frappe.utils.getdate(v).strftime("%b %Y") if v else "never"


# --------------------------------------------------------------------------- sales: funnel
def sales_funnel(ctx):
    """Enquiries, opportunities, quotations and orders, over the whole history. Orders
    are the loaded fact (every submitted sales order); the rest are counted live."""
    r = ctx.reader()
    leads = r.count("Lead")
    opps = r.count("Opportunity")
    quotes = _guarded(ctx, "Quotation", {"docstatus": 1}, ["base_grand_total"])
    orders = ctx.rows("fact_sales_order", ["base_grand_total"], lambda t: [t.src_docstatus == 1])
    q_val = sum(_num(x.get("base_grand_total")) for x in quotes)
    o_val = sum(_num(x["base_grand_total"]) for x in orders)
    site = ctx.site()

    def seen(n):
        return "Not used at all" if not n else f"{n:,} in the whole system"
    stages = [
        {"label": "Enquiries", "count": leads, "note": seen(leads),
         "drill": {"href": f"{site}/app/lead"}},
        {"label": "Opportunities", "count": opps, "note": seen(opps),
         "drill": {"href": f"{site}/app/opportunity"}},
        {"label": "Quotations", "count": len(quotes),
         "display": f"{ctx.cur} {_money(q_val)}".strip() if quotes else None,
         "note": f"{len(quotes):,} against {len(orders):,} orders",
         "drill": {"href": f"{site}/app/quotation?docstatus=1"}},
        {"label": "Orders", "count": len(orders),
         "display": f"{ctx.cur} {_money(o_val)}".strip() if orders else None,
         "note": "", "drill": {"fact": "fact_sales_order", "filters": {"src_docstatus": 1}}},
    ]
    return {"kind": "funnel", "stages": stages}


# --------------------------------------------------------------------------- projects: late jobs and money
def eng_late_cost(ctx):
    """Customers waiting on late jobs, beside what they owe. The customer is the job's
    project's, read live; what they owe is the loaded receivable."""
    late = [t for t in _tasks(ctx) if t["is_open"] and int(t["days_late"] or 0) > 0]
    if not late:
        return {"kind": "table", "rows": [], "empty": "No open job is past its promised date."}
    projects = sorted({t["project"] for t in late if t["project"]})
    customer_of = {}
    if projects:
        customer_of = {p["name"]: p.get("customer") for p in _guarded(
            ctx, "Project", {"name": ["in", projects]}, ["name", "customer"])}
    ranked, _, _ = _owed_by_customer(ctx)
    owed = dict(ranked)

    groups = defaultdict(list)
    for t in late:
        groups[customer_of.get(t["project"]) or t["project_name"] or "—"].append(t)
    rows = []
    for who, ts in groups.items():
        known = who in owed
        o = owed.get(who, {}).get("owed", 0.0) if known else 0.0
        over = owed.get(who, {}).get("buckets", {}).get("90+", 0.0) if known else 0.0
        what = sorted({t["subject"] or t["src_name"] for t in ts})
        due = min((t["exp_end_date"] for t in ts if t["exp_end_date"]), default=None)
        days = max(int(t["days_late"] or 0) for t in ts)
        is_customer = any(customer_of.get(t["project"]) for t in ts)
        rows.append((o, days, {"cells": [
            {"text": who, "tone": "" if is_customer else "mut"},
            {"text": ", ".join(what[:3]) + (f" and {len(what) - 3} more" if len(what) > 3 else "")},
            {"text": _date(due), "nowrap": True},
            {"text": _late(days), "tone": "crit", "nowrap": True},
            {"text": _money(o) if o else "—", "num": True, "tone": "crit" if over else "dim"},
            ({"ask": f"{who} is waiting on late jobs and owes us {ctx.cur} {_money(o)}. "
                     f"What are both sides?", "text": "Both sides"} if o else {"text": ""}),
        ]}))
    rows.sort(key=lambda x: (-x[0], -x[1]))
    return {"kind": "table", "rows": [r for _, _, r in rows[:10]],
            "empty": "No open job is past its promised date."}


# --------------------------------------------------------------------------- audit: approvals and history
APPROVAL_DOCS = (("Purchase Order", "Purchase order", "supplier", "base_grand_total"),
                 ("Payment Entry", "Payment", "party", "base_paid_amount"))


def _approval_rows(ctx, doctype, party, value):
    """Every purchase order (or payment) with its approval stage, read once per screen.

    Without the stage where the doctype has no workflow: there is no workflow_state
    column then, and the site refuses the field by name."""
    cache = ctx.__dict__.setdefault("_approvals", {})
    if doctype not in cache:
        fields = ["name", "docstatus", "status", "owner", party, value]
        try:
            cache[doctype] = (_guarded(ctx, doctype, {}, fields + ["workflow_state"]), True)
        except Exception as e:
            if "workflow_state" not in str(e):
                raise
            cache[doctype] = (_guarded(ctx, doctype, {}, fields), False)
    return cache[doctype]


def _stage(row, has_wf) -> str:
    if row.get("docstatus") == 0:
        return "Draft — never submitted"
    if row.get("docstatus") == 2:
        return "Cancelled"
    return (row.get("workflow_state") if has_wf else None) or row.get("status") or "Submitted"


def aud_where_approvals(ctx):
    rows = []
    for doctype, word, party, value in APPROVAL_DOCS:
        docs, has_wf = _approval_rows(ctx, doctype, party, value)
        by = defaultdict(lambda: [0, 0.0])
        for d in docs:
            k = _stage(d, has_wf)
            by[k][0] += 1
            by[k][1] += _num(d.get(value))
        order = sorted(by, key=lambda k: (k != "Draft — never submitted", k == "Cancelled",
                                          -by[k][0]))
        for k in order:
            n, v = by[k]
            dot = ("crit" if k.startswith("Draft") else "dim" if k == "Cancelled" else
                   "ok" if "approv" in k.lower() else "med")
            rows.append({"cells": [
                {"text": k, "dot": dot, "sub": word},
                {"text": f"{n:,}", "num": True},
                {"text": f"{ctx.cur} {_money(v)}".strip(), "tone": "mut", "small": True},
            ]})
    return {"kind": "table", "rows": rows, "empty": "No purchase orders or payments recorded."}


def aud_decisions(ctx):
    """The largest purchase orders and payments that were decided -- submitted through
    their approvals, or withdrawn -- and where each ended."""
    got = []
    for doctype, word, party, value in APPROVAL_DOCS:
        docs, has_wf = _approval_rows(ctx, doctype, party, value)
        got += [(d, doctype, word, party, value, has_wf) for d in docs
                if d.get("docstatus") in (1, 2)]
    got.sort(key=lambda x: -_num(x[0].get(x[4])))
    got = got[:15]
    who = _names(ctx, [d.get("owner") for d, *_ in got])
    site = ctx.site()
    rows = []
    for d, doctype, word, party, value, has_wf in got:
        ended = _stage(d, has_wf)
        slug = frappe.scrub(doctype).replace("_", "-")
        rows.append({"cells": [
            {"text": d["name"], "sub": word, "drill": {"href": f"{site}/app/{slug}/{d['name']}"}},
            {"text": d.get(party) or "—", "sub": f"raised by {who.get(d.get('owner'), '—')}"},
            {"text": _money(d.get(value)), "num": True},
            {"text": ended, "tag": "t-dr" if ended == "Cancelled" else
             "t-ok" if "approv" in ended.lower() else "t-wt"},
            {"text": ""},
        ]})
    return {"kind": "table", "rows": rows, "empty": "No purchase order or payment decided yet."}


def aud_never_submitted(ctx):
    docs = _guarded(ctx, "Purchase Order", {"docstatus": 0},
                    ["name", "supplier", "base_grand_total", "transaction_date", "owner"])
    docs.sort(key=lambda d: -_num(d.get("base_grand_total")))
    who = _names(ctx, [d.get("owner") for d in docs])
    site = ctx.site()
    rows = [{"cells": [
        {"text": d["name"], "drill": {"href": f"{site}/app/purchase-order/{d['name']}"}},
        {"text": d.get("supplier") or "—"},
        {"text": _money(d.get("base_grand_total")), "num": True,
         "tone": "crit" if _num(d.get("base_grand_total")) > 50000 else ""},
        {"text": _date(d.get("transaction_date")), "nowrap": True, "tone": "mut"},
        {"text": who.get(d.get("owner"), "—")},
        {"text": "never submitted", "tag": "t-od"},
    ]} for d in docs]
    return {"kind": "table", "rows": rows,
            "empty": "Every purchase order raised has been submitted."}


HISTORY_ROWS = (("Customer payments", "Payment Entry"), ("Customer invoices", "Sales Invoice"),
                ("Customer orders", "Sales Order"), ("Stock movements", "Stock Entry"),
                ("Purchase orders", "Purchase Order"))


def aud_history(ctx):
    """The change log, by what was changed -- the same counts as the cards above it."""
    from command_center.kpi.live import BUSINESS_DOCTYPES
    r = ctx.reader()
    named = [(label, dt_, r.count("Version", {"ref_doctype": dt_})) for label, dt_ in HISTORY_ROWS]
    business = r.count("Version", {"ref_doctype": ["in", list(BUSINESS_DOCTYPES)]})
    total = r.count("Version")
    rest = max(business - sum(n for *_, n in named), 0)
    rows = [{"cells": [{"text": label, "sub": dt_}, {"text": f"{n:,}", "num": True}]}
            for label, dt_, n in named]
    rows += [
        {"cells": [{"text": "Everything else on business records"},
                   {"text": f"{rest:,}", "num": True}]},
        {"rule": True,
         "cells": [{"text": "Changes to business records", "bold": True},
                   {"text": f"{business:,}", "num": True, "bold": True}]},
        {"cells": [{"text": "Settings, permissions and system changes", "tone": "mut"},
                   {"text": f"{max(total - business, 0):,}", "num": True, "tone": "mut"}]},
        {"cells": [{"text": "Everything recorded", "bold": True},
                   {"text": f"{total:,}", "num": True, "bold": True}]},
    ]
    return {"kind": "table", "rows": rows, "empty": "Nothing recorded."}


# --------------------------------------------------------------------------- systems and access
def _accounts(ctx):
    from command_center.kpi.live import CONFLICTS, KEY_ROLES
    r = ctx.reader()
    users = [u for u in _guarded(ctx, "User", {"user_type": "System User"},
                                 ["name", "full_name", "enabled", "last_active", "last_login"])
             if u["name"] not in ("Administrator", "Guest")]
    held = defaultdict(list)
    for row in r.all("Has Role", filters={"parenttype": "User", "role": ["in", list(KEY_ROLES)]},
                     fields=["parent", "role"], limit=20000, parent="User"):
        if row.get("role") in KEY_ROLES:
            held[row["parent"]].append(row["role"])
    out = []
    for u in users:
        roles = sorted(set(held.get(u["name"], [])), key=KEY_ROLES.index)
        clash = [say for a, b, say in CONFLICTS if set(roles) & set(a) and set(roles) & set(b)]
        out.append({**u, "roles": roles, "conflicts": clash,
                    "seen": u.get("last_active") or u.get("last_login")})
    out.sort(key=lambda u: (-len(u["conflicts"]), -len(u["roles"]), u.get("full_name") or ""))
    return out


def _person(u):
    return {"text": u.get("full_name") or u["name"], "sub": u["name"]}


def it_who_can_get_in(ctx):
    live = [u for u in _accounts(ctx) if u.get("enabled")]
    rows = []
    for u in live:
        n = len(u["conflicts"])
        rows.append({"cells": [
            _person(u),
            {"text": " · ".join(u["roles"]) or "none of the business roles", "tone": "mut",
             "small": True, "sub": "; ".join(u["conflicts"]) or None, "sub_tone": "crit"},
            {"text": str(len(u["roles"])), "num": True},
            {"text": f"{n} conflict{'s' if n != 1 else ''}" if n else "clear",
             "tag": "t-od" if n else "t-ok"},
            {"text": _month(u["seen"]), "tone": "mut", "nowrap": True},
        ]})
    return {"kind": "table", "rows": rows, "subtitle": f"{len(live):,} active accounts",
            "empty": "No active staff accounts."}


def it_switched_off(ctx):
    off = [u for u in _accounts(ctx) if not u.get("enabled")]
    rows = [{"cells": [
        _person(u),
        {"text": " · ".join(u["roles"]) or "none", "tone": "mut", "small": True},
        {"text": str(len(u["roles"])), "num": True},
        {"text": "Sign-in blocked", "tag": "t-ok"},
        {"text": _month(u["seen"]), "tone": "mut", "nowrap": True},
    ]} for u in off]
    still = sum(1 for u in off if u["roles"])
    note = (f"{_word(still).capitalize()} of them still {'has' if still == 1 else 'have'} "
            f"roles attached, so re-enabling {'it' if still == 1 else 'one'} restores "
            f"everything it had." if still else "")
    return {"kind": "table", "rows": rows, "subtitle": f"{len(off):,} account{'s' if len(off) != 1 else ''}",
            "empty": "No account is switched off.", "note": note}


# view -> fn(ctx) returning that screen's live findings (see get()). Screens register
# here; a screen without an entry has its designed finding boxes hidden.
FINDINGS: dict = {}

SCREENS = {
    "sales": {
        "How sales have moved": sales_trend,
        "Who owes us, and how long it has been": sales_ageing,
        "Largest balances owed": sales_largest_owed,
        "Orders taken but not despatched": sales_not_despatched,
        "From enquiry to order": sales_funnel,
    },
    "proc": {
        "Where the money goes": proc_money,
        "How long each supplier takes": proc_lead,
        "Orders still open": proc_open,
    },
    "inv": {
        "Where the value sits": inv_where,
        "Reserved against what is available": inv_reserved,
    },
    "eng": {
        "Can we actually deliver the work we are holding?": eng_capacity,
        "Every job past its promised date": eng_late,
        "Every open job": eng_open,
        "What the late jobs are costing us": eng_late_cost,
    },
    "cx": {
        "Open cases, longest wait first": cx_open,
        "What they are complaining about": cx_causes,
    },
    "fin": {
        "Money coming in": fin_money_in,
        "Working capital tied up": fin_working_capital,
    },
    "hr": {
        "Where people work": hr_departments,
        "Where people are": hr_where,
    },
    "aud": {
        "Decisions taken": aud_decisions,
        "Where approvals currently sit": aud_where_approvals,
        "Raised and never submitted": aud_never_submitted,
        "How much history there is": aud_history,
    },
    "it": {
        "Who can get into ERPNext today, and what they can do": it_who_can_get_in,
        "Accounts that are switched off": it_switched_off,
    },
}
