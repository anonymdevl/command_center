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

The newer chart types (hbar, stacked, grouped, combo, scatter) are checked as strictly
as charts.js checks them -- every value a number, one per label, the right number of
series -- and are drawn as inline SVG or bar tables too. Should drawing one ever fail,
its figures go in as a plain table rather than the PDF failing: a block must never
break the document it sits in.

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
MAX_COLUMNS, MAX_SERIES, MAX_SCATTER = 24, 4, 40
STRICT = ("hbar", "stacked", "grouped", "combo", "scatter")
# The screen's column colours (charts.js .md-rect.c0..c3: accent, ok, high, dim).
COLS = (ACCENT, "#127a55", "#b35a0b", "#8a8f99")
CRIT = "#c2392f"


def render(lang: str, source: str) -> str:
    try:
        data = json.loads(source)
    except ValueError:
        return ""
    try:
        if lang == "figures":
            return figures(data)
        if lang == "chart":
            return chart(data)
    except Exception:  # noqa: BLE001 -- a block that cannot be drawn is left out, never fatal
        return ""
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
    if spec.get("type") in STRICT:
        return _strict_chart(spec)
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


# ------------------------------------------------------------- the newer chart types
def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def strict_model(spec) -> dict | None:
    """The block checked as charts.js strictModel checks it, or None: not drawn."""
    if not isinstance(spec, dict) or spec.get("type") not in STRICT:
        return None
    kind = spec["type"]
    labels = spec.get("labels")
    if not isinstance(labels, list) or not labels:
        return None
    if any(not (isinstance(x, str) or _is_num(x)) or not str(x).strip() for x in labels):
        return None
    raw = spec.get("series")
    fewest = 2 if kind in ("combo", "scatter") else 1
    most = 1 if kind == "hbar" else 2 if kind in ("combo", "scatter") else MAX_SERIES
    if not isinstance(raw, list) or not fewest <= len(raw) <= most:
        return None
    series = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict) or not isinstance(s.get("values"), list) or len(s["values"]) != len(labels):
            return None
        if not all(_is_num(v) for v in s["values"]):
            return None
        name = str(s.get("name") if s.get("name") is not None else "").strip()
        series.append({"name": name or (f"Series {i + 1}" if len(raw) > 1 else ""),
                       "values": [float(v) for v in s["values"]]})
    if kind == "stacked" and any(v < 0 for s in series for v in s["values"]):
        return None
    names = [_label(x) for x in labels]
    if kind == "hbar":
        order = sorted(range(len(names)), key=lambda i: -series[0]["values"][i])
        names = [names[i] for i in order]
        series[0]["values"] = [series[0]["values"][i] for i in order]
    cap = MAX_SCATTER if kind == "scatter" else MAX_COLUMNS if kind in ("stacked", "combo") else MAX_ITEMS
    n = min(len(names), cap)
    unit2 = spec.get("unit2")
    return {"type": kind, "title": str(spec.get("title") or ""), "unit": str(spec.get("unit") or ""),
            "unit2": "" if unit2 is None else str(unit2), "labels": names[:n],
            "series": [{**s, "values": s["values"][:n]} for s in series], "total": len(names)}


