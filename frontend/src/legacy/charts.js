/**
 * Charts and figure cards inside an analyst answer, drawn as SVG and DOM nodes.
 *
 * The analyst writes them as fenced blocks in its markdown:
 *
 *   ```figures                         ```chart
 *   [{"label": "Owed to us",          {"type": "bar" | "line" | "donut" | "hbar" |
 *     "value": "GHS 9.18M",                     "stacked" | "grouped" | "combo" | "scatter",
 *     "note": "806 invoices",           "title": "...", "unit": "GHS", "unit2": "%",
 *     "tone": "bad"}]                   "labels": ["...", ...],
 *                                       "series": [{"name": "...", "values": [..]}]}
 *
 * The block is data, not markup: it is parsed as JSON, checked, capped, and drawn
 * here -- nothing in it is ever treated as HTML. A block that does not parse, or
 * whose numbers are not numbers, is not drawn at all rather than drawn wrong. The
 * system prompt requires every number in a block to come from a tool result.
 *
 * bar, line and donut are read as they always were (lenient: extra series dropped,
 * labels capped). The newer types are read strictly -- every value a real number, one
 * per label, the right number of series -- because each of them draws series against
 * each other, and a missing or misplaced value would put a figure against the wrong
 * name. The scales are honest: every bar axis includes zero, a zero is drawn as
 * nothing rather than nudged into a sliver, and stacked bars refuse negatives (a
 * negative part of a total cannot be stacked truthfully).
 *
 * Every chart carries a Download control (PNG and SVG), made from the chart itself so
 * the file shows exactly what is on the screen, in the screen's colours.
 */

const NS = "http://www.w3.org/2000/svg";
const MAX_ITEMS = 12;
const MAX_POINTS = 36;
const MAX_COLUMNS = 24; // stacked and combo: a two-year monthly run
const MAX_SERIES = 4; // stacked and grouped
const MAX_SCATTER = 40;
const LEGACY = ["bar", "line", "donut"];
const STRICT = ["hbar", "stacked", "grouped", "combo", "scatter"];

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
  return STRICT.includes(spec.type) ? strictModel(spec) : legacyModel(spec);
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
function legacyModel(spec) {
  const labels = (Array.isArray(spec.labels) ? spec.labels : []).map(String);
  const series = (Array.isArray(spec.series) ? spec.series : [])
    .filter((s) => s && Array.isArray(s.values))
    .slice(0, 3)
    .map((s) => ({ name: String(s.name || ""), values: s.values.map(Number) }));
  if (!labels.length || !series.length) return null;
  if (series.some((s) => s.values.some((v) => !Number.isFinite(v)))) return null;
  const type = LEGACY.includes(spec.type) ? spec.type : "bar";
  const cap = type === "line" ? MAX_POINTS : type === "donut" ? 6 : MAX_ITEMS;
  const shown = labels.slice(0, cap);
  return {
    type, title: spec.title ? String(spec.title) : "", unit: spec.unit ? String(spec.unit) : "",
    unit2: "", labels: shown, series, total: shown.length,
  };
}

function strictModel(spec) {
  const type = spec.type;
  const labels = spec.labels;
  if (!Array.isArray(labels) || !labels.length) return null;
  if (labels.some((l) => (typeof l !== "string" && typeof l !== "number") || !String(l).trim())) return null;
  const raw = spec.series;
  const fewest = type === "combo" || type === "scatter" ? 2 : 1;
  const most = type === "hbar" ? 1 : type === "combo" || type === "scatter" ? 2 : MAX_SERIES;
  if (!Array.isArray(raw) || raw.length < fewest || raw.length > most) return null;
  const series = [];
  for (const [i, s] of raw.entries()) {
    if (!s || typeof s !== "object" || !Array.isArray(s.values) || s.values.length !== labels.length) return null;
    if (s.values.some((v) => typeof v !== "number" || !Number.isFinite(v))) return null;
    const name = String(s.name ?? "").trim() || (raw.length > 1 ? `Series ${i + 1}` : "");
    series.push({ name, values: s.values.slice() });
  }
  if (type === "stacked" && series.some((s) => s.values.some((v) => v < 0))) return null;

  let names = labels.map(String);
  if (type === "hbar") {
    // A ranking: largest first, so the rank beside each name is true whatever order
    // the block came in.
    const order = names.map((_, i) => i).sort((a, b) => series[0].values[b] - series[0].values[a]);
    names = order.map((i) => names[i]);
    series[0].values = order.map((i) => series[0].values[i]);
  }
  const cap = type === "scatter" ? MAX_SCATTER : type === "stacked" || type === "combo" ? MAX_COLUMNS : MAX_ITEMS;
  const n = Math.min(names.length, cap);
  return {
    type, title: spec.title ? String(spec.title) : "", unit: spec.unit ? String(spec.unit) : "",
    unit2: spec.unit2 !== undefined && spec.unit2 !== null ? String(spec.unit2) : "",
    labels: names.slice(0, n), series: series.map((s) => ({ ...s, values: s.values.slice(0, n) })),
    total: names.length,
  };
}

