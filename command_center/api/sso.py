"""Sign in with the business's own ERPNext -- and only if this platform already knows you.

The "Ask AI" link on a business's ERPNext workspace points here. The person is sent to
that ERPNext to sign in (they usually already are), ERPNext tells us who they are, and
then this platform decides. ERPNext's answer is identity only; it is never permission:

    1. The sign-in must have started here, in this browser (state, single use, matched
       against a cookie set when it started), and come back within ten minutes.
    2. The business's ERPNext must vouch for the person (authorisation code exchanged
       with the client secret, then its OpenID profile read with that token).
    3. The email it names must be an account on THIS platform, enabled, holding
       Command Center Manager -- an account Michael created here. A role someone
       gives themselves on their own ERPNext changes nothing: it can show them the
       link, never let them in.

Anyone who fails any step is refused with a sentence saying why, and the refusal is
recorded in the Error Log ("Command Center sign-in refused"). A success is a normal
Frappe login (Activity Log records it) and lands on /command-center, nowhere else --
no "return to" address is taken from the request, so the link cannot be turned into a
redirect to another site.

On the business's ERPNext this needs one OAuth Client (configuration, nothing
installed): grant type Authorization Code, response type Code, scopes "openid all",
redirect URI = this site's /api/method/command_center.api.sso.callback, and Skip
Authorization ticked so a signed-in manager is not asked to confirm each time. Its
client id and secret go on the Connected Business (Sign-in section). The link is:

    https://<this site>/api/method/command_center.api.sso.start?business=<code>

Frappe's OAuth provider is the same on v14, v15 and v16, so this works whatever
version the business runs (Gigmann's live site is v14).

What it cannot protect against: whoever administers the business's ERPNext can make
an account there carry any email, and so could sign in as a manager whose email is on
this platform. That administrator can already do anything in that ERPNext; the
platform is exactly as trustworthy as they are, and no sign-in that relies on their
ERPNext can be more.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import frappe

# The manager role, defined once (api/businesses.py). Sign-in through a business's ERPNext
# admits managers only -- not System Managers, who sign in with their own password.
from command_center.api.businesses import ROLE  # noqa: E402

STATE_TTL = 600
COOKIE = "cc_sso"
HOME = "/command-center"
AUTHORIZE = "/api/method/frappe.integrations.oauth2.authorize"
TOKEN = "/api/method/frappe.integrations.oauth2.get_token"
PROFILE = "/api/method/frappe.integrations.oauth2.openid_profile"
TIMEOUT = 15


class Refused(Exception):
    """A sign-in this platform will not complete. The message is shown to the person."""


def _callback_url() -> str:
    return frappe.utils.get_url("/api/method/command_center.api.sso.callback")


def _business(code: str):
    """The business whose ERPNext vouches for people, with sign-in set up."""
    name = frappe.db.get_value("Connected Business",
                               {"business_code": code, "status": ["!=", "Paused"],
                                "is_local": 0})
    if not name:
        raise Refused("This sign-in link names a business the platform does not connect to.")
    b = frappe.get_doc("Connected Business", name)
    secret = b.get_password("sso_client_secret", raise_exception=False)
    if not (b.site_url and b.sso_client_id and secret):
        raise Refused(f"Signing in with {b.business_name}'s ERPNext is not set up yet. "
                      f"Use the platform's own sign-in page for now.")
    return b, secret


@frappe.whitelist(allow_guest=True, methods=["GET"])
def start(business: str | None = None):
    """Where the Ask AI link points: off to the business's ERPNext to say who you are."""
    try:
        b, _ = _business(business or "")
    except Refused as e:
        return _refuse(str(e), business)
    state = frappe.generate_hash(length=32)
    frappe.cache().set_value(_key(state), {"business": b.business_code},
                             expires_in_sec=STATE_TTL)
    _set_cookie(state)
    _redirect(f"{b.site_url.rstrip('/')}{AUTHORIZE}?" + urlencode({
        "client_id": b.sso_client_id, "redirect_uri": _callback_url(),
        "response_type": "code", "scope": "openid all", "state": state}))


