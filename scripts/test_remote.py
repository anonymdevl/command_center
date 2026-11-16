"""The remote connector, tested without a site and without a network.

    python3 scripts/test_remote.py

Frappe and requests are stood in for, and a fake peer answers frappe.client.get_list
from a list of rows, so what is under test is connectors/remote.py's own behaviour: a
large read comes back whole in pages with a pause between them, a long filter goes by
POST, a busy peer (429/503) is waited out and retried but a write never is, a system
read uses the service account only and refuses to write, as_system needs a service
key, nothing is written to the registry while a question is being answered, and the
change feed of a peer is its modified stamps. What it cannot test is a real ERPNext's
answers; those are checked against the live site.
"""

from __future__ import annotations

import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

frappe = types.ModuleType("frappe")
frappe.conf = {}
frappe.local = types.SimpleNamespace()
frappe.writes = []
frappe.db = types.SimpleNamespace(
    set_value=lambda *a, **k: frappe.writes.append(a))
frappe.session = types.SimpleNamespace(user="manager@example.com")
sys.modules["frappe"] = frappe

calls, sleeps = [], []
ROWS = [{"name": f"SINV-{i:05d}", "modified": f"2026-11-14 10:{i // 60:02d}:{i % 60:02d}"}
        for i in range(1234)]
script = []  # status codes to return before answering normally


class _R:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.ok = 200 <= status < 300

    def json(self):
        return self._body


def _answer(method, url, headers, params, body=None):
    calls.append({"method": method, "url": url, "auth": headers["Authorization"],
                  "params": params, "body": body})
    if script:
        code = script.pop(0)
        return _R(code, headers={"Retry-After": "1"})
    m = url.split("/api/method/")[1]
    if m == "frappe.client.get_list":
        start = int(params.get("limit_start") or 0)
        n = int(params.get("limit_page_length") or 20)
        return _R(200, {"message": ROWS[start:start + n]})
    if m == "frappe.client.get_count":
        return _R(200, {"message": len(ROWS)})
    if m == "frappe.desk.form.load.getdoctype":
        return _R(200, {"docs": [{"name": "Sales Invoice", "fields": [{"fieldname": "customer"}]}]})
    return _R(200, {"message": {"ok": True}})


class _Exc(Exception):
    pass


requests = types.ModuleType("requests")
requests.get = lambda url, headers=None, params=None, timeout=None: _answer("GET", url, headers, params or {})
requests.post = lambda url, headers=None, data=None, json=None, timeout=None: _answer("POST", url, headers, json if json is not None else (data or {}), body="json" if json is not None else "form")
requests.RequestException = _Exc
sys.modules["requests"] = requests

import time as _time  # noqa: E402
_time.sleep = lambda s: sleeps.append(s)

creds = types.ModuleType("command_center.api.credentials")
creds.user_cred = None
creds.credential_for = lambda code, user=None: creds.user_cred
sys.modules["command_center.api.credentials"] = creds
hooks = types.ModuleType("command_center.hooks")
hooks.TRACKED_DOCTYPES = ["Sales Invoice", "Task"]
sys.modules["command_center.hooks"] = hooks

from command_center.connectors.base import RemotePermissionDenied  # noqa: E402
from command_center.connectors.remote import RemoteConnector  # noqa: E402

# This file tests the transport (paging, GET vs POST, retries, whose key). Fitting reads
# to each site's field names asks the site for a doctype's definition first; that has its
# own test (insights/tests.py EveryErpnextVersion), so here it is switched off and every
# request counted below is the read itself.
RemoteConnector.fieldnames = lambda self, doctype: None


class Business:
    business_code, business_name, currency, name = "GMS", "Gigmann", "GHS", "CB-1"
    site_url, api_key, status = "https://erp.example.com/", "svc-key", "Active"
    secret = "svc-secret"

    def get_password(self, field, raise_exception=False):
        return self.secret


passed = failed = 0


def check(ok, what):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print("FAIL:", what)


def reset():
    calls.clear()
    sleeps.clear()
    script.clear()
    frappe.writes.clear()


biz = Business()
conn = RemoteConnector(biz, acting_user="manager@example.com")

# 1. A large read comes back whole, a page at a time, paced.
reset()
rows = conn.get_list("Sales Invoice", fields=["name", "modified"], limit=100000,
                     order_by="modified asc")
check(len(rows) == len(ROWS) and rows[-1]["name"] == ROWS[-1]["name"],
      f"every row comes back: {len(rows)} of {len(ROWS)}")
check(len(calls) == 3 and [int(c["params"]["limit_start"]) for c in calls] == [0, 500, 1000],
      f"in pages of 500 by limit_start: {[c['params'].get('limit_start') for c in calls]}")
