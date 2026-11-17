"""Stock & Warehouses' Stock Balance and Stock Movements tabs (api/stock.py):

    .venv-platform/bin/python manage.py test insights.test_stock

Against crafted ERPNext rows: Bin (loaded into fact_stock_balance), Item names, and a
Stock Ledger Entry that the fake filters, orders newest first and pages as ERPNext would.
"""

from __future__ import annotations

import io
import json
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client

from insights.test_figures import CODE, _Business, _d
from insights.tests import _R, _hr_match, CoverERPNext

PASS = "a-long-test-pass-9"


def stock_rows() -> dict:
    bin_ = lambda n, item, wh, qty, rate, uom="Pcs": {  # noqa: E731
        "name": n, "modified": "2026-11-10 10:00:00.000001", "item_code": item, "warehouse": wh,
        "stock_uom": uom, "actual_qty": qty, "reserved_qty": 0, "ordered_qty": 0,
        "projected_qty": qty, "valuation_rate": rate, "stock_value": qty * rate}
    sle = lambda n, day, time, item, wh, qty, after, vt, vn, cancelled=0: {  # noqa: E731
        "name": n, "posting_date": _d(day), "posting_time": time, "creation": f"{_d(day)} {time}",
        "item_code": item, "warehouse": wh, "actual_qty": qty, "qty_after_transaction": after,
        "voucher_type": vt, "voucher_no": vn, "is_cancelled": cancelled}
    return {
        "Bin": [bin_("B1", "OVEN", "Central Store - T", 2, 5800),
                bin_("B2", "GLOVE", "Central Store - T", 40, 12.5, "Box"),
                bin_("B3", "GLOVE", "Kumasi - T", 10, 12.5, "Box"),
                bin_("B4", "OVEN", "Kumasi - T", 0, 5800)],        # nothing held: not listed
        "Item": [{"name": "OVEN", "item_name": "Lab Oven 60L", "item_group": "Equipment"},
                 {"name": "GLOVE", "item_name": "Nitrile Gloves", "item_group": "Consumables"}],
        "Stock Ledger Entry": [
            sle("SLE-6", 0, "15:00:00", "GLOVE", "Central Store - T", -5, 40, "Sales Invoice", "SINV-9"),
            sle("SLE-5", 0, "11:00:00", "GLOVE", "Kumasi - T", 10, 10, "Stock Entry", "STE-3"),
            sle("SLE-4", 0, "10:00:00", "OVEN", "Central Store - T", 1, 2, "Purchase Receipt", "PR-2"),
            sle("SLE-X", -1, "09:00:00", "OVEN", "Central Store - T", 5, 6, "Stock Entry", "STE-0", 1),
            sle("SLE-3", -2, "09:00:00", "GLOVE", "Central Store - T", 45, 45, "Purchase Receipt", "PR-1"),
            sle("SLE-2", -10, "09:00:00", "OVEN", "Central Store - T", 1, 1, "Purchase Receipt", "PR-0"),
            sle("SLE-1", -45, "09:00:00", "OVEN", "Central Store - T", 0, 0, "Stock Reconciliation", "SR-1"),
        ],
    }


class StockERPNext(CoverERPNext):
    """Counts and "like" filters as ERPNext answers them; the ledger newest first."""

    def answer(self, m, p):
        dt_ = p.get("doctype")
        if dt_ in self.cover and m in ("frappe.client.get_list", "frappe.client.get_count"):
            f = p.get("filters") or {}
            f = json.loads(f) if isinstance(f, str) else f
            rows = [r for r in self.cover[dt_] if _hr_match(r, f) and _like(r, f)]
            if dt_ == "Stock Ledger Entry":
                self.ledger_reads.append(p)
                rows.sort(key=lambda r: (r["posting_date"], r["posting_time"], r["creation"],
                                         r["name"]), reverse=True)
            if m == "frappe.client.get_count":
                return _R(200, {"message": len(rows)})
            fields = p.get("fields") or ["name"]
            fields = json.loads(fields) if isinstance(fields, str) else fields
            start = int(p.get("limit_start") or 0)
            n = int(p.get("limit_page_length") or 20)
            cols = [re.split(r"\s+as\s+", str(x))[-1].strip() for x in fields]
            return _R(200, {"message": [{c: r.get(c) for c in cols} for r in rows[start:start + n]]})
        return super().answer(m, p)


