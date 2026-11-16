/**
 * Every data table on the designed screens scrolls sideways inside its own box, never
 * the page (16 Nov 2026).
 *
 * Headers no longer wrap ("On Open Invoices / GHS" on two lines on Sales and Payments),
 * and money and dates stay on one line, so a wide table is wider than its panel. Some
 * tables were already in a scroll box (.dt-scroll, the statements' .fs-wrap, the chart's
 * table view); the rest -- drawn in the markup or by panels.js, people.js, work.js,
 * cover.js, loads.js -- are put in one here, as they appear.
 *
 * Only the screen's own markup is watched (LegacyView's root, set by innerHTML). Tables
 * React draws are never moved: React would lose track of them.
 *
 * A cell is kept on one line when its whole text is a date or a figure. A text cell keeps
 * wrapping, but never down to a word a line (16 Nov 2026: with ten figure columns that
 * could no longer shrink, Finances' "Why" column was squeezed to one word wide and one
 * row filled the page). By the length of its text it gets a floor and a ceiling of
 * width (shell.py, "TABLE TEXT"): a short name a little, a sentence a comfortable
 * measure, a long explanation no more than three lines, the rest of it ended with an
 * ellipsis and the whole of it in the cell's title (and, where the row opens, there).
 * The table may then be wider than its panel; it scrolls in its own box, never the page.
 */

const BOXED = ".dt-scroll, .dt-x, .fs-wrap, .dw-tbox, .vz-table, .scrollbox, .work-table";
const DATE = /^(\d{1,2} [A-Z][a-z]{2}( \d{4})?|[A-Z][a-z]{2} \d{4}|\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?)$/;
const FIGURE = /^([A-Z]{3} ?)?[−(+-]?[\d,]+(\.\d+)?\)?( ?(%|[kKMB]|pts|days?))?$/;

function box(table) {
  const parent = table.parentElement;
  if (!parent || parent.matches(BOXED)) return;
  const ox = getComputedStyle(parent).overflowX;
  if (ox === "auto" || ox === "scroll") return;
  const wrap = document.createElement("div");
  wrap.className = "dt-x";
  parent.insertBefore(wrap, table);
  wrap.append(table);
}

// Text length bands (characters) and the width class each gets: dt-w1 a short name, a
// little floor; dt-w2 a phrase or sentence, a floor and a ceiling; dt-w3 an explanation,
// a wider floor and ceiling, and at most three lines.
const BANDS = [[60, "dt-w3"], [24, "dt-w2"], [12, "dt-w1"]];
const WIDTHS = BANDS.map(([, c]) => c);

function fit(td) {
  if (td.classList.contains("dt-nw") || !td.closest("table.dt")) return;
  const text = (td.textContent || "").trim();
  if (!text) return;
  if (text.length <= 32 && (DATE.test(text) || FIGURE.test(text))) {
    td.classList.add("dt-nw");
    return;
  }
  // Figures, a row across the whole table, and a cell already cut to one line with its
  // whole text in its title (shell.py) keep their own layout.
  if (td.classList.contains("num") || td.classList.contains("n") || td.colSpan > 1) return;
  if (td.hasAttribute("title") && !td.querySelector(":scope > .dt-tx")) return;
  const band = (BANDS.find(([n]) => text.length > n) || [])[1];
  WIDTHS.forEach((c) => td.classList.toggle(c, c === band));
  if (!band) return;
  // A cell of plain text carries its words in one block, which holds the width (a
  // table cell's own max-width is not honoured) and is clamped to three lines.
  const kids = [...td.childNodes];
  if (kids.length && kids.every((n) => n.nodeType === 3)) {
    const tx = document.createElement("span");
    tx.className = "dt-tx";
    tx.textContent = text;
    td.textContent = "";
    td.append(tx);
  }
  const tx = td.querySelector(":scope > .dt-tx");
  if (tx && band === "dt-w3") tx.title = text;
}

function oneLine(scope) {
  const cells = scope.matches?.("td") ? [scope] : scope.querySelectorAll?.("td") || [];
  cells.forEach(fit);
}

function settle(node) {
  if (node.nodeType !== 1) return;
  if (node.matches("table.dt")) box(node);
  else node.querySelectorAll("table.dt").forEach(box);
  oneLine(node);
}

/** Boxes every table under root now and as it is drawn. Returns the stop function. */
export function watchTables(root) {
  if (!root || typeof MutationObserver === "undefined") return () => {};
  settle(root);
  const seen = new MutationObserver((list) => {
    list.forEach((m) => {
      m.addedNodes.forEach(settle);
      // A cell whose text is set after it is in place (textContent on a live td).
      if (m.target.nodeType === 1 && m.target.matches("td")) oneLine(m.target);
    });
  });
  seen.observe(root, { childList: true, subtree: true });
  return () => seen.disconnect();
}
