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
 * Money in and out.
 *
 * Revenue, what it cost, what came back as cash. Three facts, one screen, and the
 * one caveat that matters stated on the card rather than in a footnote someone can
 * skip: the margin is only over lines that carry a valuation.
 */
const HEADLINE = ["revenue_invoiced", "margin_known_cost", "margin_pct", "cash_applied"];
const QUALITY = ["revenue_costed", "revenue_uncosted", "margin_excluded_lines"];

const SUBMITTED = { src_docstatus: 1 };

export default function Money({ scope, openDrawer }) {
  const currency =
    (boot.businesses || []).find((b) => b.business_code === scope)?.currency || "GHS";
  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  const groups = useApi(
    () =>
      api.facts({
        fact: "fact_sales_invoice_line",
        measures: ["base_net_amount", "base_margin_amount"],
        group_by: ["item_group"],
        filters: { ...SUBMITTED, has_cost: 1 },
        business_code: scope,
        limit: 12,
      }),
    [scope]
  );

  const payments = useApi(
    () =>
      api.facts({
        fact: "fact_payment_allocation",
        measures: ["allocated_amount"],
        group_by: ["payment_type"],
        business_code: scope,
      }),
    [scope]
  );

  const rows = groups.data?.rows || [];
  const shownNet = rows.reduce((a, r) => a + (r.base_net_amount || 0), 0);
  const pay = payments.data?.rows || [];

  return (
    <div className="view on">
      <ViewHead
        title="Money in and out"
        note={asOf ? `everything submitted up to ${asOf}, the latest date the data covers` : null}
      />

      <Kpis keys={HEADLINE} scope={scope} openDrawer={openDrawer} what="revenue and margin" />

      <Panel
        title="Where the margin comes from"
        note="lines that carry a valuation, by item group"
      >
        {groups.loading ? <Loading what="Reading margin by item group" /> : null}
        {groups.error ? (
          <Failed error={groups.error} onRetry={groups.reload} what="margin by item group" />
        ) : null}
        {groups.data && rows.length === 0 ? (
          <Empty>No costed invoice lines in this scope.</Empty>
        ) : null}
        {rows.length > 0 ? (
          <DataTable
            columns={[
              { key: "item_group", label: "Item group" },
              { key: "net", label: `Revenue (${currency})`, align: "right",
                render: (r) => exact(r.base_net_amount) },
              { key: "margin", label: `Margin (${currency})`, align: "right",
                render: (r) => exact(r.base_margin_amount) },
              { key: "pct", label: "Margin %", align: "right",
                render: (r) => percent(r.base_margin_amount, r.base_net_amount, { decimals: 1 }) },
              { key: "share", label: "Share of revenue", align: "right",
                render: (r) => percent(r.base_net_amount, shownNet, { decimals: 1 }) },
              { key: "rows", label: "Lines", align: "right", render: (r) => count(r.rows) },
            ]}
            rows={rows.map((r) => ({ __key: r.item_group || "—", ...r }))}
            onRowClick={(r) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_sales_invoice_line"
                  filters={{ ...SUBMITTED, has_cost: 1, item_group: r.item_group }}
                  title={r.item_group || "Ungrouped"}
                  subset="invoice lines that carry a valuation"
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="What the numbers rest on" note="the figures the margin excludes">
        <Kpis keys={QUALITY} scope={scope} openDrawer={openDrawer} columns={3} what="data quality" />
        <div className="drfoot">
          Margin is calculated only where a cost is recorded against the line. The
          revenue with no valuation behind it is not zero-margin revenue — its margin
          is unknown, and including it would understate the percentage rather than
          leave it unanswered.
        </div>
      </Panel>

      <Panel title="Cash matched to documents" note="by payment type">
        {payments.loading ? <Loading what="Reading payments" /> : null}
        {payments.error ? (
          <Failed error={payments.error} onRetry={payments.reload} what="payments" />
        ) : null}
        {payments.data && pay.length === 0 ? (
          <Empty>No allocated payments in this scope.</Empty>
        ) : null}
        {pay.length > 0 ? (
          <DataTable
            columns={[
              { key: "payment_type", label: "Type" },
              { key: "amount", label: currency, align: "right",
                render: (r) => exact(r.allocated_amount) },
              { key: "rows", label: "Allocations", align: "right", render: (r) => count(r.rows) },
            ]}
            rows={pay.map((r) => ({ __key: r.payment_type || "—", ...r }))}
            onRowClick={(r) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_payment_allocation"
                  filters={{ payment_type: r.payment_type }}
                  title={`${r.payment_type} allocations`}
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
