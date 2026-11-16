"""Business Health's history, for its eight-week strips and "on last week".

    history(business_code)  the last eight ISO weeks of stored snapshots (the last in each
                            week; a week with none is empty), last week's Control Health
                            and the change since, in whole points (command_center/health.py)

Reads only. The snapshots are written where the figures are worked out (api/kpi.get and
the daily health.record_all), never here.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager


@frappe.whitelist()
def history(business_code: str | None = None):
    require_manager()
    from command_center import health
    return health.history(business_code)
