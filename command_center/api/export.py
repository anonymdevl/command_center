"""Taking an answer, a table or the records behind a figure out of the platform.

Three downloads, all management-only, all reads -- nothing here creates a record.
Files are streamed back as the response; no File document is written to the site.

    answer_pdf     an Ask AI answer or a written report as a PDF: the product's brand
                   (and the business's co-brand) at the top, the title, business,
                   as-of date, who it was prepared for and when, the answer, and the
                   vendor's line and "Page X of Y" at the foot of every page
    tables_xlsx    one or more tables (from an answer or a screen) as an .xlsx, one
                   sheet each
    records_xlsx   every record behind a figure -- not just the top rows the drawer
                   shows -- up to 20,000

Screens are printed by the browser (print styles in shell.py), so the PDF is exactly
what the manager is looking at. The answer PDF is built here because it should not
depend on which screen happens to be open.
"""

from __future__ import annotations

import io
import re

import frappe
from frappe.utils import escape_html

from command_center import branding as brand
from command_center.api import pdf_blocks, report_text
from command_center.api.businesses import require_manager

EXPORT_CAP = 20000
MAX_TABLES = 20
MAX_ROWS = 5000


def _name(title: str, ext: str) -> str:
    product = brand.branding()["product"]
    stem = re.sub(r"[^\w\- ]+", "", (title or product)).strip()[:60] or product
    return f"{stem} {frappe.utils.today()}.{ext}"


def _business(business_code) -> str:
    if business_code and business_code != "__all__":
        return frappe.db.get_value("Connected Business", {"business_code": business_code}, "business_name") or business_code
    return "All businesses"


def _as_of() -> str:
    from command_center.www.command_center import _as_of as boot_as_of
    d = boot_as_of() or {}
    return d.get("date") or "not loaded"


def pdf_bytes(question: str, answer: str, checked=None, business_code: str | None = None,
              model: str | None = None, kind: str = "answer") -> bytes:
    """An answer or a report as a PDF: the download, and the scheduled email's attachment.

    It reads like the screen it came from: the figure cards and charts drawn as they are
    in the app (api/pdf_blocks.py), tables with numbers aligned, the opening line as the
    lead. "What it checked" stays on the screen, collapsed, and is never printed -- a
    list of lookups reads as gibberish to the people the document is for (Michael,
    18 Oct 2026). `checked` is accepted and ignored so callers need not change.
    """
    from frappe.utils.html_utils import sanitize_html
    from frappe.utils.pdf import get_pdf

    _ensure_fonts()
    html = _document_html(question, answer, business_code, model, sanitize_html,
                          frappe.utils.md_to_html, kind=kind)
    with _with_fonts():
        return get_pdf(html, pdf_options(business_code))


# The engine's settings for every PDF the app makes.
#
# dpi: wkhtmltopdf (0.12.6, patched Qt) lays a line out with each letter's width rounded
# to a whole pixel, then draws the letters at their exact widths. At its usual 96 dpi
# body text is 12 pixels high, the rounding adds up to several spaces across a line, and
# wherever one run of text meets the next -- a bold figure, a link -- the second starts
# where the layout said, not where the first ended: "totaledGHS 15.45M", "with   GHS".
# At 1200 dpi the same text is 150 pixels high and the rounding comes to a few hundredths
# of a space (measured against Manrope's own widths, 19 Oct 2026). Sizes on the page are
# unchanged; only the grid the engine lays text out on is finer. The PDF's styles use no
# letter-spacing: at this resolution the engine applies it many times over.
PDF_OPTIONS = {"page-size": "A4", "margin-top": "16mm", "margin-bottom": "18mm",
               "margin-left": "15mm", "margin-right": "15mm", "dpi": "1200",
               "footer-right": "Page [page] of [topage]", "footer-font-size": "6",
               "footer-font-name": "Manrope", "footer-spacing": "6", "encoding": "UTF-8"}
FOOTER_CHARS = 150  # what fits beside "Page X of Y" at the footer's size on A4


def pdf_options(business_code: str | None = None) -> dict:
    """PDF_OPTIONS with the vendor's line at the foot of every page, left, and "Page X of
    Y" right (command_center/branding.py). Any other PDF the platform makes -- a
    financial statement, a people report -- should be made with these."""
    line = brand.branding(business_code)["footer"]
    if len(line) > FOOTER_CHARS:
        line = line[:FOOTER_CHARS - 1].rstrip(" ·") + "…"
    return {**PDF_OPTIONS, "footer-left": line}


