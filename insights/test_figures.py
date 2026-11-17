"""The figures' arithmetic, against crafted ERPNext rows (17 Nov 2026).

Each test reproduces a figure that was wrong on Gigmann's live site, with its numbers
where they could be kept, and holds the fix:

    .venv-platform/bin/python manage.py test insights.test_figures

The fakes are insights/tests.py's: CoverERPNext answers the doctypes it is given from
rows, filtered and paged as ERPNext would; everything else as FakeERPNext does.
"""

from __future__ import annotations

import datetime as dt
import json
from unittest import mock

from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TransactionTestCase

from insights.tests import TODAY, CoverERPNext

CODE = "test_medical_ltd"


def _d(n):
    return str(TODAY + dt.timedelta(days=n))


class _Business(TransactionTestCase):
    """A registered business whose ERPNext answers `rows()` for the doctypes it names."""

    databases = {"default", "aux"}

    def rows(self) -> dict:
        return {}

    def setUp(self):
        from django.conf import settings
        from django.core.cache import cache
        from cryptography.fernet import Fernet
        from command_center import install
        from insights.compat import run_as
        settings.CONFIG.setdefault("encryption_key", Fernet.generate_key().decode())
        Group.objects.get_or_create(name="Insights Dashboard Manager")
        cache.clear()
        self.fake = CoverERPNext(self.rows())
        up = [mock.patch("requests.get", self.fake("GET")),
              mock.patch("requests.post", self.fake("POST")),
              mock.patch("time.sleep", lambda s: None)]
        for p in up:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in up])
        self.addCleanup(cache.clear)
        with run_as("Administrator"):
            install.register_business("Test Medical Ltd", "https://erp.test", "key", "s3cret")

    def conn(self):
        from command_center.connectors.registry import connector_for
        return connector_for(CODE).as_system()

    def load(self, *facts, full=True):
        from command_center.api.ingest import load_business
        from insights.compat import run_as
        with run_as("Administrator"):
            out = load_business(self.conn(), facts=list(facts), full=full, raise_errors=True)
        return out

    def figures(self, *keys):
        from command_center.kpi.engine import evaluate_set
        from insights.compat import run_as
        with run_as("Administrator"):
            return evaluate_set(list(keys), CODE)


# =========================================================================== 1 and 4
def order_rows() -> dict:
    """SO-942 is Gigmann's SAL-ORD-2025-00942 in small: worth 746,980, 86.14% delivered by
    quantity (174 of 202 units), with 16,290 of it still to deliver line by line -- a lab
    oven, a centrifuge, five drip stands and an infant scale, the cheap lines delivered.
    Billed for what was delivered.
    SO-DEL is delivered in full (by an over-delivery on one line) and half invoiced.
    SO-NONE has nothing delivered and nothing billed: it is promised, not "delivered but not
    invoiced"."""
    so = lambda name, total, pd, pb, net=None: {  # noqa: E731
        "name": name, "modified": "2026-11-10 10:00:00.000001", "docstatus": 1,
        "transaction_date": _d(-20), "delivery_date": _d(-5), "status": "To Deliver and Bill",
        "customer": "Ama Clinic", "customer_group": "Hospitals", "territory": "Ghana",
        "currency": "GHS", "base_grand_total": total,
        "base_net_total": total if net is None else net,
        "per_delivered": pd, "per_billed": pb}
    line = lambda parent, name, qty, done, rate, billed: {  # noqa: E731
        "parent": parent, "parenttype": "Sales Order", "name": name, "qty": qty,
        "delivered_qty": done, "base_net_rate": rate, "base_net_amount": qty * rate,
        "amount": qty * rate, "billed_amt": billed}
    left = [("oven", 1, 5800), ("centrifuge", 1, 8000), ("drip", 5, 450), ("scale", 1, 240),
            ("sutures", 1, 0), ("slides", 2, 0), ("plaster", 10, 0), ("syringes", 2, 0),
            ("tubes", 5, 0)]
    lines = [line("SO-942", n, q, 0, r, 0) for n, q, r in left]
    lines.append(line("SO-942", "assorted", 174, 174, 730690 / 174, 730690))
    lines += [line("SO-DEL", "d1", 10, 12, 100, 500),      # over-delivered: 10 of 10 count
              line("SO-NONE", "n1", 4, 0, 2500, 0)]
    return {"Sales Order": [so("SO-942", 746980, 86.138614, 97.819219),
                            so("SO-DEL", 1000, 100, 50), so("SO-NONE", 10000, 0, 0)],
            "Sales Order Item": lines}


