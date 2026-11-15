"""Settings -> Security: the administrator's view of who signs in, what changed, what the
connected ERPNext sites show, and the incidents opened from any of it.

Who may use it: the platform's administrator (an active Django superuser), and nobody
else. It is never a section an administrator can give a manager (it is not in
platform_settings.GRANTS), it is absent from everyone else's boot payload, and every call
below starts with _require_admin(). The analyst has no tool that reaches it
(command_center/ask/tools.py DENIED_DOCTYPES names it, and nothing on the question path
imports this module).

  The sign-in record   every sign-in attempt on the platform, the administration and by
                       single sign-on (SecurityEvent, on "aux", append-only): success or
                       failure, the account (only when it is an account or an email
                       address -- never whatever else was typed, which may be a
                       password), the address, a summary of the browser, and whether the
                       attempt locked the account or the address. A user's first sign-in
                       from an address or a kind of browser is flagged.
  Lockouts             read from the same counters the sign-in pages use
                       (views.login_locked), so Unlock clears exactly what blocks.
  Sessions             the live Django sessions, per person, with the address and
                       browser recorded when each began; Sign Out Everywhere ends them.
  Changes              the Settings audit trail (platform_settings.changes), filtered to
                       what bears on security.
  ERPNext watch        security_watch.py: read-only checks of each connected business's
                       ERPNext every 30 minutes.
  Findings             one per fingerprint, from the watch or the sign-in record.
                       Critical ones (and an administrator signing in from a new
                       address) go to the administrators' bell, and by email when email
                       is set up, once, never again (plans.notify, deduplicated).
  Incidents            an incident register with a timeline, and a formal Incident
                       Report as a branded PDF (export.html_pdf) or the events as Excel.
                       Nothing is sent anywhere by itself.
  Server posture       what the application can know about its own settings, safely.
                       It runs no system command; a short checklist says which commands
                       the administrator can run themselves.

Countries are not shown for addresses: that would need either a third-party lookup
(sending every visitor's address away) or an offline database the platform does not
ship. The addresses are shown as they are.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import ipaddress
import json
import os
import re
import stat

import frappe  # insights.compat
from insights.compat import users as _users
from insights.compat.state import PermissionError, ValidationError, local
from insights.core.platform_settings import _audit, _name, _require_admin, _say

SEVERITIES = ("critical", "high", "medium", "low", "info")
SEV_WORDS = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low",
             "info": "Information"}
STATUS_WORDS = {"open": "Open", "acknowledged": "Acknowledged", "cleared": "Cleared"}
INCIDENT_STATUSES = ("Open", "Investigating", "Contained", "Resolved")

# Findings the administrator hears about at once, besides every critical one.
ALERT_ALSO = {"admin_new_ip"}

# Where a session remembers how it began (set at sign-in, read by sessions()).
META = "cc_sec"

# A storm: this many lockouts, or this many failed attempts, within an hour.
STORM_LOCKOUTS, STORM_FAILURES = 3, 50

# Input limits.
MAX_TITLE, MAX_TEXT, MAX_NOTE = 200, 20000, 4000
WRITES_PER_MINUTE = 60


def now() -> _dt.datetime:
    return frappe.utils.now_datetime()


def _models():
    from insights.core import models
    return models


def _me():
    return _require_admin()


def _limit_writes(me):
    """No more than WRITES_PER_MINUTE changes a minute from one administrator: a stuck
    script or a stolen session cannot fill the register."""
    from django.core.cache import cache
    key = f"sec:writes:{me.pk}:{now():%Y%m%d%H%M}"
    n = (cache.get(key) or 0) + 1
    cache.set(key, n, timeout=120)
    if n > WRITES_PER_MINUTE:
        _say("Too many changes in a minute. Wait a moment and try again.")


def _text(v, limit: int, what: str = "text") -> str:
    v = str(v or "").replace("\r\n", "\n").strip()
    if len(v) > limit:
        _say(f"The {what} is too long: at most {limit:,} characters.")
    return v


# --- the browser, in a few words ----------------------------------------------------------
def agent_summary(ua: str) -> str:
    """"Chrome on Windows", "curl" -- a summary only; the whole user-agent string is never
    kept."""
    low = str(ua or "")[:512].lower()
    if not low:
        return "Unknown"
    for key, word in (("curl/", "curl"), ("python-requests", "Python Script"),
                      ("python-urllib", "Python Script"), ("aiohttp", "Python Script"),
                      ("go-http-client", "Go Program"), ("wget", "Wget"),
                      ("postman", "Postman"), ("okhttp", "Android App"), ("bot", "Bot"),
                      ("spider", "Bot")):
        if key in low:
            return word
    browser = ("Edge" if "edg/" in low or "edge/" in low else
               "Opera" if "opr/" in low or "opera" in low else
               "Firefox" if "firefox/" in low or "fxios/" in low else
               "Chrome" if "chrome/" in low or "crios/" in low or "chromium" in low else
               "Safari" if "safari/" in low else "Browser")
    system = ("iOS" if "iphone" in low or "ipad" in low else
              "Android" if "android" in low else
              "Windows" if "windows" in low else
              "macOS" if "mac os x" in low or "macintosh" in low else
              "Linux" if "linux" in low else "Other")
    return f"{browser} on {system}"


def _account_name(typed: str) -> tuple[str, bool]:
    """What the record keeps of a typed account name: the account itself when there is
    one, an email address as typed, and otherwise only its length -- someone who types a
    password into the email box must not find it in the record."""
    from django.contrib.auth import get_user_model
    typed = str(typed or "").strip().lower()[:150]
    if not typed:
        return "", False
    U = get_user_model()
    u = U.objects.filter(username__iexact=typed).first() or \
        U.objects.filter(email__iexact=typed).first()
    if u is not None:
        return u.username, True
    if re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,100}\.[a-z0-9-]{2,24}", typed):
        return typed, False
    return f"(not an email address, {len(typed)} characters)", False


def _request_ip(request) -> str:
    from insights.core.views import _ip
    return (_ip(request) or "")[:64]


# --- the sign-in record ---------------------------------------------------------------------
def _event(**kw):
    M = _models()
    kw.setdefault("at", now())
    for k, n in (("username", 150), ("ip", 64), ("agent", 80), ("channel", 20),
                 ("actor", 150), ("note", 255)):
        if kw.get(k):
            kw[k] = str(kw[k])[:n]
    return M.SecurityEvent.objects.create(**kw)


def record_attempt(request, typed: str, outcome: str, channel: str = "platform",
                   locked: bool = False, note: str = "") -> None:
    """A failed, blocked (refused while locked) or refused sign-in. Never stops the
    sign-in page: a record that cannot be written goes to the error log."""
    try:
        from django.core.cache import cache
        ip = _request_ip(request)
        username, known = _account_name(typed)
        if outcome == "blocked":
            # One line a minute per account and address while it stays locked: a
            # script hammering a locked door must not fill the record.
            key = f"sec:blocked:{hashlib.sha256(f'{typed}|{ip}'.encode()).hexdigest()[:24]}"
            if cache.get(key):
                return
            cache.set(key, 1, timeout=60)
        _event(kind="sign_in", outcome=outcome, username=username, known_user=known, ip=ip,
               agent=agent_summary(request.META.get("HTTP_USER_AGENT")), channel=channel,
               locked=bool(locked), note=note)
        if locked or outcome == "failed":
            _storm_check()
    except Exception:  # noqa: BLE001 -- the sign-in page answers whatever happens here
        frappe.log_error(title="Security: sign-in not recorded", message=frappe.get_traceback())


def on_logged_in(sender, request=None, user=None, **kw):
    """Django's user_logged_in: every successful sign-in, whichever page or route it came
    by (the platform's page, the administration, single sign-on)."""
    if request is None or user is None or not request.META.get("REMOTE_ADDR"):
        return  # not a sign-in over the network (a test client, a command)
    try:
        M = _models()
        path = getattr(request, "path", "") or ""
        channel = "admin" if path.startswith("/admin") else "sso" if "sso" in path else "platform"
        ip = _request_ip(request)
        agent = agent_summary(request.META.get("HTTP_USER_AGENT"))
        prior = M.SecurityEvent.objects.filter(kind="sign_in", outcome="success",
                                               username=user.username)
        first = not prior.exists()
        new_ip = not prior.filter(ip=ip).exists()
        new_agent = not prior.filter(agent=agent).exists()
        ev = _event(kind="sign_in", outcome="success", username=user.username, known_user=True,
                    ip=ip, agent=agent, channel=channel, new_ip=new_ip, new_agent=new_agent,
                    first_seen=first)
        try:
            request.session[META] = {"ip": ip, "agent": agent, "at": str(ev.at)[:19],
                                     "channel": channel}
        except Exception:  # noqa: BLE001 -- a session without its note still works
            pass
        if user.is_superuser and not first and new_ip:
            finding(
                "", "admin_new_ip", f"{user.username}|{ip}", "high",
                f"Administrator signed in from a new address: {user.username}",
                f"{_name(user)} signed in to the platform from {ip} ({agent}), an address "
                f"never used by this account before.",
                [("Account", user.username), ("Address", ip), ("Browser", agent),
                 ("When", str(ev.at)[:16]), ("Route", channel.title())],
                "If this was not the administrator, use Sign Out Everywhere for this "
                "account at once, change its password, and open an incident.",
                state=False)
    except Exception:  # noqa: BLE001
        frappe.log_error(title="Security: sign-in not recorded", message=frappe.get_traceback())


def record_sign_out(request) -> None:
    u = getattr(request, "user", None)
    if u is None or not u.is_authenticated:
        return
    try:
        _event(kind="sign_out", outcome="done", username=u.username, known_user=True,
               ip=_request_ip(request), agent=agent_summary(request.META.get("HTTP_USER_AGENT")),
               channel="platform")
    except Exception:  # noqa: BLE001
        frappe.log_error(title="Security: sign-out not recorded", message=frappe.get_traceback())


def _storm_check():
    """Many lockouts or failures within the hour: one critical finding per hour."""
    M = _models()
    since = now() - _dt.timedelta(hours=1)
    rows = M.SecurityEvent.objects.filter(kind="sign_in", at__gte=since)
    locks = rows.filter(locked=True).count()
    fails = rows.filter(outcome="failed").count()
    if locks < STORM_LOCKOUTS and fails < STORM_FAILURES:
        return
    ips = list(rows.filter(outcome__in=("failed", "blocked")).values_list("ip", flat=True)
               .distinct()[:500])
    accounts = list(rows.filter(outcome__in=("failed", "blocked")).values_list(
        "username", flat=True).distinct()[:500])
    finding(
        "", "lockout_storm", f"{now():%Y-%m-%d %H}", "critical",
        "Many failed sign-ins on the platform",
        f"In the last hour: {fails} failed sign-ins and {locks} lockouts, from "
        f"{len(ips)} address(es) against {len(accounts)} account name(s).",
        [("Failed in the last hour", fails), ("Lockouts in the last hour", locks),
         ("Addresses", ", ".join(ips[:15]) + (" …" if len(ips) > 15 else "")),
         ("Accounts tried", ", ".join(accounts[:15]) + (" …" if len(accounts) > 15 else ""))],
        "Look at Failures By Address below. The limits are holding the attempts back; if "
        "one address keeps trying, block it in the server's firewall. Make sure every "
        "administrator has a long, unique password.", state=False)


# --- findings and alerts ----------------------------------------------------------------------
def fingerprint(business_code: str, check: str, key: str) -> str:
    return hashlib.sha256(f"{business_code}|{check}|{key}".encode()).hexdigest()


def finding(business_code: str, check: str, key: str, severity: str, title: str,
            detail: str, evidence: list, action: str, doc_url: str = "",
            state: bool = True):
    """Record a finding once per fingerprint; seen again, it is refreshed (and a cleared
    state finding is open again). Critical ones alert the administrators, once."""
    M = _models()
    fp = fingerprint(business_code, check, key)
    ev = json.dumps([{"label": str(a)[:80], "value": str(b)[:600]} for a, b in evidence][:30])
    t = now()
    f = M.SecurityFinding.objects.filter(fingerprint=fp).first()
    if f is None:
        f = M.SecurityFinding.objects.create(
            fingerprint=fp, business_code=business_code or "", check_id=check,
            severity=severity, title=title[:255], detail=detail[:4000], evidence=ev,
            action=action[:2000], doc_url=(doc_url or "")[:500], state_kind=state,
            status="open", first_seen=t, last_seen=t)
    else:
        f.last_seen = t
        f.detail, f.evidence, f.title = detail[:4000], ev, title[:255]
        if SEVERITIES.index(severity) < SEVERITIES.index(f.severity):
            f.severity = severity   # it got worse
        if f.status == "cleared":
            f.status, f.cleared_at = "open", None
        f.save()
    if (f.severity == "critical" or check in ALERT_ALSO) and not f.alerted:
        _alert(f)
    return f


def clear_missing(business_code: str, check: str, seen: set):
    """State findings of this check that were not seen this time are cleared."""
    M = _models()
    (M.SecurityFinding.objects.filter(business_code=business_code, check_id=check,
                                      state_kind=True, status="open")
     .exclude(fingerprint__in=list(seen)).update(status="cleared", cleared_at=now()))


def _business_names() -> dict:
    from insights.core.models import ConnectedBusiness
    return dict(ConnectedBusiness.objects.values_list("business_code", "business_name"))


def _alert(f):
    """The bell (and email when it is set up) for every active administrator, once per
    finding: the notice is keyed by the finding's fingerprint, so it is never repeated."""
    from insights.core import plans
    where = _business_names().get(f.business_code) if f.business_code else "The platform"
    title = f"Security: {f.title}"[:255]
    body = f"{where or f.business_code}. {f.detail} Recommended: {f.action}"
    try:
        plans.notify(plans._admins(), None, "security", f"security:{f.fingerprint[:48]}",
                     title, body[:2000], link="security")
    except Exception:  # noqa: BLE001 -- the finding stays on the Security screen
        frappe.log_error(title="Security: alert not sent", message=frappe.get_traceback())
        return
    _models().SecurityFinding.objects.filter(pk=f.pk).update(alerted=True)
    f.alerted = True


def _finding_row(f, names: dict, incidents: dict | None = None) -> dict:
    from insights.core import security_watch as watch
    try:
        ev = json.loads(f.evidence or "[]")
    except ValueError:
        ev = []
    return {"id": f.pk, "business_code": f.business_code,
            "business": names.get(f.business_code, f.business_code) if f.business_code
            else "The Platform",
            "check": f.check_id, "check_label": watch.CHECK_LABELS.get(f.check_id, f.check_id),
            "severity": f.severity, "severity_label": SEV_WORDS.get(f.severity, f.severity),
            "title": f.title, "detail": f.detail, "evidence": ev, "action": f.action,
            "doc_url": f.doc_url or None, "status": f.status,
            "status_label": STATUS_WORDS.get(f.status, f.status),
            "first_seen": f.first_seen, "last_seen": f.last_seen, "cleared_at": f.cleared_at,
            "acknowledged_by": f.acknowledged_by, "acknowledged_at": f.acknowledged_at,
            "alerted": f.alerted, "incidents": (incidents or {}).get(f.pk, [])}


def _incidents_by_finding() -> dict:
    out = {}
    for i in _models().SecurityIncident.objects.all().only("id", "findings"):
        for fid in _ids(i.findings):
            out.setdefault(fid, []).append(i.pk)
    return out


def _ids(text) -> list:
    try:
        return [int(x) for x in json.loads(text or "[]")]
    except (ValueError, TypeError):
        return []


# --- the screen's calls -------------------------------------------------------------------------
@frappe.whitelist()
def overview():
    """The headline counts for the top of Settings -> Security."""
    _me()
    M = _models()
    day = now() - _dt.timedelta(hours=24)
    sign = M.SecurityEvent.objects.filter(kind="sign_in", at__gte=day)
    open_f = M.SecurityFinding.objects.filter(status="open")
    by_sev = {s: open_f.filter(severity=s).count() for s in SEVERITIES}
    from insights.core.models import SecurityCheck
    last = SecurityCheck.objects.exclude(checked_at=None).order_by("-checked_at").first()
    return {"failed_24h": sign.filter(outcome__in=("failed", "blocked")).count(),
            "success_24h": sign.filter(outcome="success").count(),
            "lockouts": len(_lockouts()), "open_findings": by_sev,
            "open_incidents": M.SecurityIncident.objects.exclude(status="Resolved").count(),
            "sessions": sum(len(v["sessions"]) for v in _sessions(None)),
            "watch_checked": last.checked_at if last else None,
            "geo": "Countries are not shown: looking an address up would send it to a third "
                   "party, and the platform has no offline address database."}


@frappe.whitelist()
def sign_ins(days=7, limit=200):
    """Recent sign-in activity, failures by address and by account, current lockouts,
    and first sign-ins from a new address or browser."""
    _me()
    M = _models()
    days = max(1, min(frappe.utils.cint(days) or 7, 90))
    limit = max(1, min(frappe.utils.cint(limit) or 200, 1000))
    since = now() - _dt.timedelta(days=days)
    rows = M.SecurityEvent.objects.filter(at__gte=since)
    recent = [_event_row(e) for e in rows[:limit]]
    fails = rows.filter(kind="sign_in", outcome__in=("failed", "blocked"))
    from django.db.models import Count, Max
    by_ip = [{"ip": r["ip"], "failures": r["n"], "last": r["last"],
              "accounts": list(fails.filter(ip=r["ip"]).values_list("username", flat=True)
                               .distinct()[:5])}
             for r in fails.values("ip").annotate(n=Count("id"), last=Max("at")).order_by("-n")[:25]]
    by_account = [{"username": r["username"], "known": r["known_user"], "failures": r["n"],
                   "last": r["last"],
                   "addresses": fails.filter(username=r["username"]).values("ip").distinct().count()}
                  for r in fails.values("username", "known_user").annotate(
                      n=Count("id"), last=Max("at")).order_by("-n")[:25]]
    from django.db.models import Q
    flagged = [_event_row(e) for e in rows.filter(kind="sign_in", outcome="success").filter(
        Q(new_ip=True) | Q(new_agent=True))[:100]]
    return {"days": days, "recent": recent, "by_ip": by_ip, "by_account": by_account,
            "flagged": flagged, "lockouts": _lockouts(), "total": rows.count()}


EVENT_WORDS = {("sign_in", "success"): "Signed In", ("sign_in", "failed"): "Wrong Password",
               ("sign_in", "blocked"): "Refused While Locked",
               ("sign_in", "refused"): "Single Sign-On Refused",
               ("sign_out", "done"): "Signed Out", ("unlock", "done"): "Unlocked",
               ("end_sessions", "done"): "Signed Out Everywhere"}


def _event_row(e) -> dict:
    return {"id": e.pk, "at": e.at, "kind": e.kind, "outcome": e.outcome,
            "what": EVENT_WORDS.get((e.kind, e.outcome), e.kind.replace("_", " ").title()),
            "username": e.username, "known": e.known_user, "ip": e.ip, "agent": e.agent,
            "channel": {"platform": "Platform", "admin": "Administration",
                        "sso": "Single Sign-On"}.get(e.channel, e.channel.title()),
            "locked": e.locked, "new_ip": e.new_ip, "new_agent": e.new_agent,
            "first_seen": e.first_seen, "actor": e.actor, "note": e.note}


def _lockouts() -> list:
    """What is locked right now, read from the sign-in pages' own counters."""
    from django.core.cache import cache

    from insights.core import views
    M = _models()
    since = now() - _dt.timedelta(minutes=views.LOCK_MINUTES + 1)
    pairs = (M.SecurityEvent.objects.filter(kind="sign_in", outcome__in=("failed", "blocked"),
                                            at__gte=since)
             .values_list("username", "known_user", "ip").distinct()[:2000])
    out, seen = [], set()
    for usr, known, ip in pairs:
        # Only an account name or an email address is ever kept; anything else typed
        # cannot be locked out by account (it is no account), only by address.
        name = usr if (known or "@" in usr) and not usr.startswith("(") else None
        tests = [("ip", f"login-fail-ip:{ip}", views.LOCK_AFTER_IP, ip, None)]
        if name:
            tests += [("pair", f"login-fail:{name}:{ip}", views.LOCK_AFTER, ip, name),
                      ("account", f"login-fail-acct:{name}", views.LOCK_AFTER_ACCOUNT, None, name)]
        for kind, key, limit, a, u in tests:
            if key in seen:
                continue
            seen.add(key)
            n = cache.get(key) or 0
            if n >= limit:
                out.append({"kind": kind, "ip": a, "username": u, "failures": n,
                            "what": {"pair": f"{u} from {a}", "ip": f"Every account from {a}",
                                     "account": f"{u} from every address"}[kind],
                            "minutes": views.LOCK_MINUTES})
    order = {"account": 0, "pair": 1, "ip": 2}
    return sorted(out, key=lambda x: (order[x["kind"]], -x["failures"]))


def _valid_ip(ip) -> str:
    ip = str(ip or "").strip()[:64]
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        _say("That is not an address.")
    return ip


@frappe.whitelist(methods=["POST"])
def unlock(kind: str = "", username: str = "", ip: str = ""):
    """End a lockout now: an account from one address, one address, or one account."""
    me = _me()
    _limit_writes(me)
    from django.core.cache import cache

    from insights.core import views
    kind = str(kind or "")
    username = str(username or "").strip().lower()[:150]
    if kind not in ("pair", "ip", "account"):
        _say("Choose what to unlock.")
    keys = []
    if kind in ("pair", "ip"):
        ip = _valid_ip(ip)
    if kind in ("pair", "account") and not username:
        _say("Name the account to unlock.")
    if kind == "pair":
        keys = [f"login-fail:{username}:{ip}"]
        what = f"{username} from {ip}"
    elif kind == "ip":
        keys = [f"login-fail-ip:{ip}"]
        what = f"every account from {ip}"
    else:
        keys = [f"login-fail-acct:{username}"]
        # and the account's pairs, so the account is truly free again
        keys += [f"login-fail:{username}:{a}" for a in _models().SecurityEvent.objects.filter(
            kind="sign_in", username=username,
            at__gte=now() - _dt.timedelta(minutes=views.LOCK_MINUTES + 1))
            .values_list("ip", flat=True).distinct()[:500]]
        what = f"{username} from every address"
    for k in keys:
        cache.delete(k)
    _event(kind="unlock", outcome="done", username=username, ip=ip if kind != "account" else "",
           actor=me.username, note=f"unlocked {what}")
    _audit(f"Security: unlocked sign-in for {what}")
    return {"ok": True, "says": f"Unlocked: {what}.", "lockouts": _lockouts()}


def _sessions(me) -> list:
    """Live sessions per person. Never the session key itself (it is a credential): the
    screen gets a count and the note each session began with."""
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.models import Session
    current = None
    req = getattr(local, "request", None)
    if req is not None and getattr(req, "session", None) is not None:
        current = req.session.session_key
    per = {}
    for s in Session.objects.filter(expire_date__gt=now()).iterator():
        try:
            d = s.get_decoded()
        except Exception:  # noqa: BLE001 -- a session that cannot be read is not live
            continue
        uid = d.get("_auth_user_id")
        if not uid:
            continue
        m = d.get(META) or {}
        per.setdefault(str(uid), []).append({
            "ip": m.get("ip") or "", "agent": m.get("agent") or "Not recorded",
            "since": m.get("at"), "channel": m.get("channel") or "",
            "expires": s.expire_date, "current": s.session_key == current})
        if sum(len(v) for v in per.values()) > 20000:
            break
    users = get_user_model().objects.filter(pk__in=[int(k) for k in per if k.isdigit()])
    out = []
    for u in users:
        rows = sorted(per.get(str(u.pk), []), key=lambda r: str(r["since"] or ""), reverse=True)
        out.append({"username": u.username, "full_name": _name(u), "is_admin": u.is_superuser,
                    "active": u.is_active, "is_me": me is not None and u.pk == me.pk,
                    "sessions": rows[:50], "count": len(rows)})
    return sorted(out, key=lambda r: (-r["count"], r["full_name"].lower()))


@frappe.whitelist()
def sessions():
    me = _me()
    return _sessions(me)


@frappe.whitelist(methods=["POST"])
def sign_out_everywhere(username: str = ""):
    """End every session of a person at once. For the administrator's own account, every
    session but this one."""
    me = _me()
    _limit_writes(me)
    from django.contrib.sessions.models import Session
    u = _users._find(str(username or "").strip()[:150])
    if u is None:
        _say("There is no one with that email on the platform.")
    keep = None
    req = getattr(local, "request", None)
    if u.pk == me.pk and req is not None:
        keep = req.session.session_key
    n = 0
    for s in Session.objects.all().iterator():
        try:
            if str(s.get_decoded().get("_auth_user_id")) != str(u.pk) or s.session_key == keep:
                continue
        except Exception:  # noqa: BLE001
            continue
        s.delete()
        n += 1
    _event(kind="end_sessions", outcome="done", username=u.username, known_user=True,
           actor=me.username, ip=_request_ip(req) if req is not None else "",
           note=f"{n} session(s) ended" + (" (this one kept)" if keep else ""))
    _audit(f"Security: signed {u.username} out everywhere ({n} session(s) ended)")
    who = "your other sessions" if keep else _name(u)
    return {"ok": True, "ended": n, "says": f"Signed out {who}: {n} session(s) ended.",
            "sessions": _sessions(me)}


# --- configuration changes ------------------------------------------------------------------------
CHANGE_KINDS = [
    ("Security", re.compile(r"^Security: ")),
    ("Business Keys", re.compile(r"API key|API secret|ERPNext key|^connected .+ at |address to ")),
    ("Claude Key", re.compile(r"Claude key")),
    ("Settings Access", re.compile(r"access to Settings")),
    ("Administrators", re.compile(r"an administrator")),
    ("People", re.compile(r"^added |^deactivated |^reactivated |password|a manager|as a manager")),
    ("Email", re.compile(r"email settings|^set up email")),
    ("Branding", re.compile(r"branding|logo|display name")),
    ("Plans", re.compile(r"\bplan\b|customer|licence|Claude price")),
]


@frappe.whitelist()
def changes(limit=200):
    """The Settings audit trail, only what bears on security, newest first."""
    _me()
    from django.contrib.admin.models import LogEntry

    from insights.core.platform_settings import AUDIT_PREFIX
    limit = max(1, min(frappe.utils.cint(limit) or 200, 500))
    out = []
    for r in (LogEntry.objects.filter(change_message__startswith=AUDIT_PREFIX)
              .select_related("user").order_by("-action_time")[:3000]):
        what = r.change_message[len(AUDIT_PREFIX):]
        kind = next((k for k, rx in CHANGE_KINDS if rx.search(what)), None)
        if kind is None:
            continue
        out.append({"when": r.action_time, "who": _name(r.user) if r.user else "",
                    "what": what, "kind": kind})
        if len(out) >= limit:
            break
    return out


# --- the ERPNext watch ------------------------------------------------------------------------
@frappe.whitelist()
def watch(status: str = "", business_code: str = ""):
    """Each business's checks (and why one could not run) and the findings."""
    _me()
    from insights.core import security_watch as w
    M = _models()
    names = _business_names()
    q = M.SecurityFinding.objects.all()
    if status in ("open", "acknowledged", "cleared"):
        q = q.filter(status=status)
    if business_code:
        q = q.filter(business_code=str(business_code)[:140])
    inc = _incidents_by_finding()
    order = {s: i for i, s in enumerate(SEVERITIES)}
    rows = [_finding_row(f, names, inc) for f in q[:1000]]
    rows.sort(key=lambda r: (r["status"] != "open", order.get(r["severity"], 9),
                             -(r["first_seen"].timestamp() if r["first_seen"] else 0)))
    return {"businesses": w.status_view(), "findings": rows,
            "checks": [{"id": c, "label": w.CHECK_LABELS[c]} for c in w.CHECK_ORDER]}


@frappe.whitelist(methods=["POST"])
def run_watch(business_code: str = ""):
    """Run the checks now for one business (or all), rather than waiting for the half hour."""
    me = _me()
    _limit_writes(me)
    from django.core.cache import cache

    from insights.core import security_watch as w
    key = f"sec:run:{business_code or '__all__'}"
    if cache.get(key):
        _say("The checks ran less than two minutes ago. Wait a moment and try again.")
    cache.set(key, 1, timeout=120)
    out = w.run(business_code=str(business_code or "")[:140] or None)
    return {"ok": True, "says": w.summary_words(out), "result": out}


@frappe.whitelist(methods=["POST"])
def acknowledge(id=None):
    """The administrator has seen a finding: it leaves the open list (it stays on record)."""
    me = _me()
    _limit_writes(me)
    f = _models().SecurityFinding.objects.filter(pk=frappe.utils.cint(id)).first()
    if f is None:
        _say("There is no such finding.")
    if f.status != "acknowledged":
        f.status, f.acknowledged_by, f.acknowledged_at = "acknowledged", me.username, now()
        f.save(update_fields=["status", "acknowledged_by", "acknowledged_at"])
        _audit(f"Security: acknowledged the finding {f.title}")
    return _finding_row(f, _business_names(), _incidents_by_finding())


# --- incidents -----------------------------------------------------------------------------------
def _incident(id):
    i = _models().SecurityIncident.objects.filter(pk=frappe.utils.cint(id)).first()
    if i is None:
        _say("There is no such incident.")
    return i


def _ref(i) -> str:
    return f"INC-{i.pk:04d}"


def _codes(value) -> list:
    if isinstance(value, str):
        value = frappe.parse_json(value) if value.strip().startswith("[") else \
            [x for x in value.split(",") if x.strip()]
    known = set(_business_names())
    out = []
    for c in value or []:
        c = str(c).strip()
        if c and c not in out:
            if c not in known:
                _say("One of the businesses is not connected.")
            out.append(c)
    return out[:50]


def _note(i, by: str, kind: str, text: str):
    _models().SecurityIncidentNote.objects.create(incident=i, at=now(), by=by, kind=kind,
                                                  text=text[:MAX_NOTE])


def _incident_row(i, names=None) -> dict:
    names = names or _business_names()
    codes = json.loads(i.businesses or "[]")
    return {"id": i.pk, "ref": _ref(i), "title": i.title, "severity": i.severity,
            "severity_label": SEV_WORDS.get(i.severity, i.severity), "status": i.status,
            "businesses": codes, "business_names": [names.get(c, c) for c in codes],
            "findings": _ids(i.findings), "opened_by": i.opened_by, "opened_at": i.opened_at,
            "resolved_at": i.resolved_at, "modified": i.modified}


def _incident_full(i) -> dict:
    names = _business_names()
    out = _incident_row(i, names)
    M = _models()
    fs = M.SecurityFinding.objects.filter(pk__in=out["findings"])
    out.update({k: getattr(i, k) for k in ("summary", "impact", "actions", "root_cause",
                                            "lessons", "recommendations")})
    out["notes"] = [{"at": n.at, "by": n.by, "kind": n.kind, "text": n.text}
                    for n in i.notes.all()]
    out["finding_rows"] = [_finding_row(f, names) for f in fs]
    return out


@frappe.whitelist()
def incidents():
    _me()
    names = _business_names()
    return [_incident_row(i, names) for i in _models().SecurityIncident.objects.all()[:500]]


@frappe.whitelist()
def incident(id=None):
    _me()
    return _incident_full(_incident(id))


def _severity(v) -> str:
    v = str(v or "high").lower()
    if v not in SEVERITIES[:4]:
        _say("Choose the severity: Critical, High, Medium or Low.")
    return v


@frappe.whitelist(methods=["POST"])
def open_incident(title: str = "", severity: str = "", summary: str = "",
                  businesses=None, finding_id=None):
    """A new incident, by hand or from a finding (its title, severity and business are
    the finding's unless typed)."""
    me = _me()
    _limit_writes(me)
    M = _models()
    f = None
    if finding_id not in (None, "", 0, "0"):
        f = M.SecurityFinding.objects.filter(pk=frappe.utils.cint(finding_id)).first()
        if f is None:
            _say("There is no such finding.")
    title = _text(title or (f.title if f else ""), MAX_TITLE, "title")
    if not title:
        _say("Type the incident's title.")
    codes = _codes(businesses) if businesses not in (None, "", "[]") else (
        [f.business_code] if f and f.business_code else [])
    sev = str(severity or (f.severity if f else "high")).lower()
    sev = "low" if sev == "info" else sev
    t = now()
    i = M.SecurityIncident.objects.create(
        title=title, severity=_severity(sev),
        status="Open", businesses=json.dumps(codes), findings=json.dumps([f.pk] if f else []),
        summary=_text(summary or (f.detail if f else ""), MAX_TEXT, "summary"),
        opened_by=me.username, opened_at=t, modified=t)
    _note(i, me.username, "opened", f"Incident opened by {_name(me)}."
          + (f" From the finding: {f.title}." if f else ""))
    _audit(f"Security: opened the incident {_ref(i)} {title}")
    return _incident_full(i)


SECTIONS = ("summary", "impact", "actions", "root_cause", "lessons", "recommendations")


@frappe.whitelist(methods=["POST"])
def update_incident(id=None, title=None, severity=None, businesses=None, **sections):
    """Change the title, severity, businesses or any of the report's sections."""
    me = _me()
    _limit_writes(me)
    i = _incident(id)
    changed = []
    if title is not None:
        t = _text(title, MAX_TITLE, "title")
        if not t:
            _say("The incident needs a title.")
        if t != i.title:
            i.title = t
            changed.append("title")
    if severity is not None and _severity(severity) != i.severity:
        i.severity = _severity(severity)
        changed.append(f"severity to {SEV_WORDS[i.severity]}")
    if businesses is not None:
        codes = _codes(businesses)
        if codes != json.loads(i.businesses or "[]"):
            i.businesses = json.dumps(codes)
            changed.append("affected businesses")
    for k in SECTIONS:
        if k in sections and sections[k] is not None:
            v = _text(sections[k], MAX_TEXT, k.replace("_", " "))
            if v != getattr(i, k):
                setattr(i, k, v)
                changed.append(k.replace("_", " "))
    if not changed:
        _say("Nothing was changed.")
    i.modified = now()
    i.save()
    _note(i, me.username, "edit", "Updated: " + ", ".join(changed) + ".")
    _audit(f"Security: updated the incident {_ref(i)}: " + ", ".join(changed))
    return _incident_full(i)


@frappe.whitelist(methods=["POST"])
def set_incident_status(id=None, status: str = "", note: str = ""):
    me = _me()
    _limit_writes(me)
    i = _incident(id)
    status = str(status or "").strip().title()
    if status not in INCIDENT_STATUSES:
        _say("Choose the status: Open, Investigating, Contained or Resolved.")
    note = _text(note, MAX_NOTE, "note")
    if status == i.status:
        _say(f"The incident is {status} already.")
    if status == "Resolved" and not (i.root_cause or "").strip():
        _say("Write the root cause before marking the incident Resolved.")
    before = i.status
    i.status = status
    i.resolved_at = now() if status == "Resolved" else None
    i.modified = now()
    i.save()
    _note(i, me.username, "status", f"Status changed from {before} to {status}."
          + (f" {note}" if note else ""))
    _audit(f"Security: set the incident {_ref(i)} to {status}")
    return _incident_full(i)


@frappe.whitelist(methods=["POST"])
def add_incident_note(id=None, text: str = ""):
    me = _me()
    _limit_writes(me)
    i = _incident(id)
    text = _text(text, MAX_NOTE, "note")
    if not text:
        _say("Type the note.")
    _note(i, me.username, "note", text)
    i.modified = now()
    i.save(update_fields=["modified"])
    return _incident_full(i)


@frappe.whitelist(methods=["POST"])
def link_finding(id=None, finding_id=None):
    """Add a finding to an incident's evidence."""
    me = _me()
    _limit_writes(me)
    i = _incident(id)
    f = _models().SecurityFinding.objects.filter(pk=frappe.utils.cint(finding_id)).first()
    if f is None:
        _say("There is no such finding.")
    ids = _ids(i.findings)
    if f.pk in ids:
        _say("That finding is on this incident already.")
    ids.append(f.pk)
    i.findings = json.dumps(ids[:200])
    codes = json.loads(i.businesses or "[]")
    if f.business_code and f.business_code not in codes:
        codes.append(f.business_code)
        i.businesses = json.dumps(codes)
    i.modified = now()
    i.save()
    _note(i, me.username, "finding", f"Finding added as evidence: {f.title}.")
    return _incident_full(i)


# --- the Incident Report ------------------------------------------------------------------------
def _para(text: str) -> str:
    esc = frappe.utils.escape_html
    text = (text or "").strip()
    if not text:
        return "<p class='muted'>Not recorded.</p>"
    return "".join(f"<p>{esc(p).replace(chr(10), '<br>')}</p>" for p in re.split(r"\n\s*\n", text))


def _fmt(v) -> str:
    if not v:
        return "—"
    return str(v)[:16]


def report_html(d: dict) -> str:
    """The Incident Report's body: every value escaped here."""
    esc = frappe.utils.escape_html
    facts = [("Reference", d["ref"]), ("Severity", d["severity_label"]), ("Status", d["status"]),
             ("Opened", f"{_fmt(d['opened_at'])} by {d['opened_by']}"),
             ("Resolved", _fmt(d["resolved_at"])),
             ("Affected Businesses", ", ".join(d["business_names"]) or "The platform only")]
    out = ("<table class='facts'><tbody>"
           + "".join(f"<tr><th>{esc(a)}</th><td>{esc(str(b))}</td></tr>" for a, b in facts)
           + "</tbody></table>")
    out += "<h2>1. Summary</h2>" + _para(d["summary"])
    out += "<h2>2. Impact</h2>" + _para(d["impact"])
    out += "<h2>3. Timeline</h2>"
    if d["notes"]:
        out += ("<table><thead><tr><th>When</th><th>By</th><th>Entry</th></tr></thead><tbody>"
                + "".join(f"<tr><td class='nw'>{esc(_fmt(n['at']))}</td><td>{esc(n['by'])}</td>"
                          f"<td>{esc(n['text'])}</td></tr>" for n in d["notes"])
                + "</tbody></table>")
    else:
        out += "<p class='muted'>Not recorded.</p>"
    out += "<h2>4. Evidence</h2>"
    if d["finding_rows"]:
        for f in d["finding_rows"]:
            out += (f"<h3>{esc(f['title'])}</h3><p>{esc(f['severity_label'])} · {esc(f['business'])}"
                    f" · {esc(f['check_label'])} · first seen {esc(_fmt(f['first_seen']))}</p>"
                    f"<p>{esc(f['detail'])}</p>")
            if f["evidence"]:
                out += ("<table><tbody>" + "".join(
                    f"<tr><th>{esc(e['label'])}</th><td>{esc(e['value'])}</td></tr>"
                    for e in f["evidence"]) + "</tbody></table>")
            if f["doc_url"]:
                out += f"<p>Document: {esc(f['doc_url'])}</p>"
    else:
        out += "<p class='muted'>No findings are attached to this incident.</p>"
    out += "<h2>5. Actions Taken</h2>" + _para(d["actions"])
    out += "<h2>6. Root Cause</h2>" + _para(d["root_cause"])
    out += "<h2>7. Recommendations</h2>" + _para(d["recommendations"])
    out += "<h3>Lessons Learned</h3>" + _para(d["lessons"])
    out += ("<h2>8. Sign-Off</h2><table class='sign'><thead><tr><th>Role</th><th>Name</th>"
            "<th>Signature</th><th>Date</th></tr></thead><tbody>"
            f"<tr><td>Prepared by</td><td>{esc(d.get('prepared_by') or '')}</td><td></td><td></td></tr>"
            "<tr><td>Reviewed by</td><td></td><td></td><td></td></tr>"
            "<tr><td>Approved by</td><td></td><td></td><td></td></tr>"
            "</tbody></table>")
    return out


def _report_args(d: dict) -> dict:
    codes = d["businesses"]
    return {"business_code": codes[0] if len(codes) == 1 else None,
            "business": ", ".join(d["business_names"]) or "The platform",
            "period": f"Opened {_fmt(d['opened_at'])}"
                      + (f" · Resolved {_fmt(d['resolved_at'])}" if d["resolved_at"] else "")}


@frappe.whitelist()
def incident_pdf(id=None):
    """The formal Incident Report, as a branded PDF. Downloaded only: never sent."""
    me = _me()
    from command_center.api.export import _name as file_name
    from command_center.api.export import html_pdf
    d = _incident_full(_incident(id))
    d["prepared_by"] = _name(me)
    a = _report_args(d)
    pdf = html_pdf(f"{d['ref']} {d['title']}", report_html(d), a["business_code"],
                   footer="Confidential. Prepared for the organisation's own records; not sent "
                          "to anyone by the platform.",
                   kicker="Incident Report", business=a["business"], period=a["period"])
    frappe.local.response.filename = file_name(f"Incident Report {d['ref']}", "pdf")
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "pdf"


@frappe.whitelist()
def incident_xlsx(id=None):
    """The incident's events as a workbook: its timeline, its findings and their
    evidence, and the platform's sign-in record from a day before it opened until it
    was resolved (or now)."""
    _me()
    from command_center.api.export import _name as file_name
    from command_center.api.export import _send_xlsx
    i = _incident(id)
    d = _incident_full(i)
    start = i.opened_at - _dt.timedelta(days=1)
    for f in d["finding_rows"]:
        if f["first_seen"] and f["first_seen"] - _dt.timedelta(days=1) < start:
            start = f["first_seen"] - _dt.timedelta(days=1)
    end = i.resolved_at or now()
    timeline = [[_fmt(n["at"]), n["by"], n["kind"].title(), n["text"]] for n in d["notes"]]
    findings = []
    for f in d["finding_rows"]:
        for e in f["evidence"] or [{"label": "", "value": ""}]:
            findings.append([f["id"], f["severity_label"], f["business"], f["check_label"],
                             f["title"], _fmt(f["first_seen"]), f["status_label"],
                             e["label"], e["value"], f["doc_url"] or ""])
    ev = [[_fmt(e.at), EVENT_WORDS.get((e.kind, e.outcome), e.kind), e.username, e.ip, e.agent,
           e.channel, "Yes" if e.locked else "", "Yes" if e.new_ip else "",
           "Yes" if e.new_agent else "", e.actor, e.note]
          for e in _models().SecurityEvent.objects.filter(at__gte=start, at__lte=end)[:20000]]
    a = _report_args(d)
    _send_xlsx(f"Incident {d['ref']} Events", [
        ("Timeline", ["When", "By", "Kind", "Entry"], timeline),
        ("Findings", ["Finding", "Severity", "Business", "Check", "Title", "First Seen",
                      "Status", "Evidence", "Value", "Document"], findings),
        ("Sign-In Record", ["When", "What", "Account", "Address", "Browser", "Route", "Locked",
                            "New Address", "New Browser", "By", "Note"], ev),
    ], a["business_code"], note="Confidential: for the organisation's own records.",
        business=a["business"], period=a["period"])
    frappe.local.response.filename = file_name(f"Incident {d['ref']} Events", "xlsx")


# --- server posture ----------------------------------------------------------------------------
MANUAL_CHECKS = [
    ("Firewall allows only SSH, HTTP and HTTPS",
     "sudo ufw status verbose",
     "Expect 22, 80 and 443 allowed and everything else denied. If the firewall is "
     "inactive: sudo ufw allow 22 && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable "
     "(make sure 22 is allowed first, or the session is cut)."),
    ("Only the expected ports are listening",
     "sudo ss -tlnp",
     "The platform should listen on 127.0.0.1:8200 only (nginx in front of it). Database "
     "ports (3306) and Redis (6379, 11000-13000) should be on 127.0.0.1, never 0.0.0.0."),
    ("Failed SSH sign-ins",
     "sudo journalctl -u ssh --since '24 hours ago' | grep -c 'Failed password'",
     "Hundreds a day is common on the internet; if it is high, use SSH keys only "
     "(PasswordAuthentication no) and consider fail2ban."),
    ("Security updates are installed",
     "sudo apt list --upgradable 2>/dev/null | grep -i security",
     "Install them in a quiet hour: sudo apt upgrade."),
    ("The platform's health check",
     "./deploy/health.sh",
     "Services, errors, loads, certificates and backups, read-only."),
]


@frappe.whitelist()
def posture():
    """What the application can know about its own security settings. Read-only; it runs
    no system command."""
    _me()
    from django.conf import settings

    from insights.core import maintenance
    items = []

    def item(label, ok, value, advice=""):
        items.append({"label": label, "ok": ok, "value": value, "advice": advice if not ok else ""})

    item("Debug Mode Off", not settings.DEBUG, "Off" if not settings.DEBUG else "On",
         "Set a secret_key in insights.json (debug follows it) or \"debug\": false, then restart.")
    item("Secret Key Set", settings.SECRET_KEY != "insecure-development-key-change-me",
         "Set" if settings.SECRET_KEY != "insecure-development-key-change-me" else "Development default",
         "Put a long random secret_key in insights.json and restart.")
    item("Session Cookie HTTPS Only", bool(settings.SESSION_COOKIE_SECURE),
         "Yes" if settings.SESSION_COOKIE_SECURE else "No",
         "Set \"secure_cookies\": true in insights.json once the site is on HTTPS.")
    item("Request Token Cookie HTTPS Only", bool(settings.CSRF_COOKIE_SECURE),
         "Yes" if settings.CSRF_COOKIE_SECURE else "No",
         "Set \"secure_cookies\": true in insights.json once the site is on HTTPS.")
    item("Session Cookie Hidden From Scripts", bool(settings.SESSION_COOKIE_HTTPONLY),
         "Yes" if settings.SESSION_COOKIE_HTTPONLY else "No")
    hsts = int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0)
    req = getattr(local, "request", None)
    https = bool(req is not None and req.is_secure())
    item("HTTPS For This Page", https, "Yes" if https else "No",
         "Open the platform at its https:// address (deploy/domain.sh sets it up).")
    items.append({"label": "Strict Transport Security (HSTS)", "ok": None,
                  "value": (f"Set by the platform ({hsts} seconds)" if hsts else
                            "Set by nginx, not the platform"),
                  "advice": "deploy/domain.sh adds the Strict-Transport-Security header in "
                            "nginx. To confirm: curl -sI https://<your address> | grep -i strict"})
    hosts = list(settings.ALLOWED_HOSTS)
    item("Allowed Host Names", bool(hosts) and "*" not in hosts, ", ".join(hosts) or "None",
         "List the platform's own address in insights.json \"allowed_hosts\" instead of *.")
    item("Session Length", settings.SESSION_COOKIE_AGE <= 24 * 3600,
         f"{settings.SESSION_COOKIE_AGE // 3600} hours",
         "Set \"session_hours\" in insights.json to 12 or less.")
    item("Stored Secrets Encrypted", bool(settings.CONFIG.get("encryption_key")),
         "Yes" if settings.CONFIG.get("encryption_key") else "No encryption key",
         "deploy/platform.sh writes encryption_key into insights.json.")
    cfg = str(os.environ.get("INSIGHTS_CONFIG") or settings.CONFIG_PATH)
    try:
        mode = stat.S_IMODE(os.stat(cfg).st_mode)
        item("insights.json Readable By Its Owner Only", not (mode & 0o077), oct(mode),
             f"chmod 600 {cfg}")
    except OSError:
        item("insights.json Readable By Its Owner Only", False, "Not found",
             "The configuration file could not be found where the platform expects it.")
    newest = None
    try:
        for p in maintenance.backup_dir().glob("insights-*"):
            if p.suffix in (".gz", ".sqlite3"):
                t = _dt.datetime.fromtimestamp(p.stat().st_mtime)
                newest = t if newest is None or t > newest else newest
    except OSError:
        newest = None
    item("Backup In The Last 36 Hours",
         bool(newest and now() - newest < _dt.timedelta(hours=36)),
         str(newest)[:16] if newest else "None found",
         "The nightly backup runs at 01:45 from the scheduler (insights-scheduler). Check it "
         "is running, and see Admin → Error log for \"Platform backup\".")
    from django.contrib.auth import get_user_model
    admins = get_user_model().objects.filter(is_superuser=True, is_active=True).count()
    item("Active Administrators", admins <= 3, str(admins),
         "Keep administrator accounts to the few people who need them.")
    return {"items": items,
            "manual": [{"label": a, "command": b, "note": c} for a, b, c in MANUAL_CHECKS],
            "note": "The platform never runs system commands from the web. Run these "
                    "yourself on the server, over SSH."}
