from frappe.model.document import Document


class CommandCenterFactPerson(Document):
    """Who works here, where, and since when.

    Headcount is a count of active people, so is_active is stored rather than
    inferred from a status string that differs between installations.

    Rows are derived and rebuildable. Nothing here is a source of truth.
    """

    @staticmethod
    def on_doctype_update():
        import frappe

        frappe.db.add_index("Command Center Fact Person", ["business_code", "department"])
        frappe.db.add_index("Command Center Fact Person", ["business_code", "is_active"])
