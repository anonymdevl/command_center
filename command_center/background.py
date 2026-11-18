"""The heavy reads, worked out behind the screens for every connected business.

Hourly (hooks.py, hourly_long) and after the nightly and weekly loads (api/ingest.py),
as the platform: the change history's summary (kpi/history.py, incrementally), the
Internal Audit screen's heavy panels (api/panels.py BEHIND) and the Financial
Statements for the period the screen opens with (api/statements.py STORED_PERIODS).
Each is kept where the screen reads it at once (speed.stored); the panels and statements
of a business whose facts have not moved are not read again for up to
speed.BG_UNCHANGED. Then the business's screens are kept warm (speed.warm). A business
known to be down is left for its next refresh.

A person's own key has answers of its own: worked out as them when they look
(speed.stored), never here.
"""

from __future__ import annotations

import frappe


def specs(code: str) -> list[dict]:
    """What is worked out behind the screens for one business, in order: the history
    first, which the audit panels read."""
    from command_center.api import panels, statements
    from command_center.kpi import history
    out = [{"name": "history", "what": history.WHAT, "fn": history.work_out,
            "kwargs": {"business_code": code}, "incremental": True}]
    for view in panels.BEHIND:
        what, kwargs = panels.behind_spec(view, code)
        out.append({"name": "panels", "what": what, "fn": panels.compute, "kwargs": kwargs,
                    "complete": panels.complete, "unchanged_ok": True})
    for period in statements.STORED_PERIODS:
        for section in statements.SECTIONS:
            out.append({"name": "statements", "what": {"section": section, "period": period},
                        "fn": statements.work_out,
                        "kwargs": {"code": code, "section": section, "period": period},
                        "complete": statements.complete, "unchanged_ok": True})
    return out


def refresh_business(code: str) -> int:
    """Everything in specs(), worked out now for one business; how many were."""
    from command_center import speed
    n = 0
    for spec in specs(code):
        if speed._business(code)["down"]:
            break
        try:
            speed.refresh(spec["name"], code, spec["what"], spec["fn"], spec["kwargs"],
                          complete=spec.get("complete", speed._always),
                          incremental=spec.get("incremental", False),
                          unchanged_ok=spec.get("unchanged_ok", False))
            n += 1
        except Exception:
            frappe.log_error(title=f"Command Center background {code}",
                             message=frappe.get_traceback())
    return n


def run_all():
    """Every loaded business: its heavy reads, then its screens kept warm. "All
    businesses" (more than one) gets the audit panels too, as the platform sees it."""
    from command_center import speed
    from command_center.api import panels
    from command_center.api.businesses import loaded_codes
    codes = loaded_codes()
    for code in codes:
        try:
            refresh_business(code)
            speed.warm(code)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"Command Center background {code}",
                             message=frappe.get_traceback())
    if len(codes) > 1:
        for view in panels.BEHIND:
            what, kwargs = panels.behind_spec(view, "__all__")
            try:
                speed.refresh("panels", "__all__", what, panels.compute, kwargs,
                              complete=panels.complete, unchanged_ok=True)
            except Exception:
                frappe.log_error(title="Command Center background __all__",
                                 message=frappe.get_traceback())


def hourly():
    run_all()


def after_load():
    """After the nightly (and the weekly) load: the facts have moved, so all of it."""
    try:
        run_all()
    except Exception:
        frappe.log_error(title="Command Center background after the load",
                         message=frappe.get_traceback())