def _logo(name: str | None, cls: str) -> str:
    """A stored logo inside the PDF, or nothing. The PDF engine draws PNG and JPEG; a
    WebP logo is left out of PDFs (the name is printed instead) and still shown on screen."""
    if not name or not name.endswith((".png", ".jpg")):
        return ""
    uri = brand.logo_data_uri(name)
    return f'<img class="{cls}" src="{uri}" alt="">' if uri else ""


def brand_header(title: str, business_code: str | None = None, kicker: str = "",
                 subtitle: str = "", business: str | None = None,
                 period: str | None = None) -> str:
    """The top of every PDF the platform makes: the product's logo (or name) and the
    business's co-brand, then the title block -- the kind of document, its title, the
    business, the period it covers, who it was prepared for and when. `title` and
    `subtitle` are plain text; they are escaped here. `business` names whom it is for
    when that is not one business (a customer's usage statement covers several), and
    `period` replaces "Figures as at ..." when the document covers a stated period."""
    b = brand.branding(business_code)
    business = business or _business(business_code)
    client = brand.for_business_name(b, business)
    mark = _logo(b["logo_light"], "hd-logo") or f'<div class="brand">{escape_html(b["product"])}</div>'
    tag = f'<div class="hd-tag">{escape_html(b["tagline"])}</div>' if b["tagline"] else ""
    client_logo = _logo(b["client_logo"], "hd-client")
    who = frappe.utils.get_fullname(frappe.session.user)
    when = frappe.utils.format_datetime(frappe.utils.now_datetime(), "d MMMM yyyy, HH:mm")
    return (
        '<table class="hd"><tr>'
        f'<td class="hd-l">{mark}{tag}</td>'
        f'<td class="hd-r">{client_logo}<div class="hd-for">Prepared for <b>{escape_html(client)}</b></div></td>'
        '</tr></table>'
        '<div class="tb">'
        + (f'<div class="kicker">{escape_html(kicker)}</div>' if kicker else "")
        + f'<h1>{escape_html(title or "")}</h1>'
        + (f'<div class="tb-sub">{escape_html(subtitle)}</div>' if subtitle else "")
        + '<table class="tb-facts"><tr>'
        f'<td><span>Business</span>{escape_html(business)}</td>'
        f'<td><span>Period</span>{escape_html(period or "Figures as at " + _pretty_date(_as_of()))}</td>'
        f'<td><span>Requested by</span>{escape_html(who)}</td>'
        f'<td><span>Generated</span>{escape_html(when)}</td>'
        '</tr></table></div>')


def brand_footer(business_code: str | None = None, note: str = "") -> str:
    """The closing block of a PDF: `note` (escaped HTML the caller wrote), then the
    vendor's line."""
    b = brand.branding(business_code)
    return (f'<div class="ft">{note}'
            f'<div class="ft-by">{escape_html(b["footer"])}</div></div>')


def _document_html(question, answer, business_code, model, sanitize, md_to_html,
                   kind: str = "answer") -> str:
    """The PDF's HTML. Separate from get_pdf so it can be looked at in a browser."""
    report = kind == "report"
    answer = report_text.tidy(answer or "", question or "", _business(business_code),
                              report=report)
    blocks = []

    def keep(m):
        drawn = pdf_blocks.render(m.group(1).lower(), m.group(2))
        if not drawn:
            return ""
        blocks.append(drawn)
        # A paragraph of its own, so markdown leaves it alone and it is easy to swap back.
        return f"\n\nCCBLOCK{len(blocks) - 1}X\n\n"

    md = re.sub(r"```\s*followups\s*\n.*?\n\s*```", "", answer or "", flags=re.S | re.I)
    md = _md_lists(md)
    md = re.sub(r"```\s*(figures|chart)\s*\n(.*?)\n\s*```", keep, md, flags=re.S | re.I)
    # The answer is model-written markdown: rendered, then sanitised, never trusted. The
    # cards and charts are ours, built from escaped values, and go in after.
    body = sanitize(md_to_html(md))
    for i, drawn in enumerate(blocks):
        body = re.sub(rf"<p>\s*CCBLOCK{i}X\s*</p>|CCBLOCK{i}X", lambda _m, d=drawn: d, body, count=1)
    body = _polish(body)
    b = brand.branding(business_code)
    business = escape_html(_business(business_code))
    note = (f"Prepared by {escape_html(b['product'])} from {business}'s ERPNext records, using "
            f"{escape_html(model or 'the analyst')}. It reads the records the person who asked "
            f"may see and cannot change anything in ERPNext. Projections are indicative; "
            f"recommendations are for management to decide on.")
    return PDF_TEMPLATE.format(
        fonts=_font_css(),
        css=pdf_blocks.CSS,
        page_css=PAGE_CSS,
        header=brand_header(question or "", business_code,
                            kicker="Management Report" if report else "Analysis"),
        body=body,
        footer=brand_footer(business_code, note),
        doc_class="report" if report else "answer",
    )


