import frappe

WORKSPACE = "Command Center"
CARDS = ["Owed to us", "Unpaid invoices", "Beyond three months",
         "Invoiced revenue", "Margin, where cost is known", "Cash applied"]
CHARTS = ["Money owed by age", "Money owed by customer", "Revenue by item group"]


def execute():
    """Remove the desk workspace. There is one Command Center and it is the page.

    The workspace was a stopgap so figures could be checked while the interface
    was outstanding. Leaving it in place once the interface exists means two
    things answer to the same name, one of them made of stock number cards, and
    the wrong one is what a manager finds first.

    Removing it also disposes of a bug rather than fixing it: the cards carried
    three-element filters where Frappe wants four, so every load raised
    "Invalid filter: =".
    """
    for card in CARDS:
        _drop("Number Card", card)
    for chart in CHARTS:
        _drop("Dashboard Chart", chart)
    _drop("Workspace", WORKSPACE)
    frappe.db.commit()


def _drop(doctype, name):
    if not frappe.db.exists(doctype, name):
        return
    # Only ever our own: a card or chart someone else built that happens to share
    # a name is not ours to delete.
    if doctype in ("Number Card", "Dashboard Chart"):
        if frappe.db.get_value(doctype, name, "module") != "Command Center":
            return
    try:
        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
    except Exception:
        frappe.log_error(title=f"Command Center: could not remove {doctype} {name}",
                         message=frappe.get_traceback())
