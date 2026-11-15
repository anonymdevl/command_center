"""frappe.utils -- the date, number and text helpers the business logic uses.

Same names, same behaviour: dates come back as datetime.date, "today" is in the
platform's time zone, flt/cint never raise on junk. The figures were tested against
Frappe's versions; these are written to give the same answers.
"""

from __future__ import annotations

import calendar
import datetime as _dt
import html as _html
import re
from decimal import Decimal

from insights.compat.state import local

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def now_datetime() -> _dt.datetime:
    return _dt.datetime.now()


def now() -> str:
    return now_datetime().strftime(DATETIME_FORMAT)


def nowdate() -> str:
    return now_datetime().strftime(DATE_FORMAT)


def today() -> str:
    return nowdate()


def getdate(value=None) -> _dt.date | None:
    if value is None:
        return now_datetime().date()
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return _dt.datetime.strptime(s[:10], fmt).date()
            except ValueError:
                continue
    raise ValueError(f"{value!r} is not a date")


def get_datetime(value=None) -> _dt.datetime | None:
    if value is None:
        return now_datetime()
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.date):
        return _dt.datetime(value.year, value.month, value.day)
    s = str(value).strip()
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("T", " ")[:26])
    except ValueError:
        return _dt.datetime.combine(getdate(s), _dt.time())


def get_datetime_str(value) -> str:
    return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")


def add_days(date, days: int):
    d = get_datetime(date) if _is_datetime(date) else getdate(date)
    return d + _dt.timedelta(days=int(days or 0))


def add_months(date, months: int):
    d = getdate(date)
    m = d.month - 1 + int(months or 0)
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return d.replace(year=y, month=m, day=day)


def add_to_date(date=None, years=0, months=0, weeks=0, days=0, hours=0, minutes=0,
                seconds=0, as_string=False, as_datetime=False):
    base = get_datetime(date) if (date is None or _is_datetime(date) or hours or minutes
                                  or seconds) else getdate(date)
    if months or years:
        moved = add_months(base, months + 12 * years)
        base = (_dt.datetime.combine(moved, base.time()) if isinstance(base, _dt.datetime)
                else moved)
    base = base + _dt.timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes,
                                seconds=seconds)
    if as_string:
        return base.strftime(DATETIME_FORMAT if isinstance(base, _dt.datetime) else DATE_FORMAT)
    return base


def date_diff(a, b) -> int:
    return (getdate(a) - getdate(b)).days


def month_diff(a, b) -> int:
    a, b = getdate(a), getdate(b)
    return (a.year - b.year) * 12 + (a.month - b.month) + 1


def get_last_day(date) -> _dt.date:
    d = getdate(date)
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def get_first_day(date) -> _dt.date:
    return getdate(date).replace(day=1)


def _is_datetime(v) -> bool:
    return isinstance(v, _dt.datetime) or (isinstance(v, str) and len(v.strip()) > 10)


def format_date(value, format_string: str | None = None) -> str:
    d = getdate(value) if value else None
    if not d:
        return ""
    return d.strftime(_py_format(format_string) if format_string else "%d-%m-%Y")


def format_datetime(value, format_string: str | None = None) -> str:
    d = get_datetime(value) if value else None
    if not d:
        return ""
    return d.strftime(_py_format(format_string) if format_string else "%d-%m-%Y %H:%M:%S")


def _py_format(fmt: str) -> str:
    """Frappe's format strings (dd-mm-yyyy, d MMM yyyy) to strftime."""
    out = fmt
    for a, b in (("yyyy", "%Y"), ("MMMM", "%B"), ("MMM", "%b"), ("MM", "%m"), ("mm", "%m"),
                 ("dd", "%d"), ("HH", "%H"), ("ss", "%S")):
        out = out.replace(a, b)
    out = re.sub(r"(?<![%A-Za-z])d(?![A-Za-z])", "%-d", out)
    return out


def convert_utc_to_system_timezone(value):
    """The platform stores and shows Accra time, which is UTC+0."""
    return get_datetime(value)


def flt(value, precision: int | None = None) -> float:
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        f = float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        f = 0.0
    return round(f, precision) if precision is not None else f


def cint(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def cstr(value) -> str:
    return "" if value is None else str(value)


def escape_html(text) -> str:
    return _html.escape(cstr(text), quote=True)


def strip_html(text) -> str:
    return re.sub(r"<[^>]*>", "", cstr(text))


def md_to_html(text) -> str:
    import markdown
    return markdown.markdown(cstr(text), extensions=["tables", "fenced_code", "sane_lists"])


def get_url(path: str = "") -> str:
    from django.conf import settings
    base = (settings.CONFIG.get("host_name") or "").rstrip("/")
    if not base:
        req = getattr(local, "request", None)
        if req is not None:
            base = f"{req.scheme}://{req.get_host()}"
    if path and not path.startswith("/"):
        path = "/" + path
    return base + (path or "")


def get_url_to_form(doctype: str, name: str) -> str:
    """Where a document opens.

    A business's own documents (Sales Invoice, Purchase Order, ...) live in its ERPNext:
    the desk route, exactly as Frappe builds it -- /app/<doctype lowercased, spaces as
    hyphens>/<name, quoted> -- for the caller to put that business's address in front
    (api/facts.py _document_url). Only the platform's own records (connected businesses,
    alert rules, load history) open in its administration. Pointing everything at the
    administration sent every "open in ERPNext" link to <business>/admin/, a 404.
    """
    from urllib.parse import quote
    from insights.core.models import DOCTYPE_MODELS
    model = DOCTYPE_MODELS.get(doctype)
    if model is not None and not str(doctype).startswith("Command Center Fact"):
        return get_url(f"/admin/core/{model._meta.model_name}/{quote(str(name), safe='')}/change/")
    slug = str(doctype).strip().lower().replace(" ", "-")
    return get_url(f"/app/{quote(slug)}/{quote(str(name), safe='')}")


def get_fullname(user: str | None = None) -> str:
    from insights.compat import users
    return users.fullname(user or local.user)


def to_plain(value):
    """Database values as the business logic expects them: Decimal -> float."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def unique(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# frappe.utils.html_utils
def sanitize_html(html: str, **kwargs) -> str:
    """Safe HTML for an exported answer: formatting kept, anything active removed."""
    import nh3
    return nh3.clean(cstr(html), tags={
        "p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li", "h1", "h2", "h3", "h4",
        "table", "thead", "tbody", "tr", "th", "td", "blockquote", "code", "pre", "span",
        "div", "hr", "a", "sup", "sub"}, attributes={"a": {"href"}, "td": {"colspan"},
                                                    "th": {"colspan"}, "span": {"class"},
                                                    "div": {"class"}})