class OrderBookLineByLine(_Business):
    rows = staticmethod(order_rows)

    def test_undelivered_is_counted_by_line_not_by_quantity_share(self):
        from insights.core.models import CommandCenterFactSalesOrder as SO
        self.load("fact_sales_order")
        got = {r.src_name: r for r in SO.objects.filter(business_code=CODE)}
        self.assertEqual(float(got["SO-942"].undelivered_value), 16290.0,
                         "746,980 x (1 - 86.14%) = 103,541.78 is quantity, not money")
        self.assertEqual(float(got["SO-942"].unbilled_value), 16290.0)
        self.assertEqual(float(got["SO-942"].delivered_unbilled_value), 0.0)
        self.assertEqual(float(got["SO-DEL"].undelivered_value), 0.0)   # over-delivery: none left
        self.assertEqual(float(got["SO-DEL"].delivered_unbilled_value), 500.0)
        self.assertEqual(float(got["SO-NONE"].undelivered_value), 10000.0)
        self.assertEqual(float(got["SO-NONE"].delivered_unbilled_value), 0.0)

        f = self.figures("order_book", "order_unbilled", "order_delivered_unbilled",
                         "order_delivered_unbilled_count", "order_awaiting_invoice")
        self.assertEqual(f["order_book"]["value"], 26290.0)
        # Delivered but not invoiced: only SO-DEL. SO-NONE's 10,000 was never delivered and
        # SO-942's unbilled 16,290 is all on lines not yet delivered.
        self.assertEqual(f["order_unbilled"]["value"], 500.0)
        self.assertEqual(f["order_delivered_unbilled"]["value"], 500.0)
        self.assertEqual(f["order_delivered_unbilled_count"]["value"], 1)
        self.assertEqual(f["order_awaiting_invoice"]["value"], 1)

    def test_check_figures_values_the_order_book_the_same_way(self):
        from command_center.api.ingest import source_figures
        from insights.compat import run_as
        with run_as("Administrator"):
            src = source_figures(CODE, TODAY)
        self.assertEqual(src["order_book"], 26290.0)
        self.assertEqual(src["order_book_count"], 3)

    def test_a_tax_is_shared_across_the_lines(self):
        from command_center.ingest import order_lines
        order = {"base_grand_total": 1150, "base_net_total": 1000}
        line = {"qty": 10, "delivered_qty": 4, "base_net_rate": 100, "base_net_amount": 1000,
                "amount": 1000, "billed_amt": 200}
        v = order_lines.values(order, [line], "delivered_qty")
        self.assertEqual(v, {"left": 690.0, "unbilled": 920.0, "delivered_unbilled": 230.0})


class SuppliersLateLineByLine(SimpleTestCase):
    """late_suppliers' "still to receive" was the order's value times (1 - per_received):
    a 10,000 order with nine cheap units of ten received is 90% received by quantity but
    has 9,100 of its value still to come."""

    def test_pending_is_by_line(self):
        from command_center.ingest import order_lines

        class Reader:
            def all(self, doctype, filters=None, fields=None, limit=None, parent=None):
                assert doctype == "Purchase Order Item" and parent == "Purchase Order"
                rows = [{"parent": "PO-1", "name": "a", "qty": 9, "received_qty": 9,
                         "base_net_rate": 100, "base_net_amount": 900, "amount": 900,
                         "billed_amt": 0},
                        {"parent": "PO-1", "name": "b", "qty": 1, "received_qty": 0,
                         "base_net_rate": 9100, "base_net_amount": 9100, "amount": 9100,
                         "billed_amt": 0}]
                return [{f: r.get(f) for f in fields} for r in rows]
        po = {"name": "PO-1", "base_grand_total": 10000, "base_net_total": 10000,
              "per_received": 90, "per_billed": 0}
        got = order_lines.order_values(Reader(), order_lines.BUYING, [po], "per_received")
        self.assertEqual(got["PO-1"]["left"], 9100.0)


# =========================================================================== 2
def po_rows() -> dict:
    """Gigmann's PUR-ORD-2024-00008 in small: cancelled, amended to -1, cancelled, amended
    to -2, which stands. Two cancelled with nothing after them: really withdrawn."""
    po = lambda name, ds, total, amended=None: {  # noqa: E731
        "name": name, "docstatus": ds, "status": {0: "Draft", 1: "To Receive and Bill",
                                                  2: "Cancelled"}[ds],
        "owner": "buyer@test.com", "supplier": "Acme Medical", "base_grand_total": total,
        "amended_from": amended, "workflow_state": None}
    return {"Purchase Order": [po("PO-8", 2, 864883.20), po("PO-8-1", 2, 661048.20, "PO-8"),
                               po("PO-8-2", 1, 864883.20, "PO-8-1"),
                               po("PO-6", 2, 439380), po("PO-135", 2, 96894)],
            "Payment Entry": []}


class AmendedIsNotWithdrawn(_Business):
    rows = staticmethod(po_rows)

    def test_withdrawn_counts_only_what_was_not_amended(self):
        from command_center.kpi.live import _Reader, po_cancelled
        from insights.compat import run_as
        with run_as("Administrator"):
            n, note = po_cancelled(_Reader(CODE))
        self.assertEqual(n, 2, "PO-8 and PO-8-1 were amended, not withdrawn")
        self.assertIn("GHS 536,274", note)

    def test_the_audit_panels_say_the_same(self):
        from command_center.api import panels, panels_core
        from insights.compat import run_as
        with run_as("Administrator"):
            ctx = panels._Ctx(CODE)
            where = panels.aud_where_approvals(ctx)
            decided = panels.aud_decisions(ctx)
            day_one = panels_core.aud_day_one(ctx)
        cancelled = [r["cells"] for r in where["rows"] if r["cells"][0]["text"] == "Cancelled"]
        self.assertEqual([c[1]["text"] for c in cancelled], ["2"], where["rows"])
        names = [r["cells"][0]["text"] for r in decided["rows"]]
        self.assertNotIn("PO-8", names)
        self.assertNotIn("PO-8-1", names)
        self.assertIn("PO-8-2", names)
        text = json.dumps(day_one)
        self.assertIn("2 purchase orders worth GHS 536,274 withdrawn", text)


