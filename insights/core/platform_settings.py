"""The Settings screen: people, businesses, the Claude key, email and personal ERPNext keys.

Who may use it:

  the administrator   (an active Django superuser) every section, always.
  a delegate          an active manager the administrator has given one or more
                      sections, on People -> Manage -> Settings Access. Each section is
                      a Django group (GRANTS below); membership is the permission:
                        Businesses              add, edit, test, pause and reload businesses
                        People                  add managers, rename, deactivate and
                                                reactivate them, reset their passwords or
                                                email them a set-password link --
                                                never make anyone an administrator, never
                                                give Settings access, never change an
                                                administrator or anyone who has Settings
                                                access (other than their own password)
                        Personal ERPNext Keys   add, replace, test and remove the keys of
                                                managers -- not of administrators
  everyone else       refused (403), whatever the screen shows.

Security (insights/core/security.py) is the administrator's alone and can never be given.
The Claude key, Email (and its Notifications status), Branding, Customers (plans,
licences, usage and rates: insights/core/plans.py), Recommendations, the Changes list
and giving Settings access stay with the administrator. A business's own
co-brand (the name and logo its documents are prepared for) and its Report Style
(Platform Branding, Client Branding or Client Letterhead, with the letterhead's images)
are part of Businesses -- except hiding the vendor's credit, which only the
administrator may choose (it is the owner's own marketing).
Every call starts with _require(section)
or _require_admin(); the boot payload's settings_sections (sections_for) tells the
screen which sections to show.

What is never returned by any call here: a password (a person's or the mail server's),
a business's API secret, a person's ERPNext secret, the Claude key. Secrets are
write-only: each is stored encrypted (insights.compat.documents.set_password) or in
insights.json (the Claude key, the mail password), and the screen is told only whether
one is set, and its last four characters.

Every change made here is written to Django's admin log (LogEntry), as who, when and
what -- never a secret's value -- and shown under Changes on the screen and in the
administration's Recent actions.

The Django administration (/admin) keeps working alongside; this is the everyday path.
"""

from __future__ import annotations

import frappe  # insights.compat
from command_center import branding
from insights.compat import users as _users
from insights.compat.state import PermissionError, ValidationError, local

MANAGER = "Insights Dashboard Manager"  # command_center.api.businesses.ROLE
AUDIT_PREFIX = "Settings: "
RELOAD_KEY = "cc:settings:reload:{}"


# --- who may ---------------------------------------------------------------------------
# The sections an administrator can give a manager, each a Django group.
GRANTS = {"businesses": "Settings: Businesses", "people": "Settings: People",
          "keys": "Settings: Personal Keys"}
GRANT_WORDS = {"businesses": "Businesses", "people": "User Management", "keys": "ERPNext API Keys"}
# What the administrator sees, in the screen's order.
ALL_SECTIONS = ["people", "businesses", "customers", "claude", "email", "branding", "keys",
                "recommend", "changes", "security"]


def _grants(u) -> list:
    """The sections given to this person (whether or not they can use them now)."""
    have = {g.name for g in u.groups.all()}
    return [k for k, g in GRANTS.items() if g in have]


def sections_for(user) -> list:
    """The Settings sections this person may open: all of them for an active
    administrator; their given ones for an active manager; none for anyone else."""
    u = _users._find(user) if isinstance(user, str) else user
    if u is None or not u.is_active:
        return []
    if u.is_superuser:
        return list(ALL_SECTIONS)
    if not u.groups.filter(name=MANAGER).exists():
        return []
    return _grants(u)


def _require_admin():
    """The signed-in person, if they are an active platform administrator."""
    u = _users._find(local.user)
    if u is None or not u.is_active or not u.is_superuser:
        raise PermissionError("Only the platform's administrator can do this.")
    return u


def _require(*sections):
    """The signed-in person, if they are the administrator or have been given any of
    `sections`."""
    u = _users._find(local.user)
    if u is not None and u.is_active and u.is_superuser:
        return u
    mine = sections_for(u) if u is not None else []
    if not any(s in mine for s in sections):
        raise PermissionError("This part of Settings is for the platform's administrator, "
                              "or for someone they have given access to it.")
    return u


def _protected(u) -> bool:
    """An administrator, or someone with Settings access: only the administrator may
    change them (so no delegate can reach more than they were given)."""
    return bool(u.is_superuser) or bool(_grants(u))


def _may_change(me, u, own_password: bool = False):
    """A delegate may change managers only -- not an administrator, not someone with
    Settings access, and not themselves (except their own password)."""
    if me.is_superuser:
        return
    if u.pk == me.pk:
        if own_password:
            return
        raise PermissionError("You cannot change your own access. Ask the platform's "
                              "administrator.")
    if u.is_superuser:
        raise PermissionError("Only the platform's administrator can change an administrator.")
    if _grants(u):
        raise PermissionError("Only the platform's administrator can change someone who has "
                              "access to Settings.")


def _say(msg: str):
    """A refusal in plain words, shown on the screen as it is."""
    raise ValidationError(msg)


# --- the audit trail ------------------------------------------------------------------
def _audit(what: str, obj=None, flag: int = 2):
    """One line in Django's admin log: who (the signed-in administrator), when (now),
    what (`what`, which never carries a secret's value)."""
    from django.contrib.admin.models import LogEntry
    from django.contrib.contenttypes.models import ContentType
    actor = _users._find(local.user)
    if actor is None:
        return
    ct = ContentType.objects.get_for_model(obj.__class__) if obj is not None else None
    LogEntry.objects.create(
        user_id=actor.pk, content_type=ct,
        object_id=str(obj.pk) if obj is not None else None,
        object_repr=str(obj)[:200] if obj is not None else "Platform settings",
        action_flag=flag, change_message=(AUDIT_PREFIX + what)[:2000])


@frappe.whitelist()
def changes(limit: int = 50):
    """The latest changes made from Settings, newest first."""
    _require_admin()
    from django.contrib.admin.models import LogEntry
    rows = (LogEntry.objects.filter(change_message__startswith=AUDIT_PREFIX)
            .select_related("user").order_by("-action_time")[:max(1, min(int(limit or 50), 500))])
    return [{"when": r.action_time, "who": _name(r.user),
             "what": r.change_message[len(AUDIT_PREFIX):]} for r in rows]


# --- people ----------------------------------------------------------------------------
def _User():
    from django.contrib.auth import get_user_model
    return get_user_model()


def _name(u) -> str:
    return (f"{u.first_name} {u.last_name}".strip()) or u.username


def _person(u, me) -> dict:
    return {"username": u.username, "email": u.email or u.username, "full_name": _name(u),
            "is_manager": any(g.name == MANAGER for g in u.groups.all()),
            "is_admin": bool(u.is_superuser), "active": bool(u.is_active),
            "has_password": u.has_usable_password(), "last_login": u.last_login,
            "joined": u.date_joined, "is_me": u.pk == me.pk,
            "settings_access": _grants(u), "protected": _protected(u),
            "customers": _customers_of(u)}


def _customers_of(u) -> list:
    """The customers (insights/core/plans.py) whose seat this person takes."""
    if u.is_superuser:
        return []
    from insights.core import plans
    return [c.name for c, _ in plans.clients_for_user(u.username)]


def _get_person(username: str):
    u = _users._find(str(username or "").strip())
    if u is None:
        _say("There is no one with that email on the platform.")
    return u


def _active_admins() -> int:
    return _User().objects.filter(is_superuser=True, is_active=True).count()


