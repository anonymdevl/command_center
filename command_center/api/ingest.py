"""Running the ingestion, and proving it landed.

The reconciliation endpoint is the important one. A fact table that does not add
up to its source is worse than no fact table, because people act on it.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Sum

from command_center.api.businesses import default_business_code, loaded_codes, require_manager
from command_center.connectors.registry import connector_for
from command_center.ingest.registry import INGESTORS


@frappe.whitelist()
def run(fact: str | None = None, business_code: str | None = None,
        full: bool = False, limit: int | None = None):
    """Load one fact, or all of them, for one business.

    The business is this site's own, or -- on the hosted service -- one reached over
    its API with its read-only service account (connectors/remote.py). Either way the
    facts are this platform's own derived tables, rebuilt from the source on demand;
    nothing in them is a second system of record.
    """
    require_manager()
    code = business_code or default_business_code()
    if not code:
        frappe.throw("No business is registered yet. Add one under Connected Business.")
    # Building a derived table is a system act. See BusinessConnector.as_system.
    conn = connector_for(code).as_system()
    full = frappe.parse_json(full) if isinstance(full, str) else bool(full)
    with business_lock(code) as got:
        if not got:
            frappe.throw(f"{conn.name} is being loaded already. Try again in a few minutes.")
        try:
            return load_business(conn, facts=[fact] if fact else None, full=full,
                                 limit=int(limit) if limit else None, raise_errors=True)
        finally:
            # A person is waiting to see what the load brought: nothing kept from
            # before it is shown, not even while the new figures are read (speed.py).
            from command_center import speed
            speed.data_changed(code, hard=True)


def load_business(conn, facts=None, full: bool = False, limit: int | None = None,
                  raise_errors: bool = False) -> dict:
    """Every fact (or the ones named) for one business, from its own watermarks.

    One definition for the button, the daily load, the fifteen-minute poll of a peer
    and the weekly rebuild. A failing fact is logged and does not stop the others --
    one broken grain should not leave every figure stale -- unless the caller is a
    person who asked for it (raise_errors), who should see the failure.
    """
    from command_center.ingest.base import resolve_as_of
    from command_center.ingest.company import scoped

    # One company of an ERPNext that keeps several (ingest/company.py); unchanged for one.
    conn = scoped(conn)
    as_of = resolve_as_of(conn)
    names = facts or list(INGESTORS)
    out = []
    for f in names:
        cls = INGESTORS.get(f)
        if not cls:
            frappe.throw(f"Unknown fact '{f}'. Known: {', '.join(INGESTORS)}")
        try:
            out.append(cls().load(conn, limit=limit, as_of=as_of, full=full))
        except Exception:
            if raise_errors:
                raise
            frappe.log_error(title=f"Command Center ingest: {f} ({conn.code})",
                             message=frappe.get_traceback())
            out.append({"fact": f, "business": conn.code, "failed": True})
    frappe.cache().delete_value(f"cc:alerts:evaluated:{conn.code}")
    return {"business": conn.code, "as_of": str(as_of), "loaded": out}


@frappe.whitelist()
def run_all(full: bool = False):
    """Every business, every fact: what deploy.sh and host.sh run. A failing business
    or fact is logged and reported, and stops nothing else."""
    require_manager()
    full = frappe.parse_json(full) if isinstance(full, str) else bool(full)
    out = []
    for code in loaded_codes():
        try:
            conn = connector_for(code).as_system()
            with business_lock(code) as got:
                out.append(load_business(conn, full=full) if got else
                           {"business": code, "skipped": "a load is already running"})
        except Exception as e:
            frappe.log_error(title=f"Command Center ingest: {code}", message=frappe.get_traceback())
            out.append({"business": code, "failed": f"{type(e).__name__}: {str(e)[:300]}"})
    for row in out:
        bad = [x["fact"] for x in row.get("loaded", []) if x.get("failed")]
        print(f"{row.get('business')}: "
              + (row.get("failed") or row.get("skipped") or
                 f"{sum(x.get('rows', 0) for x in row.get('loaded', []))} rows loaded"
                 + (f"; FAILED: {', '.join(bad)} (see Error Log)" if bad else "")))
    return out


# What the platform reads on a business's site, for the access check. Child tables name
# their parent: Frappe checks a child's permission through it.
READS = [
    ("Sales Invoice", None), ("Sales Invoice Item", "Sales Invoice"),
    ("Payment Entry", None), ("Payment Entry Reference", "Payment Entry"),
    ("Purchase Invoice", None), ("Purchase Invoice Item", "Purchase Invoice"),
    ("Sales Order", None), ("Purchase Order", None), ("Quotation", None),
    ("Bin", None), ("Item", None), ("Customer", None), ("Supplier", None),
    ("Company", None), ("Task", None), ("Project", None), ("Employee", None),
    ("Department", None), ("Issue", None), ("User", None), ("Has Role", "User"),
    ("Version", None), ("Workflow", None), ("Journal Entry", None), ("GL Entry", None),
    ("Journal Entry Account", "Journal Entry"),
]
# Roles that can change records. The platform's user on a business's site must hold
# none of them: it reads, and only reads.
WRITE_ROLES = {"System Manager", "Accounts User", "Accounts Manager", "Sales User",
               "Sales Manager", "Purchase User", "Purchase Manager", "Stock User",
               "Stock Manager", "Item Manager", "HR User", "HR Manager", "Projects User",
               "Projects Manager", "Support Team", "Manufacturing User", "Maintenance User",
               "Website Manager", "Administrator"}


def erp_members(business_code: str, role: str) -> set:
    """Who may open the platform from a business's ERPNext: its enabled users holding
    `role` there, as lower-cased emails (and user names, which are emails on Frappe).

    The business's own ERPNext decides, so adding a person is giving them the role in
    their desk -- no step on this platform. Read with the service account (only ingest
    takes one); api/sso.py asks at every sign-in and its 15-minute sync asks again, so
    taking the role away there takes the platform away too.
    """
    conn = connector_for(business_code).as_system()
    holders = {r["parent"] for r in conn.get_list(
        "Has Role", filters={"role": role, "parenttype": "User"}, fields=["parent"],
        limit=5000, parent_doctype="User") if r.get("parent")}
    if not holders:
        return set()
    users = conn.get_list("User", filters={"name": ["in", sorted(holders)], "enabled": 1},
                          fields=["name", "email"], limit=5000)
    out = set()
    for u in users:
        for v in (u.get("email"), u.get("name")):
            if v:
                out.add(str(v).strip().lower())
    return out


def probe(business_code: str):
    """Who the service account is on the business's site, and its companies: the first
    proof a registration works (install.register_business)."""
    conn = connector_for(business_code).as_system()
    who = conn._call("frappe.auth.get_logged_user")
    companies = conn.get_list("Company", fields=["name", "default_currency"], limit=20,
                              order_by="creation asc")
    return who, companies


@frappe.whitelist()
def check_access(business_code: str | None = None):
    """Can the platform's service account read everything it needs on a business's
    site -- and is it really read-only? Run by host.sh after registering a business;
    open it again whenever a figure says "could not be read":

        bench --site <site> execute command_center.api.ingest.check_access
    """
    require_manager()
    code = business_code or default_business_code()
    conn = connector_for(code).as_system()
    rows = []
    for doctype, parent in READS:
        try:
            got = conn.get_list(doctype, fields=["name"], limit=1, parent_doctype=parent)
            rows.append({"doctype": doctype, "readable": True, "sample": bool(got)})
        except Exception as e:
            rows.append({"doctype": doctype, "readable": False, "why": str(e)[:200]})
    me = None
    roles = None
    try:
        me = conn._call("frappe.auth.get_logged_user")
        roles = sorted({r["role"] for r in conn.get_list(
            "Has Role", filters={"parent": me, "parenttype": "User"}, fields=["role"],
            limit=500, parent_doctype="User")})
    except Exception:
        pass
    writes = sorted(set(roles or []) & WRITE_ROLES)
    out = {"business": code, "reads_as": me, "roles": roles,
           "unreadable": [r["doctype"] for r in rows if not r["readable"]],
           "read_only": (not writes) if roles is not None else None,
           "write_capable_roles": writes, "checked": rows}
    print(f"{code}: reads as {me}; "
          f"{len(rows) - len(out['unreadable'])} of {len(rows)} doctypes readable"
          + (f"; NOT readable: {', '.join(out['unreadable'])}" if out["unreadable"] else ""))
    if roles is None:
        print("   its roles could not be read -- confirm on that site that it holds read-only roles")
    elif writes:
        print(f"   WARNING: it holds roles that can change records: {', '.join(writes)}. "
              f"Give it a read-only role instead.")
    else:
        print(f"   read-only: holds {', '.join(roles) or 'no roles'}")
    return out


@frappe.whitelist()
def status():
    require_manager()
    return frappe.get_all(
        "Command Center Ingest State",
        fields=["fact", "business_code", "last_src_modified", "as_of_date",
                "last_run", "rows_loaded", "status", "last_error"],
        order_by="fact asc")


@frappe.whitelist()
def reconcile(business_code: str | None = None):
    """Do the facts add up to the source?

    Every figure this platform shows is derived. The only defence against a
    derivation drifting from the truth is to check it against the source and say
    so out loud — which is why this is an endpoint the interface can call, not a
    test that ran once on a laptop.
    """
    require_manager()
    code = business_code or default_business_code()
    if not code:
        frappe.throw("No business is registered yet.")
    # Building a derived table is a system act. See BusinessConnector.as_system.
    from command_center.ingest.company import scoped
    conn = scoped(connector_for(code).as_system())

    checks = []

    src_total = _source_sum(conn, "Sales Invoice", "outstanding_amount",
                            {"docstatus": 1, "outstanding_amount": [">", 0]})
    src_count = conn.get_count("Sales Invoice", {"docstatus": 1, "outstanding_amount": [">", 0]})

    f_total, f_count = _fact_sum(
        "Command Center Fact Sales Invoice", "outstanding_amount", conn.code,
        extra={"src_docstatus": 1, "unpaid_only": True})
    checks.append(_check("Outstanding receivables", src_total, f_total))
    checks.append(_check("Unpaid invoice count", src_count, f_count, money=False))

    src_rev = _source_sum(conn, "Sales Invoice Item", "base_net_amount", {"docstatus": 1},
                          parent="Sales Invoice")
    f_rev, _ = _fact_sum("Command Center Fact Sales Invoice Line",
                         "base_net_amount", conn.code,
                         extra={"src_docstatus": 1})
    checks.append(_check("Invoiced revenue (lines)", src_rev, f_rev))

    src_alloc = _source_sum(conn, "Payment Entry Reference", "allocated_amount",
                            {"docstatus": 1}, parent="Payment Entry")
    f_alloc, _ = _fact_sum("Command Center Fact Payment Allocation",
                           "allocated_amount", conn.code)
    checks.append(_check("Cash applied to documents", src_alloc, f_alloc))

    return {"business": conn.code,
            "all_reconciled": all(c["reconciled"] for c in checks),
            "checks": checks}


def _fact_sum(target, measure, business_code, extra=None):
    """SUM and COUNT over a fact table, via the query builder.

    Not `fields=["sum(x) as y"]`: Frappe v16 rejects SQL function strings in a
    select list, and the rejection is a ValidationError at request time rather
    than something a test would catch on an empty table.
    """
    extra = extra or {}
    t = frappe.qb.DocType(target)
    q = (frappe.qb.from_(t)
         .select(Sum(t[measure]), Count(t.name))
         .where(t.business_code == business_code))
    if "src_docstatus" in extra:
        q = q.where(t.src_docstatus == extra["src_docstatus"])
    if extra.get("unpaid_only"):
        q = q.where(t[measure] > 0)
    row = q.run()
    if not row or not row[0]:
        return 0, 0
    return (row[0][0] or 0), (row[0][1] or 0)


def _source_sum(conn, doctype, field, filters, parent=None):
    """SUM of one column at the source, in whichever dialect the source's Frappe speaks.

    v16 takes an aggregate as {"SUM": field} and rejects SQL function strings; v15 and
    earlier take only the string. A peer may be on either (Gigmann may move to v16 while
    the platform is live), so this goes through grouped_read, the one place both are
    spoken (grouped by docstatus, which every doctype has, then added up).
    """
    from command_center.kpi.live_departments import grouped_read
    rows = grouped_read(conn, doctype, filters, "docstatus", [("sum", field, "total")],
                        parent=parent)
    return sum(float(r.get("total") or 0) for r in rows)


def source_figures(business_code: str, as_of) -> dict:
    """What the business's ERPNext says right now, for the reconciliation check
    (api/audit.py): each by the same rule the platform's figure uses. Read as the system
    -- the read-only service account every load uses -- so like is compared with like.
    Reads only, every one an aggregate or a count, except the open sales orders, whose
    undelivered value has to be worked out per order."""
    from command_center.ingest.company import scoped
    from command_center.ingest.operations import CLOSED_ORDER
    from command_center.kpi.live_departments import grouped_read

    conn = scoped(connector_for(business_code).as_system())
    total = lambda dt, field, f, parent=None: _source_sum(conn, dt, field, f, parent)  # noqa: E731
    count = lambda dt, f=None: int(conn.get_count(dt, f or {}) or 0)  # noqa: E731
    over_90 = frappe.utils.add_days(as_of, -90)
    si_open = {"docstatus": 1, "outstanding_amount": [">", 0]}
    pi_open = {"docstatus": 1, "outstanding_amount": [">", 0]}
    out = {
        "si_unpaid_count": count("Sales Invoice", si_open),
        "si_unpaid_sum": total("Sales Invoice", "outstanding_amount", si_open),
        "si_over_90": total("Sales Invoice", "outstanding_amount",
                            {**si_open, "due_date": ["<", over_90]}),
        "pi_unpaid_count": count("Purchase Invoice", pi_open),
        "pi_unpaid_sum": total("Purchase Invoice", "outstanding_amount", pi_open),
        "si_count": count("Sales Invoice", {"docstatus": 1}),
        "si_total": total("Sales Invoice", "base_grand_total", {"docstatus": 1}),
        "si_net": total("Sales Invoice", "base_net_total", {"docstatus": 1}),
        "pe_received": total("Payment Entry", "total_allocated_amount",
                             {"docstatus": 1, "payment_type": "Receive"}),
        "stock_value": total("Bin", "stock_value", {}),
        "stock_lines": count("Bin"),
        "employees_active": count("Employee", {"status": "Active"}),
        "tasks": count("Task"),
        "cases": count("Issue"),
    }
    for party_type, sign, pay in (("Customer", 1, "Receive"), ("Supplier", -1, "Pay")):
        gl = grouped_read(conn, "GL Entry", {"is_cancelled": 0, "party_type": party_type},
                          "party_type", [("sum", "debit", "debit_total"),
                                         ("sum", "credit", "credit_total")])
        out[f"{party_type.lower()}_ledger"] = sign * sum(
            float(r.get("debit_total") or 0) - float(r.get("credit_total") or 0) for r in gl)
        unmatched = {"docstatus": 1, "party_type": party_type, "payment_type": pay,
                     "unallocated_amount": [">", 0]}
        out[f"{party_type.lower()}_unmatched"] = total("Payment Entry", "unallocated_amount", unmatched)
        out[f"{party_type.lower()}_unmatched_count"] = count("Payment Entry", unmatched)
    from command_center.ingest import order_lines
    orders = conn.get_list("Sales Order",
                           filters={"docstatus": 1, "status": ["not in", sorted(CLOSED_ORDER)]},
                           fields=["name", "base_grand_total", "base_net_total", "per_delivered",
                                   "per_billed"],
                           order_by="name asc", limit=500000)
    # Line by line, as the fact is (never value times ERPNext's delivered percentage).
    left = order_lines.order_values(conn, order_lines.SALES, orders, "per_delivered")
    out["order_book"] = round(sum(v["left"] for v in left.values()), 2)
    out["order_book_count"] = len(orders)
    return out


def changed_since(business_code: str, doctypes, since) -> dict:
    """How many records of each doctype were changed in the business's ERPNext after
    `since` -- the reconciliation check's first explanation for a difference."""
    from command_center.ingest.company import scoped
    conn = scoped(connector_for(business_code).as_system())
    out = {}
    for dt in doctypes:
        try:
            out[dt] = int(conn.get_count(dt, {"modified": [">", since]}) or 0)
        except Exception:
            out[dt] = None
    return out


