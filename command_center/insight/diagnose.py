"""What is driving a figure now: the numbers that explain it, worked out from the data.

Each function takes the screen context (recommend.engine._context: the loaded facts,
the business's ERPNext through the guarded reader, its site address) and returns plain
parts the drawer draws -- a reconciliation bridge, the largest contributors, the oldest
items, the expected-position checks, chips and sentences. Nothing here is written for
one business: every amount, name and count is read from the business's own data, and a
part with nothing behind it is left out rather than shown as zero.

    ledger(ctx, party_type, focus)   receivables / payables: open invoices to the ledger
    revenue(ctx, focus)              invoiced revenue, uncosted revenue, margin
    stock(ctx, focus)                stock value, slow stock, unvalued stock
    bank(ctx)                        bank payments matched to a statement

A check is {"label", "state": ok | warn | bad | info, "text"}; a bridge step is
{"id", "label", "value", "kind": total | process | timing | position | unexplained,
"count", "note"}.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from statistics import median
from urllib.parse import quote

import frappe
from frappe.utils import date_diff, flt, getdate

CENT = 0.005
TIMING_DAYS = 30          # a payment newer than this may simply not be matched yet
TOP = 10


def _r(v) -> float:
    return round(flt(v), 2) + 0.0


def money(cur, v) -> str:
    return f"{cur} {flt(v):,.2f}".strip()


def short(cur, v) -> str:
    """Money for a sentence: GHS 10.07M, GHS 341,565. The tables keep the cents."""
    v = flt(v)
    body = f"{v / 1e6:,.2f}M" if abs(v) >= 1e6 else f"{v:,.0f}"
    return f"{cur} {body}".strip()


def pct(part, whole):
    return round(flt(part) / flt(whole) * 100, 1) if flt(whole) else None


def plural(n, word, many=None) -> str:
    n = int(n or 0)
    return f"{n:,} {word if n == 1 else (many or word + 's')}"


def check(label, state, text) -> dict:
    return {"label": label, "state": state, "text": text}


def _single(ctx) -> bool:
    return bool(ctx.code and ctx.code != "__all__")


def _site(ctx) -> str:
    try:
        return ctx.site() if _single(ctx) else ""
    except Exception:
        return ""


# =========================================================================== the ledger
SIDES = {
    "Customer": {
        "who": "customer", "whos": "customers", "invoices": "open invoices",
        "invoice": "Sales Invoice", "invoice_fact": "fact_sales_invoice", "party_col": "customer",
        "verb": "received", "payment_type": "Receive", "notes": "credit notes",
        "owed_label": "Owed to us, by the ledger", "credit_word": "in credit",
        "total": "ar_total", "open": "ar_open_invoices", "unmatched": "ar_unmatched",
        "in_credit": "ar_in_credit", "report": "Accounts Receivable",
    },
    "Supplier": {
        "who": "supplier", "whos": "suppliers", "invoices": "open supplier bills",
        "invoice": "Purchase Invoice", "invoice_fact": "fact_purchase_invoice",
        "party_col": "supplier", "verb": "paid", "payment_type": "Pay", "notes": "debit notes",
        "owed_label": "We owe suppliers, by the ledger", "credit_word": "paid in advance",
        "total": "ap_total", "open": "ap_open_invoices", "unmatched": "ap_unmatched",
        "in_credit": "ap_in_credit", "report": "Accounts Payable",
    },
}
PB_MONEY = ("ledger_balance", "owed", "in_credit", "open_invoices", "unmatched_payments",
            "unlinked_journals", "unlinked_credit_notes", "other_unlinked", "unlinked_debits",
            "invoices_not_updated", "unexplained", "not_due", "d0_30", "d31_60", "d61_90",
            "d90_plus", "undated")
PB_FIELDS = ("party",) + PB_MONEY + ("open_invoice_count", "unmatched_payment_count",
                                     "oldest_due_after_matching", "days_overdue")
BUCKETS = (("not_due", "Not yet due"), ("d0_30", "1-30 days late"), ("d31_60", "31-60 days"),
           ("d61_90", "61-90 days"), ("d90_plus", "Over 90 days"), ("undated", "No date"))


def party_rows(ctx, party_type) -> list:
    return ctx.rows("fact_party_balance", list(PB_FIELDS),
                    lambda t: [t.party_type == party_type])


def party_links(ctx, party_type, party) -> list:
    """Where to act on one party, on the business's own ERPNext."""
    site = _site(ctx)
    if not _single(ctx):
        return []
    q = quote(party or "")
    return [{"label": "Reconcile", "href": f"{site}/app/payment-reconciliation"},
            {"label": "Ledger",
             "href": f"{site}/app/query-report/General%20Ledger?party_type={party_type}&party={q}"}]


