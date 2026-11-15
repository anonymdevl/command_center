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


# Facts that hold submittable documents. Their drafts and cancelled rows are loaded too
# (so "invoices never issued" can be answered), but every figure on the screens counts
# submitted documents only -- and a model that forgot that filter produced a table of 888
# unpaid invoices under a headline of 806 (18 Oct 2026). Submitted is the default here
# as well; asking about drafts means filtering src_docstatus explicitly.
SUBMITTABLE = {"fact_sales_invoice", "fact_sales_invoice_line", "fact_purchase_invoice",
               "fact_purchase_invoice_line", "fact_sales_order", "fact_payment_allocation"}


def _scope(fact: str, filters: dict, business_code) -> dict:
    if business_code and business_code != "__all__" and "business_code" in _columns(FACTS[fact]):
        filters = {**filters, "business_code": business_code}
    if fact in SUBMITTABLE and "src_docstatus" not in filters:
        filters = {**filters, "src_docstatus": ["=", 1]}
    return filters


def _remote(business_code):
    """The connector for a business on another site, or None for this site's own.

    On the hosted service every business is remote: its documents, fields and reports
    are read from its own ERPNext through frappe.client's read endpoints and
    frappe.desk.query_report.run, with the asker's own key there when they have linked
    one and the business's read-only service account otherwise. The connector's write
    methods exist for people pressing buttons (api/actions.py); nothing here calls them,
    and preflight holds that.
    """
    if not business_code or business_code == "__all__":
        from command_center.api.businesses import default_business_code
        business_code = default_business_code()
    if not business_code or frappe.db.get_value("Connected Business",
                                                {"business_code": business_code}, "is_local"):
        return None
    from command_center.connectors.registry import connector_for
    return connector_for(business_code)


def _far(call):
    """Run a read on a peer; its refusals come back to the model as words."""
    from command_center.connectors.base import ConnectorError
    try:
        return call()
    except ConnectorError as e:
        raise ToolError(str(e)[:400])


def _doctype_allowed(doctype: str, business_code=None) -> str:
    if doctype in DENIED_DOCTYPES:
        raise ToolError(f"{doctype} holds credentials or system configuration and is not "
                        f"available to the assistant.")
    if _remote(business_code):
        # The far site decides whether it exists and who may read it, and says so.
        if not doctype:
            raise ToolError("Name the doctype to read.")
        return doctype
    if not doctype or not frappe.db.exists("DocType", doctype):
        raise ToolError(f"There is no ERPNext doctype called {doctype!r}.")
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
    # Each row opens in its own business's ERPNext (api/facts.py builds the address).
    from command_center.api.facts import _document_url, _site_urls
    sites = _site_urls()
    from command_center.api.businesses import default_business_code
    asked = (business_code if business_code and business_code != "__all__"
             else default_business_code())
    for r in rows:
        if r.get("src_doctype") and r.get("src_name"):
            r["open_url"] = _document_url(sites, {"business_code": asked, **r})
    return {"data_set": fact, "filters": rules, "rows": rows}


def get_figures(keys, business_code=None):
    """The platform's own defined figures -- the same numbers the cards show."""
    from command_center.kpi.engine import evaluate_set
    from command_center.kpi.registry import load_all

    from command_center.kpi.live import LIVE, evaluate as evaluate_live

    known = load_all()
    unknown = [k for k in keys or [] if k not in known and k not in LIVE]
    if unknown:
        raise ToolError(f"Unknown figure(s) {', '.join(unknown)}. Known: "
                        f"{', '.join(sorted(known) + sorted(LIVE))}")
    result = evaluate_set([k for k in keys if k in known], business_code)
    result.update(evaluate_live([k for k in keys if k in LIVE], business_code))
    # What the model needs to quote a figure, not the engine's internals: the rest made
    # every lookup several times longer than its answer.
    keep = ("label", "value", "unit", "currency", "note", "as_of", "period", "group", "basis")
    return _clean({k: {f: v.get(f) for f in keep if v.get(f) not in (None, "", {})}
                   for k, v in result.items()})


