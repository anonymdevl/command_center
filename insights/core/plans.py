"""Plans, licences and usage: the platform as a product a client bought.

The pieces, in the order a month runs:

  PLANS             the catalogue (Essentials, Professional, Enterprise, Custom) in code;
                    the administrator may change any tier's limits, labels, features and
                    default rates in Settings -> Customers (saved to insights.json "plans").
  ClientAccount     a customer: one client, one or more Connected Businesses
                    (ClientBusiness), the people it pays seats for (ClientMember), its plan,
                    any limit overridden for it, the licence dates, whether it may go over
                    its AI allowance, and the administrator's rates for it.
  UsageEvent        the ledger: every billable event, once, never edited (models.py).
                    Written at the one place Claude is called (ask/claude.py, through
                    command_center/metering.py), so no model call escapes it; a question
                    that failed keeps its tokens with a quantity of 0.
  gate()            before an AI question, report, Daily Brief or scheduled send: refused
                    only when the licence has lapsed past its grace, or the allowance is used
                    and the customer may not go over it. The rest of the platform keeps
                    working either way.
  daily()           the scheduler (00:30 server time): the day's seats and businesses for
                    each customer, licence reminders at 60/30/7 days and when grace starts
                    and ends, and on the 1st the administrator's "statements are ready".
  statement()       a month's usage per customer; for the administrator the money too:
                    base fee + for each meter max(0, used - included) x the overage rate.

Months are calendar months in the server's time (insights.json "time_zone"): every meter
resets at 00:00 on the 1st.

A business that belongs to no customer, and a customer with no renewal date, keeps working
exactly as before any of this existed: no limits, no expiry ("Custom, no expiry").

Who sees what: the administrator everything (rates, costs and every customer); a
customer's Account Manager that customer's plan, licence and counts, never money; a
customer's User the plan badge only; anyone else nothing. Nothing here ever sends anything
to a customer by itself: statements are for the administrator to review.
"""

from __future__ import annotations

import calendar
import datetime as _dt
import json
from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal

import frappe  # insights.compat
from insights.compat import users as _users
from insights.compat.state import PermissionError, ValidationError, local

CONFIG_KEY = "plans"
MANAGER = "Insights Dashboard Manager"
SSO_MARK = "cc_sso_business"  # command_center.api.sso.MARK
DUE_SOON_DAYS = 30
REMIND_AT = (60, 30, 7)
WARN_AT = 0.8

# The meters: key (also the event's meter and the plan's limit), label, how a month's use
# is measured (count: the sum of the month's events; peak: the most on any day), the unit.
METERS = [
    ("ai_questions", "AI Analyst Questions", "count", "question"),
    ("ai_reports", "AI Reports", "count", "report"),
    ("scheduled_reports", "Scheduled Reports Sent", "count", "report"),
    ("daily_briefs", "Daily Briefs", "count", "brief"),
    ("ai_review", "AI Reviews", "count", "review"),
    ("seats", "User Seats", "peak", "seat"),
    ("businesses", "Connected Businesses", "peak", "business"),
]
METER = {m[0]: m for m in METERS}
# Tokens spent outside a billable event (a connection check, anything new that calls
# Claude without saying what for): on record with their cost, never counted as an event.
TOKENS_ONLY = "ai_tokens"
AI_METERS = ("ai_questions", "ai_reports", "scheduled_reports", "daily_briefs", "ai_review")

STATE_WORDS = {"active": "Active", "due": "Due Soon", "grace": "In Grace", "lapsed": "Lapsed"}

# The catalogue as shipped. Every figure and word is a default the administrator may
# change (Settings -> Customers -> Plans); none of it is a price. None = unlimited.
PLANS = {
    "essentials": {
        "name": "Essentials", "order": 1,
        "summary": "For one business and a small management team.",
        "limits": {"ai_questions": 200, "ai_reports": 4, "scheduled_reports": 4,
                   "daily_briefs": None, "ai_review": None, "seats": 5, "businesses": 1},
        "refresh": "Every 15 minutes", "support": "Email, next business day",
        "features": ["All nineteen management screens", "AI analyst questions in plain English",
                     "AI-written management reports", "Alerts and daily recommendations",
                     "Branded PDF and Excel exports"]},
    "professional": {
        "name": "Professional", "order": 2,
        "summary": "For a growing group with several businesses.",
        "limits": {"ai_questions": 1000, "ai_reports": 20, "scheduled_reports": 20,
                   "daily_briefs": None, "ai_review": None, "seats": 15, "businesses": 3},
        "refresh": "Every 15 minutes", "support": "Email and phone, same business day",
        "features": ["Everything in Essentials", "Several businesses, and all of them together",
                     "Reports scheduled and sent by email", "The Daily Brief, written by the AI",
                     "Sign-in with your own ERPNext"]},
    "enterprise": {
        "name": "Enterprise", "order": 3,
        "summary": "For larger teams that rely on the platform every day.",
        "limits": {"ai_questions": 5000, "ai_reports": 100, "scheduled_reports": 100,
                   "daily_briefs": None, "ai_review": None, "seats": 50, "businesses": 10},
        "refresh": "Every 15 minutes", "support": "Priority, with a named contact",
        "features": ["Everything in Professional", "The largest allowances",
                     "Priority support with a named contact", "Help setting up reports and rules"]},
    "custom": {
        "name": "Custom", "order": 4,
        "summary": "Limits, services and support agreed for your organisation.",
        "limits": {k: None for k in METER},
        "refresh": "As agreed", "support": "As agreed",
        "features": ["Allowances, services and support as agreed in your quotation"]},
}
PLAN_ORDER = sorted(PLANS, key=lambda k: PLANS[k]["order"])
TEXT_KEYS = ("name", "summary", "refresh", "support")

# Estimated Claude cost, in US dollars per million tokens. EDITABLE DEFAULTS, not facts:
# Anthropic's list prices when this was written (Nov 2026), cache writes at the 1-hour
# rate the analyst's fixed opening uses (2 x input). The administrator keeps them current
# in Settings -> Customers -> Claude Prices; each event keeps the cost worked out when it
# happened, so a later change never rewrites a past month.
AI_PRICE_DEFAULTS = {
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.10, "cache_write": 4.00},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 8.00},
}
PRICE_KEYS = ("input", "output", "cache_read", "cache_write")
COST_CURRENCY = "USD"


def _say(msg: str):
    raise ValidationError(msg)


def _models():
    from insights.core import models
    return models


# --- the catalogue and the price table (insights.json "plans") ------------------------
def _conf() -> dict:
    try:
        from django.conf import settings
        with open(settings.CONFIG_PATH) as fh:
            got = json.load(fh).get(CONFIG_KEY)
    except Exception:
        got = None
    return dict(got) if isinstance(got, dict) else {}


def _save_conf(cfg: dict) -> None:
    from frappe.installer import update_site_config
    update_site_config(CONFIG_KEY, cfg)


