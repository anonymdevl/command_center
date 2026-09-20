from frappe.model.document import Document


class CommandCenterFactSalesInvoice(Document):
    """Receivables at invoice grain.

    Outstanding belongs here and nowhere else. Repeating a document total onto
    item lines is how a receivable ends up multiplied by the number of things
    sold, so the measure lives at the grain it describes.

    Rows are derived and rebuildable. Nothing here is a source of truth.
    """

    @staticmethod
    def on_doctype_update():
        """Indexes the queries actually run: scope, then ageing, then party."""
        import frappe

        frappe.db.add_index("Command Center Fact Sales Invoice",
                            ["business_code", "ageing_bucket"])
        frappe.db.add_index("Command Center Fact Sales Invoice",
                            ["business_code", "customer"])
