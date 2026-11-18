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
        self.fake = getattr(self, "FAKE", TwoSites)()
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
        from command_center import background
        from command_center.recommend import engine
        for code in (A, B):
            # The change history is read behind the screens (kpi/history.py): worked out
            # first, so both readings below read the same kept summary -- otherwise the job
            # the first one starts may finish between them.
            with run_as("Administrator"):
                background.refresh_business(code)
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


# ---------------------------------------------------------------------------- behind the screens
AUD_CARDS = ["invoices_draft", "versions_total", "versions_business", "versions_earliest",
             "po_drafts_value", "po_drafts_oldest", "po_cancelled", "self_approved"]
HISTORY_CARDS = ("versions_total", "versions_business", "versions_earliest", "self_approved")
APPROVED = ("Purchase Order", "Payment Entry")


def _ops(filters) -> list:
    """[(field, op, value)] from Frappe's dict or list filters."""
    if isinstance(filters, str):
        filters = json.loads(filters or "{}")
    out = []
    if isinstance(filters, dict):
        for k, v in filters.items():
            out.append((k, v[0], v[1]) if isinstance(v, list) and len(v) == 2 else (k, "=", v))
    else:
        for f in filters or []:
            out.append((f[1], f[2], f[3]) if len(f) == 4 else (f[0], f[1], f[2]))
    return out


def _match(row, filters) -> bool:
    for field, op, value in _ops(filters):
        if field not in row:
            continue  # a scope the fake does not keep (company)
        got = row[field]
        if op == "=" and got != value:
            return False
        if op == "in" and got not in value:
            return False
        if op == "like" and value.strip("%") not in str(got or ""):
            return False
        if op in (">=", ">", "<", "<=") and not {
                ">=": str(got) >= str(value), ">": str(got) > str(value),
                "<": str(got) < str(value), "<=": str(got) <= str(value)}[op]:
            return False
    return True


class History(TwoSites):
    """TwoSites, whose change log (Version) and approved documents are kept per site and
    answered as ERPNext would -- filtered, ordered, counted -- each Version read taking
    `history_latency`, and the financial reports `report_latency`: the two reads that
    were slow on Gigmann's ERPNext."""

    def __init__(self):
        super().__init__()
        self.history_latency = self.report_latency = 0.0
        self.version_reads = []
        self.log = {1: [], 3: []}
        self.docs = {1: {}, 3: {}}
        for site, n in ((1, 40), (3, 25)):
            for i in range(n):
                doctype = APPROVED[i % 2]
                name = f"{'PO' if i % 2 else 'PE'}-{i:05d}"
                owner = f"raiser{i % 4}@test.com"
                self.docs[site][(doctype, name)] = {
                    "name": name, "owner": owner, "docstatus": 0 if i % 7 == 0 else 1,
                    "modified": "2026-11-01 10:00:00.000000"}
                self.step(site, doctype, name, owner, f"2026-10-{1 + i % 28:02d} 09:00:{i:02d}.000000")
                if i % 3:
                    self.step(site, doctype, name, "approver@test.com",
                              f"2026-10-{1 + i % 28:02d} 11:00:{i:02d}.000000")
            for j in range(15):  # the rest of the log: no approval step in it
                self.log[site].append({"name": f"V-{site}-x{j}", "ref_doctype": "Sales Invoice",
                                       "docname": f"SI-{j}", "owner": "clerk@test.com",
                                       "creation": f"2026-09-{1 + j:02d} 08:00:00.000000",
                                       "data": '{"changed": [["remarks", "", "x"]]}'})

    def step(self, site, doctype, name, who, when):
        self.log[site].append({"name": f"V-{site}-{len(self.log[site])}", "ref_doctype": doctype,
                               "docname": name, "owner": who, "creation": when,
                               "data": '{"changed": [["workflow_state", "Draft", "Approved"]]}'})

    def expected(self, site):
        """Submitted documents whose every step was taken by their raiser."""
        steps = {}
        for v in self.log[site]:
            if v["ref_doctype"] in APPROVED and "workflow_state" in v["data"]:
                steps.setdefault((v["ref_doctype"], v["docname"]), set()).add(v["owner"])
        return sum(1 for k, who in steps.items()
                   if self.docs[site].get(k, {}).get("docstatus") == 1
                   and who == {self.docs[site][k]["owner"]})

    def answer(self, m, p):
        site = 3 if getattr(_scale, "k", 1) in (3, 15) else 1
        doctype = p.get("doctype")
        if m == "frappe.desk.query_report.run" and self.report_latency:
            _sleep(self.report_latency)
        if doctype == "Version" and m in ("frappe.client.get_list", "frappe.client.get_count"):
            if self.history_latency:
                _sleep(self.history_latency)
            rows = [v for v in self.log[site] if _match(v, p.get("filters") or {})]
            if m == "frappe.client.get_count":
                return T._R(200, {"message": len(rows)})
            self.version_reads.append(p.get("filters"))
            return T._R(200, {"message": self._page(rows, p)})
        fields = p.get("fields") or ["name"]
        fields = json.loads(fields) if isinstance(fields, str) else fields
        if (doctype in APPROVED and m == "frappe.client.get_list"
                and set(fields) <= {"name", "owner", "docstatus", "modified"}):
            # The history's reads of the documents its steps name (kpi/history.py).
            f = p.get("filters") or {}
            named = any(k in ("name", "modified") for k, _, _ in _ops(f))
            order = str(p.get("order_by") or "")
            if named or (order.startswith("modified") and int(p.get("limit_page_length") or 0) == 1):
                rows = [d for (dt_, _), d in self.docs[site].items()
                        if dt_ == doctype and _match(d, f)]
                return T._R(200, {"message": self._page(rows, p)})
        return super().answer(m, p)

    @staticmethod
    def _page(rows, p):
        order = str(p.get("order_by") or "")
        if order:
            field, _, way = order.split(",")[0].strip().partition(" ")
            rows = sorted(rows, key=lambda r: (str(r.get(field)), r.get("name")),
                          reverse=way.strip().lower() == "desc")
        fields = p.get("fields") or ["name"]
        fields = json.loads(fields) if isinstance(fields, str) else fields
        start = int(p.get("limit_start") or 0)
        n = int(p.get("limit_page_length") or 20)
        return [{f: r.get(f) for f in fields} for r in rows[start:start + n]]


