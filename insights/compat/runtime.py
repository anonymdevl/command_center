"""The cache, background jobs, stored values, the error log, mail and PDF.

  frappe.cache()      Django's cache -- a table every web worker and the scheduler
                      share, outside any request's transaction, so a value set by one
                      request (a question's progress, a load lock) is seen at once by
                      the next, as Redis made it in Frappe.
  frappe.enqueue      a thread of this process, running as the person who asked.
  frappe.defaults     small stored values, per user or global (core.DefaultValue).
  frappe.log_error    core.ErrorLog.
  frappe.sendmail     SMTP from insights.json's "mail" (Settings -> Email); a message
                      that cannot be sent is logged and raised, never dropped.
  get_pdf             wkhtmltopdf, the same renderer Frappe used.
"""

from __future__ import annotations

import re

import concurrent.futures
import contextlib
import time
import traceback as _tb

from insights.compat.state import local


# --- cache -------------------------------------------------------------------------
class _Cache:
    def _c(self):
        from django.core.cache import caches
        return caches["default"]

    def get_value(self, key, *a, **k):
        return self._c().get(str(key))

    def set_value(self, key, value, expires_in_sec=None, *a, **k):
        self._c().set(str(key), value, timeout=expires_in_sec)

    def delete_value(self, key, *a, **k):
        keys = key if isinstance(key, (list, tuple)) else [key]
        for k_ in keys:
            self._c().delete(str(k_))

    get = get_value

    def set(self, key, value, *a, **k):
        self.set_value(key, value)

    def delete(self, key):
        self.delete_value(key)

    def lock(self, key, timeout=None, blocking_timeout=None):
        """One holder at a time, across workers -- the Redis lock's interface
        (acquire(blocking=False), release(), or `with`). cache.add is atomic."""
        return _Lock(self._c(), f"lock:{key}", int(timeout or 600), blocking_timeout)


class _Lock:
    def __init__(self, cache, name, timeout, blocking_timeout):
        self.cache, self.name, self.timeout = cache, name, timeout
        self.blocking_timeout = blocking_timeout
        self.held = False

    def acquire(self, blocking=True, blocking_timeout=None):
        wait = blocking_timeout if blocking_timeout is not None else self.blocking_timeout
        deadline = time.monotonic() + (float(wait) if wait is not None else 1e9)
        while True:
            if self.cache.add(self.name, 1, timeout=self.timeout):
                self.held = True
                return True
            if not blocking or time.monotonic() >= deadline:
                return False
            time.sleep(0.2)

    def release(self):
        if self.held:
            self.cache.delete(self.name)
            self.held = False

    def __enter__(self):
        if not self.acquire():
            raise LockTimeout(f"{self.name} is held by another process")
        return self

    def __exit__(self, *exc):
        self.release()


class LockTimeout(Exception):
    pass


_cache = _Cache()


def cache():
    return _cache


# --- background jobs ----------------------------------------------------------------
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="cc-job")


def enqueue(method, queue="default", timeout=None, now=False, job_name=None,
            enqueue_after_commit=False, **kwargs):
    """Run `method` (a callable or a dotted path) on a worker thread, as the person
    who asked, with its own transaction."""
    user = local.user
    site = getattr(local, "site", "")
    if isinstance(method, str):
        from insights.compat import get_attr
        func = get_attr(method)
    else:
        func = method
    kwargs.pop("is_async", None)

    def job():
        from insights.compat import run_as
        with run_as(user, site=site):
            func(**kwargs)

    if now:
        return job()
    return _pool.submit(job)


# --- stored values ---------------------------------------------------------------
class _Defaults:
    GLOBAL = "__default"

    def _m(self):
        from insights.core.models import DefaultValue
        return DefaultValue

    def get_defaults_for(self, parent):
        return {r.defkey: r.defvalue for r in self._m().objects.filter(parent=parent)}

    def add_default(self, key, value, parent=None, parenttype=None):
        self._m().objects.create(parent=parent or self.GLOBAL, defkey=key, defvalue=str(value))

    def set_default(self, key, value, parent=None, parenttype=None):
        self._m().objects.filter(parent=parent or self.GLOBAL, defkey=key).delete()
        if value is not None:
            self.add_default(key, value, parent)

    def clear_default(self, key=None, value=None, parent=None, name=None, parenttype=None):
        qs = self._m().objects.filter(parent=parent or self.GLOBAL)
        if key:
            qs = qs.filter(defkey=key)
        if value is not None:
            qs = qs.filter(defvalue=str(value))
        qs.delete()

    def get_global_default(self, key):
        r = self._m().objects.filter(parent=self.GLOBAL, defkey=key).first()
        return r.defvalue if r else None

    def set_global_default(self, key, value):
        self.set_default(key, value)

    def get_user_default(self, key, user=None):
        r = self._m().objects.filter(parent=user or local.user, defkey=key).first()
        return r.defvalue if r else self.get_global_default(key)


