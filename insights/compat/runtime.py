"""The cache, background jobs, stored values, the error log, mail and PDF.

  frappe.cache()      Django's cache -- a table every web worker and the scheduler
                      share, outside any request's transaction, so a value set by one
                      request (a question's progress, a load lock) is seen at once by
                      the next, as Redis made it in Frappe.
  frappe.enqueue      a thread of this process, running as the person who asked.
  frappe.defaults     small stored values, per user or global (core.DefaultValue).
  frappe.log_error    core.ErrorLog.
  frappe.sendmail     SMTP from the configuration (mail.host, ...); skipped and logged
                      when no mail server is configured.
  get_pdf             wkhtmltopdf, the same renderer Frappe used.
"""

from __future__ import annotations

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


def log_error(title=None, message=None, reference_doctype=None, reference_name=None, **kw):
    """Recorded outside the request's transaction: a rollback after an error must not
    erase the record of it."""
    import logging
    title = str(title or "Error")[:255]
    message = str(message if message is not None else get_traceback())
    logging.getLogger("insights").warning("%s: %s", title, message[:2000])
    try:
        from insights.core.models import ErrorLog
        ErrorLog.objects.create(title=title, error=message)
    except Exception:
        logging.getLogger("insights").exception("could not write the error log")


# --- mail ------------------------------------------------------------------------------
def sendmail(recipients=None, subject="", message="", attachments=None, sender=None, **kw):
    import smtplib
    from email.message import EmailMessage

    from django.conf import settings
    cfg = settings.CONFIG.get("mail") or {}
    if not cfg.get("host"):
        log_error("Command Center: mail not configured",
                  f"Not sent (no mail server configured): {subject} to {recipients}")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender or cfg.get("sender") or cfg.get("user")
    msg["To"] = ", ".join(recipients if isinstance(recipients, (list, tuple)) else [recipients])
    msg.set_content("This message needs an HTML-capable mail reader.")
    msg.add_alternative(message, subtype="html")
    for a in attachments or []:
        data = a.get("fcontent") or b""
        msg.add_attachment(data if isinstance(data, bytes) else str(data).encode(),
                           maintype="application", subtype="octet-stream",
                           filename=a.get("fname") or "attachment")
    with smtplib.SMTP(cfg["host"], int(cfg.get("port", 587)), timeout=30) as s:
        if cfg.get("tls", True):
            s.starttls()
        if cfg.get("user"):
            s.login(cfg["user"], cfg.get("password", ""))
        s.send_message(msg)


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