/* -------------------------------------------------------------------- chart */
function chart(spec) {
  const m = chartModel(spec);
  if (!m) return null;
  const s0 = m.series[0].values;
  const body =
    m.type === "line" ? line(m.labels, m.series, m.unit)
      : m.type === "donut" ? donut(m.labels, s0.slice(0, 6), m.unit)
        : m.type === "bar" ? bars(m.labels, s0.slice(0, MAX_ITEMS), m.unit)
          : m.type === "hbar" ? hbars(m)
            : m.type === "scatter" ? scatter(m)
              : columns(m);
  if (!body) return null;

  const wrap = el("figure", "md-chart");
  if (m.title) wrap.append(el("figcaption", "", m.title));
  wrap.append(body);
  const keys = legendItems(m);
  if (keys.length) wrap.append(legend(keys));
  if (m.total > m.labels.length) {
    wrap.append(el("div", "md-chart-note", `Showing the first ${m.labels.length} of ${m.total}.`));
  }
  wrap.append(downloads(wrap, m));
  tooltips(wrap);
  return wrap;
}

/** What the legend lists: one key per series, only where there is more than one. */
function legendItems(m) {
  if (m.type === "line" && m.series.length > 1) return m.series.map((s, i) => ({ name: s.name, cls: `s${i}` }));
  if ((m.type === "stacked" || m.type === "grouped") && m.series.length > 1) {
    return m.series.map((s, i) => ({ name: s.name, cls: `c${i}` }));
  }
  if (m.type === "combo") {
    return [{ name: withUnit(m.series[0].name, m.unit), cls: "c0" },
      { name: withUnit(m.series[1].name, m.unit2 || m.unit), cls: "s1 ln" }];
  }
  return [];
}

