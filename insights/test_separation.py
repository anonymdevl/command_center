"""Client separation (17 Nov 2026): a person uses only their own customer's businesses.

    .venv-platform/bin/python manage.py test insights.test_separation

Two customers -- Alpha (biz_a, biz_a2) and Beta (biz_b) -- and a business on no customer
(biz_u). ama@ is Alpha's, bea@ is Beta's, loose@ is on no customer; boss@ is the
administrator. Each test reproduces one way one customer's data, actions, email or bill
reached another, and holds it shut.
"""

from __future__ import annotations

import datetime as dt
import inspect
import json
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TransactionTestCase

from insights import tests as _tests  # the module: its TestCases are not collected twice

MANAGER = "Insights Dashboard Manager"
PASS = "a-long-test-pass-7"


class _Two(TransactionTestCase):
    databases = {"default", "aux"}

    def setUp(self):
        _tests.SettingsPage.setUp(self)
        self.addCleanup(_tests.SettingsPage.tearDown, self)
        from insights.core import plans
        from insights.core.models import (CommandCenterFactSalesInvoice, CommandCenterIngestState,
                                          ConnectedBusiness)
        self.M = plans._models()
        for code, name in (("biz_a", "Alpha One Ltd"), ("biz_a2", "Alpha Two Ltd"),
                           ("biz_b", "Beta Ltd"), ("biz_u", "Unplaced Ltd")):
            ConnectedBusiness.objects.create(name=name, business_name=name, business_code=code,
                                             status="Active", is_local=0, currency="GHS",
                                             site_url=f"https://{code}.test")
        self.alpha = self.M.ClientAccount.objects.create(name="Alpha Group")
        self.beta = self.M.ClientAccount.objects.create(name="Beta Group")
        for c, codes in ((self.alpha, ("biz_a", "biz_a2")), (self.beta, ("biz_b",))):
            for code in codes:
                self.M.ClientBusiness.objects.create(client=c, business_code=code)
        U = get_user_model()
        g = Group.objects.get(name=MANAGER)
        self.c = {}
        for who, cust in (("ama@a.test", self.alpha), ("bea@b.test", self.beta),
                          ("loose@x.test", None)):
            u = U.objects.create_user(who, who, PASS)
            u.groups.add(g)
            if cust is not None:
                self.M.ClientMember.objects.create(client=cust, username=who, role="manager")
            cl = Client()
            self.assertTrue(cl.login(username=who, password=PASS))
            self.c[who] = cl
        self.c["boss"] = self.admin
        # one invoice per business, a different amount each; the horizon differs too
        for i, (code, amount, horizon) in enumerate((("biz_a", 100, "2025-08-19"),
                                                     ("biz_a2", 20, "2025-09-30"),
                                                     ("biz_b", 5000, "2025-07-01"),
                                                     ("biz_u", 7, "2025-06-30"))):
            CommandCenterFactSalesInvoice.objects.create(
                name=f"F{i}", business_code=code, fact_key=f"k{i}", posting_date=dt.date(2025, 8, 1),
                customer="C", base_grand_total=amount, outstanding_amount=amount,
                as_of_date=dt.date.fromisoformat(horizon))
            CommandCenterIngestState.objects.create(
                name=f"S{i}", fact="fact_sales_invoice", business_code=code,
                as_of_date=dt.date.fromisoformat(horizon), status="OK")

    def _post(self, who, method, **args):
        return self.c[who].post(f"/api/method/{method}", json.dumps(args),
                                content_type="application/json")

    def _ok(self, who, method, **args):
        r = self._post(who, method, **args)
        self.assertEqual(r.status_code, 200, f"{method} as {who}: {r.content[:300]!r}")
        return r.json()["message"]

    def _boot(self, who) -> dict:
        page = self.c[who].get("/command-center").content.decode()
        return json.loads(re.search(r"window\.CC_BOOT = (.*?);\s*$", page, re.M).group(1))


