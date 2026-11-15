"""People Lookup and Leave, for the HR & Payroll screen and the analyst.

Three reads of the business's own ERPNext, whatever its version (v14 to v16) and whether
or not the HR app (HRMS) is installed:

    directory(business_code, q, department, branch, status, page)
        everyone on the books, searchable and filtered, a page at a time
    profile(business_code, employee)
        one person: employment, reporting line, leave balances by type, recent leave,
        attendance this month, open To-Dos, appraisals and training, assets in their
        care, and whether payroll is set up for them
    leave_overview(business_code, period)
        every active person's balance by leave type, who is away today and this week,
        the requests waiting for approval, and leave taken by department this year

Pay is never read. Not a salary, a structure's amount, a slip's total or a bank detail:
payroll appears only as "a salary structure is assigned" and "the last slip covered the
period ending ...". The fields read from Employee are named in EMPLOYEE_FIELDS and
nothing else is asked for.

The leave balances are worked out exactly as HRMS works out the balance it shows on a
Leave Application (hrms.hr.doctype.leave_application.leave_application.get_leave_details,
the same on v14, v15 and v16), from the Leave Ledger Entry:

    allocated   the allocation records in force on the date: the ledger's Leave
                Allocation entries (not expired, not leave-without-pay) that start on or
                before it -- new leave that runs to or past it, and leave carried
                forward into an allocation that covers it (get_leave_allocation_records)
    taken       the ledger's Leave Application entries over the allocation's period,
                each counted again in leave days -- holidays out unless the leave type
                counts them, half days as half -- after clipping it to the period, plus
                any Leave Encashment inside it (get_leaves_for_period)
    remaining   allocated less taken; carried-forward leave whose expiry has passed is
                dropped (get_leave_balance_on with consider_all_leaves_in_the_allocation
                _period, get_remaining_leaves)
    pending     the days on Open applications that start or end inside the period
                (get_leaves_pending_approval_for_period)
    expired     allocated - (remaining + taken), when above zero

Its total for a period matches HRMS's "Employee Leave Balance" report over the same
period: the report's opening balance plus new leave is "allocated", its leave taken is
"taken", and its closing balance is "remaining" (checked on Gigmann's ERPNext, 15 Nov
2026, for three employees: see insights/tests.py LeaveArithmetic).

A business whose ERPNext has no HR app, no leave types or no allocations gets a guide
to what to set up there (command_center/guides.py), never sample figures. A business
that does not answer gets {"kind": "unreachable"}, as every other screen part does.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

import frappe

from command_center.api.businesses import require_manager
from command_center.guides import LEAVE_STEPS, NO_HRMS_STEPS

PAGE_SIZE = 25
CACHE_SECONDS = 90
# Read from Employee, and nothing else: no pay, bank, identity or personal-contact field.
EMPLOYEE_FIELDS = ["name", "employee_name", "status", "department", "designation", "branch",
                   "employment_type", "date_of_joining", "relieving_date", "reports_to",
                   "company_email", "cell_number", "user_id", "image", "holiday_list",
                   "company"]
LEDGER_FIELDS = ["name", "employee", "leave_type", "transaction_type", "transaction_name",
                 "leaves", "from_date", "to_date", "is_carry_forward", "is_expired",
                 "is_lwp", "holiday_list"]
APPLICATION_FIELDS = ["name", "employee", "employee_name", "leave_type", "from_date",
                      "to_date", "total_leave_days", "half_day", "half_day_date", "status",
                      "docstatus", "posting_date", "leave_approver", "leave_approver_name",
                      "department"]
ATTENDANCE_STATES = ("Present", "Absent", "On Leave", "Half Day", "Work From Home")


# --------------------------------------------------------------------------- the API
@frappe.whitelist()
def directory(business_code: str | None = None, q: str | None = None,
              department: str | None = None, branch: str | None = None,
              status: str | None = None, page: int | str = 1,
              page_size: int | str = PAGE_SIZE) -> dict:
    """Everyone on the books, searched and filtered, a page at a time."""
    require_manager()
    ctx = _Ctx(business_code)
    try:
        staff = _staff(ctx)
    except Exception as e:
        return _failed(ctx, e)
    if not staff:
        return _guide_answer(ctx, "No employee is recorded in this ERPNext yet.",
                             PEOPLE_STEPS, "/app/employee/new")
    return search(staff, q=q, department=department, branch=branch, status=status,
                  page=page, page_size=page_size) | {"kind": "directory",
                                                     "as_of": str(_today())}


@frappe.whitelist()
def profile(business_code: str | None = None, employee: str | None = None) -> dict:
    """One person: everything ERPNext records about them, except their pay."""
    require_manager()
    if not employee:
        frappe.throw("Say which employee.")
    ctx = _Ctx(business_code)
    key = f"cc:people:profile:{ctx.code}:{employee}"
    cached = frappe.cache().get_value(key)
    if cached:
        return cached
    try:
        out = _profile(ctx, str(employee))
    except Exception as e:
        return _failed(ctx, e)
    frappe.cache().set_value(key, out, expires_in_sec=CACHE_SECONDS)
    return out


@frappe.whitelist()
def leave_overview(business_code: str | None = None, period: str | None = None) -> dict:
    """Every active person's leave by type, who is away, what is waiting, by department."""
    require_manager()
    ctx = _Ctx(business_code)
    year = _year(period)
    key = f"cc:people:leave:{ctx.code}:{year}"
    cached = frappe.cache().get_value(key)
    if cached:
        return cached
    try:
        out = _overview(ctx, year)
    except Exception as e:
        return _failed(ctx, e)
    frappe.cache().set_value(key, out, expires_in_sec=CACHE_SECONDS)
    return out


