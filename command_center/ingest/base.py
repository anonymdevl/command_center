"""Turning source documents into facts, with their provenance attached.

Three properties matter more than speed, and the design is shaped by them.

**Every row says where it came from.** `src_doctype`, `src_name`, `src_row_name`,
`src_modified`, `src_docstatus`. Any figure on any screen can therefore answer
"which records?" by selecting its contributing rows — drill-down is a GROUP BY in
reverse, not a separate feature that has to be built per screen.

**A reload replaces rather than duplicates.** `fact_key` is a hash of business,
source doctype, document and row. Re-ingesting the same document is safe, which is
what makes "rebuildable from source" true rather than aspirational. A fact table
nobody dares rebuild is a fact table that has quietly diverged.

**Facts are the platform's own derived tables.** Writing them in bulk breaks no
rule: the prohibition on going round ERPNext exists to protect records ERPNext
owns. These are ours, they hold no business truth of their own, and a rebuild that
takes an hour is a rebuild nobody runs.

Only the local business is ingested. A peer's figures are read from the site that
computed them — §3.3 of the blueprint. Nothing of another company's ledger is
stored here, which is why `business_code` is single-valued in practice even though
every query is written to group by it.
"""

from __future__ import annotations

import hashlib

import frappe
from frappe.utils import now_datetime

CHUNK = 5000


class Ingestor:
    # An ingestor names the fact it fills; the doctype it writes to comes from the
    # shared schema. Declaring both invites them to drift, and a fact written to one
    # table and read from another is a silent zero.
    fact: str = ""

    @property
    def target(self) -> str:
        from command_center.facts.schema import FACTS
        name = FACTS.get(self.fact)
        if not name:
            raise ValueError(
                f"{type(self).__name__} fills {self.fact!r}, which facts.schema "
                f"does not know. Add it there and nowhere else.")
        return name

    """One fact table, one source grain."""

    fact: str = ""
    target: str = ""
    source_doctype: str = ""

    # -- subclasses implement -------------------------------------------------
    def extract(self, conn, since=None, limit=None, as_of=None) -> list[dict]:
        """Return fully-formed fact rows, lineage included."""
        raise NotImplementedError

    # -- lineage --------------------------------------------------------------
    @staticmethod
    def key(business_code, src_doctype, src_name, src_row_name=None) -> str:
        raw = "|".join([business_code, src_doctype, src_name, src_row_name or ""])
        return hashlib.sha1(raw.encode()).hexdigest()

    def stamp(self, row: dict, business_code: str) -> dict:
        row["business_code"] = business_code
        row["src_doctype"] = row.get("src_doctype") or self.source_doctype
        row["fact_key"] = self.key(business_code, row["src_doctype"],
                                   row["src_name"], row.get("src_row_name"))
        now = now_datetime()
        row["ingested_at"] = now
        # bulk_insert writes raw rows, so Frappe's own columns must be supplied.
        row.setdefault("creation", now)
        row.setdefault("modified", now)
        row.setdefault("owner", frappe.session.user)
        row.setdefault("modified_by", frappe.session.user)
        row.setdefault("docstatus", 0)
        row.setdefault("idx", 0)
        return row

    # -- load -----------------------------------------------------------------
    def load(self, conn, since=None, limit=None, as_of=None,
             full: bool = False) -> dict:
        """Incremental by default, from the stored watermark.

        `full=True` ignores the watermark and reloads everything. It is safe
        because fact_key makes a reload replace rather than duplicate — the
        property that lets anyone rebuild without asking permission.
        """
        state = self._state(conn.code)
        since = None if full else (since or state.last_src_modified)
        started = now_datetime()

        try:
            rows = self.extract(conn, since=since, limit=limit, as_of=as_of)
            rows = [self.stamp(r, conn.code) for r in rows]

            if rows:
                self._purge(conn.code, {r["src_name"] for r in rows})
                self._insert(rows)

            watermark = max((r.get("src_modified") for r in rows
                             if r.get("src_modified")), default=since)
            state.update({
                "last_src_modified": watermark,
                "as_of_date": as_of,
                "last_run": started,
                "rows_loaded": len(rows),
                "status": "OK",
                "last_error": "",
            })
            state.save(ignore_permissions=True)
            frappe.db.commit()
            return {"fact": self.fact, "business": conn.code,
                    "rows": len(rows), "watermark": str(watermark) if watermark else None}

        except Exception:
            # Capture before the rollback: get_traceback() reads the live
            # exception, and anything that raises in between would replace it.
            failure = frappe.get_traceback()
            frappe.db.rollback()
            try:
                state = self._state(conn.code)
                state.update({"status": "Failed", "last_run": started,
                              "last_error": failure[-900:]})
                state.save(ignore_permissions=True)
                frappe.db.commit()
            except Exception:
                # Recording the failure must never replace the failure.
                frappe.log_error(title=f"Command Center ingest {self.fact}",
                                 message=failure)
            raise

    # -- plumbing -------------------------------------------------------------
    def _state(self, business_code: str):
        name = f"{self.fact}-{business_code}"
        if frappe.db.exists("Command Center Ingest State", name):
            return frappe.get_doc("Command Center Ingest State", name)
        doc = frappe.get_doc({
            "doctype": "Command Center Ingest State",
            "fact": self.fact, "business_code": business_code,
            "status": "Never Run",
        }).insert(ignore_permissions=True)
        # Committed immediately so it survives the rollback in load()'s failure
        # path. Without this, a first run that fails rolls back the state row it
        # is about to write the failure into, and reload() then raises
        # DoesNotExistError -- which replaces the real error with a misleading
        # "not found". That cost a debugging cycle.
        frappe.db.commit()
        return doc

    def _purge(self, business_code: str, src_names: set[str]):
        """Remove this batch's rows before reinserting them.

        Scoped to the documents in the batch, so a partial reload never deletes
        facts it is not about to replace.
        """
        names = list(src_names)
        for i in range(0, len(names), CHUNK):
            frappe.db.delete(self.target, {
                "business_code": business_code,
                "src_name": ["in", names[i:i + CHUNK]],
            })

    def _insert(self, rows: list[dict]):
        fields = sorted({k for r in rows for k in r})
        columns = ["name"] + fields
        values = []
        for r in rows:
            values.append([r["fact_key"][:32]] + [r.get(f) for f in fields])
        for i in range(0, len(values), CHUNK):
            frappe.db.bulk_insert(self.target, columns, values[i:i + CHUNK],
                                  ignore_duplicates=True)


