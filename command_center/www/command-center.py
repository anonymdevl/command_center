"""Who may open the Command Center, and where everyone else goes.

The check happens server-side, before any context is built. A page that renders
and then hides its contents has already sent them.
"""

import frappe

from command_center.api.businesses import ALLOWED_ROLES

no_cache = 1


def get_context(context):
    user = frappe.session.user

    # Not signed in: log in first, then come back here.
    if user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/command-center"
        raise frappe.Redirect

    if not ALLOWED_ROLES.intersection(frappe.get_roles(user)):
        frappe.local.flags.redirect_location = "/management-only"
        raise frappe.Redirect

    context.no_cache = 1
    context.user_fullname = frappe.utils.get_fullname(user)
    return context
