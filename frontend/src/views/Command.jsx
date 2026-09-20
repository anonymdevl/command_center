import React from "react";
import { api } from "../api/client.js";
import { boot } from "../api/boot.js";
import { useApi } from "../useApi.js";
import Kpis from "../components/Kpis.jsx";
import Panel from "../components/Panel.jsx";
import ViewHead from "../components/ViewHead.jsx";
import DataTable from "../components/DataTable.jsx";
import { Loading, Failed } from "../components/States.jsx";
import { count, exact, shortDate } from "../format.js";

/**
 * Command.
 *
 * The first screen, so it answers two questions rather than one: what the position
 * is, and whether the figures can be trusted. The second is not a technical
 * appendix -- the receivable on this dataset was misreported twice before the
 * checks existed, and a platform that cannot show its own workings is asking to be
 * believed rather than read.
 */
const HEADLINE = ["ar_total", "ar_over_90_pct", "revenue_invoiced", "margin_pct"];

const FACT_LABELS = {
  fact_sales_invoice: "Sales invoices",
  fact_sales_invoice_line: "Invoice lines",
  fact_payment_allocation: "Payments matched to documents",
};

export default function Command({ scope, go, openDrawer }) {
  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;
  const status = useApi(() => api.ingestStatus(), []);
  const verify = useApi(() => api.kpiVerify(scope), [scope]);

  const rows = (status.data || []).filter(
    (r) => scope === "__all__" || r.business_code === scope
  );

  return (
    <div className="view on">
      <ViewHead
        title="Command"
        note={
          asOf
            ? `every figure as at ${asOf}, the latest date the data covers`
            : "no facts have been loaded yet"
        }
      />

      <Kpis keys={HEADLINE} scope={scope} openDrawer={openDrawer} what="the headline figures" />

      <Panel
        title="What these figures rest on"
        note="what has been read from each connected business"
        action="Sales and money owed →"
        onTitleClick={() => go("sales")}
      >
        {status.loading ? <Loading what="Reading the load history" /> : null}
        {status.error ? (
          <Failed error={status.error} onRetry={status.reload} what="the load history" />
        ) : null}
        {status.data ? (
          <DataTable
            columns={[
              { key: "fact", label: "What", render: (r) => FACT_LABELS[r.fact] || r.fact },
              { key: "business_code", label: "Business" },
              { key: "rows_loaded", label: "Rows", align: "right",
                render: (r) => count(r.rows_loaded) },
              { key: "as_of_date", label: "Covers up to",
                render: (r) => shortDate(r.as_of_date) || "—" },
              { key: "last_run", label: "Last read",
                render: (r) => shortDate(r.last_run) || "—" },
              { key: "status", label: "Result",
                render: (r) => (
                  <span className={`flag ${r.status === "OK" ? "f-ok" : "f-crit"}`}>
                    {r.status === "OK" ? "read cleanly" : r.status.toLowerCase()}
                  </span>
                ) },
            ]}
            rows={rows.map((r) => ({ __key: `${r.fact}-${r.business_code}`, ...r }))}
          />
        ) : null}
        <div className="drfoot">
          The figures above are measured as at the date the data covers, not today.
          Ageing a stale extract against today's date is what turned a thirteen-month-old
          snapshot into a false finding about how this business collects.
        </div>
      </Panel>

      <Panel title="The platform's own checks" note="run against the loaded facts, now">
        {verify.loading ? <Loading what="Checking the figures against each other" /> : null}
        {verify.error ? (
          <Failed error={verify.error} onRetry={verify.reload} what="the checks" />
        ) : null}
        {verify.data ? (
          <>
            <DataTable
              columns={[
                { key: "label", label: "Claim",
                  render: (r) => `${r.label} is the sum of its parts` },
                { key: "whole", label: "Figure", align: "right",
                  render: (r) => exact(r.whole) },
                { key: "component_total", label: "Parts add to", align: "right",
                  render: (r) => exact(r.component_total) },
                { key: "ok", label: "Result",
                  render: (r) => (
                    <span className={`flag ${r.ok ? "f-ok" : "f-crit"}`}>
                      {r.ok ? "agrees" : `out by ${exact(r.difference)}`}
                    </span>
                  ) },
              ]}
              rows={(verify.data.checks || []).map((c) => ({ __key: c.kpi, ...c }))}
            />
            <div className="drfoot">
              {verify.data.all_ok
                ? `All ${verify.data.checked} declared identities hold. Each figure that
                   claims to be made of other figures was recomputed and compared, so a
                   new ageing bucket or invoice status that belongs to neither side would
                   fail here rather than quietly disappear from the breakdown.`
                : `A figure and its parts disagree. Until that is resolved, any breakdown
                   of it on this platform is incomplete.`}
            </div>
          </>
        ) : null}
      </Panel>
    </div>
  );
}