def bridge(rows, w) -> dict:
    """Open invoices to what the ledger says is owed, in the records' own terms.

    Per party, ingest/ledger.py holds exactly
        open - unmatched - credit notes - journals - other - not updated + debits
             - unexplained = ledger balance
    and owed = ledger balance + in credit, so the sums below reconcile to the cent; the
    `residual` is what the arithmetic of adding them up leaves (normally 0.00)."""
    t = {f: _r(sum(flt(r.get(f)) for r in rows)) for f in PB_MONEY}
    parties = lambda f: sum(1 for r in rows if abs(flt(r.get(f))) > CENT)  # noqa: E731
    n_open = sum(int(r.get("open_invoice_count") or 0) for r in rows)
    n_unm = sum(int(r.get("unmatched_payment_count") or 0) for r in rows)
    steps = [
        {"id": "open", "label": f"On {w['invoices']}", "value": t["open_invoices"],
         "kind": "total", "count": n_open, "count_word": "invoices", "key": w["open"]},
        {"id": "unmatched", "label": f"Money {w['verb']}, not matched to an invoice",
         "value": -t["unmatched_payments"], "kind": "process", "count": n_unm,
         "count_word": "payments", "key": w["unmatched"]},
        {"id": "credit_notes", "label": f"{w['notes'].capitalize()} not set against an invoice",
         "value": -t["unlinked_credit_notes"], "kind": "process",
         "count": parties("unlinked_credit_notes"), "count_word": w["whos"]},
        {"id": "journals", "label": "Journal credits not linked to an invoice",
         "value": -t["unlinked_journals"], "kind": "process",
         "count": parties("unlinked_journals"), "count_word": w["whos"]},
        {"id": "other", "label": "Payments matched to other documents (orders, journals)",
         "value": -t["other_unlinked"], "kind": "process", "count": parties("other_unlinked"),
         "count_word": w["whos"]},
        {"id": "not_updated", "label": "Invoice balances the ledger no longer holds",
         "value": -t["invoices_not_updated"], "kind": "process",
         "count": parties("invoices_not_updated"), "count_word": w["whos"]},
        {"id": "debits", "label": "Owed on no invoice (opening balances, journals, refunds)",
         "value": t["unlinked_debits"], "kind": "process", "count": parties("unlinked_debits"),
         "count_word": w["whos"]},
        {"id": "unexplained", "label": "Not explained by the records", "value": -t["unexplained"],
         "kind": "unexplained", "count": parties("unexplained"), "count_word": w["whos"]},
    ]
    for s in steps:
        if s.get("count") == 1 and s.get("count_word", "").endswith("s"):
            s["count_word"] = s["count_word"][:-1]
    running = _r(sum(s["value"] for s in steps))
    residual = _r(running - t["ledger_balance"])
    n_credit = sum(1 for r in rows if flt(r.get("in_credit")) > CENT)
    n_owing = sum(1 for r in rows if flt(r.get("owed")) > CENT)
    steps += [
        {"id": "net", "label": "Net, by the ledger", "value": t["ledger_balance"], "kind": "total"},
        {"id": "in_credit", "label": f"{w['whos'].capitalize()} {w['credit_word']}, set aside",
         "value": t["in_credit"], "kind": "position", "count": n_credit, "count_word": w["whos"],
         "key": w["in_credit"],
         "note": f"what is owed counts only the {w['whos']} with a balance due"},
        {"id": "owed", "label": w["owed_label"], "value": t["owed"], "kind": "total",
         "count": n_owing, "count_word": w["whos"], "key": w["total"]},
    ]
    for s in steps[-2:]:
        if s.get("count") == 1:
            s["count_word"] = w["who"]
    end_residual = _r(t["ledger_balance"] + t["in_credit"] - t["owed"])
    return {"steps": steps, "totals": t, "residual": residual, "end_residual": end_residual,
            "reconciles": abs(residual) <= 0.01 and abs(end_residual) <= 0.01,
            "unexplained": t["unexplained"], "gap": _r(t["open_invoices"] - t["owed"])}


def contributors(ctx, rows, party_type, w, cur, by="gap") -> dict | None:
    """The parties behind the gap (open invoices less what the ledger says is owed), or
    behind the unmatched money, largest first, each openable."""
    value = (lambda r: flt(r["open_invoices"]) - flt(r["owed"])) if by == "gap" else \
        (lambda r: flt(r["unmatched_payments"])) if by == "unmatched" else \
        (lambda r: flt(r["d90_plus"])) if by == "d90_plus" else (lambda r: flt(r["in_credit"]))
    ranked = sorted([r for r in rows if value(r) > CENT], key=lambda r: -value(r))
    if not ranked:
        return None
    whole = sum(value(r) for r in ranked)
    out = []
    for r in ranked[:TOP]:
        out.append({
            "party": r["party"], "value": _r(value(r)), "share": pct(value(r), whole),
            "open_invoices": _r(r["open_invoices"]), "owed": _r(r["owed"]),
            "ledger_balance": _r(r["ledger_balance"]), "in_credit": _r(r["in_credit"]),
            "unmatched": _r(r["unmatched_payments"]),
            "unmatched_count": int(r.get("unmatched_payment_count") or 0),
            "d90_plus": _r(r["d90_plus"]),
            "open": {"fact": w["invoice_fact"], "title": f"{r['party']}: open invoices",
                     "filters": {w["party_col"]: r["party"], "outstanding_amount": [">", 0],
                                 "src_docstatus": 1}},
            "links": party_links(ctx, party_type, r["party"]),
        })
    top = sum(x["value"] for x in out)
    return {"by": by, "rows": out, "total": _r(whole), "parties": len(ranked),
            "top_share": pct(top, whole)}