def _check_password(password, password2, user) -> str:
    """The password, if it is acceptable; otherwise Django's validators' own sentences."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError
    password = str(password or "")
    if not password:
        _say("Type the password, or choose to set it later.")
    if password != str(password2 or ""):
        _say("The two passwords are not the same.")
    try:
        validate_password(password, user=user)
    except DjangoValidationError as e:
        _say(" ".join(e.messages))
    return password


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


@frappe.whitelist()
def people():
    me = _require("people", "keys")
    rows = _User().objects.prefetch_related("groups").order_by("first_name", "last_name", "username")
    return [_person(u, me) for u in rows]


@frappe.whitelist(methods=["POST"])
def add_person(email: str = "", full_name: str = "", password: str = "", password2: str = "",
               set_later=0, manager=1, admin=0, client_id=None, override_seats=0, invite=0):
    """A new person. They sign in with their email and the password typed here, or -- if
    it is to be set later -- with their business's ERPNext, until a password is set.
    invite: no password; they are emailed a link to set their own (insights/core/invite.py).
    The person is added whether or not the email goes: the answer's "invite" says which,
    so the screen can offer to set a password instead.
    Only the administrator can add an administrator.

    client_id: the customer (insights/core/plans.py) whose seat they take. A delegate's
    new people always go on the delegate's own customer. Beyond the customer's seats
    they are refused, unless the administrator overrides (override_seats)."""
    me = _require("people")
    if _truthy(admin) and not me.is_superuser:
        raise PermissionError("Only the platform's administrator can make someone an "
                              "administrator.")
    seat = _seat_customer(me, client_id, _truthy(admin))
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.core.validators import validate_email
    email = str(email or "").strip().lower()
    try:
        validate_email(email)
    except DjangoValidationError:
        _say("That is not an email address.")
    U = _User()
    if U.objects.filter(username__iexact=email).exists() or U.objects.filter(email__iexact=email).exists():
        _say(f"{email} is already on the platform.")
    first, _, last = str(full_name or "").strip().partition(" ")
    u = U(username=email, email=email, first_name=first[:150], last_name=last.strip()[:150])
    invite = _truthy(invite)
    if _truthy(set_later) or invite:
        u.set_unusable_password()
    else:
        u.set_password(_check_password(password, password2, u))
    u.is_superuser = u.is_staff = _truthy(admin)
    if seat is not None:
        from insights.core import plans
        plans.check_seat(seat, None, _truthy(override_seats), me)
    u.save()
    if _truthy(manager):
        from django.contrib.auth.models import Group
        u.groups.add(Group.objects.get_or_create(name=MANAGER)[0])
    if seat is not None:
        plans.add_member(seat, u.username, "user")
        _audit(f"named {email} on the customer {seat.name}", u)
    roles = [r for r, on in (("manager", _truthy(manager)), ("administrator", _truthy(admin))) if on]
    _audit(f"added {email}" + (f" as {' and '.join(roles)}" if roles else "")
           + ("; to set their own password by email link" if invite else
              "; password to be set later" if _truthy(set_later) else "; password set"), u, flag=1)
    out = _person(u, me)
    if invite:
        out["invite"] = _send_link(me, u, new=True)
    return out


def _seat_customer(me, client_id, admin: bool):
    """The customer a new person's seat is on: the one the administrator chose, or the
    delegate's own (their only customer). None: no customer, no seat to count."""
    from insights.core import plans
    if admin:
        return None
    if me.is_superuser:
        return plans._client(client_id) if client_id not in (None, "", 0, "0") else None
    mine = plans.clients_for_user(me.username)
    if client_id not in (None, "", 0, "0"):
        for c, _ in mine:
            if str(c.pk) == str(client_id):
                return c
        raise PermissionError("You can add people only to your own organisation.")
    return mine[0][0] if mine else None


@frappe.whitelist(methods=["POST"])
def update_person(username: str = "", full_name: str = ""):
    me = _require("people")
    u = _get_person(username)
    _may_change(me, u)
    first, _, last = str(full_name or "").strip().partition(" ")
    if not first:
        _say("Type the person's name.")
    u.first_name, u.last_name = first[:150], last.strip()[:150]
    u.save(update_fields=["first_name", "last_name"])
    _audit(f"renamed {u.username} to {_name(u)}", u)
    return _person(u, me)


@frappe.whitelist(methods=["POST"])
def set_manager(username: str = "", on=1):
    """Make or unmake a manager. Someone who stops being a manager loses any Settings
    access too, so it does not come back by itself if they are made a manager again."""
    me = _require("people")
    from django.contrib.auth.models import Group
    u = _get_person(username)
    _may_change(me, u)
    g = Group.objects.get_or_create(name=MANAGER)[0]
    if _truthy(on):
        u.groups.add(g)
    else:
        u.groups.remove(g)
    _audit(f"{'made' if _truthy(on) else 'removed'} {u.username} "
           f"{'a manager' if _truthy(on) else 'as a manager'}", u)
    if not _truthy(on) and _grants(u):
        _set_grants(u, [])
    return _person(u, me)


@frappe.whitelist(methods=["POST"])
def set_admin(username: str = "", on=1):
    me = _require_admin()
    u = _get_person(username)
    if _truthy(on):
        u.is_superuser = u.is_staff = True
    else:
        if u.pk == me.pk:
            _say("You cannot remove yourself as an administrator. Ask another administrator.")
        if u.is_superuser and u.is_active and _active_admins() <= 1:
            _say("This is the last active administrator. Make someone else an "
                 "administrator first.")
        u.is_superuser = u.is_staff = False
    u.save(update_fields=["is_superuser", "is_staff"])
    _audit(f"{'made' if _truthy(on) else 'removed'} {u.username} "
           f"{'an administrator' if _truthy(on) else 'as an administrator'}", u)
    return _person(u, me)


@frappe.whitelist(methods=["POST"])
def set_active(username: str = "", on=1, override_seats=0):
    """Deactivate (their sign-ins end at once and they cannot sign in again) or reactivate
    -- which takes a seat again on their customer, refused beyond its seats unless the
    administrator overrides."""
    me = _require("people")
    u = _get_person(username)
    _may_change(me, u)
    if _truthy(on):
        if not u.is_active and not u.is_superuser:
            from insights.core import plans
            for c in plans.seat_clients_of(u.username):
                plans.check_seat(c, None, _truthy(override_seats), me)
        u.is_active = True
        u.save(update_fields=["is_active"])
    else:
        if u.pk == me.pk:
            _say("You cannot deactivate yourself. Ask another administrator.")
        if u.is_superuser and u.is_active and _active_admins() <= 1:
            _say("This is the last active administrator. Make someone else an "
                 "administrator first.")
        u.is_active = False
        u.save(update_fields=["is_active"])
        _users.clear_sessions(user=u.username)
    _audit(f"{'reactivated' if _truthy(on) else 'deactivated'} {u.username}", u)
    return _person(u, me)


@frappe.whitelist(methods=["POST"])
def reset_password(username: str = "", password: str = "", password2: str = "", set_later=0):
    """A new password for someone (or none, to be set later). Their other sign-ins end."""
    me = _require("people")
    u = _get_person(username)
    _may_change(me, u, own_password=True)
    if _truthy(set_later):
        if u.pk == me.pk:
            _say("You cannot remove your own password: you would not be able to sign in.")
        u.set_unusable_password()
    else:
        u.set_password(_check_password(password, password2, u))
    u.save(update_fields=["password"])
    if u.pk == me.pk:
        req = getattr(local, "request", None)
        if req is not None:
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(req, u)
    else:
        _users.clear_sessions(user=u.username)
    _audit(f"{'cleared the password of' if _truthy(set_later) else 'set a new password for'} "
           f"{u.username}", u)
    return _person(u, me)


def _send_link(me, u, new: bool = False) -> dict:
    from insights.core import invite as _invite
    out = _invite.send(u, me, new=new)
    _audit(f"{'sent' if out['ok'] else 'could not send'} a set-password link to {u.username}", u)
    return out


@frappe.whitelist(methods=["POST"])
def send_set_password_link(username: str = ""):
    """Email someone a link to set their own password (also how a forgotten one is
    handled). The same rules as reset_password: a delegate may send it to managers only,
    never to an administrator or anyone with Settings access. Their current password
    keeps working until they use the link. {"ok", "says", "person"}."""
    me = _require("people")
    u = _get_person(username)
    _may_change(me, u, own_password=True)
    if not u.is_active:
        _say(f"{_name(u)} is deactivated. Reactivate them first.")
    return {**_send_link(me, u), "person": _person(u, me)}


# --- Settings access ------------------------------------------------------------------
def _set_grants(u, sections: list) -> list:
    """Give exactly `sections`; each one given or taken away is a line in the audit."""
    from django.contrib.auth.models import Group
    had = set(_grants(u))
    want = set(sections)
    for k in GRANTS:
        if k in want and k not in had:
            u.groups.add(Group.objects.get_or_create(name=GRANTS[k])[0])
            _audit(f"gave {u.username} access to Settings: {GRANT_WORDS[k]}", u)
        elif k in had and k not in want:
            g = Group.objects.filter(name=GRANTS[k]).first()
            if g is not None:
                u.groups.remove(g)
            _audit(f"took away {u.username}'s access to Settings: {GRANT_WORDS[k]}", u)
    return [k for k in GRANTS if k in want]


