/**
 * Stock & Warehouses' Stock Balance and Stock Movements tabs, from api/stock.py.
 *
 * Stock Balance: one row per item and warehouse (the loaded Bin), searched by item,
 * filtered by warehouse, a page at a time, with the totals of everything matched.
 * Stock Movements: the Stock Ledger Entry newest first over a date range (the last 30
 * days to begin with), read live a page at a time with Show More; each row opens its
 * voucher in the business's ERPNext. Both export every matching row to Excel.
 *
 * The designed markup holds only the cards and their headings (.ppanel data-sk,
 * interface/views_b.py); everything inside is built here with DOM calls, as people.js
 * does. Nothing from the API is written as HTML. A tab is read the first time it is
 * shown, never before.
 */

import { api, call } from "../api/client.js";
import { exact, count, shortDate } from "../format.js";
import { deskPath, erpUrl } from "../erpLinks.js";
import { waitingLine } from "./reach.js";

export const STOCK_VIEWS = new Set(["inv"]);

const M = "command_center.api.stock";

/** Draw the two tabs' cards; returns the cleanup for the effect. */
export function renderStock(root, { scope } = {}) {
  if (!root) return () => {};
  const state = { alive: true, scope };
  const stops = [];
  [["balance", drawBalance], ["movements", drawMovements]].forEach(([key, draw]) => {
    const body = root.querySelector(`[data-sk="${key}"] .pp-body`);
    if (!body) return;
    body.textContent = "";
    stops.push(whenShown(body, () => draw(body, state)));
  });
  return () => {
    state.alive = false;
    stops.forEach((s) => s());
  };
}

/** Run `fn` once, the first time `node`'s tab is open (at once when it already is). */
function whenShown(node, fn) {
  const pane = node.closest(".tabpane");
  if (!pane || pane.classList.contains("on") || typeof MutationObserver === "undefined") {
    fn();
    return () => {};
  }
  const seen = new MutationObserver(() => {
    if (!pane.classList.contains("on")) return;
    seen.disconnect();
    fn();
  });
  seen.observe(pane, { attributes: true, attributeFilter: ["class"] });
  return () => seen.disconnect();
}

/* ------------------------------------------------------------------ Stock Balance */
function drawBalance(body, state) {
  const bar = el("div", "filters sk-bar");
  const q = search("Search Items");
  const wh = select("Warehouse", [["", "All Warehouses"]]);
  const n = el("span", "tcount");
  const xl = exportButton(() => api.stockBalanceXlsx({ business_code: state.scope, q: q.value,
    warehouse: wh.value }));
  bar.append(q, wh, n, xl);
  const out = el("div");
  body.append(bar, out);

  let page = 1;
  let seq = 0;
  let filled = false;
  const load = async () => {
    const mine = ++seq;
    if (!out.childNodes.length) out.append(el("div", "pp-empty", "Reading…"));
    let res;
    try {
      res = await call(`${M}.balance`, { business_code: state.scope, q: q.value,
        warehouse: wh.value, page });
    } catch (e) {
      res = { kind: "failed", message: e?.message };
    }
    if (!state.alive || mine !== seq) return;
    out.textContent = "";
    if (res?.kind !== "stock_balance") {
      n.textContent = "";
      out.append(stateNode(res));
      return;
    }
    if (!filled) {
      fill(wh, res.warehouses || []);
      filled = true;
    }
    page = res.page;
    const t = res.totals || {};
    n.textContent = `${count(t.lines)} line${t.lines === 1 ? "" : "s"}`
      + (res.as_of ? ` · as at ${shortDate(res.as_of)}` : "");
    if (!res.rows.length) {
      out.append(el("div", "pp-empty", "No stock matches."));
      return;
    }
    out.append(balanceTable(res));
    if (res.pages > 1) {
      const pager = el("div", "pp-pager");
      const prev = button("Previous", () => { page -= 1; load(); });
      const next = button("Next", () => { page += 1; load(); });
      prev.disabled = res.page <= 1;
      next.disabled = res.page >= res.pages;
      pager.append(prev, el("span", "tcount", `Page ${res.page} of ${res.pages}`), next);
      out.append(pager);
    }
  };
  wire(q, [wh], () => { page = 1; load(); });
  load();
}