# --------------------------------------------------------------------------- reading
class _Ctx:
    """The business, its reader (the screens' own, which fails fast once the business
    is known to be down) and its site address."""

    def __init__(self, business_code):
        from command_center.api.panels import _Guarded
        from command_center.kpi.live import _Reader
        self.r = _Guarded(_Reader(business_code))
        self.code = self.r.code
        self._meta = {}

    @property
    def site(self) -> str:
        return "" if self.r.local else (self.r.conn.base_url or "").rstrip("/")

    def all(self, doctype, filters=None, fields=None, **kw):
        return self.r.all(doctype, filters=filters or {}, fields=fields or ["name"], **kw)

    def read(self, doctype, filters, fields, **kw):
        """A read that refuses a reply missing a column (kpi/live._read)."""
        from command_center.kpi.live import _read
        return _read(self.r, doctype, filters, fields, **kw)

    def has(self, doctype) -> bool:
        """Whether this ERPNext has the doctype (and lets the platform count it). A
        business that does not answer is not "no HR app": that is raised."""
        if doctype not in self._meta:
            from command_center.kpi.live_departments import is_down
            try:
                self.r.count(doctype, {})
                self._meta[doctype] = True
            except Exception as e:
                if is_down(e):
                    raise
                self._meta[doctype] = False
        return self._meta[doctype]

    def business(self) -> dict:
        row = frappe.db.get_value("Connected Business", {"business_code": self.code},
                                  ["business_name", "last_sync"], as_dict=True) or {}
        return {"business": row.get("business_name") or self.code or "",
                "last_loaded": str(row["last_sync"]) if row.get("last_sync") else None}


def _failed(ctx, error) -> dict:
    """Can't reach the business: the standard state. Anything else is a fault, logged."""
    from command_center.kpi.live_departments import is_down
    if is_down(error):
        return {"kind": "unreachable", **ctx.business()}
    from command_center.connectors.base import ConnectorError
    if isinstance(error, ConnectorError):
        return {"kind": "refused", "message": str(error)[:300]}
    frappe.log_error(title="Command Center people", message=frappe.get_traceback())
    return {"kind": "failed"}


def _guide_answer(ctx, text, steps, path) -> dict:
    from command_center.guides import guide
    return {"kind": "guide", "guide": guide(ctx.code, text, steps, path)}


def _today() -> dt.date:
    return frappe.utils.getdate(frappe.utils.today())


def _d(v) -> dt.date | None:
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


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _year(period) -> int:
    m = re.match(r"^\s*(\d{4})", str(period or ""))
    return int(m.group(1)) if m else _today().year


def _iso(v) -> str | None:
    d = _d(v)
    return d.isoformat() if d else None


# --------------------------------------------------------------------------- the directory
PEOPLE_STEPS = ["Open Employee, click New for each person, and set Department, Designation "
                "and Branch.",
                "Set Reports To on each person to record the reporting line.",
                "Set Status to Left, with the Relieving Date, when someone goes."]


def _staff(ctx) -> list[dict]:
    """Everyone on the books, as the directory shows them, read once per ninety seconds."""
    key = f"cc:people:staff:{ctx.code}"
    cached = frappe.cache().get_value(key)
    if cached is not None:
        return cached
    rows = ctx.read("Employee", {}, EMPLOYEE_FIELDS, limit=20000, order_by="employee_name asc")
    names = {r["name"]: (r.get("employee_name") or r["name"]) for r in rows}
    site = ctx.site
    today = _today()
    out = []
    for r in rows:
        joined, left = _d(r.get("date_of_joining")), _d(r.get("relieving_date"))
        end = left if (left and (r.get("status") == "Left" or left <= today)) else today
        days = (end - joined).days if joined and end >= joined else None
        out.append({
            "employee": r["name"],
            "name": (r.get("employee_name") or r["name"]).strip(),
            "designation": r.get("designation") or "",
            "department": r.get("department") or "",
            "branch": r.get("branch") or "",
            "status": r.get("status") or "Active",
            "employment_type": r.get("employment_type") or "",
            "date_of_joining": _iso(joined),
            "relieving_date": _iso(left),
            "tenure_days": days,
            "tenure": _tenure(days),
            "reports_to": r.get("reports_to") or "",
            "reports_to_name": names.get(r.get("reports_to"), "") if r.get("reports_to") else "",
            "email": r.get("company_email") or "",
            "phone": r.get("cell_number") or "",
            "has_user": bool(r.get("user_id")),
            "photo": _photo(site, r.get("image")),
            "href": f"{site}/app/employee/{r['name']}" if site else "",
            # Kept for the profile's reads; never sent to the screen (see _public).
            "_user": r.get("user_id") or "",
            "_holiday_list": r.get("holiday_list") or "",
        })
    out.sort(key=lambda p: (p["status"] != "Active", p["name"].lower()))
    frappe.cache().set_value(key, out, expires_in_sec=CACHE_SECONDS)
    return out


