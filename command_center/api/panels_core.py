"""The management screens' panels and findings: Systems and Access, Internal Audit, Risk
and Compliance, and Business Overview's finding.

Registered into api/panels.py's SCREENS and FINDINGS (same shapes, same get()), so the
screens draw them exactly as they draw every other panel. Each is read from the
business's own ERPNext, its loaded records, or this platform's own tables (its people,
its alerts, its load history, its backups). Where ERPNext offers a place for something
that nothing is recorded in yet, the panel is a guide (command_center/guides.py).
"""

from __future__ import annotations

import json
from collections import defaultdict
from urllib.parse import quote

import frappe

from command_center.api.panels import (FINDINGS, SCREENS, _accounts, _date, _guarded,
                                       _money, _names, _num, _word)
from command_center.kpi.live import NeedsSetup

SEVERITY = {"crit": ("Critical", "t-od"), "high": ("High", "t-wt"), "med": ("Medium", "t-wt"),
            "info": ("For information", "t-dr")}


def _guide_panel(e: NeedsSetup) -> dict:
    return {"kind": "guide", "guide": e.status.get("guide") or {"text": e.status.get("message")}}


def _open_alerts(ctx):
    from command_center.alerts.engine import DOCTYPE, OPEN
    filters = {"status": ["in", list(OPEN)], "resolved_on": ["is", "not set"]}
    if ctx.code and ctx.code != "__all__":
        filters["business_code"] = ctx.code
    rows = frappe.get_all(DOCTYPE, filters=filters,
                          fields=["name", "title", "severity", "owner_label", "status",
                                  "deferred_until", "figure"], limit=200)
    today = frappe.utils.getdate(frappe.utils.today())
    from command_center.alerts.rules import SEVERITY_RANK
    rows = [a for a in rows if not (a.status == "Deferred" and a.deferred_until
                                    and frappe.utils.getdate(a.deferred_until) > today)]
    rows.sort(key=lambda a: (SEVERITY_RANK.get(a.severity, 9), -_num(a.figure)))
    return rows


def _raise_link(ctx, title):
    return {"href": f"{ctx.site()}/app/non-conformance/new?subject={quote(title[:140])}"}


# --------------------------------------------------------------------------- audit
def aud_day_one(ctx):
    """The open alerts, then the checks an auditor runs first, each with a way to raise
    it as a finding in ERPNext."""
    found = []
    for a in _open_alerts(ctx):
        word, tag = SEVERITY.get(a.severity, (a.severity, "t-wt"))
        found.append((a.title, word, tag, a.owner_label or "—"))
    cur = ctx.cur
    drafts = _guarded(ctx, "Purchase Order", {"docstatus": 0}, ["name", "base_grand_total"])
    if drafts:
        v = sum(_num(d.get("base_grand_total")) for d in drafts)
        found.append((f"{len(drafts):,} purchase order{'s' if len(drafts) != 1 else ''} worth "
                      f"{cur} {_money(v)} raised and never submitted for approval".replace("  ", " "),
                      "Medium", "t-wt", "Buying"))
    from command_center.kpi.live_governance import approval_record
    rec = approval_record(ctx.reader())
    if rec["alone"]:
        found.append((f"{rec['alone']:,} purchase order{'s' if rec['alone'] != 1 else ''} or "
                      f"payments approved only by the account that raised them",
                      "Critical", "t-od", "Approvals"))
    cancelled = _guarded(ctx, "Purchase Order", {"docstatus": 2}, ["name", "base_grand_total"])
    if cancelled:
        v = sum(_num(d.get("base_grand_total")) for d in cancelled)
        found.append((f"{len(cancelled):,} purchase order{'s' if len(cancelled) != 1 else ''} "
                      f"worth {cur} {_money(v)} withdrawn after being raised".replace("  ", " "),
                      "Medium", "t-wt", "Buying"))
    late = _backdated(ctx)
    if late:
        found.append((f"{late:,} journal entr{'ies' if late != 1 else 'y'} posted to a date more "
                      f"than {BACKDATED_DAYS} days before they were entered",
                      "High", "t-wt", "Accounts"))
    clash = [u for u in _accounts(ctx) if u.get("enabled") and u["conflicts"]]
    if clash:
        found.append((f"{len(clash):,} active account{'s' if len(clash) != 1 else ''} hold a "
                      f"conflicting pair of duties, such as raising a purchase and paying it",
                      "High", "t-wt", "Access"))
    rows = [{"cells": [
        {"text": t},
        {"text": risk, "tag": tag},
        {"text": area, "tone": "mut"},
        {"text": "Raise it", "drill": _raise_link(ctx, t)},
    ]} for t, risk, tag, area in found]
    return {"kind": "table", "rows": rows,
            "subtitle": (f"{_word(len(rows)).capitalize()} found in the records"
                         if rows else "Nothing found in the records"),
            "empty": "No open alert and none of the first checks found anything."}


