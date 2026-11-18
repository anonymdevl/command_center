"""The Executive Summary keeps everything it showed and did before its memo (16 Nov 2026).

    python3 scripts/test_brief_parity.py

The memo (the approved mockup-exec-summary.html) was added ABOVE the screen: "everything
currently on the screen stays below it, unchanged" -- the recommendations with their
actions, What Worked, the alerts, the PDF and Excel buttons. INVENTORY below is the screen
as it was at d44a652, each item with the file it must still be in. This fails if any of
it is lost:

  markup    the heading, the line under it, the Daily Brief box, the Recommendations and
            Alerts headings, the two live lists -- all still in views.json, in the same
            order, and all below the memo, outside it. The line on what every alert states
            was removed by the owner (17 Nov 2026, REMOVED): it must stay gone
  hooks     recommend.js still draws the full list on this screen (areas, Recently Closed,
            What Worked, the Daily Brief) with every action on every card; alerts.js still
            draws the alerts here with every action; core.js still writes the line under
            the heading; LegacyView still reads and draws both; every screen still has the
            PDF and Excel buttons, and the PDF is still the printed screen
  memo      legacy/summary.js only draws the memo: it never touches the lists below it
  bands     the memo's Healthy (summary.py, live_governance.HEALTHY) is the tiles' (home.js)

When git can see d44a652, the markup inventory is re-derived from that commit's views.json,
so INVENTORY is proven to be the old screen and not a copy of the new one. Finally the check
proves it can fail: a copy with the Alerts heading dropped, the removed banner back, the
sub-heading removed, the lists put inside the memo, the screen taken out of REC_VIEWS and the
PDF button removed must each be caught.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_REF = "d44a652"

# The screen's markup before the memo, in order (views.json "brief").
MARKUP = (
    ("<h3>Executive Summary</h3>", "the heading, as the sidebar says it"),
    ('id="brief-when">Reading the alerts&hellip;</div>', "the line under the heading"),
    ('<div class="rec-brief" id="rec-brief" hidden></div>', "the Daily Brief's box"),
    ('<div class="sect"><span>Recommendations</span><span class="rec-sub" id="rec-sub"></span></div>',
     "the Recommendations heading and its count"),
    ('<div class="rec-live-list" data-rec="all">', "the full list of recommendations"),
    ("Working out what to do first&hellip;", "the list's placeholder"),
    ('<div class="sect"><span>Alerts</span></div>', "the Alerts heading"),
    ("Each item states six things: <b>what happened · why it matters · the figure ·\n"
     "where it came from · who owns it · how long it has been true</b>. Every one links to the "
     "record behind it.", "the line on what every alert states"),
    ('<div class="alert-live-list">', "the alert list"),
)
# Below the memo means after its last line, outside it.
LISTS = ('id="rec-brief"', 'class="rec-live-list"', 'class="alert-live-list"')

# What the code that fills it must still do: (file, text, what).
HOOKS = (
    ("recommend.js", 'export const REC_VIEWS = new Set(["command", "brief"]);', "the list is drawn here"),
    ("recommend.js", "brief(root, data.brief);", "the Daily Brief at its top"),
    ("recommend.js", 'const head = el("div", "rec-area", areas[key]);', "grouped by area"),
    ("recommend.js", "`${count(recs.length)} open, most money at stake first`", "the count beside the heading"),
    ("recommend.js", 'group.append(el("div", "rec-area", "Recently closed"));', "Recently Closed"),
    ("recommend.js", "if (data.what_worked) list.append(worked(data.what_worked));", "What Worked"),
    ("recommend.js", "`What Worked${w.period ? ` — ${w.period}` : \"\"}`", "What Worked's heading"),
    ("recommend.js", 'btn(steps.hidden ? "What To Do" : "Hide Steps", "btn pri"', "What To Do"),
    ("recommend.js", 'btn("Ask AI", "btn", () => fire("cc-ask"', "Ask AI"),
    ("recommend.js", 'btn("Done", "btn", () => act(c, r, "done"))', "Done"),
    ("recommend.js", '["Not Relevant…", () => reason(c, r), false]', "Not Relevant"),
    ("recommend.js", '["Snooze 7 Days", () => act(c, r, "snooze", { days: 7 }), false]', "Snooze 7 Days"),
    ("recommend.js", '["Snooze 30 Days", () => act(c, r, "snooze", { days: 30 }), false]', "Snooze 30 Days"),
    ("recommend.js", 'el("b", null, "open the records")', "each card's records"),
    ("recommend.js", 'chip("Owner", r.owner_role), chip("Since"', "owner and seen since"),
    ("recommend.js", "c.id = `rec-${r.name}`;", "each card's id (a decision scrolls to it)"),
    ("alerts.js", 'export const ALERT_VIEWS = new Set(["command", "brief", "health", "risk"]);',
     "the alerts are drawn here"),
    ("alerts.js", 'btn("Assign", "btn pri"', "Assign"),
    ("alerts.js", 'btn("Ask AI", "btn"', "Ask AI"),
    ("alerts.js", '["Request evidence", () => fire("cc-action", { kind: "evidence"', "Request evidence"),
    ("alerts.js", '["Escalate", () => fire("cc-action", { kind: "escalate"', "Escalate"),
    ("alerts.js", '["Open the records", records, false]', "Open the records"),
    ("alerts.js", '["Defer…", ', "Defer"),
    ("alerts.js", '["Not a real problem…", ', "Not a real problem"),
    ("alerts.js", '["Dismiss…", ', "Dismiss"),
    ("alerts.js", "c.id = `alert-${a.name}`;", "each alert's id (a risk scrolls to it)"),
    ("core.js", 'if (view === "brief") briefWhen(root, alerts);', "the line under the heading, filled"),
    ("core.js", 'export const CORE_VIEWS = new Set(["command", "brief",', "the screen is finished by core.js"),
    ("LegacyView.jsx", "if (hasRecs) renderRecs(root, viewKey, recs.data, opts);", "the list drawn"),
    ("LegacyView.jsx", "if (hasAlerts) renderAlerts(root, viewKey, alerts.data, opts);", "the alerts drawn"),
    ("LegacyView.jsx", "const hasRecs = REC_VIEWS.has(viewKey);", "the list read"),
    ("LegacyView.jsx", "const hasAlerts = ALERT_VIEWS.has(viewKey) ||", "the alerts read"),
    ("ViewTools.jsx", '<ExportButton label="PDF" title="Print this screen or save it as a PDF" run={pdf} />',
     "the PDF button"),
    ("ViewTools.jsx", '<ExportButton label="Excel" title="Download the tables on this screen as Excel" run={excel} />',
     "the Excel button"),
    ("ViewTools.jsx", "window.print();", "the PDF is the printed screen, the memo with it"),
    ("App.jsx", "{!settings && !plan ? <ViewTools caption={captionOf(view)} scope={scope} /> : null}",
     "the buttons on every screen"),
)

# Changed since BASE_REF on purpose, each with what it was there: (file, text now) -> text
# then. The thing is still done; only its words or its place moved (17 Nov 2026: the AI
# button says "Ask AI", and each area of recommendations is drawn as its own group).
WAS = {
    ("recommend.js", 'group.append(el("div", "rec-area", "Recently closed"));'):
        'list.append(el("div", "rec-area", "Recently closed"));',
    ("recommend.js", 'chip("Owner", r.owner_role), chip("Since"'): 'chip("Owner", r.owner_role), chip("Seen since"',
    ("alerts.js", 'btn("Ask AI", "btn"'): 'btn("Ask AI about this", "btn"',
}
# Removed since BASE_REF on purpose, each with why: (MARKUP text) -> the decision. The
# check then holds the other way -- it must stay gone.
REMOVED = {
    MARKUP[7][0]: "17 Nov 2026, the owner: the interface stays lean; the alerts say these six "
                  "things themselves, row by row",
}
# What the memo's code may never touch: the screen below it.
MEMO_MUST_NOT = ("rec-live-list", "alert-live-list", "rec-brief", "rec-sub", "brief-when", ".alert:not",
                 "innerHTML", "insertAdjacentHTML", "outerHTML")

FILES = {
    "recommend.js": ("frontend", "src", "legacy", "recommend.js"),
    "alerts.js": ("frontend", "src", "legacy", "alerts.js"),
    "core.js": ("frontend", "src", "legacy", "core.js"),
    "home.js": ("frontend", "src", "legacy", "home.js"),
    "summary.js": ("frontend", "src", "legacy", "summary.js"),
    "LegacyView.jsx": ("frontend", "src", "components", "LegacyView.jsx"),
    "ViewTools.jsx": ("frontend", "src", "components", "ViewTools.jsx"),
    "App.jsx": ("frontend", "src", "App.jsx"),
    "live_governance.py": ("command_center", "kpi", "live_governance.py"),
}


def read(*parts):
    with open(os.path.join(ROOT, *parts)) as f:
        return f.read()


def sources() -> dict:
    out = {k: read(*v) for k, v in FILES.items()}
    out["views"] = json.loads(read("frontend", "src", "legacy", "views.json"))["brief"]
    return out


def memo_end(page: str) -> int | None:
    """Where the memo ends in the markup: the close of <div class="xm">, by depth."""
    m = re.search(r'<div class="xm"[^>]*>', page)
    if not m:
        return None
    depth, i = 0, m.start()
    for t in re.finditer(r"<(/?)div\b[^>]*>", page[m.start():]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return m.start() + t.end()
    return None


def compare(src: dict) -> list:
    """Everything the old screen showed or did that the new one does not."""
    lost = []
    page = src["views"]
    at = -1
    for text, what in MARKUP:
        i = page.find(text)
        if text in REMOVED:
            if i >= 0:
                lost.append(f"views.json: {what} is back, though it was removed on purpose ({REMOVED[text]})")
            continue
        if i < 0:
            lost.append(f"views.json: {what} is gone ({text[:60]!r})")
        elif i < at:
            lost.append(f"views.json: {what} has moved out of order")
        else:
            at = i
    end = memo_end(page)
    if end is None:
        lost.append("views.json: the memo (<div class=\"xm\">) is not there to be above the screen")
    else:
        for text in LISTS:
            i = page.find(text)
            if 0 <= i < end:
                lost.append(f"views.json: {text} is inside the memo, not below it")
    for name, text, what in HOOKS:
        if text not in src[name]:
            lost.append(f"{name}: {what} is gone ({text[:70]!r})")
    for text in MEMO_MUST_NOT:
        if text in src["summary.js"]:
            lost.append(f"summary.js uses {text!r}: the memo must not touch the screen below it")
    for line in re.findall(r"^.*\.remove\(\).*$", src["summary.js"], re.M):
        if ".xm-short,.xm-by" not in line:
            lost.append(f"summary.js removes something it did not draw: {line.strip()}")
    if "HEALTHY = 80" not in src["live_governance.py"] or \
            'if (score >= 80) return { key: "ok", word: "Healthy"' not in src["home.js"]:
        lost.append("Healthy is no longer 80% in both live_governance.HEALTHY and home.js's bands")
    return lost


def main() -> int:
    problems = []
    src = sources()

    # 1. The inventory is the old screen's: re-derived from the commit before the memo.
    try:
        old = subprocess.run(["git", "show", f"{BASE_REF}:frontend/src/legacy/views.json"],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        old = None
    if old and old.returncode == 0:
        before = json.loads(old.stdout)["brief"]
        missing = [what for text, what in MARKUP if text not in before]
        if missing:
            problems.append(f"MARKUP is not the screen at {BASE_REF}: {missing}")
        else:
            print(f"inventory matches the screen at {BASE_REF}: {len(MARKUP)} parts of its markup")
        old_files = {}
        for name, parts in FILES.items():
            got = subprocess.run(["git", "show", f"{BASE_REF}:{'/'.join(parts)}"], cwd=ROOT,
                                 capture_output=True, text=True, timeout=30)
            old_files[name] = got.stdout if got.returncode == 0 else ""
        stale = [f"{n}: {w}" for n, t, w in HOOKS if WAS.get((n, t), t) not in old_files[n]]
        if stale:
            problems.append(f"HOOKS is not the code at {BASE_REF}: {stale}")
        else:
            print(f"hooks match the code at {BASE_REF}: {len(HOOKS)} actions and calls")
    else:
        print(f"note: {BASE_REF} not reachable through git; using the written inventory")

    # 2. The new screen against it.
    lost = compare(src)
    problems += lost
    if not lost:
        print(f"parity: all {len(MARKUP)} parts of the screen kept, in order, below the memo; "
              f"all {len(HOOKS)} actions and calls intact; the memo touches nothing below it")

    # 3. The check can fail.
    page = src["views"]
    alerts_head = MARKUP[6][0]
    banner = MARKUP[7][0]
    cases = (
        ("the Alerts heading dropped", {"views": page.replace(alerts_head, "")}),
        ("the removed banner back", {"views": page.replace(alerts_head, alerts_head + banner)}),
        ("the count beside Recommendations removed",
         {"views": page.replace('<span class="rec-sub" id="rec-sub"></span>', "")}),
        ("the lists inside the memo",
         {"views": page.replace('<div class="xm-below">', '<div class="alert-live-list"></div><div class="xm-below">')}),
        ("the screen out of REC_VIEWS",
         {"recommend.js": src["recommend.js"].replace('new Set(["command", "brief"])', 'new Set(["command"])')}),
        ("the PDF button removed",
         {"ViewTools.jsx": src["ViewTools.jsx"].replace('<ExportButton label="PDF"', '<span label="PDF"')}),
        ("Snooze 30 Days removed", {"recommend.js": src["recommend.js"].replace('"Snooze 30 Days"', '"Later"')}),
        ("the memo emptying the list", {"summary.js": src["summary.js"] + '\nroot.querySelector(".rec-live-list");'}),
        ("Healthy moved", {"home.js": src["home.js"].replace('if (score >= 80) return { key: "ok"', 'if (score >= 75) return { key: "ok"')}),
    )
    for what, change in cases:
        broken = {**src, **change}
        if broken == src:
            problems.append(f"self-test: could not build the case '{what}'")
        elif not compare(broken):
            problems.append(f"self-test: the check did not catch {what}")

    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        return 1
    print("executive summary parity: all clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
