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


# Matching payments to the invoices they pay (15 Nov 2026). Where they are not matched the
# invoices overstate what is owed; this is the fix at source, in ERPNext's own tool.
RECONCILE_STEPS = [
    "In ERPNext open Accounts, then Payment Reconciliation.",
    "Choose the Company, the Party Type (Customer or Supplier) and the Party.",
    "Press Get Unreconciled Entries: the payments not yet matched are listed on one side, "
    "the open invoices on the other.",
    "Press Allocate to set each payment against the invoices it pays (oldest first, or "
    "as the remittance says), check the amounts, then press Reconcile.",
    "Repeat for the next customer or supplier. The invoices' outstanding amounts then "
    "agree with the ledger, and this platform shows the difference gone at its next load.",
]


def payment_reconciliation(business_code, text: str) -> dict:
    """The guide to matching payments in ERPNext, opening its Payment Reconciliation."""
    return guide(business_code, text, RECONCILE_STEPS, "/app/payment-reconciliation",
                 label="Open Payment Reconciliation")
