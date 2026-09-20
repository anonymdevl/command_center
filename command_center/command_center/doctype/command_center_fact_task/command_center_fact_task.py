from frappe.model.document import Document


class CommandCenterFactTask(Document):
    """Work in flight, and whether anyone owns it.

    is_assigned is stored because unowned work is the thing worth reporting, and an
    empty column reads as missing data rather than as a finding.

    Rows are derived and rebuildable. Nothing here is a source of truth.
    """

    @staticmethod
    def on_doctype_update():
        import frappe

        frappe.db.add_index("Command Center Fact Task", ["business_code", "lateness_bucket"])
        frappe.db.add_index("Command Center Fact Task", ["business_code", "assigned_to"])
        frappe.db.add_index("Command Center Fact Task", ["business_code", "is_open"])
