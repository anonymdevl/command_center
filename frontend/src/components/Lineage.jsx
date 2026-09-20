import React from "react";
import { api } from "../api/client.js";
import { useApi } from "../useApi.js";
import DataTable from "./DataTable.jsx";
import { Loading, Failed, Empty } from "./States.jsx";

/**
 * Which records produced a figure.
 *
 * One component for every screen. It lived inside Sales while Sales was the only
 * converted view; leaving it there would have meant a second copy the first time
 * another screen needed to open a figure, and the two would have drifted the way
 * kpi() did.
 *
 * Not a separate feature either: every fact row carries the ERPNext document it
 * came from, so this is the same rows selected back. That is why lineage is in
 * the schema rather than bolted onto each screen.
 */

/** What identifies a record, per fact. The invoice column is not called the same thing everywhere. */
const COLUMNS = {
  fact_sales_invoice: [
    { key: "src_name", label: "Invoice" },
    { key: "src_doctype", label: "From" },
  ],
  fact_sales_invoice_line: [
    { key: "src_name", label: "Invoice" },
    { key: "src_row_name", label: "Line" },
  ],
  fact_payment_allocation: [
    { key: "src_name", label: "Payment" },
    { key: "src_doctype", label: "From" },
  ],
};

export default function Lineage({ scope, title, fact, filters, subset }) {
  const { data, error, loading, reload } = useApi(
    () => api.lineage({ fact, filters, business_code: scope, limit: 100 }),
    [scope, fact, JSON.stringify(filters)]
  );

  const columns = [
    ...(COLUMNS[fact] || COLUMNS.fact_sales_invoice),
    {
      key: "src_modified",
      label: "Last changed",
      render: (r) => String(r.src_modified || "").slice(0, 10),
    },
  ];

  return (
    <>
      <div className="dhead">
        <div>
          <div className="dt">The records behind it</div>
          <h4>{title}</h4>
          {subset ? <div className="when">a subset of {subset}</div> : null}
        </div>
      </div>

      {loading ? <Loading what="Finding the records" /> : null}
      {error ? <Failed error={error} onRetry={reload} what="the records" /> : null}

      {data && data.length === 0 ? (
        <Empty>No records match this figure.</Empty>
      ) : null}

      {data && data.length > 0 ? (
        <>
          <DataTable rows={data.map((r, i) => ({ __key: `${r.src_name}-${i}`, ...r }))} columns={columns} />
          <div className="drfoot">
            Showing {data.length} of them. Every row names the ERPNext document it came
            from, so any figure on this screen can be taken back to its records.
          </div>
        </>
      ) : null}
    </>
  );
}
