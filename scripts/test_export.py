"""The exports, tested without a site.

    python3 scripts/test_export.py

Frappe is stood in for, so what is under test is api/export.py's own work: that a
workbook opens, has one sheet per table with unique, legal names, carries the header
block, and gives Excel numbers rather than text for figures; that the PDF template
fills without a stray brace and escapes the question; and that the model's markdown is
sanitised before it reaches the PDF. Frappe's own PDF engine and md_to_html are the
site's, and are exercised there.
"""

from __future__ import annotations

import io
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

frappe = types.ModuleType("frappe")
frappe.local = types.SimpleNamespace(response=types.SimpleNamespace())
frappe.session = types.SimpleNamespace(user="kofi@gigmann.test")
frappe.whitelist = lambda **k: (lambda f: f)
frappe.parse_json = lambda s: __import__("json").loads(s)
frappe.db = types.SimpleNamespace(get_value=lambda *a, **k: "Gigmann Medical Supplies Ltd")
frappe.utils = types.SimpleNamespace(
    today=lambda: "2026-10-18", get_fullname=lambda u: "Kofi Mensah",
    now_datetime=lambda: None, format_datetime=lambda d, f=None: "18 Oct 2026, 09:00",
    escape_html=lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
    md_to_html=lambda md: f"<p>{md}</p><script>alert(1)</script>")
sys.modules["frappe"] = frappe
sys.modules["frappe.utils"] = frappe.utils
html_utils = types.ModuleType("frappe.utils.html_utils")
html_utils.sanitize_html = lambda h: h.replace("<script>alert(1)</script>", "")
sys.modules["frappe.utils.html_utils"] = html_utils
pdf = types.ModuleType("frappe.utils.pdf")
pdf.get_pdf = lambda html, options=None: html.encode()
sys.modules["frappe.utils.pdf"] = pdf
biz = types.ModuleType("command_center.api.businesses")
biz.require_manager = lambda: None
sys.modules["command_center.api.businesses"] = biz
www = types.ModuleType("command_center.www.command_center")
www._as_of = lambda: {"date": "2025-08-19"}
sys.modules["command_center.www.command_center"] = www

from openpyxl import load_workbook  # noqa: E402

from command_center.api import export
export._ensure_fonts.done = True  # never install fonts into the home folder of whoever runs the tests  # noqa: E402

passed = failed = 0


def check(ok, what):
    global passed, failed
    passed += bool(ok)
    failed += not ok
    if not ok:
        print("FAIL:", what)


# Tables to Excel
export.tables_xlsx("Who owes us", [
    {"name": "Largest balances", "columns": ["Customer", "Owed (GHS)", "Share"],
     "rows": [["UBUNTU", "GHS 636,675.00", "6.9%"], ["A.S Hospitex", "541,841", "5.9%"]]},
    {"name": "Largest balances", "columns": ["A"], "rows": [["x"]]},
    {"name": "Bad/name:[x]?", "columns": ["A"], "rows": [["y"]]},
], "GIGMANN")
r = frappe.local.response
wb = load_workbook(io.BytesIO(r.filecontent))
check(r.type == "binary" and r.filename.endswith(".xlsx"), "an xlsx download")
check(len(wb.sheetnames) == 3 and len(set(wb.sheetnames)) == 3, "one sheet per table, names unique")
check(all(not set(n) & set("[]*?/\\:") for n in wb.sheetnames), "sheet names are legal")
ws = wb[wb.sheetnames[0]]
check(ws["A1"].value == "Who owes us" and "figures as at 2025-08-19" in ws["A2"].value,
      "title and the as-of header block")
check(ws["B5"].value == 636675.0 and abs(ws["C5"].value - 0.069) < 1e-9,
      "figures arrive as numbers, percentages as fractions")
check(ws["A5"].value == "UBUNTU", "text stays text")

# Answer to PDF
export.answer_pdf("Who owes <us>?", "**GHS 9.18M** owed", ["get_figures({})"], "GIGMANN",
                  "gemini-2.5-flash")
