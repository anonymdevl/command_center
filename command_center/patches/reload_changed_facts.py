import frappe

# The facts whose rows are worked out differently from 17 Nov 2026 (the order book line by
# line, the payments with each one's own amount); insights/core/migrations/0013 does the
# same on the standalone platform.
RELOAD = ("fact_sales_order", "fact_payment_allocation")


def execute():
    """Clear their watermarks, so the load deploy.sh runs straight after migrate reads every
    document again and replaces the rows worked out the old way."""
    if not frappe.db.exists("DocType", "Command Center Ingest State"):
        return
    for name in frappe.get_all("Command Center Ingest State", filters={"fact": ["in", list(RELOAD)]},
                               pluck="name"):
        frappe.db.set_value("Command Center Ingest State", name, "last_src_modified", None,
                            update_modified=False)
