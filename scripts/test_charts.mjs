/**
 * The answer's charts and tables, tested without a browser.
 *
 *     node scripts/test_charts.mjs
 *
 * frontend/src/legacy/charts.js and markdown.js are loaded as they ship, over a small
 * stand-in for the DOM (just what they call). Under test: every chart type draws from a
 * valid block and refuses a broken one -- a block that fails its checks is not drawn,
 * never drawn wrong -- the axes include zero, zeros draw nothing, long tables sort and
 * page with every row kept for Excel, and a copied answer says its charts in words.
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
    this.hidden = false; this.listeners = {};
  }
  get className() { return this.attrs.class || ""; }
  set className(v) { this.attrs.class = String(v); }
  get classList() {
    const me = this;
    return {
      add: (c) => { if (!me.classList.contains(c)) me.className = `${me.className} ${c}`.trim(); },
      contains: (c) => me.className.split(/\s+/).includes(c),
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
  remove() { Text.prototype.remove.call(this); }
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
}

globalThis.document = {
  createElement: (t) => new El(t),
  createElementNS: (ns, t) => new El(t, ns),
  createTextNode: (t) => new Text(t),
};
globalThis.window = { location: { origin: "http://cc.test" } };

const charts = await import("../frontend/src/legacy/charts.js");
const md = await import("../frontend/src/legacy/markdown.js");

let passed = 0;
let failed = 0;
function check(ok, what) {
  if (ok) passed++;
  else { failed++; console.log("FAIL:", what); }
}
const draw = (spec) => charts.renderBlock("chart", typeof spec === "string" ? spec : JSON.stringify(spec));

/* ------------------------------------------------------- the original three */
const bar = draw({ type: "bar", title: "Spend", unit: "GHS", labels: ["A", "B"], series: [{ name: "S", values: [10, 5] }] });
check(bar && bar.find(".md-bar").length === 2, "bar draws one row per name");
check(bar && bar.find(".md-chart-f").length === 1 && bar.find("button").map((b) => b.textContent).join() === "PNG,SVG",
  "every chart carries the Download control (PNG, SVG)");
check(draw({ type: "line", labels: ["Jan", "Feb"], series: [{ name: "S", values: [1, 2] }] })?.find("polyline").length === 1,
  "line still draws");
check(draw({ type: "donut", labels: ["X", "Y"], series: [{ name: "S", values: [3, 1] }] })?.find(".md-sl").length === 2,
  "donut still draws");
check(draw({ type: "pie", labels: ["X"], series: [{ values: [3] }] })?.find(".md-bar").length === 1,
  "an unknown type is still drawn as bars, as before");
check(draw({ type: "bar", labels: ["X", "Y"], series: [{ values: ["3", 2] }] }) !== null,
  "bar still reads a number written as text, as before");
check(draw("not json") === null, "a block that does not parse is not drawn");
check(draw({ type: "bar", labels: ["X"], series: [{ values: ["lots"] }] }) === null, "a value that is not a number: not drawn");
check(draw({ type: "line", labels: [], series: [{ values: [] }] }) === null, "no labels: not drawn");
check(draw({ type: "donut", labels: ["X", "Y"], series: [{ values: [0, 0] }] }) === null, "a donut of nothing: not drawn");

/* ------------------------------------------------------------ the new types */
const stacked = draw({
  type: "stacked", title: "Sales by line", unit: "GHS", labels: ["Jan", "Feb", "Mar"],
  series: [{ name: "Drugs", values: [100, 0, 80] }, { name: "Devices", values: [50, 60, 0] }],
});
check(stacked && stacked.find(".md-rect").length === 4, "stacked: one block per non-zero part, nothing for a zero");
check(stacked && stacked.find(".md-legend").length === 1 && stacked.find(".md-legend")[0].textContent.includes("Devices"),
  "stacked: a legend names every series");
check(stacked && stacked.find(".md-hit").every((h) => h.getAttribute("data-tip")) &&
  stacked.find(".md-hit")[0].getAttribute("data-tip").includes("Total: GHS 150"),
  "stacked: hovering a column says every part and the total");
const tickText = stacked ? stacked.find("text").map((t) => t.textContent) : [];
check(tickText.includes("0"), "stacked: the axis starts at zero");
check(draw({ type: "stacked", labels: ["A", "B"], series: [{ values: [5, -1] }] }) === null,
  "stacked refuses a negative part");