def _check(label, source, fact, money=True, tolerance=0.01):
    source = float(source or 0)
    fact = float(fact or 0)
    diff = fact - source
    return {"check": label, "source": source, "fact": fact, "difference": diff,
            "reconciled": abs(diff) <= (tolerance if money else 0)}


LOG = "Command Center Load Log"
KEEP_LOG_DAYS = 90

# What each fact is, in the words Business Health uses.
FACT_WORDS = {
    "fact_sales_invoice": "Sales invoices",
    "fact_sales_invoice_line": "Invoice lines",
    "fact_payment_allocation": "Payments received",
    "fact_purchase_invoice": "Supplier invoices",
    "fact_purchase_invoice_line": "Supplier invoice lines",
    "fact_stock_balance": "Stock on hand",
    "fact_sales_order": "Sales orders",
    "fact_task": "Jobs and tasks",
    "fact_person": "People",
    "fact_case": "Customer issues",
    "fact_party_balance": "Balances owed, by the ledger",
}


@frappe.whitelist(methods=["POST"])
def refresh(business_code: str | None = None):
    """Load what has changed since the last run, now, for Business Health's button.

    Incremental, so it reads only records modified since each fact's watermark and is
    quick enough to run while the manager waits. A full rebuild stays a deliberate call
    to run(full=True). The alerts are re-evaluated on their next read.
    """
    require_manager()
    return run(business_code=business_code)


