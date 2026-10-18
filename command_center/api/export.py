"""Taking an answer, a table or the records behind a figure out of the platform.

Three downloads, all management-only, all reads -- nothing here creates a record.
Files are streamed back as the response; no File document is written to the site.

    answer_pdf     an Ask AI answer as a PDF: Gigmann's header, the question, the
                   answer, what it checked, as-of date, who generated it and when
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

from command_center.api import pdf_blocks
from command_center.api.businesses import require_manager

EXPORT_CAP = 20000
MAX_TABLES = 20
MAX_ROWS = 5000


def _name(title: str, ext: str) -> str:
    stem = re.sub(r"[^\w\- ]+", "", (title or "AI Business Intelligence")).strip()[:60] or "AI Business Intelligence"
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
              model: str | None = None) -> bytes:
    """An answer or a report as a PDF: the download, and the scheduled email's attachment.

    It reads like the screen it came from: the figure cards and charts drawn as they are
    in the app (api/pdf_blocks.py), tables with numbers aligned, the opening line as the
    lead. "What it checked" stays on the screen, collapsed, and is never printed -- a
    list of lookups reads as gibberish to the people the document is for (Michael,
    18 Oct 2026). `checked` is accepted and ignored so callers need not change.
    """
    from frappe.utils.html_utils import sanitize_html
    from frappe.utils.pdf import get_pdf

    html = _document_html(question, answer, business_code, model, sanitize_html,
                          frappe.utils.md_to_html)
    return get_pdf(html, {"page-size": "A4", "margin-top": "16mm", "margin-bottom": "18mm",
                          "margin-left": "15mm", "margin-right": "15mm",
                          "footer-center": "Page [page] of [topage]", "footer-font-size": "7",
                          "footer-spacing": "6", "encoding": "UTF-8"})


def _document_html(question, answer, business_code, model, sanitize, md_to_html) -> str:
    """The PDF's HTML. Separate from get_pdf so it can be looked at in a browser."""
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
    who = frappe.utils.get_fullname(frappe.session.user)
    when = frappe.utils.format_datetime(frappe.utils.now_datetime(), "d MMMM yyyy, HH:mm")
    return PDF_TEMPLATE.format(
        fonts=_font_css(),
        css=pdf_blocks.CSS,
        business=escape_html(_business(business_code)),
        question=escape_html(question or ""),
        body=body,
        as_of=escape_html(_pretty_date(_as_of())),
        who=escape_html(who),
        when=escape_html(when),
        model=escape_html(model or "the analyst"),
    )


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
            return f"<t{tag}{attrs}>{text}</t{tag}>"
        return "<tr>" + re.sub(r"<t([hd])([^>]*)>(.*?)</t[hd]>", cell, r, flags=re.S) + "</tr>"

    return re.sub(r"<tr>(.*?)</tr>", lambda m: row(m.group(1)), table, flags=re.S)


def _polish(body: str) -> str:
    """Small things a well-made document does: the first paragraph is the lead, numbers
    in tables line up on the right, and each recommendation stands out."""
    body = re.sub(r"<p>", '<p class="lead">', body, count=1)
    body = re.sub(r"<table>(.*?)</table>", lambda m: f"<table>{_align(m.group(1))}</table>", body, flags=re.S)
    body = re.sub(r"<li>(\s*(?:<strong>)?\s*Recommendation)", r'<li class="rec">\1', body)
    body = re.sub(r"<p>(\s*(?:<strong>)?\s*Projection)", r'<p class="proj">\1', body)
    return body


@frappe.whitelist(methods=["POST"])
def answer_pdf(question: str, answer: str, checked=None, business_code: str | None = None,
               model: str | None = None):
    """The answer as a PDF. The answer text is the one the analyst returned."""
    require_manager()
    frappe.local.response.filename = _name(question[:60] if question else "Answer", "pdf")
    frappe.local.response.filecontent = pdf_bytes(question, answer, checked, business_code, model)
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
def records_xlsx(fact: str, filters=None, business_code: str | None = None, title: str | None = None):
    """Every record behind a figure, up to EXPORT_CAP, in the drawer's own columns."""
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
    _send_xlsx(title or data.get("noun") or fact, [(title or "Records", header, rows)],
               business_code, note=note)


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


