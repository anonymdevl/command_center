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
from urllib.parse import urlencode

import frappe
import requests

from command_center.connectors.base import (
    BusinessConnector,
    BusinessUnreachable,
    CredentialRequired,
    RemotePermissionDenied,
)

TIMEOUT = 20
# Paging and pacing for reads over REST. A peer is somebody's production ERPNext: a
# 100,000-row get_list in one request would sit on one of its web workers for a minute
# and come back as a timeout. So a large read is asked for in pages, with a pause
# between them, and a refusal to keep up (429, 502-504) is waited out and retried
# rather than failing the load. Tunable per site without a deploy:
#
#     bench --site <site> set-config command_center_remote_page 500
#     bench --site <site> set-config command_center_remote_pace_ms 250
PAGE = 500
PACE_MS = 250
RETRIES = 3
REPORT_TIMEOUT = 90
# Above this many characters of query string a read goes by POST. The binding limit is
# gunicorn's, behind the site's nginx: limit_request_line defaults to 4094 for the
# whole request line (method, path, query, protocol), and Gigmann's site refused a
# 5,963-character one with "Request Line is too large" (14 Nov 2026). 2,000 leaves room
# for the path and for a server tuned tighter still. frappe.client's read methods
# accept POST on every version (v14 to v16: no methods= restriction).
MAX_GET_QUERY = 2000


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

    def service_credential_configured(self) -> bool:
        return bool(self._service_credential())

    def _headers(self, for_write: bool = False):
        """Prefer the acting person's own credential; fall back only for reads.

        A system connector (ingest, see BusinessConnector.as_system) uses the read-only
        service account only, and never writes: a load must not run under a manager's
        own key, and nothing a load does needs a write.
        """
        if not self.base_url:
            raise BusinessUnreachable(f"{self.name} has no site URL.")

        if self.system:
            if for_write:
                raise RemotePermissionDenied(
                    f"A system read of {self.name} cannot write. Writes are made only "
                    f"by a person, under their own account on that site.")
            cred = self._service_credential()
        else:
            cred = self._user_credential()
        if not cred and not self.system:
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
              write: bool = False, whole: bool = False, timeout: float | None = None):
        """One request. `whole` returns the full response body rather than its
        `message` (a desk method such as getdoctype answers in `docs`)."""
        import time

        url = f"{self.base_url}/api/method/{method}"
        headers = self._headers(for_write=write)
        data = _encode(params or {})
        post = write or len(urlencode(data)) > MAX_GET_QUERY
        r = None
        for attempt in range(RETRIES + 1):
            try:
                if post:
                    # As JSON, not as a form: Gigmann's site (v14, behind its proxy)
                    # refused long form-encoded POSTs with a bare 400/417, while the
                    # same request as JSON is answered. Frappe reads a JSON body into
                    # form_dict on every version, and the string-encoded values are
                    # parsed exactly as a form's would be.
                    r = requests.post(url, headers=headers, json=data, timeout=_timeout(timeout))
                else:
                    r = requests.get(url, headers=headers, params=data, timeout=_timeout(timeout))
            except requests.RequestException as e:
                if not write and attempt < RETRIES and _time_left(5 * (attempt + 1)):
                    time.sleep(2 * (attempt + 1))
                    continue
                self._mark_unreachable(str(e))
                raise BusinessUnreachable(f"{self.name} did not answer: {e}") from e
            # The far site is busy, not broken: wait as long as it asks (capped), retry.
            # Writes are never retried -- a second insert is a second document.
            if (r.status_code in (429, 502, 503, 504) and not write and attempt < RETRIES):
                wait = min(_retry_after(r) or 2 * (attempt + 1), 30)
                if _time_left(wait + 5):
                    time.sleep(wait)
                    continue
            break

        if r.status_code in (401, 403):
            raise RemotePermissionDenied(
                f"{self.name} refused this. Your account there does not have "
                f"permission for it, or the key has been revoked on that site."
                + _server_message(r)
            )
        if not r.ok:
            self._mark_unreachable(f"HTTP {r.status_code}")
            raise BusinessUnreachable(f"{self.name} returned HTTP {r.status_code}"
                                      + _server_message(r))

        self._mark_reachable()
        body = r.json()
        return body if whole else body.get("message")

    def _mark_unreachable(self, error: str):
        if _in_question():
            return
        frappe.db.set_value("Connected Business", self.business.name,
                            {"status": "Unreachable", "last_error": error[:500]},
                            update_modified=False)
        # Remember it here too, so the next call that succeeds marks it Active again
        # (_mark_reachable reads this copy, not the database).
        self.business.status = "Unreachable"

    def _mark_reachable(self):
        if self.business.status == "Unreachable" and not _in_question():
            frappe.db.set_value("Connected Business", self.business.name,
                                {"status": "Active", "last_error": ""},
                                update_modified=False)
            self.business.status = "Active"

    # -- reads -------------------------------------------------------------
    def get_list(self, doctype, filters=None, fields=None, limit=20,
                 order_by=None, group_by=None, parent_doctype=None):
        """frappe.client.get_list, paged.

        Up to `limit` rows, asked for PAGE at a time with limit_start and a pause
        between pages. A grouped read is one request: its rows are groups, not
        records, and there are few of them. frappe.client.get_list takes the parent
        doctype as `parent`.
        """
        import time

        base = {
            "doctype": doctype,
            "filters": filters or {},
            "fields": fields or ["name"],
            "order_by": order_by,
            "group_by": group_by,
            "parent": parent_doctype,
        }
        want = int(limit or 20)
        page = _page()
        if group_by or want <= page:
            return self._call("frappe.client.get_list",
                              {**base, "limit_page_length": want}) or []
        out, start = [], 0
        while len(out) < want:
            n = min(page, want - len(out))
            rows = self._call("frappe.client.get_list",
                              {**base, "limit_start": start, "limit_page_length": n}) or []
            out.extend(rows)
            if len(rows) < n:
                break
            start += n
            time.sleep(_pace())
        return out

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
        # A ledger or an ageing report can take a minute on a big site.
        return self._call("frappe.desk.query_report.run", {
            "report_name": report_name,
            "filters": filters or {},
            "ignore_prepared_report": True,
        }, timeout=REPORT_TIMEOUT)

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
        """What has changed on the peer since `since`, by its own modified stamps.

        The doc_events feed (api/changes.record_event) only exists where this app is
        installed, and a peer on the hosted service has nothing of ours installed --
        that is the point of it. So the peer is asked, per tracked doctype, which
        documents were modified after the watermark: the same answer, read from
        ERPNext's own columns. Names and times only, never content.
        """
        from command_center.hooks import TRACKED_DOCTYPES

        filters = {"modified": [">", str(since)]} if since else {}
        out = []
        for doctype in TRACKED_DOCTYPES:
            try:
                rows = self.get_list(doctype, filters=filters,
                                     fields=["name", "modified", "docstatus"],
                                     order_by="modified asc", limit=limit)
            except RemotePermissionDenied:
                continue  # the service account does not read this doctype
            for r in rows:
                out.append({"business_code": self.code, "source_doctype": doctype,
                            "source_name": r.get("name"),
                            "event": {0: "Update", 1: "Submit", 2: "Cancel"}.get(
                                r.get("docstatus"), "Update"),
                            "occurred_at": r.get("modified")})
        out.sort(key=lambda e: str(e["occurred_at"] or ""))
        return out[:limit]

    # -- metadata ----------------------------------------------------------
    def get_meta(self, doctype) -> dict:
        """A doctype's fields as the peer defines them -- its own version, its own
        custom fields. frappe.desk.form.load.getdoctype is what the desk calls to open
        a form, so any user who may read the doctype may read its definition."""
        # getdoctype answers in the response's `docs`, not in `message`.
        res = self._call("frappe.desk.form.load.getdoctype", {"doctype": doctype},
                         whole=True) or {}
        docs = res.get("docs")
        if not docs:
            raise BusinessUnreachable(f"{self.name} did not describe {doctype}.")
        return next((d for d in docs if d.get("name") == doctype), docs[0])

    # -- health ------------------------------------------------------------
    def ping(self):
        try:
            self._call("frappe.auth.get_logged_user")
            return True
        except BusinessUnreachable:
            return False


