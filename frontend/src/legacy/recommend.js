/**
 * The recommendations (api/recommend.py): Home's Top actions and the Executive Summary's
 * full list, grouped by area, with the Daily Brief at its top when one is written.
 *
 * Each is the alert card's shape -- what to do, the evidence, the money at stake, who
 * owns it -- with its own actions: What To Do opens the steps and the guide to doing it
 * in ERPNext; Ask AI asks the analyst; Done, Not Relevant (with a reason, optional) and
 * Snooze 7 or 30 days are remembered on the server. Built as DOM in the designed
 * classes, never as HTML from the server.
 */

import { api } from "../api/client.js";
import { count, money } from "../format.js";
import { menu } from "./actions.js";
import { guideBox } from "./guide.js";

export const REC_VIEWS = new Set(["command", "brief"]);
const WORDS = { crit: "Critical", high: "High", med: "Medium", info: "For information" };
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
  if (!recs.length) list.append(empty(data));
  if (view === "command") {
    recs.slice(0, TOP).forEach((r) => list.append(card(r, onOpen)));
  } else {
    brief(root, data.brief);
    const sub = root.querySelector("#rec-sub");
    if (sub) sub.textContent = recs.length ? `${count(recs.length)} open, most money at stake first` : "";
    const areas = data.areas || {};
    Object.keys(areas).forEach((key) => {
      const mine = recs.filter((r) => r.area === key);
      if (!mine.length) return;
      const head = el("div", "rec-area", areas[key]);
      head.append(el("span", null, `${count(mine.length)} open`));
      list.append(head);
      mine.forEach((r) => list.append(card(r, onOpen)));
    });
    if ((data.history || []).length) {
      list.append(el("div", "rec-area", "Recently closed"));
      const ul = el("ul", "rec-done");
      data.history.forEach((h) => ul.append(el("li", null, `${h.title} — ${closed(h)}`)));
      list.append(ul);
    }
  }
  if (data.unreachable || (data.failed || []).length) {
    list.append(el("div", "rec-done", data.unreachable
      ? "The business's ERPNext did not answer, so the recommendations that read it were not checked this time."
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
      ? "The business's ERPNext did not answer; what reads it is checked again shortly."
      : "The rules found nothing worth acting on in the latest data."));
  return e;
}

function closed(h) {
  if (h.status === "Not Relevant") return `marked not relevant${h.reason ? `: ${h.reason}` : ""}`;
  if (h.status === "Done") return "marked done";
  return h.acted_by ? "cleared after it was marked done" : "cleared in the data";
}

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

function card(r, onOpen) {
  const c = el("div", `alert ${r.severity}`);
  c.id = `rec-${r.name}`;
  c.dataset.live = "1";
  c.dataset.ccWired = "1";

  const row = el("div", "arow");
  const body = el("div");
  body.append(el("span", "asev", WORDS[r.severity] || r.severity),
    el("span", "asev rec-area-tag", r.area_label || ""),
    el("div", "awhat", r.title), el("div", "awhy", r.why || ""));
  if (r.reopened_after_done) {
    body.append(el("div", "asw", `→ Marked done on ${r.reopened_after_done}, and the figures still show it.`));
  } else if (r.what_to_do?.length) {
    body.append(el("div", "asw", `→ ${r.what_to_do[0]}`));
  }
  row.append(body);
  const fig = figure(r);
  if (fig) row.append(fig);
  c.append(row);

  const steps = el("div", "rec-steps");
  steps.hidden = !opened.has(r.name);
  const ol = el("ol");
  (r.what_to_do || []).forEach((s) => ol.append(el("li", null, s)));
  steps.append(ol);
  if (r.how_in_erpnext) steps.append(guideBox(r.how_in_erpnext, { compact: true }));
  c.append(steps);

  const meta = el("div", "ameta");
  if (r.drill?.fact || r.drill?.href) {
    const src = el("span", "chip src", "");
    src.append(document.createTextNode("Records · "), el("b", null, "open the records"));
    src.onclick = () => (r.drill.href
      ? window.open(r.drill.href, "_blank", "noopener")
      : onOpen?.({ label: r.title, drill: r.drill }));
    meta.append(src);
  }
  meta.append(chip("Owner", r.owner_role), chip("Seen since", (r.first_seen || "").slice(0, 10)));
  c.append(meta);

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
  c.append(acts);
  return c;
}

function figure(r) {
  const f = el("div", "afig");
  if (r.money_at_stake) {
    const m = money(r.money_at_stake, r.currency || "");
    f.append(el("span", "cx", m.currency), document.createTextNode(m.figure));
    if (m.suffix) f.append(el("span", "mag", m.suffix));
    f.append(el("small", null, "at stake"));
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
  c.querySelector(".acts")?.before(form);
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
      c.querySelector(".acts")?.before(el("div", "rec-note", e?.message || "That did not work."));
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
