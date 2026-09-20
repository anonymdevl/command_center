"""The Command Center page.

Who may open it, and what it needs to know about them.

The check happens server-side, before any context is built. A page that renders
and then hides its contents has already sent them.
"""

import json

import frappe

from command_center.api.businesses import ALLOWED_ROLES

no_cache = 1


def get_context(context):
    user = frappe.session.user

    # Not signed in: log in first, then come back here.
    if user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/command-center"
        raise frappe.Redirect

    if not ALLOWED_ROLES.intersection(frappe.get_roles(user)):
        frappe.local.flags.redirect_location = "/management-only"
        raise frappe.Redirect

    context.no_cache = 1
    context.boot = json.dumps(_boot(user))
    return context


def _boot(user: str) -> dict:
    """Everything the interface needs on first paint, in one payload.

    Delivered inline rather than fetched, so the page does not flash a hardcoded
    name and then correct itself. The greeting is the first thing a manager reads
    and it should be right immediately.
    """
    from command_center.api.businesses import get_visible_businesses

    fullname = frappe.utils.get_fullname(user)
    try:
        scope = get_visible_businesses()
    except Exception:
        # A broken registry must not blank the whole interface.
        frappe.log_error(title="Command Center boot", message=frappe.get_traceback())
        scope = {"businesses": [], "scopes": []}

    return {
        "user": {
            "id": user,
            "name": fullname,
            "initials": _initials(fullname),
            "roles": sorted(set(frappe.get_roles(user)) & ALLOWED_ROLES),
        },
        "site": frappe.local.site,
        "businesses": scope.get("businesses", []),
        "scopes": scope.get("scopes", []),
        "as_of": _as_of(),
        "live": _live_views(),
    }


def _initials(fullname: str) -> str:
    parts = [p for p in (fullname or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def _as_of():
    """The date the figures describe, which is not necessarily today.

    Read from the ingest state rather than assumed, because on a restored or
    archived dataset the two differ by months and every ageing figure depends on
    which one is meant.
    """
    row = frappe.get_all("Command Center Ingest State",
                         filters={"fact": "fact_sales_invoice"},
                         fields=["as_of_date", "last_run", "status"],
                         limit=1)
    if not row:
        return None
    return {
        "date": str(row[0].as_of_date) if row[0].as_of_date else None,
        "last_run": str(row[0].last_run) if row[0].last_run else None,
        "status": row[0].status,
    }


def _live_views() -> list[str]:
    """Which views draw on loaded facts rather than the demo extract.

    Stated explicitly so the interface can mark the difference. A screen showing
    illustrative numbers that looks identical to one showing real ones is how a
    manager comes to distrust all of them.
    """
    # Nothing yet. The facts are loaded and reconciled, but no screen reads them
    # -- each is wired in turn. Claiming a screen is live before it is would make
    # every other claim here worth less.
    return []
