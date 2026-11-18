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
  business  the business asked about, or __all__ (for a person who sees only some
            businesses, __all__~<which>: api/businesses.scope_tag)
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

Kept warm whether or not anyone looked lately (warm(), during the WORKDAY hours): the
panels of ALWAYS_PANELS and every set of live figures or panels asked for in the last
week (the "seen" list beside the recent one), each read again only when it is missing,
from another day, or near the end of its STALE_MAX (REWARM). So the first look of the
morning, or after an idle hour, is answered at once, and nothing is re-read while it is
still good to show. (The facts' figures need no warming: the database alone.)

Worked out behind the screens (stored()). Reads too heavy for anyone to wait on -- the
change history (kpi/history.py), the Internal Audit screen's heavy panels, the default
financial statements -- are never made while a person waits. The background job
(background.py: hourly, after the nightly load) works them out and keeps the answer for
BG_KEEP under

    cc:bg:<name>:<business>:<scope>:<what was asked>

with when it was read, which the screen states ("read from ERPNext at"). A look at one
older than BG_REFRESH starts the job again behind it. With nothing kept yet (the first
look after a deploy) the job is started and the part shows the calm "not answered yet"
state (connectors.base.NotWorkedOut), filled at the next refresh. A run that fails is
remembered for BG_RETRY (the part says what happened, as a fresh read would) and never
replaces a good answer. A person's own key ("u:<person>") has answers of their own, as
above, worked out as them.

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

FRESH = {"live": 150, "panels": 120, "cover": 300}
STALE_MAX = 20 * 60
ENGINE_TTL = 6 * 3600
KEEP = STALE_MAX + 60          # how long an answer is kept at all
RECENT = 15 * 60               # what was looked at in the last quarter hour is warmed
POOL = 6
# Kept warm whoever looked: these screens' panels, and whatever was asked for in a week.
ALWAYS_PANELS = ("sales", "fin", "proc", "aud")
SEEN = 7 * 24 * 3600
# Of what was asked for in the week, the screens' figures and panels (not every drawer or
# answer opened), the most recently asked first.
ALWAYS_FNS = ("command_center.kpi.live.compute", "command_center.api.panels.compute")
ALWAYS_MOST = 60
REWARM = STALE_MAX - 5 * 60    # read again before it is too old to show
WORKDAY = (6, 21)              # the hours (server time) the remote reads are kept warm
# Worked out behind the screens (stored()).
BG_KEEP = 26 * 3600
BG_REFRESH = 15 * 60
BG_RETRY = 10 * 60
BG_LOCK = 30 * 60
BG_UNCHANGED = 6 * 3600        # a job that says so skips a business unchanged since

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
    key, sc, tag = _key(kind, business_code, what, info)
    ver = version(business_code)
    day = frappe.utils.today()
    c = frappe.cache()
    entry = c.get_value(key)
    if kind != "engine" and "~" not in tag:
        # Warmed by the scheduler as the platform, which sees every business: never a
        # partial "all", which it would fill with everyone's figures. (The facts' figures
        # are worked out again only when a load moved them, from the database alone.)
        _remember(info["code"], kind, sc, key, fn, kwargs, complete, what)
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


def _key(kind, business_code, what, info=None):
    """(the cache key, whose view, the business tag) an answer is kept under now."""
    info = info or _business(business_code)
    sc = scope(info)
    # "All businesses" for a person who sees only some is theirs alone (scope_tag): never
    # an answer made over every business, nor another customer's "all".
    from command_center.api.businesses import scope_tag
    tag = scope_tag(business_code)
    return (f"cc:fast:{kind}:{tag}:{sc}:{epoch(business_code)}:"
            f"{_digest([what, info['stamp']])}", sc, tag)


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


# --------------------------------------------------------------------------- worked out behind
def background_key(name, business_code, what) -> str:
    """Where a background answer for the business, as the acting person sees it, is kept."""
    from command_center.api.businesses import scope_tag
    info = _business(business_code)
    return (f"cc:bg:{name}:{scope_tag(business_code)}:{scope(info)}:"
            f"{_digest([what, info['stamp']])}")


def person_waits() -> bool:
    """Whether a person is waiting on this work: a web request (or one of its threads,
    parallel()), and not a background job. Outside one -- the scheduler, a job, a
    script -- a background answer not kept yet is worked out there and then."""
    flags = getattr(frappe.local, "flags", None) or {}
    if flags.get("cc_background"):
        return False
    return getattr(frappe.local, "request", None) is not None or bool(flags.get("cc_person_waits"))


def stored(name, business_code, what, fn, kwargs, complete=_always, incremental=False,
           wait=False):
    """The background answer for `fn(**kwargs)`, as the module docstring says, never made
    while the asker waits (unless `wait`, inside a background job):

      {"data", "at", "read_at", ...}   the answer last worked out
      {"failed": {"answer"|"error"}}   the last attempt failed, and nothing is kept
      None                             nothing kept yet: the job was started

    `wait` (or no person waiting, person_waits()): nothing kept yet is worked out here.
    `incremental`: fn is also handed what it worked out last time (previous=)."""
    key = background_key(name, business_code, what)
    c = frappe.cache()
    entry = c.get_value(key)
    if isinstance(entry, dict) and "data" in entry:
        _count(True)
        if time.time() - entry.get("at", 0) >= BG_REFRESH:
            _bg_start(key, fn, kwargs, complete, incremental)
        return entry
    _count(False)
    failed = c.get_value(f"{key}:failed")
    if isinstance(failed, dict):
        return failed
    if wait or not person_waits():
        return _bg_locked(key, fn, kwargs, complete, incremental, blocking=True)
    _bg_start(key, fn, kwargs, complete, incremental)
    return None


def refresh(name, business_code, what, fn, kwargs, complete=_always, incremental=False,
            unchanged_ok=False):
    """The scheduler's run of one background answer (background.py), here and now.
    `unchanged_ok`: skipped while the business's facts have not moved since it was
    worked out, for up to BG_UNCHANGED."""
    key = background_key(name, business_code, what)
    entry = frappe.cache().get_value(key)
    if (unchanged_ok and isinstance(entry, dict) and "data" in entry
            and entry.get("ver") == version(business_code)
            and time.time() - entry.get("at", 0) < BG_UNCHANGED):
        return entry
    return _bg_locked(key, fn, kwargs, complete, incremental, blocking=False)


def reraise(got):
    """A background failure ({"failed": {"error": ...}}), raised again as what it was, so
    the part says what a fresh read would have said."""
    err = (got or {}).get("failed", {}).get("error") or {}
    from command_center.connectors import base
    kind = err.get("kind")
    if kind == "refused":
        raise base.RemotePermissionDenied(err.get("message") or "", doctype=err.get("doctype"),
                                          status=err.get("status"))
    if kind == "down":
        raise base.BusinessSlow(err.get("message") or "not answered")
    if kind == "setup":
        from command_center.kpi.live import NeedsSetup
        raise NeedsSetup(err.get("status") or {})
    raise RuntimeError(err.get("message") or "could not be read")


def _error(e) -> dict:
    from command_center.connectors.base import RemotePermissionDenied
    from command_center.kpi.live import NeedsSetup
    from command_center.kpi.live_departments import is_down
    if isinstance(e, RemotePermissionDenied):
        return {"kind": "refused", "message": str(e), "doctype": getattr(e, "doctype", None),
                "status": getattr(e, "status", None)}
    if isinstance(e, NeedsSetup):
        return {"kind": "setup", "status": e.status}
    if is_down(e):
        return {"kind": "down", "message": str(e)}
    return {"kind": "failed", "message": str(e)}


def _bg_start(key, fn, kwargs, complete, incremental):
    """The job, started behind the asker, once at a time per answer."""
    lock = frappe.cache().lock(f"{key}:busy", timeout=BG_LOCK)
    if not lock.acquire(blocking=False):
        return

    def job():
        try:
            _bg_work(key, fn, kwargs, complete, incremental)
        finally:
            lock.release()
    try:
        frappe.enqueue(job, queue="long")
    except Exception:
        lock.release()


def _bg_locked(key, fn, kwargs, complete, incremental, blocking):
    """The job, here, holding its lock; or, if another holds it, what it left (blocking:
    after waiting for it), or None."""
    lock = frappe.cache().lock(f"{key}:busy", timeout=BG_LOCK)
    if not lock.acquire(blocking=blocking, blocking_timeout=BG_LOCK if blocking else None):
        return None
    try:
        if blocking:
            entry = frappe.cache().get_value(key)
            if isinstance(entry, dict) and "data" in entry:
                return entry  # worked out by the one that held the lock
        return _bg_work(key, fn, kwargs, complete, incremental)
    finally:
        lock.release()


def _bg_work(key, fn, kwargs, complete, incremental):
    """fn, as a background job, kept under `key` if complete -- or the failure, for
    BG_RETRY, beside whatever good answer is already kept."""
    c = frappe.cache()
    flags = frappe.local.flags
    was = flags.get("cc_background")
    flags["cc_background"] = True
    try:
        ver = version(kwargs.get("business_code") or kwargs.get("code"))
        before = c.get_value(key) if incremental else None
        try:
            answer = (fn(**kwargs, previous=(before or {}).get("data")) if incremental
                      else fn(**kwargs))
        except Exception as e:  # noqa: BLE001 -- said on the screen, as a fresh read would
            from command_center.kpi.live_departments import is_down
            if not is_down(e):
                frappe.log_error(title="Command Center background answer",
                                 message=frappe.get_traceback())
            failed = {"failed": {"error": _error(e)}, "at": time.time()}
            c.set_value(f"{key}:failed", failed, expires_in_sec=BG_RETRY)
            return failed
        if not complete(answer):
            failed = {"failed": {"answer": answer}, "at": time.time()}
            c.set_value(f"{key}:failed", failed, expires_in_sec=BG_RETRY)
            return failed
        entry = {"at": time.time(), "read_at": str(frappe.utils.now_datetime())[:19],
                 "ver": ver, "day": frappe.utils.today(), "data": answer}
        c.set_value(key, entry, expires_in_sec=BG_KEEP)
        c.delete_value(f"{key}:failed")
        return entry
    finally:
        flags["cc_background"] = was


# --------------------------------------------------------------------------- warming
def _recent_key(code):
    return f"cc:fast:recent:{code}"


def _path(f) -> str:
    return f"{f.__module__}.{f.__name__}"


def _seen_key(code):
    return f"cc:fast:seen:{code}"


def _spec_id(kind, fn_path, kwargs) -> str:
    return f"{kind}:{_digest([fn_path, kwargs])}"


def _remember(code, kind, sc, key, fn, kwargs, complete, what=None):
    """What was looked at, so the scheduler can read it again after each refresh (the
    last quarter hour's, by key) and keep it warm (the week's, by what was asked). Only
    the platform's own view (local, svc): a person's own key is theirs to use."""
    if sc not in ("local", "svc") or not code:
        return
    c = frappe.cache()
    now = time.time()
    spec = {"asked": now, "kind": kind, "scope": sc, "fn": _path(fn),
            "complete": _path(complete), "kwargs": kwargs}
    sid = _spec_id(kind, spec["fn"], kwargs)
    week = c.get_value(_seen_key(code)) or {}
    if now - week.get(sid, {}).get("asked", 0) >= 600:
        week = {k: v for k, v in week.items() if now - v.get("asked", 0) < SEEN}
        week[sid] = {**spec, "what": what}
        c.set_value(_seen_key(code), week, expires_in_sec=SEEN + 3600)
    seen = c.get_value(_recent_key(code)) or {}
    if now - seen.get(key, {}).get("asked", 0) < 60:
        return
    seen = {k: v for k, v in seen.items() if now - v.get("asked", 0) < RECENT}
    seen[key] = spec
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
    done = set()
    for key, spec in sorted(seen.items(), key=lambda kv: -kv[1].get("asked", 0)):
        if now - spec.get("asked", 0) >= RECENT or spec.get("scope") != sc:
            continue
        if f":{epoch(spec['kwargs'].get('business_code'))}:" not in key:
            continue  # kept under an epoch since retired
        try:
            _recompute(key, frappe.get_attr(spec["fn"]), spec["kwargs"],
                       frappe.get_attr(spec["complete"]))
            done.add(key)
            n += 1
        except Exception:
            frappe.log_error(title=f"Command Center warm {business_code}",
                             message=frappe.get_traceback())
        if _business(business_code)["down"]:
            return n
    return n + _keep_warm(business_code, sc, done)


def _workday() -> bool:
    return WORKDAY[0] <= frappe.utils.now_datetime().hour < WORKDAY[1]


def _always(business_code) -> dict:
    """What is kept warm for the business whoever looked: ALWAYS_PANELS, and the sets
    of screen figures and panels (ALWAYS_FNS) asked for under the platform's view in the
    last week, up to ALWAYS_MOST of them."""
    from command_center.api import panels
    out = {}
    for view in ALWAYS_PANELS:
        what, kwargs = panels.cache_spec(view, business_code)
        fn = _path(panels.compute)
        out[_spec_id("panels", fn, kwargs)] = {
            "kind": "panels", "fn": fn, "complete": _path(panels.complete),
            "kwargs": kwargs, "what": what}
    now = time.time()
    week = sorted((frappe.cache().get_value(_seen_key(business_code)) or {}).items(),
                  key=lambda kv: -kv[1].get("asked", 0))
    for sid, spec in week[:ALWAYS_MOST]:
        if (now - spec.get("asked", 0) < SEEN and spec.get("what") is not None
                and spec.get("fn") in ALWAYS_FNS):
            out.setdefault(sid, spec)
    return out


def _due(entry, day) -> bool:
    """Whether a kept answer needs reading again to stay ready: missing, from another
    day, or near the end of what may be shown. Not merely for a newer version: a look
    is still answered at once from it, and read again behind it (cached())."""
    if not isinstance(entry, dict) or entry.get("day") != day:
        return True
    return time.time() - entry.get("at", 0) >= REWARM


def _keep_warm(business_code, sc, done) -> int:
    """_always(), each read again only when _due(), during the working day. Never under
    a person's own key."""
    n = 0
    if not _workday():
        return n
    day = frappe.utils.today()
    for spec in _always(business_code).values():
        kind = spec.get("kind")
        if kind not in FRESH or spec.get("scope", sc) != sc:
            continue
        kwargs = spec["kwargs"]
        code = kwargs.get("business_code", business_code)
        try:
            key, here, _tag = _key(kind, code, spec["what"])
            if here != sc or key in done:
                continue
            if not _due(frappe.cache().get_value(key), day):
                continue
            ver = version(code)
            _store(key, ver, day, frappe.get_attr(spec["fn"])(**kwargs),
                   frappe.get_attr(spec["complete"]), KEEP)
            done.add(key)
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
    if person_waits():
        conf_flags["cc_person_waits"] = True  # the request itself is not carried over
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
