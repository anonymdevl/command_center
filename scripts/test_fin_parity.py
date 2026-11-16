#!/usr/bin/env python3
"""Finances keeps everything it had (the "Management Accounts" restyle, 16 Nov 2026).

Michael's rule for the restyle: "Make sure we don't lose sight of all the data there and
the reports. We're only changing appearance, not content." So the screen's inventory --
taken from the shipped screen before the restyle (f59597c) and kept in
scripts/fin_parity.json -- is compared with the screen as built now, and anything that
is gone fails:

  markup (frontend/src/legacy/views.json, "fin"):
    every id, data-* attribute and onclick target; every class the screen carried (new
    classes may be added, none may go); every figure's label and the explainer it opens;
    every panel's title, subtitle, explainer and the tab it sits in; every tab in every
    tab bar; every table heading; every button; every "what is this?" note.
  scripts:
    legacy/statements.js -- every element it looks up, every statement heading, the five
      statement figures, every button it draws, the Excel and PDF exports;
    legacy/hydrate.js -- the six figures' label -> KPI wiring (CARD_KPIS.fin), unchanged;
    legacy/viz.js, vizoptions.js -- the charts' Table, PNG and SVG controls and chart types;
    and every id statements.js looks up still exists in the markup.

Run:  python3 scripts/test_fin_parity.py            (exit 1 on any loss)
      python3 scripts/test_fin_parity.py --snapshot <views.json> <legacy dir>
                                                    (rewrite the inventory; only for a
                                                     deliberate, agreed change of content)
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(ROOT, "scripts", "fin_parity.json")
LEGACY = os.path.join(ROOT, "frontend", "src", "legacy")

# tabify() names a screen's tab group by a digest of its markup ("t6ea40"), so it changes
# with any edit to the screen. The group is compared by position, not by that name.
_TID = re.compile(r"\bt[0-9a-f]{5}\b")


def _norm(s):
    return _TID.sub("t*", s)


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def _blocks(html, cls):
    """Each element whose class list includes `cls`, as its outer HTML (balanced divs)."""
    out = []
    for m in re.finditer(r'<div class="([^"]*)"', html):
        if cls not in m.group(1).split():
            continue
        depth, i = 0, m.start()
        for t in re.finditer(r"<(/?)div\b", html[i:]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                out.append(html[i:i + t.end() + 4])
                break
    return out


def markup_inventory(html):
    inv = {}
    inv["ids"] = sorted(set(re.findall(r'\bid="([^"]+)"', html)))
    inv["data_attrs"] = sorted(set(_norm(f"{k}={v}") for k, v in
                                   re.findall(r'\b(data-[\w-]+)(?:="([^"]*)")?', html)))
    inv["onclicks"] = sorted(set(_norm(v) for v in re.findall(r'onclick="([^"]*)"', html)))
    inv["classes"] = sorted({c for v in re.findall(r'class="?([^">]+)"?', html) for c in v.split()})
    inv["figures"] = [[_text(lab), _norm(oc)] for oc, lab in
                      re.findall(r'<div class="kpi[^"]*" onclick="([^"]*)">.*?<div class="lab">(.*?)</div>', html)]
    # panels, each with the tab it sits in
    tabs_by_group = {}
    for g, bar in re.findall(r'<div class="tabbar" data-g="([^"]+)">(.*?)</div>', html):
        tabs_by_group[_norm(g)] = [_text(b) for b in re.findall(r"<button[^>]*>(.*?)</button>", bar)]
    inv["tabbars"] = tabs_by_group
    panes = [(_norm(g), int(i), m.start()) for m in re.finditer(r'<div class="tabpane[^"]*" data-g="([^"]+)" data-i="(\d+)"', html)
             for g, i in [m.groups()]]
    panels = []
    for m in re.finditer(r'<div class="panel">\s*<div class="ph[^"]*"(?: onclick="([^"]*)")?><div><b>(.*?)</b>(?:<span>(.*?)</span>)?</div>', html):
        where = [p for p in panes if p[2] < m.start()]
        tab = "-"
        if where:
            g, i, _ = max(where, key=lambda p: p[2])
            names = tabs_by_group.get(g, [])
            tab = f"{g}:{names[i] if i < len(names) else i}"
        panels.append([_text(m.group(2)), _text(m.group(3) or ""), _norm(m.group(1) or ""), tab])
    inv["panels"] = panels
    inv["table_heads"] = [[_text(th) for th in re.findall(r"<th[^>]*>(.*?)</th>", t)]
                          for t in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S)]
    inv["buttons"] = sorted(set(_text(b) for b in re.findall(r"<button[^>]*>(.*?)</button>", html)))
    inv["notes"] = [_text(t) for t in re.findall(r'<div class="thin">(.*?)</div>', html, re.S)]
    inv["explainer_links"] = len(re.findall(r"what is this\?", html))
    return inv


def script_inventory(legacy):
    read = lambda f: open(os.path.join(legacy, f)).read()
    st, hy = read("statements.js"), read("hydrate.js")
    viz, vo = read("viz.js"), read("vizoptions.js")
    inv = {}
    inv["statements_lookups"] = sorted({m[1] for m in re.findall(r"querySelector(?:All)?\((['\"`])(.*?)\1\)", st)})
    inv["statements_headings"] = sorted(set(re.findall(r'el\("h4", null, "([^"]+)"\)', st)))
    inv["statements_cards"] = re.findall(r'\badd\("([^"]+)"', st)
    inv["statements_buttons"] = sorted(set(re.findall(r'"(Show Every Account|Show Main Groups|Excel|PDF)"', st)))
    inv["statements_calls"] = sorted(set(re.findall(r"\bapi\.(\w+)\(", st)))
    inv["statements_parts"] = sorted(set(re.findall(r'part\(box, "(\w+)"\)', st)))
    inv["statements_states"] = sorted(set(re.findall(r'state === "(\w+)"', st)))
    m = re.search(r"\n  fin: \{(.*?)\n  \},", hy, re.S)
    inv["card_kpis_fin"] = dict(re.findall(r'^\s*"?([^":\n]+?)"?:\s*"(\w+)",', m.group(1), re.M)) if m else {}
    inv["viz_controls"] = sorted(set(re.findall(r'dl\("(\w+)"', viz)))
    m = re.search(r"export const VIEW_LABELS = \{(.*?)\};", vo, re.S)
    inv["viz_views"] = dict(re.findall(r'(\w+): "([^"]+)"', m.group(1))) if m else {}
    return inv


def inventory(views_path, legacy):
    html = json.load(open(views_path))["fin"]
    return {"markup": markup_inventory(html), "scripts": script_inventory(legacy)}


def lost(old, new, path=""):
    """What `old` has that `new` does not. Lists compare as multisets where order is not
    the point (ids, classes) and item by item where it is (figures, panels, tabs)."""
    out = []
    if isinstance(old, dict):
        for k, v in old.items():
            if k not in new:
                out.append(f"{path}{k}: missing entirely")
            else:
                out += lost(v, new[k], f"{path}{k}.")
    elif isinstance(old, list):
        have = list(new) if isinstance(new, list) else []
        for item in old:
            if item in have:
                have.remove(item)
            else:
                out.append(f"{path.rstrip('.')}: lost {item!r}")
    elif old != new:
        out.append(f"{path.rstrip('.')}: was {old!r}, now {new!r}")
    return out


def selectors_resolve(markup, lookups):
    """Each id statements.js looks up (#fs-..., [data-part=...]) is in the markup."""
    bad = []
    for sel in lookups:
        for i in re.findall(r"#([\w-]+)", sel):
            if i not in markup["ids"]:
                bad.append(f"statements.js looks up #{i}, which the screen no longer has")
        for k, v in re.findall(r'\[(data-[\w-]+)="([^"$]+)"\]', sel):
            if f"{k}={v}" not in markup["data_attrs"]:
                bad.append(f'statements.js looks up [{k}="{v}"], which the screen no longer has')
    for sel in lookups:
        for c in re.findall(r"\.([a-z][\w-]*)", sel):
            if c not in markup["classes"] and c not in ("kpi",):
                bad.append(f"statements.js looks up .{c}, which the screen no longer has")
    return bad


def main(argv):
    if len(argv) >= 2 and argv[1] == "--snapshot":
        snap = inventory(argv[2], argv[3])
        json.dump(snap, open(SNAP, "w"), indent=1, ensure_ascii=False, sort_keys=True)
        print(f"wrote {SNAP}")
        return 0
    old = json.load(open(SNAP))
    new = inventory(os.path.join(LEGACY, "views.json"), LEGACY)
    problems = lost(old, new)
    problems += selectors_resolve(new["markup"], new["scripts"]["statements_lookups"])
    # The six figures are still hydrated by label: each mapped label is still on a figure.
    labels = [f[0] for f in new["markup"]["figures"]]
    for lab in new["scripts"]["card_kpis_fin"]:
        if lab not in labels:
            problems.append(f"CARD_KPIS.fin maps {lab!r}, but no figure on Finances carries that label")
    n_old = sum(len(v) if isinstance(v, (list, dict)) else 1 for part in old.values() for v in part.values())
    if problems:
        print(f"Finances parity: {len(problems)} item(s) lost against the inventory of {n_old}:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"Finances parity: all {n_old} inventoried items present")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
