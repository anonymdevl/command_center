"""The department screens' figures that need more than one loaded fact.

Each is read the same way as kpi/live.py's figures and returned in the same shape: the
loaded facts where they hold the answer, and a light live read of the business's own
ERPNext for what they do not (sales order lines, warehouses, issue types, projects).

A figure whose underlying records do not exist at all returns value None with a
needs_setup status (command_center/guides.py), which the card draws as the steps to
take in ERPNext. A figure that is genuinely zero is zero.

Importing this module touches no frappe (preflight imports kpi/live.py).
"""

from __future__ import annotations

from command_center.kpi.live import Live, _read


# --------------------------------------------------------------------------- helpers
def is_down(error) -> bool:
    """The business did not answer -- as opposed to refusing one request.

    The connector raises BusinessUnreachable for both a dead connection and any non-2xx
    reply (a field a v14 site does not have comes back as HTTP 417). Only the first is
    "can't reach": a refused read is one figure's problem, not the business's."""
    from command_center.connectors.base import BusinessUnreachable, RequestRefused
    return isinstance(error, BusinessUnreachable) and not isinstance(error, RequestRefused)


def unreachable_status(error) -> dict:
    return {"state": "unreachable",
            "message": "Can't reach this business's ERPNext right now."}


def _scope(r):
    return {"business_code": r.code} if getattr(r, "code", None) else {}


def facts(r, fact, filters, fields):
    """Rows of a loaded fact, for the business the reader reads."""
    import frappe

    from command_center.facts.schema import FACTS
    return frappe.get_all(FACTS[fact], filters={**_scope(r), **(filters or {})},
                          fields=fields, limit=200000)


def chunks(seq, n=200):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def child_rows(r, doctype, parent, names, fields, extra=None):
    """A child table's rows for some parents, a chunk at a time."""
    out = []
    for part in chunks(sorted(names)):
        out += _read(r, doctype, {"parent": ["in", part], **(extra or {})}, fields,
                     parent=parent, limit=100000)
    return out


def grouped(r, doctype, filters, group_by, aggs, parent=None):
    """One aggregate read, grouped: [{group..., alias: value}].

    aggs: [(function, field, alias)]. v14 and v15 take an aggregate as the string
    "max(field) as alias"; v16 refuses that and takes {"MAX": field}, answering in
    "MAX(`field`)". The older form is tried first -- the businesses on this platform run
    v14 -- and the newer on refusal (grouped_read)."""
    import frappe
    if r.local:
        groups = [g.strip() for g in group_by.split(",") if g.strip()]
        old = groups + [f"{fn}({field}) as {alias}" for fn, field, alias in aggs]
        return [dict(x) for x in frappe.get_all(doctype, filters=filters, fields=old,
                                                group_by=group_by, limit=100000)]
    return grouped_read(r.conn, doctype, filters, group_by, aggs, parent=parent)


def grouped_read(conn, doctype, filters, group_by, aggs, parent=None, limit=100000):
    """grouped(), straight on a connector: the one place the two aggregate dialects are
    spoken (ingest reads the ledger with it as the system; the screens through grouped)."""
    groups = [g.strip() for g in group_by.split(",") if g.strip()]
    old = groups + [f"{fn}({field}) as {alias}" for fn, field, alias in aggs]
    try:
        return conn.get_list(doctype, filters=filters, fields=old, group_by=group_by,
                             limit=limit, parent_doctype=parent) or []
    except Exception as e:
        if is_down(e):
            raise
        new = groups + [{fn.upper(): field} for fn, field, _ in aggs]
        rows = conn.get_list(doctype, filters=filters, fields=new, group_by=group_by,
                             limit=limit, parent_doctype=parent) or []
        out = []
        for row in rows:
            got = {g: row.get(g) for g in groups}
            for fn, field, alias in aggs:
                got[alias] = row.get(f"{fn.upper()}(`{field}`)", row.get(f"{fn.upper()}({field})"))
            out.append(got)
        return out


def num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def cur(r) -> str:
    from command_center.api.businesses import currency_for
    return currency_for(r.code) or ""


