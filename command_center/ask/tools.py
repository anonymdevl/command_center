"""What the analyst may look at -- and the reason it can change nothing.

Decision on record (Michael, 18 Oct 2026): Gemini is used to its full capacity for
anything informational -- it reads the figures and records it needs, reasons over them,
explains, compares, projects and advises -- and it may never create, update, submit,
cancel or delete anything in ERPNext, with or without anyone's approval.

That second half is enforced by construction, not by instruction:

  * The model can call only the functions in TOOLS. There is no generic "call a
    method" tool, so it cannot reach anything else.
  * Every function here reads. Fact queries go through frappe.qb SELECTs; ERPNext
    documents go through frappe.client.get / get_list / get_count, Frappe's own
    permission-checked read endpoints. Preflight fails the build if this file or
    agent.py ever contains a write call.
  * agent.py rolls back any database write made while a question is being answered,
    and records that it happened.

Reads are scoped to the person asking, which is requirement AI-00 (the assistant has
the same authority as the human using it): ERPNext documents through that user's own
permissions, so a sales manager's question cannot reach payroll. The fact tables are
management-only and require_manager() has already run before anything here does.
Doctypes that hold credentials are refused outright, whatever the user may read.
"""

from __future__ import annotations

import datetime
import decimal
import json

import frappe
from frappe.query_builder.functions import Avg, Count, Max, Min, Sum
from pypika import CustomFunction, Order

from command_center.facts.schema import DIMENSIONS, FACTS, MEASURES, OPERATORS, condition

# Things no answer needs and no prompt should be able to reach. Password fields are
# never returned by frappe.client.get, but some of these hold tokens and secrets in
# ordinary fields, and our own credential store is one of them.
DENIED_DOCTYPES = {
    # Ours: API keys and secrets for every connected site.
    "Command Center Site Credential", "Connected Business",
    "Command Center Ingest State", "Command Center Change Event",
    "Social Login Key", "OAuth Client", "OAuth Bearer Token", "OAuth Authorization Code",
    "Connected App", "Token Cache", "User Social Login", "Email Account", "Webhook",
    "Integration Request", "System Settings", "Payment Gateway Account",
}

MAX_ROWS = 50          # records handed to the model in one call
MAX_GROUPS = 200       # grouped rows in one call
MAX_TEXT = 600         # characters of any one field value

FUNCS = {"sum": Sum, "count": Count, "avg": Avg, "min": Min, "max": Max}
_DATE_FORMAT = CustomFunction("DATE_FORMAT", ["d", "f"])
_PERIOD_FORMAT = {"day": "%Y-%m-%d", "week": "%x-W%v", "month": "%Y-%m", "year": "%Y"}


