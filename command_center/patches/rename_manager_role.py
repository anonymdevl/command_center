"""The platform's role, "Command Center Manager", is now "Insights Dashboard Manager"
(Michael, 14 Nov 2026).

Not "Dashboard Manager", which he asked for first: that is Frappe's own standard role
(who may edit desk dashboards and charts), so every holder of it would have been let
into the platform.

Frappe's own rename moves every reference -- each person's role, the doctypes'
permissions, the workspace restriction. Runs before the doctypes sync, so the renamed
permissions in their JSON meet a role that already exists. If both names exist (a site
someone half-fixed by hand), the holders of the old one are given the new one and the
old one goes.
"""

import frappe

from command_center.api.businesses import ROLE

OLD = "Command Center Manager"


def execute():
    if not frappe.db.exists("Role", OLD):
        return
    if frappe.db.exists("Role", ROLE):
        for user in frappe.get_all("Has Role", filters={"role": OLD, "parenttype": "User"},
                                   pluck="parent"):
            frappe.get_doc("User", user).add_roles(ROLE)
        frappe.delete_doc("Role", OLD, force=True, ignore_permissions=True)
        return
    frappe.rename_doc("Role", OLD, ROLE, force=True)
    frappe.db.set_value("Role", ROLE, "role_name", ROLE)
