"""One company of an ERPNext that keeps several (17 Nov 2026).

A business on the platform is one company (Connected Business.erpnext_company). An ERPNext
site can keep several, and nothing filtered by company: every load and every live read
took all of them, so a group's second company was added into the first's receivables,
sales and stock. scoped(conn) is the connector every load (api/ingest.load_business, the
reconciliation's source figures) and every live read (kpi/live._Reader, behind every
screen panel, rule and the order cover; api/statements) goes through: on a site with more
than one company, a read of a record that belongs to one -- an invoice, a payment, a
journal, a ledger entry, an order, a task -- is limited to the business's, and a stock
balance to its warehouses. On a site with one company (Gigmann, 17 Nov 2026) nothing is
added and nothing changes.
"""

from __future__ import annotations

import frappe

from command_center.ingest.base import require_fields

# The standard doctypes that carry the company they belong to (ERPNext v14 to v16). A
# child table is reached through its parent's names, which are already the company's.
COMPANY_DOCTYPES = frozenset({
    "Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry", "GL Entry",
    "Payment Ledger Entry", "Sales Order", "Purchase Order", "Quotation", "Delivery Note",
    "Purchase Receipt", "Material Request", "Stock Entry", "Stock Reconciliation",
    "Stock Ledger Entry", "Supplier Quotation", "Request for Quotation", "Pick List",
    "POS Invoice", "Opportunity", "Account", "Cost Center", "Warehouse", "Budget",
    "Period Closing Voucher", "Bank Account", "Bank Transaction", "Asset", "Project", "Task",
    "Employee", "Issue", "Salary Slip", "Payroll Entry", "Expense Claim",
    "Leave Application", "Leave Allocation", "Department", "Timesheet", "Sales Taxes and Charges Template",
    "Purchase Taxes and Charges Template",
})
# Linked to a company through its warehouse.
BY_WAREHOUSE = frozenset({"Bin"})
CACHE_SECONDS = 6 * 3600


def companies(conn) -> list | None:
    """The companies the business's ERPNext keeps, kept six hours; None when it could not
    be asked (remembered a minute, so a business that is away is not asked at every read)."""
    key = f"cc:companies:{getattr(conn, 'code', '')}"
    cache = frappe.cache()
    got = cache.get_value(key)
    if got == "?":
        return None
    if got is None:
        try:
            got = [r.get("name") for r in require_fields(
                conn.get_list("Company", fields=["name"], limit=100), ["name"], "Company")
                   if r.get("name")]
        except Exception:
            cache.set_value(key, "?", expires_in_sec=60)
            return None
        cache.set_value(key, got, expires_in_sec=CACHE_SECONDS)
    return list(got)


def company_of(conn) -> str | None:
    business = getattr(conn, "business", None)
    return (getattr(business, "erpnext_company", None) or None) if business else None


def scoped(conn):
    """The connector, limited to the business's company when its ERPNext keeps more than
    one; the connector itself otherwise (or when no company is named)."""
    if conn is None or isinstance(conn, CompanyScoped):
        return conn
    company = company_of(conn)
    if not company:
        return conn
    known = companies(conn)
    if known is None or len(known) <= 1:
        return conn   # one company, or cannot tell (the read then fails on its own)
    return CompanyScoped(conn, company)


class CompanyScoped:
    """A connector's reads, limited to one company. Everything else is the connector's."""

    def __init__(self, conn, company):
        self._conn, self.company = conn, company
        self._warehouses = None

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def as_system(self):
        return CompanyScoped(self._conn.as_system(), self.company)

    def as_user(self, user):
        return CompanyScoped(self._conn.as_user(user), self.company)

    def warehouses(self) -> list:
        if self._warehouses is None:
            self._warehouses = [r["name"] for r in require_fields(self._conn.get_list(
                "Warehouse", filters={"company": self.company}, fields=["name"], limit=100000),
                ["name"], "Warehouse")]
        return self._warehouses

    def scope(self, doctype, filters):
        from command_center.connectors.remote import _and
        names = ({k for k in filters} if isinstance(filters, dict) else
                 {x[-3] for x in (filters or []) if isinstance(x, (list, tuple)) and len(x) >= 3})
        if doctype in COMPANY_DOCTYPES and "company" not in names:
            return _and(doctype, filters or {}, [("company", "=", self.company)])
        if doctype in BY_WAREHOUSE and "warehouse" not in names:
            return _and(doctype, filters or {}, [("warehouse", "in", self.warehouses() or [""])])
        return filters

    def get_list(self, doctype, filters=None, fields=None, limit=20, order_by=None,
                 group_by=None, parent_doctype=None):
        return self._conn.get_list(doctype, filters=self.scope(doctype, filters or {}),
                                   fields=fields, limit=limit, order_by=order_by,
                                   group_by=group_by, parent_doctype=parent_doctype)

    def get_count(self, doctype, filters=None):
        return self._conn.get_count(doctype, self.scope(doctype, filters or {}))

    def get_value(self, doctype, filters, fieldname):
        if isinstance(filters, (dict, list)):
            filters = self.scope(doctype, filters)
        return self._conn.get_value(doctype, filters, fieldname)
