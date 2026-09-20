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
        # A cosmetic layer must never fail a migration -- but it must never fail
        # invisibly either. The first version of this only called log_error, and
        # when the workspace silently did not appear there was no log to read and
        # no sign anything had gone wrong. Printing puts it in the migrate output,
        # where whoever ran the command is actually looking.
        trace = frappe.get_traceback()
        print("\n!! command_center: desk views were not built\n" + trace)
        frappe.log_error(title="Command Center desk views", message=trace)
        frappe.db.commit()
