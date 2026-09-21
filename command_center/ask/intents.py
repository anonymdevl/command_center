"""What the platform can be asked, and what each answer is computed from.

Every intent returns three things beyond its sentence:

    checked   what it looked at, in words a manager can verify
    figures   named KPIs the answer leans on, so the same numbers appear on the cards
    records   where to open the rows behind it

`checked` is not documentation. The designed screen promises: "It shows what it checked
before it answers. Every figure came out of a query; the wording around it is written,
the numbers are not." So an intent that cannot say what it looked at is not allowed to
answer.

Nothing here writes. There is no intent that issues a credit note, raises an invoice or
moves money -- not because a rule forbids it but because no such function exists on the
read side of this platform. The screen makes that claim too, and `refuses` is how it
comes true: the request is recognised, named and declined with the reason, rather than
silently returning nothing.

All aggregation goes through ask/query.py, which uses frappe.qb. Field strings like
"sum(x) as y" do not work on this Frappe version, and api/facts.py already knew that.
"""

from __future__ import annotations

import re

import frappe

from command_center.ask import query, resolve
from command_center.kpi.engine import evaluate_set

UNPAID = {"outstanding_amount": [">", 0], "src_docstatus": 1}
SUBMITTED = {"src_docstatus": 1}
OPEN = {"is_open": 1}

WRITE_WORDS = re.compile(
    r"\b(issue|raise|create|post|send|pay|transfer|refund|cancel|delete|amend|"
    r"approve|write\s*off)\b", re.I)
WRITE_OBJECTS = re.compile(
    r"\b(credit\s*note|debit\s*note|invoice|payment|journal|salary|payroll|price|"
    r"discount|order)\b", re.I)


def _money(value, currency="GHS"):
    return f"{currency} {(value or 0):,.2f}"


def _n(value):
    return f"{(value or 0):,.0f}"


def _scoped(base: dict, business_code) -> dict:
    out = dict(base)
    if business_code and business_code != "__all__":
        out["business_code"] = business_code
    return out


# ---------------------------------------------------------------------------
def refuses(question, business_code=None):
    return {
        "intent": "refuse_write",
        "answer": (
            "I can't do that here. This screen reads the records and reports on them; "
            "it has no function that issues, amends, sends or pays anything. That is "
            "not a restriction someone switched on — the read side of the platform "
            "has no such action in it. Anything of that kind is done in ERPNext by a "
            "person, under their own permissions."
        ),
        "checked": ["the actions available to this screen, none of which change a "
                    "record"],
        "figures": [], "records": None,
    }


def has_party_ever_paid(question, business_code=None):
    match = resolve.best(question, business_code, kinds=("customer",))
    if not match:
        return None
    name = match["name"]

    paid = query.totals("fact_payment_allocation", _scoped({"party": name}, business_code),
                        measures=[("sum", "allocated_amount", "applied"),
                                  ("count", "name", "allocations"),
                                  ("max", "posting_date", "last_paid"),
                                  ("max", "days_to_pay", "slowest")])
    owed = query.totals("fact_sales_invoice",
                        _scoped({**UNPAID, "customer": name}, business_code),
                        measures=[("sum", "outstanding_amount", "owed"),
                                  ("count", "name", "invoices")])
    checked = [f"payments allocated to {name}", f"unpaid invoices for {name}"]
    records = {"fact": "fact_payment_allocation",
               "filters": _scoped({"party": name}, business_code)}

    if not paid.get("allocations"):
        return {
            "intent": "has_party_ever_paid", "entity": match, "figures": [],
            "answer": (
                f"No payment from {name} appears in the loaded records. "
                + (f"They owe {_money(owed['owed'])} across {_n(owed['invoices'])} "
                   f"invoices. " if owed.get("owed") else "")
                + "That means none was found, not that none was ever made — the "
                  "payments loaded here are those matched to a document."
            ),
            "checked": checked, "records": records,
        }

    return {
        "intent": "has_party_ever_paid", "entity": match, "figures": [],
        "answer": (
            f"Yes. {name} has paid {_money(paid['applied'])} across "
            f"{_n(paid['allocations'])} allocations, most recently on "
            f"{paid['last_paid']}"
            + (f", and at the slowest took {_n(paid['slowest'])} days"
               if paid.get("slowest") else "")
            + ". "
            + (f"They still owe {_money(owed['owed'])} across "
               f"{_n(owed['invoices'])} invoices."
               if owed.get("owed") else "Nothing is outstanding.")
        ),
        "checked": checked, "records": records,
    }


