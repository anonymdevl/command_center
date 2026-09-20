"""Which businesses exist, and how to reach them.

Membership is the only thing shared across a group of sites. Compute is not:
each site calculates its own figures from its own data. That split is what keeps
configuration linear as sites are added — register a business once and every
peer discovers it — while leaving no site privileged, because nothing computes
on anyone else's behalf.
"""

from __future__ import annotations

import frappe

from command_center.connectors.base import BusinessConnector
from command_center.connectors.local import LocalConnector
from command_center.connectors.remote import RemoteConnector


def connector_for(business_code: str, acting_user: str | None = None) -> BusinessConnector:
    name = frappe.db.get_value("Connected Business", {"business_code": business_code})
    if not name:
        frappe.throw(f"No connected business with code {business_code}")
    business = frappe.get_doc("Connected Business", name)
    cls = LocalConnector if business.is_local else RemoteConnector
    return cls(business, acting_user=acting_user or frappe.session.user)


def all_connectors(acting_user: str | None = None,
                   include_paused: bool = False) -> list[BusinessConnector]:
    filters = {} if include_paused else {"status": ["!=", "Paused"]}
    rows = frappe.get_all("Connected Business", filters=filters,
                          fields=["name", "business_code", "is_local"],
                          order_by="is_local desc, business_name asc")
    out = []
    for row in rows:
        business = frappe.get_doc("Connected Business", row.name)
        cls = LocalConnector if row.is_local else RemoteConnector
        out.append(cls(business, acting_user=acting_user or frappe.session.user))
    return out


def local_connector(acting_user: str | None = None) -> LocalConnector | None:
    name = frappe.db.get_value("Connected Business", {"is_local": 1})
    if not name:
        return None
    return LocalConnector(frappe.get_doc("Connected Business", name),
                          acting_user=acting_user or frappe.session.user)
