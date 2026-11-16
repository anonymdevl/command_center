/**
 * Business Overview as a front page (16 Nov 2026, the approved mockup: B over A).
 *
 * The area that most needs attention today leads, on the left; the next three stand
 * beside it; the other five are a ruled register underneath. Nothing here is new
 * content: the nine tiles are the designed tiles, filled by hydrate.js and core.js
 * exactly as before -- label, figure, footnote, flags, can't-reach and set-up states,
 * go() -- and this file only moves each one into its place and gives it a role class
 * (ov-as-lead / ov-as-sec / ov-as-row) for shell.py to style. A tile is moved, never
 * copied or rebuilt, so nothing written into it is lost and every later hydration pass
 * finds it where it is.
 *
 * What it adds is words built from figures the screen already reads: the lead's
 * kicker, its one sentence (the headline figure and its own note), its key figures
 * (the same figures its note prints, read as figures: LEAD_FIGURES), and each other
 * area's note under its footnote. Never a number it did not read.
 *
 * Which area leads is decided here, without any model, from the figures and the open
 * alerts (the bell's list, api/alerts.open_alerts): the worst alert severity, or a load
 * that failed, ranks first; then the larger money at stake; then the designed order.
 * planOverview is pure, so scripts/test_overview.mjs can prove it.
 */

import { count, money } from "../format.js";

/** The screens drawn as a front page. Its open alerts are read for the ranking only. */
export const OVERVIEW_VIEWS = new Set(["ops"]);

/**
 * The figures an area's lead story may quote beside its headline: exactly the figures
 * its headline's note already prints (kpi/*.py notes), so the story says nothing the
 * screen did not say. hydrate.js EXTRA_KPIS.ops asks for these.
 */
export const LEAD_FIGURES = {
  sales: ["ar_open_invoices", "ar_owing_count"],
  proc: ["ap_open_invoices", "ap_owing_count"],
  inv: ["stock_lines"],
  eng: ["tasks_overdue"],
  cx: ["cases_unowned"],
  hr: ["headcount"],
};

/** How many areas stand beside the lead. */
export const SECONDARY = 3;

// Alert severity, the alert engine's own order (alerts/rules.py SEVERITY_RANK).
const SEVERITY = { crit: 0, high: 1, med: 2, info: 3 };
// A figure's own state on the same scale: a load that failed needs someone (as a medium
// alert); nothing recorded yet, or no access, is a set-up step (as information). Stale,
// live and can't-reach say nothing about the area itself.
const STATE_TIER = { failed: 2, needs_setup: 3, no_access: 3 };
const NONE = 9;
// At or below this an area needs you today.
const NEEDS_YOU = 2;

// The record type behind an alert (its drill_fact), as the area that owns it.
const FACT_AREA = {
  fact_sales_invoice: "sales",
  fact_sales_invoice_line: "sales",
  fact_sales_order: "sales",
  fact_purchase_invoice: "proc",
  fact_purchase_invoice_line: "proc",
  fact_stock_balance: "inv",
  fact_task: "eng",
  fact_case: "cx",
  fact_person: "hr",
};

/** The Overview area an open alert belongs to, or null when it belongs to none. */
export function areaOfAlert(alert) {
  const fact = alert?.drill_fact;
  const f = alert?.drill_filters || {};
  if (fact === "fact_party_balance") {
    return f.party_type === "Customer" ? "sales" : f.party_type === "Supplier" ? "proc" : null;
  }
  if (fact === "fact_payment_allocation") {
    return f.payment_type === "Receive" ? "sales" : f.payment_type === "Pay" ? "proc" : "fin";
  }
  return FACT_AREA[fact] || null;
}

/**
 * Order the areas. `areas` is [{dept, index, figure}] in the designed order; `alerts`
 * the open alerts, or null when they have not been read (then nothing is said to be
 * calm). Returns {lead, sec, rows, quiet, read}: every area exactly once, the register
 * in the designed order.
 */