r = frappe.local.response
html = r.filecontent.decode()
check(r.type == "pdf" and r.filename.endswith(".pdf"), "a pdf download")
check("Who owes &lt;us&gt;?" in html, "the question is escaped")
check("<script>" not in html, "the model's markdown is sanitised")
check("Figures as at 2025-08-19" in html and "Kofi Mensah" in html, "the header says as-of and who")
check("get_figures" not in html and "What it checked" not in html,
      "what it checked stays on the screen and never reaches the PDF")
check("cannot change anything" in html, "the PDF states the boundary")

# Figures and charts are drawn on paper as on the screen, never dropped or printed raw.
md = ('Lead.\n\n```figures\n[{"label": "Owed", "value": "GHS 9.18M", "note": "806", "tone": "bad"}]\n```\n\n'
      '```chart\n{"type": "bar", "title": "Spend", "unit": "GHS", "labels": ["A", "B"], '
      '"series": [{"name": "Spend", "values": [10, 5]}]}\n```\n\n'
      '```chart\n{"type": "line", "labels": ["Jan", "Feb"], "series": [{"name": "S", "values": [1, 2]}]}\n```\n\n'
      '```chart\n{"type": "donut", "labels": ["X", "Y"], "series": [{"name": "S", "values": [3, 1]}]}\n```\n\n'
      '```chart\nnot json\n```\n\n```followups\n["Next?"]\n```\n\n'
      '| Who | Owed |\n|---|---|\n| UBUNTU | 636,675 |\n\n- **Recommendation:** Call them.')
export.answer_pdf("Report", md, [], "GIGMANN", "m")
doc = frappe.local.response.filecontent.decode()
check('class="figs"' in doc and "GHS 9.18M" in doc and "#c2392f" in doc,
      "a figures block becomes cards, in the tone's colour")
check('class="bars"' in doc and "Spend" in doc, "a bar chart is drawn as bars")
check(doc.count("<svg") == 2 and "polyline" in doc and "<path" in doc, "line and donut are drawn as SVG")
check("not json" not in doc and "```" not in doc and "CCBLOCK" not in doc,
      "a block that does not parse is dropped, not printed raw")
check("Next?" not in doc, "follow-up suggestions are left off paper")
check("font-family:'Manrope PDF'" in doc and "base64," in doc,
      "the app's typeface, Manrope, is embedded in the PDF")
check(export._md_lists("Items:\n- one\n- two") == "Items:\n\n- one\n- two",
      "a list straight after a line of text gets the blank line it needs")
_pol = export._polish('<p>Lead</p><p>More</p><table><thead><tr><th>Who</th><th>Owed</th><th>Band</th>'
                      '<th>Share</th></tr></thead><tbody><tr><td>UBUNTU</td><td>636,675</td><td>GHS 9.18M</td>'
                      '<td>73.8%</td></tr><tr><td>HAIRASH</td><td>—</td><td>GHS 0.74M</td><td>8.0%</td></tr>'
                      '</tbody></table><ul><li><strong>Recommendation:</strong> Call.</li></ul>')
check('<td class="n">636,675</td>' in _pol and '<td class="n">—</td>' in _pol
      and '<th class="n">Owed</th>' in _pol and "<td>UBUNTU</td>" in _pol and "<th>Who</th>" in _pol,
      "a column of numbers lines up on the right, heading and dashes included; words do not")
check('<li class="rec">' in _pol and _pol.count('class="lead"') == 1,
      "recommendations stand out; only the first paragraph is the lead")
check("<script" not in export.pdf_blocks.figures([{"label": "<script>x</script>", "value": "1"}]),
      "a card's text is escaped")