check(len(sleeps) == 2 and all(s == 0.25 for s in sleeps), f"with a pause between pages: {sleeps}")
# 1b. A screen's read a person is waiting for (speed.interactive) skips the pause for
#     its first pages; a system read (a load) never does.
frappe.local.cc_interactive = True
reset()
conn.get_list("Sales Invoice", fields=["name", "modified"], limit=100000)
check(len(calls) == 3 and not sleeps, f"a screen's read is not paced: {sleeps}")
reset()
conn.as_system().get_list("Sales Invoice", fields=["name", "modified"], limit=100000)
check(len(sleeps) == 2, f"a load is paced even while a screen is being read: {sleeps}")
del frappe.local.cc_interactive
frappe.conf["command_center_remote_page"] = 1000
reset()
conn.get_list("Sales Invoice", limit=100000)
check(len(calls) == 2, "the page size is a site setting")
frappe.conf.pop("command_center_remote_page")

# 2. A small or grouped read is one request; the parent doctype travels as `parent`.
reset()
conn.get_list("Sales Invoice Item", fields=["name"], limit=20, parent_doctype="Sales Invoice")
check(len(calls) == 1 and calls[0]["params"]["parent"] == "Sales Invoice",
      "a child table read names its parent")
reset()
conn.get_list("Sales Invoice", fields=["customer"], group_by="customer", limit=100000)
check(len(calls) == 1, "a grouped read is one request")

# 3. A long filter goes by POST (a GET that long fails on nginx's defaults).
reset()
conn.get_list("Sales Invoice", filters={"name": ["in", [r["name"] for r in ROWS[:600]]]}, limit=20)
check(calls[0]["method"] == "POST", "a long query goes by POST")
check(calls[0]["body"] == "json", "and as JSON")
reset()
conn.get_list("Sales Invoice", filters={"name": ["in", [r["name"] for r in ROWS[:150]]]}, limit=20)
check(calls[0]["method"] == "POST",
      "a 150-name filter (~4k characters) goes by POST: gunicorn refuses a request line over 4094")
reset()
conn.get_list("Sales Invoice", filters={"docstatus": 1}, limit=20)
check(calls[0]["method"] == "GET", "a short one by GET")
check(json.loads(calls[0]["params"]["filters"]) == {"docstatus": 1}, "filters are sent as JSON")

# 4. A busy peer is waited out and retried; a write never is.
reset()
script.extend([429, 503])
rows = conn.get_list("Sales Invoice", limit=20)
check(len(rows) == 20 and len(calls) == 3, f"429 and 503 are retried: {len(calls)} calls")
check(sleeps[:2] == [1, 1], f"waiting as long as the peer asks: {sleeps}")
creds.user_cred = {"api_key": "mine", "api_secret": "s"}
reset()
script.append(503)
try:
    conn.insert({"doctype": "ToDo"})
    check(False, "a failed write raises")
except Exception:
    pass
check(len(calls) == 1, "a write is never retried: a second insert is a second document")

# 5. Credentials: a person's own key for their reads and writes; the service account
#    for a system read, which never writes; no service key, no system read.
reset()
conn.get_list("Sales Invoice", limit=5)
check(calls[0]["auth"] == "token mine:s", "a person's own key is preferred when linked")
system = conn.as_system()
reset()
system.get_list("Sales Invoice", limit=5)
check(calls[0]["auth"] == "token svc-key:svc-secret",
      "a system read uses the service account, never a manager's key")
try:
    system.insert({"doctype": "ToDo"})
    check(False, "a system connector refuses to write")
except RemotePermissionDenied:
    check(True, "")
creds.user_cred = None
reset()
conn.get_list("Sales Invoice", limit=5)
check(calls[0]["auth"] == "token svc-key:svc-secret", "without a key of their own, reads use the service account")
biz.secret = None
try:
    conn.as_system()
    check(False, "as_system needs a service key")
except ValueError:
    check(True, "")
biz.secret = "svc-secret"

# 6. While a question is answered, a failure writes nothing to the registry (the
#    analyst's write guard would roll it back and report a write).
reset()
script.extend([500])
frappe.local.cc_deadline = _time.monotonic() + 100
try:
    conn.get_list("Sales Invoice", limit=5)
except Exception:
    pass
check(not frappe.writes, f"nothing written mid-question: {frappe.writes}")
frappe.local.cc_deadline = None
reset()
script.extend([500])
try:
    conn.get_list("Sales Invoice", limit=5)
except Exception:
    pass
check(frappe.writes, "outside a question, an unreachable peer is recorded")
reset()
conn.get_list("Sales Invoice", limit=5)
check(any(w[2].get("status") == "Active" for w in frappe.writes if len(w) > 2),
      f"the next call that succeeds marks it Active again: {frappe.writes}")
