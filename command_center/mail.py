"""What an email is about, for the platform's email log.

Every message the platform sends goes out through one place (frappe.sendmail; in the
standalone platform insights/compat/runtime.sendmail, which logs every attempt). The
log says what each message was -- an alert, a report, a notice, a test, a digest, a
set-password link (invite) -- and
which business it was about. The caller says so around the send:

    with mail.about("alert", business_code):
        frappe.sendmail(...)

It sets frappe.local, which Frappe has too, so the call is harmless where nothing reads
it. Nothing else changes: the arguments to sendmail stay Frappe's own.
"""

from __future__ import annotations

import contextlib

import frappe

KINDS = ("alert", "report", "notice", "test", "digest", "invite")


@contextlib.contextmanager
def about(kind: str, business: str | None = None):
    prev = getattr(frappe.local, "cc_mail", None)
    frappe.local.cc_mail = {"kind": kind, "business": business or ""}
    try:
        yield
    finally:
        frappe.local.cc_mail = prev


def send_each(to, **kw) -> int:
    """One message per person, so nobody sees who else it went to (17 Nov 2026: an
    alert or digest went to every manager in one To: header). Every address is tried;
    a failure for one does not stop the rest. The number sent is returned; if none was
    sent, the first failure is raised, as frappe.sendmail would have raised it. Email
    not set up at all is raised at once (there is no point trying the rest)."""
    sent, first = 0, None
    for addr in dict.fromkeys(a for a in (to or []) if a):
        try:
            frappe.sendmail(recipients=[addr], **kw)
            sent += 1
        except Exception as e:  # noqa: BLE001 -- the mail layer has logged why
            if type(e).__name__ == "MailNotConfigured":
                raise
            first = first or e
    if not sent and first is not None:
        raise first
    return sent
