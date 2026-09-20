"""A business on another site.

Same calls, different URL, different credentials. That is the whole of it — the
methods below map onto endpoints that exist unmodified on every Frappe site, so a
peer needs nothing installed beyond this app's own registry entry.

Two kinds of credential, and the distinction is the whole security model:

*   The **platform's service account** on a peer is read-only, and is used only by
    the scheduled refresh, where no human is present to attribute anything to.

*   A **manager's own account** on that peer carries every interactive call, and
    every write without exception. The far site then checks its own permissions
    and records its own change history, so the platform grants no authority of
    its own — it only carries the authority a person already has. Revoke the key
    on the owning site and their access here dies with it.

A write is never made with the service account. Not because writes are dangerous,
but because a change recorded under a shared integration name tells you nothing
about who made it, and the audit trail is most of what this platform is for.
"""

from __future__ import annotations

import json

import frappe
import requests

from command_center.connectors.base import (
    BusinessConnector,
    BusinessUnreachable,
    CredentialRequired,
    RemotePermissionDenied,
)

TIMEOUT = 20


class RemoteConnector(BusinessConnector):
    is_local = False

    # -- plumbing ----------------------------------------------------------
    @property
    def base_url(self):
        return (self.business.site_url or "").rstrip("/")

    def _user_credential(self):
        from command_center.api.credentials import credential_for

        return credential_for(self.code, user=self.acting_user)

    def _service_credential(self):
        secret = self.business.get_password("api_secret", raise_exception=False)
        if self.business.api_key and secret:
            return {"api_key": self.business.api_key, "api_secret": secret}
        return None

    def _headers(self, for_write: bool = False):
        """Prefer the acting person's own credential; fall back only for reads."""
        if not self.base_url:
            raise BusinessUnreachable(f"{self.name} has no site URL.")

        cred = self._user_credential()
        if not cred:
            if for_write:
                raise CredentialRequired(
                    f"To make changes in {self.name} you need your own account "
                    f"on {self.base_url}. Generate an API key there against your "
                    f"user, then link it once under Settings. Your permissions on "
                    f"that site will decide what you can do."
                )
            cred = self._service_credential()

        if not cred:
            raise BusinessUnreachable(
                f"{self.name} has no usable credentials — neither yours nor the "
                f"platform's read-only account."
            )
        return {
            "Authorization": f"token {cred['api_key']}:{cred['api_secret']}",
            "Accept": "application/json",
        }

    def _call(self, method: str, params: dict | None = None,
              write: bool = False):
        url = f"{self.base_url}/api/method/{method}"
        headers = self._headers(for_write=write)
        try:
            if write:
                r = requests.post(url, headers=headers,
                                  data=_encode(params or {}), timeout=TIMEOUT)
            else:
                r = requests.get(url, headers=headers,
                                 params=_encode(params or {}), timeout=TIMEOUT)
        except requests.RequestException as e:
            self._mark_unreachable(str(e))
            raise BusinessUnreachable(f"{self.name} did not answer: {e}") from e

        if r.status_code in (401, 403):
            raise RemotePermissionDenied(
                f"{self.name} refused this. Your account there does not have "
                f"permission for it, or the key has been revoked on that site."
            )
        if not r.ok:
            self._mark_unreachable(f"HTTP {r.status_code}")
            raise BusinessUnreachable(f"{self.name} returned HTTP {r.status_code}")

        self._mark_reachable()
        return r.json().get("message")

    def _mark_unreachable(self, error: str):
        frappe.db.set_value("Connected Business", self.business.name,
                            {"status": "Unreachable", "last_error": error[:500]},
                            update_modified=False)

    def _mark_reachable(self):
        if self.business.status == "Unreachable":
            frappe.db.set_value("Connected Business", self.business.name,
                                {"status": "Active", "last_error": ""},
                                update_modified=False)

    # -- reads -------------------------------------------------------------
    def get_list(self, doctype, filters=None, fields=None, limit=20,
                 order_by=None, group_by=None, parent_doctype=None):
        # frappe.client.get_list takes the parent doctype as `parent`.
        return self._call("frappe.client.get_list", {
            "doctype": doctype,
            "filters": filters or {},
            "fields": fields or ["name"],
            "limit_page_length": limit,
            "order_by": order_by,
            "group_by": group_by,
            "parent": parent_doctype,
        }) or []

    def get_doc(self, doctype, name):
        return self._call("frappe.client.get", {"doctype": doctype, "name": name})

    def get_count(self, doctype, filters=None):
        return self._call("frappe.client.get_count", {
            "doctype": doctype, "filters": filters or {},
        }) or 0

    def get_value(self, doctype, filters, fieldname):
        return self._call("frappe.client.get_value", {
            "doctype": doctype, "filters": filters, "fieldname": fieldname,
        })

    def run_report(self, report_name, filters=None):
        """Ask the owning site for its own financial statement.

        A CEO on this site opening another business's balance sheet reaches this
        method. The far site computes the statement from its own ledger under its
        own permissions and returns the result. Nothing of that ledger is stored
        here.
        """
        return self._call("frappe.desk.query_report.run", {
            "report_name": report_name,
            "filters": filters or {},
            "ignore_prepared_report": True,
        })

    # -- writes ------------------------------------------------------------
    # Carried out as the acting person, using their own credential. The far site
    # validates, applies its permissions, runs its own hooks, and records the
    # change under their name. Nothing here decides what they may do.

    def insert(self, doc):
        return self._call("frappe.client.insert", {"doc": doc}, write=True)

    def set_value(self, doctype, name, fieldname, value):
        return self._call("frappe.client.set_value", {
            "doctype": doctype, "name": name, "fieldname": fieldname,
            "value": value,
        }, write=True)

    def submit(self, doctype, name):
        doc = self.get_doc(doctype, name)
        return self._call("frappe.client.submit", {"doc": doc}, write=True)

    def cancel(self, doctype, name):
        return self._call("frappe.client.cancel", {
            "doctype": doctype, "name": name,
        }, write=True)

    def apply_workflow(self, doctype, name, action):
        return self._call("frappe.model.workflow.apply_workflow", {
            "doc": self.get_doc(doctype, name), "action": action,
        }, write=True)

    # -- change feed -------------------------------------------------------
    def fetch_changes(self, since=None, limit: int = 500):
        return self._call("command_center.api.changes.get_changes",
                          {"since": str(since) if since else None,
                           "limit": limit}) or []

    # -- health ------------------------------------------------------------
    def ping(self):
        try:
            self._call("frappe.auth.get_logged_user")
            return True
        except BusinessUnreachable:
            return False


def _encode(params: dict) -> dict:
    """Frappe's REST layer wants dicts and lists as JSON strings."""
    out = {}
    for k, v in params.items():
        if v is None:
            continue
        out[k] = json.dumps(v) if isinstance(v, (dict, list)) else v
    return out