@frappe.whitelist(allow_guest=True, methods=["GET"])
def callback(code: str | None = None, state: str | None = None, error: str | None = None,
             **kwargs):
    """Where the business's ERPNext sends the person back. Every check, then a login."""
    business = None
    try:
        if error:
            raise Refused("The ERPNext sign-in was cancelled or refused there.")
        pending = _take_state(state)
        business = pending["business"]
        b, secret = _business(business)
        profile = _identify(b, secret, code)
        user = _approved(profile)
    except Refused as e:
        return _refuse(str(e), business)
    except Exception:
        frappe.log_error(title="Command Center sign-in failed", message=frappe.get_traceback())
        return _refuse("The sign-in could not be completed. Try the link again; if it keeps "
                       "failing, use the platform's own sign-in page.", business)
    _login(user)
    _redirect(HOME)


# ---------------------------------------------------------------------------
def _key(state: str) -> str:
    return f"cc:sso:state:{state}"


def _take_state(state: str | None) -> dict:
    """The state must be one this site issued, to this browser, in the last ten
    minutes -- and it is spent on first use, so a replayed callback is refused."""
    if not state:
        raise Refused("The sign-in did not come back with its reference. Start again from the link.")
    cookie = (frappe.request.cookies.get(COOKIE) if getattr(frappe, "request", None) else None)
    pending = frappe.cache().get_value(_key(state))
    frappe.cache().delete_value(_key(state))
    if not pending:
        raise Refused("This sign-in has expired or was already used. Start again from the link.")
    if cookie != state:
        raise Refused("This sign-in was started in a different browser. Start again from the link.")
    return pending


def _identify(b, secret: str, code: str | None) -> dict:
    """Who the business's ERPNext says this is: code -> token -> OpenID profile."""
    import requests

    if not code:
        raise Refused("The business's ERPNext did not confirm who you are.")
    base = b.site_url.rstrip("/")
    r = requests.post(base + TOKEN, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": _callback_url(),
        "client_id": b.sso_client_id, "client_secret": secret}, timeout=TIMEOUT)
    if not r.ok:
        raise Refused(f"{b.business_name}'s ERPNext would not confirm the sign-in "
                      f"(HTTP {r.status_code}).")
    token = (r.json() or {}).get("access_token")
    if not token:
        raise Refused(f"{b.business_name}'s ERPNext did not issue a sign-in token.")
    p = requests.get(base + PROFILE, headers={"Authorization": f"Bearer {token}"},
                     timeout=TIMEOUT)
    if not p.ok:
        raise Refused(f"{b.business_name}'s ERPNext would not say who you are (HTTP {p.status_code}).")
    body = p.json() or {}
    # Frappe answers with the profile itself; some versions wrap it in "message".
    profile = body.get("message") if isinstance(body.get("message"), dict) else body
    if not profile.get("email"):
        raise Refused(f"{b.business_name}'s ERPNext did not give an email for your account.")
    profile["_business"] = b.business_name
    return profile


def _approved(profile: dict) -> str:
    """The platform's own decision: an enabled account here, holding the manager role."""
    email = str(profile["email"]).strip().lower()
    user = frappe.db.get_value("User", {"name": email}) or frappe.db.get_value(
        "User", {"email": email})
    if not user or user in ("Administrator", "Guest"):
        raise Refused(f"{email} has not been given access to the AI Business Intelligence "
                      f"platform. Ask the platform's administrator to add you.")
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True) or {}
    if not row.get("enabled"):
        raise Refused(f"The platform account for {email} is disabled.")
    if row.get("user_type") != "System User" or ROLE not in frappe.get_roles(user):
        raise Refused(f"{email} is known to the platform but is not one of its managers.")
    return user


def _login(user: str):
    lm = getattr(frappe.local, "login_manager", None)
    if lm is None:
        from frappe.auth import LoginManager
        lm = LoginManager()
    lm.login_as(user)


def _set_cookie(state: str):
    cm = getattr(frappe.local, "cookie_manager", None)
    if cm:
        cm.set_cookie(COOKIE, state,
                      expires=frappe.utils.add_to_date(frappe.utils.now_datetime(),
                                                       seconds=STATE_TTL),
                      httponly=True, secure=True, samesite="Lax")


def _redirect(location: str):
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = location


def _refuse(why: str, business: str | None):
    """Said to the person, and recorded for whoever watches the platform's security."""
    ip = getattr(frappe.local, "request_ip", None)
    frappe.log_error(title="Command Center sign-in refused",
                     message=json.dumps({"why": why, "business": business, "ip": ip}))
    frappe.db.commit()
    frappe.respond_as_web_page("Sign-in not completed", why, http_status_code=403,
                               indicator_color="red")