class ToolError(Exception):
    """A request the tool will not run. The message goes back to the model."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, datetime.timedelta):
        return str(v)
    if isinstance(v, str) and len(v) > MAX_TEXT:
        return v[:MAX_TEXT] + "…"
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def _fact_doctype(fact: str) -> str:
    doctype = FACTS.get(fact)
    if not doctype:
        raise ToolError(f"Unknown data set {fact!r}. Known: {', '.join(FACTS)}")
    return doctype


def _columns(doctype: str) -> set:
    meta = frappe.get_meta(doctype)
    return {f.fieldname for f in meta.fields if f.fieldname} | {"name", "creation", "modified"}


def _check_column(fact: str, column: str) -> str:
    if column not in _columns(_fact_doctype(fact)):
        raise ToolError(f"{fact} has no column {column!r}. Use describe_data to see its columns.")
    return column


def _filters(fact: str, filters) -> dict:
    """[{column, op, value | values}] -> the {column: rule} shape facts.schema reads."""
    out = {}
    for f in filters or []:
        col = _check_column(fact, f.get("column", ""))
        op = (f.get("op") or "=").strip().lower()
        if op not in OPERATORS:
            raise ToolError(f"Unknown operator {op!r}. Use one of {', '.join(OPERATORS)}")
        val = f.get("values") if op in ("in", "not in") else f.get("value")
        out[col] = [op, val]
    return out


def _scope(fact: str, filters: dict, business_code) -> dict:
    if business_code and business_code != "__all__" and "business_code" in _columns(FACTS[fact]):
        filters = {**filters, "business_code": business_code}
    return filters


def _doctype_allowed(doctype: str) -> str:
    if not doctype or not frappe.db.exists("DocType", doctype):
        raise ToolError(f"There is no ERPNext doctype called {doctype!r}.")
    if doctype in DENIED_DOCTYPES:
        raise ToolError(f"{doctype} holds credentials or system configuration and is not "
                        f"available to the assistant.")
    if not frappe.has_permission(doctype, "read"):
        raise ToolError(f"The person asking does not have read access to {doctype}.")
    return doctype


def _erp_filters(filters) -> list:
    out = []
    for f in filters or []:
        op = (f.get("op") or "=").strip().lower()
        if op not in OPERATORS + ("between", "is"):
            raise ToolError(f"Unknown operator {op!r}")
        val = f.get("values") if op in ("in", "not in", "between") else f.get("value")
        out.append([f.get("column"), op, val])
    return out


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------
def describe_data(business_code=None, fact: str | None = None):
    """The loaded data sets, their columns, and how fresh each one is."""
    from command_center.kpi.engine import _load_state  # same freshness the cards report

    facts = [fact] if fact else list(FACTS)
    out = []
    for f in facts:
        doctype = _fact_doctype(f)
        meta = frappe.get_meta(doctype)
        state = _load_state(f, business_code) or {}
        out.append({
            "data_set": f,
            "rows": frappe.db.count(doctype, _scope(f, {}, business_code) or None),
            "as_of": str(state.get("as_of_date") or ""),
            "breakdowns": DIMENSIONS.get(f, []),
            "amounts": MEASURES.get(f, []),
            "dates": [x.fieldname for x in meta.fields if x.fieldtype in ("Date", "Datetime")
                      and x.fieldname not in ("src_modified", "ingested_at")],
            "columns": {x.fieldname: f"{x.label} ({x.fieldtype})" for x in meta.fields
                        if x.fieldname and x.fieldtype not in ("Section Break", "Column Break",
                                                                "Tab Break")},
        })
    return out


def query_data(fact: str, measures=None, group_by=None, period: str | None = None,
               date_column: str | None = None, date_from: str | None = None,
               date_to: str | None = None, filters=None, order: str = "desc",
               limit: int = 50, business_code=None):
    """Totals, breakdowns and time series over one loaded data set."""
    doctype = _fact_doctype(fact)
    t = frappe.qb.DocType(doctype)
    rules = _scope(fact, _filters(fact, filters), business_code)

    if (period or date_from or date_to) and not date_column:
        raise ToolError("A period or a date range needs a date_column.")
    if date_column:
        _check_column(fact, date_column)

    q = frappe.qb.from_(t)
    for col, rule in rules.items():
        q = q.where(condition(t[col], rule))
    if date_from:
        q = q.where(t[date_column] >= date_from)
    if date_to:
        q = q.where(t[date_column] <= date_to)

    groups = []
    if period:
        if period == "quarter":
            pc = CustomFunction("CONCAT", ["a", "b", "c"])(
                CustomFunction("YEAR", ["d"])(t[date_column]), "-Q",
                CustomFunction("QUARTER", ["d"])(t[date_column]))
        elif period in _PERIOD_FORMAT:
            pc = _DATE_FORMAT(t[date_column], _PERIOD_FORMAT[period])
        else:
            raise ToolError("period must be day, week, month, quarter or year")
        q = q.select(pc.as_("period")).groupby(pc)
        groups.append("period")
    for g in (group_by or [])[:2]:
        _check_column(fact, g)
        q = q.select(t[g]).groupby(t[g])
        groups.append(g)

    aliases = []
    for m in measures or [{"function": "count", "column": "name"}]:
        fn = (m.get("function") or "sum").lower()
        if fn not in FUNCS:
            raise ToolError(f"function must be one of {', '.join(FUNCS)}")
        col = _check_column(fact, m.get("column") or "name")
        alias = f"{fn}_{col}"
        q = q.select((FUNCS[fn](t[col]) if fn != "count" else Count(t[col])).as_(alias))
        aliases.append(alias)

    if groups:
        if period and not group_by:
            q = q.orderby("period", order=Order.asc)
        else:
            q = q.orderby(aliases[0], order=Order.asc if order == "asc" else Order.desc)
        q = q.limit(min(int(limit or 50), MAX_GROUPS))
    rows = [_clean(dict(r)) for r in q.run(as_dict=True)]
    return {"data_set": fact, "filters": rules, "rows": rows, "row_count": len(rows),
            "capped": bool(groups) and len(rows) >= min(int(limit or 50), MAX_GROUPS)}


def list_records(fact: str, columns=None, filters=None, order_by: str | None = None,
                 descending: bool = True, limit: int = 20, business_code=None):
    """Individual rows of a loaded data set, each with the ERPNext document it came from."""
    doctype = _fact_doctype(fact)
    cols = [_check_column(fact, c) for c in (columns or [])][:20]
    cols = list(dict.fromkeys(cols + ["src_doctype", "src_name"]))
    rules = _scope(fact, _filters(fact, filters), business_code)
    t = frappe.qb.DocType(doctype)
    q = frappe.qb.from_(t).select(*[t[c] for c in cols])
    for col, rule in rules.items():
        q = q.where(condition(t[col], rule))
    if order_by:
        q = q.orderby(t[_check_column(fact, order_by)],
                      order=Order.desc if descending else Order.asc)
    rows = [_clean(dict(r)) for r in q.limit(min(int(limit or 20), MAX_ROWS)).run(as_dict=True)]
    for r in rows:
        if r.get("src_doctype") and r.get("src_name"):
            r["open_url"] = frappe.utils.get_url_to_form(r["src_doctype"], str(r["src_name"]))
    return {"data_set": fact, "filters": rules, "rows": rows}


def get_figures(keys, business_code=None):
    """The platform's own defined figures -- the same numbers the cards show."""
    from command_center.kpi.engine import evaluate_set
    from command_center.kpi.registry import load_all

    known = load_all()
    unknown = [k for k in keys or [] if k not in known]
    if unknown:
        raise ToolError(f"Unknown figure(s) {', '.join(unknown)}. Known: {', '.join(sorted(known))}")
    return _clean(evaluate_set(list(keys), business_code))


