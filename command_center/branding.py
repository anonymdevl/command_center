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
    document(business_code, own)
                              how one PDF or workbook carries the brand: the
                              business's Report Style (Platform Branding, Client
                              Branding or Client Letterhead) and vendor credit (Show,
                              Small, Hide) resolved; own=True for the platform's own
                              documents (usage statements, incident reports), which
                              always carry the platform's brand and full credit
    logo_data_uri(name)       a stored logo as a data: URI, for a PDF (which fetches
                              nothing)
    check_image(raw, kind)    the upload rules: PNG, JPEG or WebP only (PNG or JPEG for
                              what only PDFs use), checked by content, at most
                              MAX_BYTES (LETTER_MAX_BYTES for a letterhead, which must
                              also be a wide strip); never SVG
    store_image(kind, raw)    the file written, named after its content

The screens' logos (light and dark backgrounds, favicon) and the PDFs' Report Logo are
separate: a PDF uses the Report Logo, else the light-background logo, else the
product's name. A business's letterhead images print on every page of its PDFs
(export.page_options writes them into the PDF engine's header and footer).

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
LOGO_KINDS = ("logo_light", "logo_dark", "favicon")  # the screens'
REPORT_KIND = "logo_report"  # the PDFs' own logo, instead of the light-background one
PLATFORM_KINDS = LOGO_KINDS + (REPORT_KIND,)
CLIENT_KIND = "client"
# A business's letterhead: the strip printed at the top of every page, and the optional
# one at the foot.
LETTER_KINDS = {"header": "letterhead", "footer": "letterfoot"}

# A business's Report Style: whose brand leads its PDFs and workbooks.
STYLES = {"platform": "Platform Branding", "client": "Client Branding",
          "letterhead": "Client Letterhead"}
# The vendor's credit on a business's documents. Hide is the administrator's alone.
CREDITS = {"show": "Show", "small": "Small", "hide": "Hide"}

MAX_BYTES = 1024 * 1024
LETTER_MAX_BYTES = 2 * 1024 * 1024
FOLDER = "branding"
URL_PREFIX = "/branding/"
TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
# What the PDF engine (wkhtmltopdf) can draw: it cannot draw WebP.
PRINT_TYPES = ("png", "jpg")
# A stored file's name: its kind, the first 16 hex characters of its SHA-256, the type
# its content proved to be. Anything else is never served.
FILE_RE = re.compile(r"^(logo_light|logo_dark|favicon|logo_report|client|letterhead|letterfoot)"
                     r"-[0-9a-f]{16}\.(png|jpg|webp)$")

# The upload rules by kind. A letterhead strip is printed across the full width of an
# A4 page (210 mm): at least MIN_WIDTH pixels wide so it prints sharply, and as wide
# for its height as "ratio" says, so the header is at most 60 mm and the footer 42 mm
# deep, and neither is a sliver (an A4 letterhead at 300 dpi is about 2480 x 350 px).
LETTER_MIN_WIDTH = 1000
RULES = {
    REPORT_KIND: {"types": PRINT_TYPES, "max_bytes": MAX_BYTES},
    # A client's logo is only ever drawn on its documents, so it is one the PDFs can draw.
    CLIENT_KIND: {"types": PRINT_TYPES, "max_bytes": MAX_BYTES},
    "letterhead": {"types": PRINT_TYPES, "max_bytes": LETTER_MAX_BYTES, "ratio": (3.5, 25.0)},
    "letterfoot": {"types": PRINT_TYPES, "max_bytes": LETTER_MAX_BYTES, "ratio": (5.0, 40.0)},
}
DEFAULT_RULE = {"types": ("png", "jpg", "webp"), "max_bytes": MAX_BYTES}
A4_WIDTH_MM = 210.0


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
    for k in PLATFORM_KINDS:
        v = raw.get(k)
        out[k] = v if _ours(v, k) else None
    clients = raw.get("businesses") if isinstance(raw.get("businesses"), dict) else {}
    out["businesses"] = {str(code): _client(v) for code, v in clients.items() if isinstance(v, dict)}
    return out


def _ours(name, kind: str | None = None) -> bool:
    """A stored file name the platform made, of that kind when one is named."""
    return (isinstance(name, str) and bool(FILE_RE.match(name))
            and (kind is None or name.startswith(kind + "-")))


def _client(v: dict) -> dict:
    logo, head, foot = v.get("logo"), v.get("header"), v.get("footer")
    return {"display_name": str(v.get("display_name") or "").strip(),
            "logo": logo if _ours(logo) else None,
            "style": v.get("style") if v.get("style") in STYLES else "platform",
            "credit": v.get("credit") if v.get("credit") in CREDITS else "show",
            "header": head if _ours(head, "letterhead") else None,
            "footer": foot if _ours(foot, "letterfoot") else None}


def url_for(name: str | None) -> str | None:
    return (URL_PREFIX + name) if name else None


# --- what an output uses ---------------------------------------------------------------
def branding(business_code: str | None = None) -> dict:
    """Everything a page, PDF, workbook or email needs to carry the brand. Never raises:
    an unreadable configuration gives the defaults."""
    try:
        s = stored()
    except Exception:
        s = {**DEFAULTS, **{k: None for k in PLATFORM_KINDS}, "businesses": {}}
    light, dark = s.get("logo_light"), s.get("logo_dark")
    client = (s.get("businesses") or {}).get(str(business_code or "")) or {}
    report = s.get(REPORT_KIND)
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
        # The PDFs' logo: the Report Logo, else the light-background one (else, in the
        # PDF, the product's name).
        "report_logo": report or light or dark,
        "style": client.get("style") or "platform",
        "credit": client.get("credit") or "show",
        "letterhead": client.get("header"),
        "letterfoot": client.get("footer"),
    }
    b["footer"] = footer_line(b)
    b["prepared"] = prepared_line(b)
    return b


