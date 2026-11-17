/**
 * The Executive Summary's memo (api/summary.py, command_center/summary.py): a board memo
 * with vital signs, drawn into the top of the screen. Everything below it -- the
 * recommendations with their actions, What Worked, the alerts -- is the screen as it was,
 * drawn by recommend.js and alerts.js exactly as before.
 *
 *   header       the week, when the figures were read from ERPNext, and for whom
 *   vital signs  five figures with the cards' own drawers; a change only where one is
 *                real (the server says which, and why not)
 *   short        one paragraph: the one worked out from the figures at once, then the
 *                AI's when it is written (renderShort swaps it in), so nothing waits on it
 *   decisions    the top three open recommendations, as ranked below, with their owners;
 *                each scrolls to its card
 *   risks        the most severe open alerts, with their severity; each scrolls to its card
 *   going well   Business Health questions scoring Healthy, in their own notes' words
 *   waiting      Waiting On You's three counts (renderWaiting), each opening its screen
 *
 * Built as DOM, never as HTML from the server.
 */

import { money } from "../format.js";

export const SUMMARY_VIEWS = new Set(["brief"]);
const SEV_FLAG = { crit: "f-crit", high: "f-high", med: "f-med", info: "f-ok" };

export function renderMemo(root, data, { onOpen } = {}) {
  if (!root || !data) return;
  const body = root.querySelector("#xm-body");
  if (!body) return;
  const head = data.header || {};
  const date = root.querySelector("#xm-date");
  if (date) date.textContent = head.dateline || "";
  const who = root.querySelector("#xm-for");
  if (who) who.textContent = head.for || "";

  const out = el("div", "xm-body");
  out.id = "xm-body";
  out.dataset.live = "1";
  out.append(vitals(data.vitals || [], onOpen));

  const short = el("section", "xm-short-w");
  short.id = "xm-short";
  short.append(el("h4", "xm-h", "The Short Version"));
  out.append(short);
  fillShort(short, data.short);

  const cols = el("div", "xm-cols");
  const main = el("div", "xm-main");
  main.append(el("h4", "xm-h", "Decisions For You This Week"),
    list(data.decisions, "Nothing to decide this week: no recommendation is open.", decision));
  main.append(el("h4", "xm-h", "Risks"), list(data.risks, "No open alerts.", risk));
  const end = el("div", "xm-end");
  const well = el("ul", "xm-well");
  (data.going_well || []).forEach((w) => {
    const li = el("li");
    li.append(el("span", "xm-tick"), body2(w.key !== "control_score" ? w.question : null, w.text));
    well.append(li);
  });
  if (!well.children.length) well.append(el("li", "xm-none", data.nothing_well || "Nothing to report as going well yet"));
  // Filled by renderWaiting, called after this with the latest answer.
  const wait = el("div", "xm-wait");
  wait.id = "xm-wait";
  wait.append(el("p", "xm-none", "Reading what is waiting on you…"));
  end.append(el("h4", "xm-h", "Going Well"), well, el("h4", "xm-h", "Waiting On You"), wait);
  cols.append(main, end);
  out.append(cols);
  body.replaceWith(out);
}

/** The memo could not be read: its place says so rather than waiting for ever. */
export function memoFailed(root, error) {
  const body = root?.querySelector("#xm-body");
  if (!body || body.dataset.live === "1") return;
  body.textContent = "";
  const e = el("div", "work-empty");
  e.append(el("b", null, "The summary could not be read just now."),
    el("span", null, error?.message || "It is read again when the screen is opened."));
  body.append(e);
}

/** The AI's paragraph, once written, in place of the one worked out from the figures. */
export function renderShort(root, short) {
  const box = root?.querySelector("#xm-short");
  if (!box || !short) return;
  fillShort(box, short);
}

/** Waiting On You (api/summary.waiting): three counts, each opening its screen. A read
 *  that failed with nothing to show says so, with a retry, rather than "Reading…" for
 *  ever (17 Nov 2026). */
