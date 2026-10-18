"""The nine management reports, written by the analyst from current data.

Requirements RP-01..RP-09 name the reports and what each covers; RP-10 says they
generate without anyone reassembling them by hand. Each one is a brief to the
read-only analyst (ask/agent.py) -- the sections it must cover, from the RTM -- and the
analyst gathers the figures through its tools and writes the report. So a report is
computed the same way an answer is: every figure from the records or ERPNext's own
reports, projections and recommendations labelled, nothing changed anywhere.

A report looks at every area, which can take longer than a web request is allowed, so
it runs as a background job and the screen polls for it. The finished report is kept
in the cache for an hour, under the person who asked: nothing is written to the site.
"""

from __future__ import annotations

import uuid

import frappe

from command_center.api.businesses import require_manager

REPORT_STEPS = 16
KEEP_SECONDS = 3600

# code: (title, the brief). Sections follow the RTM's RP rows.
REPORTS = {
    "rp01": ("Executive Summary",
             "the daily executive brief: the critical movements since the previous period, "
             "the exceptions that need attention, approvals pending and overdue actions"),
    "rp02": ("Weekly management report",
             "performance across the business, unresolved tasks, sales, cash, stock, "
             "operations, people, complaints and risks"),
    "rp03": ("Monthly report",
             "financial and operational performance for the latest complete month: profit "
             "and loss against the previous month, KPI trends, variances, compliance and "
             "corrective actions"),
    "rp04": ("Board report",
             "for the board: strategy and growth, the financial position (profit and loss, "
             "balance sheet, cash), major risks, governance matters and the decisions the "
             "board is asked to take"),
    "rp05": ("Sales and Payments",
             "pipeline and conversion, orders, invoicing, collections and ageing of what "
             "customers owe, discounts, and the key customers"),
    "rp06": ("Buying and stock",
             "open purchases, supplier status and dependence, stock availability, ageing, "
             "variances and the working capital tied up in stock"),
    "rp07": ("Engineering",
             "installation and service jobs: open and completed work, response and "
             "completion against plan, what is late and with whom, cost and margin where "
             "recorded, parts and customer feedback"),
    "rp08": ("People",
             "headcount and its movement, recruitment, attendance, payroll status, "
             "performance and training -- as totals and by department only, naming no "
             "individual and giving no individual's pay"),
    "rp09": ("Compliance and audit",
             "licences and statutory deadlines, audit findings and corrective actions, "
             "who has access to what, and policy compliance -- saying plainly which of "
             "these the records do not yet hold"),
}

BRIEF = """Write the {title} for {business}.

It covers {sections}.

Gather the figures with your tools first -- several rounds, across every area this \
covers -- then write the report. Structure: a two-to-three sentence summary at the top; \
then a short section per area with a heading, the key figures (a markdown table where \
there are several), and what they mean; then "Recommendations" -- specific, each tied to \
the figures behind it. Measure periods against the end of the data ({as_of}). Where the \
records do not hold something this report should cover, say so in its section rather \
than leaving it out. Aim for one to two pages."""


def _key(job_id: str) -> str:
    return f"cc_report::{frappe.session.user}::{job_id}"


@frappe.whitelist(methods=["POST"])
def generate(code: str, business_code: str | None = None):
    """Start a report. Returns a job id to poll with status()."""
    require_manager()
    from command_center.ask import engine

    if code not in REPORTS:
        frappe.throw(f"Unknown report {code!r}")
    if not engine.analyst_enabled():
        frappe.throw("Reports are written by the analyst, which needs the Gemini key on "
                     "this site (bench --site <site> set-config command_center_gemini_key ...).")
    job_id = uuid.uuid4().hex[:12]
    frappe.cache().set_value(_key(job_id), {"state": "running", "code": code},
                             expires_in_sec=KEEP_SECONDS)
    # report_id, not job_id: frappe.enqueue keeps job_id for itself and would swallow it.
    frappe.enqueue("command_center.api.reports._run", queue="long", timeout=900,
                   report_id=job_id, code=code, business_code=business_code,
                   user=frappe.session.user, enqueue_after_commit=False)
    return {"job_id": job_id, "title": REPORTS[code][0]}


@frappe.whitelist()
def status(job_id: str):
    """Where a report is: running, done (with the report), or failed (with why)."""
    require_manager()
    return frappe.cache().get_value(_key(job_id)) or {"state": "unknown"}


def _run(report_id: str, code: str, business_code: str | None, user: str):
    job_id = report_id
    frappe.set_user(user)  # the job reads with the asker's own permissions
    from command_center.ask import agent
    from command_center.api.export import _as_of, _business

    title, sections = REPORTS[code]
    key = _key(job_id)
    try:
        brief = BRIEF.format(title=title, business=_business(business_code),
                             sections=sections, as_of=_as_of())
        result = agent.answer(brief, business_code, max_steps=REPORT_STEPS)
        if not result:
            raise RuntimeError("the analyst could not be reached or returned nothing")
        result.update({"title": title, "code": code,
                       "generated": frappe.utils.now_datetime().isoformat(timespec="minutes")})
        frappe.cache().set_value(key, {"state": "done", "report": result},
                                 expires_in_sec=KEEP_SECONDS)
    except Exception as e:
        frappe.log_error(title=f"Command Center report {code}", message=frappe.get_traceback())
        frappe.cache().set_value(key, {"state": "failed", "error": str(e)[:300]},
                                 expires_in_sec=KEEP_SECONDS)
