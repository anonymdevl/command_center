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

REPORT_STEPS = 30
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
    frappe.enqueue("command_center.api.reports._run", queue="long", timeout=1500,
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
        # A job, not a web request: room for a report's sixteen rounds.
        result = agent.answer(brief, business_code, max_steps=REPORT_STEPS, deadline=1200)
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


# ---------------------------------------------------------------------------
# On a schedule, emailed to a list (RP-10). One schedule per report per business, in
# Command Center Report Schedule. The hourly job writes each report that is due with the
# permissions of the person who set the schedule, and emails it as a PDF to the people
# listed -- who must have an account on this site, so a report never leaves the company.
# ---------------------------------------------------------------------------
SCHEDULE = "Command Center Report Schedule"
UNSCHEDULABLE = {"rp04": "The board report is released only with an approval, so it is "
                         "written on request, never sent on a timer."}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def check_schedule(doc):
    if doc.report not in REPORTS:
        frappe.throw(f"Unknown report {doc.report!r}")
    if doc.report in UNSCHEDULABLE:
        frappe.throw(UNSCHEDULABLE[doc.report])
    doc.report_title = REPORTS[doc.report][0]
    doc.hour = min(max(int(doc.hour or 0), 0), 23)
    doc.day_of_month = min(max(int(doc.day_of_month or 1), 1), 28)
    people = _recipients(doc.recipients)
    if not people:
        frappe.throw("Say who receives it: at least one person with an account on this site.")
    allowed = set(frappe.get_all("User", filters={"name": ["in", people], "enabled": 1,
                                                  "user_type": "System User"}, pluck="name"))
    strangers = [p for p in people if p not in allowed]
    if strangers:
        frappe.throw("These are not people with an account on this site, so the report "
                     f"would leave the company: {', '.join(strangers)}")
    doc.recipients = "\n".join(people)
    if not doc.run_as:
        doc.run_as = frappe.session.user


def next_run(doc, after=None):
    """The next time this schedule is due, strictly after `after` (now)."""
    from datetime import timedelta

    from frappe.utils import add_months, get_datetime, now_datetime

    now = get_datetime(after) if after else now_datetime()
    at = now.replace(hour=int(doc.hour or 0), minute=0, second=0, microsecond=0)
    if doc.frequency == "Daily":
        return at if at > now else at + timedelta(days=1)
    if doc.frequency == "Weekly":
        ahead = (WEEKDAYS.index(doc.weekday or "Monday") - at.weekday()) % 7
        at = at + timedelta(days=ahead)
        return at if at > now else at + timedelta(days=7)
    at = at.replace(day=int(doc.day_of_month or 1))
    return at if at > now else get_datetime(add_months(at, 1))


def describe(doc) -> str:
    when = {"Daily": "every day",
            "Weekly": f"{doc.weekday or 'Monday'}s",
            "Monthly": f"the {_ordinal(int(doc.day_of_month or 1))} of each month"}[doc.frequency]
    n = len(_recipients(doc.recipients))
    return f"{when} at {int(doc.hour or 0):02d}:00 · {n} {'person' if n == 1 else 'people'}"


@frappe.whitelist()
def schedules(business_code: str | None = None):
    require_manager()
    code = _local_code(business_code)
    rows = frappe.get_all(SCHEDULE, filters={"business_code": code},
                          fields=["name", "report", "enabled", "frequency", "weekday",
                                  "day_of_month", "hour", "recipients", "next_run",
                                  "last_sent", "last_status"])
    return {"business_code": code, "unschedulable": list(UNSCHEDULABLE),
            "schedules": [{**r, "recipients": _recipients(r.recipients),
                           "next_run": str(r.next_run)[:16] if r.next_run else None,
                           "last_sent": str(r.last_sent)[:16] if r.last_sent else None,
                           "says": describe(r) if r.enabled else "switched off"} for r in rows]}


@frappe.whitelist(methods=["POST"])
def save_schedule(code: str, business_code: str | None = None, frequency: str = "Weekly",
                  weekday: str = "Monday", day_of_month: int = 1, hour: int = 7,
                  recipients=None, enabled: int = 1):
    require_manager()
    biz = _local_code(business_code)
    people = frappe.parse_json(recipients) if isinstance(recipients, str) else (recipients or [])
    name = frappe.db.get_value(SCHEDULE, {"report": code, "business_code": biz})
    doc = frappe.get_doc(SCHEDULE, name) if name else frappe.new_doc(SCHEDULE)
    doc.update({"report": code, "business_code": biz, "frequency": frequency,
                "weekday": weekday, "day_of_month": day_of_month, "hour": hour,
                "recipients": "\n".join(people), "enabled": 1 if int(enabled or 0) else 0,
                "run_as": frappe.session.user})
    doc.save() if name else doc.insert()
    return {"name": doc.name, "says": describe(doc) if doc.enabled else "switched off",
            "next_run": str(doc.next_run)[:16] if doc.next_run else None}


@frappe.whitelist(methods=["POST"])
def send_now(code: str, business_code: str | None = None):
    """Write and send a scheduled report now, to its list -- for checking the schedule."""
    require_manager()
    name = frappe.db.get_value(SCHEDULE, {"report": code, "business_code": _local_code(business_code)})
    if not name:
        frappe.throw("Set the schedule first, so there is a list to send it to.")
    frappe.enqueue("command_center.api.reports.send_scheduled", queue="long", timeout=1500,
                   schedule=name, enqueue_after_commit=True)
    return {"queued": True}


def send_due():
    """Hourly: queue every enabled schedule whose time has come."""
    from frappe.utils import now_datetime

    for name in frappe.get_all(SCHEDULE, filters={"enabled": 1, "next_run": ["<=", now_datetime()]},
                               pluck="name"):
        doc = frappe.get_doc(SCHEDULE, name)
        # Moved on before the job runs, so a slow or failed job is not sent twice.
        doc.db_set("next_run", next_run(doc), update_modified=False)
        frappe.enqueue("command_center.api.reports.send_scheduled", queue="long",
                       timeout=1500, schedule=name)
    frappe.db.commit()


def send_scheduled(schedule: str):
    from frappe.utils import now_datetime

    from command_center.ask import agent, engine
    from command_center.api.export import _as_of, _business, pdf_bytes

    doc = frappe.get_doc(SCHEDULE, schedule)
    title, sections = REPORTS[doc.report]
    frappe.set_user(doc.run_as or "Administrator")
    try:
        if not engine.analyst_enabled():
            raise RuntimeError("the analyst needs the Gemini key on this site")
        brief = BRIEF.format(title=title, business=_business(doc.business_code),
                             sections=sections, as_of=_as_of())
        result = agent.answer(brief, doc.business_code, max_steps=REPORT_STEPS, deadline=1200)
        if not result or not result.get("answer"):
            raise RuntimeError("the analyst returned nothing")
        pdf = pdf_bytes(title, result["answer"], result.get("checked"), doc.business_code,
                        result.get("model"))
        business = _business(doc.business_code)
        when = frappe.utils.format_date(frappe.utils.today(), "d MMM yyyy")
        lead = (result["answer"].split("\n\n", 1)[0] or "")[:1200]
        frappe.sendmail(
            recipients=_recipients(doc.recipients),
            subject=f"{title} · {business} · {when}",
            message=(f"<p>{frappe.utils.escape_html(lead)}</p>"
                     f"<p>The full report is attached. It was written from the records as at "
                     f"{frappe.utils.escape_html(_as_of())}, with the permissions of "
                     f"{frappe.utils.escape_html(frappe.utils.get_fullname(doc.run_as))}.</p>"
                     f"<p style='color:#777'>Sent by the Command Center on its "
                     f"{frappe.utils.escape_html(describe(doc))} schedule.</p>"),
            attachments=[{"fname": f"{title} {frappe.utils.today()}.pdf", "fcontent": pdf}],
            now=True,
        )
        doc.db_set({"last_sent": now_datetime(),
                    "last_status": f"Sent to {len(_recipients(doc.recipients))} at "
                                   f"{now_datetime():%d %b %H:%M}"}, update_modified=False)
    except Exception as e:
        frappe.log_error(title=f"Command Center scheduled report {doc.report}",
                         message=frappe.get_traceback())
        doc.db_set("last_status", f"Failed {now_datetime():%d %b %H:%M}: {str(e)[:200]}",
                   update_modified=False)
    frappe.db.commit()


def _recipients(text) -> list:
    import re as _re
    return [p for p in dict.fromkeys(x.strip() for x in _re.split(r"[\n,;]+", text or "")) if p]


def _local_code(business_code):
    if business_code and business_code != "__all__":
        return business_code
    code = frappe.db.get_value("Connected Business", {"is_local": 1}, "business_code")
    if not code:
        frappe.throw("No business on this site is marked as local.")
    return code


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
