/**
 * The designed screens' charts and tables, drawn from the business's own records.
 *
 * api/panels.py answers, per screen, the data behind each panel by the panel's own
 * heading; this file draws the marks -- the trend line, the bars, the stacked bar, the
 * table rows, the bullet list -- inside the designed markup, so the design and the
 * wording stay and the figures, names and dates are the business's. The generated
 * markup carries no sample: its marks are empty until the answer arrives.
 *
 * The chart panels -- trend, bars, stack, funnel -- are drawn by viz.js (ECharts): the
 * designed mark is kept in the markup, hidden, and the interactive chart sits in its
 * place under the same heading, with the same figures and the same drill (a click on a
 * bar, slice or stage opens what clicking the designed row opened). Each panel's chart
 * is made once and updated in place on every refresh, so the screen's minute redraw
 * never stacks charts up. A panel that shows parts of a whole (COMPOSITION) offers a
 * donut and a pie in its switcher; a trend offers line, area and bars.
 *
 * A panel the server could not answer says so under its heading -- "not updated yet:
 * the business's ERPNext is taking longer than usual to answer" (reach.js), or "could
 * not be read" -- and never shows anything it did not read. Nothing from the API is written as HTML; every node is built here.
 */

import { drawCover } from "./cover.js";
import { guideBox } from "./guide.js";
import { UPDATING, WAITING, waitingLine } from "./reach.js";
import { createViz, vizOf } from "./viz.js";

export const PANEL_VIEWS = new Set(["sales", "proc", "inv", "eng", "cx", "fin", "hr", "it", "aud", "risk"]);

// The bar panels whose rows are the parts of one whole, so a donut or pie is a true
// picture of them. shares "shown": the parts of what the panel shows (its largest
// orders, say), which the chart says, rather than of the business's whole. money: the
// rows are amounts in the business's currency (a donut's total then says so).
const COMPOSITION = {
  "Where the value sits": { shares: true, money: true },
  "Where people work": { shares: true },
  "Where people are": { shares: true },
  "What they are complaining about": { shares: true },
  "Where the money goes": { shares: "shown", money: true },
};

// The designed marks a panel draws its answer into.
const MARKS = ".chartwrap, .bars, .stack, .stackkey, table.dt, .funnel, ul.bul, .cover";

export function renderPanels(root, viewKey, data, { onOpen, openDrawer, scope, failed = false } = {}) {
  if (!root || !PANEL_VIEWS.has(viewKey)) return 0;
  // The previous screen's answer, still in hand while this one's is on its way.
  if (data?.view && data.view !== viewKey) return 0;
  if (!data && !failed) {
    // Asked for, and on its way: each panel that will be drawn says it is being read
    // (once the answer is in, reset() takes the line away again).
    root.querySelectorAll(".panel").forEach((panel) => {
      if (panel.querySelector(".bk") || panel.dataset.live === "1" || !panel.querySelector(MARKS)) return;
      if (panel.querySelector(":scope > .thin[data-prov]")) return;
      notice(panel, UPDATING);
    });
    return 0;
  }
  const panels = data?.panels || {};
  let live = 0;

  // The line under the screen's heading, and the currency in the designed headings.
  const when = root.querySelector(".topbar .when");
  if (when && data?.when) when.textContent = data.when;
  if (data?.currency) {
    root.querySelectorAll("[data-cur]").forEach((n) => { n.textContent = data.currency; });
  }

  root.querySelectorAll(".panel").forEach((panel) => {
    const title = panel.querySelector(".ph b")?.textContent?.trim();
    // A panel of tiles is filled by the figures (hydrate.js), not by this answer.
    if (panel.querySelector(".bk")) return;
    reset(panel);
    const spec = title ? panels[title] : null;
    if (!spec) {
      // Nothing answered for it: its marks are hidden and the panel says why, never
      // leaving anything on show that was not read from the business.
      if (panel.querySelector(MARKS) || failed) {
        notice(panel, failed ? "Not available just now. It will be read again shortly."
          : "Nothing is measured here yet.");
      }
      return;
    }
    if (spec.kind === "unreachable") {
      notice(panel, unreachable(data));
      // A designed "Reading …" line under the heading would say it is still on its way.
      const sub = panel.querySelector(".ph b + span");
      if (sub && /…$/.test(sub.textContent.trim())) {
        sub.dataset.designed = sub.textContent;
        sub.textContent = WAITING.line;
      }
      return;
    }
    if (spec.kind === "failed") {
      notice(panel, "This could not be read from ERPNext just now. It will be tried again shortly.");
      return;
    }
    try {
      if (draw(panel, { ...spec, _cur: data?.currency || "" }, onOpen, { openDrawer, scope })) {
        panel.dataset.live = "1";
        live += 1;
      } else {
        notice(panel, "This could not be drawn.");
      }
    } catch {
      notice(panel, "This could not be drawn.");
    }
  });

  renderFindings(root, data?.findings, failed);
  return live;
}

