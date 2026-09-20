from frappe.model.document import Document


class CommandCenterFactSalesOrder(Document):
    """What we have promised and not yet delivered.

    Undelivered value is stored rather than derived, because order value less the
    delivered share is what answers whether we can deliver what we have sold, and
    every screen must agree on it.

    Rows are derived and rebuildable. Nothing here is a source of truth.
    """

    @staticmethod
    def on_doctype_update():
        import frappe

        frappe.db.add_index("Command Center Fact Sales Order", ["business_code", "lateness_bucket"])
        frappe.db.add_index("Command Center Fact Sales Order", ["business_code", "customer"])
        frappe.db.add_index("Command Center Fact Sales Order", ["business_code", "is_open"])
