/**
 * What every chart on the platform looks like: a checked chart model (charts.js for an
 * answer, panels.js for a screen) and a view ("bar", "donut", "table" ...) in, an
 * Apache ECharts option out.
 *
 * Pure -- no DOM, no ECharts import -- so it is tested in Node (scripts/test_charts.mjs)
 * and viz.js only has to mount the result. The colours come in as the theme's tokens
 * (viz.js reads them from the stylesheet), never written here, so a chart is right in
 * both themes and every accent.
 *
 * Text from data reaches the page two ways only: as chart text (drawn by ECharts as
 * SVG text, never parsed as markup) and in tooltips, which ECharts writes as HTML --
 * every tooltip here is built by tip(), which escapes each piece. No formatter here is
 * a template string ECharts would expand: each is a function returning plain text.
 */

import { magnitude, exact } from "../format.js";

/* ------------------------------------------------------------------ numbers */
const CURRENCY = /^[A-Z]{3}$/;

/** A round axis that always includes zero: about four steps of 1, 2, 2.5 or 5 x 10^n. */
export function scale(lo, hi, n = 4) {
  lo = Math.min(0, lo);
  hi = Math.max(0, hi);
  if (hi - lo <= 0) hi = lo + 1;
  const raw = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10, 20].map((f) => f * mag)
    .find((s) => Math.ceil(hi / s - 1e-9) - Math.floor(lo / s + 1e-9) <= n) || 20 * mag;
  const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
  const ticks = [];
  for (let t = a; t <= b + step / 2; t += step) ticks.push(Math.abs(t) < step / 1e6 ? 0 : +t.toPrecision(12));
  return { lo: a, hi: b, ticks };
}

/** An axis step, short: "2.5M", "250k", "40%" -- any other unit is said once, by the axis. */
export function tick(v, unit) {
  const a = Math.abs(v);
  const short = (x) => x.toLocaleString("en-GB", { maximumFractionDigits: 2 });
  const s = a >= 1e9 ? `${short(v / 1e9)}B` : a >= 1e6 ? `${short(v / 1e6)}M`
    : a >= 1e4 ? `${short(v / 1e3)}k` : short(v);
  return unit === "%" ? `${s}%` : s;
}

/** A figure on a chart: "GHS 9.18M", "73.8%", "118 days", "1,204". */
export function short(v, unit = "") {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return "—";
  const n = Number(v);
  if (CURRENCY.test(unit)) {
    // As the cards write money ("GHS 9.18M"), with thousands to one place and no
    // trailing zeros ("GHS 412k", "GHS 288.5k").
    const { value, suffix, digits } = magnitude(n, (sfx) => (sfx === "k" ? 1 : sfx ? 2 : 0));
    const p = 10 ** digits;
    return `${unit} ${(Math.round(value * p) / p || 0).toLocaleString("en-GB", { maximumFractionDigits: digits })}${suffix}`;
  }
  const a = Math.abs(n);
  const s = a >= 1e9 ? `${(n / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(n / 1e6).toFixed(2)}M`
    : a >= 1e4 ? `${(n / 1e3).toFixed(1)}k`
      : n.toLocaleString("en-GB", { maximumFractionDigits: 1 });
  return withUnitWord(s, unit);
}

/** The figure in full, for hovering and tables: "GHS 1,234,567.50". */
export function full(v, unit = "") {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return "—";
  const n = Number(v);
  if (CURRENCY.test(unit)) return `${unit} ${exact(n)}`;
  return withUnitWord(n.toLocaleString("en-GB", { maximumFractionDigits: 2 }), unit);
}

function withUnitWord(s, unit) {
  if (!unit) return s;
  if (unit === "%") return `${s}%`;
  return CURRENCY.test(unit) ? `${unit} ${s}` : `${s} ${unit}`;
}

const pct = (part, whole) => (whole ? `${((100 * part) / whole).toFixed(1)}%` : "—");
const named = (name, unit) => (unit && name ? `${name} (${unit})` : name || unit || "");
const cut = (s, n) => (String(s).length > n ? `${String(s).slice(0, n - 1)}…` : String(s));

/* ------------------------------------------------------------------- colour */
/** A colour with an alpha, from #rgb, #rrggbb or rgb(); anything else is returned as is. */
export function alpha(c, a) {
  const rgb = toRgb(c);
  return rgb ? `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})` : c;
}

