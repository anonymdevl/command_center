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

    def __init__(self, business: Any, acting_user: str | None = None,
                 system: bool = False):
        self.business = business
        self.code = business.business_code
        self.name = business.business_name
        self.currency = business.currency
        self.acting_user = acting_user
        self.system = system

    # -- identity ----------------------------------------------------------
    def as_user(self, user: str) -> "BusinessConnector":
        """Return a connector bound to an acting identity."""
        return type(self)(self.business, acting_user=user)

    def as_system(self) -> "BusinessConnector":
        """Return a connector that reads as the system rather than as a person.

        Only ingest uses this, and only against the local business. Two reasons it
        has to exist:

        The nightly load runs from the scheduler with no user at all, so there is no
        identity whose permissions could scope it. Scoping a system job to whatever
        user happened to trigger it would make the figures depend on who pressed the
        button.

        And a doctype can be readable by nobody. On this site, Issue's Custom DocPerm
        rows grant read to no role -- Custom DocPerms replace the standard ones, so
        Issue is readable by no role at all. Frappe does not raise for that: it strips
        every field from the result and returns rows carrying only name and modified.
        Sixty complaints therefore loaded blank, and only require_fields turned it into
        an error instead of a plausible screen.

        This does not widen who can see anything. Facts are read back through
        api/kpi and api/facts, and every one of those calls require_manager() first.
        What changes is that building a derived table is a system act, which is what
        it always was.
        """
        if not self.is_local:
            # A remote read goes over HTTP with the acting user's own credential on
            # that site. There is no system identity to borrow, and silently returning
            # a connector that ignores the flag would let a caller believe they had
            # escalated on a peer when nothing changed.
            raise ValueError(
                f"{self.name} is on another site. A system read has no meaning there: "
                f"a peer is read with the acting user's own credential, which is the "
                f"point of not computing on anyone else's behalf.")
        return type(self)(self.business, acting_user=self.acting_user, system=True)

    # -- reads -------------------------------------------------------------
    # Deliberately mirrors frappe.client so the local implementation is thin and
    # the remote one maps onto endpoints that already exist on every Frappe site.

    def get_list(self, doctype, filters=None, fields=None, limit=20,
                 order_by=None, group_by=None,
                 parent_doctype=None) -> list[dict]:
        """`parent_doctype` is required when doctype is a child table.

        Without it Frappe cannot resolve permissions on a child table, and it
        does not say so: it silently returns only `name` and drops every other
        field requested. That failure mode is why this argument is part of the
        interface rather than something each caller remembers.
        """
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
