"""The screens' speed, without giving up a figure's truth (command_center/speed.py):

    .venv-platform/bin/python manage.py test insights.test_speed

Kept answers are worked out again when a load changes the facts; they never cross
businesses or whose eyes the business's ERPNext answered through; reads made side by
side give exactly what reads made one after another give; a business known to be down
is said to be down at once, kept answers or not; the scheduler's refresh leaves the
screens people look at answered without a wait; and a kept answer past its freshness is
returned at once and read again behind it.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
import types
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TransactionTestCase

from insights import tests as T

_sleep = time.sleep
A, B = "test_medical_ltd", "second_clinic"
_scale = threading.local()
_value = T._value


def _scaled(field, i, doctype):
    """The fake's values, times the factor of the site (and key) being read."""
    v = _value(field, i, doctype)
    k = getattr(_scale, "k", 1)
    return round(v * k, 2) if isinstance(v, float) and k != 1 else v


class TwoSites(T.FakeERPNext):
    """erp.test as the fake answers it; erp2.test three times as large; and through a
    person's own key ("token own:...") five times as large -- so whose answer a screen
    shows can be told from its figures."""

    def __init__(self, latency=0.0):
        super().__init__()
        self.latency = latency
        self.inflight = self.most = 0
        self.lock = threading.Lock()

    def __call__(self, method_name):
        inner = super().__call__(method_name)

        def call(url, headers=None, **kw):
            _scale.k = (3 if "erp2.test" in url else 1) * (
                5 if "token own:" in str((headers or {}).get("Authorization")) else 1)
            with self.lock:
                self.inflight += 1
                self.most = max(self.most, self.inflight)
            try:
                if self.latency:
                    _sleep(self.latency)
                return inner(url, headers=headers, **kw)
            finally:
                with self.lock:
                    self.inflight -= 1
                _scale.k = 1
        return call


class _Frozen(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 15, 9, 30, 0)