function unreachable(data) {
  return waitingLine(data?.business, data?.last_loaded);
}

/** Undo what a previous answer did to the panel, so a new answer starts from the design. */
function reset(panel) {
  panel.querySelectorAll("[data-prov]").forEach((n) => {
    if (!n.classList.contains("flag")) n.remove();
  });
  panel.querySelectorAll("[data-hid]").forEach((n) => {
    n.style.display = "";
    delete n.dataset.hid;
  });
  panel.querySelectorAll(":scope > .thin[data-designed], :scope > .ph span[data-designed]").forEach((n) => {
    n.textContent = n.dataset.designed;
    delete n.dataset.designed;
  });
  delete panel.dataset.built;
}

// Hidden by style, not the hidden attribute: the designed marks set their own display
// (.funnel is a flex box), which the attribute does not override.
function hide(node) {
  if (!node || node.dataset.hid || node.style.display === "none") return;
  node.style.display = "none";
  node.dataset.hid = "1";
}

/** A calm line under the heading in place of the panel's marks. */
function notice(panel, text) {
  panel.querySelectorAll(`:scope > :not(.ph)`).forEach(hide);
  const n = el("div", "thin", text);
  n.dataset.prov = "1";
  panel.querySelector(".ph")?.after(n);
}

function draw(panel, spec, onOpen, ctx = {}) {
  if (spec.subtitle) {
    const sub = panel.querySelector(".ph b + span");
    if (sub) sub.textContent = spec.subtitle;
  }
  let ok;
  switch (spec.kind) {
    case "trend":
      ok = drawTrend(panel, spec);
      break;
    case "bars": {
      ok = drawBars(panel, spec, onOpen);
      if (ok && spec.stack) drawStack(panel, { parts: spec.stack });
      break;
    }
    case "stack":
      ok = drawStack(panel, spec);
      break;
    case "table":
      ok = drawTable(panel, spec, onOpen);
      break;
    case "list":
      ok = drawList(panel, spec);
      break;
    case "guide":
      return drawGuide(panel, spec);
    case "cover":
      // Promised Orders — Cover (legacy/cover.js) draws its own reading and guide.
      return drawCover(panel, spec, ctx);
    case "funnel":
      ok = drawFunnel(panel, spec, onOpen);
      break;
    default:
      return false;
  }
  if (ok) writeNote(panel, spec);
  return ok;
}

/**
 * The short reading under the marks. A panel designed with its own marks has a note
 * written about them, which the answer's note replaces ("" hides it). A panel designed
 * as a description only (the "Not yet measured" tab) keeps its description, and the
 * reading goes under the marks drawn for it.
 */
