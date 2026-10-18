/**
 * Charts and figure cards inside an analyst answer, drawn as SVG and DOM nodes.
 *
 * The analyst writes them as fenced blocks in its markdown:
 *
 *   ```figures                         ```chart
 *   [{"label": "Owed to us",          {"type": "bar" | "line" | "donut",
 *     "value": "GHS 9.18M",             "title": "...", "unit": "GHS",
 *     "note": "806 invoices",           "labels": ["...", ...],
 *     "tone": "bad"}]                   "series": [{"name": "...", "values": [..]}]}
 *
 * The block is data, not markup: it is parsed as JSON, checked, capped, and drawn
 * here -- nothing in it is ever treated as HTML. A block that does not parse, or
 * whose numbers are not numbers, is not drawn at all rather than drawn wrong. The
 * system prompt requires every number in a block to come from a tool result.
 */

const NS = "http://www.w3.org/2000/svg";
const MAX_ITEMS = 12;
const MAX_POINTS = 36;

export function renderBlock(lang, source) {
  let data;
  try {
    data = JSON.parse(source);
  } catch {
    return null;
  }
  if (lang === "figures") return figures(data);
  if (lang === "chart") return chart(data);
  return null;
}

/* ------------------------------------------------------------------ figures */
function figures(list) {
  if (!Array.isArray(list) || !list.length) return null;
  const row = el("div", "md-figs");
  list.slice(0, 4).forEach((f) => {
    if (!f || typeof f !== "object" || f.value === undefined) return;
    const card = el("div", `md-fig${f.tone ? ` t-${String(f.tone).replace(/\W/g, "")}` : ""}`);
    card.append(el("span", "md-fig-l", String(f.label || "")));
    card.append(el("b", "md-fig-v", String(f.value)));
    if (f.note) card.append(el("span", "md-fig-n", String(f.note)));
    row.append(card);
  });
  return row.childNodes.length ? row : null;
}

/* -------------------------------------------------------------------- chart */
function chart(spec) {
  if (!spec || typeof spec !== "object") return null;
  const labels = (Array.isArray(spec.labels) ? spec.labels : []).map(String);
  const series = (Array.isArray(spec.series) ? spec.series : [])
    .filter((s) => s && Array.isArray(s.values))
    .slice(0, 3)
    .map((s) => ({ name: String(s.name || ""), values: s.values.map(Number) }));
  if (!labels.length || !series.length) return null;
  if (series.some((s) => s.values.some((v) => !Number.isFinite(v)))) return null;

  const wrap = el("figure", "md-chart");
  if (spec.title) wrap.append(el("figcaption", "", String(spec.title)));
  const unit = spec.unit ? String(spec.unit) : "";
  const type = ["bar", "line", "donut"].includes(spec.type) ? spec.type : "bar";
  const body =
    type === "line" ? line(labels.slice(0, MAX_POINTS), series, unit)
      : type === "donut" ? donut(labels.slice(0, 6), series[0].values.slice(0, 6), unit)
        : bars(labels.slice(0, MAX_ITEMS), series[0].values.slice(0, MAX_ITEMS), unit);
  if (!body) return null;
  wrap.append(body);
  if (type === "line" && series.length > 1) wrap.append(legend(series.map((s) => s.name)));
  return wrap;
}

/** Horizontal bars, largest first as given: the clearest way to compare names. */
function bars(labels, values, unit) {
  const max = Math.max(...values.map(Math.abs), 0) || 1;
  const box = el("div", "md-bars");
  labels.forEach((l, i) => {
    const v = values[i] ?? 0;
    const row = el("div", "md-bar");
    row.append(el("span", "md-bar-l", l));
    const track = el("span", "md-bar-t");
    const fill = el("i");
    fill.style.width = `${Math.max(1.5, (Math.abs(v) / max) * 100)}%`;
    track.append(fill);
    row.append(track, el("span", "md-bar-v", fmt(v, unit)));
    box.append(row);
  });
  return box;
}

