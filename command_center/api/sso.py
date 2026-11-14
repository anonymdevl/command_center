"""Sign in with the business's own ERPNext. Who may come in is decided there, by a role.

The link on a business's ERPNext points here. The person is sent to that ERPNext to
sign in (they usually already are), ERPNext tells us who they are, and then:

    1. The sign-in must have started here, in this browser (state, single use, matched
       against a cookie set when it started), and come back within ten minutes.
    2. The business's ERPNext must vouch for the person (authorisation code exchanged
       with the client secret, then its OpenID profile read with that token).
    3. That person must hold the access role -- "Executive Insights" unless the site
       config names another (command_center_sso_role) -- on the business's ERPNext,
       and be enabled there. The platform reads this itself, with the business's
       read-only service key (api/ingest.erp_members); the token's own claims are not
       trusted for it.
    4. A platform account that was paused here (disabled) stays out, whatever ERPNext
       says: the platform's administrator can always stop one person.

A person who passes and has no account here gets one on the spot: a System User with
Command Center Manager, no password, no email. So adding someone is giving them the
role in their own ERPNext -- nothing to do on this platform (Michael, 14 Nov 2026:
"must Samuel come to me for a bench command to add a user? doesn't make sense").

Taking the role away there takes the platform away too: the next sign-in is refused,
and sync_members (every 15 minutes) removes Command Center Manager from anyone whose
role is gone and ends their sessions. Only accounts this sign-in let in are touched
(marked per business in DefaultValue, key cc_sso_business); a manager added by hand,
a System Manager and Administrator are never changed by it. If the business's ERPNext
cannot be reached, sign-in fails closed and the sync changes nothing.

Who can hand out the role is whoever may edit roles on that ERPNext -- on Gigmann's,
14 Nov 2026, only Powersoft's own accounts (demo@, Administrator, michael@). Holding
the role is the permission; that administrator is trusted exactly as far as their
ERPNext is.

Anyone refused gets a sentence saying why, and the refusal is recorded in the Error Log
("Command Center sign-in refused"). A success is a normal Frappe login (Activity Log
records it) and lands on /command-center, nowhere else -- no "return to" address is
taken from the request, so the link cannot be turned into a redirect to another site.

On the business's ERPNext this needs one OAuth Client (configuration, nothing
installed): grant type Authorization Code, response type Code, scopes "openid all",
redirect URI = this site's /api/method/command_center.api.sso.callback, and Skip
Authorization ticked. Its client id and secret go on the Connected Business (Sign-in
section). Frappe's OAuth provider is the same on v14, v15 and v16. The link is:

    https://<this site>/api/method/command_center.api.sso.start?business=<code>
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import frappe

# The manager role, defined once (api/businesses.py).
from command_center.api.businesses import ROLE  # noqa: E402

STATE_TTL = 600
COOKIE = "cc_sso"
HOME = "/command-center"
AUTHORIZE = "/api/method/frappe.integrations.oauth2.authorize"
TOKEN = "/api/method/frappe.integrations.oauth2.get_token"
PROFILE = "/api/method/frappe.integrations.oauth2.openid_profile"
TIMEOUT = 15
ACCESS_ROLE = "Executive Insights"
MARK = "cc_sso_business"
NEVER_TOUCHED = ("Administrator", "Guest")
ACCESS_PAGE = "/command-center-access"
ACCESS_KEY = "cc:sso:refused:"


class Refused(Exception):
    """A sign-in this platform will not complete. `why` picks the sentence the person
    reads (www/command_center_access.py, fixed wording); `detail` is for the log."""

    def __init__(self, why: str, detail: str = ""):
        super().__init__(detail or why)
        self.why, self.detail = why, detail or why


def access_role() -> str:
    """The role on a business's ERPNext that opens the platform."""
    return frappe.conf.get("command_center_sso_role") or ACCESS_ROLE


def _callback_url() -> str:
    return frappe.utils.get_url("/api/method/command_center.api.sso.callback")


