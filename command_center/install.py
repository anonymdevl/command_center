import frappe


def after_install():
    _create_manager_role()
    frappe.db.commit()


def _create_manager_role():
    """The only role this app ships.

    The platform is for management. There is no general staff role, because a
    staff member's view of the business is ERPNext itself — this app exists to
    answer questions staff are not asked.
    """
    if frappe.db.exists("Role", "Command Center Manager"):
        return
    frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": "Command Center Manager",
            "desk_access": 1,
            "is_custom": 1,
        }
    ).insert(ignore_permissions=True)
