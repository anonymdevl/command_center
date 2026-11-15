"""The financial statements, as the business's own ERPNext draws them.

Profit and loss (gross and net profit), the balance sheet, the trial balance and cash
flow, for a chosen period, with a comparison and the ratios a chief executive reads
first. Every figure is ERPNext's: its own Profit and Loss Statement, Balance Sheet,
Trial Balance and Cash Flow reports, run on its site (frappe.desk.query_report.run,
the same call its desk makes) with its own accounting -- finance books, opening
entries, period closing, the cash flow mapping its accountants set up. Nothing is
re-derived from the General Ledger here; the platform only reads the rows the reports
return, adds them up the way the reports' own trees say, and says plainly where the
reports disagree with themselves.

What is worked out here, and only from the reports' rows:

    gross profit   income less the accounts of type "Cost of Goods Sold" (or ticked
                   "Include in Gross" on a version that has the box), the topmost such
                   account in each branch, so a cost-of-sales group counts once
    current / fixed  the balance sheet's branches by their names and account types
                   (Bank, Cash, Receivable, Stock are current; Fixed Asset,
                   Accumulated Depreciation, Capital Work in Progress are fixed)
    the checks     assets against liabilities + equity + the provisional profit;
                   the trial balance's debits against its credits; the cash flow's
                   three sections against its net change
    the ratios     current, quick, gross and net margin, debt to equity, working capital

One platform for ERPNext 14, 15 and 16. The reports' filters are read from the site
(query_report.get_script): a report's own options -- the trial balance's period-closing
flags, renamed between v14 and v15 -- are sent by every name the site's script
declares, and the shared financial-statement filters by both their spellings (a date
range as period_start_date/period_end_date with filter_based_on, and the fiscal years
as from_fiscal_year/to_fiscal_year). A filter a version does not know is ignored by
that report; one it requires is always there.

A report that cannot run says why, as a guide to what to set up in ERPNext
(command_center/guides.py): no fiscal year for the dates, no company, no chart of
accounts, a refusal of the platform's account. A business that does not answer is the
standard "can't reach" state. Never a figure that was not read.

Everything here is a read, under the asking manager's own key on that ERPNext when they
have linked one and the business's read-only account otherwise. Answers are kept five
minutes per business and period.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from urllib.parse import quote, urlencode

import frappe

from command_center.api.businesses import require_manager

REPORTS = {"pl": "Profit and Loss Statement", "bs": "Balance Sheet",
           "tb": "Trial Balance", "cf": "Cash Flow"}
CACHE_SECONDS = 300          # an open screen asks again every five minutes
META_SECONDS = 6 * 3600      # fiscal years, the chart of accounts, the reports' filters
SECTIONS = ("summary", "tb", "cf")
PERIODS = {"this_month": "This Month", "last_month": "Last Month", "quarter": "This Quarter",
           "ytd": "Year to Date", "last_year": "Last Year", "custom": "Custom"}
MAX_CUSTOM_DAYS = 3 * 366
COGS = "Cost of Goods Sold"
CURRENT_ASSET_TYPES = {"Bank", "Cash", "Receivable", "Stock", "Tax"}
FIXED_ASSET_TYPES = {"Fixed Asset", "Accumulated Depreciation", "Capital Work in Progress"}
CURRENT_LIABILITY_TYPES = {"Payable", "Tax"}
CASH_TYPES = {"Bank", "Cash"}
# The trial balance's options for period closing and earlier years' profit, by every name
# a version has used (v14: with_period_closing_entry; v15+: the two that replaced it).
TB_OPTIONS = {"with_period_closing_entry": 1, "with_period_closing_entry_for_opening": 1,
              "with_period_closing_entry_for_current_period": 1, "show_net_values": 1,
              "show_unclosed_fy_pl_balances": 1, "show_zero_values": 0,
              "include_default_book_entries": 1}
TB_COLUMNS = ("opening_debit", "opening_credit", "debit", "credit", "closing_debit",
              "closing_credit")
# Not period columns in a financial statement's answer.
NOT_PERIODS = {"account", "currency", "total", "opening_balance", "account_name"}


class Setup(Exception):
    """A statement cannot be drawn until something is set up in ERPNext."""

    def __init__(self, guide: dict):
        super().__init__(guide.get("text"))
        self.guide = guide


# --------------------------------------------------------------------------- endpoints
@frappe.whitelist()
def get(business_code: str | None = None, period: str = "ytd", from_date: str | None = None,
        to_date: str | None = None, section: str = "summary") -> dict:
    """One part of the Financial Statements area.

    section "summary": the cards, profit and loss (with the four periods at a glance and
    twelve months' trend), the balance sheet and the ratios; "tb": the trial balance;
    "cf": cash flow. Asked for separately so the screen draws the first while ERPNext is
    still working out the others."""
    require_manager()
    if section not in SECTIONS:
        frappe.throw(f"There is no statement section called {section!r}.")
    code = _business_code(business_code)
    if not code:
        return _choose()
    key = "cc:stmts:" + _digest([code, section, period, from_date, to_date, _today()])
    cached = frappe.cache().get_value(key)
    if cached:
        return cached
    ctx = _Ctx(code)
    out = ctx.head()
    try:
        if ctx.known_down():
            return {**out, **ctx.unreachable()}
        span = resolve_period(ctx, period, from_date, to_date)
        out.update(span)
        out.update({"summary": _summary, "tb": _trial_balance, "cf": _cash_flow}[section](ctx, span))
        out["state"] = "ok"
    except Setup as s:
        return {**out, "state": "needs_setup", "guide": s.guide}
    except frappe.ValidationError as e:  # the dates asked for (a custom period)
        return {**out, "state": "invalid", "message": str(e)}
    except Exception as e:
        from command_center.kpi.live_departments import is_down
        if is_down(e):
            return {**out, **ctx.unreachable()}
        frappe.log_error(title=f"Command Center statements {section}", message=frappe.get_traceback())
        return {**out, "state": "failed",
                "message": "The statements could not be read just now. They will be asked for again shortly."}
    frappe.cache().set_value(key, out, expires_in_sec=CACHE_SECONDS)
    return out


@frappe.whitelist(methods=["POST"])
def pdf(business_code: str | None = None, period: str = "ytd", from_date: str | None = None,
        to_date: str | None = None):
    """The four statements as one PDF, from the same answers the screen shows."""
    require_manager()
    from command_center.api import export
    parts = {s: get(business_code, period, from_date, to_date, s) for s in SECTIONS}
    head = parts["summary"]
    if head.get("state") != "ok":
        frappe.throw(head.get("message") or (head.get("guide") or {}).get("text")
                     or "The statements are not available to print just now.")
    title = f"Financial Statements, {head['period']['label']}"
    body = pdf_body(parts)
    frappe.local.response.filename = export._name(title, "pdf")
    frappe.local.response.filecontent = export.html_pdf(
        title, body, head.get("business_code"),
        footer=(f"Drawn by AI Business Intelligence from {head.get('business') or 'the business'}'s "
                f"own ERPNext reports (Profit and Loss Statement, Balance Sheet, Trial Balance, "
                f"Cash Flow) on {head.get('as_of')}. It reads those reports and cannot change "
                f"anything in ERPNext."))
    frappe.local.response.type = "pdf"


# --------------------------------------------------------------------------- the business
class _Ctx:
    def __init__(self, code: str):
        self.code = code
        row = frappe.db.get_value("Connected Business", {"business_code": code},
                                  ["business_name", "erpnext_company", "currency", "status",
                                   "last_sync", "is_local"], as_dict=True) or {}
        self.row = row
        self.name = row.get("business_name") or code
        self.currency = row.get("currency") or ""
        self._company = row.get("erpnext_company") or None
        self._conn = None
        self._site = None

    # -- reading ------------------------------------------------------------------
    @property
    def conn(self):
        if self._conn is None:
            from command_center.connectors.registry import connector_for
            self._conn = connector_for(self.code)
        return self._conn

    def known_down(self) -> bool:
        # Already marked unreachable (the shell's banner says so): no wait for the
        # retries. The 15-minute refresh and the banner's Retry reach out again.
        return (self.row.get("status") == "Unreachable" and not self.row.get("is_local"))

    def head(self) -> dict:
        return {"business_code": self.code, "business": self.name, "currency": self.currency,
                "as_of": _today()}

    def unreachable(self) -> dict:
        return {"state": "unreachable", "business": self.name,
                "last_loaded": str(self.row["last_sync"]) if self.row.get("last_sync") else None,
                "message": f"Can't reach {self.name}'s ERPNext right now."}

    def site(self) -> str:
        if self._site is None:
            from command_center.guides import site_url
            self._site = site_url(self.code)
        return self._site

    def _meta(self, what: str, fetch):
        key = "cc:stmts-meta:" + _digest([self.code, what])
        got = frappe.cache().get_value(key)
        if got is not None:
            return got
        got = fetch()
        frappe.cache().set_value(key, got, expires_in_sec=META_SECONDS)
        return got

    @property
    def company(self) -> str:
        if self._company:
            return self._company
        rows = self._meta("companies", lambda: [r.get("name") for r in self._refusing(
            "the companies", lambda: self.conn.get_list("Company", fields=["name"], limit=20))])
        if len(rows) == 1:
            self._company = rows[0]
            return self._company
        from command_center.guides import guide
        raise Setup(guide(self.code, (
            f"{self.name}'s company in ERPNext is not named on the platform, and its ERPNext "
            f"holds {'no company' if not rows else 'more than one'}, so the statements cannot "
            f"be drawn for one."), [
            "In ERPNext, open Company and note the exact name of the company whose accounts "
            "these are (create it there if there is none).",
            "Ask the platform's administrator to enter that name as the Company on this "
            "business, under Settings, Businesses."], "/app/company"))

    def fiscal_years(self) -> list[dict]:
        def fetch():
            rows = self._refusing("the fiscal years", lambda: self.conn.get_list(
                "Fiscal Year", fields=["name", "year_start_date", "year_end_date"],
                order_by="year_start_date asc", limit=200))
            return [{"name": r.get("name"), "start": str(r.get("year_start_date"))[:10],
                     "end": str(r.get("year_end_date"))[:10]} for r in rows
                    if r.get("year_start_date") and r.get("year_end_date")]
        return self._meta("fiscal_years", fetch)

    def fiscal_year(self, day, required: bool = False) -> dict | None:
        d = str(day)[:10]
        for fy in self.fiscal_years():
            if fy["start"] <= d <= fy["end"]:
                return fy
        if not required:
            return None
        from command_center.guides import guide
        raise Setup(guide(self.code, (
            f"{self.name}'s ERPNext has no fiscal year covering {_pretty(d)}, so its "
            f"trial balance cannot be drawn for these dates."), [
            "In ERPNext, open Accounting, then Fiscal Year, and press Add Fiscal Year.",
            "Enter the year's name, its start date and its end date (for a calendar year, "
            "1 January to 31 December), and save.",
            "If the business keeps more than one company, add each company to the year's "
            "Companies table."], "/app/fiscal-year/new", label="Add the fiscal year in ERPNext"))

    def accounts(self) -> dict:
        """The chart of accounts: name -> root type, account type, parent. {} when it
        cannot be read; the statements then go by their own rows."""
        def fetch():
            try:
                rows = self.conn.get_list(
                    "Account", filters={"company": self.company},
                    fields=["name", "root_type", "account_type", "is_group", "parent_account"],
                    limit=20000)
            except Setup:
                raise
            except Exception as e:
                from command_center.kpi.live_departments import is_down
                if is_down(e):
                    raise
                return {}
            return {r["name"]: {"root_type": r.get("root_type") or "",
                                "account_type": r.get("account_type") or "",
                                "is_group": int(r.get("is_group") or 0),
                                "parent": r.get("parent_account") or ""}
                    for r in rows if r.get("name")}
        return self._meta(f"accounts:{self.company}", fetch)

    def options(self, report: str) -> set:
        """The filter names a report's own script on this site declares."""
        def fetch():
            got = self._refusing(report, lambda: self.conn._call(
                "frappe.desk.query_report.get_script", {"report_name": report})
                if not self.conn.is_local else _local_script(report)) or {}
            script = got.get("script") or "" if isinstance(got, dict) else ""
            return sorted(set(re.findall(r"""["']?fieldname["']?\s*:\s*["'](\w+)["']""", script)))
        return set(self._meta(f"options:{report}", fetch))

    def run(self, report: str, filters: dict) -> dict:
        """One run of one of the four reports, kept five minutes."""
        f = {k: v for k, v in filters.items() if v is not None}
        key = "cc:stmts-run:" + _digest([self.code, report, f])
        got = frappe.cache().get_value(key)
        if got is not None:
            return got
        res = self._refusing(report, lambda: self.conn.run_report(report, filters=f)) or {}
        if not isinstance(res, dict):
            res = {}
        frappe.cache().set_value(key, res, expires_in_sec=CACHE_SECONDS)
        return res

    def _refusing(self, what: str, call):
        """A read whose refusal becomes a guide; a business that is down stays down."""
        from command_center.connectors.base import (CredentialRequired, RemotePermissionDenied,
                                                    RequestRefused)
        try:
            return call()
        except Setup:
            raise
        except (RemotePermissionDenied, CredentialRequired, frappe.PermissionError) as e:
            raise Setup(_permission_guide(self, what, e))
        except RequestRefused as e:
            raise Setup(_refused_guide(self, what, str(e)))
        except frappe.ValidationError as e:  # a business on this site: ERPNext's own words
            raise Setup(_refused_guide(self, what, str(e)))


def _local_script(report):
    from frappe.desk.query_report import get_script
    return get_script(report)


def _business_code(code):
    if code and code != "__all__":
        return code
    from command_center.api.businesses import loaded_codes
    codes = loaded_codes()
    return codes[0] if len(codes) == 1 else None


def _choose() -> dict:
    from command_center.api.businesses import loaded_codes
    n = len(loaded_codes())
    if not n:
        from command_center.guides import guide
        return {"state": "needs_setup", "as_of": _today(), "guide": guide(None, (
            "No business is connected yet, so there are no statements to draw."), [
            "Ask the platform's administrator to connect the business's ERPNext under "
            "Settings, Businesses."])}
    return {"state": "choose", "as_of": _today(),
            "message": "Financial statements are drawn for one business at a time: choose "
                       "one in the business switcher at the top."}


# --------------------------------------------------------------------------- guides
def _permission_guide(ctx, what, error):
    from command_center.guides import guide
    return guide(ctx.code, (
        f"{ctx.name}'s ERPNext refused to give this platform {what}: the account it reads "
        f"with there may not run the financial statements."), [
        "In ERPNext, open the User record of the account this platform reads with -- the "
        "read-only account set up for it, or your own account if you linked your key.",
        "Give it the Accounts User role (or another role that may read Account, GL Entry "
        "and the financial statement reports), and save.",
        "The statements appear here at the next refresh, within five minutes."],
        "/app/user", label="Open Users in ERPNext")


def _refused_guide(ctx, what, message):
    from command_center.guides import guide
    said = re.sub(r"^.*?(?:returned HTTP \d+)\s*", "", message or "").strip(" ()")
    said = re.sub(r"^[\w.]*(?:Error|Exception):\s*", "", said)[:300]
    low = said.lower()
    if "fiscal year" in low:
        return guide(ctx.code, f"{ctx.name}'s ERPNext has no fiscal year set up for these "
                     f"dates, so it cannot draw {what}." + (f" It said: {said}" if said else ""), [
            "In ERPNext, open Accounting, then Fiscal Year, and add the year these dates fall "
            "in, with its start and end dates.",
            "Then open the period here again."], "/app/fiscal-year/new",
            label="Add the fiscal year in ERPNext")
    if "account" in low and ("chart" in low or "not found" in low or "root" in low):
        return guide(ctx.code, f"{ctx.name}'s chart of accounts is not set up for {what}."
                     + (f" ERPNext said: {said}" if said else ""), [
            "In ERPNext, open Accounting, then Chart of Accounts, for the company.",
            "Make sure it has the five root groups (Assets, Liabilities, Equity, Income, "
            "Expenses) and that entries are posted to accounts under them."],
            "/app/account/view/tree", label="Open the Chart of Accounts")
    return guide(ctx.code, f"{ctx.name}'s ERPNext did not produce {what}."
                 + (f" It said: {said}" if said else ""), [
        f"Open {what if what in REPORTS.values() else 'the report'} in ERPNext with the same "
        "dates to see the whole message there.",
        "Put right what it names (most often a fiscal year or the company's default "
        "accounts), then open the period here again."],
        f"/app/query-report/{quote(what)}" if what in REPORTS.values() else None)


def _no_ledger_guide(ctx):
    from command_center.guides import guide
    return guide(ctx.code, (
        f"Nothing is posted to {ctx.name}'s ledger yet, so there is no balance sheet to "
        f"draw."), [
        "In ERPNext, check the Chart of Accounts for the company is in place (Accounting, "
        "then Chart of Accounts).",
        "Post the opening balances with an Opening Entry (Journal Entry, Entry Type "
        "Opening Entry) as at the day the books start in ERPNext.",
        "Invoices, payments and journals posted after that fill the statements."],
        "/app/account/view/tree", label="Open the Chart of Accounts")


# --------------------------------------------------------------------------- the period
def resolve_period(ctx, period, from_date=None, to_date=None) -> dict:
    """The period asked for and the one it is compared with (a year earlier)."""
    getdate = frappe.utils.getdate
    today = getdate(_today())
    first = lambda d: d.replace(day=1)  # noqa: E731
    if period not in PERIODS:
        period = "ytd"
    if period == "this_month":
        a, b = first(today), today
    elif period == "last_month":
        b = first(today) - dt.timedelta(days=1)
        a = first(b)
    elif period == "quarter":
        a, b = dt.date(today.year, 3 * ((today.month - 1) // 3) + 1, 1), today
    elif period in ("ytd", "last_year"):
        fy = ctx.fiscal_year(today)
        start = getdate(fy["start"]) if fy else dt.date(today.year, 1, 1)
        if period == "ytd":
            a, b = start, today
        else:
            b = start - dt.timedelta(days=1)
            prev = ctx.fiscal_year(b)
            a = getdate(prev["start"]) if prev else _shift_year(start, -1)
    else:
        try:
            a, b = getdate(from_date), getdate(to_date)
        except Exception:
            a = b = None
        if not a or not b:
            frappe.throw("Choose both dates for a custom period.")
        if a > b:
            a, b = b, a
        if (b - a).days > MAX_CUSTOM_DAYS:
            frappe.throw("A custom period can be up to three years long.")
    ca, cb = _shift_year(a, -1), _shift_year(b, -1)
    if period == "last_year":
        label_cmp = "Year Before"
    else:
        label_cmp = "Same Period Last Year"
    # the balance sheet: as at the period's end, against the end of the month before
    bs_cmp = first(b) - dt.timedelta(days=1)
    return {
        "period": {"key": period, "label": PERIODS[period] if period != "custom" else
                   f"{_pretty(a)} to {_pretty(b)}", "from": str(a), "to": str(b),
                   "span": _span(a, b)},
        "comparison": {"label": label_cmp, "from": str(ca), "to": str(cb), "span": _span(ca, cb)},
        "balance_dates": {"at": str(b), "compare": str(bs_cmp)},
    }


def _shift_year(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February
        return d.replace(year=d.year + years, day=28)


# --------------------------------------------------------------------------- report rows
def _cols(res) -> list[dict]:
    """The period columns of a financial statement's answer, in order."""
    out = []
    for c in res.get("columns") or []:
        if not isinstance(c, dict):
            continue
        fn = c.get("fieldname")
        if fn and fn not in NOT_PERIODS and c.get("fieldtype") in ("Currency", "Float") \
                and not c.get("hidden"):
            out.append({"key": fn, "label": c.get("label") or fn})
    return out


def _is_account(r, amap) -> bool:
    if not isinstance(r, dict):
        return False
    a = r.get("account")
    if not isinstance(a, str) or not a or a.startswith("'"):
        return False
    if amap:
        return a in amap
    return isinstance(r.get("indent"), (int, float)) and "parent_account" in r


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _label(r) -> str:
    return str(r.get("account_name") or r.get("account") or "").strip().strip("'").strip()


class _Tree:
    """A statement's account rows, with their parents and section (root type)."""

    def __init__(self, res, amap, order=()):
        self.cols = _cols(res)
        rows = res.get("result") or []
        self.nodes, self.by_name, self.extra = [], {}, []
        section, sections = 0, []   # account rows between the report's total rows
        for r in rows:
            if _is_account(r, amap):
                info = amap.get(r["account"], {}) if amap else {}
                n = {"account": r["account"], "name": _label(r),
                     "indent": int(r.get("indent") or 0),
                     "parent": r.get("parent_account") or info.get("parent") or "",
                     "root_type": info.get("root_type") or "",
                     "account_type": r.get("account_type") or info.get("account_type") or "",
                     "is_group": int(r.get("is_group") if r.get("is_group") is not None
                                     else info.get("is_group") or 0),
                     "gross": int(r.get("include_in_gross") or 0), "section": section,
                     "values": {c["key"]: _num(r.get(c["key"])) for c in self.cols}}
                self.nodes.append(n)
                self.by_name[n["account"]] = n
            elif isinstance(r, dict) and r:
                if any(isinstance(r.get(c["key"]), (int, float)) for c in self.cols):
                    self.extra.append({"label": _label(r), "section": section,
                                       "values": {c["key"]: _num(r.get(c["key"])) for c in self.cols}})
                    if self.nodes and self.nodes[-1]["section"] == section:
                        sections.append(section)
                        section += 1
        # No chart of accounts to say which root is which: the report's own order
        # (income then expenses; assets, liabilities, equity), checked against the
        # section's total row where it names its root type.
        for n in self.nodes:
            if not n["root_type"]:
                n["root_type"] = self._guess_root(n["section"], order)
        for n in self.nodes:
            p = self.by_name.get(n["parent"])
            n["depth_ok"] = bool(p) or not n["parent"]

    def _guess_root(self, section, order):
        words = {"Income": "income", "Expense": "expense", "Asset": "asset",
                 "Liability": "liabilit", "Equity": "equity"}
        total = next((e["label"] for e in self.extra if e["section"] == section), "")
        for rt, w in words.items():
            if w in total.lower():
                return rt
        return order[section] if section < len(order) else ""

    def roots(self, root_type):
        return [n for n in self.nodes if n["root_type"] == root_type
                and (not n["parent"] or n["parent"] not in self.by_name)]

    def ancestors(self, n):
        seen = set()
        p = self.by_name.get(n["parent"])
        while p and p["account"] not in seen:
            seen.add(p["account"])
            yield p
            p = self.by_name.get(p["parent"])

    def topmost(self, pred, root_type=None):
        return [n for n in self.nodes if (root_type is None or n["root_type"] == root_type)
                and pred(n) and not any(pred(a) for a in self.ancestors(n))]

    def total(self, nodes, col=None):
        if col is None:
            return sum(sum(n["values"].values()) for n in nodes)
        return sum(n["values"].get(col, 0.0) for n in nodes)

    def value(self, n, col=None):
        return sum(n["values"].values()) if col is None else n["values"].get(col, 0.0)

    def extra_value(self, needle, col=None, last=False):
        hits = [e for e in self.extra if needle in e["label"].lower()]
        if not hits:
            return None
        e = hits[-1] if last else hits[0]
        return sum(e["values"].values()) if col is None else e["values"].get(col, 0.0)


def _cogs_pred(n):
    return n["account_type"] == COGS or bool(n["gross"])


# --------------------------------------------------------------------------- profit and loss
def _pl_run(ctx, a, b, periodicity="Yearly"):
    fy_a, fy_b = ctx.fiscal_year(a), ctx.fiscal_year(b)
    f = {"company": ctx.company, "filter_based_on": "Date Range",
         "period_start_date": str(a), "period_end_date": str(b),
         "from_fiscal_year": fy_a and fy_a["name"], "to_fiscal_year": fy_b and fy_b["name"],
         "periodicity": periodicity, "accumulated_values": 0,
         "include_default_book_entries": 1}
    return ctx.run(REPORTS["pl"], _with_dates(ctx, "pl", f, a, b))


def _with_dates(ctx, kind, f, a, b):
    """A version whose script names plain from_date / to_date gets them too."""
    names = ctx.options(REPORTS[kind])
    if "from_date" in names:
        f["from_date"] = str(a)
    if "to_date" in names:
        f["to_date"] = str(b)
    return f


def pl_figures(tree, col=None, amap=None) -> dict:
    income = tree.total(tree.roots("Income"), col)
    expense = tree.total(tree.roots("Expense"), col)
    cogs_nodes = tree.topmost(_cogs_pred, "Expense")
    has_cogs = bool(cogs_nodes) or any(v.get("account_type") == COGS for v in (amap or {}).values())
    cogs = tree.total(cogs_nodes, col)
    net = income - expense
    gross = income - cogs if has_cogs else None
    reported = tree.extra_value("profit", col, last=True)
    return {"income": income, "cogs": cogs if has_cogs else None, "gross_profit": gross,
            "expenses": expense, "other_expenses": expense - cogs,
            "net_profit": net, "gross_margin": _ratio(gross, income) if gross is not None else None,
            "net_margin": _ratio(net, income), "reported_net": reported,
            "has_cogs": has_cogs}


def _ratio(a, b):
    if a is None or b is None or not b or b <= 0:
        return None
    return a / b


def _pl(ctx, span):
    amap = ctx.accounts()
    p, c = span["period"], span["comparison"]
    getdate = frappe.utils.getdate
    main = _Tree(_pl_run(ctx, getdate(p["from"]), getdate(p["to"])), amap, ("Income", "Expense"))
    cmp_ = _Tree(_pl_run(ctx, getdate(c["from"]), getdate(c["to"])), amap, ("Income", "Expense"))
    fm, fc = pl_figures(main, amap=amap), pl_figures(cmp_, amap=amap)
    notes = []
    if not fm["has_cogs"]:
        notes.append("No account in the chart of accounts has the type Cost of Goods Sold, so "
                     "gross profit cannot be told apart from net profit. In ERPNext, open the "
                     "cost-of-sales accounts and set Account Type to Cost of Goods Sold.")
    if fm["reported_net"] is not None and abs(fm["reported_net"] - fm["net_profit"]) > 0.5:
        notes.append(f"ERPNext's own profit line says {fm['reported_net']:,.2f}, which is not "
                     f"income less expenses ({fm['net_profit']:,.2f}).")
    if not main.nodes:
        notes.append("Nothing was posted to income or expense accounts in this period.")
    summary = [
        _line("Revenue", fm["income"], fc["income"], bold=True, key="income"),
        _line("Cost of Goods Sold", fm["cogs"], fc["cogs"], key="cogs"),
        _line("Gross Profit", fm["gross_profit"], fc["gross_profit"], bold=True, key="gross_profit"),
        _line("Gross Margin", fm["gross_margin"], fc["gross_margin"], kind="pct", key="gross_margin"),
        _line("Operating and Other Expenses", fm["other_expenses"], fc["other_expenses"],
              key="other_expenses"),
        _line("Net Profit", fm["net_profit"], fc["net_profit"], bold=True, key="net_profit"),
        _line("Net Margin", fm["net_margin"], fc["net_margin"], kind="pct", key="net_margin"),
    ]
    rows = _merged_rows(ctx, main, cmp_, [("Income", "Total Income"), ("Expense", "Total Expenses")],
                        p["from"], p["to"])
    rows.append(_line("Net Profit", fm["net_profit"], fc["net_profit"], bold=True, kind="total"))
    return {"figures": fm, "compare_figures": fc, "summary": summary, "rows": rows,
            "notes": notes,
            "columns": [p["span"], c["span"]]}


def _trend(ctx):
    """Twelve months to date, one column a month, from one run of the report."""
    getdate = frappe.utils.getdate
    today = getdate(_today())
    months = []
    d = today.replace(day=1)
    for _ in range(12):
        months.insert(0, d)
        d = (d - dt.timedelta(days=1)).replace(day=1)
    amap = ctx.accounts()
    tree = _Tree(_pl_run(ctx, months[0], today, "Monthly"), amap, ("Income", "Expense"))
    out = []
    for i, col in enumerate(tree.cols):
        f = pl_figures(tree, col["key"], amap)
        start = months[i] if i < len(months) and len(tree.cols) == len(months) else None
        out.append({"label": col["label"], "from": str(start) if start else None,
                    "to": str(min(frappe.utils.get_last_day(start), today)) if start else None,
                    "revenue": f["income"], "gross_profit": f["gross_profit"],
                    "net_profit": f["net_profit"], "net_margin": f["net_margin"],
                    "gross_margin": f["gross_margin"]})
    return out


def _glance(ctx, trend):
    """This month, last month, year to date and the same period last year."""
    getdate = frappe.utils.getdate
    today = getdate(_today())
    fy = ctx.fiscal_year(today)
    start = getdate(fy["start"]) if fy else dt.date(today.year, 1, 1)
    amap = ctx.accounts()
    ytd = pl_figures(_Tree(_pl_run(ctx, start, today), amap, ("Income", "Expense")), amap=amap)
    ly = pl_figures(_Tree(_pl_run(ctx, _shift_year(start, -1), _shift_year(today, -1)), amap,
                          ("Income", "Expense")), amap=amap)

    def month(i):
        if len(trend) < i:
            return None
        t = trend[-i]
        return {"income": t["revenue"], "gross_profit": t["gross_profit"],
                "gross_margin": t["gross_margin"], "net_profit": t["net_profit"],
                "net_margin": t["net_margin"]}
    cols = [("This Month", month(1)), ("Last Month", month(2)), ("Year to Date", ytd),
            ("Same Period Last Year", ly)]
    rows = []
    for key, label, kind in (("income", "Revenue", "money"), ("gross_profit", "Gross Profit", "money"),
                             ("gross_margin", "Gross Margin", "pct"),
                             ("net_profit", "Net Profit", "money"), ("net_margin", "Net Margin", "pct")):
        rows.append({"label": label, "kind": kind, "bold": key in ("gross_profit", "net_profit"),
                     "values": [(f or {}).get(key) for _, f in cols]})
    last = today.replace(day=1) - dt.timedelta(days=1)
    return {"columns": [c for c, _ in cols], "rows": rows,
            "spans": [_span(today.replace(day=1), today), _span(last.replace(day=1), last),
                      _span(start, today), _span(_shift_year(start, -1), _shift_year(today, -1))]}


# --------------------------------------------------------------------------- balance sheet
def _bs_run(ctx, at, compare):
    getdate = frappe.utils.getdate
    a = getdate(compare).replace(day=1)
    b = getdate(at)
    fy_a, fy_b = ctx.fiscal_year(a), ctx.fiscal_year(b)
    f = {"company": ctx.company, "filter_based_on": "Date Range",
         "period_start_date": str(a), "period_end_date": str(b),
         "from_fiscal_year": fy_a and fy_a["name"], "to_fiscal_year": fy_b and fy_b["name"],
         "periodicity": "Monthly", "accumulated_values": 1, "include_default_book_entries": 1}
    return ctx.run(REPORTS["bs"], _with_dates(ctx, "bs", f, a, b))


def _classify(tree, n, kind):
    """current / fixed / other (assets), current / long_term / other (liabilities)."""
    name = n["name"].lower()
    t = n["account_type"]
    if re.search(r"non[\s-]*current", name):
        return None  # look inside
    if kind == "asset":
        if "current" in name or t in CURRENT_ASSET_TYPES:
            return "current"
        if "fixed" in name or t in FIXED_ASSET_TYPES:
            return "fixed"
    else:
        if "current" in name or t in CURRENT_LIABILITY_TYPES:
            return "current"
        if re.search(r"long[\s-]*term", name):
            return "long_term"
    return None


def _buckets(tree, root_type, kind):
    """Each top branch of a balance-sheet side, in a bucket. A root group or a
    "non-current" group whose own name says nothing is looked inside."""
    out = []
    children = {}
    for n in tree.nodes:
        children.setdefault(n["parent"], []).append(n)

    def walk(n, look_inside):
        b = _classify(tree, n, kind)
        if b:
            out.append((b, n))
            return
        kids = children.get(n["account"]) or []
        if kids and (look_inside or re.search(r"non[\s-]*current", n["name"].lower())):
            for k in kids:
                walk(k, False)
            return
        out.append(("other", n))
    for r in tree.roots(root_type):
        walk(r, True)
    return out


def bs_figures(tree, col) -> dict:
    assets = tree.total(tree.roots("Asset"), col)
    liabilities = tree.total(tree.roots("Liability"), col)
    equity = tree.total(tree.roots("Equity"), col)
    provisional = tree.extra_value("provisional", col)
    if provisional is None:
        # No provisional line (a year closed to equity): none to add.
        provisional = 0.0
    a = {"current": 0.0, "fixed": 0.0, "other": 0.0}
    for b, n in _buckets(tree, "Asset", "asset"):
        a[b] += tree.value(n, col)
    li = {"current": 0.0, "long_term": 0.0, "other": 0.0}
    for b, n in _buckets(tree, "Liability", "liability"):
        li[b] += tree.value(n, col)
    stock = tree.total(tree.topmost(lambda n: n["account_type"] == "Stock", "Asset"), col)
    cash = tree.total(tree.topmost(lambda n: n["account_type"] in CASH_TYPES, "Asset"), col)
    diff = assets - (liabilities + equity + provisional)
    return {"assets": assets, "current_assets": a["current"], "fixed_assets": a["fixed"],
            "other_assets": a["other"], "liabilities": liabilities,
            "current_liabilities": li["current"], "long_term_liabilities": li["long_term"],
            "other_liabilities": li["other"], "equity": equity, "provisional_profit": provisional,
            "total_equity": equity + provisional, "inventory": stock, "cash": cash,
            "difference": diff, "balances": abs(diff) < 0.5}


def _bs(ctx, span):
    bd = span["balance_dates"]
    res = _bs_run(ctx, bd["at"], bd["compare"])
    amap = ctx.accounts()
    tree = _Tree(res, amap, ("Asset", "Liability", "Equity"))
    if not tree.nodes:
        raise Setup(_no_ledger_guide(ctx))
    cols = tree.cols
    main = cols[-1]["key"] if cols else None
    cmpk = cols[-2]["key"] if len(cols) > 1 else None
    fm = bs_figures(tree, main)
    fc = bs_figures(tree, cmpk) if cmpk else None
    notes = []
    if res.get("message"):
        notes.append("ERPNext says: " + re.sub(r"<[^>]+>", "", str(res["message"])).strip())
    if not fm["balances"]:
        notes.append(f"ERPNext's balance sheet does not balance: assets are "
                     f"{fm['difference']:,.2f} {'more' if fm['difference'] > 0 else 'less'} than "
                     f"liabilities, equity and the provisional profit together. The usual cause "
                     f"is an opening balance posted to one side only; ERPNext's Trial Balance "
                     f"shows where.")
    if fm["provisional_profit"] and abs(fm["provisional_profit"]) > 0.5:
        notes.append("Provisional profit or loss is the profit or loss not yet closed into "
                     "equity with a Period Closing Voucher, as ERPNext's balance sheet shows it.")
    g = lambda k: (fm.get(k), fc.get(k) if fc else None)  # noqa: E731
    summary = [
        _line("Current Assets", *g("current_assets"), key="current_assets"),
        _line("Fixed Assets", *g("fixed_assets"), key="fixed_assets"),
        _line("Other Assets", *g("other_assets"), key="other_assets"),
        _line("Total Assets", *g("assets"), bold=True, key="assets"),
        _line("Current Liabilities", *g("current_liabilities"), key="current_liabilities"),
        _line("Long-Term Liabilities", *g("long_term_liabilities"), key="long_term_liabilities"),
        _line("Other Liabilities", *g("other_liabilities"), key="other_liabilities"),
        _line("Total Liabilities", *g("liabilities"), bold=True, key="liabilities"),
        _line("Equity", *g("equity"), key="equity"),
        _line("Provisional Profit or Loss", *g("provisional_profit"), key="provisional_profit"),
        _line("Total Equity", *g("total_equity"), bold=True, key="total_equity"),
        _line("Liabilities and Equity", fm["liabilities"] + fm["total_equity"],
              (fc["liabilities"] + fc["total_equity"]) if fc else None, bold=True, key="l_and_e"),
        _line("Difference", fm["difference"], fc["difference"] if fc else None, key="difference",
              tone=None if fm["balances"] else "bad"),
    ]
    summary = [s for s in summary if not (s["key"] in ("other_assets", "other_liabilities",
                                                      "long_term_liabilities", "provisional_profit")
                                          and not s["values"][0] and not s["values"][1])]
    fy = ctx.fiscal_year(bd["at"])
    rows = _merged_rows(ctx, tree, None, [("Asset", "Total Assets"), ("Liability", "Total Liabilities"),
                                          ("Equity", "Total Equity")],
                        fy["start"] if fy else bd["at"][:4] + "-01-01", bd["at"], cols=(main, cmpk))
    if fm["provisional_profit"] or (fc and fc["provisional_profit"]):
        rows.append(_line("Provisional Profit or Loss", fm["provisional_profit"],
                          fc["provisional_profit"] if fc else None, kind="total"))
    return {"figures": fm, "compare_figures": fc, "summary": summary, "rows": rows,
            "notes": notes, "columns": [f"As at {_pretty(bd['at'])}",
                                        f"As at {_pretty(bd['compare'])}" if cmpk else ""]}


# --------------------------------------------------------------------------- the ratios
RATIO_MEANING = {
    "current_ratio": "What the business owns that turns into cash within a year, for every "
                     "unit it must pay within a year.",
    "quick_ratio": "The same, leaving out stock, which takes longest to turn into cash.",
    "gross_margin": "Of every unit of revenue, what is left after the cost of the goods sold.",
    "net_margin": "Of every unit of revenue, what is left after every cost.",
    "debt_to_equity": "What the business owes for every unit the owners have in it.",
    "working_capital": "Short-term assets less short-term debts: the cushion that pays the "
                       "bills.",
}


def ratios(pl: dict, bs: dict) -> list[dict]:
    out = []

    def add(key, label, value, kind, reading):
        out.append({"key": key, "label": label, "value": value, "kind": kind,
                    "meaning": RATIO_MEANING[key], "reading": reading})
    ca, cl = bs["current_assets"], bs["current_liabilities"]
    cur = ca / cl if cl > 0 else None
    add("current_ratio", "Current Ratio", cur, "ratio",
        "Cannot be worked out: no current liabilities are recorded." if cur is None else
        "Below 1: more falls due within a year than the business has coming in to meet it."
        if cur < 1 else "Between 1 and 1.5: short-term debts are covered, thinly."
        if cur < 1.5 else "Short-term debts are covered with room to spare.")
    quick = (ca - bs["inventory"]) / cl if cl > 0 else None
    add("quick_ratio", "Quick Ratio", quick, "ratio",
        "Cannot be worked out: no current liabilities are recorded." if quick is None else
        "Below 1: without selling stock, short-term debts could not all be met."
        if quick < 1 else "Short-term debts could be met without selling stock.")
    gm = pl.get("gross_margin")
    add("gross_margin", "Gross Margin", gm, "pct",
        "Cannot be worked out: " + ("no revenue in the period." if not pl.get("income") or
                                    pl["income"] <= 0 else "no Cost of Goods Sold account is set up.")
        if gm is None else "Goods are sold for less than they cost." if gm < 0 else
        f"{gm * 100:.1f} of every 100 of revenue is left after the cost of goods.")
    nm = pl.get("net_margin")
    add("net_margin", "Net Margin", nm, "pct",
        "Cannot be worked out: no revenue in the period." if nm is None else
        "A loss: costs are more than revenue." if nm < 0 else
        f"{nm * 100:.1f} of every 100 of revenue is profit.")
    eq = bs["total_equity"]
    de = bs["liabilities"] / eq if eq > 0 else None
    add("debt_to_equity", "Debt to Equity", de, "ratio",
        ("Cannot be worked out: equity is negative -- the business owes more than it owns."
         if eq < 0 else "Cannot be worked out: no equity is recorded.") if de is None else
        "Above 2: the business runs mostly on borrowing and credit." if de > 2 else
        "Owners' money and borrowing are in balance." if de >= 0.5 else
        "Mostly financed by the owners.")
    wc = ca - cl
    add("working_capital", "Working Capital", wc, "money",
        "Negative: short-term debts are more than short-term assets." if wc < 0 else
        "Positive: short-term assets more than cover short-term debts.")
    return out


# --------------------------------------------------------------------------- summary
def _summary(ctx, span):
    pl = _pl(ctx, span)
    bs = _bs(ctx, span)
    trend = _trend(ctx)
    glance = _glance(ctx, trend)
    fm, fc = pl["figures"], pl["compare_figures"]
    bm, bc = bs["figures"], bs["compare_figures"] or {}
    cur_now = bm["current_assets"] / bm["current_liabilities"] if bm["current_liabilities"] > 0 else None
    cur_then = (bc["current_assets"] / bc["current_liabilities"]
                if bc and bc.get("current_liabilities", 0) > 0 else None)
    cards = {
        "revenue": _card(fm["income"], fc["income"]),
        "gross_profit": {**_card(fm["gross_profit"], fc["gross_profit"]), "margin": fm["gross_margin"]},
        "net_profit": {**_card(fm["net_profit"], fc["net_profit"]), "margin": fm["net_margin"]},
        "cash": {**_card(bm["cash"], bc.get("cash")), "as_at": span["balance_dates"]["at"]},
        "current_ratio": {"value": cur_now, "compare": cur_then},
    }
    return {"cards": cards, "pl": {**pl, "glance": glance, "trend": trend}, "bs": bs,
            "ratios": ratios(fm, bm)}


def _card(v, c):
    return {"value": v, "compare": c, "change_pct": _change_pct(v, c)}


def _change_pct(v, c):
    if v is None or c is None or not c:
        return None
    return (v - c) / abs(c)


# --------------------------------------------------------------------------- trial balance
def _trial_balance(ctx, span):
    getdate = frappe.utils.getdate
    a, b = getdate(span["period"]["from"]), getdate(span["period"]["to"])
    fy = ctx.fiscal_year(a, required=True)
    notes = []
    if str(b) > fy["end"]:
        notes.append(f"A trial balance covers one fiscal year at a time, so this one runs to "
                     f"the end of fiscal year {fy['name']} ({_pretty(fy['end'])}).")
        b = getdate(fy["end"])
    # Every name a version has used for its period-closing and earlier-years options:
    # a version ignores the ones it does not know. The script says which this site has.
    names = ctx.options(REPORTS["tb"])
    f = {"company": ctx.company, "fiscal_year": fy["name"], "from_date": str(a), "to_date": str(b),
         **TB_OPTIONS}
    res = ctx.run(REPORTS["tb"], f)
    amap = ctx.accounts()
    rows, total = [], None
    for r in res.get("result") or []:
        if _is_account(r, amap):
            rows.append({"name": _label(r), "account": r["account"], "indent": int(r.get("indent") or 0),
                         "kind": "group" if (amap.get(r["account"], {}).get("is_group") if amap
                                             else r.get("is_group")) else "account",
                         "values": [_num(r.get(k)) for k in TB_COLUMNS],
                         "drill": _gl(ctx, r["account"], a, b)})
        elif isinstance(r, dict) and r and any(isinstance(r.get(k), (int, float)) for k in TB_COLUMNS):
            total = [_num(r.get(k)) for k in TB_COLUMNS]
    if not rows:
        raise Setup(_no_ledger_guide(ctx))
    if total is None:  # no total row: the roots add up to it
        roots = [r for r in rows if r["indent"] == 0]
        total = [sum(r["values"][i] for r in roots) for i in range(len(TB_COLUMNS))]
    diffs = {"opening": total[0] - total[1], "period": total[2] - total[3],
             "closing": total[4] - total[5]}
    balanced = all(abs(v) < 0.5 for v in diffs.values())
    if not balanced:
        parts = [f"{k} by {abs(v):,.2f}" for k, v in diffs.items() if abs(v) >= 0.5]
        notes.append("ERPNext's trial balance does not balance: debits and credits differ in the "
                     + ", ".join(parts) + ". Open it in ERPNext to find the account that causes it.")
    if "show_unclosed_fy_pl_balances" in names:
        notes.append("Profit and loss of earlier years not yet closed with a Period Closing "
                     "Voucher is in the opening columns (ERPNext's own option for it), so they "
                     "add up.")
    return {"tb": {"columns": ["Opening (Dr)", "Opening (Cr)", "Debit", "Credit", "Closing (Dr)",
                               "Closing (Cr)"], "rows": rows, "total": total,
                   "differences": diffs, "balanced": balanced, "fiscal_year": fy["name"],
                   "from": str(a), "to": str(b), "notes": notes}}


# --------------------------------------------------------------------------- cash flow
def _cf_run(ctx, a, b):
    fy_a, fy_b = ctx.fiscal_year(a), ctx.fiscal_year(b)
    f = {"company": ctx.company, "filter_based_on": "Date Range",
         "period_start_date": str(a), "period_end_date": str(b),
         "from_fiscal_year": fy_a and fy_a["name"], "to_fiscal_year": fy_b and fy_b["name"],
         "periodicity": "Yearly", "accumulated_values": 0, "include_default_book_entries": 1}
    return ctx.run(REPORTS["cf"], _with_dates(ctx, "cf", f, a, b))


SECTION_WORDS = (("operating", "operat"), ("investing", "invest"), ("financing", "financ"))
SECTION_LABELS = {"operating": "Operating Activities", "investing": "Investing Activities",
                  "financing": "Financing Activities"}


def cf_parse(res) -> dict:
    """ERPNext's cash flow, by section. Its own "total" key is not used: on a mapped
    cash flow it is not the sum of the periods (Gigmann's, 15 Nov 2026). The periods are
    added up instead."""
    cols = _cols(res)
    rows = [r for r in (res.get("result") or []) if isinstance(r, dict) and r]

    def val(r):
        return sum(_num(r.get(c["key"])) for c in cols)

    def valued(r):
        return any(isinstance(r.get(c["key"]), (int, float)) for c in cols)

    def quoted(r):
        return str(r.get("account_name") or r.get("account") or "").startswith("'")

    sections, order, cur = {}, [], None
    nets = []
    for r in rows:
        label = _label(r)
        top = r.get("indent") in (0, None) and not r.get("parent_account")
        if top and not valued(r) and not quoted(r):
            kind = next((k for k, w in SECTION_WORDS if w in label.lower()), None)
            if kind is None or kind in sections:
                kind = next((k for k, _ in SECTION_WORDS if k not in sections), f"s{len(order)}")
            cur = {"kind": kind, "label": label, "lines": [], "net": None}
            sections[kind] = cur
            order.append(kind)
            continue
        if not valued(r):
            if cur is not None and label:
                cur["lines"].append({"label": label, "value": None, "kind": "heading"})
            continue
        if top and quoted(r):
            nets.append((cur, label, val(r)))
            if cur is not None and cur["net"] is None:
                cur["net"] = val(r)
                cur["net_label"] = label
                cur = None
            continue
        if cur is not None:
            cur["lines"].append({"label": label, "value": val(r),
                                 "kind": "subtotal" if quoted(r) else "line"})
    net_change = None
    named = [n for n in nets if "change" in n[1].lower()]
    if named:
        net_change = named[-1][2]
    elif nets and len(nets) > len(order):
        net_change = nets[-1][2]
    total = sum((s["net"] or 0.0) for s in sections.values())
    if net_change is None and sections:
        net_change = total
    return {"sections": [sections[k] for k in order], "net_change": net_change,
            "sum_of_sections": total}


def _cash_flow(ctx, span):
    getdate = frappe.utils.getdate
    p, c = span["period"], span["comparison"]
    main = cf_parse(_cf_run(ctx, getdate(p["from"]), getdate(p["to"])))
    cmp_ = cf_parse(_cf_run(ctx, getdate(c["from"]), getdate(c["to"])))
    if not main["sections"]:
        from command_center.guides import guide
        raise Setup(guide(ctx.code, f"{ctx.name}'s ERPNext returned no cash flow for this period.", [
            "In ERPNext, open the Cash Flow report for the same dates to see what it says.",
            "If the business uses a Cash Flow Mapping, check each mapping names its accounts."],
            f"/app/query-report/{quote(REPORTS['cf'])}"))
    before = {s["kind"]: s for s in cmp_["sections"]}
    rows = []
    for s in main["sections"]:
        old = before.get(s["kind"], {})
        old_lines = {ln["label"]: ln["value"] for ln in old.get("lines", [])}
        rows.append({"name": s["label"], "kind": "heading", "indent": 0, "values": [None, None]})
        for ln in s["lines"]:
            rows.append({"name": ln["label"], "indent": 1,
                         "kind": {"heading": "heading", "subtotal": "group"}.get(ln["kind"], "account"),
                         "values": [ln["value"], old_lines.get(ln["label"])]})
        rows.append({"name": s.get("net_label") or f"Net Cash from {SECTION_LABELS.get(s['kind'], '')}",
                     "indent": 0, "kind": "total", "values": [s["net"], old.get("net")]})
    rows.append({"name": "Net Change in Cash", "indent": 0, "kind": "total",
                 "values": [main["net_change"], cmp_["net_change"]]})
    notes = []
    if main["net_change"] is not None and abs(main["net_change"] - main["sum_of_sections"]) > 0.5:
        notes.append(f"ERPNext's net change in cash ({main['net_change']:,.2f}) is not the sum of "
                     f"its three sections ({main['sum_of_sections']:,.2f}).")
    summary = []
    for kind in ("operating", "investing", "financing"):
        s = next((x for x in main["sections"] if x["kind"] == kind), None)
        o = before.get(kind)
        summary.append(_line(SECTION_LABELS[kind], s and s["net"], o and o["net"], key=kind))
    summary.append(_line("Net Change in Cash", main["net_change"], cmp_["net_change"], bold=True,
                         key="net_change"))
    return {"cf": {"summary": summary, "rows": rows, "notes": notes,
                   "columns": [p["span"], c["span"]]}}


# --------------------------------------------------------------------------- shared rows
def _line(label, value, compare=None, bold=False, kind="money", key=None, tone=None):
    is_pct = kind == "pct"
    change = None if value is None or compare is None else value - compare
    return {"label": label, "name": label, "key": key or label, "kind": "pct" if is_pct else
            ("total" if bold and kind == "money" else kind), "bold": bold,
            "values": [value, compare], "change": change,
            "change_pct": None if is_pct else _change_pct(value, compare), "tone": tone}


def _merged_rows(ctx, main, other, sections, a, b, cols=(None, None)):
    """The account tree of `main` with the comparison's figure beside each account.
    An account only the comparison has is placed under its parent. `cols` names the
    columns of `main` to show when both figures come from one run (the balance sheet)."""
    getdate = frappe.utils.getdate
    out = []
    for root_type, total_label in sections:
        nodes = [n for n in main.nodes if n["root_type"] == root_type]
        theirs = [n for n in other.nodes if n["root_type"] == root_type] if other else []
        have = {n["account"] for n in nodes}
        merged = list(nodes)
        for n in theirs:
            if n["account"] in have:
                continue
            at = len(merged)
            for i, m in enumerate(merged):
                if m["account"] == n["parent"]:
                    at = i + 1
                    while at < len(merged) and merged[at]["indent"] > m["indent"]:
                        at += 1
            merged.insert(at, {**n, "values": {}, "only_other": True})
            have.add(n["account"])
        oth = {n["account"]: n for n in theirs}
        for n in merged:
            if other is not None:
                v = None if n.get("only_other") else main.value(n)
                c = other.value(oth[n["account"]]) if n["account"] in oth else None
            else:
                v = main.value(n, cols[0]) if cols[0] else None
                c = main.value(n, cols[1]) if cols[1] else None
            out.append({"name": n["name"], "account": n["account"], "indent": n["indent"],
                        "kind": "group" if n["is_group"] else "account", "values": [v, c],
                        "drill": _gl(ctx, n["account"], getdate(a), getdate(b))})
        if nodes or theirs:
            v = main.total(main.roots(root_type), cols[0]) if other is None else main.total(main.roots(root_type))
            c = (main.total(main.roots(root_type), cols[1]) if cols[1] else None) if other is None \
                else other.total(other.roots(root_type))
            out.append({"name": total_label, "indent": 0, "kind": "total", "values": [v, c]})
    return out


def _gl(ctx, account, a, b) -> str:
    """The General Ledger for one account on the business's own ERPNext."""
    q = urlencode({"company": ctx.company, "account": account, "from_date": str(a),
                   "to_date": str(b)}, quote_via=quote)
    return f"{ctx.site()}/app/query-report/{quote('General Ledger')}?{q}"


# --------------------------------------------------------------------------- the PDF
def pdf_body(parts: dict) -> str:
    """The statements as HTML for the PDF: every text escaped, figures formatted here."""
    from frappe.utils import escape_html as esc
    s = parts["summary"]
    cur = s.get("currency") or ""
    out = [f'<p class="lead">{esc(s["period"]["label"])}: {esc(s["period"]["span"])}, compared with '
           f'{esc(s["comparison"]["span"])}. Amounts in {esc(cur)}. Balance sheet as at '
           f'{esc(_pretty(s["balance_dates"]["at"]))}.</p>']

    def table(title, heads, rows, note=None):
        h = "".join(f'<th class="n">{esc(x)}</th>' if i else f"<th>{esc(x)}</th>"
                    for i, x in enumerate(heads))
        body = []
        for r in rows:
            pad = 10 * int(r.get("indent") or 0)
            strong = r.get("bold") or r.get("kind") in ("total", "group", "heading")
            name = esc(r.get("name") or r.get("label") or "")
            cells = [f'<td style="padding-left:{8 + pad}px">{"<b>" + name + "</b>" if strong else name}</td>']
            for v in r.get("values") or []:
                txt = _fmt(v, r.get("kind"))
                cells.append(f'<td class="n">{"<b>" + txt + "</b>" if strong else txt}</td>')
            body.append("<tr>" + "".join(cells) + "</tr>")
        notes = "".join(f"<p>{esc(n)}</p>" for n in (note or []))
        return f"<h2>{esc(title)}</h2><table><tr>{h}</tr>{''.join(body)}</table>{notes}"

    if s.get("state") == "ok":
        pl, bs = s["pl"], s["bs"]
        out.append(table("Profit and Loss", ["", *pl["columns"]], pl["summary"], pl["notes"]))
        out.append(table("Profit and Loss by Account", ["Account", *pl["columns"]], pl["rows"]))
        out.append(table("Balance Sheet", ["", *bs["columns"]], bs["summary"], bs["notes"]))
        out.append(table("Balance Sheet by Account", ["Account", *bs["columns"]], bs["rows"]))
        ratio_rows = "".join(
            f'<tr><td><b>{esc(r["label"])}</b></td><td class="n">{_fmt(r["value"], r["kind"])}</td>'
            f'<td>{esc(r["meaning"])} {esc(r["reading"])}</td></tr>' for r in s["ratios"])
        out.append("<h2>Key Ratios</h2><table><tr><th>Ratio</th><th class=\"n\">Value</th>"
                   f"<th>What It Means</th></tr>{ratio_rows}</table>")
    cf = parts.get("cf") or {}
    if cf.get("state") == "ok":
        out.append(table("Cash Flow", ["", *cf["cf"]["columns"]], cf["cf"]["rows"], cf["cf"]["notes"]))
    tb = parts.get("tb") or {}
    if tb.get("state") == "ok":
        t = tb["tb"]
        rows = t["rows"] + [{"name": "Total", "kind": "total", "values": t["total"]}]
        out.append(table(f"Trial Balance, {_pretty(t['from'])} to {_pretty(t['to'])}",
                         ["Account", *t["columns"]], rows, t["notes"]))
    return "".join(out)


def _fmt(v, kind=None) -> str:
    if v is None:
        return "—"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "ratio":
        return f"{v:.2f}"
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


# --------------------------------------------------------------------------- small things
def _today() -> str:
    return str(frappe.utils.today())


def _digest(parts) -> str:
    return hashlib.md5(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def _pretty(d) -> str:
    try:
        return frappe.utils.getdate(d).strftime("%-d %b %Y")
    except Exception:
        return str(d)


def _span(a, b) -> str:
    return f"{_pretty(a)} to {_pretty(b)}"