# =========================================================================== 3
def payment_rows() -> dict:
    """Last month: PE-1 received 1,000 and matched it to two invoices; PE-2 received 500
    and matched none of it; PE-3 received 300 and matched 200. PE-4 paid a supplier 700.
    PE-5 is this month's, so last month is a full one."""
    last = TODAY.replace(day=1) - dt.timedelta(days=20)
    pe = lambda name, kind, amount, unalloc, day=last: {  # noqa: E731
        "name": name, "modified": "2026-11-10 10:00:00.000001", "docstatus": 1,
        "posting_date": str(day), "party_type": "Supplier" if kind == "Pay" else "Customer",
        "party": "Acme" if kind == "Pay" else "Ama Clinic", "payment_type": kind,
        "base_paid_amount": amount, "base_received_amount": amount,
        "unallocated_amount": unalloc}
    ref = lambda parent, name, inv, amt, dt_="Sales Invoice": {  # noqa: E731
        "parent": parent, "parenttype": "Payment Entry", "name": name,
        "reference_doctype": dt_, "reference_name": inv, "allocated_amount": amt}
    return {"Payment Entry": [pe("PE-1", "Receive", 1000, 0), pe("PE-2", "Receive", 500, 500),
                              pe("PE-3", "Receive", 300, 100), pe("PE-4", "Pay", 700, 0),
                              pe("PE-5", "Receive", 50, 0, TODAY)],
            "Payment Entry Reference": [ref("PE-1", "r1", "SI-1", 600), ref("PE-1", "r2", "SI-2", 400),
                                        ref("PE-3", "r3", "SI-3", 200),
                                        ref("PE-4", "r4", "PI-1", 700, "Purchase Invoice"),
                                        ref("PE-5", "r5", "SI-4", 50)]}


class MoneyInIsEveryReceipt(_Business):
    rows = staticmethod(payment_rows)

    def test_money_in_counts_each_receipt_once_matched_or_not(self):
        self.load("fact_payment_allocation")
        f = self.figures("cash_in_month", "cash_applied")["cash_in_month"]
        self.assertEqual(f["value"], 1800.0, "1,200 is only the part matched to invoices")
        self.assertIn("every payment received", f["note"])
        from insights.core.models import CommandCenterFactPaymentAllocation as PA
        rows = PA.objects.filter(business_code=CODE, src_name="PE-1")
        self.assertEqual(sorted(float(r.payment_amount) for r in rows), [0.0, 1000.0])
        alone = PA.objects.get(business_code=CODE, src_name="PE-2")
        self.assertEqual((alone.src_doctype, float(alone.allocated_amount)), ("Payment Entry", 0.0))

    def test_finances_money_in_trend_is_the_same(self):
        from command_center.api import panels
        from insights.compat import run_as
        self.load("fact_payment_allocation")
        with run_as("Administrator"):
            out = panels.fin_money_in(panels._Ctx(CODE))
        self.assertEqual(out["values"][-1], 1800.0, out)


# =========================================================================== 5
def ageing_rows() -> dict:
    si = {"name": "SI-OLD", "modified": "2026-01-05 10:00:00.000001", "docstatus": 1,
          "posting_date": "2026-01-01", "due_date": "2026-01-31", "status": "Overdue",
          "is_return": 0, "customer": "Ama Clinic", "customer_group": "Hospitals",
          "territory": "Ghana", "currency": "GHS", "base_grand_total": 5000,
          "outstanding_amount": 5000}
    so = dict(order_rows()["Sales Order"][2], modified="2026-01-05 10:00:00.000001",
              delivery_date="2026-01-31", per_delivered=0, per_billed=0)
    return {"Sales Invoice": [si], "Sales Order": [so],
            "Sales Order Item": [x for x in order_rows()["Sales Order Item"]
                                 if x["parent"] == so["name"]]}


class AgeingIsNotFrozen(_Business):
    rows = staticmethod(ageing_rows)

    def _load(self, ingestor, as_of, full):
        from insights.compat import run_as
        with run_as("Administrator"):
            return ingestor().load(self.conn(), as_of=as_of, full=full)

    def test_an_untouched_invoice_and_order_age_on_every_load(self):
        from command_center.ingest.operations import SalesOrderIngestor
        from command_center.ingest.sales import SalesInvoiceIngestor
        from insights.core.models import CommandCenterFactSalesInvoice as SI
        from insights.core.models import CommandCenterFactSalesOrder as SO
        self._load(SalesInvoiceIngestor, "2026-04-15", True)
        self._load(SalesOrderIngestor, "2026-04-15", True)
        inv = SI.objects.get(business_code=CODE, src_name="SI-OLD")
        self.assertEqual((inv.days_overdue, inv.ageing_bucket), (74, "61-90"))
        # A month on, nothing changed in ERPNext: the incremental load reads nothing,
        # and the invoice and the order are 104 days past due all the same.
        got = self._load(SalesInvoiceIngestor, "2026-05-15", False)
        self.assertEqual(got["rows"], 0)
        self._load(SalesOrderIngestor, "2026-05-15", False)
        inv = SI.objects.get(business_code=CODE, src_name="SI-OLD")
        self.assertEqual((inv.days_overdue, inv.ageing_bucket, str(inv.as_of_date)),
                         (104, "90+", "2026-05-15"))
        so = SO.objects.get(business_code=CODE, src_name="SO-NONE")
        self.assertEqual((so.days_late, so.lateness_bucket), (104, "90+"))
        f = self.figures("order_book_late")["order_book_late"]
        self.assertEqual(f["value"], 10000.0)