def catalogue() -> dict:
    """Every tier as it stands: the code's defaults with the administrator's changes."""
    edits = _conf().get("catalogue") or {}
    out = {}
    for code in PLAN_ORDER:
        base = json.loads(json.dumps(PLANS[code]))
        e = edits.get(code) if isinstance(edits.get(code), dict) else {}
        for k in TEXT_KEYS:
            if isinstance(e.get(k), str) and e[k].strip():
                base[k] = e[k].strip()
        if isinstance(e.get("features"), list):
            base["features"] = [str(f).strip() for f in e["features"] if str(f).strip()]
        if isinstance(e.get("limits"), dict):
            for k in METER:
                if k in e["limits"]:
                    base["limits"][k] = _limit(e["limits"][k])
        # Rates are the administrator's (never shown to a customer).
        base["currency"] = str(e.get("currency") or "")
        base["base_fee"] = _money(e.get("base_fee"))
        base["overage"] = {k: _money((e.get("overage") or {}).get(k)) for k in METER}
        base["code"] = code
        out[code] = base
    return out


def _limit(v):
    """A limit as stored: a whole number of at least 0, or None for unlimited."""
    if v is None or v == "" or str(v).strip().lower() in ("none", "unlimited", "null"):
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        _say(f"{v!r} is not a number. Leave a limit empty for unlimited.")
    if n < 0:
        _say("A limit cannot be below 0.")
    return n


def _money(v) -> Decimal:
    try:
        d = Decimal(str(v if v not in (None, "") else 0))
    except Exception:
        _say(f"{v!r} is not an amount.")
    if d < 0:
        _say("An amount cannot be below 0.")
    return d


def prices() -> dict:
    """model -> {input, output, cache_read, cache_write} in US dollars per million tokens."""
    got = _conf().get("ai_prices")
    out = {m: dict(p) for m, p in AI_PRICE_DEFAULTS.items()}
    if isinstance(got, dict):
        for m, p in got.items():
            if isinstance(p, dict):
                out[str(m)] = {k: float(p.get(k) or 0) for k in PRICE_KEYS}
    return out


def estimate(model: str, t: dict) -> Decimal | None:
    """What these tokens cost by the price table, or None for a model with no price."""
    p = prices().get(model or "")
    if p is None:
        return None
    total = sum(Decimal(str(t.get(k) or 0)) * Decimal(str(p.get(k) or 0)) for k in PRICE_KEYS)
    return (total / Decimal(1_000_000)).quantize(Decimal("0.000001"))


# --- months -----------------------------------------------------------------------------
def now() -> _dt.datetime:
    return frappe.utils.now_datetime()


def period_of(d=None) -> str:
    d = d or now()
    return f"{d.year:04d}-{d.month:02d}"


def _check_period(period) -> str:
    p = str(period or "").strip() or period_of()
    try:
        y, m = (int(x) for x in p.split("-"))
        _dt.date(y, m, 1)
    except Exception:
        _say("Choose a month, such as 2026-11.")
    return f"{y:04d}-{m:02d}"


def period_bounds(period: str) -> tuple:
    y, m = (int(x) for x in period.split("-"))
    first = _dt.date(y, m, 1)
    nxt = _dt.date(y + (m == 12), m % 12 + 1, 1)
    return first, nxt


def period_label(period: str) -> str:
    y, m = (int(x) for x in period.split("-"))
    return f"{calendar.month_name[m]} {y}"


def resets_on(period: str | None = None) -> str:
    _, nxt = period_bounds(period or period_of())
    return f"1 {calendar.month_name[nxt.month]} {nxt.year}"


def _fmt_date(d) -> str | None:
    return f"{d.day} {calendar.month_name[d.month]} {d.year}" if d else None


# --- customers, their businesses and their people ---------------------------------------
def _loads(text) -> dict:
    try:
        v = json.loads(text or "{}")
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def limits_of(c) -> dict:
    """The limits that apply to a customer: its plan's, with its own overrides."""
    plan = catalogue().get(c.plan) or catalogue()["custom"]
    out = dict(plan["limits"])
    for k, v in _loads(c.limits).items():
        if k in METER:
            out[k] = _limit(v)
    return out


def rates_of(c) -> dict:
    """The administrator's rates for a customer: its own, else its plan's defaults."""
    plan = catalogue().get(c.plan) or catalogue()["custom"]
    r = _loads(c.rates)
    over = r.get("overage") if isinstance(r.get("overage"), dict) else {}
    return {"currency": str(r.get("currency") or plan["currency"] or ""),
            "base_fee": _money(r["base_fee"]) if r.get("base_fee") not in (None, "") else plan["base_fee"],
            "overage": {k: (_money(over[k]) if over.get(k) not in (None, "") else plan["overage"][k])
                        for k in METER}}


def _sso_users(codes) -> set:
    from insights.core.models import DefaultValue
    if not codes:
        return set()
    return set(DefaultValue.objects.filter(defkey=SSO_MARK, defvalue__in=list(codes))
               .values_list("parent", flat=True))


def _codes(c) -> list:
    return list(c.businesses.order_by("business_code").values_list("business_code", flat=True))


def members_of(c) -> dict:
    """username (lower case) -> {"role", "via"}: the people named on the customer, and
    anyone let in through one of its businesses' ERPNext (sso.py), as Users."""
    out = {}
    for u in _sso_users(_codes(c)):
        out[u.lower()] = {"role": "user", "via": "erpnext", "username": u}
    for m in c.members.all():
        out[m.username.lower()] = {"role": m.role, "via": "named", "username": m.username}
    return out


def _seat_holders(c) -> list:
    """The active people, other than administrators, who take one of the customer's seats."""
    from django.contrib.auth import get_user_model
    names = [v["username"] for v in members_of(c).values()]
    if not names:
        return []
    U = get_user_model()
    return list(U.objects.filter(username__in=names, is_active=True, is_superuser=False))


def seats_used(c) -> int:
    return len(_seat_holders(c))


def clients_for_user(username: str) -> list:
    """[(customer, role)] for a person: where they are named, and where their ERPNext let
    them in. A named role wins over the one their sign-in gives them."""
    M = _models()
    if not username or username == "Guest":
        return []
    found = {}
    from insights.core.models import DefaultValue
    codes = set(DefaultValue.objects.filter(parent__iexact=username, defkey=SSO_MARK)
                .values_list("defvalue", flat=True))
    for cb in M.ClientBusiness.objects.filter(business_code__in=codes).select_related("client"):
        found[cb.client.pk] = (cb.client, "user")
    for m in M.ClientMember.objects.filter(username__iexact=username).select_related("client"):
        found[m.client.pk] = (m.client, m.role)
    return sorted(found.values(), key=lambda x: x[0].name)


def client_of_business(business_code):
    M = _models()
    if not business_code or business_code == "__all__":
        return None
    cb = M.ClientBusiness.objects.filter(business_code=business_code).select_related("client").first()
    return cb.client if cb else None


def client_for(business_code=None, user=None):
    """The customer an event is billed to: the business's, else the person's only one."""
    c = client_of_business(business_code)
    if c is not None:
        return c
    mine = clients_for_user(user or frappe.session.user)
    return mine[0][0] if len(mine) == 1 else None


# --- the licence --------------------------------------------------------------------------
def licence(c, today=None) -> dict:
    """Where a customer's licence stands. Valid through the renewal date; then grace for
    grace_days; then lapsed (screens readable, AI paused). No renewal date: no expiry."""
    today = today or now().date()
    if c is None or not c.renewal_date:
        return {"state": "active", "label": STATE_WORDS["active"], "renewal_date": None,
                "renews": None, "days_left": None, "grace_until": None, "no_expiry": True,
                "start": _fmt_date(getattr(c, "licence_start", None)), "paused": False}
    end = c.renewal_date
    grace = max(0, int(c.grace_days or 0))
    grace_until = end + _dt.timedelta(days=grace)
    left = (end - today).days
    if left >= 0:
        state = "due" if left <= DUE_SOON_DAYS else "active"
    elif today <= grace_until:
        state = "grace"
    else:
        state = "lapsed"
    return {"state": state, "label": STATE_WORDS[state], "renewal_date": end.isoformat(),
            "renews": _fmt_date(end), "days_left": left, "grace_until": _fmt_date(grace_until),
            "grace_until_date": grace_until.isoformat(), "no_expiry": False,
            "start": _fmt_date(c.licence_start), "paused": state == "lapsed"}


