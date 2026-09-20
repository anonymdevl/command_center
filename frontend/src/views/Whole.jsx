import React from "react";
import { boot } from "../api/boot.js";
import Kpis from "../components/Kpis.jsx";
import Panel from "../components/Panel.jsx";
import ViewHead from "../components/ViewHead.jsx";
import { shortDate } from "../format.js";

/**
 * The whole business.
 *
 * Every domain's headline figure on one screen, grouped the way someone running the
 * business would ask about them: what we are owed, what we owe, what we have promised,
 * what we are holding, and who is waiting on an answer.
 *
 * No new arithmetic. Every figure is the same named KPI the domain screen shows, so
 * this screen and that one cannot disagree — which is the whole reason the KPI engine
 * was built before the screens were.
 */
const GROUPS = [
  {
    title: "Money owed to us",
    note: "receivables, measured at the data horizon",
    keys: ["ar_total", "ar_over_90", "ar_over_90_pct"],
    go: "sales",
    to: "Sales and money owed",
  },
  {
    title: "Money we owe",
    note: "payables to suppliers",
    keys: ["ap_total", "ap_over_90", "ap_unpaid_pct"],
    go: "proc",
    to: "Buying and suppliers",
  },
  {
    title: "What we have promised",
    note: "order book still to deliver",
    keys: ["order_book", "order_book_late", "order_book_late_pct"],
    go: "eng",
    to: "Engineering and delivery",
  },
  {
    title: "What we are holding",
    note: "stock on hand and what can actually be sold",
    keys: ["stock_value", "stock_available_qty", "stock_reserved_qty"],
    go: "inv",
    to: "Stock and warehouses",
  },
  {
    title: "What we earned on it",
    note: "revenue and margin where cost is known",
    keys: ["revenue_invoiced", "margin_known_cost", "margin_pct"],
    go: "fin",
    to: "Money in and out",
  },
  {
    title: "Who is waiting on us",
    note: "open complaints and unowned work",
    keys: ["cases_open", "cases_unowned", "tasks_unowned"],
    go: "cx",
    to: "Customer complaints",
  },
];

export default function Whole({ scope, go, openDrawer }) {
  const asOf = boot.as_of?.date ? shortDate(boot.as_of.date) : null;

  return (
    <div className="view on">
      <ViewHead
        title="The whole business"
        note={
          asOf
            ? `every figure as at ${asOf}, the latest date the data covers`
            : "no facts have been loaded yet"
        }
      />

      {GROUPS.map((g) => (
        <Panel
          key={g.title}
          title={g.title}
          note={g.note}
          action={`${g.to} →`}
          onTitleClick={() => go(g.go)}
        >
          <Kpis
            keys={g.keys}
            scope={scope}
            openDrawer={openDrawer}
            columns={3}
            what={g.title.toLowerCase()}
          />
        </Panel>
      ))}

      <div className="dnote" style={{ margin: "4px 0 0" }}>
        <span className="dn-i">●</span>
        <span>
          Every figure here is the same named measure its own screen shows — not a second
          calculation of it. Open any card for the records behind it, or the panel heading
          for the screen it belongs to.
        </span>
      </div>
    </div>
  );
}
