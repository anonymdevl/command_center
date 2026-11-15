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

The newer chart types (hbar, stacked, grouped, combo, scatter, pie, rose, area,
stacked_area, percentage, waterfall, funnel, gauge, heatmap, treemap, radar, bubble) are
checked as strictly as charts.js checks them -- every value a number, one per label, the
right number of series, a waterfall that adds up, a treemap whose parts fit their parent
-- and are drawn as static inline SVG or bar tables in the screen's palette. Should
drawing one ever fail, its figures go in as a plain table rather than the PDF failing:
a block must never break the document it sits in.

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
# The screen's chart series, in order (--viz1..7 in interface/p1.py, light theme).
PALETTE = ("#2443e8", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6")
SLICES = PALETTE
COLS = PALETTE
DIM, OK, HIGH = "#7c818b", "#127a55", "#a85a0a"
MAX_ITEMS, MAX_POINTS = 12, 36
MAX_COLUMNS, MAX_SERIES, MAX_SCATTER = 24, 4, 40
MAX_SHARES = 7
# The strict types, as charts.js RULES has them: series allowed, labels drawn (cap) or
# allowed at all (most_labels), and what the values may be.
RULES = {
    "hbar": {"fewest": 1, "most": 1, "cap": MAX_ITEMS},
    "stacked": {"fewest": 1, "most": MAX_SERIES, "cap": MAX_COLUMNS, "nonneg": True},
    "grouped": {"fewest": 1, "most": MAX_SERIES, "cap": MAX_ITEMS},
    "combo": {"fewest": 2, "most": 2, "cap": MAX_COLUMNS},
    "scatter": {"fewest": 2, "most": 2, "cap": MAX_SCATTER},
    "pie": {"fewest": 1, "most": 1, "share": True, "nonneg": True, "most_labels": 40},
    "rose": {"fewest": 1, "most": 1, "share": True, "nonneg": True, "most_labels": 40},
    "area": {"fewest": 1, "most": 3, "cap": MAX_POINTS},
    "stacked_area": {"fewest": 1, "most": MAX_SERIES, "cap": MAX_POINTS, "nonneg": True},
    "percentage": {"fewest": 1, "most": 6, "cap": MAX_COLUMNS, "nonneg": True},
    "waterfall": {"fewest": 1, "most": 1, "most_labels": 20},
    "funnel": {"fewest": 1, "most": 1, "cap": 8, "nonneg": True},
    "heatmap": {"fewest": 1, "most": 24, "cap": 31},
    "radar": {"fewest": 1, "most": MAX_SERIES, "fewest_labels": 3, "most_labels": 10, "nonneg": True},
    "bubble": {"fewest": 3, "most": 3, "cap": MAX_SCATTER},
}
STRICT = tuple(RULES) + ("gauge", "treemap")
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
        vals = [max(0.0, series[0]["values"][i]) if i < len(series[0]["values"]) else 0.0 for i in range(len(labels))]
        labels, vals, _ = _fold(labels, vals)
        body = _donut(labels, vals, unit)
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


def _fold(labels, values):
    """Shares of a whole: up to seven parts as they are; beyond, the six largest and
    "Other" -- never a dropped part, which would inflate every share shown."""
    if len(labels) <= MAX_SHARES:
        return list(labels), list(values), ""
    keep = sorted(sorted(range(len(values)), key=lambda i: -values[i])[: MAX_SHARES - 1])
    rest = len(labels) - len(keep)
    other = sum(v for i, v in enumerate(values) if i not in keep)
    return ([labels[i] for i in keep] + [f"Other ({rest})"], [values[i] for i in keep] + [other],
            f"The {rest} smallest are combined as Other.")


def _slice_colour(i, labels):
    return DIM if str(labels[i]).startswith("Other (") and i == len(labels) - 1 else SLICES[i % len(SLICES)]


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
                     f'A32,32 0 {large} 0 {p(a0, 32)} Z" fill="{_slice_colour(i, labels)}"/>')
        a0 = a1
    centre = fmt(total, "%" if unit == "%" else "")
    sub = (f'<text x="60" y="75" text-anchor="middle" font-size="8" fill="{MUT}">{escape(unit)}</text>'
           if unit and unit != "%" else "")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="150" height="150" viewBox="0 0 120 120" '
           f'font-family="Helvetica, Arial, sans-serif">{"".join(paths)}'
           f'<text x="60" y="{61 if sub else 64}" text-anchor="middle" font-size="12" font-weight="700" '
           f'fill="{INK}">{escape(centre)}</text>{sub}</svg>')
    rows = "".join(
        f'<tr><td><i style="background:{_slice_colour(i, labels)}"></i></td><td>{escape(l)}</td>'
        f'<td class="dn-p">{max(0, values[i]) / total * 100:.1f}%</td></tr>'
        for i, l in enumerate(labels) if i < len(values))
    return (f'<table class="dn"><tr><td class="dn-s">{svg}</td>'
            f'<td class="dn-l"><table class="dn-k">{rows}</table></td></tr></table>')