# =========================================================================== 6
class OneNumberCheck(SimpleTestCase):
    """The AI's numbers: the exact cases the three old checkers got wrong."""

    def memo(self):
        """The Executive Summary's data as summary.given() makes it, on the 17th."""
        return {"business": "Gigmann", "week_to": "Week to Tuesday 17 November 2026",
                "currency": "GHS",
                "figures": [
                    {"key": "cash_in_month", "what": "Money In, Oct (October 2026)",
                     "text": "GHS 380,574", "note": "October 2026, every payment received",
                     "change": "down 8% on September 2026"},
                    {"key": "ar_total", "what": "Owed to Us", "text": "GHS 341,565",
                     "note": "owed by 118 customers by the ledger", "change": None},
                    {"key": "control_score", "what": "Overall Business Health", "text": "74%",
                     "note": "the average of 4 of 6 questions; 2 below 60%",
                     "change": "up 3 points on last week"}],
                "decisions": [{"title": "Chase SAL-ORD-2025-00942 for GHS 16,290.",
                               "owner": "Sales", "money_text": "GHS 16,290"}],
                "risks": [], "going_well": []}

    def test_false_passes_are_caught(self):
        from command_center import summary
        data = self.memo()
        for para, why in (("Money in rose 8% to GHS 380,574.", "it fell 8%"),
                          ("Overall Business Health is 17%.", "17 is the dateline's day"),
                          ("Overall Business Health is 2026%.", "the dateline's year"),
                          ("Health fell 3 points on last week.", "it rose"),
                          ("60% of invoices are overdue.", "60% is a threshold, not a figure"),
                          ("Six of 942 orders are late; 942 matter.", "digits in a document name"),
                          ("Customers owe GHS 7M.", "not a rounding of anything given"),
                          ("Customers owe GHS 341,565 to 6%.", "4 of 6 is not 6%"),
                          ("Money in was GHS 380,574 on 18 November.", "a date not given")):
            self.assertIsNotNone(summary.check(para, "", data), f"{para!r} passed: {why}")

    def test_false_fails_are_not(self):
        from command_center import summary
        data = self.memo()
        data["figures"][1]["text"] = "341,565.00"     # given with its decimals, no currency
        for para in ("Customers owe GHS 341,565 by the ledger.",
                     "Customers owe GHS 341.6k.", "Customers owe GHS 0.34M.",
                     "Money in fell 8% to GHS 380,574 in October 2026.",
                     "Money in was down 8%, at GHS 380,574.",
                     "Overall Business Health is 74%, up 3 points on last week.",
                     "Two questions are below 60%.",
                     "Chase SAL-ORD-2025-00942 for GHS 16,290 this week, by 17 November."):
            self.assertIsNone(summary.check(para, "", data), para)

    def test_the_three_callers_share_the_one_check(self):
        import inspect
        from command_center import summary
        from command_center.insight import ai
        from command_center.recommend import daily, review
        for mod in (summary, ai, daily, review):
            src = inspect.getsource(mod)
            self.assertIn("numbers.problems", src, mod.__name__)
        for name in ("allowed_numbers", "foreign_numbers", "numbers_in"):
            for mod in (summary, ai, daily, review):
                self.assertFalse(hasattr(mod, name), f"{mod.__name__}.{name} is a second checker")

    def test_brief_and_explain_text(self):
        from command_center.recommend import numbers
        given = numbers.Given().text(
            "Business: Gigmann", "Today: 17 November 2026",
            "- Money received, last full month: GHS 380,573.61 (yesterday GHS 380,573.61)",
            "- NEW SINCE YESTERDAY: Chase 3 open orders. Money at stake: GHS 16,290.")
        self.assertEqual(numbers.problems("1. Chase the 3 open orders (GHS 16,290).\n"
                                          "2. Money received was GHS 380,574.", given), [])
        self.assertEqual(numbers.problems("Money received rose to GHS 380,574.", given),
                         ["380574 as a rise"])
        self.assertEqual(numbers.problems("Pay GHS 999,999 today.", given), ["999999"])


# =========================================================================== 7
class AwaitingPaymentIsTheLedger(_Business):
    """Ama Clinic's two invoices say 9,000 outstanding, but it paid 6,000 that nobody
    matched: the ledger says it owes 3,000. Its older order's invoice is paid by the
    ledger; only the newer one is awaiting payment, for 3,000. Kofi Stores is in credit."""

    def setUp(self):
        super().setUp()
        from insights.core import models as M
        mk = lambda model, **kw: model.objects.create(  # noqa: E731
            name=kw["src_name"] + kw.get("src_row_name", ""), fact_key=kw["src_name"] + kw.get(
                "src_row_name", ""), business_code=CODE, src_docstatus=1, **kw)
        PB, SI, SL, SO = (M.CommandCenterFactPartyBalance, M.CommandCenterFactSalesInvoice,
                          M.CommandCenterFactSalesInvoiceLine, M.CommandCenterFactSalesOrder)
        mk(PB, src_name="Ama Clinic", party_type="Customer", party="Ama Clinic",
           ledger_balance=3000, owed=3000, open_invoices=9000, unmatched_payments=6000)
        mk(PB, src_name="Kofi Stores", party_type="Customer", party="Kofi Stores",
           ledger_balance=-500, in_credit=500, open_invoices=2000, unmatched_payments=2500)
        for inv, cust, due, amt, so in (("SI-1", "Ama Clinic", "2026-06-30", 5000, "SO-1"),
                                        ("SI-2", "Ama Clinic", "2026-09-30", 4000, "SO-2"),
                                        ("SI-3", "Kofi Stores", "2026-09-30", 2000, "SO-3")):
            mk(SI, src_name=inv, customer=cust, due_date=due, posting_date=due,
               outstanding_amount=amt, base_grand_total=amt)
            mk(SL, src_name=inv, src_row_name="-1", sales_order=so, base_net_amount=amt)
            mk(SO, src_name=so, customer=cust, base_grand_total=amt)

    def test_paid_by_the_ledger_is_not_awaiting_payment(self):
        from command_center.kpi.live import _Reader
        from command_center.kpi.live_departments import order_awaiting_payment
        from insights.compat import run_as
        with run_as("Administrator"):
            n, note, drill = order_awaiting_payment(_Reader(CODE))
        self.assertEqual(n, 1, "three orders by the invoices' outstanding; one by the ledger")
        self.assertEqual(note, "GHS 3,000 on the Customer Ledger")
        self.assertEqual(drill["filters"]["src_name"], ["in", ["SO-2"]])


