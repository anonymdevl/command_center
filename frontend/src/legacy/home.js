/**
 * Home, in the approved mockup's layout, on real figures -- and the Business Health
 * score tiles, which share the gauge's three questions.
 *
 *   Hero tiles          TILE_KPIS.command (hydrate.js)
 *   Morning brief       the alert engine's top three (api/alerts.py)
 *   Largest amounts     api/home.debtors -- All, Overdue, Over 90 days
 *   Counts              cases_open, tasks_overdue
 *   Business health     the average of three stated ratios: score_paid, score_deliver,
 *                       score_paperwork. "How it is scored" lists each with its note,
 *                       so 47/100 is never a number nobody can explain.
 *   Top customers       api/home.top_customers -- share of the last twelve full months
 *
 * Built as DOM, never HTML from the server. Each part fills its own slot and leaves the
 * rest alone, so one failed read is one empty panel with a reason, not a broken screen.
 */

import { api } from "../api/client.js";
import { count, exact, money, shortDate } from "../format.js";

const SCORES = [
  ["score_paid", "Getting paid"],
  ["score_deliver", "Delivering what we sold"],
  ["score_paperwork", "Paperwork finished"],
];
const WORDS = { crit: "Critical", high: "High", med: "Medium", info: "For information" };

export function renderHome(root, { figures, alerts, scope, onOpen }) {
  if (!root?.querySelector("#mbrief")) return;
  if (alerts) brief(root, alerts);
  if (figures) {
    setText(root, "#cnt-cases", figures.cases_open ? count(figures.cases_open.value) : "—");
    setText(root, "#cnt-late", figures.tasks_overdue ? count(figures.tasks_overdue.value) : "—");
    gauge(root, figures);
  }
  debts(root, scope, onOpen);
  customers(root, scope, onOpen);
}

/** Business Health's first three questions, from the same ratios as Home's gauge. */
export function renderHealthTiles(root, figures) {
  if (!root || !figures) return 0;
  let live = 0;
  // The headline is Home's gauge: the plain average of the questions scored so far.
  const parts = SCORES.map(([k]) => figures[k]).filter((f) => f && f.value !== null && f.value !== undefined);
  const head = root.querySelector("#hh-score");
  if (head && parts.length) {
    const avg = Math.round(parts.reduce((s, f) => s + Number(f.value), 0) / parts.length);
    head.textContent = String(avg);
    head.style.color = `var(--${toneOf(avg).color})`;
    const trend = root.querySelector("#hh-trend");
    if (trend) {
      trend.textContent = `average of the ${parts.length} questions scored`;
      trend.style.color = "var(--mut)";
    }
  }
  root.querySelectorAll(".bk.q").forEach((tile) => {
    const label = tile.querySelector(".l")?.textContent?.trim();
    const key = { "Are we getting paid?": "score_paid", "Can we deliver what we sold?": "score_deliver",
                  "Is the paperwork finished?": "score_paperwork" }[label];
    const f = key && figures[key];
    if (!f || f.value === null || f.value === undefined) return;
    const score = Math.round(Number(f.value));
    const tone = toneOf(score);
    const n = tile.querySelector(".n");
    if (n) {
      n.textContent = "";
      const v = el("span", null, String(score));
      v.style.color = `var(--${tone.color})`;
      n.append(v, el("small", null, "/100"));
    }
    const bar = tile.querySelector(".bar i") || tile.querySelector(".bar")?.appendChild(el("i"));
    if (bar) {
      bar.style.width = `${Math.max(0, Math.min(100, score))}%`;
      bar.style.background = `var(--${tone.color})`;
    }
    const flag = tile.querySelector(".khead .flag");
    if (flag) {
      flag.className = `flag ${tone.flag}`;
      flag.textContent = tone.word;
    }
    const foot = tile.querySelector(".v");
    if (foot && f.note) foot.textContent = `${score}% ${f.note}`;
    tile.dataset.live = "1";
    delete tile.dataset.illustrative;
    tile.querySelector(":scope > .flag[data-prov]")?.remove();
    tile.title = "One stated ratio: " + (f.note ? `${score}% ${f.note}.` : "");
    live += 1;
  });
  return live;
}

/* ------------------------------------------------------------------ morning brief */
function brief(root, data) {
  const list = (data.alerts || []).slice(0, 3);
  const h = root.querySelector("#mb-h");
  const chips = root.querySelector("#mb-chips");
  if (!h || !chips) return;
  const words = ["Nothing", "One thing", "Two things", "Three things"];
  h.textContent = list.length
    ? `${words[list.length]} need${list.length === 1 ? "s" : ""} your attention today`
    : "Nothing material needs your attention today";
  chips.textContent = "";
  list.forEach((a) => {
    const c = el("button", `mb-chip ${a.severity}`);
    c.type = "button";
    c.title = `${WORDS[a.severity] || ""}: ${a.title}`;
    c.append(el("b", null, figureText(a)), document.createTextNode(` ${a.rule.toLowerCase()}`));
    c.onclick = () => {
      const card = document.getElementById(`alert-${a.name}`);
      card?.scrollIntoView({ behavior: "smooth", block: "center" });
      card?.classList.add("alert-flash");
      setTimeout(() => card?.classList.remove("alert-flash"), 1600);
    };
    chips.append(c);
  });
}

