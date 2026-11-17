#!/usr/bin/env python3
"""The figure rules, held over the code (17 Nov 2026). Run by preflight.

Each rule is written against a figure that was wrong on Gigmann's live site, and each is
proved able to fail: every rule is also run over a snippet of the very code that was
wrong, and a rule that passes its own bad example fails here (CLAUDE.md rule 4).

    python3 scripts/figure_rules.py
"""

from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "command_center")
failures: list[str] = []
checks = 0


def check(ok, what):
    global checks
    checks += 1
    if not ok:
        failures.append(what)


def sources():
    for base, _dirs, files in os.walk(APP):
        if "/public" in base or "/doctype" in base:
            continue
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(base, f)
                yield os.path.relpath(path, ROOT), open(path, encoding="utf-8").read()


def _parse(src):
    try:
        return ast.parse(src)
    except SyntaxError:
        return None


# --------------------------------------------------------------------------- 1
# ERPNext's per_delivered / per_received / per_billed are shares of QUANTITY (or of
# amount), never a way to value money: SAL-ORD-2025-00942 is worth 746,980 and 86.14%
# delivered by quantity, and 746,980 x 13.86% said 103,541.78 was still to deliver where
# line by line it is 16,290. Arithmetic on them is refused; ingest/order_lines.py values
# what is left from the lines. Comparing them (< 100) is a filter and is allowed.
PER = re.compile(r"\bper_(delivered|received|billed)\b")


def per_arithmetic(src) -> list:
    """Lines doing arithmetic on a per_* percentage, or on a name it was put in."""
    tree = _parse(src)
    if tree is None:
        return []
    out = set()
    for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        held = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and PER.search(ast.unparse(node.value)):
                held |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        names = re.compile(r"\b(" + "|".join(map(re.escape, held)) + r")\b") if held else None
        for node in ast.walk(fn):
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div, ast.Sub)):
                text = ast.unparse(node)
                if PER.search(text) or (names and names.search(text)):
                    out.add(node.lineno)
    return sorted(out)


# The order book's and the late suppliers' old formulas, exactly as they were.
BAD_1 = ('def extract(d):\n'
         '    delivered = flt(d.get("per_delivered"))\n'
         '    value = flt(d.get("base_grand_total"))\n'
         '    return round(max(value * (1 - min(delivered, 100.0) / 100.0), 0), 2)\n'
         'def late(x):\n'
         '    return _num(x.get("base_grand_total")) * (100 - _num(x.get("per_received"))) / 100\n')
check(len(per_arithmetic(BAD_1)) >= 2, "rule 1 cannot fail: it passes the order book's old formula")
for path, src in sources():
    for line in per_arithmetic(src):
        check(False, f"{path}:{line}: arithmetic on ERPNext's per_delivered/per_received/"
                     f"per_billed, a share of quantity, values money by a count. Value what is "
                     f"left line by line (ingest/order_lines.py).")


# --------------------------------------------------------------------------- 2
# A cancelled document that was amended is a correction, not a withdrawal: Gigmann's 132
# "withdrawn" purchase orders (GHS 19.46M) were 5 (GHS 569,924). Every read or test of
# docstatus 2 must leave the amended originals out (kpi/live.withdrawn, or amended_from).
def docstatus_two(src) -> list:
    tree = _parse(src)
    if tree is None:
        return []
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = ast.unparse(fn)
        hit = False
        for node in ast.walk(fn):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    if (isinstance(k, ast.Constant) and k.value in ("docstatus", "src_docstatus")
                            and isinstance(v, ast.Constant) and v.value == 2):
                        hit = True
            if isinstance(node, ast.Compare) and "docstatus" in ast.unparse(node.left) and any(
                    isinstance(c, ast.Constant) and c.value == 2 for c in node.comparators):
                hit = True
        if hit and "withdrawn" not in body and "amended_from" not in body and fn.name != "withdrawn":
            out.append((fn.lineno, fn.name))
    return out


BAD_2 = ('def po_cancelled(r):\n    rows = _po(r, {"docstatus": 2}, ["base_grand_total"])\n'
         '    return len(rows)\n')
check(docstatus_two(BAD_2), "rule 2 cannot fail: it passes the old count of cancelled orders")
for path, src in sources():
    for line, name in docstatus_two(src):
        check(False, f"{path}:{line} {name}(): counts cancelled (docstatus 2) documents without "
                     f"leaving out those amended (kpi/live.withdrawn): an amendment is not a "
                     f"withdrawal.")


# --------------------------------------------------------------------------- 3
# One check of an AI's numbers (recommend/numbers.py). Three drifted apart: one allowed
# every digit of the dateline, another refused "GHS 341,565" given "341,565.00".
SECOND = re.compile(r"def (allowed_numbers|foreign_numbers|numbers_in|_numbers)\(")
for path, src in sources():
    if path.endswith("recommend/numbers.py"):
        continue
    m = SECOND.search(src)
    check(not m, f"{path}: {m.group(1) if m else ''} is a second checker of an AI's numbers; "
                 f"use recommend/numbers.problems")
