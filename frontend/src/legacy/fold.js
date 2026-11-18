/** The severities, as every list, card and the bell name them. */
export const SEVERITY = { crit: "Critical", high: "High", med: "Medium", info: "For information" };

/** A row's severity word, in its severity's colour (shell.py, .fold-sev). */
export function severityTag(severity) {
  const tag = el("span", `fold-sev sev-${severity}`);
  tag.textContent = SEVERITY[severity] || severity;
  return tag;
}

/**
 * One line per item, the rest on demand: a numbered list (17 Nov 2026; the owner's
 * choice, "E · Numbered list", over the first folded cards).
 *
 * A card that carries several lines of detail and several buttons -- an approval, a
 * recommendation, an alert, a task marked done, a debtor -- becomes one numbered row:
 *
 *   01  Title, one line                                  GHS 48,200  [Approve]  ⌄
 *       CRITICAL · SALES · FINANCE
 *
 * Clicking the row, or its chevron, opens the rest under it, hung from the title's left
 * edge: the why and the step as text with the figure box to their right, then one line
 * with the facts on the left and the buttons on the right. Nothing is removed: every line
 * and every button is in the expansion, which stays in the DOM (hidden="until-found", so
 * the browser's find opens it). Opening a row closes any other open row in its list.
 *
 *   fold(card, { key, title, meta, figure, primary, text, box, more, foot, acts })
 *     card     the item's own element: its classes, id and data attributes stay
 *     key      what keeps it open across the screens' minute redraw ("appr:PO-1")
 *     title    the row's title, an element (an .awhat span): one line, ellipsised
 *     meta     the quiet line under the title: words or elements, joined by " · "
 *     figure   the amount on the row, or null
 *     primary  the one button that stays on the row, or null when there is no clear one
 *     text     the why and the step, in order
 *     box      the figure box beside the text, or null
 *     more     anything else, under the text (the steps, a narrow screen's figure)
 *     foot     the facts on the expansion's last line (owner, since, the record link)
 *     acts     the buttons at the right of that line, or null
 *
 * The number is the list's own count (CSS, shell.py NUMBERED ROWS). The toggle is a real
 * button (aria-expanded, aria-controls); Enter and Space are a button's own. A click
 * anywhere else on the row toggles it too, except on the row's own buttons and links.
 * Opening a row never touches history (backstack.js).
 */

// Rows open by key, kept for the session's page: a redraw draws them open again.
const opened = new Set();
let seq = 0;

const OWN = "button, a, input, select, textarea, label, [role='button'], [role='menu'], .amenu";

export function fold(card, {
  key = "", title = null, meta = [], figure = null, primary = null,
  text = [], box = null, more = [], foot = null, acts = null,
} = {}) {
  seq += 1;
  const id = `fold-${seq}`;
  card.classList.add("fold");
  if (key) card.dataset.fold = key;

  const row = el("div", "fold-row");
  const toggle = el("button", "fold-t");
  toggle.type = "button";
  toggle.id = `${id}-t`;
  toggle.dataset.ccWired = "1";
  toggle.setAttribute("aria-controls", `${id}-b`);
  const head = el("span", "fold-tt");
  if (title) {
    title.classList.add("fold-title");
    head.append(title);
  }
  const words = meta.filter((m) => m !== null && m !== undefined && m !== "");
  if (words.length) {
    const line = el("span", "fold-k");
    words.forEach((m, i) => {
      if (i) line.append(document.createTextNode(" · "));
      line.append(typeof m === "string" ? document.createTextNode(m) : m);
    });
    head.append(line);
  }
  toggle.append(head);
  if (figure) toggle.append(figure);
  row.append(toggle);
  if (primary) {
    const p = el("span", "fold-pri");
    p.append(primary);
    row.append(p);
  }
  const chev = el("span", "fold-chev");
  chev.setAttribute("aria-hidden", "true");
  row.append(chev);

  const panel = el("div", "fold-b");
  panel.id = `${id}-b`;
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-labelledby", toggle.id);
  const lines = text.filter(Boolean);
  if (lines.length || box) {
    const main = el("div", "fold-main");
    const body = el("div", "fold-text");
    body.append(...lines);
    main.append(body);
    if (box) {
      box.classList.add("fold-box");
      main.append(box);
      card.classList.add("fold-boxed");
    }
    panel.append(main);
  }
  panel.append(...more.filter(Boolean));
  if (foot || acts) {
    const line = el("div", "fold-foot");
    if (foot) line.append(foot);
    if (acts) line.append(acts);
    panel.append(line);
  }
  card.append(row, panel);

  row.addEventListener("click", (e) => {
    const hit = e.target.closest(OWN);
    if (hit && hit !== toggle) return;
    if (toggle.getAttribute("aria-expanded") === "true") setOpen(card, false);
    else openOnly(card);
  });
  // The browser's find-in-page reaches into a closed row: it opens, as if clicked.
  panel.addEventListener("beforematch", () => openOnly(card));
  setOpen(card, opened.has(key));
  return card;
}

/** Open or close a folded card, and only it (the preview's measurement opens them all). */
export function setOpen(card, on) {
  const toggle = card?.querySelector(":scope > .fold-row > .fold-t");
  const panel = card?.querySelector(":scope > .fold-b");
  if (!toggle || !panel) return;
  toggle.setAttribute("aria-expanded", on ? "true" : "false");
  card.classList.toggle("fold-on", on);
  if (on) panel.removeAttribute("hidden");
  else panel.setAttribute("hidden", "until-found");
  const key = card.dataset.fold;
  if (key) {
    if (on) opened.add(key);
    else opened.delete(key);
  }
}

/** The list a row belongs to: the closest [data-fold-list] (the Executive Summary's
 *  recommendations, grouped by area, are one list), else the row's own parent. */
function listOf(card) {
  return card.parentElement?.closest("[data-fold-list]") || card.parentElement;
}

/** Open a row and close every other open row of its list: one open at a time. */
export function openOnly(card) {
  const list = listOf(card);
  list?.querySelectorAll(".fold.fold-on").forEach((other) => {
    if (other !== card && listOf(other) === list) setOpen(other, false);
  });
  setOpen(card, true);
}

/** Scroll to an item by id, opened, and mark it for a moment (Home's brief, the memo). */
export function reveal(id, flash) {
  const card = document.getElementById(id);
  if (!card) return null;
  if (card.classList.contains("fold")) openOnly(card);
  card.scrollIntoView({ behavior: "smooth", block: "center" });
  if (flash) {
    card.classList.add(flash);
    setTimeout(() => card.classList.remove(flash), 1600);
  }
  return card;
}

function el(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}
