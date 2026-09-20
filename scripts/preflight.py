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

# Modules whose whole job is to write configuration the platform owns -- roles,
# workspaces, number cards, its own registry and fact tables. A bypass is correct
# there and wrong everywhere else.
#
# This is an explicit list rather than a pattern, because the previous version
# passed install.py only by coincidence: the string "Command Center Manager"
# happened to contain "Command Center". A guard that passes by accident is not a
# guard.
CONFIG_MODULES = (
    "command_center/install.py",     # the manager role, the local business
    "command_center/patches/",       # upgrade steps
    "command_center/ingest/",        # the platform's own derived tables
)

# The doctypes this app ships, read from the JSON on disk rather than listed by
# hand, so the allowance cannot drift as doctypes are added. A bypass naming one
# of these is writing the platform's own data; a bypass naming anything else is
# writing a document ERPNext owns.
OUR_DOCTYPES = tuple(
    json.load(open(j))["name"]
    for j in sorted(glob.glob(os.path.join(DOCTYPES, "*", "*.json")))
)

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
            declared = any(rel.replace(os.sep, "/").startswith(m)
                           for m in CONFIG_MODULES)
            ours = declared or any(dt in snippet for dt in OUR_DOCTYPES)
            check(ours,
                  f"{rel}: {kw.arg} on a document this app does not own — "
                  f"{snippet[:70]}. If this module writes platform "
                  f"configuration, add it to CONFIG_MODULES and say why.")


# --------------------------------------------------------------------------
# 4. Who may enter is defined once
# --------------------------------------------------------------------------
# api/businesses.py owns ALLOWED_ROLES. Everything else reads it. A second
# hardcoded role check is how an access rule ends up true in one place and false
# in another -- the apps tile showing a door the page then refuses, or worse.
ROLE_LITERAL = "Command Center Manager"
MAY_NAME_THE_ROLE = (
    "command_center/api/businesses.py",  # defines it
    "command_center/install.py",         # creates it
    "command_center/desk.py",            # restricts the workspace to it
    "command_center/hooks.py",           # names it in the fixtures export filter
)
for py in sorted(glob.glob(os.path.join(APP, "**", "*.py"), recursive=True)):
    rel = os.path.relpath(py, ROOT).replace(os.sep, "/")
    if rel in MAY_NAME_THE_ROLE:
        continue
    src = open(py).read()
    tree = ast.parse(src)
    docstrings = {
        ast.get_docstring(n, clean=False)
        for n in ast.walk(tree)
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef))
    }
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and node.value == ROLE_LITERAL
                and node.value not in docstrings):
            check(False,
                  f"{rel}: hardcodes {ROLE_LITERAL!r}. Import ALLOWED_ROLES from "
                  f"command_center.api.businesses instead, so there is one "
                  f"definition of who may enter.")


# --------------------------------------------------------------------------
# 5. The assistant's catalogue stays closed
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
# 6. Every www page's controller is named where Frappe will look for it
# --------------------------------------------------------------------------
# Frappe derives the controller name from the template by replacing hyphens with
# underscores. A controller named with a hyphen is never found, get_context never
# runs, and the page renders with an empty context -- no error, no warning. Any
# guard inside that controller silently does not run.
WWW = os.path.join(APP, "www")
if os.path.isdir(WWW):
    for tpl in sorted(glob.glob(os.path.join(WWW, "*.html"))):
        stem = os.path.splitext(os.path.basename(tpl))[0]
        wanted = os.path.join(WWW, stem.replace("-", "_") + ".py")
        hyphened = os.path.join(WWW, stem + ".py")
        if "-" in stem and os.path.exists(hyphened) and not os.path.exists(wanted):
            check(False,
                  f"www/{stem}.py will never be loaded: Frappe looks for "
                  f"www/{stem.replace('-', '_')}.py. Rename it, or get_context "
                  f"and every guard in it silently do not run.")
        # A template that interpolates context must have a controller to set it.
        source = open(tpl, encoding="utf-8").read()
        needs_context = re.search(r"\{\{\s*(boot|csrf_token)\b", source)
        if needs_context:
            check(os.path.exists(wanted),
                  f"www/{stem}.html uses {{{{ boot }}}} or {{{{ csrf_token }}}} but "
                  f"there is no www/{stem.replace('-', '_')}.py to provide it.")


# --------------------------------------------------------------------------
# 7. The frontend build arrangement
# --------------------------------------------------------------------------
# A package.json with a build script at the APP ROOT makes `bench build` try to
# run it, which fails on any server without Node. Keeping it in frontend/ is what
# lets deployment stay git pull + migrate + restart.
check(not os.path.exists(os.path.join(APP, "package.json")),
      "command_center/package.json exists — bench build will try to run it and "
      "fail on servers without Node. The frontend's package.json belongs in "
      "frontend/.")
check(not os.path.exists(os.path.join(ROOT, "package.json")),
      "package.json at the repo root — same problem; keep it in frontend/.")

DIST = os.path.join(APP, "public", "command-center")
FRONTEND = os.path.join(ROOT, "frontend", "src")
MANIFEST = os.path.join(DIST, ".vite", "manifest.json")