def _like(row, filters) -> bool:
    for f in filters if isinstance(filters, list) else []:
        if len(f) >= 3 and f[-2] == "like":
            pat = str(f[-1]).strip("%").lower()
            if pat not in str(row.get(f[-3]) or "").lower():
                return False
    return True


class _Stock(_Business):
    rows = staticmethod(stock_rows)

    def setUp(self):
        super().setUp()
        self.fake.__class__ = StockERPNext
        self.fake.ledger_reads = []
        self.load("fact_stock_balance")
        U = get_user_model()
        u = U.objects.create_user("boss@test.com", "boss@test.com", PASS)
        u.groups.add(Group.objects.get(name="Insights Dashboard Manager"))
        self.c = Client()
        self.assertTrue(self.c.login(username="boss@test.com", password=PASS))

    def raw(self, fn, **args):
        return self.c.post(f"/api/method/command_center.api.stock.{fn}",
                           json.dumps({"business_code": CODE, **args}),
                           content_type="application/json")

    def post(self, fn, **args):
        r = self.raw(fn, **args)
        self.assertEqual(r.status_code, 200, f"{fn}: {r.content[:400]!r}")
        return r.json()["message"]


class StockBalance(_Stock):
    def test_one_row_per_item_and_warehouse_by_name_largest_first(self):
        got = self.post("balance")
        self.assertEqual(got["kind"], "stock_balance")
        self.assertEqual(got["currency"], "GHS")
        self.assertEqual([(r["item_name"], r["warehouse"], r["qty"], r["value"]) for r in got["rows"]],
                         [("Lab Oven 60L", "Central Store - T", 2, 11600),
                          ("Nitrile Gloves", "Central Store - T", 40, 500),
                          ("Nitrile Gloves", "Kumasi - T", 10, 125)])
        self.assertEqual(got["rows"][0]["item_code"], "OVEN")
        self.assertEqual(got["rows"][0]["valuation_rate"], 5800)
        # the totals: every line the filters match; no quantity across different units
        self.assertEqual(got["totals"], {"lines": 3, "value": 12225, "qty": None, "uom": None})
        self.assertEqual(got["warehouses"], ["Central Store - T", "Kumasi - T"])

    def test_search_and_warehouse(self):
        got = self.post("balance", q="nitrile")
        self.assertEqual({r["item_code"] for r in got["rows"]}, {"GLOVE"})
        self.assertEqual(got["totals"], {"lines": 2, "value": 625, "qty": 50, "uom": "Box"})
        got = self.post("balance", q="oven", warehouse="Kumasi - T")
        self.assertEqual(got["rows"], [])   # the oven's Kumasi line holds nothing
        self.assertEqual(self.post("balance", q="OVEN")["rows"][0]["item_name"], "Lab Oven 60L")

    def test_pages(self):
        with mock.patch("command_center.api.stock.BALANCE_PAGE", 2):
            one, two = self.post("balance", page=1), self.post("balance", page=2)
        self.assertEqual((one["pages"], len(one["rows"]), len(two["rows"])), (2, 2, 1))
        self.assertEqual(two["totals"]["lines"], 3)

    def test_excel(self):
        from openpyxl import load_workbook
        r = self.raw("balance_xlsx", warehouse="Central Store - T")
        self.assertEqual(r.status_code, 200, r.content[:300])
        ws = load_workbook(io.BytesIO(r.content)).active
        self.assertEqual([c.value for c in ws[4]][:7], ["Item", "Item Code", "Warehouse", "Quantity",
                                                        "Unit", "Valuation Rate", "Value GHS"])
        self.assertEqual(ws.cell(row=5, column=1).value, "Lab Oven 60L")
        self.assertEqual(ws.cell(row=7, column=1).value, "Total (2 lines)")
        self.assertEqual(ws.cell(row=7, column=7).value, 12100)

    def test_managers_only(self):
        U = get_user_model()
        U.objects.create_user("clerk@test.com", "clerk@test.com", PASS)
        c = Client()
        c.login(username="clerk@test.com", password=PASS)
        for fn in ("balance", "movements", "balance_xlsx", "movements_xlsx"):
            r = c.post(f"/api/method/command_center.api.stock.{fn}", json.dumps({"business_code": CODE}),
                       content_type="application/json")
            self.assertEqual(r.status_code, 403, fn)
            self.assertEqual(self.c.get(f"/api/method/command_center.api.stock.{fn}").status_code, 405, fn)


