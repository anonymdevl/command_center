"""The product's brand, in one place: every page, PDF, workbook and email asks here.

The platform is sold under its owner's product name and logo, and every document it
produces says who built it. None of that is code: an administrator sets it under
Settings -> Branding (insights/core/platform_settings.py), and it is kept in the
platform's configuration (insights.json "branding"; site_config on a Frappe site),
read at each use so a change reaches the web server and the scheduler without a
restart. Logos are files in the platform's files folder (frappe.get_site_path), each
named after its own content, so a new logo gets a new address and the old one can be
cached for ever.

    branding(business_code)   everything an output needs: the product's name and
                              tagline, its logos, the vendor's details, the footer
                              lines, and the business's own co-brand (client name
                              and logo) when one is set for it
    public()                  what the pages may show anyone (the sign-in page too)
    footer_line(b)            "<product> · built by <company> — <person> · <email> · ..."
    prepared_line(b)          "Prepared with <product> by <company> · <email> · ..."
    logo_data_uri(name)       a stored logo as a data: URI, for a PDF (which fetches
                              nothing)
    check_image(raw)          the upload rules: PNG, JPEG or WebP only, checked by
                              content, at most MAX_BYTES; never SVG
    store_image(kind, raw)    the file written, named after its content

Nothing here names a person: the vendor's person, email, phone and website are free
text the administrator fills in, and are left out of every line while blank.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import struct

import frappe

CONFIG_KEY = "branding"
DEFAULTS = {
    "product_name": "Ultrasoft Insights",
    "tagline": "Advanced AI-Powered Business Intelligence for ERPNext",
    "company": "Ultrasoft Systems",
    "person": "",
    "email": "",
    "phone": "",
    "website": "",
}
TEXT_FIELDS = tuple(DEFAULTS)
# The longest each may be: a name that will not fit the sidebar or a page footer is a
# mistake, not a choice.
MAX_LEN = {"product_name": 60, "tagline": 80, "company": 80, "person": 80, "email": 120,
           "phone": 40, "website": 120}
LOGO_KINDS = ("logo_light", "logo_dark", "favicon")
CLIENT_KIND = "client"

MAX_BYTES = 1024 * 1024
FOLDER = "branding"
URL_PREFIX = "/branding/"
TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
# A stored file's name: its kind, the first 16 hex characters of its SHA-256, the type
# its content proved to be. Anything else is never served.
FILE_RE = re.compile(r"^(logo_light|logo_dark|favicon|client)-[0-9a-f]{16}\.(png|jpg|webp)$")


class BrandError(ValueError):
    """An upload or a value that is refused, in words for the screen."""


# --- the stored settings ---------------------------------------------------------------
def _conf() -> dict:
    """The stored branding, read afresh: insights.json on the platform (a change saved by
    the web server reaches the scheduler without a restart), site_config on Frappe."""
    stored, read = None, False
    try:
        from django.conf import settings as dj  # the platform

        import json
        with open(dj.CONFIG_PATH) as fh:
            stored = json.load(fh).get(CONFIG_KEY)
        read = True  # the file is the truth, even when it holds no branding
    except Exception:
        stored = None
    if not read:
        try:
            stored = (getattr(frappe, "conf", None) or {}).get(CONFIG_KEY)
        except Exception:
            stored = None
    return dict(stored) if isinstance(stored, dict) else {}


def stored() -> dict:
    """The settings as saved, with the defaults filled in for what was never set."""
    raw = _conf()
    out = {}
    for k, default in DEFAULTS.items():
        v = raw.get(k)
        # Never set: the default. Cleared: blank -- except the name and the company,
        # which are never blank.
        v = default if v is None else str(v).strip()
        out[k] = v or (default if k in ("product_name", "company") else "")
    for k in LOGO_KINDS:
        v = raw.get(k)
        out[k] = v if isinstance(v, str) and FILE_RE.match(v) else None
    clients = raw.get("businesses") if isinstance(raw.get("businesses"), dict) else {}
    out["businesses"] = {str(code): _client(v) for code, v in clients.items() if isinstance(v, dict)}
    return out


def _client(v: dict) -> dict:
    logo = v.get("logo")
    return {"display_name": str(v.get("display_name") or "").strip(),
            "logo": logo if isinstance(logo, str) and FILE_RE.match(logo) else None}


def url_for(name: str | None) -> str | None:
    return (URL_PREFIX + name) if name else None


# --- what an output uses ---------------------------------------------------------------
def branding(business_code: str | None = None) -> dict:
    """Everything a page, PDF, workbook or email needs to carry the brand. Never raises:
    an unreadable configuration gives the defaults."""
    try:
        s = stored()
    except Exception:
        s = {**DEFAULTS, **{k: None for k in LOGO_KINDS}, "businesses": {}}
    light, dark = s.get("logo_light"), s.get("logo_dark")
    client = (s.get("businesses") or {}).get(str(business_code or "")) or {}
    b = {
        "product": s["product_name"], "tagline": s["tagline"], "company": s["company"],
        "person": s["person"], "email": s["email"], "phone": s["phone"],
        "website": s["website"],
        # One logo set serves both backgrounds.
        "logo_light": light or dark, "logo_dark": dark or light,
        "logo_light_url": url_for(light or dark), "logo_dark_url": url_for(dark or light),
        "favicon_url": url_for(s.get("favicon")) or "/assets/command_center/images/command-center.svg",
        "client_name": client.get("display_name") or "",
        "client_logo": client.get("logo"),
        "client_logo_url": url_for(client.get("logo")),
    }
    b["footer"] = footer_line(b)
    b["prepared"] = prepared_line(b)
    return b


def public() -> dict:
    """What a page may show: the name, the logos and the vendor's footer details (the
    sign-in page shows them before anyone is signed in, so nothing private is here)."""
    b = branding()
    return {k: b[k] for k in ("product", "tagline", "company", "person", "email", "phone",
                              "website", "logo_light_url", "logo_dark_url", "favicon_url",
                              "footer", "prepared")}


def clients() -> dict:
    """business_code -> {display_name, logo_url}, for the businesses that have a co-brand."""
    try:
        got = stored().get("businesses") or {}
    except Exception:
        return {}
    return {code: {"display_name": v["display_name"], "logo_url": url_for(v["logo"])}
            for code, v in got.items() if v.get("display_name") or v.get("logo")}


def _contacts(b: dict) -> list:
    return [b[k] for k in ("email", "phone", "website") if b.get(k)]


def footer_line(b: dict) -> str:
    """Every PDF page's footer: "<product> · built by <company> — <person> · <email> ·
    <phone> · <website>", leaving out what is blank."""
    who = b["company"] + (f" — {b['person']}" if b.get("person") else "")
    return " · ".join([b["product"], f"built by {who}"] + _contacts(b))


