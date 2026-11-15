/**
 * The designed screens' charts and tables, redrawn from the business's own records.
 *
 * The department screens were generated with charts and tables from a 2025 extract.
 * api/panels.py answers, per screen, the data behind each panel by the panel's own
 * heading; this file redraws the same marks -- the trend line, the bars, the stacked
 * bar, the table rows -- inside the same markup, so the design and the wording stay
 * and only the figures, names and dates change.
 *
 * Anything still showing the 2025 sample says so: a chart or table panel with no live
 * data, and every designed finding (.warn), carries the "illustrative" flag the cards
 * already use. Nothing from the API is written as HTML; every node is built here.
 */

import { guideBox } from "./guide.js";

export const PANEL_VIEWS = new Set(["sales", "proc", "inv", "eng", "cx", "fin", "hr", "it", "aud", "risk"]);

const SAMPLE = ".chartwrap, .bars, .stack, table.dt, .funnel";

export function renderPanels(root, viewKey, data, { onOpen, openDrawer, failed = false } = {}) {
  if (!root || !PANEL_VIEWS.has(viewKey)) return 0;
  // Until the answer is in, the designed panels are left alone: marking them and then
  // clearing the mark a moment later would flash.
  if (!data && !failed) return 0;
  const panels = data?.panels || {};
  let live = 0;

  root.querySelectorAll(".panel").forEach((panel) => {
    const title = panel.querySelector(".ph b")?.textContent?.trim();
    const spec = title ? panels[title] : null;
    if (!spec) {
      if (panel.dataset.live !== "1" && panel.querySelector(SAMPLE)) flag(panel);
      return;
    }
    try {
      if (draw(panel, spec, onOpen)) {
        panel.dataset.live = "1";
        delete panel.dataset.illustrative;
        unflag(panel);
        live += 1;
      } else {
        flag(panel);
      }
    } catch {
      // A panel whose markup is not what was expected stays as designed, flagged.
      flag(panel);
    }
  });

  renderFindings(root, data?.findings, failed);
  return live;
}

function draw(panel, spec, onOpen) {
  if (spec.subtitle) {
    const sub = panel.querySelector(".ph b + span");
    if (sub) sub.textContent = spec.subtitle;
  }
  if (spec.note !== undefined) {
    const thin = panel.querySelector(":scope > .thin");
    if (thin) {
      if (spec.note) {
        thin.textContent = spec.note;
        thin.hidden = false;
      } else {
        thin.hidden = true;
      }
    }
  }
  switch (spec.kind) {
    case "trend":
      return drawTrend(panel, spec);
    case "bars": {
      const ok = drawBars(panel, spec, onOpen);
      if (ok && spec.stack) drawStack(panel, { parts: spec.stack });
      return ok;
    }
    case "stack":
      return drawStack(panel, spec);
    case "table":
      return drawTable(panel, spec, onOpen);
    case "guide":
      return drawGuide(panel, spec);
    case "funnel":
      return drawFunnel(panel, spec, onOpen);
    default:
      return false;
  }
}