def vendor() -> dict:
    """The vendor's contact details (Settings -> Branding), for "how to renew"."""
    from command_center import branding
    b = branding.branding()
    return {k: b.get(k) or "" for k in ("company", "person", "email", "phone", "website")}


def _contact_words() -> str:
    v = vendor()
    how = [x for x in (v["email"], v["phone"], v["website"]) if x]
    return f"{v['company']}" + (f" ({', '.join(how)})" if how else "")


def banner(c, lic=None) -> str | None:
    """The line shown above every screen while in grace or lapsed."""
    lic = lic or licence(c)
    if lic["state"] == "grace":
        return (f"The licence for {c.licensed_to or c.name} ended on {lic['renews']}. Everything "
                f"keeps working during the grace period, until {lic['grace_until']}. To renew, "
                f"contact {_contact_words()}.")
    if lic["state"] == "lapsed":
        return (f"The licence for {c.licensed_to or c.name} ended on {lic['renews']} and its "
                f"grace period is over. Your screens and data remain available; the AI analyst, "
                f"reports and scheduled sends are paused until it is renewed. To renew, contact "
                f"{_contact_words()}.")
    return None


# --- usage ----------------------------------------------------------------------------------
def _events(client_id, period):
    return _models().UsageEvent.objects.filter(client_id=client_id, period=period)


def used(c, period: str | None = None) -> dict:
    """meter -> this month's use. Counts: the sum of the month's events (corrections
    included). Peaks: the most on any day of the month (and now, for the current one)."""
    from django.db.models import Max, Sum
    period = period or period_of()
    rows = _events(c.pk, period)
    sums = dict(rows.filter(meter__in=[k for k, *_ in METERS if METER[k][2] == "count"])
                .order_by().values_list("meter").annotate(n=Sum("quantity")).values_list("meter", "n"))
    out = {}
    for key, _, how, _ in METERS:
        if how == "count":
            out[key] = int(sums.get(key) or 0)
        else:
            peak = rows.filter(meter=key, outcome="snapshot").aggregate(m=Max("quantity"))["m"] or 0
            adj = rows.filter(meter=key).exclude(outcome="snapshot").aggregate(s=Sum("quantity"))["s"] or 0
            out[key] = int(peak) + int(adj)
    if period == period_of():
        out["seats"] = max(out["seats"], seats_used(c))
        out["businesses"] = max(out["businesses"], c.businesses.count())
    return out


def tokens(c, period: str) -> dict:
    from django.db.models import Count, Sum
    got = _events(c.pk, period).aggregate(
        input=Sum("input_tokens"), output=Sum("output_tokens"), cache_read=Sum("cache_read_tokens"),
        cache_write=Sum("cache_write_tokens"), requests=Sum("requests"), cost=Sum("est_cost"),
        unpriced=Count("pk", filter=_unpriced_q()))
    return {k: (int(v or 0) if k not in ("cost",) else Decimal(str(v or 0)).quantize(Decimal("0.01")))
            for k, v in got.items()}


def _unpriced_q():
    from django.db.models import Q
    return Q(est_cost__isnull=True) & (Q(input_tokens__gt=0) | Q(output_tokens__gt=0))


def meters(c, period: str | None = None) -> list:
    """The meters as a customer sees them: counts and allowances, never money."""
    period = period or period_of()
    lim, got = limits_of(c), used(c, period)
    out = []
    for key, label, how, unit in METERS:
        n, inc = got[key], lim.get(key)
        pct = round(100.0 * n / inc, 1) if inc else (100.0 if inc == 0 and n else None)
        out.append({"key": key, "label": label, "used": n, "included": inc, "unit": unit,
                    "measured": "the most on any day" if how == "peak" else "this month",
                    "remaining": None if inc is None else max(0, inc - n),
                    "over": None if inc is None else max(0, n - inc),
                    "pct": pct, "warn": bool(inc is not None and pct is not None and pct >= WARN_AT * 100),
                    "full": bool(inc is not None and n >= inc)})
    return out


# --- recording ---------------------------------------------------------------------------
def _user() -> str:
    return getattr(local, "user", None) or "Guest"


def record(meter: str, quantity: int = 1, business_code=None, user=None, model: str = "",
           tokens_used: dict | None = None, outcome: str = "ok", ref: str = "", note: str = "",
           client=None, corrects=None):
    """One row in the ledger, and the allowance notices it may set off. The client and
    the cost are fixed now, as they are at this moment."""
    M = _models()
    t = tokens_used or {}
    user = user or _user()
    c = client if client is not None else client_for(business_code, user)
    at = now()
    has_tokens = any(int(t.get(k) or 0) for k in PRICE_KEYS)
    cost = estimate(model, t) if has_tokens else None
    ev = M.UsageEvent.objects.create(
        at=at, period=period_of(at), client_id=c.pk if c else None,
        client_name=c.name if c else "", business_code=str(business_code or "")[:140],
        user=str(user or "")[:150], meter=meter, quantity=int(quantity or 0),
        input_tokens=int(t.get("input") or 0), output_tokens=int(t.get("output") or 0),
        cache_read_tokens=int(t.get("cache_read") or 0),
        cache_write_tokens=int(t.get("cache_write") or 0), requests=int(t.get("requests") or 0),
        model=str(model or "")[:80], est_cost=cost, cost_currency=COST_CURRENCY if cost is not None else "",
        outcome=outcome[:20], ref=str(ref or "")[:140], note=str(note or "")[:255], corrects=corrects)
    if c is not None and meter in METER and int(quantity or 0) > 0:
        try:
            _allowance_notices(c, meter)
        except Exception:
            frappe.log_error(title="Plans: allowance notice failed", message=frappe.get_traceback())
    return ev


@contextmanager
def event(meter: str, business_code=None, ref: str = "", note: str = "", count: bool = True):
    """Around anything that may call Claude: its tokens are gathered here (meter_tokens)
    and written as ONE row when it ends -- a quantity of 1 if it succeeded (ev["ok"]) and
    counts, else 0 with the tokens it spent. Nothing at all is written for an attempt
    that called no model and did not succeed."""
    ev = {"meter": meter, "business_code": business_code, "ok": False, "count": count,
          "model": "", "tokens": {k: 0 for k in (*PRICE_KEYS, "requests")}, "ref": ref,
          "note": note, "user": _user()}
    outer = getattr(local, "cc_meter", None)
    local.cc_meter = ev
    try:
        yield ev
    finally:
        local.cc_meter = outer
        spent = any(ev["tokens"][k] for k in PRICE_KEYS)
        if ev["ok"] or spent:
            try:
                record(meter, 1 if (ev["ok"] and count) else 0, business_code, ev["user"],
                       ev["model"], ev["tokens"], outcome="ok" if ev["ok"] else "failed",
                       ref=ev["ref"], note=ev["note"])
            except Exception:
                frappe.log_error(title="Plans: usage not recorded",
                                 message=f"{json.dumps(ev, default=str)}\n\n{frappe.get_traceback()}")


