from frappe.model.document import Document


class CommandCenterFactPartyBalance(Document):
    """What each customer and supplier really owes, by the ledger, one row per party.

    Beside it, what their open invoices say, and the reasons the two differ: payments
    never matched to an invoice, journal entries and credit notes not linked to one.
    The ageing is the invoices' and opening balances' after the unmatched credits are
    set against the oldest of them first, so a payment made but never matched stops
    reading as a debt a thousand days old.

    Rows are derived and rebuilt whole on every load that finds something changed.
    """

    @staticmethod
    def on_doctype_update():
        import frappe

        frappe.db.add_index("Command Center Fact Party Balance",
                            ["business_code", "party_type", "party"])
