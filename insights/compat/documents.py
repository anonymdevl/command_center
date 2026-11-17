"""Documents: frappe.get_doc / new_doc / delete_doc and the Document base class.

A document is a row of one of the platform's tables, with its doctype's controller
(command_center/command_center/doctype/<x>/<x>.py) run around every write: before_insert,
validate, before_save, after_insert, on_update -- the same hooks, in the same order,
as Frappe ran them, so a controller's checks still hold.

Passwords never touch a business table: a Password field's value is encrypted with the
platform's key into core.Secret and read back only by get_password().
"""

from __future__ import annotations

import importlib
import os
import re

from insights.compat import meta as _meta
from insights.compat.state import DoesNotExistError, DuplicateEntryError, _dict, local, throw
from insights.compat.utils import now_datetime, to_plain

STANDARD = ("name", "creation", "modified", "modified_by", "owner", "docstatus", "idx")


# --- secrets ----------------------------------------------------------------------
def _fernet():
    from cryptography.fernet import Fernet
    from django.conf import settings
    key = settings.CONFIG.get("encryption_key")
    if not key:
        throw("The platform has no encryption_key in its configuration, so it cannot "
              "store or read passwords. Add one (insights/README: setup).")
    return Fernet(key.encode() if isinstance(key, str) else key)


def password_fields(doctype: str) -> list:
    try:
        return _meta.get_meta(doctype).password_fields()
    except DoesNotExistError:
        return []


def set_password(doctype, name, fieldname, value):
    from insights.core.models import Secret
    if value in (None, "") or set(str(value)) == {"*"}:
        return
    token = _fernet().encrypt(str(value).encode()).decode()
    Secret.objects.update_or_create(doctype=doctype, docname=name, fieldname=fieldname,
                                    defaults={"value": token})


def get_password(doctype, name, fieldname, raise_exception=True):
    from insights.core.models import Secret
    row = Secret.objects.filter(doctype=doctype, docname=name, fieldname=fieldname).first()
    if not row:
        if raise_exception:
            throw(f"Password not found for {doctype} {name} {fieldname}")
        return None
    return _fernet().decrypt(row.value.encode()).decode()


def delete_passwords(doctype, name):
    from insights.core.models import Secret
    Secret.objects.filter(doctype=doctype, docname=name).delete()


