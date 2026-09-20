"""The seam.

Everything above this module — the KPI engine, the alert rules, the screens, the
assistant's tool catalogue — talks to business data through a BusinessConnector
and never learns whether that data lives in this site's database or on a server
in another country.

That single property is what makes the platform's topology a configuration
choice. The host site is connector number one. A peer is connector number two.
Moving the platform off the site it was first installed on means flipping one
flag and supplying a URL.

Two rules are enforced here rather than by convention:

1.  Identity travels with every call. A connector is bound to an acting user, and
    writes execute as that user, so the target site's own permissions decide what
    is allowed and the target site's Version records name who did it. The platform
    grants no authority of its own.

2.  Nothing in this layer decides what a person may do. A local write runs under
    `frappe.set_user` and a remote one under that person's own API credential on
    the target site, so in both cases ERPNext's permission system is the only
    authority and its Version records name the actor. This layer's job is to
    carry authority accurately, never to add or subtract it.
"""

from __future__ import annotations

from typing import Any


class ConnectorError(Exception):
    """Base for every connector failure."""


class BusinessUnreachable(ConnectorError):
    """The business exists in the registry but did not answer."""


class CredentialRequired(ConnectorError):
    """The acting person has no account of their own on the target site.

    Not a refusal in principle — a missing link. Once they paste their own API
    key for that business, writes go through with whatever permissions they hold
    there. The platform carries authority; it never grants it.
    """


class RemotePermissionDenied(ConnectorError):
    """The target site checked the person's permissions and said no.

    This is the correct place for that decision to be made, and the correct
    system to make it.
    """


class BusinessConnector:
    """One connected business, as seen from this site."""

    is_local: bool = False

    def __init__(self, business: Any, acting_user: str | None = None):
        self.business = business
        self.code = business.business_code
        self.name = business.business_name
        self.currency = business.currency
        self.acting_user = acting_user

    # -- identity ----------------------------------------------------------
    def as_user(self, user: str) -> "BusinessConnector":
        """Return a connector bound to an acting identity."""
        return type(self)(self.business, acting_user=user)

    # -- reads -------------------------------------------------------------
    # Deliberately mirrors frappe.client so the local implementation is thin and
    # the remote one maps onto endpoints that already exist on every Frappe site.

    def get_list(self, doctype, filters=None, fields=None, limit=20,
                 order_by=None, group_by=None) -> list[dict]:
        raise NotImplementedError

    def get_doc(self, doctype, name) -> dict:
        raise NotImplementedError

    def get_count(self, doctype, filters=None) -> int:
        raise NotImplementedError

    def get_value(self, doctype, filters, fieldname):
        raise NotImplementedError

    def run_report(self, report_name, filters=None) -> dict:
        """A financial statement is a report, not a table.

        Balance sheet, P&L, trial balance, ageing — all of these already exist on
        every ERPNext site and already respect that site's permissions. Asking the
        owning site to compute its own statement is both cheaper and more correct
        than replicating the ledger and recomputing it here.
        """
        raise NotImplementedError

    # -- writes ------------------------------------------------------------
    def insert(self, doc: dict) -> dict:
        raise NotImplementedError

    def set_value(self, doctype, name, fieldname, value):
        raise NotImplementedError

    def submit(self, doctype, name) -> dict:
        raise NotImplementedError

    def cancel(self, doctype, name) -> dict:
        raise NotImplementedError

    def apply_workflow(self, doctype, name, action) -> dict:
        """Drive a document through a workflow transition.

        Kept here rather than in the API layer because a remote transition is a
        different call from a local one, and nothing above this seam should know
        that.
        """
        raise NotImplementedError

    # -- change feed -------------------------------------------------------
    def fetch_changes(self, since=None, limit: int = 500) -> list[dict]:
        """What has changed in this business since we last looked.

        Returns what changed, never what the change contained. A caller wanting
        the detail asks for the document, and that request is permission-checked
        on its own terms.
        """
        raise NotImplementedError

    # -- health ------------------------------------------------------------
    def ping(self) -> bool:
        raise NotImplementedError

    def __repr__(self):
        kind = "local" if self.is_local else "remote"
        return f"<{type(self).__name__} {self.code} ({kind})>"