export function planOverview(areas, alerts) {
  const read = Array.isArray(alerts);
  const scored = (areas || []).map((a) => {
    const mine = read ? alerts.filter((x) => areaOfAlert(x) === a.dept) : [];
    const alertTier = Math.min(NONE, ...mine.map((x) => SEVERITY[x.severity] ?? NONE));
    const stateTier = STATE_TIER[a.figure?.data_status?.state] ?? NONE;
    const fromAlerts = mine.filter((x) => x.figure_unit === "currency")
      .reduce((s, x) => s + (Number(x.figure) || 0), 0);
    const headline = a.figure?.unit === "currency" ? Number(a.figure.value) || 0 : 0;
    return { ...a, tier: Math.min(alertTier, stateTier), atStake: fromAlerts || headline };
  });
  const urgent = [...scored].sort((x, y) => x.tier - y.tier || y.atStake - x.atStake
    || x.index - y.index);
  const quiet = read && !!urgent.length && urgent[0].tier > NEEDS_YOU;
  // Nothing needs you: the largest area leads, and says so.
  const lead = quiet
    ? [...scored].sort((x, y) => y.atStake - x.atStake || x.index - y.index)[0]
    : urgent[0];
  const rest = urgent.filter((a) => a !== lead);
  return {
    lead: lead || null,
    sec: rest.slice(0, SECONDARY),
    rows: rest.slice(SECONDARY).sort((x, y) => x.index - y.index),
    quiet,
    read,
  };
}

/** A figure as words: "GHS 658.57k", "40 tasks", "12.5%". Null when it was not read. */
export function figureText(figure, unit) {
  if (!figure || figure.value === null || figure.value === undefined) return null;
  const v = Number(figure.value);
  if (figure.unit === "currency") {
    const m = money(v, figure.currency || "");
    return `${m.currency} ${m.figure}${m.suffix}`.trim();
  }
  if (figure.unit === "percent") return `${v.toFixed(1)}%`;
  if (figure.unit === "days") return `${count(Math.round(v))} days`;
  if (figure.unit === "date" || figure.unit === "time") return String(figure.value);
  const n = Number.isInteger(v) ? count(v) : v.toLocaleString("en-GB", { maximumFractionDigits: 2 });
  return unit ? `${n} ${unit}` : n;
}

const GUIDED = new Set(["needs_setup", "no_access"]);

/**
 * The lead's one sentence, from its headline figure and that figure's own note only:
 * "Work in flight: 40 tasks, 23 of them past due." A figure with nothing behind it says
 * what its state says (the guide's sentence, or why it could not be read).
 */
export function leadSentence(figure, unit) {
  if (!figure) return null;
  const st = figure.data_status?.state;
  if (GUIDED.has(st) && figure.data_status?.guide?.text) return figure.data_status.guide.text;
  const text = figureText(figure, unit);
  if (text === null || st === "unreachable") {
    return figure.data_status?.message || null;
  }
  const note = String(figure.note || "").trim().replace(/[.\s]+$/, "");
  return `${figure.label || "The figure"}: ${text}${note ? `, ${note}` : ""}.`;
}

/** The note a secondary or register line shows, when the figure was read. */
export function areaNote(figure) {
  const st = figure?.data_status?.state;
  if (!figure || figure.value === null || figure.value === undefined) return null;
  if (st === "unreachable" || GUIDED.has(st)) return null;
  return String(figure.note || "").trim() || null;
}

/* ------------------------------------------------------------------------- */

const ROLES = ["ov-as-lead", "ov-as-sec", "ov-as-row"];

/**
 * Put the nine tiles in their places. `specs` is TILE_KPIS.ops (label -> {key, unit});
 * `done` says the figures have been answered, so the kicker may say what leads.
 */
