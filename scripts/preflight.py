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
import html
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

    # The offline preview (frontend/preview.html) answers every endpoint in the
    # browser with sample figures. It is for looking at the interface on a laptop;
    # if it ever reached the bundle, the live page would quietly show samples as
    # though they were Gigmann's. vite builds index.html alone, and this proves it.
    for dirpath, _, files in os.walk(DIST):
        for f in files:
            if f.endswith((".js", ".html")):
                with open(os.path.join(dirpath, f), errors="ignore") as fh:
                    check("CC_PREVIEW_MOCK" not in fh.read(),
                          f"{f} contains the offline preview's sample API "
                          f"(frontend/preview/mock.js). The live page would show "
                          f"sample figures. Nothing in src/ may import it.")


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

# Every card that shows a real figure must open to its records.
#
# This used to be a scan for <Figure onClick=...> in the React views. Those views are
# gone: the designed screens are the product, and their figures are hydrated in place.
# Leaving the old scan would have been the third check in this file that passes
# vacuously -- it would have found no <Figure> anywhere and reported success.
#
# So the same contract is checked where the cards now live: the hydrator must clear the
# generated "not wired yet" handler and attach a real one, or a live card would still
# open the explainer that says it is not wired.
_hydrator = os.path.join(ROOT, "frontend", "src", "legacy", "hydrate.js")
_h = open(_hydrator).read()
check('card.removeAttribute("onclick")' in _h,
      "hydrate.js does not clear the generated inline onclick, so a card showing a "
      "real figure would still open the 'not wired yet' explainer.")
check("card.onclick =" in _h,
      "hydrate.js does not attach a click handler, so a hydrated card would show a "
      "real figure with no way to open its records.")
check('classList.add("clickable")' in _h,
      "hydrate.js does not mark hydrated cards clickable, so they would lose the "
      "chevron every other card has.")
