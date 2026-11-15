"""Once a day: the email digest of recommendations, and the optional Daily Brief by Claude.

    write_briefs()   06:30 (hooks.scheduler_events). For each business with the Daily Brief
                     switched on (off by default; about one Claude request per business per
                     day): Claude Sonnet writes a short plain-English brief -- what changed
                     since yesterday and the top three actions -- from the engine's
                     recommendations and a few headline figures ONLY, passed in as text. It
                     is told never to give a number it was not given, and the brief is
                     checked: one that quotes a figure not in what it was given is not used,
                     and the reason is kept instead. Shown at the top of the Executive
                     Summary and in the digest.
    send_digests()   07:00. For each business with the digest on (on by default): the
                     recommendations new since the last digest and the largest still open,
                     to every active manager, through the platform's mail. Email not set up,
                     or a refusal, is recorded and shown in Settings, never raised.

What happened is kept as stored values (frappe.defaults): BRIEF_PARENT and DIGEST_PARENT,
keyed by business.
"""

from __future__ import annotations

import json
import re

import frappe
from frappe.utils import getdate, now_datetime, today

from command_center.recommend import engine

BRIEF_PARENT = "__cc_brief"
DIGEST_PARENT = "__cc_rec_digest"
TOP = 5
# Headline figures the brief may compare with yesterday: the same ones the cards show.
BRIEF_FIGURES = (("ar_total", "Customers owe us, by the ledger"),
                 ("ar_over_90", "Of which more than 90 days late"),
                 ("ap_total", "We owe suppliers, by the ledger"),
                 ("cash_in_month", "Money received, last full month"),
                 ("revenue_last_month", "Invoiced, last full month"),
                 ("order_book_late", "Orders past their promised date, still to deliver"),
                 ("stock_value", "Stock held, at cost"))


def _get(parent, code) -> dict:
    try:
        raw = (frappe.defaults.get_defaults_for(parent) or {}).get(code)
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def _put(parent, code, value: dict):
    frappe.defaults.set_default(code, json.dumps(value, default=str), parent=parent)


def _name(code) -> str:
    return frappe.db.get_value("Connected Business", {"business_code": code},
                               "business_name") or code


def _money(cur, v) -> str:
    return f"{cur} {float(v or 0):,.0f}".strip()


# --------------------------------------------------------------------------- the brief
SYSTEM = """You write the morning brief for the chief executive of a business, from the \
business's own figures and the platform's recommendations, which are given to you below. \
The reader is busy and not an accountant.

Write, in plain English, no more than about 150 words:
1. One or two sentences on what changed since yesterday.
2. "Top three actions today:" then three short numbered lines, the most money at stake \
first, each saying what to do and the amount it concerns.

Rules you must keep:
- Use only the numbers given below, written exactly as they are given. Never work out, \
round, add up, estimate or introduce any other number, date or percentage.
- If nothing is given for yesterday, say this is the first brief, and give the actions.
- No headings, no tables, no markdown other than the numbered lines. Never name a field, \
a table or a tool."""


def _snapshot(code) -> dict:
    from command_center.kpi.engine import evaluate_set
    figs = evaluate_set([k for k, _ in BRIEF_FIGURES], code)
    recs = engine.visible(code)
    return {"date": today(),
            "figures": {k: figs[k].get("value") for k, _ in BRIEF_FIGURES
                        if figs.get(k) and figs[k].get("value") is not None},
            "recs": {r["id"]: {"title": r["title"], "money": r.get("money_at_stake") or 0}
                     for r in recs[:20]},
            "_recs": recs}