def current_recommendations(business_code=None):
    """The platform's current recommendations for the business, ranked by money at stake
    times urgency -- the same list as Home's Top actions. Reads only."""
    from command_center.recommend import engine
    if business_code and business_code != "__all__":
        codes = [business_code]
    else:
        from command_center.api.businesses import loaded_codes
        codes = loaded_codes()
    out = {"recommendations": [], "total": 0}
    for code in codes:
        got = engine.snapshot(code)
        out["recommendations"] += got["recommendations"]
        out["total"] += got["total"]
        out["worked_out"] = got["worked_out"]
    out["recommendations"].sort(key=lambda r: -(r.get("money_at_stake") or 0))
    out["recommendations"] = out["recommendations"][:15]
    return _clean(out)


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


# "This month against last month", "this quarter against the same quarter last year".
# Measured back from where the data ends, as the figures' own periods are (kpi/engine.py
# _period): on a dataset that stops in August, "this month" measured from today is an
# empty month, and comparing it with the one before reports a collapse that never was.
COMPARISONS = {
    "month_vs_previous": "the latest full month against the month before it",
    "month_vs_last_year": "the latest full month against the same month a year earlier",
    "quarter_vs_previous": "the latest full quarter against the quarter before it",
    "quarter_vs_last_year": "the latest full quarter against the same quarter a year earlier",
    "twelve_months_vs_previous": "the latest twelve full months against the twelve before them",
    "custom": "two date ranges, as given",
}


def _spans(horizon, compare: str, current_from=None, current_to=None, earlier_from=None,
           earlier_to=None) -> tuple:
    """((from, to, label), (from, to, label)) for the current and the earlier period."""
    u = frappe.utils
    if compare == "custom":
        if not (current_from and current_to and earlier_from and earlier_to):
            raise ToolError("A custom comparison needs current_from, current_to, earlier_from "
                            "and earlier_to (YYYY-MM-DD).")
        spans = []
        for a, b in ((current_from, current_to), (earlier_from, earlier_to)):
            a, b = u.getdate(a), u.getdate(b)
            if a > b:
                raise ToolError(f"{a} is after {b}: each range runs from its first date to its last.")
            spans.append((a, b, f"{a:%d %b %Y} – {b:%d %b %Y}"))
        return spans[0], spans[1]
    if compare not in COMPARISONS:
        raise ToolError(f"compare must be one of {', '.join(COMPARISONS)}")
    h = u.getdate(horizon)
    # The latest calendar month the data covers to its last day (as the engine's
    # last_full_month): data stopping on 12 August makes that July.
    end = h if h == u.getdate(u.get_last_day(h)) else u.getdate(u.add_days(u.get_first_day(h), -1))
    if compare.startswith("quarter"):
        while end.month % 3:
            end = u.getdate(u.add_days(u.get_first_day(end), -1))
        months, back = 3, 3 if compare.endswith("previous") else 12
    elif compare.startswith("twelve"):
        months, back = 12, 12
    else:
        months, back = 1, 1 if compare.endswith("previous") else 12
    start = u.getdate(u.get_first_day(u.add_months(end, -(months - 1))))
    e_start = u.getdate(u.get_first_day(u.add_months(start, -back)))
    e_end = u.getdate(u.get_last_day(u.add_months(end, -back)))

    def label(a, b):
        if months == 1:
            return f"{a:%B %Y}"
        if months == 3:
            return f"Q{(a.month - 1) // 3 + 1} {a.year}"
        return f"{a:%b %Y} – {b:%b %Y}"

    return (start, end, label(start, end)), (e_start, e_end, label(e_start, e_end))


def _figure_between(kpi, field: str, a, b, business_code) -> tuple:
    """(value, group, drill filters) of one defined figure over [a, b] on `field`, by the
    engine's own queries: its filters, its aggregate, its ratio rule."""
    from command_center.kpi import engine
    from command_center.kpi.registry import get

    span = ["between", [str(a), str(b)]]
    if kpi.agg == "ratio":
        parts = {}
        for k in (kpi.numerator, kpi.denominator):
            parts[k] = {"value": _figure_between(get(k), field, a, b, business_code)[0]}
        return engine._ratio(kpi, parts), None, None
    filters = {**(kpi.filters or {}), field: span}
    drill = {**(kpi.drill_filters or {}), field: span}
    if kpi.agg == "top":
        value, group = engine._top(kpi, business_code, filters)
        if group and group.get("drill"):
            drill.update(group.pop("drill"))
        return value, group, drill
    return engine._aggregate(kpi, business_code, filters), None, drill


