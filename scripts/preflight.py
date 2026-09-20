#!/usr/bin/env python3
"""Structural checks that need no bench, no site and no database.

Run before pushing. It catches the class of mistake that only shows up as a
`bench migrate` traceback — a doctype folder with a JSON but no controller, a
class name that does not match what Frappe derives from the doctype name, a
module listed in patches.txt that does not exist, a select-list string that v16
rejects.

    python3 scripts/preflight.py

Exit code 0 means nothing structural is wrong. It says nothing about whether the
figures are right.
"""

from __future__ import annotations

import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "command_center")
DOCTYPES = os.path.join(APP, "command_center", "doctype")

problems: list[str] = []
checks = 0


def check(ok: bool, detail: str):
    global checks
    checks += 1
    if not ok:
        problems.append(detail)


# --------------------------------------------------------------------------
# 1. Every doctype has a controller, and its class name is the one Frappe wants
# --------------------------------------------------------------------------
for jpath in sorted(glob.glob(os.path.join(DOCTYPES, "*", "*.json"))):
    folder = os.path.dirname(jpath)
    slug = os.path.basename(folder)
    d = json.load(open(jpath))
    name = d.get("name", slug)

    controller = os.path.join(folder, slug + ".py")
    check(os.path.exists(controller),
          f"{name}: no controller at {slug}/{slug}.py — bench migrate will fail "
          f"importing it, and the error names a 'deleted' doctype rather than a "
          f"missing file")
    if not os.path.exists(controller):
        continue

    src = open(controller).read()
    expected = name.replace(" ", "")
    found = re.findall(r"class (\w+)\(Document\)", src)
    check(expected in found,
          f"{name}: controller defines {found or 'no Document subclass'}, "
          f"Frappe will look for {expected}")

    check(os.path.exists(os.path.join(folder, "__init__.py")),
          f"{name}: missing __init__.py")
    check(d.get("module") == "Command Center",
          f"{name}: module is {d.get('module')!r}, must be 'Command Center'")
    check(json.dumps(d.get("field_order", [])) != "[]" or not d.get("fields"),
          f"{name}: has fields but no field_order")

    fieldnames = [f["fieldname"] for f in d.get("fields", [])]
    check(len(fieldnames) == len(set(fieldnames)),
          f"{name}: duplicate fieldnames")
    for fn in d.get("field_order", []):
        check(fn in fieldnames, f"{name}: field_order lists unknown field {fn!r}")


# --------------------------------------------------------------------------
# 2. Every module named in patches.txt exists
# --------------------------------------------------------------------------
patches = os.path.join(APP, "patches.txt")
if os.path.exists(patches):
    for line in open(patches):
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("#"):
            continue
        rel = line.split()[0].replace("command_center.", "", 1).replace(".", os.sep)
        check(os.path.exists(os.path.join(APP, rel + ".py")),
              f"patches.txt names {line}, which does not exist")


# --------------------------------------------------------------------------
# 3. Everything parses, and nothing bypasses ERPNext on a business document
# --------------------------------------------------------------------------
BYPASS = ("ignore_permissions", "ignore_validate", "ignore_mandatory")
OUR_TABLES = ("Command Center", "Connected Business")

for py in sorted(glob.glob(os.path.join(APP, "**", "*.py"), recursive=True)):
    rel = os.path.relpath(py, ROOT)
    try:
        tree = ast.parse(open(py).read())
    except SyntaxError as e:
        problems.append(f"{rel}: syntax error line {e.lineno}: {e.msg}")
        checks += 1
        continue

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)

    # v16 refuses SQL function strings in a select list. It raises at request
    # time, so an empty table hides it until a user hits the screen.
    #
    # Only a string in a `fields=` argument is dangerous. The same text as a dict
    # key is how Frappe names an aggregate column back to you, which is fine --
    # an earlier, blunter version of this check flagged four of those.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "fields" or not isinstance(kw.value, (ast.List, ast.Tuple)):
                continue
            for el in kw.value.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    if re.match(r"^\s*(sum|count|avg|min|max)\s*\(", el.value, re.I):
                        check(False,
                              f"{rel}: {el.value[:40]!r} in a fields= list — v16 "
                              f"rejects SQL function strings, use "
                              f"frappe.query_builder or dict syntax")

    # A permission bypass is legitimate on the platform's own tables and never
    # on a document ERPNext owns.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg not in BYPASS:
                continue
            snippet = ast.unparse(node)
            ours = any(t in snippet for t in OUR_TABLES) or "/ingest/" in rel
            check(ours,
                  f"{rel}: {kw.arg} on what looks like an ERPNext document — "
                  f"{snippet[:70]}")


# --------------------------------------------------------------------------
# 4. The assistant's catalogue stays closed
# --------------------------------------------------------------------------
ai = os.path.join(APP, "api", "ai_tools.py")
if os.path.exists(ai):
    src = open(ai).read()
    tree = ast.parse(src)
    catalogue = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "TOOL_CATALOGUE":
            catalogue = [k.value for k in node.value.keys]
    check(catalogue is not None, "ai_tools.py: no TOOL_CATALOGUE")
    for banned in ("create_document", "update_document", "submit_document",
                   "cancel_document", "apply_workflow_action"):
        check(banned not in (catalogue or []),
              f"ai_tools.py: {banned} is in the assistant's catalogue — that is "
              f"the manager's door, requirements AI-B1..AI-B8")
    check("eval(" not in src and "exec(" not in src,
          "ai_tools.py: eval or exec present")


# --------------------------------------------------------------------------
print(f"preflight: {checks} checks")
if problems:
    print(f"\n{len(problems)} problem(s):\n")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("all clear")
