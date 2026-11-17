"""A link by email that lets someone set their own password (Settings -> User Management).

  link(u)         the absolute address of the set-password page for `u`: the configured
                  host_name (deploy/domain.sh sets https://insights.ultrasoft-systems.com),
                  else the request's own host (insights.compat.utils.get_url)
  person_for()    the person a link is for, if it still works; otherwise None
  send(u, me)     email the link; {"ok", "says"} -- never "sent" when it was not

The token is Django's PasswordResetTokenGenerator with a salt of our own, so it is good
for nothing else. It is a hash of the person's password hash, their last sign-in and the
time it was made: it stops working once the password changes (or they sign in), and
after settings.PASSWORD_RESET_TIMEOUT (72 hours), whichever is first. Nothing about it
is stored, and the email that carries it is logged without its body
(runtime.sendmail(keep_body=False)), so the link is never in a log.

The page itself is views.set_password; who may send a link is
platform_settings.send_set_password_link (the reset-password rules).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

import frappe  # insights.compat

PATH = "/command-center-set-password"


class _Tokens(PasswordResetTokenGenerator):
    key_salt = "insights.core.invite.set-password"


TOKENS = _Tokens()


def hours() -> int:
    return int(settings.PASSWORD_RESET_TIMEOUT) // 3600


def _name(u) -> str:
    return (f"{u.first_name} {u.last_name}".strip()) or u.username


def link(u) -> str:
    query = urlencode({"uid": urlsafe_base64_encode(force_bytes(u.pk)),
                       "token": TOKENS.make_token(u)})
    return frappe.utils.get_url(f"{PATH}?{query}")


def user_of(uid):
    """The account a link's uid names, whether or not its token is good."""
    from django.contrib.auth import get_user_model
    try:
        pk = force_str(urlsafe_base64_decode(str(uid or "")[:64]))
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError):
        return None
    if not pk.isdigit():
        return None
    return get_user_model().objects.filter(pk=int(pk)).first()


def person_for(uid, token):
    """The person, if the link is theirs, still unused, not expired, and they are active."""
    u = user_of(uid)
    if u is None or not u.is_active:
        return None
    if not TOKENS.check_token(u, str(token or "")[:100]):
        return None
    return u


def email_html(u, me, url: str, new: bool) -> str:
    from command_center import branding
    esc = frappe.utils.escape_html
    product = branding.branding()["product"]
    who = f"{_name(me)} ({me.email or me.username})"
    hello = f"Hello {esc(u.first_name)}," if u.first_name else "Hello,"
    why = (f"{esc(who)} has invited you to {esc(product)}." if new else
           f"{esc(who)} has sent you a link to set your password for {esc(product)}.")
    return branding.email_html(
        f"<p>{hello}</p>"
        f"<p>{why}</p>"
        f"<p>Your sign-in email is <b>{esc(u.email or u.username)}</b>.</p>"
        f"<p style=\"margin:22px 0\"><a href=\"{esc(url)}\" style=\"display:inline-block;"
        "padding:11px 20px;background:#1d2026;color:#ffffff;text-decoration:none;"
        "border-radius:6px;font-weight:600\">Set Your Password</a></p>"
        "<p style=\"font-size:13px;color:#646973\">Or copy this address into your browser:"
        f"<br><span style=\"word-break:break-all\">{esc(url)}</span></p>"
        f"<p>The link expires in {hours()} hours and works once.</p>"
        "<p>If you weren't expecting this, ignore it: nothing changes until a password is "
        "set.</p>")


def send(u, me, new: bool = False) -> dict:
    """Email `u` a set-password link from `me`. The caller has checked `me` may."""
    from command_center import branding
    from insights.compat import runtime
    from insights.core import security
    to = u.email or u.username
    if not u.is_active:
        return {"ok": False, "says": f"{_name(u)} is deactivated. Reactivate them first."}
    product = branding.branding()["product"]
    try:
        runtime.sendmail(kind="invite", recipients=[to],
                         subject=f"Set your password for {product}",
                         message=email_html(u, me, link(u), new), keep_body=False)
    except runtime.MailError as e:
        security.record_link(u.username, "failed", actor=me.username, note=str(e))
        return {"ok": False, "says": f"No link was sent. {e} You can set a password for them "
                                     f"instead, and tell them it yourself."}
    security.record_link(u.username, "sent", actor=me.username)
    return {"ok": True, "says": f"A link was sent to {to}. It works once and expires in "
                                f"{hours()} hours."}