# ------------------------------------------------------------- the newer chart types
def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def strict_model(spec) -> dict | None:
    """The block checked as charts.js chartModel checks it, or None: not drawn."""
    if not isinstance(spec, dict) or spec.get("type") not in STRICT:
        return None
    kind = spec["type"]
    if kind == "gauge":
        return _gauge_model(spec)
    if kind == "treemap":
        return _treemap_model(spec)
    rule = RULES[kind]
    labels = spec.get("labels")
    if not isinstance(labels, list) or not labels:
        return None
    if any(not (isinstance(x, str) or _is_num(x)) or not str(x).strip() for x in labels):
        return None
    if len(labels) < rule.get("fewest_labels", 1) or len(labels) > rule.get("most_labels", 10 ** 9):
        return None
    raw = spec.get("series")
    if not isinstance(raw, list) or not rule["fewest"] <= len(raw) <= rule["most"]:
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
    if rule.get("nonneg") and any(v < 0 for s in series for v in s["values"]):
        return None
    if kind == "bubble" and any(v < 0 for v in series[2]["values"]):
        return None
    names = [_label(x) for x in labels]
    if kind == "hbar":
        order = sorted(range(len(names)), key=lambda i: -series[0]["values"][i])
        names = [names[i] for i in order]
        series[0]["values"] = [series[0]["values"][i] for i in order]
    unit2 = spec.get("unit2")
    base = {"type": kind, "title": str(spec.get("title") or ""), "unit": str(spec.get("unit") or ""),
            "unit2": "" if unit2 is None else str(unit2), "unit3": str(spec.get("unit3") or ""), "note": ""}
    if rule.get("share"):
        if not any(v > 0 for v in series[0]["values"]):
            return None
        names, vals, note = _fold(names, series[0]["values"])
        return {**base, "labels": names, "series": [{"name": series[0]["name"], "values": vals}],
                "total": len(names), "note": note}
    if kind == "waterfall":
        return _waterfall_model(spec, base, names, series[0])
    if kind == "radar":
        top = max([v for s in series for v in s["values"]] + [0.0])
        mx = spec.get("max")
        if mx is not None and (not _is_num(mx) or mx <= 0 or mx < top):
            return None
        if mx is None:
            mx = 100.0 if base["unit"] == "%" and top <= 100 else scale(0, top)["hi"]
        return {**base, "labels": names, "series": series, "total": len(names), "max": float(mx)}
    cap = rule.get("cap", len(names))
    n = min(len(names), cap)
    out = {**base, "labels": names[:n], "series": [{**s, "values": s["values"][:n]} for s in series],
           "total": len(names)}
    if out["total"] > n:
        out["note"] = f"Showing the first {n} of {out['total']}."
    return out


