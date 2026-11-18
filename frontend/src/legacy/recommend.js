/**
 * The recommendations (api/recommend.py): Home's Top actions and the Executive Summary's
 * full list, grouped by area, with the Daily Brief at its top when one is written.
 *
 * Each is the alert card's shape -- what to do, the evidence, the money at stake, who
 * owns it -- with its own actions: What To Do opens the steps and the guide to doing it
 * in ERPNext; Ask AI asks the analyst; Done, Not Relevant (with a reason, optional) and
 * Snooze 7 or 30 days are remembered on the server. Built as DOM in the designed
 * classes, never as HTML from the server.
 *
 * The adaptive layer (recommend/adaptive.py, learning.py, review.py) adds to each card:
 * its source (Rule, Adaptive -- judged against the business's own usual range -- or
 * AI-found by the daily review), "why now", a small chart of the figure with its usual
 * band, and under What To Do the learned weight and why, the threshold it ran with and,
 * for an AI-found one, the evidence it rests on. Recently Closed says what came of
 * advice marked done; the Executive Summary ends with What Worked.
 */

import { api } from "../api/client.js";
import { count, money, shortDate } from "../format.js";
import { menu } from "./actions.js";
import { guideBox } from "./guide.js";
import { sparkline } from "./spark.js";
import { fold, severityTag } from "./fold.js";

export const REC_VIEWS = new Set(["command", "brief"]);
const TOP = 5;
// Which cards have their steps open: kept across the minute's refresh.
const opened = new Set();

export function renderRecs(root, view, data, { onOpen } = {}) {
  if (!root || !data || !REC_VIEWS.has(view)) return;
  const slot = root.querySelector(".rec-live-list");
  if (!slot) return;
  const recs = data.recommendations || [];
  const list = el("div", "rec-live-list");
  list.dataset.rec = slot.dataset.rec || "";
  list.dataset.live = "1";
  // One numbered list, one row open at a time, across the areas (legacy/fold.js).
  list.dataset.foldList = "1";
  if (!recs.length) list.append(empty(data));
  if (view === "command") {
    recs.slice(0, TOP).forEach((r) => list.append(card(r, onOpen)));
  } else {
    brief(root, data.brief);
    const sub = root.querySelector("#rec-sub");
    if (sub) sub.textContent = recs.length ? `${count(recs.length)} open, most money at stake first` : "";
    // Each area is its own group -- a ruled heading with its count, and its cards under
    // it -- so the areas read at a glance rather than as one long list (17 Nov 2026).
    // The order and the cards are as they were (shell.py, EXECUTIVE SUMMARY GROUPS).
    const areas = data.areas || {};
    Object.keys(areas).forEach((key) => {
      const mine = recs.filter((r) => r.area === key);
      if (!mine.length) return;
      const group = el("section", "rec-group");
      const head = el("div", "rec-area", areas[key]);
      head.append(el("span", null, `${count(mine.length)} open`));
      group.setAttribute("aria-label", areas[key]);
      group.append(head);
      mine.forEach((r) => group.append(card(r, onOpen)));
      list.append(group);
    });
    if ((data.history || []).length) {
      const group = el("section", "rec-group rec-group-closed");
      list.append(group);
      group.append(el("div", "rec-area", "Recently closed"));
      const ul = el("ul", "rec-done");
      data.history.forEach((h) => ul.append(el("li", null, `${h.title} — ${closed(h)}`)));
      group.append(ul);
    }
    if (data.what_worked) list.append(worked(data.what_worked));
  }
  if (data.unreachable || (data.failed || []).length) {
    list.append(el("div", "rec-done", data.unreachable
      ? "The business's ERPNext was taking longer than usual to answer, so the recommendations that read it were not checked this time; they are checked again shortly."
      : `Not checked this time: ${(data.failed || []).map((f) => f.rule.toLowerCase()).join(", ")}.`));
  }
  slot.replaceWith(list);
}

/** The recommendations could not be read: the slot says so rather than waiting. */
export function recsFailed(root, view, error) {
  if (!root || !REC_VIEWS.has(view)) return;
  const slot = root.querySelector(".rec-live-list");
  if (!slot || slot.dataset.live === "1") return;
  slot.textContent = "";
  const e = el("div", "work-empty");
  e.append(el("b", null, "The recommendations could not be read just now."),
    el("span", null, error?.message || "They are read again when the screen is opened."));
  slot.append(e);
}

