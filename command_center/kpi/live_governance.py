"""Governance figures: approvals, access, record quality, findings and deadlines.

The figures behind Business Health's last three questions, the control score, Internal
Audit's findings and corrective actions, and Risk and Compliance's deadlines. Each is
read from the business's own ERPNext (or, for the alerts, this platform's own table),
in the same shape as every other live figure (kpi/live.py), and registered there.

Where ERPNext offers a place to record something but nothing is recorded there yet --
findings as Non Conformance, corrective actions as Quality Action, obligations and
deadlines as Contracts that require fulfilment -- the figure raises NeedsSetup with a
guide that says what to record and where (command_center/guides.py), never a sample.

    score_approvals   of the purchase orders and payments whose approval steps are in the
                      change log, the share where someone other than the raiser took a step
    score_records     of the invoice lines and stock lines the figures rely on, the share
                      carrying a cost (invoice lines) or a valuation (stock lines)
    score_access      of the active accounts, the share holding no conflicting pair of duties
    control_score     the plain average of the six Business Health questions scored
    alerts_open       the open alerts (the alert engine's material exceptions)
    findings_open     open Non Conformance records
    findings_repeat   open findings on a procedure that already had an earlier finding
    actions_overdue   open corrective actions (Quality Action resolutions) past their date
    deadlines_*       Contracts requiring fulfilment, not fulfilled, by deadline
    versions_deletable  the roles that may delete an entry of the change log

Importing this module touches no frappe, like kpi/live.py.
"""

from __future__ import annotations

from command_center.kpi.live import (CONFLICTS, Live, NeedsSetup, _read, _staff)

SCORE_KEYS = ("score_deliver", "score_paid", "score_paperwork")
QUESTIONS = (("score_deliver", "Can we deliver what we sold?"),
             ("score_paid", "Are we getting paid?"),
             ("score_paperwork", "Is the paperwork finished?"),
             ("score_approvals", "Were the right people asked?"),
             ("score_records", "Are our records clean?"),
             ("score_access", "Who can see what?"))
WATCH = 60   # a question scoring below this is "going badly", as the tiles colour it
HEALTHY = 80  # and at or above this "Healthy" (legacy/home.js toneOf: Act / Watch / Healthy)


def _setup(r, text, steps, path):
    from command_center.guides import needs_setup
    raise NeedsSetup(needs_setup(r.code, text, steps, path))


def _today():
    import frappe
    return frappe.utils.getdate(frappe.utils.today())


# --------------------------------------------------------------------------- approvals
def approval_record(r) -> dict:
    """Submitted purchase orders and payments whose approval steps the change log holds:
    how many, and how many had every step taken by the account that raised them (the
    same test as kpi/live.self_approved), with when it was read. Worked out behind the
    screens (kpi/history.py): the change log is the largest table on a site."""
    from command_center.kpi import history
    got = history.summary(r)
    return {"decided": got["data"]["decided"], "alone": got["data"]["alone"],
            "status": history.status(got)}


def score_approvals(r):
    got = approval_record(r)
    if not got["decided"]:
        _setup(r, "No approval steps are recorded on purchase orders or payments, so there "
                  "is nothing to check who approved what.",
               ["In ERPNext open Workflow and add one for Purchase Order (and for Payment "
                "Entry): its states, and for each step the role allowed to take it.",
                "Leave Allow Self Approval unticked on the approving steps, so whoever raised "
                "a document cannot approve it.",
                "Every approval taken from then on is kept in the document's history and "
                "counted here."], "/app/workflow/new")
    ok = got["decided"] - got["alone"]
    return (round(100 * ok / got["decided"], 4),
            f"of {got['decided']:,} approved purchase orders and payments had someone other "
            f"than the raiser approve them", {"href": "/app/version"}, got["status"], got["decided"])


