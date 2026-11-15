"""Whether the selected business's ERPNext is answering, for the banner in the shell.

    status(business_code)  the business's state as the connector last recorded it
                           (Connected Business status, set Unreachable by a failed call
                           and Active again by the next one that succeeds --
                           connectors/remote.py), when that was first noticed here, and
                           when its records were last loaded
    retry(business_code)   asks the site once (the connector's ping), which itself sets
                           the status back to Active when it answers, then reports it

Reads only: no business record is touched. A business on this site is always reachable.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import default_business_code, require_manager


def _code(business_code):
    return (business_code if business_code and business_code != "__all__"
            else default_business_code())


def _since_key(code):
    return f"cc:unreachable_since:{code}"


@frappe.whitelist()
def status(business_code: str | None = None) -> dict:
    require_manager()
    code = _code(business_code)
    if not code:
        return {"reachable": True}
    row = frappe.db.get_value("Connected Business", {"business_code": code},
                              ["business_name", "status", "is_local", "last_error"],
                              as_dict=True)
    if not row:
        return {"reachable": True}
    down = row.status == "Unreachable" and not row.is_local
    cache = frappe.cache()
    since = cache.get_value(_since_key(code))
    if down and not since:
        since = str(frappe.utils.now_datetime())[:19]
        cache.set_value(_since_key(code), since)
    elif not down and since:
        cache.delete_value(_since_key(code))
        since = None
    from frappe.query_builder.functions import Max
    t = frappe.qb.DocType("Command Center Ingest State")
    got = frappe.qb.from_(t).select(Max(t.last_run)).where(t.business_code == code).run()
    last = got[0][0] if got and got[0] else None
    return {"code": code, "name": row.business_name, "reachable": not down,
            "since": since if down else None,
            "last_load": str(last)[:19] if last else None,
            "error": (row.last_error or "")[:200] if down else ""}


@frappe.whitelist()
def retry(business_code: str | None = None) -> dict:
    require_manager()
    code = _code(business_code)
    if code:
        from command_center.connectors.registry import connector_for
        try:
            connector_for(code).ping()
        except Exception:
            frappe.log_error(title="Command Center: reachability check",
                             message=frappe.get_traceback())
        frappe.db.commit()
        # Figures and panels kept from before are read again (speed.py).
        from command_center import speed
        speed.data_changed(code, hard=True)
    return status(business_code)
