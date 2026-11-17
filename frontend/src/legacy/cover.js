/**
 * "Promised Orders — Cover" (api/coverage.py): every open order line and what covers it,
 * on Sales, Stock and Buying.
 *
 * The panel's answer is {kind: "cover", states, summary, rows, default, note, guide?}.
 * Drawn here: one button per state with its count and amount (a filter), the lines
 * largest first with their state, and Show More for the rest of a state; each line
 * opens a drawer with the order line, its stock and its purchase chain -- purchase
 * order, goods receipts, supplier invoices -- with dates and links to the business's
 * ERPNext. Where nothing links an order to its purchase, the guide to making the links
 * exact goes under the table. Nothing from the API is written as HTML.
 */

import { call } from "../api/client.js";
import { money, exact, count, shortDate } from "../format.js";
import { guideBox } from "./guide.js";

const M = "command_center.api.coverage";
const NEEDS = ["not_ordered", "partly"];

export function drawCover(panel, spec, { openDrawer, scope } = {}) {
  const box = panel.querySelector(".cover");
  if (!box) return false;
  const cur = spec._cur || "";
  box.textContent = "";
  const rows = spec.rows || [];
  const s = spec.summary || {};
  if (!rows.length) {
    box.append(el("div", "thin", spec.empty || "Every submitted Sales Order has been delivered in full."));
    return true;
  }
  const state = { filter: box.dataset.filter || spec.default || "all", extra: {}, cur, spec,
                  openDrawer, scope };
  const filters = el("div", "cv-states");
  filters.setAttribute("role", "group");
  filters.setAttribute("aria-label", "Show lines by state");
  const choices = [
    { key: "all", label: "All", count: s.lines, value: s.value, tone: "accent" },
    { key: "needs", label: "Needs Action", count: s.needs_action?.count || 0,
      value: s.needs_action?.value || 0, tone: "crit" },
    ...(spec.states || []).filter((x) => x.count > 0),
  ];
  const table = el("table", "dt cv-t");
  const wrap = el("div", "cv-scroll");
  wrap.append(table);
  const more = el("div", "cv-more");
  const redraw = () => {
    box.dataset.filter = state.filter;
    [...filters.children].forEach((b) => {
      const on = b.dataset.key === state.filter;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    drawRows(table, more, state);
  };
  choices.forEach((c) => {
    const b = el("button", "cv-s");
    b.type = "button";
    b.dataset.key = c.key;
    const dot = el("span", "cv-dot");
    dot.style.background = `var(--${c.tone === "dim" ? "dim" : c.tone})`;
    const lab = el("span", "cv-l", c.label);
    const fig = el("span", "cv-n", `${count(c.count)} · ${short(c.value, cur)}`);
    b.append(dot, lab, fig);
    b.addEventListener("click", () => { state.filter = c.key; redraw(); });
    filters.append(b);
  });
  box.append(filters);
  const flags = [];
  if (s.late_to_customer?.count) {
    flags.push(`${count(s.late_to_customer.count)} line${s.late_to_customer.count === 1 ? "" : "s"} `
      + `past the date promised to the customer (${short(s.late_to_customer.value, cur)})`);
  }
  if (s.supplier_late) {
    flags.push(`${count(s.supplier_late)} waiting on a supplier past the date asked for`);
  }
  if (flags.length) box.append(el("div", "cv-flags", flags.join(" · ")));
  box.append(wrap, more);
  if (spec.note) box.append(el("div", "thin cv-note", spec.note));
  if (spec.guide) box.append(guideBox(spec.guide, { compact: true }));
  redraw();
  return true;
}

function short(v, cur) {
  const m = money(v, cur);
  return `${m.currency} ${m.figure}${m.suffix}`.trim();
}

function visible(state) {
  const { filter, spec } = state;
  const base = (spec.rows || []).filter((r) => filter === "all" || (filter === "needs"
    ? NEEDS.includes(r.state) : r.state === filter));
  return base.concat(state.extra[filter] || []);
}

function totalFor(state) {
  const s = state.spec.summary || {};
  if (state.filter === "all") return s.lines || 0;
  if (state.filter === "needs") return s.needs_action?.count || 0;
  return (state.spec.states || []).find((x) => x.key === state.filter)?.count || 0;
}

function drawRows(table, more, state) {
  table.textContent = "";
  const head = el("thead");
  const tr = el("tr");
  [["Order"], ["Customer"], ["Item"], ["To Deliver", 1], [`Value ${state.cur}`.trim(), 1],
   ["Covered By"], ["State"], ["Due"]].forEach(([t, n]) => {
    const th = el("th", null, t);
    if (n) th.style.textAlign = "right";
    tr.append(th);
  });
  head.append(tr);
  const body = el("tbody");
  table.append(head, body);
  const rows = visible(state);
  // "All" shows the lines in the order the server ranked them: most in need of action
  // first, then the largest.
  rows.forEach((r) => body.append(rowNode(r, state)));
  if (!rows.length) {
    const t = el("tr");
    const td = el("td", null, "No line is in this state.");
    td.colSpan = 8;
    td.style.color = "var(--dim)";
    t.append(td);
    body.append(t);
  }
  more.textContent = "";
  const total = totalFor(state);
  if (rows.length < total) {
    more.append(el("span", "cv-count", `${count(rows.length)} of ${count(total)} shown`));
    const b = el("button", "btn", "Show More");
    b.type = "button";
    b.addEventListener("click", async () => {
      b.disabled = true;
      b.textContent = "Reading…";
      try {
        const got = await call(`${M}.lines`, { business_code: state.scope, state: state.filter,
                                              start: rows.length, limit: 50 });
        if (got?.kind === "cover") {
          const seen = new Set(rows.map((r) => r.id));
          state.extra[state.filter] = (state.extra[state.filter] || [])
            .concat((got.rows || []).filter((r) => !seen.has(r.id)));
        }
      } catch {
        b.textContent = "Could not read more just now";
        return;
      }
      drawRows(table, more, state);
    });
    more.append(b);
  } else if (total) {
    more.append(el("span", "cv-count", `All ${count(total)} shown`));
  }
}

function coveredBy(r) {
  const bits = [];
  const stock = (r.from_stock || 0) + (r.elsewhere || []).reduce((a, e) => a + (e.qty || 0), 0);
  if (stock) bits.push(`${qty(stock)} in stock`);
  if (r.received) bits.push(`${qty(r.received)} received`);
  if (r.on_order) bits.push(`${qty(r.on_order)} on order${r.basis === "likely" ? " (likely)" : ""}`);
  if (r.requested) bits.push(`${qty(r.requested)} requested`);
  if (r.missing && r.state !== "non_stock") bits.push(`${qty(r.missing)} missing`);
  return bits.join(" · ") || "—";
}

function rowNode(r, state) {
  const tr = el("tr", "cv-row");
  tr.tabIndex = 0;
  tr.setAttribute("role", "button");
  tr.setAttribute("aria-label", `${r.order}, ${r.item_name}: ${r.state_label}`);
  const td = (text, cls) => {
    const c = el("td", cls || null);
    if (text instanceof Node) c.append(text); else c.textContent = text ?? "";
    tr.append(c);
    return c;
  };
  td(el("b", null, r.order), "cv-o");
  td(r.customer);
  const it = td(r.item_name);
  it.className = "cv-item";
  td(`${qty(r.pending)}${r.uom ? ` ${r.uom}` : ""}`, "num");
  td(exact(r.value), "num");
  td(coveredBy(r), "cv-by");
  td(stateTag(r));
  const due = td(shortDate(r.deliver_by) || "—");
  due.style.whiteSpace = "nowrap";
  if (r.late_to_customer) {
    due.append(el("div", "cv-late", `${count(r.days_late)} days late`));
  }
  const open = () => state.openDrawer?.({ node: lineDrawer(r, state) });
  tr.addEventListener("click", open);
  tr.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  });
  return tr;
}

