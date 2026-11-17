"""Newly raised critical and high alerts, by email, to the platform's managers.

One message per evaluation pass and business, listing the critical and high alerts that
pass raised for the first time -- an alert that stays open is never sent again (the
hourly pass only refreshes it), and one that clears and comes back later is new again.
Medium and information alerts are on Home and the bell only. Sent through the
platform's mail (frappe.sendmail, insights/compat/runtime.py, set up by an administrator
under Settings → Email), which raises when it cannot send; that is caught here, so a mail
problem never stops the alert pass.

Each alert records what happened to its email ("Emailed to 3 managers", "Not emailed:
email is not set up on this platform", or the failure) as a stored value keyed by the
alert (MAIL_PARENT), shown with the alert, so nothing is lost silently and a mail problem
never stops the alerts themselves.
"""

from __future__ import annotations

import frappe

from command_center import branding, mail

SEVERITY = {"crit": "Critical", "high": "High", "med": "Medium", "info": "For information"}


NOTIFY = ("crit", "high")


def recipients(business_code: str | None = None) -> list[str]:
    """The active managers and administrators with an email address who may see this
    business: its customer's people, never another customer's (17 Nov 2026: every
    manager on the platform was sent every business's alerts and digest). Without a
    business: those who may see every business."""
    from command_center.api.businesses import ALLOWED_ROLES
    try:
        from insights.core.plans import visible_codes
    except ImportError:  # a plain Frappe site: no customers, every manager sees all
        visible_codes = None
    out = []
    for u in frappe.get_all("User", filters={"enabled": 1}, fields=["name", "email"]):
        if u.name in ("Administrator", "Guest"):
            continue
        email = u.get("email") or u.name
        if "@" not in (email or "") or not ALLOWED_ROLES.intersection(frappe.get_roles(u.name)):
            continue
        if visible_codes is not None:
            codes = visible_codes(u.name)
            if codes is not None and (not business_code or business_code not in codes):
                continue
        out.append(email)
    return sorted(set(out))


MAIL_PARENT = "__cc_alert_mail"


def _record(docs, text):
    stamp = str(frappe.utils.now_datetime())[:16]
    for d in docs:
        try:
            frappe.defaults.set_default(d.name, f"{text} ({stamp})", parent=MAIL_PARENT)
        except Exception:
            frappe.log_error(title="Command Center: alert email note",
                             message=frappe.get_traceback())


def recorded(names) -> dict:
    """alert name -> what happened to its email."""
    try:
        got = frappe.defaults.get_defaults_for(MAIL_PARENT) or {}
    except Exception:
        return {}
    return {n: got.get(n) for n in names if got.get(n)}


def notify(business_code: str, docs: list) -> str:
    """Email the alerts just raised; returns what happened, as recorded on each."""
    docs = [d for d in docs if d.severity in NOTIFY]
    if not docs:
        return ""
    to = recipients(business_code)
    if not to:
        text = "Not emailed: no manager of this business has an email address."
        _record(docs, text)
        return text
    name = frappe.db.get_value("Connected Business", {"business_code": business_code},
                               "business_name") or business_code
    esc = frappe.utils.escape_html
    items = "".join(
        f"<li><b>{esc(SEVERITY.get(d.severity, d.severity or ''))}:</b> {esc(d.title or '')}"
        f"<br><span style='color:#555'>{esc(d.why or '')}</span>"
        f"<br>Next: {esc(d.next_step or '')} · Owner: {esc(d.owner_label or '—')}</li>"
        for d in docs)
    n = len(docs)
    try:
        with mail.about("alert", business_code):
            sent = mail.send_each(
                to,
                subject=f"{n} new alert{'s' if n != 1 else ''} · {name}",
                message=branding.email_html(
                    f"<p>The alert rules raised {n} new alert{'s' if n != 1 else ''} for "
                    f"{esc(name)}:</p><ul>{items}</ul>"
                    f"<p>Open the platform's Home screen to assign, defer or dismiss them.</p>"
                    f"<p style='color:#777'>Sent by {esc(branding.branding()['product'])} to its "
                    f"managers.</p>", business_code),
                now=True)
    except Exception as e:
        # The mail layer has already logged why ("Email not sent"); the alert stands.
        frappe.log_error(title="Command Center: alert email not sent",
                         message=frappe.get_traceback())
        text = f"Not emailed: {str(e)[:200]}"
        _record(docs, text)
        return text
    text = (f"Emailed to {sent} manager{'s' if sent != 1 else ''}."
            + (f" {len(to) - sent} could not be sent." if sent < len(to) else ""))
    _record(docs, text)
    return text