def html_pdf(title: str, body_html: str, business_code: str | None = None,
             footer: str | None = None, kicker: str = "Financial Report",
             business: str | None = None, period: str | None = None) -> bytes:
    """A document the platform built itself (the financial statements, api/statements.py)
    as a PDF, in the answer's own branded layout: header and title block, body, footer
    and the vendor's line on every page. `body_html` is the caller's, built from escaped
    values; `title` and `footer` are plain text, escaped here."""
    from frappe.utils.pdf import get_pdf

    _ensure_fonts()
    html = PDF_TEMPLATE.format(
        fonts=_font_css(), css=pdf_blocks.CSS, page_css=PAGE_CSS,
        header=brand_header(title or "", business_code, kicker=kicker, business=business,
                            period=period),
        body=body_html,
        footer=brand_footer(business_code, escape_html(footer or "")),
        doc_class="report")
    with _with_fonts():
        return get_pdf(html, pdf_options(business_code))


def _ensure_fonts():
    """Manrope installed for the PDF engine, once per worker (install.install_pdf_fonts)."""
    if getattr(_ensure_fonts, "done", False):
        return
    from command_center.install import install_pdf_fonts

    install_pdf_fonts(quiet=True)
    _ensure_fonts.done = True


def _fontconfig_file() -> str | None:
    """A fontconfig file of our own for the PDF engine: the server's usual configuration,
    plus the app's Manrope folder.

    Biomed's fontconfig searches no home folder at all, so fonts installed in ~/.fonts
    or ~/.local/share/fonts were never seen, and wkhtmltopdf (0.12.6, patched Qt) also
    ignores fonts embedded in the page. Frappe starts wkhtmltopdf from this process, so
    pointing FONTCONFIG_FILE at this file while it runs hands it Manrope directly,
    whatever the server's own settings are. Written once per worker into the site's
    private files folder.
    """
    import os

    fonts = os.path.join(os.path.dirname(__file__), "fonts")
    if not os.path.isdir(fonts):
        return None
    folder = frappe.get_site_path("private", "command_center")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "pdf-fonts.conf")
    cache = os.path.join(folder, "fontcache")
    body = ('<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>\n'
            '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
            f"  <dir>{os.path.abspath(fonts)}</dir>\n"
            f"  <cachedir>{os.path.abspath(cache)}</cachedir>\n"
            # Unhinted outlines, as print should be. (Spacing is PDF_OPTIONS' dpi.)
            '  <match target="font">\n'
            '    <edit name="hinting" mode="assign"><bool>false</bool></edit>\n'
            '    <edit name="hintstyle" mode="assign"><const>hintnone</const></edit>\n'
            '    <edit name="antialias" mode="assign"><bool>true</bool></edit>\n'
            "  </match>\n</fontconfig>\n")
    if not os.path.exists(path) or open(path).read() != body:
        with open(path, "w") as f:
            f.write(body)
    return os.path.abspath(path)


class _with_fonts:
    """FONTCONFIG_FILE set to ours for the length of one PDF, then put back."""

    def __enter__(self):
        import os
        self.before = os.environ.get("FONTCONFIG_FILE")
        try:
            conf = _fontconfig_file()
        except Exception:
            conf = None
        if conf:
            os.environ["FONTCONFIG_FILE"] = conf
        return self

    def __exit__(self, *exc):
        import os
        if self.before is None:
            os.environ.pop("FONTCONFIG_FILE", None)
        else:
            os.environ["FONTCONFIG_FILE"] = self.before
        return False


