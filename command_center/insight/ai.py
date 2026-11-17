"""Explain This: a short management explanation of a figure's drawer, by the analyst.

Optional depth over the deterministic section (build.py), which stands on its own. The
analyst is given the section in words (build.as_text) and nothing else -- no tools, no
records, no ERPNext -- through ask/claude.py, so every request is metered (metering.event,
meter ai_questions) and the plan's allowance and licence gate it (metering.gate). Its
answer is checked like the Daily Brief's: one that gives a number not in what it was
given is not shown, and the reason is said instead (recommend/daily.foreign_numbers).
Kept per business, figure and data version, so opening it again costs nothing.
"""

from __future__ import annotations

import frappe

METER = "ai_questions"
KEEP_SECONDS = 6 * 3600

SYSTEM = """You explain one figure from a business's management dashboard to its chief \
executive, using only the computed facts given below. The reader is busy and is not an \
accountant.

Write:
- One sentence saying what the figure shows now.
- Then three to five bullet points, each starting with "- ", in formal plain English: what \
is driving it, what the expected position is and how far the business is from it, and what \
should be done first, by whom.

Rules you must keep:
- Use only the numbers given below, written exactly as they are given (currency, commas, \
decimals). Never calculate, round, add up, estimate, compare by percentage, or introduce \
any other number, date or percentage.
- Name only customers, suppliers, products and documents that appear below.
- No headings, no tables, no markdown other than the bullet points. Never name a field, a \
table or a tool."""


def _cache_key(code, key) -> str:
    from command_center import speed
    from command_center.api.businesses import scope_tag
    return f"cc:insight:explain:{scope_tag(code)}:{key}:{speed.version(code)}"


def explain(key: str, business_code: str | None = None) -> dict:
    """{"text", "model"} or {"error"}: never raises for a refusal or a check that failed."""
    from command_center import metering
    from command_center.api.businesses import default_business_code
    from command_center.ask import claude, llm
    from command_center.insight.build import as_text, understand
    from command_center.recommend.daily import foreign_numbers

    code = business_code or default_business_code()
    c = frappe.cache()
    kept = c.get_value(_cache_key(code, key))
    if isinstance(kept, dict) and kept.get("text"):
        return {**kept, "kept": True}
    if llm.provider() != "claude" or not claude.configured():
        return {"error": "Explain This needs the Claude key (Settings, Claude). The "
                         "explanation in this drawer is complete without it."}
    blocked = metering.gate(METER, code)
    if blocked:
        return {"error": blocked}
    section = understand(key, code)
    given = as_text(section)
    with metering.event(METER, code, ref=key, note="Explain This") as ev:
        got, err = claude.complete(SYSTEM, given, kind="analyst", timeout=60, max_tokens=2000)
        bad = foreign_numbers(got, given) if got and not err else []
        ev["ok"] = bool(got and not err and not bad)
    if err:
        return {"error": f"The analyst could not write it: {err}"}
    if bad:
        frappe.log_error(title="Command Center: Explain This not used",
                         message=f"Numbers not in the drawer: {bad}\n\n{got}")
        return {"error": f"Not shown: it gave {', '.join(bad[:3])}, which is not among the "
                         f"figures in this drawer."}
    out = {"text": got.strip(), "model": claude.model_for("analyst"),
           "at": str(frappe.utils.now_datetime())[:16]}
    c.set_value(_cache_key(code, key), out, expires_in_sec=KEEP_SECONDS)
    return out
