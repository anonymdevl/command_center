"""What each customer and supplier really owes: the ledger, beside the invoices.

The platform used to say what was owed by adding up the outstanding amounts of open
invoices. That is right only where every payment is matched to the invoice it pays.
Gigmann's are not (15 Nov 2026): its customers' open invoices came to GHS 10.07M while
the General Ledger said they owed GHS 341,565, because GHS 7.25M of payments were never
matched to an invoice, and the ageing called money already paid "1,000 days overdue".

So each business gets one row per customer and per supplier, rebuilt whole whenever
anything that can move a position changed (the General Ledger, a payment, a journal, an
invoice -- a reconciliation in ERPNext v14 and later changes the payments and invoices
without posting to the ledger, so the ledger alone is not enough to watch):

    ledger_balance   the General Ledger: debits less credits for a customer, credits
                     less debits for a supplier. What is really owed. Read as grouped
                     sums, never row by row.
    open_invoices    what the open invoices themselves say (the loaded invoice fact).
    the difference   explained in the records' own terms, so that exactly
                         open_invoices - unmatched_payments - unlinked_journals
                         - unlinked_credit_notes - other_unlinked
                         - invoices_not_updated - unexplained + unlinked_debits
                       = ledger_balance
                     `unexplained` is the remainder and is normally zero; when it is not,
                     the screens say the records disagree by that much for reasons the
                     data does not show, rather than forcing it into a category.
    ageing           the unmatched credits are set against the party's oldest open items
                     first (open invoices by due date, debits not on an invoice by posting
                     date) -- the standard assumption when payments are not matched -- and
                     what remains is aged against the data horizon. What remains is the
                     positive ledger balance; a party in credit owes nothing and is shown
                     as in credit instead.

The pieces of the explanation come from the documents ERPNext keeps current when
someone matches a payment later (Payment Entry's unallocated amount and references,
Journal Entry Account's reference), not from the ledger's own against-voucher column,
which v14 and later leave as it was posted.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import frappe
from frappe.utils import date_diff, flt, get_datetime, getdate

from command_center.ingest.base import Ingestor, ageing_bucket, require_fields

PARTIES = ("Customer", "Supplier")
INVOICE = {"Customer": "Sales Invoice", "Supplier": "Purchase Invoice"}
# The payment that reduces what a party owes: money in from a customer, out to a supplier.
REDUCING = {"Customer": "Receive", "Supplier": "Pay"}
# What is owed, from the ledger's debits and credits: SIGN * (debit - credit).
SIGN = {"Customer": 1, "Supplier": -1}
# The loaded invoice fact of each side, and its party column.
INVOICE_FACT = {"Customer": ("fact_sales_invoice", "customer"),
                "Supplier": ("fact_purchase_invoice", "supplier")}
# Anything whose change can move a position. Watched by its latest modified stamp: one
# small request each when nothing changed.
WATCHED = ("GL Entry", "Payment Entry", "Journal Entry", "Sales Invoice", "Purchase Invoice")
BUCKETS = ("not_due", "d0_30", "d31_60", "d61_90", "d90_plus")
_BUCKET_OF = {"Not yet due": "not_due", "0-30": "d0_30", "31-60": "d31_60",
              "61-90": "d61_90", "90+": "d90_plus"}
CENT = 0.005


def _r(v) -> float:
    """To the cent, and never -0.0."""
    return round(flt(v), 2) + 0.0
MONEY = ("ledger_balance", "owed", "in_credit", "open_invoices", "unmatched_payments",
         "unlinked_journals", "unlinked_credit_notes", "other_unlinked", "unlinked_debits",
         "invoices_not_updated", "unexplained") + BUCKETS + ("undated", "inside_90", "overdue")


# --------------------------------------------------------------------------- the arithmetic
def position(party_type: str, gl: dict, invoices: list, allocations: dict,
             unallocated: list, journals: list) -> dict:
    """One party's ledger balance, open invoices and the reasons they differ.

    gl           {voucher_type: (debit, credit)} from the General Ledger
    invoices     [(due_date, posting_date, outstanding)] for its submitted invoices
                 (credit notes carry a negative outstanding)
    allocations  {(payment_type, against_doctype): allocated} from its payments
    unallocated  [(payment_type, posting_date, amount)] its payments' unmatched parts
    journals     [(posting_date, debit, credit, reference_doctype or None)] its
                 journal entry lines

    Returns the explanation's columns and `items`: the open items the ageing sets the
    credits against, as [(date, amount)].
    """
    s, inv_dt, red = SIGN[party_type], INVOICE[party_type], REDUCING[party_type]
    by_type = {vt: s * (flt(d) - flt(c)) for vt, (d, c) in gl.items()}
    ledger = sum(by_type.values())
    on_invoices = by_type.get(inv_dt, 0.0)
    elsewhere = sum(v for vt, v in by_type.items()
                    if vt not in (inv_dt, "Payment Entry", "Journal Entry"))

    items = [(due or posted, flt(amt)) for due, posted, amt in invoices if flt(amt) > 0]
    open_invoices = sum(a for _, a in items)
    open_count = len(items)
    credit_notes = -sum(flt(amt) for _, _, amt in invoices if flt(amt) < 0)

    # Payments matched to documents, in owed-reducing terms (a refund counts the other way).
    matched = defaultdict(float)
    for (ptype, against), amt in allocations.items():
        matched[against] += flt(amt) if ptype == red else -flt(amt)
    matched_to_invoices = matched.pop(inv_dt, 0.0)
    matched_elsewhere = sum(matched.values())

    unmatched = sum(flt(a) for t, _, a in unallocated if t == red)
    unmatched_n = sum(1 for t, _, a in unallocated if t == red and flt(a) > 0)
    adds = [(d, flt(a)) for t, d, a in unallocated if t != red and flt(a) > 0]

    journal_credits = journal_on_invoices = journal_elsewhere = 0.0
    for posted, debit, credit, ref in journals:
        a = s * (flt(debit) - flt(credit))
        if not ref:
            if a > 0:
                adds.append((posted, a))
            else:
                journal_credits += -a
        elif ref == inv_dt:
            journal_on_invoices += a
        else:
            journal_elsewhere += a
    items += adds

    # What the ledger holds against the invoices, and what their own outstanding says.
    ledger_on_invoices = on_invoices - matched_to_invoices + journal_on_invoices
    not_updated = (open_invoices - credit_notes) - ledger_on_invoices
    other = matched_elsewhere - journal_elsewhere - elsewhere
    debits = sum(a for _, a in adds)

    out = {
        "ledger_balance": _r(ledger),
        "open_invoices": _r(open_invoices),
        "open_invoice_count": open_count,
        "unmatched_payments": _r(unmatched),
        "unmatched_payment_count": unmatched_n,
        "unlinked_journals": _r(journal_credits),
        "unlinked_credit_notes": _r(credit_notes),
        "other_unlinked": _r(other),
        "unlinked_debits": _r(debits),
        "invoices_not_updated": _r(not_updated),
    }
    # The remainder, from the rounded parts, so the identity holds to the cent.
    out["unexplained"] = _r(
        out["open_invoices"] - out["unmatched_payments"] - out["unlinked_journals"]
        - out["unlinked_credit_notes"] - out["other_unlinked"] - out["invoices_not_updated"]
        + out["unlinked_debits"] - out["ledger_balance"])
    out["items"] = items
    return out


def match_and_age(items: list, balance: float, as_of) -> dict:
    """Set the credits against the oldest open items first, and age what remains.

    items: [(date, amount)] the open items (invoices by due date, debits not on an
    invoice by posting date). balance: the ledger balance. The credits to set against
    them are whatever the items hold beyond the balance, so what remains is the balance
    itself. When the ledger holds more than the items explain, the excess has no date
    and is `undated` -- said, not guessed into a bucket. A balance of nothing or less
    ages nothing.
    """
    out = {b: 0.0 for b in BUCKETS}
    out.update({"undated": 0.0, "oldest": None})
    balance = _r(flt(balance))
    if balance <= CENT:
        return out
    as_of = getdate(as_of)
    rows = [(getdate(d) if d else None, flt(a)) for d, a in items if flt(a) > CENT]
    # Oldest first; an item with no date at all is taken as the oldest.
    rows.sort(key=lambda x: (x[0] is not None, x[0] or dt.date.min))
    credit = sum(a for _, a in rows) - balance
    if credit < 0:
        out["undated"] = -credit
        credit = 0.0
    remaining = []
    for d, a in rows:
        take = min(a, credit)
        credit -= take
        if a - take > CENT:
            remaining.append((d, a - take))
    for d, a in remaining:
        if d is None:
            out["undated"] += a
        else:
            out[_BUCKET_OF[ageing_bucket(date_diff(as_of, d))]] += a
    for k in BUCKETS + ("undated",):
        out[k] = _r(out[k])
    # Rounding each part can leave a cent between them and the balance; it goes to the
    # largest part, so the ageing always adds up to the balance.
    gap = _r(balance - sum(out[k] for k in BUCKETS + ("undated",)))
    if gap:
        big = max(BUCKETS + ("undated",), key=lambda k: out[k])
        out[big] = _r(out[big] + gap)
    dated = [d for d, _ in remaining if d]
    out["oldest"] = min(dated) if dated else None
    return out


def row_for(party_type: str, party: str, pos: dict, as_of) -> dict:
    """The fact row: the explanation, the matched ageing, and the positions it implies."""
    balance = pos["ledger_balance"]
    aged = match_and_age(pos["items"], balance, as_of)
    oldest = aged.pop("oldest")
    row = {k: v for k, v in pos.items() if k != "items"}
    row.update(aged)
    row["owed"] = _r(max(balance, 0.0))
    row["in_credit"] = _r(max(-balance, 0.0))
    row["inside_90"] = _r(sum(aged[k] for k in ("not_due", "d0_30", "d31_60", "d61_90")))
    row["overdue"] = _r(sum(aged[k] for k in ("d0_30", "d31_60", "d61_90", "d90_plus")))
    row["oldest_due_after_matching"] = oldest
    row["days_overdue"] = max(date_diff(as_of, oldest), 0) if oldest else 0
    row.update({"party_type": party_type, "party": party, "as_of_date": getdate(as_of),
                "src_doctype": party_type, "src_name": party, "src_docstatus": 1})
    return row


# --------------------------------------------------------------------------- the load
class PartyBalanceIngestor(Ingestor):
    """fact_party_balance: one row per customer and supplier, rebuilt whole.

    Registered after the invoice and payment facts, whose freshly loaded rows it reads
    for the open invoices and the payments' matches; the ledger, the unmatched payments
    and the journal lines it reads from the business's ERPNext."""

    fact = "fact_party_balance"
    source_doctype = "GL Entry"
    whole = True

    def extract(self, conn, since=None, limit=None, as_of=None):
        from command_center.ingest.base import resolve_as_of

        as_of = getdate(as_of or resolve_as_of(conn))
        mark = changed_at(conn)
        if since:
            state = self._state(conn.code)
            same_day = state.as_of_date and getdate(state.as_of_date) == as_of
            if same_day and (mark is None or mark <= get_datetime(since)):
                return None  # nothing that can move a position has changed
        gl, unallocated, journals = read_ledger(conn)
        invoices = _invoices(conn.code)
        allocations = _allocations(conn.code)
        parties = set(gl) | set(invoices) | set(unallocated) | set(journals) | set(allocations)
        rows = []
        for key in sorted(parties):
            party_type, party = key
            if not party:
                continue
            pos = position(party_type, gl.get(key, {}), invoices.get(key, []),
                           allocations.get(key, {}), unallocated.get(key, []),
                           journals.get(key, []))
            row = row_for(party_type, party, pos, as_of)
            if not any(abs(flt(row[k])) > CENT for k in MONEY):
                continue  # a settled party with nothing open: nothing to say
            row["src_modified"] = mark
            rows.append(row)
        return rows[:limit] if limit else rows