function figureText(a) {
  if (a.figure === null || a.figure === undefined) return "";
  if (a.figure_unit === "currency") {
    const m = money(a.figure, a.currency || "");
    return `${m.currency} ${m.figure}${m.suffix}`.trim();
  }
  return count(Math.round(a.figure));
}

/* ------------------------------------------------------------------ largest amounts owed */
const debtState = { scope: null, mode: "all", seq: 0 };

function debts(root, scope, onOpen) {
  const panel = root.querySelector("#debt");
  if (!panel) return;
  if (!panel.dataset.wired) {
    panel.dataset.wired = "1";
    panel.querySelectorAll(".segc button").forEach((b) => {
      b.onclick = () => {
        debtState.mode = b.dataset.mode;
        panel.querySelectorAll(".segc button").forEach((x) => {
          x.classList.toggle("on", x === b);
          x.setAttribute("aria-selected", x === b ? "true" : "false");
        });
        loadDebts(panel, debtState.scope, onOpen);
      };
    });
  }
  if (debtState.scope === scope && panel.dataset.loaded === debtState.mode) return;
  debtState.scope = scope;
  loadDebts(panel, scope, onOpen);
}

function loadDebts(panel, scope, onOpen) {
  const seq = ++debtState.seq;
  const rows = panel.querySelector("#debt-rows");
  const mode = debtState.mode;
  api.homeDebtors({ business_code: scope, mode })
    .then((d) => {
      if (seq !== debtState.seq || !document.body.contains(panel)) return;
      panel.dataset.loaded = mode;
      setText(panel, "#debt-n", `${count(d.invoices)} invoice${d.invoices === 1 ? "" : "s"}`);
      rows.textContent = "";
      if (!d.rows.length) {
        rows.append(el("div", "home-wait", mode === "all" ? "Nobody owes us anything." : "Nothing in this band."));
        return;
      }
      d.rows.forEach((r) => rows.append(debtRow(r, d.currency, onOpen)));
      if (d.customers > d.rows.length) {
        rows.append(el("div", "debt-more", `The largest ${d.rows.length} of ${count(d.customers)} customers, `
          + `${money(d.owed, d.currency || "").currency} ${exact(d.owed, { decimals: 0 })} in all`));
      }
    })
    .catch((e) => {
      if (seq !== debtState.seq) return;
      rows.textContent = "";
      rows.append(el("div", "home-wait", `The receivables could not be read: ${e?.message || "no reply"}`));
    });
}

function debtRow(r, currency, onOpen) {
  const row = el("button", "debt-row");
  row.type = "button";
  row.title = `Open ${r.customer}'s unpaid invoices`;
  const who = el("span", "debt-who");
  who.append(el("span", "av2", initials(r.customer)));
  const name = el("span", "debt-name");
  name.append(el("b", null, r.customer),
    el("span", null, `${count(r.invoices)} invoice${r.invoices === 1 ? "" : "s"}`
      + (r.last_paid ? ` · last paid ${shortDate(r.last_paid)}` : " · no payment on record")));
  who.append(name);
  const days = el("span", `dpill ${r.days > 90 ? "crit" : r.days > 30 ? "high" : "ok"}`,
    r.days > 0 ? `${count(r.days)} days` : "not yet due");
  const amt = el("span", "debt-amt");
  const inv = el("span", "debt-a");
  inv.append(el("b", null, exact(r.invoiced, { decimals: 0 })), el("small", null, "Invoiced"));
  const owed = el("span", "debt-a");
  owed.append(el("b", null, exact(r.owed, { decimals: 0 })), el("small", null, `Still owed${currency ? `, ${currency}` : ""}`));
  amt.append(inv, el("span", "debt-arrow", "→"), owed);
  row.append(who, days, amt);
  row.onclick = () => onOpen?.({ label: `${r.customer}: unpaid invoices`, drill: r.drill });
  return row;
}

/* ------------------------------------------------------------------ top customers */
const custState = { scope: undefined };

