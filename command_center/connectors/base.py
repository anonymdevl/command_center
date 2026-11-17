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


class RequestRefused(BusinessUnreachable):
    """The business answered, but refused this one request -- a field its version does
    not have, a filter it rejects (HTTP 4xx other than 401/403).

    A kind of BusinessUnreachable so every caller that already handles a failed read
    keeps working; but the business is NOT unreachable: it stays Active, the shell shows
    no "taking longer than usual" banner, and a screen's other reads carry on (is_down()
    and the panels' guard tell the two apart)."""


class BusinessSlow(BusinessUnreachable):
    """This read went unanswered after its retries (a timeout, or 429/5xx), but the
    business answered a quick check straight after (RemoteConnector._gave_up): it is
    up, only slow on this read -- a large ERPNext working through a heavy query.

    The read's own callers treat it as not answered (is_down() is True, so the part
    shows the calm "waiting for ERPNext" state and the screen's other reads do not each
    wait out the retries), but the business is NOT marked Unreachable: no banner, and
    the next screen asks again as usual (16 Nov 2026)."""


class WriteNotConfirmed(ConnectorError):
    """A write was sent, but its answer never came back (a timeout, a dropped connection):
    the business's ERPNext may or may not have made it.

    Not a refusal and not "unreachable": the one thing known is that nobody knows. A
    caller never retries it blindly and never says "nothing changed" -- the person is told
    it may have gone through and to check before trying again, and the paths that create
    work (api/actions: a To-Do, a Task, an assignment, a mention) look for what an earlier
    attempt left before making anything, so trying again does not make it twice.

    Raised by the remote transport on a write whose answer was lost (connectors/remote.py).
    api/actions also treats any other failure of a write that is not a definite refusal
    as not confirmed (actions._unsure), so the words stay true whichever is raised."""