check('dataset.illustrative' in _h,
      "hydrate.js does not mark unhydrated cards, so a demonstration figure would sit "
      "beside a real one with nothing to tell them apart.")


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
    from command_center.kpi import buying, operations, sales, stock  # noqa: F401
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

    for kpi in REGISTRY.values():
        if kpi.agg == "count_distinct":
            check(bool(kpi.distinct_on),
                  f"KPI {kpi.key} counts distinct values of nothing")

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

    # Every ingest module that reads from a source must check the fields came back.
    # Frappe does not always report an unknown field: Issue returned rows carrying
    # only name and modified when asked for resolution_date, and sixty cases loaded
    # blank. require_fields turns that into a sentence instead of a plausible screen.
    for _py in sorted(_ing_dir.glob("*.py")):
        if _py.name in ("__init__.py", "base.py", "registry.py"):
            continue
        _text = _py.read_text()
        if "get_list(" in _text:
            check("require_fields" in _text,
                  f"{_py.name} reads from a source but never calls require_fields, so "
                  f"a field the source silently drops becomes a blank fact column")

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

    # The drawer's nested drill must know the grouping column for every fact, and it
    # must be the same column the server concentrates on -- otherwise clicking a row
    # in "where it is concentrated" filters by something else and the numbers move.
    _rec = (_src / "components" / "Records.jsx").read_text()
    _dim_block = re.search(r"const DIMENSION_FIELD = \{(.*?)\};", _rec, re.S)
    _dims = dict(re.findall(r"(fact_[a-z_]+):\s*\"([a-z_]+)\"",
                            _dim_block.group(1) if _dim_block else ""))
    _pres = (_ROOT / "command_center" / "facts" / "presentation.py").read_text()
    for _fact in REGISTRY_FACTS:
        check(_fact in _dims,
              f"Records.jsx DIMENSION_FIELD has no entry for {_fact}, so its drawer "
              f"cannot drill into a concentration row")
        _spec = re.search(r'"%s": \{(.*?)\n    \},' % _fact, _pres, re.S)
        if _spec and _fact in _dims:
            _on = re.search(r'"concentrate_on": \("([a-z_]+)"', _spec.group(1))
            if _on:
                check(_dims[_fact] == _on.group(1),
                      f"{_fact}: the drawer drills on {_dims[_fact]!r} but the server "
                      f"concentrates on {_on.group(1)!r}")

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

    # Every KPI named in the hydration map must exist, and every card label it names
    # must actually be on that screen. A label that no longer matches is a card that
    # silently stays illustrative, and a key that does not exist is the same -- neither
    # raises, so neither would ever be noticed.
    _hyd = (_src / "legacy" / "hydrate.js").read_text()
    _views_json = json.loads((_src / "legacy" / "views.json").read_text())
    def _map_sections(name):
        """Each view's slice of one label->KPI map in hydrate.js.

        Split per view rather than matched as a block: an empty map written `proc: {},`
        has no closing brace on its own line, so a block pattern ran straight past it
        and read the next view's labels as belonging to it. One definition, because
        there are now two such maps -- cards and tiles -- and they must be read the
        same way.
        """
        body = re.search(r"export const %s = \{(.*?)\n\};" % name, _hyd, re.S)
        src = body.group(1) if body else ""
        starts = [(m.group(1), m.end()) for m in re.finditer(r"^  (\w+): \{", src, re.M)]
        out = []
        for i, (view, frm) in enumerate(starts):
            to = (starts[i + 1][1] - len(f"  {starts[i + 1][0]}: {{")
                  if i + 1 < len(starts) else len(src))
            out.append((view, src[frm:to]))
        return out

    for _view, _body in _map_sections("CARD_KPIS"):
        check(_view in _views_json,
              f"hydrate.js maps cards for {_view!r}, which is not a designed view")
        for _label, _key in re.findall(r'^\s*"?([^":\n]+?)"?:\s*"([a-z][a-z0-9_]+)"',
                                       _body, re.M):
            _label = _label.strip()
            check(_key in REGISTRY,
                  f"hydrate.js maps {_view}/{_label!r} to KPI {_key!r}, which is not "
                  f"registered")
            _seen_keys = re.findall(r':\s*"([a-z][a-z0-9_]+)"', _body)
            check(_seen_keys.count(_key) == 1,
                  f"{_view}: two cards both map to KPI {_key!r}, so the screen would "
                  f"show one number twice under labels that mean different things")
            check(f'class="lab">{_label}<' in _views_json.get(_view, ""),
                  f"hydrate.js maps a card labelled {_label!r} on {_view}, but no card "
                  f"on that screen carries that label, so it would stay illustrative")

    # The same for the tiles, which had no hydration at all until now: hydrate.js
    # matched .kpi only, so thirty-four .bk tiles were illustrative with no mechanism
    # that could ever make one live.
    # The query itself, not the string ".bk": the file says ".bk" in half a dozen
    # comments, so looking for that passed on a hydrator that queried nothing -- a check
    # that cannot fail, for the third time in this project.
    check('querySelectorAll(".bk")' in _hyd,
          "hydrate.js does not query .bk tiles, so every tile on six screens shows a "
          "designed figure with no way to make it live")
    # The pill the hydrator appends to a tile needs the one rule that spaces it off the
    # footnote. Without it the mark still renders, so nothing would look broken -- it
    # would just sit against the text, which is how a design regression ships unnoticed.
    check(".bk>.flag{" in _css_file.read_text().replace(" ", ""),
          "the stylesheet has no rule for a flag that is a direct child of .bk, so the "
          "illustrative and as-at marks on tiles have no spacing")

    def _tiles_on(view):
        """(label, block) per tile, with the label as the browser reads it.

        A nav label is React text and carries a real '&'; a tile label goes through
        innerHTML and carries '&amp;'. The map is keyed on what textContent returns, so
        the markup is unescaped before it is compared.
        """
        src = _views_json.get(view, "")
        # Each tile ends where the next begins. A fixed window instead of that bound
        # was the fourth check in this project that could not fail: with a tile's label
        # deleted, its window ran on into the following tile, read that tile's label,
        # and the count still came out right.
        _at = [m.start() for m in re.finditer(r'<div class="bk[^"]*"[^>]*>', src)]
        found = []
        for _i, _from in enumerate(_at):
            block = src[_from: _at[_i + 1] if _i + 1 < len(_at) else len(src)]
            label = re.search(r'class="l">(.*?)</div>', block, re.S)
            foot = re.search(r'class="v">(.*?)</div>', block, re.S)
            if label:
                found.append((html.unescape(label.group(1)).strip(),
                              html.unescape(foot.group(1)) if foot else ""))
        # Proof the reader is not silently skipping tiles, which is how a check comes to
        # cover nothing: every .bk on the screen must have been read.
        _on_screen = src.count('class="bk')
        check(len(found) == _on_screen,
              f"{view}: read {len(found)} tiles but the screen has {_on_screen}, so "
              f"some tile has no label where one is expected and would never be checked")
        return found

    _tile_views = {v for v in _views_json if 'class="bk' in _views_json[v]}
    _tile_mapped = dict(_map_sections("TILE_KPIS"))
    for _view in sorted(_tile_views):
        check(_view in _tile_mapped,
              f"{_view} has tiles but hydrate.js TILE_KPIS says nothing about it, so "
              f"nobody has decided whether any of them can be made live")
    for _view, _body in _tile_mapped.items():
        check(_view in _views_json,
              f"hydrate.js maps tiles for {_view!r}, which is not a designed view")
        _labels = dict(_tiles_on(_view))
        _keys = re.findall(r'\bkey:\s*"([a-z][a-z0-9_]+)"', _body)
        for _label, _key in re.findall(
                r'^\s*"?([^":\n]+?)"?:\s*\{\s*key:\s*"([a-z][a-z0-9_]+)"', _body, re.M):
            _label = _label.strip()
            check(_key in REGISTRY,
                  f"hydrate.js maps tile {_view}/{_label!r} to KPI {_key!r}, which is "
                  f"not registered")
            check(_keys.count(_key) == 1,
                  f"{_view}: two tiles both map to KPI {_key!r}, so the screen would "
                  f"show one number twice under labels that mean different things")
            check(_label in _labels,
                  f"hydrate.js maps a tile labelled {_label!r} on {_view}, but no tile "
                  f"on that screen carries that label, so it would stay illustrative")
            # A figure typed into a tile's footnote drifts the moment the data is
            # reloaded. The hydrator replaces such a footnote with the KPI's note, so a
            # KPI with no note would leave the stale figure sitting under the live one.
            if re.search(r"\d", _labels.get(_label, "")):
                check(bool(REGISTRY[_key].note if _key in REGISTRY else False),
                      f"{_view}: the tile {_label!r} has a figure in its footnote and "
                      f"KPI {_key!r} has no note to replace it with, so the designed "
                      f"figure would stay beside a live one")

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
# System reads: only ingest, only local, and ingest must actually ask for one
# --------------------------------------------------------------------------
# Issue on this site has Custom DocPerm rows granting read to no role. Custom DocPerms
# replace the standard ones, so it is readable by nobody -- and frappe.get_list does not
# raise for that, it strips every field and returns rows carrying only name and modified.
# Sixty complaints loaded blank. Ingest therefore reads as the system; these checks keep
# that narrow and make sure it is still asked for.
_base = open(os.path.join(ROOT, "command_center", "connectors", "base.py")).read()
_loc = open(os.path.join(ROOT, "command_center", "connectors", "local.py")).read()
_ing_api = open(os.path.join(ROOT, "command_center", "api", "ingest.py")).read()