/** a toward b by t (0..1), for ramps between a series colour and the surface. */
export function mix(a, b, t) {
  const x = toRgb(a), y = toRgb(b);
  if (!x || !y) return a;
  const c = x.map((v, i) => Math.round(v + (y[i] - v) * t));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function toRgb(c) {
  const s = String(c || "").trim();
  let m = s.match(/^#([0-9a-f]{3})$/i);
  if (m) return m[1].split("").map((h) => parseInt(h + h, 16));
  m = s.match(/^#([0-9a-f]{6})/i);
  if (m) return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16));
  m = s.match(/^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i);
  return m ? [1, 2, 3].map((i) => Number(m[i])) : null;
}

/** Only a colour may go into a style attribute in a tooltip. */
const safeColour = (c) => (/^(#[0-9a-f]{3,8}|rgba?\([\d.,\s%]+\))$/i.test(String(c).trim()) ? String(c).trim() : "currentColor");

/* ------------------------------------------------------------------ escaping */
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** A tooltip: a heading and rows of [colour, name, value, extra] -- each piece escaped. */
function tip(head, rows) {
  const out = head ? [`<div class="vz-tt-h">${esc(head)}</div>`] : [];
  rows.forEach(([colour, name, value, extra]) => {
    const dot = colour ? `<i class="vz-tt-k" style="background:${safeColour(colour)}"></i>` : "";
    out.push(`<div class="vz-tt-r">${dot}<span class="vz-tt-n">${esc(name)}</span>`
      + `<b class="vz-tt-v">${esc(value)}</b></div>`);
    if (extra) out.push(`<div class="vz-tt-x">${esc(extra)}</div>`);
  });
  return out.join("");
}

/* -------------------------------------------------------------------- views */
export const VIEW_LABELS = {
  bar: "Bar", hbar: "Bar", line: "Line", area: "Area", stacked_area: "Stacked area", pie: "Pie",
  donut: "Donut", rose: "Rose", stacked: "Stacked", grouped: "Side by side", percentage: "100%",
  combo: "Combo", scatter: "Scatter", bubble: "Bubble", waterfall: "Bridge", funnel: "Funnel",
  gauge: "Gauge", heatmap: "Heatmap", treemap: "Treemap", radar: "Radar", strip: "Stacked", table: "Table",
};

const MONTH = /^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?(\s*'?\d{2,4})?$/i;
const PERIOD = /^((19|20)\d{2}([-/]\d{1,2}([-/]\d{1,2})?)?|q[1-4]\s*'?\d{0,4}|\d{1,2}\s+[a-z]{3,9}(\s+\d{2,4})?|(week|wk|w)\s*\d+.*|h[12]\s*\d{0,4}|fy\s*\d{2,4})$/i;

/** Whether the labels run along time (months, years, quarters, dates): line and area then make sense. */
export function timeLike(labels) {
  if (!labels.length) return false;
  const hits = labels.filter((l) => MONTH.test(String(l).trim()) || PERIOD.test(String(l).trim())).length;
  return hits / labels.length >= 0.6;
}

const longNames = (labels) => labels.some((l) => String(l).length > 12) || labels.length > 8;
const nonNeg = (m) => m.series.every((s) => s.values.every((v) => v === null || v >= 0));

/** The views a chart offers in its switcher, its own first. */
export function viewsFor(m) {
  const time = m.time ?? timeLike(m.labels);
  const one = m.series.length === 1;
  const positive = nonNeg(m);
  const sharesOk = m.shares !== false && one && positive && m.labels.length <= 12
    && m.series[0].values.some((v) => v > 0);
  const many = m.series.length > 1;
  switch (m.type) {
    case "bar": case "hbar": {
      const b = m.type === "hbar" || longNames(m.labels) ? "hbar" : "bar";
      return [b, ...(time ? ["line", "area"] : []), ...(sharesOk && !time ? ["donut", "pie"] : []), "table"];
    }
    case "pie": case "donut": case "rose":
      return [m.type, ...["donut", "pie", "rose"].filter((t) => t !== m.type), "hbar", "table"];
    case "line": case "area":
      return [m.type, m.type === "line" ? "area" : "line", ...(many && positive ? ["stacked_area"] : []),
        many ? "grouped" : "bar", "table"];
    case "stacked_area":
      return ["stacked_area", "line", "stacked", "percentage", "table"];
    case "stacked":
      return ["stacked", "grouped", "percentage", ...(time ? ["stacked_area"] : []), "table"];
    case "grouped":
      return ["grouped", ...(positive ? ["stacked", "percentage"] : []), ...(time ? ["line"] : []), "table"];
    case "percentage":
      return ["percentage", "stacked", "grouped", "table"];
    case "funnel":
      return ["funnel", "hbar", "table"];
    case "treemap":
      return ["treemap", "hbar", "table"];
    case "radar":
      return ["radar", "grouped", "table"];
    case "strip":
      return ["strip", "donut", "hbar", "table"];
    default:
      return [m.type, "table"];
  }
}

/* ------------------------------------------------------------------- frame */
/** How tall a view is drawn, at this width. */
export function heightFor(m, view, width = 640, compact = false) {
  const n = m.labels.length;
  const legend = m.series.length > 1 ? 28 : 0;
  const wide = width >= 460;
  switch (view) {
    case "hbar": return Math.max(compact ? 96 : 120, n * (compact ? 30 : 32) + (compact ? 10 : 40));
    case "pie": case "donut": case "rose": return wide ? (compact ? 220 : 250) : 226 + Math.min(n, 7) * 24;
    case "funnel": return Math.max(150, n * 48 + 16);
    case "gauge": return 250;
    case "heatmap": return m.series.length * 30 + 84;
    case "treemap": return compact ? 230 : 320;
    case "radar": return wide ? 320 : 290;
    case "scatter": case "bubble": return 310;
    case "waterfall": return compact ? 220 : 290;
    case "strip": return 46;
    default: return (compact ? 190 : 270) + legend;
  }
}

function common(T, compact) {
  return {
    backgroundColor: "transparent",
    animationDuration: 650,
    animationEasing: "cubicOut",
    animationDurationUpdate: 450,
    animationEasingUpdate: "cubicInOut",
    textStyle: { fontFamily: T.font, color: T.ink2, fontSize: 12 },
    tooltip: {
      confine: true, backgroundColor: T.surface, borderColor: T.line2, borderWidth: 1, padding: [8, 11],
      textStyle: { color: T.ink, fontSize: 12, fontFamily: T.font },
      extraCssText: "border-radius:10px;box-shadow:0 10px 28px -12px rgba(0,0,0,.38);",
      transitionDuration: 0.15,
    },
    _compact: compact,
  };
}

function legend(T, names, extra = {}) {
  return {
    show: names.length > 1, data: names, bottom: 0, left: "center", icon: "roundRect", itemWidth: 10,
    itemHeight: 10, itemGap: 16, textStyle: { color: T.mut, fontSize: 12, fontFamily: T.font },
    inactiveColor: T.line2, ...extra,
  };
}

function catAxis(T, labels, extra = {}) {
  return {
    type: "category", data: labels, axisTick: { show: false },
    axisLine: { lineStyle: { color: T.line2 } },
    axisLabel: { color: T.mut, fontSize: 11, hideOverlap: true, fontFamily: T.font, formatter: (v) => cut(v, 14) },
    ...extra,
  };
}

function valAxis(T, unit, extra = {}) {
  return {
    type: "value",
    axisLabel: { color: T.mut, fontSize: 11, fontFamily: T.font, formatter: (v) => tick(v, unit) },
    splitLine: { lineStyle: { color: T.line, type: [3, 3] } },
    axisLine: { show: false }, axisTick: { show: false },
    name: unit && unit !== "%" ? unit : "", nameTextStyle: { color: T.mut, fontSize: 11, fontWeight: 600, align: "left" },
    nameGap: 10,
    ...extra,
  };
}

/** One colour per series, in the palette's fixed order -- never by rank. */
const seriesColour = (T, i, count) => (count === 1 ? T.accent : T.palette[i % T.palette.length]);
/**
 * One colour per label (a single series drawn by part). A panel's tones that mean
 * something (under a month is good, over three critical) are kept; otherwise parts
 * take the palette in order (byLabel) or all wear the accent -- and a part the panel
 * dims ("Other locations") stays dim.
 */
function labelColour(m, T, i, byLabel) {
  const tone = m.colors?.[i];
  if (tone && T[tone] && (meaningful(m) || (!byLabel && varied(m)))) return T[tone];
  if (tone === "dim" || (m.other && i === m.labels.length - 1)) return T.dim;
  return byLabel ? T.palette[i % T.palette.length] : T.accent;
}
const varied = (m) => Array.isArray(m.colors) && new Set(m.colors.filter(Boolean)).size > 1;
const STATUS = new Set(["ok", "med", "high", "crit"]);
const meaningful = (m) => Array.isArray(m.colors) && m.colors.some((t) => STATUS.has(t));

/* ------------------------------------------------------------------- build */
/** The ECharts option for this chart, drawn as this view, in these colours. */
export function buildOption(m, view, T, ctx = {}) {
  const c = { width: 640, compact: false, ...ctx };
  const o = common(T, c.compact);
  const make = {
    bar: () => bars(m, T, c, { horizontal: false }),
    hbar: () => bars(m, T, c, { horizontal: true }),
    grouped: () => bars(m, T, c, { horizontal: false, multi: true }),
    stacked: () => bars(m, T, c, { horizontal: false, multi: true, stack: true }),
    percentage: () => bars(m, T, c, { horizontal: false, multi: true, stack: true, percent: true }),
    line: () => lines(m, T, c, {}),
    area: () => lines(m, T, c, { area: true }),
    stacked_area: () => lines(m, T, c, { area: true, stack: true }),
    pie: () => pies(m, T, c, "pie"),
    donut: () => pies(m, T, c, "donut"),
    rose: () => pies(m, T, c, "rose"),
    combo: () => combo(m, T, c),
    scatter: () => points(m, T, c, false),
    bubble: () => points(m, T, c, true),
    waterfall: () => waterfall(m, T, c),
    funnel: () => funnel(m, T, c),
    gauge: () => gauge(m, T, c),
    heatmap: () => heatmap(m, T, c),
    treemap: () => treemap(m, T, c),
    radar: () => radar(m, T, c),
    strip: () => strip(m, T, c),
  }[view];
  if (!make) return null;
  const built = make();
  delete o._compact;
  return { ...o, ...built, tooltip: { ...o.tooltip, ...(built.tooltip || {}) } };
}

/* --------------------------------------------------------------------- bars */
function bars(m, T, c, { horizontal, multi = false, stack = false, percent = false }) {
  const series = multi ? m.series : m.series.slice(0, 1);
  const count = series.length;
  const byLabel = !multi && (varied(m) || ["pie", "donut", "rose", "strip"].includes(m.type));
  const totals = m.labels.map((_, i) => series.reduce((a, s) => a + (s.values[i] || 0), 0));
  const value = (s, i) => (percent ? (totals[i] ? (100 * (s.values[i] || 0)) / totals[i] : 0) : s.values[i]);
  const unit = percent ? "%" : m.unit;
  const n = m.labels.length;
  const rank = m.type === "hbar" && !m.colors;
  // Round the end of each bar away from zero, and only the outer end of a stack.
  const round = (v, topOfStack) => {
    if (stack && !topOfStack) return 0;
    const r = 4;
    if (horizontal) return v < 0 ? [r, 0, 0, r] : [0, r, r, 0];
    return v < 0 ? [0, 0, r, r] : [r, r, 0, 0];
  };
  const label = (i) => {
    if (m.displays?.[i] !== undefined && m.displays?.[i] !== null) {
      return m.notes?.[i] ? `${m.displays[i]}  ·  ${m.notes[i]}` : String(m.displays[i]);
    }
    return short(series[0].values[i], m.unit);
  };
  const showLabels = !multi && (horizontal ? n <= 16 : n <= 8);
  const out = series.map((s, si) => ({
    type: "bar", id: `s${si}`, name: s.name || m.title || "Value",
    stack: stack ? "total" : undefined,
    // The series' own colour too, so its legend key matches its bars.
    itemStyle: { color: multi ? seriesColour(T, si, count) : labelColour(m, T, 0, byLabel) },
    barMaxWidth: horizontal ? (c.compact ? 14 : 16) : multi && !stack ? 24 : 30,
    barCategoryGap: horizontal ? "38%" : "34%",
    barGap: "12%",
    cursor: c.pick ? "pointer" : "default",
    universalTransition: { enabled: true },
    emphasis: { focus: multi ? "series" : "none", itemStyle: { opacity: 0.92 } },
    data: s.values.map((_, i) => {
      const v = value(s, i);
      const topOfStack = !stack || series.slice(si + 1).every((x) => !(x.values[i] > 0));
      const colour = multi ? seriesColour(T, si, count) : labelColour(m, T, i, byLabel);
      return {
        value: v,
        itemStyle: {
          color: colour, borderRadius: round(v, topOfStack),
          ...(stack ? { borderColor: T.surface, borderWidth: 1 } : {}),
        },
      };
    }),
    label: showLabels ? {
      show: true, position: horizontal ? "right" : "top", distance: 6, color: T.ink2, fontSize: 11,
      fontWeight: 600, fontFamily: T.font, formatter: (p) => label(p.dataIndex),
    } : { show: false },
  }));
  const longest = showLabels && horizontal ? Math.max(...m.labels.map((_, i) => label(i).length)) : 0;
  const nameRoom = Math.min(Math.round(c.width * (c.width < 460 ? 0.34 : 0.3)), 200);
  const cats = catAxis(T, m.labels, horizontal ? {
    inverse: true,
    axisLine: { show: false },
    axisLabel: {
      color: T.ink2, fontSize: 12, fontFamily: T.font, width: nameRoom, overflow: "truncate",
      formatter: (v, i) => (rank ? `${i + 1}   ${v}` : String(v)),
    },
  } : {});
  const vals = valAxis(T, unit, {
    ...(percent ? { max: 100 } : {}),
    ...(horizontal && (c.compact || showLabels) ? { axisLabel: { show: false }, splitLine: { show: false }, name: "" } : {}),
  });
  const legendOn = multi && count > 1;
  return {
    grid: {
      left: horizontal ? 4 : 8, right: horizontal ? Math.min(12 + longest * 6.6, c.width * 0.42) : 14,
      top: horizontal ? 4 : unit && unit !== "%" ? 30 : 16, bottom: legendOn ? 34 : 6, containLabel: true,
    },
    xAxis: horizontal ? vals : cats,
    yAxis: horizontal ? cats : vals,
    legend: legend(T, series.map((s) => s.name), { show: legendOn }),
    series: out,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: alpha(T.ink, 0.05) } },
      formatter: (ps) => {
        const list = Array.isArray(ps) ? ps : [ps];
        const i = list[0]?.dataIndex ?? 0;
        const rows = series.map((s, si) => [
          multi ? seriesColour(T, si, count) : labelColour(m, T, i, byLabel),
          s.name || m.title || "Value",
          m.displays?.[i] && !multi ? String(m.displays[i]) : full(s.values[i], m.unit),
          percent ? `${pct(s.values[i] || 0, totals[i])} of the column` : (!multi && m.notes?.[i]) || "",
        ]);
        if (stack && count > 1) rows.push(["", "Total", full(totals[i], m.unit), ""]);
        return tip(m.labels[i], rows);
      },
    },
  };
}

/* -------------------------------------------------------------------- lines */
function lines(m, T, c, { area = false, stack = false }) {
  const count = m.series.length;
  const n = m.labels.length;
  const out = m.series.map((s, si) => {
    const colour = seriesColour(T, si, count);
    return {
      type: "line", id: `s${si}`, name: s.name || m.title || "Value",
      stack: stack ? "total" : undefined,
      showSymbol: n <= 14, symbol: "circle", symbolSize: 7, smooth: false, connectNulls: false,
      lineStyle: { width: 2.25, color: colour }, itemStyle: { color: colour, borderColor: T.surface, borderWidth: 2 },
      universalTransition: { enabled: true },
      emphasis: { focus: count > 1 ? "series" : "none", scale: 1.4 },
      areaStyle: area ? (stack ? { color: alpha(colour, 0.55) } : {
        color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: alpha(colour, 0.3) }, { offset: 1, color: alpha(colour, 0.02) }] },
      }) : undefined,
      data: s.values.map((v, i) => (m.peak && m.peak.index === i && si === 0 ? {
        value: v, symbol: "circle", symbolSize: 8,
        label: { show: true, position: "top", color: T.ink2, fontSize: 11, fontWeight: 600, fontFamily: T.font, formatter: () => m.peak.text },
      } : v)),
    };
  });
  const legendOn = count > 1;
  return {
    grid: { left: 8, right: 16, top: m.unit && m.unit !== "%" ? 30 : 18, bottom: legendOn ? 34 : 6, containLabel: true },
    xAxis: catAxis(T, m.labels, { boundaryGap: false }),
    yAxis: valAxis(T, m.unit),
    legend: legend(T, m.series.map((s) => s.name || m.title || "Value"), { show: legendOn }),
    series: out,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: T.line2, width: 1 } },
      formatter: (ps) => {
        const list = Array.isArray(ps) ? ps : [ps];
        const i = list[0]?.dataIndex ?? 0;
        const rows = m.series.map((s, si) => [seriesColour(T, si, count), s.name || m.title || "Value", full(s.values[i], m.unit), ""]);
        if (stack && count > 1) rows.push(["", "Total", full(m.series.reduce((a, s) => a + (s.values[i] || 0), 0), m.unit), ""]);
        return tip(m.labels[i], rows);
      },
    },
  };
}