@frappe.whitelist(methods=["POST"])
def set_settings_access(username: str = "", sections=None):
    """Which Settings sections a manager may open (Businesses, People, Personal ERPNext
    Keys). Administrator only; an administrator has them all already."""
    me = _require_admin()
    u = _get_person(username)
    if isinstance(sections, str):
        sections = frappe.parse_json(sections) if sections.strip().startswith("[") else \
            [x for x in sections.split(",") if x.strip()]
    wanted = [str(x).strip() for x in (sections or [])]
    unknown = [x for x in wanted if x not in GRANTS]
    if unknown:
        _say("Only Businesses, User Management and ERPNext API Keys can be given.")
    if u.is_superuser:
        _say(f"{_name(u)} is an administrator and can open all of Settings already.")
    if wanted and not u.is_active:
        _say(f"{_name(u)} is deactivated. Reactivate them first.")
    if wanted and not u.groups.filter(name=MANAGER).exists():
        _say(f"{_name(u)} is not a manager. Make them a manager first.")
    before = _grants(u)
    _set_grants(u, wanted)
    if set(before) == set(wanted):
        _say("Nothing was changed.")
    u = _get_person(u.username)
    return _person(u, me)


# --- businesses ------------------------------------------------------------------------
def _mask(value: str | None, keep: int = 4) -> str | None:
    value = str(value or "")
    if not value:
        return None
    if len(value) <= keep * 2:
        return "…" + value[-2:] if len(value) > 2 else "…"
    return "…" + value[-keep:]


def _business_model():
    from insights.core.models import ConnectedBusiness
    return ConnectedBusiness


def _get_business(name: str):
    b = _business_model().objects.filter(pk=str(name or "")).first()
    if b is None:
        _say("There is no connected business by that name.")
    return b


def _check_url(site_url: str) -> str:
    url = str(site_url or "").strip().rstrip("/")
    if not url.startswith(("https://", "http://")) or " " in url or len(url) < 10:
        _say("The ERPNext address should be the site's full address, starting with "
             "https:// (for example https://erp.example.com).")
    return url


def _has_secret(doctype, name, field="api_secret") -> bool:
    from insights.core.models import Secret
    return Secret.objects.filter(doctype=doctype, docname=name, fieldname=field).exists()


def _reload_state(code: str) -> dict | None:
    return frappe.cache().get_value(RELOAD_KEY.format(code))


def _loading(code: str) -> bool:
    """A load of this business is running now (ingest.business_lock holds its lock)."""
    return bool(frappe.cache().get_value(f"lock:cc:ingest:{code}"))


def _business_row(b) -> dict:
    from django.db.models import Count, Max, Q

    from command_center.ingest.registry import INGESTORS
    from insights.core.models import CommandCenterIngestState
    st = CommandCenterIngestState.objects.filter(business_code=b.business_code).aggregate(
        last=Max("last_run"), failed=Count("pk", filter=Q(status="Failed")),
        ok=Count("pk", filter=Q(status="OK")))
    reload = _reload_state(b.business_code)
    if reload and reload.get("state") in ("queued", "running"):
        started = reload.get("started")
        done = CommandCenterIngestState.objects.filter(
            business_code=b.business_code, last_run__gte=started).count() if started else 0
        reload = {**reload, "done": done, "total": len(INGESTORS)}
    return {"name": b.pk, "business_name": b.business_name, "business_code": b.business_code,
            "site_url": b.site_url, "status": b.status or "Active", "currency": b.currency,
            "erpnext_company": b.erpnext_company, "is_local": bool(b.is_local),
            "api_key": _mask(b.api_key), "has_secret": _has_secret("Connected Business", b.pk),
            "last_load": st["last"], "facts_ok": st["ok"], "facts_failed": st["failed"],
            "facts_total": len(INGESTORS), "last_sync": b.last_sync,
            "last_error": (b.last_error or "")[:300], "loading": _loading(b.business_code),
            "reload": reload, **_client_brand(b.business_code)}


@frappe.whitelist()
def businesses():
    _require("businesses", "keys")
    return [_business_row(b) for b in _business_model().objects.order_by("business_name")]


def _access(code: str) -> dict:
    """check_access, summed up for the screen: who it reads as, what it can read, and
    whether it can change anything (it must not)."""
    from command_center.api import ingest
    out = ingest.check_access(business_code=code)
    readable = [r["doctype"] for r in out["checked"] if r["readable"]]
    return {"reads_as": out.get("reads_as"), "roles": out.get("roles"),
            "readable": readable, "unreadable": out.get("unreadable") or [],
            "total": len(out["checked"]), "read_only": out.get("read_only"),
            "write_capable_roles": out.get("write_capable_roles") or []}


def _plain_failure(e: Exception) -> str:
    from command_center.connectors.base import (BusinessUnreachable,
                                                RemotePermissionDenied)
    if isinstance(e, RemotePermissionDenied):
        return ("The business's ERPNext refused the key and secret. Check them on that "
                "site (the user's API access) and try again.")
    if isinstance(e, BusinessUnreachable):
        return f"The business's ERPNext did not answer: {str(e)[:300]}"
    return f"It could not be reached: {str(e)[:300] or type(e).__name__}"


def _ping(b) -> tuple[bool, str | None, str | None]:
    """One quick request with the business's service key: who it reads as, or why not.
    Direct and short (no retries), so a wrong address fails in seconds, not minutes."""
    import requests
    secret = frappe.get_doc("Connected Business", b.pk).get_password("api_secret",
                                                                    raise_exception=False)
    if not (b.site_url and b.api_key and secret):
        return False, None, "Its ERPNext address, API key or API secret is missing."
    try:
        r = requests.get(f"{b.site_url.rstrip('/')}/api/method/frappe.auth.get_logged_user",
                         headers={"Authorization": f"token {b.api_key}:{secret}",
                                  "Accept": "application/json"}, timeout=10)
    except requests.RequestException as e:
        return False, None, f"The business's ERPNext did not answer ({type(e).__name__})."
    if r.status_code in (401, 403):
        return False, None, ("The business's ERPNext refused the key and secret. Check them "
                             "on that site (the user's API access).")
    if not r.ok:
        return False, None, f"The business's ERPNext answered with an error (HTTP {r.status_code})."
    try:
        who = r.json().get("message")
    except ValueError:
        return False, None, "Something answered at that address, but it is not an ERPNext site."
    return True, who, None


@frappe.whitelist(methods=["POST"])
def add_business(business_name: str = "", site_url: str = "", api_key: str = "",
                 api_secret: str = "", erpnext_company: str = ""):
    """Connect a business: registered (install.register_business, which reads its
    company and currency), then its access checked. If its ERPNext cannot be reached
    with what was typed, nothing is kept."""
    _require("businesses")
    name = str(business_name or "").strip()
    if not name:
        _say("Type the business's name.")
    url = _check_url(site_url)
    api_key, api_secret = str(api_key or "").strip(), str(api_secret or "").strip()
    if not api_key or not api_secret:
        _say("Type both the API key and the API secret of the business's read-only "
             "ERPNext user.")
    B = _business_model()
    code = frappe.scrub(name)[:40]
    if B.objects.filter(pk=name).exists() or B.objects.filter(business_name__iexact=name).exists():
        _say(f"{name} is connected already. Use Edit to change its address or key.")
    if B.objects.filter(business_code=code).exists():
        _say("A business with a very similar name is connected already. Choose another name.")

    from command_center import install
    try:
        out = install.register_business(name, url, api_key, api_secret,
                                        erpnext_company=str(erpnext_company or "").strip() or None)
    except Exception as e:  # noqa: BLE001 -- said in words; the half-made record is removed
        why = _plain_failure(e)
        if B.objects.filter(pk=name).exists():
            frappe.delete_doc("Connected Business", name, force=True)
        frappe.db.commit()
        _say(f"{name} was not connected. {why}")
    b = _get_business(out["business"])
    _audit(f"connected {name} at {url}", b, flag=1)
    return {"business": _business_row(b), "reads_as": out.get("reads_as"),
            "company": out.get("company"), "currency": out.get("currency"),
            "access": _access(b.business_code)}