check("def as_system" in _base, "connectors/base.py has no as_system")
# The method body, not a fixed number of characters: the first version looked at the
# first 800 and saw only the docstring, so it reported the guard missing when it was
# there. A check that is wrong about the code is as bad as one that cannot fail.
_as_sys = _base.split("def as_system")[1]
_as_sys = _as_sys[: _as_sys.find("\n    def ")] if "\n    def " in _as_sys else _as_sys
check("if not self.is_local" in _as_sys,
      "as_system does not refuse a remote connector, so a caller could believe they had "
      "escalated on a peer when nothing changed")
check("frappe.get_all if self.system else frappe.get_list" in _loc,
      "local connector does not switch to an unfiltered read for a system connector, so "
      "a doctype readable by no role still returns rows with every field stripped")
for _fn in ("def run(", "def reconcile(", "def scheduled_load("):
    _body = _ing_api.split(_fn)[1][:1200] if _fn in _ing_api else ""
    check("as_system()" in _body,
          f"api/ingest.py {_fn.strip('def (')} does not take a system connector, so its "
          f"reads are scoped to whoever happened to call it")
# And nothing outside ingest may ask for one.
for _py in sorted(_Path(ROOT).joinpath("command_center").rglob("*.py")):
    if _py.name in ("base.py",) or "ingest" in _py.as_posix():
        continue
    check("as_system(" not in _py.read_text(),
          f"{_py.relative_to(_Path(ROOT)).as_posix()} asks for a system read. Only ingest "
          f"may: everything else is read on behalf of a person.")