@frappe.whitelist()
def history(business_code: str | None = None, limit: int = 30):
    """Each fact's current state, and the latest loads, for Business Health."""
    require_manager()
    filters = {"business_code": business_code} if business_code and business_code != "__all__" else {}
    states = frappe.get_all("Command Center Ingest State", filters=filters,
                            fields=["fact", "business_code", "as_of_date", "last_run",
                                    "rows_loaded", "status", "last_error"], order_by="fact asc")
    try:
        loads = frappe.get_all(LOG, filters=filters,
                               fields=["fact", "started", "seconds", "status", "rows_loaded",
                                       "mode", "trigger", "run_by", "error"],
                               order_by="started desc", limit=max(1, min(int(limit or 30), 200)))
    except Exception:
        loads = []  # not migrated yet: the states still say when each fact last loaded
    for row in states + loads:
        row["what"] = FACT_WORDS.get(row["fact"], row["fact"])
        if row.get("run_by"):
            row["run_by"] = frappe.utils.get_fullname(row["run_by"])
    return {"facts": states, "loads": loads}


def prune_load_log():
    """Daily: the load history is kept for ninety days."""
    try:
        frappe.db.delete(LOG, {"started": ["<", frappe.utils.add_days(frappe.utils.now(), -KEEP_LOG_DAYS)]})
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()