@frappe.whitelist(methods=["POST"])
def update_business(name: str = "", site_url: str = "", api_key: str = "",
                    api_secret: str = "", erpnext_company: str = ""):
    """Change a business's address, key or secret. A blank key or secret keeps the
    current one; the secret is never shown back."""
    _require("businesses")
    b = _get_business(name)
    if b.is_local:
        _say("This business's data is on the platform itself; it has no address or key.")
    doc = frappe.get_doc("Connected Business", b.pk)
    changed = []
    url = _check_url(site_url) if str(site_url or "").strip() else None
    if url and url != (doc.site_url or ""):
        doc.site_url = url
        changed.append(f"address to {url}")
    if str(api_key or "").strip() and str(api_key).strip() != (doc.api_key or ""):
        doc.api_key = str(api_key).strip()
        changed.append("API key")
    if str(api_secret or "").strip():
        doc.api_secret = str(api_secret).strip()
        changed.append("API secret")
    company = str(erpnext_company or "").strip()
    if company and company != (doc.erpnext_company or ""):
        doc.erpnext_company = company
        changed.append(f"company to {company}")
    if not changed:
        _say("Nothing was changed.")
    doc.save(ignore_permissions=True)
    _audit(f"changed {b.business_name}: " + ", ".join(changed), b)
    return _business_row(_get_business(b.pk))


@frappe.whitelist(methods=["POST"])
def test_business(name: str = ""):
    """Can the platform read this business with its key, and is that key read-only?"""
    _require("businesses")
    b = _get_business(name)
    if b.is_local:
        return {"ok": True, "says": "This business's data is on the platform itself."}
    ok, who, why = _ping(b)
    if not ok:
        return {"ok": False, "says": why}
    access = _access(b.business_code)
    if b.status == "Unreachable":
        frappe.db.set_value("Connected Business", b.pk, {"status": "Active", "last_error": ""},
                            update_modified=False)
    return {"ok": True, "says": f"Connected. It reads as {who}.", "access": access}


@frappe.whitelist(methods=["POST"])
def check_figures(name: str = ""):
    """Check Figures: what the platform holds for this business, line by line, against
    what its ERPNext says right now (command_center/api/audit.py). Reads only."""
    _require("businesses")
    b = _get_business(name)
    from command_center.api import audit
    try:
        return audit.figures(b.business_code)
    except Exception as e:  # noqa: BLE001 -- said on the screen, recorded in the log
        frappe.log_error(title=f"Settings: check figures of {b.business_code}",
                         message=frappe.get_traceback())
        _say(f"The figures could not be checked just now: {_plain_failure(e)}")


@frappe.whitelist(methods=["POST"])
def set_paused(name: str = "", paused=1):
    """Pause (no loads, not offered on the screens) or resume a business."""
    _require("businesses")
    b = _get_business(name)
    status = "Paused" if _truthy(paused) else "Active"
    frappe.db.set_value("Connected Business", b.pk, "status", status)
    _audit(f"{'paused' if status == 'Paused' else 'resumed'} {b.business_name}", b)
    return _business_row(_get_business(b.pk))


def _reload_job(code: str, key: str):
    """The background half of Reload Everything: a full load of one business."""
    from command_center.api import ingest
    state = frappe.cache().get_value(key) or {}
    frappe.cache().set_value(key, {**state, "state": "running"}, expires_in_sec=86400)
    try:
        out = ingest.run(business_code=code, full=True)
        failed = [x["fact"] for x in out.get("loaded", []) if x.get("failed")]
        frappe.cache().set_value(key, {**state, "state": "failed" if failed else "done",
                                       "finished": frappe.utils.now_datetime(),
                                       "error": ("Some records did not load: " + ", ".join(failed))
                                       if failed else None}, expires_in_sec=86400)
    except Exception as e:  # noqa: BLE001 -- recorded, and said on the screen
        frappe.log_error(title=f"Settings: full reload of {code}", message=frappe.get_traceback())
        frappe.cache().set_value(key, {**state, "state": "failed",
                                       "finished": frappe.utils.now_datetime(),
                                       "error": str(e)[:300] or type(e).__name__},
                                 expires_in_sec=86400)


@frappe.whitelist(methods=["POST"])
def reload_business(name: str = ""):
    """Start a full load of one business in the background. The screen follows its
    progress through businesses() (facts reloaded so far, of all of them)."""
    _require("businesses")
    b = _get_business(name)
    if (b.status or "") == "Paused":
        _say(f"{b.business_name} is paused. Resume it first.")
    code = b.business_code
    if _loading(code):
        _say(f"{b.business_name} is being loaded already. Try again when it has finished.")
    key = RELOAD_KEY.format(code)
    actor = _users._find(local.user)
    frappe.cache().set_value(key, {"state": "queued", "started": frappe.utils.now_datetime(),
                                   "by": _name(actor)}, expires_in_sec=86400)
    _audit(f"started a full reload of {b.business_name}", b)
    frappe.db.commit()  # the job reads what this request wrote
    frappe.enqueue(_reload_job, queue="long", code=code, key=key)
    return _business_row(b)


# --- Claude ----------------------------------------------------------------------------
CLAUDE_KEY = "command_center_anthropic_key"


def _claude_masked() -> str | None:
    key = str(frappe.conf.get(CLAUDE_KEY) or "")
    if not key:
        return None
    return ("sk-ant-…" if key.startswith("sk-ant-") else "…") + key[-4:]


@frappe.whitelist()
def claude():
    _require_admin()
    from command_center.ask import claude as _c
    from command_center.ask import llm
    return {"set": bool(frappe.conf.get(CLAUDE_KEY)), "masked": _claude_masked(),
            "provider": llm.provider(), "model": _c.model_for("analyst"),
            "deep_model": _c.model_for("deep")}


@frappe.whitelist(methods=["POST"])
def set_claude_key(key: str = ""):
    """Replace the Claude key (written to insights.json; no restart needed)."""
    _require_admin()
    key = str(key or "").strip()
    if not key:
        _say("Paste the new key.")
    if any(c.isspace() for c in key) or len(key) < 20:
        _say("That does not look like a whole key. Copy it again from the Anthropic console.")
    from frappe.installer import update_site_config
    update_site_config(CLAUDE_KEY, key)
    _audit("replaced the Claude key")
    return claude()


@frappe.whitelist(methods=["POST"])
def check_claude():
    """ask.check_analyst, in plain words."""
    _require_admin()
    from command_center.api import ask
    from command_center.ask import llm
    if not llm.provider():
        return {"ok": False, "says": "No Claude key is set, so questions are answered by the "
                                     "basic search only. Add the key, then check again."}
    try:
        out = ask.check_analyst()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "says": f"The check could not run: {str(e)[:300]}"}
    if not out.get("ok"):
        return {"ok": False, "says": f"Claude did not answer. {out.get('why') or ''}".strip(),
                "model": out.get("model")}
    provider = out.get("provider")
    says = (f"{'Claude' if provider == 'claude' else (provider or 'The analyst').title()} "
            f"answered. Questions use {out.get('model')}")
    if out.get("deep_model"):
        says += f"; deeper looks and reports use {out['deep_model']}"
    says += "."
    cache = out.get("cache") or {}
    if provider == "claude":
        says += (" The saved opening is being reused, which keeps the cost down."
                 if cache.get("working") else
                 " The saved opening was not reused on the second try; costs will be higher.")
    return {"ok": True, "says": says, "model": out.get("model"),
            "deep_model": out.get("deep_model"), "provider": provider}


# --- personal ERPNext keys -------------------------------------------------------------
CRED = "Command Center Site Credential"


def _cred_row(c, names: dict, businesses: dict) -> dict:
    return {"name": c.pk, "user": c.user, "person": names.get(c.user, c.user),
            "business_code": c.business_code,
            "business_name": businesses.get(c.business_code, c.business_code),
            "api_key": _mask(c.api_key), "has_secret": _has_secret(CRED, c.pk),
            "last_used": c.last_used, "last_error": (c.last_error or "")[:300]}


@frappe.whitelist()
def credentials():
    """Everyone's keys for the administrator; managers' keys for a delegate."""
    me = _require("keys")
    from insights.core.models import CommandCenterSiteCredential
    people = list(_User().objects.all())
    names = {u.username: _name(u) for u in people}
    admins = {u.username for u in people if u.is_superuser}
    biz = dict(_business_model().objects.values_list("business_code", "business_name"))
    return [_cred_row(c, names, biz) for c in
            CommandCenterSiteCredential.objects.order_by("user", "business_code")
            if me.is_superuser or c.user not in admins]


def _may_change_key(me, username: str):
    """A delegate manages the keys of managers, not of an administrator."""
    if me.is_superuser:
        return
    u = _users._find(username)
    if u is not None and u.is_superuser:
        raise PermissionError("Only the platform's administrator can change an "
                              "administrator's keys.")