function writeNote(panel, spec) {
  if (spec.note === undefined) return;
  if (panel.dataset.built === "1") {
    if (spec.note) {
      const n = el("div", "thin", spec.note);
      n.dataset.prov = "1";
      panel.append(n);
    }
    return;
  }
  const thin = panel.querySelector(":scope > .thin");
  if (!thin) return;
  if (spec.note) {
    if (!thin.dataset.designed) thin.dataset.designed = thin.textContent;
    thin.textContent = spec.note;
  } else {
    hide(thin);
  }
}

/**
 * A mark the design did not draw for this panel -- its "Not yet measured" description
 * stood alone -- is built here, under the description, and taken away again by reset().
 */
function ensure(panel, selector, make) {
  let node = panel.querySelector(selector);
  if (node) return node;
  node = make();
  node.dataset.prov = "1";
  panel.dataset.built = "1";
  panel.append(node);
  return node;
}

/* ------------------------------------------------------------------ charts */
/**
 * The panel's interactive chart for one of its designed marks ("slot"), made the first
 * time and updated in place after, with the designed mark hidden under it.
 */
function chartIn(panel, slot, anchor, model, { onPick, onView } = {}) {
  const title = panel.querySelector(".ph b")?.textContent?.trim() || "";
  const opts = { key: `panel:${title}:${slot}`, title, compact: true, onPick, onView };
  const host = panel.querySelector(`[data-viz="${slot}"]`);
  let viz = vizOf(host);
  if (viz) {
    viz.update(model, opts);
  } else {
    host?.remove();
    viz = createViz(model, opts);
    viz.node.dataset.viz = slot;
    anchor.after(viz.node);
  }
  hide(anchor);
  return viz;
}

/** A panel's chart for this slot is not wanted this time (an empty answer). */
function noChart(panel, slot) {
  hide(panel.querySelector(`[data-viz="${slot}"]`));
}

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);

/* ------------------------------------------------------------------ trend */
function drawTrend(panel, spec) {
  const wrap = panel.querySelector(".chartwrap");
  const values = (spec.values || []).map(Number);
  if (!wrap || !values.length || values.some((v) => !Number.isFinite(v))) return false;
  const labels = (spec.labels || []).map(String);
  if (labels.length !== values.length) return false;
  const title = panel.querySelector(".ph b")?.textContent?.trim() || "";
  let top = 0;
  values.forEach((v, i) => { if (v > values[top]) top = i; });
  chartIn(panel, "trend", wrap, {
    type: "area", title, unit: spec._cur || "", unit2: "", labels, total: labels.length, note: "",
    series: [{ name: title, values }], time: true,
    peak: spec.peak && values[top] > 0 ? { index: top, text: spec.peak } : null,
  });
  return true;
}

/* ------------------------------------------------------------------ bars */
function drawBars(panel, spec, onOpen) {
  const box = ensure(panel, ".bars", () => el("div", "bars"));
  const rows = (spec.rows || []).filter((r) => r && r.label !== undefined && r.label !== null);
  box.textContent = "";
  if (!rows.length) {
    noChart(panel, "bars");
    box.append(el("div", "thin", spec.empty || "Nothing recorded."));
    return true;
  }
  const title = panel.querySelector(".ph b")?.textContent?.trim() || "";
  const drills = rows.some((r) => r.drill) && onOpen;
  chartIn(panel, "bars", box, {
    type: "hbar", title, unit: COMPOSITION[title]?.money ? spec._cur || "" : "", unit2: "",
    labels: rows.map((r) => String(r.label)),
    series: [{ name: title, values: rows.map((r) => num(r.value)) }],
    displays: rows.map((r) => (r.display ?? String(r.value ?? ""))),
    notes: rows.map((r) => r.note || ""),
    colors: rows.map((r) => r.tone || "accent"),
    shares: COMPOSITION[title]?.shares || false, total: rows.length, note: "",
  }, {
    onPick: drills ? (i) => rows[i]?.drill && onOpen({ drill: rows[i].drill, label: rows[i].label }) : undefined,
  });
  return true;
}

