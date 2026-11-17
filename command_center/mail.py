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