@frappe.whitelist(methods=["POST"])
def set_credential(user: str = "", business_code: str = "", api_key: str = "",
                   api_secret: str = ""):
    """A person's own ERPNext key for one business (used for approvals). A blank key or
    secret keeps the current one."""
    me = _require("keys")
    u = _get_person(user)
    _may_change_key(me, u.username)
    b = _business_model().objects.filter(business_code=str(business_code or "")).first()
    if b is None:
        _say("Choose a connected business.")
    api_key, api_secret = str(api_key or "").strip(), str(api_secret or "").strip()
    existing = frappe.db.get_value(CRED, {"user": u.username, "business_code": b.business_code})
    if not existing and not (api_key and api_secret):
        _say("Type both the API key and the API secret of this person's own ERPNext user.")
    if existing and not (api_key or api_secret):
        _say("Nothing was changed.")
    doc = frappe.get_doc(CRED, existing) if existing else frappe.new_doc(CRED)
    doc.update({"user": u.username, "business_code": b.business_code})
    if api_key:
        doc.api_key = api_key
    if api_secret:
        doc.api_secret = api_secret
    doc.save(ignore_permissions=True)
    from insights.core.models import CommandCenterSiteCredential
    c = CommandCenterSiteCredential.objects.get(pk=doc.name)
    _audit(f"{'replaced' if existing else 'set'} the ERPNext key of {u.username} for "
           f"{b.business_name}", c, flag=2 if existing else 1)
    return _cred_row(c, {u.username: _name(u)}, {b.business_code: b.business_name})


@frappe.whitelist(methods=["POST"])
def remove_credential(name: str = ""):
    me = _require("keys")
    from insights.core.models import CommandCenterSiteCredential
    c = CommandCenterSiteCredential.objects.filter(pk=str(name or "")).first()
    if c is None:
        _say("That key has been removed already.")
    _may_change_key(me, c.user)
    what = f"removed the ERPNext key of {c.user} for {c.business_code}"
    _audit(what, c, flag=3)
    frappe.delete_doc(CRED, c.pk, force=True)
    return {"removed": True}


@frappe.whitelist(methods=["POST"])
def test_credential(name: str = ""):
    """Does this person's key work on that business's ERPNext, and as whom?"""
    me = _require("keys")
    import requests
    from insights.core.models import CommandCenterSiteCredential
    c = CommandCenterSiteCredential.objects.filter(pk=str(name or "")).first()
    if c is None:
        _say("That key has been removed.")
    _may_change_key(me, c.user)
    b = _business_model().objects.filter(business_code=c.business_code).first()
    secret = frappe.get_doc(CRED, c.pk).get_password("api_secret", raise_exception=False)
    if b is None or not b.site_url or not (c.api_key and secret):
        return {"ok": False, "says": "The business's address, or this key or secret, is missing."}
    try:
        r = requests.get(f"{b.site_url.rstrip('/')}/api/method/frappe.auth.get_logged_user",
                         headers={"Authorization": f"token {c.api_key}:{secret}",
                                  "Accept": "application/json"}, timeout=10)
    except requests.RequestException as e:
        return {"ok": False, "says": f"{b.business_name}'s ERPNext did not answer ({type(e).__name__})."}
    if r.status_code in (401, 403):
        return {"ok": False, "says": f"{b.business_name}'s ERPNext refused this key and secret."}
    if not r.ok:
        return {"ok": False, "says": f"{b.business_name}'s ERPNext answered with an error "
                                     f"(HTTP {r.status_code})."}
    try:
        who = r.json().get("message")
    except ValueError:
        return {"ok": False, "says": "Something answered, but it is not an ERPNext site."}
    return {"ok": True, "says": f"Works. On {b.business_name} it acts as {who}."}


# --- email ----------------------------------------------------------------------------
MAIL_KEY = "mail"  # insights.json; read by insights.compat.runtime.sendmail
SECURITY = ("starttls", "ssl", "none")
SECURITY_WORDS = {"starttls": "STARTTLS", "ssl": "SSL", "none": "no encryption"}


def _email_view() -> dict:
    from insights.compat import runtime
    cfg = runtime.mail_config()
    return {"configured": bool(cfg.get("host")), "host": cfg.get("host") or "",
            "port": runtime.mail_port(cfg) if cfg.get("host") else None,
            "security": runtime.mail_security(cfg), "user": cfg.get("user") or "",
            "has_password": bool(cfg.get("password")), "sender": cfg.get("sender") or "",
            "sender_name": cfg.get("sender_name") or "",
            "last_attempt": runtime.last_mail_attempt()}


@frappe.whitelist()
def email():
    """The mail server the platform sends from. The password is never returned."""
    _require_admin()
    return _email_view()


def _valid_email(value: str, what: str) -> str:
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.core.validators import validate_email
    value = str(value or "").strip()
    if not value:
        _say(f"Type the {what}.")
    try:
        validate_email(value)
    except DjangoValidationError:
        _say(f"The {what} is not an email address.")
    return value


@frappe.whitelist(methods=["POST"])
def set_email(host: str = "", port=None, security: str = "starttls", user: str = "",
              password: str = "", sender: str = "", sender_name: str = "",
              clear_password=0):
    """Save the mail server (insights.json "mail", in the shape sendmail reads; used from
    the next message, no restart). A blank password keeps the stored one."""
    _require_admin()
    from insights.compat import runtime
    host = str(host or "").strip()
    if not host or any(c.isspace() for c in host) or "/" in host or "@" in host:
        _say("Type the mail server's address, for example smtp.gmail.com or "
             "smtp.office365.com.")
    security = str(security or "").strip().lower()
    if security not in SECURITY:
        _say("Choose the security: STARTTLS, SSL or none.")
    if str(port if port is not None else "").strip():
        try:
            port = int(str(port).strip())
        except ValueError:
            port = 0
        if not 0 < port < 65536:
            _say("The port is a number, usually 587 for STARTTLS or 465 for SSL.")
    else:
        port = {"ssl": 465, "starttls": 587, "none": 25}[security]
    user = str(user or "").strip()
    sender = _valid_email(sender or (user if "@" in user else ""), "From address")
    sender_name = str(sender_name or "").strip()[:100]
    old = runtime.mail_config()
    if str(password or ""):
        pw = str(password)
    elif _truthy(clear_password) or not user:
        pw = ""
    else:
        pw = str(old.get("password") or "")
    if user and not pw:
        _say("Type the password for this username.")
    new = {"host": host, "port": port, "security": security,
           "tls": security == "starttls", "ssl": security == "ssl",
           "user": user, "password": pw, "sender": sender, "sender_name": sender_name}
    changed = []
    if (old.get("host"), runtime.mail_port(old) if old.get("host") else None,
            runtime.mail_security(old)) != (host, port, security):
        changed.append(f"server {host} on port {port} ({SECURITY_WORDS[security]})")
    if (old.get("user") or "") != user:
        changed.append(f"username {user}" if user else "no username")
    if (old.get("password") or "") != pw:
        changed.append("password")
    if (old.get("sender") or "") != sender or (old.get("sender_name") or "") != sender_name:
        changed.append(f"From {sender_name + ' ' if sender_name else ''}<{sender}>")
    if not changed:
        _say("Nothing was changed.")
    from frappe.installer import update_site_config
    update_site_config(MAIL_KEY, new)
    _audit(("set up email: " if not old.get("host") else "changed the email settings: ")
           + ", ".join(changed))
    return _email_view()


@frappe.whitelist(methods=["POST"])
def test_email(to: str = ""):
    """Send a short message with the saved settings, and say what happened."""
    _require_admin()
    from insights.compat import runtime
    to = _valid_email(to, "address to send the test to")
    if not runtime.mail_config().get("host"):
        return {"ok": False, "says": "Email is not set up yet. Fill in the mail server above "
                                     "and save it first."}
    try:
        runtime.sendmail(
            kind="test",
            recipients=[to], subject=f"Test email from {_product()}",
            message=branding.email_html(
                f"<p>This is a test from {frappe.utils.escape_html(_product())}.</p>"
                "<p>Email is working: scheduled reports will be sent from this "
                "address.</p>"))
    except runtime.MailError as e:
        return {"ok": False, "says": str(e)}
    _audit(f"sent a test email to {to}")
    return {"ok": True, "says": f"Sent to {to}. If it has not arrived in a few minutes, look "
                                f"in the spam folder."}


EMAIL_LOG_SHOWN = 100