def find(text: str, business_code=None):
    """Customers, suppliers, items and warehouses whose names match the text."""
    from command_center.ask import resolve
    return _clean(resolve.resolve(text, business_code)[:10])


def trend(fact: str, measure: str, function: str = "sum", date_column: str | None = None,
          period: str = "month", periods: int = 12, project_ahead: int = 3,
          filters=None, business_code=None):
    """A time series, its direction, and a straight-line projection."""
    if not date_column:
        raise ToolError("trend needs a date_column.")
    res = query_data(fact, measures=[{"function": function, "column": measure}],
                     period=period, date_column=date_column, filters=filters,
                     limit=MAX_GROUPS, business_code=business_code)
    alias = f"{function}_{measure}"
    series = [{"period": r["period"], "value": float(r.get(alias) or 0)}
              for r in res["rows"] if r.get("period")][-max(2, min(int(periods), 60)):]
    out = {"data_set": fact, "measure": alias, "period": period, "series": series}
    n = len(series)
    if n < 3:
        out["note"] = "Too few periods to describe a trend."
        return out
    xs, ys = list(range(n)), [p["value"] for p in series]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    icpt = my - slope * mx
    resid = [y - (icpt + slope * x) for x, y in zip(xs, ys)]
    spread = (sum(r * r for r in resid) / max(1, n - 2)) ** 0.5
    out.update({
        "average": round(my, 2),
        "last": ys[-1], "previous": ys[-2],
        "change_vs_previous_pct": round((ys[-1] - ys[-2]) / ys[-2] * 100, 1) if ys[-2] else None,
        "slope_per_period": round(slope, 2),
        "projection": [{"step": k, "value": round(icpt + slope * (n - 1 + k), 2),
                        "low": round(icpt + slope * (n - 1 + k) - spread, 2),
                        "high": round(icpt + slope * (n - 1 + k) + spread, 2)}
                       for k in range(1, max(0, min(int(project_ahead), 12)) + 1)],
        "method": (f"Straight-line fit over the last {n} {period}s; the range is one standard "
                   f"deviation of the fit's error. Indicative only -- it assumes the recent "
                   f"pattern continues and knows nothing about seasonality or one-off orders."),
        "last_period_may_be_partial": True,
    })
    return out