/* --------------------------------------------------------------------- pies */
/**
 * The parts a pie draws: up to seven as they are; beyond, the six largest and "Other"
 * (never a dropped part, which would inflate every share shown). index maps each slice
 * back to its row (-1 for Other), so a click opens the right records.
 */
export function pieModel(m) {
  const values = m.series[0].values.map((v) => Math.max(0, v || 0));
  if (m.labels.length <= 7) return { ...m, index: m.labels.map((_, i) => (m.other && i === m.labels.length - 1 ? -1 : i)) };
  const keep = values.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).slice(0, 6).map(([, i]) => i).sort((a, b) => a - b);
  const rest = values.length - keep.length;
  const pick = (arr) => (arr ? [...keep.map((i) => arr[i]), undefined] : undefined);
  return {
    ...m, other: true,
    labels: [...keep.map((i) => m.labels[i]), `Other (${rest})`],
    series: [{ ...m.series[0], values: [...keep.map((i) => values[i]), values.reduce((a, v, i) => (keep.includes(i) ? a : a + v), 0)] }],
    displays: pick(m.displays), notes: pick(m.notes),
    colors: m.colors ? [...keep.map((i) => m.colors[i]), "dim"] : undefined,
    index: [...keep, -1],
  };
}

function pies(m0, T, c, kind) {
  const m = pieModel(m0);
  const values = m.series[0].values.map((v) => Math.max(0, v || 0));
  const total = values.reduce((a, b) => a + b, 0);
  const wide = c.width >= 460;
  const byLabel = true;
  const ofWhat = ["pie", "donut", "rose", "strip"].includes(m.type) || m.shares === true
    ? "of the total" : "of the total shown";
  const centre = wide ? ["27%", "50%"] : ["50%", 104];
  // A rose is drawn honestly: every petal the same angle, its AREA the figure (the
  // radius is the square root), from the centre -- a radius proportional to the figure
  // would make a part twice as large look four times as big.
  const radius = kind === "donut" ? (wide ? ["52%", "80%"] : [58, 92]) : (wide ? [0, "80%"] : [0, 92]);
  const room = wide ? Math.max(80, c.width * 0.5 - 70) : c.width - 80;
  const out = {
    series: [{
      type: "pie", id: "s0", name: m.series[0].name || m.title || "Value", radius, center: centre,
      roseType: kind === "rose" ? "area" : undefined,
      avoidLabelOverlap: true, label: { show: false }, labelLine: { show: false },
      cursor: c.pick ? "pointer" : "default",
      universalTransition: { enabled: true },
      itemStyle: { borderColor: T.surface, borderWidth: 2, borderRadius: kind === "donut" ? 5 : 3 },
      emphasis: { scale: true, scaleSize: 5, label: { show: false } },
      data: m.labels.map((l, i) => ({ name: l, value: kind === "rose" ? Math.sqrt(values[i]) : values[i],
        itemStyle: { color: labelColour(m, T, i, byLabel) } })),
    }],
    legend: {
      show: true, orient: "vertical", icon: "roundRect", itemWidth: 10, itemHeight: 10, itemGap: 9,
      ...(wide ? { left: "54%", top: "middle" } : { left: 16, top: 214 }),
      data: m.labels,
      // Name and share in two aligned columns. Braces and bars are taken out of the
      // name, the only text ECharts would read as layout in a rich label.
      formatter: (name) => {
        const i = m.labels.indexOf(name);
        const plain = cut(String(name).replace(/[{}|]/g, " "), Math.max(8, Math.floor(room / 7.2) - 6));
        return `{n|${plain}}{p|${pct(values[i] || 0, total)}}`;
      },
      textStyle: {
        color: T.ink2, fontSize: 12, fontFamily: T.font,
        rich: {
          n: { color: T.ink2, fontSize: 12, fontFamily: T.font, width: Math.min(170, Math.max(80, room - 70)) },
          p: { color: T.ink, fontSize: 12, fontWeight: 600, fontFamily: T.font, width: 48, align: "right" },
        },
      },
      inactiveColor: T.line2,
    },
    tooltip: {
      trigger: "item",
      formatter: (p) => tip(p.name, [[labelColour(m, T, p.dataIndex, byLabel), m.series[0].name || "Value",
        m.displays?.[p.dataIndex] ? String(m.displays[p.dataIndex]) : full(values[p.dataIndex], m.unit),
        `${pct(values[p.dataIndex], total)} ${ofWhat}`]]),
    },
  };
  if (kind === "donut") {
    out.title = {
      text: short(total, m.unit), subtext: ofWhat === "of the total" ? "Total" : "Total shown",
      left: centre[0], top: wide ? "middle" : 104 - 20, textAlign: "center", itemGap: 2,
      textStyle: { color: T.ink, fontSize: 15, fontWeight: 700, fontFamily: T.font },
      subtextStyle: { color: T.mut, fontSize: 11, fontFamily: T.font },
    };
  }
  return out;
}

