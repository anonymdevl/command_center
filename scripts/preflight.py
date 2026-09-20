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
# 9. The signal levels are distinguishable, and still legible
# --------------------------------------------------------------------------
# Quiet's colours were once an exact copy of Muted's -- only a background alpha
# differed, by 0.01 -- so choosing between them changed nothing anyone could see.
# Nothing failed; it just quietly did not work. Both properties are asserted now.
CSS_FILE = os.path.join(ROOT, "frontend", "src", "styles", "command-center.css")
if os.path.exists(CSS_FILE):
    _css = open(CSS_FILE).read()
    _TOK = ("--crit", "--high", "--med", "--ok")

    def _block(pat):
        for m in re.finditer(pat + r"\{([^}]*)\}", _css):
            if "--crit:" in m.group(1):
                return m.group(1)
        return ""

    def _toks(b):
        out = {}
        for t in _TOK:
            m = re.search(re.escape(t) + r":\s*(#[0-9a-fA-F]{6})", b)
            if m:
                out[t] = m.group(1)
        return out

    def _rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def _lum(h):
        def f(v):
            v /= 255
            return v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4
        r, g, b = (f(c) for c in _rgb(h))
        return .2126 * r + .7152 * g + .0722 * b

    def _ratio(a, b):
        la, lb = _lum(a), _lum(b)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + .05) / (lo + .05)

    def _dist(a, b):
        import math
        ra, rb = _rgb(a), _rgb(b)
        rm = (ra[0] + rb[0]) / 2
        dr, dg, db = (ra[i] - rb[i] for i in range(3))
        return math.sqrt((2 + rm / 256) * dr * dr + 4 * dg * dg +
                         (2 + (255 - rm) / 256) * db * db)

    MIN_STEP = 25.0     # below this two levels look the same side by side
    MIN_CONTRAST = 4.5  # normal-size text

    for theme in ("dark", "light"):
        pre = r'\[data-theme="light"\]' if theme == "light" else ""
        base_sel = pre or r":root"
        surf = None
        for m in re.finditer(base_sel + r"\{([^}]*)\}", _css):
            mm = re.search(r"--surface:\s*(#[0-9a-fA-F]{6})", m.group(1))
            if mm:
                surf = mm.group(1)
                break

        previous = None
        for level, sel in (("vivid", base_sel),
                           ("muted", pre + r'\[data-signal="muted"\]'),
                           ("quiet", pre + r'\[data-signal="quiet"\]')):
            tk = _toks(_block(sel))
            check(bool(tk), f"signal level {level!r} ({theme}) defines no severity colours")
            if not tk:
                continue

            if surf:
                worst = min(_ratio(v, surf) for v in tk.values())
                check(worst >= MIN_CONTRAST,
                      f"signal {level} ({theme}): worst contrast {worst:.2f}:1 against "
                      f"{surf}, below {MIN_CONTRAST}:1. Quieter must not mean unreadable.")

            if previous:
                step = min(_dist(previous[k], tk[k]) for k in tk if k in previous)
                check(step >= MIN_STEP,
                      f"signal {level} ({theme}) is only {step:.1f} from the level "
                      f"before it. Choosing between them would change nothing visible.")
            previous = tk


# --------------------------------------------------------------------------
# KPI registry. The definition modules import no frappe, deliberately -- so the
# whole catalogue can be validated here, before anything is deployed, rather than
# failing on a screen in front of the client.
# --------------------------------------------------------------------------
from pathlib import Path as _Path
_ROOT = _Path(ROOT)
sys.path.insert(0, ROOT)
try:
    from command_center.kpi.registry import (
        REGISTRY, validate_registry, dependencies, value_dependencies)
    # Every definition module, not just sales -- a KPI registered in a module this
    # check does not import is a KPI it will call unregistered.
    from command_center.kpi import buying, sales, stock  # noqa: F401
except Exception as exc:                                   # pragma: no cover
    check(False, f"the KPI registry does not import cleanly: {exc!r}")
    REGISTRY = {}