def erpnext_fields(doctype: str):
    """The fields of an ERPNext doctype, so a list or a lookup can be asked correctly."""
    _doctype_allowed(doctype)
    meta = frappe.get_meta(doctype)
    return {
        "doctype": doctype,
        "title_field": meta.title_field,
        "is_submittable": bool(meta.is_submittable),
        "fields": [{"field": f.fieldname, "label": f.label, "type": f.fieldtype,
                    "options": f.options if f.fieldtype in ("Link", "Select", "Table") else None}
                   for f in meta.fields
                   if f.fieldname and f.fieldtype not in ("Section Break", "Column Break",
                                                          "Tab Break", "HTML", "Button",
                                                          "Password")],
    }


def erpnext_list(doctype: str, fields=None, filters=None, order_by: str | None = None,
                 limit: int = 20):
    """Rows of any ERPNext doctype the person asking may read, through their permissions."""
    from frappe.client import get_list

    _doctype_allowed(doctype)
    rows = get_list(doctype, fields=(fields or ["name"])[:25], filters=_erp_filters(filters),
                    order_by=order_by or "modified desc",
                    limit_page_length=min(int(limit or 20), MAX_ROWS))
    rows = [_clean(dict(r)) for r in rows]
    for r in rows:
        if r.get("name"):
            r["open_url"] = frappe.utils.get_url_to_form(doctype, str(r["name"]))
    return {"doctype": doctype, "rows": rows}


def erpnext_count(doctype: str, filters=None):
    """How many records of a doctype match, through the asker's permissions."""
    from frappe.client import get_count

    _doctype_allowed(doctype)
    return {"doctype": doctype, "count": get_count(doctype, filters=_erp_filters(filters))}


def erpnext_document(doctype: str, name: str):
    """One ERPNext document with its lines, through the asker's permissions."""
    from frappe.client import get

    _doctype_allowed(doctype)
    doc = get(doctype, name)  # permission-checked, field-level read rules applied
    doc = _clean(doc)
    doc["open_url"] = frappe.utils.get_url_to_form(doctype, str(name))
    return doc


# ERPNext's own reports. The general ledger, purchase orders and stock movements are
# not loaded as facts; these reports read them directly, computed the way Gigmann's
# accountants already see them. An allowlist, because a custom script report can do
# anything its author wrote -- these standard ones only read.
REPORTS = {
    "Profit and Loss Statement", "Balance Sheet", "Cash Flow", "Trial Balance",
    "General Ledger", "Accounts Receivable", "Accounts Receivable Summary",
    "Accounts Payable", "Accounts Payable Summary", "Gross Profit",
    "Sales Analytics", "Purchase Analytics", "Purchase Order Analysis",
    "Sales Order Analysis", "Item-wise Sales Register", "Item-wise Purchase Register",
    "Stock Balance", "Stock Ledger", "Stock Ageing", "Stock Projected Qty",
    "Budget Variance Report", "Customer Ledger Summary", "Supplier Ledger Summary",
}
MAX_REPORT_ROWS = 80


def _company(business_code) -> str | None:
    if business_code and business_code != "__all__":
        c = frappe.db.get_value("Connected Business", business_code, "erpnext_company")
        if c:
            return c
    return frappe.defaults.get_user_default("Company")


def _report_allowed(report: str) -> str:
    if report not in REPORTS:
        raise ToolError(f"{report!r} is not one of the reports available here: "
                        f"{', '.join(sorted(REPORTS))}")
    if not frappe.db.exists("Report", report):
        raise ToolError(f"This site has no report called {report!r}.")
    return report


def report_filters(report: str, business_code=None):
    """The filters a report takes, read from its own definition."""
    _report_allowed(report)
    from frappe.desk.query_report import get_script

    script = (get_script(report) or {}).get("script") or ""
    i = script.find("filters")
    return {"report": report, "company": _company(business_code),
            "filters_definition": script[max(0, i - 20): i + 3500] if i >= 0 else script[:3500]}


