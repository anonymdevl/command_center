from frappe.model.document import Document


class CommandCenterFactPaymentAllocation(Document):
    """Cash, and the document it was applied to.

    `unallocated_amount` belongs to the payment rather than the allocation, so it
    repeats across a payment's rows. Aggregate it over distinct payments; summing
    it over allocations overstates unmatched cash.
    """

    @staticmethod
    def on_doctype_update():
        import frappe

        frappe.db.add_index("Command Center Fact Payment Allocation",
                            ["business_code", "against_name"])
        frappe.db.add_index("Command Center Fact Payment Allocation",
                            ["business_code", "party"])