class Speed(TransactionTestCase):
    databases = {"default", "aux"}

    def setUp(self):
        from cryptography.fernet import Fernet
        from django.conf import settings
        from django.core.cache import cache
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        self.fake = TwoSites()
        # The fake's "modified" stamps are fixed, so two reads of one record agree.
        frozen = types.SimpleNamespace(datetime=_Frozen, timedelta=dt.timedelta, date=dt.date)
        self.patches = [mock.patch("requests.get", self.fake("GET")),
                        mock.patch("requests.post", self.fake("POST")),
                        mock.patch("time.sleep", lambda s: None),
                        mock.patch.object(T, "_value", _scaled),
                        mock.patch.object(T, "dt", frozen)]
        for p in self.patches:
            p.start()
        cache.clear()
        from command_center import install
        from command_center.api import ingest
        from insights.compat import run_as
        with run_as("Administrator"):
            install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
            install.register_business("Second Clinic", "https://erp2.test", "key", "s3cret")
            ingest.run_all(full=True)
        U = get_user_model()
        self.clients = {}
        for who in ("one@test.com", "two@test.com"):
            u = U.objects.create_user(who, who, "a-long-test-pass-9")
            u.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
            c = Client()
            self.assertTrue(c.login(username=who, password="a-long-test-pass-9"))
            self.clients[who] = c
        self.c = self.clients["one@test.com"]

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _post(self, method, c=None, **args):
        r = (c or self.c).post(f"/api/method/command_center.api.{method}", json.dumps(args),
                               content_type="application/json")
        self.assertEqual(r.status_code, 200, f"{method}: {r.content[:300]!r}")
        return r.json()["message"], r

    def _figure(self, key, code, c=None):
        got, r = self._post("kpi.get", c=c, keys=[key], business_code=code)
        return got[key]["value"], r

    def _calls(self, fn):
        n = len(self.fake.calls)
        out = fn()
        return out, len(self.fake.calls) - n

    # ------------------------------------------------------------------ invalidation
    def test_new_data_is_worked_out_again(self):
        from command_center.api import ingest
        from insights.compat import run_as
        before, _ = self._figure("ar_open_invoices", A)
        again, r = self._figure("ar_open_invoices", A)
        self.assertEqual(before, again)
        self.assertIn('cache;desc="1 hit', r["Server-Timing"], "the second look is kept")
        # The business's invoices change; the two-minute refresh loads them.
        with mock.patch.object(T, "_value", lambda f, i, d: (_scaled(f, i, d) * 2
                                                             if f == "outstanding_amount"
                                                             else _scaled(f, i, d))):
            with run_as("Administrator"):
                ingest.poll_peers()
        after, r = self._figure("ar_open_invoices", A)
        self.assertAlmostEqual(float(after), 2 * float(before), places=0)
        self.assertIn('cache;desc="0 hit', r["Server-Timing"], "worked out again, not kept")

    def test_nothing_changed_nothing_recomputed(self):
        import contextlib

        from command_center.api import ingest
        from command_center.ingest.registry import INGESTORS
        from insights.compat import run_as
        self._figure("ar_open_invoices", A)
        # A refresh that brought nothing new keeps the figures. (A fact rebuilt whole
        # says "unchanged" with None.)
        with contextlib.ExitStack() as stack:
            for cls in INGESTORS.values():
                nothing = None if cls.whole else []
                stack.enter_context(mock.patch.object(
                    cls, "extract", lambda *a, _n=nothing, **k: _n))
                stack.enter_context(mock.patch.object(cls, "withdrawn", lambda *a, **k: set()))
            with run_as("Administrator"):
                ingest.poll_peers()
        _, r = self._figure("ar_open_invoices", A)
        self.assertIn('cache;desc="1 hit', r["Server-Timing"])

    def test_a_refresh_asked_for_is_never_answered_from_before(self):
        before, _ = self._figure("po_drafts_value", A)
        with mock.patch.object(T, "_value", lambda f, i, d: (_scaled(f, i, d) * 2
                                                             if f == "base_grand_total"
                                                             else _scaled(f, i, d))):
            kept, _ = self._figure("po_drafts_value", A)
            self.assertEqual(kept, before, "read from ERPNext moments ago: kept")
            self._post("reach.retry", business_code=A)  # the banner's Retry
            after, r = self._figure("po_drafts_value", A)
        self.assertAlmostEqual(float(after), 2 * float(before), places=0)
        self.assertIn('cache;desc="0 hit', r["Server-Timing"])

    # ------------------------------------------------------------------ never crossed
    def test_businesses_and_people_never_see_each_others(self):
        a_inv, _ = self._figure("ar_open_invoices", A)
        b_inv, _ = self._figure("ar_open_invoices", B)
        self.assertAlmostEqual(float(b_inv), 3 * float(a_inv), places=0)
        a_po, _ = self._figure("po_drafts_value", A)
        b_po, _ = self._figure("po_drafts_value", B)
        self.assertAlmostEqual(float(b_po), 3 * float(a_po), places=0)
        self.assertEqual(self._figure("ar_open_invoices", A)[0], a_inv)
        pa, _ = self._post("panels.get", view="proc", business_code=A)
        pb, _ = self._post("panels.get", view="proc", business_code=B)
        self.assertNotEqual(json.dumps(pa["panels"]), json.dumps(pb["panels"]))
        self.assertEqual(self._post("panels.get", view="proc", business_code=A)[0], pa)

        # one@ links their own key for A: their site answers them through it, and what it
        # answers them is theirs alone -- in both orders.
        own, _ = self._post("credentials.link_account", business_code=A, api_key="own",
                            api_secret="their-secret")
        two = self.clients["two@test.com"]
        mine, _ = self._figure("po_drafts_value", A)
        theirs, _ = self._figure("po_drafts_value", A, c=two)
        self.assertAlmostEqual(float(mine), 5 * float(a_po), places=0)
        self.assertEqual(theirs, a_po)
        self.assertEqual(self._figure("po_drafts_value", A)[0], mine)
        self.assertEqual(self._figure("po_drafts_value", A, c=two)[0], a_po)
        p_mine, _ = self._post("panels.get", view="proc", business_code=A)
        p_theirs, _ = self._post("panels.get", view="proc", business_code=A, c=two)
        self.assertNotEqual(json.dumps(p_mine["panels"]), json.dumps(p_theirs["panels"]))
        self.assertEqual(p_theirs, pa)

    # ------------------------------------------------------------------ side by side
    def test_side_by_side_is_the_same_as_one_after_another(self):
        from command_center import speed
        from command_center.api import panels
        from command_center.kpi import live
        from insights.compat import run_as

        def norm(x):
            return re.sub(r"read from ERPNext at \d\d:\d\d", "read from ERPNext at -",
                          json.dumps(x, sort_keys=True, default=str))

        def seq(calls):
            return [speed.attempt(c) for c in calls]

        self.fake.latency = 0.02
        keys = sorted(live.LIVE)
        from command_center.recommend import engine
        for code in (A, B):
            # The finding boxes lead with the business's recommendations. Worked out first,
            # so both readings below see the same stored ones: otherwise a refresh that falls
            # inside the first (side-by-side) reading -- likelier on a busy machine -- makes
            # the two differ for a reason that has nothing to do with reading side by side.
            engine.ensure_fresh(code, force=True)
            with run_as("one@test.com"):
                side = {v: panels.compute(v, code) for v in panels.SCREENS}
                figs = live.compute(keys, code)
            most = self.fake.most
            self.fake.most = 0
            with mock.patch.object(speed, "parallel", seq), run_as("one@test.com"):
                one = {v: panels.compute(v, code) for v in panels.SCREENS}
                figs1 = live.compute(keys, code)
            self.assertGreater(most, 1, "the reads were made side by side")
            self.assertEqual(self.fake.most, 1, "and here one after another")
            for v in panels.SCREENS:
                self.assertEqual(norm(side[v]), norm(one[v]), f"{code} {v}")
                self.assertFalse(side[v]["_failed"], f"{code} {v}: {side[v]['panels']}")
            self.assertEqual(norm(figs), norm(figs1), code)

    # ------------------------------------------------------------------ can't reach
    def test_known_down_is_said_at_once_even_with_kept_answers(self):
        from insights.core.models import ConnectedBusiness
        kept, _ = self._post("panels.get", view="proc", business_code=A)
        self.assertEqual(kept["panels"]["Open Purchase Orders"]["kind"], "table")
        self._figure("po_count", A)
        ConnectedBusiness.objects.filter(business_code=A).update(status="Unreachable")

        def no_network(*a, **k):
            raise AssertionError("a known-down business was contacted")
        with mock.patch("requests.get", no_network), mock.patch("requests.post", no_network):
            t = time.perf_counter()
            out, _ = self._post("panels.get", view="proc", business_code=A)
            fig, _ = self._post("kpi.get", keys=["po_count", "ar_open_invoices"], business_code=A)
            self.assertLess(time.perf_counter() - t, 5)
        self.assertEqual(out["panels"]["Open Purchase Orders"]["kind"], "unreachable")
        self.assertTrue(out.get("unreachable"))
        self.assertEqual(fig["po_count"]["data_status"]["state"], "unreachable")
        self.assertIsNotNone(fig["ar_open_invoices"]["value"], "loaded figures still show")

    # ------------------------------------------------------------------ warm after refresh
    def test_the_refresh_leaves_screens_answered(self):
        from command_center.api import ingest
        from command_center.recommend import engine
        from insights.compat import run_as
        # The finding boxes show the business's recommendations once they are worked out
        # (until then the older findings): worked out first, so both reads see the same.
        with run_as("Administrator"):
            engine.ensure_fresh(A, force=True)
        first, _ = self._post("panels.get", view="proc", business_code=A)
        figs, _ = self._post("kpi.get", keys=["po_count", "users_active"], business_code=A)
        # past their freshness, as they would be a few minutes later
        self._age(seconds=600)
        with run_as("Administrator"):
            ingest.poll_peers()
        (again, r), n = self._calls(lambda: self._post("panels.get", view="proc", business_code=A))
        self.assertEqual(n, 0, "answered without asking the business")
        self.assertEqual(again, first)
        (figs2, _), n = self._calls(lambda: self._post("kpi.get", keys=["po_count", "users_active"],
                                                       business_code=A))
        self.assertEqual(n, 0)
        self.assertEqual(figs2["po_count"]["value"], figs["po_count"]["value"])

    # ------------------------------------------------------------------ stale, then fresh
    def test_past_its_freshness_kept_then_read_again(self):
        first, _ = self._figure("po_drafts_value", A)
        self._age(seconds=400)
        with mock.patch.object(T, "_value", lambda f, i, d: (_scaled(f, i, d) * 2
                                                             if f == "base_grand_total"
                                                             else _scaled(f, i, d))):
            stale, r = self._figure("po_drafts_value", A)
            self.assertEqual(stale, first, "returned at once from what was kept")
            self.assertIn('cache;desc="1 hit', r["Server-Timing"])
            deadline = time.time() + 20
            fresh = stale
            while time.time() < deadline and fresh == stale:
                _sleep(0.2)
                fresh, _ = self._figure("po_drafts_value", A)
        self.assertAlmostEqual(float(fresh), 2 * float(first), places=0)

    def _age(self, seconds):
        from django.core.cache import cache
        from django.db import connections
        table = connections["aux"].ops.quote_name("cc_cache")
        with connections["aux"].cursor() as cur:
            cur.execute(f"select cache_key from {table} where cache_key like %s",
                        ["%cc:fast:live%"])
            keys = [k for (k,) in cur.fetchall()]
            cur.execute(f"select cache_key from {table} where cache_key like %s",
                        ["%cc:fast:panels%"])
            keys += [k for (k,) in cur.fetchall()]
        for raw in keys:
            key = raw.split(":", 2)[-1] if raw.startswith(":") else raw
            entry = cache.get(key)
            if isinstance(entry, dict) and "at" in entry:
                entry["at"] -= seconds
                cache.set(key, entry, timeout=3600)
        self.assertTrue(keys, "nothing was kept to age")
