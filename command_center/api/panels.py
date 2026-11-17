"""The designed screens' charts and tables, from the business's own records.

This module answers, for one screen, the data behind each of its panels -- keyed by the
panel's own heading, so the screen keeps its design and its wording and only the
figures, names and dates in it come from the business (legacy/panels.js draws them).

Every panel on a department screen is answered: with its figures, with an empty answer
that says so ("No open cases"), or -- when ERPNext records nothing of the kind at all --
with a guide to what to record there (command_center/guides.py). When the business's
ERPNext cannot be reached, a panel that reads it live answers {"kind": "unreachable"}
and the screen says so; panels drawn from the loaded facts still show them.

Shapes (all numbers plain, all text plain -- the screen never treats any of it as HTML):

    bars   {"kind": "bars", "rows": [{"label", "value", "display", "note", "tone", "drill"}]}
    trend  {"kind": "trend", "labels": [...], "values": [...], "peak": "peak GHS 3,187,600"}
    stack  {"kind": "stack", "parts": [{"label", "value", "display"}]}
    table  {"kind": "table", "rows": [{"cells": [{"text", "num", "tone", "tag", "drill",
                                                   "ask", "nowrap", "bold", "small", "dot",
                                                   "sub", "sub_tone"}], "rule"}],
            "empty": "...", "columns": [{"text", "num", "cur"}]}
           (sub is the cell's small second line; dot a coloured bullet before the text;
           rule a line above the row, for a subtotal; columns the headings, for a panel
           designed without a table)
    funnel {"kind": "funnel", "stages": [{"label", "count", "display", "note", "drill"}]}
           (one per designed stage, in order)
    list   {"kind": "list", "items": [{"text", "bold"}]}   (the panel's bullet list)
    guide  {"kind": "guide", "guide": guide(...)}
    unreachable {"kind": "unreachable"}

and on any of them "subtitle" (the line under the heading) and "note" (the short
reading under the chart; "" hides the designed one). A drill is {"fact", "filters"} for
the records drawer or {"href"} for a page on the business's ERPNext.
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
    from command_center import speed
    # Kept per business and per whose view of its ERPNext (speed.py): a complete answer
    # is returned at once while it is fresh, and read again in the background once it
    # is not; the scheduler reads the screens people look at again after each refresh.
    out = speed.cached("panels", business_code, {"view": view}, compute,
                       {"view": view, "business_code": business_code}, complete=complete)
    return {k: v for k, v in out.items() if k != "_failed"}


def compute(view: str, business_code: str | None = None) -> dict:
    """The screen's panels, findings and line under the heading, read now. Each panel is
    independent of the others, so they are read side by side (speed.parallel); a panel
    that fails is that panel's problem, as before."""
    from command_center import speed
    from command_center.kpi.live_departments import is_down
    builders = SCREENS.get(view) or {}
    with speed.interactive():
        ctx = _Ctx(business_code)
        try:
            ctx.reader()  # one guarded reader, shared by every panel's thread
        except Exception:
            pass  # asked again (and failing as that panel's problem) where it is needed
        extra = [(name, table[view]) for name, table in (("findings", FINDINGS), ("when", WHEN))
                 if view in table]
        jobs = list(builders.items()) + extra
        answers = speed.parallel([(lambda fn=fn: fn(ctx)) for _, fn in jobs])
    panels = {}
    failed = down = False
    out = {"view": view, "currency": ctx.cur, "as_of": str(ctx.as_of), "panels": panels}
    from command_center.kpi.live import _refused
    for (title, _), (ok, got) in zip(jobs[:len(builders)], answers[:len(builders)]):
        if not ok:
            failed = True  # asked again next time, a refusal too (access may be granted)
            if _refused(got):
                # Refused by the business's ERPNext: the record type and how to give the
                # platform's API user read access to it, drawn as the panel's guide.
                from command_center.guides import no_access
                st = no_access(ctx.code, got)
                panels[title] = {"kind": "guide", "guide": st["guide"], "no_access": True,
                                 "doctype": st.get("doctype")}
                continue
            if is_down(got):
                # The business did not answer: the panel says so, calmly, and is asked
                # again next time.
                down = True
                panels[title] = {"kind": "unreachable"}
                continue
            # One panel that cannot be read must not cost the screen its others.
            frappe.log_error(title=f"Command Center panel {view}: {title}",
                             message=getattr(got, "__cc_traceback__", "") or repr(got))
            panels[title] = {"kind": "failed"}
            continue
        if got is not None:
            panels[title] = got
    # The screen's live findings, filling its designed finding boxes in order (a box
    # with none is hidden on the screen). [{"title", "text", "ask"?} or {"guide": ...}]
    for (name, _), (ok, got) in zip(extra, answers[len(builders):]):
        if ok:
            out[name] = got or ([] if name == "findings" else "")
            continue
        failed = True
        down = down or is_down(got)
        if not is_down(got):
            frappe.log_error(title=f"Command Center {name} {view}",
                             message=getattr(got, "__cc_traceback__", "") or repr(got))
    if down:
        out.update({"unreachable": True, **ctx.business()})
    # Only a complete answer is kept (complete()): a panel that failed is asked again
    # next time.
    out["_failed"] = failed
    return out


def complete(out) -> bool:
    return isinstance(out, dict) and not out.get("_failed") and not out.get("unreachable")


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

    def business(self) -> dict:
        """The business's name and when its facts were last loaded, for "can't reach"."""
        from command_center.api.businesses import default_business_code
        code = self.code if self.code and self.code != "__all__" else default_business_code()
        row = frappe.db.get_value("Connected Business", {"business_code": code},
                                  ["business_name", "last_sync"], as_dict=True) or {}
        return {"business": row.get("business_name") or code or "",
                "last_loaded": str(row["last_sync"]) if row.get("last_sync") else None}


class _Guarded:
    """The live reader, for one screen's panels. Once the business has not answered,
    the screen's other panels give up at once instead of each waiting out the retries
    (Internal Audit took 73 s to fail with Gigmann's ERPNext down; now one wait)."""

    # Reads asked for twice on one screen (the staff list behind four figures, the
    # purchase orders behind three panels) go to the business once, even when they are
    # asked for at the same moment from two threads (speed.parallel).
    MEMO = ("all", "count", "has")

    def __init__(self, reader):
        import threading
        self._r = reader
        self._down = None
        self._memo = {}
        self._lock = threading.Lock()
        # Already known to be down (the shell's banner says so): fail at once rather than
        # make every screen wait out the retries first. The 15-minute refresh and the
        # banner's Retry still reach out, and the first answer marks the business Active.
        conn = getattr(reader, "conn", None)
        business = getattr(conn, "business", None) if conn is not None else None
        if business is not None and getattr(business, "status", None) == "Unreachable":
            from command_center.connectors.base import BusinessUnreachable
            self._down = BusinessUnreachable(
                f"{getattr(conn, 'name', 'The business')} is marked unreachable")

    def __getattr__(self, name):
        attr = getattr(self._r, name)
        if not callable(attr):
            return attr

        def call(*a, **k):
            from command_center.kpi.live_departments import is_down
            if self._down is not None:
                raise self._down
            try:
                return attr(*a, **k)
            except Exception as e:
                # A refused read (a field that site does not have) is that panel's
                # problem; only a business that did not answer stops the others.
                if is_down(e):
                    self._down = e
                raise
        if name not in self.MEMO:
            return call

        def once(*a, **k):
            import json
            import threading
            key = (name, json.dumps([a, k], sort_keys=True, default=str))
            with self._lock:
                slot = self._memo.get(key)
                mine = slot is None
                if mine:
                    slot = self._memo[key] = {"done": threading.Event()}
            if mine:
                try:
                    slot["value"] = call(*a, **k)
                except Exception as e:
                    slot["error"] = e
                finally:
                    slot["done"].set()
            else:
                slot["done"].wait()
            if "error" in slot:
                raise slot["error"]
            got = slot["value"]
            # Each caller its own rows: a panel may add to the ones it is handed.
            return [type(r)(r) if isinstance(r, dict) else r for r in got] if isinstance(got, list) else got
        return once


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


def _guide(ctx, text, steps, path):
    from command_center.guides import guide
    return {"kind": "guide", "guide": guide(ctx.code, text, steps, path)}


def _cols(*heads):
    """Headings for a panel designed without a table: "Value$" is a number column
    carrying the currency; a leading "#" marks any other number column."""
    out = []
    for h in heads:
        num = h.endswith("$") or h.startswith("#")
        out.append({"text": h.strip("#$"), "num": num, "cur": h.endswith("$")})
    return out


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
SO_STEPS = ["Open Sales Order, click New, choose the customer and add the items.",
            "Submit the order when the customer confirms it.",
            "Deliver against it (Create, Delivery Note) and invoice it (Create, Sales Invoice)."]


def sales_trend(ctx):
    out = _trend(ctx, "fact_sales_order", "transaction_date", "base_grand_total",
                 lambda t: [t.src_docstatus == 1])
    return out or _guide(ctx, "No confirmed sales order in the last twelve months.", SO_STEPS,
                         "/app/sales-order")


# --------------------------------------------------------------------------- owed, by the ledger
# What each customer and supplier owes is their General Ledger balance (fact_party_balance,
# ingest/ledger.py), aged after the payments never matched to an invoice are set against
# the oldest open items. The open invoices' own figure is shown beside it with the reason
# for the difference, in plain words.
POSITION_FIELDS = ["party", "ledger_balance", "owed", "in_credit", "open_invoices",
                   "open_invoice_count", "unmatched_payments", "unmatched_payment_count",
                   "unlinked_journals", "unlinked_credit_notes", "other_unlinked",
                   "unlinked_debits", "invoices_not_updated", "unexplained", "not_due",
                   "d0_30", "d31_60", "d61_90", "d90_plus", "undated", "inside_90", "overdue",
                   "oldest_due_after_matching", "days_overdue"]
_DATE_OR_NAME = ("party", "oldest_due_after_matching")
# Each reason the open invoices and the ledger differ, as a manager would say it:
# (column, sign, customer wording, supplier wording). sign -1 is a reason the ledger is
# higher than the invoices.
REASONS = (
    ("unmatched_payments", 1, "received but never matched to invoices",
     "paid but never matched to their bills"),
    ("invoices_not_updated", 1, "already paid or credited against invoices that still show it unpaid",
     "already paid or credited against bills that still show it unpaid"),
    ("unlinked_journals", 1, "of journal entries reducing the balance, not linked to any invoice",
     "of journal entries reducing what we owe, not linked to any bill"),
    ("unlinked_credit_notes", 1, "of credit notes never set against the original invoice",
     "of debit notes never set against the original bill"),
    ("other_unlinked", 1, "paid against orders or journal entries rather than invoices",
     "paid against purchase orders or journal entries rather than bills"),
    ("unlinked_debits", -1, "owed on journal entries or refunds that are on no invoice, such as opening balances",
     "owed on journal entries or refunds that are on no bill, such as opening balances"),
)
PARTY_WORDS = {"Customer": ("customer", "customers", "invoices"),
               "Supplier": ("supplier", "suppliers", "bills")}


def _positions(ctx, party_type):
    rows = ctx.rows("fact_party_balance", POSITION_FIELDS,
                    lambda t: [t.party_type == party_type])
    for r in rows:
        for k in POSITION_FIELDS:
            if k not in _DATE_OR_NAME:
                r[k] = _num(r[k])
    return rows


def _sum(rows, key):
    return sum(r[key] for r in rows)


def _amt(v) -> str:
    """GHS 341,565 under a million; GHS 10.07M above it."""
    return _short(v) if abs(_num(v)) >= 1e6 else _money(v)


