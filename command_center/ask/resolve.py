"""Finding the thing a question is about.

A CEO types "UBUNTU", not "UBUNTU ORTHOPAEDIC & SPINE HOSPITAL". They type "Ejura"
and "SICHUAN". So a question has to be matched against the names actually in the
facts, and the match has to be reported rather than assumed: the answer says which
customer it decided you meant, so a wrong guess is visible instead of silently
changing what the figures are about.

Resolution runs against the fact tables rather than against Customer and Supplier
directly. Two reasons: the facts are what the answer will be computed from, so a name
that resolves here is guaranteed to have figures behind it; and it needs no permission
on the master doctypes, which on this site is not a theoretical concern -- Issue is
readable by no role at all.
"""

from __future__ import annotations

import re

import frappe

from command_center.facts.schema import FACTS

# Where each kind of party lives, and under which column.
PARTY_SOURCES = {
    "customer": [("fact_sales_invoice", "customer"),
                 ("fact_sales_order", "customer"),
                 ("fact_case", "customer")],
    "supplier": [("fact_purchase_invoice", "supplier"),
                 ("fact_purchase_invoice_line", "supplier")],
    "item": [("fact_sales_invoice_line", "item_code"),
             ("fact_stock_balance", "item_code")],
    "warehouse": [("fact_stock_balance", "warehouse")],
}

# Words that are never a party name, however much they look like one. Without this,
# "Who owes us the most" tries to resolve "Who" and "the most".
STOPWORDS = {
    "who", "what", "when", "where", "why", "how", "which", "whose", "is", "are",
    "was", "were", "do", "does", "did", "has", "have", "had", "can", "could",
    "should", "would", "will", "the", "a", "an", "and", "or", "but", "if", "then",
    "us", "we", "our", "ours", "me", "my", "i", "it", "its", "them", "they",
    "their", "you", "your", "to", "for", "from", "of", "in", "on", "at", "by",
    "with", "about", "most", "least", "more", "less", "than", "still", "open",
    "ever", "paid", "pay", "owes", "owe", "owed", "money", "order", "orders",
    "say", "tell", "show", "find", "list", "stop", "stops", "stopped", "supplying",
    "supply", "happens", "happen", "waiting", "wait", "customers", "customer",
    "suppliers", "supplier", "invoice", "invoices", "note", "delivery", "credit",
    "much", "many", "long", "now", "yet", "also", "been", "be", "get", "got",
}

MIN_TOKEN = 3


def candidates(question: str) -> list[str]:
    """Words from the question that could be part of a name.

    Deliberately generous: a wrong candidate that matches nothing costs one query,
    while a missed one makes the answer about the wrong thing or about nothing.
    """
    words = re.findall(r"[A-Za-z0-9&.\-']+", question or "")
    out = []
    for w in words:
        if len(w) < MIN_TOKEN:
            continue
        if w.lower() in STOPWORDS:
            continue
        out.append(w)
    # Adjacent pairs too, so "A1 Medicalsupplies" and "Cocoa Clinic" can match as one
    # name rather than as two weak fragments.
    pairs = [f"{a} {b}" for a, b in zip(out, out[1:])]
    # Longest first: a two-word match is better evidence than either word alone.
    return pairs + out


def resolve(question: str, business_code: str | None = None,
            kinds: tuple = ("customer", "supplier", "item", "warehouse")) -> list[dict]:
    """Every entity the question plausibly names, best evidence first.

    Returns matches rather than one answer. The caller decides what to do with an
    ambiguous question, and the interface shows what was chosen -- guessing silently
    is how a figure ends up describing the wrong company.
    """
    found: dict = {}
    for token in candidates(question):
        for kind in kinds:
            for fact, column in PARTY_SOURCES.get(kind, []):
                doctype = FACTS.get(fact)
                if not doctype:
                    continue
                filters = {column: ["like", f"%{token}%"]}
                if business_code and business_code != "__all__":
                    filters["business_code"] = business_code
                try:
                    rows = frappe.get_all(doctype, filters=filters,
                                          fields=[column], group_by=column, limit=5)
                except Exception:
                    continue
                for row in rows:
                    value = row.get(column)
                    if not value:
                        continue
                    key = (kind, value)
                    # Keep the longest matching token as the evidence: "A1 Medicalsupplies"
                    # beats "A1".
                    if key not in found or len(token) > len(found[key]["matched_on"]):
                        found[key] = {"kind": kind, "name": value,
                                      "matched_on": token, "fact": fact,
                                      "column": column}
    return sorted(found.values(),
                  key=lambda m: (-len(m["matched_on"]), m["name"]))


def best(question: str, business_code: str | None = None,
         kinds: tuple = ("customer", "supplier", "item", "warehouse")) -> dict | None:
    matches = resolve(question, business_code, kinds)
    return matches[0] if matches else None
