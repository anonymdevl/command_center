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
    if "date" in f or f in ("exp_end_date", "completed_on", "opening_date"):
        return str(TODAY - dt.timedelta(days=rnd.randint(-30, 300)))
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
            return _R(200, {"docs": [{"name": p.get("doctype"), "fields": []}]})
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

        # someone without the role is turned away from the interface
        U.objects.create_user("clerk@test.com", "clerk@test.com", "a-long-test-pass-8")
        c2 = Client()
        c2.login(username="clerk@test.com", password="a-long-test-pass-8")
        r = c2.get("/command-center")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/management-only", r["Location"])