def run_report(report: str, filters=None, business_code=None):
    """Run a standard ERPNext report with the asker's permissions; rows, columns, summary."""
    _report_allowed(report)  # before anything else: an unlisted report never loads
    from frappe.desk.query_report import run

    pairs = filters if isinstance(filters, list) else [{"field": k, "value": v}
                                                       for k, v in (filters or {}).items()]
    f = {p.get("field"): p.get("value") for p in pairs if p.get("field") and p.get("value") not in (None, "")}
    f.setdefault("company", _company(business_code))
    try:
        res = run(report, filters=json.dumps(f), ignore_prepared_report=True) or {}
    except frappe.PermissionError:
        raise ToolError(f"The person asking may not run {report}.")
    except Exception as e:  # a missing or wrong filter is the usual cause
        raise ToolError(f"{report} could not run with these filters ({str(e)[:300]}). "
                        f"Call report_filters to see what it needs.")
    cols = []
    for c in res.get("columns") or []:
        if isinstance(c, dict):
            cols.append({"key": c.get("fieldname") or c.get("label"), "label": c.get("label"),
                         "type": c.get("fieldtype")})
        else:  # "Label:Type/Options:width"
            label = str(c).split(":")[0]
            cols.append({"key": label, "label": label, "type": None})
    rows = []
    for r in (res.get("result") or [])[:MAX_REPORT_ROWS]:
        if isinstance(r, dict):
            rows.append(_clean({k: v for k, v in r.items() if v not in (None, "")}))
        elif isinstance(r, (list, tuple)):
            rows.append(_clean({cols[i]["key"]: v for i, v in enumerate(r) if i < len(cols)}))
    total = len(res.get("result") or [])
    return {"report": report, "filters": f, "columns": cols, "rows": rows,
            "row_count": total, "trimmed": total > len(rows),
            "summary": _clean(res.get("report_summary") or []),
            "message": _clean(res.get("message") or "")}


# The six deep analyses that existed before the analyst. They stay: each is a careful,
# tested piece of reasoning, and the model calling one is better than re-deriving it.
def _intent(name: str, phrasing: str):
    def run(subject: str | None = None, business_code=None):
        from command_center.ask import intents
        fn = {f.__name__: f for f in intents.INTENTS}[name]
        res = fn(phrasing.format(subject=subject or ""), business_code)
        return _clean(res) if res else {"answered": False,
                                        "note": "That analysis found nothing to report."}
    run.__name__ = name
    return run


# ---------------------------------------------------------------------------
# The catalogue the model sees. A function not listed here does not exist to it.
# ---------------------------------------------------------------------------
_FILTERS = {
    "type": "array", "description": "Conditions, all of which must hold.",
    "items": {"type": "object", "properties": {
        "column": {"type": "string"},
        "op": {"type": "string", "description": "=, !=, >, >=, <, <=, like, in, not in"},
        "value": {"type": "string", "description": "for single-value operators"},
        "values": {"type": "array", "items": {"type": "string"},
                   "description": "for in / not in"}},
        "required": ["column"]}}
_FACT = {"type": "string", "enum": list(FACTS)}


def _decl(name, description, properties=None, required=None):
    # A tool that takes nothing has no "parameters" at all. An object with empty
    # properties is rejected by Gemini -- and one rejected declaration fails the whole
    # request, which is how every question fell back to the patterns on the live site.
    decl = {"name": name, "description": description}
    if properties:
        decl["parameters"] = {"type": "object", "properties": properties}
        if required:
            decl["parameters"]["required"] = required
    return decl


