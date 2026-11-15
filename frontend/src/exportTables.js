/**
 * The tables on a part of the page, as data for an Excel export.
 *
 * Read from what is rendered, so the sheet has exactly the figures the manager is
 * looking at -- hydrated values included -- in the same order and with the same
 * headings. Each table is named after the panel or heading it sits under.
 *
 * Every row, not only the page showing: an answer's long table shows ten rows at a
 * time (legacy/markdown.js enhanceTable) by hiding the others, and they are still read
 * here -- in the order the manager has sorted them.
 */
export function tablesFrom(root) {
  if (!root) return [];
  // Every tab's tables, not only the one showing: "the screen's tables" should not
  // depend on which tab happened to be open.
  return Array.from(root.querySelectorAll("table.dt"))
    .map((t, i) => ({
      name: titleFor(t) || `Table ${i + 1}`,
      columns: Array.from(t.querySelectorAll("thead th")).map(clean),
      rows: Array.from(t.querySelectorAll("tbody tr")).map((tr) => // hidden rows included
        Array.from(tr.querySelectorAll("td")).map(clean)),
    }))
    .filter((t) => t.rows.length);
}

function titleFor(table) {
  const panel = table.closest(".panel");
  const head = panel?.querySelector(".ph b");
  if (head) return head.textContent.trim();
  let el = table.closest(".md-table") || table;
  while ((el = el.previousElementSibling)) {
    if (/^H[1-6]$/.test(el.tagName)) return el.textContent.trim();
  }
  return "";
}

function clean(cell) {
  return (cell.textContent || "").replace(/\s+/g, " ").replace(/\s*↗$/, "").trim();
}