# --------------------------------------------------------------------------- records
def score_records(r):
    """Invoice lines carrying a cost and stock lines carrying a valuation, of all of them:
    the two gaps that make a margin or a stock value wrong without anyone seeing it."""
    import frappe

    from command_center.facts.schema import FACTS
    scope = {"business_code": r.code} if r.code else {}
    lines = frappe.db.count(FACTS["fact_sales_invoice_line"], {**scope, "src_docstatus": 1})
    costed = frappe.db.count(FACTS["fact_sales_invoice_line"],
                             {**scope, "src_docstatus": 1, "has_cost": 1})
    stock = frappe.db.count(FACTS["fact_stock_balance"], {**scope, "actual_qty": [">", 0]})
    valued = frappe.db.count(FACTS["fact_stock_balance"],
                             {**scope, "actual_qty": [">", 0], "has_valuation": 1})
    total = lines + stock
    if not total:
        return None, "no invoice or stock lines loaded yet", {"fact": "fact_stock_balance",
                                                              "filters": {}}
    missing = (lines - costed) + (stock - valued)
    return (round(100 * (costed + valued) / total, 4),
            f"of {total:,} invoice and stock lines carry a cost or valuation; "
            f"{missing:,} do not",
            {"fact": "fact_stock_balance", "filters": {"actual_qty": [">", 0], "has_valuation": 0}},
            None, total)


# --------------------------------------------------------------------------- access
def _role_sets(r):
    roles = sorted({x for a, b, _ in CONFLICTS for x in (*a, *b)})
    enabled = {u["name"] for u in _staff(r) if u["enabled"]}
    held = {u: set() for u in enabled}
    for row in r.all("Has Role", filters={"parenttype": "User", "role": ["in", roles]},
                     fields=["parent", "role"], limit=20000, parent="User"):
        if row.get("parent") in held:
            held[row["parent"]].add(row.get("role"))
    return held


def score_access(r):
    held = _role_sets(r)
    if not held:
        return None, "no active accounts"
    clash = sum(1 for roles in held.values()
                if any(roles & set(a) and roles & set(b) for a, b, _ in CONFLICTS))
    return (round(100 * (len(held) - clash) / len(held), 4),
            f"of {len(held):,} active accounts hold no conflicting pair of duties; "
            f"{clash:,} do", None, None, len(held))


# --------------------------------------------------------------------------- the score
def control_score(r):
    """The plain average of the Business Health questions scored -- the figure Home's
    gauge and Business Health's headline show. A question that cannot be scored yet is
    left out and said so, never counted as zero."""
    from command_center.kpi.engine import evaluate_set
    got = {k: (v or {}).get("value") for k, v in evaluate_set(list(SCORE_KEYS), r.code).items()}
    from command_center.connectors.base import BusinessUnreachable
    away = 0
    for key, fn in (("score_approvals", score_approvals), ("score_records", score_records),
                    ("score_access", score_access)):
        try:
            got[key] = fn(r)[0]
        except NeedsSetup:
            got[key] = None
        except BusinessUnreachable:
            # The questions read from ERPNext wait for it; the rest still count.
            got[key], away = None, away + 1
    scored = [float(v) for v in got.values() if v is not None]
    if not scored:
        return None, "no question can be scored yet"
    low = sum(1 for v in scored if v < WATCH)
    return (round(sum(scored) / len(scored)),
            f"the average of {len(scored)} of 6 questions; {low} below {WATCH}%"
            + (f"; {away} wait for ERPNext to answer" if away else ""))


# --------------------------------------------------------------------------- alerts
def alerts_open(r):
    import frappe

    from command_center.alerts.engine import DOCTYPE, OPEN
    filters = {"status": ["in", list(OPEN)], "resolved_on": ["is", "not set"]}
    if r.code:
        filters["business_code"] = r.code
    rows = frappe.get_all(DOCTYPE, filters=filters, fields=["status", "deferred_until"],
                          limit=1000)
    today = _today()
    n = sum(1 for a in rows if not (a.status == "Deferred" and a.deferred_until
                                    and frappe.utils.getdate(a.deferred_until) > today))
    return n, "open alerts from Business Health"