def why_order_open(question, business_code=None):
    match = resolve.best(question, business_code, kinds=("customer",))
    if not match:
        return None
    name = match["name"]
    filters = _scoped({**OPEN, "customer": name}, business_code)

    # A plain row read, not an aggregate, so get_all is the right call here.
    rows = frappe.get_all(
        "Command Center Fact Sales Order", filters=filters,
        fields=["src_name", "delivery_date", "days_late", "undelivered_value",
                "per_delivered", "status"],
        order_by="undelivered_value desc", limit=10)
    records = {"fact": "fact_sales_order", "filters": filters}

    if not rows:
        return {"intent": "why_order_open", "entity": match, "figures": [],
                "answer": f"{name} has no open orders in the loaded records.",
                "checked": [f"open sales orders for {name}"], "records": records}

    undelivered = sum(r.undelivered_value or 0 for r in rows)
    late = [r for r in rows if (r.days_late or 0) > 0]
    worst = max(rows, key=lambda r: r.days_late or 0)

    return {
        "intent": "why_order_open", "entity": match, "figures": [],
        "answer": (
            f"{name} has {_n(len(rows))} open order{'s' if len(rows) != 1 else ''} "
            f"worth {_money(undelivered)} still to deliver. "
            + (f"{_n(len(late))} are past the promised date, the worst by "
               f"{_n(worst.days_late)} days ({worst.src_name}, promised "
               f"{worst.delivery_date}, {(worst.per_delivered or 0):.0f}% delivered). "
               if late else "None is past its promised date. ")
            + "The records show the state, not the reason — that lives in the order's "
              "own comments and attachments, which open from the row."
        ),
        "checked": [f"open sales orders for {name}",
                    "promised date and delivered percentage on each"],
        "table": {"columns": [("src_name", "Order"), ("delivery_date", "Promised"),
                              ("days_late", "Days late"),
                              ("undelivered_value", "Still to deliver")],
                  "rows": [dict(r) for r in rows]},
        "records": records,
    }


def supplier_concentration(question, business_code=None):
    match = resolve.best(question, business_code, kinds=("supplier",))
    if not match:
        return None
    name = match["name"]
    scope = _scoped(SUBMITTED, business_code)

    whole = query.totals("fact_purchase_invoice_line", scope,
                         measures=[("sum", "base_net_amount", "spend")])
    theirs = query.totals("fact_purchase_invoice_line", {**scope, "supplier": name},
                          measures=[("sum", "base_net_amount", "spend")])
    items = query.distinct_count("fact_purchase_invoice_line", "item_code",
                                 {**scope, "supplier": name})
    sole = query.single_supplier_items(name, scope)

    total, mine = whole.get("spend") or 0, theirs.get("spend") or 0
    share = (mine / total * 100) if total else None

    return {
        "intent": "supplier_concentration", "entity": match, "figures": ["spend_total"],
        "answer": (
            f"{name} accounts for {_money(mine)} of {_money(total)} spend"
            + (f", {share:.1f}% of everything bought" if share is not None else "")
            + f", across {_n(items)} distinct items. "
            + (f"{_n(sole)} of those items have been bought from nobody else in the "
               f"loaded records — those are the ones with no second source. "
               if sole else
               "Every item bought from them has also been bought elsewhere. ")
            + "This is purchase history, not a supply-risk assessment: lead times and "
              "contracts are not in the loaded facts."
        ),
        "checked": [f"purchase lines from {name}",
                    "total purchase spend, from the same fact table",
                    "items with only one supplier in the loaded records"],
        "records": {"fact": "fact_purchase_invoice_line",
                    "filters": {**scope, "supplier": name}},
    }