class DataAndActions(_Two):

    def test_the_rule(self):
        from insights.core import plans
        self.assertEqual(plans.visible_codes("ama@a.test"), frozenset({"biz_a", "biz_a2"}))
        self.assertEqual(plans.visible_codes("bea@b.test"), frozenset({"biz_b"}))
        self.assertEqual(plans.visible_codes("loose@x.test"), frozenset({"biz_u"}))
        self.assertIsNone(plans.visible_codes("boss@test.com"))
        self.assertIsNone(plans.visible_codes("Administrator"))
        self.assertEqual(plans.visible_codes("nobody@x.test"), frozenset())

    def test_every_endpoint_refuses_another_customers_business(self):
        import importlib
        import pkgutil

        import command_center.api as api
        from insights.compat import WHITELIST
        for m in pkgutil.iter_modules(api.__path__):
            importlib.import_module(f"command_center.api.{m.name}")
        for m in ("insights.core.platform_settings", "insights.core.security", "insights.core.plans"):
            importlib.import_module(m)
        named = sorted(k for k, v in WHITELIST.items() if not v["allow_guest"]
                       and "business_code" in inspect.signature(v["fn"]).parameters)
        self.assertGreater(len(named), 40)
        for method in named:
            r = self._post("ama@a.test", method, business_code="biz_b", key="ar_total",
                           keys=["ar_total"], fact="fact_sales_invoice", question="sales?",
                           view="sales", code="rp01", todo="T", name="x", doctype="ToDo")
            self.assertIn(r.status_code, (403,), f"{method} answered for another customer's "
                                                 f"business: {r.status_code} {r.content[:160]!r}")
            self.assertIn("not one of yours", r.content.decode()
                          if r.status_code == 403 else "", method)

    def test_all_businesses_means_mine(self):
        def total(who):
            out = self._ok(who, "command_center.api.facts.query", fact="fact_sales_invoice",
                           measures=["base_grand_total"], group_by=[], business_code="__all__")
            rows = out.get("rows") if isinstance(out, dict) else out
            return round(sum(float(r.get("base_grand_total") or 0) for r in rows))
        self.assertEqual(total("ama@a.test"), 120)
        self.assertEqual(total("bea@b.test"), 5000)
        self.assertEqual(total("loose@x.test"), 7)
        self.assertEqual(total("boss"), 5127)
        # and by the query builder, as the figures read them
        from insights.compat import run_as

        import frappe
        with run_as("ama@a.test"):
            t = frappe.qb.DocType("Command Center Fact Sales Invoice")
            from frappe.query_builder.functions import Sum
            got = frappe.qb.from_(t).select(Sum(t.base_grand_total)).run()[0][0]
            self.assertEqual(round(float(got)), 120)
            self.assertEqual(frappe.db.count("Command Center Fact Sales Invoice"), 2)
            self.assertIsNone(frappe.db.get_value("Connected Business", {"business_code": "biz_b"}))
            self.assertFalse(frappe.db.exists("Command Center Fact Sales Invoice", "F2"))
            with self.assertRaises(frappe.DoesNotExistError):
                frappe.get_doc("Command Center Fact Sales Invoice", "F2")

    def test_the_business_list_and_boot(self):
        listed = self._ok("ama@a.test", "command_center.api.businesses.get_visible_businesses")
        self.assertEqual(sorted(b["business_code"] for b in listed["businesses"]), ["biz_a", "biz_a2"])
        boot = self._boot("ama@a.test")
        self.assertEqual(sorted(s["code"] for s in boot["scopes"]), ["__all__", "biz_a", "biz_a2"])
        self.assertNotIn("Beta", json.dumps(boot))
        self.assertEqual(sorted(boot["as_of_by"]), ["biz_a", "biz_a2"])
        self.assertEqual(boot["as_of_by"]["biz_a2"]["date"], "2025-09-30")
        self.assertEqual(boot["as_of"]["date"], "2025-08-19", "all of mine: the earliest")
        self.assertEqual(len(self._ok("boss", "command_center.api.businesses.get_visible_businesses")
                             ["businesses"]), 4)

    def test_records_of_another_customer_are_not_there(self):
        import frappe
        from command_center.connectors.registry import connector_for
        from insights.compat import run_as
        with run_as("Administrator"):
            alert = frappe.get_doc({"doctype": "Command Center Alert", "business_code": "biz_b",
                                    "rule": "r", "title": "Beta's", "status": "Raised"}).insert()
        r = self._post("ama@a.test", "command_center.api.alerts.act", name=alert.name,
                       action="dismissed", reason="not mine")
        self.assertIn(r.status_code, (404, 417), r.content[:200])
        with run_as("Administrator"):
            self.assertEqual(frappe.get_doc("Command Center Alert", alert.name).status, "Raised")
        with run_as("ama@a.test"):
            with self.assertRaises(Exception):
                connector_for("biz_b")
            connector_for("biz_a")
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc({"doctype": "Command Center Conversation", "business_code": "biz_b",
                                "title": "q"}).insert()

    def test_the_data_horizon_is_each_businesses_own(self):
        from command_center.api.export import _as_of as export_as_of
        from command_center.ask.agent import _as_of as agent_as_of
        from command_center.www.command_center import _as_of
        from insights.compat import run_as
        with run_as("Administrator"):
            self.assertEqual(_as_of("biz_b")["date"], "2025-07-01")
            self.assertEqual(agent_as_of("biz_a2"), "2025-09-30")
            self.assertEqual(export_as_of("biz_a"), "2025-08-19")
            self.assertEqual(_as_of()["date"], "2025-06-30", "every business: the earliest")

    def test_all_is_cached_per_whose_all(self):
        from command_center.api.businesses import scope_tag
        from insights.compat import run_as
        tags = {}
        for who in ("ama@a.test", "bea@b.test", "boss@test.com"):
            with run_as(who):
                tags[who] = scope_tag("__all__")
                self.assertEqual(scope_tag("biz_a"), "biz_a")
        self.assertEqual(tags["boss@test.com"], "__all__")
        self.assertTrue(tags["ama@a.test"].startswith("__all__~"))
        self.assertNotEqual(tags["ama@a.test"], tags["bea@b.test"])

    def test_the_analyst_never_reads_pay_people_or_logs(self):
        from command_center.ask import tools
        for doctype in ("Salary Slip", "salary slip", "Salary Structure Assignment", "User",
                        "Error Log", "Version", "  salary   structure  "):
            with self.assertRaises(tools.ToolError, msg=doctype):
                tools._doctype_allowed(doctype, "biz_a")

    def test_the_analyst_reads_with_the_askers_own_key(self):
        import frappe
        from command_center.ask import tools
        from insights.compat import run_as
        with run_as("Administrator"):
            doc = frappe.new_doc("Command Center Site Credential")
            doc.update({"user": "ama@a.test", "business_code": "biz_a", "api_key": "ama-key",
                        "api_secret": "ama-secret"})
            doc.save()
        with run_as("ama@a.test"):
            far = tools._remote("biz_a")
            self.assertIn("ama-key", far._headers()["Authorization"])
            far = tools._remote("biz_a2")
            from command_center.connectors.base import BusinessUnreachable
            with self.assertRaises(BusinessUnreachable):  # no key of hers there, no service key
                far._headers()