# The newer chart types are drawn on paper too, checked as strictly as on the screen.
_pb = export.pdf_blocks
_two = [{"name": "A", "values": [1, 2]}, {"name": "B", "values": [3, 4]}]
_ok = {
    "stacked": {"type": "stacked", "title": "Mix", "unit": "GHS", "labels": ["Jan", "Feb"], "series": _two},
    "grouped": {"type": "grouped", "labels": ["Accra", "Kumasi"], "series": _two},
    "combo": {"type": "combo", "unit": "GHS", "unit2": "%", "labels": ["Jan", "Feb"], "series": _two},
    "hbar": {"type": "hbar", "unit": "GHS", "labels": ["Small Ltd", "UBUNTU Medical Supplies Company"],
             "series": [{"name": "Owed", "values": [10, 636675]}]},
    "scatter": {"type": "scatter", "unit": "GHS", "unit2": "days", "labels": ["A", "B"], "series": _two},
}
for _k, _spec in _ok.items():
    _out = _pb.chart(_spec)
    check(_out.startswith('<div class="ch">') and ("<svg" in _out or 'class="bars hb"' in _out),
          f"{_k}: a valid block is drawn in the PDF")
    for _what, _mut in (("a value missing", lambda s: s["series"][0]["values"].pop()),
                        ("text for a number", lambda s: s["series"][0]["values"].__setitem__(0, "1")),
                        ("a null", lambda s: s["series"][0]["values"].__setitem__(0, None)),
                        ("true for a number", lambda s: s["series"][0]["values"].__setitem__(0, True)),
                        ("too many series", lambda s: s["series"].extend([{"values": [1, 2]}] * 4)),
                        ("no labels", lambda s: s.__setitem__("labels", []))):
        _bad = __import__("json").loads(__import__("json").dumps(_spec))
        _mut(_bad)
        check(_pb.chart(_bad) == "", f"{_k}: {_what} -- not drawn")
check(_pb.chart({"type": "stacked", "labels": ["A"], "series": [{"values": [-1]}]}) == "",
      "stacked refuses a negative part on paper too")
check(_pb.chart({"type": "combo", "labels": ["A"], "series": [{"values": [1]}]}) == "", "combo needs two series")
_hb = _pb.chart(_ok["hbar"])
check(_hb.index("UBUNTU") < _hb.index("Small Ltd") and '<td class="hb-r">1</td>' in _hb,
      "hbar is ranked largest first, numbered")
_st = _pb.chart({"type": "stacked", "labels": ["A", "B"], "series": [{"values": [5, 0]}, {"values": [0, 3]}]})
check(_st.count("<rect") == 2, "a zero part draws nothing on paper either")
_cap = _pb.chart({"type": "stacked", "labels": [f"M{i}" for i in range(30)], "series": [{"values": [1] * 30}]})
check(_cap.count("<rect") == 24 and "Showing the first 24 of 30." in _cap, "capped at 24 columns, and said")
check(_pb.scale(0, 9177568)["lo"] == 0 and _pb.scale(0, 9177568)["hi"] >= 9177568
      and 0 in _pb.scale(-40, 100)["ticks"], "PDF axes include zero")
check("<script" not in _pb.chart({"type": "hbar", "labels": ["<script>x</script>"], "series": [{"values": [1]}]}),
      "a label is escaped")
# A drawing that fails says its figures as a table; nothing raised reaches the PDF.
_orig = _pb._columns
_pb._columns = lambda m: 1 / 0
_fb = _pb.chart(_ok["grouped"])
_pb._columns = _orig
check("<table>" in _fb and "Accra" in _fb and "<svg" not in _fb, "a chart that cannot be drawn becomes a table")
_orig_chart = _pb.chart
_pb.chart = lambda spec: 1 / 0
check(_pb.render("chart", '{"type": "bar"}') == "", "a block that raises is left out of the PDF, never fatal")
_pb.chart = _orig_chart
_md2 = "Lead.\n\n" + "\n\n".join(f"```chart\n{__import__('json').dumps(v)}\n```" for v in _ok.values())
export.answer_pdf("Report", _md2, [], "GIGMANN", "m")
_doc2 = frappe.local.response.filecontent.decode()
check(_doc2.count('<div class="ch">') == 5 and "```" not in _doc2 and "CCBLOCK" not in _doc2,
      "every new chart type reaches the answer PDF")

