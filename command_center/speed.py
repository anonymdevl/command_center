"""Screens that answer at once: cached figures and panels, and reads made side by side.

What made a screen slow was waiting on the business's ERPNext: every figure and panel
that reads it live asked it again, one request after another, on every view and every
minute's refresh (insights/bench_screens.py measures it). Three things here, used by
api/kpi.py, api/panels.py and kpi/live.py:

Cached answers (cached()). An answer is kept in the shared cache (a table every web
thread and the scheduler see) under

    cc:fast:<kind>:<business>:<scope>:<epoch>:<what was asked>

  kind      "engine" (figures from the loaded facts), "live" (figures read from the
            business's ERPNext), "panels" (a screen's charts and tables)
  business  the business asked about, or __all__
  scope     whose eyes the business's ERPNext answered: "local" (this site's own),
            "svc" (the platform's read-only account) or "u:<person>" when that person
            has linked their own key for it -- their site's permissions decide what they
            see, so their answers are never handed to anyone else, nor anyone's to them
  epoch     changed by a hard invalidation (scope_changed): a load a person asked for,
            the banner's Retry, a business registered or changed

with the business's data version and the date stored beside the answer:

  engine    exact: used only while the version (bumped by every load that changed a
            fact, ingest/base.py) and the date are the same. Figures from the facts are
            never older than the facts.
  live,     fresh for FRESH seconds and while the version is unchanged; after that, up
  panels    to STALE_MAX old, the kept answer is returned at once and read again in the
            background (stale while revalidate), so the next look has the new one. The
            scheduler re-reads the screens people have been looking at after each
            two-minute refresh (warm()), so a manager almost always meets a fresh one.

Never cached: an answer with a part that failed or could not reach the business, and
anything while the business is marked unreachable -- the "can't reach" state is drawn
from a fresh (and, once known down, immediate) answer every time.

Reads side by side (parallel()). A screen's independent live reads are made at once
on a small pool of threads (POOL), each with its own database connection, closed
after. Not inside a question (the analyst's write guard watches one thread), and never
nested.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import frappe

FRESH = {"live": 150, "panels": 120}
STALE_MAX = 20 * 60
ENGINE_TTL = 6 * 3600
KEEP = STALE_MAX + 60          # how long an answer is kept at all
RECENT = 15 * 60               # what was looked at in the last quarter hour is warmed
POOL = 6

_pool = ThreadPoolExecutor(max_workers=POOL, thread_name_prefix="cc-read")
_tls = threading.local()


# --------------------------------------------------------------------------- versions
def _code(business_code) -> str:
    return business_code if business_code and business_code != "__all__" else "__all__"


def _token(key: str) -> str:
    c = frappe.cache()
    got = c.get_value(key)
    if not got:
        got = uuid.uuid4().hex[:12]
        c.set_value(key, got)
    return got


def version(business_code) -> str:
    """The business's data version: a new value whenever a load changed its facts."""
    return _token(f"cc:fast:ver:{_code(business_code)}")


def epoch(business_code) -> str:
    return _token(f"cc:fast:epoch:{_code(business_code)}")


def data_changed(business_code, hard: bool = False):
    """A load changed the business's facts (or, hard, a person is waiting to see the
    result: kept answers are not used even while a new one is read)."""
    c = frappe.cache()
    for code in {_code(business_code), "__all__"}:
        c.set_value(f"cc:fast:ver:{code}", uuid.uuid4().hex[:12])
        if hard:
            c.set_value(f"cc:fast:epoch:{code}", uuid.uuid4().hex[:12])


def scope_changed(business_code=None):
    """Nothing kept for the business (or for every business) is used again."""
    if business_code and business_code != "__all__":
        data_changed(business_code, hard=True)
        return
    c = frappe.cache()
    for code in frappe.get_all("Connected Business", pluck="business_code") + ["__all__"]:
        c.set_value(f"cc:fast:ver:{code}", uuid.uuid4().hex[:12])
        c.set_value(f"cc:fast:epoch:{code}", uuid.uuid4().hex[:12])


