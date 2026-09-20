/**
 * Putting live figures into the designed screens.
 *
 * The designed views are the product. I replaced eight of them with layouts of my own
 * and that was wrong twice over: it threw away work that had been settled over many
 * rounds, and it meant the thing being demonstrated was not the thing that was
 * designed.
 *
 * So nothing is rebuilt. Each designed card is found by its own label, its figure is
 * replaced with the one the KPI engine computes, and the card is wired to open the
 * real records. The markup, spacing, chevron and hairline are exactly as generated.
 *
 * A card with no KPI behind it keeps its designed figure and is marked on the card as
 * illustrative. Mixing real and demonstration figures without saying which is which
 * would make every figure on the screen worth less, and the flag slot already exists
 * in the card contract for exactly this.
 */

import { money, count, exact } from "../format.js";

/**
 * Designed card label -> KPI key, per view.
 *
 * Keyed on the label the designer wrote, so this file is the only place that knows
 * both vocabularies. A label that changes in the generators stops matching here and
 * the card falls back to illustrative rather than showing the wrong figure against
 * the wrong words.
 */
export const CARD_KPIS = {
  sales: {
    "Owed to us": "ar_total",
    "Unpaid invoices": "ar_count",
    "Not despatched": "order_book",
  },
  fin: {
    "Owed to us": "ar_total",
    "Unpaid invoices": "ar_count",
  },
  // Nothing on Buying yet. "Purchase orders" is a count of orders and the nearest
  // figure I have is unpaid supplier invoices; "Spend, top 14" is a subset and
  // spend_total is all of it. Either mapping would have put a figure under a label that
  // does not describe it, which is worse than leaving the card illustrative -- a wrong
  // number that reads as right is the one kind of error this platform cannot afford.
  proc: {},
  inv: {
    "Stock we hold": "stock_value",
    "Reserved, unavail.": "stock_reserved_qty",
    // "Lines promised" means lines with something reserved against them, not every
    // stock line, so stock_lines is not that figure.
  },
  eng: {
    "Money held up": "order_book",
    "Past due date": "order_book_late",
    "Jobs open": "tasks_open",
  },
  hr: {
    // Two different cards, two different figures. Both were mapped to headcount, which
    // would have shown the same number twice under labels that mean different things.
    "On the books": "people_total",
    Active: "headcount",
    Departments: "departments",
  },
  cx: {
    Open: "cases_open",
    // "Past due time" is about the response-time commitment, which this platform does
    // not read. Waiting over a month is a different statement.
  },
};

/** Which views have any live figure at all. Used for the banner wording. */
export function hasLiveFigures(viewKey) {
  return Object.keys(CARD_KPIS[viewKey] || {}).length > 0;
}

export function keysFor(viewKey) {
  return [...new Set(Object.values(CARD_KPIS[viewKey] || {}))];
}

/**
 * Rewrite the figures inside an already-rendered designed view.
 *
 * Returns how many cards were made live, so the caller can say so rather than assert
 * it. Every write is defensive: a card whose markup does not match what is expected is
 * left exactly as designed rather than half-rewritten.
 */
export function hydrateCards(root, viewKey, figures, { onOpen } = {}) {
  const map = CARD_KPIS[viewKey] || {};
  let live = 0;

  root.querySelectorAll(".kpi").forEach((card) => {
    const label = card.querySelector(".lab")?.textContent?.trim();
    if (!label) return;

    const key = map[label];
    const figure = key ? figures?.[key] : null;

    if (!figure) {
      markIllustrative(card);
      return;
    }

    if (writeFigure(card, figure)) {
      live += 1;
      wireOpen(card, figure, onOpen);
    }
  });

  return live;
}

/* ------------------------------------------------------------------------- */

function writeFigure(card, figure) {
  const val = card.querySelector(".val");
  if (!val) return false;

  if (figure.value === null || figure.value === undefined) {
    val.textContent = "—";
  } else if (figure.unit === "currency" && figure.currency) {
    // Rebuilt with the same markup the generator emits: currency first, then the
    // number, then the magnitude. Written as elements rather than a string so nothing
    // from the server is ever parsed as HTML.
    const parts = money(figure.value, figure.currency);
    val.textContent = "";
    val.append(el("span", "cx", parts.currency), document.createTextNode(parts.figure));
    if (parts.suffix) val.append(el("span", "mag", parts.suffix));
  } else if (figure.unit === "percent") {
    val.textContent = "";
    val.append(document.createTextNode(Number(figure.value).toFixed(1)),
               el("span", "cur", "%"));
  } else if (figure.unit === "quantity") {
    const n = Number(figure.value);
    val.textContent = Number.isInteger(n) ? count(n) : exact(n);
  } else {
    val.textContent = count(figure.value);
  }

  const delta = card.querySelector(".delta");
  if (delta && figure.note) delta.textContent = figure.note;

  // Staleness belongs on the card, not in a tooltip: this dataset ends well before
  // today and a figure that does not say so reads as current.
  if (figure.data_status?.state === "stale") {
    setFlag(card, "as at", "f-med");
  } else if (figure.data_status?.state === "failed") {
    setFlag(card, "load failed", "f-crit");
  }

  card.dataset.live = "1";
  card.title = [
    figure.as_of?.date ? `As at ${figure.as_of.date} — ${figure.as_of.basis}.` : "",
    figure.subset_of ? `A subset of ${figure.subset_of}.` : "",
    figure.data_status?.message || "",
    "Opens to the records behind it.",
  ].filter(Boolean).join(" ");

  return true;
}

function wireOpen(card, figure, onOpen) {
  // The generated markup carries an inline onclick to the "not wired yet" explainer.
  // It has to go, or a live card would still open that.
  card.removeAttribute("onclick");
  card.classList.add("clickable");
  if (!onOpen) return;
  card.onclick = () => onOpen(figure);
  card.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onOpen(figure);
    }
  };
  card.setAttribute("role", "button");
  card.setAttribute("tabindex", "0");
}

function markIllustrative(card) {
  if (card.dataset.live === "1") return;
  card.dataset.illustrative = "1";
  setFlag(card, "illustrative", "f-dim");
}

function setFlag(card, text, tone) {
  const head = card.querySelector(".khead");
  if (!head) return;
  let flag = head.querySelector(".flag");
  if (!flag) {
    flag = el("span", `flag ${tone}`, text);
    head.append(flag);
    return;
  }
  // A designed flag that says something already is left alone: it is part of the
  // design and may be saying something this does not know about.
  if (!flag.textContent.trim()) {
    flag.className = `flag ${tone}`;
    flag.textContent = text;
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