/* -------------------------------------------------------------------- combo */
function combo(m, T, c) {
  const [a, b] = m.series;
  const u2 = m.unit2 || m.unit;
  const dual = m.unit2 !== "" && m.unit2 !== m.unit;
  const ca = T.palette[0], cb = T.palette[1];
  return {
    grid: { left: 8, right: 12, top: 30, bottom: 34, containLabel: true },
    xAxis: catAxis(T, m.labels),
    yAxis: dual ? [valAxis(T, m.unit), valAxis(T, u2, { splitLine: { show: false } })] : valAxis(T, m.unit),
    legend: legend(T, [named(a.name, m.unit), named(b.name, u2)]),
    series: [
      { type: "bar", id: "s0", name: named(a.name, m.unit), barMaxWidth: 28, barCategoryGap: "36%", itemStyle: { color: ca },
        data: a.values.map((v) => ({ value: v, itemStyle: { color: ca, borderRadius: v < 0 ? [0, 0, 4, 4] : [4, 4, 0, 0] } })) },
      { type: "line", id: "s1", name: named(b.name, u2), yAxisIndex: dual ? 1 : 0, data: b.values,
        symbol: "circle", symbolSize: 7, lineStyle: { width: 2.5, color: cb },
        itemStyle: { color: cb, borderColor: T.surface, borderWidth: 2 } },
    ],
    tooltip: {
      trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: alpha(T.ink, 0.05) } },
      formatter: (ps) => {
        const i = (Array.isArray(ps) ? ps : [ps])[0]?.dataIndex ?? 0;
        return tip(m.labels[i], [[ca, a.name || "Amount", full(a.values[i], m.unit), ""], [cb, b.name || "Rate", full(b.values[i], u2), ""]]);
      },
    },
  };
}