def prepared_line(b: dict) -> str:
    """A workbook's and an email's last line: "Prepared with <product> by <company> ·
    <email> · <phone> · <website>"."""
    return " · ".join([f"Prepared with {b['product']} by {b['company']}"] + _contacts(b))


def for_business_name(b: dict, business_name: str) -> str:
    """The name a document is prepared for: the co-brand's display name if one is set."""
    return b.get("client_name") or business_name


# --- logos -------------------------------------------------------------------------------
def folder() -> str:
    return frappe.get_site_path(FOLDER)


def path_of(name: str) -> str | None:
    """The file behind a stored name, or None for a name that is not one of ours."""
    if not name or not FILE_RE.match(name):
        return None
    full = os.path.join(folder(), name)
    return full if os.path.isfile(full) else None


def logo_data_uri(name: str | None) -> str | None:
    """A stored logo as a data: URI. The PDF engine fetches nothing, so a PDF carries its
    logos inside it."""
    full = path_of(name) if name else None
    if not full:
        return None
    ext = name.rsplit(".", 1)[1]
    with open(full, "rb") as fh:
        return f"data:{TYPES[ext]};base64,{base64.b64encode(fh.read()).decode()}"


def decode_upload(data) -> bytes:
    """The bytes of an upload sent as a data: URL or bare base64 (the screen reads the
    file and sends it as text). What it says its type is, is ignored: check_image looks
    at the content."""
    if isinstance(data, bytes):
        raw = data
    else:
        text = str(data or "").strip()
        if text.startswith("data:"):
            head, _, text = text.partition(",")
            if ";base64" not in head:
                raise BrandError("Choose a PNG, JPEG or WebP image file.")
        if len(text) > (MAX_BYTES * 4) // 3 + 8:
            raise BrandError(f"That image is too large. The most it may be is "
                             f"{MAX_BYTES // 1024} KB.")
        try:
            raw = base64.b64decode(text, validate=True)
        except Exception:
            raise BrandError("That file could not be read. Choose a PNG, JPEG or WebP image.")
    if not raw:
        raise BrandError("Choose an image file.")
    return raw


