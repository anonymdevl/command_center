from frappe.model.document import Document


class CommandCenterFactSalesInvoiceLine(Document):
    """Revenue, cost and margin at item-line grain.

    `has_cost` records whether the source carried a valuation. A margin KPI must
    exclude the rows where it did not, rather than treating an absent cost as zero
    and reporting the sale as pure profit.
    """

    @staticmethod
    def on_doctype_update():
        import frappe

        frappe.db.add_index("Command Center Fact Sales Invoice Line",
                            ["business_code", "item_group"])
        frappe.db.add_index("Command Center Fact Sales Invoice Line",
                            ["business_code", "posting_date"])