def brief_input(code) -> tuple:
    """(the text Claude is given, today's snapshot). Every number in the text is one the
    engine or the figures produced, formatted once here."""
    from command_center.api.businesses import currency_for
    cur = currency_for(code) or ""
    snap = _snapshot(code)
    recs = snap.pop("_recs")
    stored = _get(BRIEF_PARENT, code)
    base = (stored.get("base") if stored.get("date") == today() else stored.get("snapshot")) or {}
    lines = [f"Business: {_name(code)}", f"Today: {getdate(today()).strftime('%-d %B %Y')}", "",
             "HEADLINE FIGURES (today; yesterday where known)"]
    for k, label in BRIEF_FIGURES:
        if k not in snap["figures"]:
            continue
        v = snap["figures"][k]
        was = (base.get("figures") or {}).get(k)
        lines.append(f"- {label}: {_money(cur, v)}"
                     + (f" (yesterday {_money(cur, was)})" if was is not None else ""))
    lines += ["", "RECOMMENDATIONS OPEN NOW, most money at stake first"]
    for r in recs[:8]:
        new = base and r["id"] not in (base.get("recs") or {})
        lines.append(f"- {'NEW SINCE YESTERDAY: ' if new else ''}{r['title']} "
                     f"Money at stake: {_money(cur, r.get('money_at_stake'))}. "
                     f"Evidence: {r['why']} First step: {(r.get('what_to_do') or [''])[0]}")
    gone = [v["title"] for k, v in (base.get("recs") or {}).items() if k not in snap["recs"]]
    if gone:
        lines += ["", "CLEARED SINCE YESTERDAY"] + [f"- {t}" for t in gone[:8]]
    if not base:
        lines += ["", "No brief was written yesterday: this is the first."]
    return "\n".join(lines), snap


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set:
    return {n.replace(",", "").rstrip(".") for n in NUMBER.findall(text or "")}


def foreign_numbers(brief: str, given: str) -> list:
    """Numbers in the brief that are not in what it was given (the numbered list's 1-3
    apart)."""
    allowed = _numbers(given) | {"1", "2", "3"}
    return sorted(n for n in _numbers(brief) if n not in allowed)


def write_brief(code) -> dict:
    """Write today's brief for one business and keep it (or why it could not be)."""
    from command_center.ask import claude, llm
    stored = _get(BRIEF_PARENT, code)
    text, snap = brief_input(code)
    base = (stored.get("base") if stored.get("date") == today() else stored.get("snapshot")) or {}
    out = {"date": today(), "at": str(now_datetime())[:16], "snapshot": snap, "base": base,
           "text": None, "error": None, "model": None}
    if llm.provider() != "claude" or not claude.configured():
        out["error"] = "The Daily Brief needs the Claude key (Settings, Claude)."
    else:
        got, err = claude.complete(SYSTEM, text, kind="analyst")
        out["model"] = claude.model_for("analyst")
        if err:
            out["error"] = f"Claude could not write it: {err}"
        else:
            bad = foreign_numbers(got, text)
            if bad:
                out["error"] = (f"Not used: it gave {', '.join(bad[:3])}, which is not in the "
                                f"figures it was given.")
                frappe.log_error(title="Command Center: daily brief not used",
                                 message=f"Numbers not in the data: {bad}\n\n{got}")
            else:
                out["text"] = got
    _put(BRIEF_PARENT, code, out)
    return out


def brief_for(code) -> dict | None:
    """Today's (or yesterday's) brief to show, when the brief is switched on."""
    if not engine.settings(code)["brief"]:
        return None
    b = _get(BRIEF_PARENT, code)
    if not b or not b.get("date"):
        return None
    age = (getdate(today()) - getdate(b["date"])).days
    if age > 1:
        return None
    return {"text": b.get("text"), "error": b.get("error"), "date": b.get("date"),
            "at": b.get("at"), "model": b.get("model")}


def write_briefs():
    from command_center.api.businesses import loaded_codes
    for code in loaded_codes():
        if not engine.settings(code)["brief"]:
            continue
        try:
            engine.ensure_fresh(code, force=True)
            write_brief(code)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Command Center: daily brief failed",
                             message=frappe.get_traceback())