def _why(r, cur, party_type) -> str:
    """The plain reasons a party's open invoices and ledger balance differ."""
    side = 2 if party_type == "Customer" else 3
    parts = []
    for row in REASONS:
        col, sign, words = row[0], row[1], row[side]
        v = r[col]
        if abs(v) < 0.5:
            continue
        if col == "invoices_not_updated" and v < 0:
            parts.append((abs(v), f"the {PARTY_WORDS[party_type][2]} show {cur} {_amt(-v)} less "
                                  f"than the ledger holds against them"))
        elif col == "other_unlinked" and v < 0:
            parts.append((abs(v), f"{cur} {_amt(-v)} of other ledger entries adding to the balance"))
        else:
            parts.append((abs(v), f"{cur} {_amt(v)} {words}"))
    parts.sort(key=lambda x: -x[0])
    out = [t for _, t in parts]
    if abs(r["unexplained"]) >= 0.5:
        out.append(f"the ledger and the {PARTY_WORDS[party_type][2]} disagree by {cur} "
                   f"{_amt(abs(r['unexplained']))} for reasons the records do not show")
    return "; ".join(out)


def _summary(ctx, party_type, rows) -> str:
    """What is owed by the ledger, what the invoices say, and why -- in words that add up:
    the open invoices less the reasons is the ledger's net balance, and the net balance is
    what is owed less what those in credit hold."""
    one, many, docs = PARTY_WORDS[party_type]
    cur = ctx.cur
    owed, on_docs, net = _sum(rows, "owed"), _sum(rows, "open_invoices"), _sum(rows, "ledger_balance")
    credit = [r for r in rows if r["in_credit"] > 0]
    lead = (f"{many.capitalize()} owe {cur} {_amt(owed)} by the ledger" if party_type == "Customer"
            else f"We owe {many} {cur} {_amt(owed)} by the ledger")
    if credit:
        held = _sum(credit, "in_credit")
        lead += (f", and {_plural(len(credit), one)} {'is' if len(credit) == 1 else 'are'} in credit "
                 f"by {cur} {_amt(held)} (paid in advance, or more than "
                 f"{'billed' if party_type == 'Customer' else 'they billed'}), so on balance "
                 + (f"they owe {cur} {_amt(net)}" if party_type == "Customer"
                    else f"we owe {cur} {_amt(net)}"))
    tot = {k: _sum(rows, k) for k in POSITION_FIELDS if k not in _DATE_OR_NAME}
    why = _why(tot, cur, party_type)
    if abs(on_docs - net) < 0.5 and not why:
        return f"{lead}, as the open {docs} say."
    return (f"{lead}. The open {docs} say {cur} {_amt(on_docs)}"
            + (f" because of: {why}." if why else "."))


def _ledger_href(ctx, party_type, party):
    """The party's account in the business's own General Ledger report."""
    from command_center.guides import site_url
    to = ctx.as_of
    frm = frappe.utils.add_days(to, -365)
    return (f"{site_url(ctx.code)}/app/query-report/General%20Ledger?party_type={quote(party_type)}"
            f"&party={quote(party)}&from_date={frm}&to_date={to}")


def _money_or_dash(v):
    return _money(v) if abs(_num(v)) >= 0.5 else "—"


def _ledger_rows(ctx, party_type, rows, top):
    one, many, _ = PARTY_WORDS[party_type]
    ranked = sorted(rows, key=lambda r: -max(r["open_invoices"], r["owed"], r["in_credit"]))
    out = []
    for r in ranked[:top]:
        diff = r["open_invoices"] - r["ledger_balance"]
        out.append({"cells": [
            {"text": r["party"] or "—", "drill": {"href": _ledger_href(ctx, party_type, r["party"])},
             "sub": (f"in credit by {_money(r['in_credit'])}" if r["in_credit"] > 0 else
                     f"{_plural(int(r['open_invoice_count']), 'open ' + ('invoice' if party_type == 'Customer' else 'bill'))}")},
            {"text": _money_or_dash(r["open_invoices"]), "num": True, "tone": "mut"},
            {"text": _money(r["ledger_balance"]), "num": True, "bold": True,
             "tone": "ok" if r["ledger_balance"] < 0 else ""},
            {"text": _money_or_dash(diff), "num": True,
             "tone": "high" if abs(diff) >= 0.5 else "mut"},
            {"text": _why(r, ctx.cur, party_type) or "They agree.", "small": True},
            {"text": _money_or_dash(r["not_due"]), "num": True},
            {"text": _money_or_dash(r["d0_30"]), "num": True},
            {"text": _money_or_dash(r["d31_60"]), "num": True},
            {"text": _money_or_dash(r["d61_90"]), "num": True},
            {"text": _money_or_dash(r["d90_plus"]), "num": True,
             "tone": "crit" if r["d90_plus"] >= 0.5 else ""},
        ]})
    t = {k: _sum(rows, k) for k in ("open_invoices", "ledger_balance", "not_due", "d0_30",
                                    "d31_60", "d61_90", "d90_plus")}
    out.append({"rule": True, "cells": [
        {"text": f"All {len(rows):,} {many}", "bold": True,
         "sub": f"the {_word(min(top, len(rows)))} largest shown" if len(rows) > top else None},
        {"text": _money(t["open_invoices"]), "num": True, "bold": True},
        {"text": _money(t["ledger_balance"]), "num": True, "bold": True,
         "sub": (f"{_money(_sum(rows, 'owed'))} owed, {_money(_sum(rows, 'in_credit'))} in credit"
                 if _sum(rows, "in_credit") >= 0.5 else None)},
        {"text": _money(t["open_invoices"] - t["ledger_balance"]), "num": True, "bold": True},
        {"text": ""},
        {"text": _money(t["not_due"]), "num": True, "bold": True},
        {"text": _money(t["d0_30"]), "num": True, "bold": True},
        {"text": _money(t["d31_60"]), "num": True, "bold": True},
        {"text": _money(t["d61_90"]), "num": True, "bold": True},
        {"text": _money(t["d90_plus"]), "num": True, "bold": True},
    ]})
    return out


LEDGER_COLUMNS = ("On Open Invoices$", "Ledger Balance$", "Difference$", "Why", "#Not Yet Due",
                  "#1–30 Days", "#31–60 Days", "#61–90 Days", "#Over 90 Days")


def _ledger_table(ctx, party_types, top):
    tables, notes = [], []
    for pt in party_types:
        rows = _positions(ctx, pt)
        if rows:
            tables += _ledger_rows(ctx, pt, rows, top[pt])
            notes.append(_summary(ctx, pt, rows))
    head = "Customer" if party_types == ("Customer",) else "Customer or Supplier"
    out = {"kind": "table", "rows": tables, "columns": _cols(head, *LEDGER_COLUMNS),
           "empty": ("No customer holds a balance in the ledger." if party_types == ("Customer",)
                     else "No customer or supplier holds a balance in the ledger.")}
    if notes:
        out["subtitle"] = notes[0]
        out["note"] = " ".join(notes[1:]) + (" " if len(notes) > 1 else "") + (
            "Ageing is after the payments not yet matched are set against the oldest open "
            "items first. Each name opens its account in ERPNext's General Ledger.")
    return out


def sales_ledger(ctx):
    return _ledger_table(ctx, ("Customer",), {"Customer": 12})


def fin_ledger(ctx):
    return _ledger_table(ctx, ("Customer", "Supplier"), {"Customer": 12, "Supplier": 8})


def _owed_by_customer(ctx):
    rows = [r for r in _positions(ctx, "Customer") if r["owed"] > 0]
    ranked = sorted(rows, key=lambda r: -r["owed"])
    return ranked, _sum(rows, "owed"), len(rows)


def _owing_drill(party):
    return {"fact": "fact_party_balance",
            "filters": {"party_type": "Customer", "party": party, "owed": [">", 0]}}


def sales_largest_owed(ctx):
    ranked, total, _ = _owed_by_customer(ctx)
    top = ranked[:10]
    if not top:
        return {"kind": "bars", "rows": [], "empty": "Nobody owes the business anything, by the ledger."}
    held = sum(r["owed"] for r in top)
    share = round(100 * held / total) if total else 0
    out = _bars([{
        "label": r["party"], "value": r["owed"], "display": _money(r["owed"]),
        "tone": _tone_days(r["days_overdue"]),
        "note": (f"open invoices say {_money(r['open_invoices'])}"
                 if abs(r["open_invoices"] - r["owed"]) >= 0.5 else None),
        "drill": _owing_drill(r["party"]),
    } for r in top])
    if len(top) == len(ranked):
        out["subtitle"] = (f"{ctx.cur} · {'the only customer' if len(top) == 1 else f'all {_word(len(top))} customers'} "
                           f"who owe us by the ledger, {ctx.cur} {_money(held)} between them")
    else:
        out["subtitle"] = (f"{ctx.cur} · the {_word(len(top))} largest hold {ctx.cur} {_money(held)}, "
                           f"{share}% of all money owed by the ledger")
    return out


def sales_ageing(ctx):
    ranked, _, n = _owed_by_customer(ctx)
    top = ranked[:10]
    if not top:
        return {"kind": "stack", "parts": [{"label": l, "value": 0, "display": "0"} for l in
                                           ("Under 1 month", "1–2 months", "2–3 months",
                                            "Over 3 months")],
                "note": "Nobody owes the business anything, by the ledger."}
    b = {k: sum(r[k] for r in top) for k in ("not_due", "d0_30", "d31_60", "d61_90", "d90_plus",
                                              "undated")}
    parts = [("Under 1 month", b["not_due"] + b["d0_30"]), ("1–2 months", b["d31_60"]),
             ("2–3 months", b["d61_90"]), ("Over 3 months", b["d90_plus"])]
    total = sum(v for _, v in parts) or 1
    inside_amt = _sum(ranked, "inside_90")
    inside_n = sum(1 for r in ranked if r["inside_90"] > 0)
    note = (f"{round(100 * b['d90_plus'] / total)}% of what the {_word(len(top))} largest owe is beyond "
            f"three months, after payments not yet matched are set against their oldest invoices. "
            f"{ctx.cur} {_short(inside_amt)} owed by {_plural(inside_n, 'customer')} is still inside "
            f"ninety days.")
    if b["undated"] >= 0.5:
        note += (f" {ctx.cur} {_money(b['undated'])} is owed by the ledger with no invoice or entry "
                 f"to date it, and is not in the bar.")
    return {"kind": "stack", "parts": [{"label": l, "value": v, "display": _money(v)}
                                       for l, v in parts], "note": note}


def sales_not_despatched(ctx):
    rows = ctx.rows("fact_sales_order", ["src_name", "customer", "undelivered_value",
                                         "base_grand_total", "days_late"],
                    lambda t: [t.src_docstatus == 1, t.is_open == 1, t.undelivered_value > 0])
    rows.sort(key=lambda r: -_num(r["undelivered_value"]))
    out = []
    for r in rows[:8]:
        # The share of the order's value delivered, from the line-by-line value still to
        # deliver -- never ERPNext's per_delivered, which is a share of quantity.
        value = _num(r["base_grand_total"])
        pct = 100 * (1 - _num(r["undelivered_value"]) / value) if value > 0 else 0
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
                fields=["name", "supplier", "base_grand_total", "base_net_total",
                        "transaction_date", "schedule_date", "per_received", "per_billed",
                        "status"])
        except Exception as e:
            ctx._pos = e
    if isinstance(ctx._pos, Exception):
        raise ctx._pos
    return ctx._pos


PO_STEPS = ["Open Purchase Order, click New, choose the supplier and add the items.",
            "Set Required By to the date the supplier agreed to deliver.",
            "Submit it once it is approved."]


