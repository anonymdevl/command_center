"""Where a request's time goes: the database, the business's ERPNext, or the platform.

Every API call is timed (views.api_method). The time spent in SQL is counted by a
wrapper on every database connection, the time spent waiting on a business's ERPNext
by the connector (connectors/remote.py), and the caches of figures and panels
(command_center/speed.py) count their hits -- all into `frappe.local.cc_timing`, the
request's Stats. The answer carries the breakdown as a `Server-Timing` header (the
browser's developer tools draw it under Timing), and a call slower than SLOW_MS is
logged with it:

    slow API command_center.api.panels.get 2140 ms: db 41 ms/63 q, remote 2050 ms/9
    calls, other 49 ms, cache 0 hit/1 miss

"remote" is the sum over the calls, so when a request reads several at once
(speed.parallel) it can be more than the request's own time. Work a request hands to
its own threads counts to the same request. Nothing is kept: one line in the log and
one header per answer.
"""

from __future__ import annotations

import logging
import threading
import time

SLOW_MS = 500
log = logging.getLogger("insights.timing")


class Stats:
    __slots__ = ("start", "db_ms", "db_n", "remote_ms", "remote_n", "hits", "misses",
                 "_lock")

    def __init__(self):
        self.start = time.perf_counter()
        self.db_ms = self.remote_ms = 0.0
        self.db_n = self.remote_n = self.hits = self.misses = 0
        self._lock = threading.Lock()

    def add_db(self, ms: float):
        with self._lock:
            self.db_ms += ms
            self.db_n += 1

    def add_remote(self, ms: float):
        with self._lock:
            self.remote_ms += ms
            self.remote_n += 1

    def add_cache(self, hit: bool):
        with self._lock:
            if hit:
                self.hits += 1
            else:
                self.misses += 1

    def total_ms(self) -> float:
        return (time.perf_counter() - self.start) * 1000

    def _other(self, total):
        return max(0.0, total - self.db_ms - min(self.remote_ms, total))

    def header(self) -> str:
        total = self.total_ms()
        parts = [f'db;dur={self.db_ms:.1f};desc="{self.db_n} queries"',
                 f'remote;dur={self.remote_ms:.1f};desc="{self.remote_n} ERPNext calls"',
                 f"app;dur={self._other(total):.1f}", f"total;dur={total:.1f}"]
        if self.hits or self.misses:
            parts.append(f'cache;desc="{self.hits} hit, {self.misses} miss"')
        return ", ".join(parts)

    def line(self) -> str:
        total = self.total_ms()
        return (f"{total:.0f} ms: db {self.db_ms:.0f} ms/{self.db_n} q, remote "
                f"{self.remote_ms:.0f} ms/{self.remote_n} calls, other "
                f"{self._other(total):.0f} ms, cache {self.hits} hit/{self.misses} miss")


def current() -> Stats | None:
    from insights.compat.state import local
    return getattr(local, "cc_timing", None)


def _db_wrapper(execute, sql, params, many, context):
    stats = current()
    if stats is None:
        return execute(sql, params, many, context)
    t = time.perf_counter()
    try:
        return execute(sql, params, many, context)
    finally:
        stats.add_db((time.perf_counter() - t) * 1000)


def install():
    """Count SQL time on every database connection, as each is opened."""
    from django.db import connections
    from django.db.backends.signals import connection_created

    def on_connect(sender, connection, **kw):
        if _db_wrapper not in connection.execute_wrappers:
            connection.execute_wrappers.append(_db_wrapper)
    connection_created.connect(on_connect, weak=False, dispatch_uid="insights.timing")
    for c in connections.all(initialized_only=True):
        if _db_wrapper not in c.execute_wrappers:
            c.execute_wrappers.append(_db_wrapper)


def finish(stats: Stats, method: str, response):
    """The header on the answer, and a log line if it was slow."""
    try:
        response["Server-Timing"] = stats.header()
    except Exception:
        pass
    if stats.total_ms() >= SLOW_MS:
        log.warning("slow API %s %s", method, stats.line())
