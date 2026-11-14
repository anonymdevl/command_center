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
    "on_update": "Update",
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

        # Frappe runs on_update *and* on_submit during a submit, which would
        # record the same transaction twice. A submitted document's edits arrive
        # through on_update_after_submit, so an on_update on a docstatus-1
        # document is always that duplicate.
        if method == "on_update" and getattr(doc, "docstatus", 0) == 1:
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
    """Scheduled every fifteen minutes: bring each peer's facts up to date.

    A peer on the hosted service has nothing of ours installed, so there is no change
    feed to read there (record_event above only fires where this app is installed).
    It is polled instead, by ERPNext's own `modified` stamps -- see
    api/ingest.poll_peers, which owns it because reading a peer as the system is an
    ingest act and nothing else may do it.
    """
    from command_center.api.ingest import poll_peers
    poll_peers()


def prune_consumed_events(keep_days: int = 14):
    frappe.db.delete("Command Center Change Event", {
        "consumed": 1,
        "occurred_at": ["<", add_days(now_datetime(), -abs(keep_days))],
    })
    frappe.db.commit()