def _business(code: str):
    """The business whose ERPNext vouches for people, with sign-in set up."""
    name = frappe.db.get_value("Connected Business",
                               {"business_code": code, "status": ["!=", "Paused"],
                                "is_local": 0})
    if not name:
        raise Refused("unknown_business", "This sign-in link names a business the platform does not connect to.")
    b = frappe.get_doc("Connected Business", name)
    secret = b.get_password("sso_client_secret", raise_exception=False)
    if not (b.site_url and b.sso_client_id and secret):
        raise Refused("not_setup", f"Signing in with {b.business_name}'s ERPNext is not set up yet. "
                      f"Use the platform's own sign-in page for now.")
    return b, secret


@frappe.whitelist(allow_guest=True, methods=["GET"])
def start(business: str | None = None):
    """Where the link points: off to the business's ERPNext to say who you are."""
    try:
        b, _ = _business(business or "")
    except Refused as e:
        return _refuse(e, business)
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
            raise Refused("cancelled", "The ERPNext sign-in was cancelled or refused there.")
        pending = _take_state(state)
        business = pending["business"]
        b, secret = _business(business)
        profile = _identify(b, secret, code)
        user = _approved(profile, b)
    except Refused as e:
        frappe.db.commit()  # an access taken away above stays taken away
        return _refuse(e, business)
    except Exception:
        frappe.log_error(title="Command Center sign-in failed", message=frappe.get_traceback())
        return _refuse(Refused("failed", "The sign-in could not be completed."), business)
    frappe.db.commit()
    _login(user)
    _redirect(HOME)


# ---------------------------------------------------------------------------
def _key(state: str) -> str:
    return f"cc:sso:state:{state}"


def _take_state(state: str | None) -> dict:
    """The state must be one this site issued, to this browser, in the last ten
    minutes -- and it is spent on first use, so a replayed callback is refused."""
    if not state:
        raise Refused("expired", "The sign-in did not come back with its reference. Start again from the link.")
    cookie = (frappe.request.cookies.get(COOKIE) if getattr(frappe, "request", None) else None)
    pending = frappe.cache().get_value(_key(state))
    frappe.cache().delete_value(_key(state))
    if not pending:
        raise Refused("expired", "This sign-in has expired or was already used. Start again from the link.")
    if cookie != state:
        raise Refused("other_browser", "This sign-in was started in a different browser. Start again from the link.")
    return pending


def _identify(b, secret: str, code: str | None) -> dict:
    """Who the business's ERPNext says this is: code -> token -> OpenID profile."""
    import requests

    if not code:
        raise Refused("unconfirmed", "The business's ERPNext did not confirm who you are.")
    base = b.site_url.rstrip("/")
    r = requests.post(base + TOKEN, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": _callback_url(),
        "client_id": b.sso_client_id, "client_secret": secret}, timeout=TIMEOUT)
    if not r.ok:
        raise Refused("unconfirmed", f"{b.business_name}'s ERPNext would not confirm the sign-in "
                      f"(HTTP {r.status_code}).")
    token = (r.json() or {}).get("access_token")
    if not token:
        raise Refused("unconfirmed", f"{b.business_name}'s ERPNext did not issue a sign-in token.")
    p = requests.get(base + PROFILE, headers={"Authorization": f"Bearer {token}"},
                     timeout=TIMEOUT)
    if not p.ok:
        raise Refused("unconfirmed", f"{b.business_name}'s ERPNext would not say who you are (HTTP {p.status_code}).")
    body = p.json() or {}
    # Frappe answers with the profile itself; some versions wrap it in "message".
    profile = body.get("message") if isinstance(body.get("message"), dict) else body
    if not profile.get("email"):
        raise Refused("unconfirmed", f"{b.business_name}'s ERPNext did not give an email for your account.")
    return profile


def _approved(profile: dict, b) -> str:
    """The role on their ERPNext lets them in; a pause here keeps them out."""
    email = str(profile["email"]).strip().lower()
    if email in ("administrator", "guest"):
        raise Refused("not_allowed", "That account cannot sign in this way.")
    role = access_role()
    try:
        from command_center.api.ingest import erp_members
        members = erp_members(b.business_code, role)
    except Exception:
        frappe.log_error(title="Command Center sign-in: role check failed",
                         message=frappe.get_traceback())
        raise Refused("unreachable", f"The platform could not check your access on {b.business_name}'s "
                      f"ERPNext just now. Try again in a minute.")
    user = _platform_user(email)
    if email not in members:
        if user:
            _unmark(user, b.business_code)
        raise Refused("no_role", f"{email} does not hold the {role} role on {b.business_name}'s "
                      f"ERPNext, so it cannot open the platform. Ask your ERPNext "
                      f"administrator for it.")
    if user:
        if user in NEVER_TOUCHED:
            raise Refused("not_allowed", "That account cannot sign in this way.")
        enabled = frappe.db.get_value("User", user, "enabled")
        if not enabled:
            raise Refused("paused", f"The platform account for {email} has been paused. Ask the "
                          f"platform's administrator.")
    else:
        user = _provision(email, profile)
    if ROLE not in frappe.get_roles(user):
        frappe.get_doc("User", user).add_roles(ROLE)
    _mark(user, b.business_code)
    return user