# --------------------------------------------------------------------------- findings
FINDING_STEPS = [
    "In ERPNext open Quality Procedure and add one for each process you audit "
    "(for example Purchasing, Stock count, Credit control).",
    "Record each finding as a Non Conformance: the subject, the procedure, what was found, "
    "and the corrective and preventive action.",
    "Set its status to Resolved when it is fixed; open findings are counted here.",
]


def _findings(r):
    if not r.has("Non Conformance"):
        _setup(r, "This ERPNext has no Non Conformance list, where audit findings are kept.",
               ["Ask your ERPNext administrator to enable the Quality module for your "
                "role (Quality Manager)."] + FINDING_STEPS, "/app/non-conformance")
    if not r.count("Non Conformance"):
        _setup(r, "No audit findings are recorded in ERPNext yet.", FINDING_STEPS,
               "/app/non-conformance/new")
    return _read(r, "Non Conformance", {"status": ["!=", "Cancelled"]},
                 ["name", "status", "procedure", "creation"], limit=20000)


def findings_open(r):
    rows = _findings(r)
    n = sum(1 for x in rows if x.get("status") == "Open")
    return n, f"of {len(rows):,} recorded", {"href": "/app/non-conformance?status=Open"}


def findings_repeat(r):
    rows = sorted(_findings(r), key=lambda x: str(x.get("creation") or ""))
    seen, repeat = set(), 0
    for x in rows:
        p = x.get("procedure")
        if p and p in seen and x.get("status") == "Open":
            repeat += 1
        if p:
            seen.add(p)
    return repeat, "open, on a procedure found wanting before", {
        "href": "/app/non-conformance?status=Open"}


ACTION_STEPS = [
    "In ERPNext open Quality Action and add one for each finding to be fixed.",
    "In its resolutions, write the problem, what will be done, who is responsible and "
    "the date it must be completed by.",
    "Mark each resolution Completed when it is done; open ones past their date are "
    "counted here.",
]


def actions_overdue(r):
    if not r.has("Quality Action"):
        _setup(r, "This ERPNext has no Quality Action list, where corrective actions are kept.",
               ACTION_STEPS, "/app/quality-action")
    if not r.count("Quality Action"):
        _setup(r, "No corrective actions are recorded in ERPNext yet.", ACTION_STEPS,
               "/app/quality-action/new")
    rows = _read(r, "Quality Action Resolution", {"status": "Open"},
                 ["parent", "status", "completion_by"], limit=20000, parent="Quality Action")
    import frappe
    today = _today()
    late = [x for x in rows if x.get("completion_by")
            and frappe.utils.getdate(x["completion_by"]) < today]
    return len(late), f"of {len(rows):,} open", {"href": "/app/quality-action?status=Open"}


# --------------------------------------------------------------------------- deadlines
DEADLINE_STEPS = [
    "In ERPNext open Contract and add one for each licence, permit, statutory filing or "
    "warranty you owe: the party is the regulator, customer or supplier concerned.",
    "Tick Requires Fulfilment and set the Fulfilment Deadline.",
    "Set Fulfilment Status to Fulfilled when it is done; the rest are counted here by "
    "how soon they fall due.",
]


def deadlines(r) -> list:
    """Open obligations: Contracts that require fulfilment and are not fulfilled, each
    with its deadline. Read once per business per ten minutes (three tiles and a table
    ask for it)."""
    import frappe
    key = f"cc:live:deadlines:{r.code or 'local'}"
    hit = frappe.cache().get_value(key)
    if hit is not None:
        return hit
    if not r.has("Contract") or not r.count("Contract", {"requires_fulfilment": 1}):
        _setup(r, "No obligations or deadlines are recorded in ERPNext yet.", DEADLINE_STEPS,
               "/app/contract/new")
    rows = _read(r, "Contract", {"requires_fulfilment": 1, "docstatus": ["<", 2],
                                 "fulfilment_status": ["not in", ["Fulfilled", "N/A"]]},
                 ["name", "party_type", "party_name", "fulfilment_deadline",
                  "fulfilment_status", "status"], limit=5000)
    out = [{**x, "fulfilment_deadline": str(x["fulfilment_deadline"])[:10]
            if x.get("fulfilment_deadline") else None} for x in rows]
    frappe.cache().set_value(key, out, expires_in_sec=300)
    return out