class DocumentChanged(ConnectorError):
    """A decision was made on a card that is out of date: the document has moved on in
    ERPNext since the screen read it (someone else approved it, it was sent back, edited).

    apply_workflow raises it rather than applying the action to whatever state the
    document is in now: ERPNext applies a workflow action to the document's CURRENT state,
    so "Approve" pressed on a card showing L1 would perform L2 once someone else had done
    L1. `state` is where the document is now, when it could be read."""

    def __init__(self, message: str = "", state: str | None = None):
        super().__init__(message)
        self.state = state


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

    `doctype` is the ERPNext record type that was refused, when the request named one
    (connectors/remote.py takes it from the request, or from the site's own message),
    and `status` the HTTP status (401: the key itself was refused; 403: the account may
    not read that record type). A figure refused so says which record type to give
    access to (guides.no_access), rather than "could not be read".
    """

    def __init__(self, message: str = "", doctype: str | None = None,
                 status: int | None = None):
        super().__init__(message)
        self.doctype = doctype or None
        self.status = status


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

        Only ingest uses this. Two reasons it has to exist:

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

        On a business on another site (the hosted service, 14 Nov 2026) there is no
        system identity to borrow there, so "the system" means exactly one thing: the
        read-only service account that business's administrators created for this
        platform. A system connector on a peer uses that key and nothing else -- never
        a manager's own credential, which could carry write rights -- and refuses every
        write (RemoteConnector._headers). A business with no service key cannot be read
        as the system at all, and says so rather than quietly using someone's account.

        This does not widen who can see anything. Facts are read back through
        api/kpi and api/facts, and every one of those calls require_manager() first.
        What changes is that building a derived table is a system act, which is what
        it always was.
        """
        if not self.is_local and not self.service_credential_configured():
            raise ValueError(
                f"{self.name} is on another site and has no read-only service account "
                f"registered, so it cannot be read as the system. Add the API key and "
                f"secret of its read-only user to the Connected Business.")
        return type(self)(self.business, acting_user=self.acting_user, system=True)

    def service_credential_configured(self) -> bool:
        return False

    def whoami(self) -> str:
        """The acting person's login on the business's ERPNext: on this site, the
        acting user; on another, whoever that person's own key belongs to there, which
        need not be spelt like their login here."""
        return self.acting_user

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

    def apply_workflow(self, doctype, name, action, expected: dict | None = None) -> dict:
        """Drive a document through a workflow transition.

        Kept here rather than in the API layer because a remote transition is a
        different call from a local one, and nothing above this seam should know
        that.

        `expected` is what the person saw when they chose the action:
        {"field": the workflow state field, "state": the state shown, "modified": the
        document's modified stamp then}. The document is read fresh first and the action
        is refused with DocumentChanged when it has moved on (check_unchanged), because
        ERPNext applies the action to the document's current state, whatever that is.
        """
        raise NotImplementedError

    def assign(self, doctype, name, users, description=None, date=None,
               priority=None) -> list:
        """Assign a document to people the way the desk's "Assign To" does:
        `frappe.desk.form.assign_to.add`, called the same way on v14, v15 and v16.

        Unlike inserting a ToDo, it tells the assignee. ERPNext creates their To-Do
        (assigned_by = the acting user), sets the document's Assigned To, writes the
        "assigned" comment on it, shares the document with them if they could not read
        it, and sends them an Assignment notification -- the bell, and an email if
        their Notification Settings allow. It runs as the acting user, who must be able
        to read the document. Returns ERPNext's answer: the document's open
        assignments, as [{"owner": user, "name": todo}] (at most five).
        """
        raise NotImplementedError

    def unassign(self, doctype, name, user) -> list:
        """Take a document's assignment off one person the way the desk's "x" on Assigned
        To does: `frappe.desk.form.assign_to.remove(doctype, name, assign_to)`, the same
        three arguments on v14, v15 and v16 (v15/v16 add `ignore_permissions`, never
        passed). ERPNext cancels that person's open To-Do on it, takes them off the
        document's Assigned To, writes the "removed assignment" comment and sends them the
        Assignment notification that it was removed. Runs as the acting user. Returns the
        document's remaining assignments."""
        raise NotImplementedError

    def comment(self, doctype, name, content) -> dict:
        """A comment on a record through the form's own endpoint
        (`frappe.desk.form.utils.add_comment`): anyone who may read the record may
        comment on it, where inserting a Comment needs System Manager. A mention in the
        content (`<span class="mention" data-id="user">`) notifies that person, exactly
        as a mention typed in the desk does."""
        raise NotImplementedError

    def desk_url(self, doctype, name) -> str:
        """Where the record opens in this business's ERPNext."""
        site = "" if self.is_local else (self.business.site_url or "").rstrip("/")
        return site + desk_path(doctype, name)

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


def check_unchanged(doc: dict, expected: dict | None):
    """Refuse a workflow action when the document is no longer what the person saw.

    The state is the test: a different workflow state means someone else already moved it
    (DocumentChanged names where it is now). The modified stamp is the second test, when
    both sides have one: the same state with a different stamp means it went away and
    came back, or was edited, since the card was read. Stamps are compared as datetimes,
    so "09:12:33" and "09:12:33.000000" are the same moment."""
    if not expected:
        return
    field = expected.get("field") or "workflow_state"
    want, now = expected.get("state"), (doc or {}).get(field)
    if want is not None and str(now or "") != str(want):
        raise DocumentChanged(
            f"This was already moved to “{now or 'another step'}” by someone else, so "
            f"nothing was done. Refresh to see where it is now.", state=now)
    seen, current = expected.get("modified"), (doc or {}).get("modified")
    if seen and current and _stamp(seen) != _stamp(current):
        raise DocumentChanged(
            "This was changed in ERPNext after your screen read it, so nothing was done. "
            "Refresh to see it as it is now.", state=now)


def _stamp(value):
    import datetime as _dt
    if isinstance(value, _dt.datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return text


def desk_path(doctype: str, name: str) -> str:
    """A record's path in the desk, the same on every Frappe: /app/<doctype-slug>/<name>."""
    from urllib.parse import quote

    slug = doctype.lower().replace(" ", "-").replace("_", "-")
    return f"/app/{slug}/{quote(str(name), safe='')}"
