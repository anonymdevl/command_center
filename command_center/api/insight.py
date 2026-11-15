"""Every figure's drawer explains, not just lists (command_center/insight).

    understand(key, business_code)  the "Understanding This Figure" section, from data
    explain(key, business_code)     Explain This: the analyst's short explanation of it
    xlsx(key, business_code)        the section as an Excel sheet (a drawer with no records)

Reads only. A manager may read any figure the screens show; nothing here writes to a
business's ERPNext.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager


@frappe.whitelist()
def understand(key: str, business_code: str | None = None):
    require_manager()
    from command_center import speed
    from command_center.insight.build import understand as build
    return speed.cached("live", business_code, {"insight": key}, build,
                        {"key": key, "business_code": business_code})


@frappe.whitelist(methods=["POST"])
def explain(key: str, business_code: str | None = None):
    require_manager()
    from command_center.insight.ai import explain as run
    return run(key, business_code)


@frappe.whitelist(methods=["POST"])
def xlsx(key: str, business_code: str | None = None):
    require_manager()
    from command_center.api.export import _send_xlsx
    from command_center.insight.build import sheet, understand as build
    s = build(key, business_code)
    _send_xlsx(s["label"], [sheet(s)], business_code)
