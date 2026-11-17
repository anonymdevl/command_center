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
 * the cards look like every other alert. The markup carries no sample request or task:
 * until the queue is read the lists say so, and when it cannot be read as this person
 * they show how to link their own ERPNext key, or that ERPNext has not answered yet. The decisions -- approve, reject, accept, send
 * back -- open the action dialog, which asks before anything changes. Escalate on open
 * work handed out sends it to the manager of the person it was given to (ActionDialog).
 *
 * Outstanding Tasks manages the work too (16 Nov 2026): New Task, and on every open row
 * Edit (date and priority), Reassign, Escalate and Cancel Assignment, each through the
 * action dialog (api/actions). A row or card opens the task's own drawer (TaskDrawer.jsx),
 * not ERPNext. Each tile filters the list (its figure's `filter`, api/work.TILE_FILTERS),
 * and Today's Delegated Tasks Done and Overdue Delegated Tasks open it filtered the same way.
 *
 * Close and bulk actions (17 Nov 2026): Close on every open row (finished, or no longer
 * needed; nobody is told). Each open row has a checkbox; Select All takes every row in
 * the current view (so after the Late tile, every late one), and while anything is
 * selected a bar offers Close Selected and Cancel Selected, which ask first in the action
 * dialog (BulkChange: how many, to whom) and then go through api/actions.bulk_tasks.
 * The selection only ever holds rows on screen, so a filter cannot act on hidden work.
 */

import React from "react";
import TaskDrawer from "../components/TaskDrawer.jsx";
import { WAITING } from "./reach.js";
import { count, exact, shortDate } from "../format.js";
import { guideBox } from "./guide.js";
import { goTarget, hydrateTiles } from "./hydrate.js";
import { menu } from "./actions.js";

export const WORK_VIEWS = new Set(["myday", "approvals", "delegation"]);

/** Designed tile label -> figure key in api/work.summary().figures. */
export const WORK_TILES = {
  myday: {
    "Awaiting you": { key: "work_awaiting" },
    "Due today": { key: "work_due_today" },
    "Delegated Tasks Done": { key: "work_to_check" },
    "Overdue Delegated Tasks": { key: "work_unkept" },
  },
  delegation: {
    "Still Open": { key: "work_open" },
    Late: { key: "work_late" },
    // Sent back twice or more through "Send it back": the platform's own record of each.
    "Sent Back More Than Once": { key: "work_reopened" },
    "High Priority": { key: "work_high" },
  },
};

/** What each filter keeps, and how the list says it. */
const FILTERS = {
  open: { label: "Still Open", keep: () => true },
  late: { label: "Late", keep: (t) => t.late_days > 0 },
  high: { label: "High Priority", keep: (t) => t.priority === "High" },
  sent_back: { label: "Sent Back More Than Once", keep: (t) => (t.sent_back || 0) >= 2 },
  check: { label: "Delegated Tasks Done" },
};

// Set by a Today tile just before it opens Outstanding Tasks; taken by the next render.
let pendingFilter = null;

// The open tasks ticked on Outstanding Tasks, by To-Do name. Emptied after a bulk action,
// and when the business changes: a To-Do name ticked for one business must never be acted
// on under another (17 Nov 2026).
const selected = new Set();
let selectedFor;
if (typeof window !== "undefined") window.addEventListener("cc-tasks-unselect", () => selected.clear());

export function renderWork(root, view, data, opts = {}) {
  if (opts.scope !== selectedFor) {
    selected.clear();
    selectedFor = opts.scope;
  }
  if (!root || !data || !WORK_VIEWS.has(view)) return 0;
  if (!data.available) return unavailable(root, view, data, opts);
  root.querySelector(".work-banner")?.remove();
  const live = WORK_TILES[view] ? hydrateTiles(root, view, data.figures, opts, WORK_TILES[view]) : 0;
  if (view === "approvals") approvals(root, data);
  if (view === "myday") today(root, data, opts);
  if (view === "delegation") delegation(root, data, opts);
  return live;
}

/** The queue cannot be read as this person: their own ERPNext key is not linked (a guide
 *  to linking it), or the business's ERPNext has not answered yet. Never a sample request. */
function unavailable(root, view, data, opts) {
  const down = !!data.unreachable;
  const figure = (key) => ({
    key, value: null, unit: "count", note: down ? WAITING.foot : "your ERPNext key is not linked",
    data_status: down ? { state: "unreachable", message: data.reason }
      : { state: "needs_setup", message: data.reason, guide: data.guide },
  });
  const tiles = WORK_TILES[view] || {};
  const figures = Object.fromEntries(Object.values(tiles).map((t) => [t.key, figure(t.key)]));
  const live = Object.keys(tiles).length ? hydrateTiles(root, view, figures, opts, tiles) : 0;
  const box = () => {
    const wrap = el("div", "work-list");
    wrap.dataset.unavailable = "1";
    if (down || !data.guide) {
      const e = el("div", "work-empty");
      e.append(el("b", null, down ? `${WAITING.line}.` : "Not available yet."),
        el("span", null, data.reason || ""));
      wrap.append(e);
    } else {
      wrap.append(guideBox(data.guide));
    }
    return wrap;
  };
  const anchor = view === "delegation" ? root.querySelector(".grid") : null;
  root.querySelectorAll(".work-list, .work-table, .work-banner, .work-tools").forEach((n) => n.remove());
  if (view === "myday") {
    const sect = Array.from(root.querySelectorAll(".sect")).find((x) => /^awaiting you/i.test(x.textContent.trim()));
    (sect || root.querySelector(".topbar")).after(box());
  } else {
    (anchor || root.querySelector(".topbar")).after(box());
  }
  setWhen(root, down ? WAITING.foot : "your ERPNext key is not linked yet");
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

function today(root, data, opts) {
  // Delegated Tasks Done and Overdue Delegated Tasks open Outstanding Tasks filtered.
  root.querySelectorAll(".bk").forEach((tile) => {
    const spec = WORK_TILES.myday[tile.querySelector(".l")?.textContent?.trim()];
    const f = spec && data.figures?.[spec.key]?.filter;
    // By data-go (hydrate.js goTarget), not the onclick this removes: read by the onclick,
    // the second draw found none and the tile fell back to its figure's ERPNext link.
    if (!f || goTarget(tile) !== "delegation") return;
    tile.removeAttribute("onclick");
    const open = () => {
      pendingFilter = f;
      window.go?.("delegation");
    };
    tile.onclick = open;
    tile.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    };
    tile.setAttribute("role", "button");
    tile.setAttribute("tabindex", "0");
    tile.title = `Opens Outstanding Tasks showing ${FILTERS[f].label}`;
  });
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
    const table = tasksTable(data.late, { empty: "Nothing you handed out is past its date.", opts });
    if (old && (old.tagName === "TABLE" || old.classList.contains("work-table"))) old.replaceWith(table);
    else promises.after(table);
  }
}