def _page() -> int:
    return max(50, int(frappe.conf.get("command_center_remote_page") or PAGE))


def _pace() -> float:
    ms = frappe.conf.get("command_center_remote_pace_ms")
    return max(0, int(PACE_MS if ms is None else ms)) / 1000


def _in_question() -> bool:
    """A question is being answered (ask/agent.py sets the deadline). Nothing may be
    written then -- not even this connector's own reachability flag, which the
    analyst's write guard would rightly roll back and report."""
    return bool(getattr(frappe.local, "cc_deadline", None))


def _timeout(wanted: float | None = None) -> float:
    """TIMEOUT (or what the call asked for), or less when a question's deadline is nearer."""
    import time
    cap = wanted or TIMEOUT
    end = getattr(frappe.local, "cc_deadline", None)
    if not end:
        return cap
    return max(3, min(cap, end - time.monotonic() - 1))


def _time_left(seconds: float) -> bool:
    import time
    end = getattr(frappe.local, "cc_deadline", None)
    return not end or end - time.monotonic() > seconds


def _retry_after(r) -> int:
    try:
        return int(float(r.headers.get("Retry-After") or 0))
    except (TypeError, ValueError):
        return 0


def _server_message(r) -> str:
    """The far site's own words for a failure, when it gave any -- a missing field or
    an unknown doctype is named there, and a bare status code names nothing."""
    try:
        body = r.json()
    except Exception:
        # Not Frappe's JSON -- a proxy or web server answered. Its first words say who.
        import re
        text = re.sub(r"<[^>]+>", " ", getattr(r, "text", "") or "")
        text = " ".join(text.split())[:300]
        return f" ({text})" if text else ""
    if not isinstance(body, dict):
        return ""
    msg = body.get("exception") or body.get("exc_type") or ""
    if not msg and body.get("_server_messages"):
        try:
            msg = json.loads(json.loads(body["_server_messages"])[0]).get("message", "")
        except Exception:
            msg = ""
    return f" ({str(msg)[:300]})" if msg else ""


def _encode(params: dict) -> dict:
    """Frappe's REST layer wants dicts and lists as JSON strings. A watermark read back
    from the platform's own database is a datetime, and an amount may be a Decimal:
    both go as the text Frappe expects ("2026-11-13 17:15:54.460895"), never fail."""
    out = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            out[k] = json.dumps(v, default=_plain)
        else:
            out[k] = _plain(v) if not isinstance(v, (str, int, float, bool)) else v
    return out


def _plain(v):
    import datetime
    import decimal
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return str(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    return str(v)
