from frappe.model.document import Document


class CommandCenterFactPurchaseInvoiceLine(Document):
    """What we bought, line by line.

    Spend at line grain, so "where the money goes" can be answered by item and by
    supplier without touching the payable.

    Rows are derived and rebuildable. Nothing here is a source of truth.
    """

    @staticmethod
    def on_doctype_update():
        """Indexes the queries actually run."""
        import frappe

        frappe.db.add_index("Command Center Fact Purchase Invoice Line",
                            ["business_code", "item_group"])
        frappe.db.add_index("Command Center Fact Purchase Invoice Line",
                            ["business_code", "supplier"])
