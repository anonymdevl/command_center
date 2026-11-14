"""People and roles, for the business logic's frappe-shaped calls.

The platform's people are Django's users: username = the person's email (that is the
"user" everywhere in the business logic), roles = Django groups, and a superuser is the
platform's administrator -- shown to the business logic as "System Manager", the role
it already treats as an administrator. There is no Frappe "User" table; these adapters
answer get_doc("User"), get_roles(), and reads of "User" / "Has Role" from Django's.
"""

from __future__ import annotations

from insights.compat.state import DoesNotExistError, _dict, local

ADMIN_ROLE = "System Manager"
ALWAYS = ["All"]


def _User():
    from django.contrib.auth import get_user_model
    return get_user_model()


def _find(name):
    if not name or name == "Guest":
        return None
    U = _User()
    return U.objects.filter(username__iexact=name).first() or U.objects.filter(
        email__iexact=name).first()


def get_roles(user: str | None = None) -> list:
    user = user or local.user
    if user == "Guest":
        return ["Guest"]
    if user == "Administrator":
        # The platform itself, as scheduled jobs and the command line run it.
        return ["Administrator", "All", ADMIN_ROLE]
    u = _find(user)
    if u is None or not u.is_active:
        return ["Guest"]
    roles = ALWAYS + list(u.groups.values_list("name", flat=True))
    if u.is_superuser:
        roles += [ADMIN_ROLE, "Administrator"]
    return sorted(set(roles))


def fullname(user: str | None) -> str:
    u = _find(user)
    if u is None:
        return user or "Guest"
    return (f"{u.first_name} {u.last_name}".strip()) or u.username


def _row(u) -> _dict:
    return _dict({"name": u.username, "email": u.email or u.username,
                  "first_name": u.first_name, "last_name": u.last_name,
                  "full_name": (f"{u.first_name} {u.last_name}".strip()) or u.username,
                  "enabled": 1 if u.is_active else 0,
                  "user_type": "System User", "creation": u.date_joined,
                  "modified": u.last_login or u.date_joined})


def get_all(doctype, filters=None, fields=None, order_by=None, limit=None, pluck=None):
    """Reads of "User" and "Has Role", with the simple filters the code uses."""
    U = _User()
    if doctype == "Has Role":
        f = _plain(filters)
        rows = []
        for u in U.objects.filter(is_active=True).prefetch_related("groups"):
            names = list(u.groups.values_list("name", flat=True))
            if u.is_superuser:
                names.append(ADMIN_ROLE)
            for r in names:
                row = _dict({"parent": u.username, "role": r, "parenttype": "User"})
                if all(_match(row.get(k), v) for k, v in f.items()):
                    rows.append(row)
    else:
        f = _plain(filters)
        rows = [r for r in (_row(u) for u in U.objects.all())
                if all(_match(r.get(k), v) for k, v in f.items())]
        if order_by and "full_name" in order_by:
            rows.sort(key=lambda r: (r.full_name or "").lower(), reverse="desc" in order_by)
    if limit:
        rows = rows[:int(limit)]
    if pluck:
        return [r.get(pluck) for r in rows]
    if fields:
        cols = [str(c).split(" as ")[0].strip() for c in fields]
        rows = [_dict({c: r.get(c) for c in cols}) for r in rows]
    return rows


def exists(doctype, filters):
    rows = get_all(doctype, filters=filters if not isinstance(filters, str) else {"name": filters},
                   fields=["name"] if doctype == "User" else ["parent"])
    if not rows:
        return None
    return rows[0].get("name") or rows[0].get("parent")


def _plain(filters) -> dict:
    if not filters:
        return {}
    if isinstance(filters, str):
        return {"name": filters}
    if isinstance(filters, dict):
        return dict(filters)
    return {f[0]: [f[1], f[2]] for f in filters if len(f) == 3}


