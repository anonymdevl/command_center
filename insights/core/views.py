"""The platform's web layer: the API the interface calls, its pages, sign-in.

  POST /api/method/<module>.<function>   every call the interface makes, answered as
                                         Frappe did ({"message": ...}, errors as
                                         {"exc_type", "_server_messages"}), so the built
                                         screens work unchanged
  POST /api/method/login | logout        the platform's own sign-in
  /command-center[/...]                  the interface (management only)
  /command-center-login, /management-only, /command-center-access
  /assets/command_center/<path>          the built interface and the app's images
  /branding/<name>                       the product's and the businesses' logos

Each request runs as its person, in one transaction (insights.compat.run_as).
"""

from __future__ import annotations

import datetime
import decimal
import importlib
import inspect
import json
import mimetypes
import os

import jinja2
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import (FileResponse, Http404, HttpResponse, HttpResponseRedirect,
                         JsonResponse)
from django.views.decorators.http import require_http_methods

import frappe  # insights.compat
from insights.compat import WHITELIST, run_as
from insights.compat.state import (AuthenticationError, DoesNotExistError, FrappeError,
                                   PermissionError, Redirect, ValidationError, _dict, local)

WWW = os.path.join(settings.BASE_DIR, "command_center", "www")
_jinja = jinja2.Environment(loader=jinja2.FileSystemLoader(WWW), autoescape=True)


# --- JSON as Frappe sent it ------------------------------------------------------------
class _Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime.datetime, datetime.date, datetime.time)):
            return str(o)
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, (set, frozenset)):
            return list(o)
        if isinstance(o, bytes):
            return o.decode("utf-8", "replace")
        return str(o)


def _json(data, status=200):
    return JsonResponse(data, status=status, encoder=_Encoder, safe=False)


def _error(exc: BaseException, status: int):
    msg = str(exc) or exc.__class__.__name__
    return _json({"exc_type": exc.__class__.__name__,
                  "exception": f"{exc.__class__.__name__}: {msg}",
                  "_server_messages": json.dumps([json.dumps({"message": msg})])}, status)


class _Cookies:
    """frappe.local.cookie_manager: cookies a call sets, applied to its response."""

    def __init__(self):
        self.pending = []

    def set_cookie(self, key, value, expires=None, secure=None, httponly=False, samesite="Lax",
                   max_age=None, **kw):
        self.pending.append((key, value, dict(expires=expires, max_age=max_age, httponly=httponly,
                                              samesite=samesite,
                                              secure=settings.SECURE if secure is None else secure)))

    def delete_cookie(self, key):
        self.pending.append((key, None, {}))

    def apply(self, response):
        for key, value, kw in self.pending:
            if value is None:
                response.delete_cookie(key)
            else:
                response.set_cookie(key, value, **{k: v for k, v in kw.items() if v is not None})
        return response


def _user(request) -> str:
    u = getattr(request, "user", None)
    return u.username if u is not None and u.is_authenticated else "Guest"


def _ip(request) -> str:
    """The visitor's address. Behind this server's nginx (the request comes from the
    loopback) it is the LAST X-Forwarded-For entry -- the one nginx appended. Earlier
    entries are whatever the visitor sent and prove nothing; trusting the first would
    let anyone pick a fresh address for every guess at a password."""
    remote = request.META.get("REMOTE_ADDR") or ""
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd and remote in ("127.0.0.1", "::1"):
        return fwd.split(",")[-1].strip()
    return remote


def _args(request) -> dict:
    args = dict(request.GET.items())
    if request.method == "POST":
        ctype = request.content_type or ""
        if "json" in ctype and request.body:
            try:
                body = json.loads(request.body)
            except ValueError:
                body = {}
            if isinstance(body, dict):
                args.update(body)
        else:
            args.update(request.POST.items())
    args.pop("cmd", None)
    return args