biz.status = "Active"

# 7. The change feed of a peer is its modified stamps, per tracked doctype.
reset()
feed = conn.fetch_changes(since="2026-11-14 10:00:00", limit=50)
check(len({c["params"]["doctype"] for c in calls}) == 2, "each tracked doctype is asked")
check(json.loads(calls[0]["params"]["filters"]) == {"modified": [">", "2026-11-14 10:00:00"]},
      "after the watermark")
check(feed and set(feed[0]) == {"business_code", "source_doctype", "source_name", "event",
                                "occurred_at"}, "in the change feed's own shape")

# 8. A doctype's definition is the peer's own (getdoctype answers in `docs`).
meta = conn.get_meta("Sales Invoice")
check(meta["fields"][0]["fieldname"] == "customer", "fields come from the peer's own definition")

# 9. Handing out work. ERPNext's own assignment (frappe.desk.form.assign_to.add) with
#    top-level arguments -- v14's add(args=None) and v15/v16's add(args: dict | None) both
#    read them from the request -- assign_to as a JSON list, under the person's own key,
#    by POST and never retried; what is not given is left out (ERPNext's own defaults).
frappe.utils = types.SimpleNamespace(get_fullname=lambda user: "Boss Manager")
creds.user_cred = {"api_key": "mine", "api_secret": "s"}
reset()
conn.assign("Sales Invoice", "ACC-SINV-0001", ["ama@example.com"], description="Chase it",
            date="2026-11-20", priority="High")
check(len(calls) == 1 and calls[0]["url"].endswith("/api/method/frappe.desk.form.assign_to.add"),
      f"one call to assign_to.add: {[c['url'] for c in calls]}")
_p = calls[0]["params"]
check(calls[0]["method"] == "POST" and calls[0]["auth"] == "token mine:s",
      "an assignment is a write, by POST, under the person's own key")
check(json.loads(_p.get("assign_to", "null")) == ["ama@example.com"] and "args" not in _p
      and (_p["doctype"], _p["name"], _p["description"], _p["date"], _p["priority"])
      == ("Sales Invoice", "ACC-SINV-0001", "Chase it", "2026-11-20", "High"),
      f"top-level arguments, assign_to a JSON list: {_p}")
reset()
conn.assign("Task", "TASK-0001", ["ama@example.com"])
check("date" not in calls[0]["params"] and "priority" not in calls[0]["params"],
      f"a date or priority not given is left to ERPNext: {calls[0]['params']}")
reset()
script.extend([503])
try:
    conn.assign("Task", "TASK-0001", ["ama@example.com"])
except Exception:
    pass
check(len(calls) == 1, f"an assignment is never retried: {len(calls)} calls")
# The comment that mentions someone goes through the form's own endpoint, which any
# reader of the record may use; v14/v15 need comment_email and comment_by.
reset()
conn._me = None
_ans = _answer


def _logged(method, url, headers, params, body=None):
    if url.endswith("frappe.auth.get_logged_user"):
        calls.append({"method": method, "url": url, "auth": headers["Authorization"],
                      "params": params, "body": body})
        return _R(200, {"message": "boss@erp.example.com"})
    return _ans(method, url, headers, params, body)


requests.get = lambda url, headers=None, params=None, timeout=None: _logged("GET", url, headers, params or {})
requests.post = lambda url, headers=None, data=None, json=None, timeout=None: _logged("POST", url, headers, json if json is not None else (data or {}), body="json")
conn.comment("ToDo", "TD-1", '<p><span class="mention" data-id="ama@example.com">@Ama</span> hi</p>')
_c = calls[-1]
check(_c["url"].endswith("/api/method/frappe.desk.form.utils.add_comment") and _c["method"] == "POST",
      f"a comment goes through add_comment: {_c['url']}")
check((_c["params"]["reference_doctype"], _c["params"]["reference_name"], _c["params"]["comment_email"],
       _c["params"]["comment_by"]) == ("ToDo", "TD-1", "boss@erp.example.com", "Boss Manager")
      and 'data-id="ama@example.com"' in _c["params"]["content"],
      f"as the person's own login there, with the mention intact: {_c['params']}")
check(conn.whoami() == "boss@erp.example.com"
      and sum(c["url"].endswith("get_logged_user") for c in calls) == 1,
      "whoami is the login the key belongs to there, asked once")
check(conn.desk_url("Sales Invoice", "ACC-SINV-0001")
      == "https://erp.example.com/app/sales-invoice/ACC-SINV-0001",
      f"a record opens on the business's own ERPNext: {conn.desk_url('Sales Invoice', 'ACC-SINV-0001')}")
creds.user_cred = None

print(f"remote: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