def _match(value, cond) -> bool:
    if isinstance(cond, (list, tuple)) and len(cond) == 2 and str(cond[0]) in (
            "=", "!=", "in", "not in", "like"):
        op, v = cond
        if op == "=":
            return value == v
        if op == "!=":
            return value != v
        if op == "in":
            return value in v
        if op == "not in":
            return value not in v
        if op == "like":
            return str(v).strip("%").lower() in str(value or "").lower()
    if isinstance(cond, (list, tuple)):
        return value in cond
    if isinstance(value, str) and isinstance(cond, str):
        return value.lower() == cond.lower()
    return value == cond


def set_value(name, fieldname, value=None):
    u = _find(name)
    if u is None:
        raise DoesNotExistError(f"User {name} not found")
    values = fieldname if isinstance(fieldname, dict) else {fieldname: value}
    for k, v in values.items():
        if k == "enabled":
            u.is_active = bool(int(v or 0))
        elif k in ("first_name", "last_name", "email"):
            setattr(u, k, v or "")
    u.save()


def delete(name):
    u = _find(name)
    if u is not None:
        u.delete()


class UserDoc(_dict):
    """get_doc("User", ...) -- the fields and methods the business logic uses."""

    @classmethod
    def load(cls, name):
        u = _find(name)
        if u is None:
            raise DoesNotExistError(f"User {name} not found")
        doc = cls(_row(u))
        doc["doctype"] = "User"
        return doc

    @property
    def flags(self):
        return self.setdefault("_flags", _dict())

    def is_new(self):
        return _find(self.get("name") or self.get("email")) is None

    def insert(self, ignore_permissions=False, **kw):
        U = _User()
        email = (self.get("email") or self.get("name") or "").strip().lower()
        if not email:
            from insights.compat.state import throw
            throw("A user needs an email")
        u = U.objects.create_user(username=email, email=email,
                                  first_name=self.get("first_name") or "",
                                  last_name=self.get("last_name") or "")
        u.set_unusable_password()
        u.is_active = bool(self.get("enabled", 1))
        u.save()
        self.update(_row(u))
        return self

    def save(self, ignore_permissions=False, **kw):
        if self.is_new():
            return self.insert()
        set_value(self.name, {"enabled": self.get("enabled", 1),
                              "first_name": self.get("first_name") or "",
                              "last_name": self.get("last_name") or ""})
        return self

    def reload(self):
        self.update(_row(_find(self.name)))
        return self

    def add_roles(self, *roles):
        from django.contrib.auth.models import Group
        u = _find(self.name)
        for r in roles:
            if r == ADMIN_ROLE:
                u.is_superuser = u.is_staff = True
                u.save()
                continue
            g, _ = Group.objects.get_or_create(name=r)
            u.groups.add(g)

    def remove_roles(self, *roles):
        u = _find(self.name)
        for r in roles:
            if r == ADMIN_ROLE:
                continue
            u.groups.remove(*u.groups.filter(name=r))

    def get_password(self, *a, **k):
        return None


def clear_sessions(user=None, keep_current=False, force=False, **kw):
    """End every sign-in session of `user` (frappe.sessions.clear_sessions)."""
    from django.contrib.sessions.models import Session
    u = _find(user)
    if u is None:
        return
    for s in Session.objects.all().iterator():
        try:
            if str(s.get_decoded().get("_auth_user_id")) == str(u.pk):
                s.delete()
        except Exception:
            continue


class RoleDoc(_dict):
    """get_doc({"doctype": "Role", "role_name": ...}) -- a Django group."""

    def insert(self, ignore_permissions=False, **kw):
        from django.contrib.auth.models import Group
        Group.objects.get_or_create(name=self.get("role_name") or self.get("name"))
        return self

    save = insert


def role_exists(name) -> str | None:
    from django.contrib.auth.models import Group
    name = name.get("name") if isinstance(name, dict) else name
    return name if Group.objects.filter(name=name).exists() else None