/* ------------------------------------------------------------ scatter, bubble */
function points(m, T, c, bubble) {
  const [xs, ys, sz] = m.series;
  const top = bubble ? Math.max(...sz.values, 0) || 1 : 1;
  const size = (v) => Math.max(4, 50 * Math.sqrt(Math.max(0, v) / top));
  const named12 = m.labels.length <= 12;
  return {
    grid: { left: 12, right: 24, top: 34, bottom: 34, containLabel: true },
    xAxis: valAxis(T, m.unit, {
      name: named(xs.name, m.unit), nameLocation: "middle", nameGap: 26,
      nameTextStyle: { color: T.mut, fontSize: 11, fontWeight: 600, align: "center" },
      splitLine: { lineStyle: { color: T.line, type: [3, 3] } },
    }),
    yAxis: valAxis(T, m.unit2, { name: named(ys.name, m.unit2), nameLocation: "end", nameGap: 12 }),
    series: [{
      type: "scatter", id: "s0", name: m.title || "Points",
      data: m.labels.map((l, i) => [xs.values[i], ys.values[i], bubble ? sz.values[i] : 0, l]),
      symbolSize: (d) => (bubble ? size(d[2]) : 11),
      itemStyle: { color: alpha(T.accent, bubble ? 0.62 : 0.85), borderColor: T.surface, borderWidth: 1.5 },
      emphasis: { focus: "self", scale: 1.15, itemStyle: { color: T.accent } },
      label: { show: named12, position: "right", color: T.ink2, fontSize: 11, fontFamily: T.font, formatter: (p) => cut(p.data[3], 18) },
      labelLayout: { hideOverlap: true },
    }],
    tooltip: {
      trigger: "item",
      formatter: (p) => tip(p.data[3], [
        ["", xs.name || "Across", full(p.data[0], m.unit), ""],
        ["", ys.name || "Up", full(p.data[1], m.unit2), ""],
        ...(bubble ? [["", sz.name || "Size", full(p.data[2], m.unit3), ""]] : []),
      ]),
    },
  };
}

