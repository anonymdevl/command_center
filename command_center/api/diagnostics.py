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

BUNDLE = ("public", "command-center", "command-center.js")
STYLES = ("public", "command-center", "command-center.css")
PAGE = ("www", "command-center.html")


@frappe.whitelist()
def deployed() -> dict:
    """The version, the served bundle, and whether known fixes are present."""
    require_manager()
    app_path = frappe.get_app_path("command_center")

    page = _read(app_path, *PAGE)
    return {
        "app_version": frappe.get_attr("command_center.__version__"),
        "frappe": frappe.__version__,
        "bundle": _stat(app_path, *BUNDLE),
        "styles": _stat(app_path, *STYLES),
        # Specific, verifiable answers about fixes that have been hard to confirm
        # from the outside. Each is a fact about the file on disk, not a claim.
        "checks": {
            "boot_payload_marked_safe": "{{ boot | safe }}" in (page or ""),
            "csrf_marked_safe": "{{ csrf_token | safe }}" in (page or ""),
            "react_mount_present": 'id="cc-root"' in (page or ""),
        },
    }


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
    target = {"bundle": BUNDLE, "styles": STYLES, "page": PAGE}.get(where)
    if not target:
        frappe.throw("where must be one of: bundle, styles, page")
    content = _read(app_path, *target) or ""
    return {"where": where, "needle": needle, "found": needle in content,
            "bytes": len(content)}