check(bool(SECOND.search("def foreign_numbers(brief, given):")), "rule 3 cannot fail")
for rel in ("command_center/summary.py", "command_center/recommend/daily.py",
            "command_center/recommend/review.py", "command_center/insight/ai.py"):
    check("numbers.problems" in open(os.path.join(ROOT, rel)).read(),
          f"{rel} shows AI text without the one number check (recommend/numbers.problems)")


# --------------------------------------------------------------------------- 4
# Money in is every receipt, once: the allocations are only the part matched to invoices
# (Gigmann's October: 349,821.03 of 380,573.61).
def money_in_measure(src) -> str | None:
    m = re.search(r'key="cash_in_month".*?measure="(\w+)"', src, re.S)
    return m.group(1) if m else None


_sales = open(os.path.join(APP, "kpi", "sales.py")).read()
check(money_in_measure(_sales) == "payment_amount",
      "kpi/sales.py cash_in_month (Money in) must sum payment_amount -- every receipt once -- "
      f"not {money_in_measure(_sales)!r}")
check(money_in_measure('key="cash_in_month",\n measure="allocated_amount"') != "payment_amount",
      "rule 4 cannot fail")
_panels = open(os.path.join(APP, "api", "panels.py")).read()
_money_in = _panels.split("def fin_money_in")[1].split("\ndef ")[0]
check('"payment_amount"' in _money_in and '"allocated_amount"' not in _money_in,
      "api/panels.py fin_money_in must chart payment_amount, as Money In's card counts it")


# --------------------------------------------------------------------------- 5
# Stock going out for good is a sale or a consumption, never a move between warehouses:
# every read of the Stock Ledger's outgoing quantities goes through
# recommend/rules.stock_used, which names the voucher types.
def ledger_outflows(src) -> list:
    tree = _parse(src)
    if tree is None:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and any(isinstance(a, ast.Constant) and a.value ==
                                              "Stock Ledger Entry" for a in node.args):
            text = ast.unparse(node)
            if "actual_qty" in text and "voucher_type" not in text:
                out.append(node.lineno)
    return out


check(ledger_outflows('grouped(ctx, "Stock Ledger Entry", {"actual_qty": ["<", 0]}, "item_code", [])'),
      "rule 5 cannot fail")
for path, src in sources():
    for line in ledger_outflows(src):
        check(False, f"{path}:{line}: reads stock going out of the Stock Ledger without naming the "
                     f"voucher types, so a warehouse transfer counts as a sale "
                     f"(recommend/rules.stock_used).")


# --------------------------------------------------------------------------- 6
# Ageing is never frozen at extract time: an ingestor that writes an age column says
# what the age is worked out from (aged_by), so every load works it out again.
AGES = ("days_overdue", "days_late", "days_open", "tenure_days", "due_age(", "late_age(",
        "wait(", "tenure(")


def frozen_ages(src) -> list:
    tree = _parse(src)
    if tree is None:
        return []
    out = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or not any(
                isinstance(b, ast.Name) and b.id == "Ingestor" for b in cls.bases):
            continue
        text = ast.unparse(cls)
        if any(a in text for a in AGES) and "aged_by" not in text:
            out.append((cls.lineno, cls.name))
    return out


check(frozen_ages('class X(Ingestor):\n    def extract(self):\n        return [{"days_overdue": 3}]\n'),
      "rule 6 cannot fail")
for path, src in sources():
    if "/ingest/" not in path:
        continue
    for line, name in frozen_ages(src):
        check(False, f"{path}:{line} {name}: writes an age without aged_by, so an incremental "
                     f"load leaves it as it was on the day the document last changed.")


# --------------------------------------------------------------------------- 7
# A large read is paged by key by the connector, never by "modified > the last page's"
# here (a document sharing the boundary's timestamp was skipped) nor by a silent cap.
PAGING = re.compile(r'\[\s*">"\s*,\s*batch\s*\[\s*-1\s*\]')
check(bool(PAGING.search('filters["modified"] = [">", batch[-1]["modified"]]')), "rule 7 cannot fail")
for path, src in sources():
    if "/ingest/" in path:
        check(not PAGING.search(src), f"{path}: pages by the last row's modified stamp, which skips "
                                      f"documents that share it; read once and let the connector page")


# --------------------------------------------------------------------------- 8
# A month is full only once it is over: the one rule is kpi/engine.full_month_end.
LASTDAY = re.compile(r"\b(\w+)\s*==\s*\w+\.getdate\(\w+\.get_last_day\(\1\)\)")
check(bool(LASTDAY.search("end = h if h == u.getdate(u.get_last_day(h)) else x")), "rule 8 cannot fail")
for path, src in sources():
    if path.endswith("kpi/engine.py"):
        continue
    check(not LASTDAY.search(src), f"{path}: decides a month is full by its last day alone; use "
                                   f"kpi/engine.full_month_end (the month must also be over)")


print(f"figure rules: {checks} checks")
if failures:
    print(f"\n{len(failures)} problem(s):")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all clear")
