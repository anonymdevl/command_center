import React from "react";
import { api } from "../api/client.js";
import { boot } from "../api/boot.js";
import { useApi } from "../useApi.js";
import Figure from "../components/Figure.jsx";
import Panel from "../components/Panel.jsx";
import DataTable from "../components/DataTable.jsx";
import { Loading, Failed } from "../components/States.jsx";
import { exact, count, percent, shortDate } from "../format.js";

/** The order the interface says them, not the order SQL returns them. */
const BUCKETS = ["Not yet due", "0-30", "31-60", "61-90", "90+"];

const UNPAID = { outstanding_amount: [">", 0], src_docstatus: 1 };

export default function Sales({ scope, openDrawer }) {
  const currency =
    (boot.businesses || []).find((b) => b.business_code === scope)?.currency || "GHS";

  const ageing = useApi(
    () =>
      api.facts({
        fact: "fact_sales_invoice",
        measures: ["outstanding_amount"],
        group_by: ["ageing_bucket"],
        filters: UNPAID,
        business_code: scope,
      }),
    [scope]
  );

  const customers = useApi(
    () =>
      api.facts({
        fact: "fact_sales_invoice",
        measures: ["outstanding_amount"],
        group_by: ["customer"],
        filters: UNPAID,
        business_code: scope,
        limit: 12,
      }),
    [scope]
  );

  if (ageing.loading || customers.loading) return <Loading what="Reading receivables" />;
  if (ageing.error) return <Failed error={ageing.error} onRetry={ageing.reload} what="receivables" />;

  const rows = ageing.data?.rows || [];
  const byBucket = Object.fromEntries(rows.map((r) => [r.ageing_bucket, r]));
  const total = rows.reduce((a, r) => a + (r.outstanding_amount || 0), 0);
  const invoices = rows.reduce((a, r) => a + (r.rows || 0), 0);

  const over90 = byBucket["90+"]?.outstanding_amount || 0;
  const over90Count = byBucket["90+"]?.rows || 0;
  const inside = total - over90;
  const insideCount = invoices - over90Count;

  const top = customers.data?.rows || [];
  const topTen = top.slice(0, 10).reduce((a, r) => a + (r.outstanding_amount || 0), 0);

  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  return (
    <div className="view on">
      <div className="topbar">
        <div>
          <h3>Sales and money owed</h3>
          <div className="when">
            {count(invoices)} unpaid invoices
            {asOf ? ` · ageing measured as at ${asOf}` : ""}
          </div>
        </div>
      </div>

      <div className="kpis" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
        <Figure
          label="Owed to us"
          value={total}
          currency={currency}
          note={`${count(invoices)} invoices`}
          tone="dn"
          onClick={() => openDrawer(<Lineage scope={scope} title="Everything owed" filters={UNPAID} />)}
        />
        <Figure
          label="Over three months"
          value={over90}
          currency={currency}
          note={`${percent(over90, total)} of the balance`}
          tone="dn"
          onClick={() =>
            openDrawer(
              <Lineage
                scope={scope}
                title="Owed more than three months"
                filters={{ ...UNPAID, ageing_bucket: "90+" }}
              />
            )
          }
        />
        <Figure
          label="Still inside 90 days"
          value={inside}
          currency={currency}
          note={`${count(insideCount)} invoices`}
          tone="flat"
          onClick={() =>
            openDrawer(
              <Lineage
                scope={scope}
                title="Owed, but not yet three months old"
                filters={{ ...UNPAID, ageing_bucket: ["in", ["Not yet due", "0-30", "31-60", "61-90"]] }}
              />
            )
          }
        />
        <Figure
          label="Ten largest hold"
          value={topTen}
          currency={currency}
          note={`${percent(topTen, total)} of everything owed`}
          tone="dn"
          onClick={() =>
            openDrawer(
              <Lineage
                scope={scope}
                title="The ten largest balances"
                filters={{ ...UNPAID, customer: ["in", top.slice(0, 10).map((r) => r.customer)] }}
              />
            )
          }
        />
      </div>

      <Panel
        title="Who owes us money, and for how long"
        note={asOf ? `as at ${asOf}` : undefined}
      >
        <DataTable
          columns={[
            { key: "ageing_bucket", label: "Age" },
            { key: "amount", label: `${currency}`, align: "right",
              render: (r) => exact(r.outstanding_amount) },
            { key: "share", label: "Share", align: "right",
              render: (r) => percent(r.outstanding_amount, total, { decimals: 1 }) },
            { key: "rows", label: "Invoices", align: "right",
              render: (r) => count(r.rows) },
          ]}
          rows={BUCKETS.filter((b) => byBucket[b]).map((b) => ({
            __key: b,
            ageing_bucket: b,
            ...byBucket[b],
          }))}
        />
      </Panel>

      <Panel title="Largest balances" note="by customer">
        {customers.error ? (
          <Failed error={customers.error} onRetry={customers.reload} what="customer balances" />
        ) : (
          <DataTable
            columns={[
              { key: "customer", label: "Customer" },
              { key: "amount", label: `${currency}`, align: "right",
                render: (r) => exact(r.outstanding_amount) },
              { key: "share", label: "Share", align: "right",
                render: (r) => percent(r.outstanding_amount, total, { decimals: 1 }) },
              { key: "rows", label: "Invoices", align: "right",
                render: (r) => count(r.rows) },
            ]}
            rows={top.map((r) => ({ __key: r.customer, ...r }))}
            onRowClick={(r) =>
              openDrawer(
                <Lineage
                  scope={scope}
                  title={r.customer}
                  filters={{ ...UNPAID, customer: r.customer }}
                />
              )
            }
          />
        )}
      </Panel>
    </div>
  );
}

/**
 * Which records produced a figure.
 *
 * Not a separate feature: every fact row carries its source document, so this is
 * the same rows selected back. That is the whole reason lineage was built into
 * the schema rather than bolted onto each screen.
 */
function Lineage({ scope, title, filters }) {
  const { data, error, loading, reload } = useApi(
    () => api.lineage({ fact: "fact_sales_invoice", filters, business_code: scope, limit: 100 }),
    [scope, JSON.stringify(filters)]
  );

  return (
    <>
      <div className="dhead">
        <div>
          <div className="dt">The records behind it</div>
          <h4>{title}</h4>
        </div>
      </div>
      {loading ? <Loading what="Finding the records" /> : null}
      {error ? <Failed error={error} onRetry={reload} what="the records" /> : null}
      {data ? (
        <>
          <DataTable
            columns={[
              { key: "src_name", label: "Invoice" },
              { key: "src_doctype", label: "From" },
              { key: "src_modified", label: "Last changed",
                render: (r) => String(r.src_modified || "").slice(0, 10) },
            ]}
            rows={data.map((r) => ({ __key: r.src_name, ...r }))}
          />
          <div className="drfoot">
            Showing {data.length} of them. Every row names the ERPNext document it came
            from, so any figure on this screen can be taken back to its records.
          </div>
        </>
      ) : null}
    </>
  );
}