function empty(data) {
  const e = el("div", "work-empty");
  e.append(el("b", null, "Nothing to recommend right now."),
    el("span", null, data.unreachable
      ? "The business's ERPNext is taking longer than usual to answer; what reads it is checked again shortly."
      : "The rules found nothing worth acting on in the latest data."));
  return e;
}

function closed(h) {
  if (h.status === "Not Relevant") return `marked not relevant${h.reason ? `: ${h.reason}` : ""}`;
  const o = h.outcome;
  const checked = o?.outcome
    ? `; checked: ${OUTCOME[o.outcome] || o.outcome}${o.note ? ` (${o.note})` : ""}`
    : o?.review_on ? `; checked again on ${o.review_on}` : "";
  if (h.status === "Done") return `marked done${checked}`;
  return (h.acted_by ? "cleared after it was marked done" : "cleared in the data") + checked;
}

const OUTCOME = { Improved: "improved", "No Change": "no change", Worse: "got worse", Unknown: "not enough history to judge" };

/** What Worked: a month of advice marked done, and what came of it (learning.what_worked). */
function worked(w) {
  const box = el("div", "rec-worked");
  box.append(el("b", null, `What Worked${w.period ? ` — ${w.period}` : ""}`), el("p", null, w.says || ""));
  if ((w.rules || []).length) {
    const ul = el("ul");
    w.rules.forEach((r) => ul.append(el("li", null, `${r.title}: improved ${r.improved} of ${r.judged}`)));
    box.append(ul);
  }
  return box;
}

const ORDINAL = ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth"];

function brief(root, b) {
  const box = root.querySelector("#rec-brief");
  if (!box) return;
  box.textContent = "";
  if (!b || !(b.text || b.error)) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.append(el("b", null, "Daily Brief"));
  if (b.text) {
    b.text.split("\n").filter((p) => p.trim()).forEach((p) => box.append(el("p", null, p)));
    box.append(el("small", null, `Written by Claude on ${b.date} from the recommendations and `
      + "headline figures below only."));
  } else {
    box.append(el("p", null, `Today's brief was not written. ${b.error}`));
  }
}

/* One numbered row (legacy/fold.js): what to do and the money at stake, with its priority,
   area and owner as the quiet line under the title; the why and the step open under it
   with the figure box beside them, then the owner, since when, its source and the record
   on one line with every action. */
function card(r, onOpen) {
  const c = el("div", `alert ${r.severity}`);
  c.id = `rec-${r.name}`;
  c.dataset.live = "1";
  c.dataset.ccWired = "1";

  // Its owner, unless the owner is the area itself ("Sales · Sales").
  const owner = (r.owner_role || "").toLowerCase() === (r.area_label || "").toLowerCase() ? null : r.owner_role;
  const meta = [severityTag(r.severity), r.area_label, owner];

  const text = [el("div", "awhy", r.why || "")];
  if (r.why_now) text.push(el("div", "rec-why-now", `Why now: ${r.why_now}`));
  if (r.ai_priority?.reason) {
    const nth = ORDINAL[r.ai_priority.rank] || `number ${r.ai_priority.rank}`;
    text.push(el("div", "rec-why-now", `The daily AI review puts this ${nth} today: ${r.ai_priority.reason}`));
  }
  if (r.reopened_after_done) {
    text.push(el("div", "asw", `→ Marked done on ${r.reopened_after_done}, and the figures still show it.`));
  } else if (r.what_to_do?.length) {
    text.push(el("div", "asw", `→ ${r.what_to_do[0]}`));
  }
  const fig = figure(r);
  const chart = r.baseline?.chart ? sparkline(r.baseline.chart, r.baseline.says) : null;
  let side = null;
  if (fig || chart) {
    side = el("div", "rec-side");
    if (fig) side.append(fig);
    if (chart) side.append(chart);
  }

  const steps = el("div", "rec-steps");
  steps.hidden = !opened.has(r.name);
  const ol = el("ol");
  (r.what_to_do || []).forEach((s) => ol.append(el("li", null, s)));
  steps.append(ol);
  if (r.how_in_erpnext) steps.append(guideBox(r.how_in_erpnext, { compact: true }));
  steps.append(...learnedNotes(r));

  // Owner, since when, where it comes from (Rule, Adaptive, AI-found; the learned weight in
  // its tooltip), when it is for, and the records behind it: plain words on one line.
  const facts = el("div", "ameta");
  facts.append(chip("Owner", r.owner_role), chip("Since", shortDate(r.first_seen) || "—"));
  if (r.source_label) {
    const src = el("span", `rec-src rec-src-${r.source || "rule"}`, r.source_label);
    if (r.learned?.explain) src.title = r.learned.explain;
    facts.append(src);
  }
  if (r.timeframe) facts.append(el("span", "rec-when", r.timeframe));
  if (r.drill?.fact || r.drill?.href) {
    const src = el("span", "chip src", "");
    src.append(document.createTextNode("Records · "), el("b", null, "open the records"));
    src.onclick = () => (r.drill.href
      ? window.open(r.drill.href, "_blank", "noopener")
      : onOpen?.({ label: r.title, drill: r.drill }));
    facts.append(src);
  }

  const acts = el("div", "acts");
  const what = btn(steps.hidden ? "What To Do" : "Hide Steps", "btn pri", () => {
    steps.hidden = !steps.hidden;
    if (steps.hidden) opened.delete(r.name); else opened.add(r.name);
    what.textContent = steps.hidden ? "What To Do" : "Hide Steps";
  });
  acts.append(
    what,
    btn("Ask AI", "btn", () => fire("cc-ask", { question: r.ask || `${r.title} What should we do?` })),
    btn("Done", "btn", () => act(c, r, "done")),
    menu([
      ["Not Relevant…", () => reason(c, r), false],
      ["Snooze 7 Days", () => act(c, r, "snooze", { days: 7 }), false],
      ["Snooze 30 Days", () => act(c, r, "snooze", { days: 30 }), false],
    ]),
  );
  return fold(c, { key: `rec:${r.name}`, title: el("span", "awhat", r.title), meta, figure: figure(r, { row: true }),
                   text, box: side, more: [steps], foot: facts, acts });
}