def _log_row(r) -> dict:
    return {"id": r.id, "at": r.at.strftime("%Y-%m-%d %H:%M:%S") if r.at else None,
            "kind": r.kind, "status": r.status, "to": r.recipients, "subject": r.subject,
            "error": r.error, "business": r.business_code,
            "can_resend": r.status == "Failed" and bool(r.body),
            "why_not": (None if r.status != "Failed" or r.body else
                        "A set-password link is never kept. Send a new one from User "
                        "Management, under Manage." if r.kind == "invite" else
                        "The report's PDF was attached and is not kept, so it cannot be sent "
                        "again from here: run the report again from Reports."
                        if r.attachments else
                        "The message was not kept, so it cannot be sent again from here."),
            "resend_of": r.resend_of}


@frappe.whitelist()
def email_log(status: str = ""):
    """The last 100 send attempts, newest first: Sent, Failed, or both. Administrator only,
    like the rest of Email."""
    _require_admin()
    from insights.core.models import EmailLog
    q = EmailLog.objects.all()
    if status in ("Sent", "Failed"):
        q = q.filter(status=status)
    rows = list(q.order_by("-at", "-id")[:EMAIL_LOG_SHOWN])
    return {"rows": [_log_row(r) for r in rows], "shown": EMAIL_LOG_SHOWN,
            "keep_days": _email_log_days()}


def _email_log_days() -> int:
    from django.conf import settings
    return int(settings.CONFIG.get("email_log_days") or 180)


@frappe.whitelist(methods=["POST"])
def resend_email(id=None):
    """Send a failed message again, to the same people, exactly as it was -- only when its
    HTML was kept (it carried no attachment). The resend is a new entry in the log."""
    _require_admin()
    from insights.compat import runtime
    from insights.core.models import EmailLog
    try:
        r = EmailLog.objects.get(pk=int(id))
    except (EmailLog.DoesNotExist, TypeError, ValueError):
        raise ValidationError("That email is not in the log.")
    if r.status != "Failed":
        raise ValidationError("That email was sent; there is nothing to resend.")
    if not r.body:
        raise ValidationError(_log_row(r)["why_not"])
    to = [x.strip() for x in (r.recipients or "").split(",") if x.strip()]
    try:
        runtime.sendmail(recipients=to, subject=r.subject, message=r.body, kind=r.kind,
                         business=r.business_code, resend_of=r.id)
    except runtime.MailError as e:
        return {"ok": False, "says": f"Not sent again: {e}"}
    _audit(f"resent the email “{r.subject}” to {', '.join(to)}")
    return {"ok": True, "says": f"Sent again to {', '.join(to)}."}


@frappe.whitelist()
def notifications():
    """What the platform sends and whether it can: email set up or not, report
    schedules and alert rules switched on, the last email, and schedules that failed."""
    _require_admin()
    from command_center.alerts.rules import RULES
    from command_center.api.reports import REPORTS
    from insights.compat import runtime
    from insights.core.models import (CommandCenterAlertRule,
                                      CommandCenterReportSchedule)
    rules = dict(CommandCenterAlertRule.objects.values_list("rule_id", "enabled"))
    schedules = list(CommandCenterReportSchedule.objects.all())
    on = [x for x in schedules if x.enabled]
    biz = dict(_business_model().objects.values_list("business_code", "business_name"))
    failing = [{"report": (REPORTS.get(x.report) or (x.report_title or x.report,))[0],
                "business": biz.get(x.business_code, x.business_code),
                "status": x.last_status}
               for x in on if str(x.last_status or "").startswith("Failed")]
    return {"email_configured": bool(runtime.mail_config().get("host")),
            "schedules_on": len(on), "schedules_total": len(schedules),
            "rules_on": sum(1 for r in RULES if rules.get(r.rule_id, 1)),
            "rules_total": len(RULES),
            "last_attempt": runtime.last_mail_attempt(), "failing": failing}


# --- recommendations --------------------------------------------------------------------
REC_COST = ("About one Claude request per business per day, written at 06:30 from the "
            "recommendations and headline figures only.")


def _rec_business(business_code: str = ""):
    rows = list(_business_model().objects.order_by("business_name"))
    if not rows:
        _say("Connect a business first (Settings, Businesses).")
    b = next((x for x in rows if x.business_code == str(business_code or "")), rows[0])
    return b, rows


def _learning_view(code, conf) -> dict:
    """Settings -> Recommendations -> Learning: what each figure's history supports, each
    rule's learned weight and threshold, and what the advice achieved."""
    from command_center.api.businesses import currency_for
    from command_center.recommend import adaptive, learning, metrics
    cur = currency_for(code) or ""
    hist = metrics.history(code)
    assessed = metrics.assess(code, hist)
    taught = learning.weights(code)
    figures = [{"key": mt.key, "label": mt.label, "grain": "Monthly" if mt.grain == "month"
                else "Daily", "points": len(hist.get(mt.key) or []),
                "status": (assessed.get(mt.key) or {}).get("status", "learning"),
                "method": (assessed.get(mt.key) or {}).get("method"),
                "says": metrics.band_words(mt, assessed.get(mt.key), cur),
                "why_now": metrics.why_now(mt, assessed.get(mt.key), cur)}
               for mt in metrics.METRICS]
    thresholds = {}
    for rule_id in adaptive.ADAPTIVE:
        mine = conf["rules"].get(rule_id)
        if not mine:
            continue
        spec = adaptive.ADAPTIVE[rule_id]
        sens = (taught.get(rule_id) or {}).get("sensitivity", 1.0)
        thresholds[rule_id] = adaptive.threshold(rule_id, mine["params"][spec["param"]], hist, sens)
    return {"figures": figures, "weights": taught, "thresholds": thresholds,
            "outcomes": learning.recent_outcomes(code, limit=12),
            "what_worked": learning.what_worked(code)}


def _rec_view(b, rows) -> dict:
    from command_center.ask import claude
    from command_center.recommend import adaptive, daily, engine, review
    from command_center.recommend.rules import AREAS, RULES
    from insights.compat import runtime
    conf = engine.settings(b.business_code)
    told = engine.suggestions(b.business_code)
    learn = _learning_view(b.business_code, conf)
    out = []
    for r in RULES:
        mine = conf["rules"][r.rule_id]
        n = told.get(r.rule_id, 0)
        t = learn["thresholds"].get(r.rule_id)
        w = learn["weights"].get(r.rule_id) or {}
        out.append({
            "mode": mine.get("mode"), "adaptive_param": (adaptive.ADAPTIVE.get(r.rule_id) or {}).get("param"),
            "threshold": ({k: t.get(k) for k in ("status", "value", "fixed", "learned", "says")}
                          if t else None),
            "weight": w.get("weight", 1.0), "weight_explain": w.get("explain"),
            "rule_id": r.rule_id, "title": r.title, "area": r.area, "area_label": AREAS[r.area],
            "severity": r.severity, "enabled": mine["enabled"], "not_relevant": n,
            "suggestion": (f"Marked not relevant {n} times: consider raising "
                           f"{r.params[0].label.lower()}." if n and r.params else None),
            "params": [{"key": p.key, "label": p.label, "unit": p.unit, "default": p.default,
                        "value": mine["params"][p.key]} for p in r.params]})
    brief = daily._get(daily.BRIEF_PARENT, b.business_code)
    rev = review.state(b.business_code)
    return {"business_code": b.business_code, "business_name": b.business_name,
            "businesses": [{"code": x.business_code, "name": x.business_name} for x in rows],
            "rules": out, "digest": conf["digest"], "brief": conf["brief"],
            "anomalies": conf["anomalies"], "ai_review": conf["ai_review"],
            "ai_review_cost": review.COST_NOTE,
            "ai_review_state": ({k: rev.get(k) for k in ("date", "at", "ok", "error", "model",
                                                          "accepted", "rejected", "patterns",
                                                          "closed", "skipped")}
                                if rev else None),
            "learning": {k: learn[k] for k in ("figures", "outcomes", "what_worked")},
            "digest_state": daily.digest_state(b.business_code) or None,
            "brief_state": ({k: brief.get(k) for k in ("date", "at", "text", "error", "model")}
                            if brief else None),
            "claude_configured": claude.configured(),
            "email_configured": bool(runtime.mail_config().get("host")),
            "brief_cost": REC_COST}


@frappe.whitelist()
def recommendations(business_code: str = ""):
    """The recommendation rules for one business: on or off, their thresholds, how often
    managers marked each not relevant; the digest and the Daily Brief switches."""
    _require_admin()
    b, rows = _rec_business(business_code)
    return _rec_view(b, rows)


