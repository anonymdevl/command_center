import React from "react";

/**
 * A table of records.
 *
 * `columns` entries: { key, label, align, render }. Values are rendered as text
 * by React, which escapes them -- the reason the port is worth doing. The vanilla
 * build assembled rows with innerHTML, so a customer name containing a tag would
 * have executed once these tables started showing real data.
 */
export default function DataTable({ columns, rows, empty = "Nothing to show.", onRowClick }) {
  if (!rows || rows.length === 0) {
    return <div className="thin">{empty}</div>;
  }
  return (
    <table className="dt">
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} style={c.align === "right" ? { textAlign: "right" } : undefined}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr
            key={row.__key || i}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            style={onRowClick ? { cursor: "pointer" } : undefined}
          >
            {columns.map((c) => (
              <td key={c.key} className={c.align === "right" ? "num" : undefined}>
                {c.render ? c.render(row) : row[c.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