def _figure_field(kpi, date_column) -> tuple:
    """(the date a figure is compared on, whether that date is not the figure's own):
    its own period's date, or one named for it."""
    from command_center.facts.schema import DATE_FIELDS
    from command_center.kpi.registry import get

    if kpi.agg == "ratio":
        got = [_figure_field(get(k), date_column) for k in (kpi.numerator, kpi.denominator)]
        if len({f for f, _ in got}) != 1:
            raise ToolError(f"{kpi.key}'s two parts are dated differently, so it cannot be "
                            f"compared over periods.")
        return got[0][0], any(u for _, u in got)
    if kpi.period and (not date_column or date_column == kpi.period["field"]):
        return kpi.period["field"], False
    dates = ", ".join(DATE_FIELDS.get(kpi.fact, [])) or "none"
    if not date_column:
        raise ToolError(
            f"{kpi.key} ({kpi.label}) is a position as it stands now, not a total over a "
            f"period, and the platform keeps no history of it. To compare the records dated "
            f"in each period instead, name a date_column ({dates}) -- and say that is what "
            f"was compared.")
    if date_column not in DATE_FIELDS.get(kpi.fact, ()):
        raise ToolError(f"{date_column!r} is not a date of {kpi.fact}: use one of {dates}.")
    return date_column, True


def compare_periods(figure: str | None = None, fact: str | None = None,
                    measure: str | None = None, function: str = "sum",
                    date_column: str | None = None, compare: str = "month_vs_previous",
                    current_from: str | None = None, current_to: str | None = None,
                    earlier_from: str | None = None, earlier_to: str | None = None,
                    filters=None, business_code=None):
    """One figure, or one measure of a data set, in two periods: both values, the change
    and the percentage change, computed by the same queries as the figures themselves
    (a figure through the KPI engine, a measure through query_data)."""
    from command_center.api.businesses import currency_for
    from command_center.kpi import engine

    if bool(figure) == bool(fact):
        raise ToolError("Name either a figure (a key from get_figures) or a data set with a "
                        "measure -- one of the two.")
    notes = []
    if figure:
        from command_center.kpi.live import LIVE
        from command_center.kpi.registry import get, load_all
        known = load_all()
        if figure in LIVE:
            raise ToolError(f"{figure} is read straight from ERPNext as it stands now; there is "
                            f"no earlier value to compare it with.")
        if figure not in known:
            raise ToolError(f"Unknown figure {figure!r}. Known: {', '.join(sorted(known))}")
        kpi = get(figure)
        field, undated = _figure_field(kpi, date_column)
        base = get(kpi.numerator) if kpi.agg == "ratio" else kpi
        t = engine._table(base)
        row = engine._scoped(frappe.qb.from_(t).select(Max(t[field])), t, business_code,
                             base.filters).run()
        horizon = row[0][0] if row and row[0] else None
        what, unit, data_set = kpi.label, kpi.unit, kpi.fact
        if undated:
            notes.append(f"{kpi.label} has no period of its own, so each value counts only the "
                         f"records whose {field.replace('_', ' ')} falls in that period -- not "
                         f"the position as it stood at the time.")
    else:
        if not (measure and date_column):
            raise ToolError("A data set comparison needs a measure and a date_column.")
        fn = (function or "sum").lower()
        got = query_data(fact, measures=[{"function": "max", "column": date_column}],
                         filters=filters, business_code=business_code)
        horizon = (got["rows"][0] if got["rows"] else {}).get(f"max_{date_column}")
        what = f"{fn} of {measure.replace('_', ' ')} in {FACT_WORDS.get(fact, fact)}"
        unit = "count" if fn == "count" else (
            "currency" if fn != "count" and any(w in measure for w in ("amount", "total", "value"))
            else None)
        data_set = fact
    if not horizon and compare != "custom":
        raise ToolError("There are no dated records to compare.")

    cur, old = _spans(horizon, compare, current_from, current_to, earlier_from, earlier_to)
    currency = currency_for(business_code) if unit == "currency" else None
    sides, drills = [], []
    for a, b, label in (cur, old):
        group = None
        if figure:
            value, group, drill = _figure_between(kpi, field, a, b, business_code)
        else:
            res = query_data(fact, measures=[{"function": fn, "column": measure}],
                             date_column=date_column, date_from=str(a), date_to=str(b),
                             filters=filters, business_code=business_code)
            value = (res["rows"][0] if res["rows"] else {}).get(f"{fn}_{measure}")
            if value is None and fn in ("sum", "count"):
                value = 0  # a sum or a count of nothing is 0; an average of nothing is unknown
            drill = {**res["filters"], date_column: ["between", [str(a), str(b)]]}
        if isinstance(value, decimal.Decimal):
            value = float(value)
        side = {"period": label, "from": str(a), "to": str(b), "value": value}
        if unit:
            side["text"] = engine._plain({"value": value, "unit": unit, "currency": currency})
        if group and group.get("label"):
            side["group"] = group["label"]
        sides.append(side)
        drills.append(drill)

    now, then = sides[0]["value"], sides[1]["value"]
    out = {"what": what, "comparison": COMPARISONS[compare], "data_horizon": str(horizon or ""),
           "unit": unit, "currency": currency, "current": sides[0], "earlier": sides[1]}
    if now is None or then is None:
        out["change"] = out["change_pct"] = None
        notes.append("One of the two periods has no value, so there is no change to state.")
    else:
        change = round(float(now) - float(then), 4)
        out["change"] = change
        out["change_pct"] = round(change / abs(float(then)) * 100, 1) if then else None
        out["direction"] = "up" if change > 0 else "down" if change < 0 else "no change"
        if unit == "percent":
            notes.append("Both values are percentages: the change is in percentage points.")
        elif unit:
            out["change_text"] = engine._plain({"value": abs(change), "unit": unit,
                                                "currency": currency})
        if not then:
            notes.append("The earlier value is zero, so there is no percentage change.")
    if drills[0] is not None:
        out["data_set"], out["filters"], out["earlier_filters"] = data_set, drills[0], drills[1]
    if notes:
        out["note"] = " ".join(notes)
    return _clean(out)


