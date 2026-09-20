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
 * People.
 *
 * Headcount, where they sit, and who cannot sign in. The last one is the only figure
 * here a CEO can act on this week, so it is on a card rather than buried in a table.
 */
const HEADLINE = ["headcount", "departments", "people_without_login"];

const ACTIVE = { is_active: 1 };

export default function People({ scope, openDrawer }) {
  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  const depts = useApi(
    () =>
      api.facts({
        fact: "fact_person",
        measures: ["tenure_days"],
        group_by: ["department"],
        filters: ACTIVE,
        business_code: scope,
        limit: 20,
      }),
    [scope]
  );

  const roles = useApi(
    () =>
      api.facts({
        fact: "fact_person",
        measures: ["tenure_days"],
        group_by: ["designation"],
        filters: ACTIVE,
        business_code: scope,
        limit: 15,
      }),
    [scope]
  );

  const d = depts.data?.rows || [];
  const r = roles.data?.rows || [];
  const total = d.reduce((a, x) => a + (x.rows || 0), 0);

  return (
    <div className="view on">
      <ViewHead title="People" note={asOf ? `as recorded on ${asOf}` : null} />

      <Kpis keys={HEADLINE} scope={scope} openDrawer={openDrawer} columns={3} what="headcount" />

      <Panel title="Where people work" note="active employees by department">
        {depts.loading ? <Loading what="Reading departments" /> : null}
        {depts.error ? (
          <Failed error={depts.error} onRetry={depts.reload} what="departments" />
        ) : null}
        {depts.data && d.length === 0 ? <Empty>No active employees recorded.</Empty> : null}
        {d.length > 0 ? (
          <DataTable
            columns={[
              { key: "department", label: "Department" },
              { key: "rows", label: "People", align: "right", render: (x) => count(x.rows) },
              { key: "share", label: "Share", align: "right",
                render: (x) => percent(x.rows, total, { decimals: 1 }) },
              { key: "tenure", label: "Average service", align: "right",
                render: (x) =>
                  x.rows
                    ? `${count(Math.round((x.tenure_days || 0) / x.rows / 365 * 10) / 10)} yrs`
                    : "—" },
            ]}
            rows={d.map((x) => ({ __key: x.department || "—", ...x }))}
            onRowClick={(x) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_person"
                  filters={{ ...ACTIVE, department: x.department }}
                  title={x.department || "No department set"}
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="What people do" note="active employees by role">
        {r.length > 0 ? (
          <DataTable
            columns={[
              { key: "designation", label: "Role" },
              { key: "rows", label: "People", align: "right", render: (x) => count(x.rows) },
            ]}
            rows={r.map((x) => ({ __key: x.designation || "—", ...x }))}
            onRowClick={(x) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_person"
                  filters={{ ...ACTIVE, designation: x.designation }}
                  title={x.designation || "No role set"}
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="Pay and leave" note="not in the loaded facts">
        <Empty>
          Salary and leave balances are not among the facts this platform reads. They are
          the most sensitive data in an ERPNext, and reading them needs an explicit
          decision about who may see them rather than a default.
        </Empty>
      </Panel>
    </div>
  );
}