def meter_tokens(model: str = "", **t):
    """One Claude response's tokens (ask/claude.py, after every reply). Inside an event
    they add to it; outside one they are written at once, so none escape."""
    ev = getattr(local, "cc_meter", None)
    if ev is not None:
        for k in (*PRICE_KEYS, "requests"):
            ev["tokens"][k] += int(t.get(k) or 0)
        ev["model"] = model or ev["model"]
        return
    record(TOKENS_ONLY, 0, None, None, model, t, outcome="ok", note="Claude call outside a billable event")


# --- the gate ------------------------------------------------------------------------------
ALLOWANCE_USED = "This month's AI allowance is used up — your administrator can extend it."


def gate(meter: str, business_code=None, user=None) -> str | None:
    """None if this may go ahead; else the sentence to show. Only AI work is ever gated."""
    c = client_for(business_code, user or _user())
    if c is None:
        return None
    lic = licence(c)
    if lic["paused"]:
        return banner(c, lic)
    inc = limits_of(c).get(meter)
    if inc is None or c.allow_overage:
        return None
    if used(c)[meter] >= inc:
        return ALLOWANCE_USED
    return None


# --- notices ---------------------------------------------------------------------------------
def _admins() -> list:
    from django.contrib.auth import get_user_model
    return list(get_user_model().objects.filter(is_superuser=True, is_active=True))


def _account_managers(c) -> list:
    from django.contrib.auth import get_user_model
    names = [m.username for m in c.members.filter(role="manager")]
    return list(get_user_model().objects.filter(username__in=names, is_active=True)) if names else []


def notify(people, c, kind: str, dedupe: str, title: str, body: str, link: str = "plan",
           email: bool = True) -> int:
    """A notice in each person's bell, once per `dedupe`; by email too when email is set
    up (a failed email is in the error log and the notice stays)."""
    M = _models()
    made = 0
    from insights.compat.runtime import mail_config
    email = email and bool(mail_config().get("host"))  # no email set up: the bell only
    for u in people:
        n, new = M.PlanNotice.objects.get_or_create(
            recipient=u.username, dedupe=dedupe[:140],
            defaults={"client_id": c.pk if c else None, "kind": kind, "title": title[:255],
                      "body": body, "link": link, "created": now()})
        if not new:
            continue
        made += 1
        if email and (u.email or "@" in u.username):
            try:
                from command_center import branding
                esc = frappe.utils.escape_html
                frappe.sendmail(recipients=[u.email or u.username], subject=title,
                                message=branding.email_html(f"<p><b>{esc(title)}</b></p><p>{esc(body)}</p>"),
                                now=True, kind="notice")
                M.PlanNotice.objects.filter(pk=n.pk).update(emailed=True)
            except Exception:
                pass  # sendmail has logged why; the bell still has it
    return made


def _allowance_notices(c, meter: str):
    inc = limits_of(c).get(meter)
    if not inc or meter not in AI_METERS:
        return
    n = used(c)[meter]
    period = period_of()
    label = METER[meter][1]
    if n >= inc:
        tail = (" Further use this month is recorded as additional usage." if c.allow_overage
                else " The AI features pause until " + resets_on(period) + " unless the allowance is extended.")
        title = f"{label}: this month's allowance is used"
        body = f"{c.name} has used {n:,} of its {inc:,} {label} for {period_label(period)}.{tail}"
        notify(_account_managers(c), c, "allowance_full", f"{period}:{c.pk}:{meter}:100", title, body)
        notify(_admins(), c, "allowance_full", f"{period}:{c.pk}:{meter}:100", title, body,
               link="settings")
    elif n >= WARN_AT * inc:
        title = f"{label}: 80% of this month's allowance used"
        body = (f"{c.name} has used {n:,} of its {inc:,} {label} for {period_label(period)}. "
                f"The meters reset on {resets_on(period)}.")
        notify(_account_managers(c), c, "allowance_80", f"{period}:{c.pk}:{meter}:80", title, body)


# --- the daily run -------------------------------------------------------------------------
def daily():
    """00:30 server time (insights/core/management/commands/scheduler.py)."""
    M = _models()
    today = now().date()
    period = period_of()
    for c in M.ClientAccount.objects.all():
        try:
            _snapshot(c, today)
            _licence_reminders(c, today)
        except Exception:
            frappe.log_error(title=f"Plans: daily run failed for {c.name}",
                             message=frappe.get_traceback())
    # The 1st (or the first run after it): last month's statements are ready to review.
    if today.day <= 5 and M.ClientAccount.objects.exists():
        first, _ = period_bounds(period)
        last = period_of(_dt.datetime.combine(first - _dt.timedelta(days=1), _dt.time()))
        notify(_admins(), None, "statements", f"statements:{last}",
               f"Usage statements for {period_label(last)} are ready to review",
               f"Each customer's usage statement for {period_label(last)} is in Settings, "
               f"under Customers. Review them before preparing any pro-forma invoice; nothing "
               f"has been sent to the customers.", link="settings")


def _snapshot(c, today):
    """The day's seats and businesses, once a day."""
    M = _models()
    period = period_of()
    for meter, n in (("seats", seats_used(c)), ("businesses", c.businesses.count())):
        if M.UsageEvent.objects.filter(client_id=c.pk, meter=meter, outcome="snapshot",
                                       at__date=today).exists():
            continue
        M.UsageEvent.objects.create(at=now(), period=period, client_id=c.pk, client_name=c.name,
                                    user="", meter=meter, quantity=n, outcome="snapshot",
                                    note="Daily count")


def _licence_reminders(c, today):
    lic = licence(c, today)
    if lic["no_expiry"]:
        return
    who = c.licensed_to or c.name
    people = _admins() + _account_managers(c)
    left = lic["days_left"]
    if left in REMIND_AT:
        notify(people, c, "renewal", f"renewal:{lic['renewal_date']}:{left}",
               f"The licence for {who} renews in {left} days",
               f"The licence for {who} ({c.name}) runs until {lic['renews']}. To renew, "
               f"contact {_contact_words()}.")
    elif lic["state"] == "grace":
        notify(people, c, "grace", f"grace:{lic['renewal_date']}",
               f"The licence for {who} has ended: grace period until {lic['grace_until']}",
               banner(c, lic))
    elif lic["state"] == "lapsed":
        notify(people, c, "lapsed", f"lapsed:{lic['renewal_date']}",
               f"The licence for {who} has lapsed", banner(c, lic))


# --- the statement ------------------------------------------------------------------------
TWO = Decimal("0.01")


def statement(c, period: str, money: bool = False) -> dict:
    """A month's usage for a customer. With money (the administrator's): for each meter,
    included = its limit (unlimited: nothing over), over = max(0, used - included),
    amount = over x the overage rate; total = base fee + every amount."""
    lim, got = limits_of(c), used(c, period)
    lines = []
    r = rates_of(c) if money else None
    total = r["base_fee"] if money else None
    for key, label, how, unit in METERS:
        n, inc = got[key], lim.get(key)
        over = 0 if inc is None else max(0, n - inc)
        line = {"key": key, "label": label, "used": n, "included": inc, "over": over,
                "measured": "the most on any day" if how == "peak" else "count for the month"}
        if money:
            rate = r["overage"][key]
            amount = (Decimal(over) * rate).quantize(TWO, ROUND_HALF_UP)
            line.update({"rate": rate, "amount": amount})
            total += amount
        lines.append(line)
    lic = licence(c)
    out = {"client": c.name, "client_id": c.pk, "licensed_to": c.licensed_to or c.name,
           "plan": (catalogue().get(c.plan) or catalogue()["custom"])["name"],
           "period": period, "period_label": period_label(period), "lines": lines,
           "licence": lic, "businesses": _business_names(c),
           "complete": period < period_of(), "generated": now().strftime("%Y-%m-%d %H:%M")}
    if money:
        out.update({"currency": r["currency"], "base_fee": r["base_fee"].quantize(TWO),
                    "total": total.quantize(TWO, ROUND_HALF_UP), "claude": tokens(c, period),
                    "allow_overage": c.allow_overage})
    return out