def owes_and_waiting(question, business_code=None):

    owed = {r["customer"]: r["owed"] for r in query.grouped(
        "fact_sales_invoice", "customer", _scoped(UNPAID, business_code),
        measures=[("sum", "outstanding_amount", "owed")], limit=500)}
    waiting = {r["customer"]: r["undelivered"] for r in query.grouped(
        "fact_sales_order", "customer", _scoped(OPEN, business_code),
        measures=[("sum", "undelivered_value", "undelivered")], limit=500)}

    both = [{"customer": c, "owed": owed[c], "undelivered": waiting[c]}
            for c in owed if c in waiting]
    both.sort(key=lambda r: -(r["owed"] or 0))

    if not both:
        return {"intent": "owes_and_waiting", "figures": [],
                "answer": "No customer both owes money and is waiting on a delivery.",
                "checked": ["unpaid invoices by customer", "open orders by customer"],
                "records": None}

    return {
        "intent": "owes_and_waiting", "figures": ["ar_total", "order_book"],
        "answer": (
            f"{_n(len(both))} customers both owe us money and are waiting on goods. "
            f"Together they owe {_money(sum(r['owed'] or 0 for r in both))} while we "
            f"owe them {_money(sum(r['undelivered'] or 0 for r in both))} of "
            f"undelivered orders. Worth knowing before chasing payment: they are "
            f"owed something too."
        ),
        "checked": ["unpaid invoices grouped by customer",
                    "open orders grouped by customer",
                    "the two lists intersected"],
        "table": {"columns": [("customer", "Customer"), ("owed", "They owe us"),
                              ("undelivered", "We owe them")],
                  "rows": both[:10]},
        "records": None,
    }


def who_owes_most(question, business_code=None):

    filters = _scoped(UNPAID, business_code)
    top5 = query.grouped("fact_sales_invoice", "customer", filters,
                         measures=[("sum", "outstanding_amount", "owed"),
                                   ("count", "name", "invoices")], limit=5)
    figures = evaluate_set(["ar_total", "ar_over_90_pct"], business_code)
    whole = figures["ar_total"]["value"] or 0
    as_of = figures["ar_total"].get("as_of") or {}

    if not top5:
        return {"intent": "who_owes_most", "figures": [],
                "answer": "Nobody owes anything on the loaded invoices.",
                "checked": ["unpaid sales invoices"], "records": None}

    top = top5[0]
    share = (top["owed"] / whole * 100) if whole else None

    return {
        "intent": "who_owes_most", "figures": ["ar_total", "ar_over_90_pct"],
        "answer": (
            f"{top['customer']} owes the most: {_money(top['owed'])} across "
            f"{_n(top['invoices'])} invoices"
            + (f", {share:.1f}% of everything owed" if share is not None else "")
            + f". The five largest together are "
              f"{_money(sum(r['owed'] or 0 for r in top5))} of {_money(whole)}, "
              f"measured as at {as_of.get('date', 'the latest date the data covers')}."
        ),
        "checked": ["unpaid sales invoices grouped by customer",
                    "the receivable total, from the same fact table"],
        "table": {"columns": [("customer", "Customer"), ("owed", "Owed"),
                              ("invoices", "Invoices")],
                  "rows": top5},
        "records": {"fact": "fact_sales_invoice", "filters": filters},
    }


