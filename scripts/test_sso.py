"""Signing in with a business's ERPNext, tested without a site and without a network.

    python3 scripts/test_sso.py

Frappe and requests are stood in for, a fake ERPNext answers the token and profile
requests, and a fake api/ingest.erp_members says who holds the access role there. What
is under test is api/sso.py's own decisions: the sign-in must have started here in this
browser and be used once; the business's ERPNext must vouch for the person; the role on
that ERPNext lets them in (an account is made for a newcomer), a pause here keeps them
out, taking the role away takes the platform away (at sign-in and in the 15-minute
sync) -- but never from a manager added by hand or an administrator, and never because
the business could not be reached. A success lands on /command-center only.
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


# Accounts on the platform. samuel came in through Gigmann's ERPNext before (marked);
# hand@ was added by hand (never marked); paused@ is disabled here; admin@ is a System
# Manager who once came in through it.
USERS, MARKS, SIGNED_OUT = {}, {}, []


def seed():
    USERS.clear()
    MARKS.clear()
    SIGNED_OUT.clear()
    USERS.update({
        "samuel@gigmann.com": {"enabled": 1, "email": "samuel@gigmann.com",
                               "roles": ["Command Center Manager"]},
        "hand@gigmann.com": {"enabled": 1, "email": "hand@gigmann.com",
                             "roles": ["Command Center Manager"]},
        "paused@gigmann.com": {"enabled": 0, "email": "paused@gigmann.com",
                               "roles": ["Command Center Manager"]},
        "admin@ultrasoft.com": {"enabled": 1, "email": "admin@ultrasoft.com",
                                "roles": ["Command Center Manager", "System Manager"]},
    })
    MARKS.update({"samuel@gigmann.com": ["gms"], "admin@ultrasoft.com": ["gms"]})


class Business:
    business_code, business_name, name = "gms", "Gigmann Medical Supplies Ltd", "Gigmann"
    site_url, sso_client_id, status, is_local = "https://erp.example.com", "cid", "Active", 0
    secret = "csecret"

    def get_password(self, field, raise_exception=False):
        return self.secret


BIZ = Business()


class _UserDoc:
    def __init__(self, name=None, data=None):
        self.name = name
        self.data = data or {}
        self.flags = types.SimpleNamespace()

    def insert(self, ignore_permissions=False):
        self.name = self.data["email"]
        USERS[self.name] = {"enabled": 1, "email": self.name, "roles": [],
                            "first_name": self.data.get("first_name")}
        return self

    def add_roles(self, *roles):
        for r in roles:
            if r not in USERS[self.name]["roles"]:
                USERS[self.name]["roles"].append(r)

    def remove_roles(self, *roles):
        USERS[self.name]["roles"] = [r for r in USERS[self.name]["roles"] if r not in roles]


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
        return u.get(fields) if u else None
    return None


def get_all(doctype, filters=None, fields=None, pluck=None, **kw):
    if doctype == "DefaultValue":
        if "parent" in filters:
            return list(MARKS.get(filters["parent"], []))
        return [u for u, codes in MARKS.items() if filters.get("defvalue") in codes]
    if doctype == "Connected Business":
        return [types.SimpleNamespace(business_code="gms", sso_client_id="cid")]
    return []


def get_doc(arg, name=None):
    if isinstance(arg, dict):
        return _UserDoc(data=arg)
    if arg == "Connected Business":
        return BIZ
    return _UserDoc(name=name)


frappe = types.ModuleType("frappe")
_cache = _Cache()
frappe.conf = {}
frappe.cache = lambda: _cache
frappe.db = types.SimpleNamespace(get_value=get_value, commit=lambda: None)
frappe.get_doc = get_doc
frappe.get_all = get_all
frappe.get_roles = lambda user: USERS.get(user, {}).get("roles", [])
frappe.defaults = types.SimpleNamespace(
    add_default=lambda key, value, parent=None: MARKS.setdefault(parent, []).append(value),
    clear_default=lambda key=None, value=None, parent=None: MARKS.__setitem__(
        parent, [v for v in MARKS.get(parent, []) if v != value]))
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
sys.modules["frappe"] = frappe
_sessions = types.ModuleType("frappe.sessions")
_sessions.clear_sessions = lambda user=None, force=False: SIGNED_OUT.append(user)
sys.modules["frappe.sessions"] = _sessions


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
_biz_mod = types.ModuleType("command_center.api.businesses")
_biz_mod.ROLE = "Command Center Manager"
sys.modules["command_center.api.businesses"] = _biz_mod

# Who holds the access role on Gigmann's ERPNext (api/ingest.erp_members).
ERP_MEMBERS = {"down": False, "asked": []}


def erp_members(code, role):
    ERP_MEMBERS["asked"].append(role)
    if ERP_MEMBERS["down"]:
        raise Exception("unreachable")
    return set(ERP_MEMBERS["who"])


_ing = types.ModuleType("command_center.api.ingest")
_ing.erp_members = erp_members
sys.modules["command_center.api.ingest"] = _ing

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
    prof = {"sub": "x", "email": ERP["email"], "name": "New Person"}
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
    SIGNED_OUT.clear()
    ERP.update({"email": "samuel@gigmann.com", "token_status": 200, "profile_status": 200,
                "profile_wrapped": False})
    ERP["posted"].clear()
    ERP_MEMBERS.update({"down": False, "who": {"samuel@gigmann.com", "new@gigmann.com",
                                               "paused@gigmann.com"}})


def begin():
    """Press the link: start() sets the state and the cookie; the browser keeps it."""
    fresh()
    sso.start(business="gms")
    state = frappe.local.cookie_manager.set[sso.COOKIE][0]
    frappe.request.cookies = {sso.COOKIE: state}
    loc = frappe.local.response.get("location", "")
    frappe.local.response = {}
    return state, loc


def refused(text=None):
    return (frappe.local.login_manager.who is None and frappe.pages
            and frappe.pages[0][2] == 403 and (text is None or text in frappe.pages[0][1]))


seed()

# 1. The link sends the person to their own ERPNext's sign-in, with this site's callback.
state, loc = begin()
check(loc.startswith("https://erp.example.com/api/method/frappe.integrations.oauth2.authorize?")
      and "client_id=cid" in loc and "state=" + state in loc
      and "platform.example.com%2Fapi%2Fmethod%2Fcommand_center.api.sso.callback" in loc,
      f"start() redirects to the business's ERPNext: {loc}")
check(frappe.local.cookie_manager.set[sso.COOKIE][1].get("httponly"), "the state cookie is httponly")

# 2. Holds the role on their ERPNext, has an account here: signed in, sent home.
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who == "samuel@gigmann.com"
      and frappe.local.response.get("location") == "/command-center",
      f"a role holder is signed in: {frappe.local.login_manager.who}, {frappe.local.response}")
check(ERP["posted"] and ERP["posted"][0][1].get("client_secret") == "csecret",
      "the code is exchanged with the client secret")
check(ERP_MEMBERS["asked"][-1] == "Executive Insights", "the access role is Executive Insights")

# 3. The same callback again is refused: a state is spent on first use.
fresh()
sso.callback(code="c1", state=state)
check(refused(), "a replayed callback is refused")
check(frappe.logged and frappe.logged[0][0] == "Command Center sign-in refused",
      "a refusal is recorded in the Error Log")

# 4. Started in another browser (cookie missing or different): refused.
state, _ = begin()
frappe.request.cookies = {}
sso.callback(code="c1", state=state)
check(refused("different browser"), "a callback without this browser's cookie is refused")

# 5. A newcomer who holds the role there: an account is made here, a manager, signed in.
state, _ = begin()
ERP["email"] = "new@gigmann.com"
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who == "new@gigmann.com"
      and "Command Center Manager" in USERS.get("new@gigmann.com", {}).get("roles", [])
      and "gms" in MARKS.get("new@gigmann.com", []),
      f"a role holder new to the platform gets an account and is signed in: {USERS.get('new@gigmann.com')}")

# 6. Without the role on their ERPNext: refused, and no account is made.
state, _ = begin()
ERP["email"] = "clerk@gigmann.com"
sso.callback(code="c1", state=state)
check(refused("does not hold the Executive Insights role") and "clerk@gigmann.com" not in USERS,
      "someone without the role there is refused, and gets no account here")

# 7. Paused here: refused, whatever their ERPNext says.
state, _ = begin()
ERP["email"] = "paused@gigmann.com"
sso.callback(code="c1", state=state)
check(refused("paused"), "an account paused on the platform stays out")

# 8. The role taken away on their ERPNext: the next sign-in is refused, and the platform
#    comes off -- the manager role, and every session.
state, _ = begin()
ERP_MEMBERS["who"] = {"new@gigmann.com"}
sso.callback(code="c1", state=state)
check(refused("does not hold"), "a role taken away there: sign-in refused")
check("Command Center Manager" not in USERS["samuel@gigmann.com"]["roles"]
      and "samuel@gigmann.com" in SIGNED_OUT,
      f"and the platform taken away: {USERS['samuel@gigmann.com']}, signed out {SIGNED_OUT}")
seed()

# 9. A manager added by hand, without the role there: refused through this link, but
#    their access here is the administrator's to change, not this sign-in's.
state, _ = begin()
ERP["email"] = "hand@gigmann.com"
sso.callback(code="c1", state=state)
check(refused("does not hold") and "Command Center Manager" in USERS["hand@gigmann.com"]["roles"],
      "a hand-added manager without the role is refused here but keeps their access")

# 10. Their ERPNext cannot be asked: fail closed, change nothing.
state, _ = begin()
ERP_MEMBERS["down"] = True
sso.callback(code="c1", state=state)
check(refused("could not check") and "Command Center Manager" in USERS["samuel@gigmann.com"]["roles"],
      "with the business unreachable, sign-in fails closed and nobody loses anything")

# 11. Email case does not matter; a wrapped profile (older Frappe) is read too.
state, _ = begin()
ERP["email"], ERP["profile_wrapped"] = "Samuel@Gigmann.com", True
sso.callback(code="c1", state=state)
check(frappe.local.login_manager.who == "samuel@gigmann.com", "email matched without regard to case")

# 12. ERPNext will not vouch (bad code, revoked client), or the sign-in was cancelled.
state, _ = begin()
ERP["token_status"] = 401
sso.callback(code="bad", state=state)
check(refused("would not confirm"), "a code ERPNext will not exchange is refused")
state, _ = begin()
sso.callback(error="access_denied", state=state)
check(refused(), "a sign-in cancelled at ERPNext is refused")

# 13. Expired (not in the cache any more): refused.
state, _ = begin()
_cache.d.clear()
sso.callback(code="c1", state=state)
check(refused("expired"), "an expired sign-in is refused")

# 14. Administrator cannot come in this way, whatever their ERPNext says.
state, _ = begin()
ERP["email"] = "Administrator"
ERP_MEMBERS["who"] = {"administrator"}
sso.callback(code="c1", state=state)
check(refused(), "Administrator cannot sign in through a business's ERPNext")

# 15. A business without sign-in set up, or unknown: refused at the start, no redirect.
fresh()
BIZ.secret = None
sso.start(business="gms")
check(not frappe.local.response.get("location") and "not set up" in frappe.pages[0][1],
      "a business with no OAuth client is refused")
BIZ.secret = "csecret"
fresh()
sso.start(business="someone-else")
check(not frappe.local.response.get("location") and frappe.pages, "an unknown business is refused")

# 16. No "return to" from the request: a success can only land on /command-center.
state, _ = begin()
sso.callback(code="c1", state=state, redirect_to="https://evil.example.com")
check(frappe.local.response.get("location") == "/command-center", "no open redirect")

# 17. The 15-minute sync: whoever lost the role there loses the platform; a System
#     Manager keeps theirs; an unreachable business changes nothing.
seed()
fresh()
ERP_MEMBERS["down"] = True
sso.sync_members()
check("Command Center Manager" in USERS["samuel@gigmann.com"]["roles"] and not SIGNED_OUT,
      "an unreachable business: the sync changes nothing")
ERP_MEMBERS.update({"down": False, "who": set()})
sso.sync_members()
check("Command Center Manager" not in USERS["samuel@gigmann.com"]["roles"]
      and "samuel@gigmann.com" in SIGNED_OUT,
      f"the sync takes the platform from someone who lost the role: {USERS['samuel@gigmann.com']}")
check("Command Center Manager" in USERS["admin@ultrasoft.com"]["roles"]
      and "admin@ultrasoft.com" not in SIGNED_OUT,
      "but never from a System Manager")
check("Command Center Manager" in USERS["hand@gigmann.com"]["roles"],
      "nor from a manager added by hand")
check(any(t == "Command Center access removed" for t, _ in frappe.logged),
      "a removal is recorded in the Error Log")

# 18. The access role can be renamed in site config.
seed()
state, _ = begin()
frappe.conf["command_center_sso_role"] = "Intelligence Layer"
sso.callback(code="c1", state=state)
check(ERP_MEMBERS["asked"][-1] == "Intelligence Layer", "the access role is a site setting")
frappe.conf.pop("command_center_sso_role")

print(f"sso: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