def _business_names(c) -> list:
    codes = _codes(c)
    if not codes:
        return []
    names = {r.business_code: r.business_name for r in frappe.get_all(
        "Connected Business", filters={"business_code": ["in", codes]},
        fields=["business_code", "business_name"])}
    return [{"code": k, "name": names.get(k) or k} for k in codes]


def ledger_rows(c, period: str) -> list:
    return list(_events(c.pk, period).order_by("at", "id"))


# --- who may ------------------------------------------------------------------------------
def _me():
    u = _users._find(local.user)
    if u is None or not u.is_active:
        raise PermissionError("Sign in to continue.")
    return u


def _require_admin():
    u = _me()
    if not u.is_superuser:
        raise PermissionError("Only the platform's administrator can do this.")
    return u


def _require_platform_user():
    u = _me()
    if not (u.is_superuser or u.groups.filter(name=MANAGER).exists()):
        raise PermissionError("This is for the platform's managers.")
    return u


def _client(client_id):
    try:
        c = _models().ClientAccount.objects.filter(pk=int(client_id)).first()
    except (TypeError, ValueError):
        c = None
    if c is None:
        _say("There is no such customer.")
    return c


def _viewable(client_id=None):
    """The customer whose Plan & Usage this person may see: the administrator any; an
    Account Manager their own (the first, when they have several and name none); anyone
    else is refused."""
    u = _require_platform_user()
    if u.is_superuser:
        if client_id:
            return _client(client_id)
        _say("Choose a customer.")
    mine = [c for c, role in clients_for_user(u.username) if role == "manager"]
    if client_id:
        for c in mine:
            if str(c.pk) == str(client_id):
                return c
        raise PermissionError("Plan & Usage is for the customer's own Account Managers.")
    if not mine:
        raise PermissionError("Plan & Usage is for the customer's own Account Managers.")
    return mine[0]


def _audit(what: str):
    from insights.core.platform_settings import _audit as audit
    audit(what)


# --- the boot payload: the badge and the banner -----------------------------------------
def boot(user: str) -> dict | None:
    """What the sidebar's plan badge and the licence banner need, for this person. None
    for anyone with no customer (the administrator included): nothing is shown, exactly
    as before plans existed."""
    mine = clients_for_user(user)
    if not mine:
        return None
    c, role = mine[0]
    if any(r == "manager" for _, r in mine):
        c, role = next(x for x in mine if x[1] == "manager")
    lic = licence(c)
    plan = catalogue().get(c.plan) or catalogue()["custom"]
    return {"client_id": c.pk, "client": c.name, "plan": plan["name"],
            "licensed_to": c.licensed_to or c.name, "renews": lic["renews"],
            "no_expiry": lic["no_expiry"], "state": lic["state"], "state_label": lic["label"],
            "days_left": lic["days_left"], "can_view": role == "manager",
            "banner": banner(c, lic), "paused": lic["paused"],
            "others": [{"client_id": x.pk, "client": x.name} for x, r in mine
                       if r == "manager" and x.pk != c.pk]}


# --- seats (Settings -> People, Settings -> Customers) -------------------------------------
def seat_refusal(c, username: str | None = None) -> str | None:
    """Why one more person cannot take a seat on this customer, or None."""
    inc = limits_of(c).get("seats")
    if inc is None:
        return None
    holders = {u.username.lower() for u in _seat_holders(c)}
    if username and username.lower() in holders:
        return None
    if len(holders) + 1 > inc:
        plan = (catalogue().get(c.plan) or catalogue()["custom"])["name"]
        return (f"{c.name} has used all {inc} of its user seats on the {plan} plan. Deactivate "
                f"someone first, or ask the platform's administrator to add seats.")
    return None


def check_seat(c, username: str | None, override: bool = False, me=None):
    """Refuse a person beyond the customer's seats, unless the administrator overrides."""
    why = seat_refusal(c, username)
    if not why:
        return
    if override and me is not None and me.is_superuser:
        return
    _say(why)


def seat_clients_of(username: str) -> list:
    """The customers whose seats this person would take if they were active again."""
    return [c for c, _ in clients_for_user(username)]


def add_member(c, username: str, role: str = "user"):
    M = _models()
    role = role if role in dict(M.ClientMember.ROLES) else "user"
    m, new = M.ClientMember.objects.get_or_create(client=c, username=username,
                                                  defaults={"role": role})
    if not new and m.role != role:
        M.ClientMember.objects.filter(pk=m.pk).update(role=role)
    return m


# --- the analyst's read-only tool ---------------------------------------------------------
def allowance_for(business_code=None, user=None) -> dict:
    """For "how much of our AI allowance have we used": counts only, never money."""
    c = client_for(business_code, user or _user())
    if c is None:
        return {"plan": None, "note": "This business is not on a plan with limits: there is "
                "no allowance to measure, and nothing is limited."}
    lic = licence(c)
    period = period_of()
    return {"customer": c.name, "plan": (catalogue().get(c.plan) or catalogue()["custom"])["name"],
            "month": period_label(period), "resets_on": resets_on(period),
            "meters": [{k: m[k] for k in ("label", "used", "included", "remaining", "pct")}
                       for m in meters(c, period)],
            "unlimited_means": "included is null: no limit on that meter",
            "overage_allowed": bool(c.allow_overage),
            "licence": {"state": lic["label"], "renews": lic["renews"] or "no expiry",
                        "days_left": lic["days_left"]},
            "note": "Counts as recorded before the question being answered now."}


# ==============================================================================================
# Endpoints
# ==============================================================================================
def _plan_public(p: dict) -> dict:
    """A tier as a customer may see it: no rates."""
    return {k: p[k] for k in ("code", "name", "summary", "limits", "refresh", "support", "features")}


def _client_public(c) -> dict:
    period = period_of()
    p = catalogue().get(c.plan) or catalogue()["custom"]
    return {"client_id": c.pk, "client": c.name, "licensed_to": c.licensed_to or c.name,
            "plan": _plan_public(p), "limits": limits_of(c), "licence": licence(c),
            "banner": banner(c), "period": period, "period_label": period_label(period),
            "resets_on": resets_on(period), "meters": meters(c, period),
            "allow_overage": bool(c.allow_overage), "businesses": _business_names(c),
            "seats_used": seats_used(c)}


@frappe.whitelist()
def my_plan(client_id=None):
    """Plan & Usage: the customer's plan, licence and this month's meters (counts only)."""
    return _client_public(_viewable(client_id))