def _font_css() -> str:
    """Manrope, the app's own typeface, embedded in the PDF (scripts/build_pdf_fonts.py).

    Embedded rather than linked: the server's PDF engine fetches nothing reliably and has
    no Manrope installed, so without this every PDF came out in DejaVu Sans -- wide,
    heavy, and dropping the space before a bold word ("totaledGHS 15.45M").
    """
    import base64
    import os

    here = os.path.join(os.path.dirname(__file__), "fonts")
    out = []
    for weight, name in ((400, "regular"), (600, "semibold"), (700, "bold")):
        path = os.path.join(here, f"manrope-{name}.ttf")
        if not os.path.exists(path):
            continue
        data = base64.b64encode(open(path, "rb").read()).decode()
        # A value put into the template, not part of it: single braces.
        out.append("@font-face{font-family:'Manrope PDF';font-weight:%d;font-style:normal;"
                   "src:url(data:font/truetype;base64,%s) format('truetype')}" % (weight, data))
    return "\n".join(out)


def _pretty_date(value: str) -> str:
    """2025-08-19 -> 19 August 2025."""
    try:
        return frappe.utils.format_date(value, "d MMMM yyyy") if re.match(r"\d{4}-\d{2}-\d{2}", str(value)) else value
    except Exception:
        return value


def _md_lists(md: str) -> str:
    """A list straight after a line of text needs a blank line before it, or the PDF's
    markdown runs the items into the paragraph (" - Draft invoices: ... - Draft orders")."""
    return re.sub(r"(?m)^(?!\s*(?:[-*+]|\d+\.)\s)(\S[^\n]*)\n(\s*(?:[-*+]|\d+\.)\s)", r"\1\n\n\2", md)


_NUMBER = re.compile(r"^\s*(?:<strong>)?\s*[-+(]?(?:GHS|USD|\$|€|£)?\s*[-+]?[\d,]+(?:\.\d+)?\s*"
                     r"(?:%|[kKMB]|days?|months?)?\)?\s*(?:</strong>)?\s*$")


_BLANK = re.compile(r"^\s*(?:—|–|-|n/a|N/A)?\s*$")


def _thousands(cell: str) -> str:
    """A bare figure of five digits or more gets its thousands separators: 1234567.5 ->
    1,234,567.5. Anything already formatted, or with words, is left as written."""
    m = re.fullmatch(r"(\s*(?:<strong>)?\s*(?:GHS\s*)?)(-?)(\d{5,})(\.\d+)?(\s*(?:</strong>)?\s*)", cell)
    if not m:
        return cell
    return f"{m.group(1)}{m.group(2)}{int(m.group(3)):,}{m.group(4) or ''}{m.group(5)}"


def _align(table: str) -> str:
    """A column whose every value is a number (or a dash) is right-aligned, heading
    included, so a heading sits over its figures rather than across the page from them."""
    rows = re.findall(r"<tr>(.*?)</tr>", table, flags=re.S)
    cells = [re.findall(r"<t([hd])([^>]*)>(.*?)</t[hd]>", r, flags=re.S) for r in rows]
    width = max((len(c) for c in cells), default=0)
    numeric = []
    for i in range(width):
        vals = [c[i][2] for c in cells if len(c) > i and c[i][0] == "d"]
        filled = [v for v in vals if not _BLANK.match(re.sub(r"<[^>]+>", "", v))]
        numeric.append(bool(filled) and all(_NUMBER.match(v) or _BLANK.match(re.sub(r"<[^>]+>", "", v))
                                            for v in vals))

    def row(r):
        i = -1

        def cell(m):
            nonlocal i
            i += 1
            tag, attrs, text = m.group(1), m.group(2), m.group(3)
            if i < len(numeric) and numeric[i]:
                attrs = re.sub(r'\s*style="[^"]*"', "", attrs) + ' class="n"'
                if tag == "d":
                    text = _thousands(text)
            return f"<t{tag}{attrs}>{text}</t{tag}>"
        return "<tr>" + re.sub(r"<t([hd])([^>]*)>(.*?)</t[hd]>", cell, r, flags=re.S) + "</tr>"

    return re.sub(r"<tr>(.*?)</tr>", lambda m: row(m.group(1)), table, flags=re.S)