# =========================================================================== 8
class DrillsMatchTheirFigures(_Business):
    """A rule's records add up to its figure: drafts are in no figure, so they are in no
    drill either."""

    def setUp(self):
        super().setUp()
        import uuid
        from insights.core import models as M
        SL, PL = M.CommandCenterFactSalesInvoiceLine, M.CommandCenterFactPurchaseInvoiceLine
        day = TODAY - dt.timedelta(days=10)

        def mk(model, ds, **kw):
            k = uuid.uuid4().hex
            model.objects.create(name=k, fact_key=k, business_code=CODE, src_docstatus=ds,
                                 src_name=f"INV-{k[:6]}", posting_date=day, **kw)
        for ds, margin in ((1, -2000), (0, -5000)):          # the draft is 5,000 below cost
            mk(SL, ds, item_code="BED-2", item_group="Beds", base_net_amount=1000,
               base_margin_amount=margin, has_cost=1)
        for ds, amount in ((1, 20000), (0, 9000)):
            mk(SL, ds, item_code="SRV-1", item_group="Services", base_net_amount=amount,
               has_cost=0, base_margin_amount=0)
        mk(SL, 1, item_code="CON-1", item_group="Consumables", base_net_amount=10000,
           base_margin_amount=2000, has_cost=1)
        for s, v in (("Sup One", 80000), ("Sup Two", 10000), ("Sup Three", 5000)):
            mk(PL, 1, supplier=s, base_net_amount=v)
        mk(PL, 0, supplier="Sup One", base_net_amount=70000)    # a draft bill

    def _drill_total(self, drill, measure, sign=1):
        import frappe
        from command_center.facts.schema import FACTS
        rows = frappe.get_all(FACTS[drill["fact"]], filters={"business_code": CODE,
                                                              **drill["filters"]},
                              fields=[measure], limit=100000)
        return round(sign * sum(float(r[measure] or 0) for r in rows), 2)

    def test_each_rules_drill_adds_up_to_its_money(self):
        from command_center.recommend import engine, rules
        from insights.compat import run_as
        with run_as("Administrator"):
            ctx = engine._context(CODE)
            defaults = {r.rule_id: {p.key: float(p.default) for p in r.params} for r in rules.RULES}
            for fn, measure, sign in ((rules.sold_below_cost, "base_margin_amount", -1),
                                      (rules.lines_without_cost, "base_net_amount", 1),
                                      (rules.supplier_concentration, "base_net_amount", 1)):
                [rec] = fn(ctx, defaults[fn.__name__])
                self.assertEqual(self._drill_total(rec["drill"], measure, sign), round(rec["money"], 2),
                                 f"{fn.__name__}: its records do not add up to its figure")

    def test_every_fact_drill_on_a_fact_with_drafts_names_its_docstatus(self):
        """Structural: every drill into a fact that holds drafts (invoices and their lines)
        says which documents it counts, as the figure does."""
        import ast
        import inspect
        from command_center.insight import diagnose
        from command_center.recommend import rules
        drafty = {"fact_sales_invoice", "fact_sales_invoice_line", "fact_purchase_invoice",
                  "fact_purchase_invoice_line"}
        for mod in (rules, diagnose):
            for node in ast.walk(ast.parse(inspect.getsource(mod))):
                if not isinstance(node, ast.Dict):
                    continue
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                if "fact" not in keys or "filters" not in keys:
                    continue
                fact = node.values[keys.index("fact")]
                if not (isinstance(fact, ast.Constant) and fact.value in drafty):
                    continue
                filt = node.values[keys.index("filters")]
                src = ast.unparse(filt)
                self.assertTrue("src_docstatus" in src or "src_name" in src,
                                f"{mod.__name__} line {node.lineno}: a drill into {fact.value} "
                                f"that counts drafts: {src}")


