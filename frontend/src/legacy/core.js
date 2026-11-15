/**
 * The management screens (Home to Internal Audit), after their figures, panels, alerts
 * and work have been drawn: what is left so that nothing on them is ever a sample.
 *
 *   settle      a card or tile whose figure could not be read shows a dash and says so
 *               ("not read", or "can't reach" when the business's ERPNext is down) --
 *               never the designed figure, never "illustrative"
 *   notes       a tile with an empty footnote takes its figure's note
 *   findings    Business Overview's finding box (api/panels_core.ops_findings)
 *   health      Business Health's sentence on what is going badly is drawn by
 *               home.js; the questions to ask first come from the open alerts here
 *   brief       the Executive Summary's line under its heading
 *
 * Built as DOM, never HTML from the server.
 */

import { CARD_KPIS, TILE_KPIS } from "./hydrate.js";
import { HEALTH_QUESTIONS } from "./home.js";
import { WORK_TILES } from "./work.js";

/** The screens this file finishes. Each .kpi and .bk on them has a figure or a guide. */
export const CORE_VIEWS = new Set(["command", "brief", "myday", "ops", "health", "approvals",
  "delegation", "risk", "it", "aud", "reports", "ask"]);
/** Core screens whose findings come from api/panels.get (not in panels.js PANEL_VIEWS). */
export const CORE_PANEL_VIEWS = new Set(["ops"]);
/** Cards that open a screen rather than records, once they hold a figure. */
const CARD_GO = { aud: { "Raise today": "health" } };

export function renderCore(root, view, state = {}) {
  if (!root || !CORE_VIEWS.has(view)) return;
  const { figures, figuresDone, panels, alerts, work, workDone, isWork, reachDown } = state;
  const figs = { ...(figures || {}), ...((work && work.figures) || {}) };
  const done = figuresDone && (!isWork || workDone);
  // While the figures are on their way a card is a quiet placeholder, never "illustrative".
  root.querySelectorAll(".kpi[data-illustrative], .bk[data-illustrative]").forEach((n) => {
    delete n.dataset.illustrative;
    n.querySelectorAll(".flag[data-prov]").forEach((f) => {
      if (f.textContent === "illustrative") f.remove();
    });
  });
  // A panel that could not be read says so; its table holds no sample rows to show.
  root.querySelectorAll(".panel[data-illustrative]").forEach((panel) => {
    delete panel.dataset.illustrative;
    panel.querySelectorAll(".flag[data-prov]").forEach((f) => {
      f.textContent = reachDown ? "can't reach" : "not read";
    });
    const sub = panel.querySelector(".ph b + span");
    if (sub) sub.textContent = reachDown ? "Can't reach ERPNext just now" : "Could not be read just now";
  });
  root.querySelectorAll(".kpi").forEach((card) => finish(card, view, "card", figs, done, reachDown));
  root.querySelectorAll(".bk").forEach((tile) => finish(tile, view, "tile", figs, done, reachDown));
  if (CORE_PANEL_VIEWS.has(view) && panels) findings(root, panels.findings);
  if (view === "health" && alerts) askFirst(root, alerts.alerts || []);
  if (view === "brief") briefWhen(root, alerts);
  Object.entries(CARD_GO[view] || {}).forEach(([label, to]) => {
    const card = [...root.querySelectorAll(".kpi")].find((c) => c.querySelector(".lab")?.textContent?.trim() === label);
    if (card && card.dataset.live === "1" && !card.dataset.setup) {
      card.onclick = () => window.go?.(to);
    }
  });
}

function figureFor(node, view, kind, figs) {
  const label = node.querySelector(kind === "card" ? ".lab" : ".l")?.textContent?.trim();
  if (!label) return null;
  if (kind === "card") return figs[CARD_KPIS[view]?.[label]] || null;
  const spec = TILE_KPIS[view]?.[label] || WORK_TILES[view]?.[label];
  if (spec) return figs[spec.key] || null;
  if (view === "health") return figs[HEALTH_QUESTIONS[label]] || null;
  return null;
}

