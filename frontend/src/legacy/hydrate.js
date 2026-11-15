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

import { guideCard } from "./guide.js";
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
  // Home. "Money in, month" read GHS 0 because it was a month measured from today on a
  // dataset that ends in 2025; it is now the last full month the data covers, named.
  command: {
    "Money in, month": "cash_in_month",
    "Owed to us": "ar_total",
    "Days to get paid": "days_to_pay",
    Waiting: "order_book_count",
    "Past due": "order_book_late",
    "Stock we hold": "stock_value",
  },
  sales: {
    "Owed to us": "ar_total",
    "Unpaid invoices": "ar_count",
    "Not despatched": "order_book",
    "Last full month": "revenue_last_month",
    "Best month": "revenue_best_month",
    "Never issued": "invoices_draft",
  },
  fin: {
    "Owed to us": "ar_total",
    "Unpaid invoices": "ar_count",
    "Last full month": "revenue_last_month",
    "Best month": "revenue_best_month",
    "Never issued": "invoices_draft",
    // Bank payments carrying the clearance date ERPNext's bank reconciliation sets.
    "Bank checks": "bank_cleared_pct",
  },
  // The two concentration cards are shares of all submitted supplier spend, which is
  // what their labels say. "Spend, top 14" is the fourteen largest purchase orders
  // themselves (read live, the same fourteen "Where the money goes" draws), never
  // spend_total, which is all of it.
  proc: {
    "Top supplier": "supplier_top_share",
    "Top 2 suppliers": "supplier_top2_share",
    // Read straight from ERPNext's purchase orders (kpi/live.py): no fact loads them yet.
    "Purchase orders": "po_count",
    "Longest wait": "po_longest_wait",
    "Spend, top 14": "po_spend_top14",
    // Submitted orders with no promised date, or one equal to the order date.
    "No due date": "po_no_due_date",
  },
  // Systems and Access: the accounts and roles themselves, read from ERPNext.
  it: {
    "Staff accounts": "users_active",
    "Role conflicts": "users_role_conflicts",
    "5 manager roles": "users_manager_roles",
    Departments: "departments_erp",
    Disabled: "users_disabled",
    "Last refreshed": "last_refreshed",
  },
  inv: {
    "Stock we hold": "stock_value",
    "Reserved, unavail.": "stock_reserved_qty",
    // "Lines promised" means lines with something reserved against them, not every
    // stock line, so stock_lines is not that figure -- stock_lines_promised is.
    "Lines promised": "stock_lines_promised",
    "Worst shortfall": "stock_worst_shortfall",
    // Batches holding stock that expire within ninety days; "—" when no batch carries
    // an expiry date at all, which is a different statement from none expiring.
    // "Off warehouse" stays illustrative: which location is "not a warehouse" is a
    // judgement about one business's set-up, not something ERPNext records.
    "Near expiry": "batches_near_expiry",
  },
  eng: {
    "Money held up": "order_book",
    "Past due date": "order_book_late",
    "Jobs open": "tasks_open",
    "Longest wait": "tasks_longest_wait",
    Engineers: "engineers",
    // Open jobs with hours, expenses or project costs booked against them.
    "Jobs costed": "tasks_costed",
  },
  hr: {
    // Two different cards, two different figures. Both were mapped to headcount, which
    // would have shown the same number twice under labels that mean different things.
    "On the books": "people_total",
    Active: "headcount",
    Departments: "departments",
    Left: "people_left",
    Engineers: "engineers",
    // When pay was last run, from submitted salary slips: dates and a count, no amounts.
    Payroll: "payroll_last_run",
  },
  cx: {
    Open: "cases_open",
    Closed: "cases_closed",
    "Average wait": "cases_avg_wait",
    // Against the resolution time each case's service level promised, read live --
    // never "waiting over a month", which is a different statement.
    "Past due time": "cases_past_due",
    // Open cases matched against the loaded receivable by customer.
    "Also owe us": "cases_owing",
    // "Equipment down" stays illustrative: ERPNext's Issue has no field saying a
    // machine is out of service, and guessing it from the subject would be wrong.
  },
  aud: {
    // "Unsupported" on Internal Audit is the invoices never issued, as its footnote says.
    Unsupported: "invoices_draft",
    // The change log and the purchase orders, read from ERPNext (kpi/live.py).
    "Changes logged": "versions_total",
    "On business docs": "versions_business",
    "Earliest entry": "versions_earliest",
    Unsubmitted: "po_drafts_value",
    "Oldest of those": "po_drafts_oldest",
    Withdrawn: "po_cancelled",
    // Purchase orders and payments whose every recorded approval step was taken by the
    // account that raised them, from the change log.
    "Self-approved": "self_approved",
    // Findings and corrective actions are ERPNext's own Non Conformance and Quality
    // Action (kpi/live_governance.py); until any are recorded each card is a guide.
    "Open findings": "findings_open",
    "Repeat findings": "findings_repeat",
    "Overdue actions": "actions_overdue",
    // What would be raised today: the open alerts, the same list Business Health shows.
    "Raise today": "alerts_open",
    // The average of the Business Health questions scored, as Home's gauge.
    "Control score": "control_score",
    // The roles ERPNext's own permission rules let delete a change-log entry.
    "Can be deleted": "versions_deletable",
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
 * Today and Outstanding Tasks take their tiles from the manager's own queue
 * (legacy/work.js WORK_TILES); Business Health's six questions are drawn by
 * legacy/home.js; every other tile on the management screens is mapped here, and a
 * tile whose figure cannot be read shows a dash and says why (legacy/core.js).
 */
export const TILE_KPIS = {
  ops: {
    "Sales & money owed": { key: "ar_total" },
    "Buying & suppliers": { key: "ap_total" },
    "Stock & warehouses": { key: "stock_value" },
    "Engineering & installs": { key: "tasks_open", unit: "tasks" },
    "Customer Service & Issues": { key: "cases_open", unit: "open cases" },
    People: { key: "people_total", unit: "employees" },
    // Payment entries plus journals, counted live: the facts hold neither, and
    // cash_applied is money in only, so it would be half of what the label says.
    "Money in & out": { key: "postings_count", unit: "postings" },
    // The active ERPNext accounts, and the open alerts Internal Audit would raise.
    "Systems & access": { key: "users_active", unit: "accounts" },
    "Internal Audit": { key: "alerts_open", unit: "open alerts" },
  },
  // Home's three hero tiles (the approved mockup's layout, 18 Oct 2026).
  command: {
    "Sales & money owed": { key: "ar_total" },
    "Buying & suppliers": { key: "ap_total" },
    "Stock & warehouses": { key: "stock_value" },
  },
  // Today and Outstanding Tasks: legacy/work.js WORK_TILES, from the manager's own queue.
  myday: {},
  delegation: {},
  // Deadlines are Contracts that require fulfilment (kpi/live_governance.py), counted by
  // how soon they fall due; Findings are open Non Conformance records; Going wrong is
  // the open alerts Business Health lists.
  risk: {
    Overdue: { key: "deadlines_overdue" },
    "Within 1 month": { key: "deadlines_month" },
    "Within 3 months": { key: "deadlines_quarter" },
    Findings: { key: "findings_open" },
    "Going wrong": { key: "alerts_open" },
  },
  // Three of the six questions are now one stated ratio each (kpi score_*); legacy/
  // home.js draws their score, bar and flag. The other three still need a source.
  health: {},
  // Where orders are held up. The stages overlap (an order not despatched is usually
  // not invoiced either), so each box is its own count over open orders. Awaiting stock
  // and Awaiting purchase need each order line against its warehouse and what is on
  // order from suppliers, and the design does not say where one ends and the other
  // begins; Awaiting install has no ERPNext record behind it; Awaiting payment needs
  // invoices traced back to their orders, which no fact holds. Those four stay
  // illustrative.
  sales: {
    "Awaiting despatch": { key: "order_awaiting_despatch" },
    "Awaiting invoice": { key: "order_awaiting_invoice" },
  },
};

/**
 * While the figures are on their way, the cards that will receive one show a quiet
 * placeholder instead of their designed figure: a sample value that flashes and then
 * changes reads as the number being wrong. Cards with no KPI behind them are left as
 * designed (they will be marked illustrative). writeFigure clears the mark.
 */
export function markLoading(root, viewKey, on) {
  if (!root) return;
  const cards = CARD_KPIS[viewKey] || {};
  const tiles = TILE_KPIS[viewKey] || {};
  root.querySelectorAll(".kpi").forEach((card) => {
    const label = card.querySelector(".lab")?.textContent?.trim();
    if (label && cards[label] && card.dataset.live !== "1") toggle(card, on);
  });
  root.querySelectorAll(".bk").forEach((tile) => {
    const label = tile.querySelector(".l")?.textContent?.trim();
    if (label && tiles[label] && tile.dataset.live !== "1") toggle(tile, on);
  });
}

function toggle(node, on) {
  if (on) node.dataset.loading = "1";
  else delete node.dataset.loading;
}

/** Which views have any live figure at all. Used for the banner wording. */
export function hasLiveFigures(viewKey) {
  return keysFor(viewKey).length > 0;
}

/** Figures a screen needs beyond its cards and tiles: Home's counts and health gauge,
 *  and Business Health's three scored questions (legacy/home.js draws both). */
export const EXTRA_KPIS = {
  command: ["cases_open", "tasks_overdue", "score_paid", "score_deliver", "score_paperwork",
            "score_approvals", "score_records", "score_access", "control_score"],
  health: ["score_paid", "score_deliver", "score_paperwork", "score_approvals", "score_records",
           "score_access", "control_score"],
};

export function keysFor(viewKey) {
  const cards = Object.values(CARD_KPIS[viewKey] || {});
  const tiles = Object.values(TILE_KPIS[viewKey] || {}).map((spec) => spec.key);
  return [...new Set([...cards, ...tiles, ...(EXTRA_KPIS[viewKey] || [])])];
}

/**
 * Rewrite the figures inside an already-rendered designed view.
 *
 * Returns how many cards were made live, so the caller can say so rather than assert
 * it. Every write is defensive: a card whose markup does not match what is expected is
 * left exactly as designed rather than half-rewritten.
 */
export function hydrateCards(root, viewKey, figures, { onOpen, openDrawer } = {}) {
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
    // Nothing recorded in ERPNext yet: the card says how to set it up (guides.py).
    if (figure.data_status?.state === "needs_setup" && figure.data_status.guide) {
      guideCard(card, figure.data_status.guide, openDrawer);
      live += 1;
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
export function hydrateTiles(root, viewKey, figures, { onOpen, openDrawer } = {}, map = TILE_KPIS[viewKey] || {}) {
  // `map` is TILE_KPIS by default; Today and Outstanding Tasks pass legacy/work.js's,
  // whose figures come from the work queue rather than the KPI engine.
  let live = 0;

  root.querySelectorAll(".bk").forEach((tile) => {
    const label = tile.querySelector(".l")?.textContent?.trim();
    const spec = label ? map[label] : null;
    const figure = spec ? figures?.[spec.key] : null;

    if (!figure) {
      markIllustrative(tile);
      return;
    }
    if (figure.data_status?.state === "needs_setup" && figure.data_status.guide) {
      if (!navigates(tile)) guideCard(tile, figure.data_status.guide, openDrawer);
      live += 1;
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
  delete card.dataset.loading;
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
  delete tile.dataset.loading;
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

  if (figure.unit === "date") {
    // "5 Feb" with the year beside it, as the designed card wrote it.
    const d = new Date(`${String(figure.value).slice(0, 10)}T00:00`);
    target.textContent = d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    target.append(document.createTextNode(" "), el("span", "cur", String(d.getFullYear())));
    return;
  }

  if (figure.unit === "time") {
    const d = new Date(String(figure.value).replace(" ", "T"));
    target.textContent = Number.isNaN(d.getTime()) ? String(figure.value)
      : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    return;
  }

  if (figure.unit === "days") {
    // Whole days, with the unit the designed card wrote beside it.
    target.textContent = count(Math.round(Number(figure.value)));
    target.append(document.createTextNode(" "), el("span", "cur", "days"));
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
  // Quiet: it is on nearly every card, so it must not shout like a status does.
  if (state === "stale") setFlag(node, "as at", "f-asat");
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