defaults = _Defaults()


# --- error log -----------------------------------------------------------------------
def get_traceback(*a, **k) -> str:
    return _tb.format_exc()


# Secrets that may sit in an exception's text: a key in an address (?key=...), an
# Authorization header (token key:secret, Bearer ...), and the shapes of the AI keys.
# Whatever matches is replaced before anything is logged (17 Nov 2026: a Gemini request
# that failed printed its address, key and all, into the error log).
_SECRET_PATTERNS = (
    (re.compile(r"(?i)([?&;](?:key|api_key|apikey|token|access_token|refresh_token|"
                r"client_secret|secret|password|pwd)=)[^&\s'\"<>]+"), r"\1[redacted]"),
    (re.compile(r"(?i)(\btoken\s+)[A-Za-z0-9._\-]{6,}:[A-Za-z0-9._\-]{6,}"), r"\1[redacted]"),
    (re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/\-]{8,}=*"), r"\1[redacted]"),
    (re.compile(r"(?i)(x-goog-api-key['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"), r"\1[redacted]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "sk-ant-[redacted]"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), "AIza[redacted]"),
)
# Configured secrets, matched by value wherever they appear.
_SECRET_CONF = ("command_center_anthropic_key", "command_center_gemini_key", "secret_key",
                "encryption_key")


def redact(text) -> str:
    """`text` with every key, token and secret it carries replaced by [redacted]."""
    out = str(text if text is not None else "")
    if not out:
        return out
    try:
        from insights.compat import conf
        values = [str(conf.get(k) or "") for k in _SECRET_CONF]
        values.append(str((conf.get("mail") or {}).get("password") or "")
                      if isinstance(conf.get("mail"), dict) else "")
        for v in values:
            if len(v) >= 8 and v in out:
                out = out.replace(v, "[redacted]")
    except Exception:
        pass
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def log_error(title=None, message=None, reference_doctype=None, reference_name=None, **kw):
    """Recorded outside the request's transaction: a rollback after an error must not
    erase the record of it. Keys and secrets in the text are redacted first (redact)."""
    import logging
    title = redact(str(title or "Error"))[:255]
    message = redact(str(message if message is not None else get_traceback()))
    logging.getLogger("insights").warning("%s: %s", title, message[:2000])
    try:
        from insights.core.models import ErrorLog
        ErrorLog.objects.create(title=title, error=message)
    except Exception:
        logging.getLogger("insights").exception("could not write the error log")


# --- mail ------------------------------------------------------------------------------
# The "mail" key of insights.json, written by Settings -> Email:
#   {"host": "smtp.example.com", "port": 587, "security": "starttls" | "ssl" | "none",
#    "user": "...", "password": "...", "sender": "reports@example.com",
#    "sender_name": "AI Business Intelligence"}
# Older configurations with only "tls": true/false (STARTTLS or none) still work.
MAIL_ATTEMPT_KEY = "cc:mail:last_attempt"
MAIL_NOT_SENT = "Email not sent"  # the error log title of every message not sent


class MailError(Exception):
    """A message that was not sent; str(e) is the reason in plain words."""


class MailNotConfigured(MailError):
    pass


def mail_config() -> dict:
    """The mail settings, read from insights.json at each send: the web server and the
    scheduler are separate processes, and a change saved in Settings by one must be
    used by the other without a restart."""
    import json

    from django.conf import settings
    cfg = None
    try:
        with open(settings.CONFIG_PATH) as fh:
            cfg = json.load(fh).get("mail")
    except (OSError, ValueError, AttributeError):
        cfg = None
    if cfg is None:
        cfg = settings.CONFIG.get("mail")
    return dict(cfg) if isinstance(cfg, dict) else {}


def mail_security(cfg: dict) -> str:
    s = str(cfg.get("security") or "").strip().lower()
    if s in ("starttls", "ssl", "none"):
        return s
    if cfg.get("ssl"):
        return "ssl"
    return "starttls" if cfg.get("tls", True) else "none"


def mail_port(cfg: dict) -> int:
    try:
        port = int(cfg.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    return port or {"ssl": 465, "starttls": 587, "none": 25}[mail_security(cfg)]


def explain_mail_error(e: Exception, host: str, port: int, security: str) -> str:
    """Why a message was not sent, in words the administrator can act on."""
    import smtplib
    import socket
    import ssl
    where = f"{host} on port {port}"
    match = ("Check that the security setting matches the port: STARTTLS usually uses port "
             "587, SSL uses port 465.")
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return ("The mail server refused the username or password. Check them; some "
                "providers (Gmail, Microsoft 365) need an app password here.")
    if isinstance(e, smtplib.SMTPNotSupportedError):
        if "auth" in str(e).lower():
            return ("The mail server does not accept a username and password on this "
                    "connection. Try STARTTLS or SSL, or leave the username blank if it "
                    "needs none.")
        return f"The mail server at {where} does not offer STARTTLS. {match}"
    if isinstance(e, smtplib.SMTPSenderRefused):
        return (f"The mail server would not send from {e.sender}. Use a From address the "
                f"server allows, usually the username's own address.")
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return ("The mail server refused the address "
                + ", ".join(str(r) for r in (e.recipients or {})) + ".")
    if isinstance(e, ssl.SSLError):
        return f"The secure connection to {where} failed. {match}"
    if isinstance(e, socket.gaierror):
        return f"The mail server {host} could not be found. Check its address."
    if isinstance(e, (socket.timeout, TimeoutError)):
        return (f"The mail server at {where} did not answer in time. Check the address and "
                f"port. {match}")
    if isinstance(e, (ConnectionRefusedError, smtplib.SMTPConnectError)):
        return (f"Could not connect to the mail server at {where}: the connection was "
                f"refused. Check the address and port.")
    if isinstance(e, smtplib.SMTPServerDisconnected):
        return f"The mail server at {where} closed the connection. {match}"
    if isinstance(e, smtplib.SMTPResponseException):
        said = e.smtp_error.decode(errors="replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        return f"The mail server refused the message: {e.smtp_code} {said[:200]}"
    if isinstance(e, OSError):
        return f"Could not connect to the mail server at {where} ({e.strerror or e})."
    return f"The email could not be sent: {str(e)[:200] or type(e).__name__}"


def _record_attempt(ok: bool, subject: str, to: list, error: str | None = None):
    """The last send, kept for Settings -> Email (Notifications). Failures are also in
    the error log, under MAIL_NOT_SENT."""
    try:
        from insights.compat.utils import now_datetime
        cache().set_value(MAIL_ATTEMPT_KEY, {
            "when": now_datetime().strftime("%Y-%m-%d %H:%M:%S"), "ok": bool(ok),
            "subject": str(subject or "")[:200], "to": len(to), "error": error},
            expires_in_sec=None)
    except Exception:
        import logging
        logging.getLogger("insights").exception("could not record the email attempt")


# A message's own HTML is kept for a resend when it carries no attachment and is no
# larger than this; a report's PDF is never kept.
EMAIL_BODY_KEEP = 256 * 1024


def _log_send(ok: bool, subject: str, to: list, error: str | None, message: str,
              attachments, kind: str | None, business: str | None, resend_of=None,
              keep_body: bool = True):
    """One row in the email log (insights.core.models.EmailLog) for every attempt. What
    the message is about comes from the caller's `command_center.mail.about(...)` (or the
    `kind`/`business` given here). A log that cannot be written never stops the send.
    keep_body=False: the message is not kept (a set-password link must not sit in a log),
    so it cannot be resent from the log."""
    try:
        from insights.compat.utils import now_datetime
        from insights.core.models import EmailLog
        ctx = getattr(local, "cc_mail", None) or {}
        n = len(attachments or [])
        body = message or ""
        EmailLog.objects.create(
            at=now_datetime(), kind=str(kind or ctx.get("kind") or "other")[:20],
            status="Sent" if ok else "Failed", recipients=", ".join(to)[:5000],
            subject=str(subject or "")[:255], error=str(error or "")[:2000],
            business_code=str(business or ctx.get("business") or "")[:140],
            body=body if keep_body and not n and len(body.encode()) <= EMAIL_BODY_KEEP else "",
            attachments=n, resend_of=resend_of,
            sent_by=str(getattr(local, "user", "") or "")[:150])
    except Exception:
        import logging
        logging.getLogger("insights").exception("could not write the email log")


def last_mail_attempt() -> dict | None:
    """The last send: what _record_attempt kept, or else the last failure in the log."""
    try:
        got = cache().get_value(MAIL_ATTEMPT_KEY)
        if got:
            return got
        from insights.core.models import ErrorLog
        e = ErrorLog.objects.filter(title__startswith=MAIL_NOT_SENT).order_by("-creation").first()
    except Exception:
        return None
    if e is None:
        return None
    return {"when": e.creation.strftime("%Y-%m-%d %H:%M:%S"), "ok": False, "subject": "",
            "to": 0, "error": (e.error or "").split("\n", 1)[0][:300]}


def sendmail(recipients=None, subject="", message="", attachments=None, sender=None,
             kind=None, business=None, resend_of=None, keep_body=True, **kw):
    """Send now through the configured mail server, or raise MailError with the reason.

    Never silent: a message that is not sent -- email not set up, server refused it --
    is written to the error log (MAIL_NOT_SENT) and raised, so the caller records it
    as failed (a report schedule's last status says why). Every attempt, sent or not,
    is a row in the email log (_log_send; Settings -> Email)."""
    import smtplib
    import ssl
    from email.message import EmailMessage
    from email.utils import formataddr

    if isinstance(recipients, (list, tuple, set)):
        to = [str(r).strip() for r in recipients if r and str(r).strip()]
    else:
        to = [r.strip() for r in str(recipients or "").split(",") if r.strip()]
    cfg = mail_config()
    if not cfg.get("host"):
        why = ("Email is not set up, so nothing was sent. The platform's administrator can "
               "set it up in Settings, under Email.")
        log_error(f"{MAIL_NOT_SENT}: email is not set up",
                  f"{why}\nSubject: {subject}\nTo: {', '.join(to)}")
        _record_attempt(False, subject, to, why)
        _log_send(False, subject, to, why, message, attachments, kind, business, resend_of,
                  keep_body)
        raise MailNotConfigured(why)
    if not to:
        why = "There is no one to send it to."
        _log_send(False, subject, to, why, message, attachments, kind, business, resend_of,
                  keep_body)
        raise MailError(why)

    host, security = str(cfg["host"]).strip(), mail_security(cfg)
    port = mail_port(cfg)
    from_addr = sender or cfg.get("sender") or cfg.get("user")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = (formataddr((str(cfg["sender_name"]), from_addr))
                   if cfg.get("sender_name") and not sender else from_addr)
    msg["To"] = ", ".join(to)
    msg.set_content("This message needs an HTML-capable mail reader.")
    msg.add_alternative(message, subtype="html")
    for a in attachments or []:
        data = a.get("fcontent") or b""
        msg.add_attachment(data if isinstance(data, bytes) else str(data).encode(),
                           maintype="application", subtype="octet-stream",
                           filename=a.get("fname") or "attachment")
    try:
        if security == "ssl":
            s = smtplib.SMTP_SSL(host, port, timeout=30, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(host, port, timeout=30)
        with s:
            if security == "starttls":
                s.starttls(context=ssl.create_default_context())
            if cfg.get("user"):
                s.login(str(cfg["user"]), str(cfg.get("password") or ""))
            s.send_message(msg)
    except Exception as e:
        why = explain_mail_error(e, host, port, security)
        log_error(f"{MAIL_NOT_SENT}: {str(subject)[:150]}",
                  f"{why}\nTo: {', '.join(to)}\n\n{get_traceback()}")
        _record_attempt(False, subject, to, why)
        _log_send(False, subject, to, why, message, attachments, kind, business, resend_of,
                  keep_body)
        raise MailError(why) from e
    _record_attempt(True, subject, to)
    _log_send(True, subject, to, None, message, attachments, kind, business, resend_of,
              keep_body)


# --- pdf ---------------------------------------------------------------------------
def get_pdf(html: str, options: dict | None = None, **kw) -> bytes:
    """wkhtmltopdf, as Frappe's get_pdf used, with the same options."""
    import shutil
    import subprocess
    import tempfile
    exe = shutil.which("wkhtmltopdf")
    if not exe:
        from insights.compat.state import throw
        throw("PDF export needs wkhtmltopdf on the server (apt install wkhtmltopdf).")
    args = [exe, "--quiet", "--encoding", "utf-8"]
    for k, v in (options or {}).items():
        flag = "--" + str(k).lstrip("-")
        if v is None or v is True or v == "":
            args.append(flag)
        elif v is False:
            continue
        else:
            args += [flag, str(v)]
    with tempfile.TemporaryDirectory() as d:
        src, out = f"{d}/in.html", f"{d}/out.pdf"
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(html)
        subprocess.run(args + [src, out], check=True, timeout=120)
        with open(out, "rb") as fh:
            return fh.read()
