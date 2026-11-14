"""What a doctype looks like: read from its JSON, the one definition (frappe.get_meta)."""

from __future__ import annotations

import functools
import glob
import json
import os

from insights.compat.state import _dict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCTYPE_DIR = os.path.join(ROOT, "command_center", "command_center", "doctype")
STANDARD = ("name", "creation", "modified", "modified_by", "owner", "docstatus", "idx")


class Meta(_dict):
    def get_field(self, fieldname):
        for f in self.fields:
            if f.fieldname == fieldname:
                return f
        return None

    def has_field(self, fieldname) -> bool:
        return self.get_field(fieldname) is not None

    def get_valid_columns(self) -> list:
        return list(STANDARD) + [f.fieldname for f in self.fields if f.fieldtype not in
                                 ("Section Break", "Column Break", "Tab Break", "HTML",
                                  "Password", "Button", "Heading")]

    def password_fields(self) -> list:
        return [f.fieldname for f in self.fields if f.fieldtype == "Password"]

    def get_table_fields(self) -> list:
        return []


@functools.lru_cache(maxsize=None)
def _all() -> dict:
    out = {}
    for path in glob.glob(os.path.join(DOCTYPE_DIR, "*", "*.json")):
        d = json.load(open(path))
        if d.get("doctype") != "DocType":
            continue
        meta = Meta(d)
        meta.fields = [_dict(f) for f in d.get("fields", [])]
        meta.module_path = os.path.dirname(path)
        out[d["name"]] = meta
    return out


def get_meta(doctype: str) -> Meta:
    meta = _all().get(doctype)
    if meta is None:
        from insights.compat.state import DoesNotExistError
        raise DoesNotExistError(f"DocType {doctype} not found")
    return meta


def exists(doctype: str) -> bool:
    return doctype in _all()