def _platform_user(email: str) -> str | None:
    return (frappe.db.get_value("User", {"name": email})
            or frappe.db.get_value("User", {"email": email}))


def _provision(email: str, profile: dict) -> str:
    """An account for someone their ERPNext let in: a manager, no password, no email."""
    first = profile.get("given_name") or (profile.get("name") or email).split(" ")[0]
    last = profile.get("family_name") or " ".join((profile.get("name") or "").split(" ")[1:])
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": first,
                           "last_name": last, "user_type": "System User",
                           "send_welcome_email": 0})
    user.flags.no_welcome_mail = True
    user.insert(ignore_permissions=True)
    return user.name


def _marks(user: str) -> list:
    return frappe.get_all("DefaultValue", filters={"parent": user, "defkey": MARK},
                          pluck="defvalue")


def _mark(user: str, code: str):
    """Remember that this business's role let them in -- what the sync may undo."""
    if code not in _marks(user):
        frappe.defaults.add_default(MARK, code, parent=user)


def _unmark(user: str, code: str):
    """Their role on that business is gone. Without any business left, so is the
    platform: the manager role comes off and they are signed out everywhere. A manager
    added by hand (never marked) is not touched, nor an administrator."""
    if code not in _marks(user):
        return
    frappe.defaults.clear_default(MARK, value=code, parent=user)
    if _marks(user) or user in NEVER_TOUCHED or "System Manager" in frappe.get_roles(user):
        return
    frappe.get_doc("User", user).remove_roles(ROLE)
    from frappe.sessions import clear_sessions
    clear_sessions(user=user, force=True)
    frappe.log_error(title="Command Center access removed",
                     message=json.dumps({"user": user, "business": code,
                                         "why": f"no longer holds {access_role()}"}))


def sync_members():
    """Every 15 minutes (hooks.py): whoever came in through a business's ERPNext and no
    longer holds the role there loses the platform. A business that cannot be reached
    changes nothing -- a network fault never locks anyone out."""
    role = access_role()
    from command_center.api.ingest import erp_members
    for b in frappe.get_all("Connected Business",
                            filters={"is_local": 0, "status": ["!=", "Paused"]},
                            fields=["business_code", "sso_client_id"]):
        if not b.sso_client_id:
            continue
        try:
            members = erp_members(b.business_code, role)
        except Exception:
            frappe.log_error(title=f"Command Center access sync: {b.business_code} unreachable",
                             message=frappe.get_traceback())
            continue
        for user in frappe.get_all("DefaultValue",
                                   filters={"defkey": MARK, "defvalue": b.business_code},
                                   pluck="parent"):
            email = str(frappe.db.get_value("User", user, "email") or user).strip().lower()
            if email not in members and user.lower() not in members:
                _unmark(user, b.business_code)
    frappe.db.commit()


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


def _refuse(e: Refused, business: str | None):
    """Recorded for whoever watches the platform's security, then the person is sent to
    the platform's own page for it (/command-center-access) -- a designed page in plain
    words, not a bare 403. What it shows travels as a one-time reference into the cache,
    never in the address, so nobody can make that page say something else or use it to
    learn which businesses the platform connects."""
    ip = getattr(frappe.local, "request_ip", None)
    frappe.log_error(title="Command Center sign-in refused",
                     message=json.dumps({"why": e.why, "detail": e.detail,
                                         "business": business, "ip": ip}))
    ref = frappe.generate_hash(length=24)
    frappe.cache().set_value(f"{ACCESS_KEY}{ref}", {"why": e.why, "business": business},
                             expires_in_sec=STATE_TTL)
    frappe.db.commit()
    _redirect(f"{ACCESS_PAGE}?ref={ref}")
