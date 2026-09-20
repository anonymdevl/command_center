import frappe


def execute():
    """Register the host site as connector number one.

    The app must never treat the site it is installed on as a special case. It is
    simply the Connected Business flagged `is_local`. Every engine above this
    layer sees N businesses and never asks which one it is living inside — which
    is what makes moving the platform to another site a configuration change
    rather than a rewrite.
    """
    if frappe.db.exists("Connected Business", {"is_local": 1}):
        return

    company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
    if not company:
        # Site has no Company yet. The business is registered on first use.
        return

    currency = frappe.db.get_value("Company", company, "default_currency")

    frappe.get_doc(
        {
            "doctype": "Connected Business",
            "business_name": company,
            "business_code": frappe.scrub(company)[:40],
            "is_local": 1,
            "erpnext_company": company,
            "currency": currency,
            "status": "Active",
        }
    ).insert(ignore_permissions=True)