def _public(p) -> dict:
    return {k: v for k, v in p.items() if not k.startswith("_")}


def _tenure(days) -> str:
    if days is None:
        return ""
    years, rest = divmod(int(days), 365)
    months = rest // 30
    if not years and not months:
        return "under a month"
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    return " ".join(parts)


def _photo(site, image) -> str:
    """A photo the browser can show: a public file on the business's site. A private
    file needs a session there, so it is not offered."""
    image = (image or "").strip()
    if image.startswith(("http://", "https://")):
        return image
    if image.startswith("/files/") and site:
        return site + image
    return ""


def search(staff, q=None, department=None, branch=None, status=None, page=1,
           page_size=PAGE_SIZE) -> dict:
    """The directory's search, filters and paging, over the staff list."""
    words = [w for w in re.split(r"\s+", (q or "").lower().strip()) if w]

    def hit(p):
        if department and p["department"] != department:
            return False
        if branch and p["branch"] != branch:
            return False
        if status and p["status"] != status:
            return False
        hay = " ".join([p["name"], p["employee"], p["designation"], p["department"],
                        p["branch"], p["email"]]).lower()
        return all(w in hay for w in words)

    found = [p for p in staff if hit(p)]
    try:
        size = max(1, min(int(page_size or PAGE_SIZE), 200))
    except (TypeError, ValueError):
        size = PAGE_SIZE
    pages = max(1, -(-len(found) // size))
    try:
        page = min(max(1, int(page or 1)), pages)
    except (TypeError, ValueError):
        page = 1
    return {
        "rows": [_public(p) for p in found[(page - 1) * size: page * size]],
        "total": len(found), "on_books": len(staff),
        "page": page, "pages": pages, "page_size": size,
        "filters": {
            "departments": sorted({p["department"] for p in staff if p["department"]}),
            "branches": sorted({p["branch"] for p in staff if p["branch"]}),
            "statuses": sorted({p["status"] for p in staff if p["status"]}),
        },
    }


def resolve(staff, text) -> list[dict]:
    """Employees matching an ID or a name (or part of one), best first."""
    t = (text or "").strip().lower()
    if not t:
        return []
    exact = [p for p in staff if p["employee"].lower() == t or p["name"].lower() == t]
    if exact:
        return exact
    words = t.split()
    return [p for p in staff
            if all(w in f"{p['name']} {p['employee']}".lower() for w in words)]


# --------------------------------------------------------------------------- leave maths
# Pure functions over plain rows, so the arithmetic can be checked by hand (tests) and
# against HRMS's own report (Kraken, read-only). Names follow HRMS's functions.
def norm_entry(r) -> dict:
    return {"employee": r.get("employee"), "leave_type": r.get("leave_type"),
            "transaction_type": r.get("transaction_type"),
            "transaction_name": r.get("transaction_name"), "leaves": _f(r.get("leaves")),
            "from_date": _d(r.get("from_date")), "to_date": _d(r.get("to_date")),
            "is_carry_forward": bool(int(_f(r.get("is_carry_forward")))),
            "is_expired": bool(int(_f(r.get("is_expired")))),
            "is_lwp": bool(int(_f(r.get("is_lwp")))),
            "holiday_list": r.get("holiday_list") or ""}


def allocation_records(entries, allocations, date) -> dict:
    """get_leave_allocation_records: leave type -> the allocation in force on `date`.

    entries: one employee's submitted ledger entries (norm_entry); allocations: Leave
    Allocation name -> {"from_date", "to_date"} (the ledger joins to it)."""
    out = {}
    for e in entries:
        if e["transaction_type"] != "Leave Allocation" or e["is_expired"] or e["is_lwp"]:
            continue
        if not e["from_date"] or not e["to_date"] or e["from_date"] > date:
            continue
        la = allocations.get(e["transaction_name"])
        if not la:
            continue
        a_from, a_to = _d(la["from_date"]), _d(la["to_date"])
        if e["is_carry_forward"]:
            # carried-forward leave counts only into the allocation that covers the date
            if not (a_from <= e["to_date"] <= a_to and a_from <= date <= a_to):
                continue
        elif e["to_date"] < date:
            continue
        g = out.setdefault(e["leave_type"], {"leave_type": e["leave_type"], "cf": 0.0,
                                             "new": 0.0, "from_date": e["from_date"],
                                             "to_date": e["to_date"]})
        g["cf" if e["is_carry_forward"] else "new"] += e["leaves"]
        g["from_date"] = min(g["from_date"], e["from_date"])
        g["to_date"] = max(g["to_date"], e["to_date"])
    for g in out.values():
        g["total"] = g["cf"] + g["new"]
    return out


def leave_days(frm, to, half_day=False, half_day_date=None, include_holiday=False,
               holidays=0) -> float:
    """get_number_of_leave_days."""
    if half_day:
        if frm == to:
            n = 0.5
        elif half_day_date and frm <= half_day_date <= to:
            n = (to - frm).days + 0.5
        else:
            n = (to - frm).days + 1
    else:
        n = (to - frm).days + 1
    if not include_holiday:
        n -= holidays
    return float(n)


def leaves_for_period(entries, leave_type, frm, to, include_holiday=False,
                      holidays=None, half_days=None, default_list="") -> float:
    """get_leaves_for_period (skip_expired_leaves=True): leave used in [frm, to], as a
    negative number. holidays(list_name, a, b) counts a list's holidays in [a, b];
    half_days maps a Leave Application to its half-day date."""
    days = 0.0
    for e in entries:
        if e["leave_type"] != leave_type or not (e["leaves"] < 0 or e["is_expired"]):
            continue
        a, b = e["from_date"], e["to_date"]
        if not a or not b:
            continue
        if not (frm <= a <= to or frm <= b <= to or (a < frm and b > to)):
            continue
        inclusive = a >= frm and b <= to
        kind = e["transaction_type"]
        if inclusive and kind == "Leave Encashment":
            days += e["leaves"]
        elif kind == "Leave Application":
            a, b = max(a, frm), min(b, to)
            half = bool(e["leaves"] % 1)
            hd = _d((half_days or {}).get(e["transaction_name"])) if half else None
            off = 0
            if not include_holiday and holidays:
                off = holidays(e["holiday_list"] or default_list, a, b)
            days -= leave_days(a, b, half, hd, include_holiday, off)
    return days


def leave_details(entries, allocations, date, leave_types=None, open_applications=(),
                  holidays=None, half_days=None, default_list="") -> list[dict]:
    """get_leave_details: per leave type in force on `date`, allocated / taken / pending /
    remaining / expired, over that allocation's period. leave_types: name ->
    {"include_holiday"}; open_applications: Open Leave Applications (any not cancelled)."""
    out = []
    types = leave_types or {}
    for lt, alloc in sorted(allocation_records(entries, allocations, date).items()):
        inc = bool(int(_f((types.get(lt) or {}).get("include_holiday"))))
        a_from, a_to = alloc["from_date"], alloc["to_date"]
        used = leaves_for_period(entries, lt, a_from, a_to, inc, holidays, half_days,
                                 default_list)
        balance = alloc["total"] + used
        # carried-forward leave with an expiry of its own (get_allocation_expiry_for_cf_leaves)
        cf_expiry = min((e["to_date"] for e in entries
                         if e["leave_type"] == lt and e["is_carry_forward"]
                         and e["transaction_type"] == "Leave Allocation"
                         and e["to_date"] and a_from <= e["to_date"] <= a_to), default=None)
        if cf_expiry and alloc["cf"]:
            cf_left = 0.0 if date > cf_expiry else alloc["cf"] + used
            balance = alloc["new"] + cf_left
        taken = -used
        pending = sum(_f(x.get("total_leave_days")) for x in open_applications
                      if x.get("leave_type") == lt and (
                          a_from <= (_d(x.get("from_date")) or dt.date.min) <= a_to
                          or a_from <= (_d(x.get("to_date")) or dt.date.min) <= a_to))
        expired = alloc["total"] - (balance + taken)
        out.append({"leave_type": lt, "from_date": a_from.isoformat(),
                    "to_date": a_to.isoformat(), "allocated": _r(alloc["total"]),
                    "carried_forward": _r(alloc["cf"]), "new": _r(alloc["new"]),
                    "taken": _r(taken), "pending": _r(pending),
                    "remaining": _r(balance), "expired": _r(expired) if expired > 0 else 0.0})
    return out


def _r(v) -> float:
    v = round(float(v or 0), 3)
    return 0.0 if v == 0 else v


# --------------------------------------------------------------------------- leave reads
def _leave_ready(ctx) -> dict | None:
    """None when leave can be read; otherwise the guide that says what to set up."""
    if not ctx.has("Leave Type") or not ctx.has("Leave Ledger Entry"):
        return _guide_answer(ctx, "Leave is not set up in this ERPNext: the HR app is not "
                                  "installed, so there are no leave types, allocations or "
                                  "applications to read.", NO_HRMS_STEPS, "/app")
    if not ctx.r.count("Leave Type", {}):
        return _guide_answer(ctx, "No leave type is set up in this ERPNext yet, so no one "
                                  "has any leave to show.", LEAVE_STEPS, "/app/leave-type/new")
    return None


class _LeaveBook:
    """The reads behind the balances, for some employees and dates: the leave types,
    the allocations, the ledger, the holiday lists and the half days."""

    def __init__(self, ctx, employees=None, since=None, until=None):
        self.ctx = ctx
        emp = {"employee": ["in", sorted(employees)]} if employees else {}
        self.types = {t["name"]: t for t in ctx.read(
            "Leave Type", {}, ["name", "include_holiday", "is_lwp"], limit=500)}
        af = {"docstatus": 1, **emp}
        if since:
            af["to_date"] = [">=", str(since)]
        self.allocs = {a["name"]: a for a in ctx.read(
            "Leave Allocation", af, ["name", "employee", "leave_type", "from_date", "to_date"],
            limit=50000)}
        lf = {"docstatus": 1, **emp}
        if since:
            lo = min([_d(a["from_date"]) for a in self.allocs.values()] + [since])
            lf["to_date"] = [">=", str(lo)]
        if until:
            hi = max([_d(a["to_date"]) for a in self.allocs.values()] + [until])
            lf["from_date"] = ["<=", str(hi)]
        rows = ctx.read("Leave Ledger Entry", lf, LEDGER_FIELDS, limit=100000)
        self.entries = defaultdict(list)
        for r in rows:
            e = norm_entry(r)
            self.entries[e["employee"]].append(e)
        self._holidays = None
        self._half = None

    def half_days(self) -> dict:
        """Application -> half-day date, for the ledger entries with a half day in them."""
        if self._half is None:
            names = sorted({e["transaction_name"] for es in self.entries.values() for e in es
                            if e["transaction_type"] == "Leave Application" and e["leaves"] % 1})
            self._half = {}
            for i in range(0, len(names), 200):
                for a in self.ctx.read("Leave Application", {"name": ["in", names[i:i + 200]]},
                                       ["name", "half_day_date"], limit=200):
                    self._half[a["name"]] = a.get("half_day_date")
        return self._half

    def holidays(self, lists, frm, to):
        """(list, a, b) -> holidays in [a, b], from each Holiday List's own rows."""
        if self._holidays is None:
            self._holidays = defaultdict(set)
            lists = sorted({x for x in lists if x})
            if lists and self.ctx.has("Holiday List"):
                for h in self.ctx.read("Holiday", {"parent": ["in", lists],
                                                   "holiday_date": ["between", [str(frm), str(to)]]},
                                       ["parent", "holiday_date"], parent="Holiday List",
                                       limit=100000):
                    d = _d(h.get("holiday_date"))
                    if d:
                        self._holidays[h["parent"]].add(d)
        book = self._holidays
        return lambda name, a, b: sum(1 for d in book.get(name, ()) if a <= d <= b)

    def window(self):
        dates = [d for es in self.entries.values() for e in es
                 for d in (e["from_date"], e["to_date"]) if d]
        return (min(dates), max(dates)) if dates else (_today(), _today())

    def details(self, employee, date, default_list="", open_apps=()):
        es = self.entries.get(employee, [])
        lists = {e["holiday_list"] for es_ in self.entries.values() for e in es_} | {default_list}
        frm, to = self.window()
        return leave_details(es, self.allocs, date, self.types, open_apps,
                             self.holidays(lists, frm, to), self.half_days(), default_list)

    def taken(self, employee, frm, to, default_list="") -> float:
        es = self.entries.get(employee, [])
        lists = {e["holiday_list"] for es_ in self.entries.values() for e in es_} | {default_list}
        w_from, w_to = self.window()
        hol = self.holidays(lists, w_from, w_to)
        return -sum(leaves_for_period(es, lt, frm, to,
                                      bool(int(_f(self.types.get(lt, {}).get("include_holiday")))),
                                      hol, self.half_days(), default_list)
                    for lt in {e["leave_type"] for e in es})


def _application(a, site, today) -> dict:
    frm, to = _d(a.get("from_date")), _d(a.get("to_date"))
    posted = _d(a.get("posting_date"))
    return {"name": a["name"], "employee": a.get("employee") or "",
            "employee_name": (a.get("employee_name") or "").strip(),
            "leave_type": a.get("leave_type") or "", "from_date": _iso(frm), "to_date": _iso(to),
            "days": _r(a.get("total_leave_days")), "status": a.get("status") or "",
            "half_day": bool(int(_f(a.get("half_day")))),
            "posted": _iso(posted), "waiting_days": (today - posted).days if posted else None,
            "approver": (a.get("leave_approver_name") or a.get("leave_approver") or "").strip(),
            "href": f"{site}/app/leave-application/{a['name']}" if site else ""}


# --------------------------------------------------------------------------- the profile
def _profile(ctx, employee) -> dict:
    staff = _staff(ctx)
    person = next((p for p in staff if p["employee"] == employee), None)
    if not person:
        return {"kind": "missing", "message": f"No employee {employee} on the books."}
    today = _today()
    site = ctx.site
    manager = next((p for p in staff if p["employee"] == person["reports_to"]), None)
    reports = [p for p in staff if p["reports_to"] == employee]

    def brief(p):
        return {"employee": p["employee"], "name": p["name"], "designation": p["designation"],
                "status": p["status"]}

    out = {"kind": "profile", "as_of": today.isoformat(), "person": _public(person),
           "manager": brief(manager) if manager else None,
           "reports": [brief(p) for p in sorted(reports, key=lambda p: (p["status"] != "Active",
                                                                        p["name"]))]}
    for name, fn in (("leave", _profile_leave), ("applications", _profile_applications),
                     ("attendance", _profile_attendance), ("todos", _profile_todos),
                     ("appraisals", _profile_appraisals), ("training", _profile_training),
                     ("assets", _profile_assets), ("payroll", _profile_payroll)):
        out[name] = _section(fn, ctx, person, today, site)
    return out


def _section(fn, ctx, person, today, site):
    """One part of the profile. A part ERPNext refuses says so; only a business that
    does not answer fails the whole profile."""
    from command_center.connectors.base import ConnectorError
    from command_center.kpi.live_departments import is_down
    try:
        return fn(ctx, person, today, site)
    except Exception as e:
        if is_down(e):
            raise
        if not isinstance(e, ConnectorError) and not isinstance(e, frappe.ValidationError):
            frappe.log_error(title=f"Command Center people: {fn.__name__}",
                             message=frappe.get_traceback())
        return {"state": "unreadable"}


def _profile_leave(ctx, person, today, site):
    guide = _leave_ready(ctx)
    if guide:
        return {"state": "guide", "guide": guide["guide"]}
    emp = person["employee"]
    book = _LeaveBook(ctx, [emp])
    open_apps = ctx.read("Leave Application", {"employee": emp, "status": "Open",
                                               "docstatus": ["<", 2]},
                         ["name", "leave_type", "from_date", "to_date", "total_leave_days"],
                         limit=500)
    rows = book.details(emp, today, person["_holiday_list"], open_apps)
    if not rows:
        from command_center.guides import guide
        return {"state": "none", "guide": guide(
            ctx.code, "No leave is allocated to this person for the current period.",
            LEAVE_STEPS[2:], f"/app/leave-allocation/new?employee={emp}")}
    return {"state": "ok", "types": rows,
            "href": f"{site}/app/query-report/Employee Leave Balance?employee={emp}" if site else ""}


def _profile_applications(ctx, person, today, site):
    if not ctx.has("Leave Application"):
        return {"state": "not_installed"}
    rows = ctx.read("Leave Application", {"employee": person["employee"]}, APPLICATION_FIELDS,
                    limit=10, order_by="from_date desc")
    rows.sort(key=lambda a: str(a.get("from_date") or ""), reverse=True)
    return {"state": "ok", "items": [_application(a, site, today) for a in rows[:10]]}


def _profile_attendance(ctx, person, today, site):
    if not ctx.has("Attendance"):
        return {"state": "not_installed"}
    first = today.replace(day=1)
    rows = ctx.read("Attendance", {"employee": person["employee"], "docstatus": 1,
                                   "attendance_date": ["between", [str(first), str(today)]]},
                    ["name", "status", "late_entry", "early_exit"], limit=62)
    counts = {s: 0 for s in ATTENDANCE_STATES}
    for a in rows:
        counts[a.get("status") or "Present"] = counts.get(a.get("status") or "Present", 0) + 1
    # late_entry and early_exit exist from v13; a site without them answers None
    late = (sum(1 for a in rows if int(_f(a.get("late_entry"))))
            if any(a.get("late_entry") is not None for a in rows) else None)
    early = (sum(1 for a in rows if int(_f(a.get("early_exit"))))
             if any(a.get("early_exit") is not None for a in rows) else None)
    return {"state": "ok" if rows else "none", "month": first.strftime("%B"),
            "from": first.isoformat(), "to": today.isoformat(), "marked": len(rows),
            "counts": counts, "late": late, "early_exit": early}


def _profile_todos(ctx, person, today, site):
    user = person["_user"]
    if not user:
        return {"state": "no_user"}
    filters = {"allocated_to": user, "status": "Open"}
    n = ctx.r.count("ToDo", filters)
    rows = ctx.read("ToDo", filters, ["name", "description", "reference_type", "reference_name",
                                      "date", "priority"], limit=8, order_by="modified desc")
    items = []
    for t in rows:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t.get("description") or "")).strip()
        ref = t.get("reference_type"), t.get("reference_name")
        slug = (ref[0] or "").lower().replace(" ", "-")
        items.append({"text": (text[:140] + "…") if len(text) > 140 else text,
                      "reference": f"{ref[0]} {ref[1]}" if ref[0] and ref[1] else "",
                      "due": _iso(t.get("date")), "priority": t.get("priority") or "",
                      "href": (f"{site}/app/{slug}/{ref[1]}" if ref[0] and ref[1]
                               else f"{site}/app/todo/{t['name']}") if site else ""})
    return {"state": "ok", "open": int(n or 0), "items": items}