function delegation(root, data, opts) {
  setWhen(root, `${data.open.length} open · ${data.late.length} late · `
    + `${data.check.length} to check · ${data.open.filter((t) => t.priority === "High").length} high priority`);
  newTaskButton(root);
  // The designed sample (one task, its states and its evidence) goes, up to the note.
  const grid = root.querySelector(".grid");
  // The filter lives on the screen's own markup, so leaving the screen clears it; a
  // Today tile hands one over just before it opens this screen.
  if (grid && pendingFilter) {
    grid.dataset.filter = pendingFilter;
    pendingFilter = null;
  }
  const current = FILTERS[grid?.dataset.filter] ? grid.dataset.filter : "";
  const redraw = (f) => {
    if (grid) grid.dataset.filter = f || "";
    delegation(root, data, opts);
  };
  root.querySelectorAll(".bk").forEach((tile) => {
    const spec = WORK_TILES.delegation[tile.querySelector(".l")?.textContent?.trim()];
    const f = spec && data.figures?.[spec.key]?.filter;
    if (!f) return;
    const pick = () => redraw(current === f ? "" : f);
    tile.removeAttribute("onclick");
    tile.classList.add("clickable");
    tile.classList.toggle("work-on", current === f);
    tile.setAttribute("role", "button");
    tile.setAttribute("tabindex", "0");
    tile.setAttribute("aria-pressed", current === f ? "true" : "false");
    tile.title = current === f ? "Shows every task again" : `Shows only ${FILTERS[f].label}`;
    tile.onclick = pick;
    tile.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pick();
      }
    };
  });
  let n = grid?.nextElementSibling;
  while (n && !n.classList.contains("note")) {
    const next = n.nextElementSibling;
    n.remove();
    n = next;
  }
  const wrap = el("div", "work-list");
  const rows = current && current !== "check" ? data.open.filter(FILTERS[current].keep) : data.open;
  if (current) {
    const bar = el("div", "work-filter");
    const shown = current === "check" ? data.check.length : rows.length;
    bar.append(el("span", null, `Showing ${FILTERS[current].label}: ${count(shown)} `
      + `${shown === 1 ? "task" : "tasks"}`), btn("Show All", "btn", () => redraw("")));
    wrap.append(bar);
  }
  if (!current || current === "check") {
    wrap.append(el("div", "sect", "Marked done: check the evidence"));
    if (!data.check.length) wrap.append(empty("Nothing to check.",
      `Work you handed out appears here when the person marks it done, for ${14} days.`));
    data.check.forEach((t) => wrap.append(checkCard(t, opts)));
  }
  if (current !== "check") {
    wrap.append(el("div", "sect", current ? FILTERS[current].label : "Still Open"));
    // Only what is on screen stays selected, so a filter never acts on hidden work.
    const shown = new Set(rows.map((t) => t.name));
    [...selected].forEach((name) => shown.has(name) || selected.delete(name));
    wrap.append(tasksTable(rows, { withPriority: true, selectable: true, opts,
      empty: current ? `Nothing you handed out is ${FILTERS[current].label.toLowerCase()}.`
        : "Nothing you handed out is open." }));
  } else {
    selected.clear();
  }
  (grid || root.querySelector(".topbar")).after(wrap);
}

