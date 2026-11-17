"""The nine management reports, written by the analyst from current data.

Requirements RP-01..RP-09 name the reports and what each covers; RP-10 says they
generate without anyone reassembling them by hand. Each one is a brief to the
read-only analyst (ask/agent.py) -- the sections it must cover, from the RTM -- and the
analyst gathers the figures through its tools and writes the report. So a report is
computed the same way an answer is: every figure from the records or ERPNext's own
reports, projections and recommendations labelled, nothing changed anywhere.

A report looks at every area, which can take longer than a web request is allowed, so
it runs as a background job. Each run is kept (Command Center Report Run): its state,
who asked, and the report once written, so leaving the Reports screen loses nothing --
the job carries on, the screen picks it up again on return ("Last run", View Last
Report), and the person who ran it is told in the bell when it is ready. A second Run
of a report being written returns that run; a run that cannot finish (past its
deadline, or its worker gone with a server restart) is failed with the reason, or
picked up again once. Nothing is written to the business's ERPNext.
"""

from __future__ import annotations

import json
import uuid

import frappe

from command_center import branding, mail
from command_center.api.businesses import require_manager

REPORT_STEPS = 30

# code: (title, the brief). Sections follow the RTM's RP rows.
REPORTS = {
    "rp01": ("Executive Summary",
             "the daily executive brief: the critical movements since the previous period, "
             "the exceptions that need attention, approvals pending and overdue actions"),
    "rp02": ("Weekly Management Report",
             "performance across the business, unresolved tasks, sales, cash, stock, "
             "operations, people, complaints and risks"),
    "rp03": ("Monthly Report",
             "financial and operational performance for the latest complete month: profit "
             "and loss against the previous month, KPI trends, variances, compliance and "
             "corrective actions"),
    "rp04": ("Board Report",
             "for the board: strategy and growth, the financial position (profit and loss, "
             "balance sheet, cash), major risks, governance matters and the decisions the "
             "board is asked to take"),
    "rp05": ("Sales and Payments",
             "pipeline and conversion, orders, invoicing, collections and ageing of what "
             "customers owe, discounts, and the key customers"),
    "rp06": ("Buying and Stock",
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
    "rp09": ("Compliance and Audit",
             "licences and statutory deadlines, audit findings and corrective actions, "
             "who has access to what, and policy compliance -- saying plainly which of "
             "these the records do not yet hold"),
}

BRIEF = """Write the {title} for {business}.

It covers {sections}.

Gather the figures with your tools first -- several rounds, across every area this \
covers -- then write the report. Measure periods against the end of the data ({as_of}). \
Where the records do not hold something this report should cover, say so in its section \
rather than leaving it out. Aim for one to two pages.

THIS IS A FORMAL DOCUMENT FOR DIRECTORS, NOT A CHAT REPLY. It is printed under its own \
title block, which already gives the report's name ({title}), the business, the period \
and the date, so:
- Do not start with a heading or a line that repeats the title or the business's name. \
Start with the summary paragraph itself.
- Write formal business English in the third person: complete sentences, no emoji, no \
exclamation marks, and no conversational phrases ("Here's", "Here is", "Let's", "Great", \
"I have", "Below is", "Let me know", "I hope this helps").
- Structure: a summary of two or three sentences at the top, with no heading; then one \
section per area, each under a "##" heading in Title Case (for example "## Cash and \
Receivables"), with the key figures (a markdown table where there are several, amounts \
with the currency and thousands separators) and what they mean; then a final section \
headed exactly "## Recommendations".
- Recommendations: a numbered list ("1.", "2.", ...), three to six items, each a single \
formal sentence that starts with a verb, states the action precisely with the figure \
behind it, and names the responsible function and the date or timeframe where the data \
supports one -- for example "1. Reconcile the GHS 7.25M of unmatched customer receipts \
in ERPNext's Payment Reconciliation, led by the Finance Manager, by 30 November." Do \
not label the items "Recommendation:" and do not use bold inside them.
- No follow-up questions block in a report, and no closing remarks after the \
recommendations."""


def _tidy(answer, title: str, business_code) -> str:
    """The report as a document: no repeated title, no emoji or chat, Title Case
    headings, numbered recommendations (api/report_text.py)."""
    from command_center.api.export import _business
    from command_center.api.report_text import tidy
    return tidy(answer or "", title, _business(business_code), report=True)


def _title(title: str) -> str:
    """The report's name as a document title: "Weekly management report" -> "Weekly
    Management Report"."""
    from command_center.api.report_text import title_case
    return title_case(title)


# ---------------------------------------------------------------------------
# A run of a report, kept (Command Center Report Run): per business, report and person,
# with its state -- queued, running, done, failed -- and the report once written. The
# Reports screen reads it on load ("Last run", View Last Report), so leaving the screen
# loses nothing: the job carries on, and the person who ran it is told in the bell.
# ---------------------------------------------------------------------------
RUN = "Command Center Report Run"
ALL = "__all__"
KEEP_RUNS = 10            # per business and report; older ones go at night (prune_runs)
DEADLINE_SECONDS = 1500   # the analyst's 1200 s, plus writing it up; then it has failed
HEARTBEAT_SECONDS = 30    # a running job says it is alive this often ...
STALE_SECONDS = 180       # ... and one silent this long has lost its worker
MAX_ATTEMPTS = 2          # a run whose worker died is picked up once more, then failed
BELL_DAYS = 7             # a finished report stays in the bell this long, until seen
RESULT_KEYS = ("answer", "checked", "model", "title", "code", "generated", "cut_short")

STOPPED = ("It did not finish within {m} minutes, so it was stopped. Run it again; if it "
           "stops again, the analyst may be unable to reach the business's ERPNext.")
LOST = ("The server restarted while it was being written, so it was stopped. Run it again.")


def _now():
    return frappe.utils.now_datetime()


def _biz(business_code) -> str:
    return business_code or ALL


def _plans():
    try:
        from insights.core import plans
    except ImportError:  # a plain Frappe site: no customers, every manager sees every run
        return None
    return plans


def _is_admin(user=None) -> bool:
    return "System Manager" in frappe.get_roles(user or frappe.session.user)


def _clients(user, memo) -> frozenset:
    if user not in memo:
        p = _plans()
        try:
            memo[user] = frozenset(c.pk for c, _ in p.clients_for_user(user)) if p else frozenset()
        except Exception:
            memo[user] = frozenset()
    return memo[user]


def _may_see(business_code, run_by=None, user=None, memo=None) -> bool:
    """Whether this person may see a run: their own; any, for an administrator; one of a
    business that belongs to a customer, only if they are one of that customer's people
    (managers of another customer's business never see it); one of a business on no
    customer, any manager, as every other screen. A run over all businesses is seen by
    the people who share the runner's customers."""
    user = user or frappe.session.user
    memo = {} if memo is None else memo
    if run_by and run_by == user:
        return True
    if _is_admin(user):
        return True
    p = _plans()
    if p is None:
        return True
    if not business_code or business_code == ALL:
        return bool(run_by) and _clients(user, memo) == _clients(run_by, memo)
    # One business: the platform's one rule (insights/core/plans.py visible_codes).
    return p.may_see(user, business_code)


def _first_name(user) -> str:
    name = frappe.utils.get_fullname(user) or user or ""
    return name.split()[0] if name.strip() else name


def _when(d) -> str | None:
    """"14:32 today", "09:05 yesterday", "12 Nov 14:32": server time, as every other
    time on the platform."""
    if not d:
        return None
    d = frappe.utils.get_datetime(d)
    today = _now().date()
    hm = f"{d:%H:%M}"
    if d.date() == today:
        return f"{hm} today"
    if (today - d.date()).days == 1:
        return f"{hm} yesterday"
    return f"{d.day} {d:%b} {hm}"


def _iso(d) -> str | None:
    return frappe.utils.get_datetime(d).isoformat(timespec="seconds") if d else None


FIELDS = ["name", "business_code", "report", "title", "state", "kind", "run_by", "schedule",
          "started", "claimed", "heartbeat", "deadline", "finished", "attempts", "worker",
          "seen", "error"]


def _row(r) -> dict:
    """A run as the screen shows it -- never the report itself (see open_run)."""
    me = frappe.session.user
    live = r.state in ("queued", "running")
    return {"name": r.name, "business_code": r.business_code, "code": r.report,
            "title": r.title, "state": r.state, "kind": r.kind or "manual",
            "run_by": r.run_by, "run_by_name": _first_name(r.run_by), "mine": r.run_by == me,
            "started": _iso(r.started), "finished": _iso(r.finished),
            "started_label": _when(r.started), "finished_label": _when(r.finished),
            "error": r.error or None,
            # Seconds since it started, by the server's clock, for the screen's counter.
            "elapsed": int((_now() - frappe.utils.get_datetime(r.started)).total_seconds())
            if live and r.started else None}


def _get(name):
    rows = frappe.get_all(RUN, filters={"name": name}, fields=FIELDS + ["result"], limit=1)
    return rows[0] if rows else None


def _visible_run(name):
    r = _get(name) if name else None
    if r is None or not _may_see(r.business_code, r.run_by):
        return None
    return r


def _live(business_code, code):
    """The run of this report for this business still being written, that this person
    may see -- a second Run returns it rather than writing the report twice."""
    memo = {}
    for r in frappe.get_all(RUN, filters={"business_code": business_code, "report": code,
                                          "state": ["in", ["queued", "running"]]},
                            fields=FIELDS, order_by="started desc"):
        if _may_see(r.business_code, r.run_by, memo=memo):
            return r
    return None


def _new_run(code, business_code, user, kind="manual", schedule=None, state="queued", worker=""):
    now = _now()
    # The doctype by name, not RUN: preflight allows a permission bypass only on a
    # document it can see is the app's own.
    doc = frappe.get_doc({
        "doctype": "Command Center Report Run", "business_code": _biz(business_code), "report": code,
        "title": _title(REPORTS[code][0]), "state": state, "kind": kind, "run_by": user,
        "schedule": schedule, "started": now,
        "deadline": frappe.utils.add_to_date(now, seconds=DEADLINE_SECONDS),
        "claimed": now if state == "running" else None,
        "heartbeat": now if (state == "running" and _beats()) else None,
        "attempts": 1 if state == "running" else 0, "worker": worker,
        # A scheduled report goes by email; only one someone ran waits in their bell.
        "seen": 1 if kind == "scheduled" else 0,
    }).insert(ignore_permissions=True)
    return doc.name


def _claim(name, token) -> bool:
    """Take a queued run to write it. One conditional update, so of two workers that
    try (the web process and a sweep after a restart) exactly one gets it."""
    r = _get(name)
    if r is None or r.state != "queued":
        return False
    now = _now()
    frappe.db.set_value(RUN, {"name": name, "state": "queued", "worker": r.worker or ""}, {
        "state": "running", "worker": token, "claimed": now,
        "heartbeat": now if _beats() else None,
        "attempts": int(r.attempts or 0) + 1,
        "deadline": frappe.utils.add_to_date(now, seconds=DEADLINE_SECONDS)},
        update_modified=False)
    frappe.db.commit()
    return frappe.db.get_value(RUN, name, "worker") == token


def _finish(name, token, state, result=None, error=None):
    """Record the outcome -- only by the worker that holds the run, so a run the sweep
    already gave to another worker is not overwritten by a late first one."""
    values = {"state": state, "finished": _now(), "heartbeat": None,
              "error": (error or None) and str(error)[:500]}
    if result is not None:
        values["result"] = json.dumps({k: result.get(k) for k in RESULT_KEYS if k in result},
                                      default=str)
    frappe.db.set_value(RUN, {"name": name, "worker": token}, values, update_modified=False)
    frappe.db.commit()


def _beats() -> bool:
    """A heartbeat needs a thread with its own database connection: the standalone
    platform's run_as. On Frappe (RQ workers) only the deadline applies."""
    try:
        from insights.compat import run_as  # noqa: F401
    except ImportError:
        return False
    return True


class _Heartbeat:
    """While a run is written, mark it alive every HEARTBEAT_SECONDS from a thread of its
    own -- its own connection and transaction, so the analyst's write guard (which undoes
    any write made while a question is answered) never sees or undoes it."""

    def __init__(self, name, token):
        import threading
        self.name, self.token = name, token
        self.stop_ = threading.Event()
        self.thread = threading.Thread(target=self._beat, daemon=True,
                                       name=f"cc-report-beat-{name}")

    def __enter__(self):
        if _beats():
            self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop_.set()

    def _beat(self):
        from insights.compat import run_as
        while not self.stop_.wait(HEARTBEAT_SECONDS):
            try:
                with run_as("Administrator"):
                    frappe.db.set_value(RUN, {"name": self.name, "worker": self.token,
                                              "state": "running"},
                                        "heartbeat", _now(), update_modified=False)
            except Exception:
                pass  # a missed beat is a late one; the sweep allows for three


def sweep(business_code=None, code=None):
    """Runs that can no longer finish, put right: one past its deadline has failed, with
    the reason; one whose worker stopped beating (the server restarted under it) is
    picked up again once, then failed; one queued that no worker took is queued again.
    Called when the Reports screen reads its runs, before a new one starts, and every
    five minutes by the scheduler (hooks.py)."""
    now = _now()
    filters = {"state": ["in", ["queued", "running"]]}
    if business_code:
        filters["business_code"] = _biz(business_code)
    if code:
        filters["report"] = code
    changed = 0
    def age(d) -> float:
        return (now - frappe.utils.get_datetime(d)).total_seconds() if d else 0

    for r in frappe.get_all(RUN, filters=filters, fields=FIELDS):
        if r.deadline and now > frappe.utils.get_datetime(r.deadline):
            frappe.db.set_value(RUN, {"name": r.name, "state": r.state}, {
                "state": "failed", "finished": now, "heartbeat": None,
                "error": STOPPED.format(m=DEADLINE_SECONDS // 60)}, update_modified=False)
            changed += 1
        elif r.state == "running" and r.heartbeat and age(r.heartbeat) > STALE_SECONDS:
            if int(r.attempts or 0) < MAX_ATTEMPTS and r.kind != "scheduled":
                frappe.db.set_value(RUN, {"name": r.name, "state": "running", "worker": r.worker},
                                    {"state": "queued", "worker": "", "heartbeat": None},
                                    update_modified=False)
                frappe.db.commit()
                _enqueue(r.name, r.report, r.business_code, r.run_by)
            else:
                frappe.db.set_value(RUN, {"name": r.name, "state": "running"}, {
                    "state": "failed", "finished": now, "heartbeat": None, "error": LOST},
                    update_modified=False)
            changed += 1
        elif r.state == "queued" and age(r.started) > STALE_SECONDS and _beats():
            # Never taken (the process that queued it went away first). Queuing it again
            # is safe: only one worker can claim it.
            _enqueue(r.name, r.report, r.business_code, r.run_by)
    if changed:
        frappe.db.commit()
    return changed


def _enqueue(name, code, business_code, user):
    # report_id, not job_id: frappe.enqueue keeps job_id for itself and would swallow it.
    frappe.enqueue("command_center.api.reports._run", queue="long",
                   timeout=DEADLINE_SECONDS, report_id=name, code=code,
                   business_code=None if business_code == ALL else business_code,
                   user=user, enqueue_after_commit=False)


@frappe.whitelist(methods=["POST"])
def generate(code: str, business_code: str | None = None):
    """Start a report -- or, when this report for this business is already being
    written, return that run instead of writing it twice. Returns the run to follow
    with status(); the run carries on whether or not anyone is watching."""
    require_manager()
    from command_center.ask import engine

    if code not in REPORTS:
        frappe.throw(f"Unknown report {code!r}")
    biz = _biz(business_code)
    sweep(biz, code)
    with frappe.cache().lock(f"cc_report_start::{biz}::{code}", timeout=30, blocking_timeout=15):
        live = _live(biz, code)
        if live:
            return {"job_id": live.name, "title": REPORTS[code][0], "already": True,
                    "run": _row(live)}
        if not engine.analyst_enabled():
            frappe.throw("Reports are written by the analyst, which needs an AI key on this "
                         "site (bench --site <site> set-config command_center_anthropic_key ...).")
        # The plan: a lapsed licence, or the month's AI reports used with no overage allowed.
        from command_center import metering
        blocked = metering.gate("ai_reports", business_code)
        if blocked:
            frappe.throw(blocked)
        name = _new_run(code, business_code, frappe.session.user)
        frappe.db.commit()
    _enqueue(name, code, biz, frappe.session.user)
    return {"job_id": name, "title": REPORTS[code][0], "run": _row(_get(name))}


@frappe.whitelist()
def status(job_id: str):
    """Where a run is: queued or running, done (with the report), or failed (with why).
    Readable from any page, device or sign-in of anyone who may see the run."""
    require_manager()
    r = _visible_run(job_id)
    if r is None:
        return {"state": "unknown"}
    if r.state in ("queued", "running"):
        sweep(r.business_code, r.report)
        r = _visible_run(job_id)
    out = {"state": "running" if r.state == "queued" else r.state, "run": _row(r)}
    if r.state == "done":
        out["report"] = _report(r)
    elif r.state == "failed":
        out["error"] = r.error or "The report could not be written."
    return out


def _report(r) -> dict:
    try:
        rep = json.loads(r.result or "{}")
    except ValueError:
        rep = {}
    rep.setdefault("title", r.title)
    rep.setdefault("code", r.report)
    rep["business_code"] = None if r.business_code == ALL else r.business_code
    rep["run"] = r.name
    return rep


@frappe.whitelist()
def latest(business_code: str | None = None):
    """Each report's latest run for this business, and its latest written one -- what
    the Reports screen's "Last run" and View Last Report show on load."""
    require_manager()
    biz = _biz(business_code)
    sweep(biz)
    memo, out = {}, {}
    for r in frappe.get_all(RUN, filters={"business_code": biz}, fields=FIELDS,
                            order_by="started desc", limit=len(REPORTS) * KEEP_RUNS * 3):
        if not _may_see(r.business_code, r.run_by, memo=memo):
            continue
        slot = out.setdefault(r.report, {"latest": None, "last_done": None})
        if slot["latest"] is None:
            slot["latest"] = _row(r)
        if slot["last_done"] is None and r.state == "done":
            slot["last_done"] = _row(r)
    return {"business_code": biz, "runs": out}


@frappe.whitelist()
def open_run(run: str):
    """A written report, to read again: the same report, nothing rewritten and nothing
    counted again (the AI report was counted once, when it was written)."""
    require_manager()
    r = _visible_run(run)
    if r is None:
        frappe.throw("That report is not available.", frappe.PermissionError)
    if r.state != "done":
        frappe.throw("That report has not been written.")
    if r.run_by == frappe.session.user and not r.seen:
        _mark_seen(r.name)
    return {"report": _report(r), "run": _row(r)}


def _mark_seen(name):
    frappe.db.set_value(RUN, {"name": name, "run_by": frappe.session.user}, "seen", 1,
                        update_modified=False)
    frappe.db.commit()


@frappe.whitelist(methods=["POST"])
def mark_seen(run: str):
    require_manager()
    _mark_seen(run)
    return {"ok": True}


@frappe.whitelist()
def mine():
    """For the bell: this person's reports finished and not yet seen (in the last
    BELL_DAYS days), and those still being written, so any page can follow them and
    say when one is ready."""
    require_manager()
    me = frappe.session.user
    since = frappe.utils.add_to_date(_now(), days=-BELL_DAYS)
    ready = frappe.get_all(RUN, filters={"run_by": me, "kind": "manual", "seen": 0,
                                         "state": ["in", ["done", "failed"]],
                                         "finished": [">=", since]},
                           fields=FIELDS, order_by="finished desc", limit=10)
    running = frappe.get_all(RUN, filters={"run_by": me, "kind": "manual",
                                           "state": ["in", ["queued", "running"]]},
                             fields=FIELDS, order_by="started desc", limit=10)
    return {"ready": [_row(r) for r in ready], "running": [_row(r) for r in running]}


def prune_runs(keep: int = KEEP_RUNS) -> int:
    """Nightly: the latest `keep` runs of each report for each business are kept, the
    rest dropped. A run still being written is never dropped."""
    gone = 0
    pairs = {(r.business_code, r.report) for r in frappe.get_all(
        RUN, fields=["business_code", "report"], limit=100000)}
    for biz, code in pairs:
        names = frappe.get_all(RUN, filters={"business_code": biz, "report": code,
                                             "state": ["in", ["done", "failed"]]},
                               order_by="started desc", pluck="name", limit=100000)
        old = names[keep:]
        if old:
            frappe.db.delete(RUN, {"name": ["in", old]})
            gone += len(old)
    if gone:
        frappe.db.commit()
    return gone


def _run(report_id: str, code: str, business_code: str | None, user: str):
    name = report_id
    token = uuid.uuid4().hex[:12]
    frappe.set_user(user)  # the job reads with the asker's own permissions
    if not _claim(name, token):
        return  # taken by another worker, or no longer waiting
    from command_center.ask import agent
    from command_center.api.export import _as_of, _business

    title, sections = REPORTS[code]
    with _Heartbeat(name, token):
        try:
            brief = BRIEF.format(title=title, business=_business(business_code),
                                 sections=sections, as_of=_as_of(business_code))
            # A job, not a web request: room for a report's sixteen rounds. One AI report
            # on the usage ledger, counted when it is written -- never on reopening it.
            from command_center import metering
            with metering.event("ai_reports", business_code, ref=code) as ev:
                result = agent.answer(brief, business_code, max_steps=REPORT_STEPS,
                                      deadline=1200, deep=True)
                ev["ok"] = bool(result and result.get("answered"))
            if not result or not result.get("answer"):
                if result and result.get("analyst_error"):
                    frappe.log_error(title=f"Command Center report {code}",
                                     message=str(result["analyst_error"]))
                raise RuntimeError("the analyst could not be reached or returned nothing")
            result["answer"] = _tidy(result.get("answer"), title, business_code)
            result.update({"title": _title(title), "code": code,
                           "generated": _now().isoformat(timespec="minutes")})
            _finish(name, token, "done", result=result)
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(title=f"Command Center report {code}", message=frappe.get_traceback())
            _finish(name, token, "failed", error=str(e)[:300] or "The report could not be written.")


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
    strangers = [p for p in people if not may_receive(p, doc.business_code)]
    if strangers:
        frappe.throw("These are not managers of this business on the platform, so the "
                     f"report would leave the company: {', '.join(strangers)}")
    doc.recipients = "\n".join(people)
    if not doc.run_as:
        doc.run_as = frappe.session.user


def may_receive(person: str, business_code: str | None) -> bool:
    """A scheduled report goes only to an enabled manager (or administrator) of the
    platform who may see its business -- its customer's own people (insights/core/
    plans.py visible_codes). Any account used to pass (every account read as a "System
    User"), so another customer's manager, or anyone added at all, could be sent it."""
    from command_center.api.businesses import ALLOWED_ROLES
    if not person or not frappe.db.get_value("User", {"name": person, "enabled": 1}, "name"):
        return False
    if not ALLOWED_ROLES.intersection(frappe.get_roles(person)):
        return False
    p = _plans()
    if p is None or not business_code or business_code == ALL:
        return True
    return p.may_see(person, business_code)


SEND_NOW_GUARD = 120  # seconds: a second Send Now of the same schedule in this time is refused


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
    # A double click, or a second press while the first is being written, is one send:
    # held for SEND_NOW_GUARD seconds (cache.add is atomic across workers).
    if not frappe.cache().lock(f"cc:report:send_now:{name}", timeout=SEND_NOW_GUARD).acquire(
            blocking=False):
        frappe.throw("This report is being sent already. It will arrive in a few minutes; "
                     "press Send Now again after that only if it has not.")
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

    from command_center import metering
    from command_center.ask import engine

    doc = frappe.get_doc(SCHEDULE, schedule)
    frappe.set_user(doc.run_as or "Administrator")
    # On record like a run someone pressed, so the Reports screen's "Last run" says it
    # and the report can be reopened there; it is emailed, so it waits in no bell.
    token = uuid.uuid4().hex[:12]
    run = _new_run(doc.report, doc.business_code, doc.run_as or "Administrator",
                   kind="scheduled", schedule=doc.name, state="running", worker=token)
    frappe.db.commit()
    written = {}
    try:
        if not engine.analyst_enabled():
            raise RuntimeError("the analyst needs an AI key on this site")
        # The plan: paused after the licence's grace, or the month's scheduled reports used
        # with no overage allowed -- the last status says so.
        blocked = metering.gate("scheduled_reports", doc.business_code)
        if blocked:
            raise RuntimeError(blocked)
        # One scheduled report on the usage ledger, counted once it has been sent; a send
        # that fails keeps the tokens it spent and is not counted.
        with _Heartbeat(run, token), \
                metering.event("scheduled_reports", doc.business_code, ref=doc.report) as ev:
            _write_and_send(doc, written)
            ev["ok"] = True
        _finish(run, token, "done", result=written["result"])
        doc.db_set({"last_sent": now_datetime(),
                    "last_status": f"Sent to {len(_recipients(doc.recipients))} at "
                                   f"{now_datetime():%d %b %H:%M}"}, update_modified=False)
    except Exception as e:
        frappe.log_error(title=f"Command Center scheduled report {doc.report}",
                         message=frappe.get_traceback())
        if written.get("result"):
            # Written, then not sent: the report is there to read; the reason is with it.
            _finish(run, token, "done", result=written["result"],
                    error=f"Written but not sent: {str(e)[:200]}")
        else:
            _finish(run, token, "failed", error=str(e)[:300])
        doc.db_set("last_status", f"Failed {now_datetime():%d %b %H:%M}: {str(e)[:200]}",
                   update_modified=False)
    frappe.db.commit()


def _write_and_send(doc, written=None):
    from command_center.ask import agent
    from command_center.api.export import _as_of, _business, pdf_bytes

    title, sections = REPORTS[doc.report]
    heading = _title(title)
    brief = BRIEF.format(title=title, business=_business(doc.business_code),
                         sections=sections, as_of=_as_of(doc.business_code))
    result = agent.answer(brief, doc.business_code, max_steps=REPORT_STEPS, deadline=1200,
                          deep=True)
    if not result or not result.get("answer"):
        raise RuntimeError("the analyst returned nothing")
    answer = _tidy(result["answer"], title, doc.business_code)
    if written is not None:
        written["result"] = {**result, "answer": answer, "title": heading, "code": doc.report,
                             "generated": _now().isoformat(timespec="minutes")}
    pdf = pdf_bytes(heading, answer, result.get("checked"), doc.business_code,
                    result.get("model"), kind="report")
    business = _business(doc.business_code)
    when = frappe.utils.format_date(frappe.utils.today(), "d MMM yyyy")
    lead = (answer.split("\n\n", 1)[0] or "")[:1200]
    esc = frappe.utils.escape_html
    # Checked again at the send: someone who has since left the business's customer, or
    # been deactivated, is not sent it.
    to = [p for p in _recipients(doc.recipients) if may_receive(p, doc.business_code)]
    if not to:
        raise RuntimeError("no one on its list is still a manager of this business on the "
                           "platform")
    with mail.about("report", doc.business_code):
        frappe.sendmail(
            recipients=to,
            subject=f"{heading} · {business} · {when}",
            message=branding.email_html(
                f"<p><b>{esc(heading)}</b> · {esc(business)}</p>"
                f"<p>{esc(lead)}</p>"
                f"<p>The full report is attached. It was written from the records as at "
                f"{esc(_as_of(doc.business_code))}, with the permissions of "
                f"{esc(frappe.utils.get_fullname(doc.run_as))}.</p>"
                f"<p style='color:#777'>Sent by {esc(branding.branding()['product'])} on its "
                f"{esc(describe(doc))} schedule.</p>", doc.business_code),
            attachments=[{"fname": f"{heading} {frappe.utils.today()}.pdf", "fcontent": pdf}],
            now=True,
        )


def _recipients(text) -> list:
    import re as _re
    return [p for p in dict.fromkeys(x.strip() for x in _re.split(r"[\n,;]+", text or "")) if p]


def _local_code(business_code):
    if business_code and business_code != "__all__":
        return business_code
    from command_center.api.businesses import default_business_code
    code = default_business_code()
    if not code:
        frappe.throw("No business is registered yet.")
    return code


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