def _waterfall_model(spec, base, names, s):
    """Levels (by index in "totals"; first and last unless said) and movements between
    them. Each level after the first must equal the running level, or nothing is drawn."""
    n = len(names)
    totals = spec.get("totals", [0, n - 1] if n > 1 else [0])
    if not isinstance(totals, list) or not all(isinstance(t, int) and not isinstance(t, bool) and 0 <= t < n
                                               for t in totals):
        return None
    if 0 not in totals:
        return None
    vals = s["values"]
    tol = max(0.01, max([abs(v) for v in vals] + [1]) * 0.005)
    level, bars = 0.0, []
    for i, v in enumerate(vals):
        if i in totals:
            if i > 0 and abs(level - v) > tol:
                return None
            level = v
            bars.append({"low": min(0.0, v), "high": max(0.0, v), "end": v, "kind": "total"})
        else:
            nxt = level + v
            bars.append({"low": min(level, nxt), "high": max(level, nxt), "end": nxt,
                         "kind": "down" if v < 0 else "up"})
            level = nxt
    return {**base, "labels": names, "series": [{"name": s["name"], "values": vals}], "total": n, "bars": bars}


def _gauge_model(spec):
    value = spec.get("value")
    if not _is_num(value):
        return None
    unit = str(spec.get("unit") or "")
    lo = spec.get("min", 0)
    hi = spec.get("max", 100 if unit == "%" else None)
    if not _is_num(lo) or not _is_num(hi) or hi <= lo:
        return None
    target = spec.get("target")
    if target is not None and not _is_num(target):
        return None
    label = str(spec.get("label") or spec.get("title") or "")
    off = value < lo or value > hi
    return {"type": "gauge", "title": str(spec.get("title") or ""), "unit": unit, "unit2": "", "unit3": "",
            "labels": [label or "Value"], "series": [{"name": label, "values": [float(value)]}], "total": 1,
            "gauge": {"value": float(value), "min": float(lo), "max": float(hi),
                      "target": None if target is None else float(target),
                      "better": "lower" if spec.get("better") == "lower" else "higher", "label": label},
            "note": f"The figure is off the scale ({_label(lo)} to {_label(hi)}); it is shown at the end." if off else ""}


def _treemap_model(spec):
    """Two levels at most; a parent's parts may not exceed it, and what they leave is
    shown as "Not broken down"."""
    items = spec.get("items")
    if items is None:
        labels, series = spec.get("labels"), spec.get("series")
        if (isinstance(labels, list) and isinstance(series, list) and len(series) == 1
                and isinstance(series[0], dict) and isinstance(series[0].get("values"), list)
                and len(series[0]["values"]) == len(labels)):
            items = [{"name": l, "value": v} for l, v in zip(labels, series[0]["values"])]
    if not isinstance(items, list) or not items or len(items) > 200:
        return None
    tree = []
    for it in items:
        if not isinstance(it, dict) or not (isinstance(it.get("name"), str) or _is_num(it.get("name"))) \
                or not str(it.get("name")).strip():
            return None
        kids = None
        if "children" in it:
            ch = it["children"]
            if not isinstance(ch, list) or not ch or len(ch) > 100:
                return None
            kids = []
            for c in ch:
                if not isinstance(c, dict) or "children" in c or not _is_num(c.get("value")) or c["value"] < 0 \
                        or not (isinstance(c.get("name"), str) or _is_num(c.get("name"))) or not str(c["name"]).strip():
                    return None
                kids.append({"name": _label(c["name"]), "value": float(c["value"])})
        total = sum(k["value"] for k in kids) if kids else None
        value = it.get("value", total)
        if not _is_num(value) or value < 0:
            return None
        if kids:
            tol = max(0.01, value * 0.005)
            if total > value + tol:
                return None
            if value - total > tol:
                kids.append({"name": "Not broken down", "value": value - total, "rest": True})
            kids = _fold_list(kids, 15)
        node = {"name": _label(it["name"]), "value": float(value)}
        if kids:
            node["children"] = kids
        tree.append(node)
    if not any(t["value"] > 0 for t in tree):
        return None
    top = _fold_list(sorted(tree, key=lambda t: -t["value"]), 30)
    note = f"The {len(tree) - len(top) + 1} smallest are combined as Other." if len(top) < len(tree) else ""
    return {"type": "treemap", "title": str(spec.get("title") or ""), "unit": str(spec.get("unit") or ""),
            "unit2": "", "unit3": "", "tree": top, "labels": [t["name"] for t in top],
            "series": [{"name": "", "values": [t["value"] for t in top]}], "total": len(top), "note": note}