function customers(root, scope, onOpen) {
  const panel = root.querySelector("#topc");
  if (!panel || custState.scope === scope && panel.dataset.loaded) return;
  custState.scope = scope;
  api.topCustomers({ business_code: scope })
    .then((d) => {
      if (!document.body.contains(panel)) return;
      panel.dataset.loaded = "1";
      const list = panel.querySelector("#topc-l");
      const bar = panel.querySelector("#topc-bar");
      list.textContent = "";
      bar.textContent = "";
      if (d.period?.label) setText(panel, "#topc-sub", `Share of sales, ${d.period.label}`);
      if (!d.rows.length) {
        list.append(el("li", "home-wait", "No invoiced sales in the last twelve months of data."));
        return;
      }
      d.rows.forEach((r, i) => {
        const seg = el("i", `c${i}`);
        seg.style.width = `${r.share}%`;
        seg.title = `${r.customer}: ${r.share}%`;
        bar.append(seg);
        const li = el("li");
        const b = el("button", "topc-row");
        b.type = "button";
        b.append(el("span", "av2", initials(r.customer)), el("span", `topc-dot c${i}`),
          el("span", "topc-name", r.customer), el("span", "topc-pct", `${r.share.toFixed(0)}%`));
        b.title = `${r.customer}: ${d.currency || ""} ${exact(r.sold, { decimals: 0 })}`;
        b.onclick = () => onOpen?.({ label: `${r.customer}: sales, ${d.period.label}`, drill: r.drill });
        li.append(b);
        list.append(li);
      });
    })
    .catch((e) => {
      const list = panel.querySelector("#topc-l");
      list.textContent = "";
      list.append(el("li", "home-wait", `The sales could not be read: ${e?.message || "no reply"}`));
    });
}

/* ------------------------------------------------------------------ gauge */
function gauge(root, figures) {
  const box = root.querySelector("#gauge-v");
  if (!box) return;
  const parts = SCORES.map(([k, label]) => ({ key: k, label, f: figures[k] }))
    .filter((p) => p.f && p.f.value !== null && p.f.value !== undefined);
  box.textContent = "";
  if (!parts.length) {
    box.append(el("div", "home-wait", "Not enough data to score yet."));
    return;
  }
  const score = Math.round(parts.reduce((s, p) => s + Number(p.f.value), 0) / parts.length);
  const worst = parts.reduce((a, b) => (Number(a.f.value) <= Number(b.f.value) ? a : b));
  const tone = toneOf(score);
  box.append(dial(score, tone.color));
  const mid = el("div", "gauge-mid");
  mid.append(el("b", null, String(score)), el("small", null, "/100"));
  box.append(mid);
  box.append(el("div", "gauge-say", `${tone.say} — ${worst.label.toLowerCase()} is the drag`));

  const how = root.querySelector("#gauge-how");
  const list = root.querySelector("#gauge-parts");
  if (list) {
    list.textContent = "";
    parts.forEach((p) => {
      const li = el("li");
      li.append(el("b", null, `${Math.round(p.f.value)}`), el("span", null, `${p.label}: ${Math.round(p.f.value)}% ${p.f.note || ""}`));
      list.append(li);
    });
    list.append(el("li", "gauge-note", `The plain average of these ${parts.length}. `
      + "Approvals, record quality and access are not scored until their data exists."));
  }
  if (how && !how.dataset.wired) {
    how.dataset.wired = "1";
    how.onclick = () => {
      const open = list.hidden;
      list.hidden = !open;
      how.setAttribute("aria-expanded", String(open));
      how.textContent = open ? "Hide how it is scored" : "How it is scored";
    };
  }
}

function dial(score, color) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 220 140");
  svg.setAttribute("class", "dial");
  svg.setAttribute("aria-hidden", "true");
  const ticks = 44;
  for (let i = 0; i < ticks; i++) {
    const a = Math.PI * (1.1 - (1.2 * i) / (ticks - 1));
    const on = i / (ticks - 1) <= score / 100;
    const line = document.createElementNS(NS, "line");
    line.setAttribute("x1", String(110 + Math.cos(a) * 78));
    line.setAttribute("y1", String(118 - Math.sin(a) * 78));
    line.setAttribute("x2", String(110 + Math.cos(a) * 98));
    line.setAttribute("y2", String(118 - Math.sin(a) * 98));
    line.setAttribute("stroke", on ? `var(--${color})` : "var(--line2)");
    line.setAttribute("stroke-width", "4");
    line.setAttribute("stroke-linecap", "round");
    svg.append(line);
  }
  return svg;
}

function toneOf(score) {
  if (score >= 80) return { color: "ok", flag: "f-ok", word: "Healthy", say: "Healthy" };
  if (score >= 60) return { color: "med", flag: "f-med", word: "Watch", say: "Steady" };
  if (score >= 40) return { color: "high", flag: "f-high", word: "High", say: "Under strain" };
  return { color: "crit", flag: "f-crit", word: "Critical", say: "In trouble" };
}

/* ------------------------------------------------------------------ helpers */
function initials(name) {
  return (name || "?").replace(/[^A-Za-z0-9 ]/g, " ").trim().split(/\s+/).slice(0, 2)
    .map((w) => w[0]).join("").toUpperCase() || "?";
}

function setText(root, sel, text) {
  const n = root.querySelector(sel);
  if (n) n.textContent = text;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
