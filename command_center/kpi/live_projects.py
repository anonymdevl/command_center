"""Engineering & Installations' figures for every project, open and completed (18 Nov 2026).

The rest of the screen is about the work still open. These are about the projects
themselves: what is open, overdue or not started, what was finished and when, and for
whom. A project is read from the business's ERPNext (its status, type, customer and
dates); its work is the loaded task fact (each task's dates, status and engineers).

Nothing is guessed. A project is complete when its own status says so, and finished on
the day its project records (Actual End Date), or else on the last day one of its tasks
was completed; a completed project that records neither has no completion date and is
counted in no month. On time means a task finished on or before its Expected End Date;
a task with no due date or no completion date is not measured.

Importing this module touches no frappe (preflight imports kpi/live.py).
"""

from __future__ import annotations

import datetime as dt
from statistics import median

from command_center.kpi.live import Live, _read
from command_center.kpi.live_departments import facts, num

CLOSED = {"Completed", "Cancelled"}
PROJECT_FIELDS = ["name", "project_name", "status", "project_type", "customer",
                  "expected_start_date", "expected_end_date", "actual_end_date",
                  "percent_complete"]
TASK_FIELDS = ["src_name", "subject", "project", "status", "is_open", "exp_start_date",
               "exp_end_date", "completed_on", "days_late", "engineers", "customer",
               "as_of_date"]


def _day(v):
    if not v:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _names(text):
    return [n.strip() for n in (text or "").split(",") if n.strip()]


REPEAT_WORK = ("repair", "maint", "servic", "warrant", "fault", "breakdown")


def is_repeat_work(t, project_type="") -> bool:
    """Work that should not need doing again soon: a repair, a service, a warranty call
    (by the task's own words after " - ", or its project's type). An installation of a
    second unit is not a return visit."""
    words = f"{(t.get('subject') or '').partition(' - ')[2]} {project_type or ''}".lower()
    return any(w in words for w in REPEAT_WORK)


def stem(subject) -> str:
    """What a task is about, without the work done to it: "Slitlamp - Maintenance" is
    the Slitlamp. A subject with no " - " is taken whole."""
    return (subject or "").split(" - ")[0].strip()


def book(r) -> dict:
    """Every project with its work, worked out once per reader:
    {"as_of": date, "projects": [...], "tasks": [...]}."""
    cached = getattr(r, "_project_book", None)
    if cached is not None:
        return cached
    tasks = facts(r, "fact_task", {}, TASK_FIELDS)
    as_of = max((_day(t["as_of_date"]) for t in tasks if t["as_of_date"]),
                default=None) or dt.date.today()
    by_project = {}
    for t in tasks:
        by_project.setdefault(t["project"], []).append(t)
    projects = []
    for p in _read(r, "Project", {}, PROJECT_FIELDS, limit=100000):
        work = by_project.get(p["name"], [])
        done = [t for t in work if t["status"] == "Completed"]
        open_ = [t for t in work if t["is_open"]]
        # Not finished by the task's own status, whatever its project says: a project
        # closed with work still open is shown as such, and listed among records to tidy.
        unfinished = [t for t in work if t["status"] not in ("Completed", "Cancelled", "Template")]
        finished = (_day(p.get("actual_end_date"))
                    or max((_day(t["completed_on"]) for t in done if t["completed_on"]),
                           default=None))
        start = (_day(p.get("expected_start_date"))
                 or min((_day(t["exp_start_date"]) for t in work if t["exp_start_date"]),
                        default=None))
        due = (_day(p.get("expected_end_date"))
               or max((_day(t["exp_end_date"]) for t in work if t["exp_end_date"]),
                      default=None))
        status = p.get("status") or "Open"
        late = (as_of - due).days if (status not in CLOSED and due and due < as_of) else 0
        late = max(late, max((int(t["days_late"] or 0) for t in open_), default=0))
        if status == "Completed":
            stage = "completed"
        elif status == "Cancelled":
            stage = "cancelled"
        elif late > 0:
            stage = "overdue"
        elif not done and not num(p.get("percent_complete")):
            stage = "not_started"
        else:
            stage = "in_progress"
        engineers = list(dict.fromkeys(n for t in work for n in _names(t["engineers"])))
        projects.append({
            "name": p["name"], "title": p.get("project_name") or p["name"],
            "status": status, "stage": stage, "type": p.get("project_type") or "",
            "customer": p.get("customer") or "", "start": start, "due": due,
            "finished": finished if status == "Completed" else None, "days_late": late,
            "tasks": len(work), "done": len(done), "open_tasks": len(unfinished),
            "engineers": engineers,
        })
    r._project_book = {"as_of": as_of, "projects": projects, "tasks": tasks}
    return r._project_book


def quarter_start(day):
    return dt.date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def year_back(day):
    """The first day of the month eleven months before: twelve whole months to as-of."""
    m = day.month - 11
    y = day.year + (m - 1) // 12
    return dt.date(y, (m - 1) % 12 + 1, 1)


