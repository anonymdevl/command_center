/**
 * Finances' Financial Statements: profit and loss, the balance sheet, the trial balance
 * and cash flow, as the business's own ERPNext draws them (api/statements.py).
 *
 * The generated markup (interface/statements.py) is the frame: the period switch, the
 * export buttons and one tab per statement. This file asks for the chosen period and
 * draws what comes back -- the five cards, the statement tables (indented account tree,
 * subtotals in bold, negatives in brackets, the business's currency), the comparison
 * column, a guide where ERPNext is not set up for a statement, "not updated yet" where it
 * does not answer. An account opens its General Ledger on the business's ERPNext.
 *
 * Three requests, so the first statements draw while ERPNext is still working out the
 * trial balance and cash flow. Every node is built here; nothing from the server is
 * ever written as HTML. The cards carry data-live, so hydrate.js leaves them alone.
 */

import { api } from "../api/client.js";
import { exact, money } from "../format.js";
import { guideBox } from "./guide.js";
import { waitingLine } from "./reach.js";

export const STATEMENT_VIEWS = new Set(["fin"]);
const SECTIONS = ["summary", "tb", "cf"];
const STORE = "cc-fs-period";
const ARROW = "M7 17 17 7M8.5 7H17v8.5";

/** Attach to the Finances screen. Returns { refresh, destroy }. */
export function mountStatements(root, { scope } = {}) {
  const box = root?.querySelector("#fs");
  if (!box) return null;
  const saved = load();
  const st = { period: saved.period || "ytd", from: saved.from || "", to: saved.to || "",
    data: {}, seq: 0, scope, alive: true };

  const periods = [...box.querySelectorAll(".fs-p")];
  const custom = box.querySelector("#fs-custom");
  const fromIn = box.querySelector("#fs-from");
  const toIn = box.querySelector("#fs-to");
  if (fromIn) fromIn.value = st.from;
  if (toIn) toIn.value = st.to;

  const mark = () => {
    periods.forEach((b) => {
      const on = b.dataset.period === st.period;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (custom) custom.hidden = st.period !== "custom";
  };
  periods.forEach((b) => {
    b.onclick = () => {
      st.period = b.dataset.period;
      mark();
      if (st.period === "custom" && !(st.from && st.to)) {
        fromIn?.focus();
        return;
      }
      keep(st);
      fetchAll(true);
    };
  });
  const apply = box.querySelector("#fs-apply");
  if (apply) {
    apply.onclick = () => {
      st.from = fromIn?.value || "";
      st.to = toIn?.value || "";
      if (!st.from || !st.to) {
        say(box, "Choose both dates for a custom period.");
        return;
      }
      keep(st);
      fetchAll(true);
    };
  }
  const xlsx = box.querySelector("#fs-xlsx");
  if (xlsx) xlsx.onclick = () => busy(xlsx, "Excel", () => exportExcel(st));
  const pdf = box.querySelector("#fs-pdf");
  if (pdf) {
    pdf.onclick = () => busy(pdf, "PDF", () => api.statementsPdf(args(st)));
  }
  // The cards open the statement they come from.
  box.querySelector("#fs-cards")?.addEventListener("click", (e) => {
    const card = e.target.closest(".kpi[data-tab]");
    if (!card) return;
    box.querySelectorAll('.tabbar[data-g="fs"] .tab')[Number(card.dataset.tab)]?.click();
  });

  function args(s) {
    return { business_code: s.scope, period: s.period,
      from_date: s.period === "custom" ? s.from : undefined,
      to_date: s.period === "custom" ? s.to : undefined };
  }

  function fetchAll(changed) {
    const seq = ++st.seq;
    if (changed) {
      st.data = {};
      waiting(box);
    }
    SECTIONS.forEach((section) => {
      api.statements({ ...args(st), section })
        .then((res) => {
          if (!st.alive || seq !== st.seq) return;
          st.data[section] = res;
          draw(box, section, res);
        })
        .catch((e) => {
          if (!st.alive || seq !== st.seq || e?.name === "AbortError") return;
          // A refresh that fails keeps the statements already on the screen.
          if (st.data[section]) return;
          draw(box, section, { state: "failed", message: e?.message });
        });
    });
  }

  mark();
  fetchAll(true);
  return {
    refresh: () => fetchAll(false),
    destroy: () => { st.alive = false; },
  };
}

// --------------------------------------------------------------------------- drawing
function waiting(box) {
  box.querySelector("#fs-state").hidden = true;
  const cards = box.querySelector("#fs-cards");
  cards.textContent = "";
  box.querySelectorAll(".fs-body").forEach((b) => {
    b.textContent = "";
    b.append(el("div", "fs-wait", "Reading ERPNext's own statements for this period…"));
  });
}

function say(box, text) {
  const s = box.querySelector("#fs-state");
  s.hidden = !text;
  s.textContent = text || "";
}

function part(box, name) {
  return box.querySelector(`.fs-body[data-part="${name}"]`);
}

function draw(box, section, res) {
  const targets = section === "summary" ? ["pl", "bs", "ratios"] : [section];
  if (!res || res.state !== "ok") {
    targets.forEach((t) => notOk(part(box, t), res));
    if (section === "summary") {
      box.querySelector("#fs-cards").textContent = "";
      say(box, "");
      whenLine(box, res);
    }
    return;
  }
  if (section === "summary") {
    whenLine(box, res);
    say(box, "");
    cards(box.querySelector("#fs-cards"), res);
    pl(part(box, "pl"), res);
    bs(part(box, "bs"), res);
    ratios(part(box, "ratios"), res);
  } else if (section === "tb") {
    tb(part(box, "tb"), res);
  } else {
    cf(part(box, "cf"), res);
  }
}

function whenLine(box, res) {
  const w = box.querySelector("#fs-when");
  if (!w || !res) return;
  if (res.state !== "ok") {
    w.textContent = "";
    return;
  }
  const at = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  w.textContent = `${res.period.span} · amounts in ${res.currency || "the company's currency"} · `
    + `from ${res.business}'s own ERPNext reports · read ${at}`;
}

function notOk(target, res) {
  if (!target) return;
  target.textContent = "";
  const state = res?.state;
  if (state === "needs_setup" && res.guide) {
    target.append(guideBox(res.guide));
  } else if (state === "unreachable") {
    target.append(el("div", "thin", waitingLine(res.business, res.last_loaded)));
  } else {
    target.append(el("div", "thin", res?.message
      || "The statements could not be read just now. They will be asked for again shortly."));
  }
}

// --------------------------------------------------------------------------- the cards
function cards(row, res) {
  row.textContent = "";
  const c = res.cards || {};
  const cur = res.currency || "";
  const cmp = res.comparison?.label?.toLowerCase() || "the comparison";
  const pct = (v) => (v === null || v === undefined ? null : `${(v * 100).toFixed(1)}%`);
  const change = (x) => {
    if (x?.change_pct === null || x?.change_pct === undefined) return [`No figure for ${cmp}`, "flat"];
    const up = x.change_pct >= 0;
    return [`${up ? "+" : "−"}${Math.abs(x.change_pct * 100).toFixed(1)}% on ${cmp}`, up ? "up" : "down"];
  };
  const add = (label, value, note, tone, tab, title) => {
    const card = el("div", "kpi clickable sig");
    card.dataset.live = "1";
    card.dataset.tab = String(tab);
    card.title = title;
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    card.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); card.click(); } };
    const cut = el("span", "sig-cut");
    cut.setAttribute("aria-hidden", "true");
    const go = el("span", "sig-go");
    go.setAttribute("aria-hidden", "true");
    go.append(arrow());
    const head = el("div", "khead");
    head.append(el("div", "lab", label));
    const val = el("div", "val");
    value(val);
    card.append(cut, go, head, val, el("div", `delta ${tone || "flat"}`, note));
    row.append(card);
  };
  const moneyInto = (v) => (node) => {
    if (v === null || v === undefined) {
      node.textContent = "—";
      return;
    }
    const m = money(v, cur);
    node.append(el("span", "cx", m.currency), document.createTextNode(m.figure));
    if (m.suffix) node.append(el("span", "mag", m.suffix));
  };
  const [rn, rt] = change(c.revenue);
  add("Revenue", moneyInto(c.revenue?.value), rn, rt, 0, "Income for the period, from the profit and loss statement");
  add("Gross Profit", moneyInto(c.gross_profit?.value),
    c.gross_profit?.margin === null || c.gross_profit?.margin === undefined
      ? "No Cost of Goods Sold account to set against revenue"
      : `Margin ${pct(c.gross_profit.margin)}`, "flat", 0, "Revenue less the cost of goods sold");
  add("Net Profit", moneyInto(c.net_profit?.value),
    c.net_profit?.margin === null || c.net_profit?.margin === undefined
      ? "No revenue in the period" : `Margin ${pct(c.net_profit.margin)}`,
    (c.net_profit?.value ?? 0) < 0 ? "down" : "flat", 0, "Revenue less every cost");
  add("Bank and Cash", moneyInto(c.cash?.value),
    `As at ${pretty(c.cash?.as_at)}${c.cash?.compare !== null && c.cash?.compare !== undefined
      ? ` · was ${figure(c.cash.compare, cur)}` : ""}`, "flat", 1,
    "Accounts with Account Type Bank or Cash");
  const cr = c.current_ratio?.value;
  add("Current Ratio", (n) => { n.textContent = cr === null || cr === undefined ? "—" : cr.toFixed(2); },
    cr === null || cr === undefined ? "No current liabilities recorded"
      : cr < 1 ? "Current Liabilities exceed Current Assets" : "Current Assets cover Current Liabilities",
    cr !== null && cr !== undefined && cr < 1 ? "down" : "flat", 4,
    "Current assets for every unit of current liabilities");
}