export function renderWaiting(root, data, { go, error, retry } = {}) {
  const box = root?.querySelector("#xm-wait");
  if (!box) return;
  if (!data) {
    if (!error) return;
    box.textContent = "";
    delete box.dataset.live;
    const signedOut = error.status === 401 || error.status === 403;
    box.append(el("p", "xm-none", signedOut
      ? "You have been signed out: sign in again to see what is waiting on you."
      : `What is waiting on you could not be read just now.${error.message ? ` ${error.message}` : ""}`));
    if (retry && !signedOut) {
      const b = el("button", "xm-link", "Try Again");
      b.type = "button";
      b.onclick = () => {
        box.textContent = "";
        box.append(el("p", "xm-none", "Reading what is waiting on you…"));
        retry();
      };
      box.append(b);
    }
    return;
  }
  box.textContent = "";
  box.dataset.live = "1";
  if (!data.available) {
    box.append(el("p", "xm-none", data.reason || "Your approvals and tasks could not be read just now."));
    if (!data.unreachable) {
      const b = el("button", "xm-link", "How To Link Your Key");
      b.type = "button";
      b.onclick = () => go?.("approvals");
      box.append(b);
    }
    return;
  }
  const ul = el("ul", "xm-counts");
  (data.items || []).forEach((it) => {
    const li = el("li");
    const b = el("button", `xm-count${it.count ? "" : " zero"}`);
    b.type = "button";
    b.append(el("b", null, String(it.count)), el("span", null, it.label));
    b.onclick = () => go?.(it.opens);
    li.append(b);
    ul.append(li);
  });
  box.append(ul);
}

function fillShort(box, s) {
  box.querySelectorAll(".xm-short,.xm-by").forEach((n) => n.remove());
  if (!s) return;
  const p = el("p", "xm-short", s.text || "");
  p.dataset.source = s.source || "fallback";
  box.append(p);
  let by;
  if (s.source === "ai") {
    by = `Written by the AI${s.at ? ` at ${s.at}` : " today"} from the figures on this page; every number in it was checked against them.`;
  } else if (s.pending) {
    by = "Worked out from the figures on this page. The AI's version is being written and will take its place.";
  } else {
    by = `Worked out from the figures on this page.${s.why ? ` ${s.why}` : ""}`;
  }
  box.append(el("p", "xm-by", by));
}

function vitals(items, onOpen) {
  const row = el("div", "xm-vitals");
  row.setAttribute("role", "list");
  items.forEach((v) => {
    const f = v.figure || null;
    const b = el("button", "xm-v");
    b.type = "button";
    b.setAttribute("role", "listitem");
    b.dataset.key = v.key;
    b.append(el("span", "xm-vl", v.label));
    const n = el("span", "xm-vn");
    if (v.shown && f) {
      if (f.unit === "currency") {
        const m = money(f.value, f.currency || "");
        if (m.currency) n.append(el("span", "xm-cx", m.currency));
        n.append(document.createTextNode(m.figure));
        if (m.suffix) n.append(el("span", "xm-mag", m.suffix));
      } else if (f.unit === "percent") {
        n.append(document.createTextNode(String(Math.round(Number(f.value)))), el("small", null, "%"));
      } else {
        n.append(document.createTextNode(String(f.value)));
      }
    } else {
      n.textContent = "—";
      n.classList.add("none");
    }
    b.append(n);
    const c = v.change;
    if (c?.text) {
      b.append(el("span", `xm-vd ${c.kind === "pending" ? "wait" : c.tone || "flat"}`, c.text));
    } else if (!v.shown) {
      b.append(el("span", "xm-vd wait", "Not read yet"));
    }
    if (f && f.key) {
      b.onclick = () => onOpen?.(f);
    } else {
      b.disabled = true;
    }
    row.append(b);
  });
  return row;
}

function list(items, none, draw) {
  const ol = el("ol", "xm-ol");
  (items || []).forEach((x) => ol.append(draw(x)));
  return ol.children.length ? ol : el("p", "xm-none", none);
}

function decision(d) {
  const li = el("li");
  const b = el("button", "xm-item", d.title || "");
  b.type = "button";
  b.onclick = () => reach(`rec-${d.name}`);
  const body = el("div");
  body.append(b);
  if (d.owner) body.append(el("span", "xm-k", d.owner));
  li.append(body);
  return li;
}

function risk(r) {
  const li = el("li");
  const b = el("button", "xm-item", r.title || "");
  b.type = "button";
  b.onclick = () => reach(`alert-${r.name}`);
  const body = el("div");
  body.append(b, el("span", `flag ${SEV_FLAG[r.severity] || "f-med"} xm-sev`, r.severity_word || ""));
  li.append(body);
  return li;
}

/** Scroll to the full card below and mark it for a moment. */
function reach(id) {
  const card = document.getElementById(id);
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  card.classList.add("xm-reached");
  setTimeout(() => card.classList.remove("xm-reached"), 1600);
}

function body2(label, text) {
  const s = el("span");
  if (label) s.append(el("b", null, label), document.createTextNode(" "));
  s.append(document.createTextNode(text || ""));
  return s;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