# Every chart type of 2026 is drawn on paper too -- static SVG in the screen's palette --
# checked as strictly as on the screen, its text escaped, never breaking the PDF.
_L3 = ["Jan", "Feb", "Mar"]
_s2 = [{"name": "A", "values": [5.0, 7, 3]}, {"name": "B", "values": [2, 4, 6]}]
_new = {
    "pie": {"type": "pie", "title": "Sales by branch", "unit": "GHS", "labels": ["Accra", "Kumasi"],
            "series": [{"name": "Sales", "values": [60, 40]}]},
    "rose": {"type": "rose", "labels": ["A", "B", "C"], "series": [{"values": [9, 4, 1]}]},
    "area": {"type": "area", "unit": "GHS", "labels": _L3, "series": [_s2[0]]},
    "stacked_area": {"type": "stacked_area", "labels": _L3, "series": _s2},
    "percentage": {"type": "percentage", "labels": _L3, "series": _s2},
    "waterfall": {"type": "waterfall", "unit": "GHS", "labels": ["Opening", "In", "Out", "Closing"],
                  "series": [{"values": [100, 50, -30, 120]}]},
    "funnel": {"type": "funnel", "labels": ["Enquiries", "Quotes", "Orders"], "series": [{"values": [100, 40, 10]}]},
    "gauge": {"type": "gauge", "title": "Collected inside 90 days", "unit": "%", "value": 26.2, "target": 80},
    "heatmap": {"type": "heatmap", "labels": _L3, "series": _s2},
    "treemap": {"type": "treemap", "unit": "GHS", "items": [
        {"name": "Supplier A", "children": [{"name": "Drugs", "value": 60}, {"name": "Devices", "value": 30}]},
        {"name": "Supplier B", "value": 50}, {"name": "Supplier C", "value": 20}]},
    "radar": {"type": "radar", "unit": "%", "labels": ["Paid", "Delivered", "Paperwork"],
              "series": [{"name": "Now", "values": [26, 91, 99]}]},
    "bubble": {"type": "bubble", "labels": _L3, "series": _s2 + [{"name": "Size", "values": [1, 4, 9]}]},
}
check(set(_new) | set(_ok) | {"bar", "line", "donut"} == set(_pb.STRICT) | {"bar", "line", "donut"},
      "every strict chart type has a PDF check")
for _k, _spec in _new.items():
    _out = _pb.chart(_spec)
    check(_out.startswith('<div class="ch">') and "<svg" in _out and "<table><thead>" not in _out,
          f"{_k}: drawn in the PDF as a picture, not a fallback table")
    if _k in ("gauge", "treemap"):
        continue
    for _what, _mut in (("a value missing", lambda s: s["series"][0]["values"].pop()),
                        ("text for a number", lambda s: s["series"][0]["values"].__setitem__(0, "1")),
                        ("a null", lambda s: s["series"][0]["values"].__setitem__(0, None)),
                        ("no labels", lambda s: s.__setitem__("labels", []))):
        _bad = __import__("json").loads(__import__("json").dumps(_spec))
        _mut(_bad)
        check(_pb.chart(_bad) == "", f"{_k}: {_what} -- not drawn")
for _k in ("pie", "rose", "stacked_area", "percentage", "funnel", "radar"):
    _neg = __import__("json").loads(__import__("json").dumps(_new[_k]))
    _neg["series"][0]["values"][0] = -1
    check(_pb.chart(_neg) == "", f"{_k} refuses a negative value on paper")
check(_pb.chart({**_new["waterfall"], "series": [{"values": [100, 50, -30, 125]}]}) == "",
      "a waterfall that does not add up is not drawn on paper")
_wf = _pb.chart(_new["waterfall"])
check(_wf.count("<rect") == 4 and "+GHS 50" in _wf and "−GHS 30" in _wf, "a waterfall draws each step, signed")
_pie9 = _pb.chart({"type": "pie", "labels": [f"P{i}" for i in range(9)], "series": [{"values": list(range(9, 0, -1))}]})
check("Other (3)" in _pie9 and "The 3 smallest are combined as Other." in _pie9 and _pie9.count("<path") == 7,
      "a pie of nine parts: six and Other, and it says so")