TOOLS = {
    "describe_data": (describe_data, _decl(
        "describe_data",
        "List the loaded business data sets (or one of them): columns, breakdowns, amounts, "
        "dates, row counts and how current each is. Call this first when unsure which data "
        "or column answers a question.",
        {"fact": _FACT})),
    "query_data": (query_data, _decl(
        "query_data",
        "Totals, counts, averages, minimums or maximums over one loaded data set -- overall, "
        "broken down by up to two columns, and/or by period (day, week, month, quarter, year) "
        "over a date column, with filters and a date range. Use for any 'how much', 'how many', "
        "'who/which is biggest', 'by month', 'compare' question.",
        {"fact": _FACT,
         "measures": {"type": "array", "items": {"type": "object", "properties": {
             "function": {"type": "string", "enum": list(FUNCS)},
             "column": {"type": "string"}}, "required": ["function", "column"]}},
         "group_by": {"type": "array", "items": {"type": "string"}},
         "period": {"type": "string", "enum": ["day", "week", "month", "quarter", "year"]},
         "date_column": {"type": "string"},
         "date_from": {"type": "string", "description": "YYYY-MM-DD"},
         "date_to": {"type": "string", "description": "YYYY-MM-DD"},
         "filters": _FILTERS,
         "order": {"type": "string", "enum": ["desc", "asc"]},
         "limit": {"type": "integer"}},
        ["fact"])),
    "list_records": (list_records, _decl(
        "list_records",
        "Individual rows of a loaded data set (largest, latest, overdue ...), each with a link "
        "to the ERPNext document it came from.",
        {"fact": _FACT, "columns": {"type": "array", "items": {"type": "string"}},
         "filters": _FILTERS, "order_by": {"type": "string"},
         "descending": {"type": "boolean"}, "limit": {"type": "integer"}},
        ["fact"])),
    "get_figures": (get_figures, _decl(
        "get_figures",
        "The platform's defined headline figures by key -- exactly the numbers its cards "
        "show, with their as-of date and data status. Prefer these when one matches.",
        {"keys": {"type": "array", "items": {"type": "string"}}}, ["keys"])),
    "find": (find, _decl(
        "find",
        "Look up customers, suppliers, items or warehouses by name or part of a name, to get "
        "the exact name before filtering on it.",
        {"text": {"type": "string"}}, ["text"])),
    "trend": (trend, _decl(
        "trend",
        "A measure over time: the series, its average, change against the previous period, "
        "direction, and a straight-line projection with a range. Use for 'trend', 'growing', "
        "'forecast', 'projection', 'where will we be' questions.",
        {"fact": _FACT, "measure": {"type": "string"},
         "function": {"type": "string", "enum": list(FUNCS)},
         "date_column": {"type": "string"},
         "period": {"type": "string", "enum": ["week", "month", "quarter", "year"]},
         "periods": {"type": "integer"}, "project_ahead": {"type": "integer"},
         "filters": _FILTERS},
        ["fact", "measure", "date_column"])),
    "erpnext_fields": (erpnext_fields, _decl(
        "erpnext_fields",
        "The fields of any ERPNext doctype (Sales Order, Quotation, Lead, Journal Entry, "
        "Employee, Project, Issue, Item ...) so it can be listed or read correctly.",
        {"doctype": {"type": "string"}}, ["doctype"])),
    "erpnext_list": (erpnext_list, _decl(
        "erpnext_list",
        "Rows of any ERPNext doctype the person asking may read -- including data not in the "
        "loaded sets (quotations, leads, journals, projects, assets ...). Reads only.",
        {"doctype": {"type": "string"}, "fields": {"type": "array", "items": {"type": "string"}},
         "filters": _FILTERS, "order_by": {"type": "string"}, "limit": {"type": "integer"}},
        ["doctype"])),
    "erpnext_count": (erpnext_count, _decl(
        "erpnext_count", "How many records of an ERPNext doctype match some conditions.",
        {"doctype": {"type": "string"}, "filters": _FILTERS}, ["doctype"])),
    "erpnext_document": (erpnext_document, _decl(
        "erpnext_document",
        "One ERPNext document in full, with its line items -- an invoice, order, quotation, "
        "employee, project, issue ...",
        {"doctype": {"type": "string"}, "name": {"type": "string"}}, ["doctype", "name"])),
    "report_filters": (report_filters, _decl(
        "report_filters",
        "The filters an ERPNext report takes (dates, periodicity, fiscal year, company ...), "
        "read from the report itself. Call before run_report when unsure.",
        {"report": {"type": "string", "enum": sorted(REPORTS)}}, ["report"])),
    "run_report": (run_report, _decl(
        "run_report",
        "Run one of ERPNext's standard reports -- the way Gigmann's accountants see the "
        "numbers. Use for profit and loss, the balance sheet, cash flow, the trial balance, "
        "the general ledger, purchase orders, stock movements and ageing, gross profit, and "
        "anything else the loaded data sets do not hold. The company is filled in.",
        {"report": {"type": "string", "enum": sorted(REPORTS)},
         # A list of pairs, not an open object: Gemini rejects an object parameter with
         # no declared properties.
         "filters": {"type": "array", "description": "the report's own filters, e.g. "
                     "from_date 2025-01-01, to_date 2025-08-19, periodicity Monthly",
                     "items": {"type": "object", "properties": {
                         "field": {"type": "string"}, "value": {"type": "string"}},
                         "required": ["field", "value"]}}},
        ["report"])),
}

