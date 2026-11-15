"""The ERPNext watch: read-only security checks of every connected business's ERPNext.

Every 30 minutes (the scheduler) and on Run Checks Now, for each active business on
another site, with the platform's existing read-only service account
(connector_for(...).as_system(): the business's read key and nothing else, never a
write). Field names were checked read-only against a live v14 site (Gigmann, 15 Nov
2026); the connector leaves out any field a site's version lacks.

  server_scripts  Server Script: code that can reach the server (os., subprocess,
                  __import__, exec, eval, execute_in_shell, open( ...) -- flagged, never
                  run; an API script anyone may call without signing in; scripts new or
                  changed since the last check (API and scheduled ones rated higher).
  console         Console Log: code run in the System Console in the last 30 days.
  admins          Has Role: anyone newly holding System Manager or Administrator.
  api_keys        User.api_key: a key generated or replaced since the last check. Only a
                  fingerprint of each key is kept; the screen shows its last four
                  characters. The secret is a password field and is never read.
  logins          Activity Log (operation Login): failed sign-ins in the last 24 hours
                  (a spike, and from which addresses) and a successful sign-in from an
                  address the account had not used in the checks so far.
  users           User: system users created in the last 7 days, or enabled again.
  settings        System Settings: two-factor sign-in, the password policy and its
                  strength, the lock after failed sign-ins, sign-in by mobile number or
                  user name, error details shown to users, the session length.

A check the read account may not read is shown with a guide to the read permission it
needs (optional: nothing else depends on it). A site that does not answer is shown as
unreachable and tried again next time. The first run of a check records what is there
(the baseline) and reports only what is plainly risky or recent; later runs compare.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re

import frappe  # insights.compat
from command_center.connectors.base import (BusinessUnreachable, RemotePermissionDenied,
                                            RequestRefused)
from insights.core.security import clear_missing, finding, now

CHECK_ORDER = ("server_scripts", "console", "admins", "api_keys", "logins", "users", "settings")
CHECK_LABELS = {"server_scripts": "Server Scripts", "console": "System Console",
                "admins": "Administrator Roles", "api_keys": "API Keys",
                "logins": "Sign-Ins", "users": "New And Re-Enabled Users",
                "settings": "Password And Two-Factor Settings",
                # the platform's own (security.py)
                "admin_new_ip": "Platform Sign-Ins", "lockout_storm": "Platform Sign-Ins"}
DOCTYPES = {"server_scripts": ["Server Script"], "console": ["Console Log"],
            "admins": ["Has Role", "User"], "api_keys": ["User"], "logins": ["Activity Log"],
            "users": ["User"], "settings": ["System Settings"]}

LOOKBACK_DAYS = 7
CONSOLE_DAYS = 30
SPIKE_TOTAL, SPIKE_ONE_IP, SPIKE_CRITICAL = 20, 10, 100
ADMIN_ROLES = ("System Manager", "Administrator")

# Code that can reach the operating system, files or the interpreter itself: in a Server
# Script it is how a backdoor runs commands. Flagged, never executed.
RISKY = [
    ("os module", re.compile(r"\bos\s*\.")),
    ("subprocess", re.compile(r"\bsubprocess\b")),
    ("__import__", re.compile(r"__import__")),
    ("exec()", re.compile(r"(?<![\w.])exec\s*\(")),
    ("eval()", re.compile(r"(?<![\w.])eval\s*\(")),
    ("execute_in_shell", re.compile(r"execute_in_shell")),
    ("open()", re.compile(r"(?<![\w.])open\s*\(")),
    ("importlib", re.compile(r"\bimportlib\b")),
    ("sys module", re.compile(r"\bsys\s*\.")),
    ("interpreter internals", re.compile(r"__(builtins|globals|subclasses|class|bases|mro|code)__")),
    ("compile()", re.compile(r"(?<![\w.])compile\s*\(")),
    ("socket", re.compile(r"\bsocket\b")),
]
# Worth a look, common in ordinary scripts too.
NOTABLE = [
    ("raw SQL", re.compile(r"frappe\.db\.sql\s*\(")),
    ("acts as another user", re.compile(r"frappe\.set_user\s*\(")),
    ("skips permissions", re.compile(r"ignore_permissions")),
    ("calls out to the internet", re.compile(r"make_(post|get)_request|requests\.(get|post)")),
    ("base64", re.compile(r"base64")),
]


def scan(code: str) -> tuple[list, list]:
    """(risky, notable): each (what, line number, the line, shortened)."""
    risky, notable = [], []
    for n, line in enumerate(str(code or "").splitlines()[:5000], 1):
        if line.strip().startswith("#"):
            continue
        for label, rx in RISKY:
            if rx.search(line):
                risky.append((label, n, line.strip()[:120]))
        for label, rx in NOTABLE:
            if rx.search(line):
                notable.append((label, n, line.strip()[:120]))
    return risky, notable


def _h(v) -> str:
    return hashlib.sha256(str(v or "").encode()).hexdigest()[:16]


def _mask(key: str) -> str:
    key = str(key or "")
    return "…" + key[-4:] if len(key) > 8 else "…"


def _dt_of(v):
    if not v:
        return None
    if isinstance(v, _dt.datetime):
        return v
    try:
        return _dt.datetime.fromisoformat(str(v)[:26])
    except ValueError:
        return None


def _recent(v, days=LOOKBACK_DAYS) -> bool:
    t = _dt_of(v)
    return bool(t and now() - t < _dt.timedelta(days=days))


def _ts(v) -> str:
    return str(v or "")[:16]


# --- links into the business's ERPNext ----------------------------------------------------
class _Ctx:
    def __init__(self, b, conn, reads_as):
        self.b, self.conn, self.reads_as = b, conn, reads_as
        self.code = b.business_code
        self.admins: set = set()

    def url(self, doctype, name=None) -> str:
        """The document on the business's ERPNext (api/facts._document_url); without a
        name, the doctype's own page (a list, or a single doctype's form)."""
        from command_center.api.facts import _document_url
        sites = {self.code: (self.b.site_url or "").rstrip("/")}
        got = _document_url(sites, {"business_code": self.code, "src_doctype": doctype,
                                    "src_name": name or "x"}) or ""
        if name is None and got:
            got = got.rsplit("/", 1)[0]
        return got


# --- the checks ---------------------------------------------------------------------------
def check_server_scripts(ctx, prev, first):
    rows = ctx.conn.get_list(
        "Server Script", fields=["name", "script_type", "reference_doctype", "doctype_event",
                                 "api_method", "allow_guest", "event_frequency", "disabled",
                                 "modified", "modified_by", "owner", "creation", "script"],
        limit=500, order_by="modified desc")
    found, base = [], {}
    can_read_code = all("script" in r for r in rows)
    for r in rows:
        name = str(r.get("name"))
        on = not frappe.utils.cint(r.get("disabled"))
        kind = r.get("script_type") or ""
        code = r.get("script") or ""
        h = _h(code)
        base[name] = {"h": h, "m": str(r.get("modified") or ""), "on": on}
        url = ctx.url("Server Script", name)
        what = (f"{kind} script" + (f" on {r['reference_doctype']}" if r.get("reference_doctype") else "")
                + (f", method {r['api_method']}" if r.get("api_method") else "")
                + (f", runs {r['event_frequency']}" if r.get("event_frequency") else ""))
        common = [("Script", name), ("Type", what), ("Enabled", "Yes" if on else "No"),
                  ("Created", f"{_ts(r.get('creation'))} by {r.get('owner') or '—'}"),
                  ("Last Changed", f"{_ts(r.get('modified'))} by {r.get('modified_by') or '—'}")]
        risky, notable = scan(code)
        if risky:
            ev = common + [(f"Line {n}", f"{label}: {line}") for label, n, line in risky[:8]]
            found.append(finding(
                ctx.code, "server_scripts", f"code:{name}:{h}", "critical" if on else "medium",
                f"Server Script can reach the server: {name}",
                f"The {'enabled' if on else 'disabled'} Server Script {name} contains code "
                f"that can run system commands or read files "
                f"({', '.join(sorted({x[0] for x in risky}))}). This is how the backdoor of "
                f"October 2026 ran commands. The platform only read it; nothing was run.",
                ev, "Open the script on the business's ERPNext and confirm who wrote it and why. "
                    "If nobody can explain it, disable it at once, open an incident, check "
                    "the accounts that created or changed it, and review the server.",
                url, state=True))
        elif notable and on:
            found.append(finding(
                ctx.code, "server_scripts", f"notable:{name}:{h}", "low",
                f"Server Script worth a review: {name}",
                f"The enabled Server Script {name} uses "
                f"{', '.join(sorted({x[0] for x in notable}))}. Common in ordinary scripts, "
                f"but each should be known.",
                common + [(f"Line {n}", f"{label}: {line}") for label, n, line in notable[:6]],
                "Confirm the script is one your team knows about.", url, state=True))
        if on and kind == "API" and frappe.utils.cint(r.get("allow_guest")):
            found.append(finding(
                ctx.code, "server_scripts", f"guest:{name}", "high",
                f"Anyone can call this Server Script without signing in: {name}",
                f"The API Server Script {name} (method {r.get('api_method') or '—'}) allows "
                f"guests, so anyone on the internet can run it.", common,
                "Untick Allow Guest unless the script is meant to be public, and check what "
                "it does with what it is sent.", url, state=True))
        higher = kind in ("API", "Scheduler Event")
        before = (prev or {}).get(name)
        is_new = (not first and before is None) or (first and _recent(r.get("creation")))
        changed = (not first and before is not None and before.get("h") != h
                   and can_read_code)
        if on and is_new:
            found.append(finding(
                ctx.code, "server_scripts", f"new:{name}:{r.get('creation')}",
                "high" if higher else "medium", f"New Server Script: {name}",
                f"A new enabled {what} was created on {_ts(r.get('creation'))} by "
                f"{r.get('owner') or 'an unknown account'}.", common,
                "Confirm with whoever created it that it is expected. Scripts that run "
                "on a schedule or answer API calls deserve the closest look.", url, state=False))
        elif on and changed:
            found.append(finding(
                ctx.code, "server_scripts", f"changed:{name}:{h}",
                "high" if higher else "medium", f"Server Script changed: {name}",
                f"The code of the enabled {what} changed since the last check "
                f"(last changed {_ts(r.get('modified'))} by {r.get('modified_by') or '—'}).",
                common, "Confirm the change was expected; the script's version history on "
                        "the business's ERPNext shows what changed.", url, state=False))
    enabled = sum(1 for v in base.values() if v["on"])
    msg = f"{len(rows)} Server Script(s), {enabled} enabled."
    if rows and not can_read_code:
        msg += " Their code could not be read with this account, so it was not checked."
    return found, base, msg


def check_console(ctx, prev, first):
    since = (now() - _dt.timedelta(days=CONSOLE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    rows = ctx.conn.get_list("Console Log", fields=["name", "script", "owner", "creation"],
                             filters=[["creation", ">=", since]], limit=200,
                             order_by="creation desc")
    found = []
    for r in rows:
        name = str(r.get("name"))
        risky, _ = scan(r.get("script") or "")
        first_line = next((x.strip() for x in str(r.get("script") or "").splitlines() if x.strip()), "")
        ev = [("Entry", name), ("Run By", r.get("owner") or "—"), ("When", _ts(r.get("creation"))),
              ("First Line", first_line[:120] or "—")]
        ev += [(f"Line {n}", f"{label}: {line}") for label, n, line in risky[:6]]
        found.append(finding(
            ctx.code, "console", f"console:{name}", "critical" if risky else "high",
            f"Code was run in the System Console by {r.get('owner') or 'an unknown account'}",
            f"The System Console runs code directly on the business's ERPNext, with every "
            f"permission. Entry {name} was run on {_ts(r.get('creation'))}"
            + (f" and can reach the server ({', '.join(sorted({x[0] for x in risky}))})."
               if risky else "."),
            ev, "Confirm with the person named that they ran it and why. The System Console "
                "should be used only by the implementer, rarely.",
            ctx.url("Console Log", name), state=False))
    return found, {"seen": [str(r.get("name")) for r in rows][:200]}, \
        f"{len(rows)} System Console run(s) in the last {CONSOLE_DAYS} days."


def check_admins(ctx, prev, first):
    roles = ctx.conn.get_list("Has Role", fields=["parent", "role", "creation"],
                              filters={"parenttype": "User", "role": ["in", list(ADMIN_ROLES)]},
                              limit=1000, parent_doctype="User")
    names = sorted({str(r.get("parent")) for r in roles if r.get("parent")})
    users = {}
    if names:
        for u in ctx.conn.get_list("User", fields=["name", "full_name", "enabled", "creation",
                                                   "last_login", "last_ip"],
                                   filters={"name": ["in", names]}, limit=1000):
            users[str(u.get("name"))] = u
    holders = sorted(n for n in names if frappe.utils.cint((users.get(n) or {}).get("enabled", 1)))
    ctx.admins = set(holders)
    before = set((prev or {}).get("holders") or [])
    found = []
    for r in roles:
        n = str(r.get("parent"))
        if n not in holders or n == "Administrator":
            continue
        new = (not first and n not in before) or _recent(r.get("creation"))
        if not new:
            continue
        u = users.get(n) or {}
        found.append(finding(
            ctx.code, "admins", f"{n}:{r.get('role')}:{r.get('creation')}", "critical",
            f"New {r.get('role')}: {n}",
            f"{u.get('full_name') or n} now holds {r.get('role')} on the business's ERPNext, "
            f"which can change anything, including Server Scripts and other users.",
            [("Account", n), ("Name", u.get("full_name") or "—"), ("Role", r.get("role")),
             ("Role Given", _ts(r.get("creation"))), ("Account Created", _ts(u.get("creation"))),
             ("Last Sign-In", f"{_ts(u.get('last_login'))} from {u.get('last_ip') or '—'}")],
            "Confirm with the business's own administrator that this was intended. If not, "
            "remove the role, disable the account, and open an incident.",
            ctx.url("User", n), state=False))
    return found, {"holders": holders}, \
        f"System Manager or Administrator: {', '.join(holders) or 'nobody'}."


def check_api_keys(ctx, prev, first):
    rows = ctx.conn.get_list("User", fields=["name", "full_name", "enabled", "api_key", "modified"],
                             filters=[["api_key", "is", "set"]], limit=1000)
    if rows and not all("api_key" in r for r in rows):
        raise RemotePermissionDenied("The API key field is not readable with this account.")
    base = {}
    found = []
    for r in rows:
        n = str(r.get("name"))
        key = r.get("api_key") or ""
        if not key:
            continue
        h = _h(key)
        base[n] = h
        was = (prev or {}).get(n)
        if first or was == h:
            continue
        own = n == ctx.reads_as
        found.append(finding(
            ctx.code, "api_keys", f"{n}:{h}", "low" if own else "high",
            (f"API key {'generated' if was is None else 'replaced'} for {n}"),
            f"{r.get('full_name') or n} has a {'new' if was is None else 'replaced'} API key on "
            f"the business's ERPNext: whoever holds it and its secret can do whatever this "
            f"account may, without signing in."
            + (" This is the platform's own read account." if own else ""),
            [("Account", n), ("Key", _mask(key)), ("Account Changed", _ts(r.get("modified"))),
             ("Enabled", "Yes" if frappe.utils.cint(r.get("enabled", 1)) else "No")],
            "Confirm who generated the key and what uses it. A key nobody needs should be "
            "removed (User → API Access → Generate Keys replaces it).",
            ctx.url("User", n), state=False))
    return found, base, f"{len(base)} account(s) hold an API key: {', '.join(sorted(base)) or 'none'}."


def check_logins(ctx, prev, first):
    prev = prev or {}
    last = _dt_of(prev.get("until"))
    day = now() - _dt.timedelta(hours=24)
    fails = ctx.conn.get_list(
        "Activity Log", fields=["name", "user", "status", "ip_address", "creation"],
        filters=[["operation", "=", "Login"], ["status", "=", "Failed"],
                 ["creation", ">=", day.strftime("%Y-%m-%d %H:%M:%S")]],
        limit=5000, order_by="creation desc")
    since = (last if last and not first else now() - _dt.timedelta(days=30))
    oks = ctx.conn.get_list(
        "Activity Log", fields=["name", "user", "full_name", "ip_address", "creation"],
        filters=[["operation", "=", "Login"], ["status", "=", "Success"],
                 ["creation", ">=", since.strftime("%Y-%m-%d %H:%M:%S")]],
        limit=5000, order_by="creation asc")
    seen = {u: list(ips) for u, ips in (prev.get("ips") or {}).items()}
    found = []
    by_ip = {}
    for r in fails:
        by_ip[r.get("ip_address") or "unknown"] = by_ip.get(r.get("ip_address") or "unknown", 0) + 1
    top = sorted(by_ip.items(), key=lambda x: -x[1])
    if len(fails) >= SPIKE_TOTAL or (top and top[0][1] >= SPIKE_ONE_IP):
        accounts = sorted({str(r.get("user") or "") for r in fails})
        found.append(finding(
            ctx.code, "logins", f"spike:{now():%Y-%m-%d}",
            "critical" if len(fails) >= SPIKE_CRITICAL else "high",
            f"Failed sign-ins on the business's ERPNext: {len(fails)} in 24 hours",
            f"{len(fails)} failed sign-ins in the last 24 hours from {len(by_ip)} address(es), "
            f"against {len(accounts)} account(s).",
            [("Failed In 24 Hours", len(fails))]
            + [(f"From {ip}", n) for ip, n in top[:10]]
            + [("Accounts Tried", ", ".join(accounts[:15]) + (" …" if len(accounts) > 15 else ""))],
            "If the addresses are not your staff's, block them in the server's firewall, and "
            "make sure System Settings locks an account after a few failed attempts "
            "(Allow Consecutive Login Attempts).",
            ctx.url("Activity Log"), state=False))
    for r in oks:
        u, ip = str(r.get("user") or ""), str(r.get("ip_address") or "")
        if not u or not ip:
            continue
        known = seen.setdefault(u, [])
        if ip in known:
            continue
        if not first and known:
            admin = u in ctx.admins
            found.append(finding(
                ctx.code, "logins", f"newip:{u}:{ip}", "high" if admin else "medium",
                f"Sign-in from a new address: {u}",
                f"{r.get('full_name') or u} signed in to the business's ERPNext from {ip} on "
                f"{_ts(r.get('creation'))}, an address this account had not used before."
                + (" The account holds System Manager." if admin else ""),
                [("Account", u), ("Address", ip), ("When", _ts(r.get("creation"))),
                 ("Addresses Seen Before", ", ".join(known[-5:]))],
                "Confirm with the person that it was them (a new phone, home or travel is "
                "common). If not, reset their password and end their sessions there.",
                ctx.url("Activity Log", r.get("name")), state=False))
        known.append(ip)
        del known[:-50]
    if len(seen) > 2000:
        seen = dict(list(seen.items())[-2000:])
    msg = (f"{len(fails)} failed sign-in(s) in the last 24 hours"
           + (f", most from {top[0][0]} ({top[0][1]})" if top else "") + ".")
    return found, {"ips": seen, "until": str(now())[:19]}, msg


def check_users(ctx, prev, first):
    rows = ctx.conn.get_list("User", fields=["name", "full_name", "enabled", "user_type",
                                             "creation", "modified", "owner"],
                             filters={"user_type": "System User"}, limit=5000)
    base, found = {}, []
    for r in rows:
        n = str(r.get("name"))
        on = bool(frappe.utils.cint(r.get("enabled")))
        base[n] = on
        if n in ("Administrator", "Guest"):
            continue
        was = (prev or {}).get(n)
        common = [("Account", n), ("Name", r.get("full_name") or "—"),
                  ("Created", f"{_ts(r.get('creation'))} by {r.get('owner') or '—'}"),
                  ("Last Changed", _ts(r.get("modified")))]
        if on and ((not first and was is None) or _recent(r.get("creation"))):
            found.append(finding(
                ctx.code, "users", f"new:{n}", "medium", f"New user: {n}",
                f"{r.get('full_name') or n} was added as a system user on the business's "
                f"ERPNext on {_ts(r.get('creation'))}.", common,
                "Confirm the person is a new member of staff and has only the roles they need.",
                ctx.url("User", n), state=False))
        elif on and not first and was is False:
            found.append(finding(
                ctx.code, "users", f"enabled:{n}:{r.get('modified')}", "medium",
                f"User enabled again: {n}",
                f"{r.get('full_name') or n} had been disabled and is enabled again.", common,
                "Confirm the person is back and still needs access.",
                ctx.url("User", n), state=False))
    return found, base, f"{sum(base.values())} enabled system user(s)."


SETTINGS_RULES = [
    # field, bad when, severity, title, why, action
    ("enable_two_factor_auth", lambda v: not frappe.utils.cint(v), "medium",
     "Two-factor sign-in is off",
     "A stolen or guessed password is enough to sign in to the business's ERPNext.",
     "Switch on Two Factor Authentication in System Settings, at least for System Managers "
     "(Role → Two Factor Authentication)."),
    ("enable_password_policy", lambda v: not frappe.utils.cint(v), "medium",
     "The password policy is off", "Any password is accepted, however weak.",
     "Switch on Enable Password Policy in System Settings, with a minimum strength of 3."),
    ("minimum_password_score", lambda v: 0 < frappe.utils.cint(v) < 3, "low",
     "Weak passwords are accepted",
     "The minimum password strength is below 3 of 4.",
     "Set Minimum Password Score to 3 in System Settings."),
    ("allow_consecutive_login_attempts", lambda v: frappe.utils.cint(v) == 0, "high",
     "Accounts are never locked after failed sign-ins",
     "With no limit on consecutive failed attempts, a password can be guessed for ever.",
     "Set Allow Consecutive Login Attempts to 5 and Allow Login After Fail to 60 or more."),
    ("allow_consecutive_login_attempts", lambda v: frappe.utils.cint(v) > 10, "low",
     "Many failed sign-ins are allowed before a lock",
     "More than ten wrong passwords are allowed in a row.",
     "Set Allow Consecutive Login Attempts to 5."),
    ("allow_login_using_mobile_number", lambda v: frappe.utils.cint(v), "low",
     "Sign-in with a mobile number is allowed",
     "Mobile numbers are easier to find than email addresses, which helps password guessing.",
     "Untick Allow Login Using Mobile Number unless your staff need it."),
    ("allow_login_using_user_name", lambda v: frappe.utils.cint(v), "low",
     "Sign-in with a user name is allowed",
     "User names are often easy to guess, which helps password guessing.",
     "Untick Allow Login Using User Name unless your staff need it."),
    ("allow_error_traceback", lambda v: frappe.utils.cint(v), "low",
     "Error details are shown to users",
     "Technical error details tell an attacker about the system.",
     "Untick Show Full Error And Allow Reporting Of Issues To The Developer."),
    ("session_expiry", lambda v: _hours(v) > 24, "low", "Sessions last more than a day",
     "A computer left signed in stays signed in for a long time.",
     "Set Session Expiry to 12:00 or less."),
]


def _hours(v) -> float:
    m = re.match(r"\s*(\d+)(?::(\d+))?", str(v or ""))
    return (int(m.group(1)) + int(m.group(2) or 0) / 60) if m else 0


def check_settings(ctx, prev, first):
    doc = ctx.conn.get_doc("System Settings", "System Settings")
    if not isinstance(doc, dict) or not doc:
        raise RemotePermissionDenied("System Settings came back empty.")
    found, base = [], {}
    url = ctx.url("System Settings")
    for field, bad, sev, title, why, action in SETTINGS_RULES:
        if field not in doc:
            continue  # this version does not have it
        if field == "minimum_password_score" and not frappe.utils.cint(doc.get("enable_password_policy")):
            continue  # said already: the policy itself is off
        v = doc.get(field)
        base[field] = str(v)
        if bad(v):
            found.append(finding(
                ctx.code, "settings", f"{field}:{v}", sev, title, why,
                [("Setting", field), ("Value", v),
                 ("Settings Last Changed", f"{_ts(doc.get('modified'))} by {doc.get('modified_by') or '—'}")],
                action, url, state=True))
    return found, base, f"{len(found)} setting(s) to look at."


CHECKS = {"server_scripts": check_server_scripts, "console": check_console,
          "admins": check_admins, "api_keys": check_api_keys, "logins": check_logins,
          "users": check_users, "settings": check_settings}


def guide(check: str, business_name: str, reads_as: str | None) -> str:
    who = reads_as or "the platform's read account"
    dts = " and ".join(DOCTYPES.get(check, []))
    return (f"{business_name}'s ERPNext does not let {who} read {dts}, so this check cannot "
            f"run. It is optional: everything else on the platform works without it. To "
            f"include it, on that ERPNext open Role Permissions Manager, choose {dts}, and "
            f"add a rule giving the read account's role Read only (and Report, if offered). "
            f"Never give it Write, Create, Delete, Submit or the System Manager role: the "
            f"platform must stay read-only there. Some ERPNext versions let only System "
            f"Manager read {dts}; then leave this check off.")


# --- running ----------------------------------------------------------------------------------
def _store(code, check, status, message, baseline=None):
    from insights.core.models import SecurityCheck
    t = now()
    row, _ = SecurityCheck.objects.get_or_create(business_code=code, check_id=check)
    row.status, row.message, row.checked_at = status, message[:2000], t
    if baseline is not None:
        row.baseline = json.dumps(baseline)[:2_000_000]
        row.first_run = row.first_run or t
    row.save()


def _businesses(code=None):
    from insights.core.models import ConnectedBusiness
    q = ConnectedBusiness.objects.filter(is_local=0).exclude(status="Paused")
    if code:
        q = q.filter(business_code=code)
    return list(q.order_by("business_name"))


def run_business(b) -> dict:
    from command_center.connectors.registry import connector_for
    from insights.core.models import SecurityCheck
    code = b.business_code
    out = {"business": code, "name": b.business_name, "checks": {}, "findings": 0}
    try:
        conn = connector_for(code, "Administrator").as_system()
    except Exception as e:  # noqa: BLE001 -- no read key: said for every check
        for c in CHECK_ORDER:
            _store(code, c, "error", str(e)[:300])
            out["checks"][c] = "error"
        return out
    try:
        reads_as = conn._call("frappe.auth.get_logged_user")
    except RemotePermissionDenied:
        for c in CHECK_ORDER:
            _store(code, c, "refused", "The business's ERPNext refused the platform's read key.")
            out["checks"][c] = "refused"
        return out
    except BusinessUnreachable as e:
        if not isinstance(e, RequestRefused):
            for c in CHECK_ORDER:
                _store(code, c, "unreachable", "The business's ERPNext did not answer; the "
                                               "checks run again at the next half hour.")
                out["checks"][c] = "unreachable"
            return out
        reads_as = None
    ctx = _Ctx(b, conn, reads_as)
    stored = {r.check_id: r for r in SecurityCheck.objects.filter(business_code=code)}
    for c in CHECK_ORDER:
        row = stored.get(c)
        first = row is None or row.first_run is None
        try:
            prev = json.loads(row.baseline) if row is not None and row.baseline else None
        except ValueError:
            prev, first = None, True
        try:
            found, base, msg = CHECKS[c](ctx, prev, first)
        except RemotePermissionDenied:
            _store(code, c, "refused", guide(c, b.business_name, reads_as))
            out["checks"][c] = "refused"
            continue
        except RequestRefused as e:
            missing = " 404" in str(e) or "not found" in str(e).lower()
            _store(code, c, "unavailable" if missing else "error",
                   (f"This ERPNext has no {' or '.join(DOCTYPES[c])} to check."
                    if missing else f"The business's ERPNext refused this read: {str(e)[:300]}"))
            out["checks"][c] = "unavailable" if missing else "error"
            continue
        except BusinessUnreachable:
            for rest in CHECK_ORDER[CHECK_ORDER.index(c):]:
                _store(code, rest, "unreachable", "The business's ERPNext stopped answering; "
                                                  "the checks run again at the next half hour.")
                out["checks"][rest] = "unreachable"
            break
        except Exception:  # noqa: BLE001 -- one check's fault, recorded; the others run
            frappe.log_error(title=f"Security watch: {c} on {code}", message=frappe.get_traceback())
            _store(code, c, "error", "This check failed on the platform; it is in the error log.")
            out["checks"][c] = "error"
            continue
        clear_missing(code, c, {f.fingerprint for f in found if f.state_kind})
        _store(code, c, "ok", msg, base)
        out["checks"][c] = "ok"
        out["findings"] += len(found)
    return out


def run(business_code=None) -> list:
    out = []
    for b in _businesses(business_code):
        try:
            out.append(run_business(b))
        except Exception:  # noqa: BLE001 -- one business's fault never stops the others
            frappe.log_error(title=f"Security watch: {b.business_code}",
                             message=frappe.get_traceback())
    frappe.db.commit()
    return out


def scheduled():
    """Every 30 minutes (insights/core/management/commands/scheduler.py)."""
    run()


def summary_words(out: list) -> str:
    if not out:
        return "No connected business to check (businesses on the platform itself and paused ones are not checked)."
    parts = []
    for b in out:
        st = list(b["checks"].values())
        if st and all(s == "unreachable" for s in st):
            parts.append(f"{b['name']}: did not answer")
            continue
        ok = st.count("ok")
        refused = st.count("refused")
        parts.append(f"{b['name']}: {ok} of {len(CHECK_ORDER)} checks ran"
                     + (f", {refused} not permitted" if refused else "")
                     + f", {b['findings']} finding(s) seen")
    return "; ".join(parts) + "."


STATUS_LABELS = {"ok": "Checked", "refused": "Not Permitted", "unavailable": "Not On This Version",
                 "unreachable": "Unreachable", "error": "Failed", None: "Not Yet Run"}


def status_view() -> list:
    from insights.core.models import SecurityCheck
    rows = {(r.business_code, r.check_id): r for r in SecurityCheck.objects.all()}
    out = []
    for b in _businesses():
        checks = []
        for c in CHECK_ORDER:
            r = rows.get((b.business_code, c))
            st = r.status if r else None
            checks.append({"id": c, "label": CHECK_LABELS[c], "status": st or "pending",
                           "status_label": STATUS_LABELS.get(st, st), "message": r.message if r else
                           "The first check runs within half an hour, or press Run Checks Now.",
                           "checked_at": r.checked_at if r else None,
                           "guide": st == "refused"})
        last = max((x["checked_at"] for x in checks if x["checked_at"]), default=None)
        out.append({"business_code": b.business_code, "name": b.business_name,
                    "site_url": b.site_url, "checked_at": last, "checks": checks})
    return out
