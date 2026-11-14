"""Signing in with a business's ERPNext, tested without a site and without a network.

    python3 scripts/test_sso.py

Frappe and requests are stood in for, and a fake ERPNext answers the token and profile
requests, so what is under test is api/sso.py's own decisions: the sign-in must have
started here in this browser and be used once; the business's ERPNext must vouch for the
person; and the platform itself must already know them -- an enabled account holding
Command Center Manager. A role someone gives themselves on their own ERPNext gets them
nowhere, a refusal is recorded, and a success lands on /command-center only.
"""

from __future__ import annotations

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class _Cache:
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        return self.d.get(k)

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = v

    def delete_value(self, k):
        self.d.pop(k, None)


USERS = {
    "samuel@gigmann.com": {"enabled": 1, "user_type": "System User",
                           "roles": ["Command Center Manager"]},
    "clerk@gigmann.com": {"enabled": 1, "user_type": "System User", "roles": ["Accounts User"]},
    "gone@gigmann.com": {"enabled": 0, "user_type": "System User",
                         "roles": ["Command Center Manager"]},
}


class Business:
    business_code, business_name, name = "gms", "Gigmann Medical Supplies Ltd", "Gigmann"
    site_url, sso_client_id, status, is_local = "https://erp.example.com", "cid", "Active", 0
    secret = "csecret"

    def get_password(self, field, raise_exception=False):
        return self.secret


BIZ = Business()


def get_value(doctype, filters, fields=None, as_dict=False, **kw):
    if doctype == "Connected Business":
        f = filters
        ok = f.get("business_code") == BIZ.business_code and BIZ.is_local == f.get("is_local", 0)
        return BIZ.name if ok else None
    if doctype == "User":
        if isinstance(filters, dict):
            key = filters.get("name") or filters.get("email")
            return key if key in USERS else None
        u = USERS.get(filters)
        return {"enabled": u["enabled"], "user_type": u["user_type"]} if u else None
    return None


frappe = types.ModuleType("frappe")
_cache = _Cache()
frappe.cache = lambda: _cache
frappe.db = types.SimpleNamespace(get_value=get_value, commit=lambda: None)
frappe.get_doc = lambda dt, name: BIZ
frappe.get_roles = lambda user: USERS.get(user, {}).get("roles", [])
frappe.generate_hash = lambda length=32: "S" * length
frappe.logged = []
frappe.log_error = lambda title=None, message=None: frappe.logged.append((title, message))
frappe.get_traceback = lambda: "Traceback"
frappe.pages = []
frappe.respond_as_web_page = lambda title, msg, http_status_code=None, indicator_color=None: \
    frappe.pages.append((title, msg, http_status_code))
frappe.whitelist = lambda **kw: (lambda f: f)
frappe.utils = types.SimpleNamespace(get_url=lambda path: "https://platform.example.com" + path,
                                     add_to_date=lambda d, seconds=0: d,
                                     now_datetime=lambda: "now")
frappe.request = types.SimpleNamespace(cookies={})


class _Cookies:
    def __init__(self):
        self.set = {}

    def set_cookie(self, key, value, **kw):
        self.set[key] = (value, kw)


class _Login:
    def __init__(self):
        self.who = None

    def login_as(self, user):
        self.who = user


frappe.local = types.SimpleNamespace(response={}, cookie_manager=_Cookies(),
                                     login_manager=_Login(), request_ip="1.2.3.4")
sys.modules["frappe"] = frappe
_biz_mod = types.ModuleType("command_center.api.businesses")
_biz_mod.ROLE = "Command Center Manager"
sys.modules["command_center.api.businesses"] = _biz_mod

ERP = {"email": "samuel@gigmann.com", "token_status": 200, "profile_status": 200,
       "posted": [], "profile_wrapped": False}


class _R:
    def __init__(self, status, body):
        self.status_code, self._b, self.ok = status, body, 200 <= status < 300

    def json(self):
        return self._b


def _post(url, data=None, timeout=None):
    ERP["posted"].append((url, dict(data or {})))
    return _R(ERP["token_status"], {"access_token": "tok"} if ERP["token_status"] == 200 else {})


def _get(url, headers=None, timeout=None):
    prof = {"sub": "x", "email": ERP["email"], "roles": ["Command Center Manager"]}
    return _R(ERP["profile_status"], {"message": prof} if ERP["profile_wrapped"] else prof)


sys.modules["requests"] = types.SimpleNamespace(post=_post, get=_get)

from command_center.api import sso  # noqa: E402

passed = failed = 0


def check(ok, what):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print("FAIL:", what)


