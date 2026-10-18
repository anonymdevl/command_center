/**
 * Today, Approvals and Outstanding Tasks, on ERPNext's own records (api/work.py).
 *
 * The three screens were designed with sample requests and sample tasks. Their layout
 * stays; what is inside the lists is replaced with the real queue:
 *
 *   Approvals            every document whose workflow has a step this person may take
 *   Today                the first few of those, and the work they handed out that is
 *                        past its date
 *   Outstanding Tasks    work handed out: what the assignee has marked done (to check)
 *                        and what is still open
 *
 * Built as DOM, never as HTML from the server, in the classes the designed cards use, so
 * the cards look like every other alert. The decisions -- approve, reject, accept, send
 * back -- open the action dialog, which asks before anything changes.
 */

import { count, exact, shortDate } from "../format.js";
import { hydrateTiles } from "./hydrate.js";

export const WORK_VIEWS = new Set(["myday", "approvals", "delegation"]);

/** Designed tile label -> figure key in api/work.summary().figures. */
export const WORK_TILES = {
  myday: {
    "Awaiting you": { key: "work_awaiting" },
    "Due today": { key: "work_due_today" },
    "Evidence to check": { key: "work_to_check" },
    "Promises unkept": { key: "work_unkept" },
  },
  delegation: {
    "Still open": { key: "work_open" },
    Late: { key: "work_late" },
    // "Reopened twice+" needs the history of each To-Do, which is not read yet.
    "High risk": { key: "work_high" },
  },
};

export function renderWork(root, view, data, opts = {}) {
  if (!root || !data || !WORK_VIEWS.has(view)) return 0;
  if (!data.available) {
    banner(root, data.reason);
    return 0;
  }
  root.querySelector(".work-banner")?.remove();
  const live = WORK_TILES[view] ? hydrateTiles(root, view, data.figures, opts, WORK_TILES[view]) : 0;
  if (view === "approvals") approvals(root, data);
  if (view === "myday") today(root, data);
  if (view === "delegation") delegation(root, data);
  return live;
}

/* ------------------------------------------------------------------ screens */
function approvals(root, data) {
  const n = data.approvals.length;
  setWhen(root, n ? `${n} waiting on you, oldest first by how long it has waited`
    : "nothing is waiting on you");
  const anchor = root.querySelector(".topbar");
  root.querySelectorAll(".alert, .work-list").forEach((a) => a.remove());
  const list = el("div", "work-list");
  if (!n) list.append(empty("Nothing is waiting on you.",
    "When a document reaches a step your role can take in ERPNext, it appears here."));
  data.approvals.forEach((a) => list.append(approvalCard(a, data.currency)));
  anchor.after(list);
}

function today(root, data) {
  const now = new Date();
  setWhen(root, `${now.toLocaleDateString("en-GB", { weekday: "long" })} `
    + `${now.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}`
    + " · only what is waiting on you");

  const sects = Array.from(root.querySelectorAll(".sect"));
  const waiting = sects.find((s) => /^awaiting you/i.test(s.textContent.trim()));
  if (waiting) {
    // The designed sample cards between the heading and the next section go.
    for (let n = waiting.nextElementSibling; n && n.classList.contains("alert"); ) {
      const next = n.nextElementSibling;
      n.remove();
      n = next;
    }
    root.querySelectorAll(".work-list").forEach((l) => l.remove());
    const list = el("div", "work-list");
    const first = data.approvals.slice(0, 3);
    if (!first.length) list.append(empty("Nothing is waiting on you.", "Approvals that need your step appear here."));
    first.forEach((a) => list.append(approvalCard(a, data.currency)));
    if (data.approvals.length > 3) {
      const more = el("button", "lnk work-more", `All ${data.approvals.length} on Approvals →`);
      more.type = "button";
      more.onclick = () => window.go?.("approvals");
      list.append(more);
    }
    waiting.after(list);
  }

  const promises = sects.find((s) => /^promises|^work you handed out/i.test(s.textContent.trim()));
  if (promises) {
    promises.textContent = "Work you handed out that is past its date";
    const old = promises.nextElementSibling;
    const table = tasksTable(data.late, { empty: "Nothing you handed out is past its date." });
    if (old && (old.tagName === "TABLE" || old.classList.contains("work-table"))) old.replaceWith(table);
    else promises.after(table);
  }
}

function delegation(root, data) {
  setWhen(root, `${data.open.length} open · ${data.late.length} late · `
    + `${data.check.length} to check · ${data.open.filter((t) => t.priority === "High").length} high risk`);
  // The designed sample (one task, its states and its evidence) goes, up to the note.
  const grid = root.querySelector(".grid");
  let n = grid?.nextElementSibling;
  while (n && !n.classList.contains("note")) {
    const next = n.nextElementSibling;
    n.remove();
    n = next;
  }
  const wrap = el("div", "work-list");
  wrap.append(el("div", "sect", "Marked done: check the evidence"));
  if (!data.check.length) wrap.append(empty("Nothing to check.",
    `Work you handed out appears here when the person marks it done, for ${14} days.`));
  data.check.forEach((t) => wrap.append(checkCard(t)));
  wrap.append(el("div", "sect", "Still open"));
  wrap.append(tasksTable(data.open, { withPriority: true, empty: "Nothing you handed out is open." }));
  (grid || root.querySelector(".topbar")).after(wrap);
}

