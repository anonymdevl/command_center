"""insights.compat -- the platform's own runtime, answering to the name `frappe`.

The business logic in command_center/ was written against Frappe and is tested that
way: `import frappe`, frappe.db.get_value, frappe.get_doc, frappe.qb, frappe.cache(),
frappe.session.user. The platform no longer runs on Frappe. Rather than rewrite 13,500
tested lines, install() registers THIS package under the name `frappe` (and the handful
of submodules the code imports), and each call is answered by the platform's own
pieces: Django's ORM and auth, PyPika, Django's cache, a thread pool. No Frappe code is
installed or imported anywhere.

What is deliberately NOT here: anything that only makes sense inside an ERPNext site --
local workflows, local query reports, desk tags. Those paths were for a business living
on the platform's own site, which a standalone platform never has; they raise a clear
error rather than pretending.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import secrets as _secrets
import sys
import types
from contextlib import contextmanager

from insights.compat import qb as qb  # noqa: F401
from insights.compat import utils  # noqa: F401
from insights.compat.db import db  # noqa: F401
from insights.compat.documents import (Document, delete_doc, get_doc, new_doc,  # noqa: F401
                                       rename_doc)
from insights.compat.meta import get_meta  # noqa: F401
from insights.compat.runtime import (cache, defaults, enqueue, get_pdf,  # noqa: F401
                                     get_traceback, log_error, sendmail)
from insights.compat.state import (AuthenticationError, DoesNotExistError,  # noqa: F401
                                   DuplicateEntryError, PermissionError, Redirect,
                                   ValidationError, _dict, local, msgprint, session,
                                   set_user, throw)
from insights.compat.users import clear_sessions, get_roles  # noqa: F401

__version__ = "insights-1.0"
conf = _dict()
flags = _dict()

# --- endpoints ---------------------------------------------------------------------
WHITELIST: dict = {}


def whitelist(allow_guest=False, methods=None, xss_safe=False):
    """Register a function callable as /api/method/<module>.<name>."""
    def wrap(fn):
        WHITELIST[f"{fn.__module__}.{fn.__name__}"] = {
            "fn": fn, "allow_guest": bool(allow_guest),
            "methods": [m.upper() for m in (methods or ["GET", "POST"])]}
        fn.whitelisted = True
        return fn
    return wrap


def get_attr(path: str):
    module, _, name = path.rpartition(".")
    return getattr(importlib.import_module(module), name)


# --- small helpers --------------------------------------------------------------------
def parse_json(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return value
    if isinstance(value, dict):
        return _dict(value)
    return value


def as_json(obj, indent=1, **kw) -> str:
    return json.dumps(obj, indent=indent, default=str, sort_keys=True)


def scrub(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(text or "").replace(" ", "_").replace("-", "_").lower())


def generate_hash(txt=None, length: int = 56) -> str:
    return _secrets.token_hex((length + 1) // 2)[:length]


def get_list(doctype, *args, **kwargs):
    return db.get_all(doctype, *args, **kwargs)


def get_all(doctype, *args, **kwargs):
    return db.get_all(doctype, *args, **kwargs)


def get_value(*args, **kwargs):
    return db.get_value(*args, **kwargs)


def has_permission(doctype=None, ptype="read", doc=None, user=None, **kw) -> bool:
    """The platform's own tables are open to its managers and administrators."""
    from command_center.api.businesses import ALLOWED_ROLES
    return bool(ALLOWED_ROLES.intersection(get_roles(user or local.user)))


def only_for(roles, message=False):
    roles = [roles] if isinstance(roles, str) else list(roles)
    if not set(roles).intersection(get_roles()):
        raise PermissionError("Not permitted")


def get_app_path(app: str, *parts) -> str:
    base = importlib.import_module(app).__file__
    return os.path.join(os.path.dirname(base), *parts)


def get_site_path(*parts) -> str:
    from django.conf import settings
    root = settings.CONFIG.get("files_root") or os.path.join(settings.BASE_DIR, "files")
    return os.path.join(root, *parts)


def _(text, *a, **k):
    return text


def bold(text) -> str:
    return f"<b>{text}</b>"


_config_stamp = [None]


def _refresh_config():
    """Re-read insights.json when it has changed since this process last read it.

    The web workers and the scheduler are separate processes. A setting changed from
    one of them (Settings -> Claude key, Email) is written to the file; every other
    process picks it up at its next unit of work, without a restart. One stat call."""
    try:
        from django.conf import settings
        path = settings.CONFIG_PATH
        stamp = os.stat(path).st_mtime_ns
    except Exception:
        return
    if _config_stamp[0] is None:
        _config_stamp[0] = stamp
        return
    if stamp == _config_stamp[0]:
        return
    try:
        with open(path) as fh:
            fresh = json.load(fh)
    except Exception:
        return  # mid-write or unreadable: keep what we have, try again next time
    _config_stamp[0] = stamp
    # Merged over what this process holds: a changed or added setting takes effect;
    # nothing this process was started with is lost.
    settings.CONFIG.update(fresh)
    conf.update(fresh)


