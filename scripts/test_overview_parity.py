"""Business Overview keeps everything it showed and did before its front-page redesign.

    python3 scripts/test_overview_parity.py

The redesign of 16 Nov 2026 changed the screen's appearance only ("we're only changing
appearance, not content", Michael). BASELINE below is the inventory of the screen as it
was at f59597c: every tile, its label, the figure it is filled with (TILE_KPIS.ops), the
unit word beside a count, its designed footnote and flag, and what a click on it does;
the heading, the line under it, and the finding box. This script fails if the built
screen (frontend/src/legacy/views.json) or the code that fills it has lost any of it:

  markup    each tile is still a .bk with its .khead > .l label, its designed .flag, a
            .n figure slot, a .v footnote, the signature arrow, and the same go() click
  figures   TILE_KPIS.ops still maps every label to the same KPI and unit word
  hooks     core.js still finishes the screen (dashes, can't-reach, set-up guides) and
            draws its finding box; LegacyView still installs go() and reads its panels
  moves     legacy/overview.js only moves tiles: it never clones, rebuilds or removes
            one, and takes back only what it added itself
  order     scripts/test_overview.mjs: every area placed exactly once, whatever the data

When git can see f59597c, the baseline is also re-derived from that commit's views.json
and compared, so the inventory below is proven to be the old screen and not a copy of
the new one. Finally the check proves it can fail: a copy of the markup with one click
target changed, one tile dropped and the finding box removed must each be caught.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY = os.path.join(ROOT, "frontend", "src", "legacy")
BASE_REF = "f59597c"

# The inventory of the screen before the redesign: label, click, designed footnote,
# designed flag, KPI key, unit word printed beside a count (None for money).
BASELINE = {
    "heading": "Business Overview",
    "when": "Nine areas · open any one of them",
    "finding_boxes": 1,
    "tiles": [
        ("Sales & money owed", "go('sales')", "owed to us", "Live data", "ar_total", None),
        ("Buying & suppliers", "go('proc')", "owed to suppliers", "Live data", "ap_total", None),
        ("Stock & warehouses", "go('inv')", "value on hand", "Live data", "stock_value", None),
        ("Engineering & installs", "go('eng')", "open jobs", "Live data", "tasks_open", "tasks"),
        ("Customer Service & Issues", "go('cx')", "open complaints and service cases", "Live data",
         "cases_open", "open cases"),
        ("Money in & out", "go('fin')", "payments and journals", "Live data", "postings_count",
         "postings"),
        ("People", "go('hr')", "everyone on the books", "Live data", "people_total", "employees"),
        ("Systems & access", "go('it')", "active ERPNext accounts", "Live data", "users_active",
         "accounts"),
        ("Internal Audit", "go('aud')", "open alerts to review", "Live data", "alerts_open",
         "open alerts"),
    ],
}


# The ERPNext wording review of 17 Nov 2026 renamed some of what BASELINE records: each
# old word -> the agreed new one. BASELINE itself stays the screen at BASE_REF (proven
# below); the built screen is checked against BASELINE with these applied, so a rename
# not listed here is still a loss.
WORDING = {
    "Nine areas · open any one of them": "",
    "Sales & money owed": "Sales and Payments",
    "Buying & suppliers": "Buying and Suppliers",
    "Stock & warehouses": "Stock & Warehouses",
    "Engineering & installs": "Project Insights",
    "Money in & out": "Finances",
    "Systems & access": "Systems and Access",
    "owed to us": "Accounts Receivable",
    "owed to suppliers": "Accounts Payable",
    "value on hand": "Stock Value",
    "payments and journals": "Payment Entries and Journal Entries",
    "everyone on the books": "Employees",
    "open alerts to review": "open alerts",
    "Live data": "Live Data",
    "postings": "entries",
}


def now(word):
    """What BASELINE's word reads as today."""
    return WORDING.get(word, word)