def check_image(raw: bytes) -> str:
    """The image's type ("png", "jpg" or "webp"), if it is one and within the size
    limit; otherwise BrandError in plain words.

    Checked by content, never by the file's name or the type the browser claims: the
    signature and the header that follows it must both be right, and the picture must
    have a size. SVG is refused whatever it is called -- it is a document that can
    carry scripts, not a picture."""
    if len(raw) > MAX_BYTES:
        raise BrandError(f"That image is too large ({len(raw) // 1024} KB). The most it may be "
                         f"is {MAX_BYTES // 1024} KB.")
    head = raw[:512].lstrip().lower()
    if head.startswith((b"<?xml", b"<svg", b"<!doctype", b"<html")) or b"<svg" in head:
        raise BrandError("SVG images are not accepted, because they can carry scripts. "
                         "Save the logo as a PNG, JPEG or WebP image.")
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        if len(raw) < 33 or raw[12:16] != b"IHDR":
            raise BrandError("That PNG file is damaged.")
        w, h = struct.unpack(">II", raw[16:24])
        if not (0 < w <= 10000 and 0 < h <= 10000):
            raise BrandError("That PNG file has no usable size.")
        return "png"
    if raw[:3] == b"\xff\xd8\xff":
        # A start-of-frame marker says the picture's size; a JPEG without one is not a picture.
        if not re.search(rb"\xff[\xc0-\xc3\xc5-\xc7\xc9-\xcb\xcd-\xcf]", raw[2:]):
            raise BrandError("That JPEG file is damaged.")
        return "jpg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        if raw[12:15] != b"VP8" or len(raw) < 30:
            raise BrandError("That WebP file is damaged.")
        return "webp"
    raise BrandError("That is not a PNG, JPEG or WebP image.")


def store_image(kind: str, raw: bytes) -> str:
    """Write a checked image to the files folder under a name made from its content, and
    return that name. The uploaded file's own name is never used."""
    if kind not in LOGO_KINDS + (CLIENT_KIND,):
        raise BrandError("Unknown kind of logo.")
    ext = check_image(raw)
    name = f"{kind}-{hashlib.sha256(raw).hexdigest()[:16]}.{ext}"
    os.makedirs(folder(), exist_ok=True)
    full = os.path.join(folder(), name)
    if not os.path.exists(full):
        tmp = full + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, full)
    return name


def in_use(cfg: dict | None = None) -> set:
    """Every file name the stored branding still refers to."""
    cfg = cfg if cfg is not None else _conf()
    names = {cfg.get(k) for k in LOGO_KINDS}
    for v in (cfg.get("businesses") or {}).values():
        if isinstance(v, dict):
            names.add(v.get("logo"))
    return {n for n in names if isinstance(n, str)}


def forget(name: str | None, cfg: dict) -> None:
    """Delete a logo file the branding no longer refers to."""
    if not name or name in in_use(cfg):
        return
    full = path_of(name)
    if full:
        try:
            os.remove(full)
        except OSError:
            pass


# --- emails ------------------------------------------------------------------------------
def email_html(body: str, business_code: str | None = None) -> str:
    """An email's body inside the brand: the product's name (and its logo, when the
    platform has a public address to load it from) at the top, the vendor's line at the
    foot. `body` is HTML the caller has already escaped."""
    from frappe.utils import escape_html as esc

    b = branding(business_code)
    logo = ""
    try:
        from frappe.utils import get_url
        base = get_url("")
    except Exception:
        base = ""
    if b["logo_light_url"] and base.startswith("https://"):
        logo = (f"<img src=\"{esc(base.rstrip('/') + b['logo_light_url'])}\" alt=\"\" "
                f"style=\"height:28px;vertical-align:middle;margin-right:8px\">")
    return (
        "<div style=\"font-family:Helvetica,Arial,sans-serif;font-size:14px;line-height:1.55;"
        "color:#1d2026;max-width:640px\">"
        f"<div style=\"border-bottom:1px solid #e3e5ea;padding-bottom:10px;margin-bottom:16px\">"
        f"{logo}<b style=\"font-size:15px\">{esc(b['product'])}</b>"
        + (f"<span style=\"color:#646973\"> · {esc(b['tagline'])}</span>" if b["tagline"] else "")
        + "</div>"
        f"{body}"
        "<div style=\"border-top:1px solid #e3e5ea;margin-top:20px;padding-top:10px;"
        f"font-size:12px;color:#7a808a\">{esc(b['prepared'])}</div></div>")
