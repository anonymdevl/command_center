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
 * Stock and warehouses.
 *
 * The designed panels are kept, including the two that say a thing is not measured in
 * this extract. Movement history and expiry dates are genuinely not in the loaded
 * facts, and a panel that filled itself with something adjacent would be worse than
 * one that says so.
 *
 * The figure that matters most here is free-to-sell rather than on-hand. Reporting
 * what is on the shelf as though it were available is how goods get promised twice.
 */
const HEADLINE = ["stock_value", "stock_available_qty", "stock_reserved_qty",
                  "stock_unvalued_lines"];

export default function Stock({ scope, openDrawer }) {
  const currency =
    (boot.businesses || []).find((b) => b.business_code === scope)?.currency || "GHS";
  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  const warehouses = useApi(
    () =>
      api.facts({
        fact: "fact_stock_balance",
        measures: ["stock_value", "actual_qty", "reserved_qty", "available_qty"],
        group_by: ["warehouse"],
        business_code: scope,
        limit: 20,
      }),
    [scope]
  );

  const groups = useApi(
    () =>
      api.facts({
        fact: "fact_stock_balance",
        measures: ["stock_value"],
        group_by: ["item_group"],
        business_code: scope,
        limit: 12,
      }),
    [scope]
  );

  const wh = warehouses.data?.rows || [];
  const ig = groups.data?.rows || [];
  const whTotal = wh.reduce((a, r) => a + (r.stock_value || 0), 0);
  const igTotal = ig.reduce((a, r) => a + (r.stock_value || 0), 0);

  return (
    <div className="view on">
      <ViewHead
        title="Stock and warehouses"
        note={asOf ? `balances as read on ${asOf}` : null}
      />

      <Kpis keys={HEADLINE} scope={scope} openDrawer={openDrawer} what="stock" />

      <Panel title="Where the value sits" note="by warehouse">
        {warehouses.loading ? <Loading what="Reading warehouse balances" /> : null}
        {warehouses.error ? (
          <Failed error={warehouses.error} onRetry={warehouses.reload} what="warehouse balances" />
        ) : null}
        {warehouses.data && wh.length === 0 ? (
          <Empty>No stock balances in this scope.</Empty>
        ) : null}
        {wh.length > 0 ? (
          <DataTable
            columns={[
              { key: "warehouse", label: "Warehouse" },
              { key: "value", label: `Value (${currency})`, align: "right",
                render: (r) => exact(r.stock_value) },
              { key: "share", label: "Share", align: "right",
                render: (r) => percent(r.stock_value, whTotal, { decimals: 1 }) },
              { key: "on_hand", label: "On hand", align: "right",
                render: (r) => count(Math.round(r.actual_qty || 0)) },
              { key: "free", label: "Free to sell", align: "right",
                render: (r) => count(Math.round(r.available_qty || 0)) },
              { key: "rows", label: "Item lines", align: "right", render: (r) => count(r.rows) },
            ]}
            rows={wh.map((r) => ({ __key: r.warehouse || "—", ...r }))}
            onRowClick={(r) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_stock_balance"
                  filters={{ warehouse: r.warehouse }}
                  title={r.warehouse || "Unnamed warehouse"}
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="Reserved against what is available" note="where stock is already promised">
        {wh.length > 0 ? (
          <>
            <DataTable
              columns={[
                { key: "warehouse", label: "Warehouse" },
                { key: "on_hand", label: "On hand", align: "right",
                  render: (r) => count(Math.round(r.actual_qty || 0)) },
                { key: "reserved", label: "Reserved", align: "right",
                  render: (r) => count(Math.round(r.reserved_qty || 0)) },
                { key: "free", label: "Free to sell", align: "right",
                  render: (r) => count(Math.round(r.available_qty || 0)) },
                { key: "pct", label: "Reserved %", align: "right",
                  render: (r) => percent(r.reserved_qty, r.actual_qty, { decimals: 1 }) },
              ]}
              rows={wh
                .filter((r) => (r.reserved_qty || 0) > 0)
                .map((r) => ({ __key: r.warehouse || "—", ...r }))}
              onRowClick={(r) =>
                openDrawer(
                  <Records
                    scope={scope}
                    fact="fact_stock_balance"
                    filters={{ warehouse: r.warehouse, reserved_qty: [">", 0] }}
                    title={`Reserved in ${r.warehouse}`}
                    openDrawer={openDrawer}
                  />
                )
              }
            />
            <div className="drfoot">
              Only warehouses with something reserved are listed. Free to sell is on
              hand less reserved, and it is the figure to quote when someone asks what
              can be shipped — quoting on hand is how the same units get sold twice.
            </div>
          </>
        ) : null}
      </Panel>

      <Panel title="What we hold, by item group" note="largest value first">
        {groups.loading ? <Loading what="Reading stock by item group" /> : null}
        {groups.error ? (
          <Failed error={groups.error} onRetry={groups.reload} what="stock by item group" />
        ) : null}
        {ig.length > 0 ? (
          <DataTable
            columns={[
              { key: "item_group", label: "Item group" },
              { key: "value", label: `Value (${currency})`, align: "right",
                render: (r) => exact(r.stock_value) },
              { key: "share", label: "Share", align: "right",
                render: (r) => percent(r.stock_value, igTotal, { decimals: 1 }) },
              { key: "rows", label: "Item lines", align: "right", render: (r) => count(r.rows) },
            ]}
            rows={ig.map((r) => ({ __key: r.item_group || "—", ...r }))}
            onRowClick={(r) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_stock_balance"
                  filters={{ item_group: r.item_group }}
                  title={r.item_group || "Ungrouped"}
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="Stock that is not moving" note="not measured in this extract">
        <Empty>
          This needs movement history, which is a separate fact from the balances loaded
          here — a balance says what is on the shelf, not when it last moved. The panel
          stays empty rather than guessing from what is in stock now.
        </Empty>
      </Panel>

      <Panel title="Expiry" note="not recorded in this extract">
        <Empty>
          Batch expiry dates are not maintained in this ERPNext, so there is nothing to
          report against.
        </Empty>
      </Panel>
    </div>
  );
}