function arrow() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  [["viewBox", "0 0 24 24"], ["width", "18"], ["height", "18"], ["fill", "none"], ["stroke", "currentColor"],
    ["stroke-width", "1.8"], ["stroke-linecap", "round"], ["stroke-linejoin", "round"]]
    .forEach(([k, v]) => svg.setAttribute(k, v));
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", ARROW);
  svg.append(p);
  return svg;
}

// --------------------------------------------------------------------------- statements
function pl(target, res) {
  const p = res.pl;
  target.textContent = "";
  target.append(el("h4", null, "Profit and Loss"));
  target.append(el("div", "fs-sub", `${res.period.label}: ${p.columns[0]}, against ${res.comparison.label.toLowerCase()} (${p.columns[1]})`));
  target.append(table(["", res.period.label, res.comparison.label, "Change"], p.summary,
    { change: true, cmp: true, bars: true }));
  const says = plSays(p, res);
  if (says) target.append(el("p", "fs-says", says));
  notes(target, p.notes);
  const g = p.glance;
  if (g) {
    target.append(el("h4", null, "At a Glance"));
    target.append(table(["", ...g.columns], g.rows));
  }
  if (p.trend?.length) {
    target.append(el("h4", null, "Month by Month"));
    target.append(table(["Month", "Revenue", "Gross Profit", "Net Profit", "Net Margin"],
      p.trend.map((t) => ({ name: t.label, values: [t.revenue, t.gross_profit, t.net_profit, t.net_margin],
        kinds: ["money", "money", "money", "pct"] }))));
  }
  tree(target, "Profit and Loss by Account", ["Account", res.period.label, res.comparison.label], p.rows,
    { cmp: true });
}

