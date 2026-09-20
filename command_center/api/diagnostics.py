"""What is actually deployed on this site.

Written because I could not tell whether a fix had reached the server, and kept
asking rather than checking. A symptom that looks identical before and after a
deploy is indistinguishable from a fix that did not work, and guessing which
wastes a round trip every time.

Read-only, management-only, and it reports the served files rather than what the
repository says should be there.
"""

from __future__ import annotations

import hashlib
import os

import frappe

from command_center.api.businesses import require_manager

DIST = ("public", "command-center")
MANIFEST = ("public", "command-center", ".vite", "manifest.json")
PAGE = ("www", "command-center.html")


@frappe.whitelist()
def deployed() -> dict:
    """The version, the served bundle, and whether known fixes are present."""
    require_manager()
    app_path = frappe.get_app_path("command_center")

    page = _read(app_path, *PAGE)
    # Filenames are content-hashed, so the manifest is the only way to know which
    # files the page actually loads. Reading fixed names reported "not present"
    # for a perfectly good deploy, which is the kind of false alarm that makes a
    # diagnostic worth less than none.
    js, css = _entry(app_path)
    return {
        "app_version": frappe.get_attr("command_center.__version__"),
        "frappe": frappe.__version__,
        "bundle": _stat(app_path, *DIST, js) if js else {"present": False,
                                                         "why": "no manifest entry"},
        "styles": _stat(app_path, *DIST, css) if css else {"present": False,
                                                           "why": "no css in manifest"},
        # Specific, verifiable answers about fixes that have been hard to confirm
        # from the outside. Each is a fact about the file on disk, not a claim.
        "checks": {
            "boot_payload_marked_safe": "{{ boot | safe }}" in (page or ""),
            "csrf_marked_safe": "{{ csrf_token | safe }}" in (page or ""),
            "react_mount_present": 'id="cc-root"' in (page or ""),
        },
    }


def _entry(app_path: str):
    """The hashed filenames the page will load, from Vite's manifest."""
    path = os.path.join(app_path, *MANIFEST)
    if not os.path.exists(path):
        return None, None
    try:
        import json as _json

        manifest = _json.load(open(path))
        entry = next(v for v in manifest.values() if v.get("isEntry"))
        css = (entry.get("css") or [None])[0]
        return entry["file"], css
    except Exception:
        return None, None


def _stat(base: str, *parts) -> dict:
    path = os.path.join(base, *parts)
    if not os.path.exists(path):
        return {"present": False, "path": os.path.join(*parts)}
    raw = open(path, "rb").read()
    return {
        "present": True,
        "path": os.path.join(*parts),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest()[:12],
        "modified": frappe.utils.get_datetime_str(
            frappe.utils.convert_utc_to_system_timezone(
                frappe.utils.get_datetime(
                    __import__("datetime").datetime.utcfromtimestamp(
                        os.path.getmtime(path)
                    )
                )
            )
        ),
    }


def _read(base: str, *parts) -> str | None:
    path = os.path.join(base, *parts)
    if not os.path.exists(path):
        return None
    return open(path, encoding="utf-8").read()


@frappe.whitelist()
def contains(needle: str, where: str = "bundle") -> dict:
    """Is a given string present in the served bundle?

    Blunt, and useful: it answers "did my change reach the server" in one call
    instead of a deploy-and-squint cycle.
    """
    require_manager()
    app_path = frappe.get_app_path("command_center")
    if where == "page":
        target = PAGE
    else:
        js, css = _entry(app_path)
        name = js if where == "bundle" else css
        if not name:
            frappe.throw("No manifest entry — the interface has not been built.")
        target = DIST + (name,)
    content = _read(app_path, *target) or ""
    return {"where": where, "needle": needle, "found": needle in content,
            "bytes": len(content)}