# --------------------------------------------------------------------------
# The question box: read-only, honest about failure, and one screen not two
# --------------------------------------------------------------------------
_ask_engine = open(os.path.join(ROOT, "command_center", "ask", "engine.py")).read()
_ask_intents = open(os.path.join(ROOT, "command_center", "ask", "intents.py")).read()
_ask_api = open(os.path.join(ROOT, "command_center", "api", "ask.py")).read()
_ask_query = open(os.path.join(ROOT, "command_center", "ask", "query.py")).read()

# It must not be able to change anything. The screen promises a credit note is refused
# "not because it was told to, but because no such function exists".
for _name, _src in (("ask/engine.py", _ask_engine), ("ask/intents.py", _ask_intents),
                    ("api/ask.py", _ask_api), ("ask/query.py", _ask_query)):
    check("api import actions" not in _src and "api.actions" not in _src,
          f"{_name} can reach actions.py. The question box is read-only by "
          f"construction, which is what makes the refusal true rather than a promise.")
    for _write in (".insert(", ".save(", ".submit(", "db.set_value(", "db.delete("):
        check(_write not in _src,
              f"{_name} contains {_write} — the question box writes nothing")

# Aggregation must not use SQL function strings: this Frappe version rejects them, and
# the first draft of intents.py used them throughout.
for _name, _src in (("ask/intents.py", _ask_intents), ("ask/query.py", _ask_query)):
    check(not re.search(r'fields=\[[^\]]*\b(sum|count|avg|max|min)\s*\(',
                        _src, re.I | re.S),
          f"{_name} passes a SQL function string in fields=. Use ask/query.py, which "
          f"builds aggregates with frappe.qb like api/facts.py does.")

# A broken intent must not read as a question the platform cannot answer.
check('"failed": True' in _ask_engine,
      "ask/engine.py does not distinguish a failure from an unanswerable question, so "
      "a bug inside an intent would come back as 'I do not understand'")
check("failures.append" in _ask_engine,
      "ask/engine.py swallows intent exceptions without recording them")

# Every intent must say what it checked; the screen promises it.
_intent_names = re.findall(r"^def ([a-z_]+)\(question", _ask_intents, re.M)
check(len(_intent_names) >= 5,
      f"only {len(_intent_names)} intents found in ask/intents.py")
for _fn in _intent_names:
    _body = _ask_intents.split(f"def {_fn}(question")[1].split("\ndef ")[0]
    check('"checked"' in _body,
          f"intent {_fn} returns no 'checked', but the screen promises it shows what "
          f"it checked before it answers")

# One question screen, not two.
_views_j = json.loads(open(os.path.join(ROOT, "frontend", "src", "legacy",
                                        "views.json")).read())
_nav_j = json.loads(open(os.path.join(ROOT, "frontend", "src", "legacy",
                                      "nav.json")).read())
_nav_keys = [i["key"] for g in _nav_j["groups"] for i in g["items"]]
check("search" not in _views_j and "search" not in _nav_keys,
      "'Find anything' is still present. It and 'Ask the business' were two doors to "
      "one room; the merge is not done while both exist.")
check("ask" in _views_j and "ask" in _nav_keys,
      "'Ask the business' is missing — that is the screen the merge keeps")
check('k === "search"' in open(os.path.join(ROOT, "frontend", "src",
                                            "App.jsx")).read(),
      "an old #search link has nowhere to land; it should redirect to the one screen")

# --------------------------------------------------------------------------
# The Gemini router: no key in the repo, no blind trust, always a fallback
# --------------------------------------------------------------------------
# A key committed to git is a key that has leaked. This scans every tracked text file,
# not just the ask/ package, because the likeliest place for one to end up is a script
# or a note somebody wrote while testing.
_KEYISH = re.compile(r"AIza[0-9A-Za-z_\-]{30,}")
for _path in sorted(_Path(ROOT).rglob("*")):
    if not _path.is_file():
        continue
    _rel = _path.relative_to(_Path(ROOT)).as_posix()
    if (_rel.startswith(("node_modules/", ".git/"))
            or "/node_modules/" in _rel or _path.suffix in (".png", ".jpg", ".woff2")):
        continue
    try:
        _text = _path.read_text(errors="ignore")
    except Exception:
        continue
    check(not _KEYISH.search(_text),
          f"{_rel} contains something shaped like a Google API key. Keys belong in "
          f"site_config.json on the server, never in a tracked file.")