def completed_since(b, since):
    return [p for p in b["projects"] if p["finished"] and since <= p["finished"] <= b["as_of"]]


def tasks_done_since(b, since):
    return [t for t in b["tasks"] if t["status"] == "Completed" and _day(t["completed_on"])
            and since <= _day(t["completed_on"]) <= b["as_of"]]


def on_time(tasks):
    """(on time, measured): finished on or before the Expected End Date."""
    measured = [t for t in tasks if t["exp_end_date"] and t["completed_on"]]
    ok = sum(1 for t in measured if _day(t["completed_on"]) <= _day(t["exp_end_date"]))
    return ok, len(measured)


def turnaround(projects):
    """Median days from a project's start to its finish, over those recording both."""
    days = [(p["finished"] - p["start"]).days for p in projects
            if p["finished"] and p["start"] and p["finished"] >= p["start"]]
    return (median(days) if days else None), len(days)


def _plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


# --------------------------------------------------------------------------- the cards
PROJECTS = "/app/project"


def _stage(r, stage):
    return [p for p in book(r)["projects"] if p["stage"] == stage]


def projects_open(r):
    b = book(r)
    open_ = [p for p in b["projects"] if p["status"] not in CLOSED]
    late = sum(1 for p in open_ if p["stage"] == "overdue")
    return len(open_), f"{late:,} of them overdue" if late else "none overdue", {
        "href": f"{PROJECTS}?status=Open"}


def projects_overdue(r):
    late = _stage(r, "overdue")
    worst = max((p["days_late"] for p in late), default=0)
    return len(late), (f"the longest {worst:,} days past due" if late else
                       "every open project is within its date"), {
        "href": f"{PROJECTS}?status=Open"}


def projects_not_started(r):
    n = len(_stage(r, "not_started"))
    return n, "no task finished yet", {"href": f"{PROJECTS}?status=Open"}


def projects_completed(r):
    b = book(r)
    n = sum(1 for p in b["projects"] if p["status"] == "Completed")
    return n, f"of {_plural(len(b['projects']), 'project')}", {
        "href": f"{PROJECTS}?status=Completed"}


def done_quarter(r):
    b = book(r)
    since = quarter_start(b["as_of"])
    n = len(completed_since(b, since))
    jobs = len(tasks_done_since(b, since))
    return n, f"{_plural(jobs, 'task')} finished since {since.strftime('%-d %b')}", {
        "href": f"{PROJECTS}?status=Completed"}


def done_year(r):
    b = book(r)
    since = year_back(b["as_of"])
    n = len(completed_since(b, since))
    jobs = len(tasks_done_since(b, since))
    return n, f"{_plural(jobs, 'task')} finished", {"href": f"{PROJECTS}?status=Completed"}


def customers_served(r):
    b = book(r)
    served = {t["customer"] for t in tasks_done_since(b, year_back(b["as_of"])) if t["customer"]}
    return len(served), "served in the last 12 months", {"href": f"{PROJECTS}?status=Completed"}


def finished_on_time(r):
    b = book(r)
    ok, measured = on_time(tasks_done_since(b, year_back(b["as_of"])))
    if not measured:
        return None, "no finished task records both dates", None
    return round(100 * ok / measured), f"of {_plural(measured, 'task')} with a due date", {
        "fact": "fact_task", "filters": {"status": "Completed"}}


def typical_turnaround(r):
    b = book(r)
    days, n = turnaround(completed_since(b, year_back(b["as_of"])))
    if days is None:
        return None, "no finished project records its start", None
    return round(days), f"start to finish, over {_plural(n, 'project')}", {
        "href": f"{PROJECTS}?status=Completed"}


FIGURES = {k.key: k for k in (
    Live("projects_open", "Open Projects", "count", projects_open, PROJECTS, source="fact_task"),
    Live("projects_overdue", "Overdue Projects", "count", projects_overdue, PROJECTS,
         source="fact_task"),
    Live("projects_not_started", "Projects Not Started", "count", projects_not_started,
         PROJECTS, source="fact_task"),
    Live("projects_completed", "Projects Completed", "count", projects_completed, PROJECTS,
         source="fact_task"),
    Live("projects_done_quarter", "Projects Completed This Quarter", "count", done_quarter,
         PROJECTS, source="fact_task"),
    Live("projects_done_year", "Projects Completed, Last 12 Months", "count", done_year,
         PROJECTS, source="fact_task"),
    Live("customers_served", "Customers Served, Last 12 Months", "count", customers_served,
         PROJECTS, source="fact_task"),
    Live("tasks_on_time", "Tasks Finished On Time", "percent", finished_on_time, PROJECTS,
         source="fact_task"),
    Live("projects_turnaround", "Typical Project Turnaround", "days", typical_turnaround,
         PROJECTS, source="fact_task"),
)}