def _polish(body: str) -> str:
    """Small things a well-made document does: the first paragraph is the lead, numbers
    in tables line up on the right, each recommendation stands out, the document's title
    is the only top-level heading, and a heading never ends a page on its own."""
    body = re.sub(r"<p>", '<p class="lead">', body, count=1)
    body = re.sub(r"<h1\b([^>]*)>(.*?)</h1>", r"<h2\1>\2</h2>", body, flags=re.S)
    body = re.sub(r"<table>(.*?)</table>", lambda m: f"<table>{_align(m.group(1))}</table>", body, flags=re.S)
    body = re.sub(r"<li>(\s*(?:<strong>)?\s*Recommendation)", r'<li class="rec">\1', body)
    body = re.sub(r"<p>(\s*(?:<strong>)?\s*Projection)", r'<p class="proj">\1', body)
    # The list under a Recommendations heading: numbered, set off from the text.
    body = re.sub(r"(<h[23][^>]*>\s*(?:Recommendations?|Recommended Actions?|Next Steps|Actions)\b[^<]*</h[23]>\s*)<(ol|ul)>",
                  r'\1<\2 class="recs">', body, flags=re.I)
    return _keep_with_next(body)


def _keep_with_next(body: str) -> str:
    """A heading and the paragraph (or short list or table) after it, kept on one page:
    the engine ignores page-break-after:avoid, but keeps a block whole."""
    def keep(m):
        head, nxt, tag = m.group(1), m.group(3), m.group(4)
        if tag in ("ul", "ol") and (re.search(r"<(ul|ol)\b", nxt[3:]) or nxt.count("<li") > 6):
            return m.group(0)
        if tag == "table" and nxt.count("<tr") > 12:
            return m.group(0)
        return f'<div class="keep">{head}{nxt}</div>'
    return re.sub(r"(<h([234])\b[^>]*>.*?</h\2>)\s*(<(p|ul|ol|table)\b.*?</\4>)", keep, body, flags=re.S)


@frappe.whitelist(methods=["POST"])
def answer_pdf(question: str, answer: str, checked=None, business_code: str | None = None,
               model: str | None = None, kind: str = "answer"):
    """The answer (or, with kind="report", a written report) as a PDF. The text is the one
    the analyst returned."""
    require_manager()
    kind = "report" if kind == "report" else "answer"
    frappe.local.response.filename = _name(question[:60] if question else "Answer", "pdf")
    frappe.local.response.filecontent = pdf_bytes(question, answer, checked, business_code, model,
                                                  kind=kind)
    frappe.local.response.type = "pdf"


@frappe.whitelist(methods=["POST"])
def tables_xlsx(title: str, tables, business_code: str | None = None):
    """Tables as an .xlsx, one sheet each. tables: [{name, columns: [..], rows: [[..]]}]"""
    require_manager()
    tables = frappe.parse_json(tables) if isinstance(tables, str) else (tables or [])
    sheets = []
    for i, t in enumerate(tables[:MAX_TABLES]):
        cols = [str(c) for c in (t.get("columns") or [])][:60]
        rows = [[_cell(v) for v in (r or [])][:60] for r in (t.get("rows") or [])[:MAX_ROWS]]
        sheets.append((t.get("name") or f"Table {i + 1}", cols, rows))
    _send_xlsx(title or "Tables", sheets, business_code)


@frappe.whitelist(methods=["POST"])
def records_xlsx(fact: str, filters=None, business_code: str | None = None, title: str | None = None,
                 kpi: str | None = None):
    """Every record behind a figure, up to EXPORT_CAP, in the drawer's own columns -- and,
    for a figure's drawer (kpi), its Understanding This Figure section as the first sheet."""
    require_manager()
    from command_center.api.facts import _records

    data = _records(fact, filters, business_code, limit=EXPORT_CAP, cap=EXPORT_CAP)
    cols = data.get("columns") or []
    header = [c.get("label") or c.get("key") for c in cols] + ["ERPNext link"]
    rows = [[_cell(r.get(c.get("key"))) for c in cols] + [r.get("open_url") or ""]
            for r in data.get("rows") or []]
    s = data.get("summary") or {}
    note = (f"{s.get('shown', len(rows))} of {s.get('count', len(rows))} records"
            + (" -- the export cap was reached" if s.get("count", 0) > len(rows) else ""))
    sheets = [(title or "Records", header, rows)]
    if kpi:
        from command_center.insight.build import sheet, understand
        sheets.insert(0, sheet(understand(kpi, business_code)))
    _send_xlsx(title or data.get("noun") or fact, sheets, business_code, note=note)


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    # A figure written as text in a table ("GHS 9,177,568.91", "73.8%") is a number to
    # whoever opens the sheet; give Excel the number.
    m = re.fullmatch(r"(?:GHS\s*)?(-?[\d,]+(?:\.\d+)?)\s*(%)?", s)
    if m:
        try:
            n = float(m.group(1).replace(",", ""))
            return n / 100 if m.group(2) else n
        except ValueError:
            pass
    return s


