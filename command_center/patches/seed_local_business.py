import frappe


def execute():
    """Upgrade path only.

    A fresh install seeds through `after_install` — see the note there about
    patches being marked applied without running. This exists for sites that
    already carry an earlier version of the app, and for repairing a site whose
    registry row was deleted.
    """
    from command_center.install import seed_local_business

    name = seed_local_business()
    if name:
        frappe.db.commit()
