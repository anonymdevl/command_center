/**
 * Live alerts in the designed alert cards (api/alerts.py).
 *
 * Home's "Needs your attention" and the Executive Summary were drawn with the alerts
 * the extract produced on the day it was taken. They are now the alert engine's: the
 * same six parts -- what, why, figure, source, owner, elapsed -- in the same card, read
 * from the KPIs the cards beside them use.
 *
 * Every action is real. Assign, Request evidence and Escalate become a To-Do linked to
 * the alert; Defer, Dismiss and "Not a real problem" are remembered with a reason; the
 * records open in the drawer. Built as DOM in the designed classes, never as HTML.
 */

import { api } from "../api/client.js";
import { money, exact } from "../format.js";
import { menu } from "./actions.js";

export const ALERT_VIEWS = new Set(["command", "brief", "health"]);
const WORDS = { crit: "Critical", high: "High", med: "Medium", info: "For information" };

export function renderAlerts(root, view, data, { onOpen } = {}) {
  if (!root || !data || !ALERT_VIEWS.has(view)) return;
  const alerts = data.alerts || [];
  const list = el("div", "alert-live-list");
  if (!alerts.length) {
    const e = el("div", "work-empty");
    e.append(el("b", null, "Nothing needs your attention."),
      el("span", null, "The alert rules found no material exception in the latest data."));
    list.append(e);
  }
  alerts.forEach((a) => list.append(card(a, onOpen)));

  if (view === "command") {
    const head = Array.from(root.querySelectorAll(".sect"))
      .find((s) => /needs your attention/i.test(s.textContent));
    // The heading's words are in its first span (or, in an older build, a bare text node).
    const label = head?.querySelector(":scope > span") || (head?.firstChild?.nodeType === 3 ? head.firstChild : null);
    if (label) label.textContent = `Needs your attention — ${alerts.length} item${alerts.length === 1 ? "" : "s"}`;
  }

  // Later passes (new figures, an action taken) replace the list where it already is.
  const existing = root.querySelector(".alert-live-list");
  if (existing) {
    existing.replaceWith(list);
    return;
  }
  const designed = Array.from(root.querySelectorAll(".alert:not([data-live])"));
  if (!designed.length) return;
  designed[0].before(list);
  designed.forEach((d) => d.remove());
}

function card(a, onOpen) {
  const c = el("div", `alert ${a.severity}`);
  c.id = `alert-${a.name}`;
  c.dataset.live = "1";
  c.dataset.ccWired = "1";

  const row = el("div", "arow");
  const body = el("div");
  const sev = el("span", "asev", WORDS[a.severity] || a.severity);
  body.append(sev);
  if (a.status === "Actioned") body.append(el("span", "asev astate", "Assigned"));
  body.append(el("div", "awhat", a.title), el("div", "awhy", a.why || ""),
    el("div", "asw", `→ ${a.next_step || ""}`));
  row.append(body);
  if (a.figure !== null && a.figure !== undefined) row.append(figure(a));
  c.append(row);

  const records = () => {
    act(a.name, "acknowledge");
    onOpen?.({ label: a.title, drill: { fact: a.drill_fact, filters: a.drill_filters } });
  };
  const meta = el("div", "ameta");
  if (a.drill_fact) {
    const src = el("span", "chip src", "");
    src.append(document.createTextNode(`${a.source_label || "Records"} · `), el("b", null, "open the records"));
    src.onclick = records;
    meta.append(src);
  }
  meta.append(chip("Owner", a.owner_label), chip("Elapsed", a.elapsed));
  if (a.todo) {
    const t = el("a", "chip", "");
    t.href = `/app/todo/${encodeURIComponent(a.todo)}`;
    t.target = "_blank";
    t.rel = "noreferrer";
    t.append(document.createTextNode("To-Do "), el("b", null, a.todo));
    meta.append(t);
  }
  c.append(meta);

  const ctx = { title: a.title, detail: [a.why, a.next_step && `Next: ${a.next_step}`].filter(Boolean).join("\n"),
                owner: a.owner_label, alert: a.name };
  const acts = el("div", "acts");
  acts.append(
    btn("Assign", "btn pri", () => fire("cc-action", { kind: "assign", ...ctx })),
    btn("Ask AI about this", "btn", () => {
      act(a.name, "acknowledge");
      fire("cc-ask", { question: `${a.title}. What is behind this, and what should we do about it?` });
    }),
    menu([
      ["Request evidence", () => fire("cc-action", { kind: "evidence", ...ctx }), false],
      ["Escalate", () => fire("cc-action", { kind: "escalate", ...ctx }), false],
      ...(a.drill_fact ? [["Open the records", records, false]] : []),
      ["Defer…", () => fire("cc-action", { kind: "alert", verb: "defer", alert: a.name, title: a.title }), false],
      ["Not a real problem…", () => fire("cc-action", { kind: "alert", verb: "false_positive", alert: a.name, title: a.title }), false],
      ["Dismiss…", () => fire("cc-action", { kind: "alert", verb: "dismiss", alert: a.name, title: a.title }), true],
    ]),
  );
  c.append(acts);
  return c;
}

function figure(a) {
  const f = el("div", "afig");
  if (a.figure_unit === "currency") {
    const m = money(a.figure, a.currency || "");
    f.append(el("span", "cx", m.currency), document.createTextNode(m.figure));
    if (m.suffix) f.append(el("span", "mag", m.suffix));
  } else {
    f.append(document.createTextNode(exact(a.figure, { decimals: 0 })));
    const unit = { count: "", quantity: "" }[a.figure_unit] ?? a.figure_unit;
    if (unit) f.append(el("small", null, unit));
  }
  return f;
}

/** Fire-and-forget: opening an alert acknowledges it. A failure changes nothing seen. */
function act(name, action) {
  api.alertAct({ name, action }).catch(() => {});
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
