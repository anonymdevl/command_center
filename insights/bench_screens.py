"""How long each designed screen takes to fill, against a slow ERPNext.

    INSIGHTS_CONFIG=$PWD/insights.json DJANGO_SETTINGS_MODULE=insights.settings \\
        .venv-platform/bin/python manage.py test insights.bench_screens

Not part of `manage.py test insights` (the name does not start with "test"): it is a
measurement, not a check. The fake ERPNext of insights/tests.py answers every read after
BENCH_LATENCY_MS (default 150-300 ms, like a business's server across the internet), the
connector's own pause between pages is left in, and each screen's calls are made the way
the interface makes them (LegacyView.jsx): the figures it names, its panels, its work
queue, its alerts, Home's two lists.

For each screen it prints the slowest of its calls (the browser makes them at once, so
the slowest is when the screen is filled) and their sum, three ways:
  cold   nothing cached (the first screen of the day)
  warm   the same screen again a few seconds later (a revisit, the minute's refresh)
  polled after the two-minute refresh of the business has run (scheduler)
The breakdown from Server-Timing (database / ERPNext / platform) is printed per call,
and BENCH_OUT=<file> writes everything as JSON.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TransactionTestCase

from insights import tests as T

_sleep = time.sleep  # the fake waits for real, whatever a test does to time.sleep

VIEWS = ["command", "brief", "myday", "ops", "health", "approvals", "delegation", "ask",
         "reports", "risk", "sales", "proc", "inv", "eng", "cx", "fin", "hr", "it", "aud"]
PANEL_VIEWS = {"sales", "proc", "inv", "eng", "cx", "fin", "hr", "it", "aud", "risk", "ops"}
WORK_VIEWS = {"myday", "approvals", "delegation"}
ALERT_VIEWS = {"command", "brief", "health", "risk"}
CODE = "test_medical_ltd"


class SlowERPNext(T.FakeERPNext):
    def __init__(self, low_ms=150, high_ms=300):
        super().__init__()
        self.low, self.high = low_ms / 1000, high_ms / 1000
        self.on = False

    def answer(self, m, p):
        if self.on:
            _sleep(random.uniform(self.low, self.high))
        return super().answer(m, p)


def _keys():
    """Each screen's figure keys, as frontend/src/legacy/hydrate.js keysFor() names them."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = (f'import {{ keysFor }} from "{root}/frontend/src/legacy/hydrate.js";'
           f"const v = {json.dumps(VIEWS)}; const o = {{}};"
           "for (const k of v) o[k] = keysFor(k); console.log(JSON.stringify(o));")
    out = subprocess.run(["node", "--input-type=module", "-e", src], capture_output=True,
                         text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def _calls(view, keys):
    out = []
    if keys:
        out.append(("command_center.api.kpi.get", {"keys": keys, "business_code": CODE}))
    if view in PANEL_VIEWS:
        out.append(("command_center.api.panels.get", {"view": view, "business_code": CODE}))
    if view in WORK_VIEWS:
        out.append(("command_center.api.work.summary", {"business_code": CODE}))
    if view in ALERT_VIEWS:
        out.append(("command_center.api.alerts.open_alerts", {"business_code": CODE}))
    if view == "command":
        out.append(("command_center.api.home.debtors", {"business_code": CODE, "mode": "all"}))
        out.append(("command_center.api.home.top_customers", {"business_code": CODE}))
    if view == "health":
        out.append(("command_center.api.ingest.history", {"business_code": CODE}))
    if view == "reports":
        out.append(("command_center.api.reports.schedules", {"business_code": CODE}))
    return out


def _timing(header: str) -> dict:
    got = {}
    for part in (header or "").split(","):
        m = re.match(r"\s*(\w+);dur=([\d.]+)", part)
        if m:
            got[m.group(1)] = float(m.group(2))
    return got


class ScreenBench(TransactionTestCase):
    databases = {"default", "aux"}

    def setUp(self):
        from django.conf import settings
        from cryptography.fernet import Fernet
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        lo, _, hi = os.environ.get("BENCH_LATENCY_MS", "150-300").partition("-")
        self.fake = SlowERPNext(int(lo), int(hi or lo))
        self.patches = [mock.patch("requests.get", self.fake("GET")),
                        mock.patch("requests.post", self.fake("POST"))]
        if os.environ.get("BENCH_N"):
            self.patches.append(mock.patch.object(T, "N", int(os.environ["BENCH_N"])))
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _screen(self, c, view, keys):
        rows = []
        for method, args in _calls(view, keys):
            n0 = len(self.fake.calls)
            t = time.perf_counter()
            r = c.post(f"/api/method/{method}", json.dumps(args), content_type="application/json")
            ms = (time.perf_counter() - t) * 1000
            self.assertEqual(r.status_code, 200, f"{view} {method}: {r.content[:300]!r}")
            rows.append({"method": method.rsplit(".", 2)[-2] + "." + method.rsplit(".", 1)[-1],
                         "ms": round(ms), "bytes": len(r.content),
                         "erp_calls": len(self.fake.calls) - n0,
                         **{k: round(v) for k, v in _timing(r.get("Server-Timing")).items()}})
        return rows

    def test_screens(self):
        from django.core.cache import cache

        from command_center import install
        from command_center.api import ingest
        from insights.compat import run_as

        with mock.patch("time.sleep", lambda s: None):
            with run_as("Administrator"):
                install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
                ingest.run_all(full=True)
        U = get_user_model()
        m = U.objects.create_user("manager@test.com", "manager@test.com", "a-long-test-pass-9")
        m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        c = Client()
        self.assertTrue(c.login(username="manager@test.com", password="a-long-test-pass-9"))
        keys = _keys()

        self.fake.on = True
        result = {}
        cache.clear()
        for view in VIEWS:
            if not _calls(view, keys.get(view)):
                continue
            cold = self._screen(c, view, keys.get(view))
            warm = self._screen(c, view, keys.get(view))
            result[view] = {"cold": cold, "warm": warm}
        # The two-minute refresh, then every screen again: what a manager meets after it.
        t = time.perf_counter()
        with run_as("Administrator"):
            from command_center.api import changes
            changes.refresh_peers()
        poll_ms = round((time.perf_counter() - t) * 1000)
        for view in result:
            result[view]["polled"] = self._screen(c, view, keys.get(view))

        lat = os.environ.get("BENCH_LATENCY_MS", "150-300")
        print(f"\nscreen bench: ERPNext latency {lat} ms per request, "
              f"N={T.N} rows per doctype; refresh_peers took {poll_ms} ms\n")
        print(f"{'screen':<11}{'cold max':>10}{'cold sum':>10}{'warm max':>10}"
              f"{'polled max':>12}{'ERP calls':>11}")
        tot = {"cold": 0, "warm": 0, "polled": 0}
        for view, r in result.items():
            mx = {k: max(x["ms"] for x in r[k]) for k in ("cold", "warm", "polled")}
            for k in tot:
                tot[k] += mx[k]
            print(f"{view:<11}{mx['cold']:>10}{sum(x['ms'] for x in r['cold']):>10}"
                  f"{mx['warm']:>10}{mx['polled']:>12}{sum(x['erp_calls'] for x in r['cold']):>11}")
        print(f"{'all':<11}{tot['cold']:>10}{'':>10}{tot['warm']:>10}{tot['polled']:>12}")
        print("\nper call, cold: ms (db / remote / app) [ERPNext calls] bytes")
        for view, r in result.items():
            print(f"  {view}: " + "; ".join(
                f"{x['method']} {x['ms']} ({x.get('db', 0)}/{x.get('remote', 0)}/{x.get('app', 0)})"
                f" [{x['erp_calls']}] {x['bytes']}" for x in r["cold"]))
        if os.environ.get("BENCH_OUT"):
            with open(os.environ["BENCH_OUT"], "w") as fh:
                json.dump({"latency_ms": lat, "n": T.N, "poll_ms": poll_ms, "screens": result},
                          fh, indent=1)