def money(r, v) -> str:
    return f"{cur(r)} {num(v):,.0f}".strip()


def setup(r, text, steps, path):
    from command_center.guides import needs_setup
    return needs_setup(r.code, text, steps, path)


def _orders_drill(names):
    names = sorted(names)
    return {"fact": "fact_sales_order",
            "filters": {"src_name": ["in", names]} if names else {"is_open": 1, "src_name": "-"}}


# --------------------------------------------------------------------------- sales: where orders are held up
def _open_orders(r):
    return facts(r, "fact_sales_order", {"src_docstatus": 1, "is_open": 1,
                                         "undelivered_value": [">", 0]},
                 ["src_name", "undelivered_value", "base_grand_total"])


def short_lines(r):
    """Open order lines still to deliver that the warehouse cannot cover, read once per
    request: [(order, gap, on_order)]. Each line is compared with what its own warehouse
    holds (the loaded stock position); services and other non-stock items are left out.
    It does not share stock out between orders competing for it, so it is the least
    that is short, never more."""
    if getattr(r, "_short_lines", None) is not None:
        return r._short_lines
    orders = {o["src_name"]: o for o in _open_orders(r)}
    out = []
    if orders:
        lines = child_rows(r, "Sales Order Item", "Sales Order", orders,
                           ["parent", "item_code", "warehouse", "qty", "delivered_qty",
                            "conversion_factor"])
        items = sorted({x.get("item_code") for x in lines if x.get("item_code")})
        stocked = set()
        for part in chunks(items):
            stocked |= {i["name"] for i in _read(r, "Item", {"name": ["in", part]},
                                                 ["name", "is_stock_item"])
                        if int(i.get("is_stock_item") or 0)}
        bins = {(b["item_code"], b["warehouse"]): b for b in facts(
            r, "fact_stock_balance", {}, ["item_code", "warehouse", "actual_qty", "ordered_qty"])}
        for x in lines:
            if x.get("item_code") not in stocked:
                continue
            left = (num(x.get("qty")) - num(x.get("delivered_qty"))) * (num(x.get("conversion_factor")) or 1)
            if left <= 0:
                continue
            b = bins.get((x.get("item_code"), x.get("warehouse"))) or {}
            gap = left - max(num(b.get("actual_qty")), 0)
            if gap > 0:
                out.append((x["parent"], gap, max(num(b.get("ordered_qty")), 0)))
    try:
        r._short_lines = out
    except AttributeError:
        pass
    return out


def _value_of(r, names):
    return sum(num(o["undelivered_value"]) for o in _open_orders(r) if o["src_name"] in names)


def order_awaiting_stock(r):
    """Open orders with a line its warehouse does not hold enough stock for."""
    names = {o for o, _, _ in short_lines(r)}
    return len(names), money(r, _value_of(r, names)), _orders_drill(names)


def order_awaiting_purchase(r):
    """Of those, the orders with a short line nothing (or not enough) is on order from a
    supplier for -- the shortfall nobody has bought yet."""
    names = {o for o, gap, on_order in short_lines(r) if on_order < gap}
    return len(names), money(r, _value_of(r, names)), _orders_drill(names)


INSTALL_STEPS = [
    "Open the Sales Order that needs installing.",
    "Click Create, then Project (or open Project, New, and choose the order in Sales Order).",
    "Add the installation work as Tasks on that project, with an expected end date.",
    "Set the project to Completed when the installation is signed off.",
]


def order_awaiting_install(r):
    """Confirmed orders whose installation project, linked to the order, is still open --
    whether or not the goods have gone."""
    projects = _read(r, "Project", {"sales_order": ["is", "set"]},
                     ["name", "sales_order", "status"])
    if not projects:
        return (None, "no project is linked to an order", None,
                setup(r, "No project in ERPNext is linked to a sales order, so nothing says "
                         "which orders are waiting to be installed.", INSTALL_STEPS,
                      "/app/project"))
    waiting = {p["sales_order"] for p in projects
               if (p.get("status") or "") not in ("Completed", "Cancelled")}
    orders = facts(r, "fact_sales_order", {"src_docstatus": 1}, ["src_name", "base_grand_total"])
    names = {o["src_name"] for o in orders if o["src_name"] in waiting}
    value = sum(num(o["base_grand_total"]) for o in orders if o["src_name"] in names)
    return len(names), money(r, value), _orders_drill(names)