def brand_rows_head(title: str, business_code, note: str | None = None,
                    business: str | None = None, period: str | None = None) -> list:
    """The rows above a sheet's table: its title, then "<product> · <business> · figures
    as at ... · exported by ... on ...", then a blank row (the table's headings are row 4).
    For any other workbook the platform makes, so every sheet starts the same way."""
    b = brand.branding(business_code)
    business = business or _business(business_code)
    return [[title],
            [f"{b['product']} · {brand.for_business_name(b, business)} · "
             f"{period or 'figures as at ' + _as_of()} · "
             f"exported by {frappe.utils.get_fullname(frappe.session.user)} on "
             f"{frappe.utils.format_datetime(frappe.utils.now_datetime(), 'd MMM yyyy, HH:mm')}"
             + (f" · {note}" if note else "")],
            []]


def brand_rows_foot(business_code) -> list:
    """The rows under a sheet's table: a blank row, then "Prepared with <product> by
    <company> · <email> · <phone> · <website>"."""
    return [[], [brand.branding(business_code)["prepared"]]]


def _send_xlsx(title: str, sheets: list, business_code, note: str | None = None,
               business: str | None = None, period: str | None = None):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.creator = brand.branding(business_code)["product"]
    used = set()
    for name, cols, rows in sheets or [("Empty", [], [])]:
        sheet = re.sub(r"[\[\]\*\?/\\:]", " ", str(name))[:28].strip() or "Sheet"
        base, k = sheet, 2
        while sheet in used:
            sheet = f"{base[:25]} {k}"
            k += 1
        used.add(sheet)
        ws = wb.create_sheet(sheet)
        for row in brand_rows_head(title, business_code, note, business, period):
            ws.append(row)
        ws["A1"].font = Font(bold=True, size=13)
        ws["A2"].font = Font(size=9, color="646973")
        ws.append(cols)
        for c in ws[4]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append(r)
        for row in brand_rows_foot(business_code):
            ws.append(row)
        ws.cell(row=ws.max_row, column=1).font = Font(size=9, italic=True, color="7a808a")
        ws.freeze_panes = "A5"
        # The same lines when the sheet is printed.
        ws.oddHeader.left.text = brand.branding(business_code)["product"]
        ws.oddHeader.right.text = business or _business(business_code)
        ws.oddFooter.left.text = brand.branding(business_code)["prepared"][:250]
        ws.oddFooter.right.text = "Page &P of &N"
        for i, col in enumerate(cols, start=1):
            width = max([len(str(col))] + [len(str(r[i - 1])) for r in rows[:200] if len(r) >= i])
            ws.column_dimensions[get_column_letter(i)].width = min(max(10, width + 2), 60)
    buf = io.BytesIO()
    wb.save(buf)
    frappe.local.response.filename = _name(title, "xlsx")
    frappe.local.response.filecontent = buf.getvalue()
    frappe.local.response.type = "binary"