@frappe.whitelist()
def plans():
    """View Plans: every tier by what it includes, and how to ask for a quotation. No
    prices: those are agreed in a quotation."""
    _require_platform_user()
    from insights.compat.runtime import mail_config
    v = vendor()
    return {"plans": [_plan_public(p) for p in catalogue().values()],
            "meters": [{"key": k, "label": label} for k, label, *_ in METERS],
            "vendor": v, "can_email": bool(v["email"] and mail_config().get("host"))}


@frappe.whitelist(methods=["POST"])
def request_quote(plan: str = "", message: str = "", client_id=None):
    """Request a Quotation: an email to the vendor (Settings -> Branding), and a notice to
    the administrator. Without the vendor's email or the platform's email, it says whom
    to contact instead."""
    c = _viewable(client_id)
    p = catalogue().get(str(plan or "")) or _say("Choose a plan.")
    me = _me()
    who = (f"{me.first_name} {me.last_name}".strip() or me.username)
    msg = " ".join(str(message or "").split())[:1500]
    title = f"Quotation requested: {p['name']} plan for {c.name}"
    body = (f"{who} ({me.email or me.username}) of {c.name} asks for a quotation for the "
            f"{p['name']} plan. They are on the "
            f"{(catalogue().get(c.plan) or catalogue()['custom'])['name']} plan now."
            + (f" Their message: {msg}" if msg else ""))
    notify(_admins(), c, "quote", f"quote:{c.pk}:{now():%Y%m%d%H%M%S}", title, body,
           link="settings", email=False)
    v = vendor()
    from insights.compat.runtime import mail_config
    if not (v["email"] and mail_config().get("host")):
        return {"sent": False, "contact": v}
    from command_center import branding
    esc = frappe.utils.escape_html
    try:
        frappe.sendmail(recipients=[v["email"]], subject=title,
                        message=branding.email_html(f"<p><b>{esc(title)}</b></p><p>{esc(body)}</p>"),
                        now=True, kind="notice")
    except Exception:
        return {"sent": False, "contact": v}
    return {"sent": True, "to": v["email"]}


def _period_rows(st: dict, money: bool) -> list:
    rows = []
    for ln in st["lines"]:
        inc = "Unlimited" if ln["included"] is None else ln["included"]
        row = [ln["label"], ln["used"], inc, ln["over"], ln["measured"]]
        if money:
            row += [float(ln["rate"]), float(ln["amount"])]
        rows.append(row)
    return rows


def _statement_html(st: dict, money: bool) -> str:
    esc = frappe.utils.escape_html

    def num(v):
        return f"{v:,.2f}" if isinstance(v, (Decimal, float)) else (f"{v:,}" if isinstance(v, int) else esc(str(v)))
    head = "<th>Meter</th><th class='n'>Used</th><th class='n'>Included</th><th class='n'>Over</th><th>Measured as</th>"
    if money:
        head += f"<th class='n'>Rate ({esc(st['currency'] or '—')})</th><th class='n'>Amount</th>"
    body = ""
    for ln in st["lines"]:
        inc = "Unlimited" if ln["included"] is None else num(ln["included"])
        body += (f"<tr><td>{esc(ln['label'])}</td><td class='n'>{num(ln['used'])}</td>"
                 f"<td class='n'>{inc}</td><td class='n'>{num(ln['over'])}</td><td>{esc(ln['measured'])}</td>")
        if money:
            body += f"<td class='n'>{num(ln['rate'])}</td><td class='n'>{num(ln['amount'])}</td>"
        body += "</tr>"
    lic = st["licence"]
    facts = (f"<p class='lead'>{esc(st['licensed_to'])} · {esc(st['plan'])} plan · "
             f"{esc(st['period_label'])}"
             + ("" if st["complete"] else " (month in progress)") + "</p>"
             f"<p>Businesses: {esc(', '.join(b['name'] for b in st['businesses']) or 'none assigned')}. "
             f"Licence: {esc(lic['label'])}" + (f", renews {esc(lic['renews'])}" if lic["renews"] else ", no expiry")
             + ".</p>")
    out = facts + f"<h2>Usage</h2><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    if money:
        cur = esc(st["currency"] or "")
        out += ("<h2>Summary</h2><table><tbody>"
                f"<tr><td>Monthly base fee</td><td class='n'>{cur} {num(st['base_fee'])}</td></tr>"
                f"<tr><td>Additional usage</td><td class='n'>{cur} {num(st['total'] - st['base_fee'])}</td></tr>"
                f"<tr><td><b>Total for the month</b></td><td class='n'><b>{cur} {num(st['total'])}</b></td></tr>"
                "</tbody></table>"
                f"<p>Estimated Claude cost for the month (by the price table): USD {num(st['claude']['cost'])} "
                f"over {st['claude']['requests']:,} requests. This is the platform's own cost, "
                f"not a charge to the customer.</p>")
    return out


def _statement_note(money: bool) -> str:
    base = ("Meters count from 00:00 on the 1st to the end of the month, in the platform's "
            "server time. Seats and businesses are the most in use on any day of the month.")
    if money:
        return (base + " This usage statement is the basis for a pro-forma invoice; it is not "
                "an invoice and has not been sent to the customer.")
    return base + " Counts only; charges, if any, are set out in your quotation and invoices."


def _send_pdf(st: dict, money: bool):
    from command_center.api.export import _name, html_pdf
    title = f"Usage Statement · {st['period_label']}"
    code = (st["businesses"][0]["code"] if len(st["businesses"]) == 1 else None)
    # The platform's own document: its brand, whatever the business's Report Style.
    pdf = html_pdf(title, _statement_html(st, money), code, footer=_statement_note(money),
                   kicker="Usage Statement", business=st["licensed_to"], own=True,
                   period=st["period_label"] + ("" if st["complete"] else " (month in progress)"))
    frappe.local.response.filename = _name(f"Usage Statement {st['client']} {st['period']}", "pdf")
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "pdf"


def _send_sheet(c, st: dict, money: bool):
    from command_center.api.export import _send_xlsx
    cols = ["Meter", "Used", "Included", "Over", "Measured as"]
    if money:
        cols += [f"Rate ({st['currency'] or '—'})", "Amount"]
    rows = _period_rows(st, money)
    if money:
        rows += [[], ["Monthly base fee", "", "", "", "", "", float(st["base_fee"])],
                 ["Total for the month", "", "", "", "", "", float(st["total"])],
                 ["Estimated Claude cost (USD, platform's own cost)", "", "", "", "", "",
                  float(st["claude"]["cost"])]]
    sheets = [("Usage", cols, rows)]
    if money:
        led = [[e.at.strftime("%Y-%m-%d %H:%M"), e.meter, e.quantity, e.business_code, e.user,
                e.model, e.input_tokens, e.output_tokens, e.cache_read_tokens, e.cache_write_tokens,
                e.requests, float(e.est_cost) if e.est_cost is not None else "", e.outcome, e.ref,
                e.note, e.id, e.corrects or ""] for e in ledger_rows(c, st["period"])]
        sheets.append(("Ledger", ["When", "Meter", "Quantity", "Business", "Person", "Model",
                                  "Input tokens", "Output tokens", "Cache read", "Cache write",
                                  "Requests", "Est. cost (USD)", "Outcome", "Reference", "Note",
                                  "Row", "Corrects row"], led))
    code = (st["businesses"][0]["code"] if len(st["businesses"]) == 1 else None)
    _send_xlsx(f"Usage Statement · {st['period_label']}", sheets, code,
               note=_statement_note(money), business=st["licensed_to"], period=st["period_label"],
               own=True)
    from command_center.api.export import _name
    frappe.local.response.filename = _name(f"Usage Statement {st['client']} {st['period']}", "xlsx")