/* ---------------------------------------------------------------- waterfall */
function waterfall(m, T, c) {
  const bars = m.bars;
  const values = m.series[0].values;
  const colour = (b) => (b.kind === "total" ? T.accent : b.kind === "up" ? T.ok : T.crit);
  const sign = (v) => (v < 0 ? "−" : "+");
  const text = (i) => (bars[i].kind === "total" ? short(values[i], m.unit) : `${sign(values[i])}${short(Math.abs(values[i]), m.unit)}`);
  return {
    grid: { left: 8, right: 14, top: 34, bottom: 6, containLabel: true },
    xAxis: catAxis(T, m.labels),
    yAxis: valAxis(T, m.unit),
    series: [{
      type: "custom", id: "s0", name: m.title || "Bridge",
      encode: { x: 0, y: [1, 2] },
      data: bars.map((b, i) => [i, b.low, b.high, b.end]),
      renderItem: (params, api) => {
        const i = api.value(0);
        const b = bars[i];
        const lo = api.coord([i, b.low]);
        const hi = api.coord([i, b.high]);
        const bw = Math.min(api.size([1, 0])[0] * 0.58, 56);
        const kids = [{
          type: "rect",
          shape: { x: lo[0] - bw / 2, y: hi[1], width: bw, height: Math.max(1, lo[1] - hi[1]), r: 3 },
          style: { fill: colour(b) },
        }];
        if (i < bars.length - 1) {
          const y = api.coord([i, b.end])[1];
          const nx = api.coord([i + 1, b.end])[0];
          kids.push({ type: "line", shape: { x1: lo[0] + bw / 2, y1: y, x2: nx - bw / 2, y2: y },
            style: { stroke: T.dim, lineWidth: 1, lineDash: [3, 3] } });
        }
        if (bars.length <= 14) {
          kids.push({ type: "text", style: { text: text(i), x: lo[0], y: hi[1] - 5, align: "center", verticalAlign: "bottom",
            fill: T.ink2, fontSize: 11, fontWeight: 600, fontFamily: T.font } });
        }
        return { type: "group", children: kids };
      },
    }],
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        const i = p.dataIndex;
        const b = bars[i];
        return b.kind === "total"
          ? tip(m.labels[i], [[colour(b), "Level", full(values[i], m.unit), ""]])
          : tip(m.labels[i], [[colour(b), b.kind === "up" ? "Increase" : "Decrease", `${sign(values[i])}${full(Math.abs(values[i]), m.unit)}`, ""],
            ["", "Level after", full(b.end, m.unit), ""]]);
      },
    },
  };
}

/* ------------------------------------------------------------------- funnel */
function funnel(m, T, c) {
  const values = m.series[0].values.map((v) => Math.max(0, v || 0));
  const first = values[0] || 0;
  const n = values.length;
  const top = Math.max(...values, 0) || 1;
  const wide = c.width >= 460;
  const count = (i) => values[i];
  const line = (i) => {
    const lead = `${m.labels[i]} · ${m.unit ? short(count(i), m.unit) : Number(count(i)).toLocaleString("en-GB")}`;
    const sub = m.displays?.[i] ? String(m.displays[i]) : i > 0 && first ? `${pct(values[i], first)} of the first stage` : "";
    return sub ? `${lead}\n${sub}` : lead;
  };
  return {
    series: [{
      type: "funnel", id: "s0", name: m.series[0].name || m.title || "Stages", sort: "none", gap: 3,
      left: 6, top: 8, bottom: 8, width: wide ? "52%" : "46%", min: 0, max: top, minSize: "0%",
      cursor: c.pick ? "pointer" : "default",
      label: { show: true, position: "right", color: T.ink2, fontSize: 12, lineHeight: 16, fontFamily: T.font, formatter: (p) => line(p.dataIndex) },
      labelLine: { show: true, length: 12, lineStyle: { color: T.line2 } },
      itemStyle: { borderColor: T.surface, borderWidth: 1, borderRadius: 3 },
      emphasis: { label: { fontWeight: 700 } },
      data: m.labels.map((l, i) => ({ name: l, value: values[i], itemStyle: { color: mix(T.accent, T.surface, (0.55 * i) / Math.max(1, n - 1)) } })),
    }],
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        const i = p.dataIndex;
        const rows = [[mix(T.accent, T.surface, (0.55 * i) / Math.max(1, n - 1)), m.series[0].name || "Count", full(count(i), m.unit), ""]];
        if (m.displays?.[i]) rows.push(["", "Value", String(m.displays[i]), ""]);
        if (i > 0) rows.push(["", "Of the stage before", pct(values[i], values[i - 1]), ""]);
        if (i > 0) rows.push(["", "Of the first stage", pct(values[i], first), ""]);
        if (m.notes?.[i]) rows.push(["", "", "", m.notes[i]]);
        return tip(m.labels[i], rows);
      },
    },
  };
}

/* -------------------------------------------------------------------- gauge */
function gauge(m, T, c) {
  const g = m.gauge;
  const meets = g.target === null ? null : g.better === "higher" ? g.value >= g.target : g.value <= g.target;
  const colour = meets === null ? T.accent : meets ? T.ok : T.high;
  const shown = Math.min(g.max, Math.max(g.min, g.value));
  const arc = { startAngle: 210, endAngle: -30, min: g.min, max: g.max, radius: "86%", center: ["50%", "58%"] };
  const out = [{
    type: "gauge", id: "s0", name: g.label || m.title || "Value", ...arc, splitNumber: 1,
    progress: { show: true, width: 16, roundCap: true, itemStyle: { color: colour } },
    axisLine: { roundCap: true, lineStyle: { width: 16, color: [[1, T.raised]] } },
    pointer: { show: false }, axisTick: { show: false }, splitLine: { show: false }, anchor: { show: false },
    axisLabel: { show: true, distance: -30, color: T.mut, fontSize: 11, fontFamily: T.font, formatter: (v) => tick(v, m.unit) },
    title: { show: true, offsetCenter: [0, "26%"], color: T.mut, fontSize: 12, fontFamily: T.font },
    detail: { valueAnimation: false, offsetCenter: [0, "-6%"], color: T.ink, fontSize: 32, fontWeight: 700, fontFamily: T.font,
      formatter: () => short(g.value, m.unit) },
    data: [{ value: shown, name: g.target === null ? cut(g.label || "", 32) : `Target ${short(g.target, m.unit)}` }],
  }];
  if (g.target !== null) {
    out.push({
      type: "gauge", id: "s1", name: "Target", ...arc, splitNumber: 1,
      axisLine: { show: false }, progress: { show: false }, axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { show: false }, anchor: { show: false }, title: { show: false }, detail: { show: false },
      pointer: { show: true, icon: "rect", width: 3, length: "20%", offsetCenter: [0, "-74%"], itemStyle: { color: T.ink } },
      data: [{ value: Math.min(g.max, Math.max(g.min, g.target)) }],
    });
  }
  return {
    series: out,
    tooltip: {
      trigger: "item",
      formatter: () => tip(g.label || m.title, [
        [colour, "Figure", full(g.value, m.unit), ""],
        ...(g.target !== null ? [["", "Target", full(g.target, m.unit), meets ? "On target" : "Short of target"]] : []),
        ["", "Scale", `${full(g.min, m.unit)} to ${full(g.max, m.unit)}`, ""],
      ]),
    },
  };
}