# --------------------------------------------------------------------------- the digest
def _item(r, cur) -> str:
    esc = frappe.utils.escape_html
    first = (r.get("what_to_do") or [""])[0]
    money = (f" · {esc(_money(cur, r['money_at_stake']))}" if r.get("money_at_stake") else "")
    return (f"<li><b>{esc(r['title'])}</b>{money}<br><span style='color:#555'>{esc(r['why'])}"
            f"</span><br>First: {esc(first)} · Owner: {esc(r.get('owner_role') or '—')}</li>")


def send_digest(code, force: bool = False) -> dict:
    from command_center.alerts.notify import recipients
    from command_center.api.businesses import currency_for
    if not force and not engine.settings(code)["digest"]:
        return {}
    state = _get(DIGEST_PARENT, code)
    last = state.get("sent_at")
    recs = engine.visible(code)
    stamp = str(now_datetime())[:16]
    if not recs:
        state.update({"at": stamp, "ok": True, "says": "Nothing was open, so nothing was sent."})
        _put(DIGEST_PARENT, code, state)
        return state
    new = [r for r in recs if r.get("first_seen") and (not last or r["first_seen"] > last)]
    rest = [r for r in recs if r not in new][:TOP]
    to = recipients()
    if not to:
        state.update({"at": stamp, "ok": False, "says": "Not sent: no manager has an email address."})
        _put(DIGEST_PARENT, code, state)
        return state
    cur = currency_for(code) or ""
    name = _name(code)
    esc = frappe.utils.escape_html
    brief = brief_for(code)
    parts = []
    if brief and brief.get("text"):
        parts.append("<h3>Daily Brief</h3>" + "".join(
            f"<p>{esc(p)}</p>" for p in brief["text"].split("\n") if p.strip())
            + "<p style='color:#777'>Written by Claude from the figures below only.</p>")
    if new:
        parts.append(f"<h3>New since the last digest ({len(new)})</h3><ul>"
                     + "".join(_item(r, cur) for r in new[:TOP]) + "</ul>")
    if rest:
        parts.append("<h3>Still open, most money at stake first</h3><ul>"
                     + "".join(_item(r, cur) for r in rest) + "</ul>")
    subject = (f"{len(new)} new recommendation{'s' if len(new) != 1 else ''} · {name}" if new
               else f"{len(recs)} open recommendation{'s' if len(recs) != 1 else ''} · {name}")
    try:
        frappe.sendmail(
            recipients=to, subject=subject,
            message=(f"<p>What the figures of {esc(name)} say is worth doing today.</p>"
                     + "".join(parts)
                     + "<p>Open the platform's Home screen to mark each one done, not "
                       "relevant, or snooze it.</p><p style='color:#777'>Sent by AI Business "
                       "Intelligence to its managers. Switch the digest off in Settings, "
                       "Recommendations.</p>"),
            now=True)
    except Exception as e:
        frappe.log_error(title="Command Center: recommendation digest not sent",
                         message=frappe.get_traceback())
        state.update({"at": stamp, "ok": False, "says": f"Not sent: {str(e)[:200]}"})
        _put(DIGEST_PARENT, code, state)
        return state
    state.update({"at": stamp, "ok": True, "sent_at": stamp, "new": len(new), "open": len(recs),
                  "says": f"Sent to {len(to)} manager{'s' if len(to) != 1 else ''}: "
                          f"{len(new)} new, {len(recs)} open."})
    _put(DIGEST_PARENT, code, state)
    return state


def digest_state(code) -> dict:
    return _get(DIGEST_PARENT, code)


def send_digests():
    from command_center.api.businesses import loaded_codes
    for code in loaded_codes():
        if not engine.settings(code)["digest"]:
            continue
        try:
            engine.ensure_fresh(code, force=True)
            send_digest(code)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="Command Center: recommendation digest failed",
                             message=frappe.get_traceback())