def _profile_appraisals(ctx, person, today, site):
    if not ctx.has("Appraisal"):
        return {"state": "not_installed"}
    rows = ctx.read("Appraisal", {"employee": person["employee"], "docstatus": ["<", 2]},
                    ["name", "start_date", "end_date", "status", "docstatus", "final_score",
                     "total_score"], limit=5, order_by="end_date desc")
    rows.sort(key=lambda a: str(a.get("end_date") or ""), reverse=True)
    return {"state": "ok", "items": [{
        "name": a["name"], "from": _iso(a.get("start_date")), "to": _iso(a.get("end_date")),
        "status": a.get("status") or ("Submitted" if a.get("docstatus") == 1 else "Draft"),
        "score": (_r(a.get("final_score")) if a.get("final_score") is not None
                  else _r(a.get("total_score")) if a.get("total_score") is not None else None),
        "href": f"{site}/app/appraisal/{a['name']}" if site else ""} for a in rows]}


def _profile_training(ctx, person, today, site):
    if not ctx.has("Training Event"):
        return {"state": "not_installed"}
    rows = ctx.read("Training Event Employee", {"employee": person["employee"]},
                    ["parent", "status", "attendance"], parent="Training Event", limit=20)
    names = sorted({r["parent"] for r in rows if r.get("parent")})
    events = {e["name"]: e for e in ctx.read(
        "Training Event", {"name": ["in", names]}, ["name", "event_name", "start_time",
                                                    "docstatus"], limit=len(names))} if names else {}
    items = []
    for r in rows:
        e = events.get(r.get("parent")) or {}
        items.append({"event": e.get("event_name") or r.get("parent"),
                      "date": _iso(e.get("start_time")),
                      "status": r.get("attendance") or r.get("status") or "",
                      "href": f"{site}/app/training-event/{r['parent']}" if site else ""})
    items.sort(key=lambda x: x["date"] or "", reverse=True)
    return {"state": "ok", "items": items[:5]}