const grouped = draw({
  type: "grouped", labels: ["Accra", "Kumasi"],
  series: [{ name: "2025", values: [10, -4] }, { name: "2026", values: [12, 0] }],
});
check(grouped && grouped.find(".md-rect").length === 3, "grouped: a bar per value, none for zero, negatives drawn");
check(draw({ type: "grouped", labels: ["A"], series: [1, 2, 3, 4, 5].map((i) => ({ name: `${i}`, values: [i] })) }) === null,
  "grouped: more than four series is not drawn");

const combo = draw({
  type: "combo", title: "Sales and margin", unit: "GHS", unit2: "%", labels: ["Jan", "Feb"],
  series: [{ name: "Sales", values: [120000, 98000] }, { name: "Margin", values: [31.5, 28] }],
});
check(combo && combo.find(".md-rect").length === 2 && combo.find("polyline").length === 1,
  "combo: bars for the first series, a line for the second");
check(combo && combo.find("text").some((t) => t.textContent === "%") === false
  && combo.find("text").some((t) => /%$/.test(t.textContent)),
  "combo: the rate has its own axis in its own unit");
check(draw({ type: "combo", labels: ["Jan"], series: [{ values: [1] }] }) === null, "combo with one series: not drawn");

const hbar = draw({
  type: "hbar", unit: "GHS", labels: ["Small Pharmacy Ltd", "UBUNTU Medical Supplies Company Limited"],
  series: [{ name: "Owed", values: [1000, 636675] }],
});
const hrows = hbar ? hbar.find(".md-hbar") : [];
check(hrows.length === 2 && hrows[0].textContent.startsWith("1UBUNTU Medical Supplies Company Limited"),
  "hbar: ranked largest first, the whole long name kept, with its rank");
check(draw({ type: "hbar", labels: ["A"], series: [{ values: [1] }, { values: [2] }] }) === null,
  "hbar with two series: not drawn");
const hneg = draw({ type: "hbar", labels: ["Up", "Down"], series: [{ values: [10, -10] }] });
check(hneg && hneg.find(".md-hbar-t")[1].children[0].style.left === "0.00%"
  && hneg.find(".md-hbar-t")[0].children[0].style.left === "50.00%",
  "hbar: bars grow from zero, a negative one runs the other way");

const scatter = draw({
  type: "scatter", unit: "GHS", unit2: "days", labels: ["A", "B", "C"],
  series: [{ name: "Owed", values: [5, 10, 2] }, { name: "Overdue", values: [30, 90, 0] }],
});
check(scatter && scatter.find(".md-dot").length === 3 && scatter.find(".md-plab").length === 3,
  "scatter: a dot and a name for each point");
check(draw({ type: "scatter", labels: ["A"], series: [{ values: [1] }] }) === null, "scatter with one series: not drawn");

// The strict checks, the same for every new type.
for (const type of ["hbar", "stacked", "grouped", "combo", "scatter"]) {
  const two = type === "combo" || type === "scatter";
  const ok = { type, labels: ["A", "B"], series: two ? [{ values: [1, 2] }, { values: [3, 4] }] : [{ values: [1, 2] }] };
  check(draw(ok) !== null, `${type}: a valid block is drawn`);
  const bad = (mut) => { const s = JSON.parse(JSON.stringify(ok)); mut(s); return draw(s); };
  check(bad((s) => { s.series[0].values = [1]; }) === null, `${type}: a value missing for a label: not drawn`);
  check(bad((s) => { s.series[0].values = [1, "2"]; }) === null, `${type}: a number written as text: not drawn`);
  check(bad((s) => { s.series[0].values = [1, null]; }) === null, `${type}: a null value: not drawn`);
  check(bad((s) => { s.labels = []; s.series.forEach((x) => { x.values = []; }); }) === null, `${type}: no labels: not drawn`);
  check(bad((s) => { s.labels[0] = { html: "<b>x</b>" }; }) === null, `${type}: a label that is not text: not drawn`);
  check(bad((s) => { s.series = "x"; }) === null, `${type}: series not a list: not drawn`);
}

// Caps: drawn up to the cap, and said.
const many = Array.from({ length: 30 }, (_, i) => `M${i + 1}`);
const capped = draw({ type: "stacked", labels: many, series: [{ values: many.map(() => 1) }] });
check(capped && capped.find(".md-rect").length === 24 && capped.find(".md-chart-note")[0]?.textContent === "Showing the first 24 of 30.",
  "stacked: capped at 24 columns, and it says so");

// A label is text, never markup.
const sneaky = draw({ type: "hbar", labels: ["<img src=x onerror=alert(1)>"], series: [{ values: [1] }] });
check(sneaky && sneaky.find("img").length === 0, "a label is drawn as text, never as markup");

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