def _no_pos(ctx):
    return _guide(ctx, "No purchase order has been submitted in ERPNext yet.", PO_STEPS,
                  "/app/purchase-order/new")


def proc_money(ctx):
    top = sorted(_pos(ctx), key=lambda r: -_num(r.get("base_grand_total")))[:14]
    if not top:
        return _no_pos(ctx)
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
        return _no_pos(ctx) if not _pos(ctx) else _guide(
            ctx, "No purchase order carries a date the supplier promised.",
            ["Open each open Purchase Order.", "Set Required By to the date the supplier "
             "agreed to deliver, then Update Items (or set it before submitting)."],
            "/app/purchase-order?docstatus=1")
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
        return _no_pos(ctx)
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
STOCK_STEPS = ["Receive goods from suppliers with a Purchase Receipt (from the Purchase "
               "Order: Create, Purchase Receipt), choosing the warehouse they go into.",
               "Stock already on the shelf: enter it once with a Stock Reconciliation, "
               "giving the quantity and valuation rate per warehouse."]


def inv_where(ctx):
    rows = ctx.rows("fact_stock_balance", ["warehouse", "stock_value"])
    by = defaultdict(float)
    for r in rows:
        by[r["warehouse"]] += _num(r["stock_value"])
    ranked = [kv for kv in sorted(by.items(), key=lambda kv: -kv[1]) if kv[1] > 0]
    if not ranked:
        return _guide(ctx, "No stock with a value is recorded in ERPNext.", STOCK_STEPS,
                      "/app/stock-entry/new")
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


TASK_STEPS = ["Open Project, click New for each installation or service job, and set the "
              "Customer.", "Add the work as Tasks, each with an Expected End Date.",
              "Assign each task to the engineer doing it (the Assign To in the sidebar)."]


def eng_capacity(ctx):
    tasks = _tasks(ctx)
    open_ = [t for t in tasks if t["is_open"]]
    if not tasks:
        return _guide(ctx, "No project task is recorded in ERPNext.", TASK_STEPS, "/app/project")
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


def _project_info(ctx, projects):
    """Project -> its customer and type, read once per screen."""
    cache = ctx.__dict__.setdefault("_projects", {})
    want = sorted({p for p in projects if p and p not in cache})
    for i in range(0, len(want), 200):
        for p in _guarded(ctx, "Project", {"name": ["in", want[i:i + 200]]},
                          ["name", "customer", "project_type"]):
            cache[p["name"]] = p
    return cache


def eng_late(ctx):
    late = [t for t in _tasks(ctx) if t["is_open"] and int(t["days_late"] or 0) > 0]
    late.sort(key=lambda t: -int(t["days_late"] or 0))
    late = late[:12]
    info = _project_info(ctx, [t["project"] for t in late])
    progress = {}
    if late:
        progress = {x["name"]: x.get("progress") for x in _guarded(
            ctx, "Task", {"name": ["in", [t["src_name"] for t in late]]}, ["name", "progress"])}
    rows = [{"cells": [
        {"text": t["subject"] or t["src_name"],
         "drill": {"fact": "fact_task", "filters": {"src_name": t["src_name"]}}},
        {"text": (info.get(t["project"]) or {}).get("customer") or "—"},
        {"text": _date(t["exp_end_date"]), "nowrap": True},
        {"text": _late(t["days_late"]), "tone": "crit", "nowrap": True},
        {"text": f"{_num(progress.get(t['src_name'])):.0f}%" if _num(progress.get(t["src_name"]))
         else ("Not started" if (t["status"] or "") == "Open" else t["status"] or "")},
        {"text": t["assigned_to"] or "Nobody", "tone": "" if t["assigned_to"] else "high"},
        {"ask": f"Why is the {t['subject'] or t['src_name']} job still open?", "text": "Ask why"},
    ]} for t in late]
    return {"kind": "table", "rows": rows, "empty": "No open job is past its promised date."}