# --------------------------------------------------------------------------- whose view
def _business(business_code) -> dict:
    """The business a live read goes to (the default one for __all__, as _Reader does),
    whether it is this site's own, and whether it is marked unreachable."""
    from command_center.api.businesses import default_business_code
    code = (business_code if business_code and business_code != "__all__"
            else default_business_code())
    row = (frappe.db.get_value("Connected Business", {"business_code": code},
                               ["is_local", "status", "modified"], as_dict=True)
           if code else None) or {}
    return {"code": code, "local": bool(row.get("is_local")) or not code,
            "down": row.get("status") == "Unreachable",
            "stamp": str(row.get("modified") or "")}


def scope(info: dict) -> str:
    """Whose eyes the business's ERPNext answers through (connectors/remote._headers):
    this site's own tables, the platform's read-only account, or the person's own key."""
    if info["local"]:
        return "local"
    user = frappe.session.user
    if frappe.db.exists("Command Center Site Credential",
                        {"user": user, "business_code": info["code"]}):
        return f"u:{user}"
    return "svc"


def _digest(what) -> str:
    return hashlib.sha1(json.dumps(what, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _count(hit: bool):
    stats = getattr(frappe.local, "cc_timing", None)
    if stats is not None:
        try:
            stats.add_cache(hit)
        except Exception:
            pass


# --------------------------------------------------------------------------- cached answers
def _always(answer) -> bool:
    return True


def cached(kind: str, business_code, what, fn, kwargs: dict, complete=_always):
    """fn(**kwargs) for one business, kept as the module docstring says.

    `fn` is a module-level function (it may be run again in the background or by the
    scheduler, with the same kwargs) and `complete(answer)` says whether an answer may
    be kept at all."""
    info = _business(business_code)
    if kind != "engine" and info["down"]:
        # Known down: a fresh answer, which fails fast and says so.
        _count(False)
        return fn(**kwargs)
    sc = scope(info)
    key = (f"cc:fast:{kind}:{_code(business_code)}:{sc}:{epoch(business_code)}:"
           f"{_digest([what, info['stamp']])}")
    ver = version(business_code)
    day = frappe.utils.today()
    c = frappe.cache()
    entry = c.get_value(key)
    if kind != "engine":
        _remember(info["code"], kind, sc, key, fn, kwargs, complete)
    if isinstance(entry, dict) and entry.get("day") == day:
        age = time.time() - entry.get("at", 0)
        if kind == "engine":
            if entry.get("ver") == ver:
                _count(True)
                return entry["data"]
        elif entry.get("ver") == ver and age < FRESH[kind]:
            _count(True)
            return entry["data"]
        elif age < STALE_MAX:
            _count(True)
            _revalidate(key, fn, kwargs, complete)
            return entry["data"]
    _count(False)
    return _store(key, ver, day, fn(**kwargs), complete,
                  ENGINE_TTL if kind == "engine" else KEEP)


def _store(key, ver, day, answer, complete, ttl):
    try:
        if complete(answer):
            frappe.cache().set_value(key, {"at": time.time(), "ver": ver, "day": day,
                                           "data": answer}, expires_in_sec=ttl)
    except Exception:
        frappe.log_error(title="Command Center cache", message=frappe.get_traceback())
    return answer


def _recompute(key, fn, kwargs, complete, business_code=None):
    """fn again, kept under `key` -- if it is still the key the asker would use (the
    version is read before the work, so a load finishing meanwhile is not hidden)."""
    ver = version(kwargs.get("business_code", business_code))
    return _store(key, ver, frappe.utils.today(), fn(**kwargs), complete, KEEP)


def _revalidate(key, fn, kwargs, complete):
    """Read it again in the background, once at a time per answer."""
    lock = frappe.cache().lock(f"{key}:busy", timeout=120)
    if not lock.acquire(blocking=False):
        return

    def job():
        try:
            _recompute(key, fn, kwargs, complete)
        except Exception:
            frappe.log_error(title="Command Center background refresh",
                             message=frappe.get_traceback())
        finally:
            lock.release()
    try:
        frappe.enqueue(job)
    except Exception:
        lock.release()


# --------------------------------------------------------------------------- warming
def _recent_key(code):
    return f"cc:fast:recent:{code}"


def _path(f) -> str:
    return f"{f.__module__}.{f.__name__}"


def _remember(code, kind, sc, key, fn, kwargs, complete):
    """What was looked at, so the scheduler can read it again after each refresh. Only
    the platform's own view (local, svc): a person's own key is theirs to use."""
    if sc not in ("local", "svc") or not code:
        return
    c = frappe.cache()
    seen = c.get_value(_recent_key(code)) or {}
    now = time.time()
    if now - seen.get(key, {}).get("asked", 0) < 60:
        return
    seen = {k: v for k, v in seen.items() if now - v.get("asked", 0) < RECENT}
    seen[key] = {"asked": now, "kind": kind, "scope": sc,
                 "fn": _path(fn), "complete": _path(complete), "kwargs": kwargs}
    c.set_value(_recent_key(code), seen, expires_in_sec=RECENT * 2)


def warm(business_code):
    """After a refresh of the business (api/ingest.poll_peers): read again what people
    looked at in the last quarter hour, so their next look is already fresh. Run by the
    scheduler, as the platform -- only answers kept under the platform's own view."""
    from command_center.kpi import live as _live  # noqa: F401 (registers every figure)
    seen = frappe.cache().get_value(_recent_key(business_code)) or {}
    info = _business(business_code)
    if info["down"]:
        return 0
    sc = scope(info)
    n = 0
    now = time.time()
    for key, spec in sorted(seen.items(), key=lambda kv: -kv[1].get("asked", 0)):
        if now - spec.get("asked", 0) >= RECENT or spec.get("scope") != sc:
            continue
        if f":{epoch(spec['kwargs'].get('business_code'))}:" not in key:
            continue  # kept under an epoch since retired
        try:
            _recompute(key, frappe.get_attr(spec["fn"]), spec["kwargs"],
                       frappe.get_attr(spec["complete"]))
            n += 1
        except Exception:
            frappe.log_error(title=f"Command Center warm {business_code}",
                             message=frappe.get_traceback())
        if _business(business_code)["down"]:
            break
    return n


# --------------------------------------------------------------------------- side by side
@contextlib.contextmanager
def interactive():
    """A screen's reads, which a person is waiting for: the connector asks for their
    first pages without its pause (connectors/remote.py); a load is always paced."""
    was = getattr(frappe.local, "cc_interactive", False)
    frappe.local.cc_interactive = True
    try:
        yield
    finally:
        frappe.local.cc_interactive = was


def parallel(calls: list) -> list:
    """Run each zero-argument callable, at once where that is safe, and return
    [(True, value) or (False, exception)] in the same order.

    Sequential inside a question (ask/agent.py's deadline and write guard belong to one
    thread), inside another parallel(), or for a single call. Each thread acts as the
    same person, counts to the same request's timing, and opens its own database
    connection, closed when it is done. A thread writes nothing to the database: the
    connector's reachability marks are handed back and written here, on the request's
    own transaction (connectors/remote.py)."""
    local = frappe.local
    if (len(calls) < 2 or getattr(local, "cc_deadline", None) or getattr(_tls, "inside", False)
            or not hasattr(local, "reset")):
        return [attempt(c) for c in calls]
    user = frappe.session.user
    site = getattr(local, "site", "")
    stats = getattr(local, "cc_timing", None)
    quick = getattr(local, "cc_interactive", False)
    conf_flags = dict(getattr(local, "flags", {}) or {})
    marks: list = []

    def run(c):
        _tls.inside = True
        local.reset(user=user, site=site)
        local.flags.update(conf_flags)
        local.cc_timing = stats
        local.cc_interactive = quick
        local.cc_defer_marks = marks
        try:
            return attempt(c)
        finally:
            _tls.inside = False
            local.reset()
            try:
                from django.db import connections
                connections.close_all()
            except Exception:
                pass

    futures = [_pool.submit(run, c) for c in calls]
    out = [f.result() for f in futures]
    apply_marks(marks)
    return out


def attempt(c):
    try:
        return (True, c())
    except Exception as e:  # noqa: BLE001 -- the caller decides, as it did in sequence
        e.__cc_traceback__ = frappe.get_traceback()
        return (False, e)


def apply_marks(marks):
    """The reachability marks the threads recorded, written in the order they were made."""
    for name, values in marks:
        try:
            frappe.db.set_value("Connected Business", name, values, update_modified=False)
        except Exception:
            frappe.log_error(title="Command Center reachability", message=frappe.get_traceback())