# =========================================================================== 9
class _Ledger:
    """A business's Stock Ledger, answering grouped reads as ERPNext does."""

    local = False

    def __init__(self, rows):
        self.rows, self.conn = rows, self

    def reader(self):
        return self

    def get_list(self, doctype, filters=None, fields=None, group_by=None, limit=None,
                 parent_doctype=None, order_by=None):
        import re
        from insights.tests import _hr_match
        rows = [r for r in self.rows if _hr_match(r, filters or {})]
        groups = [g.strip() for g in (group_by or "").split(",") if g.strip()]
        out = {}
        for r in rows:
            key = tuple(r.get(g) for g in groups)
            got = out.setdefault(key, {g: r.get(g) for g in groups})
            for f in fields:
                m = re.match(r"(sum|count|max)\((\w+)\) as (\w+)", str(f))
                if not m:
                    continue
                fn, field, alias = m.groups()
                v = r.get(field)
                got[alias] = (got.get(alias) or 0) + (v if fn == "sum" else 1) if fn != "max" \
                    else max(str(got.get(alias) or ""), str(v))
        return list(out.values())


class TransfersAreNotSales(SimpleTestCase):
    def test_only_sales_and_consumption_take_stock_out(self):
        from command_center.recommend.rules import outflow
        day = str(TODAY - dt.timedelta(days=5))
        sle = lambda vt, vno, wh, q: {"item_code": "ITEM-A", "voucher_type": vt,  # noqa: E731
                                      "voucher_no": vno, "warehouse": wh, "actual_qty": q,
                                      "posting_date": day, "is_cancelled": 0, "name": vno + wh}
        ctx = _Ledger([sle("Stock Entry", "STE-1", "W1", -10), sle("Stock Entry", "STE-1", "W2", 10),
                       sle("Delivery Note", "DN-1", "W2", -3),
                       sle("Stock Entry", "STE-2", "W2", -2),            # a Material Issue
                       sle("Stock Reconciliation", "SR-1", "W1", -5),
                       sle("Purchase Receipt", "PR-9", "W1", -4)])       # a return to a supplier
        self.assertEqual(outflow(ctx, 90), {"ITEM-A": (5.0, 2)},
                         "the transfer, the correction and the return are not sales")


# =========================================================================== 10
class HealthOnLastWeek(TransactionTestCase):
    databases = {"default", "aux"}

    def setUp(self):
        from insights.compat import run_as
        self._as = run_as("Administrator")
        self._as.__enter__()
        self.addCleanup(lambda: self._as.__exit__(None, None, None))

    def figs(self, **scores):
        from insights.tests import SIX, _health_figs
        vals = {k: scores.get(k, 70.0) for k in SIX}
        scored = [v for v in vals.values() if v is not None]
        return _health_figs(round(sum(scored) / len(scored)), **vals)

    def test_monday_is_compared_with_a_week_before_not_with_sunday(self):
        from command_center import health
        health.snapshot("biz", self.figs(), today=dt.date(2026, 11, 9))         # Monday a week before
        health.snapshot("biz", self.figs(score_paid=40.0), today=dt.date(2026, 11, 15))  # Sunday
        health.snapshot("biz", self.figs(score_paid=46.0), today=dt.date(2026, 11, 16))  # Monday
        got = health.history("biz", today=dt.date(2026, 11, 16))
        self.assertEqual(got["last_week"]["day"], "2026-11-09")
        self.assertEqual(got["delta"], -4, "against the 9th (70 each), not Sunday the 15th")

    def test_a_question_entering_does_not_move_the_change(self):
        from command_center import health
        before = self.figs(score_approvals=None)                  # five scored a week ago
        health.snapshot("biz", before, today=dt.date(2026, 11, 9))
        now = self.figs(score_approvals=10.0)                     # the sixth arrives, low
        health.snapshot("biz", now, today=dt.date(2026, 11, 16))
        got = health.history("biz", today=dt.date(2026, 11, 16))
        self.assertEqual(got["delta"], 0, "the same five questions, unchanged")
        self.assertEqual(got["delta_questions"], {"questions": 5, "of": 6})
        from command_center import summary
        fig = {"value": 60, "data_status": {"state": "live"}}
        self.assertEqual(summary.health_change("biz", fig, got)["text"],
                         "No change on last week, on the 5 questions scored both times")

    def test_a_partial_read_never_replaces_a_fuller_one(self):
        from command_center import health
        day = dt.date(2026, 11, 16)
        self.assertTrue(health.snapshot("biz", self.figs(), today=day))
        loading = self.figs(score_paid=None)
        loading["score_paid"]["data_status"]["state"] = "not_loaded"
        self.assertFalse(health.snapshot("biz", loading, today=day))


# =========================================================================== 12
class AMonthIsFullOnceItIsOver(SimpleTestCase):
    def test_the_last_day_of_the_month_is_not_yet_a_full_month(self):
        from command_center.kpi.engine import full_month_end
        self.assertEqual(str(full_month_end("2026-10-31", today="2026-10-31")), "2026-09-30")
        self.assertEqual(str(full_month_end("2026-10-31", today="2026-11-01")), "2026-10-31")
        self.assertEqual(str(full_month_end("2026-10-12", today="2026-11-17")), "2026-09-30")

    def test_the_analysts_comparisons_use_the_same_rule(self):
        from command_center.ask import tools
        with mock.patch("frappe.utils.today", lambda: "2026-10-31"):
            (a, b, label), _ = tools._spans("2026-10-31", "month_vs_previous")
        self.assertEqual(label, "September 2026")


# =========================================================================== 13
class RowsERPNext(CoverERPNext):
    """CoverERPNext, counting only the rows a count's filters match."""

    def answer(self, m, p):
        from insights.tests import _R, _hr_match
        if m == "frappe.client.get_count" and p.get("doctype") in self.cover:
            f = p.get("filters") or {}
            f = json.loads(f) if isinstance(f, str) else f
            return _R(200, {"message": len([r for r in self.cover[p["doctype"]] if _hr_match(r, f)])})
        return super().answer(m, p)


