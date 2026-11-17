"""Security and operations fixes of 17 Nov 2026, each with the bug it reproduces:

    .venv-platform/bin/python manage.py test insights.test_security

  WritesRefuseGet            writes answered GET, which carries no CSRF token
  SignOnTakesNoAccount       single sign-on matched any account by email, the
                             administrator's included, and ignored the customer's seats
  AddressMoveForgetsSecrets  a new business address received the stored secrets
  AnalystWriteGuard          `SET SESSION` counted as a write on MariaDB, so every
                             question with a lookup was rolled back
  WriteTimeoutIsUnconfirmed  a slow write was a failure and marked the business down
  LockoutCountsEveryFailure  the lockout counters were read-then-written by 8 threads
  KeysNeverLogged            the Gemini key travelled in the URL and reached the log
  KeysDelegateRule           a keys delegate could change keys of people with Settings
"""

from __future__ import annotations

import json
import threading
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TransactionTestCase

# The module, not its classes: a TestCase imported here would be collected and run again.
from insights import tests as _tests

MANAGER = "Insights Dashboard Manager"


def _platform(test):
    """A signed-in administrator and manager, a fake ERPNext, a temporary config: the
    Settings tests' own set-up (insights/tests.py SettingsPage)."""
    _tests.SettingsPage.setUp(test)
    test.addCleanup(_tests.SettingsPage.tearDown, test)


def _business(test, name="Test Medical Ltd", url="https://erp.test"):
    r = test.admin.post("/api/method/insights.core.platform_settings.add_business",
                        json.dumps({"business_name": name, "site_url": url,
                                    "api_key": "key-abcd1234", "api_secret": "biz-secret-value-71x"}),
                        content_type="application/json")
    test.assertEqual(r.status_code, 200, r.content[:300])
    return r.json()["message"]["business"]


class WritesRefuseGet(TransactionTestCase):
    """Every endpoint answers POST only unless it names GET itself, and only the
    sign-on redirects and three read-only diagnostics do. A GET to a write is refused
    (405) before it runs; a POST still needs the request token."""

    databases = {"default", "aux"}
    GET_ALLOWED = {"command_center.api.sso.start", "command_center.api.sso.callback",
                   "command_center.api.diagnostics.deployed",
                   "command_center.api.diagnostics.contains",
                   "command_center.api.export.pdf_diagnostics"}
    WRITES = ["command_center.api.actions.create_task", "command_center.api.actions.submit_document",
              "command_center.api.actions.assign_to", "command_center.api.work.review",
              "command_center.api.alerts.act", "command_center.api.credentials.link_account",
              "command_center.api.credentials.unlink_account", "command_center.api.ingest.run",
              "command_center.api.ingest.run_all", "command_center.api.ask.answer",
              "command_center.api.reach.retry", "command_center.api.ask.check_analyst"]

    def setUp(self):
        _platform(self)

    def _all_endpoints(self):
        import importlib
        import pkgutil

        import command_center.api as api
        from insights.compat import WHITELIST
        for m in pkgutil.iter_modules(api.__path__):
            importlib.import_module(f"command_center.api.{m.name}")
        for m in ("insights.core.platform_settings", "insights.core.security", "insights.core.plans"):
            importlib.import_module(m)
        return WHITELIST

    def test_only_the_named_endpoints_answer_get(self):
        found = {k for k, v in self._all_endpoints().items() if "GET" in v["methods"]}
        self.assertEqual(found, self.GET_ALLOWED)

    def test_a_write_by_get_is_refused_before_it_runs(self):
        self._all_endpoints()
        with mock.patch("command_center.api.ingest.run_all") as ran, \
                mock.patch("command_center.api.actions.create_task") as made:
            for method in self.WRITES:
                r = self.manager.get(f"/api/method/{method}?business_code=x&subject=hi")
                self.assertEqual(r.status_code, 405, f"{method} answered a GET: {r.status_code}")
        self.assertFalse(ran.called or made.called)

    def test_a_post_without_the_request_token_is_refused(self):
        c = Client(enforce_csrf_checks=True)
        self.assertTrue(c.login(username="manager@test.com", password="a-long-test-pass-6"))
        r = c.post("/api/method/command_center.api.reach.retry", "{}",
                   content_type="application/json")
        self.assertEqual(r.status_code, 403)
        page = c.get("/command-center")
        token = c.cookies["csrftoken"].value
        self.assertEqual(page.status_code, 200)
        r = c.post("/api/method/command_center.api.businesses.get_visible_businesses", "{}",
                   content_type="application/json", HTTP_X_FRAPPE_CSRF_TOKEN=token)
        self.assertEqual(r.status_code, 200, r.content[:200])