BACKDATED_DAYS = 30


def _backdated(ctx) -> int:
    rows = _guarded(ctx, "Journal Entry", {"docstatus": 1}, ["name", "posting_date", "creation"])
    n = 0
    for r in rows:
        if r.get("posting_date") and r.get("creation"):
            gap = (frappe.utils.getdate(r["creation"]) - frappe.utils.getdate(r["posting_date"])).days
            if gap > BACKDATED_DAYS:
                n += 1
    return n


def aud_actions(ctx):
    from command_center.kpi.live_governance import ACTION_STEPS
    from command_center.guides import guide
    r = ctx.reader()
    if not r.has("Quality Action") or not r.count("Quality Action"):
        return {"kind": "guide", "guide": guide(
            ctx.code, "No corrective actions are recorded in ERPNext yet.", ACTION_STEPS,
            "/app/quality-action/new")}
    rows = _guarded(ctx, "Quality Action Resolution", {"status": "Open"},
                    ["parent", "problem", "resolution", "status", "responsible", "completion_by"],
                    parent="Quality Action")
    today = frappe.utils.getdate(frappe.utils.today())
    rows.sort(key=lambda x: str(x.get("completion_by") or "9999"))
    who = _names(ctx, [x.get("responsible") for x in rows])
    site = ctx.site()
    out = []
    for x in rows[:30]:
        due = frappe.utils.getdate(x["completion_by"]) if x.get("completion_by") else None
        late = bool(due and due < today)
        text = frappe.utils.strip_html(x.get("resolution") or x.get("problem") or "").strip()
        out.append({"cells": [
            {"text": text[:140] or x.get("parent") or "—", "sub": x.get("parent"),
             "drill": {"href": f"{site}/app/quality-action/{x.get('parent')}"}},
            {"text": who.get(x.get("responsible"), "—") if x.get("responsible") else "nobody named",
             "tone": "" if x.get("responsible") else "crit"},
            {"text": _date(due) if due else "no date", "nowrap": True,
             "tone": "crit" if late else "mut"},
            {"text": "Overdue" if late else "Open", "tag": "t-od" if late else "t-wt"},
        ]})
    return {"kind": "table", "rows": out, "empty": "No corrective action is open."}


def _kind(data) -> tuple[str, str]:
    """What a change-log entry did, in words: (kind, what happened)."""
    try:
        d = json.loads(data) if isinstance(data, str) else (data or {})
    except ValueError:
        return "Record changed", "Changed"
    changed = d.get("changed") or []
    fields = [c[0] for c in changed if isinstance(c, (list, tuple)) and c]
    for c in changed:
        if isinstance(c, (list, tuple)) and len(c) >= 3 and c[0] == "docstatus":
            return ({1: ("Submitted", "Submitted"), 2: ("Cancelled", "Cancelled")}
                    .get(c[2], ("Record changed", "Status changed")))
    if "workflow_state" in fields:
        step = next((c[2] for c in changed if c[0] == "workflow_state" and len(c) >= 3), "")
        return "Approval", f"Moved to {step}" if step else "Approval step"
    parts = [", ".join(f.replace("_", " ") for f in fields[:3])] if fields else []
    if d.get("added"):
        parts.append(f"{len(d['added'])} row{'s' if len(d['added']) != 1 else ''} added")
    if d.get("removed"):
        parts.append(f"{len(d['removed'])} row{'s' if len(d['removed']) != 1 else ''} removed")
    if d.get("row_changed"):
        parts.append("rows edited")
    return "Record changed", ("Changed " + "; ".join(parts)) if parts else "Changed"


def aud_trail(ctx):
    rows = _guarded(ctx, "Version", {}, ["name", "creation", "owner", "ref_doctype", "docname",
                                         "data"], limit=50, order_by="creation desc")
    who = _names(ctx, [r.get("owner") for r in rows])
    site = ctx.site()
    out = []
    for r in rows:
        kind, what = _kind(r.get("data"))
        slug = frappe.scrub(r.get("ref_doctype") or "").replace("_", "-")
        when = frappe.utils.get_datetime(r["creation"]) if r.get("creation") else None
        out.append({"cells": [
            {"text": when.strftime("%-d %b %Y") if when else "—",
             "sub": when.strftime("%H:%M") if when else None, "nowrap": True},
            {"text": who.get(r.get("owner"), r.get("owner") or "—")},
            {"text": kind, "tone": "mut", "small": True},
            {"text": what},
            {"text": r.get("docname") or "—", "sub": r.get("ref_doctype"),
             "drill": {"href": f"{site}/app/{slug}/{r.get('docname')}"}},
        ]})
    return {"kind": "table", "rows": out, "subtitle": "The fifty most recent changes",
            "empty": "The change history is empty."}