_gem = open(os.path.join(ROOT, "command_center", "ask", "gemini.py")).read()
_llm = open(os.path.join(ROOT, "command_center", "ask", "planner_llm.py")).read()
_eng = open(os.path.join(ROOT, "command_center", "ask", "engine.py")).read()

check("frappe.conf.get" in _gem,
      "gemini.py does not read the key from site_config; it must not come from "
      "anywhere a repository can hold")
check("timeout=" in _gem,
      "gemini.py calls the API with no timeout, so a slow third party would hang the "
      "screen a manager is waiting on")
check('"-latest"' in _gem or "not \"-latest\"" in _gem or "-latest" in _gem,
      "gemini.py should record why the model name is pinned rather than floating")
check("DEFAULT_MODEL" in _gem and "-latest" not in _gem.split("DEFAULT_MODEL =")[1][:60],
      "the default Gemini model is a floating -latest name, so a deployed "
      "demonstration would change behaviour with no deploy")

# The router names an intent. It must be checked against the registry, and a subject it
# did not take from the question must not be trusted.
check("if chosen not in names" in _llm,
      "planner_llm.py does not validate the intent name against the registry, so an "
      "invented handler name would be acted on")
check("not any(m[\"name\"] == subject for m in found)" in _llm
      or "not any(m['name'] == subject for m in found)" in _llm,
      "planner_llm.py does not check the subject came from the question, so the answer "
      "could be about a company the user never mentioned")
check("Never state any number" in _llm,
      "the router prompt does not forbid the model stating a figure")

# The patterns must remain reachable whatever the router does.
check("for intent in intents.INTENTS:" in _eng,
      "engine.plan() no longer falls back to the patterns, so no key or no network "
      "would leave the screen with nothing")
check('result["planner"] = "gemini"' in _eng,
      "engine.plan() does not record that the router chose, so nobody could tell which "
      "path answered")

# An intent must not gate on the question's wording. The matcher routes; the intent
# answers. When they were the same thing, a question the router classified correctly was
# still refused by the intent's own regex, which made the router pointless.
check("if not re.search(" not in _ask_intents,
      "an intent in ask/intents.py still gates on the question's wording. The matcher "
      "decides routing; an intent chosen by the model must answer without re-checking "
      "the phrasing, or the router is overruled by the patterns it replaces.")
check("MATCHERS" in _ask_intents and "MATCHERS.get(" in _eng,
      "the fallback no longer routes through MATCHERS")
_matcher_block = re.search(r"MATCHERS = \{(.*?)\n\}", _ask_intents, re.S)
_matched = set(re.findall(r'"([a-z_]+)":', _matcher_block.group(1) if _matcher_block else ""))

_ans_js = open(os.path.join(ROOT, "frontend", "src", "legacy", "answer.js")).read()
check("p.planner" in _ans_js and "Gemini" in _ans_js,
      "answer.js does not disclose which path read the question. A reader is entitled "
      "to know whether a model was involved in interpreting their words.")
check("not from the model" in _ans_js,
      "answer.js does not state that the figures did not come from the model")

# Every intent the router is offered must have a description.
_names = re.findall(r"^def ([a-z_]+)\(question", _ask_intents, re.M)
_desc_block = re.search(r"DESCRIPTIONS = \{(.*?)\n\}", _ask_intents, re.S)
_described = set(re.findall(r'"([a-z_]+)":', _desc_block.group(1) if _desc_block else ""))
for _n in _names:
    check(_n in _described,
          f"intent {_n} has no DESCRIPTIONS entry; a router cannot choose something "
          f"nobody described to it")
    check(_n in _matched,
          f"intent {_n} has no MATCHERS entry, so the pattern fallback can never reach "
          f"it and it would only work while Gemini is up")

