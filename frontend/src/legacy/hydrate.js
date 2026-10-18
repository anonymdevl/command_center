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
 *
 * Two kinds of thing carry a figure: the `.kpi` cards and the `.bk` tiles. Both are
 * hydrated here, by the same rules and through the same figure renderer, because a tile
 * that could never be made live was thirty-four figures the platform could not stand
 * behind.
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

/**
 * Designed tile label -> KPI, per view.
 *
 * Tiles are the other half of the interface and had no hydration at all: this file
 * matched `.kpi` only, so all thirty-four `.bk` tiles across six screens showed their
 * designed figures with no way to make any of them live. That is the gap this map and
 * hydrateTiles close.
 *
 * A tile is not a card. Its figure carries its own unit word inside the number
 * (`31 <small>projects</small>`), its label sits in `.l` rather than `.lab`, and its
 * footnote is `.v` rather than `.delta`. So the value here is an object: the KPI key,
 * and the unit word to print beside a count. A currency figure needs no unit word --
 * the currency is the unit -- so it has none.
 *
 * Only Business Overview can be served from facts today. The tiles on Today and
 * Outstanding Tasks measure work handed out and promises kept, which is the task and
 * approval engine and not a fact; Risk and Compliance measures deadlines this platform
 * does not yet hold; Business Health's tiles are scores out of a hundred, which is a
 * composite and not any single KPI; and the six "Awaiting ..." tiles on Sales are
 * mutually exclusive pipeline stages, so mapping one of them to the whole order book
 * would count orders waiting on stock as orders waiting on despatch. Each of those is
 * a mapping that would read as right and be wrong, so each stays illustrative and says
 * so on the tile.
 */
export const TILE_KPIS = {
  ops: {
    "Sales & money owed": { key: "ar_total" },
    "Buying & suppliers": { key: "ap_total" },
    "Stock & warehouses": { key: "stock_value" },
    "Engineering & installs": { key: "tasks_open", unit: "tasks" },
    "Customer Service & Issues": { key: "cases_open", unit: "open cases" },
    People: { key: "people_total", unit: "employees" },
    // "Money in & out" is 7,751 payment entries plus 7,065 journals on the site. The
    // facts hold neither count, and cash_applied is money in only, so a figure under
    // that label would be half of what the label says. Illustrative.
    // "Systems & access" and "Internal Audit" say on themselves that ERPNext holds no
    // record of either; both are flagged "Not yet" as designed.
  },
  myday: {},
  delegation: {},
  risk: {},
  health: {},
  sales: {},
};

/** Which views have any live figure at all. Used for the banner wording. */
export function hasLiveFigures(viewKey) {
  return keysFor(viewKey).length > 0;
}