/* ------------------------------------------------------------------ stack */
function drawStack(panel, spec) {
  const bar = panel.querySelector(".stack");
  const parts = spec.parts || [];
  if (!bar || !parts.length) return false;
  const segs = [...bar.children];
  // The designed segments carry the meaning of each part's colour (under a month is
  // good, over three is critical); the chart keeps it.
  const tones = parts.map((_, i) => {
    const m = String(segs[i]?.getAttribute("style") || "").match(/var\(--([\w-]+)\)/);
    return m ? m[1] : "accent";
  });
  const key = panel.querySelector(".stackkey");
  if (key) {
    [...key.querySelectorAll("b")].forEach((b, i) => {
      if (parts[i]) b.textContent = parts[i].display ?? String(parts[i].value);
    });
  }
  const title = panel.querySelector(".ph b")?.textContent?.trim() || "";
  chartIn(panel, "stack", bar, {
    type: "strip", title, unit: "", unit2: "", labels: parts.map((p) => String(p.label ?? "")),
    series: [{ name: title, values: parts.map((p) => Math.max(0, num(p.value))) }],
    displays: parts.map((p) => p.display ?? String(p.value ?? "")), colors: tones,
    shares: true, total: parts.length, note: "",
  }, {
    // The designed key says each part's figure beside its colour: it is the legend while
    // the parts are drawn as one bar, and the chart's own legend takes over otherwise.
    onView: (v) => { if (key && !key.dataset.hid) key.style.display = v === "strip" ? "" : "none"; },
  });
  return true;
}

/* ------------------------------------------------------------------ funnel */
function drawFunnel(panel, spec, onOpen) {
  // One stage for each designed stage, in order: the same stages, now drawn as a
  // funnel, each opening what the designed stage opened.
  const box = panel.querySelector(".funnel");
  const stages = box ? [...box.querySelectorAll(".fstage")] : [];
  const rows = spec.stages || [];
  if (!stages.length || stages.length !== rows.length) return false;
  const title = panel.querySelector(".ph b")?.textContent?.trim() || "";
  const drills = rows.some((r) => r.drill) && onOpen;
  chartIn(panel, "funnel", box, {
    type: "funnel", title, unit: "", unit2: "", labels: rows.map((r) => String(r.label ?? "")),
    series: [{ name: "Count", values: rows.map((r) => Math.max(0, num(r.count))) }],
    displays: rows.map((r) => r.display || ""), notes: rows.map((r) => r.note || ""),
    total: rows.length, note: "",
  }, {
    onPick: drills ? (i) => rows[i]?.drill && onOpen({ drill: rows[i].drill, label: rows[i].label }) : undefined,
  });
  return true;
}