def order_awaiting_payment(r):
    """Confirmed orders with an invoice raised against them that is still unpaid: the
    invoice lines name their order, the invoices what is outstanding. The value is what
    those invoices still owe, each invoice once."""
    unpaid = {x["src_name"]: num(x["outstanding_amount"]) for x in facts(
        r, "fact_sales_invoice", {"src_docstatus": 1, "outstanding_amount": [">", 0]},
        ["src_name", "outstanding_amount"])}
    confirmed = {o["src_name"] for o in facts(r, "fact_sales_order", {"src_docstatus": 1},
                                              ["src_name"])}
    names, invoices = set(), set()
    for line in facts(r, "fact_sales_invoice_line", {"src_docstatus": 1,
                                                     "sales_order": ["is", "set"]},
                      ["src_name", "sales_order"]):
        if line["src_name"] in unpaid and line["sales_order"] in confirmed:
            names.add(line["sales_order"])
            invoices.add(line["src_name"])
    return (len(names), f"{money(r, sum(unpaid[i] for i in invoices))} unpaid",
            _orders_drill(names))


# --------------------------------------------------------------------------- stock
OFF_TYPES = ("Transit",)
# A warehouse whose name says goods are not sold from it (Stock & Warehouses' finding,
# and the stock that may cover a promised order: coverage.py).
NOT_FOR_SALE = r"adjust|transit|damage|expired|reject|quarantine|return|scrap"


def off_warehouses(r):
    """Warehouses goods are not sold from: marked Transit, or switched off.
    Returns (names, classified) -- classified is False when no warehouse carries a type
    and none is switched off, i.e. ERPNext records nothing to tell them apart."""
    rows = _read(r, "Warehouse", {"is_group": 0}, ["name", "warehouse_type", "disabled"])
    off = {w["name"] for w in rows
           if (w.get("warehouse_type") or "") in OFF_TYPES or int(w.get("disabled") or 0)}
    classified = any(w.get("warehouse_type") for w in rows) or any(
        int(w.get("disabled") or 0) for w in rows)
    return off, classified


def stock_off_warehouse(r):
    off, classified = off_warehouses(r)
    held = facts(r, "fact_stock_balance", {}, ["warehouse", "stock_value"])
    total = sum(num(x["stock_value"]) for x in held)
    value = sum(num(x["stock_value"]) for x in held if x["warehouse"] in off)
    if not classified:
        return (None, "no warehouse is marked as not for sale", None, setup(
            r, "ERPNext does not say which of your locations goods are not sold from.",
            ["Open Warehouse and pick each location that is not a store: goods in "
             "transit, a holding or adjustment location, damaged or returned goods.",
             "Set its Warehouse Type to Transit and save.",
             "Switch off (tick Disabled) any location no longer used once it is empty."],
            "/app/warehouse"))
    pct = round(100 * value / total) if total else 0
    return value, f"{pct}% of everything", {
        "fact": "fact_stock_balance",
        "filters": {"warehouse": ["in", sorted(off)]} if off else {"warehouse": "-"}}


# --------------------------------------------------------------------------- service
def down_types(r):
    return [t["name"] for t in _read(r, "Issue Type", {"name": ["like", "%down%"]}, ["name"])]


def cases_equipment_down(r):
    """Open cases whose Issue Type says the equipment is out of service."""
    types = down_types(r)
    if not types:
        return (None, "no equipment-down issue type", None, setup(
            r, "ERPNext has no way yet to mark a case where a customer's machine is out of "
               "service.",
            ["Open Issue Type, click New and name it Equipment Down.",
             "On every case where a machine cannot be used, set Issue Type to Equipment Down.",
             "Set its Priority to Urgent, so the wait is measured against the tightest "
             "service level."],
            "/app/issue-type/new"))
    open_ = facts(r, "fact_case", {"is_open": 1}, ["issue_type"])
    n = sum(1 for c in open_ if c["issue_type"] in types)
    return n, f"of {len(open_)} open", {"fact": "fact_case",
                                        "filters": {"is_open": 1, "issue_type": ["in", types]}}


