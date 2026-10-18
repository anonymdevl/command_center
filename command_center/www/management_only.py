"""The page for someone signed in without access: /management-only.

Signed out: to the sign-in page, which is where they can do something about it.
Management after all (a role just granted): straight on to the Command Center.
"""

import frappe

from command_center.api.businesses import ALLOWED_ROLES

no_cache = 1


def get_context(context):
    user = frappe.session.user
    if user == "Guest":
        frappe.local.flags.redirect_location = "/command-center-login"
        raise frappe.Redirect
    if ALLOWED_ROLES.intersection(frappe.get_roles(user)):
        frappe.local.flags.redirect_location = "/command-center"
        raise frappe.Redirect

    from command_center.www.command_center import _assets, _payload

    context.no_cache = 1
    context.assets = _assets()
    context.full_name = frappe.utils.get_fullname(user)
    context.user_id = user
    context.csrf_token = _payload(frappe.sessions.get_csrf_token())
    return context