def eng_open(ctx):
    tasks = _tasks(ctx)
    open_ = [t for t in tasks if t["is_open"]]
    open_.sort(key=lambda t: -int(t["days_late"] or 0))
    shown = open_[:15]
    info = _project_info(ctx, [t["project"] for t in shown])
    rows = []
    for t in shown:
        d = int(t["days_late"] or 0)
        p = info.get(t["project"]) or {}
        rows.append({"cells": [
            {"text": t["subject"] or t["src_name"],
             "drill": {"fact": "fact_task", "filters": {"src_name": t["src_name"]}}},
            {"text": p.get("customer") or "—", "tone": "" if p.get("customer") else "mut"},
            {"text": p.get("project_type") or "Not set", "tone": "mut"},
            {"text": f"{_late(d)} late" if d > 0 else
             ("No date set" if not t["exp_end_date"] else "On time"),
             "tag": "t-od" if d > 0 else ("t-wt" if not t["exp_end_date"] else "t-ok")},
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
    # Every receipt once (payment_amount), as Money In's card counts it -- not the part
    # matched to invoices.
    out = _trend(ctx, "fact_payment_allocation", "posting_date", "payment_amount",
                 lambda t: [t.payment_type == "Receive", t.src_docstatus == 1])
    if out:
        out["subtitle"] = f"Monthly, {out['period']}"
        return out
    return _guide(ctx, "No payment received in the last twelve months is recorded in ERPNext.",
                  ["Record each payment received with Payment Entry (from the Sales Invoice: "
                   "Create, Payment).", "Allocate it against the invoices it pays in the "
                   "References table, then Submit."], "/app/payment-entry/new")


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
        return {"kind": "bars", "rows": [], "empty": "Nothing is tied up.", "note": ""}
    out = _bars(rows)
    owed = rows[0]["value"] if rows[0]["label"].startswith("Owed") else 0
    stock = next((r["value"] for r in rows if r["label"] == "Stock in warehouses"), 0)
    out["note"] = (f"{ctx.cur} {_short(owed)} is owed to the business for over three months, "
                   f"against {ctx.cur} {_short(stock)} held in stock." if owed and stock else "")
    return out


# --------------------------------------------------------------------------- people
def _people(ctx):
    return ctx.rows("fact_person", ["department", "branch", "status", "is_active"])


PEOPLE_STEPS = ["Open Employee, click New for each person, and set Department, Designation "
                "and Branch.", "Set Status to Left, with the Relieving Date, when someone goes."]


def hr_departments(ctx):
    by = defaultdict(int)
    for p in _people(ctx):
        if p["is_active"]:
            by[p["department"] or "No department"] += 1
    if not by:
        return _guide(ctx, "No active employee is recorded in ERPNext.", PEOPLE_STEPS,
                      "/app/employee/new")
    ranked = sorted(by.items(), key=lambda kv: -kv[1])
    return _bars([{"label": d, "value": n, "display": str(n), "tone": "accent",
                   "drill": {"fact": "fact_person", "filters": {"department": d, "is_active": 1}}
                   if d != "No department" else None} for d, n in ranked[:12]])


def hr_where(ctx):
    people = _people(ctx)
    if not people:
        return _guide(ctx, "No employee is recorded in ERPNext.", PEOPLE_STEPS,
                      "/app/employee/new")
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
    project's, read live; what they owe is their ledger balance."""
    late = [t for t in _tasks(ctx) if t["is_open"] and int(t["days_late"] or 0) > 0]
    if not late:
        return {"kind": "table", "rows": [], "empty": "No open job is past its promised date."}
    projects = sorted({t["project"] for t in late if t["project"]})
    customer_of = {}
    if projects:
        customer_of = {p["name"]: p.get("customer") for p in _guarded(
            ctx, "Project", {"name": ["in", projects]}, ["name", "customer"])}
    ranked, _, _ = _owed_by_customer(ctx)
    owed = {r["party"]: r for r in ranked}

    groups = defaultdict(list)
    for t in late:
        groups[customer_of.get(t["project"]) or t["project_name"] or "—"].append(t)
    rows = []
    for who, ts in groups.items():
        known = who in owed
        o = owed[who]["owed"] if known else 0.0
        over = owed[who]["d90_plus"] if known else 0.0
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
        fields = ["name", "docstatus", "status", "owner", "amended_from", party, value]
        try:
            docs, has_wf = _guarded(ctx, doctype, {}, fields + ["workflow_state"]), True
        except Exception as e:
            if "workflow_state" not in str(e):
                raise
            docs, has_wf = _guarded(ctx, doctype, {}, fields), False
        # An original cancelled to be amended was replaced by its amendment, which stands
        # in its place: counting both says one order twice, the first time as "Cancelled"
        # (kpi/live.withdrawn -- read here from the rows already in hand).
        gone = {d.get("amended_from") for d in docs if d.get("amended_from")}
        cache[doctype] = ([d for d in docs if not (d.get("docstatus") == 2 and d["name"] in gone)],
                          has_wf)
    return cache[doctype]


def _stage(row, has_wf) -> str:
    """Where a document stands. Its rows come from _approval_rows, which has left out the
    originals cancelled to be amended: "Cancelled" here is withdrawn."""
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


# =========================================================================== department screens:
# the "Not yet measured" panels, the line under each heading, and the findings.
def _today():
    return frappe.utils.getdate(frappe.utils.today())


def _days_ago(n):
    return str(frappe.utils.add_days(_today(), -n))


def _grouped(ctx, doctype, filters, group_by, aggs, parent=None):
    from command_center.kpi.live_departments import grouped
    return grouped(ctx.reader(), doctype, filters, group_by, aggs, parent=parent)


def _count(ctx, doctype, filters=None):
    return ctx.reader().count(doctype, filters or {})


def _has(ctx, doctype):
    return ctx.reader().has(doctype)


def _pct(a, b):
    return round(100 * a / b) if b else 0


def _plural(n, word, many=None):
    return f"{n:,} {word if n == 1 else (many or word + 's')}"


# --------------------------------------------------------------------------- sales: discounts
PRICE_STEPS = ["Open Item Price (or the Price List \"Standard Selling\") and give each item "
               "its selling price.",
               "Allowed discounts go in Pricing Rule: choose the items or item group, the "
               "customers, and the discount percentage.",
               "Invoices then carry the price-list rate, so any price typed below it shows "
               "here."]


def sales_discounts(ctx):
    """Invoice lines in the last twelve months sold below their price-list rate with no
    pricing rule behind them: a discount typed in by hand, outside any recorded policy."""
    since = _days_ago(365)
    lines = _guarded(ctx, "Sales Invoice Item",
                     {"docstatus": 1, "discount_amount": [">", 0], "creation": [">=", since]},
                     ["parent", "item_code", "qty", "price_list_rate", "rate", "discount_amount",
                      "pricing_rules"], parent="Sales Invoice", limit=20000)
    if not lines and not _count(ctx, "Sales Invoice Item", {"docstatus": 1,
                                                            "price_list_rate": [">", 0]}):
        return _guide(ctx, "No invoice line carries a price-list price, so a discount "
                           "cannot be told from a normal price.", PRICE_STEPS,
                      "/app/item-price")
    loose = [x for x in lines if not (x.get("pricing_rules") or "").strip()
             and _num(x.get("price_list_rate")) > _num(x.get("rate"))]
    cust = {r["src_name"]: r["customer"] for r in ctx.rows(
        "fact_sales_invoice", ["src_name", "customer"],
        lambda t: [t.src_name.isin(sorted({x["parent"] for x in loose}) or ["-"])])}
    for x in loose:
        x["given"] = (_num(x.get("price_list_rate")) - _num(x.get("rate"))) * _num(x.get("qty"))
    loose.sort(key=lambda x: -x["given"])
    site = ctx.site()
    rows = [{"cells": [
        {"text": x["parent"], "drill": {"href": f"{site}/app/sales-invoice/{x['parent']}"}},
        {"text": cust.get(x["parent"]) or "—"},
        {"text": x.get("item_code") or ""},
        {"text": _money(x.get("price_list_rate")), "num": True, "tone": "mut"},
        {"text": _money(x.get("rate")), "num": True},
        {"text": f"{_pct(_num(x['price_list_rate']) - _num(x['rate']), _num(x['price_list_rate']))}%",
         "num": True, "tone": "high"},
        {"text": _money(x["given"]), "num": True, "tone": "crit"},
    ]} for x in loose[:12]]
    total = sum(x["given"] for x in loose)
    return {"kind": "table", "rows": rows,
            "columns": _cols("Invoice", "Customer", "Product", "List price$", "Sold at$",
                             "#Below list", "Given away$"),
            "empty": "No invoice line in the last twelve months was sold below its "
                     "price-list price outside a pricing rule.",
            "note": (f"{_plural(len(loose), 'line')} in the last twelve months, "
                     f"{ctx.cur} {_money(total)} below list in all."
                     if loose else "")}


# --------------------------------------------------------------------------- buying
def proc_checks(ctx):
    """Unpaid supplier invoices not resting on both a purchase order and a goods receipt
    (or an invoice that itself received the goods)."""
    unpaid = ctx.rows("fact_purchase_invoice", ["src_name", "supplier", "outstanding_amount",
                                                "due_date"],
                      lambda t: [t.src_docstatus == 1, t.outstanding_amount > 0])
    cols = _cols("Invoice", "Supplier", "Owed$", "What is missing")
    if not unpaid:
        return {"kind": "table", "rows": [], "columns": cols,
                "empty": "Nothing is owed to suppliers."}
    names = sorted({u["src_name"] for u in unpaid})
    lines, heads = [], {}
    for i in range(0, len(names), 200):
        part = names[i:i + 200]
        lines += _guarded(ctx, "Purchase Invoice Item", {"parent": ["in", part]},
                          ["parent", "purchase_order", "purchase_receipt"],
                          parent="Purchase Invoice", limit=100000)
        heads.update({h["name"]: h for h in _guarded(
            ctx, "Purchase Invoice", {"name": ["in", part]}, ["name", "update_stock"])})
    gaps = defaultdict(set)
    for x in lines:
        if not x.get("purchase_order"):
            gaps[x["parent"]].add("No purchase order")
        if not x.get("purchase_receipt") and not int((heads.get(x["parent"]) or {}).get(
                "update_stock") or 0):
            gaps[x["parent"]].add("No goods receipt")
    flagged = sorted([u for u in unpaid if gaps.get(u["src_name"])],
                     key=lambda u: -_num(u["outstanding_amount"]))
    site = ctx.site()
    rows = [{"cells": [
        {"text": u["src_name"], "drill": {"href": f"{site}/app/purchase-invoice/{u['src_name']}"}},
        {"text": u["supplier"] or "—"},
        {"text": _money(u["outstanding_amount"]), "num": True},
        {"text": " · ".join(sorted(gaps[u["src_name"]])), "tag": "t-od"},
    ]} for u in flagged[:12]]
    held = sum(_num(u["outstanding_amount"]) for u in flagged)
    return {"kind": "table", "rows": rows, "columns": cols,
            "empty": "Every unpaid supplier invoice rests on a purchase order and a goods receipt.",
            "note": (f"{_word(len(flagged)).capitalize() if len(flagged) <= 20 else f'{len(flagged):,}'} of "
                     f"{len(unpaid):,} unpaid supplier invoices, {ctx.cur} {_money(held)} between "
                     f"them, should be checked before they are paid." if flagged else "")}


def proc_performance(ctx):
    """Per supplier: of the orders received, how many arrived by the date asked for, and
    how much was turned away at the door."""
    lines = _guarded(ctx, "Purchase Receipt Item", {"docstatus": 1, "purchase_order": ["is", "set"]},
                     ["parent", "purchase_order", "received_qty", "rejected_qty"],
                     parent="Purchase Receipt", limit=50000)
    if not lines:
        return _guide(ctx, "No goods receipt in ERPNext is linked to a purchase order, so "
                           "nothing says when an order actually arrived.",
                      ["Open the Purchase Order when the goods arrive.",
                       "Click Create, then Purchase Receipt, so the receipt carries the order.",
                       "Enter any quantity turned away in Rejected Qty, then Submit."],
                      "/app/purchase-receipt")
    receipts = {}
    parents = sorted({x["parent"] for x in lines})
    for i in range(0, len(parents), 200):
        for h in _guarded(ctx, "Purchase Receipt", {"name": ["in", parents[i:i + 200]]},
                          ["name", "posting_date", "supplier"]):
            receipts[h["name"]] = h
    pos = {p["name"]: p for p in _pos(ctx)}
    first = {}
    got = defaultdict(lambda: [0.0, 0.0])
    for x in lines:
        h = receipts.get(x["parent"]) or {}
        po = x["purchase_order"]
        if h.get("posting_date"):
            d = frappe.utils.getdate(h["posting_date"])
            first[po] = min(first.get(po, d), d)
        sup = h.get("supplier") or (pos.get(po) or {}).get("supplier")
        got[sup][0] += _num(x.get("received_qty"))
        got[sup][1] += _num(x.get("rejected_qty"))
    by = defaultdict(lambda: [0, 0])
    for po, arrived in first.items():
        p = pos.get(po)
        if not p or not p.get("schedule_date"):
            continue
        late = arrived > frappe.utils.getdate(p["schedule_date"])
        by[p.get("supplier")][0] += 1
        by[p.get("supplier")][1] += int(late)
    if not by:
        return _guide(ctx, "The orders that were received carry no Required By date to "
                           "measure them against.", ["Set Required By on each Purchase Order "
                                                     "to the date the supplier agreed."],
                      "/app/purchase-order")
    site = ctx.site()
    rows = []
    for sup, (n, late) in sorted(by.items(), key=lambda kv: -kv[1][0])[:8]:
        on = _pct(n - late, n)
        recv, rej = got.get(sup, [0, 0])
        note = f"{_plural(n, 'order')} · {late} late"
        if rej:
            note += f" · {_pct(rej, recv)}% turned away"
        rows.append({"label": sup or "—", "value": on, "display": f"{on}% on time", "note": note,
                     "tone": "ok" if on >= 90 else "med" if on >= 70 else "crit",
                     "drill": {"href": f"{site}/app/purchase-receipt?supplier={quote(sup or '')}"}})
    out = _bars(rows)
    out["note"] = "Each order is on time when its first goods receipt is dated on or before the date the order asked for."
    return out


def proc_advances(ctx):
    pays = _guarded(ctx, "Payment Entry", {"docstatus": 1, "payment_type": "Pay",
                                           "party_type": "Supplier", "unallocated_amount": [">", 0]},
                    ["name", "party", "posting_date", "unallocated_amount", "target_exchange_rate"])
    for x in pays:
        x["base"] = _num(x.get("unallocated_amount")) * (_num(x.get("target_exchange_rate")) or 1)
    pays.sort(key=lambda x: -x["base"])
    site = ctx.site()
    rows = [{"cells": [
        {"text": x.get("party") or "—"},
        {"text": x["name"], "drill": {"href": f"{site}/app/payment-entry/{x['name']}"}, "tone": "mut"},
        {"text": _date(x.get("posting_date")), "nowrap": True},
        {"text": _money(x["base"]), "num": True},
    ]} for x in pays[:12]]
    total = sum(x["base"] for x in pays)
    suppliers = len({x.get("party") for x in pays})
    # Not every payment not yet matched is an advance: most may pay bills that were simply
    # never matched to it. What is really ahead of the bills is what suppliers hold in
    # credit by the ledger, so the note says both.
    ahead = [r for r in _positions(ctx, "Supplier") if r["in_credit"] > 0]
    ahead_note = (f" By the ledger, {ctx.cur} {_money(_sum(ahead, 'in_credit'))} of it is really "
                  f"ahead of the bills ({_plural(len(ahead), 'supplier')} in credit); the rest "
                  f"pays bills it was never matched to." if pays else "")
    return {"kind": "table", "rows": rows,
            "columns": _cols("Supplier", "Payment", "Paid on", "Not yet matched$"),
            "empty": "Every payment to a supplier is matched to an invoice.",
            "note": (f"{ctx.cur} {_money(total)} paid to {_plural(suppliers, 'supplier')} and "
                     f"not yet matched to an invoice.{ahead_note} Match each to its invoice with "
                     f"Payment Reconciliation once the goods are billed." if pays else "")}


# --------------------------------------------------------------------------- stock
def inv_not_moving(ctx):
    held = defaultdict(lambda: [0.0, 0.0])
    for r in ctx.rows("fact_stock_balance", ["item_code", "actual_qty", "stock_value"]):
        held[r["item_code"]][0] += _num(r["actual_qty"])
        held[r["item_code"]][1] += _num(r["stock_value"])
    held = {k: v for k, v in held.items() if v[0] > 0}
    if not held:
        return _guide(ctx, "No stock is recorded in ERPNext.", STOCK_STEPS, "/app/stock-entry/new")
    # The last time each was sold or used (recommend/rules.stock_used): a transfer between
    # warehouses, a receipt or a stock correction is not the stock moving on.
    from command_center.recommend.rules import stock_used
    last = {item: v[2] for item, v in stock_used(ctx, last=True).items()}
    today = _today()
    idle = []
    for item, (qty, value) in held.items():
        d = last.get(item)
        days = frappe.utils.date_diff(today, d) if d else None
        if days is None or days > 90:
            idle.append((item, qty, value, d, days))
    idle.sort(key=lambda x: -x[2])
    rows = [{"cells": [
        {"text": item, "drill": {"fact": "fact_stock_balance", "filters": {"item_code": item}}},
        {"text": f"{qty:,.0f}", "num": True},
        {"text": _money(value), "num": True},
        {"text": _date(d) if d else "never", "nowrap": True, "tone": "mut"},
        {"text": _late(days) if days is not None else "—", "tone": "crit" if (days or 999) > 180 else "high"},
    ]} for item, qty, value, d, days in idle[:12]]
    total = sum(x[2] for x in idle)
    out = {"kind": "table", "rows": rows,
           "columns": _cols("Product", "#Held", "Value$", "Last moved", "Idle for"),
           "empty": "Every product holding stock has moved in the last ninety days.",
           "note": (f"{_plural(len(idle), 'product')} holding stock {'has' if len(idle) == 1 else 'have'} "
                    f"not moved in ninety days: {ctx.cur} {_money(total)} on the shelf."
                    if idle else "")}
    return out


EXPIRY_STEPS = ["Open each Item that expires, tick Has Batch No and Has Expiry Date, and save.",
                "When goods arrive (Purchase Receipt), enter the Batch No and its Expiry Date "
                "on each line.",
                "Stock already on the shelf: give it a batch with its expiry date through a "
                "Stock Reconciliation."]


def inv_expiry(ctx):
    batches = _guarded(ctx, "Batch", {"expiry_date": ["is", "set"], "batch_qty": [">", 0]},
                       ["name", "item", "expiry_date", "batch_qty"])
    if not batches and not _count(ctx, "Batch", {"expiry_date": ["is", "set"]}):
        return _guide(ctx, "No batch in ERPNext carries an expiry date yet.", EXPIRY_STEPS,
                      "/app/item")
    today = _today()
    soon = []
    for b in batches:
        days = frappe.utils.date_diff(b["expiry_date"], today)
        if days <= 90:
            soon.append((days, b))
    soon.sort(key=lambda x: x[0])
    site = ctx.site()
    rows = [{"cells": [
        {"text": b["name"], "drill": {"href": f"{site}/app/batch/{quote(b['name'])}"}},
        {"text": b.get("item") or ""},
        {"text": f"{_num(b.get('batch_qty')):,.0f}", "num": True},
        {"text": _date(b["expiry_date"]), "nowrap": True},
        {"text": "Expired" if d < 0 else f"in {_late(d)}", "tag": "t-od" if d < 30 else "t-wt"},
    ]} for d, b in soon[:12]]
    gone = sum(1 for d, _ in soon if d < 0)
    return {"kind": "table", "rows": rows,
            "columns": _cols("Batch", "Product", "#Quantity", "Expires", "When"),
            "empty": "No batch holding stock expires in the next ninety days.",
            "note": (f"{_plural(len(soon), 'batch', 'batches')} holding stock expire within ninety days"
                     + (f"; {gone} already {'has' if gone == 1 else 'have'}." if gone else ".")
                     if soon else "")}


# --------------------------------------------------------------------------- projects
def _norm(text):
    import re
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def eng_quality(ctx):
    tasks = _tasks(ctx)
    if not tasks:
        return _guide(ctx, "No project task is recorded in ERPNext.", TASK_STEPS, "/app/project")
    open_ = [t for t in tasks if t["is_open"]]
    items = []
    same = defaultdict(list)
    for t in open_:
        same[_norm(t["subject"])].append(t)
    twice = [v for k, v in same.items() if k and len(v) > 1]
    if twice:
        ex = twice[0][0]["subject"]
        items.append({"text": f"{_plural(sum(len(v) for v in twice), 'open job')} share a name "
                              f"with another open job (“{ex}” is one), so some work may be "
                              f"counted twice.", "bold": "recorded twice"})
    undated = [t for t in open_ if not t["exp_end_date"]]
    if undated:
        items.append({"text": f"{_plural(len(undated), 'open job')} {'has' if len(undated) == 1 else 'have'} "
                              f"no expected end date, so {'it' if len(undated) == 1 else 'they'} "
                              f"can never show as late."})
    stuck = _count(ctx, "Task", {"status": "Completed", "progress": ["<", 100]})
    if stuck:
        items.append({"text": f"{_plural(stuck, 'completed job')} still {'shows' if stuck == 1 else 'show'} "
                              f"less than 100% progress, so completion reads worse than it is."})
    untyped = _count(ctx, "Project", {"status": "Open", "project_type": ["is", "not set"]})
    if untyped:
        items.append({"text": f"{_plural(untyped, 'open project')} {'has' if untyped == 1 else 'have'} "
                              f"no Project Type, so installations cannot be told from other work."})
    from command_center.kpi.live_departments import late_customers
    _, orphan, _ = late_customers(ctx.reader())
    if orphan:
        items.append({"text": f"{_plural(len(orphan), 'late job')} {'belongs' if len(orphan) == 1 else 'belong'} "
                              f"to a project with no customer, so what {'it is' if len(orphan) == 1 else 'they are'} "
                              f"costing us cannot be counted."})
    if not items:
        return {"kind": "list", "items": [{"text": "No duplicate, undated or inconsistent job "
                                                   "was found in the records."}], "note": ""}
    return {"kind": "list", "items": items,
            "note": "Each of these makes the figures above less reliable than they look. "
                    "Tidying them in ERPNext makes every figure on this screen trustworthy."}


def eng_earns(ctx):
    from command_center.kpi.live import PROJECT_COSTS
    projects = _guarded(ctx, "Project", {"status": ["!=", "Cancelled"]},
                        ["name", "project_name", "customer", "total_billed_amount", *PROJECT_COSTS])
    for p in projects:
        p["cost"] = sum(_num(p.get(f)) for f in PROJECT_COSTS)
        p["billed"] = _num(p.get("total_billed_amount"))
    costed = [p for p in projects if p["cost"] > 0]
    if not costed:
        return _guide(ctx, "No project carries a cost, so nobody can say whether a job makes "
                           "money or loses it.",
                      ["Book engineers' hours with Timesheet against the project and task, at "
                       "their costing rate.",
                       "Issue parts with Stock Entry (Material Issue), setting Project on it.",
                       "Set Project on purchase invoices and expense claims bought for the job.",
                       "Invoice the customer from the project's Sales Order, with Project set."],
                      "/app/timesheet/new")
    costed.sort(key=lambda p: -max(p["billed"], p["cost"]))
    site = ctx.site()
    rows = []
    for p in costed[:12]:
        m = p["billed"] - p["cost"]
        rows.append({"cells": [
            {"text": p.get("project_name") or p["name"],
             "drill": {"href": f"{site}/app/project/{quote(p['name'])}"}},
            {"text": p.get("customer") or "—", "tone": "" if p.get("customer") else "mut"},
            {"text": _money(p["billed"]), "num": True},
            {"text": _money(p["cost"]), "num": True},
            {"text": _money(m), "num": True, "tone": "ok" if m >= 0 else "crit"},
        ]})
    loss = sum(1 for p in costed if p["billed"] < p["cost"])
    return {"kind": "table", "rows": rows,
            "columns": _cols("Project", "Customer", "Billed$", "Cost$", "Margin$"),
            "note": (f"{_plural(len(costed), 'project')} of {len(projects):,} carry a cost; "
                     f"{loss} of them {'has' if loss == 1 else 'have'} cost more than billed."
                     if costed else "")}


def eng_warranty(ctx):
    steps = ["When a customer reports a fault on a machine you sold, open Warranty Claim, "
             "click New.", "Choose the Customer, the Serial No (or Item Code) and describe "
             "the complaint.", "Record the repair with Maintenance Visit (Create, Maintenance "
             "Visit) and close the claim."]
    if not _has(ctx, "Warranty Claim") or not _count(ctx, "Warranty Claim"):
        return _guide(ctx, "No warranty claim is recorded in ERPNext.", steps,
                      "/app/warranty-claim/new")
    claims = _guarded(ctx, "Warranty Claim", {}, ["name", "item_code", "customer",
                                                  "complaint_date", "status"], limit=20000)
    by = defaultdict(lambda: {"n": 0, "open": 0, "who": set(), "last": None})
    for c in claims:
        g = by[c.get("item_code") or "Item not given"]
        g["n"] += 1
        g["open"] += int((c.get("status") or "") not in ("Closed", "Cancelled"))
        g["who"].add(c.get("customer"))
        d = c.get("complaint_date")
        if d and (not g["last"] or str(d) > str(g["last"])):
            g["last"] = d
    site = ctx.site()
    rows = [{"cells": [
        {"text": item, "drill": {"href": f"{site}/app/warranty-claim?item_code={quote(item)}"}},
        {"text": f"{g['n']:,}", "num": True, "tone": "crit" if g["n"] > 2 else ""},
        {"text": f"{len(g['who']):,}", "num": True},
        {"text": f"{g['open']:,}", "num": True},
        {"text": _date(g["last"]), "nowrap": True, "tone": "mut"},
    ]} for item, g in sorted(by.items(), key=lambda kv: -kv[1]["n"])[:12]]
    repeat = sum(1 for g in by.values() if g["n"] > 1)
    return {"kind": "table", "rows": rows,
            "columns": _cols("Product", "#Claims", "#Customers", "#Still open", "Latest"),
            "note": f"{_plural(len(claims), 'claim')}; {_plural(repeat, 'product')} came back more than once."}


def eng_maintenance(ctx):
    steps = ["After an installation, open Maintenance Schedule and click New (or from the "
             "Sales Order: Create, Maintenance Schedule).",
             "Choose the customer, add the item with its start and end date and how often it "
             "is serviced, then click Generate Schedule.",
             "Submit it; each visit appears with its date, and is closed with a Maintenance "
             "Visit."]
    if not _has(ctx, "Maintenance Schedule") or not _count(ctx, "Maintenance Schedule",
                                                           {"docstatus": 1}):
        return _guide(ctx, "No maintenance schedule is recorded in ERPNext, so no service "
                           "visit is planned after an installation.", steps,
                      "/app/maintenance-schedule/new")
    heads = {h["name"]: h for h in _guarded(ctx, "Maintenance Schedule", {"docstatus": 1},
                                            ["name", "customer"], limit=20000)}
    visits = []
    names = sorted(heads)
    edge = str(frappe.utils.add_days(_today(), 60))
    for i in range(0, len(names), 200):
        visits += _guarded(ctx, "Maintenance Schedule Detail",
                           {"parent": ["in", names[i:i + 200]], "completion_status": "Pending",
                            "scheduled_date": ["<=", edge]},
                           ["parent", "item_code", "scheduled_date"],
                           parent="Maintenance Schedule", limit=100000)
    visits.sort(key=lambda v: str(v.get("scheduled_date")))
    today = _today()
    site = ctx.site()
    rows = []
    for v in visits[:12]:
        d = frappe.utils.date_diff(v["scheduled_date"], today)
        rows.append({"cells": [
            {"text": (heads.get(v["parent"]) or {}).get("customer") or "—",
             "drill": {"href": f"{site}/app/maintenance-schedule/{v['parent']}"}},
            {"text": v.get("item_code") or ""},
            {"text": _date(v["scheduled_date"]), "nowrap": True},
            {"text": f"{_late(-d)} overdue" if d < 0 else f"in {_late(d)}",
             "tag": "t-od" if d < 0 else "t-wt"},
        ]})
    over = sum(1 for v in visits if frappe.utils.date_diff(v["scheduled_date"], today) < 0)
    return {"kind": "table", "rows": rows,
            "columns": _cols("Customer", "Equipment", "Visit due", "When"),
            "empty": "No service visit is due in the next sixty days.",
            "note": (f"{_plural(len(visits), 'visit')} due or overdue in the next sixty days"
                     + (f", {over} already overdue." if over else ".") if visits else "")}


# --------------------------------------------------------------------------- service
CASE_STEPS = ["Open Issue, click New for each complaint, query or fault, and choose the "
              "Customer.", "Set the Issue Type and Priority.",
              "Close it with Resolution Details saying what was done."]


def cx_repeat(ctx):
    cases = ctx.rows("fact_case", ["customer", "issue_type", "opening_date", "src_name"])
    if not cases:
        return _guide(ctx, "No customer case is recorded in ERPNext.", CASE_STEPS, "/app/issue/new")
    if not any(c["issue_type"] for c in cases):
        return _guide(ctx, "No case carries an Issue Type, so the same problem cannot be "
                           "told apart from a different one.",
                      ["Open Issue Type and create the kinds of problem you see (Equipment "
                       "Fault, Delivery, Billing...).", "Set Issue Type on every case, "
                                                        "open and closed."], "/app/issue-type")
    since = frappe.utils.getdate(_days_ago(365))
    by = defaultdict(list)
    for c in cases:
        if c["customer"] and c["issue_type"] and c["opening_date"] and \
                frappe.utils.getdate(c["opening_date"]) >= since:
            by[(c["customer"], c["issue_type"])].append(c)
    rep = sorted([(k, v) for k, v in by.items() if len(v) > 1], key=lambda kv: -len(kv[1]))
    rows = [{"cells": [
        {"text": cu, "drill": {"fact": "fact_case", "filters": {"customer": cu, "issue_type": ty}}},
        {"text": ty},
        {"text": f"{len(v):,}", "num": True, "tone": "crit" if len(v) > 2 else "high"},
        {"text": _date(max(x["opening_date"] for x in v)), "nowrap": True, "tone": "mut"},
    ]} for (cu, ty), v in rep[:12]]
    return {"kind": "table", "rows": rows,
            "columns": _cols("Customer", "Problem", "#Cases", "Latest"),
            "empty": "No customer has raised the same kind of problem twice in the last year.",
            "note": (f"{_plural(len(rep), 'customer and problem')} came back more than once "
                     f"in the last year." if rep else "")}


def cx_fixed(ctx):
    closed = ctx.rows("fact_case", ["src_name"], lambda t: [t.is_open == 0])
    if not closed:
        if not ctx.rows("fact_case", ["src_name"]):
            return _guide(ctx, "No customer case is recorded in ERPNext.", CASE_STEPS,
                          "/app/issue/new")
        return {"kind": "bars", "rows": [], "empty": "No case has been closed yet.", "note": ""}
    from command_center.ingest.operations import CLOSED_CASE
    written = _count(ctx, "Issue", {"status": ["in", sorted(CLOSED_CASE)],
                                    "resolution_details": ["is", "set"]})
    written = min(written, len(closed))
    rows = [{"label": "Closed saying what fixed it", "value": written, "display": f"{written:,}",
             "tone": "ok"},
            {"label": "Closed with nothing written", "value": len(closed) - written,
             "display": f"{len(closed) - written:,}", "tone": "high",
             "drill": {"fact": "fact_case", "filters": {"is_open": 0}}}]
    out = _bars(rows)
    out["note"] = (f"{_pct(len(closed) - written, len(closed))}% of closed cases say nothing about "
                   f"how they were resolved. ERPNext does not record whether the customer agreed; "
                   f"ask them before closing, and write it in Resolution Details.")
    return out


# --------------------------------------------------------------------------- finances
def _ahead(ctx, party_type, rows):
    """What is owed and not yet due after matching, by due date: [(due_date, amount)].

    The unmatched credits were set against the oldest items first, so what is left not
    yet due is the newest invoices: each party's not-yet-due part is filled from its
    latest-falling invoices back."""
    fact, col = (("fact_sales_invoice", "customer") if party_type == "Customer"
                 else ("fact_purchase_invoice", "supplier"))
    today = ctx.as_of
    by = defaultdict(list)
    for x in ctx.rows(fact, [col, "due_date", "outstanding_amount"],
                      lambda t: [t.src_docstatus == 1, t.outstanding_amount > 0,
                                 t.due_date >= today]):
        by[x[col]].append((frappe.utils.getdate(x["due_date"]), _num(x["outstanding_amount"])))
    out = []
    for r in rows:
        left = r["not_due"]
        for due, amt in sorted(by.get(r["party"], []), key=lambda x: x[0], reverse=True):
            if left < 0.005:
                break
            take = min(amt, left)
            out.append((due, take))
            left -= take
        if left >= 0.005:
            out.append((today, left))
    return out


def fin_suppliers_due(ctx):
    rows = [r for r in _positions(ctx, "Supplier") if r["owed"] > 0]
    if not rows and not ctx.rows("fact_purchase_invoice", ["src_name"], lambda t: [t.src_docstatus == 1]):
        return _guide(ctx, "No supplier invoice is recorded in ERPNext.",
                      ["Record each supplier's bill as a Purchase Invoice (from the Purchase "
                       "Order or Receipt: Create, Purchase Invoice).",
                       "Check its Due Date against the supplier's payment terms, then Submit."],
                      "/app/purchase-invoice/new")
    today = ctx.as_of
    bands = [("Overdue now", "crit"), ("Due in 7 days", "high"), ("Due in 8–30 days", "med"),
             ("Due in 31–60 days", "accent"), ("Later", "dim")]

    def band(due):
        d = frappe.utils.date_diff(due, today)
        return 1 if d <= 7 else 2 if d <= 30 else 3 if d <= 60 else 4
    sums = [0.0] * len(bands)
    sums[0] = _sum(rows, "overdue")
    for due, amt in _ahead(ctx, "Supplier", rows):
        sums[band(due)] += amt
    out = _bars([{"label": l, "value": v, "display": _money(v), "tone": tone}
                 for (l, tone), v in zip(bands, sums)])
    edge = frappe.utils.add_days(today, 30)
    customers = [r for r in _positions(ctx, "Customer") if r["owed"] > 0]
    coming = sum(a for due, a in _ahead(ctx, "Customer", customers) if due <= edge)
    undated = _sum(rows, "undated")
    out["note"] = ((f"{ctx.cur} {_money(sums[0] + sums[1] + sums[2])} is overdue or due to suppliers "
                    f"within thirty days by the ledger, after payments not yet matched are set "
                    f"against the oldest bills; customers are due to pay {ctx.cur} {_money(coming)} "
                    f"in the same thirty days."
                    + (f" {ctx.cur} {_money(undated)} more is owed with no bill to date it."
                       if undated >= 0.5 else ""))
                   if rows else "Nothing is owed to suppliers, by the ledger.")
    return out


def _balances(ctx, accounts):
    if not accounts:
        return {}
    rows = _grouped(ctx, "GL Entry", {"account": ["in", accounts], "is_cancelled": 0}, "account",
                    [("sum", "debit", "debit_total"), ("sum", "credit", "credit_total")])
    return {r["account"]: _num(r.get("debit_total")) - _num(r.get("credit_total")) for r in rows}


def fin_cash(ctx):
    accounts = _guarded(ctx, "Account", {"account_type": ["in", ["Bank", "Cash"]], "is_group": 0},
                        ["name", "account_type"], limit=500)
    if not accounts:
        return _guide(ctx, "No ledger account in ERPNext is marked as a bank or cash account.",
                      ["Open Chart of Accounts and click each bank and cash account.",
                       "Set Account Type to Bank (or Cash) and save."],
                      "/app/account/view/tree")
    bal = _balances(ctx, [a["name"] for a in accounts])
    r = ctx.reader()
    rows = []
    for a in sorted(accounts, key=lambda a: -bal.get(a["name"], 0.0))[:12]:
        last = None
        if a.get("account_type") == "Bank":
            dates = [r.edge("Payment Entry", "clearance_date",
                            {"docstatus": 1, side: a["name"], "clearance_date": ["is", "set"]})
                     for side in ("paid_from", "paid_to")]
            dates = [d for d in dates if d]
            last = max(str(d) for d in dates) if dates else None
        stale = a.get("account_type") == "Bank" and (
            not last or frappe.utils.date_diff(_today(), last) > 45)
        rows.append({"cells": [
            {"text": a["name"], "drill": {"href": f"{ctx.site()}/app/general-ledger?account={quote(a['name'])}"}},
            {"text": a.get("account_type") or "", "tone": "mut"},
            {"text": _money(bal.get(a["name"], 0.0)), "num": True,
             "tone": "crit" if bal.get(a["name"], 0.0) < 0 else ""},
            {"text": (_date(last) if last else ("never" if a.get("account_type") == "Bank" else "—")),
             "tone": "high" if stale else "mut", "nowrap": True},
        ]})
    total = sum(bal.get(a["name"], 0.0) for a in accounts)
    return {"kind": "table", "rows": rows,
            "columns": _cols("Account", "Type", "Balance$", "Last matched to a statement"),
            "note": f"{ctx.cur} {_money(total)} across {_plural(len(accounts), 'account')}, as the ledger has it."}


def _site_has(ctx, doctype, field):
    """Whether the business's ERPNext has this field on this doctype: True, False, or
    None when it cannot be told (a business on this site, or no definition readable).
    For the few places where versions differ in shape, not just in a field's name."""
    try:
        conn = getattr(ctx.reader(), "conn", None)
    except Exception:
        return None
    if conn is None or not hasattr(conn, "fieldnames"):
        return None
    have = conn.fieldnames(doctype)
    return None if have is None else field in have


def fin_budget(ctx):
    steps = ["Open Budget, click New, and set Budget Against to Cost Center (a department's "
             "cost centre) and the Fiscal Year.",
             "Add each expense Account with its budget amount for the year.",
             "Choose what happens when it is exceeded (Warn or Stop), then Submit."]
    if not _count(ctx, "Budget", {"docstatus": 1}):
        return _guide(ctx, "No budget is set in ERPNext.", steps, "/app/budget/new")
    today = str(_today())
    years = _guarded(ctx, "Fiscal Year", {"year_start_date": ["<=", today],
                                          "year_end_date": [">=", today]},
                     ["name", "year_start_date", "year_end_date"], limit=5)
    if not years:
        return _guide(ctx, "No fiscal year in ERPNext covers today.",
                      ["Open Fiscal Year, click New, and set this year's start and end dates."],
                      "/app/fiscal-year/new")
    fy = years[0]
    window = (str(fy["year_start_date"]), str(fy["year_end_date"]))
    if _site_has(ctx, "Budget", "fiscal_year") is False:
        # ERPNext 16: a budget names its own account and amount and runs from one fiscal
        # year to another (budget_start_date..budget_end_date); no per-account table.
        budgets = _guarded(ctx, "Budget", {"docstatus": 1, "budget_against": "Cost Center",
                                           "budget_start_date": ["<=", today],
                                           "budget_end_date": [">=", today]},
                           ["name", "cost_center", "account", "budget_amount",
                            "budget_start_date", "budget_end_date"], limit=500)
        lines = [{"parent": b["name"], "account": b["account"],
                  "budget_amount": b["budget_amount"]} for b in budgets if b.get("account")]
        if budgets:
            window = (str(min(b["budget_start_date"] for b in budgets)),
                      str(max(b["budget_end_date"] for b in budgets)))
        label = (fy["name"] if not budgets or window == (str(fy["year_start_date"]),
                                                         str(fy["year_end_date"]))
                 else f"{_date(window[0])} to {_date(window[1])}")
    else:
        budgets = _guarded(ctx, "Budget", {"docstatus": 1, "fiscal_year": fy["name"],
                                           "budget_against": "Cost Center"},
                           ["name", "cost_center"], limit=500)
        lines = (_guarded(ctx, "Budget Account", {"parent": ["in", [b["name"] for b in budgets]]},
                          ["parent", "account", "budget_amount"], parent="Budget", limit=5000)
                 if budgets else [])
        label = fy["name"]
    if not budgets:
        return _guide(ctx, f"No cost-centre budget is set for {fy['name']}.", steps,
                      "/app/budget/new")
    cc = {b["name"]: b["cost_center"] for b in budgets}
    accounts = sorted({x["account"] for x in lines})
    actual = {}
    if accounts:
        for r in _grouped(ctx, "GL Entry", {"account": ["in", accounts], "is_cancelled": 0,
                                            "posting_date": ["between", list(window)]},
                          "account, cost_center",
                          [("sum", "debit", "debit_total"), ("sum", "credit", "credit_total")]):
            actual[(r["account"], r.get("cost_center"))] = (_num(r.get("debit_total"))
                                                            - _num(r.get("credit_total")))
    # A budget set on a group cost centre covers the spending of every cost centre under
    # it: the ledger posts to the leaves, never to the group, which read 0% used
    # (17 Nov 2026). ERPNext's tree (lft/rgt) says which are under which.
    tree = {c["name"]: (_num(c.get("lft")), _num(c.get("rgt"))) for c in _guarded(
        ctx, "Cost Center", {}, ["name", "lft", "rgt"], limit=5000)}

    def under(top):
        lo, hi = tree.get(top, (None, None))
        if lo is None:
            return {top}
        return {n for n, (a, b) in tree.items() if lo <= a and b <= hi} | {top}

    rows = []
    for x in lines:
        budget = _num(x["budget_amount"])
        centres = under(cc.get(x["parent"]))
        spent = sum(v for (acc, centre), v in actual.items()
                    if acc == x["account"] and centre in centres)
        used = _pct(spent, budget)
        rows.append((used, {"label": f"{x['account']} · {cc.get(x['parent'])}", "value": min(used, 150),
                            "display": f"{used}% used",
                            "note": f"{ctx.cur} {_short(spent)} of {_short(budget)}",
                            "tone": "crit" if used > 100 else "high" if used > 85 else "accent",
                            "drill": {"href": f"{ctx.site()}/app/budget/{quote(x['parent'])}"}}))
    rows.sort(key=lambda r: -r[0])
    out = _bars([r for _, r in rows[:10]])
    over = sum(1 for u, _ in rows if u > 100)
    out["subtitle"] = f"{label}, spending against each budget line"
    out["note"] = (f"{_plural(over, 'budget line')} already over budget." if over else
                   "No budget line is over budget so far this year.")
    return out


def fin_tax(ctx):
    accounts = _guarded(ctx, "Account", {"account_type": "Tax", "is_group": 0}, ["name"], limit=500)
    if not accounts:
        return _guide(ctx, "No ledger account in ERPNext is marked as a tax account.",
                      ["Open Chart of Accounts and click each VAT, NHIL, GETFund, withholding "
                       "and PAYE account.", "Set Account Type to Tax and save."],
                      "/app/account/view/tree")
    names = [a["name"] for a in accounts]
    bal = _balances(ctx, names)
    months = _months_back(_today(), 1)
    y, m = months[0]
    first = dt.date(y, m, 1)
    last = frappe.utils.getdate(frappe.utils.get_last_day(first))
    moved = {r["account"]: _num(r.get("credit_total")) - _num(r.get("debit_total")) for r in _grouped(
        ctx, "GL Entry", {"account": ["in", names], "is_cancelled": 0,
                          "posting_date": ["between", [str(first), str(last)]]}, "account",
        [("sum", "debit", "debit_total"), ("sum", "credit", "credit_total")])}
    rows = [{"cells": [
        {"text": n, "drill": {"href": f"{ctx.site()}/app/general-ledger?account={quote(n)}"}},
        {"text": _money(-bal.get(n, 0.0)), "num": True, "tone": "crit" if -bal.get(n, 0.0) > 0 else ""},
        {"text": _money(moved.get(n, 0.0)), "num": True, "tone": "mut"},
    ]} for n in sorted(names, key=lambda n: bal.get(n, 0.0))[:12]]
    return {"kind": "table", "rows": rows,
            "columns": _cols("Tax account", "Owed now$", f"Added in {first:%B}$"),
            "note": "What each tax account says is owed. ERPNext keeps the amounts, not the "
                    "filing dates: put each filing date in the Calendar (Event) with a reminder."}


def fin_profit(ctx):
    since = frappe.utils.add_days(ctx.as_of, -365)
    lines = ctx.rows("fact_sales_invoice_line", ["item_group", "base_net_amount",
                                                 "base_cost_amount", "has_cost"],
                     lambda t: [t.src_docstatus == 1, t.posting_date >= since])
    if not lines:
        return _guide(ctx, "No sales invoice in the last twelve months.",
                      ["Invoice each delivery with Sales Invoice (from the Delivery Note: "
                       "Create, Sales Invoice) and Submit it."], "/app/sales-invoice/new")
    if not any(l["has_cost"] for l in lines):
        return _guide(ctx, "No invoice line carries the cost of what was sold, so margin "
                           "cannot be worked out.", STOCK_STEPS + [
                           "Sell from stock (Update Stock on the invoice, or a Delivery Note) "
                           "so each line takes its cost from the stock it came out of."],
                      "/app/stock-ledger")
    by = defaultdict(lambda: [0.0, 0.0, 0.0])
    for l in lines:
        g = by[l["item_group"] or "No item group"]
        if l["has_cost"]:
            g[0] += _num(l["base_net_amount"])
            g[1] += _num(l["base_cost_amount"])
        else:
            g[2] += _num(l["base_net_amount"])
    rows = []
    for grp, (rev, cost, unc) in sorted(by.items(), key=lambda kv: -(kv[1][0] + kv[1][2]))[:10]:
        if rev <= 0:
            continue
        m = _pct(rev - cost, rev)
        note = f"{ctx.cur} {_short(rev)} sold with a cost"
        if unc:
            note += f" · {_short(unc)} without"
        rows.append({"label": grp, "value": max(m, 0), "display": f"{m}% margin", "note": note,
                     "tone": "crit" if m < 10 else "med" if m < 25 else "ok",
                     "drill": {"fact": "fact_sales_invoice_line",
                               "filters": {"item_group": grp, "src_docstatus": 1}}})
    out = _bars(rows)
    total = sum(v[0] + v[2] for v in by.values())
    unc = sum(v[2] for v in by.values())
    out["subtitle"] = "By product group, last twelve months"
    out["note"] = (f"{_pct(unc, total)}% of sales in the period carry no cost and are left out of "
                   f"the margin rather than counted as pure profit." if unc else
                   "Every line sold in the period carries its cost.")
    return out


# --------------------------------------------------------------------------- people
def _dept_key(name):
    import re
    words = _norm(re.sub(r"\s-\s[^-]+$", "", name or "")).split()
    drop = {"dept", "department", "departments", "unit", "the", "and", "of", "division"}
    return " ".join(sorted(w for w in words if w not in drop))


def hr_dupe_depts(ctx):
    people = [p for p in _people(ctx) if p["is_active"]]
    rows = _guarded(ctx, "Department", {"is_group": 0}, ["name"], limit=2000)
    names = sorted({d["name"] for d in rows} | {p["department"] for p in people if p["department"]})
    if not names:
        return _guide(ctx, "No department is recorded in ERPNext.",
                      ["Open Department and create each department once.",
                       "Set Department on every Employee."], "/app/department")
    count = defaultdict(int)
    for p in people:
        count[p["department"]] += 1
    groups = defaultdict(list)
    for n in names:
        if _dept_key(n):
            groups[_dept_key(n)].append(n)
    dup = [sorted(v) for v in groups.values() if len(v) > 1]
    if not dup:
        return {"kind": "list", "items": [{"text": "No two departments look like the same one "
                                                   "typed twice."}], "note": ""}
    items = [{"text": " and ".join(f"“{n}” ({count.get(n, 0)})" for n in g)
              + " look like the same department, recorded more than once."} for g in dup[:6]]
    return {"kind": "list", "items": items,
            "note": "Headcount by department cannot be counted reliably until these are merged: "
                    "move the people to one department and disable the other."}


def _employees(ctx, doctype, filters):
    """The distinct employees with at least one record of this kind."""
    return {r.get("employee") for r in _grouped(ctx, doctype, filters, "employee",
                                                [("count", "name", "records")])}


HRMS_STEPS = ["Ask your ERPNext administrator to install the HR and payroll app (HRMS).",
              "Set up Leave Types and a Holiday List, then allocate leave with Leave Allocation."]


def hr_appraisals(ctx):
    if not _has(ctx, "Appraisal"):
        return _guide(ctx, "Appraisals and training are not set up in this ERPNext.", HRMS_STEPS, "/app")
    since = _days_ago(365)
    done = _count(ctx, "Appraisal", {"docstatus": 1, "end_date": [">=", since]})
    started = _count(ctx, "Appraisal", {"docstatus": 0})
    events = _count(ctx, "Training Event", {"docstatus": 1, "start_time": [">=", since]}) \
        if _has(ctx, "Training Event") else 0
    if not done and not started and not events and not _count(ctx, "Appraisal"):
        return _guide(ctx, "No appraisal or training is recorded in ERPNext.",
                      ["Set up an Appraisal Template with the goals each role is reviewed on.",
                       "For each review, open Appraisal, choose the employee, the period and "
                       "the template, score it and Submit.",
                       "Record courses with Training Event, and each person's result with "
                       "Training Result."], "/app/appraisal/new")
    active = {p["src_name"] for p in ctx.rows("fact_person", ["src_name"], lambda t: [t.is_active == 1])}
    seen = active & _employees(ctx, "Appraisal", {"docstatus": 1, "end_date": [">=", since]})
    site = ctx.site()
    out = _bars([
        {"label": "Appraisals completed, last 12 months", "value": done, "display": f"{done:,}",
         "tone": "ok", "drill": {"href": f"{site}/app/appraisal?docstatus=1"}},
        {"label": "Appraisals started, not completed", "value": started, "display": f"{started:,}",
         "tone": "high", "drill": {"href": f"{site}/app/appraisal?docstatus=0"}},
        {"label": "Active staff not appraised in 12 months", "value": len(active - seen),
         "display": f"{len(active - seen):,} of {len(active):,}", "tone": "crit"},
        {"label": "Training events held, last 12 months", "value": events, "display": f"{events:,}",
         "tone": "accent", "drill": {"href": f"{site}/app/training-event"}},
    ])
    out["note"] = ""
    return out


# --------------------------------------------------------------------------- promised orders: what covers them
def _cover(view):
    """The "Promised Orders — Cover" panel (api/coverage.py), the same on each screen
    but for the state it opens on."""
    def build(ctx):
        from command_center.api.coverage import panel
        return panel(ctx, view)
    build.__name__ = f"cover_{view}"
    return build


# --------------------------------------------------------------------------- the line under each heading
def _n(ctx, fact, where=None):
    return len(ctx.rows(fact, ["src_name"], where))


def when_sales(ctx):
    inv = _n(ctx, "fact_sales_invoice", lambda t: [t.src_docstatus == 1])
    orders = _n(ctx, "fact_sales_order", lambda t: [t.src_docstatus == 1])
    unpaid = _n(ctx, "fact_sales_invoice", lambda t: [t.src_docstatus == 1, t.outstanding_amount > 0])
    owing = _n(ctx, "fact_party_balance", lambda t: [t.party_type == "Customer", t.owed > 0])
    return (f"{inv:,} invoices · {orders:,} orders · {unpaid:,} still open · "
            f"{owing:,} customer{'s' if owing != 1 else ''} owing by the ledger")


def when_proc(ctx):
    pos = _pos(ctx)
    top = sum(_num(p.get("base_grand_total")) for p in
              sorted(pos, key=lambda r: -_num(r.get("base_grand_total")))[:14])
    return f"{len(pos):,} purchase orders · {ctx.cur} {_short(top)} across the fourteen largest alone"


def when_inv(ctx):
    rows = ctx.rows("fact_stock_balance", ["warehouse", "stock_value"])
    total = sum(_num(r["stock_value"]) for r in rows)
    places = len({r["warehouse"] for r in rows})
    return (f"{ctx.cur} {_money(total)} held · {len(rows):,} product-location records "
            f"across {_word(places)} place{'s' if places != 1 else ''}")


def when_eng(ctx):
    jobs = len(_tasks(ctx))
    eng = ctx.kpi("engineers").get("value") or 0
    return f"Where sold revenue gets stuck · {jobs:,} jobs · {eng:,} engineer{'s' if eng != 1 else ''}"


def when_cx(ctx):
    cases = ctx.rows("fact_case", ["is_open"])
    return f"{len(cases):,} cases · {sum(1 for c in cases if c['is_open']):,} open"


def when_fin(ctx):
    return f"Full ledger · {ctx.cur} · to {_date(ctx.as_of)}"


def when_hr(ctx):
    people = _people(ctx)
    active = sum(1 for p in people if p["is_active"])
    return f"{len(people):,} on the books · {active:,} active · pay is never read here"


WHEN = {"sales": when_sales, "proc": when_proc, "inv": when_inv, "eng": when_eng, "cx": when_cx,
        "fin": when_fin, "hr": when_hr}


# --------------------------------------------------------------------------- findings
def find_proc(ctx):
    pos = _pos(ctx)
    out = []
    by = defaultdict(float)
    for p in pos:
        by[p.get("supplier")] += _num(p.get("base_grand_total"))
    total = sum(by.values())
    if total and len(by) > 1:
        ranked = sorted(by.items(), key=lambda kv: -kv[1])
        two = ranked[0][1] + ranked[1][1]
        if two >= 0.5 * total:
            out.append({"title": f"Two suppliers take {_pct(two, total)}% of all buying.",
                        "text": f"{ranked[0][0]} and {ranked[1][0]} hold {ctx.cur} {_short(two)} of "
                                f"{ctx.cur} {_short(total)} ordered. If either stops supplying, or a "
                                f"shipment is held, there may be no second source ready.",
                        "ask": f"How dependent are we on {ranked[0][0]} and {ranked[1][0]}, and "
                               f"who else could supply the same items?"})
    waiting = [p for p in pos if _num(p.get("per_received")) < 100
               and (p.get("status") or "") not in ("Closed", "Completed", "On Hold")
               and p.get("schedule_date")
               and frappe.utils.getdate(p["schedule_date"]) < _today()]
    if waiting:
        w = min(waiting, key=lambda p: str(p["schedule_date"]))
        late = frappe.utils.date_diff(_today(), w["schedule_date"])
        out.append({"title": f"{_plural(len(waiting), 'purchase order')} past the date asked for.",
                    "text": f"The oldest, {w['name']} from {w.get('supplier')}, was due "
                            f"{_date(w['schedule_date'])} and is {_late(late)} late, worth "
                            f"{ctx.cur} {_money(w.get('base_grand_total'))}.",
                    "ask": f"Which purchase orders are past their Required By date, and what "
                           f"have the suppliers said?"})
    # The second box: payments to suppliers never matched to their bills.
    return out[:1] + [f for f in (_owed_finding(ctx, "Supplier"),) if f][:1]


def find_inv(ctx):
    out = []
    import re
    held = defaultdict(float)
    for r in ctx.rows("fact_stock_balance", ["warehouse", "stock_value"]):
        held[r["warehouse"]] += _num(r["stock_value"])
    total = sum(held.values())
    from command_center.kpi.live_departments import NOT_FOR_SALE, off_warehouses
    off, _ = off_warehouses(ctx.reader())
    odd = re.compile(NOT_FOR_SALE, re.I)
    suspect = sorted([(w, v) for w, v in held.items() if v > 0 and (w in off or odd.search(w or ""))],
                     key=lambda kv: -kv[1])
    if suspect and total:
        w, v = suspect[0]
        out.append({"title": f"{ctx.cur} {_short(v)} of stock sits in {w}.",
                    "text": f"That is {_pct(v, total)}% of everything held, in a location "
                            f"{'marked as not for sale' if w in off else 'whose name says goods are not sold from it'}. "
                            f"Nothing can be sold or reserved from there until it is moved.",
                    "ask": f"What stock is held in {w}, and why is it there?"})
    return out


def find_eng(ctx):
    from command_center.kpi.live_departments import late_customers, owed_by
    by, _, late = late_customers(ctx.reader())
    owed = owed_by(ctx.reader())
    both = sorted([(c, owed.get(c, 0.0), ts) for c, ts in by.items() if owed.get(c, 0.0) > 0],
                  key=lambda x: -x[1])
    out = []
    if both:
        c, o, ts = both[0]
        days = max(int(t["days_late"] or 0) for t in ts)
        out.append({"title": f"{c} is waiting on us and owes us {ctx.cur} {_money(o)}.",
                    "text": f"{_plural(len(ts), 'job')} for them {'is' if len(ts) == 1 else 'are'} past "
                            f"the promised date, the oldest by {_late(days)}. Asking for the money "
                            f"without mentioning the work is a difficult call.",
                    "ask": f"What should I say to {c}, given the late work and what they owe?"})
    return out


def find_cx(ctx):
    cases = ctx.rows("fact_case", ["customer", "days_open", "subject"], lambda t: [t.is_open == 1])
    owed = {r["party"]: r["owed"] for r in _positions(ctx, "Customer") if r["owed"] > 0}
    both = [c for c in cases if c["customer"] and owed.get(c["customer"])]
    if not both:
        return []
    top = max(both, key=lambda c: owed[c["customer"]])
    return [{"title": f"{_word(len(both)).capitalize() if len(both) <= 20 else len(both)} of the "
                      f"{_plural(len(cases), 'open case')} {'is' if len(both) == 1 else 'are'} from "
                      f"customers who also owe us money.",
             "text": f"{top['customer']} owes {ctx.cur} {_money(owed[top['customer']])} and has been "
                     f"waiting {_plural(int(top['days_open'] or 0), 'day')} for an answer. Anyone "
                     f"ringing them about the debt needs to know that first.",
             "ask": "Which customers owe us money and are also waiting on us?",
             "ask_label": "Show me all of them"}]


def find_hr(ctx):
    people = ctx.rows("fact_person", ["department", "status", "relieving_date"])
    left = [p for p in people if p["status"] == "Left"]
    if not people or not left:
        return []
    by = defaultdict(int)
    for p in left:
        by[p["department"] or "No department"] += 1
    dept, n = max(by.items(), key=lambda kv: kv[1])
    eng = ctx.kpi("engineers").get("value") or 0
    jobs = ctx.kpi("tasks_overdue").get("value") or 0
    text = f"{dept} has lost the most: {n}."
    if eng or jobs:
        text += (f" The business employs {_plural(int(eng), 'engineer')}, against "
                 f"{_plural(int(jobs), 'open job')} past the promised date.")
    return [{"title": f"{_word(len(left)).capitalize() if len(left) <= 20 else len(left)} of "
                      f"{len(people):,} on the books have left — {_pct(len(left), len(people))}%.",
             "text": text, "ask": "Who has left, from which departments, and how long did they stay?"}]


def _owed_finding(ctx, party_type):
    """When the open invoices and the ledger disagree: what is really owed, and why."""
    rows = _positions(ctx, party_type)
    if not rows:
        return None
    one, many, docs = PARTY_WORDS[party_type]
    owed, on_docs = _sum(rows, "owed"), _sum(rows, "open_invoices")
    if abs(on_docs - owed) < max(1.0, 0.01 * max(owed, on_docs)):
        return None
    cur = ctx.cur
    tot = {k: _sum(rows, k) for k in POSITION_FIELDS if k not in _DATE_OR_NAME}
    title = (f"Customers owe {cur} {_amt(owed)} by the ledger, not the {cur} {_amt(on_docs)} "
             f"their open invoices say." if party_type == "Customer" else
             f"We owe suppliers {cur} {_amt(owed)} by the ledger, not the {cur} {_amt(on_docs)} "
             f"their open bills say.")
    credit = [r for r in rows if r["in_credit"] > 0]
    held = (f"less {cur} {_amt(_sum(credit, 'in_credit'))} that {_plural(len(credit), one)} "
            f"{'holds' if len(credit) == 1 else 'hold'} in credit, which no "
            f"{'invoice' if party_type == 'Customer' else 'bill'} can show" if credit else "")
    reasons = "; ".join(x for x in (_why(tot, cur, party_type), held) if x)
    text = (f"The difference: {reasons}. Until the payments are matched, "
            f"every list of {'debtors' if party_type == 'Customer' else 'bills to pay'} drawn from "
            f"the {docs} is wrong by that much; the figures here use the ledger.")
    return {"title": title.replace("  ", " "), "text": text,
            "ask": (f"Which customers have payments not matched to invoices, and how much does "
                    f"each really owe?" if party_type == "Customer" else
                    f"Which suppliers have payments not matched to bills, and how much do we "
                    f"really owe each?"),
            "ask_label": "Show me who"}


def _matching_guide(ctx, party_type):
    """The guide to fixing it at source, when there are payments to match."""
    from command_center.guides import payment_reconciliation
    rows = _positions(ctx, party_type)
    paid, n = _sum(rows, "unmatched_payments"), int(_sum(rows, "unmatched_payment_count"))
    if paid < 0.5:
        return None
    text = (f"{ctx.cur} {_amt(paid)} received from customers ({_plural(n, 'payment')}) was never "
            f"matched to invoices. Matching them in ERPNext puts the invoices right:"
            if party_type == "Customer" else
            f"{ctx.cur} {_amt(paid)} paid to suppliers ({_plural(n, 'payment')}) was never "
            f"matched to their bills. Matching them in ERPNext puts the bills right:")
    return {"guide": payment_reconciliation(ctx.code, text.strip())}


def find_sales(ctx):
    return [f for f in (_owed_finding(ctx, "Customer"), _matching_guide(ctx, "Customer")) if f]


def find_fin(ctx):
    out = [f for f in (_owed_finding(ctx, "Customer"), _owed_finding(ctx, "Supplier")) if f]
    if len(out) < 2:
        out += [f for f in (_matching_guide(ctx, "Customer"), _matching_guide(ctx, "Supplier")) if f]
    return out[:2]


FINDINGS = {"sales": find_sales, "fin": find_fin, "proc": find_proc, "inv": find_inv, "eng": find_eng, "cx": find_cx, "hr": find_hr}
# The finding boxes show the area's largest open recommendations first, and the findings
# above where the area has fewer (command_center/recommend/surface.py).
from command_center.recommend.surface import wrap as _with_recommendations  # noqa: E402
_with_recommendations(FINDINGS)


SCREENS = {
    "sales": {
        "How sales have moved": sales_trend,
        "Who owes us, and how long it has been": sales_ageing,
        "Largest balances owed": sales_largest_owed,
        "What each customer really owes": sales_ledger,
        "Orders taken but not despatched": sales_not_despatched,
        "From enquiry to order": sales_funnel,
        "Discounts and price changes outside policy": sales_discounts,
        "Promised Orders — Cover": _cover("sales"),
    },
    "proc": {
        "Where the money goes": proc_money,
        "How long each supplier takes": proc_lead,
        "Orders still open": proc_open,
        "Checks before we pay": proc_checks,
        "Supplier performance": proc_performance,
        "Money paid to suppliers in advance": proc_advances,
        "Promised Orders — Cover": _cover("proc"),
    },
    "inv": {
        "Where the value sits": inv_where,
        "Reserved against what is available": inv_reserved,
        "Stock that is not moving": inv_not_moving,
        "Expiry": inv_expiry,
        "Promised Orders — Cover": _cover("inv"),
    },
    "eng": {
        "Can we actually deliver the work we are holding?": eng_capacity,
        "Every job past its promised date": eng_late,
        "Every open job": eng_open,
        "What the late jobs are costing us": eng_late_cost,
        "Why these numbers probably understate the problem": eng_quality,
        "What engineering earns": eng_earns,
        "Warranty and repeat failures": eng_warranty,
        "Maintenance we should be selling": eng_maintenance,
    },
    "cx": {
        "Open cases, longest wait first": cx_open,
        "What they are complaining about": cx_causes,
        "Why the same problems keep happening": cx_repeat,
        "Did we actually fix it": cx_fixed,
    },
    "fin": {
        "Money coming in": fin_money_in,
        "Working capital tied up": fin_working_capital,
        "What we owe suppliers": fin_suppliers_due,
        "Receivables and payables": fin_ledger,
        "Cash and bank position": fin_cash,
        "Budget against actual": fin_budget,
        "Tax and statutory deadlines": fin_tax,
        "Profit on what we sell": fin_profit,
    },
    "hr": {
        "Where people work": hr_departments,
        "Where people are": hr_where,
        "Departments are recorded inconsistently": hr_dupe_depts,
        "Appraisals and training": hr_appraisals,
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