def changed_at(conn):
    """The latest modified stamp among the documents that can move a position."""
    marks = []
    for doctype in WATCHED:
        got = conn.get_list(doctype, fields=["modified"], order_by="modified desc", limit=1)
        if got and got[0].get("modified"):
            marks.append(get_datetime(got[0]["modified"]))
    return max(marks) if marks else None


def read_ledger(conn):
    """From the business's ERPNext: the ledger per party and kind of entry (grouped sums),
    the payments' unmatched parts, and the journal lines that name a party.

    Returns three maps keyed by (party_type, party)."""
    from command_center.kpi.live_departments import grouped_read

    parties = {"party_type": ["in", list(PARTIES)]}
    gl_fields = ["party_type", "party", "voucher_type", "debit_total", "credit_total"]
    rows = require_fields(grouped_read(
        conn, "GL Entry", {"is_cancelled": 0, **parties}, "party_type, party, voucher_type",
        [("sum", "debit", "debit_total"), ("sum", "credit", "credit_total")]),
        gl_fields, "GL Entry")
    gl = defaultdict(dict)
    for r in rows:
        key = (r.get("party_type"), r.get("party"))
        d, c = gl[key].get(r.get("voucher_type") or "", (0.0, 0.0))
        gl[key][r.get("voucher_type") or ""] = (d + flt(r.get("debit_total")),
                                                c + flt(r.get("credit_total")))

    pe_fields = ["name", "party_type", "party", "payment_type", "posting_date",
                 "unallocated_amount", "source_exchange_rate", "target_exchange_rate"]
    pays = require_fields(conn.get_list(
        "Payment Entry", filters={"docstatus": 1, "unallocated_amount": [">", 0], **parties},
        fields=pe_fields, order_by="name asc", limit=500000), pe_fields, "Payment Entry")
    unallocated = defaultdict(list)
    for p in pays:
        # In the party account's currency: the money in came out of it (source), the
        # money out went into it (target).
        rate = flt(p.get("source_exchange_rate") if p.get("payment_type") == "Receive"
                   else p.get("target_exchange_rate")) or 1.0
        unallocated[(p.get("party_type"), p.get("party"))].append(
            (p.get("payment_type"), p.get("posting_date"), flt(p.get("unallocated_amount")) * rate))

    je_fields = ["parent", "party_type", "party", "debit", "credit", "reference_type",
                 "reference_name"]
    lines = require_fields(conn.get_list(
        "Journal Entry Account", filters={"docstatus": 1, **parties}, fields=je_fields,
        order_by="name asc", limit=500000, parent_doctype="Journal Entry"),
        je_fields, "Journal Entry Account")
    # Posting dates only for the lines the ageing needs: those adding to what is owed
    # without being on an invoice.
    need = sorted({x["parent"] for x in lines if not x.get("reference_name")
                   and SIGN.get(x.get("party_type"), 0) * (flt(x.get("debit")) - flt(x.get("credit"))) > 0})
    dated = {}
    for i in range(0, len(need), 200):
        part = need[i:i + 200]
        for j in require_fields(conn.get_list("Journal Entry", filters={"name": ["in", part]},
                                              fields=["name", "posting_date"], limit=len(part)),
                                ["name", "posting_date"], "Journal Entry"):
            dated[j["name"]] = j.get("posting_date")
    journals = defaultdict(list)
    for x in lines:
        ref = x.get("reference_type") if x.get("reference_name") else None
        journals[(x.get("party_type"), x.get("party"))].append(
            (dated.get(x["parent"]), x.get("debit"), x.get("credit"), ref))
    return gl, unallocated, journals


