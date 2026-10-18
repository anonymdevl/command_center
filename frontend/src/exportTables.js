/**
 * The tables on a part of the page, as data for an Excel export.
 *
 * Read from what is rendered, so the sheet has exactly the figures the manager is
 * looking at -- hydrated values included -- in the same order and with the same
 * headings. Each table is named after the panel or heading it sits under.
 */
export function tablesFrom(root) {
  if (!root) return [];
  // Every tab's tables, not only the one showing: "the screen's tables" should not
  // depend on which tab happened to be open.
  return Array.from(root.querySelectorAll("table.dt"))
    .map((t, i) => ({
      name: titleFor(t) || `Table ${i + 1}`,
      columns: Array.from(t.querySelectorAll("thead th")).map(clean),
      rows: Array.from(t.querySelectorAll("tbody tr")).map((tr) =>
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
