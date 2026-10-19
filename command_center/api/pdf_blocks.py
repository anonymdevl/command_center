"""The answer's figure cards and charts, drawn for paper.

On screen, charts.js draws an answer's ```figures and ```chart blocks. A PDF engine runs
no script, so the PDF used to turn them into plain tables -- correct, but nothing like
the report the manager had just read. These draw the same things the same way: the
figure cards in the screen's three tints, bars as bars, a line as a line, a donut as a
donut, as HTML tables and inline SVG that wkhtmltopdf renders reliably (no flexbox, no
grid, no CSS variables, no script).

Every value comes from the block's JSON and is escaped; nothing in a block is ever
treated as markup. A block that does not parse, or whose numbers are not numbers, is
left out rather than drawn wrong -- the same rule as the screen.

Imports nothing from frappe, so it can be tested on its own.
"""

from __future__ import annotations

import json
import math
from html import escape

# The light theme's colours (interface/p1.py), written out: a PDF has no CSS variables.
INK, INK2, MUT, LINE, RAISED = "#111317", "#3b3f47", "#646973", "#e3e5ea", "#f2f3f5"
ACCENT, ACCENT_BG = "#2443e8", "#e6eafd"
TINTS = ("#dceae2", "#f1e6d4", "#e1e5f0")
TONES = {"bad": "#c2392f", "warn": "#a85a0a", "good": "#127a55"}
SLICES = ("#2443e8", "#127a55", "#111317", "#b35a0b", "#8a8f99", "#7a4fd6")
MAX_ITEMS, MAX_POINTS = 12, 36


def render(lang: str, source: str) -> str:
    try:
        data = json.loads(source)
    except ValueError:
        return ""
    if lang == "figures":
        return figures(data)
    if lang == "chart":
        return chart(data)
    return ""


# ---------------------------------------------------------------------------- figures
def figures(items) -> str:
    """Up to four cards in one row, equal in height, values on one line across the row:
    the background is on the table cell itself, so every card in the row is as tall as
    the tallest, and labels get two lines of room so a long one does not push its value
    below the others."""
    if not isinstance(items, list):
        return ""
    cards = [f for f in items if isinstance(f, dict) and f.get("value") is not None][:4]
    if not cards:
        return ""
    width = f"{100 / len(cards):.2f}%"
    cells = []
    for i, f in enumerate(cards):
        tone = TONES.get(str(f.get("tone") or "").lower(), INK)
        note = escape(str(f["note"])) if f.get("note") else ""
        cells.append(
            f'<td class="fig" style="width:{width};background:{TINTS[i % 3]}">'
            f'<div class="fig-l">{escape(str(f.get("label") or ""))}</div>'
            f'<div class="fig-v" style="color:{tone}">{escape(str(f["value"]))}</div>'
            f'<div class="fig-n">{note}</div></td>')
    return f'<table class="figs"><tr>{"".join(cells)}</tr></table>'


# ------------------------------------------------------------------------------ chart
def chart(spec) -> str:
    if not isinstance(spec, dict):
        return ""
    labels = [str(x) for x in (spec.get("labels") or []) if x is not None]
    series = []
    for s in (spec.get("series") or [])[:3]:
        if not isinstance(s, dict) or not isinstance(s.get("values"), list):
            continue
        try:
            vals = [float(v) for v in s["values"]]
        except (TypeError, ValueError):
            return ""
        if any(math.isnan(v) or math.isinf(v) for v in vals):
            return ""
        series.append({"name": str(s.get("name") or ""), "values": vals})
    if not labels or not series:
        return ""
    unit = str(spec.get("unit") or "")
    kind = spec.get("type") if spec.get("type") in ("bar", "line", "donut") else "bar"
    if kind == "line":
        body = _line(labels[:MAX_POINTS], series, unit)
    elif kind == "donut":
        body = _donut(labels[:6], series[0]["values"][:6], unit)
    else:
        body = _bars(labels[:MAX_ITEMS], series[0]["values"][:MAX_ITEMS], unit)
    if not body:
        return ""
    title = f'<div class="ch-t">{escape(str(spec["title"]))}</div>' if spec.get("title") else ""
    return f'<div class="ch">{title}{body}</div>'


