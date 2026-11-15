/**
 * The designed screens' charts and tables, drawn from the business's own records.
 *
 * api/panels.py answers, per screen, the data behind each panel by the panel's own
 * heading; this file draws the marks -- the trend line, the bars, the stacked bar, the
 * table rows, the bullet list -- inside the designed markup, so the design and the
 * wording stay and the figures, names and dates are the business's. The generated
 * markup carries no sample: its marks are empty until the answer arrives.
 *
 * A panel the server could not answer says so under its heading -- "can't reach the
 * business's ERPNext", or "could not be read" -- and never shows anything it did not
 * read. Nothing from the API is written as HTML; every node is built here.
 */

import { guideBox } from "./guide.js";

export const PANEL_VIEWS = new Set(["sales", "proc", "inv", "eng", "cx", "fin", "hr", "it", "aud", "risk"]);

// The designed marks a panel draws its answer into.
const MARKS = ".chartwrap, .bars, .stack, .stackkey, table.dt, .funnel, ul.bul";

export function renderPanels(root, viewKey, data, { onOpen, openDrawer, failed = false } = {}) {
  if (!root || !PANEL_VIEWS.has(viewKey)) return 0;
  // The previous screen's answer, still in hand while this one's is on its way.
  if (data?.view && data.view !== viewKey) return 0;
  if (!data && !failed) return 0;
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
      return;
    }
    if (spec.kind === "failed") {
      notice(panel, "This could not be read from ERPNext just now. It will be tried again shortly.");
      return;
    }
    try {
      if (draw(panel, { ...spec, _cur: data?.currency || "" }, onOpen)) {
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
  const who = data?.business ? `${data.business}'s` : "the business's";
  let when = "";
  if (data?.last_loaded) {
    const d = new Date(String(data.last_loaded).replace(" ", "T"));
    if (!Number.isNaN(d.getTime())) {
      when = ` Last loaded ${d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}.`;
    }
  }
  return `Can't reach ${who} ERPNext right now — showing nothing new until it's back.${when}`;
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
  panel.querySelectorAll(":scope > .thin[data-designed]").forEach((n) => {
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

function draw(panel, spec, onOpen) {
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
  const box = ensure(panel, ".bars", () => el("div", "bars"));
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
