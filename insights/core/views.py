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
from command_center.connectors.base import WriteUnconfirmed
from insights.compat import WHITELIST, run_as
from insights.core import timing
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
    stats = timing.Stats()
    response = _answer(entry, method, user, request, cookies, stats)
    timing.finish(stats, method, response)
    return _gzip(request, response)


def _gzip(request, response):
    """An answer of figures or panels sent compressed when the browser accepts it (a
    screen's panels are tens of kilobytes of JSON, a few once compressed). Only JSON:
    downloads are already compressed or are not worth the work."""
    if not str(response.get("Content-Type", "")).startswith("application/json"):
        return response
    from django.middleware.gzip import GZipMiddleware
    return GZipMiddleware(lambda r: response).process_response(request, response)


def _answer(entry, method, user, request, cookies, stats):
    try:
        with run_as(user, request=request):
            local.cc_timing = stats
            local.form_dict = _dict(_args(request))
            local.request_ip = _ip(request)
            local.cookie_manager = cookies
            # A business named by the call must be one of this person's (businesses.
            # require_business; the data layer limits everything else they read). Before
            # the call runs, for every endpoint, so none can forget it.
            if user != "Guest" and local.form_dict.get("business_code"):
                from command_center.api.businesses import require_business
                require_business(str(local.form_dict.get("business_code")))
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
    except WriteUnconfirmed as e:
        # A write the business's ERPNext did not confirm in time: it may have gone
        # through. Said as it is (504, exc_type "WriteUnconfirmed"), never as the general
        # failure -- that would invite pressing again and doing it twice.
        return _error(e, 504)
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
# The password rules as the screens say them (SettingsPeople.jsx RULES, the set-password
# page); the rules themselves are settings.AUTH_PASSWORD_VALIDATORS.
RULES = ("At least 10 characters. Not a common password, not only numbers, and not too "
         "like your name or email.")
# Wider limits as well, so neither one address trying many accounts nor many addresses
# trying one account get far.
LOCK_AFTER_IP, LOCK_AFTER_ACCOUNT = 20, 20


def _fail_keys(request, usr: str) -> tuple:
    ip = _ip(request)
    return (f"login-fail:{usr}:{ip}", f"login-fail-ip:{ip}", f"login-fail-acct:{usr}")


# The counters are rows of core.SignInCounter, each raised by one atomic UPDATE. They
# were cache values read and then written back, and the web server runs eight threads:
# two failures at once each read 4 and wrote 5, so a burst of guesses counted as fewer
# than it was and the lockout came late (17 Nov 2026).
def _counter():
    from insights.core.models import SignInCounter
    return SignInCounter


def _now():
    return datetime.datetime.now()


def fail_count(key: str) -> int:
    """How many failures a counter holds now (0 once its window has passed)."""
    row = _counter().objects.filter(key=key[:255], expires__gt=_now()).values_list("n", flat=True).first()
    return int(row or 0)


def count_failure(key: str, minutes: int = LOCK_MINUTES) -> None:
    """One more failure, atomically: a counter whose window has passed starts again at
    0 (conditionally, so two threads cannot both restart it), then n = n + 1 in the
    database; a counter not there yet is made, and if another thread made it first,
    raised instead."""
    from django.db import IntegrityError, transaction
    from django.db.models import F
    C, key = _counter(), key[:255]
    now = _now()
    until = now + datetime.timedelta(minutes=minutes)
    C.objects.filter(key=key, expires__lte=now).update(n=0, expires=until)
    if C.objects.filter(key=key).update(n=F("n") + 1, expires=until):
        return
    try:
        with transaction.atomic(using="aux"):
            C.objects.create(key=key, n=1, expires=until)
    except IntegrityError:
        C.objects.filter(key=key).update(n=F("n") + 1, expires=until)


def clear_failures(*keys: str) -> None:
    _counter().objects.filter(key__in=[k[:255] for k in keys]).delete()


def login_locked(request, usr: str) -> bool:
    pair, ip, acct = (fail_count(k) for k in _fail_keys(request, usr))
    return pair >= LOCK_AFTER or ip >= LOCK_AFTER_IP or acct >= LOCK_AFTER_ACCOUNT


def login_failed(request, usr: str) -> None:
    for k in _fail_keys(request, usr):
        count_failure(k)


def login_succeeded(request, usr: str) -> None:
    clear_failures(_fail_keys(request, usr)[0])


def admin_login(request, extra_context=None):
    """The administration's own sign-in page, under the same limits as the platform's.
    Every attempt is in the security record (insights/core/security.py); a success is
    recorded by Django's user_logged_in, whichever way the person signed in."""
    from django.contrib import admin

    from insights.core import security
    if request.method == "POST":
        usr = str(request.POST.get("username") or "").strip().lower()[:150]
        if login_locked(request, usr):
            security.record_attempt(request, usr, "blocked", "admin")
            return HttpResponse(f"Too many failed attempts. Try again in {LOCK_MINUTES} minutes.",
                                status=429, content_type="text/plain")
        resp = admin.AdminSite.login(admin.site, request, extra_context)
        if resp.status_code in (301, 302) and request.user.is_authenticated:
            login_succeeded(request, usr)
        else:
            login_failed(request, usr)
            security.record_attempt(request, usr, "failed", "admin",
                                    locked=login_locked(request, usr))
        return resp
    return admin.AdminSite.login(admin.site, request, extra_context)