def party_brief(question, business_code=None):
    match = resolve.best(question, business_code, kinds=("customer", "supplier"))
    if not match:
        return None
    name, checked, parts = match["name"], [], []

    if match["kind"] == "customer":
        owed = query.totals("fact_sales_invoice",
                            _scoped({**UNPAID, "customer": name}, business_code),
                            measures=[("sum", "outstanding_amount", "owed"),
                                      ("count", "name", "invoices"),
                                      ("max", "days_overdue", "worst")])
        checked.append(f"unpaid invoices for {name}")
        parts.append(
            f"they owe {_money(owed['owed'])} across {_n(owed['invoices'])} invoices, "
            f"the oldest {_n(owed['worst'])} days past due"
            if owed.get("owed") else "they owe nothing on the loaded invoices")

        orders = query.totals("fact_sales_order",
                              _scoped({**OPEN, "customer": name}, business_code),
                              measures=[("sum", "undelivered_value", "undelivered"),
                                        ("count", "name", "orders")])
        checked.append(f"open orders for {name}")
        if orders.get("orders"):
            parts.append(f"we owe them {_money(orders['undelivered'])} of goods "
                         f"across {_n(orders['orders'])} open orders")

        cases = query.totals("fact_case",
                             _scoped({**OPEN, "customer": name}, business_code),
                             measures=[("count", "name", "cases"),
                                       ("max", "days_open", "longest")])
        checked.append(f"open complaints from {name}")
        if cases.get("cases"):
            parts.append(f"they have {_n(cases['cases'])} open complaint"
                         f"{'s' if cases['cases'] != 1 else ''}, the longest waiting "
                         f"{_n(cases['longest'])} days")
        records = {"fact": "fact_sales_invoice",
                   "filters": _scoped({**UNPAID, "customer": name}, business_code)}
    else:
        spend = query.totals("fact_purchase_invoice_line",
                             _scoped({**SUBMITTED, "supplier": name}, business_code),
                             measures=[("sum", "base_net_amount", "spend"),
                                       ("count", "name", "lines")])
        checked.append(f"purchase lines from {name}")
        if spend.get("spend"):
            parts.append(f"we have bought {_money(spend['spend'])} from them across "
                         f"{_n(spend['lines'])} lines")
        ap = query.totals("fact_purchase_invoice",
                          _scoped({**UNPAID, "supplier": name}, business_code),
                          measures=[("sum", "outstanding_amount", "owed"),
                                    ("count", "name", "invoices")])
        checked.append(f"unpaid supplier invoices for {name}")
        if ap.get("owed"):
            parts.append(f"we still owe them {_money(ap['owed'])} across "
                         f"{_n(ap['invoices'])} invoices")
        records = {"fact": "fact_purchase_invoice",
                   "filters": _scoped({**UNPAID, "supplier": name}, business_code)}

    if not parts:
        return None

    return {
        "intent": "party_brief", "entity": match, "figures": [],
        "answer": (f"On {name}: " + "; ".join(parts) + ". Those are the facts on "
                   "record. What to say with them is a judgement this platform does "
                   "not make for you."),
        "checked": checked, "records": records,
    }


# What each intent is for, in one line, for the router prompt. Beside the intents so the
# two cannot drift, and preflight fails an intent with no description -- a router cannot
# choose something nobody has described to it.
DESCRIPTIONS = {
    "refuses": "The user is asking to change, create, send, pay or delete something "
               "rather than asking a question.",
    "has_party_ever_paid": "Whether a named customer has ever paid us, what they paid, "
                           "and what they still owe.",
    "why_order_open": "Why a named customer's order is still open: how much is "
                      "undelivered and how far past the promised date.",
    "supplier_concentration": "How dependent we are on a named supplier: their share of "
                              "spend and how many items have no second source.",
    "owes_and_waiting": "Which customers both owe us money and are waiting on goods "
                        "from us.",
    "who_owes_most": "Who owes us the most, the largest debtors, and their share of the "
                     "total receivable.",
    "party_brief": "Everything on record about one named customer or supplier, for "
                   "someone about to speak to them.",
}


# How the fallback router decides. These are matchers, not permission: an intent does
# not consult them before answering, because the Gemini router may have chosen it from
# a phrasing no pattern covers -- which is the entire point of having a router. Gating
# the answer on the pattern too would have made the router useless, and did until it was
# caught by a test asking "who are we most exposed to on the money side".
MATCHERS = {
    "refuses": lambda q: bool(WRITE_WORDS.search(q) and WRITE_OBJECTS.search(q)),
    "has_party_ever_paid": lambda q, _p=re.compile(r"\bever\s+paid|\bpaid\s+us|\bpayments?\s+from\b", re.I): bool(_p.search(q)),
    "why_order_open": lambda q, _p=re.compile(r"\border\b.*\b(open|late|outstanding|delayed)|" r"why.*\border\b", re.I): bool(_p.search(q)),
    "supplier_concentration": lambda q, _p=re.compile(r"what (if|happens).*(stop|fail|lose|lost)|depend(ent|ence)|" r"concentrat", re.I): bool(_p.search(q)),
    "owes_and_waiting": lambda q, _p=re.compile(r"owe.*(wait|deliver)|(wait|deliver).*owe", re.I): bool(_p.search(q)),
    "who_owes_most": lambda q, _p=re.compile(r"\bwho\b.*\bowe|owes? us (the )?most|largest (debtor|balance)|" r"biggest debtor", re.I): bool(_p.search(q)),
    "party_brief": lambda q, _p=re.compile(r"what (should|do) i say|brief me|tell me about|summar", re.I): bool(_p.search(q)),
}

# Refusal first, then specific before general.
INTENTS = [
    refuses,
    has_party_ever_paid,
    why_order_open,
    supplier_concentration,
    owes_and_waiting,
    who_owes_most,
    party_brief,
]