/** New Task, beside the screen's heading: the action dialog's own form. */
function newTaskButton(root) {
  const bar = root.querySelector(".topbar");
  if (!bar || bar.querySelector(".work-tools")) return;
  const tools = el("div", "work-tools");
  tools.append(btn("New Task", "btn pri", () => fire("cc-action", { kind: "new_task", title: "" })));
  bar.append(tools);
}

/** The task's own drawer (TaskDrawer.jsx), never ERPNext. */
function openTask(t, opts) {
  if (!opts?.openDrawer) {
    window.open(t.url, "_blank", "noopener");
    return;
  }
  opts.openDrawer(React.createElement(TaskDrawer, { task: t, scope: opts.scope }));
}

function opensTask(node, t, opts) {
  node.classList.add("work-row");
  node.tabIndex = 0;
  node.setAttribute("role", "button");
  node.title = "Opens the task";
  node.onclick = () => openTask(t, opts);
  node.onkeydown = (e) => {
    if (e.target === node && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      openTask(t, opts);
    }
  };
}

/** What an open task's buttons send to the action dialog. */
export function taskRequest(kind, t) {
  return { kind, title: t.title, detail: t.detail, todo: t.name, assignee: t.to,
           assignee_name: t.to_name, date: t.date, priority: t.priority,
           doctype: t.reference?.doctype, docname: t.reference?.name };
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

function checkCard(t, opts) {
  const card = el("div", "alert med");
  opensTask(card, t, opts);
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

function tasksTable(rows, { withPriority = false, selectable = false, empty: none, opts } = {}) {
  if (!rows.length) {
    const e = empty(none, "");
    e.classList.add("work-table");
    return e;
  }
  const table = el("table", "dt");
  const head = el("tr");
  const boxes = [];
  let sync = () => {};
  if (selectable) head.append(el("th", "work-pick"));
  ["What", "Given to", "By when", "Late by", ...(withPriority ? ["Priority"] : []), ""].forEach((h) => head.append(el("th", null, h)));
  const thead = el("thead");
  thead.append(head);
  const tbody = el("tbody");
  rows.forEach((t) => {
    const tr = el("tr");
    const late = el("td", null, t.late_days ? days(t.late_days) : t.date ? "not yet due" : "no date set");
    if (t.late_days > 30) late.style.color = "var(--crit)";
    else if (t.late_days > 0) late.style.color = "var(--high)";
    const last = el("td", "work-acts");
    // Edit, Reassign, Close, Cancel: the work stays the manager's to manage (api/actions).
    // Escalate goes up the line, to the manager ERPNext names for the person. Close is
    // finished or no longer needed; Cancel is withdrawn.
    // One visible action and the rest under "⋯" (as on the alert cards), so a row stays one
    // line; the task drawer, opened by the row, carries every action too.
    last.onclick = (e) => e.stopPropagation();
    last.append(
      btn("Reassign", "btn", () => fire("cc-action", taskRequest("reassign", t))),
      menu([
        ["Edit Date And Priority", () => fire("cc-action", taskRequest("edit_task", t))],
        ["Escalate", () => fire("cc-action", taskRequest("escalate", t))],
        ["Close", () => fire("cc-action", taskRequest("close_task", t))],
        ["Cancel Assignment", () => fire("cc-action", taskRequest("cancel_task", t)), true],
      ]));
    opensTask(tr, t, opts);
    if (selectable) {
      const td = el("td", "work-pick");
      const box = checkbox(`Select ${t.title}`, selected.has(t.name), (on) => {
        if (on) selected.add(t.name);
        else selected.delete(t.name);
        sync();
      });
      box.dataset.todo = t.name;
      boxes.push(box);
      td.onclick = (e) => e.stopPropagation();
      td.append(box);
      tr.append(td);
    }
    tr.append(el("td", null, t.title), el("td", null, t.to_name || t.to || "—"),
      el("td", null, t.date ? shortDate(t.date) : "—"), late,
      ...(withPriority ? [el("td", null, t.priority)] : []), last);
    tbody.append(tr);
  });
  table.append(thead, tbody);
  // In a scroller, so a phone scrolls the table rather than the whole screen.
  const wrap = el("div", "work-table");
  wrap.append(table);
  if (!selectable) return wrap;

  // Select All (every row in this view), the count, and -- while anything is selected --
  // the bar with Close Selected and Cancel Selected, which ask first.
  const out = el("div", "work-selectable");
  const tools = el("div", "work-select");
  const all = checkbox("Select All", false, (on) => {
    rows.forEach((t) => (on ? selected.add(t.name) : selected.delete(t.name)));
    sync();
  });
  const allLabel = el("label", "work-all");
  allLabel.append(all, el("span", null, "Select All"));
  const tally = el("span", "work-count");
  tools.append(allLabel, tally);
  const bar = el("div", "work-bulk");
  bar.setAttribute("role", "region");
  bar.setAttribute("aria-label", "Selected Tasks");
  const barCount = el("b", "work-bulk-n");
  const chosen = () => rows.filter((t) => selected.has(t.name))
    .map((t) => ({ name: t.name, title: t.title, to: t.to, to_name: t.to_name }));
  const acts = el("div", "work-bulk-acts");
  acts.append(
    btn("Close Selected", "btn pri", () => fire("cc-action", { kind: "bulk_tasks", action: "close", tasks: chosen() })),
    btn("Cancel Selected", "btn dgr", () => fire("cc-action", { kind: "bulk_tasks", action: "cancel", tasks: chosen() })),
    btn("Clear", "btn", () => {
      selected.clear();
      sync();
    }));
  bar.append(barCount, acts);
  sync = () => {
    const n = rows.filter((t) => selected.has(t.name)).length;
    boxes.forEach((b) => { b.checked = selected.has(b.dataset.todo); });
    all.checked = n > 0 && n === rows.length;
    all.indeterminate = n > 0 && n < rows.length;
    tally.textContent = n ? `${count(n)} of ${count(rows.length)} selected` : `${count(rows.length)} in this view`;
    barCount.textContent = `${count(n)} Selected`;
    bar.hidden = !n;
  };
  sync();
  out.append(tools, wrap, bar);
  return out;
}

function checkbox(label, on, change) {
  const box = el("input");
  box.type = "checkbox";
  box.checked = !!on;
  box.setAttribute("aria-label", label);
  box.dataset.ccWired = "1";
  box.onclick = (e) => e.stopPropagation();
  box.onchange = () => change(box.checked);
  return box;
}

/* ------------------------------------------------------------------ helpers */
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