def unmatched_payments(ctx, party_type, as_of) -> dict | None:
    """The payments themselves, read from the business's ERPNext now: how old each
    unmatched amount is, so recent ones (timing) are told from old ones (process)."""
    if not _single(ctx):
        return None
    w = SIDES[party_type]
    try:
        r = ctx.reader()
        rows = r.all("Payment Entry",
                     filters={"docstatus": 1, "party_type": party_type,
                              "payment_type": w["payment_type"], "unallocated_amount": [">", 0]},
                     fields=["name", "party", "posting_date", "unallocated_amount",
                             "source_exchange_rate", "target_exchange_rate"],
                     limit=20000, order_by="posting_date asc")
    except Exception as e:
        from command_center.kpi.live_departments import is_down
        if not is_down(e):
            frappe.log_error(title="Command Center insight: unmatched payments not read",
                             message=frappe.get_traceback())
        return {"error": "The payments could not be read from ERPNext just now, so their "
                         "ages are not shown."}
    site = _site(ctx)
    as_of = getdate(as_of)
    items = []
    for p in rows:
        rate = flt(p.get("source_exchange_rate") if w["payment_type"] == "Receive"
                   else p.get("target_exchange_rate")) or 1.0
        amt = _r(flt(p.get("unallocated_amount")) * rate)
        if amt <= CENT:
            continue
        posted = getdate(p.get("posting_date")) if p.get("posting_date") else None
        age = date_diff(as_of, posted) if posted else None
        items.append({"name": p.get("name"), "party": p.get("party"), "date": str(posted or ""),
                      "amount": amt, "days": age,
                      "href": f"{site}/app/payment-entry/{quote(str(p.get('name')))}"})
    recent = [i for i in items if i["days"] is not None and i["days"] <= TIMING_DAYS]
    old = [i for i in items if i not in recent]
    return {"count": len(items), "total": _r(sum(i["amount"] for i in items)),
            "recent": {"count": len(recent), "total": _r(sum(i["amount"] for i in recent))},
            "old": {"count": len(old), "total": _r(sum(i["amount"] for i in old))},
            "oldest": sorted(items, key=lambda i: (i["date"] or "0000", -i["amount"]))[:8],
            "timing_days": TIMING_DAYS}


def ageing(rows, ctx, w) -> dict:
    t = {k: _r(sum(flt(r.get(k)) for r in rows)) for k, _ in BUCKETS}
    whole = _r(sum(t.values()))
    out = {"buckets": [{"id": k, "label": label, "value": t[k], "share": pct(t[k], whole)}
                       for k, label in BUCKETS if abs(t[k]) > CENT or k != "undated"],
           "total": whole}
    # The same open invoices aged as they stand, before the unmatched credits are set
    # against them: how much of "over 90 days" is money already paid.
    inv = ctx.rows(w["invoice_fact"], ["ageing_bucket", "outstanding_amount"],
                   lambda t_: [t_.src_docstatus == 1, t_.outstanding_amount > 0])
    over = _r(sum(flt(r["outstanding_amount"]) for r in inv if r["ageing_bucket"] == "90+"))
    out["invoices_over_90"] = over
    out["invoices_total"] = _r(sum(flt(r["outstanding_amount"]) for r in inv))
    return out


LEDGER_FOCUS = {
    "ar_total": "bridge", "ar_owing_count": "bridge", "largest_debt": "bridge",
    "ar_open_invoices": "bridge", "ar_count": "bridge",
    "ar_unmatched": "unmatched", "ar_unmatched_count": "unmatched",
    "ar_over_90": "ageing", "ar_inside_90": "ageing", "ar_undated": "ageing",
    "ar_over_90_pct": "ageing", "score_paid": "ageing", "ar_open_over_90": "ageing",
    "ar_open_inside_90": "ageing",
    "ar_in_credit": "credit", "ar_in_credit_count": "credit",
    "ap_total": "bridge", "ap_owing_count": "bridge", "ap_open_invoices": "bridge",
    "ap_count": "bridge", "ap_unpaid_pct": "bridge",
    "ap_unmatched": "unmatched", "ap_unmatched_count": "unmatched",
    "ap_over_90": "ageing", "ap_inside_90": "ageing", "ap_undated": "ageing",
    "ap_in_credit": "credit",
}