/** Under What To Do: the evidence (AI-found), the usual range, the threshold, the weight. */
function learnedNotes(r) {
  const out = [];
  if ((r.evidence || []).length) {
    const box = el("div", "rec-learned");
    box.append(el("b", null, "The Evidence It Rests On"));
    const ul = el("ul");
    r.evidence.forEach((e) => ul.append(el("li", null, e.text)));
    box.append(ul);
    if (r.confidence) box.append(el("p", null, `Confidence: ${r.confidence}. Found by the daily AI review; every figure in it was checked against the evidence.`));
    out.push(box);
  }
  const lines = [];
  if (r.baseline?.says) lines.push([r.baseline.label || "The Figure", r.baseline.says]);
  if (r.threshold?.says) lines.push(["Threshold", r.threshold.says]);
  if (r.learned?.explain) lines.push(["Why It Ranks Here", r.learned.explain]);
  if (lines.length) {
    const box = el("div", "rec-learned");
    lines.forEach(([k, v]) => {
      const p = el("p");
      p.append(el("b", null, `${k}: `), document.createTextNode(v));
      box.append(p);
    });
    out.push(box);
  }
  return out;
}

/** The money at stake, or the count: in the figure box, or on the row (a span, without
 *  "at stake", which the box says). */
function figure(r, { row = false } = {}) {
  const f = el(row ? "span" : "div", "afig");
  if (r.money_at_stake) {
    const m = money(r.money_at_stake, r.currency || "");
    f.append(el("span", "cx", m.currency), document.createTextNode(m.figure));
    if (m.suffix) f.append(el("span", "mag", m.suffix));
    if (!row) f.append(el("small", null, "at stake"));
    return f;
  }
  if (r.count) {
    f.append(document.createTextNode(count(r.count)));
    if (r.unit) f.append(el("small", null, r.unit));
    return f;
  }
  return null;
}

/** "Not relevant": an optional reason, asked for in the card itself. */
function reason(c, r) {
  if (c.querySelector(".rec-reason")) return;
  const form = el("form", "rec-reason");
  const input = el("input");
  input.placeholder = "Why not (optional), so the rule can be tuned";
  input.maxLength = 300;
  form.append(input, btn("Not Relevant", "btn pri", () => form.requestSubmit()),
    btn("Cancel", "btn", () => form.remove()));
  form.onsubmit = (e) => {
    e.preventDefault();
    act(c, r, "not_relevant", { reason: input.value });
  };
  c.querySelector(".fold-foot")?.before(form);
  input.focus();
}

function act(c, r, action, extra = {}) {
  c.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  api.recAct({ name: r.name, action, ...extra })
    .then(() => {
      opened.delete(r.name);
      c.remove();
      fire("cc-recs-changed", {});
    })
    .catch((e) => {
      c.querySelectorAll("button").forEach((b) => { b.disabled = false; });
      c.querySelector(".rec-note")?.remove();
      c.querySelector(".fold-foot")?.before(el("div", "rec-note", e?.message || "That did not work."));
    });
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
