"""The change history's figures, worked out behind the screens (speed.stored).

ERPNext's change log (Version) is the largest table on a site. Reading it while a
person waits cost the Internal Audit screen 147 s on Gigmann's ERPNext (v14): every
approval step is a Version row whose data mentions workflow_state, found only by a LIKE
scan, paged. So the figures that read it -- how much is logged, since when, and which
approved purchase orders and payments had every step taken by the account that raised
them (kpi/live self_approved, live_governance approval_record, the panels' "How much
history there is") -- read one summary, which the background job (background.py: hourly
and after the nightly load) keeps.

The scan is incremental. What was found is kept per business and whose view (for each
purchase order or payment named in a step, the accounts that took its steps, and its
owner and docstatus), and each run reads only the Version rows created since the last
one, and the documents modified since. A full rescan is made weekly, or when nothing is
kept. A figure reads summary(), which raises NotWorkedOut while it is first worked out.
"""

from __future__ import annotations

import time

WHAT = {"history": 1}
FULL_EVERY = 7 * 24 * 3600
SCAN_KEEP = 8 * 24 * 3600
LIMIT = 5_000_000
STEP = '%"workflow_state"%'
SEP = "\x1f"


def summary(r) -> dict:
    """The kept summary for the reader's business, as whoever reads sees it:
    {"data": {...}, "read_at": "YYYY-MM-DD HH:MM:SS", ...}. Raises the business's
    known-down error, NotWorkedOut while it is first worked out (the job started; with no
    person waiting it is worked out here instead, speed.person_waits), or what the last
    attempt met."""
    from command_center import speed
    from command_center.connectors.base import NotWorkedOut
    down = getattr(r, "_down", None)
    if down is not None:
        raise down
    # Read through the asker's own reader: the same business, as the same person sees it.
    got = speed.stored("history", r.code, WHAT, work_out, {"business_code": r.code, "reader": r},
                       incremental=True)
    if got is None:
        raise NotWorkedOut("the change history is being read")
    if "failed" in got:
        speed.reraise(got)
    return got


def status(got) -> dict:
    """A figure's data_status for a summary read at got["read_at"] (kpi/live compute
    states it as the figure's as-of)."""
    return {"state": "live", "message": None, "read_at": got.get("read_at")}


def work_out(business_code=None, previous=None, reader=None) -> dict:
    """The summary, read now: incrementally from the scan the last run kept (beside the
    summary, for SCAN_KEEP), or in full. `previous` is the last summary (speed.stored);
    `reader` the asker's (kpi/live _Reader), else one for the business as whoever runs
    this sees it."""
    import frappe

    from command_center import speed
    from command_center.api.panels import HISTORY_ROWS
    from command_center.kpi.live import APPROVED_DOCTYPES, BUSINESS_DOCTYPES, _read, _Reader
    r = reader if reader is not None else _Reader(business_code)
    key = speed.background_key("history-scan", business_code, WHAT)
    c = frappe.cache()
    scan = c.get_value(key)
    now = time.time()
    full = not isinstance(scan, dict) or now - scan.get("full_at", 0) >= FULL_EVERY
    if full:
        scan = {"steps": {}, "docs": {}, "mark": None, "doc_marks": {}, "first": None,
                "full_at": now}
    steps, docs = scan["steps"], scan["docs"]

    # The approval steps since the last run: who took them, on which document.
    filters = {"ref_doctype": ["in", list(APPROVED_DOCTYPES)], "data": ["like", STEP]}
    if scan.get("mark"):
        filters["creation"] = [">=", scan["mark"]]
    mark = scan.get("mark")
    for v in _read(r, "Version", filters, ["ref_doctype", "docname", "owner", "creation"],
                   limit=LIMIT, order_by="creation asc"):
        owners = steps.setdefault(f"{v['ref_doctype']}{SEP}{v['docname']}", [])
        if v.get("owner") not in owners:
            owners.append(v.get("owner"))
        if v.get("creation") and (mark is None or str(v["creation"]) > mark):
            mark = str(v["creation"])
    scan["mark"] = mark

    # Each named document's owner and docstatus: those changed since, and those not yet read.
    for doctype in APPROVED_DOCTYPES:
        prefix = f"{doctype}{SEP}"
        since = scan["doc_marks"].get(doctype)
        # Read before the documents, so one saved meanwhile is read again next time.
        top = _edge(r, doctype, "modified")
        if since and not full:
            for d in _read(r, doctype, {"modified": [">=", since]}, ["name", "owner", "docstatus"],
                           limit=LIMIT):
                if prefix + d["name"] in steps:
                    docs[prefix + d["name"]] = [d.get("owner"), int(d.get("docstatus") or 0)]
        need = [k[len(prefix):] for k in steps if k.startswith(prefix) and k not in docs]
        for i in range(0, len(need), 500):
            chunk = need[i:i + 500]
            got = {d["name"]: d for d in _read(r, doctype, {"name": ["in", chunk]},
                                                ["name", "owner", "docstatus"], limit=500)}
            for name in chunk:
                d = got.get(name)
                # Gone (deleted, or not readable): counted neither way, as before.
                docs[prefix + name] = ([d.get("owner"), int(d.get("docstatus") or 0)]
                                       if d else [None, None])
        if top:
            scan["doc_marks"][doctype] = str(top)

    decided = alone = 0
    for k, owners in steps.items():
        d = docs.get(k)
        if d and d[1] == 1:
            decided += 1
            if set(owners) == {d[0]}:
                alone += 1

    # How much is logged: counts, quick on the indexed ref_doctype; the first entry
    # once a week (it only changes when the log is cleared).
    total = r.count("Version")
    business = r.count("Version", {"ref_doctype": ["in", list(BUSINESS_DOCTYPES)]})
    by_doctype = {dt_: r.count("Version", {"ref_doctype": dt_}) for _, dt_ in HISTORY_ROWS}
    if full or not scan.get("first"):
        first = _edge(r, "Version", "creation", last=False) if total else None
        scan["first"] = str(first) if first else None
    c.set_value(key, scan, expires_in_sec=SCAN_KEEP)
    return {"decided": decided, "alone": alone, "total": total, "business": business,
            "by_doctype": by_doctype, "first": scan["first"]}


def _edge(r, doctype, field, last=True):
    """The largest (or smallest) value of a field, or None (as _Reader.edge, through any
    reader)."""
    rows = r.all(doctype, fields=[field], limit=1, order_by=f"{field} {'desc' if last else 'asc'}")
    return rows[0].get(field) if rows else None