def _invoices(code) -> dict:
    """(party_type, party) -> [(due_date, posting_date, outstanding)], submitted only."""
    from command_center.facts.schema import FACTS
    out = defaultdict(list)
    for party_type, (fact, col) in INVOICE_FACT.items():
        for r in frappe.get_all(FACTS[fact], filters={"business_code": code, "src_docstatus": 1,
                                                      "outstanding_amount": ["!=", 0]},
                                fields=[col, "due_date", "posting_date", "outstanding_amount"],
                                limit=1000000):
            out[(party_type, r.get(col))].append(
                (r.get("due_date"), r.get("posting_date"), flt(r.get("outstanding_amount"))))
    return out


def _allocations(code) -> dict:
    """(party_type, party) -> {(payment_type, against_doctype): allocated}, from the loaded
    payments (submitted only), as grouped sums."""
    from frappe.query_builder.functions import Sum

    from command_center.facts.schema import FACTS
    t = frappe.qb.DocType(FACTS["fact_payment_allocation"])
    q = (frappe.qb.from_(t)
         .select(t.party_type, t.party, t.payment_type, t.against_doctype, Sum(t.allocated_amount))
         .where(t.business_code == code).where(t.src_docstatus == 1)
         .where(t.party_type.isin(list(PARTIES)))
         .groupby(t.party_type, t.party, t.payment_type, t.against_doctype))
    out = defaultdict(dict)
    for party_type, party, ptype, against, amt in q.run():
        out[(party_type, party)][(ptype, against)] = flt(amt)
    return out


INGESTORS = {"fact_party_balance": PartyBalanceIngestor}