def fresh():
    frappe.local.response = {}
    frappe.local.login_manager = _Login()
    frappe.local.cookie_manager = _Cookies()
    frappe.pages.clear()
    frappe.logged.clear()
    ERP.update({"email": "samuel@gigmann.com", "token_status": 200, "profile_status": 200,
                "profile_wrapped": False})
    ERP["posted"].clear()


def begin():
    """Press the Ask AI link: start() sets the state and the cookie; the browser keeps it."""
    fresh()
    sso.start(business="gms")
    state = frappe.local.cookie_manager.set[sso.COOKIE][0]
    frappe.request.cookies = {sso.COOKIE: state}
    loc = frappe.local.response.get("location", "")
    frappe.local.response = {}
    return state, loc


# 1. The link sends the person to their own ERPNext's sign-in, with this site's callback.
state, loc = begin()
check(loc.startswith("https://erp.example.com/api/method/frappe.integrations.oauth2.authorize?")
      and "client_id=cid" in loc and "state=" + state in loc
      and "platform.example.com%2Fapi%2Fmethod%2Fcommand_center.api.sso.callback" in loc,
      f"start() redirects to the business's ERPNext: {loc}")
check(frappe.local.cookie_manager.set[sso.COOKIE][1].get("httponly"), "the state cookie is httponly")

# 2. A known manager, vouched for by ERPNext: signed in, sent to /command-center.
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who == "samuel@gigmann.com"
      and frappe.local.response.get("location") == "/command-center",
      f"a known manager is signed in: {frappe.local.login_manager.who}, {frappe.local.response}")
check(ERP["posted"] and ERP["posted"][0][1].get("client_secret") == "csecret",
      "the code is exchanged with the client secret")

# 3. The same callback again is refused: a state is spent on first use.
fresh()
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who is None and frappe.pages and frappe.pages[0][2] == 403,
      "a replayed callback is refused")
check(frappe.logged and frappe.logged[0][0] == "Command Center sign-in refused",
      "a refusal is recorded in the Error Log")

# 4. Started in another browser (cookie missing or different): refused.
state, _ = begin()
frappe.request.cookies = {}
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who is None and "different browser" in frappe.pages[0][1],
      "a callback without this browser's cookie is refused")

# 5. Someone who gave themselves a role on their ERPNext, unknown here: refused.
state, _ = begin()
ERP["email"] = "newcomer@gigmann.com"
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who is None and "has not been given access" in frappe.pages[0][1],
      "an ERPNext account the platform does not know is refused, whatever its roles there")

# 6. Known here but not a manager: refused. Disabled: refused.
state, _ = begin()
ERP["email"] = "clerk@gigmann.com"
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who is None and "not one of its managers" in frappe.pages[0][1],
      "an account here without Command Center Manager is refused")
state, _ = begin()
ERP["email"] = "gone@gigmann.com"
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who is None and "disabled" in frappe.pages[0][1],
      "a disabled account is refused")

# 7. Email case does not matter; a wrapped profile (older Frappe) is read too.
state, _ = begin()
ERP["email"], ERP["profile_wrapped"] = "Samuel@Gigmann.com", True
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who == "samuel@gigmann.com", "email matched without regard to case")

# 8. ERPNext will not vouch (bad code, revoked client): refused.
state, _ = begin()
ERP["token_status"] = 401
sso.callback(code="bad", state=state)
check(frappe.local.login_manager.who is None and "would not confirm" in frappe.pages[0][1],
      "a code ERPNext will not exchange is refused")
state, _ = begin()
sso.callback(error="access_denied", state=state)
check(frappe.local.login_manager.who is None, "a sign-in cancelled at ERPNext is refused")

# 9. Expired (not in the cache any more): refused.
state, _ = begin()
_cache.d.clear()
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who is None and "expired" in frappe.pages[0][1], "an expired sign-in is refused")

# 10. A business without sign-in set up, or unknown: refused at the start, no redirect.
fresh()
BIZ.secret = None
sso.start(business="gms")
check(not frappe.local.response.get("location") and "not set up" in frappe.pages[0][1],
      "a business with no OAuth client is refused")
BIZ.secret = "csecret"
fresh()
sso.start(business="someone-else")
check(not frappe.local.response.get("location") and frappe.pages, "an unknown business is refused")

# 11. No "return to" from the request: a success can only land on /command-center.
state, _ = begin()
sso.callback(code="c1", state=state, redirect_to="https://evil.example.com")
check(frappe.local.response.get("location") == "/command-center", "no open redirect")

print(f"sso: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