def read(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


def tile_map(hydrate_src: str) -> dict:
    """TILE_KPIS.ops as label -> (key, unit)."""
    body = re.search(r"export const TILE_KPIS = \{(.*?)\n\};", hydrate_src, re.S).group(1)
    ops = re.search(r"^  ops: \{(.*?)^  \},", body, re.S | re.M).group(1)
    out = {}
    for label, key, unit in re.findall(
            r'^\s*"?([^":\n/]+?)"?:\s*\{\s*key:\s*"(\w+)"(?:,\s*unit:\s*"([^"]+)")?\s*\}', ops, re.M):
        out[html.unescape(label.strip())] = (key, unit or None)
    return out


def inventory(markup: str) -> dict:
    """What a screen's markup carries: its tiles and the boxes around them."""
    starts = [m.start() for m in re.finditer(r'<div class="bk[\s"]', markup)]
    tiles = []
    for i, frm in enumerate(starts):
        block = markup[frm: starts[i + 1] if i + 1 < len(starts) else len(markup)]
        opening = re.match(r'<div class="([^"]*)"([^>]*)>', block)
        classes, attrs = opening.group(1).split(), opening.group(2)
        click = re.search(r'onclick="([^"]*)"', attrs)
        label = re.search(r'<div class="khead"><div class="l">(.*?)</div>', block, re.S)
        flag = re.search(r'<div class="khead"><div class="l">.*?</div><span class="flag[^"]*">(.*?)</span>',
                         block, re.S)
        foot = re.search(r'<div class="v">(.*?)</div>', block, re.S)
        tiles.append({
            "label": html.unescape(label.group(1)).strip() if label else None,
            "click": html.unescape(click.group(1)) if click else None,
            "foot": html.unescape(foot.group(1)).strip() if foot else None,
            "flag": html.unescape(flag.group(1)).strip() if flag else None,
            "classes": classes,
            "figure_slot": '<div class="n">' in block,
            "arrow": 'class="sig-go"' in block,
        })
    head = re.search(r"<h3>(.*?)</h3>", markup)
    when = re.search(r'<div class="when">(.*?)</div>', markup)
    return {
        "heading": head.group(1) if head else None,
        "when": html.unescape(when.group(1)) if when else None,
        "finding_boxes": len(re.findall(r'<div class="warn"', markup)),
        "tiles": tiles,
    }


def compare(markup: str, tmap: dict, js: dict) -> list:
    """Everything the old screen showed or did that the new one does not."""
    lost = []
    inv = inventory(markup)
    for k in ("heading", "when", "finding_boxes"):
        if inv[k] != now(BASELINE[k]):
            lost.append(f"{k}: was {now(BASELINE[k])!r}, now {inv[k]!r}")
    by_label = {t["label"]: t for t in inv["tiles"]}
    if len(inv["tiles"]) != len(BASELINE["tiles"]):
        lost.append(f"the screen had {len(BASELINE['tiles'])} tiles and now has {len(inv['tiles'])}")
    for label, click, foot, flag, key, unit in BASELINE["tiles"]:
        label, foot, flag, unit = now(label), now(foot), now(flag), now(unit)
        t = by_label.get(label)
        if not t:
            lost.append(f"tile {label!r} is gone")
            continue
        if t["click"] != click:
            lost.append(f"{label}: opened {click!r}, now {t['click']!r}")
        if t["foot"] != foot:
            lost.append(f"{label}: footnote was {foot!r}, now {t['foot']!r}")
        if t["flag"] != flag:
            lost.append(f"{label}: flag was {flag!r}, now {t['flag']!r}")
        for cls in ("bk", "clickable", "sig"):
            if cls not in t["classes"]:
                lost.append(f"{label}: no longer class {cls!r}")
        if not t["figure_slot"]:
            lost.append(f"{label}: has no .n slot for its figure")
        if not t["arrow"]:
            lost.append(f"{label}: lost the signature arrow")
        if tmap.get(label) != (key, unit):
            lost.append(f"{label}: was filled with {(key, unit)}, now {tmap.get(label)}")
    core, lv, ov = js["core"], js["legacy_view"], js["overview"]
    if not re.search(r'CORE_VIEWS = new Set\(\[[^\]]*"ops"', core):
        lost.append("core.js no longer finishes ops: unread figures would keep a placeholder")
    if not re.search(r'CORE_PANEL_VIEWS = new Set\(\[[^\]]*"ops"', core):
        lost.append("core.js no longer draws the Overview's finding box")
    if "window.go = " not in lv:
        lost.append("LegacyView no longer installs go(): no tile would open anything")
    if "CORE_PANEL_VIEWS.has(viewKey)" not in lv:
        lost.append("LegacyView no longer reads the Overview's panels (its finding)")
    for bad in ("cloneNode", "innerHTML", "outerHTML", "replaceWith", "insertAdjacentHTML"):
        if bad in ov:
            lost.append(f"overview.js uses {bad}: a tile must be moved, never rebuilt")
    for line in re.findall(r"^.*\.remove\(\).*$", ov, re.M):
        if "data-ov-add" not in line:
            lost.append(f"overview.js removes something it did not add: {line.strip()}")
    return lost


def kpi_keys() -> set:
    keys = set()
    for name in os.listdir(os.path.join(ROOT, "command_center", "kpi")):
        if name.endswith(".py"):
            keys |= set(re.findall(r'key="(\w+)"', read("command_center", "kpi", name)))
    keys |= set(re.findall(r'^\s*"(\w+)":', read("command_center", "kpi", "live.py"), re.M))
    return keys


def main() -> int:
    problems = []
    views = json.loads(read("frontend", "src", "legacy", "views.json"))
    hyd = read("frontend", "src", "legacy", "hydrate.js")
    js = {"core": read("frontend", "src", "legacy", "core.js"),
          "legacy_view": read("frontend", "src", "components", "LegacyView.jsx"),
          "overview": read("frontend", "src", "legacy", "overview.js")}
    tmap = tile_map(hyd)

    # 1. The inventory is the old screen's: re-derived from the commit before the change.
    try:
        old = subprocess.run(["git", "show", f"{BASE_REF}:frontend/src/legacy/views.json"],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
        old_hyd = subprocess.run(["git", "show", f"{BASE_REF}:frontend/src/legacy/hydrate.js"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        old = old_hyd = None
    if old and old.returncode == 0 and old_hyd.returncode == 0:
        before = inventory(json.loads(old.stdout)["ops"])
        derived = [(t["label"], t["click"], t["foot"], t["flag"], *tile_map(old_hyd.stdout)[t["label"]])
                   for t in before["tiles"]]
        if derived != [tuple(t) for t in BASELINE["tiles"]] or any(
                before[k] != BASELINE[k] for k in ("heading", "when", "finding_boxes")):
            problems.append(f"BASELINE is not the screen at {BASE_REF}: {derived}")
        else:
            print(f"baseline matches the screen at {BASE_REF}: {len(derived)} tiles")
    else:
        print(f"note: {BASE_REF} not reachable through git; using the written inventory")

    # 2. The new screen against it.
    lost = compare(views["ops"], tmap, js)
    problems += lost
    if not lost:
        print(f"parity: all {len(BASELINE['tiles'])} tiles keep label, figure, unit, footnote, "
              f"flag, arrow and click; heading, line and finding box kept; hooks intact")

    # 3. The lead story's figures are real KPIs.
    lead = re.search(r"export const LEAD_FIGURES = \{(.*?)\n\};", js["overview"], re.S)
    known = kpi_keys()
    for key in re.findall(r'"(\w+)"', lead.group(1) if lead else ""):
        if key not in known:
            problems.append(f"overview.js LEAD_FIGURES names {key!r}, which is not a KPI")
    if not lead:
        problems.append("overview.js has no LEAD_FIGURES")

    # 4. The check can fail.
    page = views["ops"]
    for what, broken, tm in (
            ("a click target changed", page.replace("go(&#39;cx&#39;)", "go(&#39;fin&#39;)", 1), tmap),
            ("a tile dropped", re.sub(r'<div class="bk[^>]*data-dept="it".*?</div></div>', "", page,
                                      count=1, flags=re.S), tmap),
            ("the finding box removed", page.replace('<div class="warn" hidden></div>', ""), tmap),
            ("a figure remapped", page, {**tmap, "People": ("headcount", "employees")}),
    ):
        if broken == page and tm is tmap:
            problems.append(f"self-test: could not build the case '{what}'")
        elif not compare(broken, tm, js):
            problems.append(f"self-test: the check did not catch {what}")
    for what, src in (("a clone", js["overview"] + "\nt.cloneNode(true);"),
                      ("a removed tile", js["overview"] + "\n  tile.remove();")):
        if not compare(page, tmap, {**js, "overview": src}):
            problems.append(f"self-test: the check did not catch {what} in overview.js")

    # 5. The ordering: every area exactly once (Node, as the frontend build needs).
    node = shutil.which("node")
    if node:
        t = subprocess.run([node, os.path.join(ROOT, "scripts", "test_overview.mjs")],
                           capture_output=True, text=True, timeout=120)
        print(t.stdout.strip())
        if t.returncode:
            problems.append("scripts/test_overview.mjs failed:\n" + (t.stdout + t.stderr)[-1500:])
    else:
        problems.append("no node on PATH: scripts/test_overview.mjs cannot run")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        return 1
    print("overview parity: all clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