def _bars(labels, values, unit) -> str:
    top = max([abs(v) for v in values] + [0]) or 1
    rows = []
    for i, label in enumerate(labels):
        v = values[i] if i < len(values) else 0
        pct = max(1.5, abs(v) / top * 100)
        rows.append(
            f'<tr><td class="bar-l">{escape(label)}</td>'
            f'<td class="bar-t"><div class="bar-track"><div class="bar-f" style="width:{pct:.1f}%"></div></div></td>'
            f'<td class="bar-v">{escape(fmt(v, unit))}</td></tr>')
    return f'<table class="bars">{"".join(rows)}</table>'


def _line(labels, series, unit) -> str:
    W, H, L, R, T, B = 640, 220, 8, 8, 14, 26
    vals = [v for s in series for v in s["values"][: len(labels)]]
    if not vals:
        return ""
    lo, hi = min([0] + vals), max(vals) or 1
    span = (hi - lo) or 1

    def x(i):
        return L + ((W - L - R) / 2 if len(labels) == 1 else i * (W - L - R) / (len(labels) - 1))

    def y(v):
        return T + (H - T - B) * (1 - (v - lo) / span)

    parts, grid = [], []
    # Gridlines and their labels go on top of the shaded area, or the area hides them.
    for f in (0, 0.5, 1):
        gy = T + (H - T - B) * f
        grid.append(f'<line x1="{L}" x2="{W - R}" y1="{gy:.1f}" y2="{gy:.1f}" stroke="#c9cdd4" '
                    f'stroke-width="0.8" stroke-dasharray="3,3"/>')
        grid.append(f'<text x="{W - R}" y="{gy - 4:.1f}" text-anchor="end" font-size="9" fill="{MUT}">'
                    f'{escape(fmt(hi - span * f, unit))}</text>')
    colours = (ACCENT, "#127a55", "#b35a0b")
    areas, lines = [], []
    for si, s in enumerate(series):
        pts = [(x(i), y(v)) for i, v in enumerate(s["values"][: len(labels)])]
        if not pts:
            continue
        path = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        if si == 0 and len(pts) > 1:
            areas.append(f'<path d="M{pts[0][0]:.1f},{y(lo):.1f} L{path.replace(" ", " L")} '
                         f'L{pts[-1][0]:.1f},{y(lo):.1f} Z" fill="{ACCENT_BG}"/>')
        lines.append(f'<polyline points="{path}" fill="none" stroke="{colours[si]}" stroke-width="2.4" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
        lines.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.5" fill="{colours[si]}"/>')
    parts = areas + grid + lines
    step = max(1, math.ceil(len(labels) / 8))
    for i, label in enumerate(labels):
        if i % step and i != len(labels) - 1:
            continue
        parts.append(f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle" font-size="9" fill="{MUT}">'
                     f'{escape(label[:9])}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="220" viewBox="0 0 {W} {H}" '
           f'font-family="Helvetica, Arial, sans-serif">{"".join(parts)}</svg>')
    legend = ""
    if len(series) > 1:
        legend = '<div class="lg">' + "".join(
            f'<span><i style="background:{colours[i]}"></i>{escape(s["name"])}</span>'
            for i, s in enumerate(series)) + "</div>"
    return svg + legend


def _donut(labels, values, unit) -> str:
    total = sum(max(0, v) for v in values)
    if not total:
        return ""
    paths, a0 = [], -math.pi / 2

    def p(a, r):
        return f"{60 + r * math.cos(a):.2f},{60 + r * math.sin(a):.2f}"

    for i, v in enumerate(values):
        a1 = a0 + max(0, v) / total * math.pi * 2
        large = 1 if a1 - a0 > math.pi else 0
        end = a1 - 0.0001
        paths.append(f'<path d="M{p(a0, 52)} A52,52 0 {large} 1 {p(end, 52)} L{p(end, 32)} '
                     f'A32,32 0 {large} 0 {p(a0, 32)} Z" fill="{SLICES[i % len(SLICES)]}"/>')
        a0 = a1
    centre = fmt(total, "%" if unit == "%" else "")
    sub = (f'<text x="60" y="75" text-anchor="middle" font-size="8" fill="{MUT}">{escape(unit)}</text>'
           if unit and unit != "%" else "")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="150" height="150" viewBox="0 0 120 120" '
           f'font-family="Helvetica, Arial, sans-serif">{"".join(paths)}'
           f'<text x="60" y="{61 if sub else 64}" text-anchor="middle" font-size="12" font-weight="700" '
           f'fill="{INK}">{escape(centre)}</text>{sub}</svg>')
    rows = "".join(
        f'<tr><td><i style="background:{SLICES[i % len(SLICES)]}"></i></td><td>{escape(l)}</td>'
        f'<td class="dn-p">{max(0, values[i]) / total * 100:.1f}%</td></tr>'
        for i, l in enumerate(labels) if i < len(values))
    return (f'<table class="dn"><tr><td class="dn-s">{svg}</td>'
            f'<td class="dn-l"><table class="dn-k">{rows}</table></td></tr></table>')