def ledger(ctx, party_type: str, key: str) -> dict:
    w, cur = SIDES[party_type], ctx.cur
    focus = LEDGER_FOCUS.get(key, "bridge")
    rows = party_rows(ctx, party_type)
    if not rows:
        return {"empty": True}
    b = bridge(rows, w)
    t = b["totals"]
    live = unmatched_payments(ctx, party_type, ctx.as_of) if focus in ("bridge", "unmatched") else None
    by = {"bridge": "gap", "unmatched": "unmatched", "ageing": "d90_plus", "credit": "in_credit"}[focus]
    contrib = contributors(ctx, rows, party_type, w, cur, by=by)
    aged = ageing(rows, ctx, w)
    credit = contributors(ctx, rows, party_type, w, cur, by="in_credit") if focus != "credit" else contrib

    gap, owed = b["gap"], t["owed"]
    checks = []
    tol = max(1.0, abs(t["open_invoices"]) * 0.005)
    checks.append(check(
        f"{w['invoices'].capitalize()} should equal what the ledger says is owed",
        "ok" if abs(gap) <= tol else "bad",
        (f"They agree: {money(cur, t['open_invoices'])} on the invoices, "
         f"{money(cur, owed)} by the ledger." if abs(gap) <= tol else
         f"They differ by {money(cur, gap)}: the invoices say {money(cur, t['open_invoices'])}, "
         f"the ledger {money(cur, owed)}. The difference is payments and credits recorded "
         f"but never set against the invoices they settle.")))
    if live and not live.get("error") and live["count"]:
        old = live["old"]
        checks.append(check(
            "Every payment should be matched to its invoice within the month",
            "bad" if old["count"] else "warn",
            f"{plural(old['count'], 'payment')} worth {money(cur, old['total'])} "
            f"{'has' if old['count'] == 1 else 'have'} waited over {TIMING_DAYS} days unmatched; "
            f"{plural(live['recent']['count'], 'payment')} worth "
            f"{money(cur, live['recent']['total'])} {'is' if live['recent']['count'] == 1 else 'are'} "
            f"recent and may simply not be matched yet."))
    elif t["unmatched_payments"] > CENT:
        checks.append(check("Every payment should be matched to its invoice within the month",
                            "bad", f"{money(cur, t['unmatched_payments'])} {w['verb']} is not "
                                   f"matched to any invoice."))
    over = next((x["value"] for x in aged["buckets"] if x["id"] == "d90_plus"), 0)
    share = pct(over, owed)
    if share is not None:
        checks.append(check(
            "Most of what is owed should be inside its terms, little over 90 days",
            "ok" if share <= 10 else "warn" if share <= 25 else "bad",
            f"{share}% of the {money(cur, owed)} owed by the ledger is over 90 days late "
            f"({money(cur, over)}), after payments not yet matched are set against the "
            f"oldest invoices. Healthy is 10% or less."))
    if t["undated"] > CENT:
        checks.append(check("Everything owed should trace to a dated document", "warn",
                            f"{money(cur, t['undated'])} of the balance has no invoice or "
                            f"journal date to age it by."))
    n_credit = sum(1 for r in rows if flt(r["in_credit"]) > CENT)
    if n_credit:
        both = [r for r in rows if flt(r["in_credit"]) > CENT and flt(r["open_invoices"]) > CENT]
        checks.append(check(
            f"{w['whos'].capitalize()} {w['credit_word']} should be few, and settled",
            "warn" if both else "info",
            f"{plural(n_credit, w['who'])} {'holds' if n_credit == 1 else 'hold'} "
            f"{money(cur, t['in_credit'])} of credit"
            + (f"; {plural(len(both), w['who'])} of them also show open invoices, so the credit "
               f"should be set against those invoices rather than refunded." if both else ".")))
    checks.append(check(
        "Every difference should be explained by the records",
        "ok" if abs(b["unexplained"]) <= 1 else "warn",
        "Nothing is left unexplained." if abs(b["unexplained"]) <= 1 else
        f"{money(cur, b['unexplained'])} of the difference is not explained by the payments, "
        f"journals and credit notes ERPNext holds (for example exchange differences, or "
        f"entries in another company)."))

    # The sentences: what the gap is made of, largest parts first.
    said = []
    parts = sorted([s for s in b["steps"] if s["kind"] in ("process", "unexplained")
                    and abs(s["value"]) > CENT], key=lambda s: -abs(s["value"]))
    if abs(gap) > tol:
        said.append(f"The {w['invoices']} say {money(cur, t['open_invoices'])}; the ledger says "
                    f"{money(cur, owed)} is owed. The {money(cur, gap)} between them is "
                    f"bookkeeping, not money owed: it is mostly "
                    + "; ".join(f"{s['label'].lower()} ({money(cur, abs(s['value']))}"
                                + (f", {s['count']:,} {s['count_word']}" if s.get("count") else "")
                                + ")" for s in parts[:3]) + ".")
    if t["in_credit"] > CENT:
        said.append(f"{plural(n_credit, w['who'])} {'is' if n_credit == 1 else 'are'} "
                    f"{w['credit_word']} by {money(cur, t['in_credit'])}, so the net ledger is "
                    f"{money(cur, t['ledger_balance'])}; what is owed counts only those with a "
                    f"balance due ({money(cur, owed)}).")
    if contrib and contrib["rows"]:
        lead = contrib["rows"][:3]
        said.append(f"The {min(TOP, contrib['parties'])} largest of {plural(contrib['parties'], w['who'])} "
                    f"are {contrib['top_share']}% of it: "
                    + ", ".join(f"{x['party']} ({money(cur, x['value'])})" for x in lead) + ".")
    if live and not live.get("error") and live["count"]:
        said.append(f"Of the {plural(live['count'], 'payment')} not matched, "
                    f"{money(cur, live['old']['total'])} is over {TIMING_DAYS} days old (a process "
                    f"fault: the payment was never set against its invoice) and "
                    f"{money(cur, live['recent']['total'])} is recent (timing).")
    if over > CENT and aged["invoices_over_90"] > over + CENT:
        said.append(f"Aged as they stand, the invoices put {money(cur, aged['invoices_over_90'])} "
                    f"over 90 days; once the unmatched payments are set against the oldest, "
                    f"{money(cur, over)} is.")
    return {"focus": focus, "bridge": b, "contributors": contrib, "unmatched": live,
            "ageing": aged, "credit": credit, "checks": checks, "diagnosis": said,
            "headline": ledger_headline(focus, b, contrib, aged, over, share, n_credit, tol,
                                        w, cur),
            "chips": [
                {"label": w["invoices"].capitalize(), "value": t["open_invoices"], "unit": "currency"},
                {"label": "By the ledger", "value": owed, "unit": "currency"},
                {"label": "Difference", "value": gap, "unit": "currency",
                 "state": "bad" if abs(gap) > tol else "ok"},
                {"label": "Not explained", "value": b["unexplained"], "unit": "currency",
                 "state": "ok" if abs(b["unexplained"]) <= 1 else "warn"},
            ]}


