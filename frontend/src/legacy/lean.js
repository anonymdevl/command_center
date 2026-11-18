/**
 * Long words on a card show their first line; a click on them opens the rest (18 Nov 2026).
 *
 * "Some of the cards are too busy with plenty text." A card leads with its heading, its
 * figure or chart and one line of reading; the explanation is there for whoever wants it,
 * one click away, never in the way of the figure. Nothing is reworded or removed: the
 * same words, folded. The subtitles, notes and findings the platform writes (panels.py)
 * keep their full text, so Ask, the PDF and the tests read what they always read.
 *
 * What is folded, and to how many lines:
 *   a panel's subtitle and its notes ("thin") ..... one line
 *   a finding's sentence (its heading stays whole) .. one line
 *   the line along the top of a screen (banner) ..... one line
 *   a panel's list of explanations (ul.bul) ......... three lines
 *   a "How This Works" box (.note) .................. its heading only, the list on a click
 * Words that are cut short end in a chevron and open on a click or Enter; words that fit
 * stay plain text. The numbered rows (fold.js) have their own opening and are left alone.
 *
 * Only the screen's own markup is watched (LegacyView's root), as tables.js does: the
 * panels are drawn into it after it is set, and redrawn on each refresh, so each piece is
 * folded as it appears and measured again when its text or its size changes (a tab shown,
 * a window narrowed).
 */

const SPOTS = [
  [".panel > .ph b + span", 1],
  [".panel > .thin", 1, "pad"],
  [".panel > .cover .thin", 1, "pad"],
  [".panel .guide-t", 1],
  [".warn > .warn-t", 1],
  [".view > .banner", 1, "pad"],
  [".panel > ul.bul", 3, "box"],
];
const SKIP = ".fold, .dw, .drawer";

let sizes = null;
const inners = new WeakMap(); // a padded box -> the span its words are folded in

/**
 * A box with padding (a note, a banner) folds its words in a span of their own: folded
 * on the box itself, the next line shows through the padding under the last one. The
 * span is put back whenever the box's text is set again (panels.js sets textContent).
 */
function target(host) {
  if (!inners.has(host)) return host;
  let inner = inners.get(host);
  if (inner.parentElement !== host || host.childNodes.length !== 1) {
    const open = inner.classList.contains("lean-open");
    inner = document.createElement("span");
    inner.className = open ? "lean lean-open" : "lean";
    inner.style.setProperty("--lean", host.style.getPropertyValue("--lean"));
    inner.append(...host.childNodes);
    host.append(inner);
    inners.set(host, inner);
  }
  return inner;
}

/** The words open and close on a click (or Enter) on the words themselves. */
function wire(host) {
  host.addEventListener("click", (e) => {
    if (!host.classList.contains("lean-can")) return;
    if (e.target.closest("a, button, input, select, textarea")) return;
    e.stopPropagation();
    flip(host);
  });
  host.addEventListener("keydown", (e) => {
    if (!host.classList.contains("lean-can") || e.target !== host) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      flip(host);
    }
  });
}

function flip(host) {
  const open = target(host).classList.toggle("lean-open");
  host.setAttribute("aria-expanded", String(open));
  check(host);
}

/**
 * Marks the words as foldable only when they are longer than their lines: a chevron at
 * the end of the first line, the pointer, and a place in the keyboard order. Words that
 * fit stay plain text.
 */
function check(host) {
  const el = target(host);
  const open = el.classList.contains("lean-open");
  const shown = host.offsetParent !== null && el.clientHeight > 0;
  const can = open || (shown && el.scrollHeight > el.clientHeight + 1);
  if (host.classList.contains("lean-can") === can) return;
  host.classList.toggle("lean-can", can);
  if (can) {
    host.tabIndex = 0;
    host.setAttribute("role", "button");
    host.setAttribute("aria-expanded", String(open));
  } else {
    host.removeAttribute("tabindex");
    host.removeAttribute("role");
    host.removeAttribute("aria-expanded");
  }
}

function mark(host, lines, kind) {
  if (host.dataset.lean || host.closest(SKIP)) return;
  host.dataset.lean = kind || "line";
  host.style.setProperty("--lean", lines);
  if (kind === "pad") {
    inners.set(host, document.createElement("span"));
    target(host);
    host.style.setProperty("--lean-pt", getComputedStyle(host).paddingTop);
  } else {
    host.classList.add(kind === "box" ? "lean-box" : "lean");
  }
  wire(host);
  sizes?.observe(host);
  check(host);
}

function noteBox(note) {
  if (note.dataset.lean || note.closest(SKIP)) return;
  const head = note.querySelector(":scope > h4");
  if (!head || !note.querySelector(":scope > ul, :scope > ol, :scope > p")) return;
  note.dataset.lean = "1";
  note.classList.add("lean-note");
  head.tabIndex = 0;
  head.setAttribute("role", "button");
  head.setAttribute("aria-expanded", "false");
  const flip = () => {
    const open = note.classList.toggle("lean-open");
    head.setAttribute("aria-expanded", String(open));
  };
  head.addEventListener("click", flip);
  head.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      flip();
    }
  });
}

function settle(root) {
  if (root.nodeType !== 1) return;
  SPOTS.forEach(([sel, lines, kind]) => {
    if (root.matches(sel)) mark(root, lines, kind);
    root.querySelectorAll(sel).forEach((el) => mark(el, lines, kind));
  });
  if (root.matches(".note")) noteBox(root);
  root.querySelectorAll(".note").forEach(noteBox);
}

/** Folds the long words under root now and as they are drawn. Returns the stop function. */
export function watchLean(root) {
  if (!root || typeof MutationObserver === "undefined") return () => {};
  if (typeof ResizeObserver !== "undefined") {
    sizes = sizes || new ResizeObserver((list) => list.forEach((e) => check(e.target)));
  }
  settle(root);
  const seen = new MutationObserver((list) => {
    const again = new Set();
    list.forEach((m) => {
      m.addedNodes.forEach(settle);
      // Words set on a piece already in place (a refreshed note), or on what holds one.
      const t = m.target.nodeType === 1 ? m.target : m.target.parentElement;
      const host = t?.closest?.("[data-lean]");
      if (host) again.add(host);
    });
    again.forEach(check);
  });
  seen.observe(root, { childList: true, subtree: true, characterData: true });
  return () => {
    seen.disconnect();
    root.querySelectorAll("[data-lean]").forEach((el) => sizes?.unobserve(el));
  };
}