def aud_findings(ctx):
    """For the two finding boxes: the purchase orders never sent for approval (approval
    history), and what the change history is (audit trail). None hides a box."""
    drafts = _guarded(ctx, "Purchase Order", {"docstatus": 0},
                      ["name", "base_grand_total", "transaction_date"])
    first = None
    if drafts:
        v = sum(_num(d.get("base_grand_total")) for d in drafts)
        big = sum(1 for d in drafts if _num(d.get("base_grand_total")) > 50000)
        oldest = min((str(d["transaction_date"]) for d in drafts if d.get("transaction_date")),
                     default=None)
        first = {"title": f"{ctx.cur} {_money(v)} of purchase orders were raised and never "
                          f"submitted for approval.".strip(),
                 "text": (f"{_word(len(drafts)).capitalize()} order{'s' if len(drafts) != 1 else ''}"
                          + (f", {big} of them over {ctx.cur} 50,000" if big else "")
                          + (f", the oldest dated {_date(oldest)}" if oldest else "")
                          + ". They are not rejected and not withdrawn — simply never sent."),
                 "ask": "Which purchase orders were raised and never submitted, and who raised them?",
                 "ask_label": "Ask about them"}
    second = {"title": "Every entry above is read from the business's own ERPNext.",
              "text": "Each is a change a person made to a document there, with who and when; "
                      "nothing in this history is typed in by this platform."}
    return [first, second]


# --------------------------------------------------------------------------- systems and access
def _platform_people():
    from command_center.api.businesses import ROLE
    out = []
    for u in frappe.get_all("User", fields=["name", "full_name", "enabled", "modified"]):
        if u.name in ("Administrator", "Guest"):
            continue
        roles = set(frappe.get_roles(u.name)) if u.enabled else set()
        access = ("Administrator" if "System Manager" in roles else
                  "Manager" if ROLE in roles else "No access")
        out.append(frappe._dict({**u, "access": access}))
    order = {"Administrator": 0, "Manager": 1, "No access": 2}
    out.sort(key=lambda u: (not u["enabled"], order[u["access"]], (u.full_name or "").lower()))
    return out


def it_platform_people(ctx):
    people = _platform_people()
    rows = [{"cells": [
        {"text": u.full_name or u.name, "sub": u.name},
        {"text": u["access"], "tone": "" if u["access"] != "No access" else "mut"},
        {"text": "Active" if u.enabled else "Deactivated", "tag": "t-ok" if u.enabled else "t-dr"},
        {"text": _date(u.modified) if u.modified else "never", "tone": "mut", "nowrap": True},
    ]} for u in people]
    live = sum(1 for u in people if u.enabled and u["access"] != "No access")
    return {"kind": "table", "rows": rows,
            "subtitle": f"{live:,} active account{'s' if live != 1 else ''} with access",
            "empty": "Nobody has an account on this platform yet."}


def it_platform_access(ctx):
    people = [u for u in _platform_people() if u.enabled]
    n = defaultdict(int)
    for u in people:
        n[u["access"]] += 1
    rows = [
        {"cells": [{"text": "Administrator"}, {"text": f"{n['Administrator']:,}", "num": True},
                   {"text": "Every screen, plus people, businesses, keys and alert rules"}]},
        {"cells": [{"text": "Manager"}, {"text": f"{n['Manager']:,}", "num": True},
                   {"text": "Every screen for the businesses connected here"}]},
    ]
    if n["No access"]:
        rows.append({"cells": [{"text": "No access", "tone": "mut"},
                               {"text": f"{n['No access']:,}", "num": True, "tone": "mut"},
                               {"text": "Has an account but is turned away at sign-in",
                                "tone": "mut"}]})
    return {"kind": "table", "rows": rows}


def it_data_current(ctx):
    from command_center.api.ingest import FACT_WORDS
    filters = {"business_code": ctx.code} if ctx.code and ctx.code != "__all__" else {}
    states = frappe.get_all("Command Center Ingest State", filters=filters,
                            fields=["fact", "as_of_date", "last_run", "status", "last_error"],
                            order_by="fact asc")
    rows = []
    for s in states:
        ok = s.status == "OK"
        rows.append({"cells": [
            {"text": FACT_WORDS.get(s.fact, s.fact)},
            {"text": _date(s.as_of_date) if s.as_of_date else "—", "nowrap": True},
            {"text": (frappe.utils.get_datetime(s.last_run).strftime("%-d %b %H:%M")
                      if s.last_run else "never"), "nowrap": True, "tone": "mut"},
            {"text": "Loaded" if ok else (s.status or "Never run"),
             "tag": "t-ok" if ok else "t-od" if s.status == "Failed" else "t-dr"},
        ]})
    return {"kind": "table", "rows": rows,
            "empty": "Nothing has been loaded yet. Business Health → Refresh now reads ERPNext."}