def _days_left(x):
    import frappe
    if not x.get("fulfilment_deadline"):
        return None
    return (frappe.utils.getdate(x["fulfilment_deadline"]) - _today()).days


def deadlines_overdue(r):
    rows = deadlines(r)
    n = sum(1 for x in rows if (_days_left(x) is not None and _days_left(x) < 0))
    undated = sum(1 for x in rows if _days_left(x) is None)
    return n, (f"deadlines already passed · {undated} with no date" if undated
               else "deadlines already passed"), {"href": "/app/contract?requires_fulfilment=1"}


def deadlines_month(r):
    n = sum(1 for x in deadlines(r) if _days_left(x) is not None and 0 <= _days_left(x) <= 30)
    return n, "in the next 30 days", {"href": "/app/contract?requires_fulfilment=1"}


def deadlines_quarter(r):
    n = sum(1 for x in deadlines(r) if _days_left(x) is not None and 0 <= _days_left(x) <= 90)
    return n, "in the next 90 days", {"href": "/app/contract?requires_fulfilment=1"}


# --------------------------------------------------------------------------- change log
def versions_deletable(r):
    """The roles the business's ERPNext lets delete an entry of its change log (Version),
    from the doctype's own permission rules."""
    import frappe
    if r.local:
        perms = [p.as_dict() if hasattr(p, "as_dict") else dict(p)
                 for p in (frappe.get_meta("Version").permissions or [])]
    else:
        perms = r.conn.get_meta("Version").get("permissions")
    if not perms:
        raise RuntimeError("the change log's permission rules were not described")
    roles = sorted({p.get("role") for p in perms if int(p.get("delete") or 0)})
    if not roles:
        return 0, "no role may delete an entry; the Administrator account still can"
    return len(roles), "roles may delete entries: " + ", ".join(roles)


LIVE = {k.key: k for k in (
    Live("score_approvals", "Were the right people asked?", "percent", score_approvals,
         "/app/version", subset_of="purchase orders and payments with approval steps recorded"),
    Live("score_records", "Are our records clean?", "percent", score_records, "",
         source="fact_stock_balance", reads_erp=False),
    Live("score_access", "Who can see what?", "percent", score_access, "/app/user?enabled=1"),
    # Worked out mostly from the loaded records, so it is not held back when ERPNext is
    # down: the questions read from ERPNext are left out and the note says so.
    Live("control_score", "Overall Business Health", "percent", control_score, "/app/version",
         source="fact_sales_invoice"),
    Live("alerts_open", "Open Alerts", "count", alerts_open, "/app/version",
         source="fact_sales_invoice", reads_erp=False),
    Live("findings_open", "Open findings", "count", findings_open, "/app/non-conformance"),
    Live("findings_repeat", "Repeat findings", "count", findings_repeat, "/app/non-conformance"),
    Live("actions_overdue", "Overdue corrective actions", "count", actions_overdue,
         "/app/quality-action"),
    Live("deadlines_overdue", "Deadlines passed", "count", deadlines_overdue, "/app/contract"),
    Live("deadlines_month", "Deadlines within a month", "count", deadlines_month, "/app/contract"),
    Live("deadlines_quarter", "Deadlines within three months", "count", deadlines_quarter,
         "/app/contract"),
    Live("versions_deletable", "Roles that may delete the change log", "count",
         versions_deletable, "/app/version"),
)}
