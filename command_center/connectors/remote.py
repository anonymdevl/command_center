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
import re
from urllib.parse import urlencode

import frappe
import requests

from command_center.connectors.base import (
    BusinessConnector,
    BusinessSlow,
    BusinessUnreachable,
    RequestRefused,
    CredentialRequired,
    RemotePermissionDenied,
    check_unchanged,
    WriteUnconfirmed,
)

TIMEOUT = 20
# A write waits longer than a read: a submit of a large document on v14 (stock and GL
# postings, the workflow's hooks) can take most of a minute and still succeed. A write
# not confirmed in this time is WriteUnconfirmed -- it may have gone through -- never a
# plain failure, and never retried.
WRITE_TIMEOUT = 60
UNCONFIRMED = ("{name}'s ERPNext did not confirm this in time. It may still have gone "
               "through -- check in ERPNext before trying again.")
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
# Pages of a screen's read (not a load) asked for without the pause between them.
INTERACTIVE_PAGES = 4
REPORT_TIMEOUT = 90
# The quick check made once a read has gone unanswered after its retries: does the site
# answer at all? One request, no retries, this long at most. It answers: the business is
# up and only slow on that read (BusinessSlow), never marked Unreachable for it. It does
# not: the business is marked Unreachable, and the shell's banner says so (16 Nov 2026 --
# one slow read used to flip the whole business, for everyone, until the next poll).
CHECK_TIMEOUT = 8
CHECK_METHOD = "frappe.auth.get_logged_user"
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
        if write and timeout is None:
            timeout = WRITE_TIMEOUT
        r = None
        started = time.perf_counter()
        try:
            r = self._send(url, headers, data, post, write, timeout, method=method)
        finally:
            _count(started)
        return self._answer(r, whole, doctype=(params or {}).get("doctype"), write=write,
                            method=method)

    def _send(self, url, headers, data, post, write, timeout, method=None):
        import time

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
                # A write that was sent and not answered may have been made; one that
                # never connected was not (ConnectionError other than a read timeout).
                sent = write and not (isinstance(e, requests.exceptions.ConnectionError)
                                      and not isinstance(e, requests.exceptions.ReadTimeout))
                raise self._gave_up(str(e), f"{self.name} did not answer: {e}", write,
                                    unconfirmed=method if sent else None) from e
            # The far site is busy, not broken: wait as long as it asks (capped), retry.
            # Writes are never retried -- a second insert is a second document.
            if (r.status_code in (429, 502, 503, 504) and not write and attempt < RETRIES):
                wait = min(_retry_after(r) or 2 * (attempt + 1), 30)
                if _time_left(wait + 5):
                    time.sleep(wait)
                    continue
            break
        return r

    def _answer(self, r, whole, doctype=None, write=False, method=None):
        if r.status_code in (401, 403):
            said = _server_message(r)
            raise RemotePermissionDenied(
                f"{self.name} refused this. Your account there does not have "
                f"permission for it, or the key has been revoked on that site." + said,
                # The record type refused: the one asked for, else (a report, a method)
                # the one the site names in its own refusal.
                doctype=(doctype if isinstance(doctype, str) and doctype else None)
                or _refused_doctype(said),
                status=r.status_code)
        if not r.ok:
            if r.status_code >= 500 or r.status_code == 429:
                # Broken or overloaded even after the retries: down, unless it answers
                # the quick check (a proxy's 504 on one heavy query, one method's 500).
                # A write its proxy gave up waiting on (502/504) may still be running
                # on ERPNext, and commit: unconfirmed, not failed.
                raise self._gave_up(f"HTTP {r.status_code}",
                                    f"{self.name} returned HTTP {r.status_code}"
                                    + _server_message(r), write,
                                    unconfirmed=method if write and r.status_code in (502, 504)
                                    else None)
            # It answered and refused this one request (a field its version lacks, a
            # filter it rejects): one figure's problem, not the business's.
            self._mark_reachable()
            raise RequestRefused(f"{self.name} returned HTTP {r.status_code}"
                                 + _server_message(r))

        self._mark_reachable()
        body = r.json()
        return body if whole else body.get("message")

    def _gave_up(self, error: str, message: str, write: bool = False,
                 unconfirmed: str | None = None) -> BusinessUnreachable:
        """A request unanswered after its retries. Whether the business is down is asked
        once, by the quick check: answered, this request was only slow (BusinessSlow,
        the business stays as it is); not answered, the business is marked Unreachable.
        Inside a question nothing is marked and no check is spent (the analyst's
        deadline); a business already marked down is not checked again.

        A write is sent once, never retried. One that was sent and not answered
        (`unconfirmed`: a timeout, a proxy's 502/504) may have been made, so it is
        WriteUnconfirmed -- "check before trying again" -- not a failure; and the quick
        check is made for it as for a read, so a slow submit never marks a business
        that answers as Unreachable (17 Nov 2026: it did, for everyone)."""
        if _in_question():
            return BusinessUnreachable(message)
        answers = self.business.status != "Unreachable" and self._answers()
        if unconfirmed:
            if not answers:
                self._mark_unreachable(error)
            return WriteUnconfirmed(UNCONFIRMED.format(name=self.name), method=unconfirmed)
        if answers:
            if write:
                return BusinessUnreachable(message)  # refused there; the business is up
            return BusinessSlow(message + " (it answered a check straight after, so it is "
                                          "slow on this read, not down)")
        self._mark_unreachable(error)
        return BusinessUnreachable(message)

    def _answers(self) -> bool:
        """One quick request, no retries: does the site answer at all? Any reply short
        of a 429/5xx is an answer (a 401 or 403 is the site answering too)."""
        import time
        started = time.perf_counter()
        self.check_error = ""
        try:
            r = requests.get(f"{self.base_url}/api/method/{CHECK_METHOD}",
                             headers=self._headers(), timeout=_timeout(CHECK_TIMEOUT))
        except Exception as e:
            self.check_error = str(e)
            return False
        finally:
            _count(started)
        code = getattr(r, "status_code", 0) or 0
        if code >= 500 or code == 429 or code == 0:
            self.check_error = f"HTTP {code}"
            return False
        self._mark_reachable()
        return True

    def recheck(self) -> bool:
        """The shell's check (api/reach.status and Retry): the quick check, recorded
        either way -- Active when it answers, Unreachable when it does not."""
        if _in_question():
            return self._answers()
        if self._answers():
            _checked(self.code)
            return True
        self._mark_unreachable(self.check_error or "did not answer the check")
        return False

    def _mark_unreachable(self, error: str):
        if _in_question():
            return
        _mark(self.business.name, {"status": "Unreachable", "last_error": error[:500]})
        # Just found down: the banner's own check (api/reach.status) waits a minute
        # before asking again.
        _checked(self.code)
        # Remember it here too, so the next call that succeeds marks it Active again
        # (_mark_reachable reads this copy, not the database).
        self.business.status = "Unreachable"

    def _mark_reachable(self):
        if self.business.status == "Unreachable" and not _in_question():
            _mark(self.business.name, {"status": "Active", "last_error": ""})
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

        fields, filters, renamed, missing = self._fit(doctype, fields or ["name"], filters or {})
        base = {
            "doctype": doctype,
            "filters": filters,
            "fields": fields,
            "order_by": order_by,
            "group_by": group_by,
            "parent": parent_doctype,
        }
        want = int(limit or 20)
        page = _page()
        if group_by or want <= page:
            return _refit(self._call("frappe.client.get_list",
                                     {**base, "limit_page_length": want}) or [], renamed, missing)
        out, start = [], 0
        while len(out) < want:
            n = min(page, want - len(out))
            rows = self._call("frappe.client.get_list",
                              {**base, "limit_start": start, "limit_page_length": n}) or []
            out.extend(rows)
            if len(rows) < n:
                break
            start += n
            # Paced: a load may run to thousands of pages on somebody's production
            # server. A screen's read a person is waiting for (speed.interactive, never
            # a system read) goes without the pause for its first INTERACTIVE_PAGES.
            quick = (getattr(frappe.local, "cc_interactive", False) and not self.system
                     and start < INTERACTIVE_PAGES * page)
            pause = 0 if quick else _pace()
            if pause:
                started = time.perf_counter()
                time.sleep(pause)
                _count(started)
        return _refit(out, renamed, missing)

    # -- one platform, every ERPNext version ------------------------------------
    def fieldnames(self, doctype) -> set | None:
        """The fields this site's version of a doctype has (its own custom fields
        included), from its own definition; cached for six hours. None when it cannot
        be told -- the read then goes out exactly as written."""
        key = f"cc:fields:{getattr(self, 'code', '') or self.name}:{doctype}"
        cache = frappe.cache() if callable(getattr(frappe, "cache", None)) else None
        cached = cache.get_value(key) if cache else None
        if cached is not None:
            return set(cached) or None
        try:
            meta = self.get_meta(doctype)
        except BusinessUnreachable as e:
            if isinstance(e, RequestRefused):
                return None
            raise  # the site is down: the read itself would fail the same way
        except Exception:
            return None  # cannot tell: the read goes out as written
        names = sorted({f.get("fieldname") for f in ((meta or {}).get("fields") or [])
                        if isinstance(f, dict) and f.get("fieldname")})
        if cache:
            cache.set_value(key, names, expires_in_sec=6 * 3600)
        return set(names) or None

    def _fit(self, doctype, fields, filters):
        """Ask this site for what it has, by the names it uses.

        A field another version names differently (FIELD_ALIASES) is asked for by
        this site's name and handed back under the asked-for one. A plain column the
        site does not have at all -- an HR-app field where HR is not installed, a
        workflow field where there is no workflow -- is left out of the request and
        comes back empty, instead of failing the whole read. Filters are never
        dropped: a filter on a field the site lacks still fails, so no figure can
        quietly widen to rows it should not count."""
        plain = [f for f in fields if isinstance(f, str) and _PLAIN.match(f)
                 and f not in _STANDARD]
        if not plain and not filters:
            return fields, filters, {}, []
        have = self.fieldnames(doctype)
        if not have:
            return fields, filters, {}, []
        aliases = FIELD_ALIASES.get(doctype, {})
        renamed, missing, out = {}, [], []
        for f in fields:
            if f in plain and f not in have:
                alt = aliases.get(f)
                if alt and alt in have:
                    renamed[alt] = f
                    out.append(alt)
                else:
                    missing.append(f)
                continue
            out.append(f)
        if not out:
            out = ["name"]

        def key(k):
            alt = aliases.get(k)
            return alt if (k not in have and alt and alt in have) else k
        if isinstance(filters, dict):
            filters = {key(k): v for k, v in filters.items()}
        elif isinstance(filters, list):
            filters = [([key(x[0])] + list(x[1:]) if len(x) == 3 else
                        [x[0], key(x[1])] + list(x[2:]) if len(x) == 4 else x)
                       if isinstance(x, (list, tuple)) else x for x in filters]
        return out, filters, renamed, missing

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

    def apply_workflow(self, doctype, name, action, expected=None):
        # Read fresh, and refuse when it has moved on since the card was read: ERPNext's
        # apply_workflow reloads the document and applies the action to its CURRENT state.
        doc = self.get_doc(doctype, name)
        check_unchanged(doc, expected)
        return self._call("frappe.model.workflow.apply_workflow", {
            "doc": doc, "action": action,
        }, write=True)

    def assign(self, doctype, name, users, description=None, date=None, priority=None):
        # Top-level arguments, not an `args` wrapper: v14's add(args=None) and v15/v16's
        # add(args: dict | None = None) both read them from the request when `args` is
        # absent. assign_to goes as a JSON list (every version parse_json's it). A date
        # or priority left out takes ERPNext's own default: today, Medium.
        return self._call("frappe.desk.form.assign_to.add", {
            "doctype": doctype, "name": name, "assign_to": list(users),
            "description": description, "date": date, "priority": priority,
        }, write=True) or []

    def unassign(self, doctype, name, user):
        # remove(doctype, name, assign_to) on every version; assign_to is one login.
        return self._call("frappe.desk.form.assign_to.remove", {
            "doctype": doctype, "name": name, "assign_to": user,
        }, write=True) or []

    def whoami(self):
        if not getattr(self, "_me", None):
            self._me = self._call("frappe.auth.get_logged_user")
        return self._me

    def comment(self, doctype, name, content):
        # v14 and v15 require comment_email and comment_by (v16 takes the session's user
        # for the first): the person's own login there, and their name.
        me = self.whoami()
        return self._call("frappe.desk.form.utils.add_comment", {
            "reference_doctype": doctype, "reference_name": name, "content": content,
            "comment_email": me,
            "comment_by": (frappe.utils.get_fullname(self.acting_user)
                           if self.acting_user else me) or me,
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
            # It answered, but not with a definition: refused, not unreachable.
            raise RequestRefused(f"{self.name} did not describe {doctype}.")
        return next((d for d in docs if d.get("name") == doctype), docs[0])

    # -- health ------------------------------------------------------------
    def ping(self):
        try:
            self._call("frappe.auth.get_logged_user")
            return True
        except BusinessUnreachable:
            return False


# Renamed between ERPNext versions: the platform asks by whichever name the site has.
# (Checked on live sites, 15 Nov 2026: v14 Issue has resolution_by / resolution_date;
# v15 and v16 have sla_resolution_by / sla_resolution_date.)
FIELD_ALIASES = {
    "Issue": {"resolution_by": "sla_resolution_by", "sla_resolution_by": "resolution_by",
              "resolution_date": "sla_resolution_date",
              "sla_resolution_date": "resolution_date"},
}
_STANDARD = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
             "parent", "parenttype", "parentfield", "_assign", "_comments", "_liked_by",
             "_user_tags", "_seen"}
_PLAIN = __import__("re").compile(r"^[a-z_][a-z0-9_]*$")


def _refit(rows, renamed, missing):
    """Rows back under the names asked for; left-out columns present and empty."""
    if not (renamed or missing):
        return rows
    for r in rows:
        if not isinstance(r, dict):
            continue
        for alt, want in renamed.items():
            if alt in r:
                r[want] = r.pop(alt)
        for f in missing:
            r.setdefault(f, None)
    return rows


def _page() -> int:
    return max(50, int(frappe.conf.get("command_center_remote_page") or PAGE))


def _pace() -> float:
    ms = frappe.conf.get("command_center_remote_pace_ms")
    return max(0, int(PACE_MS if ms is None else ms)) / 1000


def _mark(name: str, values: dict):
    """Record the business's reachability. A read made on one of a request's own
    threads (speed.parallel) hands the mark back to be written on the request's
    transaction, so no thread writes beside it."""
    marks = getattr(frappe.local, "cc_defer_marks", None)
    if marks is not None:
        marks.append((name, values))
        return
    frappe.db.set_value("Connected Business", name, values, update_modified=False)


CHECKED_KEY = "cc:reach:checked:{}"
RECHECK_SECONDS = 60


def _checked(code):
    """Note that the business's reachability was just found out, so api/reach.status
    does not ask it again within RECHECK_SECONDS."""
    try:
        frappe.cache().set_value(CHECKED_KEY.format(code), 1, expires_in_sec=RECHECK_SECONDS)
    except Exception:
        pass


def _count(started: float):
    """Time spent waiting on the business, counted to the request that waited
    (insights/core/timing.py), when one is being timed."""
    import time
    stats = getattr(frappe.local, "cc_timing", None)
    if stats is not None:
        try:
            stats.add_remote((time.perf_counter() - started) * 1000)
        except Exception:
            pass


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


# Frappe's refusals name the record type: "No permission for Issue Type", "Insufficient
# Permission for Issue", "User x does not have doctype access via role permission for
# document Issue". Only a name shaped like a doctype is taken, and only when the request
# itself named none.
_REFUSED = re.compile(r"(?:[Pp]ermission for(?: document)?|[Nn]o permission to read|access to)"
                      r"\s+([A-Z][A-Za-z0-9]*(?: [A-Z][A-Za-z0-9]*){0,4})")


def _refused_doctype(said: str) -> str | None:
    m = _REFUSED.search(re.sub(r"<[^>]+>", "", said or ""))
    return m.group(1) if m else None


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
