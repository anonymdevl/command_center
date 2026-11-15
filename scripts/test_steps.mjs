// The page's grouping of the analyst's live steps (frontend/src/legacy/steps.js).
//
//     node scripts/test_steps.mjs
//
// Run by scripts/test_analyst.py when Node is installed. groupSteps is pure, so this
// needs no browser: a run of one kind of lookup is one row with a count, a step with no
// kind (a plain string, or a message from the model client) is never grouped, and each
// step's own line is kept for "Show all".
import { groupSteps, hasHidden, stepOf } from "../frontend/src/legacy/steps.js";

let failed = 0;
const check = (ok, what) => {
  if (!ok) {
    failed += 1;
    console.log("FAIL:", what);
  }
};
const step = (kind, group, text) => ({ kind, group, text });

const rows = groupSteps([
  step("get_figures", "Reading the headline figures", "Reading the headline figures"),
  ...["General Ledger", "Trial Balance", "Balance Sheet", "Cash Flow", "Profit and Loss Statement",
    "Accounts Receivable"].map((r) => step("run_report", "Running an ERPNext report", `Running ERPNext's ${r}`)),
  "Gemini 3.8 Flash did not reply; trying another",
  "Gemini 3.8 Flash did not reply; trying another",
  step("erpnext", "Reading ERPNext records", "Reading Quotation records"),
  step("run_report", "Running an ERPNext report", "Running ERPNext's Stock Balance"),
]);
check(rows.length === 6, `six rows, got ${rows.length}: ${JSON.stringify(rows.map((r) => r.label))}`);
check(rows[0].label === "Reading the headline figures" && rows[0].count === 1, "a single step keeps its own words");
check(rows[1].label === "Running an ERPNext report" && rows[1].count === 6
  && rows[1].details[0] === "Running ERPNext's General Ledger" && rows[1].details.length === 6,
  `six reports in a row are one row with a count, each kept for Show all: ${JSON.stringify(rows[1])}`);
check(rows[2].count === 1 && rows[3].count === 1, "steps with no kind are never grouped");
check(rows[5].label === "Running ERPNext's Stock Balance", "only consecutive steps of a kind are grouped");
check(hasHidden(rows), "a grouped row means Show all has something to show");
check(!hasHidden(groupSteps(["a", "b"])), "nothing grouped, nothing hidden");
check(groupSteps([]).length === 0 && groupSteps(null).length === 0, "no steps, no rows");
check(stepOf("plain").text === "plain" && stepOf({ text: "t", kind: "k" }).kind === "k",
  "old plain-string steps and new ones both read");

console.log(`steps: ${failed ? "FAILED" : "ok"}`);
process.exit(failed ? 1 : 0);