class BankTransfersCountOnce(_Business):
    def rows(self):
        pe = lambda name, frm, to, cleared=None: {  # noqa: E731
            "name": name, "docstatus": 1, "paid_from": frm, "paid_to": to,
            "clearance_date": cleared}
        return {"Account": [{"name": "GCB - G", "account_type": "Bank", "is_group": 0},
                            {"name": "Ecobank - G", "account_type": "Bank", "is_group": 0}],
                "Payment Entry": [pe("PE-1", "Debtors - G", "GCB - G", "2026-11-01"),
                                  pe("PE-2", "GCB - G", "Creditors - G"),
                                  pe("PE-3", "GCB - G", "Ecobank - G", "2026-11-02")]}

    def setUp(self):
        super().setUp()
        self.fake.__class__ = RowsERPNext

    def test_a_transfer_between_banks_is_one_payment(self):
        from command_center.kpi.live import _Reader, bank_cleared_pct
        from insights.compat import run_as
        with run_as("Administrator"):
            value, note = bank_cleared_pct(_Reader(CODE))[:2]
        self.assertEqual(note, "of 3 bank payments matched to a statement", "the transfer was counted twice")
        self.assertAlmostEqual(value, 100 * 2 / 3, places=3)


# =========================================================================== 17
class _Live(_Ledger):
    """A business's ERPNext as a screen reads it: plain reads cut to their fields, counts,
    and grouped sums (_Ledger)."""

    base_url = "https://erp.test"
    code = CODE

    def get_list(self, doctype, filters=None, fields=None, group_by=None, limit=None,
                 parent_doctype=None, order_by=None):
        from insights.tests import _hr_match
        if group_by:
            return super().get_list(doctype, filters, fields, group_by)
        rows = [r for r in self.rows.get(doctype, []) if _hr_match(r, filters or {})]
        return [{f: r.get(f) for f in (fields or ["name"])} for r in rows]

    def all(self, doctype, filters=None, fields=None, limit=None, parent=None, order_by=None):
        return self.get_list(doctype, filters, fields)

    def count(self, doctype, filters=None):
        return len(self.get_list(doctype, filters))

    def has(self, doctype):
        return True


class BudgetOnAGroupCostCentre(_Business):
    def test_a_group_budget_counts_its_childrens_spending(self):
        from command_center.api import panels
        from insights.compat import run_as
        year = str(TODAY.year)
        gl = lambda cc, debit: {"account": "Travel - G", "cost_center": cc, "debit": debit,  # noqa: E731
                                "credit": 0, "is_cancelled": 0, "posting_date": _d(-1)}
        live = _Live({})
        live.rows = {
            "Budget": [{"name": "BUD-1", "docstatus": 1, "fiscal_year": year,
                        "budget_against": "Cost Center", "cost_center": "Sales - G"}],
            "Budget Account": [{"parent": "BUD-1", "account": "Travel - G", "budget_amount": 10000}],
            "Fiscal Year": [{"name": year, "year_start_date": f"{year}-01-01",
                             "year_end_date": f"{year}-12-31"}],
            "Cost Center": [{"name": "Main - G", "lft": 1, "rgt": 8},
                            {"name": "Sales - G", "lft": 2, "rgt": 7},       # a group
                            {"name": "Accra Sales - G", "lft": 3, "rgt": 4},
                            {"name": "Kumasi Sales - G", "lft": 5, "rgt": 6}]}
        # grouped GL reads aggregate the GL rows (_Ledger)
        ledger = [gl("Accra Sales - G", 3000), gl("Kumasi Sales - G", 2500), gl("Main - G", 9999)]

        class Reader(_Live):
            def get_list(self, doctype, filters=None, fields=None, group_by=None, **kw):
                if doctype == "GL Entry":
                    return _Ledger(ledger).get_list(doctype, filters, fields, group_by)
                return super().get_list(doctype, filters, fields, group_by)
        r = Reader({})
        r.rows = live.rows
        with run_as("Administrator"):
            ctx = panels._Ctx(CODE)
            ctx._reader = r
            out = panels.fin_budget(ctx)
        [bar] = out["bars"] if "bars" in out else out["rows"]
        self.assertEqual(bar["display"], "55% used", "5,500 of 10,000 spent under Sales - G, not 0%")


class DatelineIsTheOldestRead(_Business):
    def test_the_memo_is_dated_by_its_stalest_vital_sign(self):
        from command_center import summary
        from insights.compat import run_as
        live = {"data_status": {"state": "live"}, "value": 1}
        figs = {"cash_in_month": {**live, "as_of": {"last_read": "2026-11-17 09:40:00"}},
                "ar_total": {**live, "as_of": {"last_read": "2026-11-16 18:05:00"}},
                "score_paid": {**live, "as_of": {"last_read": "2026-11-17 10:15:00"}}}
        with run_as("Administrator"):
            head = summary.header(CODE, figs, user="Administrator",
                                  now=dt.datetime(2026, 11, 17, 10, 30))
        self.assertIn("read from ERPNext at 18:05 on 16 Nov 2026", head["dateline"])


