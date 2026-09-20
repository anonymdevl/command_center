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
        """The document, or as much of it as can be had.

        A third-party app that overrides a doctype's controller and fails to
        import takes `frappe.get_doc` down with it for that doctype — on this
        client's site, posawesome did exactly that to Sales Invoice, and nobody
        could open an invoice in the desk either.

        The platform should degrade rather than die: fall back to a
        controller-free read and mark the result, so a drawer shows the record
        with a caveat instead of a screen showing a traceback. The permission
        check still happens, against the same doctype's own permissions.
        """
        with acting_as(self.acting_user):
            try:
                doc = frappe.get_doc(doctype, name)
                doc.check_permission("read")
                return doc.as_dict()
            except ImportError:
                frappe.log_error(
                    title=f"Command Center: controller unavailable for {doctype}",
                    message=frappe.get_traceback())
                return self._get_doc_without_controller(doctype, name)

    def _get_doc_without_controller(self, doctype, name):
        if not frappe.has_permission(doctype, "read", doc=name,
                                     user=self.acting_user):
            raise frappe.PermissionError(
                f"Not permitted to read {doctype} {name}")

        meta = frappe.get_meta(doctype)
        row = frappe.db.get_value(doctype, name, "*", as_dict=True)
        if not row:
            frappe.throw(f"{doctype} {name} not found")
        out = dict(row)
        out["doctype"] = doctype
        for df in meta.get_table_fields():
            out[df.fieldname] = frappe.db.get_all(
                df.options, filters={"parent": name, "parenttype": doctype},
                fields=["*"], order_by="idx asc")
        out["_controller_unavailable"] = True
        out["_caveat"] = (
            f"An app installed on this site overrides {doctype} and failed to "
            f"load. This record was read directly, so computed fields may be "
            f"missing.")
        return out

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
