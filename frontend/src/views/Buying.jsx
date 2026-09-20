import React from "react";
import { api } from "../api/client.js";
import { boot } from "../api/boot.js";
import { useApi } from "../useApi.js";
import Kpis from "../components/Kpis.jsx";
import Records from "../components/Records.jsx";
import Panel from "../components/Panel.jsx";
import ViewHead from "../components/ViewHead.jsx";
import DataTable from "../components/DataTable.jsx";
import { Loading, Failed, Empty } from "../components/States.jsx";
import { exact, count, percent, shortDate } from "../format.js";

/**
 * Buying and suppliers.
 *
 * The designed screen's panels are kept as they were designed, including the ones
 * that say a thing is not in this extract -- that honesty is part of the design, and
 * filling those panels with something invented would be the opposite of what they
 * say. What changes is that the money panels now read the loaded facts.
 */
const HEADLINE = ["spend_total", "ap_total", "ap_over_90", "ap_unpaid_pct"];

const UNPAID = { outstanding_amount: [">", 0], src_docstatus: 1 };
const SUBMITTED = { src_docstatus: 1 };

export default function Buying({ scope, openDrawer }) {
  const currency =
    (boot.businesses || []).find((b) => b.business_code === scope)?.currency || "GHS";
  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  const byGroup = useApi(
    () =>
      api.facts({
        fact: "fact_purchase_invoice_line",
        measures: ["base_net_amount"],
        group_by: ["item_group"],
        filters: SUBMITTED,
        business_code: scope,
        limit: 12,
      }),
    [scope]
  );

  const bySupplier = useApi(
    () =>
      api.facts({
        fact: "fact_purchase_invoice_line",
        measures: ["base_net_amount"],
        group_by: ["supplier"],
        filters: SUBMITTED,
        business_code: scope,
        limit: 12,
      }),
    [scope]
  );

  const ageing = useApi(
    () =>
      api.facts({
        fact: "fact_purchase_invoice",
        measures: ["outstanding_amount"],
        group_by: ["ageing_bucket"],
        filters: UNPAID,
        business_code: scope,
      }),
    [scope]
  );

  const groups = byGroup.data?.rows || [];
  const suppliers = bySupplier.data?.rows || [];
  const buckets = ageing.data?.rows || [];

  const groupTotal = groups.reduce((a, r) => a + (r.base_net_amount || 0), 0);
  const supplierTotal = suppliers.reduce((a, r) => a + (r.base_net_amount || 0), 0);
  const owedShown = buckets.reduce((a, r) => a + (r.outstanding_amount || 0), 0);
  const byBucket = Object.fromEntries(buckets.map((r) => [r.ageing_bucket, r]));

  return (
    <div className="view on">
      <ViewHead
        title="Buying and suppliers"
        note={asOf ? `everything submitted up to ${asOf}, the latest date the data covers` : null}
      />

      <Kpis keys={HEADLINE} scope={scope} openDrawer={openDrawer} what="spend and payables" />

      <Panel title="Where the money goes" note="by item group">
        {byGroup.loading ? <Loading what="Reading spend by item group" /> : null}
        {byGroup.error ? (
          <Failed error={byGroup.error} onRetry={byGroup.reload} what="spend by item group" />
        ) : null}
        {byGroup.data && groups.length === 0 ? (
          <Empty>No submitted purchase lines in this scope.</Empty>
        ) : null}
        {groups.length > 0 ? (
          <DataTable
            columns={[
              { key: "item_group", label: "Item group" },
              { key: "spend", label: `Spend (${currency})`, align: "right",
                render: (r) => exact(r.base_net_amount) },
              { key: "share", label: "Share", align: "right",
                render: (r) => percent(r.base_net_amount, groupTotal, { decimals: 1 }) },
              { key: "rows", label: "Lines", align: "right", render: (r) => count(r.rows) },
            ]}
            rows={groups.map((r) => ({ __key: r.item_group || "—", ...r }))}
            onRowClick={(r) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_purchase_invoice_line"
                  filters={{ ...SUBMITTED, item_group: r.item_group }}
                  title={r.item_group || "Ungrouped"}
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="Who we buy from" note="by supplier, largest first">
        {bySupplier.loading ? <Loading what="Reading spend by supplier" /> : null}
        {bySupplier.error ? (
          <Failed error={bySupplier.error} onRetry={bySupplier.reload} what="spend by supplier" />
        ) : null}
        {suppliers.length > 0 ? (
          <>
            <DataTable
              columns={[
                { key: "supplier", label: "Supplier" },
                { key: "spend", label: `Spend (${currency})`, align: "right",
                  render: (r) => exact(r.base_net_amount) },
                { key: "share", label: "Share", align: "right",
                  render: (r) => percent(r.base_net_amount, supplierTotal, { decimals: 1 }) },
                { key: "rows", label: "Lines", align: "right", render: (r) => count(r.rows) },
              ]}
              rows={suppliers.map((r) => ({ __key: r.supplier || "—", ...r }))}
              onRowClick={(r) =>
                openDrawer(
                  <Records
                    scope={scope}
                    fact="fact_purchase_invoice_line"
                    filters={{ ...SUBMITTED, supplier: r.supplier }}
                    title={r.supplier}
                    openDrawer={openDrawer}
                  />
                )
              }
            />
            <div className="drfoot">
              Shares are of the {count(suppliers.length)} suppliers shown, not of all
              spend — so a concentration read off this table is a floor, not the whole
              picture. Open any row for the full set behind it.
            </div>
          </>
        ) : null}
      </Panel>

      <Panel
        title="How long each supplier waits for us"
        note={asOf ? `measured as at ${asOf}` : undefined}
      >
        {ageing.loading ? <Loading what="Reading payables ageing" /> : null}
        {ageing.error ? (
          <Failed error={ageing.error} onRetry={ageing.reload} what="payables ageing" />
        ) : null}
        {ageing.data && buckets.length === 0 ? (
          <Empty>Nothing outstanding to suppliers in this scope.</Empty>
        ) : null}
        {buckets.length > 0 ? (
          <DataTable
            columns={[
              { key: "ageing_bucket", label: "Age" },
              { key: "amount", label: currency, align: "right",
                render: (r) => exact(r.outstanding_amount) },
              { key: "share", label: "Share", align: "right",
                render: (r) => percent(r.outstanding_amount, owedShown, { decimals: 1 }) },
              { key: "rows", label: "Invoices", align: "right", render: (r) => count(r.rows) },
            ]}
            rows={["Not yet due", "0-30", "31-60", "61-90", "90+"]
              .filter((b) => byBucket[b])
              .map((b) => ({ __key: b, ageing_bucket: b, ...byBucket[b] }))}
            onRowClick={(r) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_purchase_invoice"
                  filters={{ ...UNPAID, ageing_bucket: r.ageing_bucket }}
                  title={`Owed to suppliers, ${r.ageing_bucket}`}
                  subset="everything we owe"
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="Supplier performance" note="not scored in this extract">
        <Empty>
          On-time delivery and quality scoring are not switched on in this ERPNext, so
          there is nothing to report. This panel stays empty rather than showing a
          score derived from something else.
        </Empty>
      </Panel>
    </div>
  );
}
