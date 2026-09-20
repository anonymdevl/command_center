"""Running the ingestion, and proving it landed.

The reconciliation endpoint is the important one. A fact table that does not add
up to its source is worse than no fact table, because people act on it.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count, Sum

from command_center.api.businesses import require_manager
from command_center.connectors.registry import connector_for, local_connector
from command_center.ingest.registry import INGESTORS


@frappe.whitelist()
def run(fact: str | None = None, business_code: str | None = None,
        full: bool = False, limit: int | None = None):
    """Load one fact, or all of them, for the local business.

    Only the local business is ingested. A peer's figures are read from the site
    that computed them, so there is no version of this that reaches across sites
    and quietly copies someone else's ledger here.
    """
    require_manager()

    conn = connector_for(business_code) if business_code else local_connector()
    # Building a derived table is a system act. See BusinessConnector.as_system.
    conn = conn.as_system() if conn else conn
    if not conn:
        frappe.throw("No local business is registered.")
    if not conn.is_local:
        frappe.throw(
            f"{conn.name} is on another site, which computes its own figures. "
            f"Ingestion only ever runs against the business whose data is here."
        )

    from command_center.ingest.base import resolve_as_of
    as_of = resolve_as_of(conn)

    names = [fact] if fact else list(INGESTORS)
    out = []
    for f in names:
        cls = INGESTORS.get(f)
        if not cls:
            frappe.throw(f"Unknown fact '{f}'. Known: {', '.join(INGESTORS)}")
        out.append(cls().load(conn, limit=limit, as_of=as_of,
                              full=frappe.parse_json(full) if isinstance(full, str) else bool(full)))
    return {"as_of": str(as_of), "loaded": out}


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
    conn = connector_for(business_code) if business_code else local_connector()
    # Building a derived table is a system act. See BusinessConnector.as_system.
    conn = conn.as_system() if conn else conn
    if not conn:
        frappe.throw("No local business is registered.")

    checks = []

    src = conn.get_list("Sales Invoice",
                        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
                        fields=[{"SUM": "outstanding_amount"}, {"COUNT": "name"}])
    src_total = _first(src, "SUM(`outstanding_amount`)")
    src_count = _first(src, "COUNT(`name`)")

    f_total, f_count = _fact_sum(
        "Command Center Fact Sales Invoice", "outstanding_amount", conn.code,
        extra={"src_docstatus": 1, "unpaid_only": True})
    checks.append(_check("Outstanding receivables", src_total, f_total))
    checks.append(_check("Unpaid invoice count", src_count, f_count, money=False))

    src_rev = conn.get_list("Sales Invoice Item",
                            filters={"docstatus": 1},
                            fields=[{"SUM": "base_net_amount"}])
    f_rev, _ = _fact_sum("Command Center Fact Sales Invoice Line",
                         "base_net_amount", conn.code,
                         extra={"src_docstatus": 1})
    checks.append(_check("Invoiced revenue (lines)",
                         _first(src_rev, "SUM(`base_net_amount`)"), f_rev))

    src_alloc = conn.get_list("Payment Entry Reference",
                              filters={"docstatus": 1},
                              fields=[{"SUM": "allocated_amount"}])
    f_alloc, _ = _fact_sum("Command Center Fact Payment Allocation",
                           "allocated_amount", conn.code)
    checks.append(_check("Cash applied to documents",
                         _first(src_alloc, "SUM(`allocated_amount`)"), f_alloc))

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


def _first(rows, key):
    if not rows:
        return 0
    row = rows[0]
    return row.get(key) or row.get(key.replace("`", "")) or 0


def _check(label, source, fact, money=True, tolerance=0.01):
    source = float(source or 0)
    fact = float(fact or 0)
    diff = fact - source
    return {"check": label, "source": source, "fact": fact, "difference": diff,
            "reconciled": abs(diff) <= (tolerance if money else 0)}


def scheduled_load():
    """Daily incremental load of every fact for the local business.

    Runs without a user, so it uses the local connector directly rather than the
    management-only entry point. Failures are logged per fact and do not stop the
    others — one broken grain should not leave every figure stale.
    """
    conn = local_connector()
    if not conn:
        return
    # No user runs the scheduler, so there is no identity to scope this to.
    conn = conn.as_system()
    from command_center.ingest.base import resolve_as_of
    as_of = resolve_as_of(conn)
    for name, cls in INGESTORS.items():
        try:
            cls().load(conn, as_of=as_of)
        except Exception:
            frappe.log_error(title=f"Command Center ingest: {name}",
                             message=frappe.get_traceback())


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