class SignOnTakesNoAccount(TransactionTestCase):
    """A business's ERPNext vouches for an email; it never opens an account the sign-in
    did not make itself for that business (or one of the same customer): not an
    administrator's, not a Settings delegate's, not one added by hand. A newcomer takes
    a seat, and is refused when none is free."""

    databases = {"default", "aux"}

    def setUp(self):
        _platform(self)
        _business(self)
        U = get_user_model()
        g = Group.objects.get(name=MANAGER)
        self.hand = U.objects.create_user("hand@test.com", "hand@test.com", "a-long-test-pass-7")
        self.hand.groups.add(g)
        self.delegate = U.objects.create_user("delegate@test.com", "delegate@test.com", "x-long-pass-8")
        self.delegate.groups.add(g, Group.objects.get_or_create(name="Settings: People")[0])
        self.sso = U.objects.create_user("sso@test.com", "sso@test.com")
        self.sso.groups.add(g)
        from insights.core.models import DefaultValue
        for u in ("sso@test.com", "delegate@test.com", "boss@test.com"):
            DefaultValue.objects.create(parent=u, defkey="cc_sso_business",
                                        defvalue="test_medical_ltd")

    def _sign_in(self, email, members=None):
        from command_center.api import sso
        from insights.compat import run_as
        b = type("B", (), {"business_code": "test_medical_ltd",
                           "business_name": "Test Medical Ltd"})()
        with mock.patch("command_center.api.ingest.erp_members",
                        lambda code, role: set(members if members is not None else [email])):
            with run_as("Guest"):
                try:
                    return sso._approved({"email": email, "given_name": "New"}, b)
                except sso.Refused as e:
                    return e

    def test_existing_accounts_it_did_not_make(self):
        from command_center.api.sso import Refused
        for who, says in (("boss@test.com", "administrator"), ("hand@test.com", "directly"),
                          ("delegate@test.com", "Settings access")):
            got = self._sign_in(who)
            self.assertIsInstance(got, Refused, f"{who} was signed in by the business's ERPNext")
            self.assertEqual(got.why, "own_account")
            self.assertIn(says, got.detail)
        self.assertEqual(self._sign_in("sso@test.com"), "sso@test.com")
        self.assertEqual(self._sign_in("new@test.com"), "new@test.com")

    def test_a_newcomer_takes_a_seat(self):
        from command_center.api.sso import Refused
        from insights.core import plans
        M = plans._models()
        c = M.ClientAccount.objects.create(name="Test Customer", limits=json.dumps({"seats": 1}))
        M.ClientBusiness.objects.create(client=c, business_code="test_medical_ltd")
        # sso@test.com came in through it already: the one seat is taken
        got = self._sign_in("late@test.com")
        self.assertIsInstance(got, Refused)
        self.assertEqual(got.why, "no_seat")
        self.assertFalse(get_user_model().objects.filter(username="late@test.com").exists())
        self.assertEqual(self._sign_in("sso@test.com"), "sso@test.com")