def _fold_list(items, most):
    if len(items) <= most:
        return items
    ranked = sorted(items, key=lambda x: -x["value"])
    rest = ranked[most - 1:]
    return ranked[: most - 1] + [{"name": f"Other ({len(rest)})", "value": sum(x["value"] for x in rest), "rest": True}]


def _label(x) -> str:
    """A label as JavaScript's String() writes it: 2025, not 2025.0."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def _strict_chart(spec) -> str:
    m = strict_model(spec)
    if not m:
        return ""
    draw = {"hbar": _hbars, "scatter": _scatter, "bubble": _scatter, "pie": _pie, "rose": _pie,
            "area": _area, "stacked_area": _area, "waterfall": _waterfall, "funnel": _funnel,
            "gauge": _gauge, "heatmap": _heatmap, "treemap": _treemap, "radar": _radar}.get(m["type"], _columns)
    try:
        body = draw(m)
    except Exception:  # noqa: BLE001 -- never let a drawing break the PDF: say the figures instead
        body = _table(m)
    keys = _legend_keys(m)
    if keys:
        body += '<div class="lg">' + "".join(
            f'<span><i style="background:{c};{"height:3px;width:14px" if ln else ""}"></i>{escape(n)}</span>'
            for n, c, ln in keys) + "</div>"
    if m.get("note"):
        body += f'<div class="ch-n">{escape(m["note"])}</div>'
    title = f'<div class="ch-t">{escape(m["title"])}</div>' if m["title"] else ""
    return f'<div class="ch">{title}{body}</div>'


def _with_unit(name, unit):
    return f"{name} ({unit})" if unit and name else name or unit or ""


def _legend_keys(m):
    s = m["series"]
    if m["type"] in ("stacked", "grouped", "percentage", "area", "stacked_area", "radar") and len(s) > 1:
        return [(x["name"], COLS[i % len(COLS)], m["type"] in ("area", "radar")) for i, x in enumerate(s)]
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
    if m["type"] == "percentage":
        # Each column as shares of its own total, drawn as a stack to 100%.
        tot = [sum(s["values"][i] for s in m["series"]) for i in range(len(m["labels"]))]
        m = {**m, "type": "stacked", "unit": "%", "series": [
            {**s, "values": [100 * v / tot[i] if tot[i] else 0.0 for i, v in enumerate(s["values"])]}
            for s in m["series"]]}
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
    bubble = m["type"] == "bubble"
    big = (max(m["series"][2]["values"] + [0.0]) or 1.0) if bubble else 1.0
    for i, label in enumerate(m["labels"]):
        px, py = x(xs[i]), y(ys[i])
        # A bubble's AREA is its figure: the radius is the square root.
        r = max(2.0, 24 * math.sqrt(max(0.0, m["series"][2]["values"][i]) / big)) if bubble else 4.5
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.1f}" fill="{ACCENT}" '
                     f'fill-opacity="{0.6 if bubble else 1}" stroke="#ffffff" stroke-width="1.5"/>')
        if named:
            right = px > W - R - 110
            short = label if len(label) <= 18 else label[:17] + "…"
            gap = 4 + r
            parts.append(_t(px - gap if right else px + gap, py + 3, short, "end" if right else "start", fill=INK2))
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


# ------------------------------------------------------------- the 2026 chart types
def _arc(cx, cy, r0, r1, a0, a1) -> str:
    """A ring (or pie) sector from angle a0 to a1, as an SVG path."""
    large = 1 if a1 - a0 > math.pi else 0
    e = a1 - 0.0001

    def p(a, r):
        return f"{cx + r * math.cos(a):.2f},{cy + r * math.sin(a):.2f}"

    if r0 <= 0:
        return f"M{cx:.2f},{cy:.2f} L{p(a0, r1)} A{r1:.2f},{r1:.2f} 0 {large} 1 {p(e, r1)} Z"
    return (f"M{p(a0, r1)} A{r1:.2f},{r1:.2f} 0 {large} 1 {p(e, r1)} L{p(e, r0)} "
            f"A{r0:.2f},{r0:.2f} 0 {large} 0 {p(a0, r0)} Z")


def _pie(m) -> str:
    """A pie, or a rose: every petal the same angle, its AREA the figure (radius is the
    square root), so a part twice as large looks twice as large."""
    labels, values = m["labels"], [max(0.0, v) for v in m["series"][0]["values"]]
    total = sum(values)
    if not total:
        return ""
    rose = m["type"] == "rose"
    big = max(values) or 1
    paths, a0 = [], -math.pi / 2
    for i, v in enumerate(values):
        if rose:
            a1 = a0 + 2 * math.pi / len(values)
            r = 56 * math.sqrt(v / big)
        else:
            a1 = a0 + v / total * 2 * math.pi
            r = 56
        if r > 0 and a1 > a0:
            paths.append(f'<path d="{_arc(60, 60, 0, r, a0, a1)}" fill="{_slice_colour(i, labels)}" '
                         f'stroke="#ffffff" stroke-width="1"/>')
        a0 = a1
    svg = _svg(120, 120, paths).replace('width="120" height="120"', 'width="150" height="150"', 1)
    rows = "".join(
        f'<tr><td><i style="background:{_slice_colour(i, labels)}"></i></td><td>{escape(l)}</td>'
        f'<td class="dn-p">{values[i] / total * 100:.1f}%</td></tr>' for i, l in enumerate(labels))
    return (f'<table class="dn"><tr><td class="dn-s">{svg}</td>'
            f'<td class="dn-l"><table class="dn-k">{rows}</table></td></tr></table>')


def _area(m) -> str:
    """Areas over time, from zero: each series shaded under its line, or stacked."""
    W, H, T, B, L, R = 640, 230, 26, 28, 56, 14
    labels, series, unit = m["labels"], m["series"], m["unit"]
    stack = m["type"] == "stacked_area"
    n = len(labels)
    tops = []
    acc = [0.0] * n
    for s in series:
        cur = [(acc[i] if stack else 0.0) + s["values"][i] for i in range(n)]
        tops.append((list(acc) if stack else [0.0] * n, cur))
        if stack:
            acc = cur
    vals = [v for _, cur in tops for v in cur]
    a = scale(min(vals + [0.0]), max(vals + [0.0]))

    def x(i):
        return L + ((W - L - R) / 2 if n == 1 else i * (W - L - R) / (n - 1))

    def y(v):
        return T + (H - T - B) * (1 - (v - a["lo"]) / (a["hi"] - a["lo"]))

    parts = []
    for t in a["ticks"]:
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{LINE}" stroke-width="0.8"/>')
        parts.append(_t(L - 6, y(t) + 3, tick(t, unit), "end"))
    if unit and unit != "%":
        parts.append(_t(L - 6, T - 12, unit, "end", weight="700"))
    for si, (low, cur) in enumerate(tops):
        c = COLS[si % len(COLS)]
        up = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(cur))
        down = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in reversed(list(enumerate(low))))
        parts.append(f'<polygon points="{up} {down}" fill="{c}" fill-opacity="{0.55 if stack else 0.16}"/>')
        parts.append(f'<polyline points="{up}" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/>')
    step = max(1, math.ceil(n / 8))
    for i, label in enumerate(labels):
        if i % step and i != n - 1:
            continue
        parts.append(_t(x(i), H - 9, label[:9]))
    return _svg(W, H, parts)


def _waterfall(m) -> str:
    """A bridge: levels from zero, movements floating from the level before, joined."""
    W, H, T, B, L, R = 640, 250, 30, 30, 56, 14
    bars, labels, vals, unit = m["bars"], m["labels"], m["series"][0]["values"], m["unit"]
    a = scale(min(b["low"] for b in bars), max(b["high"] for b in bars))

    def y(v):
        return T + (H - T - B) * (1 - (v - a["lo"]) / (a["hi"] - a["lo"]))

    n = len(bars)
    band = (W - L - R) / n
    bw = min(band * 0.58, 56)
    parts = []
    for t in a["ticks"]:
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{LINE}" stroke-width="0.8"/>')
        parts.append(_t(L - 6, y(t) + 3, tick(t, unit), "end"))
    if unit and unit != "%":
        parts.append(_t(L - 6, T - 14, unit, "end", weight="700"))
    for i, b in enumerate(bars):
        cx = L + band * (i + 0.5)
        colour = ACCENT if b["kind"] == "total" else OK if b["kind"] == "up" else CRIT
        top, bottom = y(b["high"]), y(b["low"])
        parts.append(f'<rect x="{cx - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(1.0, bottom - top):.1f}" '
                     f'rx="2" fill="{colour}"/>')
        if i < n - 1:
            ly = y(b["end"])
            parts.append(f'<line x1="{cx + bw / 2:.1f}" x2="{cx + band - bw / 2:.1f}" y1="{ly:.1f}" y2="{ly:.1f}" '
                         f'stroke="{DIM}" stroke-width="0.8" stroke-dasharray="3,3"/>')
        v = vals[i]
        text = fmt(v, unit) if b["kind"] == "total" else ("−" if v < 0 else "+") + fmt(abs(v), unit)
        parts.append(_t(cx, top - 5, text, fill=INK2, weight="700"))
        fit = max(4, int(band // 6))
        label = labels[i]
        parts.append(_t(cx, H - 10, label if len(label) <= fit else label[: fit - 1] + "…"))
    parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="{INK2}" stroke-width="0.8"/>')
    return _svg(W, H, parts)


def _funnel(m) -> str:
    """Stages in order, each as wide as its count, with its share of the first stage."""
    labels, vals = m["labels"], [max(0.0, v) for v in m["series"][0]["values"]]
    n = len(vals)
    W, row = 640, 40
    H = n * row + 8
    big = max(vals) or 1
    cx, full = 170, 320
    first = vals[0]
    parts = []
    for i, v in enumerate(vals):
        w0 = full * v / big
        w1 = full * (vals[i + 1] if i + 1 < n else 0) / big
        y0, y1 = 4 + i * row, 4 + i * row + row - 3
        c = _mix(ACCENT, "#ffffff", 0.55 * i / max(1, n - 1))
        parts.append(f'<polygon points="{cx - w0 / 2:.1f},{y0} {cx + w0 / 2:.1f},{y0} {cx + w1 / 2:.1f},{y1} '
                     f'{cx - w1 / 2:.1f},{y1}" fill="{c}"/>')
        share = f" · {v / first * 100:.1f}% of the first" if i and first else ""
        parts.append(_t(cx + full / 2 + 16, y0 + row / 2 + 1,
                        f"{labels[i]} · {fmt(v, m['unit'])}{share}", "start", size=10, fill=INK2))
    return _svg(W, H, parts)


def _mix(a, b, t):
    x = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    y = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(p + (q - p) * t):02x}" for p, q in zip(x, y))


def _gauge(m) -> str:
    """One figure on its scale: a track, the figure's arc, a tick at the target."""
    g = m["gauge"]
    lo, hi, v = g["min"], g["max"], g["value"]
    meets = None if g["target"] is None else (v >= g["target"] if g["better"] == "higher" else v <= g["target"])
    colour = ACCENT if meets is None else OK if meets else HIGH
    a0, a1 = math.radians(150), math.radians(390)

    def ang(x):
        return a0 + (a1 - a0) * (min(hi, max(lo, x)) - lo) / (hi - lo)

    cx, cy, r0, r1 = 120, 105, 66, 84
    parts = [f'<path d="{_arc(cx, cy, r0, r1, a0, a1)}" fill="{RAISED}"/>']
    if ang(v) > a0:
        parts.append(f'<path d="{_arc(cx, cy, r0, r1, a0, ang(v))}" fill="{colour}"/>')
    if g["target"] is not None:
        t = ang(g["target"])
        parts.append(f'<line x1="{cx + (r0 - 6) * math.cos(t):.1f}" y1="{cy + (r0 - 6) * math.sin(t):.1f}" '
                     f'x2="{cx + (r1 + 6) * math.cos(t):.1f}" y2="{cy + (r1 + 6) * math.sin(t):.1f}" '
                     f'stroke="{INK}" stroke-width="2.5"/>')
    parts.append(_t(cx, cy + 6, fmt(v, m["unit"]), size=22, fill=INK, weight="700"))
    under = f"Target {fmt(g['target'], m['unit'])}" if g["target"] is not None else g["label"]
    parts.append(_t(cx, cy + 26, under[:34], size=9))
    parts.append(_t(cx + r1 * math.cos(a0), cy + r1 * math.sin(a0) + 16, tick(lo, m["unit"])))
    parts.append(_t(cx + r1 * math.cos(a1), cy + r1 * math.sin(a1) + 16, tick(hi, m["unit"])))
    return _svg(240, 190, parts)