class StockMovements(_Stock):
    def test_newest_first_over_the_last_thirty_days_cancelled_left_out(self):
        got = self.post("movements")
        self.assertEqual(got["kind"], "stock_movements")
        self.assertEqual([r["id"] for r in got["rows"]], ["SLE-6", "SLE-5", "SLE-4", "SLE-3", "SLE-2"])
        self.assertEqual((got["from_date"], got["to_date"]), (_d(-30), _d(0)))
        self.assertEqual(got["total"], 5)
        self.assertIsNone(got["next"])
        first = got["rows"][0]
        self.assertEqual((first["item_name"], first["in_qty"], first["out_qty"], first["balance_qty"],
                          first["voucher_type"], first["voucher_no"]),
                         ("Nitrile Gloves", 0, 5, 40, "Sales Invoice", "SINV-9"))
        self.assertEqual(got["rows"][1]["in_qty"], 10)
        # one page at a time: never more than a page (and one to tell if there is more)
        asked = self.fake.ledger_reads[0]
        self.assertLessEqual(int(asked["limit_page_length"]), 101)
        self.assertIn(["is_cancelled", "=", 0], json.loads(asked["filters"])
                      if isinstance(asked["filters"], str) else asked["filters"])

    def test_pages_through_a_busy_day(self):
        with mock.patch("command_center.api.stock.MOVEMENTS_PAGE", 2):
            seen, nxt, pages = [], {}, 0
            while nxt is not None and pages < 10:
                got = self.post("movements", from_date=_d(-60), **(nxt or {}))
                seen += [r["id"] for r in got["rows"]]
                nxt = got["next"]
                pages += 1
        self.assertEqual(seen, ["SLE-6", "SLE-5", "SLE-4", "SLE-3", "SLE-2", "SLE-1"])
        self.assertEqual(pages, 3)

    def test_search_by_item_name_or_voucher_and_warehouse(self):
        got = self.post("movements", q="lab oven")
        self.assertEqual([r["id"] for r in got["rows"]], ["SLE-4", "SLE-2"])
        got = self.post("movements", q="SINV")
        self.assertEqual([r["id"] for r in got["rows"]], ["SLE-6"])
        got = self.post("movements", warehouse="Kumasi - T")
        self.assertEqual([r["id"] for r in got["rows"]], ["SLE-5"])
        # a warehouse that is not one of this business's is refused, not read
        self.assertEqual(self.raw("movements", warehouse="Elsewhere - X").status_code, 417)

    def test_excel(self):
        from openpyxl import load_workbook
        r = self.raw("movements_xlsx", from_date=_d(-60))
        self.assertEqual(r.status_code, 200, r.content[:300])
        ws = load_workbook(io.BytesIO(r.content)).active
        self.assertEqual([c.value for c in ws[4]][:9], ["Date", "Item", "Item Code", "Warehouse", "In",
                                                        "Out", "Balance After", "Voucher Type",
                                                        "Voucher No"])
        self.assertEqual(ws.max_row - 4 - 2, 6)     # six entries, then the vendor's credit
        self.assertEqual(ws.cell(row=5, column=9).value, "SINV-9")

    def test_unreachable(self):
        self.fake.down = True
        from django.core.cache import cache
        cache.clear()
        self.assertEqual(self.post("movements")["kind"], "unreachable")