def ledger_headline(focus, b, contrib, aged, over, share, n_credit, tol, w, cur) -> str:
    """The drawer's one sentence: what is going on, and what clears most of it -- every
    figure in it read off the bridge, the ageing or the contributors above."""
    t, gap, owed = b["totals"], b["gap"], b["totals"]["owed"]
    lead = ""
    if contrib and contrib["rows"]:
        n, every = len(contrib["rows"]), len(contrib["rows"]) == contrib["parties"]
        who = (contrib["rows"][0]["party"] if n == 1 else
               f"the {plural(n, w['who'])} concerned" if every else
               f"the {plural(n, w['who'])} with the largest amounts")
        verb = {"gap": "Reconciling", "unmatched": "Matching the payments of",
                "d90_plus": "Collecting from" if w["who"] == "customer" else "Settling",
                "in_credit": "Setting off the credit of"}[contrib["by"]]
        lead = (f" {verb} {who} clears " +
                ("all of it." if every else f"{contrib['top_share']}% of it."))
    if focus == "ageing":
        if over <= CENT or share is None:
            return f"Nothing owed is over 90 days late: {short(cur, owed)} is owed by the ledger."
        return (f"{short(cur, over)} of the {short(cur, owed)} owed by the ledger is over 90 days "
                f"late ({share}%), after payments not yet matched are set against the oldest "
                f"invoices." + lead)
    if focus == "unmatched":
        if t["unmatched_payments"] <= CENT:
            return f"Every payment {w['verb']} is matched to an invoice."
        return (f"{short(cur, t['unmatched_payments'])} {w['verb']} is not matched to any "
                f"invoice, so the {w['invoices']} overstate what is owed by that much." + lead)
    if focus == "credit":
        if t["in_credit"] <= CENT:
            return f"No {w['who']} is {w['credit_word']}."
        return (f"{plural(n_credit, w['who'])} {'is' if n_credit == 1 else 'are'} "
                f"{w['credit_word']} by {short(cur, t['in_credit'])}." + lead)
    if abs(gap) <= tol:
        return (f"The {w['invoices']} and the ledger agree: {short(cur, owed)} is owed.")
    parts = sorted([s for s in b["steps"] if s["kind"] in ("process", "unexplained")
                    and abs(s["value"]) > CENT], key=lambda s: -abs(s["value"]))
    said = (f"The {w['invoices']} say {short(cur, t['open_invoices'])}, but the ledger says "
            f"{short(cur, owed)} is owed")
    if parts:
        p = parts[0]
        said += f"; {short(cur, abs(p['value']))} of the gap is {p['label'][0].lower()}{p['label'][1:]}"
    return said + "." + (lead if contrib and contrib["by"] == "gap" else "")


# =========================================================================== revenue and margin
def _month(d) -> tuple:
    d = getdate(d)
    return (d.year, d.month)


def _label(ym) -> str:
    return dt.date(ym[0], ym[1], 1).strftime("%b %Y")


def _prev(ym, n=1) -> tuple:
    y, m = ym
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return (y, m)


def last_full_month(horizon) -> tuple:
    h = getdate(horizon)
    nxt = h + dt.timedelta(days=1)
    return (h.year, h.month) if nxt.month != h.month else _prev((h.year, h.month))


