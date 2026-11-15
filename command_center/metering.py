"""Usage metering, as the business logic sees it: one seam to the platform's plans.

The ledger, the allowances and the licence live in insights/core/plans.py (the standalone
platform). The business logic only says what is happening -- a question is being answered,
a report written, Claude replied with these tokens -- through the four calls below, and
asks whether AI work may go ahead. On a plain Frappe site, where there are no plans, every
call does nothing and every gate is open, so the business logic runs exactly as before.

    event(meter, business_code)   around anything that may call Claude; one ledger row
    tokens(model, **usage)        after every Claude reply (ask/claude.py), so none escape
    gate(meter, business_code)    None, or the sentence to show instead of the AI work
    allowance(business_code)      this month's allowance and use, for the analyst's tool

Metering never stops the work it measures: a failure to record is logged, not raised.
"""

from __future__ import annotations

from contextlib import contextmanager

import frappe


def _plans():
    try:
        from insights.core import plans
    except ImportError:  # not the standalone platform
        return None
    return plans


@contextmanager
def event(meter: str, business_code=None, ref: str = "", note: str = "", count: bool = True):
    p = _plans()
    if p is None:
        yield {"ok": False, "model": ""}
        return
    with p.event(meter, business_code, ref=ref, note=note, count=count) as ev:
        yield ev


def tokens(model: str = "", **usage):
    p = _plans()
    if p is None:
        return
    try:
        p.meter_tokens(model, **usage)
    except Exception:
        frappe.log_error(title="Usage not recorded", message=frappe.get_traceback())


def gate(meter: str, business_code=None) -> str | None:
    p = _plans()
    if p is None:
        return None
    try:
        return p.gate(meter, business_code)
    except Exception:
        # A fault in the plans never takes the AI away from a client.
        frappe.log_error(title="Plans: gate failed", message=frappe.get_traceback())
        return None


def allowance(business_code=None) -> dict:
    p = _plans()
    if p is None:
        return {"plan": None, "note": "Plans and allowances are not in use on this site."}
    return p.allowance_for(business_code)