@frappe.whitelist()
def usage_statement(client_id=None, period=None, format: str = "pdf"):
    """The customer's own usage statement for a month: counts only, PDF or Excel."""
    c = _viewable(client_id)
    st = statement(c, _check_period(period), money=False)
    if str(format) == "xlsx":
        return _send_sheet(c, st, False)
    return _send_pdf(st, False)


@frappe.whitelist()
def notices():
    """This person's notices that are not dismissed, newest first."""
    u = _require_platform_user()
    rows = _models().PlanNotice.objects.filter(recipient=u.username, dismissed__isnull=True)[:30]
    return [{"id": n.pk, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
             "created": n.created} for n in rows]


@frappe.whitelist(methods=["POST"])
def dismiss_notice(id=None):
    u = _require_platform_user()
    _models().PlanNotice.objects.filter(pk=frappe.utils.cint(id), recipient=u.username).update(
        dismissed=now())
    return {"ok": True}


# --- the administrator: Settings -> Customers ---------------------------------------------
def _admin_row(c) -> dict:
    period = period_of()
    st = statement(c, period, money=True)
    lim = limits_of(c)
    members = members_of(c)
    from django.contrib.auth import get_user_model
    users = {u.username.lower(): u for u in get_user_model().objects.filter(
        username__in=[v["username"] for v in members.values()])}
    people = []
    for k, v in sorted(members.items()):
        u = users.get(k)
        people.append({"username": v["username"], "role": v["role"], "via": v["via"],
                       "name": (f"{u.first_name} {u.last_name}".strip() or u.username) if u else v["username"],
                       "active": bool(u and u.is_active), "admin": bool(u and u.is_superuser)})
    r = rates_of(c)
    return {"id": c.pk, "name": c.name, "licensed_to": c.licensed_to, "plan": c.plan,
            "plan_name": (catalogue().get(c.plan) or catalogue()["custom"])["name"],
            "limits": lim, "overrides": {k: _limit(v) for k, v in _loads(c.limits).items() if k in METER},
            "licence_start": c.licence_start.isoformat() if c.licence_start else None,
            "renewal_date": c.renewal_date.isoformat() if c.renewal_date else None,
            "grace_days": c.grace_days, "allow_overage": bool(c.allow_overage),
            "licence": licence(c), "businesses": _business_names(c), "members": people,
            "seats_used": seats_used(c), "meters": meters(c, period), "statement": _jsonable(st),
            "rates": {"currency": r["currency"], "base_fee": float(r["base_fee"]),
                      "overage": {k: float(v) for k, v in r["overage"].items()}},
            "own_rates": _loads(c.rates), "notes": c.notes}


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


@frappe.whitelist()
def customers():
    """Every customer, with its plan, licence, seats, this month's usage and its
    estimated Claude cost against its allowance; the businesses not yet on a customer."""
    _require_admin()
    M = _models()
    rows = [_admin_row(c) for c in M.ClientAccount.objects.all()]
    taken = set(M.ClientBusiness.objects.values_list("business_code", flat=True))
    allb = frappe.get_all("Connected Business", fields=["business_code", "business_name", "status"],
                          order_by="business_name asc")
    from django.contrib.auth import get_user_model
    people = [{"username": u.username, "name": (f"{u.first_name} {u.last_name}".strip() or u.username),
               "active": u.is_active}
              for u in get_user_model().objects.filter(is_superuser=False).order_by("first_name", "username")]
    return {"customers": rows, "period": period_of(), "period_label": period_label(period_of()),
            "resets_on": resets_on(), "unassigned": [b for b in allb if b.business_code not in taken],
            "all_businesses": allb, "people": people,
            "plans": [{"code": k, "name": p["name"]} for k, p in catalogue().items()],
            "meters": [{"key": k, "label": label, "how": how} for k, label, how, _ in METERS],
            "states": STATE_WORDS, "cost_currency": COST_CURRENCY}


def _date(v, what):
    if v in (None, ""):
        return None
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        _say(f"The {what} is not a date.")


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


@frappe.whitelist(methods=["POST"])
def save_customer(id=None, name: str = "", licensed_to: str = "", plan: str = "custom",
                  limits=None, licence_start=None, renewal_date=None, grace_days=30,
                  allow_overage=1, rates=None, businesses=None, notes: str = ""):
    """Add or change a customer. limits/rates: JSON; businesses: the business codes."""
    _require_admin()
    M = _models()
    name = " ".join(str(name or "").split())
    if not name:
        _say("Type the customer's name.")
    if len(name) > 140 or any(ch in name for ch in "<>{}"):
        _say("The customer's name is too long, or contains < > { or }.")
    if plan not in PLANS:
        _say("Choose a plan.")
    lim = frappe.parse_json(limits) if isinstance(limits, str) else (limits or {})
    lim = {k: _limit(v) for k, v in dict(lim or {}).items() if k in METER}
    rr = frappe.parse_json(rates) if isinstance(rates, str) else (rates or {})
    rr = dict(rr or {})
    clean_rates = {}
    if str(rr.get("currency") or "").strip():
        clean_rates["currency"] = str(rr["currency"]).strip().upper()[:8]
    if rr.get("base_fee") not in (None, ""):
        clean_rates["base_fee"] = str(_money(rr["base_fee"]))
    over = {k: str(_money(v)) for k, v in dict(rr.get("overage") or {}).items()
            if k in METER and v not in (None, "")}
    if over:
        clean_rates["overage"] = over
    start, end = _date(licence_start, "licence start"), _date(renewal_date, "renewal date")
    if start and end and end < start:
        _say("The renewal date is before the licence start.")
    try:
        grace = int(grace_days if grace_days not in (None, "") else 30)
    except (TypeError, ValueError):
        _say("The grace period is a number of days.")
    if not 0 <= grace <= 365:
        _say("The grace period is between 0 and 365 days.")
    codes = frappe.parse_json(businesses) if isinstance(businesses, str) else (businesses or [])
    codes = [str(x) for x in (codes or [])]
    known = set(frappe.get_all("Connected Business", pluck="business_code"))
    bad = [x for x in codes if x not in known]
    if bad:
        _say(f"There is no connected business {bad[0]}.")
    c = _client(id) if id else M.ClientAccount()
    clash = M.ClientAccount.objects.filter(name__iexact=name).exclude(pk=c.pk or 0).exists()
    if clash:
        _say(f"There is already a customer called {name}.")
    taken = M.ClientBusiness.objects.filter(business_code__in=codes).exclude(client_id=c.pk or 0)
    if taken.exists():
        t = taken.select_related("client").first()
        _say(f"{t.business_code} already belongs to {t.client.name}. Take it off there first.")
    before = _admin_row(c) if c.pk else None
    c.name, c.licensed_to, c.plan = name, " ".join(str(licensed_to or "").split())[:140], plan
    c.limits, c.rates = json.dumps(lim), json.dumps(clean_rates)
    c.licence_start, c.renewal_date, c.grace_days = start, end, grace
    c.allow_overage, c.notes = _truthy(allow_overage), str(notes or "")[:2000]
    c.save()
    M.ClientBusiness.objects.filter(client=c).exclude(business_code__in=codes).delete()
    for code in codes:
        M.ClientBusiness.objects.get_or_create(client=c, business_code=code)
    after = _admin_row(c)
    if before is None:
        _audit(f"added the customer {c.name} on the {after['plan_name']} plan")
    else:
        changed = [w for k, w in (("plan", "plan"), ("licensed_to", "licensed-to name"),
                                  ("overrides", "limits"), ("renewal_date", "renewal date"),
                                  ("licence_start", "licence start"), ("grace_days", "grace period"),
                                  ("allow_overage", "overage"), ("own_rates", "rates"),
                                  ("businesses", "businesses"), ("name", "name"), ("notes", "notes"))
                   if before[k] != after[k]]
        _audit(f"changed the customer {c.name}: " + (", ".join(changed) or "nothing"))
    return after