function bs(target, res) {
  const b = res.bs;
  target.textContent = "";
  target.append(el("h4", null, "Balance Sheet"));
  target.append(table(["", ...b.columns.filter(Boolean)], b.summary.map((r) => ({ ...r, values: r.values.slice(0, b.columns.filter(Boolean).length) }))));
  const f = b.figures;
  // balances: true (checked, balances), false (checked, out by the difference), or null
  // (could not be checked -- never shown as passed, nor as failed).
  target.append(el("div", `fs-check ${f.balances ? "ok" : f.balances === false ? "bad" : "na"}`,
    f.balances ? "Balances: assets equal liabilities and equity, with the profit or loss since the books were last closed"
      : f.balances === false ? `Does not balance: out by ${exact(Math.abs(f.difference ?? 0))}`
        : "Not checked: the profit and loss since the books were last closed could not be read"));
  notes(target, b.notes);
  tree(target, "Balance Sheet by Account", ["Account", ...b.columns.filter(Boolean)], b.rows);
}

function tb(target, res) {
  const t = res.tb;
  target.textContent = "";
  target.append(el("h4", null, "Trial Balance"));
  target.append(el("div", "fs-sub", `${pretty(t.from)} to ${pretty(t.to)} · fiscal year ${t.fiscal_year}`));
  target.append(el("div", `fs-check ${t.balanced ? "ok" : "bad"}`, t.balanced
    ? "Balances: debits equal credits in the opening, the period and the closing columns"
    : `Does not balance: ${Object.entries(t.differences).filter(([, v]) => Math.abs(v) >= 0.5)
      .map(([k, v]) => `${k} out by ${exact(Math.abs(v))}`).join(", ")}`));
  notes(target, t.notes);
  const rows = [...t.rows, { name: "Total", kind: "total", indent: 0, values: t.total }];
  tree(target, null, ["Account", ...t.columns], rows, { tall: true });
}

