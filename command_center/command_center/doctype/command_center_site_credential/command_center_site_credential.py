import frappe
from frappe.model.document import Document


class CommandCenterSiteCredential(Document):
    """One manager's own account on one other site.

    The platform never holds a credential that can act on behalf of everybody.
    Each manager links their own account to each business they work in, so a
    change made from this platform arrives at the owning site as that person —
    checked against their permissions there, recorded under their name in its
    change history, and revocable by deleting the key on that site without
    anyone touching this one.
    """

    def validate(self):
        if self.user != frappe.session.user and "System Manager" not in frappe.get_roles():
            frappe.throw("You can only store your own credentials.",
                         frappe.PermissionError)

        business = frappe.db.get_value(
            "Connected Business", {"business_code": self.business_code},
            ["name", "is_local"], as_dict=True)
        if not business:
            frappe.throw(f"No connected business with code {self.business_code}.")
        if business.is_local:
            frappe.throw(
                "This business is on this site, so your existing login already "
                "applies. No separate credentials are needed.")
