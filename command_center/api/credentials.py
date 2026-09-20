"""Whose credentials apply, and who may see them.

A credential row belongs to one person. Nobody — including another manager —
reads or uses anyone else's, which is enforced by a query condition rather than
by remembering to filter.
"""

from __future__ import annotations

import frappe

from command_center.api.businesses import require_manager


def credential_query_conditions(user: str | None = None) -> str:
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        # A System Manager may see that a credential exists. The secret itself is
        # encrypted at rest and is never returned by a read.
        return ""
    return f"`tabCommand Center Site Credential`.`user` = {frappe.db.escape(user)}"


def has_credential_permission(doc, user: str | None = None, permission_type=None) -> bool:
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return permission_type in ("read", "delete", "report")
    return doc.user == user


def credential_for(business_code: str, user: str | None = None) -> dict | None:
    """The acting user's own key for a business, or None."""
    user = user or frappe.session.user
    name = frappe.db.get_value("Command Center Site Credential",
                               {"user": user, "business_code": business_code})
    if not name:
        return None
    doc = frappe.get_doc("Command Center Site Credential", name)
    secret = doc.get_password("api_secret", raise_exception=False)
    if not (doc.api_key and secret):
        return None
    return {"name": name, "api_key": doc.api_key, "api_secret": secret}


@frappe.whitelist()
def link_account(business_code: str, api_key: str, api_secret: str):
    """Attach the signed-in manager's own account on another business's site."""
    require_manager()
    existing = frappe.db.get_value("Command Center Site Credential",
                                   {"user": frappe.session.user,
                                    "business_code": business_code})
    doc = (frappe.get_doc("Command Center Site Credential", existing) if existing
           else frappe.new_doc("Command Center Site Credential"))
    doc.update({"user": frappe.session.user, "business_code": business_code,
                "api_key": api_key, "api_secret": api_secret})
    doc.save()

    from command_center.connectors.registry import connector_for

    reachable = connector_for(business_code).ping()
    return {"linked": True, "reachable": reachable}


@frappe.whitelist()
def unlink_account(business_code: str):
    require_manager()
    name = frappe.db.get_value("Command Center Site Credential",
                               {"user": frappe.session.user,
                                "business_code": business_code})
    if name:
        frappe.delete_doc("Command Center Site Credential", name,
                          ignore_permissions=False)
    return {"linked": False}