/** A line over time, with the area under the first series and three gridlines. */
function line(labels, series, unit) {
  const W = 640, H = 220, L = 8, R = 8, T = 14, B = 26;
  const all = series.flatMap((s) => s.values.slice(0, labels.length));
  const lo = Math.min(0, ...all), hi = Math.max(...all) || 1;
  const x = (i) => L + (labels.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (labels.length - 1));
  const y = (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "md-line", role: "img" });
  [0, 0.5, 1].forEach((f) => {
    const gy = T + (H - T - B) * f;
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: gy, y2: gy, class: "md-grid" }));
    const t = svgEl("text", { x: W - R, y: gy - 4, class: "md-axis", "text-anchor": "end" });
    t.textContent = fmt(hi - (hi - lo) * f, unit);
    svg.append(t);
  });
  series.forEach((s, si) => {
    const pts = s.values.slice(0, labels.length).map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    if (si === 0 && pts.length > 1) {
      svg.append(svgEl("path", {
        d: `M${x(0)},${y(lo)} L${pts.join(" L")} L${x(pts.length - 1)},${y(lo)} Z`, class: "md-area",
      }));
    }
    svg.append(svgEl("polyline", { points: pts.join(" "), class: `md-ln s${si}` }));
    const last = s.values.length - 1;
    if (last >= 0 && last < labels.length) {
      svg.append(svgEl("circle", { cx: x(last), cy: y(s.values[last]), r: 3.5, class: `md-pt s${si}` }));
    }
  });
  const step = Math.ceil(labels.length / 8);
  labels.forEach((l, i) => {
    if (i % step && i !== labels.length - 1) return;
    const t = svgEl("text", { x: x(i), y: H - 8, class: "md-axis", "text-anchor": "middle" });
    t.textContent = l.length > 9 ? l.slice(0, 9) : l;
    svg.append(t);
  });
  return svg;
}

/** Shares of a whole, with the percentages said in the legend. */
function donut(labels, values, unit) {
  const total = values.reduce((a, b) => a + Math.max(0, b), 0);
  if (!total) return null;
  const box = el("div", "md-donut");
  const svg = svgEl("svg", { viewBox: "0 0 120 120", role: "img" });
  let a0 = -Math.PI / 2;
  values.forEach((v, i) => {
    const a1 = a0 + (Math.max(0, v) / total) * Math.PI * 2;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (a, r) => `${60 + r * Math.cos(a)},${60 + r * Math.sin(a)}`;
    svg.append(svgEl("path", {
      d: `M${p(a0, 52)} A52,52 0 ${large} 1 ${p(a1 - 0.0001, 52)} L${p(a1 - 0.0001, 32)} A32,32 0 ${large} 0 ${p(a0, 32)} Z`,
      class: `md-sl c${i}`,
    }));
    a0 = a1;
  });
  // The total in the hole, the currency on a small line under it so both fit.
  const tot = svgEl("text", { x: 60, y: unit && unit !== "%" ? 61 : 64, "text-anchor": "middle", class: "md-dt" });
  tot.textContent = fmt(total, unit === "%" ? "%" : "");
  svg.append(tot);
  if (unit && unit !== "%") {
    const u = svgEl("text", { x: 60, y: 75, "text-anchor": "middle", class: "md-axis" });
    u.textContent = unit;
    svg.append(u);
  }
  const leg = el("div", "md-legend col");
  labels.forEach((l, i) => {
    const item = el("span", "");
    item.append(el("i", `c${i}`), el("span", "", l),
      el("b", "", `${((Math.max(0, values[i]) / total) * 100).toFixed(1)}%`));
    leg.append(item);
  });
  box.append(svg, leg);
  return box;
}

function legend(names) {
  const leg = el("div", "md-legend");
  names.forEach((n, i) => {
    const item = el("span", "");
    item.append(el("i", `s${i}`), el("span", "", n));
    leg.append(item);
  });
  return leg;
}

/** 9,177,568 -> "GHS 9.18M"; small numbers kept exact. */
function fmt(v, unit) {
  const a = Math.abs(v);
  const s = a >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(v / 1e6).toFixed(2)}M`
    : a >= 1e4 ? `${(v / 1e3).toFixed(1)}k` : Number.isInteger(v) ? v.toLocaleString("en-GB")
      : v.toLocaleString("en-GB", { maximumFractionDigits: 1 });
  return unit === "%" ? `${s}%` : unit ? `${unit} ${s}` : s;
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function svgEl(tag, attrs) {
  const n = document.createElementNS(NS, tag);
  Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, String(v)));
  return n;
}
