"""The change feed, and the peer refresh that consumes it.

Nothing in here is allowed to break a business transaction. A failure to record
that an invoice was submitted is an inconvenience; a failure that prevents the
invoice being submitted is a production incident caused by a reporting tool, and
there is no version of that which is acceptable.
"""

from __future__ import annotations

import frappe
from frappe.utils import now_datetime, add_days

from command_center.hooks import TRACKED_DOCTYPES

EVENT_BY_HOOK = {
    "after_insert": "Insert",
    "on_submit": "Submit",
    "on_update_after_submit": "Update",
    "on_cancel": "Cancel",
}


def record_event(doc, method=None):
    """doc_events handler for every tracked doctype."""
    if doc.doctype not in TRACKED_DOCTYPES:
        return
    try:
        event = EVENT_BY_HOOK.get(method)
        if not event:
            return

        code = frappe.cache().get_value(
            "cc_local_business_code",
            lambda: frappe.db.get_value("Connected Business", {"is_local": 1},
                                        "business_code"),
        )
        if not code:
            return

        frappe.get_doc({
            "doctype": "Command Center Change Event",
            "business_code": code,
            "source_doctype": doc.doctype,
            "source_name": doc.name,
            "event": event,
            "occurred_at": now_datetime(),
        }).insert(ignore_permissions=True)

    except Exception:
        frappe.log_error(title="Command Center change feed",
                         message=frappe.get_traceback())


@frappe.whitelist()
def get_changes(since: str | None = None, limit: int = 500):
    """Read this site's feed. Called by peers over REST.

    Returns what changed, not what the changes contained. A peer that wants the
    detail asks for the document, and that request is permission-checked on its
    own terms.
    """
    filters = {}
    if since:
        filters["occurred_at"] = [">", since]
    return frappe.get_all(
        "Command Center Change Event",
        filters=filters,
        fields=["business_code", "source_doctype", "source_name", "event",
                "occurred_at"],
        order_by="occurred_at asc",
        limit_page_length=min(int(limit), 2000),
    )


def refresh_peers():
    """Scheduled: ask every peer what has changed since we last looked.

    Peers are read for their conclusions, not their ledgers. If one is
    unreachable the others still refresh — a group of businesses should not lose
    its whole view because one server is down.
    """
    from command_center.connectors.base import BusinessUnreachable
    from command_center.connectors.registry import all_connectors

    for conn in all_connectors():
        if conn.is_local:
            continue
        try:
            conn.fetch_changes(since=conn.business.last_sync, limit=500)
            frappe.db.set_value("Connected Business", conn.business.name,
                                "last_sync", now_datetime(),
                                update_modified=False)
        except BusinessUnreachable as e:
            frappe.log_error(title=f"Command Center peer refresh: {conn.name}",
                             message=str(e))
    frappe.db.commit()


def prune_consumed_events(keep_days: int = 14):
    frappe.db.delete("Command Center Change Event", {
        "consumed": 1,
        "occurred_at": ["<", add_days(now_datetime(), -abs(keep_days))],
    })
    frappe.db.commit()