class SettingsDelegates(_Two):

    def setUp(self):
        super().setUp()
        U = get_user_model()
        ama = U.objects.get(username="ama@a.test")
        for g in ("Settings: People", "Settings: Businesses", "Settings: Personal Keys"):
            ama.groups.add(Group.objects.get_or_create(name=g)[0])

    def test_a_delegate_sees_and_changes_only_their_customer(self):
        S = "insights.core.platform_settings"
        people = {p["username"] for p in self._ok("ama@a.test", f"{S}.people")}
        self.assertIn("ama@a.test", people)
        self.assertNotIn("bea@b.test", people)
        self.assertNotIn("loose@x.test", people)
        biz = {b["business_code"] for b in self._ok("ama@a.test", f"{S}.businesses")}
        self.assertEqual(biz, {"biz_a", "biz_a2"})
        for fn, args in (("update_business", {"name": "Beta Ltd", "api_key": "x"}),
                         ("set_paused", {"name": "Beta Ltd", "paused": 1}),
                         ("reload_business", {"name": "Beta Ltd"}),
                         ("test_business", {"name": "Beta Ltd"}),
                         ("set_active", {"username": "bea@b.test", "on": 0}),
                         ("reset_password", {"username": "bea@b.test", "set_later": 1}),
                         ("set_credential", {"user": "bea@b.test", "business_code": "biz_b",
                                             "api_key": "k", "api_secret": "s"}),
                         ("set_credential", {"user": "ama@a.test", "business_code": "biz_b",
                                             "api_key": "k", "api_secret": "s"})):
            r = self._post("ama@a.test", f"{S}.{fn}", **args)
            self.assertIn(r.status_code, (403, 417), f"{fn}: {r.content[:200]!r}")
        self.assertTrue(get_user_model().objects.get(username="bea@b.test").is_active)
        from insights.core.models import ConnectedBusiness
        self.assertEqual(ConnectedBusiness.objects.get(pk="Beta Ltd").status, "Active")
        # a business a delegate adds is their own customer's
        out = self._ok("ama@a.test", f"{S}.add_business", business_name="Alpha Three Ltd",
                       site_url="https://erp.test", api_key="key-abcd1234",
                       api_secret="biz-secret-value-71x")
        self.assertEqual(out["business"]["business_code"], "alpha_three_ltd")
        self.assertTrue(self.M.ClientBusiness.objects.filter(client=self.alpha,
                                                             business_code="alpha_three_ltd").exists())