def _send_xlsx(title: str, sheets: list, business_code, note: str | None = None):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb.active)
    used = set()
    for name, cols, rows in sheets or [("Empty", [], [])]:
        sheet = re.sub(r"[\[\]\*\?/\\:]", " ", str(name))[:28].strip() or "Sheet"
        base, k = sheet, 2
        while sheet in used:
            sheet = f"{base[:25]} {k}"
            k += 1
        used.add(sheet)
        ws = wb.create_sheet(sheet)
        ws.append([title])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([f"{_business(business_code)} · figures as at {_as_of()} · exported by "
                   f"{frappe.utils.get_fullname(frappe.session.user)} on "
                   f"{frappe.utils.format_datetime(frappe.utils.now_datetime(), 'd MMM yyyy, HH:mm')}"
                   + (f" · {note}" if note else "")])
        ws.append([])
        ws.append(cols)
        for c in ws[4]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append(r)
        ws.freeze_panes = "A5"
        for i, col in enumerate(cols, start=1):
            width = max([len(str(col))] + [len(str(r[i - 1])) for r in rows[:200] if len(r) >= i])
            ws.column_dimensions[get_column_letter(i)].width = min(max(10, width + 2), 60)
    buf = io.BytesIO()
    wb.save(buf)
    frappe.local.response.filename = _name(title, "xlsx")
    frappe.local.response.filecontent = buf.getvalue()
    frappe.local.response.type = "binary"


PDF_TEMPLATE = """<!doctype html><html><head><meta charset="utf-8"><style>
{fonts}
@page{{size:A4}}
body{{font-family:'Manrope PDF',Manrope,'Helvetica Neue',Helvetica,Arial,'Liberation Sans',sans-serif;
 color:#111317;font-size:10pt;line-height:1.6;margin:0;-webkit-font-smoothing:antialiased}}
.hd{{border-bottom:1px solid #e3e5ea;padding-bottom:10px;margin-bottom:22px}}
.hd td{{border:0;padding:0;vertical-align:bottom;background:none}}
.brand{{font-size:8.5pt;font-weight:700;color:#2443e8}}
.biz{{font-size:8.5pt;color:#646973;margin-top:2px}}
.meta{{font-size:8.5pt;color:#646973;text-align:right;line-height:1.5}}
h1{{font-size:22pt;font-weight:700;letter-spacing:-.025em;line-height:1.15;margin:0 0 10px}}
p{{margin:0 0 9px}}
p.lead{{font-size:11.5pt;line-height:1.55;color:#24272d;margin-bottom:14px}}
h2{{font-size:13pt;font-weight:700;margin:24px 0 8px;letter-spacing:-.015em;page-break-after:avoid}}
h3{{font-size:11.5pt;font-weight:700;margin:20px 0 6px;letter-spacing:-.01em;page-break-after:avoid}}
h4{{font-size:10.5pt;font-weight:600;margin:14px 0 4px}}
hr{{border:0;border-top:1px solid #e3e5ea;margin:18px 0}}
ul,ol{{margin:4px 0 12px;padding-left:18px}}
li{{margin:4px 0}}
li.rec{{list-style:none;margin:8px 0 8px -18px;padding:9px 13px;border-left:3px solid #2443e8;background:#f4f6fe;
 border-radius:0 8px 8px 0}}
p.proj{{padding:9px 13px;border-left:3px solid #a85a0a;background:#fbf5ec;border-radius:0 8px 8px 0}}
strong,b{{font-weight:700}}
em{{color:#3b3f47}}
table{{border-collapse:collapse;width:100%;margin:10px 0 16px;font-size:9pt;page-break-inside:auto}}
tr{{page-break-inside:avoid}}
th{{text-align:left;color:#3b3f47;font-weight:600;background:#f2f3f5;border-bottom:1px solid #d9dce2;padding:8px 9px;
 font-size:8.5pt}}
td{{border-bottom:1px solid #eceef1;padding:7px 9px;vertical-align:top}}
td.n,th.n{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
th.n{{white-space:normal}}
tbody tr:nth-child(even) td{{background:#fafbfc}}
code{{font-family:Menlo,Consolas,monospace;font-size:8.5pt}}
.ft{{margin-top:30px;border-top:1px solid #e3e5ea;padding-top:10px;font-size:7.5pt;color:#8a8f99;line-height:1.55}}
{css}
</style></head><body>
<table class="hd" style="width:100%;border-collapse:collapse"><tr>
<td><div class="brand">AI Business Intelligence</div><div class="biz">{business}</div></td>
<td class="meta">Figures as at {as_of}<br>Prepared for {who} · {when}</td></tr></table>
<h1>{question}</h1>
{body}
<div class="ft">Prepared by AI Business Intelligence from {business}'s ERPNext records, using {model}.
It reads the records the person who asked may see and cannot change anything in ERPNext.
Projections are indicative; recommendations are for management to decide on.</div>
</body></html>"""