class Behind(TransactionTestCase):
    """The change history, the Internal Audit screen's heavy panels and the year-to-date
    statements are read behind the screens (speed.stored, background.py): never while a
    person waits, answered from storage once worked out, the history read again only
    from where it left off.

    BENCH=1 prints the before/after timings."""

    databases = {"default", "aux"}
    FAKE = History
    tearDown = Speed.tearDown
    _post = Speed._post
    _calls = Speed._calls

    def setUp(self):
        from command_center import speed
        Speed.setUp(self)
        # Kept warm at any hour the tests run.
        p = mock.patch.object(speed, "_workday", lambda: True)
        p.start()
        self.patches.append(p)

    def _wait(self, fn, ok, seconds=60):
        deadline = time.time() + seconds
        while True:
            got = fn()
            if ok(got) or time.time() > deadline:
                return got
            _sleep(0.2)

    def _say(self, *lines):
        import os
        if os.environ.get("BENCH"):
            print("\n" + "\n".join(lines))

    def _run_all(self):
        from command_center import background
        from insights.compat import run_as
        with run_as("Administrator"):
            background.run_all()

    # ------------------------------------------------------------------ nothing kept yet
    def test_nothing_kept_answers_at_once_then_fills(self):
        from command_center.kpi import history
        from insights.compat import run_as
        self.fake.history_latency = 0.6
        # What a person waited for before: the change history read while they wait.
        t = time.perf_counter()
        with run_as("Administrator"):
            history.work_out(A)
        before = time.perf_counter() - t
        from django.core.cache import cache
        cache.delete_many([k for k in self._keys("cc:bg:")])
        t = time.perf_counter()
        (figs, _), n = self._calls(lambda: self._post("kpi.get", keys=AUD_CARDS, business_code=A))
        first = time.perf_counter() - t
        self.assertLess(first, before / 2, "the first look does not wait for the history")
        for k in HISTORY_CARDS:
            st = figs[k]["data_status"]
            self.assertEqual(st["state"], "unreachable", k)  # the calm "not answered yet"
            self.assertTrue(st.get("pending"), k)
            self.assertIsNone(figs[k]["value"], k)
        self.assertIsNotNone(figs["po_drafts_value"]["value"], "the rest is read as usual")
        t = time.perf_counter()
        aud, _ = self._post("panels.get", view="aud", business_code=A)
        aud_first = time.perf_counter() - t
        self.assertTrue(aud.get("pending"))
        self.assertEqual(aud["panels"]["Decisions taken"]["kind"], "unreachable")
        self.assertEqual(aud["panels"]["Raised and never submitted"]["kind"], "table")
        self.fake.report_latency = 0.6
        from command_center.api import statements
        t = time.perf_counter()
        with run_as("Administrator"):
            statements.work_out(A, "summary", "ytd")  # read while waiting, as before
        fs_before = time.perf_counter() - t
        cache.delete_many([k for k in self._keys("cc:stmts")])
        t = time.perf_counter()
        fs, _ = self._post("statements.get", business_code=A, period="ytd", section="summary")
        fs_first = time.perf_counter() - t
        self.assertLess(fs_first, fs_before / 2, "the first look does not wait for the reports")
        self.assertEqual(fs["state"], "unreachable")
        self.assertTrue(fs.get("pending"))
        # The jobs the looks started fill them in: the next refresh shows them.
        figs = self._wait(lambda: self._post("kpi.get", keys=AUD_CARDS, business_code=A)[0],
                          lambda f: f["self_approved"]["value"] is not None)
        self.assertEqual(figs["self_approved"]["value"], self.fake.expected(1))
        self.assertEqual(figs["versions_total"]["value"], len(self.fake.log[1]))
        self.assertRegex(figs["self_approved"]["as_of"]["basis"], r"^read from ERPNext at \d\d:\d\d$")
        fs = self._wait(lambda: self._post("statements.get", business_code=A, period="ytd",
                                           section="summary")[0],
                        lambda f: f["state"] == "ok")
        self.assertEqual(fs["state"], "ok")
        self.assertTrue(fs.get("read_at"))
        aud = self._wait(lambda: self._post("panels.get", view="aud", business_code=A)[0],
                         lambda a: not a.get("pending"))
        self.assertEqual(aud["panels"]["Decisions taken"]["kind"], "table")
        self._say(f"history read while waiting (before): {before:.2f}s",
                  f"Internal Audit cards, nothing kept yet: {first:.2f}s ({n} ERPNext calls)",
                  f"Internal Audit panels, nothing kept yet: {aud_first:.2f}s",
                  f"statements ytd summary read while waiting (before): {fs_before:.2f}s",
                  f"statements ytd, nothing kept yet: {fs_first:.2f}s")

    # ------------------------------------------------------------------ from storage
    def test_after_the_job_they_answer_from_storage(self):
        self.fake.history_latency = self.fake.report_latency = 0.6
        # A first look, so the screen's figures are known to the warming; then the hour's job.
        self._post("kpi.get", keys=AUD_CARDS, business_code=A)
        t = time.perf_counter()
        self._run_all()
        job = time.perf_counter() - t
        t = time.perf_counter()
        (figs, r), n = self._calls(lambda: self._post("kpi.get", keys=AUD_CARDS, business_code=A))
        cards_t = time.perf_counter() - t
        self.assertEqual(n, 0, "the Internal Audit cards from storage, no ERPNext call")
        self.assertEqual(figs["self_approved"]["value"], self.fake.expected(1))
        self.assertTrue(all(figs[k]["data_status"]["state"] == "live" for k in HISTORY_CARDS))
        t = time.perf_counter()
        (aud, _), n_aud = self._calls(lambda: self._post("panels.get", view="aud", business_code=A))
        aud_t = time.perf_counter() - t
        self.assertEqual(n_aud, 0, "the Internal Audit panels too")
        self.assertFalse(aud.get("pending") or aud.get("unreachable"))
        t = time.perf_counter()
        n_fs = 0
        for section in ("summary", "tb", "cf"):
            (fs, _), k = self._calls(lambda s=section: self._post(
                "statements.get", business_code=A, period="ytd", section=s))
            self.assertEqual(fs["state"], "ok", section)
            n_fs += k
        fs_t = time.perf_counter() - t
        self.assertEqual(n_fs, 0, "the year-to-date statements from storage")
        # Another period is still read when asked for.
        (fs, _), k = self._calls(lambda: self._post("statements.get", business_code=A,
                                                    period="last_month", section="summary"))
        self.assertEqual(fs["state"], "ok")
        self.assertGreater(k, 0)
        # The PDF is drawn from the same answers (the renderer itself stubbed: wkhtmltopdf
        # is the server's).
        with mock.patch("command_center.api.export.html_pdf", lambda *a, **k: b"%PDF-1.4"):
            (r, _), k = self._calls(lambda: (self.c.post(
                "/api/method/command_center.api.statements.pdf",
                json.dumps({"business_code": A, "period": "ytd"}),
                content_type="application/json"), None))
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(k, 0)
        # Each business its own; the panels' history counts are the cards'.
        b, _ = self._post("kpi.get", keys=["self_approved", "versions_total"], business_code=B)
        self.assertEqual(b["self_approved"]["value"], self.fake.expected(3))
        self.assertNotEqual(b["versions_total"]["value"], figs["versions_total"]["value"])
        rows = aud["panels"]["How much history there is"]["rows"]
        self.assertEqual(rows[-1]["cells"][1]["text"], f"{figs['versions_total']['value']:,}")
        self._say(f"background job, both businesses: {job:.2f}s",
                  f"Internal Audit cards from storage: {cards_t:.2f}s, {n} calls",
                  f"Internal Audit panels from storage: {aud_t:.2f}s, {n_aud} calls",
                  f"statements ytd (3 sections) from storage: {fs_t:.2f}s, {n_fs} calls")

    def test_a_persons_own_key_has_its_own(self):
        self._run_all()
        self._post("credentials.link_account", business_code=A, api_key="own",
                   api_secret="their-secret")
        mine, _ = self._post("kpi.get", keys=["self_approved"], business_code=A)
        self.assertTrue(mine["self_approved"]["data_status"].get("pending"),
                        "never the platform's answer to someone reading with their own key")
        # Worked out as them, behind the screens (their own job: waited for, so its reads
        # are not counted below).
        mine = self._wait(lambda: self._post("kpi.get", keys=["self_approved"], business_code=A)[0],
                          lambda f: f["self_approved"]["value"] is not None)
        self.assertEqual(mine["self_approved"]["value"], self.fake.expected(1))
        (theirs, _), n = self._calls(lambda: self._post(
            "kpi.get", keys=["self_approved"], business_code=A, c=self.clients["two@test.com"]))
        self.assertEqual(theirs["self_approved"]["value"], self.fake.expected(1))
        self.assertEqual(n, 0)

    # ------------------------------------------------------------------ incremental
    def test_the_history_is_read_from_where_it_left_off(self):
        from django.core.cache import cache

        from command_center.kpi import history
        self._run_all()
        figs, _ = self._post("kpi.get", keys=list(HISTORY_CARDS), business_code=A)
        before = figs["self_approved"]["value"]
        self.assertEqual(before, self.fake.expected(1))
        self.assertTrue(any("creation" not in json.dumps(f) for f in self.fake.version_reads),
                        "the first run reads the whole history")
        # Since then: a new document approved by its raiser alone, and one approved
        # earlier cancelled.
        self.fake.docs[1][("Purchase Order", "PO-00099")] = {
            "name": "PO-00099", "owner": "raiser1@test.com", "docstatus": 1,
            "modified": "2026-11-16 12:00:00.000000"}
        self.fake.step(1, "Purchase Order", "PO-00099", "raiser1@test.com",
                       "2026-11-16 11:00:00.000000")
        helped = {v["docname"] for v in self.fake.log[1] if v["owner"] == "approver@test.com"}
        gone = next(k for k, d in self.fake.docs[1].items()
                    if d["docstatus"] == 1 and k[1] in helped)
        self.fake.docs[1][gone].update({"docstatus": 2, "modified": "2026-11-16 12:30:00.000000"})
        self.fake.version_reads.clear()
        self._run_all()
        reads = [str(f) for f in self.fake.version_reads]
        self.assertTrue(reads and all("creation" in f for f in reads),
                        f"only the rows created since the last run: {reads}")
        figs, _ = self._post("kpi.get", keys=list(HISTORY_CARDS), business_code=A)
        self.assertEqual(figs["self_approved"]["value"], self.fake.expected(1))
        self.assertNotEqual(figs["self_approved"]["value"], before)
        self.assertEqual(figs["versions_total"]["value"], len(self.fake.log[1]))
        # A week on, everything is read again.
        for raw in self._keys("cc:bg:history-scan:"):
            scan = cache.get(raw)
            scan["full_at"] -= history.FULL_EVERY + 1
            cache.set(raw, scan, timeout=3600)
        self.fake.version_reads.clear()
        self._run_all()
        self.assertTrue(any('"creation"' not in json.dumps(f) for f in self.fake.version_reads),
                        "the weekly rescan reads the whole history")

    def _keys(self, prefix):
        from django.db import connections
        table = connections["aux"].ops.quote_name("cc_cache")
        with connections["aux"].cursor() as cur:
            cur.execute(f"select cache_key from {table} where cache_key like %s", [f"%{prefix}%"])
            raw = [k for (k,) in cur.fetchall()]
        return [k.split(":", 2)[-1] if k.startswith(":") else k for k in raw]