def erpnext_fields(doctype: str, business_code=None):
    """The fields of an ERPNext doctype, so a list or a lookup can be asked correctly."""
    _doctype_allowed(doctype, business_code)
    far = _remote(business_code)
    if far:
        # The business's own definition: its version, its custom fields.
        m = _far(lambda: far.get_meta(doctype))
        title, submittable, fields = (m.get("title_field"), m.get("is_submittable"),
                                      [frappe._dict(f) for f in m.get("fields") or []])
    else:
        meta = frappe.get_meta(doctype)
        title, submittable, fields = meta.title_field, meta.is_submittable, meta.fields
    return {
        "doctype": doctype,
        "title_field": title,
        "is_submittable": bool(submittable),
        "fields": [{"field": f.fieldname, "label": f.label, "type": f.fieldtype,
                    "options": f.options if f.fieldtype in ("Link", "Select", "Table") else None}
                   for f in fields
                   if f.fieldname and f.fieldtype not in ("Section Break", "Column Break",
                                                          "Tab Break", "HTML", "Button",
                                                          "Password")],
    }


def _open_url(far, doctype, name) -> str:
    if far:
        return f"{far.base_url}/app/{frappe.scrub(doctype).replace('_', '-')}/{name}"
    return frappe.utils.get_url_to_form(doctype, str(name))


def erpnext_list(doctype: str, fields=None, filters=None, order_by: str | None = None,
                 limit: int = 20, business_code=None):
    """Rows of any ERPNext doctype the person asking may read, through their permissions."""
    _doctype_allowed(doctype, business_code)
    far = _remote(business_code)
    args = dict(fields=(fields or ["name"])[:25], filters=_erp_filters(filters),
                order_by=order_by or "modified desc")
    n = min(int(limit or 20), MAX_ROWS)
    if far:
        rows = _far(lambda: far.get_list(doctype, limit=n, **args))
    else:
        from frappe.client import get_list
        rows = get_list(doctype, limit_page_length=n, **args)
    rows = [_clean(dict(r)) for r in rows]
    for r in rows:
        if r.get("name"):
            r["open_url"] = _open_url(far, doctype, str(r["name"]))
    return {"doctype": doctype, "rows": rows}