/** Horizontal bars, largest first as given: the clearest way to compare names. */
function bars(labels, values, unit) {
  const max = Math.max(...values.map(Math.abs), 0) || 1;
  const box = el("div", "md-bars");
  labels.forEach((l, i) => {
    const v = values[i] ?? 0;
    const row = el("div", "md-bar");
    row.setAttribute("data-tip", `${l}: ${exact(v, unit)}`);
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
  // Invisible bands over each point, so hovering near it says its figures.
  const gap = labels.length > 1 ? (W - L - R) / (labels.length - 1) : W - L - R;
  labels.forEach((l, i) => {
    const tip = [l, ...series.filter((s) => i < s.values.length)
      .map((s) => `${s.name ? `${s.name}: ` : ""}${exact(s.values[i], unit)}`)].join("\n");
    svg.append(svgEl("rect", { x: x(i) - gap / 2, y: T, width: gap, height: H - T - B, class: "md-hit", "data-tip": tip }));
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
      "data-tip": `${labels[i] ?? ""}: ${exact(v, unit)} (${((Math.max(0, v) / total) * 100).toFixed(1)}%)`,
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
  const leg = el("div", "md-legend stack");
  labels.forEach((l, i) => {
    const item = el("span", "");
    item.append(el("i", `c${i}`), el("span", "", l),
      el("b", "", `${((Math.max(0, values[i]) / total) * 100).toFixed(1)}%`));
    leg.append(item);
  });
  box.append(svg, leg);
  return box;
}

/**
 * A ranking with room for long names: rank, the whole name and its figure on one line,
 * the bar under it. Bars grow from zero, so a negative figure runs the other way.
 */
function hbars(m) {
  const values = m.series[0].values;
  const g = hbarGeometry(values);
  const box = el("div", "md-hbars");
  m.labels.forEach((l, i) => {
    const v = values[i];
    const row = el("div", "md-hbar");
    row.setAttribute("data-tip", `${l}: ${exact(v, m.unit)}`);
    const head = el("div", "md-hbar-h");
    head.append(el("span", "md-hbar-r", String(i + 1)), el("span", "md-hbar-l", l),
      el("b", "md-hbar-v", fmt(v, m.unit)));
    const track = el("span", "md-hbar-t");
    const fill = el("i", v < 0 ? "neg" : "");
    fill.style.left = `${g[i].left.toFixed(2)}%`;
    fill.style.width = `${g[i].width.toFixed(2)}%`;
    track.append(fill);
    row.append(head, track);
    box.append(row);
  });
  return box;
}

/** Where each ranked bar starts and how wide it is, in percent of the track. */
function hbarGeometry(values) {
  const lo = Math.min(0, ...values), hi = Math.max(0, ...values);
  const span = hi - lo || 1;
  const zero = (-lo / span) * 100;
  return values.map((v) => {
    const width = (Math.abs(v) / span) * 100;
    return { left: v < 0 ? zero - width : zero, width };
  });
}

/**
 * Columns over labels: stacked (parts of a total), grouped (series side by side) or
 * combo (an amount as bars, a rate as a line, on its own axis when its unit differs).
 */
function columns(m) {
  const { type, labels, series, unit } = m;
  const dual = type === "combo" && m.unit2 !== "" && m.unit2 !== unit;
  const W = 640, H = 240, T = 26, B = 30, L = 56, R = dual ? 56 : 14;
  const barSeries = type === "combo" ? [series[0]] : series;
  let lo = 0, hi = 0;
  if (type === "stacked") {
    labels.forEach((_, i) => { hi = Math.max(hi, series.reduce((a, s) => a + s.values[i], 0)); });
  } else {
    barSeries.forEach((s) => s.values.forEach((v) => { lo = Math.min(lo, v); hi = Math.max(hi, v); }));
  }
  const lineVals = type === "combo" ? series[1].values : null;
  if (lineVals && !dual) lineVals.forEach((v) => { lo = Math.min(lo, v); hi = Math.max(hi, v); });
  const a1 = scale(lo, hi);
  const a2 = dual ? scale(Math.min(0, ...lineVals), Math.max(0, ...lineVals)) : a1;
  const ih = H - T - B;
  const y1 = (v) => T + ih * (1 - (v - a1.lo) / (a1.hi - a1.lo));
  const y2 = (v) => T + ih * (1 - (v - a2.lo) / (a2.hi - a2.lo));
  const n = labels.length;
  const band = (W - L - R) / n;
  const cx = (i) => L + band * (i + 0.5);

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "md-cols", role: "img", "aria-label": m.title || "Chart" });
  a1.ticks.forEach((t) => {
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: y1(t), y2: y1(t), class: "md-grid" }));
    svg.append(text(L - 6, y1(t) + 3, tick(t, unit), "md-axis", "end"));
  });
  if (dual) a2.ticks.forEach((t) => svg.append(text(W - R + 6, y2(t) + 3, tick(t, m.unit2), "md-axis", "start")));
  if (unit && unit !== "%") svg.append(text(L - 6, T - 12, unit, "md-axis md-unit", "end"));
  if (dual && m.unit2 !== "%") svg.append(text(W - R + 6, T - 12, m.unit2, "md-axis md-unit", "start"));

  const inner = band * (type === "grouped" ? 0.8 : 0.62);
  labels.forEach((_, i) => {
    const x0 = L + band * i + (band - inner) / 2;
    if (type === "stacked") {
      let acc = 0;
      series.forEach((s, si) => {
        const v = s.values[i];
        // A zero part draws nothing: no sliver to make it look like something.
        if (v > 0) {
          svg.append(svgEl("rect", { x: x0, y: y1(acc + v), width: inner, height: y1(acc) - y1(acc + v), class: `md-rect c${si}` }));
        }
        acc += v;
      });
      if (n <= MAX_ITEMS && acc > 0) svg.append(text(cx(i), y1(acc) - 5, tick(acc, unit), "md-val", "middle"));
    } else {
      const k = barSeries.length;
      const w = inner / k;
      barSeries.forEach((s, si) => {
        const v = s.values[i];
        const top = y1(Math.max(v, 0)), bottom = y1(Math.min(v, 0));
        if (bottom - top <= 0) return;
        svg.append(svgEl("rect", {
          x: x0 + si * w + (k > 1 ? w * 0.06 : 0), y: top, width: w - (k > 1 ? w * 0.12 : 0), height: bottom - top,
          class: `md-rect c${si}`,
        }));
      });
    }
  });
  // The zero line over the bars: where every bar starts.
  svg.append(svgEl("line", { x1: L, x2: W - R, y1: y1(0), y2: y1(0), class: "md-base" }));

  if (type === "combo") {
    const yy = dual ? y2 : y1;
    const pts = lineVals.map((v, i) => `${cx(i).toFixed(1)},${yy(v).toFixed(1)}`);
    svg.append(svgEl("polyline", { points: pts.join(" "), class: "md-ln s1" }));
    lineVals.forEach((v, i) => svg.append(svgEl("circle", { cx: cx(i), cy: yy(v), r: 3, class: "md-pt s1" })));
  }

  // The names along the bottom, thinned and shortened to fit.
  const fit = Math.max(3, Math.floor(band / 6.2));
  const every = Math.ceil(n / Math.floor((W - L - R) / 34));
  labels.forEach((l, i) => {
    if (i % every && i !== n - 1) return;
    svg.append(text(cx(i), H - 10, l.length > fit ? `${l.slice(0, fit - 1)}…` : l, "md-axis", "middle"));
  });

  // One hover band per label, saying every figure in it.
  labels.forEach((l, i) => {
    const lines = series.map((s, si) =>
      `${s.name ? `${s.name}: ` : ""}${exact(s.values[i], si === 1 && type === "combo" ? m.unit2 || unit : unit)}`);
    if (type === "stacked" && series.length > 1) lines.push(`Total: ${exact(series.reduce((a, s) => a + s.values[i], 0), unit)}`);
    svg.append(svgEl("rect", { x: L + band * i, y: T, width: band, height: ih, class: "md-hit", "data-tip": [l, ...lines].join("\n") }));
  });
  return svg;
}