class EmailsStayWithTheCustomer(_Two):

    def test_alert_and_digest_recipients_and_one_message_each(self):
        from command_center.alerts import notify
        from insights.compat import run_as
        with run_as("Administrator"):
            to_a = notify.recipients("biz_a")
            to_b = notify.recipients("biz_b")
        self.assertIn("ama@a.test", to_a)
        self.assertNotIn("bea@b.test", to_a)
        self.assertNotIn("loose@x.test", to_a)
        self.assertIn("bea@b.test", to_b)
        self.assertNotIn("ama@a.test", to_b)
        sent = []
        doc = type("A", (), {"severity": "crit", "title": "Cash", "why": "w", "next_step": "n",
                             "owner_label": "o", "name": "AL-1"})()
        with mock.patch("frappe.sendmail", lambda **kw: sent.append(kw["recipients"])), \
                run_as("Administrator"):
            notify.notify("biz_a", [doc])
        self.assertTrue(sent)
        self.assertTrue(all(len(r) == 1 for r in sent), f"one address per message: {sent}")
        self.assertNotIn(["bea@b.test"], sent)


class ReportSchedules(_Two):

    def test_recipients_are_the_customers_and_send_now_is_once(self):
        R = "command_center.api.reports"
        r = self._post("ama@a.test", f"{R}.save_schedule", code="rp01", business_code="biz_a",
                       recipients=json.dumps(["bea@b.test"]))
        self.assertEqual(r.status_code, 417, r.content[:200])
        self.assertIn("not managers of this business", r.content.decode())
        self._ok("ama@a.test", f"{R}.save_schedule", code="rp01", business_code="biz_a",
                 recipients=json.dumps(["ama@a.test"]))
        r = self._post("bea@b.test", f"{R}.save_schedule", code="rp01", business_code="biz_a",
                       recipients=json.dumps(["bea@b.test"]))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self._ok("ama@a.test", f"{R}.send_now", code="rp01",
                                  business_code="biz_a"), {"queued": True})
        r = self._post("ama@a.test", f"{R}.send_now", code="rp01", business_code="biz_a")
        self.assertEqual(r.status_code, 417, "a second Send Now at once is refused")
        self.assertIn("being sent already", r.content.decode())


