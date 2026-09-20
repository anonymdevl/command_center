import React from "react";
import { api } from "../api/client.js";
import { useApi } from "../useApi.js";
import DataTable from "./DataTable.jsx";
import { Loading, Failed, Empty } from "./States.jsx";
import { exact, count, shortDate } from "../format.js";

/**
 * What is behind a figure, as something to decide on.
 *
 * This replaces the lineage drawer, which listed an invoice code, an internal row
 * id and a timestamp. That proved the figure traced back to a document -- the
 * engineering requirement -- and told a manager nothing. Opening "Invoiced revenue"
 * and finding a hundred rows of codes is worse than not offering the drawer at all,
 * because it looks like the answer and is not.
 *
 * Three things, in the order a decision needs them:
 *
 *   The sentence.  What these records add up to, and where the weight sits. "The
 *                  five largest are 62% of it" is what changes what someone does
 *                  next; a hundred rows never says it.
 *   The weight.    Those five, with their share, each openable in its own right.
 *   The records.   Largest first, in business columns, each opening the actual
 *                  document in ERPNext.
 */
export default function Records({ scope, title, fact, filters, subset, openDrawer }) {
  const { data, error, loading, reload } = useApi(
    () => api.records({ fact, filters, business_code: scope, limit: 100 }),
    [scope, fact, JSON.stringify(filters)]
  );

  return (
    <>
      <div className="dhead">
        <div>
          <div className="dt">What is behind it</div>
          <h4>{title}</h4>
          {subset ? <div className="when">a subset of {subset}</div> : null}
        </div>
      </div>

      {loading ? <Loading what="Reading the records" /> : null}
      {error ? <Failed error={error} onRetry={reload} what="the records" /> : null}

      {data && data.summary.count === 0 ? (
        <Empty>Nothing matches this figure.</Empty>
      ) : null}

      {data && data.summary.count > 0 ? (
        <>
          <Headline data={data} />
          <Concentration data={data} scope={scope} filters={filters} openDrawer={openDrawer} />
          <Table data={data} />
        </>
      ) : null}
    </>
  );
}

/* ------------------------------------------------------------------------- */

/** The sentence. Read off the whole set, not the page being shown. */
function Headline({ data }) {
  const s = data.summary;
  const money = `${data.currency || ""} ${exact(s.total)}`.trim();
  const plural = s.count === 1 ? data.noun : `${data.noun}s`;

  return (
    <div className="dsum">
      <div className="dsum-n">{money}</div>
      <div className="dsum-t">
        {count(s.count)} {plural} of {s.measure_word}
        {s.top_share != null ? (
          <>
            {" · "}
            <b>{s.top_share}%</b> of it sits with {s.concentration.length}{" "}
            {s.concentration.length === 1 ? s.dimension_word : `${s.dimension_word}s`}
          </>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Where the weight sits.
 *
 * Each row is openable, so "who are those five" is one click rather than a question
 * the manager has to take somewhere else.
 */
function Concentration({ data, scope, filters, openDrawer }) {
  const s = data.summary;
  if (!s.concentration.length) return null;

  const dimension = DIMENSION_FIELD[data.fact];

  return (
    <div className="panel" style={{ margin: "0 0 14px" }}>
      <div className="ph">
        <div>
          <b>Where it is concentrated</b>
          <span>largest {s.dimension_word}s first</span>
        </div>
      </div>
      <DataTable
        columns={[
          { key: "label", label: s.dimension_word.replace(/^./, (c) => c.toUpperCase()) },
          { key: "value", label: data.currency || "Amount", align: "right",
            render: (r) => exact(r.value) },
          { key: "share", label: "Share", align: "right",
            render: (r) => (r.share == null ? "—" : `${r.share}%`) },
          { key: "count", label: "Records", align: "right", render: (r) => count(r.count) },
        ]}
        rows={s.concentration.map((c) => ({ __key: c.label, ...c }))}
        onRowClick={
          dimension && openDrawer
            ? (r) =>
                openDrawer(
                  <Records
                    scope={scope}
                    fact={data.fact}
                    filters={{ ...(filters || {}), [dimension]: r.label }}
                    title={r.label}
                    openDrawer={openDrawer}
                  />
                )
            : undefined
        }
      />
    </div>
  );
}

/** Which field the concentration groups by, so clicking one can filter to it. */
const DIMENSION_FIELD = {
  fact_sales_invoice: "customer",
  fact_sales_invoice_line: "customer",
  fact_payment_allocation: "party",
};

/** The records. Columns and their order are the server's, so every drawer agrees. */
function Table({ data }) {
  const columns = data.columns.map((c) => ({
    key: c.key,
    label: c.label,
    align: c.type === "text" || c.type === "doc" ? undefined : "right",
    render: (row) => cell(row, c, data),
  }));

  return (
    <>
      <DataTable
        columns={columns}
        rows={data.rows.map((r, i) => ({ __key: `${r.src_name}-${i}`, ...r }))}
      />
      <div className="drfoot">
        The {count(data.summary.shown)} largest of {count(data.summary.count)}. Each row
        opens the document in ERPNext, where the full history, attachments and
        comments live — this platform reports on it rather than replacing it.
      </div>
    </>
  );
}

/** One cell, formatted by the type the server declared. */
function cell(row, column, data) {
  const v = row[column.key];

  if (column.type === "doc") {
    return row.open_url ? (
      <a
        className="dlink"
        href={row.open_url}
        target="_blank"
        rel="noreferrer"
        onClick={(e) => e.stopPropagation()}
        title={`Open ${row.src_doctype} ${row.src_name} in ERPNext`}
      >
        {v} ↗
      </a>
    ) : (
      v || "—"
    );
  }

  if (v === null || v === undefined || v === "") return "—";
  if (column.type === "currency") return exact(v);
  if (column.type === "percent") return `${Number(v).toFixed(1)}%`;
  if (column.type === "number") return count(v);
  if (column.type === "date") return shortDate(v) || "—";
  if (column.type === "days") {
    // Zero days late is not the same as no answer, and neither is a negative number:
    // an invoice that is not yet due should not read as "0 days late".
    const n = Number(v);
    if (n < 0) return `${count(Math.abs(n))} early`;
    return count(n);
  }
  return String(v);
}