def _profile_assets(ctx, person, today, site):
    if not ctx.has("Asset"):
        return {"state": "not_installed"}
    conn = getattr(ctx.r, "conn", None)
    have = conn.fieldnames("Asset") if conn is not None else None
    if have is not None and "custodian" not in have:
        return {"state": "not_recorded"}
    rows = ctx.read("Asset", {"custodian": person["employee"], "docstatus": 1},
                    ["name", "asset_name", "status", "location"], limit=20)
    return {"state": "ok", "items": [{
        "name": a["name"], "asset": a.get("asset_name") or a["name"],
        "status": a.get("status") or "", "location": a.get("location") or "",
        "href": f"{site}/app/asset/{a['name']}" if site else ""} for a in rows]}


def _profile_payroll(ctx, person, today, site):
    """Whether payroll is set up for the person -- never what they are paid."""
    if not ctx.has("Salary Slip"):
        return {"state": "not_installed"}
    emp = person["employee"]
    structure = (ctx.r.count("Salary Structure Assignment", {"employee": emp, "docstatus": 1}) > 0
                 if ctx.has("Salary Structure Assignment") else None)
    last = ctx.read("Salary Slip", {"employee": emp, "docstatus": 1}, ["end_date"], limit=1,
                    order_by="end_date desc")
    return {"state": "ok", "structure": structure,
            "last_slip": _iso(last[0].get("end_date")) if last else None}