def revenue(ctx, key: str) -> dict:
    cur = ctx.cur
    rows = ctx.rows("fact_sales_invoice_line",
                    ["posting_date", "base_net_amount", "base_margin_amount", "has_cost",
                     "customer", "item_group", "item_code"],
                    lambda t: [t.src_docstatus == 1])
    rows = [r for r in rows if r["posting_date"]]
    if not rows:
        return {"empty": True}
    horizon = max(getdate(r["posting_date"]) for r in rows)
    last = last_full_month(horizon)
    months = [_prev(last, i) for i in range(11, -1, -1)]
    net, cost_net, margin = defaultdict(float), defaultdict(float), defaultdict(float)
    for r in rows:
        ym = _month(r["posting_date"])
        net[ym] += flt(r["base_net_amount"])
        if r["has_cost"]:
            cost_net[ym] += flt(r["base_net_amount"])
            margin[ym] += flt(r["base_margin_amount"])
    in12 = set(months)
    out = {"chips": [], "checks": [], "diagnosis": [], "tables": []}
    focus = ("margin" if key in ("margin_pct", "margin_known_cost") else
             "uncosted" if key in ("revenue_uncosted", "margin_excluded_lines", "revenue_costed")
             else "revenue")
    if focus == "revenue":
        a, b, ly = net.get(last, 0.0), net.get(_prev(last), 0.0), net.get(_prev(last, 12), 0.0)
        vals = [net.get(m, 0.0) for m in months]
        out["chips"] = [
            {"label": _label(last), "value": _r(a), "unit": "currency"},
            {"label": _label(_prev(last)), "value": _r(b), "unit": "currency"},
            {"label": f"{_label(_prev(last, 12))}", "value": _r(ly), "unit": "currency"},
            {"label": "Typical month (median of 12)", "value": _r(median(vals)), "unit": "currency"},
        ]
        lo, hi = min(vals), max(vals)
        out["checks"].append(check(
            "A month's sales should sit inside the business's own usual range",
            "ok" if lo <= a <= hi and a >= median(vals) * 0.75 else "warn",
            f"{_label(last)}: {money(cur, a)}. Over the twelve months to it, months ran from "
            f"{money(cur, lo)} to {money(cur, hi)} (median {money(cur, median(vals))})."))
        # Who moved it, against the month before.
        by = defaultdict(lambda: [0.0, 0.0])
        for r in rows:
            ym = _month(r["posting_date"])
            if ym == last:
                by[r["customer"] or "not stated"][0] += flt(r["base_net_amount"])
            elif ym == _prev(last):
                by[r["customer"] or "not stated"][1] += flt(r["base_net_amount"])
        moves = sorted(((c, v[0] - v[1], v[0], v[1]) for c, v in by.items()), key=lambda x: x[1])
        downs = [m for m in moves if m[1] < -CENT][:5]
        ups = [m for m in reversed(moves) if m[1] > CENT][:5]
        if ups or downs:
            out["tables"].append({
                "title": f"What moved it: {_label(last)} against {_label(_prev(last))}",
                "columns": [("Customer", "text"), (_label(last), "currency"),
                            (_label(_prev(last)), "currency"), ("Change", "currency")],
                "rows": [{"cells": [c, _r(x), _r(y), _r(d)],
                          "open": {"fact": "fact_sales_invoice_line", "title": f"{c}: sales",
                                   "filters": {"customer": c, "src_docstatus": 1}}}
                         for c, d, x, y in ups + downs]})
        change = a - b
        out["diagnosis"].append(
            f"{_label(last)} invoiced {money(cur, a)}, {'up' if change >= 0 else 'down'} "
            f"{money(cur, abs(change))} on {_label(_prev(last))}"
            + (f" and {'up' if a >= ly else 'down'} {money(cur, abs(a - ly))} on the same month "
               f"a year earlier." if ly else "."))
        if ups:
            out["diagnosis"].append("Largest rises: " + ", ".join(
                f"{c} (+{money(cur, d)})" for c, d, _, _ in ups[:3]) + ".")
        if downs:
            out["diagnosis"].append("Largest falls: " + ", ".join(
                f"{c} (−{money(cur, abs(d))})" for c, d, _, _ in downs[:3]) + ".")
    elif focus == "uncosted":
        items = defaultdict(lambda: [0.0, 0])
        total = sum(flt(r["base_net_amount"]) for r in rows)
        for r in rows:
            if not r["has_cost"]:
                x = items[r["item_code"] or "not stated"]
                x[0] += flt(r["base_net_amount"])
                x[1] += 1
        un = sum(v[0] for v in items.values())
        out["chips"] = [{"label": "Revenue with no cost", "value": _r(un), "unit": "currency"},
                        {"label": "Share of revenue", "value": pct(un, total), "unit": "percent"},
                        {"label": "Products", "value": len(items), "unit": "count"}]
        out["checks"].append(check(
            "Every sale should carry its cost, so its margin is known",
            "ok" if un <= CENT else "warn" if (pct(un, total) or 0) <= 2 else "bad",
            f"{money(cur, un)} ({pct(un, total) or 0}% of invoiced revenue) was sold with no "
            f"valuation recorded, so its margin is unknown and is left out of the margin."))
        top = sorted(items.items(), key=lambda kv: -kv[1][0])[:TOP]
        if top:
            out["tables"].append({
                "title": "Products sold with no cost recorded, largest first",
                "columns": [("Product", "text"), ("Revenue", "currency"), ("Lines", "count"),
                            ("Share", "percent")],
                "rows": [{"cells": [i, _r(v[0]), v[1], pct(v[0], un)],
                          "open": {"fact": "fact_sales_invoice_line", "title": f"{i}: lines with no cost",
                                   "filters": {"item_code": i, "has_cost": 0, "src_docstatus": 1}}}
                         for i, v in top]})
            out["diagnosis"].append(
                f"{plural(len(items), 'product')} account for it; the largest is {top[0][0]} "
                f"({money(cur, top[0][1][0])}). A service sold with no stock behind it carries no "
                f"cost by design; a stocked product with none means it was received without a "
                f"valuation rate.")
    else:
        pcts = [(m, pct(margin.get(m, 0.0), cost_net.get(m, 0.0))) for m in months]
        known = [p for _, p in pcts if p is not None]
        a = pct(margin.get(last, 0.0), cost_net.get(last, 0.0))
        out["chips"] = [{"label": f"Margin, {_label(last)}", "value": a, "unit": "percent"},
                        {"label": "Typical (median of 12)", "value": round(median(known), 1) if known else None,
                         "unit": "percent"}]
        if known and a is not None:
            out["checks"].append(check(
                "Margin should hold steady inside its own range",
                "ok" if min(known) <= a <= max(known) and a >= median(known) - 3 else "warn",
                f"{_label(last)}: {a}%. Over twelve months it ran from {min(known)}% to "
                f"{max(known)}% (median {round(median(known), 1)}%)."))
        groups = defaultdict(lambda: [0.0, 0.0])
        below = [0, 0.0]
        for r in rows:
            if not r["has_cost"] or _month(r["posting_date"]) not in in12:
                continue
            g = groups[r["item_group"] or "not stated"]
            g[0] += flt(r["base_net_amount"])
            g[1] += flt(r["base_margin_amount"])
            if flt(r["base_margin_amount"]) < -CENT:
                below[0] += 1
                below[1] += flt(r["base_margin_amount"])
        top = sorted(groups.items(), key=lambda kv: -kv[1][0])[:8]
        if top:
            out["tables"].append({
                "title": "Margin by product group, last twelve months",
                "columns": [("Product group", "text"), ("Revenue", "currency"),
                            ("Margin", "currency"), ("Margin %", "percent")],
                "rows": [{"cells": [g, _r(v[0]), _r(v[1]), pct(v[1], v[0])],
                          "open": {"fact": "fact_sales_invoice_line", "title": f"{g}: sales",
                                   "filters": {"item_group": g, "src_docstatus": 1, "has_cost": 1}}}
                         for g, v in top]})
        if below[0]:
            out["checks"].append(check("Nothing should be sold below cost", "bad",
                                       f"{plural(below[0], 'line')} in twelve months lost "
                                       f"{money(cur, abs(below[1]))} against their cost."))
        if a is not None:
            out["diagnosis"].append(
                f"Margin in {_label(last)} was {a}% on {money(cur, cost_net.get(last, 0.0))} of "
                f"revenue whose cost is known.")
    return out


