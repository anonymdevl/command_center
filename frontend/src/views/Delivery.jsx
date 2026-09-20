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
 * Engineering and delivery.
 *
 * The question the designed screen asks is "can we actually deliver the work we are
 * holding?", and it is now answerable: the order book is what we have promised and not
 * delivered, and free-to-sell stock is what we have to deliver it with. Both are facts,
 * so the comparison is real rather than rhetorical.
 *
 * The two sides are deliberately shown as two figures rather than one ratio. A single
 * "coverage %" would imply the stock on hand is the right stock for those orders, which
 * needs item-level matching this does not yet do. Overstating what a figure knows is
 * how a platform loses the room.
 */
const ORDER_BOOK = ["order_book", "order_book_late", "order_book_late_pct", "order_unbilled"];
const WORK = ["tasks_open", "tasks_overdue", "tasks_unowned"];

const OPEN_ORDER = { is_open: 1 };
const OPEN_TASK = { is_open: 1 };
const LATE = ["0-30", "31-60", "61-90", "90+"];

export default function Delivery({ scope, openDrawer }) {
  const currency =
    (boot.businesses || []).find((b) => b.business_code === scope)?.currency || "GHS";
  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  const lateness = useApi(
    () =>
      api.facts({
        fact: "fact_sales_order",
        measures: ["undelivered_value"],
        group_by: ["lateness_bucket"],
        filters: OPEN_ORDER,
        business_code: scope,
      }),
    [scope]
  );

  const owed = useApi(
    () =>
      api.facts({
        fact: "fact_sales_order",
        measures: ["undelivered_value", "base_grand_total"],
        group_by: ["customer"],
        filters: OPEN_ORDER,
        business_code: scope,
        limit: 12,
      }),
    [scope]
  );

  const people = useApi(
    () =>
      api.facts({
        fact: "fact_task",
        measures: ["days_late"],
        group_by: ["assigned_to"],
        filters: { ...OPEN_TASK, lateness_bucket: ["in", LATE] },
        business_code: scope,
        limit: 12,
      }),
    [scope]
  );

  const l = lateness.data?.rows || [];
  const o = owed.data?.rows || [];
  const p = people.data?.rows || [];
  const bookShown = l.reduce((a, x) => a + (x.undelivered_value || 0), 0);
  const BANDS = ["Not yet due", "No date set", "0-30", "31-60", "61-90", "90+"];

  return (
    <div className="view on">
      <ViewHead
        title="Engineering and delivery"
        note={asOf ? `promises measured against ${asOf}, the latest date the data covers` : null}
      />

      <Kpis keys={ORDER_BOOK} scope={scope} openDrawer={openDrawer} what="the order book" />

      <Panel
        title="Can we deliver what we have sold?"
        note="undelivered order value, by how far past the promised date"
      >
        {lateness.loading ? <Loading what="Reading the order book" /> : null}
        {lateness.error ? (
          <Failed error={lateness.error} onRetry={lateness.reload} what="the order book" />
        ) : null}
        {lateness.data && l.length === 0 ? <Empty>No open orders.</Empty> : null}
        {l.length > 0 ? (
          <>
            <DataTable
              columns={[
                { key: "lateness_bucket", label: "Against the promise" },
                { key: "value", label: `Still to deliver (${currency})`, align: "right",
                  render: (x) => exact(x.undelivered_value) },
                { key: "share", label: "Share", align: "right",
                  render: (x) => percent(x.undelivered_value, bookShown, { decimals: 1 }) },
                { key: "rows", label: "Orders", align: "right", render: (x) => count(x.rows) },
              ]}
              rows={BANDS.filter((b) => l.find((x) => x.lateness_bucket === b)).map((b) => ({
                __key: b,
                ...l.find((x) => x.lateness_bucket === b),
              }))}
              onRowClick={(x) =>
                openDrawer(
                  <Records
                    scope={scope}
                    fact="fact_sales_order"
                    filters={{ ...OPEN_ORDER, lateness_bucket: x.lateness_bucket }}
                    title={`Order book, ${x.lateness_bucket}`}
                    subset="everything promised and not delivered"
                    openDrawer={openDrawer}
                  />
                )
              }
            />
            <div className="drfoot">
              Undelivered value is order value less the delivered share, so a part-shipped
              order counts only for what is still owed. Free-to-sell stock is on Stock and
              warehouses; the two are shown separately because matching specific stock to
              specific orders needs item-level work this does not yet do, and a single
              coverage figure would claim more than it knows.
            </div>
          </>
        ) : null}
      </Panel>

      <Panel title="Who is waiting on us" note="open orders by customer">
        {owed.loading ? <Loading what="Reading orders by customer" /> : null}
        {o.length > 0 ? (
          <DataTable
            columns={[
              { key: "customer", label: "Customer" },
              { key: "undelivered", label: `Still to deliver (${currency})`, align: "right",
                render: (x) => exact(x.undelivered_value) },
              { key: "ordered", label: `Ordered (${currency})`, align: "right",
                render: (x) => exact(x.base_grand_total) },
              { key: "done", label: "Delivered", align: "right",
                render: (x) =>
                  percent(
                    (x.base_grand_total || 0) - (x.undelivered_value || 0),
                    x.base_grand_total,
                    { decimals: 1 }
                  ) },
              { key: "rows", label: "Orders", align: "right", render: (x) => count(x.rows) },
            ]}
            rows={o.map((x) => ({ __key: x.customer || "—", ...x }))}
            onRowClick={(x) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_sales_order"
                  filters={{ ...OPEN_ORDER, customer: x.customer }}
                  title={x.customer}
                  openDrawer={openDrawer}
                />
              )
            }
          />
        ) : null}
      </Panel>

      <Panel title="The work behind it" note="tasks in flight">
        <Kpis keys={WORK} scope={scope} openDrawer={openDrawer} columns={3} what="work in flight" />
      </Panel>

      <Panel title="Who is carrying the late work" note="overdue tasks by owner">
        {people.loading ? <Loading what="Reading overdue work" /> : null}
        {people.error ? (
          <Failed error={people.error} onRetry={people.reload} what="overdue work" />
        ) : null}
        {people.data && p.length === 0 ? (
          <Empty>Nothing is past its due date.</Empty>
        ) : null}
        {p.length > 0 ? (
          <DataTable
            columns={[
              { key: "assigned_to", label: "Owner",
                render: (x) => x.assigned_to || "nobody assigned" },
              { key: "rows", label: "Late tasks", align: "right", render: (x) => count(x.rows) },
              { key: "worst", label: "Days late in total", align: "right",
                render: (x) => count(x.days_late || 0) },
            ]}
            rows={p.map((x) => ({ __key: x.assigned_to || "—", ...x }))}
            onRowClick={(x) =>
              openDrawer(
                <Records
                  scope={scope}
                  fact="fact_task"
                  filters={{ ...OPEN_TASK, lateness_bucket: ["in", LATE],
                             assigned_to: x.assigned_to }}
                  title={x.assigned_to || "Late work with no owner"}
                  subset="all work in flight"
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