# --------------------------------------------------------------------------- the overview
def _overview(ctx, year) -> dict:
    staff = _staff(ctx)
    active = [p for p in staff if p["status"] == "Active"]
    if not active:
        return _guide_answer(ctx, "No active employee is recorded in this ERPNext yet.",
                             PEOPLE_STEPS, "/app/employee/new")
    guide = _leave_ready(ctx)
    if guide:
        return guide
    today = _today()
    start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
    # Balances as they stand today in the current year, at the year's end for a past
    # one, and as the year opens for a year still to come.
    date = today if start <= today <= end else end if end < today else start
    site = ctx.site
    ids = {p["employee"] for p in active}
    book = _LeaveBook(ctx, None, since=min(start, date), until=max(end, date))
    open_apps = ctx.read("Leave Application", {"status": "Open", "docstatus": ["<", 2]},
                         APPLICATION_FIELDS, limit=5000)
    by_emp = defaultdict(list)
    for a in open_apps:
        by_emp[a.get("employee")].append(a)

    types_seen, rows = set(), []
    for p in active:
        details = book.details(p["employee"], date, p["_holiday_list"], by_emp.get(p["employee"], ()))
        types_seen |= {d["leave_type"] for d in details}
        rows.append({"employee": p["employee"], "name": p["name"], "department": p["department"],
                     "designation": p["designation"],
                     "balances": {d["leave_type"]: d for d in details}})
    if not types_seen:
        from command_center.guides import guide
        return {"kind": "guide", "guide": guide(
            ctx.code, f"No one has leave allocated for the period covering "
                      f"{date.strftime('%-d %B %Y')}, so there is no balance to show.",
            LEAVE_STEPS[1:], "/app/leave-allocation/new")}

    # who is away: approved leave over this week (Monday to Sunday) and today
    week_from = date - dt.timedelta(days=date.weekday())
    week_to = week_from + dt.timedelta(days=6)
    approved = ctx.read("Leave Application", {"docstatus": 1, "status": "Approved",
                                              "from_date": ["<=", str(week_to)],
                                              "to_date": [">=", str(week_from)]},
                        APPLICATION_FIELDS, limit=2000)
    away = [_application(a, site, date) for a in approved if a.get("employee") in ids]
    away.sort(key=lambda a: (a["from_date"] or "", a["employee_name"]))
    today_away = [a for a in away if a["from_date"] and a["to_date"]
                  and a["from_date"] <= date.isoformat() <= a["to_date"]]

    pending = [_application(a, site, date) for a in open_apps if a.get("employee") in ids]
    pending.sort(key=lambda a: -(a["waiting_days"] or 0))

    # leave taken this year, to the date, by department
    dept = defaultdict(lambda: {"people": 0, "days": 0.0, "with_leave": 0})
    upto = min(end, date)
    for p in active:
        d = dept[p["department"] or "No department"]
        d["people"] += 1
        days = book.taken(p["employee"], start, upto, p["_holiday_list"]) if upto >= start else 0.0
        d["days"] += days
        d["with_leave"] += 1 if days > 0 else 0
    departments = sorted(({"department": k, "people": v["people"], "days": _r(v["days"]),
                           "with_leave": v["with_leave"],
                           "per_person": _r(v["days"] / v["people"]) if v["people"] else None}
                          for k, v in dept.items()), key=lambda x: (-x["days"], x["department"]))

    counts = defaultdict(int)
    for r in rows:
        for lt in r["balances"]:
            counts[lt] += 1
    types = sorted(types_seen, key=lambda lt: (-counts[lt], lt))
    return {"kind": "leave", "year": year, "as_of": date.isoformat(),
            "week": {"from": week_from.isoformat(), "to": week_to.isoformat()},
            "types": [{"name": lt, "people": counts[lt]} for lt in types],
            "rows": rows, "without": sum(1 for r in rows if not r["balances"]),
            "away_today": today_away, "away_week": away, "pending": pending,
            "departments": departments,
            "href": f"{site}/app/query-report/Employee Leave Balance" if site else ""}