def erpnext_count(doctype: str, filters=None, business_code=None):
    """How many records of a doctype match, through the asker's permissions."""
    _doctype_allowed(doctype, business_code)
    far = _remote(business_code)
    if far:
        return {"doctype": doctype,
                "count": _far(lambda: far.get_count(doctype, _erp_filters(filters)))}
    from frappe.client import get_count
    return {"doctype": doctype, "count": get_count(doctype, filters=_erp_filters(filters))}


def erpnext_document(doctype: str, name: str, business_code=None):
    """One ERPNext document with its lines, through the asker's permissions."""
    _doctype_allowed(doctype, business_code)
    far = _remote(business_code)
    if far:
        doc = _far(lambda: far.get_doc(doctype, name))
    else:
        from frappe.client import get
        doc = get(doctype, name)  # permission-checked, field-level read rules applied
    doc = _clean(doc)
    doc["open_url"] = _open_url(far, doctype, name)
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
        c = frappe.db.get_value("Connected Business", {"business_code": business_code}, "erpnext_company")
        if c:
            return c
    return frappe.defaults.get_user_default("Company")


def _report_allowed(report: str, business_code=None) -> str:
    if report not in REPORTS:
        raise ToolError(f"{report!r} is not one of the reports available here: "
                        f"{', '.join(sorted(REPORTS))}")
    if not _remote(business_code) and not frappe.db.exists("Report", report):
        raise ToolError(f"This site has no report called {report!r}.")
    return report


def report_filters(report: str, business_code=None):
    """The filters a report takes, read from its own definition."""
    _report_allowed(report, business_code)
    far = _remote(business_code)
    if far:
        got = _far(lambda: far._call("frappe.desk.query_report.get_script",
                                     {"report_name": report})) or {}
    else:
        from frappe.desk.query_report import get_script
        got = get_script(report) or {}
    script = got.get("script") or ""
    i = script.find("filters")
    return {"report": report, "company": _company(business_code),
            "filters_definition": script[max(0, i - 20): i + 3500] if i >= 0 else script[:3500]}


def run_report(report: str, filters=None, business_code=None):
    """Run a standard ERPNext report with the asker's permissions; rows, columns, summary."""
    _report_allowed(report, business_code)  # before anything else: an unlisted report never loads
    far = _remote(business_code)

    pairs = filters if isinstance(filters, list) else [{"field": k, "value": v}
                                                       for k, v in (filters or {}).items()]
    f = {p.get("field"): p.get("value") for p in pairs if p.get("field") and p.get("value") not in (None, "")}
    f.setdefault("company", _company(business_code))
    try:
        if far:
            res = far.run_report(report, filters=f) or {}
        else:
            from frappe.desk.query_report import run
            res = run(report, filters=json.dumps(f), ignore_prepared_report=True) or {}
    except ToolError:
        raise
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


# People and leave, read live from the business's ERPNext the way the HR screen reads them
# (api/people.py): the leave balances worked out as HRMS works them out, who is away,
# what is waiting for approval. Contact details, photos and pay never come this way.
def people(text: str | None = None, department: str | None = None,
           status: str | None = None, business_code=None):
    """Employees by name or ID, department or status: job, department, branch, manager."""
    from command_center.api import people as P
    return _clean(_far(lambda: P.people_for_analyst(business_code, text, department, status)))