if os.path.isdir(FRONTEND):
    # Filenames are content-hashed, so the manifest is the only way to know which
    # file the page will actually load. It must ship.
    check(os.path.exists(MANIFEST),
          "no .vite/manifest.json in command_center/public/command-center/. The "
          "page resolves the bundle through it, so without it nothing loads. "
          "Run: cd frontend && npm run build")

    if os.path.exists(MANIFEST):
        manifest = json.load(open(MANIFEST))
        entry = next((v for v in manifest.values() if v.get("isEntry")), None)
        check(entry is not None, "manifest has no entry marked isEntry")

        if entry:
            bundle = os.path.join(DIST, entry["file"])
            check(os.path.exists(bundle),
                  f"the manifest points at {entry['file']}, which is not in "
                  f"command_center/public/command-center/. The page would load "
                  f"nothing. Run: cd frontend && npm run build")
            for css in entry.get("css", []):
                check(os.path.exists(os.path.join(DIST, css)),
                      f"the manifest points at {css}, which is missing")

            # A stale bundle ships the wrong interface while the source looks
            # right -- the failure mode of committing build output.
            if os.path.exists(bundle):
                newest_src = max(
                    (os.path.getmtime(os.path.join(dirpath, f))
                     for dirpath, _, files in os.walk(FRONTEND) for f in files),
                    default=0)
                check(os.path.getmtime(bundle) >= newest_src,
                      "the committed bundle is older than frontend/src. Run: "
                      "cd frontend && npm run build")

    # Unhashed leftovers from before hashing was introduced would be served
    # forever by any browser that cached them.
    for stale in ("command-center.js", "command-center.css"):
        check(not os.path.exists(os.path.join(DIST, stale)),
              f"{stale} is a leftover from the unhashed build and should be "
              f"deleted; a browser that cached it will keep using it")


# --------------------------------------------------------------------------
# 8. One definition per component, and every card opens something
# --------------------------------------------------------------------------
# The generators are exec'd into a single namespace, so a function defined in
# two files silently shadows itself. kpi() was defined twice and the copies
# differed by one class, which is why cards looked different between views --
# the exact failure a component is meant to make impossible.
IFACE_DIR = os.path.join(ROOT, "interface")
if os.path.isdir(IFACE_DIR):
    seen: dict[str, list[str]] = {}
    for py in sorted(glob.glob(os.path.join(IFACE_DIR, "*.py"))):
        try:
            tree = ast.parse(open(py).read())
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                seen.setdefault(node.name, []).append(os.path.basename(py))
    for fn, files in sorted(seen.items()):
        check(len(files) == 1,
              f"{fn}() is defined in {', '.join(files)}. The generators share one "
              f"namespace, so the later definition silently replaces the earlier "
              f"and the two can drift apart unnoticed.")

# Every figure opens to its records. A card that does not is an exception to the
# product's central promise, and it also looks like a different component.
LEGACY_VIEWS = os.path.join(ROOT, "frontend", "src", "legacy", "views.json")
if os.path.exists(LEGACY_VIEWS):
    views = json.load(open(LEGACY_VIEWS))
    plain = sum(len(re.findall(r'<div class="kpi">', html)) for html in views.values())
    check(plain == 0,
          f"{plain} card(s) render without the clickable affordance. Every figure "
          f"opens to its records; an unwired one falls back to the shared "
          f"'unwired' panel rather than silently losing its chevron.")

# The React card must follow the same rule as the generated one.
#
# Scanned by brace depth rather than by regex. The first version of this used
# `<Figure\b([^>]*?)/>`, which cannot match an element whose props contain an
# arrow function -- `onClick={() =>` has a `>` in it. So the rule matched nothing
# and passed vacuously, which is worse than not having it.
def _jsx_elements(src: str, tag: str):
    """Yield the source of each self-closing <tag ... /> element."""
    i = 0
    needle = "<" + tag
    while True:
        i = src.find(needle, i)
        if i == -1:
            return
        depth = 0
        j = i + len(needle)
        while j < len(src):
            c = src[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            elif c == "/" and depth == 0 and src[j : j + 2] == "/>":
                yield src[i : j + 2]
                break
            j += 1
        i = j + 1


for jsx in sorted(glob.glob(os.path.join(ROOT, "frontend", "src", "views", "*.jsx"))):
    src = open(jsx).read()
    found = list(_jsx_elements(src, "Figure"))
    for element in found:
        label = re.search(r'label="([^"]*)"', element)
        check("onClick" in element,
              f"{os.path.relpath(jsx, ROOT)}: <Figure "
              f"{label.group(1) if label else '?'!r} has no onClick, so it renders "
              f"without the chevron while every generated card has one.")
    # A check that matches nothing is not a passing check.
    if "<Figure" in src:
        check(len(found) > 0,
              f"{os.path.relpath(jsx, ROOT)}: the file uses <Figure> but the "
              f"scanner found none, so the onClick rule did not run.")


# --------------------------------------------------------------------------
print(f"preflight: {checks} checks")
if problems:
    print(f"\n{len(problems)} problem(s):\n")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("all clear")