# --------------------------------------------------------------------------
# The sidebar captions, and the screen headings agreeing with them
# --------------------------------------------------------------------------
# Michael settled these nineteen captions in order. They live in the NAV tuples in
# interface/build.py and nowhere else, and each screen's own <h3> has to say the same
# thing -- a sidebar reading "Sales and Payments" that opens a screen headed "Sales and
# money owed to us" is the same fault as a card whose label and figure disagree.
CAPTIONS = [
    "Home", "Executive Summary", "Today", "Business Overview", "Business Health",
    "Risk and Compliance", "Approvals", "Outstanding Tasks", "Ask AI", "Reports",
    "Sales and Payments", "Buying and Suppliers", "Stock & Warehouses",
    "Project Insights", "Customer Service & Issues", "Finances", "HR & Payroll",
    "Systems and Access", "Internal Audit",
]
_nav = json.loads(open(os.path.join(ROOT, "frontend", "src", "legacy",
                                    "nav.json")).read())
_views = json.loads(open(os.path.join(ROOT, "frontend", "src", "legacy",
                                      "views.json")).read())
_items = [i for g in _nav["groups"] for i in g["items"]]
_labels = [i["label"] for i in _items]
check(_labels == CAPTIONS,
      f"the sidebar captions are not the agreed nineteen in order.\n      got:  {_labels}"
      f"\n      want: {CAPTIONS}")

# A React-rendered label must carry a real ampersand, not an HTML entity, or it shows
# literally as "&amp;". The h3 goes through innerHTML and needs the entity.
for _lab in _labels:
    check("&amp;" not in _lab,
          f"nav label {_lab!r} contains an HTML entity. nav.json is rendered as text by "
          f"React, so it would display the entity itself.")

for _item in _items:
    _html = _views.get(_item["key"]) or ""
    _m = re.search(r"<h3>(.*?)</h3>", _html)
    if not _m:
        continue  # Home has no heading; it opens with the greeting
    _h3 = _m.group(1).replace("&amp;", "&").strip()
    check(_h3 == _item["label"],
          f"screen {_item['key']} is headed {_h3!r} but its sidebar caption is "
          f"{_item['label']!r}")

# --------------------------------------------------------------------------
# The deploy script's order, because the order is why it exists
# --------------------------------------------------------------------------
_deploy = open(os.path.join(ROOT, "deploy.sh")).read()
# Anchored on the commands, not on prose: the first version matched the word
# "migrate" in this script's own header comment and reported the order wrong.
_steps = ('git -C "$APP_DIR" pull', 'bench --site "$SITE" migrate',
          "command_center.api.ingest.run", "bench restart")
_order = [_deploy.find(x) for x in _steps]
check(all(i != -1 for i in _order),
      "deploy.sh is missing one of pull, migrate, ingest or restart")
check(_order == sorted(_order),
      "deploy.sh runs its steps out of order: pull, then migrate, then ingest, then "
      "restart. Ingesting before migrate hits a missing table; restarting before "
      "ingest serves half an update.")
check("FULL=1" in _deploy.split("seed.reseed")[-1][:400],
      "deploy.sh reseeds without forcing a full reload, so the fact rows of the "
      "deleted documents would survive and keep being counted.")
check("--ff-only" in _deploy,
      "deploy.sh pulls without --ff-only, so a diverged server checkout would merge "
      "silently instead of stopping.")