/* ------------------------------------------------------------------ cards */
function approvalCard(a, currency) {
  const sev = a.waiting_days > 30 ? "crit" : a.waiting_days > 7 ? "high" : "med";
  const card = el("div", `alert ${sev}`);
  card.dataset.ccWired = "1";
  card.dataset.live = "1";
  const row = el("div", "arow");
  const body = el("div");
  body.append(
    el("span", "asev", a.waiting_days ? `Waiting ${days(a.waiting_days)}` : "New today"),
    el("div", "awhat", `${a.doctype} — ${a.title}`),
    el("div", "awhy", `At “${a.state}” · raised by ${a.raised_by} on ${shortDate(a.raised)}`),
    el("div", "asw", `→ Your step: ${a.actions.join(" or ")}.`),
  );
  row.append(body);
  if (a.value) {
    const fig = el("div", "afig");
    fig.append(el("span", "cx", currency || ""), document.createTextNode(exact(a.value, { decimals: 0 })));
    row.append(fig);
  }
  card.append(row);

  const meta = el("div", "ameta");
  const doc = el("a", "chip src", "");
  doc.href = a.url;
  doc.target = "_blank";
  doc.rel = "noreferrer";
  doc.append(document.createTextNode(`${a.doctype} · `), el("b", null, a.name));
  meta.append(doc, chip("State", a.state), chip("Raised by", a.raised_by));
  card.append(meta);

  const acts = el("div", "acts");
  a.actions.forEach((action, i) => {
    acts.append(btn(action, i === 0 ? "btn pri" : /reject|cancel|return/i.test(action) ? "btn dgr" : "btn",
      () => fire("cc-action", { kind: "decide", doctype: a.doctype, name: a.name, action,
                                title: `${a.doctype} — ${a.title}` })));
  });
  acts.append(btn("Ask AI about this", "btn", () => fire("cc-ask", {
    question: `${a.doctype} ${a.name} (${a.title}) is waiting for my approval. `
      + "What should I know before I decide?" })));
  card.append(acts);
  return card;
}

function checkCard(t) {
  const card = el("div", "alert med");
  card.dataset.ccWired = "1";
  card.dataset.live = "1";
  const row = el("div", "arow");
  const body = el("div");
  body.append(
    el("span", "asev", "Marked done"),
    el("div", "awhat", t.title),
    el("div", "awhy", `Given to ${t.to_name || t.to} · marked done on ${shortDate(t.closed_on)}`),
    el("div", "asw", "→ Accept it, or send it back with what is still needed."),
  );
  row.append(body);
  card.append(row);
  if (t.detail) card.append(el("div", "work-detail", t.detail));

  const meta = el("div", "ameta");
  const link = el("a", "chip src", "");
  link.href = t.url;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.append(document.createTextNode("To-Do · "), el("b", null, t.name));
  meta.append(link);
  if (t.date) meta.append(chip("Due", shortDate(t.date)));
  if (t.reference) meta.append(chip(t.reference.doctype, t.reference.name));
  card.append(meta);

  const acts = el("div", "acts");
  acts.append(
    btn("Accept it", "btn pri", () => fire("cc-action", { kind: "review", verdict: "accept", todo: t.name, title: t.title })),
    btn("Send it back", "btn dgr", () => fire("cc-action", { kind: "review", verdict: "return", todo: t.name, title: t.title })),
  );
  card.append(acts);
  return card;
}

function tasksTable(rows, { withPriority = false, empty: none } = {}) {
  if (!rows.length) {
    const e = empty(none, "");
    e.classList.add("work-table");
    return e;
  }
  const table = el("table", "dt work-table");
  const head = el("tr");
  ["What", "Given to", "By when", "Late by", ...(withPriority ? ["Priority"] : []), ""].forEach((h) => head.append(el("th", null, h)));
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  rows.forEach((t) => {
    const tr = el("tr");
    const late = el("td", null, t.late_days ? days(t.late_days) : t.date ? "not yet due" : "no date set");
    if (t.late_days > 30) late.style.color = "var(--crit)";
    else if (t.late_days > 0) late.style.color = "var(--high)";
    const open = el("a", "btn", "Open");
    open.href = t.url;
    open.target = "_blank";
    open.rel = "noreferrer";
    const last = el("td");
    last.append(open);
    tr.append(el("td", null, t.title), el("td", null, t.to_name || t.to || "—"),
      el("td", null, t.date ? shortDate(t.date) : "—"), late,
      ...(withPriority ? [el("td", null, t.priority)] : []), last);
    tbody.append(tr);
  });
  table.append(thead, tbody);
  return table;
}

/* ------------------------------------------------------------------ helpers */
function banner(root, reason) {
  if (root.querySelector(".work-banner")) return;
  const b = el("div", "warn work-banner");
  b.append(el("b", null, "These requests and tasks are samples. "), document.createTextNode(reason || ""));
  root.querySelector(".topbar")?.after(b);
}

function setWhen(root, text) {
  const w = root.querySelector(".topbar .when");
  if (w) w.textContent = text;
}

function days(n) {
  if (n >= 60) return `${Math.round(n / 30.4)} months`;
  return `${count(n)} day${n === 1 ? "" : "s"}`;
}

function empty(title, sub) {
  const e = el("div", "work-empty");
  e.append(el("b", null, title));
  if (sub) e.append(el("span", null, sub));
  return e;
}

function chip(label, value) {
  const c = el("span", "chip", `${label} `);
  c.append(el("b", null, value || "—"));
  return c;
}

function btn(text, cls, fn) {
  const b = el("button", cls, text);
  b.type = "button";
  b.dataset.ccWired = "1";
  b.onclick = (e) => {
    e.stopPropagation();
    fn();
  };
  return b;
}

function fire(name, detail) {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