_old9 = _pb.chart({"type": "donut", "labels": [f"P{i}" for i in range(9)], "series": [{"values": list(range(9, 0, -1))}]})
check("Other (3)" in _old9, "an old donut of nine parts folds the rest into Other rather than dropping them")
check(_pb.chart({"type": "gauge", "unit": "GHS", "value": 5}) == "", "a money gauge needs its scale")
check(_pb.chart({"type": "gauge", "unit": "%", "value": "5"}) == "", "a gauge's figure must be a number")
check("#a85a0a" in _pb.chart(_new["gauge"]) and "#127a55" in _pb.chart({**_new["gauge"], "value": 90}),
      "a gauge short of target is amber, on target green")
check(_pb.chart({"type": "treemap", "items": [{"name": "A", "value": 5, "children": [{"name": "x", "value": 9}]}]}) == "",
      "a treemap whose parts exceed their parent is not drawn")
check("Not broken down" in _pb.chart({"type": "treemap", "items": [{"name": "A", "value": 100,
                                                                     "children": [{"name": "x", "value": 60}]}]}),
      "what a parent's parts leave is shown on paper too")
_tm_rects = _pb._squarify([(0, 6.0), (1, 3.0), (2, 1.0)], 0, 0, 100, 100)
check(len(_tm_rects) == 3 and abs(sum(w * h for _, _, _, w, h in _tm_rects) - 10000) < 1e-6
      and abs(_tm_rects[0][3] * _tm_rects[0][4] - 6000) < 1e-6, "the treemap layout gives each part its share of the area")
check(_pb.chart({"type": "radar", "labels": ["A", "B"], "series": [{"values": [1, 2]}]}) == "",
      "a radar of two dimensions is refused on paper")
for _k, _spec in _new.items():
    _evil = __import__("json").loads(__import__("json").dumps(_spec))
    if "labels" in _evil:
        _evil["labels"][0] = "<script>x</script>"
    if "items" in _evil:
        _evil["items"][0]["name"] = "<script>x</script>"
    _evil["title"] = "<script>t</script>"
    check("<script" not in _pb.chart(_evil), f"{_k}: text is escaped on paper")
_origd = _pb._funnel
_pb._funnel = lambda m: 1 / 0
check("<table>" in _pb.chart(_new["funnel"]), "a new chart that cannot be drawn becomes a table on paper")
_pb._funnel = _origd
_md3 = "Lead.\n\n" + "\n\n".join(f"```chart\n{__import__('json').dumps(v)}\n```" for v in _new.values())
export.answer_pdf("Report", _md3, [], "GIGMANN", "m")
_doc3 = frappe.local.response.filecontent.decode()
check(_doc3.count('<div class="ch">') == len(_new) and "```" not in _doc3, "every 2026 chart type reaches the answer PDF")

# the engine's settings: a fine layout grid, and no letter-spacing it would overdo
check(int(export.PDF_OPTIONS["dpi"]) >= 1200, "PDFs lay text out at 1200 dpi or finer")
check("letter-spacing" not in export.PDF_TEMPLATE + export.PAGE_CSS and "letter-spacing" not in export.pdf_blocks.CSS,
      "the PDF's styles use no letter-spacing")

# The brand on every output (command_center/branding.py): the product's name at the top,
# the vendor's line at the foot of every page and the end of every sheet.
_b = export.brand.branding("GIGMANN")
check(_b["product"] == "Ultrasoft Insights" and _b["company"] == "Ultrasoft Systems",
      "the product and vendor default to Ultrasoft Insights by Ultrasoft Systems")
_seen = {}
pdf.get_pdf = lambda html, options=None: (_seen.update(options or {}), html.encode())[1]
export.answer_pdf("Who owes us?", "Lead.", [], "GIGMANN", "m")
_ans = frappe.local.response.filecontent.decode()
check('<div class="brand">Ultrasoft Insights</div>' in _ans and "Ultrasoft Insights · built by Ultrasoft Systems" not in _ans,
      "an answer PDF carries the product at the top; the vendor's line is the page footer's, "
      "not repeated in the closing note")
check(_seen.get("footer-left", "").startswith("Ultrasoft Insights · built by Ultrasoft Systems")
      and _seen.get("footer-right") == "Page [page] of [topage]",
      "every PDF page's footer: the vendor's line, and Page X of Y")
