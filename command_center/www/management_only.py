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
        frappe.local.flags.redirect_location = "/sign-in"
        raise frappe.Redirect
    if ALLOWED_ROLES.intersection(frappe.get_roles(user)):
        frappe.local.flags.redirect_location = "/command-center"
        raise frappe.Redirect

    from command_center.www.command_center import _assets, _brand, _payload

    context.no_cache = 1
    context.assets = _assets()
    context.brand = _brand()
    context.erp_url = _erp_url(user)
    context.full_name = frappe.utils.get_fullname(user)
    context.user_id = user
    context.csrf_token = _payload(frappe.sessions.get_csrf_token())
    return context


def _erp_url(user: str) -> str | None:
    """Their own ERPNext, for "Back to ERPNext": the business they signed in from (the
    sign-in marks it, api/sso.MARK), else the only business there is. Never "/app" --
    the standalone platform has no desk there, and it was a 404 (17 Nov 2026). With no
    one address to send them to, the page offers none."""
    from command_center.api.sso import MARK
    codes = frappe.get_all("DefaultValue", filters={"parent": user, "defkey": MARK}, pluck="defvalue")
    filters = {"business_code": ["in", codes]} if codes else {}
    urls = {(u or "").strip().rstrip("/") for u in frappe.get_all(
        "Connected Business", filters={**filters, "is_local": 0}, pluck="site_url")}
    urls = {u for u in urls if u.startswith(("https://", "http://"))}
    return f"{urls.pop()}/app" if len(urls) == 1 else None