def _heatmap(m) -> str:
    """Two dimensions as a grid of cells, darker for more; the figure on each cell."""
    cols, rows = m["labels"], [s["name"] for s in m["series"]]
    vals = [v for s in m["series"] for v in s["values"]]
    lo, hi = min(vals), max(vals)
    diverging = lo < 0 < hi
    if diverging:
        hi = max(-lo, hi)
        lo = -hi
    span = (hi - lo) or 1
    L, T = 110, 8
    cw = min(48.0, (640 - L - 8) / len(cols))
    ch = 22
    parts = []
    for r, s in enumerate(m["series"]):
        parts.append(_t(L - 6, T + r * ch + ch / 2 + 3, rows[r][:18], "end", fill=INK2))
        for c, v in enumerate(s["values"]):
            t = (v - lo) / span
            if diverging:
                fill = _mix("#ffffff", PALETTE[0], (t - 0.5) * 2) if t >= 0.5 else _mix("#ffffff", PALETTE[1], (0.5 - t) * 2)
                dark = abs(t - 0.5) > 0.28
            else:
                fill = _mix("#e9ecfc", PALETTE[0], t)
                dark = t > 0.55
            x, y = L + c * cw, T + r * ch
            parts.append(f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{cw - 2:.1f}" height="{ch - 2}" rx="2" fill="{fill}"/>')
            if len(vals) <= 120:
                parts.append(_t(x + cw / 2, y + ch / 2 + 3, tick(v, m["unit"]), size=8,
                                fill="#ffffff" if dark else INK))
    for c, label in enumerate(cols):
        parts.append(_t(L + c * cw + cw / 2, T + len(rows) * ch + 12, label[:6], size=8))
    return _svg(640, T + len(rows) * ch + 20, parts)


def _squarify(items, x, y, w, h):
    """Rectangles for items (largest first) filling x, y, w, h, kept close to square
    (Bruls, Huizing and van Wijk's squarified layout)."""
    out = []
    items = [it for it in items if it[1] > 0]
    total = sum(v for _, v in items)
    if not items or total <= 0 or w <= 0 or h <= 0:
        return out
    scale_ = w * h / total
    rest = [(k, v * scale_) for k, v in items]

    def worst(row, side):
        s = sum(a for _, a in row)
        return max(max(side * side * a / (s * s), (s * s) / (side * side * a)) for _, a in row)

    while rest:
        side = min(w, h)
        row = [rest.pop(0)]
        while rest and worst(row + [rest[0]], side) <= worst(row, side):
            row.append(rest.pop(0))
        s = sum(a for _, a in row)
        if w >= h:
            cw = s / h
            yy = y
            for k, a in row:
                out.append((k, x, yy, cw, a / cw))
                yy += a / cw
            x, w = x + cw, w - cw
        else:
            rh = s / w
            xx = x
            for k, a in row:
                out.append((k, xx, y, a / rh, rh))
                xx += a / rh
            y, h = y + rh, h - rh
    return out


def _treemap(m) -> str:
    """What a whole is made of, as areas: parts in their parent's colour, lighter for
    smaller, each named with its figure where it fits."""
    W, H = 640, 300
    parts = []
    tree = m["tree"]
    for i, x, y, w, h in _squarify([(i, t["value"]) for i, t in enumerate(tree)], 0, 0, W, H):
        t = tree[i]
        colour = DIM if t.get("rest") else PALETTE[i % len(PALETTE)]
        kids = t.get("children")
        if kids:
            head = 16 if h > 40 else 0
            parts.append(f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{w - 2:.1f}" height="{h - 2:.1f}" fill="{colour}"/>')
            if head and w > 50:
                parts.append(_t(x + 6, y + 12, f"{t['name']}  {fmt(t['value'], m['unit'])}"[: int(w / 5.5)],
                                "start", size=8, fill="#ffffff", weight="700"))
            for j, kx, ky, kw, kh in _squarify([(j, k["value"]) for j, k in enumerate(kids)],
                                               x + 3, y + head + 2, w - 6, h - head - 5):
                k = kids[j]
                kc = DIM if k.get("rest") else _mix(colour, "#ffffff", min(0.55, 0.16 * j))
                parts.append(f'<rect x="{kx + 0.5:.1f}" y="{ky + 0.5:.1f}" width="{max(0.0, kw - 1):.1f}" '
                             f'height="{max(0.0, kh - 1):.1f}" fill="{kc}"/>')
                if kw > 46 and kh > 24:
                    parts.append(_t(kx + kw / 2, ky + kh / 2 - 1, k["name"][: int(kw / 5.5)], size=8, fill="#ffffff"))
                    parts.append(_t(kx + kw / 2, ky + kh / 2 + 9, fmt(k["value"], m["unit"]), size=8, fill="#ffffff"))
        else:
            parts.append(f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{w - 2:.1f}" height="{h - 2:.1f}" fill="{colour}"/>')
            if w > 46 and h > 24:
                parts.append(_t(x + w / 2, y + h / 2 - 1, t["name"][: int(w / 5.5)], size=8, fill="#ffffff", weight="700"))
                parts.append(_t(x + w / 2, y + h / 2 + 9, fmt(t["value"], m["unit"]), size=8, fill="#ffffff"))
    return _svg(W, H, parts)


def _radar(m) -> str:
    """Each dimension a spoke from zero to the scale's top; each series a shape."""
    n = len(m["labels"])
    cx, cy, r = 320, 135, 105
    mx = m["max"] or 1

    def pt(i, v):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * v / mx * math.cos(a), cy + r * v / mx * math.sin(a)

    parts = []
    for k in (0.25, 0.5, 0.75, 1):
        ring = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, mx * k) for i in range(n)))
        parts.append(f'<polygon points="{ring}" fill="none" stroke="{LINE}" stroke-width="0.8"/>')
    for i, label in enumerate(m["labels"]):
        x, y = pt(i, mx)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{LINE}" stroke-width="0.8"/>')
        lx, ly = pt(i, mx * 1.12)
        anchor = "middle" if abs(lx - cx) < 8 else "start" if lx > cx else "end"
        parts.append(_t(lx, ly + 3, label[:24], anchor, fill=INK2))
    parts.append(_t(cx + 4, cy - r - 2 + 10, tick(mx, m["unit"]), "start", size=7))
    for si, s in enumerate(m["series"]):
        c = COLS[si % len(COLS)]
        shape = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, v) for i, v in enumerate(s["values"])))
        parts.append(f'<polygon points="{shape}" fill="{c}" fill-opacity="0.16" stroke="{c}" stroke-width="2"/>')
    return _svg(640, 270, parts)