def it_backups(ctx):
    try:
        from insights.core.maintenance import backup_dir
        found = sorted(backup_dir().glob("insights-*"), key=lambda p: p.stat().st_mtime,
                       reverse=True)
    except Exception:
        found = []
    found = [p for p in found if not p.name.endswith(".json")][:5]
    import datetime as dt
    rows = [{"cells": [
        {"text": p.name},
        {"text": dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%-d %b %H:%M"),
         "nowrap": True},
        {"text": f"{p.stat().st_size / 1e6:,.1f} MB", "tone": "mut"},
    ]} for p in found]
    return {"kind": "table", "rows": rows,
            "empty": "No backup has been taken yet. The nightly job writes the first one."}


def it_findings(ctx):
    accounts = [u for u in _accounts(ctx) if u.get("enabled")]
    worst = next((u for u in accounts if u["conflicts"]), None)
    if not worst:
        return [{"title": "No active account holds a conflicting pair of duties.",
                 "text": "Nobody can both raise a purchase and approve its payment, adjust stock "
                         "and post the accounting for it, or change pay and approve paying it."}]
    name = worst.get("full_name") or worst["name"]
    return [{"title": f"{name} holds {len(worst['roles'])} of the business roles: "
                      f"{', '.join(worst['roles'])}.",
             "text": f"That single account {'; '.join(worst['conflicts'])}. Some overlap is "
                     f"unavoidable in a small team, but it should be a decision somebody took, "
                     f"not something nobody noticed.",
             "ask": f"Which duties does {name} hold in ERPNext, and which should be separated?",
             "ask_label": "Ask about it"}]


# --------------------------------------------------------------------------- risk
def risk_obligations(ctx):
    from command_center.kpi.live_governance import _days_left, deadlines
    try:
        rows = deadlines(ctx.reader())
    except NeedsSetup as e:
        return _guide_panel(e)
    site = ctx.site()

    def key(x):
        d = _days_left(x)
        return (d is None, d if d is not None else 0)
    out = []
    for x in sorted(rows, key=key)[:40]:
        d = _days_left(x)
        stands, tag = (("No deadline set", "t-dr") if d is None else
                       (f"Overdue by {-d} day{'s' if d != -1 else ''}", "t-od") if d < 0 else
                       ("Due today", "t-od") if d == 0 else
                       (f"Due in {d} day{'s' if d != 1 else ''}", "t-wt" if d <= 30 else "t-ok"))
        out.append({"cells": [
            {"text": x["name"], "drill": {"href": f"{site}/app/contract/{quote(x['name'])}"},
             "sub": x.get("fulfilment_status")},
            {"text": x.get("party_type") or "—", "tone": "mut"},
            {"text": x.get("party_name") or "—"},
            {"text": _date(x["fulfilment_deadline"]) if x.get("fulfilment_deadline") else "—",
             "nowrap": True},
            {"text": stands, "tag": tag},
        ]})
    return {"kind": "table", "rows": out, "empty": "Every recorded obligation is fulfilled."}


# --------------------------------------------------------------------------- overview
AREAS = (("fact_sales_invoice", "Sales & money owed"), ("fact_purchase_invoice", "Buying & suppliers"),
         ("fact_stock_balance", "Stock & warehouses"), ("fact_task", "Engineering & installs"),
         ("fact_case", "Customer Service & Issues"), ("fact_person", "People"))


def ops_findings(ctx):
    from command_center.facts.schema import FACTS
    scope = {"business_code": ctx.code} if ctx.code and ctx.code != "__all__" else {}
    empty = [label for fact, label in AREAS if not frappe.db.count(FACTS[fact], scope)]
    if not empty:
        return []
    return [{"title": f"{_word(len(empty)).capitalize()} area{'s' if len(empty) != 1 else ''} "
                      f"{'has' if len(empty) == 1 else 'have'} nothing recorded in ERPNext yet: "
                      f"{', '.join(empty)}.",
             "text": "Their screens say what to record there, and where, to fill them."}]


SCREENS.setdefault("it", {}).update({
    "Who can sign in to this platform": it_platform_people,
    "This platform's own access": it_platform_access,
    "Is the data current": it_data_current,
    "Backups and recovery": it_backups,
})
SCREENS.setdefault("aud", {}).update({
    "What an auditor would raise on day one": aud_day_one,
    "Corrective actions": aud_actions,
    "The latest changes": aud_trail,
})
SCREENS.setdefault("risk", {}).update({"Obligations and deadlines": risk_obligations})
SCREENS.setdefault("ops", {})
FINDINGS["it"] = it_findings
FINDINGS["aud"] = aud_findings
FINDINGS["ops"] = ops_findings