/* ------------------------------------------------------------------ heatmap */
function heatmap(m, T, c) {
  const rows = m.series.map((s) => s.name);
  const data = [];
  m.series.forEach((s, si) => s.values.forEach((v, i) => data.push([i, si, v])));
  const all = data.map((d) => d[2]);
  let lo = Math.min(...all), hi = Math.max(...all);
  const diverging = lo < 0 && hi > 0;
  if (diverging) {
    const a = Math.max(-lo, hi);
    lo = -a; hi = a;
  }
  if (lo === hi) hi = lo + 1;
  const cells = data.length;
  // A figure on a cell in whichever ink reads on it: light on the darker cells.
  const darkTheme = (toRgb(T.surface) || [255, 255, 255]).reduce((a, v) => a + v, 0) < 384;
  const ink = (v) => (darkTheme ? T.ink : Math.abs(v - (diverging ? 0 : lo)) / (hi - lo) > (diverging ? 0.28 : 0.55) ? "#ffffff" : T.ink);
  const ramp = diverging ? [T.palette[1], mix(T.raised, T.surface, 0.2), T.palette[0]] : [mix(T.palette[0], T.surface, 0.88), T.palette[0]];
  return {
    grid: { left: 8, right: 14, top: 8, bottom: 46, containLabel: true },
    xAxis: catAxis(T, m.labels, { splitArea: { show: false }, axisLine: { show: false } }),
    yAxis: catAxis(T, rows, { inverse: true, axisLine: { show: false },
      axisLabel: { color: T.ink2, fontSize: 11, fontFamily: T.font, width: Math.min(160, c.width * 0.3), overflow: "truncate" } }),
    visualMap: {
      type: "continuous", min: lo, max: hi, calculable: false, orient: "horizontal", left: "center", bottom: 0,
      itemWidth: 10, itemHeight: Math.min(180, c.width * 0.45), text: [short(hi, m.unit), short(lo, m.unit)],
      textGap: 8, textStyle: { color: T.mut, fontSize: 11, fontFamily: T.font }, inRange: { color: ramp },
    },
    series: [{
      type: "heatmap", id: "s0", name: m.title || "Value",
      data: data.map((d) => ({ value: d, label: { color: ink(d[2]) } })),
      label: { show: cells <= 84, fontSize: 10, fontFamily: T.font, formatter: (p) => tick(p.value[2], m.unit) },
      itemStyle: { borderColor: T.surface, borderWidth: 2, borderRadius: 3 },
      emphasis: { itemStyle: { borderColor: T.ink, borderWidth: 1 } },
    }],
    tooltip: {
      trigger: "item",
      formatter: (p) => tip(`${rows[p.value[1]]} · ${m.labels[p.value[0]]}`, [["", m.title || "Value", full(p.value[2], m.unit), ""]]),
    },
  };
}

/* ------------------------------------------------------------------ treemap */
function treemap(m, T, c) {
  const deep = m.tree.some((t) => t.children);
  const total = m.tree.reduce((a, t) => a + t.value, 0);
  // Parts take lighter steps of their parent's colour, largest darkest.
  const node = (t, colour) => ({
    name: t.name, value: t.value,
    itemStyle: { color: t.rest ? T.dim : colour },
    ...(t.children ? {
      children: t.children.map((k, j) => node(k, k.rest ? T.dim : mix(colour, T.surface, Math.min(0.55, 0.16 * j)))),
    } : {}),
  });
  return {
    series: [{
      type: "treemap", id: "s0", name: "All", roam: false, nodeClick: deep ? "zoomToNode" : false,
      left: 0, right: 0, top: 0, bottom: deep ? 30 : 0, squareRatio: 0.5 * (1 + Math.sqrt(5)),
      breadcrumb: {
        show: deep, bottom: 2, left: 4, height: 22, emptyItemWidth: 20,
        itemStyle: { color: T.raised, borderColor: T.line2, borderWidth: 1, textStyle: { color: T.ink2, fontFamily: T.font } },
        emphasis: { itemStyle: { color: T.line2 } },
      },
      label: {
        show: true, color: "#ffffff", fontSize: 12, fontFamily: T.font, lineHeight: 16, overflow: "truncate",
        formatter: (p) => `${p.name}\n${short(p.value, m.unit)}`,
      },
      upperLabel: { show: deep, height: 22, color: "#ffffff", fontSize: 12, fontWeight: 600, fontFamily: T.font,
        formatter: (p) => `${p.name}  ${short(p.value, m.unit)}` },
      itemStyle: { borderColor: T.surface, borderWidth: 2, gapWidth: 2, borderRadius: 4 },
      // The whole (no heading), each top-level part (a heading when it has parts of its
      // own), and those parts, in lighter steps of their parent's colour.
      levels: [
        { itemStyle: { borderWidth: 0, gapWidth: 3 }, upperLabel: { show: false } },
        { itemStyle: { borderWidth: deep ? 3 : 0, gapWidth: 2 } },
        { itemStyle: { borderWidth: 0, gapWidth: 1 } },
      ],
      data: m.tree.map((t, i) => node(t, T.palette[i % T.palette.length])),
    }],
    tooltip: {
      trigger: "item",
      formatter: (p) => {
        const path = (p.treePathInfo || []).slice(1).map((x) => x.name);
        return tip(path.join(" › ") || p.name, [["", "Value", full(p.value, m.unit), total ? `${pct(p.value, total)} of the whole` : ""]]);
      },
    },
  };
}

/* -------------------------------------------------------------------- radar */
/** Rings at a round step: the number of steps that divides max into 1, 2, 3 or 5 x 10^n. */
function niceSplit(max) {
  for (const n of [5, 4, 6, 3, 2]) {
    const step = max / n;
    const mag = 10 ** Math.floor(Math.log10(step));
    if ([1, 2, 3, 5, 10].some((f) => Math.abs(step - f * mag) < mag * 1e-9)) return n;
  }
  return 4;
}

