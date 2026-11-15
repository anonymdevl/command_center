/**
 * The charts and the answer's tables, tested without a browser.
 *
 *     node scripts/test_charts.mjs
 *
 * frontend/src/legacy/charts.js, vizoptions.js and markdown.js are loaded as they ship,
 * over a small stand-in for the DOM (just what they call). Under test: every chart type
 * is drawn from a valid block and refused from a broken one -- a block that fails its
 * checks is not drawn, never drawn wrong -- and the blocks the analyst wrote before the
 * charts moved to ECharts still draw; every view every chart offers builds an ECharts
 * option that Apache ECharts itself renders (server-side, to SVG, from
 * frontend/node_modules) with its value axis from zero; text from data is never
 * markup, in the drawing or the tooltip; long tables sort and page with every row kept
 * for Excel, and a copied answer says its charts in words.
 * Run by scripts/preflight.py.
 */

/* ------------------------------------------------------------ a small DOM */
class Text {
  constructor(t) { this.nodeType = 3; this.textContent = String(t); this.parentNode = null; }
  remove() { if (this.parentNode) this.parentNode.childNodes.splice(this.parentNode.childNodes.indexOf(this), 1); this.parentNode = null; }
}

class El {
  constructor(tag, ns) {
    this.nodeType = 1; this.localName = tag; this.tagName = tag.toUpperCase(); this.ns = ns || null;
    this.childNodes = []; this.attrs = {}; this.style = {}; this._text = ""; this.parentNode = null;
    this.hidden = false; this.listeners = {}; this.dataset = {};
  }
  get className() { return this.attrs.class || ""; }
  set className(v) { this.attrs.class = String(v); }
  get classList() {
    const me = this;
    const has = (c) => me.className.split(/\s+/).includes(c);
    return {
      add: (c) => { if (!has(c)) me.className = `${me.className} ${c}`.trim(); },
      remove: (c) => { me.className = me.className.split(/\s+/).filter((x) => x && x !== c).join(" "); },
      toggle: (c, on) => { if (on ?? !has(c)) { if (!has(c)) me.className = `${me.className} ${c}`.trim(); } else me.className = me.className.split(/\s+/).filter((x) => x && x !== c).join(" "); },
      contains: has,
      get length() { return me.className.split(/\s+/).filter(Boolean).length; },
    };
  }
  append(...nodes) {
    nodes.forEach((n) => {
      if (typeof n === "string") n = new Text(n);
      if (n.parentNode) n.remove();
      n.parentNode = this;
      this.childNodes.push(n);
    });
  }
  after(n) { const p = this.parentNode; p.childNodes.splice(p.childNodes.indexOf(this) + 1, 0, n); n.parentNode = p; }
  remove() { Text.prototype.remove.call(this); }
  get isConnected() { return false; }
  get firstChild() { return this.childNodes[0] || null; }
  get children() { return this.childNodes.filter((c) => c.nodeType === 1); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); }
  get textContent() { return this.childNodes.length ? this.childNodes.map((c) => c.textContent).join("") : this._text; }
  set textContent(v) { this.childNodes = []; this._text = String(v); }
  all() { return this.children.flatMap((c) => [c, ...c.all()]); }
  /** Only "tag" and ".class" selectors -- all these tests need. */
  find(sel) {
    return this.all().filter((n) => (sel.startsWith(".") ? n.classList.contains(sel.slice(1)) : n.localName === sel));
  }
  get tBodies() { return this.children.filter((c) => c.tagName === "TBODY"); }
  get tHead() { return this.children.find((c) => c.tagName === "THEAD") || null; }
  get rows() { return this.children.filter((c) => c.tagName === "TR"); }
  get cells() { return this.children.filter((c) => c.tagName === "TH" || c.tagName === "TD"); }
  // What ECharts asks of a canvas when it measures text (server-side it draws SVG).
  getContext() { return { measureText: (t) => ({ width: String(t).length * 6.5 }), font: "" }; }
}