def _label(x) -> str:
    """A label as JavaScript's String() writes it: 2025, not 2025.0."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def _strict_chart(spec) -> str:
    m = strict_model(spec)
    if not m:
        return ""
    try:
        body = {"hbar": _hbars, "scatter": _scatter}.get(m["type"], _columns)(m)
    except Exception:  # noqa: BLE001 -- never let a drawing break the PDF: say the figures instead
        body = _table(m)
    keys = _legend_keys(m)
    if keys:
        body += '<div class="lg">' + "".join(
            f'<span><i style="background:{c};{"height:3px;width:14px" if ln else ""}"></i>{escape(n)}</span>'
            for n, c, ln in keys) + "</div>"
    if m["total"] > len(m["labels"]):
        body += f'<div class="ch-n">Showing the first {len(m["labels"])} of {m["total"]}.</div>'
    title = f'<div class="ch-t">{escape(m["title"])}</div>' if m["title"] else ""
    return f'<div class="ch">{title}{body}</div>'


def _with_unit(name, unit):
    return f"{name} ({unit})" if unit and name else name or unit or ""


def _legend_keys(m):
    s = m["series"]
    if m["type"] in ("stacked", "grouped") and len(s) > 1:
        return [(x["name"], COLS[i], False) for i, x in enumerate(s)]
    if m["type"] == "combo":
        return [(_with_unit(s[0]["name"], m["unit"]), COLS[0], False),
                (_with_unit(s[1]["name"], m["unit2"] or m["unit"]), COLS[1], True)]
    return []


def scale(lo: float, hi: float, n: int = 4) -> dict:
    """A round axis that always includes zero, as charts.js scale() draws it."""
    lo, hi = min(0.0, lo), max(0.0, hi)
    if hi - lo <= 0:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next((f * mag for f in (1, 2, 2.5, 5, 10, 20)
                 if math.ceil(hi / (f * mag) - 1e-9) - math.floor(lo / (f * mag) + 1e-9) <= n), 20 * mag)
    a, b = math.floor(lo / step + 1e-9) * step, math.ceil(hi / step - 1e-9) * step
    ticks, t = [], a
    while t <= b + step / 2:
        ticks.append(0.0 if abs(t) < step / 1e6 else float(f"{t:.12g}"))
        t += step
    return {"lo": a, "hi": b, "ticks": ticks}


def tick(v: float, unit: str = "") -> str:
    """An axis step, short: "2.5M", "250k", "40%"."""
    a = abs(v)

    def short(x):
        s = f"{x:,.2f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s

    s = (f"{short(v / 1e9)}B" if a >= 1e9 else f"{short(v / 1e6)}M" if a >= 1e6 else
         f"{short(v / 1e3)}k" if a >= 1e4 else short(v))
    return f"{s}%" if unit == "%" else s


def _svg(w, h, parts) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'font-family="Helvetica, Arial, sans-serif">{"".join(parts)}</svg>')


def _t(x, y, s, anchor="middle", size=9, fill=MUT, weight=""):
    bold = f' font-weight="{weight}"' if weight else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" fill="{fill}"{bold}>'
            f'{escape(str(s))}</text>')


def _columns(m) -> str:
    kind, labels, series, unit = m["type"], m["labels"], m["series"], m["unit"]
    dual = kind == "combo" and m["unit2"] != "" and m["unit2"] != unit
    W, H, T, B, L = 640, 240, 26, 30, 56
    R = 56 if dual else 14
    bars = series[:1] if kind == "combo" else series
    lo = hi = 0.0
    if kind == "stacked":
        hi = max(sum(s["values"][i] for s in series) for i in range(len(labels)))
    else:
        vals = [v for s in bars for v in s["values"]]
        lo, hi = min([0.0] + vals), max([0.0] + vals)
    line = series[1]["values"] if kind == "combo" else None
    if line and not dual:
        lo, hi = min([lo] + line), max([hi] + line)
    a1 = scale(lo, hi)
    a2 = scale(min(line), max(line)) if dual else a1
    ih = H - T - B

    def y1(v):
        return T + ih * (1 - (v - a1["lo"]) / (a1["hi"] - a1["lo"]))

    def y2(v):
        return T + ih * (1 - (v - a2["lo"]) / (a2["hi"] - a2["lo"]))

    n = len(labels)
    band = (W - L - R) / n
    parts = []
    for t in a1["ticks"]:
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y1(t):.1f}" y2="{y1(t):.1f}" stroke="{LINE}" stroke-width="0.8"/>')
        parts.append(_t(L - 6, y1(t) + 3, tick(t, unit), "end"))
    if dual:
        parts += [_t(W - R + 6, y2(t) + 3, tick(t, m["unit2"]), "start") for t in a2["ticks"]]
    if unit and unit != "%":
        parts.append(_t(L - 6, T - 12, unit, "end", weight="700"))
    if dual and m["unit2"] != "%":
        parts.append(_t(W - R + 6, T - 12, m["unit2"], "start", weight="700"))
    inner = band * (0.8 if kind == "grouped" else 0.62)
    for i in range(n):
        x0 = L + band * i + (band - inner) / 2
        if kind == "stacked":
            acc = 0.0
            for si, s in enumerate(series):
                v = s["values"][i]
                if v > 0:
                    parts.append(f'<rect x="{x0:.1f}" y="{y1(acc + v):.1f}" width="{inner:.1f}" '
                                 f'height="{y1(acc) - y1(acc + v):.1f}" fill="{COLS[si]}"/>')
                acc += v
            if n <= MAX_ITEMS and acc > 0:
                parts.append(_t(L + band * (i + 0.5), y1(acc) - 5, tick(acc, unit), fill=INK2, weight="700"))
        else:
            k = len(bars)
            w = inner / k
            for si, s in enumerate(bars):
                v = s["values"][i]
                top, bottom = y1(max(v, 0)), y1(min(v, 0))
                if bottom - top <= 0:
                    continue
                gap = w * 0.06 if k > 1 else 0
                parts.append(f'<rect x="{x0 + si * w + gap:.1f}" y="{top:.1f}" width="{w - 2 * gap:.1f}" '
                             f'height="{bottom - top:.1f}" fill="{COLS[si]}"/>')
    parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y1(0):.1f}" y2="{y1(0):.1f}" stroke="{INK2}" stroke-width="0.8"/>')
    if kind == "combo":
        yy = y2 if dual else y1
        pts = [(L + band * (i + 0.5), yy(v)) for i, v in enumerate(line)]
        parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" '
                     f'stroke="{COLS[1]}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>')
        parts += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{COLS[1]}"/>' for x, y in pts]
    fit = max(3, int(band // 6.2))
    every = math.ceil(n / int((W - L - R) // 34))
    for i, label in enumerate(labels):
        if i % every and i != n - 1:
            continue
        parts.append(_t(L + band * (i + 0.5), H - 10, label if len(label) <= fit else label[: fit - 1] + "…"))
    return _svg(W, H, parts)


def _scatter(m) -> str:
    W, H, T, B, L, R = 640, 280, 26, 42, 56, 18
    xs, ys = m["series"][0]["values"], m["series"][1]["values"]
    ax, ay = scale(min(xs), max(xs)), scale(min(ys), max(ys))

    def x(v):
        return L + (W - L - R) * (v - ax["lo"]) / (ax["hi"] - ax["lo"])

    def y(v):
        return T + (H - T - B) * (1 - (v - ay["lo"]) / (ay["hi"] - ay["lo"]))

    parts = []
    for t in ay["ticks"]:
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}" '
                     f'stroke="{INK2 if t == 0 else LINE}" stroke-width="0.8"/>')
        parts.append(_t(L - 6, y(t) + 3, tick(t, m["unit2"]), "end"))
    for t in ax["ticks"]:
        parts.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{T}" y2="{H - B}" '
                     f'stroke="{INK2 if t == 0 else LINE}" stroke-width="0.8"/>')
        parts.append(_t(x(t), H - B + 14, tick(t, m["unit"])))
    parts.append(_t(W - R, H - 6, _with_unit(m["series"][0]["name"], m["unit"]), "end", weight="700"))
    parts.append(_t(L - 6, T - 12, _with_unit(m["series"][1]["name"], m["unit2"]), "start", weight="700"))
    named = len(m["labels"]) <= MAX_ITEMS
    for i, label in enumerate(m["labels"]):
        px, py = x(xs[i]), y(ys[i])
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{ACCENT}" stroke="#ffffff" stroke-width="1.5"/>')
        if named:
            right = px > W - R - 110
            short = label if len(label) <= 18 else label[:17] + "…"
            parts.append(_t(px - 8 if right else px + 8, py + 3, short, "end" if right else "start", fill=INK2))
    return _svg(W, H, parts)


def _hbars(m) -> str:
    values = m["series"][0]["values"]
    lo, hi = min([0.0] + values), max([0.0] + values)
    span = (hi - lo) or 1
    zero = -lo / span * 100
    rows = []
    for i, label in enumerate(m["labels"]):
        v = values[i]
        width = abs(v) / span * 100
        left = zero - width if v < 0 else zero
        rows.append(
            f'<tr><td class="hb-r">{i + 1}</td><td class="hb-l">{escape(label)}</td>'
            f'<td class="bar-v">{escape(fmt(v, m["unit"]))}</td></tr>'
            f'<tr><td></td><td colspan="2" class="hb-t"><div class="bar-track">'
            f'<div class="bar-f" style="margin-left:{left:.1f}%;width:{width:.1f}%;'
            f'{"background:" + CRIT if v < 0 else ""}"></div></div></td></tr>')
    return f'<table class="bars hb">{"".join(rows)}</table>'


def _table(m) -> str:
    """The chart's figures as a plain table: what goes in when a drawing cannot."""
    s = m["series"]
    units = [m["unit2"] or m["unit"] if i == 1 and m["type"] in ("combo", "scatter") else m["unit"]
             for i in range(len(s))]
    head = "".join(f"<th>{escape(x['name'])}</th>" for x in s)
    rows = "".join(
        f"<tr><td>{escape(label)}</td>"
        + "".join(f'<td class="n">{escape(fmt(x["values"][i], units[j]))}</td>' for j, x in enumerate(s))
        + "</tr>" for i, label in enumerate(m["labels"]))
    return f"<table><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table>"


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
table.hb td{{padding:2px 0}}
td.hb-r{{width:16px;color:{MUT};padding-right:6px}}
td.hb-l{{color:{INK2};padding-right:10px}}
td.hb-t{{padding-bottom:6px}}
.ch-n{{font-size:7pt;color:{MUT};margin-top:5px}}
"""
