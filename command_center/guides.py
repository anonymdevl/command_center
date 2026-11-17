"""What to do in ERPNext when a figure or panel has nothing to show yet.

A production screen never shows sample figures. When the business's ERPNext holds
nothing behind a figure or a panel, the platform says so and teaches what to record
there to fill it, with a link to the right page on that business's own ERPNext.

    from command_center.guides import guide
    guide(business_code,
          "No batches with an expiry date are recorded yet.",
          ["Open Item, tick Has Batch No and Has Expiry Date for products that expire.",
           "Receive stock against a batch, entering its expiry date."],
          "/app/batch")

returns {"text", "steps", "href", "label"} -- plain text only; the screen
(frontend/src/legacy/guide.js) draws it and never treats any of it as HTML.

A KPI or panel that returns a guide carries it as "guide" (a panel: {"kind": "guide",
"guide": {...}}; a figure: value None and data_status {"state": "needs_setup",
"message": text, "guide": {...}}).
"""

from __future__ import annotations


def site_url(business_code: str | None) -> str:
    """The business's own ERPNext address ('' for a business on this site)."""
    import frappe

    from command_center.api.businesses import default_business_code
    code = business_code if business_code and business_code != "__all__" else default_business_code()
    if not code:
        return ""
    row = frappe.db.get_value("Connected Business", {"business_code": code},
                              ["site_url", "is_local"], as_dict=True)
    if not row or row.get("is_local"):
        return ""
    return (row.get("site_url") or "").rstrip("/")


def guide(business_code, text: str, steps: list[str] | None = None, path: str | None = None,
          label: str = "Open in ERPNext") -> dict:
    out = {"text": str(text), "steps": [str(s) for s in (steps or [])]}
    if path:
        out["href"] = site_url(business_code) + (path if path.startswith("/") else f"/{path}")
        out["label"] = label
    return out


def needs_setup(business_code, text, steps=None, path=None) -> dict:
    """A figure's data_status for 'nothing recorded yet': message plus the guide."""
    return {"state": "needs_setup", "message": str(text),
            "guide": guide(business_code, text, steps, path)}


# A figure or panel the business's ERPNext refused to let the platform read (16 Nov 2026):
# not a failure of the platform and not missing data, but an access to grant there. The
# standard ERPNext role that reads each record type the screens most often need; any
# other is named on its own and given by Role Permission.
READ_ROLES = {
    "Issue": "Support Team", "Issue Type": "Support Team", "Issue Priority": "Support Team",
    "Service Level Agreement": "Support Team", "Warranty Claim": "Maintenance User",
    "Maintenance Visit": "Maintenance User",
    "Project": "Projects User", "Task": "Projects User", "Timesheet": "Projects User",
    "Employee": "HR User", "Leave Application": "HR User", "Attendance": "HR User",
    "Sales Order": "Sales User", "Quotation": "Sales User", "Customer": "Sales User",
    "Purchase Order": "Purchase User", "Supplier": "Purchase User",
    "Material Request": "Purchase User",
    "Sales Invoice": "Accounts User", "Purchase Invoice": "Accounts User",
    "Payment Entry": "Accounts User", "Journal Entry": "Accounts User",
    "GL Entry": "Accounts User",
    "Delivery Note": "Stock User", "Purchase Receipt": "Stock User",
    "Stock Entry": "Stock User", "Bin": "Stock User", "Item": "Stock User",
}


def no_access(business_code, error=None, doctype: str | None = None) -> dict:
    """A figure's data_status when the business's ERPNext refused the read: the record
    type refused and how to give the platform's API user read access to it there.
    `error` is the connector's RemotePermissionDenied (its .doctype and .status)."""
    doctype = doctype or getattr(error, "doctype", None)
    if getattr(error, "status", None) == 401:
        text = ("The business's ERPNext refused this platform's API Key: it "
                "may have been revoked or changed there.")
        steps = ["On that ERPNext, open the platform's API user and generate a new API key "
                 "and secret under API Access.",
                 "Enter them under Settings → Businesses → Manage, then reload this screen."]
        return {"state": "no_access", "message": text, "doctype": doctype,
                "guide": guide(business_code, text, steps, "/app/user", "Open Users in ERPNext")}
    what = doctype or "this record type"
    role = READ_ROLES.get(doctype or "")
    text = (f"The business's ERPNext does not let this platform read {what}, so this "
            f"figure cannot be worked out.")
    give = (f"Give that user read access to {what}: add the {role} role, which reads it, "
            f"or add a Role Permission for {what} with Read ticked for one of its roles."
            if role else
            f"Give that user read access to {what}: add a role that reads it, or add a Role "
            f"Permission for {what} with Read ticked for one of its roles.")
    steps = ["On that ERPNext, open User and find the API user this platform reads with "
             "(the one whose API key is entered under Settings → Businesses, or your own "
             "if you linked your own key).",
             give,
             "Reload this screen: the figure is read again."]
    return {"state": "no_access", "message": text, "doctype": doctype,
            "guide": guide(business_code, text, steps, "/app/user", "Open Users in ERPNext")}


# Matching payments to the invoices they pay (15 Nov 2026). Where they are not matched the
# invoices overstate what is owed; this is the fix at source, in ERPNext's own tool.
RECONCILE_STEPS = [
    "In ERPNext open Accounts, then Payment Reconciliation.",
    "Choose the Company, the Party Type (Customer or Supplier) and the Party.",
    "Press Get Unreconciled Entries: unreconciled payments on one side, "
    "open invoices on the other.",
    "Press Allocate to set each payment against the invoices it pays (oldest first, or "
    "as the remittance says), check the amounts, then press Reconcile.",
    "Repeat for the next customer or supplier. The invoices' outstanding amounts then "
    "agree with the Customer or Supplier Ledger, and this platform shows the difference gone at its next load.",
]


def payment_reconciliation(business_code, text: str) -> dict:
    """The guide to matching payments in ERPNext, opening its Payment Reconciliation."""
    return guide(business_code, text, RECONCILE_STEPS, "/app/payment-reconciliation",
                 label="Open Payment Reconciliation")


# Leave, for the HR screen's People Lookup and Leave (api/people.py, 15 Nov 2026): what
# to set up in ERPNext so that each person has a balance to show.
LEAVE_STEPS = [
    "Create each kind of leave once under Leave Type (Annual Leave, Sick Leave ...): the "
    "days allowed, whether unused days carry forward, and whether holidays count.",
    "Create a Holiday List for the year with the weekly off days and public holidays, and "
    "set it on the Company (or on each Employee).",
    "Give each person their leave for the year: a Leave Policy assigned with Leave Policy "
    "Assignment, or a Leave Allocation per person and leave type, then Submit it.",
    "Staff apply with Leave Application; the leave approver approves and submits it, and "
    "the balance here updates on its own.",
]
NO_HRMS_STEPS = ["Ask your ERPNext administrator to install the HR and payroll app (HRMS) "
                 "on this ERPNext."] + LEAVE_STEPS
