from frappe.model.document import Document


class CommandCenterFactPurchaseInvoice(Document):
    """What we owe suppliers, at invoice grain.

    Outstanding belongs here and nowhere else, for the same reason it does on the
    sales side: a document total repeated onto item lines is how a payable ends up
    multiplied by the number of things bought.

    Rows are derived and rebuildable. Nothing here is a source of truth.
    """

    @staticmethod
    def on_doctype_update():
        """Indexes the queries actually run."""
        import frappe

        frappe.db.add_index("Command Center Fact Purchase Invoice",
                            ["business_code", "ageing_bucket"])
        frappe.db.add_index("Command Center Fact Purchase Invoice",
                            ["business_code", "supplier"])