# =========================================================================== 15
class DeletedDraftsLeave(_Business):
    def rows(self):
        si = lambda name: {"name": name, "modified": "2026-10-01 10:00:00.000001",  # noqa: E731
                           "docstatus": 0, "posting_date": "2026-09-01", "due_date": "2026-09-30",
                           "status": "Draft", "is_return": 0, "customer": "Ama Clinic",
                           "customer_group": "Hospitals", "territory": "Ghana", "currency": "GHS",
                           "base_grand_total": 1500, "outstanding_amount": 1500}
        task = lambda name: {"name": name, "modified": "2026-10-01 10:00:00.000001",  # noqa: E731
                             "subject": name, "status": "Open", "priority": "High",
                             "project": None, "owner": "a@test.com", "exp_start_date": None,
                             "exp_end_date": "2026-10-10", "completed_on": None, "_assign": None}
        return {"Sales Invoice": [si("SI-D1"), si("SI-D2")], "Task": [task("T-1"), task("T-2")]}

    def test_a_deleted_draft_or_task_leaves_at_the_next_incremental_load(self):
        from command_center.ingest.operations import TaskIngestor
        from command_center.ingest.sales import SalesInvoiceIngestor
        from insights.compat import run_as
        from insights.core.models import CommandCenterFactSalesInvoice as SI
        from insights.core.models import CommandCenterFactTask as T
        with run_as("Administrator"):
            for ing in (SalesInvoiceIngestor, TaskIngestor):
                ing().load(self.conn(), as_of="2026-11-01", full=True)
        self.fake.cover["Sales Invoice"] = self.fake.cover["Sales Invoice"][1:]   # SI-D1 deleted
        self.fake.cover["Task"] = self.fake.cover["Task"][:1]                     # T-2 deleted
        with run_as("Administrator"):
            for ing in (SalesInvoiceIngestor, TaskIngestor):
                ing().load(self.conn(), as_of="2026-11-01", full=False)
        self.assertEqual(sorted(SI.objects.filter(business_code=CODE).values_list("src_name", flat=True)),
                         ["SI-D2"])
        self.assertEqual(sorted(T.objects.filter(business_code=CODE).values_list("src_name", flat=True)),
                         ["T-1"])
        f = self.figures("invoices_draft")["invoices_draft"]
        self.assertEqual(f["value"], 1)


# =========================================================================== 11
def two_company_rows() -> dict:
    si = lambda name, company, amt: {  # noqa: E731
        "name": name, "modified": "2026-10-01 10:00:00.000001", "docstatus": 1,
        "posting_date": "2026-09-01", "due_date": "2026-09-30", "status": "Unpaid",
        "is_return": 0, "customer": "Ama Clinic", "customer_group": "Hospitals",
        "territory": "Ghana", "currency": "GHS", "base_grand_total": amt,
        "outstanding_amount": amt, "company": company}
    return {"Company": [{"name": "Test Medical Ltd", "default_currency": "GHS"},
                        {"name": "Sister Pharma Ltd", "default_currency": "GHS"}],
            "Sales Invoice": [si("SI-1", "Test Medical Ltd", 1000), si("SI-2", "Sister Pharma Ltd", 7000)],
            "Bin": [{"name": "B1", "modified": "2026-10-01 10:00:00", "warehouse": "Stores - TML",
                     "item_code": "A", "stock_uom": "Nos", "actual_qty": 5, "reserved_qty": 0,
                     "ordered_qty": 0, "projected_qty": 5, "valuation_rate": 10, "stock_value": 50},
                    {"name": "B2", "modified": "2026-10-01 10:00:00", "warehouse": "Stores - SPL",
                     "item_code": "A", "stock_uom": "Nos", "actual_qty": 9, "reserved_qty": 0,
                     "ordered_qty": 0, "projected_qty": 9, "valuation_rate": 10, "stock_value": 90}],
            "Warehouse": [{"name": "Stores - TML", "company": "Test Medical Ltd"},
                          {"name": "Stores - SPL", "company": "Sister Pharma Ltd"}]}


class OneCompanyOfSeveral(_Business):
    rows = staticmethod(two_company_rows)

    def setUp(self):
        super().setUp()
        self.fake.__class__ = RowsERPNext

    def test_a_business_reads_only_its_own_company(self):
        from insights.core.models import CommandCenterFactSalesInvoice as SI
        from insights.core.models import CommandCenterFactStockBalance as SB
        self.load("fact_sales_invoice", "fact_stock_balance")
        self.assertEqual(list(SI.objects.filter(business_code=CODE).values_list("src_name", flat=True)),
                         ["SI-1"], "Sister Pharma's invoice was loaded into Test Medical's figures")
        self.assertEqual(list(SB.objects.filter(business_code=CODE).values_list("src_name", flat=True)),
                         ["B1"])
        from command_center.kpi.live import _Reader
        from insights.compat import run_as
        with run_as("Administrator"):
            self.assertEqual(_Reader(CODE).count("Sales Invoice", {"docstatus": 1}), 1)


class OneCompanyChangesNothing(_Business):
    def rows(self):
        rows = two_company_rows()
        rows["Company"] = rows["Company"][:1]
        rows["Sales Invoice"] = [dict(r, company=None) for r in rows["Sales Invoice"]]
        return rows

    def test_a_single_company_site_is_read_as_before(self):
        from insights.core.models import CommandCenterFactSalesInvoice as SI
        self.load("fact_sales_invoice")
        self.assertEqual(SI.objects.filter(business_code=CODE).count(), 2,
                         "no company filter is added where the ERPNext keeps one company")
