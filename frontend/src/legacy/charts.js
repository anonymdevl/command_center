/**
 * Charts and figure cards inside an analyst answer.
 *
 * The analyst writes them as fenced blocks in its markdown:
 *
 *   ```figures                         ```chart
 *   [{"label": "Owed to us",          {"type": "bar", "title": "...", "unit": "GHS",
 *     "value": "GHS 9.18M",             "labels": ["...", ...],
 *     "note": "806 invoices",           "series": [{"name": "...", "values": [..]}]}
 *     "tone": "bad"}]
 *
 * Types: bar, line, donut (read as they always were: lenient), and, read strictly,
 * hbar, stacked, grouped, combo, scatter, pie, rose, area, stacked_area, percentage,
 * waterfall, funnel, gauge, heatmap, treemap, radar, bubble. A type nobody knows is
 * drawn as bars, as before.
 *
 * The block is data, not markup: it is parsed as JSON, checked, capped, and handed to
 * viz.js, which draws it -- nothing in it is ever treated as HTML. A block that does
 * not parse, or whose numbers are not numbers, is not drawn at all rather than drawn
 * wrong. The strict types are checked to the letter -- every value a real number, one
 * per label, the right number of series -- because each draws series against each
 * other, and a missing or misplaced value would put a figure against the wrong name.
 * The scales are honest: bar axes include zero, stacked shapes refuse negatives, a
 * waterfall must add up (each total equals the running level before it is drawn), a
 * treemap's parts may not exceed their parent, and a share of a whole with more than
 * seven parts keeps its six largest and combines the rest as Other rather than
 * dropping them (which would inflate every share shown).
 *
 * The system prompt requires every number in a block to come from a tool result.
 */

import { createViz } from "./viz.js";
import { scale, tick } from "./vizoptions.js";

const MAX_ITEMS = 12;
const MAX_POINTS = 36;
const MAX_COLUMNS = 24; // stacked and combo: a two-year monthly run
const MAX_SERIES = 4; // stacked and grouped
const MAX_SCATTER = 40;
const MAX_SHARES = 7; // pie, donut, rose: beyond this the smallest become "Other"
const LEGACY = ["bar", "line", "donut"];

/**
 * The strict types: how many series (fewest, most), how many labels are drawn (cap:
 * the rest are left out and the chart says so) or allowed at all (most_labels: a
 * block with more is refused, where leaving some out would make it wrong), and what
 * the values may be.
 */
const RULES = {
  hbar: { fewest: 1, most: 1, cap: MAX_ITEMS },
  stacked: { fewest: 1, most: MAX_SERIES, cap: MAX_COLUMNS, nonneg: true },
  grouped: { fewest: 1, most: MAX_SERIES, cap: MAX_ITEMS },
  combo: { fewest: 2, most: 2, cap: MAX_COLUMNS },
  scatter: { fewest: 2, most: 2, cap: MAX_SCATTER },
  pie: { fewest: 1, most: 1, share: true, nonneg: true, most_labels: 40 },
  rose: { fewest: 1, most: 1, share: true, nonneg: true, most_labels: 40 },
  area: { fewest: 1, most: 3, cap: MAX_POINTS },
  stacked_area: { fewest: 1, most: MAX_SERIES, cap: MAX_POINTS, nonneg: true },
  percentage: { fewest: 1, most: 6, cap: MAX_COLUMNS, nonneg: true },
  waterfall: { fewest: 1, most: 1, most_labels: 20 },
  funnel: { fewest: 1, most: 1, cap: 8, nonneg: true },
  heatmap: { fewest: 1, most: 24, cap: 31 },
  radar: { fewest: 1, most: MAX_SERIES, fewest_labels: 3, most_labels: 10, nonneg: true },
  bubble: { fewest: 3, most: 3, cap: MAX_SCATTER },
};
export const CHART_TYPES = [...LEGACY, ...Object.keys(RULES), "gauge", "treemap"];

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

/**
 * A chart block, checked and capped, as the plain data that is drawn -- or null when
 * the block must not be drawn. Exported so the checks can be tested without a page and
 * so a copied answer can say a chart's figures in words.
 */