# =========================================================================== stock
def stock(ctx, key: str) -> dict:
    from command_center.recommend.rules import held, outflow
    cur = ctx.cur
    rows = ctx.rows("fact_stock_balance", ["item_code", "warehouse", "actual_qty",
                                           "stock_value", "has_valuation"])
    if not rows:
        return {"empty": True}
    out = {"chips": [], "checks": [], "diagnosis": [], "tables": []}
    total = sum(flt(r["stock_value"]) for r in rows)
    wh = defaultdict(float)
    for r in rows:
        wh[r["warehouse"] or "not stated"] += flt(r["stock_value"])
    unvalued = [r for r in rows if not r["has_valuation"] and flt(r["actual_qty"]) > 0]
    out["chips"] = [{"label": "Stock on hand", "value": _r(total), "unit": "currency"},
                    {"label": "Warehouses", "value": len(wh), "unit": "count"},
                    {"label": "Lines with no value", "value": len(unvalued), "unit": "count",
                     "state": "warn" if unvalued else "ok"}]
    out["checks"].append(check(
        "Every item held should carry a valuation", "ok" if not unvalued else "warn",
        "Every line held carries a value." if not unvalued else
        f"{plural(len(unvalued), 'stock line')} held with no valuation add nothing to the "
        f"{money(cur, total)}, so it understates what is held by an unknown amount."))
    out["tables"].append({
        "title": "Where it is held",
        "columns": [("Warehouse", "text"), ("Value", "currency"), ("Share", "percent")],
        "rows": [{"cells": [w_, _r(v), pct(v, total)],
                  "open": {"fact": "fact_stock_balance", "title": f"{w_}: stock",
                           "filters": {"warehouse": w_}}}
                 for w_, v in sorted(wh.items(), key=lambda kv: -kv[1])[:6]]})
    if _single(ctx):
        try:
            have = {i: x for i, x in held(ctx).items() if x["qty"] > 0 and x["value"] > 0}
            moved = outflow(ctx, 90)
            moved2 = outflow(ctx, 180)
            idle = sorted([i for i in have if i not in moved], key=lambda i: -have[i]["value"])
            idle_v = sum(have[i]["value"] for i in idle)
            long_v = sum(have[i]["value"] for i in idle if i not in moved2)
            out["chips"].append({"label": "Not moved in 90 days", "value": _r(idle_v),
                                 "unit": "currency", "state": "warn" if idle_v > CENT else "ok"})
            out["checks"].append(check(
                "Stock should turn: little should sit unsold for three months",
                "ok" if (pct(idle_v, total) or 0) <= 10 else "warn" if (pct(idle_v, total) or 0) <= 25 else "bad",
                f"{plural(len(idle), 'product')} worth {money(cur, idle_v)} "
                f"({pct(idle_v, total) or 0}% of stock by value) had nothing sold or issued in 90 "
                f"days; {money(cur, long_v)} of it in 180 days."))
            if idle:
                out["tables"].append({
                    "title": "Not moved in 90 days, largest first",
                    "columns": [("Product", "text"), ("Held", "quantity"), ("Value", "currency"),
                                ("Moved in 180 days", "text")],
                    "rows": [{"cells": [i, have[i]["qty"], _r(have[i]["value"]),
                                        "yes" if i in moved2 else "no"],
                              "open": {"fact": "fact_stock_balance", "title": f"{i}: stock",
                                       "filters": {"item_code": i}}} for i in idle[:TOP]]})
                out["diagnosis"].append(
                    f"{money(cur, idle_v)} of the {money(cur, total)} held has not moved in 90 "
                    f"days; the largest is {idle[0]} ({money(cur, have[idle[0]]['value'])}).")
        except Exception:
            frappe.log_error(title="Command Center insight: stock movement not read",
                             message=frappe.get_traceback())
            out["diagnosis"].append("The stock movements could not be read from ERPNext just "
                                    "now, so slow stock is not shown.")
    return out