@contextmanager
def run_as(user: str, site: str = "", request=None):
    """One unit of work -- a request, a job, a scheduled run -- as `user`: fresh state,
    one transaction, committed if it finishes, rolled back if it raises."""
    from django.db import close_old_connections
    _refresh_config()
    close_old_connections()
    local.reset(user=user or "Guest", site=site or conf.get("site_name", ""))
    local.request = request
    db.begin()
    ok = False
    try:
        yield
        ok = True
    finally:
        try:
            db.end(ok)
        finally:
            close_old_connections()


# --- local-only paths ------------------------------------------------------------------
def _local_only(*a, **k):
    raise ValidationError("This needs a business living on the platform's own site, "
                          "which a standalone platform does not have.")


class LoginManager:
    """frappe.auth.LoginManager -- login_as(user) on the current request."""

    def login_as(self, user):
        from django.contrib.auth import get_user_model, login
        req = getattr(local, "request", None)
        u = get_user_model().objects.get(username=user)
        if req is not None:
            login(req, u, backend="django.contrib.auth.backends.ModelBackend")
        local.user = user


def _csrf_token():
    req = getattr(local, "request", None)
    if req is None:
        return None
    from django.middleware.csrf import get_token
    return get_token(req)


def _update_site_config(key, value, *a, **k):
    from django.conf import settings
    path = settings.CONFIG_PATH
    data = {}
    if os.path.exists(path):
        with open(path) as fh:
            data = json.load(fh)
    data[key] = value
    tmp = f"{path}.tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    settings.CONFIG[key] = value
    conf[key] = value
    try:
        _config_stamp[0] = os.stat(path).st_mtime_ns  # this process is already current
    except Exception:
        pass


class _RequestView:
    """frappe.request, over the Django request being served (cookies, headers)."""

    def __init__(self, req):
        self._req = req

    @property
    def cookies(self):
        return self._req.COOKIES

    @property
    def headers(self):
        return self._req.headers

    @property
    def method(self):
        return self._req.method

    @property
    def path(self):
        return self._req.path

    def __bool__(self):
        return True


def __getattr__(name):
    """Per-request attributes read off the thread's state, not fixed at import."""
    if name == "form_dict":
        return local.form_dict
    if name == "request":
        req = getattr(local, "request", None)
        return _RequestView(req) if req is not None else None
    raise AttributeError(name)


def _module(name: str, **attrs) -> types.ModuleType:
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m


def install(config: dict):
    """Register this package as `frappe`. Called once, from settings.py."""
    conf.clear()
    conf.update(config or {})
    me = sys.modules[__name__]
    from insights.compat.qb import _Functions
    utils_mod = utils
    utils_mod.html_utils = _module("frappe.utils.html_utils", sanitize_html=utils.sanitize_html)
    utils_mod.pdf = _module("frappe.utils.pdf", get_pdf=get_pdf)
    functions = _module("frappe.query_builder.functions",
                        **{k: getattr(_Functions, k) for k in dir(_Functions) if not k.startswith("_")})
    query_builder = _module("frappe.query_builder", functions=functions,
                            DocType=qb.DocType, Field=qb.Field, Order=qb.Order)
    model = _module("frappe.model")
    model.document = _module("frappe.model.document", Document=Document)
    model.workflow = _module("frappe.model.workflow", apply_workflow=_local_only,
                             get_transitions=_local_only)
    sessions = _module("frappe.sessions", clear_sessions=clear_sessions,
                       get_csrf_token=_csrf_token)
    client = _module("frappe.client",
                     get_list=lambda doctype, **k: db.get_all(doctype, **k),
                     get_count=lambda doctype, filters=None, **k: db.count(doctype, filters),
                     get=lambda doctype, name=None, **k: get_doc(doctype, name).as_dict())
    desk = _module("frappe.desk")
    desk.query_report = _module("frappe.desk.query_report", run=_local_only,
                                get_script=_local_only)
    tag = _module("frappe.desk.doctype.tag.tag", add_tag=lambda *a, **k: None)
    me.sessions = sessions
    me.auth = _module("frappe.auth", LoginManager=LoginManager)
    me.installer = _module("frappe.installer", update_site_config=_update_site_config)
    me.query_builder = query_builder
    me.model = model
    me.client = client
    me.desk = desk
    for name, mod in {
        "frappe": me, "frappe.utils": utils_mod, "frappe.utils.html_utils": utils_mod.html_utils,
        "frappe.utils.pdf": utils_mod.pdf, "frappe.query_builder": query_builder,
        "frappe.query_builder.functions": functions, "frappe.model": model,
        "frappe.model.document": model.document, "frappe.model.workflow": model.workflow,
        "frappe.sessions": sessions, "frappe.auth": me.auth, "frappe.installer": me.installer,
        "frappe.client": client, "frappe.desk": desk, "frappe.desk.query_report": desk.query_report,
        "frappe.desk.doctype": _module("frappe.desk.doctype"),
        "frappe.desk.doctype.tag": _module("frappe.desk.doctype.tag"),
        "frappe.desk.doctype.tag.tag": tag,
    }.items():
        sys.modules[name] = mod
