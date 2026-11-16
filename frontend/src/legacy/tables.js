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
 * A cell is kept on one line when its whole text is a date or a figure; text cells keep
 * wrapping, so a long name or reason stays readable.
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

function oneLine(scope) {
  const cells = scope.matches?.("td") ? [scope] : scope.querySelectorAll?.("td") || [];
  cells.forEach((td) => {
    if (td.classList.contains("dt-nw") || !td.closest("table.dt")) return;
    const text = (td.textContent || "").trim();
    if (text && text.length <= 32 && (DATE.test(text) || FIGURE.test(text))) td.classList.add("dt-nw");
  });
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