function stateTag(r) {
  const cls = { not_ordered: "t-od", partly: "t-wt", requested: "t-rq", on_order: "t-oo",
                received: "t-ok", in_stock: "t-ok", non_stock: "t-dr" }[r.state] || "t-dr";
  const wrap = el("span", "cv-tags");
  wrap.append(el("span", `tag ${cls}`, r.state_label));
  if (r.basis === "likely") wrap.append(el("span", "cv-pill", "Likely"));
  if (r.supplier_late) wrap.append(el("span", "cv-pill late", "Supplier Late"));
  return wrap;
}

/* ------------------------------------------------------------------ the drawer */
function lineDrawer(r, state) {
  const box = el("div", "cv-d");
  const h = el("div", "dhead");
  const left = el("div");
  left.append(el("div", "dt", "Promised Order Line"), el("h4", null, r.item_name || r.item_code));
  left.append(el("div", "cv-sub", [r.order, r.customer].filter(Boolean).join(" · ")));
  const close = el("button", "btn", "Close ✕");
  close.type = "button";
  close.addEventListener("click", () => state.openDrawer?.(null));
  h.append(left, close);
  box.append(h, stateTag(r));
  box.append(el("p", "cv-say", r.narrative || ""));

  const kv = el("dl", "kv cv-kv");
  const row = (k, v) => {
    if (v == null || v === "") return;
    kv.append(el("dt", null, k));
    const dd = el("dd");
    if (v instanceof Node) dd.append(v); else dd.textContent = v;
    kv.append(dd);
  };
  const unit = r.uom ? ` ${r.uom}` : "";
  row("Sales Order", link(r.order, r.order_href));
  row("Customer", r.customer);
  row("Item", link(r.item_code, r.item_href));
  row("Transaction Date", shortDate(r.ordered_on));
  row("Promised For", r.deliver_by ? `${shortDate(r.deliver_by)}${r.late_to_customer
    ? ` · ${count(r.days_late)} days late` : ""}` : "No date set");
  row("Ordered", `${qty(r.ordered)}${unit}`);
  if (r.delivered) row("Delivered", `${qty(r.delivered)}${unit}`);
  row("Still to Deliver", `${qty(r.pending)}${unit}`);
  row("Value", `${state.cur} ${exact(r.value)}`.trim());
  box.append(kv);

  section(box, "Stock");
  const st = el("ul", "cv-list");
  if (r.from_stock) st.append(li(`${qty(r.from_stock)}${unit} in ${r.warehouse}`, "can go now"));
  (r.elsewhere || []).forEach((e) => st.append(li(`${qty(e.qty)}${unit} in ${e.warehouse}`,
    "to be moved first")));
  if (r.received) st.append(li(`${qty(r.received)}${unit} received for this order`, "ready to deliver"));
  if (!st.children.length) {
    st.append(li(r.state === "non_stock" ? "Not kept in stock" : `None free in ${r.warehouse || "any warehouse"}`,
      r.state === "non_stock" ? "" : "earlier orders come first"));
  }
  box.append(st);

  section(box, "Purchase Chain");
  if (!(r.covers || []).length && !(r.requests || []).length) {
    box.append(el("div", "cv-empty", r.state === "in_stock" || r.state === "non_stock"
      ? "Nothing ordered for it, and nothing needs to be."
      : "No purchase order or material request covers it."));
  }
  (r.covers || []).forEach((c) => box.append(chain(c, unit)));
  (r.requests || []).forEach((q) => {
    const card = el("div", "cv-c");
    const top = el("div", "cv-ch");
    top.append(badge(q.kind), link(q.request, q.href), el("span", "cv-m", "Material Request"));
    card.append(top);
    const ul = el("ul", "cv-list");
    ul.append(li("Raised", shortDate(q.raised) || "—"));
    if (q.required_by) ul.append(li("Required by", shortDate(q.required_by)));
    ul.append(li("Counted for this line", `${qty(q.qty)}${unit}, not yet ordered`));
    card.append(ul);
    if (q.reason) card.append(el("div", "cv-why", q.reason));
    box.append(card);
  });
  if (r.missing && r.state !== "non_stock") {
    box.append(el("div", "cv-miss", `${qty(r.missing)}${unit} not covered by stock or any order.`));
  }
  if (r.basis === "likely" || (r.missing && r.state !== "non_stock")) {
    box.append(el("div", "cv-tip", "Raise the purchase from the sales order (Create, Purchase "
      + "Order or Material Request) and the link is exact."));
  }

  const acts = el("div", "acts");
  acts.style.marginTop = "18px";
  if (r.order_href) {
    const a = el("a", "btn pri", "Open the Sales Order ↗");
    a.href = r.order_href;
    a.target = "_blank";
    a.rel = "noopener";
    acts.append(a);
  }
  const ask = el("button", "btn", "Ask AI");
  ask.type = "button";
  ask.addEventListener("click", () => {
    state.openDrawer?.(null);
    window.ask2?.(`What is holding sales order ${r.order} for ${r.customer}, and what covers it?`);
  });
  acts.append(ask);
  box.append(acts);
  return box;
}