function radar(m, T, c) {
  const count = m.series.length;
  const wide = c.width >= 460;
  return {
    radar: {
      indicator: m.labels.map((l) => ({ name: l, max: m.max })), shape: "polygon",
      radius: wide ? "66%" : "56%", center: ["50%", count > 1 ? "48%" : "52%"], splitNumber: niceSplit(m.max),
      axisName: { color: T.ink2, fontSize: 11, fontFamily: T.font, formatter: (v) => cut(v, wide ? 22 : 14) },
      splitLine: { lineStyle: { color: T.line2 } }, axisLine: { lineStyle: { color: T.line2 } },
      splitArea: { areaStyle: { color: [alpha(T.raised, 0), alpha(T.raised, 0.9)] } },
    },
    legend: legend(T, m.series.map((s) => s.name || m.title || "Value"), { show: count > 1 }),
    series: [{
      type: "radar", id: "s0", name: m.title || "Value", symbolSize: 5, emphasis: { focus: "self" },
      data: m.series.map((s, si) => {
        const colour = seriesColour(T, si, count);
        return {
          name: s.name || m.title || "Value", value: s.values,
          lineStyle: { width: 2, color: colour }, itemStyle: { color: colour },
          areaStyle: { color: alpha(colour, 0.16) },
        };
      }),
    }],
    tooltip: {
      trigger: "item",
      formatter: (p) => tip(p.name, m.labels.map((l, i) => [seriesColour(T, p.dataIndex, count), l, full(p.value[i], m.unit), ""])),
    },
  };
}

/* ------------------------------------------------- a single 100% bar (panels) */
function strip(m, T, c) {
  const values = m.series[0].values.map((v) => Math.max(0, v || 0));
  const total = values.reduce((a, b) => a + b, 0);
  const live = values.map((v, i) => (v > 0 ? i : -1)).filter((i) => i >= 0);
  const first = live[0], last = live[live.length - 1];
  return {
    grid: { left: 0, right: 0, top: 6, bottom: 6 },
    xAxis: { type: "value", show: false, max: total || 1 },
    yAxis: { type: "category", show: false, data: [""] },
    series: m.labels.map((l, i) => ({
      type: "bar", id: `p${i}`, name: l, stack: "all", barWidth: 26, data: [values[i]],
      universalTransition: { enabled: true },
      itemStyle: {
        color: labelColour(m, T, i, true), borderColor: T.surface, borderWidth: values[i] ? 1.5 : 0,
        borderRadius: [i === first ? 7 : 0, i === last ? 7 : 0, i === last ? 7 : 0, i === first ? 7 : 0],
      },
      emphasis: { focus: "self" },
    })),
    tooltip: {
      trigger: "item",
      formatter: (p) => tip(p.seriesName, [[labelColour(m, T, p.seriesIndex, true), m.series[0].name || "Value",
        m.displays?.[p.seriesIndex] ? String(m.displays[p.seriesIndex]) : full(values[p.seriesIndex], m.unit),
        `${pct(values[p.seriesIndex], total)} of the total`]]),
    },
  };
}

/* -------------------------------------------------------------------- table */
/** The chart's figures as rows, for "view as table" -- every value in full. */
export function tableOf(m) {
  const u = (si) => (si === 1 && ["combo", "scatter", "bubble"].includes(m.type) ? m.unit2 || m.unit
    : si === 2 && m.type === "bubble" ? m.unit3 : m.unit);
  if (m.type === "gauge") {
    const g = m.gauge;
    return {
      head: ["", "Figure", ...(g.target !== null ? ["Target"] : []), "Scale"],
      rows: [{ index: 0, cells: [g.label || m.title || "Value", full(g.value, m.unit),
        ...(g.target !== null ? [full(g.target, m.unit)] : []), `${full(g.min, m.unit)} to ${full(g.max, m.unit)}`] }],
    };
  }
  if (m.type === "treemap") {
    const total = m.tree.reduce((a, t) => a + t.value, 0);
    const rows = [];
    m.tree.forEach((t, i) => {
      rows.push({ index: i, strong: true, cells: [t.name, full(t.value, m.unit), pct(t.value, total)] });
      (t.children || []).forEach((k) => rows.push({ index: i, cells: [`   ${k.name}`, full(k.value, m.unit), pct(k.value, total)] }));
    });
    return { head: ["", m.unit ? `Value (${m.unit})` : "Value", "Share"], rows };
  }
  if (m.type === "waterfall") {
    return {
      head: ["", "Change", "Level"],
      rows: m.labels.map((l, i) => ({
        index: i,
        cells: [l, m.bars[i].kind === "total" ? "" : `${m.series[0].values[i] < 0 ? "−" : "+"}${full(Math.abs(m.series[0].values[i]), m.unit)}`,
          full(m.bars[i].end, m.unit)],
      })),
    };
  }
  const share = ["pie", "donut", "rose", "strip"].includes(m.type);
  const one = m.series.length === 1;
  const total = share ? m.series[0].values.reduce((a, v) => a + Math.max(0, v || 0), 0) : 0;
  const head = ["", ...m.series.map((s, si) => named(s.name || (one ? m.title || "Value" : ""), u(si)) || "Value")];
  if (share) head.push("Share");
  if (m.notes?.some(Boolean)) head.push("");
  return {
    head,
    rows: m.labels.map((l, i) => ({
      index: i,
      cells: [
        l,
        ...m.series.map((s, si) => (one && m.displays?.[i] ? String(m.displays[i]) : full(s.values[i], u(si)))),
        ...(share ? [pct(Math.max(0, m.series[0].values[i] || 0), total)] : []),
        ...(m.notes?.some(Boolean) ? [m.notes[i] || ""] : []),
      ],
    })),
  };
}

/** One sentence that says what the chart shows, for a screen reader. */
export function describe(m, view) {
  const what = `${VIEW_LABELS[view] || "Chart"} chart${m.title ? ` of ${m.title}` : ""}`;
  if (m.type === "gauge") return `${what}: ${full(m.gauge.value, m.unit)}${m.gauge.target !== null ? ` against a target of ${full(m.gauge.target, m.unit)}` : ""}.`;
  const s = m.series[0];
  if (!s || !m.labels.length) return `${what}.`;
  let top = 0;
  s.values.forEach((v, i) => { if ((v ?? -Infinity) > (s.values[top] ?? -Infinity)) top = i; });
  const series = m.series.length > 1 ? `, ${m.series.length} series` : "";
  return `${what}: ${m.labels.length} items${series}; the largest${m.series.length > 1 ? ` in ${s.name}` : ""} is `
    + `${m.labels[top]} at ${full(s.values[top], m.unit)}. Choose Table for every figure.`;
}
