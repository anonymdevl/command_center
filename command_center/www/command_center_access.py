"""Where a sign-in through a business's ERPNext lands when the platform says no:
/command-center-access?ref=<one-time reference>.

api/sso.py records the reason under the reference (ten minutes) and sends the person
here, so they read a plain sentence on the platform's own page, never a bare 403. The
wording is fixed here, per reason: nothing in the address is shown, so the page cannot
be made to say something else, nor used to learn which businesses the platform
connects. An unknown or expired reference shows the general message.
"""

import frappe

from command_center.api.sso import ACCESS_KEY

no_cache = 1

# why -> (heading, sentence, offer "Try again")
REASONS = {
    "no_role": ("You don't have access yet",
                "Your account on {business}'s ERPNext isn't set up for the platform. Ask "
                "your ERPNext administrator to give you access, then open it again from "
                "ERPNext.", False),
    "paused": ("Your access is paused",
               "Your access to the platform has been paused. Please contact your "
               "administrator.", False),
    "expired": ("This sign-in has expired",
                "For your security, each sign-in works once and only for a few minutes. "
                "Please open the platform again from ERPNext.", True),
    "other_browser": ("Please continue in the same browser",
                      "This sign-in was started in a different browser or window. Open the "
                      "platform again from ERPNext in this browser.", True),
    "cancelled": ("Sign-in cancelled",
                  "Nothing was changed. Open the platform again from ERPNext whenever "
                  "you're ready.", True),
    "unconfirmed": ("We couldn't confirm your sign-in",
                    "{business}'s ERPNext didn't confirm who you are. Please try again.", True),
    "unreachable": ("We couldn't check your access",
                    "{business}'s ERPNext didn't respond just now. Please try again in a "
                    "minute.", True),
    "not_setup": ("Sign-in from ERPNext isn't available yet",
                  "It hasn't been set up for this business. Please contact your "
                  "administrator.", False),
    "unknown_business": ("Sign-in from ERPNext isn't available",
                         "This link doesn't belong to a business the platform serves. "
                         "Please contact your administrator.", False),
    "not_allowed": ("This account can't sign in this way",
                    "Please use the platform's own sign-in page.", False),
    "own_account": ("This account can't sign in this way",
                    "An account with your email already exists on the platform and wasn't "
                    "set up through {business}'s ERPNext, so it doesn't open from there. "
                    "Please use the platform's own sign-in page, or contact your "
                    "administrator.", False),
    "no_seat": ("There's no seat free for you yet",
                "Your organisation has used all of the user seats on its plan. Please ask "
                "your administrator to free or add a seat, then open the platform again "
                "from ERPNext.", False),
    "failed": ("Something went wrong",
               "The sign-in couldn't be completed. Please try again; if it keeps "
               "happening, contact your administrator.", True),
}


def get_context(context):
    ref = str(frappe.form_dict.get("ref") or "")[:64]
    pending = frappe.cache().get_value(f"{ACCESS_KEY}{ref}") if ref else None
    why = (pending or {}).get("why") or "failed"
    heading, sentence, retry = REASONS.get(why, REASONS["failed"])

    business_name, erp_url, retry_url = "your company", None, None
    code = (pending or {}).get("business")
    if code:
        b = frappe.db.get_value("Connected Business", {"business_code": code, "is_local": 0},
                                ["business_name", "site_url"], as_dict=True)
        if b:
            business_name = b.business_name or business_name
            erp_url = (b.site_url or "").rstrip("/") + "/app" if b.site_url else None
            if retry:
                retry_url = f"/api/method/command_center.api.sso.start?business={code}"

    from command_center.www.command_center import _assets, _brand

    context.no_cache = 1
    context.assets = _assets()
    context.brand = _brand()
    context.heading = heading
    text = sentence.format(business=business_name)
    context.sentence = text[:1].upper() + text[1:]
    context.retry_url = retry_url
    context.erp_url = erp_url
    context.own_sign_in = why in ("not_allowed", "own_account", "not_setup",
                                  "unknown_business") or not erp_url
    return context