def document(business_code: str | None = None, own: bool = False, style: str | None = None,
             credit: str | None = None) -> dict:
    """branding(), resolved for one PDF or workbook.

    own=True: the platform's own documents (a customer's usage statement, an incident
    report) -- the platform's brand and the full vendor credit, whatever the business
    chose, and no co-brand. Otherwise the business's Report Style and credit, or `style`
    and `credit` when given (Settings' preview, which stores nothing).

    Adds "look" (platform, client or letterhead -- a letterhead with no header image
    prints as client branding), "credit", "credit_line" (a PDF's, blank when hidden),
    "prepared_credit" (a workbook's) and "issuer" (whose document it reads as)."""
    b = branding(None if own else business_code)
    if own:
        style, credit = "platform", "show"
    else:
        style = style if style in STYLES else b["style"]
        credit = credit if credit in CREDITS else b["credit"]
    if style == "letterhead" and not b["letterhead"]:
        style = "client"
    b = {**b, "look": style, "credit": credit}
    small = small_line(b)
    b["credit_line"] = {"show": b["footer"], "small": small, "hide": ""}[credit]
    b["prepared_credit"] = {"show": b["prepared"], "small": small, "hide": ""}[credit]
    return b


def small_line(b: dict) -> str:
    """The vendor's credit in one short line: "Prepared with <product>"."""
    return f"Prepared with {b['product']}"


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


def decode_upload(data, max_bytes: int = MAX_BYTES) -> bytes:
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
        if len(text) > (max_bytes * 4) // 3 + 8:
            raise BrandError(f"That image is too large. The most it may be is "
                             f"{max_bytes // 1024} KB.")
        try:
            raw = base64.b64decode(text, validate=True)
        except Exception:
            raise BrandError("That file could not be read. Choose a PNG, JPEG or WebP image.")
    if not raw:
        raise BrandError("Choose an image file.")
    return raw


def rule(kind: str | None) -> dict:
    return RULES.get(kind or "", DEFAULT_RULE)


def check_image(raw: bytes, kind: str | None = None) -> str:
    """The image's type ("png", "jpg" or "webp"), if it is one and within the rules for
    `kind` (RULES: the size limit, the types the PDFs can draw, a letterhead's shape);
    otherwise BrandError in plain words.

    Checked by content, never by the file's name or the type the browser claims: the
    signature and the header that follows it must both be right, and the picture must
    have a size. SVG is refused whatever it is called -- it is a document that can
    carry scripts, not a picture."""
    r = rule(kind)
    ext = _check_content(raw, r["max_bytes"])
    if ext not in r["types"]:
        raise BrandError("PDFs cannot show WebP images, so this one must be a PNG or JPEG "
                         "image.")
    if "ratio" in r:
        size = image_size(raw)
        if not size:
            raise BrandError("The size of that image could not be read. Save it again as a "
                             "PNG or JPEG image.")
        w, h = size
        lo, hi = r["ratio"]
        part = "header" if kind == "letterhead" else "footer"
        if w < LETTER_MIN_WIDTH or not (lo <= w / h <= hi):
            raise BrandError(
                f"A letterhead {part} should be a wide strip as wide as the page: at least "
                f"{LETTER_MIN_WIDTH} pixels wide, and {lo:g} to {hi:g} times as wide as it is "
                f"tall (an A4 letterhead at 300 dpi is about 2480 x 350 pixels). This one is "
                f"{w} x {h} pixels.")
    return ext


def image_size(raw: bytes) -> tuple[int, int] | None:
    """(width, height) in pixels of a PNG or JPEG, from its header; None if unreadable."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) >= 24:
        w, h = struct.unpack(">II", raw[16:24])
        return (w, h) if w and h else None
    if raw[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(raw)
    while i + 4 <= n:
        if raw[i] != 0xFF:
            return None
        marker = raw[i + 1]
        if marker == 0xFF:  # padding
            i += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker in (0xD9, 0xDA):  # end of image, or the picture data: no size before it
            return None
        length = struct.unpack(">H", raw[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if i + 9 > n:
                return None
            h, w = struct.unpack(">HH", raw[i + 5:i + 9])
            return (w, h) if w and h else None
        if length < 2:
            return None
        i += 2 + length
    return None


def height_mm(name: str | None, width_mm: float = A4_WIDTH_MM) -> float:
    """How deep a stored image prints at `width_mm` wide (a letterhead: the page's width)."""
    full = path_of(name) if name else None
    if not full:
        return 0.0
    with open(full, "rb") as fh:
        size = image_size(fh.read())
    if not size:
        return 0.0
    return round(width_mm * size[1] / size[0], 1)


def _check_content(raw: bytes, max_bytes: int) -> str:
    if len(raw) > max_bytes:
        raise BrandError(f"That image is too large ({len(raw) // 1024} KB). The most it may be "
                         f"is {max_bytes // 1024} KB.")
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
    if kind not in PLATFORM_KINDS + (CLIENT_KIND,) + tuple(LETTER_KINDS.values()):
        raise BrandError("Unknown kind of logo.")
    ext = check_image(raw, kind)
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
    names = {cfg.get(k) for k in PLATFORM_KINDS}
    for v in (cfg.get("businesses") or {}).values():
        if isinstance(v, dict):
            names.update(v.get(k) for k in ("logo", "header", "footer"))
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
