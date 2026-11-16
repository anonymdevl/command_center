"""Whether the selected business's ERPNext is answering, for the banner in the shell.

    status(business_code)  the business's state as the connector last recorded it
                           (Connected Business status, set Unreachable only when a read
                           went unanswered after its retries AND the quick check straight
                           after it failed too -- a read that was merely slow leaves it
                           Active; connectors/remote.py), when that was first noticed
                           here, and when its records were last loaded. While it is
                           marked down, the site is asked again (the quick check) at most
                           once a minute, so a business that is back clears by itself on
                           the next look instead of waiting for the next refresh
    retry(business_code)   the quick check now, which sets the status back to Active when
                           it answers, then reports it

The only write is the connector's own reachability mark. A business on this site is
always reachable.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import default_business_code, require_manager


def _code(business_code):
    return (business_code if business_code and business_code != "__all__"
            else default_business_code())


def _since_key(code):
    return f"cc:unreachable_since:{code}"


def _recheck_due(code) -> bool:
    from command_center.connectors.remote import CHECKED_KEY
    return not frappe.cache().get_value(CHECKED_KEY.format(code))


def _recheck(code) -> bool:
    """The connector's quick check, recorded either way; True when the site answered."""
    from command_center.connectors.registry import connector_for
    ok = False
    try:
        conn = connector_for(code)
        check = getattr(conn, "recheck", None) or conn.ping
        ok = bool(check())
    except Exception:
        frappe.log_error(title="Command Center: reachability check",
                         message=frappe.get_traceback())
    frappe.db.commit()
    return ok


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
    if down and _recheck_due(code):
        down = not _recheck(code)
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
        _recheck(code)
        # Figures and panels kept from before are read again (speed.py).
        from command_center import speed
        speed.data_changed(code, hard=True)
    return status(business_code)
