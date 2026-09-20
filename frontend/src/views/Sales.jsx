import React from "react";
import { api } from "../api/client.js";
import { boot } from "../api/boot.js";
import { useApi } from "../useApi.js";
import Kpis from "../components/Kpis.jsx";
import Records from "../components/Records.jsx";
import Panel from "../components/Panel.jsx";
import DataTable from "../components/DataTable.jsx";
import { Loading, Failed } from "../components/States.jsx";
import { exact, count, percent, shortDate } from "../format.js";
import ViewHead from "../components/ViewHead.jsx";

/** The order the interface says them, not the order SQL returns them. */
const BUCKETS = ["Not yet due", "0-30", "31-60", "61-90", "90+"];

const UNPAID = { outstanding_amount: [">", 0], src_docstatus: 1 };

/**
 * Sales and money owed.
 *
 * The figures are named, not computed. This file used to sum the ageing buckets to
 * get a total, subtract to get "inside 90 days" and call percent() for the share --
 * so the screen and the server each had their own idea of the receivable. They
 * agreed, until they would not have.
 */
// Three, not four. ar_over_90_pct was here too, which put "74% of the balance" in
// one card's footnote and "73.84%" in the next card's figure -- the same number twice
// at two precisions, which reads as a discrepancy. The percentage lives on Command,
// where the amount it is a share of is not also on screen.
const FIGURES = ["ar_total", "ar_over_90", "ar_inside_90"];

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

  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  // The breakdown's own total, used for the share column. Taken from the rows being
  // shown rather than from the headline figure, so the column always sums to 100%
  // of what is on screen.
  const rows = ageing.data?.rows || [];
  const shown = rows.reduce((a, r) => a + (r.outstanding_amount || 0), 0);
  const byBucket = Object.fromEntries(rows.map((r) => [r.ageing_bucket, r]));
  const top = customers.data?.rows || [];

  return (
    <div className="view on">
      <ViewHead
        title="Sales and money owed"
        note={asOf ? `ageing measured as at ${asOf}, the latest date the data covers` : null}
      />

      <Kpis
        keys={FIGURES}
        scope={scope}
        openDrawer={openDrawer}
        columns={3}
        what="receivables"
      />

      <Panel title="Who owes us money, and for how long" note={asOf ? `as at ${asOf}` : undefined}>
        {ageing.loading ? <Loading what="Reading the ageing" /> : null}
        {ageing.error ? (
          <Failed error={ageing.error} onRetry={ageing.reload} what="the ageing" />
        ) : null}
        {ageing.data ? (
          <DataTable
            columns={[
              { key: "ageing_bucket", label: "Age" },
              { key: "amount", label: currency, align: "right",
                render: (r) => exact(r.outstanding_amount) },
              { key: "share", label: "Share", align: "right",
                render: (r) => percent(r.outstanding_amount, shown, { decimals: 1 }) },
              { key: "rows", label: "Invoices", align: "right", render: (r) => count(r.rows) },
            ]}
            rows={BUCKETS.filter((b) => byBucket[b]).map((b) => ({
              __key: b,
              ageing_bucket: b,
              ...byBucket[b],
            }))}
            onRowClick={(r) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_sales_invoice"
                  filters={{ ...UNPAID, ageing_bucket: r.ageing_bucket }}
                  title={`Owed, ${r.ageing_bucket}`}
                  subset="everything owed"
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="Largest balances" note="by customer">
        {customers.loading ? <Loading what="Reading customer balances" /> : null}
        {customers.error ? (
          <Failed error={customers.error} onRetry={customers.reload} what="customer balances" />
        ) : null}
        {customers.data ? (
          <DataTable
            columns={[
              { key: "customer", label: "Customer" },
              { key: "amount", label: currency, align: "right",
                render: (r) => exact(r.outstanding_amount) },
              { key: "share", label: "Share", align: "right",
                render: (r) => percent(r.outstanding_amount, shown, { decimals: 1 }) },
              { key: "rows", label: "Invoices", align: "right", render: (r) => count(r.rows) },
            ]}
            rows={top.map((r) => ({ __key: r.customer, ...r }))}
            onRowClick={(r) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_sales_invoice"
                  filters={{ ...UNPAID, customer: r.customer }}
                  title={r.customer}
                  subset="everything owed"
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>
    </div>
  );
}