globalThis.document = {
  createElement: (t) => new El(t),
  createElementNS: (ns, t) => new El(t, ns),
  createTextNode: (t) => new Text(t),
  documentElement: new El("html"),
};
globalThis.window = { location: { origin: "http://cc.test" } };

const charts = await import("../frontend/src/legacy/charts.js");
const vo = await import("../frontend/src/legacy/vizoptions.js");
const md = await import("../frontend/src/legacy/markdown.js");
let echarts = null;
try {
  echarts = (await import("../frontend/src/legacy/echarts-lib.js")).default;
} catch (e) {
  console.log("FAIL: Apache ECharts could not be loaded from frontend/node_modules "
    + `(cd frontend && npm install): ${e.message}`);
  process.exit(1);
}

let passed = 0;
let failed = 0;
function check(ok, what) {
  if (ok) passed++;
  else { failed++; console.log("FAIL:", what); }
}
const draw = (spec) => charts.renderBlock("chart", typeof spec === "string" ? spec : JSON.stringify(spec));
const model = (spec) => charts.chartModel(JSON.parse(JSON.stringify(spec)));
const LIGHT = {
  ink: "#111317", ink2: "#3b3f47", mut: "#646973", dim: "#7c818b", line: "#ecedf0", line2: "#dfe1e6",
  surface: "#ffffff", raised: "#f5f6f8", accent: "#2443e8", ok: "#127a55", med: "#856307", high: "#a85a0a",
  crit: "#c2392f", font: "Manrope", palette: ["#2443e8", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"],
};
const DARK = { ...LIGHT, ink: "#f2f3f5", surface: "#141518", accent: "#6a7fef",
  palette: ["#6a7fef", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9"] };

/** ECharts itself draws the option, server-side, to SVG: the proof an option is right. */
function render(m, view, T = LIGHT, width = 640) {
  const c = echarts.init(null, null, { renderer: "svg", ssr: true, width, height: vo.heightFor(m, view, width) });
  try {
    c.setOption({ ...vo.buildOption(m, view, T, { width }), animation: false });
    const yAxis = c.getModel().getComponent("yAxis");
    const xAxis = c.getModel().getComponent("xAxis");
    const value = [yAxis, xAxis].find((a) => a && a.axis && a.axis.type === "value");
    return { svg: c.renderToSVGString(), extent: value ? value.axis.scale.getExtent() : null };
  } finally {
    c.dispose();
  }
}

/* ---------------------------------------------------- one valid block of each */
const L3 = ["Jan 26", "Feb", "Mar"];
const two = [{ name: "Drugs", values: [100, 0, 80] }, { name: "Devices", values: [50, 60, 0] }];
const VALID = {
  bar: { type: "bar", title: "Spend", unit: "GHS", labels: ["A", "B"], series: [{ name: "S", values: [10, 5] }] },
  line: { type: "line", unit: "GHS", labels: L3, series: two },
  donut: { type: "donut", labels: ["X", "Y"], series: [{ name: "S", values: [3, 1] }] },
  hbar: { type: "hbar", unit: "GHS", labels: ["Small Pharmacy Ltd", "UBUNTU Medical Supplies Company Limited"], series: [{ name: "Owed", values: [1000, 636675] }] },
  stacked: { type: "stacked", unit: "GHS", labels: L3, series: two },
  grouped: { type: "grouped", labels: ["Accra", "Kumasi"], series: [{ name: "2025", values: [10, -4] }, { name: "2026", values: [12, 0] }] },
  combo: { type: "combo", unit: "GHS", unit2: "%", labels: ["Jan", "Feb"], series: [{ name: "Sales", values: [120000, 98000] }, { name: "Margin", values: [31.5, 28] }] },
  scatter: { type: "scatter", unit: "GHS", unit2: "days", labels: ["A", "B", "C"], series: [{ name: "Owed", values: [5, 10, 2] }, { name: "Overdue", values: [30, 90, 0] }] },
  pie: { type: "pie", unit: "GHS", labels: ["Accra", "Kumasi", "Tamale"], series: [{ name: "Sales", values: [60, 30, 10] }] },
  rose: { type: "rose", labels: ["Billing", "Delivery", "Quality"], series: [{ name: "Cases", values: [12, 7, 3] }] },
  area: { type: "area", unit: "GHS", labels: L3, series: [{ name: "Cash", values: [5, 7, 6] }] },
  stacked_area: { type: "stacked_area", unit: "GHS", labels: L3, series: two },
  percentage: { type: "percentage", labels: L3, series: two },
  waterfall: { type: "waterfall", unit: "GHS", labels: ["Opening", "Sales", "Costs", "Closing"], series: [{ name: "Cash", values: [100, 50, -30, 120] }] },
  funnel: { type: "funnel", labels: ["Enquiries", "Quotations", "Orders", "Invoices"], series: [{ name: "Count", values: [120, 64, 31, 30] }] },
  gauge: { type: "gauge", title: "Collected inside 90 days", unit: "%", value: 26.2, target: 80 },
  heatmap: { type: "heatmap", labels: ["Mon", "Tue", "Wed"], series: [{ name: "Morning", values: [3, 5, 1] }, { name: "Afternoon", values: [7, 0, 2] }] },
  treemap: { type: "treemap", unit: "GHS", items: [{ name: "Supplier A", children: [{ name: "Drugs", value: 60 }, { name: "Devices", value: 30 }] }, { name: "Supplier B", value: 50 }] },
  radar: { type: "radar", unit: "%", labels: ["Paid", "Delivered", "Paperwork", "Approvals"], series: [{ name: "Now", values: [26, 91, 99, 70] }] },
  bubble: { type: "bubble", unit: "GHS", unit2: "days", labels: ["A", "B", "C"], series: [{ name: "Owed", values: [5, 10, 2] }, { name: "Overdue", values: [30, 90, 0] }, { name: "Invoices", values: [4, 12, 1] }] },
};
check(Object.keys(VALID).sort().join() === [...charts.CHART_TYPES].sort().join(),
  "every chart type the renderer knows has a valid block under test");

for (const [type, spec] of Object.entries(VALID)) {
  const m = model(spec);
  check(m && m.type === type, `${type}: a valid block is read`);
  const fig = draw(spec);
  check(fig && fig.find(".vz").length === 1 && fig.find(".vz-stage").length === 1, `${type}: a valid block is drawn`);
  const dls = fig ? fig.find(".vz-dl").map((b) => b.textContent).join() : "";
  check(dls === "PNG,SVG", `${type}: the chart carries Download PNG and SVG`);
  const views = m ? vo.viewsFor(m) : [];
  check(views[0] === (type === "bar" ? "bar" : type) || (type === "bar" && views[0] === "hbar"), `${type}: its own view comes first`);
  check(views[views.length - 1] === "table", `${type}: the figures can always be seen as a table`);
  const opts = fig ? fig.find(".vz-opt").map((b) => b.textContent) : [];
  check(views.length < 2 || (opts.length === views.length && opts.includes("Table")), `${type}: the switcher offers every view`);
  for (const v of views) {
    if (v === "table") {
      const t = m && vo.tableOf(m);
      check(t && t.rows.length > 0 && t.rows.every((r) => r.cells.length === t.head.length), `${type}: the table has a cell for every heading`);
      continue;
    }
    let out = null;
    try { out = render(m, v); } catch (e) { check(false, `${type} as ${v}: ECharts could not draw it (${e.message})`); continue; }
    check(out.svg.startsWith("<svg") && out.svg.length > 600, `${type} as ${v}: ECharts draws it`);
    check(!out.svg.includes("<script"), `${type} as ${v}: no script in the drawing`);
    if (out.extent && ["bar", "hbar", "line", "area", "stacked", "grouped", "percentage", "stacked_area", "combo", "waterfall", "scatter", "bubble"].includes(v)) {
      check(out.extent[0] <= 0 && out.extent[1] >= 0, `${type} as ${v}: the value axis includes zero`);
    }
  }
  try { render(m, views[0], DARK, 360); check(true, ""); } catch (e) { check(false, `${type}: draws in dark at phone width (${e.message})`); }
}

/* ---------------------------------------------- blocks written before ECharts */
check(model({ type: "bar", labels: ["X", "Y"], series: [{ values: ["3", 2] }] }) !== null,
  "bar still reads a number written as text, as before");
check(model({ type: "column", labels: ["X"], series: [{ values: [3] }] })?.type === "bar",
  "a type nobody knows is still drawn as bars, as before");
check(model({ type: "line", labels: ["A", "B", "C"], series: [{ values: [1, 2] }] })?.series[0].values[2] === null,
  "an old line with a value short is drawn with a gap, not refused");
check(model({ type: "bar", labels: ["A"], series: [{ values: [1] }, { values: [2] }] }).series.length === 1,
  "an old bar with extra series draws the first, as before");
check(draw("not json") === null, "a block that does not parse is not drawn");
check(draw({ type: "bar", labels: ["X"], series: [{ values: ["lots"] }] }) === null, "a value that is not a number: not drawn");
check(draw({ type: "line", labels: [], series: [{ values: [] }] }) === null, "no labels: not drawn");
check(draw({ type: "donut", labels: ["X", "Y"], series: [{ values: [0, 0] }] }) === null, "a donut of nothing: not drawn");
const oldDonut = model({ type: "donut", labels: ["a", "b", "c", "d", "e", "f", "g", "h", "i"], series: [{ values: [9, 8, 7, 6, 5, 4, 3, 2, 1] }] });
check(oldDonut && oldDonut.labels.length === 7 && oldDonut.labels[6] === "Other (3)" && oldDonut.series[0].values[6] === 6
  && oldDonut.note === "The 3 smallest are combined as Other.",
  "a share of nine parts keeps the six largest and adds the rest as Other -- nothing dropped");

/* ------------------------------------------------------- the strict checks */
for (const type of Object.keys(VALID)) {
  if (["bar", "line", "donut", "gauge", "treemap"].includes(type)) continue;
  const ok = VALID[type];
  const bad = (mut) => { const s = JSON.parse(JSON.stringify(ok)); mut(s); return draw(s); };
  check(bad((s) => { s.series[0].values = s.series[0].values.slice(1); }) === null, `${type}: a value missing for a label: not drawn`);
  check(bad((s) => { s.series[0].values[1] = String(s.series[0].values[1]); }) === null, `${type}: a number written as text: not drawn`);
  check(bad((s) => { s.series[0].values[1] = null; }) === null, `${type}: a null value: not drawn`);
  check(bad((s) => { s.series[0].values[1] = true; }) === null, `${type}: true for a number: not drawn`);
  check(bad((s) => { s.labels = []; s.series.forEach((x) => { x.values = []; }); }) === null, `${type}: no labels: not drawn`);
  check(bad((s) => { s.labels[0] = { html: "<b>x</b>" }; }) === null, `${type}: a label that is not text: not drawn`);
  check(bad((s) => { s.series = "x"; }) === null, `${type}: series not a list: not drawn`);
  check(bad((s) => { s.series = [...s.series, ...Array.from({ length: 25 }, () => ({ values: s.labels.map(() => 1) }))]; }) === null,
    `${type}: too many series: not drawn`);
}
for (const type of ["stacked", "stacked_area", "percentage", "pie", "rose", "funnel", "radar"]) {
  const s = JSON.parse(JSON.stringify(VALID[type]));
  s.series[0].values[0] = -1;
  check(draw(s) === null, `${type} refuses a negative value`);
}
check(draw({ type: "combo", labels: ["Jan"], series: [{ values: [1] }] }) === null, "combo with one series: not drawn");
check(draw({ type: "scatter", labels: ["A"], series: [{ values: [1] }] }) === null, "scatter with one series: not drawn");
check(draw({ type: "bubble", labels: ["A"], series: [{ values: [1] }, { values: [1] }] }) === null, "bubble needs three series");
check(draw({ ...VALID.bubble, series: [VALID.bubble.series[0], VALID.bubble.series[1], { values: [1, -2, 3] }] }) === null,
  "bubble refuses a negative size");
check(draw({ type: "hbar", labels: ["A"], series: [{ values: [1] }, { values: [2] }] }) === null, "hbar with two series: not drawn");
check(draw({ type: "grouped", labels: ["A"], series: [1, 2, 3, 4, 5].map((i) => ({ name: `${i}`, values: [i] })) }) === null,
  "grouped: more than four series is not drawn");
const hb = model(VALID.hbar);
check(hb.labels[0] === "UBUNTU Medical Supplies Company Limited" && hb.series[0].values[0] === 636675,
  "hbar: ranked largest first, the whole long name kept");
const hbOpt = vo.buildOption(hb, "hbar", LIGHT, { width: 640 });
check(hbOpt.yAxis.axisLabel.formatter(hb.labels[0], 0).startsWith("1"), "hbar: each name carries its rank");

// Waterfall: it must add up.
check(model({ ...VALID.waterfall, series: [{ values: [100, 50, -30, 125] }] }) === null,
  "waterfall: a closing that does not equal opening plus movements is not drawn");
const wf = model(VALID.waterfall);
check(wf.bars[1].low === 100 && wf.bars[1].high === 150 && wf.bars[2].low === 120 && wf.bars[2].high === 150
  && wf.bars[3].kind === "total" && wf.bars[3].high === 120, "waterfall: each movement floats from the level before it");
check(model({ type: "waterfall", labels: ["Opening", "In", "Out"], totals: [0], series: [{ values: [10, 5, -20] }] })?.bars[2].low === -5,
  "waterfall: without a closing it may be said so, and a level may go below zero");
check(model({ ...VALID.waterfall, totals: [1, 3] }) === null, "waterfall: the first bar must be a level");
check(model({ ...VALID.waterfall, totals: [0, 9] }) === null, "waterfall: a total outside the bars is refused");
check(model({ ...VALID.waterfall, labels: Array.from({ length: 21 }, (_, i) => `S${i}`), series: [{ values: Array(21).fill(0) }] }) === null,
  "waterfall: more than twenty steps is refused, not cut (a cut bridge would not add up)");

// Gauge.
check(model({ type: "gauge", unit: "GHS", value: 5 }) === null, "gauge: a money gauge needs its scale (max)");
check(model({ type: "gauge", unit: "%", value: "70" }) === null, "gauge: the figure must be a number");
check(model({ type: "gauge", unit: "%", value: 70, target: "80" }) === null, "gauge: the target must be a number");
check(model({ type: "gauge", unit: "%", value: 70, min: 50, max: 40 }) === null, "gauge: a scale that runs backwards is refused");
check(model({ type: "gauge", unit: "%", value: 130 }).note.includes("off the scale"), "gauge: a figure off the scale says so");
const gOpt = vo.buildOption(model(VALID.gauge), "gauge", LIGHT, {});
check(gOpt.series[0].progress.itemStyle.color === LIGHT.high, "gauge: short of its target is shown in the warning colour");
check(vo.buildOption(model({ ...VALID.gauge, value: 85 }), "gauge", LIGHT, {}).series[0].progress.itemStyle.color === LIGHT.ok,
  "gauge: on target is shown in the good colour");

// Treemap.
check(model({ type: "treemap", items: [{ name: "A", value: 50, children: [{ name: "x", value: 40 }, { name: "y", value: 30 }] }] }) === null,
  "treemap: parts larger than their parent are refused");
const tm = model({ type: "treemap", items: [{ name: "A", value: 100, children: [{ name: "x", value: 60 }] }] });
check(tm && tm.tree[0].children.some((c) => c.name === "Not broken down" && c.value === 40),
  "treemap: what the parts do not account for is shown, not left blank");
check(model({ type: "treemap", items: [{ name: "A", children: [{ name: "x", value: 1, children: [] }] }] }) === null,
  "treemap: deeper than two levels is refused");
check(model({ type: "treemap", labels: ["A", "B"], series: [{ values: [3, 1] }] })?.tree.length === 2, "treemap: one level from labels and a series");
check(model({ type: "treemap", items: [{ name: "A", value: -1 }] }) === null, "treemap: a negative part is refused");

// Radar, heatmap, funnel.
check(model({ type: "radar", labels: ["A", "B"], series: [{ values: [1, 2] }] }) === null, "radar: fewer than three dimensions is refused");
check(model({ ...VALID.radar, max: 50 }) === null, "radar: a scale below a value is refused");
check(model(VALID.radar).max === 100, "radar: a percentage scale runs to 100");
check(model({ type: "heatmap", labels: ["A"], series: Array.from({ length: 25 }, (_, i) => ({ name: `R${i}`, values: [i] })) }) === null,
  "heatmap: more than 24 rows is refused");
const fu = model({ type: "funnel", labels: Array.from({ length: 10 }, (_, i) => `S${i}`), series: [{ values: Array.from({ length: 10 }, (_, i) => 10 - i) }] });
check(fu.labels.length === 8 && fu.note === "Showing the first 8 of 10.", "funnel: capped at eight stages, and it says so");

// Caps: drawn up to the cap, and said.
const many = Array.from({ length: 30 }, (_, i) => `M${i + 1}`);
const capped = draw({ type: "stacked", labels: many, series: [{ values: many.map(() => 1) }] });
check(capped && capped.find(".md-chart-note")[0]?.textContent === "Showing the first 24 of 30.",
  "stacked: capped at 24 columns, and it says so");
check(model({ type: "stacked", labels: many, series: [{ values: many.map(() => 1) }] }).labels.length === 24, "stacked: 24 columns drawn");

/* -------------------------------------------------------- views and options */
check(vo.viewsFor(model(VALID.area)).join() === "area,line,bar,table", "a time series offers area, line, bar and table");
check(vo.viewsFor(model({ type: "bar", labels: ["Jan", "Feb", "Mar"], series: [{ values: [1, 2, 3] }] })).includes("line"),
  "bars over months offer a line");
check(vo.viewsFor(model(VALID.pie)).join() === "pie,donut,rose,hbar,table", "a share offers pie, donut, rose, bar and table");
check(!vo.viewsFor(model(VALID.grouped)).includes("stacked"), "a series with a negative is never offered stacked");
check(vo.viewsFor({ ...model(VALID.hbar), shares: false }).every((v) => !["pie", "donut"].includes(v)),
  "a ranking that is not a whole is never offered as a pie");
const nine = { type: "hbar", title: "Staff", unit: "", labels: Array.from({ length: 9 }, (_, i) => `D${i}`),
  series: [{ name: "Staff", values: [9, 8, 7, 6, 5, 4, 3, 2, 1] }], shares: true, total: 9, note: "" };
check(vo.viewsFor(nine).includes("donut"), "a whole of nine parts offers a donut");
const pm = vo.pieModel(nine);
check(pm.labels.length === 7 && pm.index[6] === -1 && pm.index[0] === 0 && pm.series[0].values[6] === 6,
  "a pie of nine parts draws six and Other, and each slice still opens its own row");
check(vo.viewsFor({ type: "strip", labels: ["a"], series: [{ values: [1] }] }).join() === "strip,donut,hbar,table",
  "a screen's stacked bar offers donut, bars and table");
const comboOpt = vo.buildOption(model(VALID.combo), "combo", LIGHT, {});
check(Array.isArray(comboOpt.yAxis) && comboOpt.yAxis[1].axisLabel.formatter(40) === "40%",
  "combo: the rate has its own axis in its own unit");
const darkOpt = vo.buildOption(model(VALID.area), "area", DARK, {});
check(darkOpt.series[0].lineStyle.color === DARK.accent && darkOpt.tooltip.backgroundColor === DARK.surface,
  "colours are the theme's tokens: a dark chart is drawn in dark's");
check(vo.buildOption(model(VALID.stacked), "stacked", LIGHT, {}).series.map((s) => s.data[0].itemStyle.color).join()
  === LIGHT.palette.slice(0, 2).join(), "series take the palette in its fixed order");
const toned = { type: "hbar", title: "Owed", labels: ["A", "B"], series: [{ name: "Owed", values: [5, 3] }],
  colors: ["crit", "ok"], displays: ["5,000", "3,000"], notes: ["120 days", ""], total: 2, note: "" };
const tonedOpt = vo.buildOption(toned, "hbar", LIGHT, { width: 400, compact: true });
check(tonedOpt.series[0].data[0].itemStyle.color === LIGHT.crit && tonedOpt.series[0].label.formatter({ dataIndex: 0 }) === "5,000  ·  120 days",
  "a screen's bar keeps its tone and says its figure and note as the design did");
check(vo.short(9177568.91, "GHS") === "GHS 9.18M" && vo.full(9177568.91, "GHS") === "GHS 9,177,568.91"
  && vo.short(73.84, "%") === "73.8%" && vo.short(118, "days") === "118 days", "figures are written with their currency or unit");

/* ------------------------------------------------- text is text, never markup */
const evil = "<img src=x onerror=alert(1)>";
const sneakyM = model({ type: "hbar", labels: [evil], series: [{ name: evil, values: [1] }] });
const sneakySvg = render(sneakyM, "hbar").svg;
check(!sneakySvg.includes("<img") && sneakySvg.includes("&lt;img"), "a label is drawn as text, never as markup");
const tipHtml = vo.buildOption(sneakyM, "hbar", LIGHT, {}).tooltip.formatter([{ dataIndex: 0 }]);
check(!tipHtml.includes("<img") && tipHtml.includes("&lt;img"), "a tooltip escapes the label and series name");
const pieTip = vo.buildOption(model({ type: "pie", labels: [evil, "b"], series: [{ values: [1, 2] }] }), "pie", LIGHT, {})
  .tooltip.formatter({ name: evil, dataIndex: 0 });
check(!pieTip.includes("<img") && pieTip.includes("&lt;img"), "a pie's tooltip escapes too");
const tmTip = vo.buildOption(model({ type: "treemap", items: [{ name: evil, value: 1 }] }), "treemap", LIGHT, {})
  .tooltip.formatter({ name: evil, value: 1, treePathInfo: [{ name: "" }, { name: evil }] });
check(!tmTip.includes("<img"), "a treemap's tooltip escapes too");
check(!vo.buildOption(sneakyM, "hbar", { ...LIGHT, accent: "red\" onmouseover=\"x" }, {}).tooltip.formatter([{ dataIndex: 0 }]).includes("onmouseover"),
  "only a colour reaches a tooltip's style");
const sneakyFig = draw({ type: "hbar", labels: [evil], series: [{ values: [1] }] });
check(sneakyFig && sneakyFig.find("img").length === 0, "the chart's own nodes hold no markup from data");

// The axis.
const ax = charts.scale(0, 9177568);
check(ax.lo === 0 && ax.hi >= 9177568 && ax.ticks[0] === 0 && ax.ticks.length <= 6, "an axis from zero past the top value");
const axn = charts.scale(-40, 100);
check(axn.lo <= -40 && axn.ticks.includes(0), "an axis over negatives still passes through zero");
check(charts.scale(0, 0).hi > 0, "an all-zero chart still has an axis");
check(charts.tick(2500000, "GHS") === "2.5M" && charts.tick(250000, "") === "250k" && charts.tick(40, "%") === "40%"
  && charts.tick(0.25, "") === "0.25", "axis steps are short and exact");

/* ------------------------------------------------------------ answer tables */
check(md.sortNumber("GHS 1,234.50") === 1234.5 && md.sortNumber("12%") === 12 && md.sortNumber("(5,000)") === -5000
  && md.sortNumber("1.2M") === 1200000 && md.sortNumber("118 days") === 118 && md.sortNumber("−3") === -3,
  "cells read as figures: currency, commas, %, brackets, M, words after");
check(Number.isNaN(md.sortNumber("UBUNTU")) && Number.isNaN(md.sortNumber("Q3 2025"))
  && Number.isNaN(md.sortNumber("12 months ago and more 5")), "words are not figures");
check(md.sortNumber("12 months") === 12, "'12 months' is twelve, not twelve million");
check(md.sortDate("2026-10-18") > md.sortDate("18 Sep 2026") && md.sortDate("Oct 2026") > md.sortDate("Sep 2026"),
  "dates read as dates");

const rows = Array.from({ length: 25 }, (_, i) => `| Customer ${i + 1} | GHS ${((i * 7919) % 100) * 1000} | ${i % 5 ? `${i}%` : "—"} |`);
const doc = md.renderMarkdown(["| Customer | Owed | Share |", "|---|---:|---:|", ...rows].join("\n"));
const table = doc.find("table")[0];
const body = table.tBodies[0];
const visible = () => body.rows.filter((r) => !r.hidden);
check(body.rows.length === 25 && visible().length === 10, "a long table shows ten rows, with all 25 still in it");
const pager = doc.find(".md-pager")[0];
check(pager && pager.textContent.startsWith("1–10 of 25"), "the pager says which rows are showing");
const [prev, next, all] = pager.find("button");
check(prev.disabled && !next.disabled, "on the first page only Next works");
next.onclick();
check(visible()[0].cells[0].textContent === "Customer 11" && pager.textContent.startsWith("11–20 of 25"), "Next shows the next ten");
all.onclick();
check(visible().length === 25 && pager.textContent.startsWith("All 25 rows"), "Show all shows every row");
all.onclick();
const owedHead = table.tHead.rows[0].cells[1];
check(owedHead.textContent === "Owed", "the heading's text is unchanged (Excel reads it)");
owedHead.find("button")[0].onclick();
const owed = body.rows.map((r) => md.sortNumber(r.cells[1].textContent));
check(owedHead.getAttribute("aria-sort") === "descending" && owed.every((v, i) => !i || owed[i - 1] >= v),
  "a figures column sorts largest first, by value not by text");
check(visible().length === 10 && visible()[0] === body.rows[0], "sorting goes back to the first page");
owedHead.find("button")[0].onclick();
check(owedHead.getAttribute("aria-sort") === "ascending", "a second click sorts the other way");
const shareHead = table.tHead.rows[0].cells[2];
shareHead.find("button")[0].onclick();
const share = body.rows.map((r) => r.cells[2].textContent);
check(share.slice(-5).every((v) => v === "—") && share[0] === "24%", "blanks sort last; 24% before 9%");
const nameHead = table.tHead.rows[0].cells[0];
nameHead.find("button")[0].onclick();
check(body.rows[0].cells[0].textContent === "Customer 1" && body.rows[1].cells[0].textContent === "Customer 2",
  "a text column sorts A to Z, Customer 2 before Customer 10");

const short = md.renderMarkdown("| A | B |\n|---|---|\n| x | 1 |\n| y | 2 |");
check(short.find(".md-pager").length === 0 && short.find(".md-sort").length === 2, "a short table sorts but has no pager");

/* ------------------------------------------------------------- copying */
const answer = [
  "**Customers owe GHS 9.18M.**", "",
  "```figures", JSON.stringify([{ label: "Owed to us", value: "GHS 9.18M", note: "806 invoices" }]), "```", "",
  "```chart", JSON.stringify({ type: "combo", title: "Sales and margin", unit: "GHS", unit2: "%", labels: ["Jan"],
    series: [{ name: "Sales", values: [1200] }, { name: "Margin", values: [30] }] }), "```", "",
  "```chart", "not json", "```", "",
  "| Who | Owed |", "|---|---|", "| UBUNTU | 636,675 |", "",
  "```followups", JSON.stringify(["Next?"]), "```",
].join("\n");
const said = md.answerAsText(answer);
check(said.includes("- Owed to us: GHS 9.18M (806 invoices)"), "copied: figure cards in words");
check(said.includes("Sales and margin:\n- Jan: Sales GHS 1,200, Margin 30%"), "copied: a chart's figures in words, each in its unit");
check(!said.includes("```") && !said.includes("Next?") && !said.includes("not json"),
  "copied: no JSON, no broken block, no suggested questions");
check(said.includes("| UBUNTU | 636,675 |"), "copied: tables kept as they are");

console.log(`charts: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
