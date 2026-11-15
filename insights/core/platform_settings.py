"""The Settings screen: people, businesses, the Claude key, email and personal ERPNext keys.

Who may use it:

  the administrator   (an active Django superuser) every section, always.
  a delegate          an active manager the administrator has given one or more
                      sections, on People -> Manage -> Settings Access. Each section is
                      a Django group (GRANTS below); membership is the permission:
                        Businesses              add, edit, test, pause and reload businesses
                        People                  add managers, rename, deactivate and
                                                reactivate them, reset their passwords --
                                                never make anyone an administrator, never
                                                give Settings access, never change an
                                                administrator or anyone who has Settings
                                                access (other than their own password)
                        Personal ERPNext Keys   add, replace, test and remove the keys of
                                                managers -- not of administrators
  everyone else       refused (403), whatever the screen shows.

The Claude key, Email (and its Notifications status), the Changes list and giving
Settings access stay with the administrator. Every call starts with _require(section)
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
from insights.compat import users as _users
from insights.compat.state import PermissionError, ValidationError, local

MANAGER = "Insights Dashboard Manager"  # command_center.api.businesses.ROLE
AUDIT_PREFIX = "Settings: "
RELOAD_KEY = "cc:settings:reload:{}"


# --- who may ---------------------------------------------------------------------------
# The sections an administrator can give a manager, each a Django group.
GRANTS = {"businesses": "Settings: Businesses", "people": "Settings: People",
          "keys": "Settings: Personal Keys"}
GRANT_WORDS = {"businesses": "Businesses", "people": "People", "keys": "Personal ERPNext Keys"}
# What the administrator sees, in the screen's order.
ALL_SECTIONS = ["people", "businesses", "claude", "email", "keys", "changes"]


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
            "settings_access": _grants(u), "protected": _protected(u)}


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
               set_later=0, manager=1, admin=0):
    """A new person. They sign in with their email and the password typed here, or -- if
    it is to be set later -- with their business's ERPNext, until a password is set.
    Only the administrator can add an administrator."""
    me = _require("people")
    if _truthy(admin) and not me.is_superuser:
        raise PermissionError("Only the platform's administrator can make someone an "
                              "administrator.")
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
    if _truthy(set_later):
        u.set_unusable_password()
    else:
        u.set_password(_check_password(password, password2, u))
    u.is_superuser = u.is_staff = _truthy(admin)
    u.save()
    if _truthy(manager):
        from django.contrib.auth.models import Group
        u.groups.add(Group.objects.get_or_create(name=MANAGER)[0])
    roles = [r for r, on in (("manager", _truthy(manager)), ("administrator", _truthy(admin))) if on]
    _audit(f"added {email}" + (f" as {' and '.join(roles)}" if roles else "")
           + ("; password to be set later" if _truthy(set_later) else "; password set"), u, flag=1)
    return _person(u, me)


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
def set_active(username: str = "", on=1):
    """Deactivate (their sign-ins end at once and they cannot sign in again) or reactivate."""
    me = _require("people")
    u = _get_person(username)
    _may_change(me, u)
    if _truthy(on):
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
        _say("Only Businesses, People and Personal ERPNext Keys can be given.")
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
            "reload": reload}


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
            recipients=[to], subject="Test email from AI Business Intelligence",
            message=("<p>This is a test from AI Business Intelligence.</p>"
                     "<p>Email is working: scheduled reports will be sent from this "
                     "address.</p>"))
    except runtime.MailError as e:
        return {"ok": False, "says": str(e)}
    _audit(f"sent a test email to {to}")
    return {"ok": True, "says": f"Sent to {to}. If it has not arrived in a few minutes, look "
                                f"in the spam folder."}


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