# --------------------------------------------------------------------------- projects
def late_customers(r):
    """Customers waiting on open jobs past their promised date: {customer: [tasks]}, and
    the late tasks whose project names no customer."""
    late = [t for t in facts(r, "fact_task", {"is_open": 1, "days_late": [">", 0]},
                             ["src_name", "subject", "project", "project_name",
                              "exp_end_date", "days_late"])]
    projects = sorted({t["project"] for t in late if t["project"]})
    customer_of = {}
    for part in chunks(projects):
        customer_of.update({p["name"]: p.get("customer") for p in _read(
            r, "Project", {"name": ["in", part]}, ["name", "customer"])})
    by, orphan = {}, []
    for t in late:
        c = customer_of.get(t["project"])
        if c:
            by.setdefault(c, []).append(t)
        else:
            orphan.append(t)
    return by, orphan, late


def owed_by(r):
    """What each customer owes by the ledger (fact_party_balance), not by its open
    invoices: a payment never matched to an invoice is still a payment."""
    out = {}
    for x in facts(r, "fact_party_balance", {"party_type": "Customer", "owed": [">", 0]},
                   ["party", "owed"]):
        out[x["party"]] = out.get(x["party"], 0.0) + num(x["owed"])
    return out


def eng_money_held(r):
    """What customers waiting on late jobs owe us."""
    by, orphan, late = late_customers(r)
    if not late:
        return 0, "no job is past its date", {"fact": "fact_task", "filters": {"is_open": 1}}
    if not by:
        return (None, "late jobs name no customer", None, setup(
            r, "The late jobs' projects do not say which customer they are for.",
            ["Open each Project with work past its date.",
             "Set Customer to the customer the work is for, and save.",
             "Start new installation projects from the customer's Sales Order (Create, "
             "Project) so the customer is set for you."],
            "/app/project?status=Open"))
    owed = owed_by(r)
    held = {c: owed.get(c, 0.0) for c in by}
    total = sum(held.values())
    owing = sorted([c for c in held if held[c] > 0], key=lambda c: -held[c])
    if not owing:
        note = "none of them owes us anything"
    elif len(owing) == 1 or held[owing[0]] >= 0.5 * total:
        note = f"{owing[0]} alone" if len(owing) == 1 else f"{owing[0]}, most of it"
    else:
        note = f"across {len(owing)} customers"
    return total, note, {"fact": "fact_party_balance",
                         "filters": {"party_type": "Customer", "owed": [">", 0],
                                     "party": ["in", owing or ["-"]]}}


FIGURES = {k.key: k for k in (
    Live("order_awaiting_stock", "Orders awaiting stock", "count", order_awaiting_stock,
         "/app/sales-order?status=To%20Deliver%20and%20Bill", source="fact_sales_order"),
    Live("order_awaiting_purchase", "Orders awaiting purchase", "count", order_awaiting_purchase,
         "/app/purchase-order", source="fact_sales_order"),
    Live("order_awaiting_install", "Orders awaiting installation", "count",
         order_awaiting_install, "/app/project?status=Open", source="fact_sales_order"),
    Live("order_awaiting_payment", "Orders awaiting payment", "count", order_awaiting_payment,
         "/app/sales-invoice?status=Overdue", source="fact_sales_invoice"),
    Live("stock_off_warehouse", "Stock outside a sellable warehouse", "currency",
         stock_off_warehouse, "/app/warehouse", source="fact_stock_balance"),
    Live("cases_equipment_down", "Open cases with equipment down", "count", cases_equipment_down,
         "/app/issue", source="fact_case"),
    Live("eng_money_held", "Owed by customers waiting on late jobs", "currency", eng_money_held,
         "/app/project", source="fact_task"),
)}