class BillingAndLicence(_Two):

    def test_all_businesses_is_billed_and_gated(self):
        from insights.compat import run_as
        from insights.core import plans
        with run_as("ama@a.test"):
            self.assertEqual(plans.client_for("__all__").pk, self.alpha.pk)
            self.assertEqual(plans.client_for(None).pk, self.alpha.pk)
            ev = plans.record("ai_questions", 1, "__all__")
        self.assertEqual(ev.client_id, self.alpha.pk, "never unbilled for a customer user")
        self.M.ClientAccount.objects.filter(pk=self.alpha.pk).update(
            renewal_date=dt.date.today() - dt.timedelta(days=90), grace_days=0)
        with run_as("ama@a.test"):
            self.assertTrue(plans.gate("ai_questions", "__all__"), "a lapsed licence is not "
                                                                   "gone round by asking about all")
            self.assertTrue(plans.gate("ai_questions", "biz_a"))
        with run_as("bea@b.test"):
            self.assertIsNone(plans.gate("ai_questions", "__all__"))

    def test_a_past_month_keeps_its_terms(self):
        from insights.core import plans
        c = self.alpha
        self.M.ClientAccount.objects.filter(pk=c.pk).update(
            limits=json.dumps({"ai_questions": 10}),
            rates=json.dumps({"currency": "GHS", "base_fee": "100", "overage": {"ai_questions": "2"}}))
        c.refresh_from_db()
        oct_ = dt.datetime(2026, 10, 15, 9, 0)
        with mock.patch.object(plans, "now", lambda: oct_):
            plans.snapshot(c)
            for _ in range(12):
                plans.record("ai_questions", 1, "biz_a", user="ama@a.test")
        # November: the administrator doubles the rate and the base fee
        self.M.ClientAccount.objects.filter(pk=c.pk).update(
            limits=json.dumps({"ai_questions": 5}),
            rates=json.dumps({"currency": "GHS", "base_fee": "200", "overage": {"ai_questions": "4"}}))
        c.refresh_from_db()
        with mock.patch.object(plans, "now", lambda: dt.datetime(2026, 11, 3, 9, 0)):
            st = plans.statement(c, "2026-10", money=True)
        line = next(x for x in st["lines"] if x["key"] == "ai_questions")
        self.assertEqual((line["included"], line["over"], float(line["amount"])), (10, 2, 4.0))
        self.assertEqual(float(st["total"]), 104.0)
        self.assertTrue(st["terms_kept"])

    def test_usage_is_on_record_while_it_is_being_spent(self):
        from insights.compat import run_as
        from insights.core import plans
        from insights.core.models import UsageEvent
        with run_as("ama@a.test"):
            with plans.event("ai_reports", "biz_a") as ev:
                plans.meter_tokens("claude-opus-5-5", input=1000, output=50, requests=1)
                # the worker could die here: the tokens are already on record
                row = UsageEvent.objects.get(pk=ev["row"])
                self.assertEqual((row.outcome, row.quantity, row.input_tokens), ("running", 0, 1000))
                plans.meter_tokens("claude-opus-5-5", input=500, output=10, requests=1)
                self.assertEqual(UsageEvent.objects.get(pk=ev["row"]).input_tokens, 1500)
                ev["ok"] = True
        row = UsageEvent.objects.get(pk=ev["row"])
        self.assertEqual((row.outcome, row.quantity, row.input_tokens, row.requests, row.client_id),
                         ("ok", 1, 1500, 2, self.alpha.pk))
        self.assertEqual(UsageEvent.objects.filter(meter="ai_reports").count(), 1)
        # settled once: a closed row is never changed again
        self.assertEqual(UsageEvent.objects.filter(pk=row.pk).settle(quantity=9), 0)
        # one left running by a worker that died is closed by the daily run
        with run_as("ama@a.test"):
            with mock.patch.object(plans, "now", lambda: dt.datetime.now() - dt.timedelta(hours=5)):
                stuck = plans.record("ai_reports", 0, "biz_a", outcome="running")
        plans.daily()
        self.assertEqual(UsageEvent.objects.get(pk=stuck.pk).outcome, "interrupted")