# --------------------------------------------------------------------------
# The design foundations of the restyle (17 Oct 2026)
# --------------------------------------------------------------------------
# The first design drifted into looking generated partly because nothing held it to
# one system: twenty-five font sizes, sixteen accents, colours typed into rules.
# These hold the foundations in place.
if os.path.exists(CSS_FILE):
    _css = open(CSS_FILE).read()

    def _first(sel):
        m = re.search(r"(?:^|\}|\*/)\s*" + sel + r"\{([^}]*)\}", _css)
        return m.group(1) if m else ""

    _dark, _light = _first(r":root"), _first(r'\[data-theme="light"\]')
    _colour = lambda v: v.startswith(("#", "rgb", "linear-gradient"))
    _dtok = {k for k, v in re.findall(r"(--[\w-]+):\s*([^;]+)", _dark) if _colour(v.strip())}
    _ltok = {k for k, v in re.findall(r"(--[\w-]+):\s*([^;]+)", _light)}
    _missing = sorted(_dtok - _ltok)
    check(bool(_dtok) and not _missing,
          "the light theme does not define " + ", ".join(_missing or ["any colour token"])
          + ". A colour defined only for dark shows its dark value in light mode.")

    # One type scale. A px font size outside the token definitions is a size nobody
    # chose from the scale -- the drift this replaces.
    _rules = re.sub(r"(?:^|\}|\*/)\s*(?::root|\[data-theme=\"light\"\])\{[^}]*\}", "}", _css)
    _loose = sorted(set(re.findall(r"font(?:-size)?:\s*(?:\d{3}\s+)?(\d+(?:\.\d+)?px)", _rules)))
    check(not _loose,
          "the stylesheet sets font sizes off the type scale: " + ", ".join(_loose)
          + ". Use var(--fs-...) from p1.py.")
    _wloose = sorted(set(re.findall(r"font(?:-weight)?:\s*(\d{3})\b", _rules)))
    check(not _wloose,
          "the stylesheet sets font weights off the four-weight scale: " + ", ".join(_wloose)
          + ". Use var(--fw-regular|medium|semibold|bold) from p1.py.")

    # The font ships with the app. A web-font URL would make every page load ask a
    # third party for the typeface -- and fail offline.
    for _f in (CSS_FILE, os.path.join(ROOT, "frontend", "index.html"),
               os.path.join(APP, "www", "command-center.html")):
        _t = open(_f).read()
        for _host in ("fonts.googleapis.com", "fonts.gstatic.com", "use.typekit.net"):
            check(_host not in _t,
                  f"{os.path.basename(_f)} loads a font from {_host}. Fonts are bundled "
                  f"(@fontsource-variable/manrope); nothing may fetch one at runtime.")
    check(re.search(r"--sans:\s*'Manrope Variable'", _dark) is not None,
          "--sans does not start with 'Manrope Variable', so the bundled font is "
          "not the one the interface uses.")
    if os.path.isdir(DIST):
        check(any(f.startswith("manrope-latin-wght") and f.endswith(".woff2")
                  for f in os.listdir(DIST)),
              "the bundle has no Manrope latin woff2, so the font would fall back to "
              "the system face. Run: cd frontend && npm run build")

    # Every accent the picker offers has CSS in both themes, and the default is one
    # of them. An accent without rules silently shows the base colour.
    _extras = json.load(open(os.path.join(ROOT, "frontend", "src", "legacy", "extras.json")))
    _acc = [a["key"] for a in _extras.get("accents", [])]
    check(bool(_acc), "extras.json lists no accents")
    for _a in _acc:
        check(f'[data-accent="{_a}"]{{' in _css and f'[data-theme="light"][data-accent="{_a}"]{{' in _css,
              f"accent {_a!r} is offered by the picker but has no CSS for both themes")
    _app = open(os.path.join(ROOT, "frontend", "src", "appearance.js")).read()
    _dm = re.search(r'accent:\s*"(\w+)"', _app)
    check(bool(_dm) and _dm.group(1) in _acc,
          f"appearance.js defaults to accent {(_dm.group(1) if _dm else None)!r}, "
          f"which is not one of {_acc}")
    for _f in (os.path.join(ROOT, "frontend", "index.html"),
               os.path.join(APP, "www", "command-center.html")):
        _m = re.search(r'data-accent="(\w+)"', open(_f).read())
        check(bool(_m) and _m.group(1) in _acc,
              f"{os.path.basename(_f)} starts on accent {(_m.group(1) if _m else None)!r}, "
              f"which has no CSS")

# --------------------------------------------------------------------------
# The shell has one owner (restyle phase 3)
# --------------------------------------------------------------------------
# Its rules were spread over four generator files, each overriding the last, so a
# change in one was undone by another further down. shell.py now owns them, and no
# other generator may style a shell class again.
_SHELL_CLASSES = ("shell", "col", "side", "brand", "logo", "nav", "navsec", "navgrp", "navi",
                  "biz", "biz-row", "biz-sw", "biz-menu", "biz-opt", "topnav", "ask", "ask-go",
                  "pill", "ib", "who", "av", "whotxt", "appearmenu", "swatches", "dnote")
