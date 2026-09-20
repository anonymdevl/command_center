import frappe


def after_install():
    """Runs once, on `bench install-app`.

    Everything the app needs on a fresh site belongs here — *not* in a patch.
    Frappe records every entry in patches.txt as already-applied when an app is
    installed, on the reasonable assumption that a new install is at current
    schema. A patch therefore never executes on the site it was written for, and
    the failure is silent: the Patch Log says it ran.

    That bug cost one install. It is worth the comment.
    """
    create_manager_role()
    seed_local_business()
    frappe.db.commit()
    _build_desk_views()


def create_manager_role():
    """The only role this app ships.

    The platform is for management. There is no general staff role, because a
    staff member's view of the business is ERPNext itself — this app exists to
    answer questions staff are not asked.
    """
    if frappe.db.exists("Role", "Command Center Manager"):
        return
    frappe.get_doc({
        "doctype": "Role",
        "role_name": "Command Center Manager",
        "desk_access": 1,
    }).insert(ignore_permissions=True)


def seed_local_business():
    """Register the host site as connector number one.

    The app must never treat the site it is installed on as a special case. It is
    simply the Connected Business flagged `is_local`. Every engine above that
    layer sees N businesses and never asks which one it is living inside — which
    is what makes moving the platform to another site a configuration change
    rather than a rewrite.

    Idempotent, because this is called from install and from the upgrade patch.
    """
    if frappe.db.exists("Connected Business", {"is_local": 1}):
        return None

    company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
    if not company:
        # No Company yet. Registration happens on first use instead of failing
        # the install of an app that is perfectly installable.
        return None

    doc = frappe.get_doc({
        "doctype": "Connected Business",
        "business_name": company,
        "business_code": frappe.scrub(company)[:40],
        "is_local": 1,
        "erpnext_company": company,
        "currency": frappe.db.get_value("Company", company, "default_currency"),
        "timezone": frappe.db.get_single_value("System Settings", "time_zone"),
        "status": "Active",
    }).insert(ignore_permissions=True)
    return doc.name


def _build_desk_views():
    """Cosmetic, so it must never fail the install."""
    try:
        from command_center.desk import build

        build()
    except Exception:
        frappe.log_error(title="Command Center desk views",
                         message=frappe.get_traceback())