def leave(person: str | None = None, year: str | None = None, business_code=None):
    """One person's leave balances by type and recent leave, or everyone's: who is away
    today and this week, requests waiting for approval, balances, taken by department."""
    from command_center.api import people as P
    out = _far(lambda: P.for_analyst(business_code, person, year))
    if isinstance(out.get("balances"), list) and len(out["balances"]) > MAX_GROUPS:
        out["balances"] = out["balances"][:MAX_GROUPS]
        out["balances_note"] = f"first {MAX_GROUPS} people only"
    return _clean(out)


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
        "over a date column, with filters, a date range, an order and a limit. Do the work "
        "here, in one call, rather than fetching rows. For breakdowns, rankings and periods; "
        "for a headline number a defined figure (get_figures) is quicker. Submitted "
        "documents only unless you filter src_docstatus.",
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
        "First choice for any headline number: the platform's defined figures by key -- "
        "exactly the numbers its cards show, with their note and as-of date. Ask for every "
        "key you need in one call.",
        {"keys": {"type": "array", "items": {"type": "string"}}}, ["keys"])),
    "current_recommendations": (current_recommendations, _decl(
        "current_recommendations",
        "The platform's current recommendations for this business -- what its figures say "
        "is worth doing, ranked by money at stake: each with its title, the evidence, the "
        "steps, the money at stake, the area and who would act. First choice for 'what "
        "should I focus on', 'what needs my attention', 'where are we losing money', "
        "'what should we do'. The same list as the screens' Top actions.")),
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
    "compare_periods": (compare_periods, _decl(
        "compare_periods",
        "One number in two periods -- both values, the change and the % change, by the "
        "same rules as the figures. Give a figure key (e.g. revenue_last_month, "
        "cash_in_month, revenue_invoiced) OR a data set with a measure, function and "
        "date_column. compare: month_vs_previous, month_vs_last_year, quarter_vs_previous, "
        "quarter_vs_last_year, twelve_months_vs_previous (full periods, counted back from "
        "where the data ends), or custom with current_from/current_to/earlier_from/"
        "earlier_to. Use for 'up or down on last month', 'against last year', 'why did it "
        "fall'. A figure that is a position now (amount owed, stock) has no history: it "
        "is compared only if you name a date_column, and then counts the records dated in "
        "each period.",
        {"figure": {"type": "string", "description": "a figure key, as for get_figures"},
         "fact": _FACT, "measure": {"type": "string"},
         "function": {"type": "string", "enum": list(FUNCS)},
         "date_column": {"type": "string"},
         "compare": {"type": "string", "enum": list(COMPARISONS)},
         "current_from": {"type": "string", "description": "YYYY-MM-DD, custom only"},
         "current_to": {"type": "string", "description": "YYYY-MM-DD, custom only"},
         "earlier_from": {"type": "string", "description": "YYYY-MM-DD, custom only"},
         "earlier_to": {"type": "string", "description": "YYYY-MM-DD, custom only"},
         "filters": _FILTERS})),
    "erpnext_fields": (erpnext_fields, _decl(
        "erpnext_fields",
        "The fields of any ERPNext doctype (Sales Order, Quotation, Lead, Journal Entry, "
        "Employee, Project, Issue, Item ...) so it can be listed or read correctly.",
        {"doctype": {"type": "string"}}, ["doctype"])),
    "erpnext_list": (erpnext_list, _decl(
        "erpnext_list",
        "Rows of any ERPNext doctype the person asking may read -- for data not in the loaded "
        "sets (quotations, leads, journals, projects, assets ...). Ask only for the fields "
        "you need, with filters and a small limit. Reads only.",
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
    "people": (people, _decl(
        "people",
        "Find employees by name or employee ID (or part of one), department or status "
        "(Active, Left ...): their job, department, branch, manager, joining date and "
        "length of service. Read live from ERPNext. No contact details and no pay.",
        {"text": {"type": "string", "description": "a name, part of one, or an employee ID"},
         "department": {"type": "string"}, "status": {"type": "string"}})),
    "leave": (leave, _decl(
        "leave",
        "Leave, read live from ERPNext and counted as ERPNext's own leave balance counts "
        "it. With a person (name or employee ID): their balance by leave type -- "
        "allocated, taken, pending approval, remaining -- and their recent leave. "
        "Without: who is on approved leave today and this week, requests waiting for "
        "approval and for how long, every active person's balances, and days taken this "
        "year by department.",
        {"person": {"type": "string", "description": "a name or employee ID; leave out "
                                                     "for everyone"},
         "year": {"type": "string", "description": "YYYY; this year when left out"}})),
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
    import inspect
    accepted = set(inspect.signature(fn).parameters)
    args = dict(args or {})
    args.pop("business_code", None)  # scope comes from the session, never from the model
    # Only the arguments the tool takes. A model sometimes adds one of its own ("question"
    # on erpnext_count, 18 Oct 2026), and passing it on failed the lookup every time.
    args = {k: v for k, v in args.items() if k in accepted}
    if "business_code" in accepted:
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
    "fact_party_balance": "what each customer and supplier owes by the ledger, with what "
                          "their open invoices say, why the two differ, and the ageing after "
                          "unmatched payments are set against the oldest invoices",
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
    if name == "compare_periods":
        what = _figure_label(a.get("figure")) or (
            f"{str(a.get('measure') or 'the total').replace('_', ' ')} in {fact}")
        return f"Comparing {what} with an earlier period"
    if name == "get_figures":
        return "Reading the headline figures"
    if name == "find":
        return f"Looking up “{str(a.get('text', ''))[:40]}”"
    if name == "describe_data":
        return "Checking what data is loaded"
    if name == "current_recommendations":
        return "Reading the current recommendations"
    if name == "run_report":
        return f"Running ERPNext's {a.get('report', 'report')}"
    if name == "report_filters":
        return f"Checking how {a.get('report', 'the report')} is filtered"
    if name in ("erpnext_list", "erpnext_count", "erpnext_fields"):
        return f"Reading {a.get('doctype', 'ERPNext')} records"
    if name == "people":
        return (f"Looking up “{str(a.get('text'))[:40]}” among the staff" if a.get("text")
                else "Reading the staff list")
    if name == "leave":
        return (f"Reading {str(a.get('person'))[:40]}'s leave" if a.get("person")
                else "Reading who is on leave and the balances")
    if name == "erpnext_document":
        return f"Opening {a.get('doctype', '')} {a.get('name', '')}".strip()
    if name in INTENT_WORDS:
        return INTENT_WORDS[name].format(s=a.get("subject") or "it")
    return "Looking something up"


def _figure_label(key) -> str | None:
    if not key:
        return None
    try:
        from command_center.kpi.registry import load_all
        k = load_all().get(key)
        return f"“{k.label}”" if k else None
    except Exception:
        return None


# Steps of one kind in a row are shown as one line with a count ("Running an ERPNext
# report ×6"), the detail of each under "Show all". The kind's words are the line.
STEP_KINDS = {
    "query_data": "Adding up the records", "trend": "Working out a trend",
    "compare_periods": "Comparing with an earlier period", "list_records": "Reading records",
    "get_figures": "Reading the headline figures", "find": "Looking up a name",
    "describe_data": "Checking what data is loaded", "run_report": "Running an ERPNext report",
    "current_recommendations": "Reading the current recommendations",
    "report_filters": "Checking how a report is filtered",
    "erpnext_list": "Reading ERPNext records", "erpnext_count": "Reading ERPNext records",
    "erpnext_fields": "Reading ERPNext records", "erpnext_document": "Opening an ERPNext document",
    "people": "Reading the staff list", "leave": "Reading leave",
    "who_owes_most": "Working out who owes the most",
    "has_party_ever_paid": "Reading a payment history", "why_order_open": "Looking at an open order",
    "supplier_concentration": "Measuring dependence on a supplier",
    "owes_and_waiting": "Finding customers who owe and are waiting", "party_brief": "Preparing a brief",
}


class Step(str):
    """One live step: its words (it is a str, so anything that showed a string still
    does), plus the kind of lookup it is, so the page can group a run of them."""
    kind: str | None = None
    group: str | None = None


def step(name: str, args: dict) -> Step:
    s = Step(describe(name, args))
    s.group = STEP_KINDS.get(name)
    s.kind = ("erpnext" if name in ("erpnext_list", "erpnext_count", "erpnext_fields")
              else name) if s.group else None
    return s


def summary(name: str, args: dict) -> str:
    """One readable line per call, for "what it checked"."""
    a = {k: v for k, v in (args or {}).items() if v not in (None, [], "")}
    return f"{name}({json.dumps(a, default=str)[:220]})"