/** Two measures for each name: one dot per name, both axes from zero. */
function scatter(m) {
  const W = 640, H = 280, T = 26, B = 42, L = 56, R = 18;
  const xs = m.series[0].values, ys = m.series[1].values;
  const ax = scale(Math.min(0, ...xs), Math.max(0, ...xs));
  const ay = scale(Math.min(0, ...ys), Math.max(0, ...ys));
  const x = (v) => L + (W - L - R) * ((v - ax.lo) / (ax.hi - ax.lo));
  const y = (v) => T + (H - T - B) * (1 - (v - ay.lo) / (ay.hi - ay.lo));
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "md-scatter", role: "img", "aria-label": m.title || "Chart" });
  ay.ticks.forEach((t) => {
    svg.append(svgEl("line", { x1: L, x2: W - R, y1: y(t), y2: y(t), class: t === 0 ? "md-base" : "md-grid" }));
    svg.append(text(L - 6, y(t) + 3, tick(t, m.unit2), "md-axis", "end"));
  });
  ax.ticks.forEach((t) => {
    svg.append(svgEl("line", { x1: x(t), x2: x(t), y1: T, y2: H - B, class: t === 0 ? "md-base" : "md-grid" }));
    svg.append(text(x(t), H - B + 14, tick(t, m.unit), "md-axis", "middle"));
  });
  svg.append(text(W - R, H - 6, withUnit(m.series[0].name, m.unit), "md-axis md-unit", "end"));
  svg.append(text(L - 6, T - 12, withUnit(m.series[1].name, m.unit2), "md-axis md-unit", "start"));
  const named = m.labels.length <= MAX_ITEMS;
  m.labels.forEach((l, i) => {
    const px = x(xs[i]), py = y(ys[i]);
    svg.append(svgEl("circle", { cx: px, cy: py, r: 4.5, class: "md-dot c0" }));
    if (named) {
      const right = px > W - R - 110;
      svg.append(text(right ? px - 8 : px + 8, py + 3, l.length > 18 ? `${l.slice(0, 17)}…` : l, "md-plab", right ? "end" : "start"));
    }
  });
  m.labels.forEach((l, i) => {
    svg.append(svgEl("circle", {
      cx: x(xs[i]), cy: y(ys[i]), r: 10, class: "md-hit",
      "data-tip": `${l}\n${m.series[0].name || "x"}: ${exact(xs[i], m.unit)}\n${m.series[1].name || "y"}: ${exact(ys[i], m.unit2)}`,
    }));
  });
  return svg;
}

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

