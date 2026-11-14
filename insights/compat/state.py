"""Per-request (and per-job) state: who is acting, and what the request carries.

Frappe kept this in frappe.local, a werkzeug LocalProxy. Here it is a thread-local:
each web request is served on one thread from start to finish, and each background
job and scheduled run gets a thread of its own, so a thread-local is exactly the
lifetime the business logic expects.
"""

from __future__ import annotations

import threading


class _dict(dict):
    """A dict whose keys are also attributes -- frappe._dict."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            return None

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        self.pop(key, None)

    def copy(self):
        return _dict(self)


class Local(threading.local):
    """frappe.local. Attributes not set on this thread simply do not exist, as with
    Frappe's own, so `getattr(frappe.local, "x", None)` behaves the same."""

    def __init__(self):
        self.reset()

    def reset(self, user: str = "Guest", site: str = ""):
        keep = ("reset",)
        for k in list(self.__dict__):
            if k not in keep:
                del self.__dict__[k]
        self.user = user
        self.site = site
        self.flags = _dict()
        self.response = _dict()
        self.form_dict = _dict()
        self.request = None
        self.request_ip = None
        self.cookie_manager = None
        self.login_manager = None


local = Local()


class _Session:
    """frappe.session -- only .user is used."""

    @property
    def user(self):
        return getattr(local, "user", "Guest") or "Guest"

    @user.setter
    def user(self, value):
        local.user = value

    @property
    def data(self):
        return _dict()


session = _Session()


def set_user(user: str):
    """Act as `user` for the rest of this thread's work (frappe.set_user)."""
    local.user = user or "Guest"


# --- errors -----------------------------------------------------------------
class FrappeError(Exception):
    http_status_code = 500


class ValidationError(FrappeError):
    """Something the person asked for cannot be done; shown to them in words."""

    http_status_code = 417


class PermissionError(FrappeError):  # noqa: A001 (the name the business logic uses)
    http_status_code = 403


class DoesNotExistError(ValidationError):
    http_status_code = 404


class DuplicateEntryError(ValidationError):
    http_status_code = 409


class AuthenticationError(FrappeError):
    http_status_code = 401


class Redirect(Exception):
    """Raised by a page's get_context after setting local.flags.redirect_location."""


def throw(msg, exc=ValidationError, title=None, **kwargs):
    if isinstance(exc, type) and issubclass(exc, BaseException):
        raise exc(str(msg))
    raise ValidationError(str(msg))


def msgprint(msg, title=None, raise_exception=False, **kwargs):
    if raise_exception:
        throw(msg, raise_exception if isinstance(raise_exception, type) else ValidationError)
    local.__dict__.setdefault("messages", []).append(str(msg))
