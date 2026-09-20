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
import { count, percent, shortDate } from "../format.js";

/**
 * Customer complaints.
 *
 * The figure that matters is not how many complaints there are, it is how many nobody
 * has picked up. A complaint with an owner is being handled; one without is a customer
 * waiting on silence, and that is what loses the account.
 */
const HEADLINE = ["cases_open", "cases_unowned", "cases_over_30"];

const OPEN = { is_open: 1 };

export default function Complaints({ scope, openDrawer }) {
  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  const waiting = useApi(
    () =>
      api.facts({
        fact: "fact_case",
        measures: ["days_open"],
        group_by: ["wait_bucket"],
        filters: OPEN,
        business_code: scope,
      }),
    [scope]
  );

  const kinds = useApi(
    () =>
      api.facts({
        fact: "fact_case",
        measures: ["days_open"],
        group_by: ["issue_type"],
        filters: OPEN,
        business_code: scope,
        limit: 15,
      }),
    [scope]
  );

  const customers = useApi(
    () =>
      api.facts({
        fact: "fact_case",
        measures: ["days_open"],
        group_by: ["customer"],
        filters: OPEN,
        business_code: scope,
        limit: 12,
      }),
    [scope]
  );

  const w = waiting.data?.rows || [];
  const k = kinds.data?.rows || [];
  const c = customers.data?.rows || [];
  const openTotal = w.reduce((a, x) => a + (x.rows || 0), 0);

  const BANDS = ["Not yet due", "0-30", "31-60", "61-90", "90+", "No date set"];

  return (
    <div className="view on">
      <ViewHead
        title="Customer complaints"
        note={asOf ? `waiting time measured as at ${asOf}` : null}
      />

      <Kpis keys={HEADLINE} scope={scope} openDrawer={openDrawer} columns={3} what="complaints" />

      <Panel title="Open cases, longest wait first" note="by how long they have been open">
        {waiting.loading ? <Loading what="Reading open cases" /> : null}
        {waiting.error ? (
          <Failed error={waiting.error} onRetry={waiting.reload} what="open cases" />
        ) : null}
        {waiting.data && w.length === 0 ? <Empty>No open complaints.</Empty> : null}
        {w.length > 0 ? (
          <DataTable
            columns={[
              { key: "wait_bucket", label: "Waiting" },
              { key: "rows", label: "Cases", align: "right", render: (x) => count(x.rows) },
              { key: "share", label: "Share", align: "right",
                render: (x) => percent(x.rows, openTotal, { decimals: 1 }) },
              { key: "avg", label: "Average days open", align: "right",
                render: (x) => (x.rows ? count(Math.round((x.days_open || 0) / x.rows)) : "—") },
            ]}
            rows={BANDS.filter((b) => w.find((x) => x.wait_bucket === b)).map((b) => ({
              __key: b,
              ...w.find((x) => x.wait_bucket === b),
            }))}
            onRowClick={(x) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_case"
                  filters={{ ...OPEN, wait_bucket: x.wait_bucket }}
                  title={`Open ${x.wait_bucket}`}
                  subset="all open complaints"
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="What they are complaining about" note="open cases by type">
        {k.length > 0 ? (
          <DataTable
            columns={[
              { key: "issue_type", label: "Type" },
              { key: "rows", label: "Cases", align: "right", render: (x) => count(x.rows) },
              { key: "share", label: "Share", align: "right",
                render: (x) => percent(x.rows, openTotal, { decimals: 1 }) },
            ]}
            rows={k.map((x) => ({ __key: x.issue_type || "—", ...x }))}
            onRowClick={(x) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_case"
                  filters={{ ...OPEN, issue_type: x.issue_type }}
                  title={x.issue_type || "No type recorded"}
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : (
          <Empty>No type recorded against the open cases.</Empty>
        )}
      </Panel>

      <Panel title="Who is complaining" note="open cases by customer">
        {c.length > 0 ? (
          <DataTable
            columns={[
              { key: "customer", label: "Customer" },
              { key: "rows", label: "Cases", align: "right", render: (x) => count(x.rows) },
              { key: "avg", label: "Average days open", align: "right",
                render: (x) => (x.rows ? count(Math.round((x.days_open || 0) / x.rows)) : "—") },
            ]}
            rows={c.map((x) => ({ __key: x.customer || "—", ...x }))}
            onRowClick={(x) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_case"
                  filters={{ ...OPEN, customer: x.customer }}
                  title={x.customer || "No customer recorded"}
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