def scheduled_load():
    """Daily incremental load of every fact for every business.

    Runs without a user, so it takes system connectors directly rather than the
    management-only entry point: the local business read as the system, a peer read
    with its read-only service account. Failures are logged per fact and per business
    and stop nothing else.
    """
    _load_all(full=False)


def scheduled_full_load():
    """Weekly: rebuild every peer's facts from scratch.

    A peer is polled by its modified stamps (changes.refresh_peers), which sees every
    edit, submission and cancellation but not a deletion -- a deleted draft leaves no
    row to be modified. A full load purges and reloads, so whatever was deleted on the
    peer in the week is gone here too. The local business has the change feed and its
    own daily load, and is not rebuilt.
    """
    _load_all(full=True, remote_only=True)


def _load_all(full: bool, remote_only: bool = False):
    for code in loaded_codes():
        try:
            conn = connector_for(code)
            if remote_only and conn.is_local:
                continue
            # No user runs the scheduler, so there is no identity to scope this to.
            conn = conn.as_system()
        except Exception:
            frappe.log_error(title=f"Command Center ingest: {code}",
                             message=frappe.get_traceback())
            continue
        with business_lock(code) as got:
            if got:
                load_business(conn, full=full)


def poll_peers():
    """Every two minutes (changes.refresh_peers): each business on another site is
    asked, fact by fact, for the documents modified after that fact's stored watermark
    -- one small request per fact when nothing changed -- and only those are reloaded;
    documents cancelled since are taken out (Ingestor.load). Read with the peer's
    read-only service account. If one peer is unreachable the others still refresh: a
    group of businesses should not lose its whole view because one server is down.
    """
    from frappe.utils import now_datetime

    from command_center.connectors.base import ConnectorError

    was_down = {b.business_code: b.status == "Unreachable"
                for b in frappe.get_all("Connected Business", fields=["business_code", "status"])}
    for code in loaded_codes():
        try:
            conn = connector_for(code, acting_user="Administrator")
            if conn.is_local:
                continue  # the local business has its change feed and the daily load
            # No user runs the scheduler: a system read, i.e. the service account.
            system = conn.as_system()
            with business_lock(code) as got:
                if not got:
                    continue  # a load of this business is already running
                load_business(system)
            frappe.db.set_value("Connected Business", conn.business.name, "last_sync",
                                now_datetime(), update_modified=False)
            frappe.db.commit()
            _warm(code)
        except (ConnectorError, ValueError) as e:
            # Polled every two minutes: a business that was already down before this
            # attempt is not logged again (its going down was), so the error log is not
            # filled 720 times a day while it stays down. Anything else is always logged.
            from command_center.connectors.base import BusinessUnreachable, RequestRefused
            already_down = (isinstance(e, BusinessUnreachable) and not isinstance(e, RequestRefused)
                            and was_down.get(code))
            if not already_down:
                frappe.log_error(title=f"Command Center peer refresh: {code}", message=str(e))
    frappe.db.commit()


