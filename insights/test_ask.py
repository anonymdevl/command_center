"""The question flow on the platform, against the fake ERPNext's loaded figures:

    .venv-platform/bin/python manage.py test insights.test_ask

The compare tool must give the same numbers as the figures it compares (the engine's
own rules), the starter questions may carry no number the engine did not produce and
must fall back to plain questions when there are none, and the live steps and Stop
must work through the web layer. The model itself is not called: there is no key here.
"""

from __future__ import annotations

import json
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TransactionTestCase

from insights.tests import FakeERPNext

CODE = "test_medical_ltd"


class AskFlow(TransactionTestCase):
    databases = {"default", "aux"}

    def setUp(self):
        from cryptography.fernet import Fernet
        from django.conf import settings
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        self.patches = [mock.patch("requests.get", FakeERPNext()("GET")),
                        mock.patch("requests.post", FakeERPNext()("POST")),
                        mock.patch("time.sleep", lambda s: None)]
        for p in self.patches:
            p.start()
        from command_center import install
        from command_center.api import ingest
        from insights.compat import run_as
        with run_as("Administrator"):
            install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")
            ingest.run_all(full=True)

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_compare_periods_agrees_with_the_figures(self):
        from command_center.ask import tools
        from command_center.kpi.engine import evaluate, evaluate_set
        from insights.compat import run_as

        with run_as("Administrator"):
            # A figure with a period of its own: the latest full month is that figure.
            c = tools.compare_periods(figure="revenue_last_month", business_code=CODE)
            fig = evaluate("revenue_last_month", CODE)
            self.assertAlmostEqual(c["current"]["value"], float(fig["value"]), places=2)
            self.assertEqual(c["current"]["period"], fig["period"]["label"])
            self.assertEqual(c["current"]["from"], fig["period"]["from"])
            # The month before, by the same rule, counted independently.
            q = tools.query_data("fact_sales_invoice_line",
                                 measures=[{"function": "sum", "column": "base_net_amount"}],
                                 date_column="posting_date", date_from=c["earlier"]["from"],
                                 date_to=c["earlier"]["to"], business_code=CODE)
            before = float(q["rows"][0]["sum_base_net_amount"] or 0)
            self.assertAlmostEqual(c["earlier"]["value"], before, places=2)
            self.assertAlmostEqual(c["change"], c["current"]["value"] - before, places=2)
            if before:
                self.assertAlmostEqual(c["change_pct"],
                                       round((c["current"]["value"] - before) / abs(before) * 100, 1))
            self.assertTrue(c["current"]["text"].startswith("GHS"))
            self.assertEqual(c["data_set"], "fact_sales_invoice_line")
            self.assertEqual(c["filters"]["posting_date"],
                             ["between", [c["current"]["from"], c["current"]["to"]]])

            # The same measure asked of the data set directly agrees with the figure.
            d = tools.compare_periods(fact="fact_sales_invoice_line", measure="base_net_amount",
                                      date_column="posting_date", business_code=CODE)
            self.assertAlmostEqual(d["current"]["value"], c["current"]["value"], places=2)
            self.assertAlmostEqual(d["earlier"]["value"], c["earlier"]["value"], places=2)

            # A quarter against the same quarter a year earlier: twelve months apart.
            y = tools.compare_periods(figure="revenue_last_month", compare="quarter_vs_last_year",
                                      business_code=CODE)
            self.assertEqual(int(y["current"]["from"][:4]) - 1, int(y["earlier"]["from"][:4]))
            self.assertEqual(y["current"]["from"][5:], y["earlier"]["from"][5:])
            self.assertTrue(re.match(r"Q[1-4] \d{4}$", y["current"]["period"]))

            # Custom ranges, and a ratio by its parts.
            k = tools.compare_periods(figure="margin_pct", date_column="posting_date",
                                      compare="custom", current_from=c["current"]["from"],
                                      current_to=c["current"]["to"],
                                      earlier_from=c["earlier"]["from"],
                                      earlier_to=c["earlier"]["to"], business_code=CODE)
            parts = {}
            for key in ("margin_known_cost", "revenue_costed"):
                parts[key] = tools._figure_between(
                    __import__("command_center.kpi.registry", fromlist=["get"]).get(key),
                    "posting_date", c["current"]["from"], c["current"]["to"], CODE)[0]
            if parts["revenue_costed"]:
                self.assertAlmostEqual(k["current"]["value"],
                                       round(parts["margin_known_cost"] / parts["revenue_costed"] * 100, 4))
            self.assertIn("percentage points", k.get("note", ""))

            # A position now has no history: refused, unless the records dated in each
            # period are what is wanted, and then the answer says so.
            with self.assertRaises(tools.ToolError):
                tools.compare_periods(figure="ar_total", business_code=CODE)
            a = tools.compare_periods(figure="ar_open_invoices", date_column="posting_date",
                                      business_code=CODE)
            self.assertIn("not the position as it stood", a["note"])
            with self.assertRaises(tools.ToolError):
                tools.compare_periods(figure="users_active", business_code=CODE)
            with self.assertRaises(tools.ToolError):
                tools.compare_periods(figure="revenue_last_month", compare="fortnight",
                                      business_code=CODE)

            # Through the analyst's own dispatch, as the model would call it.
            r = tools.run("compare_periods", {"figure": "cash_in_month", "business_code": "x"}, CODE)
            self.assertAlmostEqual(r["current"]["value"],
                                   float(evaluate_set(["cash_in_month"], CODE)["cash_in_month"]["value"]),
                                   places=2)

    def test_starters_quote_only_engine_figures(self):
        from command_center.api import starters
        from command_center.ask import quick, tools
        from command_center.kpi.engine import evaluate_set
        from insights.compat import run_as

        with run_as("Administrator"):
            out = starters.build(CODE, starters.areas_for(["System Manager"]))
            truth = evaluate_set(starters.FIGURES, CODE)
            sales = tools.compare_periods(figure="revenue_last_month", business_code=CODE)
        got = out["starters"]
        self.assertTrue(4 <= len(got) <= 6, got)
        self.assertTrue(out["live"], got)
        for s in got:
            if not s["live"]:
                continue
            self.assertTrue(s["figures"], s)
            # Every figure it names is the engine's, written the engine's way...
            for k, text in s["figures"].items():
                if k in truth:
                    self.assertEqual(text, quick._short(truth[k]), (k, s))
                elif k in ("current", "earlier"):
                    self.assertEqual(text, sales[k]["text"], s)
                elif k in ("current_period", "earlier_period"):
                    self.assertEqual(text, sales[k.split("_")[0]]["period"], s)
                elif k == "change_pct":
                    self.assertEqual(text, f"{abs(sales['change_pct']):.0f}%", s)
                else:
                    self.fail(f"a starter names a figure the engine did not give: {k} in {s}")
            # ...and it carries no number that is not one of them.
            words = " ".join(s["figures"].values())
            for n in re.findall(r"\d[\d,.]*", s["q"]):
                self.assertIn(n.rstrip(".,"), words, f"{n!r} in {s['q']!r} is not an engine figure")

        # The role decides the order.
        self.assertEqual(starters.areas_for(["Accounts Manager"])[0], "money")
        self.assertEqual(starters.areas_for(["Stock Manager"])[0], "stock")
        self.assertEqual(starters.areas_for(["Sales User"])[0], "sales")
        self.assertEqual(starters.areas_for(["System Manager"]), starters.EVERYONE)

        # No figures (a business with nothing loaded), or figures that fail: the plain
        # questions, never an empty list and never a number.
        with run_as("Administrator"):
            empty = starters.build("nothing_loaded", starters.EVERYONE)
            with mock.patch.object(starters, "_live", side_effect=RuntimeError("boom")), \
                    mock.patch.object(starters.frappe, "log_error") as logged:
                broken = starters.build(CODE, starters.EVERYONE)
            self.assertTrue(logged.called, "a failure behind the starters is logged, not hidden")
        for res in (empty, broken):
            self.assertEqual(len(res["starters"]), starters.MIN, res)
            self.assertFalse(res["live"])
            self.assertTrue(all(not s["live"] and s["q"] for s in res["starters"]))

    def test_starters_steps_and_stop_through_the_web(self):
        U = get_user_model()
        m = U.objects.create_user("manager@test.com", "manager@test.com", "a-long-test-pass-9")
        m.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        c = Client()
        self.assertTrue(c.login(username="manager@test.com", password="a-long-test-pass-9"))

        def post(method, **args):
            r = c.post(f"/api/method/{method}", json.dumps(args), content_type="application/json")
            self.assertEqual(r.status_code, 200, f"{method}: {r.content[:400]!r}")
            return r.json()["message"]

        got = post("command_center.api.starters.starters", business_code=CODE)
        self.assertTrue(4 <= len(got["starters"]) <= 6, got)
        self.assertEqual(post("command_center.api.starters.starters", business_code=CODE), got,
                         "kept briefly: the second call is the same list")

        # A question with an id: its steps are recorded with their kind, and a Stop that
        # arrives while it works is seen by the analyst's flag.
        from command_center.ask import tools
        seen = {}

        def fake_answer(question, business_code=None, history=None, on_step=None):
            import frappe
            on_step(tools.step("run_report", {"report": "General Ledger"}))
            on_step(tools.step("run_report", {"report": "Trial Balance"}))
            seen["before"] = frappe.local.cc_should_stop()
            from command_center.api import ask as ask_api
            ask_api.stop("q1")  # pressed while it works (the endpoint, in this request)
            seen["after"] = frappe.local.cc_should_stop()
            return {"answered": True, "answer": "ok", "format": "markdown"}

        with mock.patch("command_center.ask.engine.answer", fake_answer):
            post("command_center.api.ask.answer", question="Q", business_code=CODE, ask_id="q1")
        self.assertEqual(seen, {"before": False, "after": True})
        steps = post("command_center.api.ask.poll", ask_id="q1")["steps"]
        self.assertEqual([s["kind"] for s in steps], ["run_report", "run_report"], steps)
        self.assertEqual(steps[1]["text"], "Running ERPNext's Trial Balance")
        self.assertEqual(steps[1]["group"], "Running an ERPNext report")

        # The next question under a new id starts with no stop flag left over.
        with mock.patch("command_center.ask.engine.answer",
                        lambda q, b=None, h=None, on_step=None: (
                            seen.update(fresh=__import__("frappe").local.cc_should_stop())
                            or {"answered": True, "answer": "ok"})):
            post("command_center.api.ask.answer", question="Q", business_code=CODE, ask_id="q2")
        self.assertFalse(seen["fresh"])
        self.assertEqual(post("command_center.api.ask.stop", ask_id="q3"), {"stopping": True})