class AddressMoveForgetsSecrets(TransactionTestCase):
    """A business pointed at another server needs its key and secret typed again; the
    stored secret, the sign-in's client secret and the managers' own keys are removed,
    so none is ever sent to the new address."""

    databases = {"default", "aux"}

    def setUp(self):
        _platform(self)
        _business(self)

    def _update(self, **args):
        return self.admin.post("/api/method/insights.core.platform_settings.update_business",
                               json.dumps({"name": "Test Medical Ltd", **args}),
                               content_type="application/json")

    def test_moving_needs_the_secret_again_and_forgets_the_old(self):
        from insights.compat import documents, run_as
        from insights.core.models import CommandCenterSiteCredential, ConnectedBusiness, Secret
        documents.set_password("Connected Business", "Test Medical Ltd", "sso_client_secret", "oauth-s")
        ConnectedBusiness.objects.filter(pk="Test Medical Ltd").update(sso_client_id="cid")
        with run_as("Administrator"):
            import frappe
            doc = frappe.new_doc("Command Center Site Credential")
            doc.update({"user": "manager@test.com", "business_code": "test_medical_ltd",
                        "api_key": "pk", "api_secret": "personal-1"})
            doc.save()
        # another server, no secret typed: refused, and nothing changed
        r = self._update(site_url="https://evil.example")
        self.assertEqual(r.status_code, 417)
        self.assertIn("type the API key and the API secret", r.content.decode())
        self.assertEqual(ConnectedBusiness.objects.get(pk="Test Medical Ltd").site_url, "https://erp.test")
        self.assertEqual(documents.get_password("Connected Business", "Test Medical Ltd",
                                                "api_secret"), "biz-secret-value-71x")
        # a key typed but no secret: still refused
        self.assertEqual(self._update(site_url="https://evil.example", api_key="k2").status_code, 417)
        # the same server, another path: no secret needed
        self.assertEqual(self._update(site_url="https://erp.test/erp").status_code, 200)
        # another server with both: the old secrets and the personal keys are gone
        r = self._update(site_url="https://new.example", api_key="k3", api_secret="new-secret-3")
        self.assertEqual(r.status_code, 200, r.content[:300])
        self.assertEqual(documents.get_password("Connected Business", "Test Medical Ltd",
                                                "api_secret"), "new-secret-3")
        self.assertFalse(Secret.objects.filter(docname="Test Medical Ltd",
                                               fieldname="sso_client_secret").exists())
        self.assertFalse(ConnectedBusiness.objects.get(pk="Test Medical Ltd").sso_client_id)
        self.assertFalse(CommandCenterSiteCredential.objects.filter(
            business_code="test_medical_ltd").exists())
        self.assertFalse(Secret.objects.filter(doctype="Command Center Site Credential").exists())

    def test_the_rule_is_the_scheme_host_and_port(self):
        from insights.core.platform_settings import address_moved
        self.assertFalse(address_moved("https://erp.test", "https://ERP.test/app/"))
        self.assertFalse(address_moved("https://erp.test", "https://erp.test:443"))
        self.assertTrue(address_moved("https://erp.test", "http://erp.test"))
        self.assertTrue(address_moved("https://erp.test", "https://erp.test:8443"))
        self.assertTrue(address_moved("https://erp.test", "https://erp.test.evil.example"))
        self.assertFalse(address_moved("", "https://erp.test"))


class AnalystWriteGuard(TransactionTestCase):
    """On MariaDB the analyst limits each lookup with SET SESSION max_statement_time; that
    is not a write, so the write guard stays quiet -- and a real write is still caught."""

    databases = {"default", "aux"}

    def test_set_session_is_not_a_write_and_an_insert_is(self):
        from django.db import connections

        import frappe
        from command_center.ask import agent
        from insights.compat import run_as

        issued = []

        class _Cursor:
            description = None

            def execute(self, sql, values=None):
                issued.append(sql)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        conn = connections["default"]
        with run_as("Administrator"):
            self.assertEqual(frappe.db.db_type, "sqlite")
            with mock.patch.object(conn, "vendor", "mysql"), \
                    mock.patch.object(conn, "cursor", lambda *a, **k: _Cursor()):
                self.assertEqual(frappe.db.db_type, "mariadb")
                before = frappe.db.transaction_writes
                with agent._statement_limit(10):
                    pass
                self.assertEqual(issued, ["SET SESSION max_statement_time = %s",
                                          "SET SESSION max_statement_time = 0"])
                self.assertEqual(frappe.db.transaction_writes, before,
                                 "SET SESSION was counted as a write")
                frappe.db.sql("UPDATE `tabDefaultValue` SET defvalue = 'x' WHERE 1 = 0")
                self.assertEqual(frappe.db.transaction_writes, before + 1)
            # and on the real database: a read is no write; an insert is one
            before = frappe.db.transaction_writes
            frappe.db.sql("select 1")
            self.assertEqual(frappe.db.transaction_writes, before)
            frappe.db.sql("insert into \"tabDefaultValue\" (parent, defkey, defvalue) "
                          "values ('x', 'y', 'z')")
            self.assertEqual(frappe.db.transaction_writes, before + 1)
            t = frappe.qb.DocType("DefaultValue")
            frappe.qb.into(t).columns("parent", "defkey", "defvalue").insert("a", "b", "c").run()
            self.assertEqual(frappe.db.transaction_writes, before + 2)


