// Business Overview's front page (frontend/src/legacy/overview.js).
//
//     node scripts/test_overview.mjs
//
// Run by scripts/test_overview_parity.py. planOverview is pure, so this needs no
// browser: every area is placed exactly once whatever the figures and alerts say; the
// worst alert leads, then the larger money at stake, then the designed order; nothing
// is called calm when the alerts were not read; and the lead's sentence is built only
// from its own figure and note.
import { areaOfAlert, areaNote, figureText, leadSentence, planOverview, SECONDARY }
  from "../frontend/src/legacy/overview.js";

let failed = 0;
const check = (ok, what) => {
  if (!ok) {
    failed += 1;
    console.log("FAIL:", what);
  }
};

const DEPTS = ["sales", "proc", "inv", "eng", "cx", "fin", "hr", "it", "aud"];
const money = (v, state = "stale") => ({ label: "Owed", value: v, unit: "currency", currency: "GHS",
  note: "a note", data_status: { state } });
const areas = (figs = {}) => DEPTS.map((dept, index) => ({ dept, index, figure: figs[dept] || null }));
const alert = (fact, severity, figure = 0, unit = "currency", filters = {}) =>
  ({ drill_fact: fact, severity, figure, figure_unit: unit, drill_filters: filters });
const placed = (p) => [p.lead, ...p.sec, ...p.rows].map((a) => a.dept);
const once = (p) => {
  const all = placed(p);
  return all.length === DEPTS.length && new Set(all).size === DEPTS.length
    && DEPTS.every((d) => all.includes(d));
};

// Which area an alert belongs to.
check(areaOfAlert(alert("fact_stock_balance", "crit")) === "inv", "stock alerts are Stock & warehouses");
check(areaOfAlert(alert("fact_sales_order", "high")) === "sales", "order alerts are Sales");
check(areaOfAlert(alert("fact_task", "high")) === "eng", "job alerts are Engineering");
check(areaOfAlert(alert("fact_party_balance", "med", 0, "currency", { party_type: "Supplier" })) === "proc",
  "a supplier balance is Buying");
check(areaOfAlert(alert("fact_party_balance", "med", 0, "currency", { party_type: "Customer" })) === "sales",
  "a customer balance is Sales");
check(areaOfAlert(alert("fact_unknown", "crit")) === null, "an alert on no area's records ranks none");

// The worst alert leads; the next three stand beside it; the register keeps the designed order.
let p = planOverview(areas({ inv: money(658572), sales: money(0) }), [
  alert("fact_stock_balance", "crit", 3, "products"),
  alert("fact_sales_order", "high", 135188),
  alert("fact_sales_order", "high", 51131),
  alert("fact_task", "high", 23, "jobs"),
]);
check(once(p), `every area exactly once: ${placed(p)}`);
check(p.lead.dept === "inv", `the critical alert leads, got ${p.lead.dept}`);
check(p.sec.length === SECONDARY && p.sec[0].dept === "sales" && p.sec[1].dept === "eng",
  `high alerts next, more money first: ${p.sec.map((a) => a.dept)}`);
check(p.rows.map((a) => a.index).join() === [...p.rows.map((a) => a.index)].sort((a, b) => a - b).join(),
  "the register is in the designed order");
check(!p.quiet && p.read, "alerts read and something wrong: not quiet");

// Same severity: the larger money at stake leads.
p = planOverview(areas({ sales: money(10), proc: money(900) }), [
  alert("fact_purchase_invoice", "med", 50), alert("fact_sales_invoice", "med", 500)]);
check(p.lead.dept === "sales", `same severity, more money leads: ${p.lead.dept}`);

// A failed load needs someone; can't-reach and stale do not.
p = planOverview(areas({ hr: { value: 1, unit: "count", data_status: { state: "failed" } },
  sales: money(5, "unreachable") }), []);
check(p.lead.dept === "hr" && !p.quiet, "a failed load leads when there is no alert");

// Nothing wrong: the largest area leads, and the screen says nothing needs you.
p = planOverview(areas({ sales: money(100), inv: money(900), proc: money(50) }), []);
check(p.quiet && p.lead.dept === "inv", `quiet, largest leads: ${p.lead.dept} quiet=${p.quiet}`);
check(once(p), "quiet: every area exactly once");

// Alerts not read: never called calm.
p = planOverview(areas({ sales: money(100) }), null);
check(!p.quiet && !p.read && once(p), "unread alerts never make the screen quiet");

// No figures at all: the designed order.
p = planOverview(areas(), null);
check(placed(p).join() === DEPTS.join(), `nothing read: the designed order, got ${placed(p)}`);

// Many random cases: always every area once.
for (let i = 0; i < 300; i += 1) {
  const figs = {};
  DEPTS.forEach((d) => {
    if (Math.random() < 0.7) figs[d] = money(Math.round(Math.random() * 1e6),
      ["live", "stale", "failed", "unreachable", "needs_setup"][i % 5]);
  });
  const facts = ["fact_sales_order", "fact_task", "fact_case", "fact_stock_balance", "fact_person", "x"];
  const list = Array.from({ length: i % 7 }, (_, j) => alert(facts[(i + j) % facts.length],
    ["crit", "high", "med", "info"][(i * j) % 4], Math.random() * 1e5));
  const plan = planOverview(areas(figs), i % 3 ? list : null);
  if (!once(plan)) {
    check(false, `random case ${i}: ${placed(plan)}`);
    break;
  }
}

// The words: only the figure and its own note.
check(figureText(money(658572.05)) === "GHS 658.57k", `money: ${figureText(money(658572.05))}`);
check(figureText({ value: 40, unit: "count" }, "tasks") === "40 tasks", "a count with its unit word");
check(figureText({ value: null, unit: "count" }) === null, "an unread figure has no words");
check(leadSentence({ label: "Work in flight", value: 40, unit: "count", note: "23 of them past due",
  data_status: { state: "stale" } }, "tasks") === "Work in flight: 40 tasks, 23 of them past due.",
  "the sentence is the figure and its note");
check(leadSentence({ label: "X", value: null, data_status: { state: "unreachable",
  message: "Can't reach this business's ERPNext right now." } })
  === "Can't reach this business's ERPNext right now.", "an unreachable figure says so, no number");
check(leadSentence({ label: "X", value: null, data_status: { state: "needs_setup",
  guide: { text: "Nothing is recorded yet." } } }) === "Nothing is recorded yet.",
  "a figure with a guide says the guide's sentence");
check(areaNote({ value: 3, note: "n", data_status: { state: "unreachable" } }) === null,
  "no note under a figure that could not be read");

if (failed) {
  console.log(`${failed} failure(s)`);
  process.exit(1);
}
console.log("overview ordering: all clear");