# --------------------------------------------------------------------------- for the analyst
def for_analyst(business_code, person=None, period=None) -> dict:
    """The leave picture for a question (ask/tools.leave_and_people): one person's
    balances and recent leave, or everyone's -- who is away, what is waiting, balances.
    No contact detail, photo or pay leaves the platform this way."""
    ctx = _Ctx(business_code)
    staff = _staff(ctx)
    if person:
        found = resolve(staff, person)
        if not found:
            return {"answered": False, "note": f"No employee matches {person!r}."}
        if len(found) > 1:
            return {"answered": False, "note": "More than one employee matches; ask again "
                                               "with the full name or the employee ID.",
                    "matches": [_brief(p) for p in found[:15]]}
        p = found[0]
        today = _today()
        return {"answered": True, "as_of": today.isoformat(), "person": _brief(p),
                "leave": _section(_profile_leave, ctx, p, today, ctx.site),
                "recent_leave": _section(_profile_applications, ctx, p, today, ctx.site)}
    out = _overview(ctx, _year(period))
    if out.get("kind") != "leave":
        return {"answered": False, **out}
    return {"answered": True, "as_of": out["as_of"], "week": out["week"],
            "away_today": out["away_today"], "away_this_week": out["away_week"],
            "pending_approval": out["pending"], "by_department": out["departments"],
            "leave_types": out["types"],
            "balances": [{"employee": r["employee"], "name": r["name"],
                          "department": r["department"],
                          "balances": [{k: b[k] for k in ("leave_type", "allocated", "taken",
                                                          "pending", "remaining")}
                                       for b in r["balances"].values()]}
                         for r in out["rows"]],
            "without_allocation": out["without"]}


def people_for_analyst(business_code, text=None, department=None, status=None) -> dict:
    """The directory for a question: who works where, under whom, since when."""
    staff = _staff(_Ctx(business_code))
    hits = resolve(staff, text) if text else staff
    hits = [p for p in hits if (not department or p["department"] == department)
            and (not status or p["status"] == status)]
    return {"total": len(hits), "on_books": len(staff),
            "people": [_brief(p) | {"reports_to": p["reports_to_name"],
                                    "joined": p["date_of_joining"], "tenure": p["tenure"],
                                    "has_login": p["has_user"]} for p in hits[:50]],
            "shown": min(len(hits), 50)}


def _brief(p) -> dict:
    return {"employee": p["employee"], "name": p["name"], "designation": p["designation"],
            "department": p["department"], "branch": p["branch"], "status": p["status"]}