class WriteTimeoutIsUnconfirmed(TransactionTestCase):
    """A write ERPNext does not confirm in time reaches the screen as "it may have gone
    through -- check before trying again" (HTTP 504, WriteUnconfirmed), never as the
    platform's general failure, and the business that answers the check stays Active."""

    databases = {"default", "aux"}

    def setUp(self):
        _platform(self)
        _business(self)

    def test_unconfirmed_reaches_the_screen(self):
        import requests

        import frappe
        from command_center.connectors.registry import connector_for
        from insights.compat import WHITELIST, run_as
        from insights.core.models import ConnectedBusiness

        def slow(url, **kw):
            if "frappe.client.insert" in url:
                raise requests.exceptions.ReadTimeout("read timed out (read timeout=60)")
            return self.fake("POST")(url, **kw)

        def make():
            conn = connector_for("test_medical_ltd")
            conn._user_credential = lambda: {"api_key": "mine", "api_secret": "s"}
            return conn.insert({"doctype": "ToDo", "description": "x"})

        WHITELIST["insights.test_security.make"] = {"fn": make, "allow_guest": False,
                                                     "methods": ["POST"]}
        self.addCleanup(WHITELIST.pop, "insights.test_security.make")
        with mock.patch("requests.post", slow):
            r = self.admin.post("/api/method/insights.test_security.make", "{}",
                                content_type="application/json")
        self.assertEqual(r.status_code, 504, r.content[:300])
        body = r.json()
        self.assertEqual(body["exc_type"], "WriteUnconfirmed")
        self.assertIn("may still have gone through", body["_server_messages"])
        self.assertEqual(ConnectedBusiness.objects.get(pk="Test Medical Ltd").status, "Active")
        del frappe, run_as