function balanceTable(res) {
  const cur = res.currency || "";
  const wrap = el("div", "pp-scroll sk-scroll");
  const t = table(["Item", "Warehouse", ["Quantity", 1], ["Valuation Rate", 1],
    [`Value ${cur}`.trim(), 1]]);
  t.classList.add("sk-t", "sk-bal");
  const tb = t.querySelector("tbody");
  res.rows.forEach((r) => {
    const tr = el("tr");
    tr.append(itemCell(r), cut(r.warehouse), numCell(qtyText(r.qty, r.uom)),
      numCell(exact(r.valuation_rate)), numCell(exact(r.value)));
    tb.append(tr);
  });
  const s = res.totals || {};
  const foot = el("tfoot");
  const tr = el("tr");
  const label = td(`Total (${count(s.lines)} Line${s.lines === 1 ? "" : "s"})`);
  label.colSpan = 2;
  tr.append(label, numCell(s.qty == null ? "" : qtyText(s.qty, s.uom)), numCell(""),
    numCell(exact(s.value)));
  foot.append(tr);
  t.append(foot);
  wrap.append(t);
  return wrap;
}

/* ------------------------------------------------------------------ Stock Movements */
function drawMovements(body, state) {
  const bar = el("div", "filters sk-bar");
  const q = search("Search Items or Vouchers");
  const wh = select("Warehouse", [["", "All Warehouses"]]);
  const from = dateInput("From");
  const to = dateInput("To");
  const n = el("span", "tcount");
  const xl = exportButton(() => api.stockMovementsXlsx({ business_code: state.scope, q: q.value,
    warehouse: wh.value, from_date: from.value, to_date: to.value }));
  const dates = el("span", "sk-dates");
  dates.append(from, el("span", "sk-to", "to"), to);
  bar.append(q, wh, dates, n, xl);
  const out = el("div");
  body.append(bar, out);

  let seq = 0;
  let filled = false;
  let shown = [];
  let total = null;
  let code = state.scope;
  const more = el("div", "pp-pager");

  const read = (cursor) => call(`${M}.movements`, { business_code: state.scope, q: q.value,
    warehouse: wh.value, from_date: from.value, to_date: to.value, ...(cursor || {}) });

  const draw = (res) => {
    out.textContent = "";
    n.textContent = total == null ? "" : `${count(total)} movement${total === 1 ? "" : "s"}`;
    if (!shown.length) {
      out.append(el("div", "pp-empty", "No movements in these dates."));
      return;
    }
    out.append(movementTable(shown, code));
    more.textContent = "";
    if (res.next) {
      if (total != null) more.append(el("span", "tcount", `${count(shown.length)} of ${count(total)}`));
      const b = button("Show More", async () => {
        b.disabled = true;
        b.textContent = "Reading…";
        const mine = seq;
        let got;
        try {
          got = await read(res.next);
        } catch {
          got = null;
        }
        if (!state.alive || mine !== seq) return;
        if (got?.kind !== "stock_movements") {
          b.disabled = false;
          b.textContent = "Try Again";
          return;
        }
        const ids = new Set(shown.map((r) => r.id));
        shown = shown.concat(got.rows.filter((r) => !ids.has(r.id)));
        draw(got);
      });
      more.append(b);
    }
    out.append(more);
  };

  const load = async () => {
    const mine = ++seq;
    out.textContent = "";
    out.append(el("div", "pp-empty", "Reading…"));
    let res;
    try {
      res = await read(null);
    } catch (e) {
      res = { kind: "failed", message: e?.message };
    }
    if (!state.alive || mine !== seq) return;
    if (res?.kind !== "stock_movements") {
      out.textContent = "";
      n.textContent = "";
      out.append(stateNode(res));
      return;
    }
    if (!filled) {
      fill(wh, res.warehouses || []);
      from.value = res.from_date || "";
      to.value = res.to_date || "";
      filled = true;
    }
    code = res.business_code || state.scope;
    shown = res.rows || [];
    total = res.total;
    draw(res);
  };
  wire(q, [wh, from, to], load);
  load();
}

