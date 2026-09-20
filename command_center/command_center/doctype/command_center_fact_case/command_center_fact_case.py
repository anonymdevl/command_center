from frappe.model.document import Document


class CommandCenterFactCase(Document):
    """Complaints and support cases, and how long people are waiting.

    Days open is measured against the data horizon, never today, for the same reason
    receivables ageing is.

    Rows are derived and rebuildable. Nothing here is a source of truth.
    """

    @staticmethod
    def on_doctype_update():
        import frappe

        frappe.db.add_index("Command Center Fact Case", ["business_code", "wait_bucket"])
        frappe.db.add_index("Command Center Fact Case", ["business_code", "is_open"])
        frappe.db.add_index("Command Center Fact Case", ["business_code", "customer"])