function legend(items) {
  const leg = el("div", "md-legend");
  items.forEach((k) => {
    const item = el("span", "");
    item.append(el("i", k.cls), el("span", "", k.name));
    leg.append(item);
  });
  return leg;
}

/* ---------------------------------------------------------------- hovering */
/** A small label that follows the pointer over anything carrying data-tip. */
function tooltips(fig) {
  let tip = null;
  const show = (target, ev) => {
    if (!tip) {
      tip = el("div", "md-tip");
      tip.setAttribute("role", "tooltip");
      fig.append(tip);
    }
    tip.textContent = target.getAttribute("data-tip");
    tip.hidden = false;
    const r = fig.getBoundingClientRect();
    let left = ev.clientX - r.left + 14;
    const top = ev.clientY - r.top + 14;
    if (left + tip.offsetWidth > r.width - 4) left = Math.max(4, ev.clientX - r.left - tip.offsetWidth - 14);
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  };
  const move = (ev) => {
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-tip]") : null;
    if (t && fig.contains(t)) show(t, ev);
    else if (tip) tip.hidden = true;
  };
  fig.addEventListener("mousemove", move);
  fig.addEventListener("click", move);
  fig.addEventListener("mouseleave", () => { if (tip) tip.hidden = true; });
}

/* -------------------------------------------------------------- downloading */
function downloads(fig, m) {
  const row = el("div", "md-chart-f");
  row.append(el("span", "md-dl-t", "Download"));
  const button = (label, title, run) => {
    const b = el("button", "md-dl", label);
    b.type = "button";
    b.title = title;
    b.onclick = async () => {
      try {
        await run();
      } catch (e) {
        b.textContent = "Failed";
        b.title = e?.message || "The download failed.";
        setTimeout(() => { b.textContent = label; b.title = title; }, 2500);
      }
    };
    return b;
  };
  row.append(
    button("PNG", "Save this chart as a picture", () => savePng(fig, m)),
    button("SVG", "Save this chart as a drawing that stays sharp at any size", () => {
      const { svg } = exportSvg(fig, m);
      save(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }), fileName(m, "svg"));
    }),
  );
  return row;
}

async function savePng(fig, m) {
  const { svg, width, height } = exportSvg(fig, m);
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = () => reject(new Error("The chart could not be turned into a picture."));
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  });
  const k = 2;
  const canvas = document.createElement("canvas");
  canvas.width = width * k;
  canvas.height = height * k;
  const ctx = canvas.getContext("2d");
  ctx.scale(k, k);
  ctx.drawImage(img, 0, 0, width, height);
  const blob = await new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("The picture could not be made."))), "image/png"));
  save(blob, fileName(m, "png"));
}

