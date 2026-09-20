"""The Command Center page.

Who may open it, and what it needs to know about them.

THE FILENAME MATTERS. Frappe finds a page's controller by taking the template
name and replacing hyphens with underscores:

    www/command-center.html  ->  www/command_center.py

Named with a hyphen, the controller is simply never found. Frappe does not warn:
get_context does not run, the context is empty, and the page renders anyway. Here
that meant `window.CC_BOOT = ;` -- a syntax error, so the interface fell back to
its signed-out defaults and showed "Guest" with no businesses and no figures.

It also meant the management-only guard below never executed, so the page was
reachable by any signed-in user. A gate that silently does not run is worse than
no gate, because it is believed.

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
    context.boot = _payload(_boot(user))
    # The interface posts to /api/method, so it needs the token for this session.
    context.csrf_token = _payload(frappe.sessions.get_csrf_token())
    return context


def _payload(value) -> str:
    """JSON for a <script> block, marked safe in the template.

    Frappe's Jinja autoescapes, so `{{ boot }}` arrives as &quot;…&quot; and the
    script is a syntax error -- the interface then sees no payload at all and
    falls back to a signed-out default, which reads as an empty business switcher
    and the wrong name in the corner. One escape, two symptoms.

    `| safe` in the template is only safe because of the substitution below: a
    business named with a closing script tag would otherwise end the block early.
    """
    return (json.dumps(value)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"))


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