def api_login(request):
    if request.method != "POST":
        return _error(PermissionError("Use POST"), 405)
    args = _args(request)
    from insights.core import security
    usr = str(args.get("usr") or "").strip().lower()[:150]
    pwd = str(args.get("pwd") or "")
    if login_locked(request, usr):
        security.record_attempt(request, usr, "blocked", "platform")
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
        security.record_attempt(request, usr, "failed", "platform",
                                locked=login_locked(request, usr),
                                note="account deactivated" if user is not None else "")
        return _json({"message": "That email or password is not right."}, 401)
    login_succeeded(request, usr)
    login(request, user)
    return _json({"message": "Logged In", "home_page": "/command-center",
                  "full_name": user.get_full_name() or user.username})


def api_logout(request):
    from insights.core import security
    security.record_sign_out(request)
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


def old_sign_in(request):
    """/command-center-login was the sign-in page's address until 17 Nov 2026: a permanent
    redirect to /sign-in, keeping any ?next=."""
    from django.http import HttpResponsePermanentRedirect
    qs = request.META.get("QUERY_STRING", "")
    return HttpResponsePermanentRedirect("/sign-in" + (f"?{qs}" if qs else ""))


def management_only(request):
    return _page(request, "management-only.html", "management_only")


def command_center_access(request):
    return _page(request, "command-center-access.html", "command_center_access")


def _link_locked(request) -> bool:
    """A set-password link counts its refusals against the address only (the sign-in
    pages' own counter, so Security -> Unlock clears it): never against the account, or
    anyone could lock a person out by forging links in their name."""
    return fail_count(_fail_keys(request, "")[1]) >= LOCK_AFTER_IP


def _link_failed(request) -> None:
    count_failure(_fail_keys(request, "")[1])


@require_http_methods(["GET", "POST"])
def set_password(request):
    """/command-center-set-password?uid=...&token=...: the page the set-password email
    links to (insights/core/invite.py). GET shows the form; the form posts back here
    (Django's CSRF check, the page's token); on success the password is set, every other
    session of theirs ends, they are signed in and go to the platform. A bad, used or
    expired link, and every refusal while the address is locked, is one calm sentence and
    a line in the security record. The password is never in a URL or a log."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.middleware.csrf import get_token

    from command_center.www.command_center import _assets, _brand
    from insights.compat import users as _users
    from insights.core import invite, security
    src = request.POST if request.method == "POST" else request.GET
    uid, token = str(src.get("uid") or "")[:64], str(src.get("token") or "")[:100]
    ctx = {"state": "form", "error": "", "uid": uid, "token": token, "minutes": LOCK_MINUTES,
           "action": invite.PATH, "rules": RULES}
    status = 200
    u = None
    if _link_locked(request):
        ctx["state"], status = "locked", 429
        security.record_password_set(request, "", "blocked")
    else:
        u = invite.person_for(uid, token)
        if u is None:
            _link_failed(request)
            named = invite.user_of(uid)
            security.record_password_set(request, named.username if named else "", "refused",
                                         note="bad, used or expired link")
            ctx["state"], status = "expired", 400
    if u is not None and request.method == "POST":
        pw, pw2 = str(request.POST.get("password") or ""), str(request.POST.get("password2") or "")
        if not pw:
            ctx["error"] = "Type the new password twice."
        elif pw != pw2:
            ctx["error"] = "The two passwords are not the same."
        else:
            try:
                validate_password(pw, user=u)
            except DjangoValidationError as e:
                ctx["error"] = " ".join(e.messages)
        if not ctx["error"]:
            u.set_password(pw)
            u.save(update_fields=["password"])
            _users.clear_sessions(user=u.username)
            security.record_password_set(request, u.username, "done")
            login(request, u)
            response = HttpResponseRedirect("/command-center")
            response["Cache-Control"] = "no-store"
            return response
        status = 400
    if u is not None:
        ctx["email"] = u.email or u.username
    with run_as("Guest", request=request):
        ctx.update(brand=_brand(), assets=_assets())
        html = _jinja.get_template("command-center-set-password.html").render(
            **ctx, csrf=get_token(request))
    resp = HttpResponse(html, status=status)
    resp["Cache-Control"] = "no-store"
    # The link's token never leaves in a Referer: strict-origin sends the site's origin
    # alone. Not no-referrer: under it a browser posts the form with Origin "null", which
    # the request-token check refuses (18 Nov 2026, the first live invite).
    resp["Referrer-Policy"] = "strict-origin"
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp


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