# --- the Document class -------------------------------------------------------------
class Document(_dict):
    """A record, as the business logic and the controllers use it."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        object.__setattr__(self, "flags", _dict())
        object.__setattr__(self, "_before", None)
        object.__setattr__(self, "_new", True)
        if args and isinstance(args[0], dict):
            self.update(args[0])
        elif args:
            self.update(kwargs)
            self["doctype"] = args[0]
            if len(args) > 1 and args[1] is not None:
                self._load(args[1])
                return
        else:
            self.update(kwargs)

    # attribute access: fields as attributes, unknown -> None (as Frappe)
    def __getattr__(self, key):
        if key in ("flags", "_before", "_new"):
            return object.__getattribute__(self, key)
        return self.get(key)

    def __setattr__(self, key, value):
        if key in ("flags", "_before", "_new"):
            object.__setattr__(self, key, value)
        else:
            self[key] = value

    def as_dict(self, **kw):
        return _dict({k: v for k, v in self.items()})

    def is_new(self) -> bool:
        return bool(object.__getattribute__(self, "_new"))

    def get_doc_before_save(self):
        return object.__getattribute__(self, "_before")

    @property
    def meta(self):
        return _meta.get_meta(self.doctype)

    # load / reload
    def _load(self, name):
        from insights.compat.db import model_for, scoped
        model = model_for(self.doctype)
        # Another customer's record is not there for this person (db.business_scope).
        row = scoped(model, model.objects.filter(pk=name)).values().first()
        if row is None:
            raise DoesNotExistError(f"{self.doctype} {name} not found")
        self.update({k: to_plain(v) for k, v in row.items()})
        self._new = False
        self._before = _dict(self.as_dict())

    def reload(self):
        self._load(self.name)
        return self

    # writes
    def run_method(self, method, *args, **kwargs):
        fn = getattr(type(self), method, None)
        if callable(fn):
            return fn(self, *args, **kwargs)
        return None

    def insert(self, ignore_permissions=False, ignore_if_duplicate=False, **kw):
        self._set_name()
        stamp = now_datetime()
        self.setdefault("creation", stamp)
        self["modified"] = stamp
        self.setdefault("owner", local.user)
        self["modified_by"] = local.user
        self.setdefault("docstatus", 0)
        self._check_scope()  # never a record for another customer's business
        self.run_method("before_insert")
        self.run_method("validate")
        self.run_method("before_save")
        from insights.compat.db import db, model_for
        model = model_for(self.doctype)
        if model.objects.filter(pk=self.name).exists():
            if ignore_if_duplicate:
                return self
            raise DuplicateEntryError(f"{self.doctype} {self.name} already exists")
        model(**self._columns(model)).save(force_insert=True)
        self._store_passwords()
        db._wrote()
        self._new = False
        self.run_method("after_insert")
        self.run_method("on_update")
        self._before = _dict(self.as_dict())
        return self

    def save(self, ignore_permissions=False, **kw):
        if self.is_new():
            return self.insert(ignore_permissions=ignore_permissions)
        if self._before is None:
            try:
                before = Document(self.doctype, self.name)
                self._before = _dict(before.as_dict())
            except DoesNotExistError:
                self._before = None
        self["modified"] = now_datetime()
        self["modified_by"] = local.user
        self._check_scope()
        self.run_method("validate")
        self.run_method("before_save")
        from insights.compat.db import db, model_for
        model = model_for(self.doctype)
        cols = self._columns(model)
        cols.pop("name", None)
        model.objects.filter(pk=self.name).update(**cols)
        self._store_passwords()
        db._wrote()
        self.run_method("on_update")
        self._before = _dict(self.as_dict())
        return self

    def db_set(self, fieldname, value=None, update_modified=True, **kw):
        from insights.compat.db import db
        values = fieldname if isinstance(fieldname, dict) else {fieldname: value}
        self.update(values)
        db.set_value(self.doctype, self.name, values, update_modified=update_modified)

    def delete(self, ignore_permissions=False, **kw):
        delete_doc(self.doctype, self.name)

    def get_password(self, fieldname="password", raise_exception=True):
        return get_password(self.doctype, self.name, fieldname, raise_exception)

    def append(self, key, value=None):
        self.setdefault(key, []).append(_dict(value or {}))
        return self[key][-1]

    def get_valid_dict(self):
        return self.as_dict()

    def check_permission(self, ptype="read"):
        """A record of a business that is not one of the acting person's is refused
        (insights/compat/db.py business_scope); everything else is the business logic's
        own checks, as before."""
        self._check_scope()
        return True

    def _check_scope(self):
        code = self.get("business_code")
        if not code or code in ("", "__all__"):
            return
        from insights.compat.db import business_scope
        scope = business_scope()
        if scope is not None and code not in scope:
            from insights.compat.state import PermissionError as _Refused
            raise _Refused("That business is not one of yours on this platform.")

    # internals
    def _columns(self, model) -> dict:
        names = {f.attname for f in model._meta.concrete_fields}
        pw = set(password_fields(self.doctype))
        return {k: v for k, v in self.items() if k in names and k not in pw}

    def _store_passwords(self):
        for f in password_fields(self.doctype):
            if self.get(f):
                set_password(self.doctype, self.name, f, self.get(f))

    def _set_name(self):
        if self.get("name"):
            return
        rule = (self.meta.get("autoname") or "hash").strip()
        if rule.startswith("field:"):
            value = self.get(rule.split(":", 1)[1])
            if not value:
                throw(f"{self.doctype}: {rule.split(':', 1)[1]} is required")
            self["name"] = str(value)
        elif rule.startswith("format:"):
            self["name"] = re.sub(r"\{(\w+)\}", lambda m: str(self.get(m.group(1)) or ""),
                                  rule.split(":", 1)[1])
        else:
            from insights.compat import generate_hash
            self["name"] = generate_hash(length=10)


# --- controllers --------------------------------------------------------------------
_controllers: dict = {}


def controller(doctype: str):
    if doctype in _controllers:
        return _controllers[doctype]
    cls = Document
    try:
        meta = _meta.get_meta(doctype)
        folder = os.path.basename(meta.module_path)
        mod = importlib.import_module(
            f"command_center.command_center.doctype.{folder}.{folder}")
        name = re.sub(r"[^0-9A-Za-z]", "", doctype.title())
        cls = getattr(mod, name, None) or next(
            (v for v in vars(mod).values() if isinstance(v, type) and issubclass(v, Document)
             and v is not Document), Document)
    except (DoesNotExistError, ImportError):
        cls = Document
    _controllers[doctype] = cls
    return cls


def get_doc(arg, name=None, **kw):
    if isinstance(arg, dict):
        doctype = arg.get("doctype")
        if doctype == "User":
            from insights.compat import users
            return users.UserDoc(arg)
        if doctype == "Role":
            from insights.compat import users
            return users.RoleDoc(arg)
        doc = controller(doctype)(arg)
        return doc
    if arg == "User":
        from insights.compat import users
        return users.UserDoc.load(name)
    doc = controller(arg)(arg, name)
    return doc


def new_doc(doctype, **kw):
    return get_doc({"doctype": doctype, **kw})


def delete_doc(doctype, name=None, force=False, ignore_permissions=False, **kw):
    from insights.compat.db import db, model_for
    if doctype == "User":
        from insights.compat import users
        users.delete(name)
        return
    model = model_for(doctype)
    doc = None
    try:
        doc = get_doc(doctype, name)
        doc.run_method("on_trash")
    except DoesNotExistError:
        if not force:
            raise
    model.objects.filter(pk=name).delete()
    delete_passwords(doctype, name)
    db._wrote()
    if doc is not None:
        doc.run_method("after_delete")


def rename_doc(doctype, old, new, force=False, **kw):
    from insights.compat.db import db, model_for
    model = model_for(doctype)
    row = model.objects.filter(pk=old).values().first()
    if row is None:
        raise DoesNotExistError(f"{doctype} {old} not found")
    row["name"] = new
    model(**row).save(force_insert=True)
    model.objects.filter(pk=old).delete()
    from insights.core.models import Secret
    Secret.objects.filter(doctype=doctype, docname=old).update(docname=new)
    db._wrote()
    return new
