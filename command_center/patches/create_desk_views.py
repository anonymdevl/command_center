import frappe


def execute():
    """Build the desk workspace on an existing site.

    A fresh install gets this from after_install. This patch is for sites that
    already carry the app — which is every site by the time a workspace is worth
    having.
    """
    from command_center.desk import build

    try:
        build()
    except Exception:
        # A cosmetic layer must never fail a migration.
        frappe.log_error(title="Command Center desk views",
                         message=frappe.get_traceback())
