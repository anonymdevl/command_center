"""What the scope switcher is built from.

The list a manager sees is derived from where they can actually reach, not from a
separate permission table this app maintains. That is not a shortcut — a list
kept here would drift from the truth held on each site, and a switcher that
offers a business the user cannot read is worse than one that omits it.
"""

from __future__ import annotations

import frappe

ROLE = "Command Center Manager"

# The only definition of who may enter. The apps-screen tile, the page guard and
# every endpoint read this one set, so a change here cannot leave a door open
# somewhere else.
#
# System Manager is included so the people who administer the site can support it.
# Everyone else is sent to /management-only.
ALLOWED_ROLES = {ROLE, "System Manager"}


def has_app_permission() -> bool:
    """Whether to show the Command Center tile on /apps.

    Frappe calls this for the apps screen. Returning False hides the tile rather
    than offering a link that leads to a refusal.
    """
    if frappe.session.user == "Guest":
        return False
    return bool(ALLOWED_ROLES.intersection(frappe.get_roles()))


def require_manager():
    """The platform is management-only.

    There is no general staff view, by design and by contract. A staff member's
    window into the business is ERPNext itself.
    """
    if not ALLOWED_ROLES.intersection(frappe.get_roles()):
        frappe.throw("The Command Center is available to management only.",
                     frappe.PermissionError)


@frappe.whitelist()
def get_visible_businesses():
    """The three levels the interface is built on.

    Level one is every business in this list at once. Level two is any single
    entry. Level three is the records underneath it.
    """
    require_manager()

    rows = frappe.get_all(
        "Connected Business",
        filters={"status": ["!=", "Paused"]},
        fields=["business_code", "business_name", "is_local", "status",
                "currency", "erpnext_company", "site_url", "last_sync"],
        order_by="is_local desc, business_name asc",
    )

    for row in rows:
        # Reading is available wherever the platform can reach. Acting requires
        # the manager's own account on the owning site, which is why a peer
        # reports can_act as false until per-user authorisation is in place.
        row["can_read"] = row["status"] == "Active"
        row["can_act"] = bool(row["is_local"])
        row["acts_at"] = None if row["is_local"] else row["site_url"]

    return {
        "businesses": rows,
        "scopes": [{"code": "__all__", "label": "All businesses"}] + [
            {"code": r["business_code"], "label": r["business_name"]} for r in rows
        ],
    }


@frappe.whitelist()
def test_connection(business_code: str):
    require_manager()
    from command_center.connectors.registry import connector_for

    conn = connector_for(business_code)
    return {"business": conn.name, "reachable": conn.ping()}


def currency_for(business_code: str | None) -> str | None:
    """One currency, or none because there is more than one.

    Across all businesses a money figure is only a number if every site reports in
    the same currency. When they do not, saying so is the only honest answer: adding
    cedis to dollars produces a total that means nothing.

    Defined here because both the KPI engine and the records drawer need it, and it
    was briefly defined in both.
    """
    if business_code and business_code != "__all__":
        return frappe.db.get_value("Connected Business",
                                   {"business_code": business_code}, "currency")
    found = {c for (c,) in frappe.db.sql(
        """select distinct currency from `tabConnected Business`
           where status = 'Active' and ifnull(currency, '') != ''""")}
    return found.pop() if len(found) == 1 else None