def _warm(code):
    """The screens people have been looking at, read again now that the business is
    up to date, so their next look (or the minute's refresh) is answered at once."""
    try:
        from command_center import speed
        speed.warm(code)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title=f"Command Center warm {code}", message=frappe.get_traceback())


class business_lock:
    """One load per business at a time. The fifteen-minute poll, the daily load, the
    weekly rebuild and a manager's Refresh can otherwise overlap on a slow peer, and
    two loads purging and inserting the same rows is one too many."""

    def __init__(self, code):
        self.lock = frappe.cache().lock(f"cc:ingest:{code}", timeout=3600)
        self.got = False

    def __enter__(self):
        try:
            self.got = self.lock.acquire(blocking=False)
        except Exception:
            self.got = True  # no lock available: load anyway, as before
        return self.got

    def __exit__(self, *exc):
        if self.got:
            try:
                self.lock.release()
            except Exception:
                pass
        return False


@frappe.whitelist()
def seed_demo(dry_run: bool = True):
    """Top up the thin part of the demonstration extract.

    Defaults to a dry run: it reports what it would create and creates nothing. A
    seeder that writes on its first accidental call is a seeder that eventually
    writes into the wrong site.
    """
    require_manager()
    from command_center.demo import seed
    return seed.run(dry_run=dry_run)


@frappe.whitelist()
def unseed_demo():
    """Remove exactly what seed_demo created."""
    require_manager()
    from command_center.demo import seed
    return seed.remove()