def _rec_list(value, what):
    import json
    if isinstance(value, str):
        try:
            value = json.loads(value or "null")
        except ValueError:
            _say(f"The {what} could not be read.")
    return value


@frappe.whitelist(methods=["POST"])
def set_recommendations(business_code: str = "", rules=None, digest=None, brief=None,
                        anomalies=None, ai_review=None):
    """Save one business's rules ({rule_id: {"enabled", "params", "mode"}}), the digest,
    the brief, the unusual-movement findings and the daily AI review."""
    _require_admin()
    from command_center.recommend import engine
    from command_center.recommend.rules import BY_ID
    b, rows = _rec_business(business_code)
    old = engine.settings(b.business_code)
    new = {"rules": {k: {kk: (dict(vv) if kk == "params" else vv) for kk, vv in v.items()}
                     for k, v in old["rules"].items()},
           "digest": old["digest"], "brief": old["brief"], "anomalies": old["anomalies"],
           "ai_review": old["ai_review"], "ai_review_set": old["ai_review_set"]}
    changed = []
    for rule_id, mine in (_rec_list(rules, "rules") or {}).items():
        rule = BY_ID.get(rule_id)
        if rule is None or not isinstance(mine, dict):
            continue
        cur = new["rules"][rule_id]
        if "enabled" in mine and bool(mine["enabled"]) != cur["enabled"]:
            cur["enabled"] = bool(mine["enabled"])
            changed.append(f"{rule.title} {'on' if cur['enabled'] else 'off'}")
        mode = mine.get("mode")
        if mode not in (None, "") and "mode" in cur:
            if mode not in ("fixed", "adaptive"):
                _say(f"{rule.title}: choose Fixed or Adaptive.")
            if mode != cur["mode"]:
                cur["mode"] = mode
                changed.append(f"{rule.title}: {mode}")
        for p in rule.params:
            v = (mine.get("params") or {}).get(p.key)
            if v in (None, ""):
                continue
            try:
                v = float(str(v).replace(",", ""))
            except ValueError:
                _say(f"{rule.title}: \u201c{p.label}\u201d must be a number.")
            if v < 0 or (p.unit == "percent" and v > 1000):
                _say(f"{rule.title}: \u201c{p.label}\u201d is out of range.")
            if v != cur["params"][p.key]:
                cur["params"][p.key] = v
                changed.append(f"{rule.title}: {p.label.lower()} {v:g}")
    given = {"digest": digest, "brief": brief, "anomalies": anomalies, "ai_review": ai_review}
    for flag, word in (("digest", "daily email digest"), ("brief", "Daily Brief by Claude"),
                       ("anomalies", "unusual movements"), ("ai_review", "daily AI review")):
        v = given[flag]
        if v is None or v == "":
            continue
        v = _truthy(v)
        if v != new[flag]:
            new[flag] = v
            changed.append(f"{word} {'on' if v else 'off'}")
        if flag == "ai_review":
            new["ai_review_set"] = True
    if not changed:
        _say("Nothing was changed.")
    engine.save_settings(b.business_code, new)
    _audit(f"changed the recommendations for {b.business_name}: " + "; ".join(changed)[:1500])
    return _rec_view(b, rows)


@frappe.whitelist(methods=["POST"])
def write_brief_now(business_code: str = ""):
    """Write today's Daily Brief for one business now (one Claude request)."""
    _require_admin()
    from command_center.recommend import daily, engine
    b, rows = _rec_business(business_code)
    if not engine.settings(b.business_code)["brief"]:
        _say("Switch the Daily Brief on for this business first.")
    engine.ensure_fresh(b.business_code, force=True)
    out = daily.write_brief(b.business_code)
    _audit(f"wrote the Daily Brief for {b.business_name} now")
    return {"ok": bool(out.get("text")), "says": "Written." if out.get("text") else out.get("error"),
            **_rec_view(b, rows)}


@frappe.whitelist(methods=["POST"])
def run_review_now(business_code: str = ""):
    """Run today's AI review for one business now (one Claude request; at most one
    successful review a day)."""
    _require_admin()
    from command_center.recommend import engine, review
    b, rows = _rec_business(business_code)
    if not engine.settings(b.business_code)["ai_review"]:
        _say("Switch the daily AI review on for this business first.")
    out = review.review(b.business_code)
    _audit(f"ran the daily AI review for {b.business_name} now")
    says = (out.get("skipped") or out.get("error")
            or f"Reviewed: {out.get('accepted', 0)} accepted, {len(out.get('rejected') or [])} "
               f"not used.")
    return {"ok": bool(out.get("ok")), "says": says, **_rec_view(b, rows)}


# --- branding --------------------------------------------------------------------------
# The product's name, tagline, logos and the vendor's footer (command_center/branding.py
# reads them for every page, PDF, workbook and email), kept in insights.json "branding".
# The administrator's alone. A business's co-brand -- the client name and logo its
# documents are "Prepared for" -- is set from Businesses, by whoever may edit businesses.
def _product() -> str:
    return branding.branding()["product"]


def _brand_cfg() -> dict:
    return dict(branding._conf())


def _save_brand(cfg: dict) -> None:
    from frappe.installer import update_site_config
    update_site_config(branding.CONFIG_KEY, cfg)


def _brand_view() -> dict:
    s = branding.stored()
    return {**{k: s[k] for k in branding.TEXT_FIELDS},
            "defaults": dict(branding.DEFAULTS),
            "max_len": dict(branding.MAX_LEN),
            "max_kb": branding.MAX_BYTES // 1024,
            **{f"{k}_url": branding.url_for(s[k]) for k in branding.PLATFORM_KINDS},
            # What the PDFs print now: the Report Logo, else the light-background logo,
            # else the product's name (a WebP logo cannot be drawn in a PDF).
            "report_uses": ("report" if s[branding.REPORT_KIND] else
                            "light" if _printable(s["logo_light"] or s["logo_dark"]) else "name"),
            "preview": branding.public()}


def _printable(name) -> bool:
    return bool(name) and name.endswith(tuple("." + t for t in branding.PRINT_TYPES))


def _brand_image(kind: str, raw: bytes) -> str:
    """The stored file's name, or a refusal in plain words."""
    try:
        return branding.store_image(kind, raw)
    except branding.BrandError as e:
        _say(str(e))


def _decoded(data, max_bytes: int = branding.MAX_BYTES) -> bytes:
    try:
        return branding.decode_upload(data, max_bytes)
    except branding.BrandError as e:
        _say(str(e))


@frappe.whitelist()
def brand():
    """The product's branding as saved, with the defaults and the logos' addresses."""
    _require_admin()
    return _brand_view()


@frappe.whitelist(methods=["POST"])
def set_brand(product_name: str = "", tagline: str = "", company: str = "", person: str = "",
              email: str = "", phone: str = "", website: str = ""):
    """Save the product's name and tagline and the vendor's footer details. A blank
    product name or company goes back to the default; the others may be left blank."""
    _require_admin()
    given = {"product_name": product_name, "tagline": tagline, "company": company,
             "person": person, "email": email, "phone": phone, "website": website}
    words = {"product_name": "product name", "tagline": "tagline", "company": "company",
             "person": "name and role", "email": "email", "phone": "phone number",
             "website": "website"}
    clean = {}
    for k, v in given.items():
        v = " ".join(str(v or "").split())
        if any(c in v for c in "<>{}"):
            _say(f"The {words[k]} cannot contain < > {{ or }}.")
        if len(v) > branding.MAX_LEN[k]:
            _say(f"The {words[k]} is too long: at most {branding.MAX_LEN[k]} characters.")
        clean[k] = v
    if clean["email"]:
        _valid_email(clean["email"], "email")
    if clean["website"] and (" " in clean["website"] or "." not in clean["website"]):
        _say("The website should be an address such as www.example.com.")
    cfg = _brand_cfg()
    changed = [words[k] for k, v in clean.items() if (cfg.get(k) or "") != v]
    if not changed:
        _say("Nothing was changed.")
    cfg.update(clean)
    _save_brand(cfg)
    _audit("changed the branding: " + ", ".join(changed))
    return _brand_view()