_shell_sel = re.compile(r"\.(%s)(?![\w-])" % "|".join(map(re.escape, _SHELL_CLASSES)))
_span = re.compile(r'(?:\b[A-Z_]*CSS\s*=\s*(?:[A-Z_]+\s*\+\s*)*"""|\+\s*""")(.*?)"""', re.S)
for _f in sorted(os.listdir(os.path.join(ROOT, "interface"))):
    if not _f.endswith(".py") or _f == "shell.py":
        continue
    _src = open(os.path.join(ROOT, "interface", _f)).read()
    _hits = sorted({m.group(0) for css in _span.findall(_src)
                    for sel in re.findall(r"([^{}]+)\{[^{}]*\}", css)
                    for m in _shell_sel.finditer(sel)})
    check(not _hits,
          f"interface/{_f} styles shell classes {', '.join(_hits)}. The shell is styled "
          f"in interface/shell.py only, which is appended last.")
_views = json.load(open(os.path.join(ROOT, "frontend", "src", "legacy", "views.json")))
_inview = sorted({c for h in _views.values() for c in _SHELL_CLASSES
                  if re.search(r'class="[^"]*\b%s\b' % re.escape(c), h)})
check(not _inview,
      f"a screen uses shell class(es) {', '.join(_inview)}, so restyling the shell would "
      f"change that screen too. Rename the screen's class.")

# --------------------------------------------------------------------------
# The analyst reads everything it may and changes nothing (decision of 18 Oct 2026)
# --------------------------------------------------------------------------
# Gemini is used to its full capacity for anything informational, and may never create,
# edit, submit, cancel or delete anything, whoever approves. That holds only while no
# code the analyst can reach has a write in it, so the whole question path is scanned.
_WRITE = re.compile(
    r"\.(insert|save|submit|cancel|delete|db_set|db_insert|db_update)\(|"
    r"frappe\.(delete_doc|new_doc|get_doc|rename_doc|set_value|enqueue|call)\b|"
    r"frappe\.db\.(sql|set_value|delete|insert|commit|set_single_value|bulk_insert|truncate)\b|"
    r"frappe\.client\.(insert|save|submit|cancel|delete|set_value|insert_many|bulk_update|rename_doc)\b|"
    r"from\s+frappe\.client\s+import[^\n]*\b(insert|save|submit|cancel|delete|set_value|"
    r"insert_many|bulk_update|rename_doc)\b")
_READ_PATH = [os.path.join(APP, "ask", f) for f in sorted(os.listdir(os.path.join(APP, "ask")))
              if f.endswith(".py")] + [os.path.join(APP, "kpi", "engine.py"),
                                       os.path.join(APP, "kpi", "registry.py"),
                                       os.path.join(APP, "facts", "schema.py")]
for _f in _READ_PATH:
    _src = open(_f).read()
    for _m in _WRITE.finditer(_src):
        _line = _src[:_m.start()].count("\n") + 1
        check(False, f"{os.path.relpath(_f, ROOT)}:{_line} has a write ({_m.group(0)}) on the "
                     f"question path. The analyst is read-only: no code it can reach may "
                     f"create, change or delete a record.")

_tools_src = open(os.path.join(APP, "ask", "tools.py")).read()
check("Command Center Site Credential" in _tools_src and '"Connected Business"' in _tools_src,
      "ask/tools.py no longer refuses the credential doctypes (Command Center Site "
      "Credential, Connected Business). The analyst must never read API keys.")
check("def run(" in _tools_src and "TOOLS.get(name)" in _tools_src,
      "ask/tools.py does not dispatch through the TOOLS registry, so the model could reach "
      "a function that is not in its catalogue.")
_agent_src = open(os.path.join(APP, "ask", "agent.py")).read()
check("transaction_writes" in _agent_src and "frappe.db.rollback()" in _agent_src,
      "ask/agent.py lost its write guard: any write made while answering must be rolled "
      "back and recorded.")
check("tools.run(" in _agent_src and "frappe.get_attr" not in _agent_src
      and "getattr(tools" not in _agent_src,
      "ask/agent.py calls tools other than through tools.run, which is the only way a "
      "model's function call may be honoured.")

# The analyst's loop -- dispatch, scope, budget, the write guard -- tested offline.
import subprocess as _sp
_t = _sp.run([sys.executable, os.path.join(ROOT, "scripts", "test_analyst.py")],
             capture_output=True, text=True, timeout=120)
check(_t.returncode == 0,
      "scripts/test_analyst.py failed:\n" + (_t.stdout + _t.stderr)[-1500:])

# --------------------------------------------------------------------------
print(f"preflight: {checks} checks")
if problems:
    print(f"\n{len(problems)} problem(s):\n")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("all clear")
