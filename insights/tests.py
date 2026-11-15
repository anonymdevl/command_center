"""The platform end to end, against a fake ERPNext:

    .venv-platform/bin/python manage.py test insights

A fake ERPNext answers the platform's API reads with plausible rows for whatever fields
it is asked for (and the parents it names), so what is under test is the whole data
path on the platform's own database: registering a business (its secret stored
encrypted), the full load of every fact (bulk writes, purges, watermarks), the figures'
cross-checks, an incremental reload, and the screens' calls through the web layer with
a signed-in manager. What it cannot test is a real ERPNext's answers -- those are
checked on the server against Gigmann's live site.
"""

from __future__ import annotations

import datetime as dt
import json
import random
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TransactionTestCase

TODAY = dt.date.today()
N = 60
# The department screens: every figure, panel and finding on them is the business's own.
DEPARTMENT_VIEWS = ("sales", "proc", "inv", "eng", "cx", "fin", "hr")


class _R:
    def __init__(self, status, body):
        self.status_code, self._body, self.ok, self.headers = status, body, 200 <= status < 300, {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


def _value(field: str, i: int, doctype: str):
    rnd = random.Random(f"{doctype}:{field}:{i}")
    f = field.lower()
    if f in ("name",):
        return f"{''.join(w[0] for w in doctype.split())}-{i:05d}"
    if f in ("modified", "creation"):
        return (dt.datetime.now() - dt.timedelta(days=rnd.randint(0, 300))).strftime("%Y-%m-%d %H:%M:%S.%f")
    if f == "docstatus":
        return 1
    if f in ("resolution_by", "response_by", "last_active", "last_login"):
        return (dt.datetime.now() - dt.timedelta(days=rnd.randint(-20, 200))).strftime("%Y-%m-%d %H:%M:%S")
    if "date" in f or "deadline" in f or f in ("exp_end_date", "completed_on", "opening_date",
                                                "completion_by"):
        return str(TODAY - dt.timedelta(days=rnd.randint(-30, 300)))
    if f in ("is_stock_item",):
        return 1
    if f.endswith("exchange_rate") or f == "conversion_factor":
        return 1.0
    if f in ("sales_order", "against_sales_order"):
        return f"SO-{rnd.randint(0, N - 1):05d}"
    if f == "purchase_order":
        return f"PO-{rnd.randint(0, N - 1):05d}"
    if f.startswith(("is_", "has_")) or f in ("enabled", "disabled", "is_return"):
        return 0
    if f.startswith("per_"):
        return rnd.choice([0, 50, 100])
    if any(k in f for k in ("amount", "total", "value", "rate", "qty", "outstanding",
                            "paid", "allocated", "cost", "price", "valuation")):
        return round(rnd.uniform(100, 20000), 2)
    if f in ("status",):
        return rnd.choice({"Sales Invoice": ["Unpaid", "Overdue", "Paid"],
                           "Purchase Invoice": ["Unpaid", "Overdue", "Paid"],
                           "Sales Order": ["To Deliver and Bill", "To Bill", "Completed"],
                           "Task": ["Open", "Working", "Completed", "Overdue"],
                           "Issue": ["Open", "Replied", "Closed"],
                           "Employee": ["Active"]}.get(doctype, ["Open"]))
    if f in ("customer", "party") or "customer" in f:
        return rnd.choice(["Ubuntu Ltd", "Ejura Clinic", "Korle Bu", "Ridge Hospital"])
    if "supplier" in f:
        return rnd.choice(["Min-Medical", "CT Consult", "Chunjee"])
    if "item" in f:
        return rnd.choice(["ITM-001", "ITM-002", "ITM-003"])
    if "warehouse" in f:
        return rnd.choice(["Stores - GMS", "Kumasi - GMS"])
    if f in ("company",):
        return "Test Medical Ltd"
    if "currency" in f:
        return "GHS"
    if f in ("party_type",):
        return "Customer"
    if f in ("payment_type",):
        return "Receive"
    if f in ("reference_doctype", "against_doctype"):
        return "Sales Invoice"
    if f in ("reference_name", "against_name"):
        return f"SI-{rnd.randint(0, N - 1):05d}"
    if "user" in f or "owner" in f or "email" in f or f == "assigned_to" or f == "_assign":
        return "clerk@test.com"
    if f in ("priority",):
        return rnd.choice(["Low", "Medium", "High"])
    if f.endswith("_days") or f in ("days",):
        return rnd.randint(0, 120)
    return f"{field}-{rnd.randint(1, 5)}"


class FakeERPNext:
    """GET/POST /api/method/frappe.client.* and the few others the platform calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, method_name):
        def call(url, headers=None, params=None, data=None, json=None, timeout=None):
            body = json if json is not None else (data if data is not None else params) or {}
            m = url.split("/api/method/", 1)[1]
            self.calls.append(m)
            return self.answer(m, body)
        return call

    def answer(self, m, p):
        if m == "frappe.auth.get_logged_user":
            return _R(200, {"message": "reader@test.com"})
        if m == "frappe.client.get_count":
            return _R(200, {"message": N})
        if m in ("frappe.client.get_list",):
            return _R(200, {"message": self.rows(p)})
        if m == "frappe.desk.form.load.getdoctype":
            doc = {"name": p.get("doctype"), "fields": []}
            if p.get("doctype") == "Version":
                # ERPNext's own rules for the change log: System Manager reads, nobody deletes
                doc["permissions"] = [{"role": "System Manager", "read": 1, "delete": 0}]
            return _R(200, {"docs": [doc]})
        return _R(200, {"message": {}})

    def rows(self, p):
        doctype = p.get("doctype")
        fields = p.get("fields") or ["name"]
        fields = json.loads(fields) if isinstance(fields, str) else fields
        filters = p.get("filters") or {}
        filters = json.loads(filters) if isinstance(filters, str) else filters
        start = int(p.get("limit_start") or 0)
        n = int(p.get("limit_page_length") or 20)
        if doctype == "Company":
            return [{"name": "Test Medical Ltd", "default_currency": "GHS"}][:n]
        parents = names = None
        if isinstance(filters, dict):
            if isinstance(filters.get("parent"), list) and filters["parent"][0] == "in":
                parents = filters["parent"][1]
            if isinstance(filters.get("name"), list) and filters["name"][0] == "in":
                names = filters["name"][1]
            ds = filters.get("docstatus")
            if ds == 2 or (isinstance(ds, list) and ds[0] in ("=", "in") and 2 in (
                    ds[1] if isinstance(ds[1], list) else [ds[1]])):
                return []  # the cancellation sweep: nothing was cancelled
        out = []
        cols = [re.split(r"\s+as\s+", str(f))[-1].strip() for f in fields]
        if names is not None:
            idxs = [int(x.split("-")[-1]) for x in names if x.split("-")[-1].isdigit()]
        elif parents is not None:
            idxs = list(range(len(parents)))
        else:
            idxs = list(range(start, min(start + n, N)))
        for i in idxs:
            row = {c: _value(c, i, doctype) for c in cols}
            if names is not None and "name" in cols:
                row["name"] = names[idxs.index(i)]
            if parents is not None:
                row["parent"] = parents[i]
                row["name"] = f"row-{doctype[:4]}-{i}"
            out.append(row)
        return out[:n]


class PlatformEndToEnd(TransactionTestCase):
    databases = {"default", "aux"}

    def setUp(self):
        from django.conf import settings
        from cryptography.fernet import Fernet
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        self.fake = FakeERPNext()
        self.patches = [mock.patch("requests.get", self.fake("GET")),
                        mock.patch("requests.post", self.fake("POST")),
                        mock.patch("time.sleep", lambda s: None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_register_load_figures_screens(self):
        from command_center import install
        from command_center.api import ingest, kpi
        from insights.compat import documents, run_as
        from insights.core.models import Secret

        with run_as("Administrator"):
            out = install.register_business("Test Medical Ltd", "https://erp.test", "key",
                                            "s3cret")
        self.assertEqual(out["code"], "test_medical_ltd")
        self.assertEqual(out["currency"], "GHS")
        # the secret is stored encrypted, and reads back
        row = Secret.objects.get(doctype="Connected Business", fieldname="api_secret")
        self.assertNotIn("s3cret", row.value)
        self.assertEqual(documents.get_password("Connected Business", "Test Medical Ltd",
                                                "api_secret"), "s3cret")

        with run_as("Administrator"):
            result = ingest.run_all(full=True)
        loaded = result[0]["loaded"]
        failed = [f["fact"] for f in loaded if f.get("failed")]
        self.assertEqual(failed, [], f"facts that failed to load: {failed}")
        rows = {f["fact"]: f.get("rows") for f in loaded}
        for fact in ("fact_sales_invoice", "fact_sales_invoice_line", "fact_payment_allocation",
                     "fact_purchase_invoice", "fact_sales_order", "fact_stock_balance"):
            self.assertGreater(rows.get(fact) or 0, 0, f"{fact} loaded no rows: {rows}")

        with run_as("Administrator"):
            check = kpi.verify()
        self.assertTrue(check["all_ok"], json.dumps(check, default=str)[:800])

        # an incremental reload is harmless (watermarks, upserts)
        with run_as("Administrator"):
            again = ingest.run_all(full=False)
        self.assertFalse([f for f in again[0]["loaded"] if f.get("failed")])

        # the screens' calls, through the web layer, as a signed-in manager
        U = get_user_model()
        m = U.objects.create_user("manager@test.com", "manager@test.com", "a-long-test-pass-9")
        m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        c = Client()
        self.assertTrue(c.login(username="manager@test.com", password="a-long-test-pass-9"))
        # the 15-minute refresh stamps last_sync (a datetime) -- the page must still build
        from insights.core.models import ConnectedBusiness
        ConnectedBusiness.objects.update(last_sync=dt.datetime.now())
        page = c.get("/command-center").content.decode()
        self.assertIn("Test Medical Ltd", page)
        for method, args in [
            ("command_center.api.kpi.get", {"keys": ["ar_total", "revenue_invoiced", "ap_total",
                                                     "order_book"]}),
            ("command_center.api.home.debtors", {}),
            ("command_center.api.home.top_customers", {}),
            ("command_center.api.facts.records", {"fact": "fact_sales_invoice", "limit": 5}),
            ("command_center.api.ingest.status", {}),
            ("command_center.api.alerts.open_alerts", {}),
            ("command_center.api.ingest.history", {}),
        ]:
            r = c.post(f"/api/method/{method}", json.dumps(args), content_type="application/json")
            self.assertEqual(r.status_code, 200, f"{method}: {r.content[:400]!r}")
        figures = c.post("/api/method/command_center.api.kpi.get",
                         json.dumps({"keys": ["ar_total"]}), content_type="application/json").json()
        self.assertGreater(figures["message"]["ar_total"]["value"] or 0, 0)

        # every figure read live from the business's ERPNext, and the order-book boxes,
        # come back read -- never "could not be read" -- with somewhere to open
        from command_center.kpi.live import LIVE
        keys = sorted(LIVE) + ["order_awaiting_despatch", "order_awaiting_invoice"]
        got = c.post("/api/method/command_center.api.kpi.get",
                     json.dumps({"keys": keys, "business_code": "test_medical_ltd"}),
                     content_type="application/json").json()["message"]
        for key in keys:
            self.assertNotEqual(got[key]["data_status"]["state"], "failed",
                                f"{key}: {got[key]}")
            self.assertTrue(got[key]["drill"], f"{key} opens to nothing")

        # every designed screen's charts and tables answer from the loaded records
        from command_center.api import panels as panels_api
        for view, builders in panels_api.SCREENS.items():
            r = c.post("/api/method/command_center.api.panels.get",
                       json.dumps({"view": view, "business_code": "test_medical_ltd"}),
                       content_type="application/json")
            self.assertEqual(r.status_code, 200, f"panels {view}: {r.content[:300]!r}")
            got = r.json()["message"]["panels"]
            self.assertEqual(sorted(got), sorted(builders), f"panels {view} answered {sorted(got)}")
            bad = {t: p for t, p in got.items() if p.get("kind") in ("failed", "unreachable")}
            self.assertFalse(bad, f"panels {view} could not be read: {bad}")
            if view in DEPARTMENT_VIEWS:
                self.assertTrue(r.json()["message"].get("when"), f"{view}: no line under the heading")

        # the administration, with a loaded business in it: every list and the first
        # record of each opens for the platform's administrator
        from django.contrib import admin as dj_admin
        boss = U.objects.create_superuser("boss@test.com", "boss@test.com", "a-long-test-pass-7")
        ca = Client(raise_request_exception=True)
        self.assertEqual(ca.post("/admin/login/?next=/admin/", {
            "username": "boss@test.com", "password": "a-long-test-pass-7"}).status_code, 302)
        self.assertEqual(ca.get("/admin/").status_code, 200)
        for model in dj_admin.site._registry:
            base = f"/admin/{model._meta.app_label}/{model._meta.model_name}/"
            self.assertEqual(ca.get(base).status_code, 200, base)
            first = model.objects.first()
            if first is not None:
                page = f"{base}{first.pk}/change/"
                self.assertEqual(ca.get(page).status_code, 200, page)
        boss.delete()

        # the business's ERPNext stops answering: the panels that read it live say so,
        # the ones drawn from the loaded facts still show them, and a live figure reads
        # "can't reach" -- never a guide, never "could not be read"
        import requests as _rq
        from django.core.cache import cache

        def down(*a, **k):
            raise _rq.ConnectionError("connection refused")
        cache.clear()
        with mock.patch("requests.get", down), mock.patch("requests.post", down):
            for view in DEPARTMENT_VIEWS:
                msg = c.post("/api/method/command_center.api.panels.get",
                             json.dumps({"view": view, "business_code": "test_medical_ltd"}),
                             content_type="application/json").json()["message"]
                kinds = {t: p.get("kind") for t, p in msg["panels"].items()}
                self.assertEqual(sorted(kinds), sorted(panels_api.SCREENS[view]), view)
                self.assertNotIn("failed", kinds.values(), f"{view}: {kinds}")
                if "unreachable" in kinds.values():
                    self.assertTrue(msg.get("unreachable"), view)
                    self.assertEqual(msg.get("business"), "Test Medical Ltd")
            sales = c.post("/api/method/command_center.api.panels.get",
                           json.dumps({"view": "sales", "business_code": "test_medical_ltd"}),
                           content_type="application/json").json()["message"]
            self.assertEqual(sales["panels"]["Largest balances owed"]["kind"], "bars")
            self.assertEqual(sales["panels"]["From enquiry to order"]["kind"], "unreachable")
            self.assertTrue(sales["unreachable"])
            live = c.post("/api/method/command_center.api.kpi.get",
                          json.dumps({"keys": ["po_count", "order_awaiting_stock"],
                                      "business_code": "test_medical_ltd"}),
                          content_type="application/json").json()["message"]
            for key, fig in live.items():
                self.assertEqual(fig["data_status"]["state"], "unreachable", f"{key}: {fig}")
                self.assertIsNone(fig["value"])
        cache.clear()

        # someone without the role is turned away from the interface
        U.objects.create_user("clerk@test.com", "clerk@test.com", "a-long-test-pass-8")
        c2 = Client()
        c2.login(username="clerk@test.com", password="a-long-test-pass-8")
        r = c2.get("/command-center")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/management-only", r["Location"])


class CommandLine(TransactionTestCase):
    """The management commands as the install script runs them: through manage.py's
    argument parsing (call_command skips that, which hid a clash with --args)."""

    databases = {"default", "aux"}

    def test_execute_from_the_command_line(self):
        import io
        from contextlib import redirect_stdout
        from django.core.management import ManagementUtility
        out = io.StringIO()
        with redirect_stdout(out):
            ManagementUtility(["manage.py", "execute", "command_center.api.kpi.verify",
                               "--kwargs", "{}", "--args", "[]"]).execute()
        self.assertIn('"all_ok"', out.getvalue())


class Upkeep(TransactionTestCase):
    """The nightly upkeep: old errors pruned, a backup written and old ones dropped."""

    databases = {"default", "aux"}

    def test_daily(self):
        import os
        import tempfile
        import time
        from pathlib import Path
        from django.conf import settings
        from insights.core import maintenance
        from insights.core.models import ErrorLog
        old = ErrorLog.objects.using("aux").create(title="old", error="x")
        ErrorLog.objects.using("aux").filter(pk=old.pk).update(
            creation=dt.datetime.now() - dt.timedelta(days=90))
        ErrorLog.objects.using("aux").create(title="recent", error="y")
        import shutil
        from django.db import connection
        if connection.vendor == "mysql" and not (shutil.which("mariadb-dump")
                                                 or shutil.which("mysqldump")):
            self.skipTest("no mariadb-dump on this machine to back MariaDB up with")
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(
                settings.CONFIG, {"backup_dir": d}):
            stale = Path(d, "insights-20200101-000000.sqlite3")
            stale.write_text("old")
            os.utime(stale, (time.time() - 30 * 86400,) * 2)
            out = maintenance.daily()
            self.assertEqual(out["error_log_pruned"], 1)
            self.assertTrue(Path(out["backup"]).exists(), out)
            self.assertFalse(stale.exists())
        titles = set(ErrorLog.objects.using("aux").values_list("title", flat=True))
        self.assertIn("recent", titles)
        self.assertNotIn("old", titles)


class SignInLimits(TransactionTestCase):
    """Wrong passwords are limited -- on the platform's sign-in and the administration's
    -- and a made-up X-Forwarded-For does not get round the limit."""

    databases = {"default", "aux"}

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        get_user_model().objects.create_superuser("boss@test.com", "boss@test.com",
                                                  "a-long-test-pass-1")

    def _api(self, c, pwd, fake_ip):
        return c.post("/api/method/login", json.dumps({"usr": "boss@test.com", "pwd": pwd}),
                      content_type="application/json", REMOTE_ADDR="127.0.0.1",
                      HTTP_X_FORWARDED_FOR=f"{fake_ip}, 41.66.1.1")

    def test_spoofed_forwarded_for_is_not_a_fresh_address(self):
        c = Client()
        codes = [self._api(c, "wrong-password-x", f"10.0.0.{i}").status_code for i in range(7)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5:], [429, 429])
        # the right password is refused too while locked
        self.assertEqual(self._api(c, "a-long-test-pass-1", "10.9.9.9").status_code, 429)

    def test_admin_sign_in_is_limited(self):
        c = Client()
        codes = [c.post("/admin/login/?next=/admin/", {"username": "boss@test.com",
                                                       "password": "wrong-password-x"}).status_code
                 for _ in range(6)]
        self.assertEqual(codes[:5], [200] * 5)   # the form again, with its error
        self.assertEqual(codes[5], 429)

    def test_admin_sign_in_works(self):
        r = Client().post("/admin/login/?next=/admin/", {"username": "boss@test.com",
                                                         "password": "a-long-test-pass-1"})
        self.assertEqual(r.status_code, 302)


class PanelHeadings(TransactionTestCase):
    """Every panel api/panels.py answers is a heading on that screen, word for word --
    a heading that does not match would leave the designed sample in place."""

    def test_headings_exist(self):
        import html as _html
        from pathlib import Path
        from django.conf import settings
        from command_center.api.panels import SCREENS
        views = json.loads(Path(settings.BASE_DIR, "frontend/src/legacy/views.json").read_text())
        for view, builders in SCREENS.items():
            markup = _html.unescape(views[view])
            for title in builders:
                self.assertIn(f"<b>{title}</b>", markup, f"{view}: no panel headed {title!r}")


class SettingsPage(TransactionTestCase):
    """The Settings screen's calls (insights/core/platform_settings.py): for the platform's
    administrator only, refused to a manager by the server; people, businesses, the
    Claude key and personal ERPNext keys; no call ever returns a secret; refusals and
    password rules come back as plain sentences; every change is in the audit trail."""

    databases = {"default", "aux"}
    MOD = "insights.core.platform_settings"
    SECRET = "biz-secret-value-71x"
    PERSONAL = "personal-secret-value-93q"

    def setUp(self):
        import os
        import tempfile
        from django.conf import settings
        from django.core.cache import cache
        from cryptography.fernet import Fernet
        cache.clear()
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        self.fake = FakeERPNext()
        self.enqueued = []
        fd, self.cfg = tempfile.mkstemp(suffix=".json")
        os.write(fd, b"{}")
        os.close(fd)
        import frappe
        self.patches = [mock.patch("requests.get", self.fake("GET")),
                        mock.patch("requests.post", self.fake("POST")),
                        mock.patch("time.sleep", lambda s: None),
                        mock.patch.object(settings, "CONFIG_PATH", self.cfg),
                        mock.patch.dict(settings.CONFIG),
                        mock.patch.dict(frappe.conf),
                        mock.patch("insights.compat.enqueue",
                                   lambda fn, **kw: self.enqueued.append((fn, kw)))]
        for p in self.patches:
            p.start()
        U = get_user_model()
        self.boss = U.objects.create_superuser("boss@test.com", "boss@test.com", "a-long-test-pass-5")
        mgr = U.objects.create_user("manager@test.com", "manager@test.com", "a-long-test-pass-6")
        mgr.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        self.admin, self.manager = Client(), Client()
        self.assertTrue(self.admin.login(username="boss@test.com", password="a-long-test-pass-5"))
        self.assertTrue(self.manager.login(username="manager@test.com", password="a-long-test-pass-6"))
        self.bodies = []

    def tearDown(self):
        import os
        for p in reversed(self.patches):
            p.stop()
        os.unlink(self.cfg)

    def _call(self, client, fn, **args):
        r = client.post(f"/api/method/{self.MOD}.{fn}", json.dumps(args),
                        content_type="application/json")
        self.bodies.append(r.content.decode())
        return r

    def _ok(self, fn, **args):
        r = self._call(self.admin, fn, **args)
        self.assertEqual(r.status_code, 200, f"{fn}: {r.content[:400]!r}")
        return r.json()["message"]

    def _refused(self, fn, **args) -> str:
        r = self._call(self.admin, fn, **args)
        self.assertEqual(r.status_code, 417, f"{fn} was not refused: {r.content[:300]!r}")
        msgs = [json.loads(m)["message"] for m in json.loads(r.json()["_server_messages"])]
        text = " ".join(msgs)
        self.assertNotIn("Traceback", text)
        return text

    def test_a_manager_is_refused_every_call(self):
        from insights.compat import WHITELIST
        names = [k.rsplit(".", 1)[1] for k in WHITELIST if k.startswith(self.MOD + ".")]
        self.assertGreaterEqual(len(names), 20)
        for fn in names:
            r = self._call(self.manager, fn, username="boss@test.com", name="x")
            self.assertEqual(r.status_code, 403, f"{fn} answered a manager: {r.status_code}")
            self.assertEqual(self._call(Client(), fn).status_code, 401, fn)
        # and nothing was changed by trying
        self.assertTrue(get_user_model().objects.get(username="boss@test.com").is_superuser)

    def test_people(self):
        listed = {p["username"]: p for p in self._ok("people")}
        self.assertTrue(listed["boss@test.com"]["is_admin"])
        self.assertTrue(listed["manager@test.com"]["is_manager"])
        self.assertFalse(listed["manager@test.com"]["is_admin"])
        # password rules, in Django's own plain sentences
        self.assertIn("not the same", self._refused(
            "add_person", email="new@test.com", full_name="Ama Mensah",
            password="a-long-test-pass-1", password2="a-long-test-pass-2"))
        self.assertIn("too short", self._refused(
            "add_person", email="new@test.com", full_name="Ama Mensah",
            password="short1", password2="short1"))
        self.assertIn("too common", self._refused(
            "add_person", email="new@test.com", full_name="Ama Mensah",
            password="password123", password2="password123"))
        self.assertIn("not an email", self._refused("add_person", email="nobody", set_later=1))
        p = self._ok("add_person", email="New@Test.com", full_name="Ama Mensah",
                     password="a-long-test-pass-3", password2="a-long-test-pass-3", manager=1)
        self.assertEqual((p["username"], p["full_name"], p["is_manager"], p["has_password"]),
                         ("new@test.com", "Ama Mensah", True, True))
        self.assertIn("already", self._refused("add_person", email="new@test.com", set_later=1))
        self.assertTrue(Client().login(username="new@test.com", password="a-long-test-pass-3"))
        later = self._ok("add_person", email="later@test.com", full_name="Kofi Boateng",
                         set_later=1, manager=0)
        self.assertFalse(later["has_password"])
        self.assertFalse(later["is_manager"])
        # make / unmake manager and administrator, deactivate / reactivate
        self.assertTrue(self._ok("set_manager", username="later@test.com", on=1)["is_manager"])
        self.assertTrue(self._ok("set_admin", username="later@test.com", on=1)["is_admin"])
        self.assertFalse(self._ok("set_admin", username="later@test.com", on=0)["is_admin"])
        off = self._ok("set_active", username="new@test.com", on=0)
        self.assertFalse(off["active"])
        self.assertFalse(get_user_model().objects.get(username="new@test.com").is_active)
        self.assertFalse(Client().login(username="new@test.com", password="a-long-test-pass-3"))
        self.assertTrue(self._ok("set_active", username="new@test.com", on=1)["active"])
        # a new password, validated the same way
        self.assertIn("too short", self._refused("reset_password", username="new@test.com",
                                                 password="tiny", password2="tiny"))
        self._ok("reset_password", username="new@test.com", password="another-long-pass-4",
                 password2="another-long-pass-4")
        self.assertTrue(Client().login(username="new@test.com", password="another-long-pass-4"))
        # never a password, in any form
        for body in self.bodies:
            self.assertNotIn("pbkdf2", body)
            self.assertNotIn("a-long-test-pass-3", body)
            self.assertNotIn("another-long-pass-4", body)
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        for phrase in ("added new@test.com as manager", "deactivated new@test.com",
                       "set a new password for new@test.com", "made later@test.com an administrator"):
            self.assertIn(phrase, whats)
        self.assertNotIn("another-long-pass-4", whats)

    def test_the_last_administrator_stays(self):
        self.assertIn("yourself", self._refused("set_admin", username="boss@test.com", on=0))
        self.assertIn("yourself", self._refused("set_active", username="boss@test.com", on=0))
        self.assertIn("own password", self._refused("reset_password", username="boss@test.com",
                                                    set_later=1))
        boss = get_user_model().objects.get(username="boss@test.com")
        self.assertTrue(boss.is_superuser and boss.is_active)
        # with a second administrator, one may be removed -- but never the last active one
        self._ok("add_person", email="second@test.com", full_name="Second Admin", set_later=1,
                 admin=1)
        self.assertFalse(self._ok("set_active", username="second@test.com", on=0)["active"])
        from insights.compat import run_as
        from insights.compat.state import ValidationError
        from insights.core import platform_settings as ps
        get_user_model().objects.filter(username="second@test.com").update(is_active=True)
        with run_as("second@test.com"):
            ps.set_active("boss@test.com", 0)       # two active: allowed
        get_user_model().objects.filter(username="boss@test.com").update(is_active=True)
        get_user_model().objects.filter(username="second@test.com").update(is_superuser=False)
        U = get_user_model()
        self.assertEqual(U.objects.filter(is_superuser=True, is_active=True).count(), 1)
        with mock.patch.object(ps, "_require_admin", lambda: U.objects.get(username="second@test.com")):
            with run_as("second@test.com"), self.assertRaises(ValidationError) as e:
                ps.set_admin("boss@test.com", 0)
        self.assertIn("last active administrator", str(e.exception))

    def test_businesses_and_keys(self):
        from insights.compat import documents
        out = self._ok("add_business", business_name="Test Medical Ltd",
                       site_url="https://erp.test/", api_key="key-abcd1234", api_secret=self.SECRET)
        self.assertEqual(out["access"]["reads_as"], "reader@test.com")
        self.assertEqual(out["currency"], "GHS")
        self.assertTrue(out["access"]["read_only"])
        self.assertFalse(out["access"]["unreadable"])
        row = out["business"]
        self.assertEqual((row["site_url"], row["api_key"], row["has_secret"]),
                         ("https://erp.test", "…1234", True))
        self.assertIn("connected already", self._refused(
            "add_business", business_name="Test Medical Ltd", site_url="https://erp.test",
            api_key="k", api_secret="s"))
        self.assertIn("https://", self._refused(
            "add_business", business_name="Other Ltd", site_url="erp.other", api_key="k",
            api_secret="s"))
        # a business whose ERPNext refuses the key is not kept
        refuse = lambda *a, **k: _R(401, {"exc_type": "AuthenticationError"})  # noqa: E731
        with mock.patch("requests.get", refuse), mock.patch("requests.post", refuse):
            msg = self._refused("add_business", business_name="Refusing Ltd",
                                site_url="https://erp.refuse", api_key="k", api_secret="s")
        self.assertIn("was not connected", msg)
        from insights.core.models import ConnectedBusiness, Secret
        self.assertFalse(ConnectedBusiness.objects.filter(pk="Refusing Ltd").exists())
        self.assertFalse(Secret.objects.filter(docname="Refusing Ltd").exists())

        # edit: a blank secret keeps the stored one, a new one replaces it
        self._ok("update_business", name="Test Medical Ltd", site_url="https://erp2.test")
        self.assertEqual(documents.get_password("Connected Business", "Test Medical Ltd",
                                                "api_secret"), self.SECRET)
        self._ok("update_business", name="Test Medical Ltd", api_secret=self.SECRET + "-new")
        self.assertEqual(documents.get_password("Connected Business", "Test Medical Ltd",
                                                "api_secret"), self.SECRET + "-new")
        self.assertIn("Nothing was changed", self._refused("update_business", name="Test Medical Ltd"))
        tested = self._ok("test_business", name="Test Medical Ltd")
        self.assertTrue(tested["ok"], tested)
        self.assertIn("reader@test.com", tested["says"])
        self.assertEqual(self._ok("set_paused", name="Test Medical Ltd", paused=1)["status"], "Paused")
        self.assertIn("paused", self._refused("reload_business", name="Test Medical Ltd"))
        self.assertEqual(self._ok("set_paused", name="Test Medical Ltd", paused=0)["status"], "Active")
        # Reload Everything starts a background job and returns at once
        started = self._ok("reload_business", name="Test Medical Ltd")
        self.assertEqual(len(self.enqueued), 1)
        self.assertEqual(self.enqueued[0][1]["code"], "test_medical_ltd")
        self.assertEqual(started["reload"]["state"], "queued")
        listed = self._ok("businesses")[0]
        self.assertEqual(listed["reload"]["state"], "queued")
        self.assertEqual(listed["reload"]["total"], listed["facts_total"])

        # personal ERPNext keys
        self.assertIn("both", self._refused("set_credential", user="manager@test.com",
                                            business_code="test_medical_ltd", api_key="pk"))
        cred = self._ok("set_credential", user="manager@test.com", business_code="test_medical_ltd",
                        api_key="pkey-5678", api_secret=self.PERSONAL)
        self.assertEqual((cred["api_key"], cred["has_secret"]), ("…5678", True))
        self.assertEqual(len(self._ok("credentials")), 1)
        self.assertTrue(self._ok("test_credential", name=cred["name"])["ok"])
        self._ok("set_credential", user="manager@test.com", business_code="test_medical_ltd",
                 api_key="pkey-9999")
        self.assertEqual(documents.get_password("Command Center Site Credential", cred["name"],
                                                "api_secret"), self.PERSONAL)
        self.assertTrue(self._ok("remove_credential", name=cred["name"])["removed"])
        self.assertEqual(self._ok("credentials"), [])

        # the Claude key: replaced, shown only masked
        self.assertFalse(self._ok("claude")["set"])
        self.assertIn("whole key", self._refused("set_claude_key", key="sk-ant-short"))
        claude_key = "sk-ant-test-0000wxyz"
        shown = self._ok("set_claude_key", key=claude_key)
        self.assertEqual((shown["set"], shown["masked"]), (True, "sk-ant-…wxyz"))
        self.assertEqual(json.load(open(self.cfg))["command_center_anthropic_key"], claude_key)
        with mock.patch("command_center.api.ask.check_analyst",
                        lambda: {"ok": True, "provider": "claude", "model": "m-1",
                                 "deep_model": "m-2", "cache": {"working": True}}):
            checked = self._ok("check_claude")
        self.assertTrue(checked["ok"])
        self.assertIn("m-1", checked["says"])

        # no call returned a secret, a key in full, or the Claude key
        self._ok("businesses")
        self._ok("changes")
        for body in self.bodies:
            for secret in (self.SECRET, self.PERSONAL, "key-abcd1234", "pkey-5678", claude_key):
                self.assertNotIn(secret, body)
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        for phrase in ("connected Test Medical Ltd", "API secret", "paused Test Medical Ltd",
                       "started a full reload", "replaced the Claude key",
                       "removed the ERPNext key of manager@test.com"):
            self.assertIn(phrase, whats)


class PagesNotStored(TransactionTestCase):
    """The pages carry the person's details and their session's request token: the
    browser must never keep them, or a stale token refuses every request after sign-in."""

    databases = {"default", "aux"}

    def test_no_store(self):
        U = get_user_model()
        u = U.objects.create_user("m@test.com", "m@test.com", "a-long-test-pass-5")
        u.groups.add(Group.objects.get_or_create(name="Insights Dashboard Manager")[0])
        c = Client()
        self.assertEqual(c.get("/command-center-login")["Cache-Control"], "no-store")
        c.login(username="m@test.com", password="a-long-test-pass-5")
        self.assertEqual(c.get("/command-center")["Cache-Control"], "no-store")


class KpiCatalogueThreads(TransactionTestCase):
    """The figure catalogue is complete for every request, however many arrive at once."""

    def test_concurrent_load(self):
        import threading
        from command_center.kpi import registry
        saved = dict(registry.REGISTRY)
        registry.REGISTRY.clear()
        registry._LOADED = False
        import sys
        import command_center.kpi as kpi_pkg
        for m in ("buying", "operations", "sales", "stock"):
            sys.modules.pop(f"command_center.kpi.{m}", None)
            if hasattr(kpi_pkg, m):
                delattr(kpi_pkg, m)
        seen, errors = [], []

        def worker():
            try:
                seen.append(len(registry.load_all()))
            except Exception as e:  # pragma: no cover - would be the failure
                errors.append(e)
        threads = [threading.Thread(target=worker) for _ in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        try:
            self.assertFalse(errors, errors)
            self.assertEqual(len(set(seen)), 1, f"some requests saw a partial catalogue: {seen}")
            self.assertIn("revenue_12m", registry.REGISTRY)
        finally:
            registry.REGISTRY.clear()
            registry.REGISTRY.update(saved)
            registry._LOADED = True


class SettingsDelegation(TransactionTestCase):
    """Settings sections the administrator gives a manager (Businesses, People, Personal
    ERPNext Keys): a delegate can do exactly their sections, never anything that makes
    or changes an administrator or gives Settings access; the boot payload says which
    sections to show; every grant is audited. And Email: the password is never
    returned, and the test email and scheduled reports use the saved settings."""

    databases = {"default", "aux"}
    MOD = SettingsPage.MOD
    MAIL_PW = "mail-pass-xyz-77"
    setUp = SettingsPage.setUp
    tearDown = SettingsPage.tearDown
    _call = SettingsPage._call
    _ok = SettingsPage._ok

    def _as(self, client, fn, status=200, **args):
        r = self._call(client, fn, **args)
        self.assertEqual(r.status_code, status, f"{fn}: {r.content[:400]!r}")
        return r.json().get("message") if status == 200 else r.json()

    def _boot(self, client) -> dict:
        page = client.get("/command-center").content.decode()
        return json.loads(re.search(r"window\.CC_BOOT = (.*?);\s*$", page, re.M).group(1))

    def _grant(self, *sections, who="manager@test.com"):
        return self._ok("set_settings_access", username=who, sections=list(sections))

    def test_boot_and_a_plain_manager(self):
        self.assertEqual(self._boot(self.admin)["settings_sections"],
                         ["people", "businesses", "claude", "email", "keys", "changes"])
        self.assertEqual(self._boot(self.manager)["settings_sections"], [])
        for fn in ("people", "businesses", "credentials", "email", "notifications",
                   "set_email", "test_email", "set_settings_access", "changes"):
            self._as(self.manager, fn, 403, username="manager@test.com", sections=["people"])
        self._grant("businesses", "keys")
        self.assertEqual(self._boot(self.manager)["settings_sections"], ["businesses", "keys"])
        # no longer a manager: no Settings, and the grants are gone for good
        self._ok("set_manager", username="manager@test.com", on=0)
        self.assertEqual(self._boot(self.admin)["settings_sections"][0], "people")
        self._ok("set_manager", username="manager@test.com", on=1)
        self.assertEqual(self._boot(self.manager)["settings_sections"], [])

    def test_a_businesses_delegate(self):
        self._grant("businesses")
        out = self._as(self.manager, "add_business", business_name="Test Medical Ltd",
                       site_url="https://erp.test", api_key="key-abcd1234",
                       api_secret="biz-secret-value-71x")
        self.assertEqual(out["access"]["reads_as"], "reader@test.com")
        self.assertTrue(self._as(self.manager, "test_business", name="Test Medical Ltd")["ok"])
        self.assertEqual(self._as(self.manager, "set_paused", name="Test Medical Ltd",
                                  paused=1)["status"], "Paused")
        self._as(self.manager, "set_paused", name="Test Medical Ltd", paused=0)
        self._as(self.manager, "reload_business", name="Test Medical Ltd")
        self.assertEqual(len(self._as(self.manager, "businesses")), 1)
        refused = [("people", {}), ("add_person", {"email": "x@test.com", "set_later": 1}),
                   ("claude", {}), ("set_claude_key", {"key": "sk-ant-" + "x" * 30}),
                   ("email", {}), ("set_email", {"host": "smtp.test.com", "sender": "a@test.com"}),
                   ("test_email", {"to": "a@test.com"}), ("notifications", {}),
                   ("set_settings_access", {"username": "manager@test.com",
                                            "sections": ["people"]}),
                   ("credentials", {}), ("changes", {})]
        for fn, args in refused:
            body = self._as(self.manager, fn, 403, **args)
            self.assertNotIn("Traceback", json.dumps(body))
        self.assertNotIn("command_center_anthropic_key", json.load(open(self.cfg)))
        self.assertNotIn("mail", json.load(open(self.cfg)))
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        self.assertIn("connected Test Medical Ltd", whats)

    def test_a_people_delegate(self):
        U = get_user_model()
        self._grant("people")
        # adds managers, but never an administrator
        self._as(self.manager, "add_person", 403, email="boss2@test.com", full_name="B Two",
                 set_later=1, admin=1)
        self.assertFalse(U.objects.filter(username="boss2@test.com").exists())
        p = self._as(self.manager, "add_person", email="ama@test.com", full_name="Ama Mensah",
                     password="a-long-test-pass-3", password2="a-long-test-pass-3", manager=1)
        self.assertTrue(p["is_manager"] and not p["is_admin"])
        # changes managers: deactivate, reactivate, reset the password, rename
        self.assertFalse(self._as(self.manager, "set_active", username="ama@test.com", on=0)["active"])
        self.assertTrue(self._as(self.manager, "set_active", username="ama@test.com", on=1)["active"])
        self._as(self.manager, "reset_password", username="ama@test.com",
                 password="another-long-pass-4", password2="another-long-pass-4")
        self.assertTrue(Client().login(username="ama@test.com", password="another-long-pass-4"))
        # never: make an administrator, give Settings access, touch an administrator
        self._as(self.manager, "set_admin", 403, username="ama@test.com", on=1)
        self._as(self.manager, "set_settings_access", 403, username="ama@test.com",
                 sections=["people"])
        for fn, args in (("set_active", {"on": 0}), ("set_manager", {"on": 0}),
                         ("reset_password", {"password": "hijack-long-pass-9",
                                             "password2": "hijack-long-pass-9"}),
                         ("reset_password", {"set_later": 1}),
                         ("update_person", {"full_name": "Someone Else"})):
            self._as(self.manager, fn, 403, username="boss@test.com", **args)
        boss = U.objects.get(username="boss@test.com")
        self.assertTrue(boss.is_superuser and boss.is_active and boss.check_password("a-long-test-pass-5"))
        self.assertEqual(boss.first_name, "")
        self.assertFalse(U.objects.get(username="ama@test.com").is_superuser)
        # nor anyone else with Settings access (that would reach past what was given)
        self._grant("businesses", who="ama@test.com")
        self._as(self.manager, "set_active", 403, username="ama@test.com", on=0)
        self._as(self.manager, "reset_password", 403, username="ama@test.com",
                 password="hijack-long-pass-9", password2="hijack-long-pass-9")
        self.assertTrue(U.objects.get(username="ama@test.com").is_active)
        # nor their own access; their own password, yes
        self._as(self.manager, "set_manager", 403, username="manager@test.com", on=0)
        self._as(self.manager, "reset_password", username="manager@test.com",
                 password="my-own-long-pass-8", password2="my-own-long-pass-8")
        listed = {x["username"]: x for x in self._as(self.manager, "people")}
        self.assertTrue(listed["boss@test.com"]["protected"])
        self.assertEqual(listed["ama@test.com"]["settings_access"], ["businesses"])
        self._as(self.manager, "businesses", 403)
        self._as(self.manager, "claude", 403)
        self._as(self.manager, "email", 403)
        for body in self.bodies:
            self.assertNotIn("pbkdf2", body)

    def test_a_keys_delegate(self):
        self._ok("add_business", business_name="Test Medical Ltd", site_url="https://erp.test",
                 api_key="key-abcd1234", api_secret="biz-secret-value-71x")
        boss_key = self._ok("set_credential", user="boss@test.com", business_code="test_medical_ltd",
                            api_key="bkey-1111", api_secret="boss-secret-1")
        self._grant("keys")
        mine = self._as(self.manager, "set_credential", user="manager@test.com",
                        business_code="test_medical_ltd", api_key="pkey-5678",
                        api_secret="personal-secret-2")
        self.assertEqual([c["user"] for c in self._as(self.manager, "credentials")],
                         ["manager@test.com"])
        self.assertEqual(len(self._ok("credentials")), 2)
        self._as(self.manager, "set_credential", 403, user="boss@test.com",
                 business_code="test_medical_ltd", api_key="evil", api_secret="evil")
        self._as(self.manager, "remove_credential", 403, name=boss_key["name"])
        self._as(self.manager, "test_credential", 403, name=boss_key["name"])
        self.assertTrue(self._as(self.manager, "test_credential", name=mine["name"])["ok"])
        self._as(self.manager, "add_business", 403, business_name="Other Ltd",
                 site_url="https://erp.other", api_key="k", api_secret="s")
        self._as(self.manager, "add_person", 403, email="x@test.com", set_later=1)

    def test_grants_by_the_administrator_are_audited(self):
        p = self._grant("businesses", "keys")
        self.assertEqual(p["settings_access"], ["businesses", "keys"])
        p = self._grant("businesses")
        self.assertEqual(p["settings_access"], ["businesses"])
        self.assertIn("Nothing was changed", self._call(
            self.admin, "set_settings_access", username="manager@test.com",
            sections=["businesses"]).content.decode())
        self.assertIn("Only Businesses", self._call(
            self.admin, "set_settings_access", username="manager@test.com",
            sections=["claude"]).content.decode())
        self.assertIn("administrator", self._call(
            self.admin, "set_settings_access", username="boss@test.com",
            sections=["people"]).content.decode())
        self._ok("add_person", email="plain@test.com", full_name="Not Manager", set_later=1, manager=0)
        self.assertIn("not a manager", self._call(
            self.admin, "set_settings_access", username="plain@test.com",
            sections=["people"]).content.decode())
        self.assertEqual(self._grant(who="manager@test.com")["settings_access"], [])
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        for phrase in ("gave manager@test.com access to Settings: Businesses",
                       "gave manager@test.com access to Settings: Personal ERPNext Keys",
                       "took away manager@test.com's access to Settings: Personal ERPNext Keys",
                       "took away manager@test.com's access to Settings: Businesses"):
            self.assertIn(phrase, whats)
        from django.contrib.admin.models import LogEntry
        e = LogEntry.objects.filter(change_message__contains="gave manager@test.com").first()
        self.assertEqual(e.user.username, "boss@test.com")

    def test_email_settings_and_test_email(self):
        import smtplib
        from insights.core.models import ErrorLog
        n = self._ok("notifications")
        self.assertFalse(n["email_configured"])
        self.assertIsNone(n["last_attempt"])
        self.assertFalse(self._ok("test_email", to="boss@test.com")["ok"])
        self.assertIn("Type the password", self._call(
            self.admin, "set_email", host="smtp.test.com", port=587, security="starttls",
            user="reports@test.com").content.decode())
        self.assertIn("mail server", self._call(
            self.admin, "set_email", host="smtp test", sender="a@test.com").content.decode())
        shown = self._ok("set_email", host="smtp.test.com", port="587", security="starttls",
                         user="reports@test.com", password=self.MAIL_PW,
                         sender="reports@test.com", sender_name="Reports")
        self.assertTrue(shown["configured"] and shown["has_password"])
        self.assertNotIn("password", shown)
        stored = json.load(open(self.cfg))["mail"]
        self.assertEqual((stored["host"], stored["port"], stored["user"], stored["password"],
                          stored["tls"]), ("smtp.test.com", 587, "reports@test.com",
                                           self.MAIL_PW, True))
        # a blank password keeps the stored one
        self._ok("set_email", host="smtp.test.com", port=587, security="starttls",
                 user="reports@test.com", sender="reports@test.com", sender_name="Board Reports")
        self.assertEqual(json.load(open(self.cfg))["mail"]["password"], self.MAIL_PW)
        self._ok("email")
        for body in self.bodies:
            self.assertNotIn(self.MAIL_PW, body)
        whats = " | ".join(c["what"] for c in self._ok("changes"))
        self.assertIn("set up email: server smtp.test.com on port 587 (STARTTLS)", whats)
        self.assertNotIn(self.MAIL_PW, whats)

        # the test email goes out with exactly the stored settings
        with mock.patch("smtplib.SMTP") as smtp:
            out = self._ok("test_email", to="boss@test.com")
        self.assertTrue(out["ok"], out)
        smtp.assert_called_once_with("smtp.test.com", 587, timeout=30)
        s = smtp.return_value
        s.starttls.assert_called_once()
        s.login.assert_called_once_with("reports@test.com", self.MAIL_PW)
        sent = s.send_message.call_args[0][0]
        self.assertEqual((sent["To"], sent["From"]), ("boss@test.com",
                                                      "Board Reports <reports@test.com>"))
        self.assertTrue(self._ok("notifications")["last_attempt"]["ok"])
        # SSL on 465
        self._ok("set_email", host="smtp.test.com", port=465, security="ssl",
                 user="reports@test.com", sender="reports@test.com", sender_name="Board Reports")
        with mock.patch("smtplib.SMTP_SSL") as ssl_smtp, mock.patch("smtplib.SMTP") as plain:
            self.assertTrue(self._ok("test_email", to="boss@test.com")["ok"])
        self.assertEqual(ssl_smtp.call_args[0], ("smtp.test.com", 465))
        plain.assert_not_called()
        # failures in plain words, in the error log, and as the last attempt
        with mock.patch("smtplib.SMTP_SSL") as ssl_smtp:
            ssl_smtp.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"no")
            out = self._ok("test_email", to="boss@test.com")
        self.assertFalse(out["ok"])
        self.assertIn("refused the username or password", out["says"])
        with mock.patch("smtplib.SMTP_SSL", side_effect=ConnectionRefusedError(61, "refused")):
            out = self._ok("test_email", to="boss@test.com")
        self.assertIn("Could not connect to the mail server at smtp.test.com on port 465", out["says"])
        self.assertTrue(ErrorLog.objects.filter(title__startswith="Email not sent").exists())
        last = self._ok("notifications")["last_attempt"]
        self.assertFalse(last["ok"])
        self.assertIn("Could not connect", last["error"])

    def test_scheduled_reports_use_the_email_settings(self):
        import frappe
        from insights.compat import run_as
        from insights.compat.runtime import MailNotConfigured
        from insights.core.models import CommandCenterReportSchedule, ErrorLog
        # not set up: never silently dropped -- raised, logged, and the schedule says so
        with run_as("boss@test.com"), self.assertRaises(MailNotConfigured):
            frappe.sendmail(recipients=["a@test.com"], subject="Weekly", message="<p>x</p>")
        self.assertTrue(ErrorLog.objects.filter(title="Email not sent: email is not set up").exists())
        sched = CommandCenterReportSchedule.objects.create(
            name="rs-1", report="rp01", business_code="test_medical_ltd", enabled=1,
            recipients="a@test.com", run_as="boss@test.com")
        stub = {"answer": "All is well.\n\nMore.", "checked": [], "model": "m"}
        with mock.patch("command_center.ask.engine.analyst_enabled", lambda: True), \
                mock.patch("command_center.ask.agent.answer", lambda *a, **k: stub), \
                mock.patch("command_center.api.export.pdf_bytes", lambda *a, **k: b"%PDF"), \
                mock.patch("command_center.api.export._business", lambda c: "Test Medical Ltd"), \
                mock.patch("command_center.api.export._as_of", lambda: "15 Nov 2026"):
            from command_center.api import reports
            with run_as("boss@test.com"):
                reports.send_scheduled("rs-1")
            sched.refresh_from_db()
            self.assertTrue(sched.last_status.startswith("Failed"), sched.last_status)
            self.assertIn("Email is not set up", sched.last_status)
            failing = self._ok("notifications")["failing"]
            self.assertEqual(failing[0]["report"], "Executive Summary")
            # set up: the same schedule goes out through the stored server
            self._ok("set_email", host="smtp.test.com", port=587, security="starttls",
                     user="reports@test.com", password=self.MAIL_PW, sender="reports@test.com")
            with mock.patch("smtplib.SMTP") as smtp, run_as("boss@test.com"):
                reports.send_scheduled("rs-1")
        smtp.assert_called_once_with("smtp.test.com", 587, timeout=30)
        smtp.return_value.login.assert_called_once_with("reports@test.com", self.MAIL_PW)
        self.assertEqual(smtp.return_value.send_message.call_args[0][0]["To"], "a@test.com")
        sched.refresh_from_db()
        self.assertTrue(sched.last_status.startswith("Sent to 1"), sched.last_status)
        n = self._ok("notifications")
        self.assertEqual((n["schedules_on"], n["failing"]), (1, []))


class DocumentLinks(TransactionTestCase):
    """A record opens in its own business's ERPNext, at the document -- never at this
    platform's administration (which sent every link to <business>/admin/, a 404)."""

    databases = {"default", "aux"}

    def test_links(self):
        from command_center.api.facts import _document_url
        from insights.compat.utils import get_url_to_form
        sites = {"gms": "https://erp.example.com"}
        self.assertEqual(
            _document_url(sites, {"business_code": "gms", "src_doctype": "Sales Invoice",
                                  "src_name": "ACC-SINV-2026-00012"}),
            "https://erp.example.com/app/sales-invoice/ACC-SINV-2026-00012")
        self.assertEqual(
            _document_url(sites, {"business_code": "gms", "src_doctype": "Purchase Order",
                                  "src_name": "PUR-ORD 2026/7"}),
            "https://erp.example.com/app/purchase-order/PUR-ORD%202026%2F7")
        # the platform's own records still open in its administration
        self.assertIn("/admin/core/connectedbusiness/", get_url_to_form("Connected Business", "X"))
        self.assertNotIn("/admin", _document_url(sites, {"business_code": "gms",
                                                          "src_doctype": "Task", "src_name": "T-1"}))


class NothingIllustrative(TransactionTestCase):
    """The department screens carry nothing that is not the business's own: every card
    and tile names a figure, every panel has a builder, every finding box is filled by
    the screen's findings, and the markup and explainers name no customer, supplier,
    person, place, year or currency of any one business."""

    NAMES = ("UBUNTU", "HAIRASH", "SICHUAN", "CYNSEL", "EJURA", "SUNYANI", "KUMASI", "ACCRA",
             "SAMUEL", "SIMON", "GIGMANN", "SAMKWARTH", "AGAHF", "QINGDAO", "ROSSY", "LILIAN",
             "VINEYARD", "KING JO", "ILEE", "ST JOHN", "KORLE", "GMSL", "HITECH", "OSEIKOJOKROM")

    def _load(self):
        import html as _html
        from pathlib import Path
        from django.conf import settings
        base = Path(settings.BASE_DIR, "frontend/src/legacy")
        views = json.loads((base / "views.json").read_text())
        extras = json.loads((base / "extras.json").read_text())
        hydrate = (base / "hydrate.js").read_text()
        return views, extras, hydrate, _html

    @staticmethod
    def _js_map(src, name, tiles=False):
        body = src[src.index(f"export const {name} = {{"):]
        body = body[:body.index("\n};")]
        out = {}
        for m in re.finditer(r"^  (\w+): \{$(.*?)^  \},?$", body, re.S | re.M):
            pat = (r'(?:"([^"]+)"|(\w+)):\s*\{\s*key:\s*"(\w+)"' if tiles
                   else r'(?:"([^"]+)"|(\w+)):\s*"(\w+)"')
            out[m.group(1)] = {(a or b): k for a, b, k in re.findall(pat, m.group(2))}
        for m in re.finditer(r"^  (\w+): \{\},?$", body, re.M):
            out[m.group(1)] = {}
        return out

    def test_every_card_tile_and_panel_is_answered(self):
        from command_center.api.panels import FINDINGS, SCREENS
        from command_center.kpi.live import LIVE
        from command_center.kpi.registry import load_all
        views, _, hydrate, _html = self._load()
        cards = self._js_map(hydrate, "CARD_KPIS")
        tiles = self._js_map(hydrate, "TILE_KPIS", tiles=True)
        known = set(load_all()) | set(LIVE)
        for view in DEPARTMENT_VIEWS:
            markup = _html.unescape(views[view])
            for label in re.findall(r'<div class="lab">([^<]+)</div>', markup):
                key = cards.get(view, {}).get(label.strip())
                self.assertTrue(key, f"{view}: card {label!r} has no figure")
                self.assertIn(key, known, f"{view}: card {label!r} names unknown figure {key}")
            for label in re.findall(r'<div class="l">([^<]+)</div>', markup):
                key = tiles.get(view, {}).get(label.strip())
                self.assertTrue(key, f"{view}: tile {label!r} has no figure")
                self.assertIn(key, known, f"{view}: tile {label!r} names unknown figure {key}")
            for block in markup.split('<div class="panel">')[1:]:
                title = re.search(r"<b>([^<]+)</b>", block).group(1).strip()
                if 'class="bk' in block:
                    continue   # a panel of tiles: the tiles are its figures
                self.assertIn(title, SCREENS.get(view, {}), f"{view}: panel {title!r} has no builder")
            if 'class="warn"' in markup:
                self.assertIn(view, FINDINGS, f"{view} has finding boxes and no findings")

    def test_no_business_of_its_own_in_the_markup(self):
        views, extras, _, _html = self._load()
        bad = re.compile(r"demo|illustrative|sample|seeded|extract|this copy|\b(?:19|20)\d\d\b|GHS|"
                         + "|".join(map(re.escape, self.NAMES)), re.I)
        for view in DEPARTMENT_VIEWS:
            markup = _html.unescape(views[view])
            hit = bad.search(markup)
            self.assertIsNone(hit, f"{view} markup says {hit and markup[max(0, hit.start() - 60):hit.end() + 20]!r}")
            self.assertNotIn("openDrawer(", markup, f"{view} opens a static drawer")
            for key in set(re.findall(r"explain\('([a-z0-9_]+)'\)", markup)):
                text = _html.unescape(extras["explainers"].get(key, ""))
                self.assertTrue(text, f"{view}: explainer {key} is missing")
                hit = bad.search(text)
                self.assertIsNone(hit, f"{view}: explainer {key} says "
                                       f"{hit and text[max(0, hit.start() - 60):hit.end() + 20]!r}")


# ---------------------------------------------------------------------------------------
# The management screens: Home, Executive Summary, Today, Business Overview, Business
# Health, Approvals, Outstanding Tasks, Risk and Compliance, Systems and Access, Internal
# Audit, Reports, Ask AI and the access-denied page. Nothing on them may be a sample.
# ---------------------------------------------------------------------------------------
CORE_VIEWS = ("command", "brief", "myday", "ops", "health", "approvals", "delegation", "risk",
              "it", "aud", "reports", "ask", "denied")
# A business's own names, figures and dates never sit in the markup: they are read.
NOT_IN_MARKUP = re.compile(
    r"Gigmann|Biomed|Samuel|Simon|Moses|Nketiah|UBUNTU|Ubuntu|HAIRASH|Sunyani|Kumasi|Accra|"
    r"SICHUAN|CYNSEL|Ejura|EJURA|A1 MEDICAL|PUR-ORD|ACC-PAY|SAL-ORD|PROJ-\d|"
    r"[Dd]emo|[Ii]llustrative|[Ss]eeded|prototype|\bGHS\b|\b(19|20)\d{2}\b")


def _js_map(src: str, name: str) -> dict:
    """view -> its slice of one exported label map in a legacy/*.js file."""
    body = re.search(r"export const %s = \{(.*?)\n\};" % name, src, re.S)
    body = body.group(1) if body else ""
    starts = [(m.group(1), m.end()) for m in re.finditer(r"^  (\w+): \{", body, re.M)]
    out = {}
    for i, (view, frm) in enumerate(starts):
        to = starts[i + 1][1] - len(f"  {starts[i + 1][0]}: {{") if i + 1 < len(starts) else len(body)
        out[view] = {html_unescape(l.strip()) for l in re.findall(
            r'^\s*"?([^":\n/]+?)"?:\s*(?:"[a-z0-9_]+"|\{\s*key:)', body[frm:to], re.M)}
    return out


def html_unescape(s):
    import html
    return html.unescape(s)


class ManagementScreens(TransactionTestCase):
    databases = {"default", "aux"}

    def _legacy(self, name):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "frontend" / "src" / "legacy" / name).read_text()

    def test_markup_holds_no_sample(self):
        views = json.loads(self._legacy("views.json"))
        extras = json.loads(self._legacy("extras.json"))
        nav = json.loads(self._legacy("nav.json"))
        hyd, work, home = self._legacy("hydrate.js"), self._legacy("work.js"), self._legacy("home.js")
        cards, tiles, work_tiles = _js_map(hyd, "CARD_KPIS"), _js_map(hyd, "TILE_KPIS"), _js_map(work, "WORK_TILES")
        questions = set(re.findall(r'\["score_\w+", "[^"]+", "([^"]+)"\]', home))
        self.assertEqual(len(questions), 6, "home.js names the six Business Health questions")
        self.assertIn("score_approvals", home, "Were the right people asked? feeds Home's gauge")
        for view in CORE_VIEWS:
            page = views[view]
            # every card and tile has a figure or a guide behind it
            for label in re.findall(r'class="lab">(.*?)</div>', page):
                self.assertIn(html_unescape(label), cards.get(view, set()),
                              f"{view}: card {label!r} has no figure behind it")
            for block in re.split(r'(?=<div class="bk)', page)[1:]:
                label = re.search(r'class="l">(.*?)</div>', block, re.S)
                self.assertTrue(label, f"{view}: a tile with no label")
                label = html_unescape(label.group(1)).strip()
                self.assertTrue(label in tiles.get(view, set()) or label in work_tiles.get(view, set())
                                or (view == "health" and label in questions),
                                f"{view}: tile {label!r} has no figure behind it")
            # no designed alert, request or task, and no sample rows in a table
            self.assertNotIn('class="alert ', page, f"{view} carries a designed alert")
            if view not in ("reports", "it"):
                self.assertNotRegex(page, r"<tbody>\s*<tr", f"{view} carries sample table rows")
            # nothing about one business, no sample wording, no year, no currency
            hit = NOT_IN_MARKUP.search(page)
            self.assertIsNone(hit, f"{view} names {hit and hit.group(0)!r}: "
                                   f"{hit and page[max(0, hit.start() - 80):hit.end() + 40]!r}")
            for key in set(re.findall(r"explain\((?:'|&#39;)(\w+)", page)):
                text = extras["explainers"].get(key, "")
                hit = NOT_IN_MARKUP.search(text)
                self.assertIsNone(hit, f"explainer {key!r} (on {view}) names "
                                       f"{hit and hit.group(0)!r}")
        # the static drills and canned answers are gone, and these screens open no drawer
        self.assertEqual((extras["drill"], extras["brain"]), ({}, []))
        for view in CORE_VIEWS:
            self.assertNotRegex(views[view], r"openDrawer\((?:'|&#39;)\w", f"{view} opens a static drawer")
        # nav badges are never typed in: a number in the sidebar must be counted
        for group in nav["groups"]:
            for item in group["items"]:
                self.assertEqual(item["badge"], "", f"nav {item['key']} carries a typed badge")
        # the check can fail: a typed name, a sample alert, an unmapped card
        self.assertIsNotNone(NOT_IN_MARKUP.search('<b>UBUNTU</b> owes <span class="cx">GHS</span>'))
        self.assertIsNone(NOT_IN_MARKUP.search(views["ops"]))
        self.assertNotIn("Not a real label", cards.get("aud", set()))

    def test_live_figures_guides_and_unreachable(self):
        import requests

        from command_center import install
        from command_center.api import ingest
        from insights.compat import run_as

        Group.objects.get_or_create(name="Insights Dashboard Manager")
        fake = FakeERPNext()
        answer = fake.answer

        def no_findings(m, p):
            # Nothing recorded as a finding or an obligation on this ERPNext yet.
            if m == "frappe.client.get_count" and p.get("doctype") in ("Non Conformance", "Contract"):
                return _R(200, {"message": 0})
            return answer(m, p)
        fake.answer = no_findings
        from django.conf import settings
        from cryptography.fernet import Fernet
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        up = [mock.patch("requests.get", fake("GET")), mock.patch("requests.post", fake("POST")),
              mock.patch("time.sleep", lambda s: None)]
        for p in up:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in up])
        with run_as("Administrator"):
            install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
            ingest.run_all(full=True)
        U = get_user_model()
        m = U.objects.create_user("boss@test.com", "boss@test.com", "a-long-test-pass-9")
        m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        c = Client()
        self.assertTrue(c.login(username="boss@test.com", password="a-long-test-pass-9"))

        def post(method, **args):
            r = c.post(f"/api/method/{method}", json.dumps(args), content_type="application/json")
            self.assertEqual(r.status_code, 200, f"{method}: {r.content[:300]!r}")
            return r.json()["message"]

        from command_center.kpi.live_governance import LIVE as GOV
        got = post("command_center.api.kpi.get", keys=sorted(GOV), business_code="test_medical_ltd")
        for key, fig in got.items():
            self.assertIn(fig["data_status"]["state"], ("live", "needs_setup", "stale"), f"{key}: {fig}")
        # nothing recorded: a guide naming the ERPNext page, never a figure
        for key, path in (("findings_open", "/app/non-conformance"), ("deadlines_overdue", "/app/contract")):
            st = got[key]["data_status"]
            self.assertEqual(st["state"], "needs_setup", key)
            self.assertIsNone(got[key]["value"])
            self.assertIn(path, st["guide"]["href"])
            self.assertTrue(st["guide"]["steps"])
        self.assertEqual(got["score_access"]["note"], "no active accounts")  # the fake has none
        self.assertIsNotNone(got["control_score"]["value"])
        self.assertEqual(got["versions_deletable"]["value"], 0)
        # the risk table is a guide too, and the platform's own people are listed
        risk = post("command_center.api.panels.get", view="risk", business_code="test_medical_ltd")
        self.assertEqual(risk["panels"]["Obligations and deadlines"]["kind"], "guide")
        it = post("command_center.api.panels.get", view="it", business_code="test_medical_ltd")
        people = it["panels"]["Who can sign in to this platform"]["rows"]
        self.assertIn("boss@test.com", [r["cells"][0]["sub"] for r in people])
        # no personal key linked: the work screens get a guide, not someone else's queue
        work = post("command_center.api.work.summary", business_code="test_medical_ltd")
        self.assertFalse(work["available"])
        self.assertIn("Personal ERPNext Keys", " ".join(work["guide"]["steps"]))
        # alerts raised for the first time are emailed once; without mail it is recorded
        alerts = post("command_center.api.alerts.open_alerts", business_code="test_medical_ltd")
        loud = [a for a in alerts["alerts"] if a["severity"] in ("crit", "high")]
        if loud:
            self.assertTrue(all((a["emailed"] or "").startswith("Not emailed") for a in loud), loud)
        self.assertTrue(post("command_center.api.reach.status",
                             business_code="test_medical_ltd")["reachable"])

        # the business's ERPNext stops answering
        def down(*a, **k):
            raise requests.ConnectionError("no route to host")
        with mock.patch("requests.get", down), mock.patch("requests.post", down):
            from django.core.cache import cache
            cache.clear()
            got = post("command_center.api.kpi.get", keys=["users_active", "users_disabled"],
                       business_code="test_medical_ltd")
            self.assertEqual(got["users_active"]["data_status"]["state"], "unreachable")
            self.assertEqual(got["users_disabled"]["data_status"]["state"], "unreachable")
            st = post("command_center.api.reach.status", business_code="test_medical_ltd")
            self.assertFalse(st["reachable"])
            self.assertEqual(st["name"], "Test Medical Ltd")
            self.assertTrue(st["since"])
            from command_center.api import work as work_api
            from command_center.connectors.registry import connector_for
            with mock.patch.object(work_api, "_source", lambda code: (
                    work_api._Remote(connector_for("test_medical_ltd")), None)):
                w = post("command_center.api.work.summary", business_code="test_medical_ltd")
            self.assertTrue(w["unreachable"])
            self.assertIn("Can't reach", w["reason"])
            self.assertFalse(post("command_center.api.reach.retry",
                                  business_code="test_medical_ltd")["reachable"])
        # it answers again: Retry finds it, and the status recovers by itself
        st = post("command_center.api.reach.retry", business_code="test_medical_ltd")
        self.assertTrue(st["reachable"])
        self.assertIsNone(st["since"])