/* ------------------------------------------------------------------ table */
function drawTable(panel, spec, onOpen) {
  const table = ensure(panel, "table.dt", () => {
    const t = el("table", "dt");
    const tr = el("tr");
    (spec.columns || []).forEach((c) => {
      const th = el("th", null, c.text || "");
      if (c.cur && spec._cur) th.append(document.createTextNode(` ${spec._cur}`));
      if (c.num) th.style.textAlign = "right";
      tr.append(th);
    });
    const thead = el("thead");
    thead.append(tr);
    t.append(thead, el("tbody"));
    return t;
  });
  const body = table?.querySelector("tbody");
  if (!body) return false;
  const cols = table.querySelectorAll("thead th").length || 1;
  body.textContent = "";
  const rows = spec.rows || [];
  if (!rows.length) {
    const tr = el("tr");
    const td = el("td", null, spec.empty || "Nothing recorded.");
    td.colSpan = cols;
    td.style.color = "var(--dim)";
    tr.append(td);
    body.append(tr);
    return true;
  }
  rows.forEach((r) => {
    const tr = el("tr");
    // A rule above a subtotal row, as the designed tables draw one.
    if (r.rule) tr.style.borderTop = "2px solid var(--line2)";
    (r.cells || []).forEach((c) => {
      const td = el("td", c.num ? "num" : null);
      if (c.tone) td.style.color = `var(--${c.tone})`;
      if (c.nowrap) td.style.whiteSpace = "nowrap";
      if (c.ask) {
        const b = el("button", "btn", c.text || "Ask");
        b.type = "button";
        b.addEventListener("click", () => window.ask2?.(c.ask));
        td.append(b);
      } else if (c.tag) {
        td.append(el("span", `tag ${c.tag}`, c.text || ""));
      } else if (c.drill && onOpen) {
        const a = el("span", "lnk", c.text || "");
        a.addEventListener("click", () => onOpen({ drill: c.drill, label: c.text }));
        td.append(a);
      } else if (c.bold) {
        td.append(el("b", null, c.text ?? ""));
      } else {
        td.textContent = c.text ?? "";
      }
      // The designed cells' small print: a coloured dot before the text, a smaller face,
      // and a second line under it (a doctype, an address, what a role allows).
      if (c.dot) {
        const dot = el("span", null, "\u25CF ");
        dot.style.color = `var(--${c.dot})`;
        td.prepend(dot);
      }
      if (c.small) td.style.fontSize = "var(--fs-xs)";
      if (c.sub) {
        const sub = el("div", null, c.sub);
        sub.style.fontSize = "var(--fs-2xs)";
        sub.style.color = `var(--${c.sub_tone || "dim"})`;
        if (c.sub_tone) sub.style.marginTop = "3px";
        td.append(sub);
      }
      tr.append(td);
    });
    body.append(tr);
  });
  return true;
}

/* ------------------------------------------------------------------ guide */
// Nothing recorded in ERPNext behind this panel yet: the sample marks go and the guide
// (what to record there, and where) takes their place, under the designed heading.
function drawGuide(panel, spec) {
  if (!spec.guide) return false;
  panel.querySelectorAll(":scope > :not(.ph)").forEach(hide);
  const box = guideBox(spec.guide);
  box.dataset.prov = "1";
  panel.append(box);
  return true;
}

/* ------------------------------------------------------------------ list */
function drawList(panel, spec) {
  const ul = ensure(panel, "ul.bul", () => el("ul", "bul"));
  ul.textContent = "";
  (spec.items || []).forEach((it) => ul.append(el("li", null, it.text || "")));
  return true;
}

/* ------------------------------------------------------------------ findings */
// The designed finding boxes (.warn) were written about the 2025 extract. The server
// sends the screen's live findings (api/panels.py FINDINGS): each fills a box in turn
// -- a heading, a sentence, and an "Ask" button when it has a question -- and a box
// with no live finding to carry is hidden, never left showing the old one.
function renderFindings(root, findings, failed) {
  const boxes = [...root.querySelectorAll(".warn")];
  if (!boxes.length) return;
  if (!Array.isArray(findings)) {
    if (failed) boxes.forEach((w) => { w.hidden = true; });
    else boxes.forEach((w) => { if (w.dataset.live !== "1") w.hidden = true; });
    return;
  }
  boxes.forEach((w, i) => {
    const f = findings[i];
    if (!f) {
      w.hidden = true;
      return;
    }
    w.hidden = false;
    w.dataset.live = "1";
    w.textContent = "";
    if (f.guide) {
      w.append(guideBox(f.guide, { compact: true }));
      return;
    }
    if (f.title) w.append(el("b", null, f.title));
    if (f.text) w.append(document.createTextNode(` ${f.text}`));
    if (f.ask) {
      const acts = el("div", "acts");
      const b = el("button", "btn", f.ask_label || "Ask about it");
      b.type = "button";
      b.addEventListener("click", () => window.ask2?.(f.ask));
      acts.append(b);
      w.append(acts);
    }
  });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