function cf(target, res) {
  const c = res.cf;
  target.textContent = "";
  target.append(el("h4", null, "Cash Flow"));
  target.append(el("div", "fs-sub", `${res.period.label}: ${c.columns[0]}, against ${res.comparison.label.toLowerCase()} (${c.columns[1]})`));
  target.append(table(["", res.period.label, res.comparison.label, "Change"], c.summary,
    { change: true, cmp: true }));
  notes(target, c.notes);
  target.append(el("h4", null, "Cash Flow in Detail"));
  target.append(table(["", res.period.label, res.comparison.label], c.rows, { cmp: true }));
}

function ratios(target, res) {
  target.textContent = "";
  target.append(el("h4", null, "Key Ratios"));
  target.append(el("div", "fs-sub", `Profit for ${res.period.label.toLowerCase()}; balances as at ${pretty(res.balance_dates.at)}`));
  const t = el("table", "dt fs-t");
  const head = el("thead");
  const hr = el("tr");
  ["Ratio", "Value", "What It Means"].forEach((h, i) => hr.append(el("th", i === 1 ? "n" : null, h)));
  head.append(hr);
  const body = el("tbody");
  (res.ratios || []).forEach((r) => {
    const tr = el("tr");
    tr.append(el("td", null, r.label));
    const v = el("td", "n", fmt(r.value, r.kind, res.currency));
    if (typeof r.value === "number" && r.value < 0) v.classList.add("neg");
    tr.append(v);
    const m = el("td");
    m.append(el("div", null, r.reading), el("div", "fs-mean", r.meaning));
    tr.append(m);
    body.append(tr);
  });
  t.append(head, body);
  const wrap = el("div", "fs-wrap");
  wrap.append(t);
  target.append(wrap);
}

function notes(target, list) {
  if (!list?.length) return;
  const ul = el("ul", "fs-notes");
  list.forEach((n) => ul.append(el("li", null, n)));
  target.append(ul);
}

/** An account tree: the main groups first, every account a click away. */
function tree(target, title, heads, rows, { tall = false, cmp = false } = {}) {
  if (title) target.append(el("h4", null, title));
  const deep = rows.some((r) => (r.indent || 0) > 1);
  const holder = el("div");
  holder.append(table(heads, rows, { tall, fold: true, cmp }));
  target.append(holder);
  if (deep) {
    const b = el("button", "btn fs-more", "Show Every Account");
    b.type = "button";
    b.dataset.ccWired = "1";
    b.onclick = () => {
      const all = holder.classList.toggle("fs-all");
      b.textContent = all ? "Show Main Groups" : "Show Every Account";
    };
    target.append(b);
  }
}

/**
 * One statement table. `cmp` marks the comparison column (the second figure) so it reads
 * as the quieter one, as on printed management accounts. `bars` adds a slim bar per money
 * line, its length that line's share of the largest line in the same table -- drawn from
 * the figures already in the row, never a new one.
 */