_rep_md = ("# Executive Summary: Gigmann Medical Supplies Ltd\n\nHere's the summary you asked for:\n\n"
           "Sales fell 12% 📉 to GHS 1.2M.\n\n## cash and receivables\n\n| Customer | Owed |\n|---|---|\n"
           "| UBUNTU | 636675 |\n\n## Recommendations\n\n- **Recommendation:** Reconcile the GHS 7.25M "
           "of unmatched receipts by 30 November.\n- Recommendation: chase Ubuntu.\n")
export.answer_pdf("Executive Summary", _rep_md, [], "GIGMANN", "m", kind="report")
_rep = frappe.local.response.filecontent.decode()
check(_rep.count("Executive Summary") == 1 and "Executive Summary: Gigmann" not in _rep,
      "a report's heading that repeats its title is dropped: the title is said once")
check("Management Report" in _rep and "Prepared for <b>Gigmann Medical Supplies Ltd</b>" in _rep,
      "a report PDF opens with its title block")
check("📉" not in _rep and "Here's" not in _rep, "emoji and a chatty opening are left out of a report")
_tidied = export.report_text.tidy(_rep_md, "Executive Summary", "Gigmann Medical Supplies Ltd")
check("## Cash and Receivables" in _tidied, "a report's headings are in Title Case")
check("1. Reconcile the GHS 7.25M" in _tidied and "2. Chase Ubuntu." in _tidied
      and "Recommendation:" not in _tidied, "recommendations are a numbered list, without a label")
_pol2 = export._polish("<p>Lead</p><h2>Cash</h2><p>Text.</p><table><thead><tr><th>Who</th><th>Owed</th></tr></thead>"
                       "<tbody><tr><td>UBUNTU</td><td>636675</td></tr><tr><td>Year</td><td>2025</td></tr></tbody></table>"
                       "<h1>Stray</h1><h2>Recommendations</h2><ol><li>Reconcile.</li></ol>")
check('<td class="n">636,675</td>' in _pol2 and '<td class="n">2025</td>' in _pol2,
      "a bare figure of five digits or more gets its thousands separators; a year does not")
check('<div class="keep"><h2>Cash</h2><p>Text.</p></div>' in _pol2, "a heading is kept on the page with what follows it")
check('<ol class="recs">' in _pol2 and "<h1>" not in _pol2, "the Recommendations list is set off; a body h1 becomes h2")
check("p.proj{" not in export.PAGE_CSS, "a Projection reads as body text: no tinted box or accent bar in the PDF")
_rt = export.report_text
check(_rt.tidy("## Weekly Management Report — Gigmann Medical Supplies Ltd, November 2026\n\nText.",
               "Weekly management report", "Gigmann Medical Supplies Ltd").strip() == "Text.",
      "the title with the business and a date is a repeat too")
check(_rt.tidy("## Weekly Sales\n\nText.", "Weekly management report", "Gigmann").startswith("## Weekly Sales"),
      "a heading that is not the title is kept")
check(_rt.title_case("sales and payments in GHS: what to do") == "Sales and Payments in GHS: What to Do",
      "Title Case keeps acronyms and lowers short joining words")
export.tables_xlsx("Who owes us", [{"name": "T", "columns": ["A", "B"], "rows": [["x", "1"]]}], "GIGMANN")
_ws = load_workbook(io.BytesIO(frappe.local.response.filecontent)).active
check(_ws["A2"].value.startswith("Ultrasoft Insights · Gigmann Medical Supplies Ltd · figures as at"),
      "a sheet's header row names the product, the business and the date")
check(_ws.cell(row=_ws.max_row, column=1).value == "Prepared with Ultrasoft Insights by Ultrasoft Systems"
      and _ws.cell(row=_ws.max_row - 1, column=1).value is None,
      "a sheet ends with the vendor's line, after a blank row")

# _cell
check(export._cell("GHS 1,234.50") == 1234.5 and export._cell("12%") == 0.12, "figure parsing")
check(export._cell("Q3 2025") == "Q3 2025" and export._cell(None) == "", "non-figures untouched")

print(f"export: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