export function keysFor(viewKey) {
  const cards = Object.values(CARD_KPIS[viewKey] || {});
  const tiles = Object.values(TILE_KPIS[viewKey] || {}).map((spec) => spec.key);
  return [...new Set([...cards, ...tiles])];
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

/**
 * The same, for the designed tiles.
 *
 * A tile that navigates keeps navigating. The generated markup carries either
 * `go('sales')`, which is real behaviour the screen promises ("open any one of them"),
 * or `explain('unwired')`, which is a placeholder. Only the placeholder is replaced, so
 * hydrating Business Overview does not cost it its navigation.
 */
export function hydrateTiles(root, viewKey, figures, { onOpen } = {}) {
  const map = TILE_KPIS[viewKey] || {};
  let live = 0;

  root.querySelectorAll(".bk").forEach((tile) => {
    const label = tile.querySelector(".l")?.textContent?.trim();
    const spec = label ? map[label] : null;
    const figure = spec ? figures?.[spec.key] : null;

    if (!figure) {
      markIllustrative(tile);
      return;
    }

    if (writeTileFigure(tile, figure, spec.unit)) {
      live += 1;
      if (!navigates(tile)) wireOpen(tile, figure, onOpen);
    }
  });

  return live;
}

/* ------------------------------------------------------------------------- */

function writeFigure(card, figure) {
  const val = card.querySelector(".val");
  if (!val) return false;

  renderFigure(val, figure, null);

  const delta = card.querySelector(".delta");
  if (delta && figure.note) delta.textContent = figure.note;

  provenance(card, figure);
  card.dataset.live = "1";
  card.title = titleFor(figure, "Opens to the records behind it.");

  return true;
}

function writeTileFigure(tile, figure, unit) {
  const n = tile.querySelector(".n");
  if (!n) return false;

  // The designed colour was chosen for the designed number: red for four broken
  // promises. It cannot be carried over to a figure that may be nothing of the kind.
  n.removeAttribute("style");
  renderFigure(n, figure, unit);

  // The footnote becomes the KPI's note when the designed one carries a figure of its
  // own, because a number typed into prose drifts the moment the data is reloaded --
  // "GHS 9.18M owed, 74% over 3 months" was true of one extract and silently wrong
  // after the next. A footnote with no figure in it is a statement about the business
  // ("Payroll shown as status only, names hidden", "Seeded for the demonstration") and
  // is left exactly as designed, because that is not what a KPI note is for.
  const v = tile.querySelector(".v");
  if (v && figure.note && /\d/.test(v.textContent || "")) v.textContent = figure.note;

  provenance(tile, figure);
  tile.dataset.live = "1";
  tile.title = titleFor(
    figure,
    navigates(tile) ? "" : "Opens to the records behind it.");

  return true;
}

/** Writes one figure into one slot. Cards and tiles differ in the slot, not the value. */
function renderFigure(target, figure, unit) {
  if (figure.value === null || figure.value === undefined) {
    target.textContent = "—";
    return;
  }

  if (figure.unit === "currency" && figure.currency) {
    // Rebuilt with the same markup the generator emits: currency first, then the
    // number, then the magnitude. Written as elements rather than a string so nothing
    // from the server is ever parsed as HTML.
    const parts = money(figure.value, figure.currency);
    target.textContent = "";
    target.append(el("span", "cx", parts.currency), document.createTextNode(parts.figure));
    if (parts.suffix) target.append(el("span", "mag", parts.suffix));
    return;
  }

  if (figure.unit === "percent") {
    target.textContent = "";
    target.append(document.createTextNode(Number(figure.value).toFixed(1)),
                  el("span", "cur", "%"));
    return;
  }

  if (figure.unit === "quantity") {
    const q = Number(figure.value);
    target.textContent = Number.isInteger(q) ? count(q) : exact(q);
  } else {
    target.textContent = count(figure.value);
  }

  // A count on a tile says what it counts, inside the figure, exactly as designed.
  if (unit) target.append(el("small", null, unit));
}

/**
 * Staleness belongs on the face of the card, not in a tooltip: this dataset ends well
 * before today, and a figure that does not say so reads as current.
 */
function provenance(node, figure) {
  const state = figure.data_status?.state;
  if (state === "stale") setFlag(node, "as at", "f-med");
  else if (state === "failed") setFlag(node, "load failed", "f-crit");
  else clearFlag(node);
  delete node.dataset.illustrative;
}

function titleFor(figure, closing) {
  return [
    figure.as_of?.date ? `As at ${figure.as_of.date} — ${figure.as_of.basis}.` : "",
    figure.subset_of ? `A subset of ${figure.subset_of}.` : "",
    figure.data_status?.message || "",
    closing,
  ].filter(Boolean).join(" ");
}

function navigates(tile) {
  return /(^|[^\w.])go\(/.test(tile.getAttribute("onclick") || "");
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

function markIllustrative(node) {
  if (node.dataset.live === "1") return;
  node.dataset.illustrative = "1";
  setFlag(node, "illustrative", "f-dim");
}

/**
 * The flag slot.
 *
 * A card has one designed into its khead for exactly this. A tile has none -- and on
 * Business Overview the flag it does carry is saying something about the domain ("Live
 * data", "Seeded", "Not yet"), which is a different statement from this one about the
 * figure. So a tile gets its own pill as a direct child, below the footnote, and the
 * designed flag is never touched.
 *
 * Every pill this file writes is marked, so it can be taken back when the figure it
 * described is replaced: a tile marked illustrative before the figures arrived must not
 * still say so once they have.
 */
function setFlag(node, text, tone) {
  if (node.classList.contains("bk")) {
    const pill = node.querySelector(":scope > .flag[data-prov]");
    if (pill) {
      pill.className = `flag ${tone}`;
      pill.textContent = text;
      return;
    }
    node.append(ownFlag(tone, text));
    return;
  }

  const head = node.querySelector(".khead");
  if (!head) return;
  const flag = head.querySelector(".flag");
  if (!flag) {
    head.append(ownFlag(tone, text));
    return;
  }
  // A designed flag that says something already is left alone: it is part of the
  // design and may be saying something this does not know about.
  if (!flag.textContent.trim() || flag.dataset.prov === "1") {
    flag.className = `flag ${tone}`;
    flag.textContent = text;
    flag.dataset.prov = "1";
  }
}

/** A figure that is live and current says nothing extra, so any pill of ours goes. */
function clearFlag(node) {
  const pill = node.classList.contains("bk")
    ? node.querySelector(":scope > .flag[data-prov]")
    : node.querySelector(".khead .flag[data-prov]");
  if (pill) pill.remove();
}

function ownFlag(tone, text) {
  const pill = el("span", `flag ${tone}`, text);
  pill.dataset.prov = "1";
  return pill;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