export function renderOverview(root, { figures, alerts, specs, done } = {}) {
  const leadBox = root?.querySelector("#ov-lead");
  const secBox = root?.querySelector("#ov-sec");
  const rowBox = root?.querySelector("#ov-rows");
  if (!leadBox || !secBox || !rowBox) return null;
  const tiles = [...root.querySelectorAll(".bk[data-dept]")];
  // The designed order, remembered on the first pass (later passes see moved tiles).
  tiles.forEach((t, i) => {
    if (t.dataset.ovI === undefined) t.dataset.ovI = String(i);
  });
  const areas = tiles.map((tile) => {
    const label = tile.querySelector(".l")?.textContent?.trim() || "";
    const spec = specs?.[label] || null;
    return {
      dept: tile.dataset.dept,
      index: Number(tile.dataset.ovI),
      tile,
      label,
      unit: spec?.unit,
      figure: (spec && figures?.[spec.key]) || null,
    };
  });
  const plan = planOverview(areas, alerts);
  if (!plan.lead) return plan;

  place(plan.lead, leadBox, "ov-as-lead");
  plan.sec.forEach((a) => place(a, secBox, "ov-as-sec"));
  plan.rows.forEach((a) => place(a, rowBox, "ov-as-row"));

  // The lead: kicker, sentence, key figures.
  const { tile, figure, unit, dept } = plan.lead;
  const head = tile.querySelector(".khead");
  if (head && done) {
    const kick = add("span", "ov-kick", plan.quiet ? "Largest Area" : "Leads Today");
    head.prepend(kick);
  }
  const sentence = done ? leadSentence(figure, unit) : null;
  const say = plan.quiet
    ? add("p", "ov-say", "Nothing needs you today.")
    : sentence ? add("p", "ov-say", sentence) : null;
  if (say) (head || tile.firstChild)?.after(say);
  if (plan.quiet && sentence) say.after(add("p", "ov-dek", sentence));
  const figs = (LEAD_FIGURES[dept] || [])
    .map((k) => figures?.[k])
    .filter((f) => f && figureText(f) !== null && !GUIDED.has(f.data_status?.state)
      && f.data_status?.state !== "unreachable")
    .slice(0, 2);
  if (figs.length) {
    const box = add("div", "ov-figs");
    figs.forEach((f) => {
      const one = el("div", "ov-fig");
      one.append(el("b", null, figureText(f)), el("span", null, f.label || ""));
      box.append(one);
    });
    const v = tile.querySelector(".v") || tile.querySelector(".n");
    if (v) v.after(box);
  }

  // Every other area: its note under its footnote.
  [...plan.sec, ...plan.rows].forEach((a) => {
    const note = areaNote(a.figure);
    const foot = a.tile.querySelector(".v");
    if (note && foot && note !== foot.textContent.trim()) foot.after(add("div", "ov-note", note));
  });

  tiles.forEach(keys);
  return plan;
}

/** Move one tile into its box, in order, with its role; take back what a previous pass added. */
function place(area, box, role) {
  const t = area.tile;
  t.querySelectorAll("[data-ov-add]").forEach((n) => n.remove());
  ROLES.forEach((r) => t.classList.toggle(r, r === role));
  box.append(t);
}

/**
 * A tile that opens something can be reached and opened from the keyboard (Enter or
 * Space click it, which runs its own onclick); one that opens nothing cannot.
 */
function keys(tile) {
  const opens = tile.classList.contains("clickable")
    && (tile.getAttribute("onclick") || typeof tile.onclick === "function");
  if (opens) {
    if (!tile.hasAttribute("tabindex")) tile.setAttribute("tabindex", "0");
    if (!tile.hasAttribute("role")) tile.setAttribute("role", "link");
    if (!tile.dataset.ovKeys) {
      tile.dataset.ovKeys = "1";
      tile.addEventListener("keydown", (e) => {
        // A tile hydrate.js or guide.js wired handles its own keys.
        if (typeof tile.onkeydown === "function") return;
        if (e.target !== tile || (e.key !== "Enter" && e.key !== " ")) return;
        e.preventDefault();
        tile.click();
      });
    }
  } else if (tile.dataset.ovKeys) {
    tile.removeAttribute("tabindex");
    tile.removeAttribute("role");
  }
}

function add(tag, className, text) {
  const node = el(tag, className, text);
  node.dataset.ovAdd = "1";
  return node;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