# =========================================================================== bank
def bank(ctx) -> dict:
    """Per bank account: payments through it, how many are matched to a statement, and
    when one last was."""
    if not _single(ctx):
        return {"empty": True}
    from command_center.recommend.rules import grouped
    r = ctx.reader()
    banks = [a["name"] for a in r.all("Account", filters={"account_type": "Bank", "is_group": 0},
                                      fields=["name"], limit=500)]
    if not banks:
        return {"empty": True}
    per = defaultdict(lambda: [0, 0])
    for side in ("paid_from", "paid_to"):
        for cleared, idx in ((None, 0), (True, 1)):
            f = {"docstatus": 1, side: ["in", banks]}
            if cleared:
                f["clearance_date"] = ["is", "set"]
            for row in grouped(ctx, "Payment Entry", f, side, [("count", "name", "n")]):
                per[row.get(side)][idx] += int(flt(row.get("n")))
    site = _site(ctx)
    rows = sorted(per.items(), key=lambda kv: -(kv[1][0] - kv[1][1]))
    total, cleared = sum(v[0] for v in per.values()), sum(v[1] for v in per.values())
    out = {"chips": [{"label": "Bank payments", "value": total, "unit": "count"},
                     {"label": "Matched to a statement", "value": cleared, "unit": "count"},
                     {"label": "Not yet matched", "value": total - cleared, "unit": "count",
                      "state": "warn" if total - cleared else "ok"}],
           "checks": [check("Every bank payment should be matched to the bank statement",
                            "ok" if total and cleared == total else "bad" if total else "info",
                            f"{cleared:,} of {total:,} payments through a bank account carry a "
                            f"clearance date.")],
           "diagnosis": [], "tables": []}
    if rows:
        out["tables"].append({
            "title": "Bank accounts, most unmatched first",
            "columns": [("Account", "text"), ("Payments", "count"), ("Matched", "count"),
                        ("Not matched", "count")],
            "rows": [{"cells": [a, v[0], v[1], v[0] - v[1]],
                      "links": [{"label": "Bank Reconciliation Tool",
                                 "href": f"{site}/app/bank-reconciliation-tool"}]}
                     for a, v in rows[:8]]})
        worst = rows[0]
        if worst[1][0] - worst[1][1]:
            out["diagnosis"].append(f"{worst[0]} has the most still to match: "
                                    f"{worst[1][0] - worst[1][1]:,} of {worst[1][0]:,}.")
    return out