else:
    check(bool(REGISTRY), "the KPI registry is empty")
    REGISTRY_FACTS = set(re.findall(
        r'"(fact_[a-z_]+)":\s*"Command Center Fact',
        (_Path(ROOT) / "command_center" / "facts" / "schema.py").read_text()))

    for detail in validate_registry():
        check(False, f"KPI registry: {detail}")

    for kpi in REGISTRY.values():
        check(not kpi.validate(), f"KPI {kpi.key}: " + "; ".join(kpi.validate()))
        check(bool(kpi.label.strip()), f"KPI {kpi.key} has no label")
        check(kpi.subset_of is not None or kpi.share_of is None,
              f"KPI {kpi.key} has share_of but no subset_of, so a screen can show "
              f"the percentage without saying what the whole is")

    # Every fact a KPI names must be one the schema maps. Reading the module as
    # text keeps this check free of frappe.
    _eng = (_ROOT / "command_center" / "facts" / "schema.py").read_text()
    _known = set(re.findall(r'"(fact_[a-z_]+)":\s*"Command Center Fact', _eng))
    for kpi in REGISTRY.values():
        check(kpi.fact in _known,
              f"KPI {kpi.key} reads fact {kpi.fact!r}, which facts.schema does not map")

    # And every fact the engine maps must be a doctype that exists in this app.
    for fact, doctype in re.findall(r'"(fact_[a-z_]+)":\s*"([^"]+)"', _eng):
        folder = doctype.lower().replace(" ", "_")
        path = _ROOT / "command_center" / "command_center" / "doctype" / folder
        check(path.is_dir(),
              f"facts.schema maps {fact} to {doctype!r}, but {folder}/ does not exist")


    # The map existed twice before (api/facts.ALLOWED and kpi/engine.FACTS). This
    # fails the build if a third copy appears.
    _homes = []
    for _py in sorted((_ROOT / "command_center").rglob("*.py")):
        if re.search(r'^\s*"fact_sales_invoice"\s*:\s*"Command Center Fact',
                     _py.read_text(), re.M):
            _homes.append(_py.relative_to(_ROOT).as_posix())
    check(_homes == ["command_center/facts/schema.py"],
          f"the fact-to-doctype map should be defined only in facts/schema.py, "
          f"found in: {_homes}")

    # A KPI key typed into a screen must exist. Without this a typo is a card that
    # silently does not render, which is worse than an error.
    _src = _ROOT / "frontend" / "src"
    for _jsx in sorted(_src.rglob("*.jsx")):
        _text = _jsx.read_text()
        for _arr in re.findall(r'(?:HEADLINE|FIGURES|QUALITY|keys)\s*=\s*[\[{]([^\]}]*)[\]}]',
                               _text):
            for _key in re.findall(r'"([a-z][a-z0-9_]{3,})"', _arr):
                check(_key in REGISTRY,
                      f"{_jsx.name} names KPI {_key!r}, which is not registered")

    # An ingestor's target must resolve. A class attribute declared after a property
    # of the same name silently replaces it -- `target: str = ""` sat below the
    # target property and made every ingestor write to an empty table name. Nothing
    # else in this file would have caught it.
    import ast as _ast
    _ing_dir = _ROOT / "command_center" / "ingest"
    _declared_facts = set()
    for _py in sorted(_ing_dir.glob("*.py")):
        _tree = _ast.parse(_py.read_text())
        for _cls in [n for n in _ast.walk(_tree) if isinstance(n, _ast.ClassDef)]:
            _attrs = [t.target.id for t in _cls.body if isinstance(t, _ast.AnnAssign)]
            _attrs += [t.targets[0].id for t in _cls.body
                       if isinstance(t, _ast.Assign) and isinstance(t.targets[0], _ast.Name)]
            _props = [n.name for n in _cls.body if isinstance(n, _ast.FunctionDef)
                      and any(getattr(d, "id", "") == "property" for d in n.decorator_list)]
            _shadowed = set(_attrs) & set(_props)
            check(not _shadowed,
                  f"{_py.name}: {_cls.name} declares {sorted(_shadowed)} as a class "
                  f"attribute as well as a property; the attribute wins and the "
                  f"property never runs")
            for _dup in {a for a in _attrs if _attrs.count(a) > 1}:
                check(False, f"{_py.name}: {_cls.name} declares {_dup!r} twice")
            for _t in _cls.body:
                if (isinstance(_t, _ast.AnnAssign) and getattr(_t.target, "id", "") == "fact"
                        and isinstance(_t.value, _ast.Constant) and _t.value.value):
                    _declared_facts.add(_t.value.value)
    for _f in sorted(_declared_facts):
        check(_f in REGISTRY_FACTS,
              f"an ingestor fills {_f!r}, which facts.schema does not map")

    # No orphan component. Lineage.jsx survived as dead code after Records.jsx
    # replaced it, and nothing noticed -- an unused file still gets read by the next
    # person as if it were the current answer.
    _all_jsx = sorted(_src.rglob("*.jsx"))
    _imported = set()
    for _f in _all_jsx:
        for _m in re.findall(r'from\s+"[^"]*/([A-Za-z0-9_]+)\.jsx"', _f.read_text()):
            _imported.add(_m)
    for _f in _all_jsx:
        _stem = _f.stem
        if _stem in ("App", "main"):
            continue
        check(_stem in _imported,
              f"{_f.relative_to(_ROOT).as_posix()} is imported by nothing. Delete it "
              f"or wire it up; dead code reads as the current answer.")

    # A flag tone must be a class the stylesheet defines. "bad" was invented in the
    # components and styled nowhere, so a failed load rendered as an ordinary badge.
    _css_file = _src / "styles" / "command-center.css"
    _flag_classes = set(re.findall(r"\.flag\.([a-z0-9-]+)", _css_file.read_text()))
    for _jsx in sorted(_src.rglob("*.jsx")):
        _t = _jsx.read_text()
        for _tone in set(re.findall(r'tone:\s*"([a-z0-9- ]+)"', _t)) | set(
                re.findall(r'`flag \$\{[^}]*\?\s*"([a-z0-9-]+)"\s*:\s*"([a-z0-9-]+)"',
                           _t) and
                [x for pair in re.findall(
                    r'`flag \$\{[^}]*\?\s*"([a-z0-9-]+)"\s*:\s*"([a-z0-9-]+)"', _t)
                 for x in pair]):
            for _one in _tone.split():
                check(_one in _flag_classes,
                      f"{_jsx.name} uses flag tone {_one!r}, which the stylesheet does "
                      f"not define (it has: {', '.join(sorted(_flag_classes))})")

    # Every converted screen must declare the facts it reads, so the illustrative
    # banner is derived rather than remembered.
    _app = (_src / "App.jsx").read_text()
    _ported = re.search(r'const PORTED = \{(.*?)\}', _app, re.S)
    _keys = set(re.findall(r'^\s*([a-z_]+):', _ported.group(1), re.M)) if _ported else set()
    _ctrl = (_ROOT / "command_center" / "www" / "command_center.py").read_text()
    _declared = re.search(r'VIEW_FACTS = \{(.*?)\n\}', _ctrl, re.S)
    _dkeys = set(re.findall(r'"([a-z_]+)":', _declared.group(1))) if _declared else set()
    check(_keys and _keys == _dkeys,
          f"PORTED views {sorted(_keys)} and VIEW_FACTS {sorted(_dkeys)} disagree, so "
          f"the illustrative banner would be wrong on the difference")
    for _fact in re.findall(r'"(fact_[a-z_]+)"', _declared.group(1) if _declared else ""):
        check(_fact in REGISTRY_FACTS,
              f"VIEW_FACTS names {_fact!r}, which facts.schema does not map")

    # No cycle among value dependencies. A cycle cannot be ordered, so a ratio in
    # one would be evaluated before its denominator and print an em dash -- which is
    # exactly what happened, and what the previous version of this check missed by
    # asserting check(True, ...): a check that cannot fail is worse than none,
    # because it reads like coverage.
    for key in REGISTRY:
        seen, frontier, looped = set(), {key}, False
        while frontier and not looped:
            nxt = set()
            for dep in frontier:
                for onward in value_dependencies(dep):
                    if onward == key:
                        looped = True
                    if onward not in seen:
                        seen.add(onward)
                        nxt.add(onward)
            frontier = nxt
        check(not looped,
              f"KPI {key} depends on its own value through a chain of ratios, which "
              f"cannot be evaluated in any order")


# --------------------------------------------------------------------------
print(f"preflight: {checks} checks")
if problems:
    print(f"\n{len(problems)} problem(s):\n")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("all clear")
