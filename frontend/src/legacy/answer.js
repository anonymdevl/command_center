/**
 * Rendering an answer into the designed Ask screen.
 *
 * The designed markup calls runSearch(value) and expects the answer to appear in its
 * own #sout2. So this builds nodes into that container and changes nothing else — no
 * new layout, no replacement screen.
 *
 * Everything is written with textContent. The answer text and the figures come from
 * the server, and nothing from the server is ever parsed as HTML.
 *
 * What it shows, in the order the screen promises: the answer, then what it checked,
 * then the rows. "What it checked" is not a footnote here — the designed note says the
 * screen shows it *before* it answers, and the reason is that a sentence about money
 * is worth nothing if you cannot see where it came from.
 */

import { exact, count, shortDate } from "../format.js";

export function renderAnswer(container, payload, { onOpen } = {}) {
  container.textContent = "";
  if (!payload) return;

  container.append(block(payload, onOpen));
}

export function renderThinking(container, question) {
  container.textContent = "";
  const el = div("step");
  el.append(span("spin"), text(`Looking up “${question}”…`));
  container.append(el);
}

export function renderFailure(container, message) {
  container.textContent = "";
  const el = div("warn");
  el.append(bold("Could not answer that."), text(" " + (message || "")));
  container.append(el);
}

/* ------------------------------------------------------------------------- */

function block(p, onOpen) {
  const wrap = div("panel");
  wrap.style.margin = "0 0 16px";

  const head = div("ph");
  const headText = document.createElement("div");
  headText.append(bold(p.answered ? "Answer" : "I cannot answer that"));
  if (p.intent) headText.append(span("", ` · ${p.intent.replace(/_/g, " ")}`));
  head.append(headText);
  wrap.append(head);

  const body = div("askans");
  body.append(text(p.answer || ""));
  wrap.append(body);

  if (p.entity) {
    const who = div("drfoot");
    who.append(text(
      `Read as ${p.entity.name} (${p.entity.kind}), matched on “${p.entity.matched_on}”. ` +
      `If that is the wrong one, name it more fully.`));
    wrap.append(who);
  }

  if (p.checked?.length) wrap.append(checkedList(p.checked));
  if (p.table?.rows?.length) wrap.append(table(p.table));
  if (p.suggestions?.length) wrap.append(suggestions(p.suggestions));

  if (p.records?.fact && onOpen) {
    const acts = div("acts");
    acts.style.margin = "12px 14px 14px";
    const b = document.createElement("button");
    b.className = "btn";
    b.textContent = "Open the records behind this";
    b.onclick = () => onOpen(p.records, p.answer);
    acts.append(b);
    wrap.append(acts);
  }

  return wrap;
}

function checkedList(items) {
  const wrap = div("askchecked");
  wrap.append(span("askchecked-t", "What it checked"));
  const ul = document.createElement("ul");
  items.forEach((i) => {
    const li = document.createElement("li");
    li.textContent = i;
    ul.append(li);
  });
  wrap.append(ul);
  return wrap;
}

function table(spec) {
  const t = document.createElement("table");
  t.className = "dt";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  spec.columns.forEach(([key, label]) => {
    const th = document.createElement("th");
    th.textContent = label;
    if (key !== spec.columns[0][0]) th.className = "r";
    hr.append(th);
  });
  thead.append(hr);
  t.append(thead);

  const tbody = document.createElement("tbody");
  spec.rows.forEach((row) => {
    const tr = document.createElement("tr");
    spec.columns.forEach(([key], i) => {
      const td = document.createElement("td");
      td.textContent = cell(key, row[key]);
      if (i > 0) td.className = "r";
      tr.append(td);
    });
    tbody.append(tr);
  });
  t.append(tbody);
  return t;
}

function cell(key, value) {
  if (value === null || value === undefined || value === "") return "—";
  if (/owed|undelivered|amount|value|spend/i.test(key)) return exact(value);
  if (/date|promised|paid/i.test(key)) return shortDate(value) || String(value);
  if (typeof value === "number") return count(value);
  return String(value);
}

function suggestions(list) {
  const wrap = div("askchecked");
  wrap.append(span("askchecked-t", "Try one of these"));
  const box = div("sugg");
  list.forEach((q) => {
    const b = document.createElement("button");
    b.className = "btn";
    b.textContent = q;
    // The designed screen installs runSearch globally; reuse it so a suggestion
    // behaves exactly like typing the question.
    b.onclick = () => window.runSearch && window.runSearch(q);
    box.append(b);
  });
  wrap.append(box);
  return wrap;
}

/* small builders, so nothing is ever assembled as an HTML string */
function div(cls) { const d = document.createElement("div"); if (cls) d.className = cls; return d; }
function span(cls, t) { const s = document.createElement("span"); if (cls) s.className = cls; if (t) s.textContent = t; return s; }
function bold(t) { const b = document.createElement("b"); b.textContent = t; return b; }
function text(t) { return document.createTextNode(t); }
