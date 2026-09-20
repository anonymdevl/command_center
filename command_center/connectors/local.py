"""The business this site owns.

No HTTP, no credentials, no serialisation. Calls land straight on frappe, under
the acting user, so ERPNext's permission system and its Version audit trail
apply without this app reimplementing either.
"""

from __future__ import annotations

from contextlib import contextmanager

import frappe

from command_center.connectors.base import BusinessConnector


@contextmanager
def acting_as(user: str | None):
    """Run a block as a specific user, then restore.

    Used on every call rather than once at the edge, because a scheduled job and
    a click from a manager arrive through the same connector and must not be
    allowed to borrow each other's authority.
    """
    if not user or user == frappe.session.user:
        yield
        return
    previous = frappe.session.user
    try:
        frappe.set_user(user)
        yield
    finally:
        frappe.set_user(previous)


class LocalConnector(BusinessConnector):
    is_local = True

    def get_list(self, doctype, filters=None, fields=None, limit=20,
                 order_by=None, group_by=None):
        with acting_as(self.acting_user):
            return frappe.get_list(
                doctype,
                filters=filters or {},
                fields=fields or ["name"],
                limit_page_length=limit,
                order_by=order_by,
                group_by=group_by,
            )

    def get_doc(self, doctype, name):
        with acting_as(self.acting_user):
            doc = frappe.get_doc(doctype, name)
            doc.check_permission("read")
            return doc.as_dict()

    def get_count(self, doctype, filters=None):
        with acting_as(self.acting_user):
            return frappe.db.count(doctype, filters or {})

    def get_value(self, doctype, filters, fieldname):
        with acting_as(self.acting_user):
            return frappe.db.get_value(doctype, filters, fieldname)

    def run_report(self, report_name, filters=None):
        from frappe.desk.query_report import run

        with acting_as(self.acting_user):
            return run(report_name, filters=filters or {}, ignore_prepared_report=True)

    # -- writes ------------------------------------------------------------
    def insert(self, doc):
        with acting_as(self.acting_user):
            d = frappe.get_doc(doc)
            d.insert()
            return d.as_dict()

    def set_value(self, doctype, name, fieldname, value):
        with acting_as(self.acting_user):
            d = frappe.get_doc(doctype, name)
            d.check_permission("write")
            d.set(fieldname, value)
            d.save()
            return d.as_dict()

    def submit(self, doctype, name):
        with acting_as(self.acting_user):
            d = frappe.get_doc(doctype, name)
            d.submit()
            return d.as_dict()

    def cancel(self, doctype, name):
        with acting_as(self.acting_user):
            d = frappe.get_doc(doctype, name)
            d.cancel()
            return d.as_dict()

    def apply_workflow(self, doctype, name, action):
        from frappe.model.workflow import apply_workflow

        with acting_as(self.acting_user):
            doc = frappe.get_doc(doctype, name)
            return apply_workflow(doc, action).as_dict()

    def fetch_changes(self, since=None, limit: int = 500):
        from command_center.api.changes import get_changes

        return get_changes(since=since, limit=limit)

    def ping(self):
        return True