export function chartModel(spec) {
  if (!spec || typeof spec !== "object" || Array.isArray(spec)) return null;
  if (spec.type === "gauge") return gaugeModel(spec);
  if (spec.type === "treemap") return treemapModel(spec);
  if (RULES[spec.type]) return strictModel(spec);
  return legacyModel(spec);
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

/* ------------------------------------------------------------------- models */
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const str = (v) => (v === undefined || v === null ? "" : String(v));
const okLabel = (l) => (typeof l === "string" || isNum(l)) && String(l).trim() !== "";

function base(spec, type) {
  return {
    type, title: str(spec.title), unit: str(spec.unit), unit2: str(spec.unit2),
    unit3: str(spec.unit3), note: "",
  };
}

function legacyModel(spec) {
  const labels = (Array.isArray(spec.labels) ? spec.labels : []).map(String);
  const series = (Array.isArray(spec.series) ? spec.series : [])
    .filter((s) => s && Array.isArray(s.values))
    .slice(0, 3)
    .map((s) => ({ name: String(s.name || ""), values: s.values.map(Number) }));
  if (!labels.length || !series.length) return null;
  if (series.some((s) => s.values.some((v) => !Number.isFinite(v)))) return null;
  const type = LEGACY.includes(spec.type) ? spec.type : "bar";
  const m = base(spec, type);
  m.unit2 = "";
  if (type === "donut") {
    // Shares of a whole: negatives count as nothing, as they always did.
    const values = labels.map((_, i) => Math.max(0, series[0].values[i] ?? 0));
    if (!values.some((v) => v > 0)) return null;
    return fold({ ...m, labels, series: [{ name: series[0].name, values }], total: labels.length });
  }
  const cap = type === "line" ? MAX_POINTS : MAX_ITEMS;
  const shown = labels.slice(0, cap);
  const out = type === "bar" ? [series[0]] : series;
  return withCap({
    ...m, labels: shown, total: labels.length,
    series: out.map((s) => ({ name: s.name, values: shown.map((_, i) => (i < s.values.length ? s.values[i] : null)) })),
  });
}

function strictModel(spec) {
  const type = spec.type;
  const rule = RULES[type];
  const labels = spec.labels;
  if (!Array.isArray(labels) || !labels.length || !labels.every(okLabel)) return null;
  if (rule.fewest_labels && labels.length < rule.fewest_labels) return null;
  if (rule.most_labels && labels.length > rule.most_labels) return null;
  const raw = spec.series;
  if (!Array.isArray(raw) || raw.length < rule.fewest || raw.length > rule.most) return null;
  const series = [];
  for (const [i, s] of raw.entries()) {
    if (!s || typeof s !== "object" || !Array.isArray(s.values) || s.values.length !== labels.length) return null;
    if (!s.values.every(isNum)) return null;
    const name = String(s.name ?? "").trim() || (raw.length > 1 ? `Series ${i + 1}` : "");
    series.push({ name, values: s.values.slice() });
  }
  if (rule.nonneg && series.some((s) => s.values.some((v) => v < 0))) return null;
  if (type === "bubble" && series[2].values.some((v) => v < 0)) return null;

  let names = labels.map(String);
  const m = base(spec, type);
  if (type === "hbar") {
    // A ranking: largest first, so the rank beside each name is true whatever order
    // the block came in.
    const order = names.map((_, i) => i).sort((a, b) => series[0].values[b] - series[0].values[a]);
    names = order.map((i) => names[i]);
    series[0].values = order.map((i) => series[0].values[i]);
  }
  if (rule.share) {
    if (!series[0].values.some((v) => v > 0)) return null;
    return fold({ ...m, labels: names, series, total: names.length });
  }
  if (type === "waterfall") return waterfall(spec, m, names, series[0]);
  if (type === "radar") {
    const top = Math.max(...series.flatMap((s) => s.values), 0);
    let max = spec.max;
    if (max !== undefined && (!isNum(max) || max <= 0 || max < top)) return null;
    if (max === undefined) max = m.unit === "%" && top <= 100 ? 100 : scale(0, top).hi;
    return { ...m, labels: names, series, total: names.length, max };
  }
  const cap = rule.cap || names.length;
  const n = Math.min(names.length, cap);
  return withCap({
    ...m, labels: names.slice(0, n), series: series.map((s) => ({ ...s, values: s.values.slice(0, n) })),
    total: names.length,
  });
}

function withCap(m) {
  if (m.total > m.labels.length) m.note = `Showing the first ${m.labels.length} of ${m.total}.`;
  return m;
}

/** Shares of a whole: up to seven parts as they are; beyond, the six largest and "Other". */
function fold(m) {
  const values = m.series[0].values;
  if (m.labels.length <= MAX_SHARES) return m;
  const keep = values.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).slice(0, MAX_SHARES - 1)
    .map(([, i]) => i).sort((a, b) => a - b);
  const rest = m.labels.length - keep.length;
  const other = values.reduce((a, v, i) => (keep.includes(i) ? a : a + v), 0);
  return {
    ...m,
    labels: [...keep.map((i) => m.labels[i]), `Other (${rest})`],
    series: [{ ...m.series[0], values: [...keep.map((i) => values[i]), other] }],
    other: true,
    note: `The ${rest} smallest are combined as Other.`,
  };
}

/**
 * A bridge from one level to another: "totals" names the bars that are levels (by
 * index; the first and last unless said), every other bar is a movement from the level
 * before it. Each level after the first must equal the running level -- a bridge that
 * does not add up is not drawn.
 */