def fmt(v: float, unit: str = "") -> str:
    """9177568 -> "GHS 9.18M", as charts.js writes it."""
    a = abs(v)
    s = (f"{v / 1e9:.2f}B" if a >= 1e9 else f"{v / 1e6:.2f}M" if a >= 1e6 else
         f"{v / 1e3:.1f}k" if a >= 1e4 else f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}")
    return f"{s}%" if unit == "%" else f"{unit} {s}" if unit else s


# The styles these blocks need, for the PDF template.
CSS = f"""
table.figs{{width:100%;border-collapse:separate;border-spacing:8px 0;margin:16px -8px 12px;table-layout:fixed}}
table.figs td.fig{{border:0;border-radius:9px;padding:10px 12px 11px;vertical-align:top}}
.fig-l{{font-size:7pt;font-weight:600;color:{INK2};line-height:1.3;height:2.6em;overflow:hidden}}
.fig-v{{font-size:12.5pt;font-weight:700;line-height:1.15;margin-top:3px;white-space:nowrap}}
.fig-n{{font-size:6.5pt;color:{MUT};margin-top:3px;line-height:1.35}}
.ch{{border:1px solid {LINE};border-radius:10px;padding:13px 15px 11px;margin:14px 0;page-break-inside:avoid}}
.ch-t{{font-size:8.5pt;font-weight:700;color:{INK};margin-bottom:8px}}
table.bars{{width:100%;border-collapse:collapse;margin:0}}
table.bars td,table.dn td,table.dn-k td{{background:none!important}}
table.bars td{{border:0;padding:3px 0;font-size:7.5pt;vertical-align:middle}}
td.bar-l{{width:32%;color:{INK2};padding-right:10px}}
td.bar-t{{width:auto}}
.bar-track{{height:7px;background:{RAISED};border-radius:5px;overflow:hidden}}
.bar-f{{height:7px;background:{ACCENT};border-radius:5px}}
td.bar-v{{width:18%;text-align:right;font-weight:700;color:{INK};padding-left:10px;white-space:nowrap}}
.lg{{font-size:7.5pt;color:{INK2};margin-top:6px}}
.lg span{{margin-right:14px}}
.lg i,.dn-k i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:middle}}
table.dn{{border-collapse:collapse;margin:0}}
table.dn td{{border:0;vertical-align:middle;background:none}}
td.dn-l{{padding-left:18px}}
table.dn-k td{{border:0;padding:3px 6px 3px 0;font-size:7.5pt;color:{INK2};background:none}}
td.dn-p{{font-weight:700;color:{INK};text-align:right;padding-left:14px}}
"""
