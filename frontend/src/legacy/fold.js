/**
 * One line per item, the rest on demand (17 Nov 2026, the approved declutter mockups).
 *
 * A card that carries several lines of detail and several buttons -- an approval, a
 * recommendation, an alert, a task marked done, a debtor -- becomes one row: only the
 * essentials and its primary action. Clicking the row, or its chevron, opens the rest
 * under it. Nothing is removed: every line and every button is moved into the expansion,
 * which stays in the DOM (hidden="until-found", so the browser's find opens it).
 *
 *   fold(card, { key, head, primary, body })
 *     card     the item's own element: its classes, id and data attributes stay
 *     key      what keeps it open across the screens' minute redraw ("appr:PO-1")
 *     head     the row's essentials, as phrasing elements (spans): they are the toggle
 *     primary  the one button that stays on the row, or null when there is no clear one
 *     body     everything else, in order
 *
 * The toggle is a real button (aria-expanded, aria-controls); Enter and Space are a
 * button's own. A click anywhere else on the row toggles it too, except on the row's
 * own buttons and links. Opening a row never touches history (backstack.js).
 */

// Rows open by key, kept for the session's page: a redraw draws them open again.
const opened = new Set();
let seq = 0;

const OWN = "button, a, input, select, textarea, label, [role='button'], [role='menu'], .amenu";

export function fold(card, { key = "", head = [], primary = null, body = [] } = {}) {
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
  toggle.append(...head.filter(Boolean));
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
  panel.append(...body.filter(Boolean));
  card.append(row, panel);

  row.addEventListener("click", (e) => {
    const hit = e.target.closest(OWN);
    if (hit && hit !== toggle) return;
    setOpen(card, toggle.getAttribute("aria-expanded") !== "true");
  });
  // The browser's find-in-page reaches into a closed row: it opens, as if clicked.
  panel.addEventListener("beforematch", () => setOpen(card, true));
  setOpen(card, opened.has(key));
  return card;
}

/** Open or close a folded card. */
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

/** Scroll to an item by id, opened, and mark it for a moment (Home's brief, the memo). */
export function reveal(id, flash) {
  const card = document.getElementById(id);
  if (!card) return null;
  if (card.classList.contains("fold")) setOpen(card, true);
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