def require_fields(rows: list[dict], fields, context: str) -> list[dict]:
    """Fail loudly when the source returned fewer columns than were asked for.

    Frappe drops fields silently in at least one case — a child table queried
    without `parent_doctype` comes back with only `name`, no error. The first
    symptom was a KeyError several frames deep inside a loop, which says nothing
    about the cause.

    Checking the first row costs nothing and turns that into a sentence.
    """
    if not rows:
        return rows
    missing = [f for f in fields if f not in rows[0]]
    if missing:
        frappe.throw(
            f"{context}: the source returned no {', '.join(missing)}. "
            f"For a child table this usually means parent_doctype was not "
            f"passed, in which case Frappe returns only 'name' and reports "
            f"nothing. Got: {', '.join(sorted(rows[0]))}."
        )
    return rows


def ageing_bucket(days: int | None) -> str:
    """The four bands, named the way the interface says them."""
    if days is None:
        return "Unknown"
    if days <= 0:
        return "Not yet due"
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def resolve_as_of(conn) -> str:
    """The date ageing is measured against, and it is not today by default.

    On a restored or archived dataset, measuring against the current date puts
    every balance in the oldest bucket. That is a statement about the age of the
    snapshot, not about how the business collects — and reading it as the latter
    produced a materially wrong finding on this very dataset, which is why this
    function exists rather than a call to `today()`.

    The horizon is the latest posting date the data actually contains. On live
    data that is today or close to it, so nothing is lost.
    """
    latest = conn.get_list("Sales Invoice", filters={"docstatus": 1},
                           fields=["posting_date"],
                           order_by="posting_date desc", limit=1)
    if latest:
        return latest[0]["posting_date"]
    return frappe.utils.today()
