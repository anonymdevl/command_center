"""What the scope switcher is built from.

The list a manager sees is derived from where they can actually reach, not from a
separate permission table this app maintains. That is not a shortcut — a list
kept here would drift from the truth held on each site, and a switcher that
offers a business the user cannot read is worse than one that omits it.
"""

from __future__ import annotations

import frappe

ROLE = "Insights Dashboard Manager"

# The only definition of who may enter. The apps-screen tile, the page guard and
# every endpoint read this one set, so a change here cannot leave a door open
# somewhere else.
#
# System Manager is included so the people who administer the site can support it.
# Everyone else is sent to /management-only.
ALLOWED_ROLES = {ROLE, "System Manager"}


def has_app_permission() -> bool:
    """Whether to show the Command Center tile on /apps.

    Frappe calls this for the apps screen. Returning False hides the tile rather
    than offering a link that leads to a refusal.
    """
    if frappe.session.user == "Guest":
        return False
    return bool(ALLOWED_ROLES.intersection(frappe.get_roles()))


def require_manager(business_code: str | None = None):
    """The platform is management-only -- and, given a business, one of this person's own.

    There is no general staff view, by design and by contract. A staff member's
    window into the business is ERPNext itself.
    """
    if not ALLOWED_ROLES.intersection(frappe.get_roles()):
        from command_center.branding import branding
        frappe.throw(f"{branding()['product']} is available to management only.",
                     frappe.PermissionError)
    if business_code:
        require_business(business_code)


# --- whose businesses (17 Nov 2026) ----------------------------------------------------
# A person may use only the businesses of their own customer(s) (insights/core/plans.py
# visible_codes); an administrator sees all. Enforced in three places that everything
# passes through, so no endpoint can forget it: the web layer checks any business_code a
# call names (insights/core/views.py, before the call runs), the data layer limits every
# read of a business table to the person's businesses (insights/compat/db.py
# business_scope -- "__all__" therefore means all of MY businesses), and connector_for
# finds no business the person may not see. A plain Frappe site has no customers: every
# manager sees every business, as before.
NOT_YOURS = "That business is not one of yours on this platform."


def allowed_codes():
    """The business codes the acting person may use, or None for every one."""
    try:
        from insights.compat.db import business_scope
    except ImportError:  # a plain Frappe site: no customers
        return None
    return business_scope()


def may_use(business_code: str | None) -> bool:
    if not business_code or business_code == "__all__":
        return True
    codes = allowed_codes()
    return codes is None or business_code in codes


def require_business(business_code: str | None):
    """Refuse (403) a business that is not one of the acting person's."""
    if not may_use(business_code):
        frappe.throw(NOT_YOURS, frappe.PermissionError)


def scope_tag(business_code: str | None) -> str:
    """What to file an answer under in a shared cache. One business: its code. "All
    businesses": "__all__" -- or, for a person who sees only some of them, "__all__~"
    and a digest of which, so their "all" is never another person's "all"."""
    if business_code and business_code != "__all__":
        return business_code
    codes = allowed_codes()
    if codes is None:
        return "__all__"
    import hashlib
    return "__all__~" + hashlib.sha1(",".join(sorted(codes)).encode()).hexdigest()[:12]


@frappe.whitelist()
def get_visible_businesses():
    """The three levels the interface is built on.

    Level one is every business in this list at once. Level two is any single
    entry. Level three is the records underneath it.
    """
    require_manager()

    rows = frappe.get_all(
        "Connected Business",
        filters={"status": ["!=", "Paused"]},
        fields=["business_code", "business_name", "is_local", "status",
                "currency", "erpnext_company", "site_url", "last_sync"],
        order_by="is_local desc, business_name asc",
    )

    for row in rows:
        # Reading is available wherever the platform can reach. Acting requires
        # the manager's own account on the owning site: a peer can be acted in once
        # this manager has linked their own key for it (credentials.link_account).
        # A business whose ERPNext has not answered lately (Unreachable) is still read:
        # its loaded figures stand, the rest follow as soon as it answers (16 Nov 2026:
        # it used to be greyed out of the picker as "unreachable").
        row["can_read"] = row["status"] in ("Active", "Unreachable")
        row["waiting"] = row["status"] == "Unreachable"
        row["can_act"] = bool(row["is_local"]) or bool(frappe.db.exists(
            "Command Center Site Credential",
            {"user": frappe.session.user, "business_code": row["business_code"]}))
        row["acts_at"] = None if row["is_local"] else row["site_url"]

    return {
        "businesses": rows,
        "scopes": [{"code": "__all__", "label": "All businesses"}] + [
            {"code": r["business_code"], "label": r["business_name"]} for r in rows
        ],
    }


@frappe.whitelist()
def test_connection(business_code: str):
    require_manager()
    from command_center.connectors.registry import connector_for

    conn = connector_for(business_code)
    return {"business": conn.name, "reachable": conn.ping()}


def currency_for(business_code: str | None) -> str | None:
    """One currency, or none because there is more than one.

    Across all businesses a money figure is only a number if every site reports in
    the same currency. When they do not, saying so is the only honest answer: adding
    cedis to dollars produces a total that means nothing.

    Defined here because both the KPI engine and the records drawer need it, and it
    was briefly defined in both.
    """
    if business_code and business_code != "__all__":
        return frappe.db.get_value("Connected Business",
                                   {"business_code": business_code}, "currency")
    # Through get_all, so "all businesses" is all of this person's (compat business_scope).
    found = {c for c in frappe.get_all("Connected Business",
                                       filters={"status": "Active", "currency": ["is", "set"]},
                                       pluck="currency") if c}
    return found.pop() if len(found) == 1 else None


def default_business_code() -> str | None:
    """The business meant when none is named: this site's own, else the first active one.

    On a client's own ERPNext that is the local business, as it always was. On the
    hosted service (14 Nov 2026) no business lives on the site itself -- every one is
    reached over its API -- so "the business" is the first active one. One definition,
    because seven modules used to look for is_local=1 each in their own way, and each
    would have found nothing on the hosted site.
    """
    code = frappe.db.get_value("Connected Business", {"is_local": 1, "status": ["!=", "Paused"]},
                               "business_code")
    if code:
        return code
    # Not "Active" only: a business marked Unreachable after one failed call is still
    # the business meant -- a load is how it becomes reachable again. Paused is the only
    # state that takes a business out (as in loaded_codes).
    return frappe.db.get_value("Connected Business", {"status": ["!=", "Paused"]},
                               "business_code", order_by="business_name asc")


def loaded_codes() -> list[str]:
    """Every business whose figures are computed here: local and remote alike, unless
    paused. The scheduler loads these, and the alerts and reports run over them."""
    return frappe.get_all("Connected Business", filters={"status": ["!=", "Paused"]},
                          order_by="is_local desc, business_name asc",
                          pluck="business_code")