/* ------------------------------------------------------------------ trend */
function drawTrend(panel, spec) {
  const wrap = panel.querySelector(".chartwrap");
  const values = (spec.values || []).map(Number);
  if (!wrap || !values.length || values.some((v) => !Number.isFinite(v))) return false;
  const max = Math.max(...values, 0) || 1;
  const n = values.length;
  const pts = values.map((v, i) => {
    const x = n === 1 ? 50 : (100 * i) / (n - 1);
    const y = 38 - (36 * Math.max(v, 0)) / max;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const line = wrap.querySelector("polyline");
  const area = wrap.querySelector("polygon");
  if (!line) return false;
  line.setAttribute("points", pts.join(" "));
  if (area) {
    const first = pts[0].split(",")[0];
    const last = pts[pts.length - 1].split(",")[0];
    area.setAttribute("points", `${first},38 ${pts.join(" ")} ${last},38`);
  }
  const xlab = wrap.querySelector(".xlab");
  if (xlab) {
    xlab.textContent = "";
    (spec.labels || []).forEach((l) => {
      const s = el("span", null, l);
      s.style.flex = "1";
      s.style.textAlign = "center";
      xlab.append(s);
    });
  }
  const ymax = wrap.querySelector(".ymax");
  if (ymax && spec.peak) ymax.textContent = spec.peak;
  return true;
}

/* ------------------------------------------------------------------ bars */
function drawBars(panel, spec, onOpen) {
  const box = panel.querySelector(".bars");
  if (!box) return false;
  const rows = spec.rows || [];
  box.textContent = "";
  if (!rows.length) {
    box.append(el("div", "thin", spec.empty || "Nothing recorded."));
    return true;
  }
  const max = Math.max(...rows.map((r) => Number(r.value) || 0), 0) || 1;
  rows.forEach((r) => {
    const row = el("div", "barrow");
    const fill = el("div", "barfill");
    fill.style.width = `${Math.max(0, (100 * (Number(r.value) || 0)) / max).toFixed(1)}%`;
    fill.style.background = `var(--${r.tone || "accent"})`;
    const track = el("div", "bartrack");
    track.append(fill);
    const val = el("div", "barval", r.display ?? String(r.value ?? ""));
    if (r.note) val.append(el("span", "barnote", r.note));
    row.append(el("div", "barlab", r.label), track, val);
    if (r.drill && onOpen) clickable(row, () => onOpen({ drill: r.drill, label: r.label }));
    box.append(row);
  });
  return true;
}

/* ------------------------------------------------------------------ stack */
function drawStack(panel, spec) {
  const bar = panel.querySelector(".stack");
  const parts = spec.parts || [];
  if (!bar || !parts.length) return false;
  const total = parts.reduce((s, p) => s + (Number(p.value) || 0), 0) || 1;
  const segs = [...bar.children];
  parts.forEach((p, i) => {
    if (segs[i]) segs[i].style.width = `${((100 * (Number(p.value) || 0)) / total).toFixed(2)}%`;
  });
  const key = panel.querySelector(".stackkey");
  if (key) {
    [...key.querySelectorAll("b")].forEach((b, i) => {
      if (parts[i]) b.textContent = parts[i].display ?? String(parts[i].value);
    });
  }
  return true;
}

/* ------------------------------------------------------------------ funnel */
function drawFunnel(panel, spec, onOpen) {
  // The designed stages are redrawn in place, one for one: the bar, "Stage · count ·
  // value", and the line under it.
  const stages = [...panel.querySelectorAll(".funnel .fstage")];
  const rows = spec.stages || [];
  if (!stages.length || stages.length !== rows.length) return false;
  const max = Math.max(...rows.map((r) => Number(r.count) || 0), 0) || 1;
  rows.forEach((r, i) => {
    const stage = stages[i];
    const bar = stage.querySelector(".fbar");
    if (bar) bar.style.width = `${Math.max(2, (100 * (Number(r.count) || 0)) / max).toFixed(1)}%`;
    const txt = stage.querySelector(".ftxt");
    if (txt) {
      txt.textContent = "";
      txt.append(el("b", null, r.label), document.createTextNode(
        ` · ${Number(r.count || 0).toLocaleString("en-GB")}${r.display ? ` · ${r.display}` : ""}`));
    }
    const note = stage.querySelector(".fnote");
    if (note) {
      note.textContent = r.note || "";
      note.hidden = !r.note;
    }
    if (r.drill && onOpen) clickable(stage, () => onOpen({ drill: r.drill, label: r.label }));
  });
  return true;
}

/* ------------------------------------------------------------------ table */
function drawTable(panel, spec, onOpen) {
  const table = panel.querySelector("table.dt");
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
  panel.querySelectorAll(":scope > :not(.ph)").forEach((n) => { n.hidden = true; });
  let box = panel.querySelector(":scope > .guide[data-prov]");
  if (box) box.remove();
  box = guideBox(spec.guide);
  box.dataset.prov = "1";
  panel.append(box);
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
    delete w.dataset.illustrative;
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

/* ------------------------------------------------------------------ flags */
function flag(node, text = "illustrative") {
  node.dataset.illustrative = "1";
  const where = node.classList.contains("warn") ? node : node.querySelector(".ph > div") || node;
  let pill = where.querySelector(":scope > .flag[data-prov]");
  if (!pill) {
    pill = el("span", "flag f-dim", text);
    pill.dataset.prov = "1";
    pill.style.marginLeft = "8px";
    if (node.classList.contains("warn")) where.prepend(pill);
    else where.append(pill);
  }
}

function unflag(node) {
  node.querySelectorAll(".ph .flag[data-prov]").forEach((p) => p.remove());
}

function clickable(node, fn) {
  node.classList.add("clickable");
  node.setAttribute("role", "button");
  node.setAttribute("tabindex", "0");
  node.addEventListener("click", fn);
  node.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