def _resolve(method: str):
    if method not in WHITELIST and method.startswith("command_center."):
        try:
            importlib.import_module(method.rpartition(".")[0])
        except ImportError:
            pass
    return WHITELIST.get(method)


def _call(fn, args: dict):
    sig = inspect.signature(fn)
    if any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values()):
        return fn(**args)
    return fn(**{k: v for k, v in args.items() if k in sig.parameters})


# --- the API -----------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def api_method(request, method):
    if method == "login":
        return api_login(request)
    if method == "logout":
        return api_logout(request)
    entry = _resolve(method)
    if entry is None:
        return _error(DoesNotExistError(f"No such method: {method}"), 404)
    if request.method not in entry["methods"]:
        return _error(PermissionError("Not allowed with this method"), 405)
    user = _user(request)
    if user == "Guest" and not entry["allow_guest"]:
        return _error(AuthenticationError("Sign in to continue."), 401)

    cookies = _Cookies()
    try:
        with run_as(user, request=request):
            local.form_dict = _dict(_args(request))
            local.request_ip = _ip(request)
            local.cookie_manager = cookies
            result = _call(entry["fn"], dict(local.form_dict))
            response = _render_result(result, local.response)
    except PermissionError as e:
        return _error(e, 403)
    except AuthenticationError as e:
        return _error(e, 401)
    except DoesNotExistError as e:
        return _error(e, 404)
    except (ValidationError, FrappeError) as e:
        return _error(e, getattr(e, "http_status_code", 417))
    except Exception as e:  # noqa: BLE001 -- a raw traceback must never reach a screen
        frappe.log_error(title=f"API {method}", message=frappe.get_traceback())
        return _error(Exception("Something went wrong on the platform. It has been "
                                "recorded for the administrator."), 500)
    return cookies.apply(response)


def _render_result(result, resp):
    kind = resp.get("type")
    if kind == "redirect":
        return HttpResponseRedirect(resp.get("location") or "/")
    if kind in ("download", "binary", "pdf"):
        content = resp.get("filecontent") or b""
        name = resp.get("filename") or "download"
        out = HttpResponse(content if isinstance(content, bytes) else str(content).encode(),
                           content_type=resp.get("content_type")
                           or mimetypes.guess_type(name)[0] or "application/octet-stream")
        out["Content-Disposition"] = f'attachment; filename="{name}"'
        return out
    if kind == "page":
        return HttpResponse(resp.get("page") or "", status=int(resp.get("http_status_code") or 200))
    return _json({"message": result})


# --- sign-in -------------------------------------------------------------------------------
LOCK_AFTER, LOCK_MINUTES = 5, 15
# Wider limits as well, so neither one address trying many accounts nor many addresses
# trying one account get far.
LOCK_AFTER_IP, LOCK_AFTER_ACCOUNT = 20, 20


def _fail_keys(request, usr: str) -> tuple:
    ip = _ip(request)
    return (f"login-fail:{usr}:{ip}", f"login-fail-ip:{ip}", f"login-fail-acct:{usr}")


def login_locked(request, usr: str) -> bool:
    from django.core.cache import cache
    pair, ip, acct = (cache.get(k) or 0 for k in _fail_keys(request, usr))
    return pair >= LOCK_AFTER or ip >= LOCK_AFTER_IP or acct >= LOCK_AFTER_ACCOUNT


def login_failed(request, usr: str) -> None:
    from django.core.cache import cache
    for k in _fail_keys(request, usr):
        cache.set(k, (cache.get(k) or 0) + 1, timeout=LOCK_MINUTES * 60)


def login_succeeded(request, usr: str) -> None:
    from django.core.cache import cache
    cache.delete(_fail_keys(request, usr)[0])


