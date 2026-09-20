from frappe.model.document import Document


class CommandCenterFactStockBalance(Document):
    """What is on the shelf, and what it is worth.

    One row per item per warehouse, read from Bin. Free-to-sell is stored rather
    than derived at read time, because on-hand minus reserved is the figure a
    manager means by "stock" and every screen should agree on it.

    Rows are derived and rebuildable. Nothing here is a source of truth.
    """

    @staticmethod
    def on_doctype_update():
        """Indexes the queries actually run."""
        import frappe

        frappe.db.add_index("Command Center Fact Stock Balance",
                            ["business_code", "warehouse"])
        frappe.db.add_index("Command Center Fact Stock Balance",
                            ["business_code", "item_group"])