function movementTable(rows, code) {
  const wrap = el("div", "pp-scroll sk-scroll");
  const t = table(["Date", "Item", "Warehouse", ["In", 1], ["Out", 1], ["Balance Qty", 1],
    "Voucher Type", "Voucher No"]);
  t.classList.add("sk-t", "sk-mov");
  const tb = t.querySelector("tbody");
  rows.forEach((r) => {
    const href = r.voucher_no ? erpUrl(deskPath(r.voucher_type, r.voucher_no), code) : null;
    const tr = el("tr", href ? "sk-row" : null);
    const voucher = href ? link(r.voucher_no, href) : document.createTextNode(r.voucher_no || "");
    const vc = el("td", "sk-v");
    vc.title = r.voucher_no || "";
    vc.append(voucher);
    tr.append(td(shortDate(r.date) || ""), itemCell(r), cut(r.warehouse),
      numCell(r.in_qty ? qtyText(r.in_qty) : ""), numCell(r.out_qty ? qtyText(r.out_qty) : ""),
      numCell(qtyText(r.balance_qty)), cut(r.voucher_type), vc);
    if (href) {
      tr.tabIndex = 0;
      tr.setAttribute("role", "link");
      tr.setAttribute("aria-label", `Open ${r.voucher_type} ${r.voucher_no} in ERPNext`);
      const open = (e) => {
        if (e.target.closest("a")) return; // the link itself opens it
        window.open(href, "_blank", "noopener");
      };
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          window.open(href, "_blank", "noopener");
        }
      });
    }
    tb.append(tr);
  });
  wrap.append(t);
  return wrap;
}

/* ------------------------------------------------------------------ small */
function stateNode(res) {
  if (res?.kind === "unreachable") return el("div", "thin", waitingLine(res.business, res.last_loaded));
  if (res?.kind === "refused") {
    return el("div", "thin", "The business's ERPNext refused this read.");
  }
  return el("div", "thin", res?.message
    ? `This could not be read just now: ${res.message}`
    : "This could not be read from ERPNext just now.");
}

function wire(q, selects, fn) {
  let t = null;
  q.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(fn, 300);
  });
  selects.forEach((s) => s.addEventListener("change", fn));
}

function itemCell(r) {
  const c = el("td", "sk-item");
  const name = r.item_name || r.item_code || "";
  c.title = r.item_code && r.item_code !== name ? `${name} (${r.item_code})` : name;
  c.append(el("b", "sk-cut", name));
  if (r.item_code && r.item_code !== name) c.append(el("div", "sk-cut sk-code", r.item_code));
  return c;
}

function cut(text) {
  const c = el("td", "sk-c");
  c.title = text || "";
  c.append(el("span", "sk-cut", text || ""));
  return c;
}

function numCell(text) {
  return el("td", "num", text);
}

function qtyText(v, uom) {
  const x = Number(v) || 0;
  const s = Number.isInteger(x) ? x.toLocaleString("en-GB")
    : x.toLocaleString("en-GB", { maximumFractionDigits: 3 });
  return uom ? `${s} ${uom}` : s;
}

function exportButton(run) {
  const b = el("button", "btn sk-xl", "Excel");
  b.type = "button";
  b.title = "Download every matching row as Excel";
  b.addEventListener("click", async () => {
    if (b.disabled) return;
    b.disabled = true;
    b.textContent = "Preparing…";
    try {
      await run();
      b.textContent = "Downloaded";
    } catch (e) {
      b.textContent = "Export Failed";
      b.title = e?.message || "The export failed.";
    }
    setTimeout(() => {
      b.disabled = false;
      b.textContent = "Excel";
    }, 2200);
  });
  return b;
}

function search(label) {
  const q = el("input");
  q.type = "search";
  q.placeholder = label;
  q.setAttribute("aria-label", label);
  return q;
}

function dateInput(label) {
  const d = el("input", "sk-date");
  d.type = "date";
  d.setAttribute("aria-label", label);
  return d;
}

function table(heads) {
  const t = el("table", "dt");
  const tr = el("tr");
  heads.forEach((h) => {
    const [label, isNum] = Array.isArray(h) ? h : [h, 0];
    const th = el("th", isNum ? "num" : null, label);
    tr.append(th);
  });
  const thead = el("thead");
  thead.append(tr);
  t.append(thead, el("tbody"));
  return t;
}

function td(content, cls) {
  const c = el("td", cls || null);
  if (content instanceof Node) c.append(content); else c.textContent = content ?? "";
  return c;
}

function select(label, options) {
  const s = el("select");
  s.setAttribute("aria-label", label);
  options.forEach(([v, t]) => {
    const o = el("option", null, t);
    o.value = v;
    s.append(o);
  });
  return s;
}

function fill(sel, values) {
  values.forEach((v) => {
    if ([...sel.options].some((o) => o.value === v)) return;
    const o = el("option", null, v);
    o.value = v;
    sel.append(o);
  });
}

function button(text, fn) {
  const b = el("button", "btn", text);
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}

function link(text, href) {
  const a = el("a", "lnk", text || "");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