def admin_login(request, extra_context=None):
    """The administration's own sign-in page, under the same limits as the platform's."""
    from django.contrib import admin
    if request.method == "POST":
        usr = str(request.POST.get("username") or "").strip().lower()
        if login_locked(request, usr):
            return HttpResponse(f"Too many failed attempts. Try again in {LOCK_MINUTES} minutes.",
                                status=429, content_type="text/plain")
        resp = admin.AdminSite.login(admin.site, request, extra_context)
        if resp.status_code in (301, 302) and request.user.is_authenticated:
            login_succeeded(request, usr)
        else:
            login_failed(request, usr)
        return resp
    return admin.AdminSite.login(admin.site, request, extra_context)


def api_login(request):
    if request.method != "POST":
        return _error(PermissionError("Use POST"), 405)
    args = _args(request)
    usr = str(args.get("usr") or "").strip().lower()
    pwd = str(args.get("pwd") or "")
    if login_locked(request, usr):
        return _json({"message": f"Too many failed attempts. Try again in {LOCK_MINUTES} "
                                 f"minutes."}, 429)
    user = authenticate(request, username=usr, password=pwd)
    if user is None:
        from django.contrib.auth import get_user_model
        alt = get_user_model().objects.filter(email__iexact=usr).first()
        if alt is not None:
            user = authenticate(request, username=alt.username, password=pwd)
    if user is None or not user.is_active:
        login_failed(request, usr)
        return _json({"message": "That email or password is not right."}, 401)
    login_succeeded(request, usr)
    login(request, user)
    return _json({"message": "Logged In", "home_page": "/command-center",
                  "full_name": user.get_full_name() or user.username})


def api_logout(request):
    logout(request)
    return _json({"message": "Logged Out"})


# --- pages ---------------------------------------------------------------------------------
def _page(request, template: str, controller: str):
    """Render command_center/www/<template> with its get_context, as Frappe did."""
    mod = importlib.import_module(f"command_center.www.{controller}")
    ctx = _dict()
    with run_as(_user(request), request=request):
        local.form_dict = _dict(request.GET.items())
        try:
            out = mod.get_context(ctx)
            ctx = out if out is not None else ctx
        except Redirect:
            return HttpResponseRedirect(local.flags.redirect_location or "/")
        html = _jinja.get_template(template).render(**ctx)
    resp = HttpResponse(html)
    # Each page carries the signed-in person's details and the request token of their
    # session: never kept by the browser or anything in between, so it cannot come back
    # stale after a sign-in or sign-out (a stale token refuses every request).
    resp["Cache-Control"] = "no-store"
    return resp


def command_center(request, path=""):
    return _page(request, "command-center.html", "command_center")


def command_center_login(request):
    return _page(request, "command-center-login.html", "command_center_login")


def management_only(request):
    return _page(request, "management-only.html", "management_only")


def command_center_access(request):
    return _page(request, "command-center-access.html", "command_center_access")


def home(request):
    return HttpResponseRedirect("/command-center")


def assets(request, path):
    """The built interface and images (command_center/public). In production nginx
    serves these straight from disk; this is the fallback and the development path."""
    base = os.path.realpath(settings.APP_PUBLIC)
    full = os.path.realpath(os.path.join(base, path))
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        raise Http404()
    response = FileResponse(open(full, "rb"),
                            content_type=mimetypes.guess_type(full)[0] or "application/octet-stream")
    if "/command-center/" in full and os.path.basename(full).count(".") >= 2:
        response["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def branding_file(request, name):
    """A logo set under Settings -> Branding (command_center/branding.py). Only names the
    platform made itself -- kind, content hash, the type the content proved to be -- are
    served, from the files folder only, as that type and nothing else. The name changes
    with the content, so it may be cached for ever. Open to anyone: the sign-in page
    shows the product's logo."""
    from command_center import branding
    full = branding.path_of(name)
    if not full:
        raise Http404()
    response = FileResponse(open(full, "rb"), content_type=branding.TYPES[name.rsplit(".", 1)[1]])
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


def csrf_failure(request, reason=""):
    return _error(PermissionError("Your session token has expired. Reload the page and "
                                  "try again."), 403)