# The document's typography, one family throughout (the charts' SVG text included), on
# one scale: 18pt title, 12pt sections, 10pt sub-sections, 9pt text, 8pt tables, 7pt notes.
PAGE_CSS = """
@page{size:A4}
body{font-family:'Manrope PDF','Manrope','Helvetica Neue',Helvetica,Arial,'Liberation Sans',sans-serif;
 color:#111317;font-size:9pt;line-height:1.6;margin:0;-webkit-font-smoothing:antialiased}
svg text{font-family:'Manrope PDF','Manrope','Helvetica Neue',Helvetica,Arial,sans-serif}
table.hd{width:100%;border-collapse:collapse;margin:0 0 14px}
table.hd td{border:0;padding:0;vertical-align:middle;background:none}
.hd-logo{height:26px;max-width:200px;display:block}
.hd-client{height:22px;max-width:150px;display:block;margin:0 0 3px auto}
.brand{font-size:10pt;font-weight:700;color:#2443e8;line-height:1.2}
.hd-tag{font-size:7pt;color:#646973;margin-top:2px}
.hd-r{text-align:right}
.hd-for{font-size:7pt;color:#646973}
.hd-for b{color:#24272d;font-weight:600}
.tb{border-top:2px solid #2443e8;border-bottom:1px solid #e3e5ea;padding:12px 0 10px;margin:0 0 20px;
 page-break-inside:avoid}
.kicker{font-size:7pt;font-weight:700;color:#2443e8;text-transform:uppercase;margin-bottom:4px}
h1{font-size:18pt;font-weight:700;line-height:1.2;margin:0 0 6px}
.tb-sub{font-size:9pt;color:#3b3f47;margin-bottom:6px}
table.tb-facts{width:100%;border-collapse:collapse;margin:8px 0 0;font-size:7.5pt}
table.tb-facts td{border:0;padding:0 12px 0 0;background:none;vertical-align:top;color:#24272d;width:25%}
table.tb-facts td span{display:block;font-size:6.5pt;font-weight:600;color:#8a8f99;text-transform:uppercase}
p{margin:0 0 9px}
p.lead{font-size:10pt;line-height:1.55;color:#24272d;margin-bottom:12px}
h2{font-size:12pt;font-weight:700;line-height:1.3;margin:20px 0 7px;padding-top:2px;page-break-after:avoid;color:#111317}
h3{font-size:10pt;font-weight:700;margin:16px 0 5px;page-break-after:avoid}
h4{font-size:9pt;font-weight:600;margin:12px 0 4px;page-break-after:avoid}
.keep{page-break-inside:avoid}
hr{border:0;border-top:1px solid #e3e5ea;margin:18px 0}
ul,ol{margin:4px 0 12px;padding-left:18px}
li{margin:4px 0}
li.rec{list-style:none;margin:7px 0 7px -18px;padding:8px 12px;border-left:3px solid #2443e8;background:#f4f6fe;
 border-radius:0 8px 8px 0}
ol.recs,ul.recs{padding-left:0;margin-left:0;list-style:none;counter-reset:rec}
ol.recs li,ul.recs li{position:relative;margin:0 0 7px;padding:8px 12px 8px 34px;border-left:3px solid #2443e8;
 background:#f4f6fe;border-radius:0 8px 8px 0;page-break-inside:avoid}
ol.recs li:before{counter-increment:rec;content:counter(rec);position:absolute;left:11px;top:8px;
 font-weight:700;color:#2443e8}
ul.recs li:before{content:"";position:absolute;left:13px;top:14px;width:6px;height:6px;border-radius:3px;
 background:#2443e8}
p.proj{padding:9px 13px;border-left:3px solid #a85a0a;background:#fbf5ec;border-radius:0 8px 8px 0}
strong,b{font-weight:700}
em{color:#3b3f47}
table{border-collapse:collapse;width:100%;margin:8px 0 14px;font-size:8pt;page-break-inside:auto}
tr{page-break-inside:avoid}
thead{display:table-header-group}
th{text-align:left;color:#24272d;font-weight:600;background:#eef0f4;border-bottom:1.5px solid #c9cdd5;padding:7px 8px;
 font-size:7.5pt}
td{border-bottom:1px solid #eceef1;padding:6px 8px;vertical-align:top}
td.n,th.n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
th.n{white-space:normal}
tbody tr:nth-child(even) td{background:#f8f9fb}
code{font-family:Menlo,Consolas,monospace;font-size:8.5pt}
.ft{margin-top:26px;border-top:1px solid #e3e5ea;padding-top:9px;font-size:6.5pt;color:#8a8f99;line-height:1.55;
 page-break-inside:avoid}
.ft-by{margin-top:5px;color:#646973;font-weight:600}
"""