def _table(m) -> str:
    """The chart's figures as a plain table: what goes in when a drawing cannot."""
    if m["type"] == "gauge":
        g = m["gauge"]
        tgt = f'<td class="n">{escape(fmt(g["target"], m["unit"]))}</td>' if g["target"] is not None else "<td></td>"
        return (f"<table><thead><tr><th></th><th>Figure</th><th>Target</th></tr></thead><tbody><tr>"
                f'<td>{escape(g["label"] or m["title"])}</td><td class="n">{escape(fmt(g["value"], m["unit"]))}</td>'
                f"{tgt}</tr></tbody></table>")
    if m["type"] == "treemap":
        rows = "".join(
            f'<tr><td>{escape(t["name"])}</td><td class="n">{escape(fmt(t["value"], m["unit"]))}</td></tr>'
            + "".join(f'<tr><td>&nbsp;&nbsp;{escape(k["name"])}</td><td class="n">{escape(fmt(k["value"], m["unit"]))}</td></tr>'
                      for k in t.get("children", []))
            for t in m["tree"])
        return f"<table><tbody>{rows}</tbody></table>"
    s = m["series"]
    units = [m["unit2"] or m["unit"] if i == 1 and m["type"] in ("combo", "scatter", "bubble")
             else m.get("unit3", "") if i == 2 and m["type"] == "bubble" else m["unit"] for i in range(len(s))]
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