for _name, _phrasing, _desc in [
    ("who_owes_most", "Who owes us the most?",
     "The customers who owe the most, how old the debt is, and how concentrated it is."),
    ("has_party_ever_paid", "Has {subject} ever paid us?",
     "A customer's payment history: whether, how much and how recently they have paid."),
    ("why_order_open", "Why is the {subject} order still open?",
     "Why a sales order is still open: what is undelivered or unbilled and for how long."),
    ("supplier_concentration", "What happens if {subject} stops supplying?",
     "How dependent the business is on one supplier, including items no one else supplies."),
    ("owes_and_waiting", "Which customers owe us money and are also waiting on us?",
     "Customers who owe money while also waiting on undelivered orders -- leverage both ways."),
    ("party_brief", "What should I say to {subject}?",
     "A briefing on one customer before a call: balance, history, open orders, issues."),
]:
    _subj = "{subject}" in _phrasing
    TOOLS[_name] = (_intent(_name, _phrasing), _decl(
        _name, _desc,
        {"subject": {"type": "string", "description": "exact name, from find"}} if _subj else {},
        ["subject"] if _subj else None))


def run(name: str, args: dict, business_code=None):
    """Run one tool by name. Anything not in TOOLS does not exist."""
    entry = TOOLS.get(name)
    if not entry:
        raise ToolError(f"There is no tool called {name!r}.")
    fn, _ = entry
    args = dict(args or {})
    args.pop("business_code", None)  # scope comes from the session, never from the model
    if name not in ("erpnext_fields", "erpnext_list", "erpnext_count", "erpnext_document"):
        args["business_code"] = business_code
    return fn(**args)


def declarations() -> list:
    return [decl for _, decl in TOOLS.values()]


FACT_WORDS = {
    "fact_sales_invoice": "sales invoices", "fact_sales_invoice_line": "sales invoice lines",
    "fact_payment_allocation": "customer payments", "fact_purchase_invoice": "supplier bills",
    "fact_purchase_invoice_line": "supplier bill lines", "fact_stock_balance": "stock balances",
    "fact_sales_order": "sales orders", "fact_task": "jobs and tasks",
    "fact_person": "staff records", "fact_case": "customer issues",
}
INTENT_WORDS = {
    "who_owes_most": "Working out who owes the most", "has_party_ever_paid": "Reading {s}'s payment history",
    "why_order_open": "Looking at why {s} is still open", "supplier_concentration": "Measuring dependence on {s}",
    "owes_and_waiting": "Finding customers who owe and are waiting", "party_brief": "Preparing a brief on {s}",
}


def describe(name: str, args: dict) -> str:
    """One step, in the words a director would use -- shown live while the analyst works."""
    a = args or {}
    fact = FACT_WORDS.get(a.get("fact"), "the records")
    by = ", ".join(str(g).replace("_", " ") for g in (a.get("group_by") or []))
    if name == "query_data":
        when = f" by {a['period']}" if a.get("period") else ""
        return f"Adding up {fact}" + (f" by {by}" if by else "") + when
    if name == "list_records":
        return f"Reading the {fact}"
    if name == "trend":
        return f"Working out the trend in {fact}"
    if name == "get_figures":
        return "Reading the headline figures"
    if name == "find":
        return f"Looking up “{str(a.get('text', ''))[:40]}”"
    if name == "describe_data":
        return "Checking what data is loaded"
    if name == "run_report":
        return f"Running ERPNext's {a.get('report', 'report')}"
    if name == "report_filters":
        return f"Checking how {a.get('report', 'the report')} is filtered"
    if name in ("erpnext_list", "erpnext_count", "erpnext_fields"):
        return f"Reading {a.get('doctype', 'ERPNext')} records"
    if name == "erpnext_document":
        return f"Opening {a.get('doctype', '')} {a.get('name', '')}".strip()
    if name in INTENT_WORDS:
        return INTENT_WORDS[name].format(s=a.get("subject") or "it")
    return "Looking something up"


def summary(name: str, args: dict) -> str:
    """One readable line per call, for "what it checked"."""
    a = {k: v for k, v in (args or {}).items() if v not in (None, [], "")}
    return f"{name}({json.dumps(a, default=str)[:220]})"