@frappe.whitelist(methods=["POST"])
def extend_licence(id=None, days=30):
    """Move the renewal date on by `days` (from today, if it has already passed)."""
    _require_admin()
    c = _client(id)
    n = frappe.utils.cint(days)
    if not 1 <= n <= 1100:
        _say("Extend by between 1 and 1,100 days.")
    base = max(c.renewal_date or now().date(), now().date())
    c.renewal_date = base + _dt.timedelta(days=n)
    c.save(update_fields=["renewal_date", "modified"])
    _audit(f"extended the licence of {c.name} to {c.renewal_date.isoformat()}")
    return _admin_row(c)


@frappe.whitelist(methods=["POST"])
def remove_customer(id=None):
    """Take a customer off (its businesses go back to no plan). Its usage stays on record."""
    _require_admin()
    c = _client(id)
    name = c.name
    c.delete()
    _audit(f"removed the customer {name}; its usage stays on record")
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def set_member(id=None, username: str = "", role: str = "user", remove=0, override_seats=0):
    """Name a person on a customer (taking a seat), change their role, or take them off."""
    me = _require_admin()
    c = _client(id)
    u = _users._find(str(username or "").strip())
    if u is None:
        _say("There is no one with that email on the platform.")
    if u.is_superuser:
        _say("An administrator does not take a customer's seat.")
    M = _models()
    if _truthy(remove):
        M.ClientMember.objects.filter(client=c, username=u.username).delete()
        _audit(f"took {u.username} off the customer {c.name}")
        return _admin_row(c)
    if u.is_active:
        check_seat(c, u.username, _truthy(override_seats), me)
    add_member(c, u.username, role)
    _audit(f"named {u.username} on the customer {c.name} as "
           f"{dict(M.ClientMember.ROLES).get(role, 'User')}")
    return _admin_row(c)


@frappe.whitelist(methods=["POST"])
def record_correction(id=None, period=None, meter: str = "", quantity=0, note: str = ""):
    """A correction to a month's usage: a new row, never a change to an old one."""
    _require_admin()
    c = _client(id)
    if meter not in METER:
        _say("Choose a meter.")
    q = frappe.utils.cint(quantity)
    if not q:
        _say("Type the number to add (or, with a minus sign, to take away).")
    note = " ".join(str(note or "").split())
    if not note:
        _say("Say why the correction is made: it is kept with the row.")
    period = _check_period(period)
    M = _models()
    M.UsageEvent.objects.create(at=now(), period=period, client_id=c.pk, client_name=c.name,
                                user=_user(), meter=meter, quantity=q, outcome="correction",
                                note=note[:255])
    _audit(f"recorded a correction of {q:+d} {METER[meter][1].lower()} for {c.name}, "
           f"{period_label(period)}: {note[:120]}")
    return _jsonable(statement(c, period, money=True))


@frappe.whitelist()
def billing_statement(id=None, period=None, format: str = "json"):
    """The administrator's usage statement for a customer and month, with the money:
    JSON for the screen, or a branded PDF or Excel workbook (with the ledger)."""
    _require_admin()
    c = _client(id)
    st = statement(c, _check_period(period), money=True)
    if str(format) == "pdf":
        return _send_pdf(st, True)
    if str(format) == "xlsx":
        return _send_sheet(c, st, True)
    return _jsonable(st)


@frappe.whitelist()
def plan_settings():
    """The catalogue with its default rates, and the Claude price table."""
    _require_admin()
    return _jsonable({"plans": list(catalogue().values()), "meters": [
        {"key": k, "label": label} for k, label, *_ in METERS],
        "prices": prices(), "price_defaults": AI_PRICE_DEFAULTS, "cost_currency": COST_CURRENCY})


@frappe.whitelist(methods=["POST"])
def save_plan(code: str = "", name: str = "", summary: str = "", refresh: str = "",
              support: str = "", features=None, limits=None, currency: str = "",
              base_fee=None, overage=None):
    """Change a tier: its words, limits, features and default rates."""
    _require_admin()
    if code not in PLANS:
        _say("Choose a plan.")
    feats = frappe.parse_json(features) if isinstance(features, str) and features.strip().startswith("[") \
        else [x for x in str(features or "").split("\n")]
    lim = frappe.parse_json(limits) if isinstance(limits, str) else (limits or {})
    over = frappe.parse_json(overage) if isinstance(overage, str) else (overage or {})
    entry = {"name": " ".join(str(name or "").split())[:40],
             "summary": " ".join(str(summary or "").split())[:200],
             "refresh": " ".join(str(refresh or "").split())[:60],
             "support": " ".join(str(support or "").split())[:80],
             "features": [" ".join(str(f).split())[:120] for f in feats if str(f).strip()][:15],
             "limits": {k: _limit(v) for k, v in dict(lim or {}).items() if k in METER},
             "currency": str(currency or "").strip().upper()[:8],
             "base_fee": str(_money(base_fee)),
             "overage": {k: str(_money(v)) for k, v in dict(over or {}).items() if k in METER}}
    for k in ("name", "summary", "refresh", "support", "features"):
        if any(ch in json.dumps(entry[k]) for ch in "<>{}") and k != "features":
            _say("Plan text cannot contain < > { or }.")
    cfg = _conf()
    cat = dict(cfg.get("catalogue") or {})
    cat[code] = entry
    cfg["catalogue"] = cat
    _save_conf(cfg)
    _audit(f"changed the {catalogue()[code]['name']} plan")
    return plan_settings()


@frappe.whitelist(methods=["POST"])
def save_prices(prices=None):
    """The Claude price table: model -> {input, output, cache_read, cache_write}, US
    dollars per million tokens. Used for events from now on; past ones keep theirs."""
    _require_admin()
    got = frappe.parse_json(prices) if isinstance(prices, str) else (prices or {})
    clean = {}
    for m, p in dict(got or {}).items():
        m = str(m).strip()
        if not m or len(m) > 80 or not all(ch.isalnum() or ch in "-._" for ch in m):
            _say("A model is named as Anthropic names it, for example claude-sonnet-5-5.")
        clean[m] = {k: float(_money((p or {}).get(k))) for k in PRICE_KEYS}
    cfg = _conf()
    cfg["ai_prices"] = clean
    _save_conf(cfg)
    _audit("changed the Claude price table")
    return plan_settings()


@frappe.whitelist()
def client_choices():
    """The customers a new person may be added to from Settings -> People: every one for
    the administrator, a delegate's own for a delegate."""
    from insights.core.platform_settings import _require
    me = _require("people")
    M = _models()
    if me.is_superuser:
        rows = list(M.ClientAccount.objects.all())
    else:
        rows = [c for c, _ in clients_for_user(me.username)]
    return [{"id": c.pk, "name": c.name, "seats_used": seats_used(c),
             "seats": limits_of(c).get("seats")} for c in rows]
