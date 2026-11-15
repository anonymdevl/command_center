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