function table(heads, rows, { change = false, tall = false, fold = false, cmp = false, bars = false } = {}) {
  const t = el("table", `dt fs-t${bars ? " fs-barred" : ""}`);
  const head = el("thead");
  const hr = el("tr");
  heads.forEach((h, i) => hr.append(el("th", [i ? "n" : null, cmp && i === 2 ? "cmp" : null]
    .filter(Boolean).join(" ") || null, h)));
  if (bars) hr.append(el("th", "fs-bar-h"));
  head.append(hr);
  const body = el("tbody");
  const isMoney = (r) => r.kind !== "pct" && r.kind !== "heading" && typeof r.values?.[0] === "number";
  const top = bars ? Math.max(0, ...rows.filter(isMoney).map((r) => Math.abs(r.values[0]))) : 0;
  rows.forEach((r) => {
    const tr = el("tr");
    const kind = r.kind;
    if (kind === "total" || r.bold) tr.classList.add("fs-total");
    else if (kind === "group") tr.classList.add("fs-group");
    else if (kind === "heading") tr.classList.add("fs-heading");
    if (fold && (r.indent || 0) > 1) tr.classList.add("fs-deep");
    const name = el("td");
    name.style.paddingLeft = `${12 + 16 * (r.indent || 0)}px`;
    const label = r.name || r.label || "";
    if (r.drill) {
      const a = el("a", "fs-acc", label);
      a.href = r.drill;
      a.target = "_blank";
      a.rel = "noopener";
      a.title = "Open its General Ledger in ERPNext";
      name.append(a);
    } else {
      name.textContent = label;
    }
    tr.append(name);
    (r.values || []).forEach((v, i) => {
      const k = r.kinds?.[i] || (kind === "pct" ? "pct" : "money");
      const td = el("td", "n", kind === "heading" && (v === null || v === undefined) ? "" : fmt(v, k));
      if (r.tone === "bad" && i === 0 && v) td.classList.add("neg");
      if (cmp && i === 1) td.classList.add("cmp");
      tr.append(td);
    });
    if (change) tr.append(changeCell(r));
    if (bars) tr.append(barCell(r, isMoney(r) && top ? Math.abs(r.values[0]) / top : null));
    body.append(tr);
  });
  t.append(head, body);
  const wrap = el("div", `fs-wrap${tall ? " tall" : ""}`);
  wrap.append(t);
  return wrap;
}

function barCell(r, share) {
  const td = el("td", "fs-bar-c");
  td.setAttribute("aria-hidden", "true");
  if (share === null) return td;
  const costly = /cost|expense/i.test(r.label || "");
  const bar = el("span", `fs-bar${costly ? " cost" : ""}${r.values[0] < 0 ? " neg" : ""}`);
  bar.style.width = `${Math.max(share * 100, share > 0 ? 1.5 : 0).toFixed(1)}%`;
  td.append(bar);
  return td;
}

/**
 * One plain sentence under the profit and loss, worked out from the statement's own
 * lines only: how revenue and the other expenses moved against the comparison, and the
 * net result with its margin. Every figure in it is one the table above shows, written
 * the same way (the changes to one decimal, the result in full); nothing is estimated.
 * No sentence when revenue or the net result is missing.
 */
function plSays(p, res) {
  const by = Object.fromEntries((p.summary || []).map((r) => [r.key, r]));
  const rev = by.income?.values?.[0];
  const net = by.net_profit?.values?.[0];
  if (typeof rev !== "number" || typeof net !== "number") return "";
  // "Same Period Last Year" / "Year Before", as the comparison column is headed.
  const cmp = `the ${(res.comparison?.label || "comparison").toLowerCase()}`;
  const pct = (x) => `${Math.abs(x * 100).toFixed(1)}%`;
  const moved = (r, noun) => {
    const c = r?.change_pct;
    if (c === null || c === undefined) return "";
    if (Math.abs(c) < 0.0005) return `${noun} was unchanged`;
    return `${noun} ${c > 0 ? "rose" : "fell"} ${pct(c)}`;
  };
  const parts = [moved(by.income, "Revenue"), moved(by.other_expenses, "operating and other expenses")]
    .filter(Boolean);
  const margin = by.net_margin?.values?.[0];
  const cur = res.currency || "";
  const result = net === 0 ? "breaks even"
    : `closes with a net ${net < 0 ? "loss" : "profit"} of ${`${cur} ${exact(Math.abs(net))}`.trim()}`
      + (typeof margin === "number" ? `, ${pct(margin)} of revenue` : "");
  return parts.length ? `${parts.join(" and ")} on ${cmp}; the period ${result}.` : `The period ${result}.`;
}

