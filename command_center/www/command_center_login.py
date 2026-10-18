"""The Command Center's own sign-in page: /command-center-login.

The page is ours; the sign-in is ERPNext's. The form posts to Frappe's own
/api/method/login, so passwords, lock-outs after failed attempts, and password
policy all behave exactly as they do on ERPNext's login. If the account uses
two-factor authentication, the page hands over to ERPNext's /login for the code
step and comes back here -- a second, home-made 2FA flow would be a second thing to
get wrong.

Signed in already: management goes straight to the Command Center; anyone else to
the access page, rather than being shown a form that cannot help them.
"""

import frappe

from command_center.api.businesses import ALLOWED_ROLES

no_cache = 1


def get_context(context):
    user = frappe.session.user
    if user != "Guest":
        target = ("/command-center" if ALLOWED_ROLES.intersection(frappe.get_roles(user))
                  else "/management-only")
        frappe.local.flags.redirect_location = target
        raise frappe.Redirect

    from command_center.www.command_center import _assets, _payload

    context.no_cache = 1
    context.assets = _assets()
    context.csrf_token = _payload(frappe.sessions.get_csrf_token())
    return context