function save(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function fileName(m, ext) {
  const slug = m.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
  return `${slug || "chart"}.${ext}`;
}

/**
 * The chart as one standalone SVG: its title, the drawing as it is on the screen
 * (cloned, with the screen's computed colours written onto each shape, since a file
 * has no stylesheet), and the legend. Bars, which the screen draws as HTML, are drawn
 * again here from the same numbers.
 */
export function exportSvg(fig, m) {
  const cs = getComputedStyle(fig);
  const tok = (name, fb) => (cs.getPropertyValue(name) || "").trim() || fb;
  const C = {
    bg: tok("--surface", "#ffffff"), ink: tok("--ink", "#111317"), ink2: tok("--ink2", "#3b3f47"),
    mut: tok("--mut", "#646973"), raised: tok("--raised", "#f2f3f5"), crit: tok("--crit", "#c2392f"),
    c: [["--accent", "#2443e8"], ["--ok", "#127a55"], ["--high", "#b35a0b"], ["--dim", "#8a8f99"],
      ["--crit", "#c2392f"], ["--med", "#946f05"]].map(([t, f]) => tok(t, f)),
  };
  C.s = [C.c[0], C.c[1], C.c[3]];
  const W = 680, pad = 20;
  const out = svgEl("svg", { xmlns: NS, "font-family": "Manrope, Helvetica, Arial, sans-serif" });
  const bg = svgEl("rect", { x: 0, y: 0, width: W, fill: C.bg });
  out.append(bg);
  let y = pad;
  if (m.title) {
    out.append(fileText(pad, y + 14, m.title, { "font-size": 15, "font-weight": 600, fill: C.ink }));
    y += 32;
  }

  if (m.type === "bar" || m.type === "hbar") {
    const values = m.series[0].values;
    const max = Math.max(...values.slice(0, m.labels.length).map(Math.abs), 0) || 1;
    const geo = m.type === "hbar" ? hbarGeometry(values) : null;
    const tw = W - 2 * pad;
    m.labels.forEach((l, i) => {
      const v = values[i] ?? 0;
      const name = `${m.type === "hbar" ? `${i + 1}. ` : ""}${l}`;
      out.append(fileText(pad, y + 12, name.length > 70 ? `${name.slice(0, 69)}…` : name, { "font-size": 12, fill: C.ink2 }));
      out.append(fileText(W - pad, y + 12, fmt(v, m.unit), { "font-size": 12, "font-weight": 600, fill: C.ink, "text-anchor": "end" }));
      out.append(svgEl("rect", { x: pad, y: y + 18, width: tw, height: 8, rx: 4, fill: C.raised }));
      const left = geo ? geo[i].left : 0;
      const width = geo ? geo[i].width : Math.max(1.5, (Math.abs(v) / max) * 100);
      if (width > 0) {
        out.append(svgEl("rect", {
          x: pad + (tw * left) / 100, y: y + 18, width: (tw * width) / 100, height: 8, rx: 4,
          fill: v < 0 && geo ? C.crit : C.c[0],
        }));
      }
      y += 34;
    });
  } else if (m.type === "donut") {
    const c = inlineClone(fig.querySelector(".md-donut svg"));
    Object.entries({ x: pad, y, width: 160, height: 160 }).forEach(([k, v]) => c.setAttribute(k, v));
    out.append(c);
    const values = m.series[0].values.slice(0, 6);
    const total = values.reduce((a, b) => a + Math.max(0, b), 0) || 1;
    m.labels.forEach((l, i) => {
      const ly = y + 22 + i * 24;
      out.append(svgEl("rect", { x: pad + 190, y: ly - 9, width: 10, height: 10, rx: 3, fill: C.c[i % 6] }));
      out.append(fileText(pad + 208, ly, l.length > 48 ? `${l.slice(0, 47)}…` : l, { "font-size": 12, fill: C.ink2 }));
      out.append(fileText(W - pad, ly, `${((Math.max(0, values[i] ?? 0) / total) * 100).toFixed(1)}%`,
        { "font-size": 12, "font-weight": 600, fill: C.ink, "text-anchor": "end" }));
    });
    y += Math.max(160, m.labels.length * 24 + 10) + 6;
  } else {
    const src = fig.querySelector(":scope > svg");
    const vb = src.viewBox.baseVal;
    const h = ((W - 2 * pad) * vb.height) / vb.width;
    const c = inlineClone(src);
    Object.entries({ x: pad, y, width: W - 2 * pad, height: h }).forEach(([k, v]) => c.setAttribute(k, v));
    out.append(c);
    y += h + 8;
  }

  // The legend, wrapped across lines.
  let lx = pad;
  const keys = legendItems(m);
  keys.forEach((k, i) => {
    const n = Number(k.cls.slice(1, 2));
    const colour = k.cls.startsWith("c") ? C.c[n] : C.s[n];
    const lineKey = k.cls.includes("ln");
    const wide = 22 + k.name.length * 6.6;
    if (lx + wide > W - pad && lx > pad) { lx = pad; y += 20; }
    out.append(lineKey
      ? svgEl("rect", { x: lx, y: y + 6, width: 14, height: 3, rx: 1.5, fill: colour })
      : svgEl("rect", { x: lx, y: y + 2, width: 10, height: 10, rx: 3, fill: colour }));
    out.append(fileText(lx + (lineKey ? 20 : 16), y + 11, k.name, { "font-size": 11, fill: C.mut }));
    lx += wide + 10;
    if (i === keys.length - 1) y += 22;
  });
  if (m.total > m.labels.length) {
    out.append(fileText(pad, y + 11, `Showing the first ${m.labels.length} of ${m.total}.`, { "font-size": 11, fill: C.mut }));
    y += 20;
  }
  const height = Math.ceil(y + pad - 8);
  bg.setAttribute("height", height);
  out.setAttribute("width", W);
  out.setAttribute("height", height);
  out.setAttribute("viewBox", `0 0 ${W} ${height}`);
  return { svg: new XMLSerializer().serializeToString(out), width: W, height };
}

/** A copy of an on-screen SVG with its computed look written onto every element. */
function inlineClone(src) {
  const copy = src.cloneNode(true);
  const from = [src, ...src.querySelectorAll("*")];
  const to = [copy, ...copy.querySelectorAll("*")];
  const props = ["fill", "fill-opacity", "stroke", "stroke-width", "stroke-dasharray", "stroke-linejoin",
    "stroke-linecap", "opacity", "font-size", "font-weight", "font-family"];
  from.forEach((n, i) => {
    const t = to[i];
    const s = getComputedStyle(n);
    props.forEach((p) => {
      const v = s.getPropertyValue(p);
      if (v) t.setAttribute(p, v);
    });
    if (n.classList.contains("md-hit")) {
      t.setAttribute("fill", "#000");
      t.setAttribute("fill-opacity", "0");
      t.setAttribute("stroke", "none");
    }
    t.removeAttribute("class");
    const tip = t.getAttribute("data-tip");
    if (tip) {
      t.removeAttribute("data-tip");
      const title = document.createElementNS(NS, "title");
      title.textContent = tip;
      t.append(title);
    }
  });
  copy.removeAttribute("role");
  return copy;
}

function fileText(x, y, s, attrs) {
  const t = svgEl("text", { x, y, ...attrs });
  t.textContent = s;
  return t;
}

/* ---------------------------------------------------------------- numbers */
/** 9,177,568 -> "GHS 9.18M"; small numbers kept exact. */
function fmt(v, unit) {
  const a = Math.abs(v);
  const s = a >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(v / 1e6).toFixed(2)}M`
    : a >= 1e4 ? `${(v / 1e3).toFixed(1)}k` : Number.isInteger(v) ? v.toLocaleString("en-GB")
      : v.toLocaleString("en-GB", { maximumFractionDigits: 1 });
  return unit === "%" ? `${s}%` : unit ? `${unit} ${s}` : s;
}

/** An axis step, short: "2.5M", "250k", "40%" -- any other unit is said once, at the top. */
export function tick(v, unit) {
  const a = Math.abs(v);
  const short = (x) => x.toLocaleString("en-GB", { maximumFractionDigits: 2 });
  const s = a >= 1e9 ? `${short(v / 1e9)}B` : a >= 1e6 ? `${short(v / 1e6)}M`
    : a >= 1e4 ? `${short(v / 1e3)}k` : short(v);
  return unit === "%" ? `${s}%` : s;
}

/** The figure in full, for hovering: "GHS 1,234,567.5". */
function exact(v, unit) {
  const s = Number(v).toLocaleString("en-GB", { maximumFractionDigits: 2 });
  return unit === "%" ? `${s}%` : unit ? `${unit} ${s}` : s;
}

function withUnit(name, unit) {
  return unit && name ? `${name} (${unit})` : name || unit || "";
}

/* ----------------------------------------------------------------- builders */
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

function text(x, y, s, cls, anchor) {
  const t = svgEl("text", { x, y, class: cls, "text-anchor": anchor });
  t.textContent = s;
  return t;
}