function waterfall(spec, m, names, s) {
  const n = names.length;
  let totals = spec.totals === undefined ? (n > 1 ? [0, n - 1] : [0]) : spec.totals;
  if (!Array.isArray(totals) || !totals.every((t) => Number.isInteger(t) && t >= 0 && t < n)) return null;
  totals = [...new Set(totals)];
  if (!totals.includes(0)) return null;
  const isTotal = names.map((_, i) => totals.includes(i));
  const values = s.values;
  const span = Math.max(...values.map(Math.abs), 1);
  const tol = Math.max(0.01, span * 0.005);
  let level = 0;
  const bars = [];
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (isTotal[i]) {
      if (i > 0 && Math.abs(level - v) > tol) return null;
      level = v;
      bars.push({ low: Math.min(0, v), high: Math.max(0, v), end: v, kind: "total" });
    } else {
      const next = level + v;
      bars.push({ low: Math.min(level, next), high: Math.max(level, next), end: next, kind: v < 0 ? "down" : "up" });
      level = next;
    }
  }
  return { ...m, labels: names, series: [{ name: s.name, values }], total: n, bars, totals: isTotal };
}

/** One figure against its scale and, when given, its target. */
function gaugeModel(spec) {
  const value = spec.value;
  if (!isNum(value)) return null;
  const m = base(spec, "gauge");
  const min = spec.min === undefined ? 0 : spec.min;
  let max = spec.max;
  if (max === undefined && m.unit === "%") max = 100;
  if (!isNum(min) || !isNum(max) || max <= min) return null;
  const target = spec.target;
  if (target !== undefined && target !== null && !isNum(target)) return null;
  const better = spec.better === "lower" ? "lower" : "higher";
  const label = str(spec.label) || m.title;
  const off = value < min || value > max;
  return {
    ...m, labels: [label || "Value"], series: [{ name: label, values: [value] }], total: 1,
    gauge: { value, min, max, target: isNum(target) ? target : null, better, label },
    note: off ? `The figure is off the scale (${min} to ${max}); it is shown at the end.` : "",
  };
}

/**
 * What a whole is made of, two levels deep: "items" [{name, value, children: [{name,
 * value}]}], or labels + one series for a single level. A parent's value may be left
 * out (its parts are added up); given, its parts may not exceed it, and what they do
 * not account for is shown as "Not broken down" rather than left as blank space.
 */
function treemapModel(spec) {
  const m = base(spec, "treemap");
  let items;
  if (Array.isArray(spec.items)) {
    items = spec.items;
  } else if (Array.isArray(spec.labels) && Array.isArray(spec.series) && spec.series.length === 1
    && Array.isArray(spec.series[0]?.values) && spec.series[0].values.length === spec.labels.length) {
    items = spec.labels.map((name, i) => ({ name, value: spec.series[0].values[i] }));
  } else {
    return null;
  }
  if (!items.length || items.length > 200) return null;
  const tree = [];
  for (const it of items) {
    if (!it || typeof it !== "object" || !okLabel(it.name)) return null;
    let kids = null;
    if (it.children !== undefined) {
      if (!Array.isArray(it.children) || !it.children.length || it.children.length > 100) return null;
      kids = [];
      for (const c of it.children) {
        if (!c || typeof c !== "object" || !okLabel(c.name) || !isNum(c.value) || c.value < 0) return null;
        if (c.children !== undefined) return null;
        kids.push({ name: String(c.name), value: c.value });
      }
    }
    const sum = kids ? kids.reduce((a, c) => a + c.value, 0) : null;
    let value = it.value;
    if (value === undefined && kids) value = sum;
    if (!isNum(value) || value < 0) return null;
    if (kids) {
      const tol = Math.max(0.01, value * 0.005);
      if (sum > value + tol) return null;
      if (value - sum > tol) kids.push({ name: "Not broken down", value: value - sum, rest: true });
      kids = foldList(kids, 15);
    }
    tree.push({ name: String(it.name), value, ...(kids ? { children: kids } : {}) });
  }
  if (!tree.some((t) => t.value > 0)) return null;
  const top = foldList(tree.sort((a, b) => b.value - a.value), 30);
  const note = top.length < tree.length ? `The ${tree.length - top.length + 1} smallest are combined as Other.` : "";
  return {
    ...m, tree: top, labels: top.map((t) => t.name), series: [{ name: m.title, values: top.map((t) => t.value) }],
    total: top.length, note,
  };
}

function foldList(list, most) {
  if (list.length <= most) return list;
  const sorted = [...list].sort((a, b) => b.value - a.value);
  const keep = sorted.slice(0, most - 1);
  const rest = sorted.slice(most - 1);
  return [...keep, { name: `Other (${rest.length})`, value: rest.reduce((a, x) => a + x.value, 0), rest: true }];
}

/* -------------------------------------------------------------------- chart */
function chart(spec) {
  const m = chartModel(spec);
  if (!m) return null;
  const wrap = el("figure", "md-chart");
  if (m.title) wrap.append(el("figcaption", "", m.title));
  // The view chosen is remembered for this chart (by its title), not for every chart of its type.
  const viz = createViz(m, { key: m.title ? `answer:${m.type}:${m.title}` : null, title: m.title });
  wrap.append(viz.node);
  if (m.note) wrap.append(el("div", "md-chart-note", m.note));
  return wrap;
}

// The axis helpers live with the chart options; re-exported for the tests and callers.
export { scale, tick };

/* ----------------------------------------------------------------- builders */
function el(tag, cls, t) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (t !== undefined) n.textContent = t;
  return n;
}
