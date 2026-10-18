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
import { renderMarkdown } from "./markdown.js";

export function renderAnswer(container, payload, { onOpen, onPdf } = {}) {
  container.textContent = "";
  if (!payload) return;

  container.append(block(payload, onOpen, onPdf));
}

export function renderThinking(container, question, steps = []) {
  container.textContent = "";
  const box = div("ap-think");
  box.append(span("ap-spin"));
  const t = document.createElement("div");
  t.append(bold(`Looking into “${question}”`),
    span("", steps.length ? "Working through it" : "Reading the question"));
  if (steps.length) {
    const ol = document.createElement("ol");
    ol.className = "ap-steps";
    steps.forEach((s, i) => {
      const li = document.createElement("li");
      li.className = i === steps.length - 1 ? "now" : "done";
      li.textContent = s;
      ol.append(li);
    });
    t.append(ol);
  }
  box.append(t);
  container.append(box);
}

export function renderFailure(container, message) {
  container.textContent = "";
  const el = div("warn");
  el.append(bold("Could not answer that."), text(" " + (message || "")));
  container.append(el);
}

/* ------------------------------------------------------------------------- */

function block(p, onOpen, onPdf) {
  const wrap = div("panel");
  wrap.style.margin = "0 0 16px";

  // No "Answer" heading: the question is the heading, and a label over a reply reads
  // like an exam paper.
  if (p.question) {
    const q = div("ans-q");
    q.textContent = p.question;
    wrap.append(q);
  }
  if (p.analyst_error) {
    const n = div("ap-note");
    n.append(text("The analyst could not answer this time, so this is the basic engine's answer."),
      span("", `Reason: ${p.analyst_error}`));
    wrap.append(n);
  }

  const body = div("askans");
  // The analyst answers in formatted text; the pattern answers are plain sentences.
  body.append(p.format === "markdown" ? renderMarkdown(p.answer) : text(p.answer || ""));
  wrap.append(body);

  if (p.entity) {
    const who = div("drfoot");
    who.append(text(
      `Read as ${p.entity.name} (${p.entity.kind}), matched on “${p.entity.matched_on}”. ` +
      `If that is the wrong one, name it more fully.`));
    wrap.append(who);
  }

  if (p.checked?.length) wrap.append(checkedList(p.checked, p));
  if (p.table?.rows?.length) wrap.append(table(p.table));
  if (p.suggestions?.length) wrap.append(suggestions(p.suggestions));

  const acts = div("acts");
  acts.style.margin = "12px 14px 14px";
  if (p.records?.fact && onOpen) {
    const b = document.createElement("button");
    b.className = "btn";
    b.textContent = "Open the records behind this";
    b.onclick = () => onOpen(p.records, p.answer);
    acts.append(b);
  }
  if (p.answered && p.answer && onPdf) {
    const b = document.createElement("button");
    b.className = "btn";
    b.textContent = "Download PDF";
    b.onclick = async () => {
      b.disabled = true;
      b.textContent = "Preparing…";
      try {
        await onPdf(p);
        b.textContent = "Downloaded";
      } catch (e) {
        b.textContent = "Export failed";
        b.title = e?.message || "";
      }
      setTimeout(() => { b.disabled = false; b.textContent = "Download PDF"; }, 2500);
    };
    acts.append(b);
  }
  if (acts.childNodes.length) wrap.append(acts);

  return wrap;
}

function checkedList(items, p) {
  const wrap = div("askchecked");
  wrap.append(span("askchecked-t", "What it checked"));
  const ul = document.createElement("ul");
  items.forEach((i) => {
    const li = document.createElement("li");
    li.textContent = i;
    ul.append(li);
  });
  // Which path understood the question. Worth showing rather than hiding: the figures
  // are the same either way, and a reader is entitled to know whether a model was
  // involved in reading their words.
  if (p?.planner) {
    const li = document.createElement("li");
    li.textContent =
      p.mode === "analyst"
        ? `answered by Gemini (${p.model}) from the lookups above. It reads the business `
          + "within your permissions; it cannot change anything in ERPNext"
        : p.planner === "gemini"
          ? "the wording was read by Gemini, which chose what to look up — the figures "
            + "above came from the records, not from the model"
          : "the wording was matched against known question patterns, with no model "
            + "involved";
    ul.append(li);
  }
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