class LockoutCountsEveryFailure(TransactionTestCase):
    """Eight threads failing at once each count: the counter is one atomic UPDATE."""

    databases = {"default", "aux"}

    def test_concurrent_failures_all_count(self):
        from django.db import close_old_connections

        from insights.core import views
        n_threads, each = 8, 6
        barrier = threading.Barrier(n_threads)

        def fail():
            try:
                barrier.wait()
                for _ in range(each):
                    views.count_failure("login-fail-ip:203.0.113.9")
            finally:
                close_old_connections()

        threads = [threading.Thread(target=fail) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(views.fail_count("login-fail-ip:203.0.113.9"), n_threads * each)
        views.clear_failures("login-fail-ip:203.0.113.9")
        self.assertEqual(views.fail_count("login-fail-ip:203.0.113.9"), 0)

    def test_a_window_that_passed_starts_again(self):
        import datetime as dt

        from insights.core import views
        from insights.core.models import SignInCounter
        views.count_failure("k1")
        views.count_failure("k1")
        SignInCounter.objects.filter(key="k1").update(expires=dt.datetime.now() - dt.timedelta(seconds=1))
        self.assertEqual(views.fail_count("k1"), 0)
        views.count_failure("k1")
        self.assertEqual(views.fail_count("k1"), 1)


class KeysNeverLogged(TransactionTestCase):
    """The Gemini key goes as a header, never in the address; and whatever an exception
    prints, keys and tokens are redacted before the error log keeps it."""

    databases = {"default", "aux"}

    def test_gemini_key_is_a_header(self):
        import frappe
        from command_center.ask import gemini
        from insights.compat import run_as
        seen = []

        def post(url, params=None, headers=None, json=None, timeout=None):
            seen.append((url, params, headers))
            raise ConnectionError(f"HTTPSConnectionPool: Max retries exceeded with url: {url}"
                                  f"?key={(params or {}).get('key', '')}")

        key = "AIzaSy" + "k" * 33
        with mock.patch.dict(frappe.conf, {"command_center_gemini_key": key}), \
                mock.patch("requests.post", post), run_as("Administrator"):
            gemini.chat([{"role": "user", "parts": [{"text": "hi"}]}], [], "sys", timeout=5)
        self.assertTrue(seen)
        for url, params, headers in seen:
            self.assertNotIn(key, url)
            self.assertNotIn("key", params or {})
            self.assertEqual((headers or {}).get("x-goog-api-key"), key)

    def test_the_error_log_is_redacted(self):
        import frappe
        from insights.compat import run_as
        from insights.core.models import ErrorLog
        key = "AIzaSy" + "q" * 33
        with mock.patch.dict(frappe.conf, {"command_center_anthropic_key": "sk-ant-api03-" + "z" * 40}), \
                run_as("Administrator"):
            frappe.log_error(title="x", message=(
                f"Max retries exceeded with url: /v1beta/models/m:generateContent?key={key}\n"
                f"headers {{'Authorization': 'token abcdef123456:fedcba654321'}}\n"
                f"anthropic sk-ant-api03-{'z' * 40}"))
        text = ErrorLog.objects.using("aux").latest("creation").error
        self.assertNotIn(key, text)
        self.assertNotIn("fedcba654321", text)
        self.assertNotIn("z" * 40, text)
        self.assertIn("[redacted]", text)


class KeysDelegateRule(TransactionTestCase):
    """A Personal ERPNext Keys delegate manages managers' keys only: never an
    administrator's, never anyone else's with Settings access, and does not see them."""

    databases = {"default", "aux"}

    def setUp(self):
        _platform(self)
        _business(self)
        U = get_user_model()
        other = U.objects.create_user("other@test.com", "other@test.com", "a-long-test-pass-9")
        other.groups.add(Group.objects.get(name=MANAGER),
                         Group.objects.get_or_create(name="Settings: Businesses")[0])
        self.manager_user = U.objects.get(username="manager@test.com")
        self.manager_user.groups.add(Group.objects.get_or_create(name="Settings: Personal Keys")[0])

    def _call(self, client, fn, **args):
        return client.post(f"/api/method/insights.core.platform_settings.{fn}", json.dumps(args),
                           content_type="application/json")

    def test_settings_people_keys_are_the_administrators(self):
        r = self._call(self.admin, "set_credential", user="other@test.com",
                       business_code="test_medical_ltd", api_key="ok", api_secret="other-secret")
        self.assertEqual(r.status_code, 200)
        other_key = r.json()["message"]["name"]
        r = self._call(self.manager, "set_credential", user="other@test.com",
                       business_code="test_medical_ltd", api_key="evil", api_secret="evil")
        self.assertEqual(r.status_code, 403, r.content[:200])
        self.assertEqual(self._call(self.manager, "remove_credential", name=other_key).status_code, 403)
        self.assertEqual(self._call(self.manager, "test_credential", name=other_key).status_code, 403)
        listed = [c["user"] for c in self._call(self.manager, "credentials").json()["message"]]
        self.assertNotIn("other@test.com", listed)
        # their own key, yes
        r = self._call(self.manager, "set_credential", user="manager@test.com",
                       business_code="test_medical_ltd", api_key="mine", api_secret="mine-secret")
        self.assertEqual(r.status_code, 200, r.content[:200])
        listed = [c["user"] for c in self._call(self.manager, "credentials").json()["message"]]
        self.assertEqual(listed, ["manager@test.com"])