function chain(c, unit) {
  const card = el("div", "cv-c");
  const top = el("div", "cv-ch");
  top.append(badge(c.kind), link(c.po, c.po_href), el("span", "cv-m", c.supplier || ""));
  card.append(top);
  const ul = el("ul", "cv-list");
  ul.append(li("Raised", shortDate(c.raised) || "—"));
  if (c.expected) {
    ul.append(li(c.late ? "Was due" : "Expected", `${shortDate(c.expected)}${c.late ? " · supplier late" : ""}`));
  }
  ul.append(li("On the order", `${qty(c.po_qty)}${unit}, ${qty(c.po_received)} received`));
  const mine = [];
  if (c.received) mine.push(`${qty(c.received)}${unit} received`);
  if (c.on_order) mine.push(`${qty(c.on_order)}${unit} still to come`);
  ul.append(li("Counted for this line", mine.join(", ")));
  if (c.request) ul.append(li("From request", link(c.request, c.request_href)));
  card.append(ul);
  if (c.reason) card.append(el("div", "cv-why", c.reason));
  const docs = el("ul", "cv-list cv-docs");
  (c.receipts || []).forEach((x) => docs.append(li(link(x.name, x.href),
    `Goods receipt · ${shortDate(x.date) || "—"} · ${qty(x.qty)}${unit}`)));
  (c.invoices || []).forEach((x) => docs.append(li(link(x.name, x.href),
    `Supplier invoice${x.received_on_it ? ", stock received on it" : ""} · ${shortDate(x.date) || "—"} · ${qty(x.qty)}${unit}`)));
  if (!docs.children.length) docs.append(li("No Purchase Receipt or Purchase Invoice yet", ""));
  card.append(docs);
  return card;
}

function badge(kind) {
  return el("span", `cv-k ${kind === "likely" ? "likely" : "linked"}`,
    kind === "likely" ? "Likely" : "Linked");
}

function section(box, title) {
  box.append(el("div", "sect", title));
}

function li(left, right) {
  const n = el("li");
  const a = el("span");
  if (left instanceof Node) a.append(left); else a.textContent = left ?? "";
  const b = el("span");
  if (right instanceof Node) b.append(right); else b.textContent = right ?? "";
  n.append(a, b);
  return n;
}

function link(text, href) {
  if (!href) return document.createTextNode(text || "");
  const a = el("a", "lnk", text || "");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

function qty(v) {
  const n = Number(v) || 0;
  return Number.isInteger(n) ? n.toLocaleString("en-GB")
    : n.toLocaleString("en-GB", { maximumFractionDigits: 3 });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