function finish(node, view, kind, figs, done, reachDown) {
  const f = figureFor(node, view, kind, figs);
  const st = f?.data_status?.state;
  if (f && node.dataset.live === "1") {
    if (st === "unreachable" && !node.classList.contains("q")) flag(node, "can't reach", "f-dim");
    if (kind === "tile" && f.note) {
      const foot = node.querySelector(".v");
      if (foot && !foot.textContent.replace(/ /g, "").trim()) foot.textContent = f.note;
    }
    return;
  }
  if (f && st === "needs_setup" && node.dataset.live !== "1") {
    // A tile that opens another screen keeps doing so; it says what is missing, and the
    // screen it opens carries the guide.
    const v = node.querySelector(kind === "card" ? ".val" : ".n");
    if (v) v.textContent = "—";
    const foot = node.querySelector(kind === "card" ? ".delta" : ".v");
    if (foot) foot.textContent = f.note || "not recorded yet";
    flag(node, "set up", "f-dim");
    delete node.dataset.loading;
    node.dataset.live = "1";
    return;
  }
  if (!done || node.dataset.live === "1") return;
  // Asked for and not answered: say so, and keep nothing designed on the card.
  delete node.dataset.illustrative;
  const val = node.querySelector(kind === "card" ? ".val" : ".n");
  if (val) val.textContent = "—";
  const foot = node.querySelector(kind === "card" ? ".delta" : ".v");
  if (foot) foot.textContent = reachDown ? "can't reach ERPNext just now" : "could not be read just now";
  const designed = node.querySelector(".khead > .flag:not([data-prov])");
  if (designed) {
    designed.className = "flag f-dim";
    designed.textContent = reachDown ? "Can't reach" : "Not read";
  } else {
    flag(node, reachDown ? "can't reach" : "not read", "f-dim");
  }
  if (!/(^|[^\w.])go\(/.test(node.getAttribute("onclick") || "")) node.removeAttribute("onclick");
}

function flag(node, text, tone) {
  const head = node.classList.contains("bk") ? node : node.querySelector(".khead");
  if (!head) return;
  let pill = head.querySelector(":scope > .flag[data-prov]");
  if (!pill) {
    pill = el("span", `flag ${tone}`);
    pill.dataset.prov = "1";
    head.append(pill);
  }
  pill.className = `flag ${tone}`;
  pill.textContent = text;
}

function findings(root, list) {
  const boxes = [...root.querySelectorAll(".warn")];
  boxes.forEach((w, i) => {
    const f = Array.isArray(list) ? list[i] : null;
    if (!f) {
      w.hidden = true;
      return;
    }
    w.hidden = false;
    w.dataset.live = "1";
    w.textContent = "";
    if (f.title) w.append(el("b", null, f.title));
    if (f.text) w.append(document.createTextNode(` ${f.text}`));
  });
}

function askFirst(root, alerts) {
  const note = root.querySelector("#hh-ask");
  const ul = note?.querySelector("ul");
  if (!ul) return;
  ul.textContent = "";
  alerts.slice(0, 3).forEach((a) => {
    const li = el("li");
    const b = el("button", "lnk", `${a.title}. What is behind it?`);
    b.type = "button";
    b.onclick = () => window.ask2?.(`${a.title}. What is behind this, and what should we do about it?`);
    li.append(b);
    ul.append(li);
  });
  note.hidden = !ul.children.length;
}

function briefWhen(root, alerts) {
  const w = root.querySelector("#brief-when");
  if (!w || !alerts) return;
  const n = (alerts.alerts || []).length;
  const at = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  w.textContent = `Read at ${at} · ${n ? `${n} open alert${n === 1 ? "" : "s"}, most severe first`
    : "no open alerts"} · from the latest records`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