@frappe.whitelist(methods=["POST"])
def upload_brand_logo(kind: str = "", data: str = ""):
    """A logo for light backgrounds, one for dark backgrounds, the favicon, or the
    Sign-In Logo (the sign-in page's own): PNG, JPEG or WebP, at most branding.MAX_BYTES,
    checked by its content (never SVG). Or the Report Logo the PDFs use instead of the
    light-background one: PNG or JPEG only (the PDF engine cannot draw WebP)."""
    _require_admin()
    if kind not in branding.PLATFORM_KINDS:
        _say("Choose which logo this is.")
    name = _brand_image(kind, _decoded(data))
    cfg = _brand_cfg()
    old = cfg.get(kind)
    cfg[kind] = name
    _save_brand(cfg)
    branding.forget(old, cfg)
    _audit(f"uploaded a new {kind.replace('_', ' ')}")
    return _brand_view()


@frappe.whitelist(methods=["POST"])
def remove_brand_logo(kind: str = ""):
    _require_admin()
    if kind not in branding.PLATFORM_KINDS:
        _say("Choose which logo to remove.")
    cfg = _brand_cfg()
    old = cfg.pop(kind, None)
    if not old:
        _say("There is no such logo to remove.")
    _save_brand(cfg)
    branding.forget(old, cfg)
    _audit(f"removed the {kind.replace('_', ' ')}")
    return _brand_view()


def _is_admin() -> bool:
    u = _users._find(local.user)
    return bool(u is not None and u.is_active and u.is_superuser)


def _client_brand(code: str) -> dict:
    c = (branding.stored().get("businesses") or {}).get(code) or {}
    return {"client_name": c.get("display_name") or "",
            "client_logo_url": branding.url_for(c.get("logo")),
            "report_style": c.get("style") or "platform",
            "credit": c.get("credit") or "show",
            "letterhead_url": branding.url_for(c.get("header")),
            "letterfoot_url": branding.url_for(c.get("footer")),
            "may_hide_credit": _is_admin(),
            "letter_max_kb": branding.LETTER_MAX_BYTES // 1024}


# What a business's co-brand keeps when it is the default, so a business with nothing
# chosen has no entry at all.
_CLIENT_DEFAULTS = {"style": "platform", "credit": "show"}
_CLIENT_FILES = ("logo", "header", "footer")


def _set_client(b, **changes) -> dict:
    cfg = _brand_cfg()
    clients = dict(cfg.get("businesses") or {})
    mine = dict(clients.get(b.business_code) or {})
    old = {k: mine.get(k) for k in _CLIENT_FILES}
    mine.update(changes)
    mine = {k: v for k, v in mine.items() if v and _CLIENT_DEFAULTS.get(k) != v}
    if mine:
        clients[b.business_code] = mine
    else:
        clients.pop(b.business_code, None)
    cfg["businesses"] = clients
    _save_brand(cfg)
    for k, name in old.items():
        if name and name != mine.get(k):
            branding.forget(name, cfg)
    return _business_row(_get_business(b.pk))


@frappe.whitelist(methods=["POST"])
def set_business_brand(name: str = "", display_name: str = ""):
    """The name this business's documents are prepared for ("Prepared for ..."); blank
    goes back to its own name."""
    _require("businesses")
    b = _get_business(name)
    display = " ".join(str(display_name or "").split())
    if any(c in display for c in "<>{}"):
        _say("The display name cannot contain < > { or }.")
    if len(display) > 100:
        _say("The display name is too long: at most 100 characters.")
    _audit(f"set {b.business_name}'s display name to {display}" if display
           else f"cleared {b.business_name}'s display name", b)
    return _set_client(b, display_name=display)


@frappe.whitelist(methods=["POST"])
def upload_business_logo(name: str = "", data: str = ""):
    """The business's own logo, shown beside the product's on its documents."""
    _require("businesses")
    b = _get_business(name)
    logo = _brand_image(branding.CLIENT_KIND, _decoded(data))
    _audit(f"uploaded a logo for {b.business_name}", b)
    return _set_client(b, logo=logo)


@frappe.whitelist(methods=["POST"])
def remove_business_logo(name: str = ""):
    _require("businesses")
    b = _get_business(name)
    _audit(f"removed {b.business_name}'s logo", b)
    return _set_client(b, logo=None)


# --- a business's Report Style ------------------------------------------------------------
def _check_credit(credit: str, current: str) -> None:
    """Hiding the vendor's credit is the administrator's alone: a delegate may choose
    Show or Small, and may leave a Hide the administrator set as it is."""
    if credit == "hide" and current != "hide" and not _is_admin():
        raise PermissionError("Only the platform's administrator can hide the vendor's credit. "
                              "Choose Show or Small.")


@frappe.whitelist(methods=["POST"])
def set_business_report_style(name: str = "", style: str = "", credit: str = ""):
    """Whose brand leads this business's PDFs and workbooks (Platform Branding, Client
    Branding, Client Letterhead) and how the vendor's credit appears (Show, Small,
    Hide -- Hide by the administrator only). A blank value leaves it as it is."""
    _require("businesses")
    b = _get_business(name)
    now = (branding.stored().get("businesses") or {}).get(b.business_code) or {}
    style = str(style or "").strip() or now.get("style") or "platform"
    credit = str(credit or "").strip() or now.get("credit") or "show"
    if style not in branding.STYLES:
        _say("Choose Platform Branding, Client Branding or Client Letterhead.")
    if credit not in branding.CREDITS:
        _say("Choose Show, Small or Hide for the vendor's credit.")
    _check_credit(credit, now.get("credit") or "show")
    if style == "letterhead" and not now.get("header"):
        _say("Upload the letterhead's header image first, then choose Client Letterhead.")
    if style == (now.get("style") or "platform") and credit == (now.get("credit") or "show"):
        _say("Nothing was changed.")
    _audit(f"set {b.business_name}'s report style to {branding.STYLES[style]}, vendor credit "
           f"{branding.CREDITS[credit]}", b)
    return _set_client(b, style=style, credit=credit)


def _letter_part(part: str) -> str:
    kind = branding.LETTER_KINDS.get(str(part or ""))
    if not kind:
        _say("Choose the letterhead's header or footer.")
    return kind


@frappe.whitelist(methods=["POST"])
def upload_business_letterhead(name: str = "", part: str = "header", data: str = ""):
    """The business's letterhead: the header strip printed across the top of every page
    of its PDFs, or the footer strip across the foot. PNG or JPEG, at most
    branding.LETTER_MAX_BYTES, a wide strip (branding.RULES), checked by content."""
    _require("businesses")
    b = _get_business(name)
    kind = _letter_part(part)
    image = _brand_image(kind, _decoded(data, branding.LETTER_MAX_BYTES))
    _audit(f"uploaded a letterhead {part} for {b.business_name}", b)
    return _set_client(b, **{part: image})


@frappe.whitelist(methods=["POST"])
def remove_business_letterhead(name: str = "", part: str = "header"):
    """Remove the letterhead's header or footer image. Without a header image a
    letterhead cannot print, so the business goes to Client Branding."""
    _require("businesses")
    b = _get_business(name)
    _letter_part(part)
    now = (branding.stored().get("businesses") or {}).get(b.business_code) or {}
    if not now.get(part):
        _say("There is no such image to remove.")
    changes = {part: None}
    if part == "header" and now.get("style") == "letterhead":
        changes["style"] = "client"
    _audit(f"removed {b.business_name}'s letterhead {part}"
           + (" (its report style is now Client Branding)" if "style" in changes else ""), b)
    return _set_client(b, **changes)


@frappe.whitelist(methods=["POST"])
def preview_report_style(name: str = "", style: str = "", credit: str = ""):
    """A one-page sample PDF in the Report Style and credit chosen on the screen (saved
    or not), with the business's stored logo and letterhead; without a business, the
    platform's own brand (Settings -> Branding, the administrator's). Stores nothing.
    Where there is no PDF engine (a laptop), the page's HTML instead."""
    import base64

    from command_center.api import export
    if name:
        _require("businesses")
        b = _get_business(name)
        code = b.business_code
        now = (branding.stored().get("businesses") or {}).get(code) or {}
        style = style if style in branding.STYLES else None
        credit = credit if credit in branding.CREDITS else None
        _check_credit(credit or "", now.get("credit") or "show")
    else:
        _require_admin()
        code, style, credit = None, "platform", "show"
    out = export.preview(code, style=style, credit=credit)
    look = branding.document(code, style=style, credit=credit)
    return {"pdf": base64.b64encode(out["pdf"]).decode() if out["pdf"] else None,
            "html": out["html"], "reason": out["reason"],
            "style": look["look"], "style_label": branding.STYLES[look["look"]],
            "credit": look["credit"]}