function changeCell(r) {
  if (r.kind === "pct") {
    if (r.change === null || r.change === undefined) return el("td", "n", "—");
    const pts = r.change * 100;
    return el("td", `n ${pts >= 0 ? "pos" : "neg"}`, `${pts >= 0 ? "+" : "−"}${Math.abs(pts).toFixed(1)} pts`);
  }
  if (r.change_pct === null || r.change_pct === undefined) return el("td", "n", "—");
  // Up is good for income and profit, and bad for a cost.
  const costly = /cost|expense/i.test(r.label || "");
  const good = costly ? r.change_pct <= 0 : r.change_pct >= 0;
  return el("td", `n ${good ? "pos" : "neg"}`,
    `${r.change_pct >= 0 ? "+" : "−"}${Math.abs(r.change_pct * 100).toFixed(1)}%`);
}

// --------------------------------------------------------------------------- export
async function exportExcel(st) {
  const s = st.data.summary;
  if (!s || s.state !== "ok") throw new Error("The statements have not been read yet.");
  const n = (v) => (v === null || v === undefined ? "" : v);
  const pad = (r) => `${"    ".repeat(r.indent || 0)}${r.name || r.label || ""}`;
  const sheet = (name, columns, rows) => ({ name, columns,
    rows: rows.map((r) => [pad(r), ...(r.values || []).map(n)]) });
  const tables = [
    sheet("Profit and Loss", ["", s.pl.columns[0], s.pl.columns[1]], s.pl.summary),
    sheet("P&L by Account", ["Account", s.pl.columns[0], s.pl.columns[1]], s.pl.rows),
    sheet("Balance Sheet", ["", ...s.bs.columns.filter(Boolean)], s.bs.summary),
    sheet("Balance Sheet by Account", ["Account", ...s.bs.columns.filter(Boolean)], s.bs.rows),
    { name: "Key Ratios", columns: ["Ratio", "Value", "Reading", "What It Means"],
      rows: s.ratios.map((r) => [r.label, n(r.value), r.reading, r.meaning]) },
  ];
  const c = st.data.cf;
  if (c?.state === "ok") tables.push(sheet("Cash Flow", ["", ...c.cf.columns], c.cf.rows));
  const t = st.data.tb;
  if (t?.state === "ok") {
    tables.push(sheet("Trial Balance", ["Account", ...t.tb.columns],
      [...t.tb.rows, { name: "Total", values: t.tb.total }]));
  }
  await api.tablesXlsx({ title: `Financial Statements, ${s.period.label}`, tables,
    business_code: st.scope });
}

async function busy(button, label, run) {
  if (button.disabled) return;
  button.disabled = true;
  button.textContent = "Preparing…";
  try {
    await run();
    button.textContent = "Downloaded";
  } catch (e) {
    button.textContent = "Export failed";
    button.title = e?.message || "The export failed.";
  }
  setTimeout(() => {
    button.disabled = false;
    button.textContent = label;
  }, 2200);
}

// --------------------------------------------------------------------------- small things
function fmt(v, kind, cur) {
  if (v === null || v === undefined || v === "") return "—";
  if (kind === "pct") return `${(v * 100).toFixed(1)}%`;
  if (kind === "ratio") return Number(v).toFixed(2);
  const s = exact(Math.abs(v));
  const body = v < 0 ? `(${s})` : s;
  return cur ? `${cur} ${body}` : body;
}

function figure(v, cur) {
  const m = money(v, cur);
  return `${m.currency} ${v < 0 ? "−" : ""}${m.figure.replace("-", "")}${m.suffix}`;
}

function pretty(iso) {
  if (!iso) return "";
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? String(iso)
    : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORE) || "{}") || {};
  } catch {
    return {};
  }
}

function keep(st) {
  try {
    localStorage.setItem(STORE, JSON.stringify({ period: st.period, from: st.from, to: st.to }));
  } catch {
    /* a private window: the period is not remembered, nothing else changes */
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== null && text !== undefined) node.textContent = text;
  return node;
}