PDF_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
{fonts}
{page_css}
{css}
</style></head><body class="{doc_class}">
{header}
{body}
{footer}
</body></html>"""


@frappe.whitelist()
def pdf_diagnostics():
    """What the server's PDF engine has to work with -- System Managers only, reads only.

    Built to find out why Biomed's PDFs came out in DejaVu Sans: which wkhtmltopdf, which
    home folder the workers run as, whether the Manrope files are installed there, and
    what fontconfig answers when asked for Manrope.
    """
    import os
    import shutil
    import subprocess

    if "System Manager" not in frappe.get_roles():
        frappe.throw("System Managers only.", frappe.PermissionError)

    def run(*cmd):
        if not shutil.which(cmd[0]):
            return f"{cmd[0]} not found"
        try:
            r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=20)
            return (r.stdout or r.stderr).strip()[:1500]
        except Exception as e:
            return f"failed: {e}"

    home = os.path.expanduser("~")
    folder = os.path.join(home, ".fonts", "command_center")
    _ensure_fonts()
    out = {
        "wkhtmltopdf": run("wkhtmltopdf", "--version"),
        "home": home,
        "installed": sorted(os.listdir(folder)) if os.path.isdir(folder) else "folder missing",
        "fc_match": run("fc-match", "Manrope"),
        "fc_list": run("fc-list", ":family=Manrope", "family", "style", "file"),
        "bundled": sorted(os.listdir(os.path.join(os.path.dirname(__file__), "fonts"))),
    }
    try:
        out["pdf_generator"] = frappe.db.get_single_value("Print Settings", "pdf_generator")
    except Exception as e:
        out["pdf_generator"] = f"n/a ({type(e).__name__})"

    # The decisive test: the same tiny page three ways, through Frappe's own get_pdf, and
    # which font each PDF actually used.
    import base64
    from frappe.utils.pdf import get_pdf

    ttf = base64.b64encode(open(os.path.join(os.path.dirname(__file__), "fonts", "manrope-bold.ttf"),
                                "rb").read()).decode()
    tests = {
        "system": "body{font-family:'Manrope';font-weight:700}",
        "embedded": ("@font-face{font-family:'MPDF';font-weight:700;src:url(data:font/truetype;base64,%s) "
                     "format('truetype')} body{font-family:'MPDF';font-weight:700}" % ttf),
        "embedded_x": ("@font-face{font-family:'MPDF2';src:url(data:application/x-font-ttf;base64,%s) "
                       "format('truetype')} body{font-family:'MPDF2'}" % ttf),
    }
    out["fc_scan"] = run("fc-scan", "--format", "%{family}|%{style}|%{weight}\n",
                         os.path.join(os.path.dirname(__file__), "fonts", "manrope-regular.ttf"))
    with _with_fonts():
        out["our_conf"] = os.environ.get("FONTCONFIG_FILE")
        out["fc_match_ours"] = run("fc-match", "Manrope:bold")
        try:
            pdf = get_pdf("<html><head><style>body{font-family:'Manrope';font-weight:700}</style>"
                          "</head><body><p>Executive Summary 123</p></body></html>")
            import re as _re
            out["test_ours"] = sorted({x.decode() for x in _re.findall(rb"/BaseFont\s*/([A-Za-z0-9+_-]+)", pdf)})
        except Exception as e:
            out["test_ours"] = f"failed: {e}"[:300]
    for name, css in tests.items():
        try:
            pdf = get_pdf(f"<html><head><style>{css}</style></head><body><p>Executive Summary 123</p></body></html>")
            import re as _re
            out[f"test_{name}"] = sorted(set(_re.findall(rb"/BaseFont\s*/([A-Za-z0-9+_-]+)", pdf)))
            out[f"test_{name}"] = [x.decode() for x in out[f"test_{name}"]]
        except Exception as e:
            out[f"test_{name}"] = f"failed: {e}"[:300]
    return out


@frappe.whitelist(methods=["POST"])
def pdf_probe(answer: str):
    """The same answer drawn several ways, to find the setting that keeps the spaces
    around bold text -- System Managers only, reads only, makes nothing.

    Biomed's wkhtmltopdf set the first Manrope reports with spaces lost or doubled at
    the edges of bold words ("totaledGHS 15.45M"); see PDF_OPTIONS. The variants compare
    resolutions. The PDFs come back with the app's commit and the engine's font file.
    """
    import base64
    import os
    import subprocess

    from frappe.utils.html_utils import sanitize_html
    from frappe.utils.pdf import get_pdf

    if "System Manager" not in frappe.get_roles():
        frappe.throw("System Managers only.", frappe.PermissionError)
    _ensure_fonts()
    base = _document_html("Spacing probe", answer, None, None, sanitize_html, frappe.utils.md_to_html)
    variants = {
        "a_now": (base, {}),
        "b_dpi2400": (base, {"dpi": "2400"}),
        "c_dpi600": (base, {"dpi": "600"}),
        "d_dpi96": (base, {"dpi": "96"}),
    }
    out = {}
    try:
        app = os.path.dirname(frappe.get_app_path("command_center"))
        out["commit"] = subprocess.run(["git", "-C", app, "log", "-1", "--format=%h %s"],
                                       capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as e:
        out["commit"] = f"n/a ({e})"
    with _with_fonts():
        conf = os.environ.get("FONTCONFIG_FILE")
        out["conf"] = open(conf).read() if conf and os.path.exists(conf) else None
        for name, (html, extra) in variants.items():
            try:
                out[name] = base64.b64encode(get_pdf(html, {**PDF_OPTIONS, **extra})).decode()
            except Exception as e:
                out[name] = f"failed: {e}"[:300]
    return out
