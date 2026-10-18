/**
 * The interface, offline, for looking at it.
 *
 * Restyling nineteen screens one deploy at a time means every visual check costs a
 * push, a pull and a restart on Biomed. So preview.html loads this first: it answers
 * the platform's endpoints in the browser and the real App renders on top of it --
 * the same components, the same views.json, the same hydrator. Nothing in src/ knows
 * it is here.
 *
 * Never shipped. Only preview.html imports this file, and vite builds index.html
 * alone, so it cannot reach the bundle; preflight fails the build if the marker below
 * ever appears in the built output.
 *
 * The figures are Biomed's, verified on the live site at the data horizon and recorded
 * in CLAUDE.md. Two KPIs have no recorded value (stock_reserved_qty, order_book_late),
 * so they come back as null -- which also shows how a card looks when a figure cannot
 * be computed, rather than inventing one. Customers in the records drawer are samples
 * and named as such.
 */

export const PREVIEW_MARKER = "CC_PREVIEW_MOCK";

// ?theme=light&accent=cobalt -- so a screenshot run can pin the look without clicking.
// Written where appearance.js reads it, before the app starts.
{
  const q = new URLSearchParams(window.location.search);
  for (const [param, key] of [["theme", "icc-theme"], ["accent", "icc-accent"], ["signal", "icc-signal"]]) {
    const v = q.get(param);
    if (v) {
      try {
        localStorage.setItem(key, v);
      } catch {
        /* private window: the default applies */
      }
    }
  }
}

const AS_OF = { date: "2025-08-19", basis: "data_horizon" };
const BUSINESS = "GIGMANN";

window.CC_BOOT = {
  user: {
    id: "preview@gigmann.local",
    name: "Kofi Mensah",
    initials: "KM",
    roles: ["Command Center Manager"],
  },
  site: "preview",
  businesses: [
    {
      business_code: BUSINESS,
      business_name: "Gigmann Medical Supplies Ltd",
      is_local: 1,
      status: "Active",
      currency: "GHS",
      erpnext_company: "Gigmann Medical Supplies Ltd",
      site_url: null,
      last_sync: "2025-08-19 06:00:00",
      can_act: true,
      can_read: true,
      acts_at: null,
    },
  ],
  scopes: [
    { code: "__all__", label: "All businesses" },
    { code: BUSINESS, label: "Gigmann Medical Supplies Ltd" },
  ],
  as_of: AS_OF,
};

/* key: [label, unit, value, direction, fact] -- values from CLAUDE.md, verified live. */
const KPIS = {
  ar_total: ["Owed to us", "currency", 9177568.91, "higher_is_worse", "fact_sales_invoice"],
  ar_count: ["Unpaid invoices", "count", 806, "neutral", "fact_sales_invoice"],
  order_book: ["Promised, not delivered", "currency", 9131894.14, "neutral", "fact_sales_order"],
  order_book_late: ["Open orders", "count", null, "higher_is_worse", "fact_sales_order"],
  stock_value: ["Stock on hand", "currency", 3769970.49, "neutral", "fact_stock_balance"],
  stock_reserved_qty: ["Reserved against orders", "quantity", null, "neutral", "fact_stock_balance"],
  ap_total: ["We owe suppliers", "currency", 5645271.09, "higher_is_worse", "fact_purchase_invoice"],
  tasks_open: ["Work in flight", "count", 57, "neutral", "fact_task"],
  cases_open: ["Open complaints", "count", 39, "higher_is_worse", "fact_case"],
  people_total: ["On the books", "count", 35, "neutral", "fact_person"],
  headcount: ["People employed", "count", 24, "neutral", "fact_person"],
  departments: ["Departments", "count", 11, "neutral", "fact_person"],
  // The windowed and leader figures (18 Oct 2026), at the designed extract's values.
  // The live site computes them; these only let the cards be looked at here.
  order_book_count: ["Open orders", "count", 4, "neutral", "fact_sales_order", "worth GHS 84,950.00 still to deliver"],
  cash_in_month: ["Money in, last full month", "currency", 1182400, "higher_is_better", "fact_payment_allocation", "July 2025, matched to invoices"],
  days_to_pay: ["Days paid after the due date", "days", 41, "higher_is_worse", "fact_payment_allocation", "after the due date, on average, May – Jul 2025"],
  revenue_last_month: ["Invoiced, last full month", "currency", 1550000, "higher_is_better", "fact_sales_invoice_line", "July 2025"],
  revenue_best_month: ["Best month invoiced", "currency", 3190000, "higher_is_better", "fact_sales_invoice_line", "June 2025"],
  invoices_draft: ["Invoices never issued", "count", 88, "higher_is_worse", "fact_sales_invoice", "worth GHS 903,632.00, in no total"],
  supplier_top_share: ["Top supplier", "percent", 57, "higher_is_worse", "fact_purchase_invoice_line", "CYNSEL (sample), of all supplier spend"],
  supplier_top2_share: ["Top two suppliers", "percent", 95, "higher_is_worse", "fact_purchase_invoice_line", "CYNSEL and MEDISOURCE (sample)"],
  stock_worst_shortfall: ["Worst shortfall", "quantity", 39941, "higher_is_worse", "fact_stock_balance", "5ml syringes (sample)"],
  stock_lines_promised: ["Lines promised", "count", 771, "neutral", "fact_stock_balance", "with stock reserved against them"],
  tasks_longest_wait: ["Longest wait", "days", 850, "higher_is_worse", "fact_task", "Samkwarth lab setup (sample)"],
  engineers: ["Engineers", "count", 3, "neutral", "fact_person", "active, by job title"],
  people_left: ["Left", "count", 8, "higher_is_worse", "fact_person", "average stay 213 days"],
  cases_closed: ["Closed", "count", 2, "higher_is_better", "fact_case", "resolved and closed"],
  cases_avg_wait: ["Average wait", "days", 12, "higher_is_worse", "fact_case", "on 39 open cases"],
};

function figure(key) {
  const k = KPIS[key];
  if (!k) return null;
  const [label, unit, value, direction, fact, note] = k;
  return {
    key,
    label,
    value,
    note: note || "",
    unit,
    direction,
    currency: unit === "currency" ? "GHS" : null,
    mixed_currency: false,
    scope: BUSINESS,
    as_of: AS_OF,
    basis: null,
    drill: { fact, filters: {} },
    data_status: {
      state: "stale",
      days_behind: null,
      message: "Preview: Biomed's figures at the data horizon, not a live read.",
    },
  };
}

const SAMPLE_CUSTOMERS = [
  ["Northbridge Clinic (sample)", 418950, 6],
  ["Akwaaba Medical Centre (sample)", 301600, 4],
  ["Coastline Diagnostics (sample)", 276500, 3],
  ["St. Anne's Hospital (sample)", 97410, 2],
];

function records(fact) {
  const total = SAMPLE_CUSTOMERS.reduce((s, c) => s + c[1], 0);
  return {
    fact,
    noun: "record",
    currency: "GHS",
    summary: {
      count: SAMPLE_CUSTOMERS.length,
      shown: SAMPLE_CUSTOMERS.length,
      total,
      measure_word: "sample values",
      top_share: 75,
      dimension_word: "customer",
      concentration: SAMPLE_CUSTOMERS.map(([label, value, count]) => ({
        label,
        value,
        count,
        share: Math.round((value / total) * 1000) / 10,
      })),
    },
    columns: [
      { key: "src_name", label: "Document", type: "doc" },
      { key: "customer", label: "Customer", type: "text" },
      { key: "posting_date", label: "Date", type: "date" },
      { key: "days_late", label: "Days late", type: "days" },
      { key: "outstanding", label: "Outstanding", type: "currency" },
    ],
    rows: SAMPLE_CUSTOMERS.map(([customer, outstanding], i) => ({
      src_doctype: "Sales Invoice",
      src_name: `SAMPLE-INV-${1001 + i}`,
      open_url: null,
      customer,
      posting_date: "2025-05-0" + (i + 2),
      days_late: [118, 47, 96, 12][i],
      outstanding,
    })),
  };
}

const REPORT_TITLES = { rp01: "Executive Summary", rp02: "Weekly management report",
  rp03: "Monthly report", rp04: "Board report", rp05: "Sales and Payments",
  rp06: "Buying and stock", rp07: "Engineering", rp08: "People", rp09: "Compliance and audit" };
const reportPolls = {};
const askStarted = {};
const deepStarted = {};

// A lookup is answered in its own shape: a sentence and a table, no cards or charts.
const LOOKUP_SAMPLE = (question) => ({
  answered: true, format: "markdown", mode: "analyst", planner: "gemini",
  model: "gemini-3.8-flash", question,
  notice: "Preview only — no AI is connected on this laptop. This is the sample for a " +
    "lookup question; on the live site Gemini answers each question from your data.",
  answer: [
    "There are **13 active users** in ERPNext; 4 more accounts are disabled.",
    "",
    "| User | Role profile | Last login |",
    "|---|---|---|",
    "| Kofi Mensah (sample) | Chief Executive | 18 Oct 2026 |",
    "| Ama Owusu (sample) | Finance Manager | 17 Oct 2026 |",
    "| Yaw Boateng (sample) | Stock Manager | 16 Oct 2026 |",
    "",
    "```followups",
    JSON.stringify(["Which users have not logged in for 30 days?", "Who can approve purchase orders?"]),
    "```",
  ].join("\n"),
  checked: ["(sample) the live site lists the lookups Gemini actually made"],
});

const HANDLERS = {
  "command_center.api.kpi.get": ({ keys }) =>
    Object.fromEntries((keys || []).map((k) => [k, figure(k)]).filter(([, f]) => f)),
  "command_center.api.businesses.get_visible_businesses": () => ({
    businesses: window.CC_BOOT.businesses,
    scopes: window.CC_BOOT.scopes,
  }),
  "command_center.api.facts.records": ({ fact }) => records(fact),
  // The shape the analyst returns, so the formatted answer can be looked at offline.
  // The figures are Biomed's verified ones; the customer rows are the samples above.
  "command_center.api.ask.answer": ({ question }) => (/^(how many|show|list|who is)/i.test(question || "")
    ? LOOKUP_SAMPLE(question) : {
    answered: true,
    format: "markdown",
    mode: "analyst",
    planner: "gemini",
    model: "gemini-2.5-flash",
    question,
    answer: [
      "Customers owe **GHS 9.18M** across **806 unpaid invoices**, and nearly three quarters of " +
        "it is more than 90 days old — a collection problem, not a sales one. *(Preview: on the " +
        "live site Gemini answers from the records.)*",
      "",
      "```figures",
      JSON.stringify([
        { label: "Owed to us", value: "GHS 9.18M", note: "806 unpaid invoices", tone: "bad" },
        { label: "Over 90 days", value: "73.8%", note: "GHS 6.78M", tone: "warn" },
        { label: "We owe suppliers", value: "GHS 5.65M", note: "122 bills" },
      ]),
      "```",
      "",
      "```chart",
      JSON.stringify({ type: "bar", title: "Largest balances (sample customers)", unit: "GHS",
        labels: SAMPLE_CUSTOMERS.map((c) => c[0].replace(" (sample)", "")),
        series: [{ name: "Owed", values: SAMPLE_CUSTOMERS.map((c) => c[1]) }] }),
      "```",
      "",
      "## Largest balances",
      "| Customer | Owed (GHS) | Invoices | Oldest |",
      "|---|---:|---:|---:|",
      ...SAMPLE_CUSTOMERS.map(([n, v, c], i) => `| ${n} | ${v.toLocaleString("en-GB")} | ${c} | ${[118, 47, 96, 12][i]} days |`),
      "",
      "**Projection:** at the last six months' collection rate the over-90 share stays above " +
        "70% through November — indicative only, it assumes the recent pattern continues.",
      "",
      "- **Recommendation:** Finance to agree payment dates with the three largest debtors this week.",
      "- **Recommendation:** Hold new credit for customers more than 90 days overdue until a plan is agreed.",
      "",
      "```followups",
      JSON.stringify(["Which of these customers has not paid in 90 days?",
        "How does what we are owed compare with a year ago?", "What do we owe our suppliers?"]),
      "```",
    ].join("\n"),
    // Said on the answer itself: on 18 Oct this fixed sample was read as the AI giving
    // the same answer to every question. The server never sends a notice.
    notice: "Preview only — no AI is connected on this laptop, so every question shows this " +
      "same sample answer to demonstrate the layout. On the live site Gemini reads each " +
      "question and looks up what that question needs.",
    checked: [
      "(sample) the live site lists the lookups Gemini actually made for this question",
    ],
    records: { fact: "fact_sales_invoice", filters: {} },
  }),
  // The same list engine.ANALYST_EXAMPLES serves on the site (copied: there is no
  // server here to ask).
  // Live steps, as on the site: the answer request is still working while poll() reads
  // the steps recorded under its ask_id.
  "command_center.api.ask.poll": ({ ask_id, deep }) => {
    if (deep) {
      // A deeper look: three more steps over a few seconds, then the fuller answer.
      const d0 = deepStarted[ask_id];
      if (!d0) return { state: "unknown", steps: [] };
      const n = Math.floor((Date.now() - d0) / 1500);
      const steps = ["Running ERPNext's Profit and Loss Statement", "Working out the trend in sales invoices",
        "Adding up sales orders by month"].slice(0, Math.min(3, n + 1));
      if (n < 4) return { state: "running", steps };
      const full = HANDLERS["command_center.api.ask.answer"]({ question: "growth" });
      return { state: "done", steps, result: { ...full, deepened: true,
        notice: "Preview only — this stands in for the fuller answer a deeper look produces." } };
    }
    const t0 = askStarted[ask_id];
    if (!t0) return { state: "unknown", steps: [] };
    const n = Math.min(3, 1 + Math.floor((Date.now() - t0) / 700));
    return { state: "running", steps: ["Reading the headline figures",
      "Adding up sales invoices by customer", "Working out the trend in customer payments"].slice(0, n) };
  },
  // Reports: a job that is "done" on the second poll, with the sample answer as its text.
  "command_center.api.reports.generate": ({ code }) => {
    reportPolls[code] = 0;
    return { job_id: `preview-${code}`, title: REPORT_TITLES[code] || code };
  },
  "command_center.api.reports.status": ({ job_id }) => {
    const code = job_id.replace("preview-", "");
    if ((reportPolls[code] = (reportPolls[code] || 0) + 1) < 2) return { state: "running" };
    const r = HANDLERS["command_center.api.ask.answer"]({ question: REPORT_TITLES[code] });
    return { state: "done", report: { ...r, title: REPORT_TITLES[code], code,
      generated: new Date().toISOString() } };
  },
  "command_center.api.ask.answerable": () => ({
    mode: "analyst",
    examples: [
      { q: "How did sales trend over the last 12 months, and where are we heading?", area: "Sales" },
      { q: "Who owes us the most, and how long have they owed it?", area: "Money owed" },
      { q: "Which suppliers do we depend on most, and what if one stopped?", area: "Buying" },
      { q: "What stock is promised to customers but not on the shelves?", area: "Stock" },
      { q: "Which installation jobs are running late, and who has them?", area: "Projects" },
      { q: "Show our open quotations and their total value.", area: "Sales" },
      { q: "Which customers buy the most from us, and what do they buy?", area: "Customers" },
      { q: "What should I raise with UBUNTU before our call?", area: "Briefing" },
    ],
  }),
  // The action dialog. The preview has no ERPNext, so the To-Do is not created --
  // the name it returns says so rather than looking like a real record.
  "command_center.api.actions.people": () => [
    { user: "akosua@gigmann.example", name: "Akosua Boateng" },
    { user: "kwame@gigmann.example", name: "Kwame Mensah" },
    { user: "efua@gigmann.example", name: "Efua Owusu" },
  ],
  "command_center.api.actions.create_task": ({ subject }) => ({ name: "preview-only", subject }),
  // Today, Approvals and Outstanding Tasks. Sample people and documents, marked so.
  "command_center.api.work.summary": () => {
    const fig = (key, label, value, note) => ({ key, label, value, unit: "count", note,
      currency: null, as_of: { date: "2026-10-18", basis: "today" },
      drill: { href: "/app/todo" }, data_status: { state: "live" } });
    const approvals = [
      { doctype: "Purchase Order", name: "PUR-ORD-2025-00231", title: "Medi-Source Ghana (sample)",
        state: "Pending Approval", actions: ["Approve", "Reject"], value: 48200,
        raised_by: "Ama Owusu (sample)", raised: "2026-10-06", waiting_days: 12, url: "/app/purchase-order" },
      { doctype: "Sales Invoice", name: "ACC-SINV-2025-00870", title: "A1 MEDICALSUPPLIES (sample)",
        state: "Awaiting CEO", actions: ["Approve", "Send back"], value: 11000,
        raised_by: "Yaw Boateng (sample)", raised: "2026-10-16", waiting_days: 2, url: "/app/sales-invoice" },
    ];
    const open = [
      { name: "td-01", title: "Get a payment plan from HAIRASH ENTERPRISE (sample)", status: "Open", priority: "High",
        date: "2026-09-26", late_days: 22, to: "kwame@gigmann.example", to_name: "Kwame Mensah (sample)", url: "/app/todo" },
      { name: "td-02", title: "Count the 5ml syringes in Kumasi (sample)", status: "Open", priority: "Medium",
        date: "2026-10-25", late_days: 0, to: "efua@gigmann.example", to_name: "Efua Owusu (sample)", url: "/app/todo" },
    ];
    const check = [
      { name: "td-03", title: "Confirm the C-arm installation date with UBUNTU (sample)", detail: "Called them; installation booked for 4 November.",
        status: "Closed", priority: "Medium", date: "2026-10-10", closed_on: "2026-10-15",
        to: "akosua@gigmann.example", to_name: "Akosua Boateng (sample)", url: "/app/todo" },
    ];
    const late = open.filter((t) => t.late_days > 0);
    return { available: true, currency: "GHS", approvals, open, late, check, mine: [],
      figures: {
        work_awaiting: fig("work_awaiting", "Awaiting you", 2, "GHS 59,200 involved"),
        work_due_today: fig("work_due_today", "Due today", 0, "on your own list, today or earlier"),
        work_to_check: fig("work_to_check", "Evidence to check", 1, "marked done in the last 14 days"),
        work_unkept: fig("work_unkept", "Promises unkept", 1, "oldest is 22 days late"),
        work_open: fig("work_open", "Still open", 2, "work you handed out"),
        work_late: fig("work_late", "Late", 1, "past the date you set"),
        work_high: fig("work_high", "High risk", 1, "marked high priority"),
      } };
  },
  "command_center.api.actions.apply_workflow_action": () => ({ workflow_state: "Approved (preview)" }),
  "command_center.api.work.review": () => ({ ok: true }),
  "command_center.api.ingest.status": () => [],
};

const realFetch = window.fetch.bind(window);

window.fetch = async (input, init = {}) => {
  const url = typeof input === "string" ? input : input.url;
  const m = url.match(/\/api\/method\/([\w.]+)/);
  if (!m) return realFetch(input, init);

  const method = m[1];
  let args = {};
  try {
    args = JSON.parse(init.body || "{}");
  } catch {
    /* no args */
  }
  const handler = HANDLERS[method];
  const json = (status, body) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });

  // A short delay so loading states are visible, as they are on the real site. An ask
  // with an ask_id takes a couple of seconds, long enough for its steps to show;
  // ?slow=N holds it for N.
  const slow = Number(new URLSearchParams(window.location.search).get("slow") || 0);
  if (method.endsWith("ask.answer") && args.ask_id) askStarted[args.ask_id] = Date.now();
  const deepen = method.endsWith("ask.answer") && args.ask_id && /grow|forecast|deeper/i.test(args.question || "");
  const askWait = method.endsWith("ask.answer") ? (slow ? slow * 1000 : args.ask_id ? 2400 : 120) : 120;
  await new Promise((r) => setTimeout(r, askWait));
  if (init.signal?.aborted) throw new DOMException("aborted", "AbortError");

  if (!handler) {
    console.warn(`[preview] no sample answer for ${method}`);
    return json(417, { message: `Preview has no sample data for ${method}.` });
  }
  const out = handler(args);
  if (deepen && out && typeof out === "object") {
    // A big question: the first pass comes back cut short and a deeper look carries on.
    deepStarted[args.ask_id] = Date.now();
    return json(200, { message: { ...out, cut_short: true, deep: { ask_id: args.ask_id } } });
  }
  return json(200, { message: out });
};

console.info(`[preview] ${PREVIEW_MARKER}: sample API active, nothing reaches a server`);

/**
 * ?audit=1 -- walk every screen and record what does not fit.
 *
 * "Text spilling out of a card" was the most repeated complaint of the first build,
 * and it is only ever found by looking. This finds it by measuring: any card, tile,
 * label, tag or footnote whose content is wider than its box, and any screen that
 * scrolls sideways. The result is written into <pre id="cc-audit"> so a headless
 * browser can read it with --dump-dom.
 */
if (new URLSearchParams(window.location.search).get("audit")) {
  const VIEWS = ["command", "brief", "myday", "ops", "health", "risk", "approvals",
    "delegation", "ask", "reports", "sales", "proc", "inv", "eng", "cx", "fin", "hr", "it", "aud"];
  const SEL = ".kpis,.kpi,.khead,.lab,.val,.delta,.bk,.l,.n,.v,.flag,.panel,.ph,.tag,.chip,.btn,.navi";
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const describe = (el) =>
    `${el.className.toString().split(" ")[0]} "${(el.textContent || "").trim().slice(0, 40)}"`;

  window.addEventListener("load", async () => {
    await wait(600);
    const report = {};
    for (const v of VIEWS) {
      window.location.hash = v;
      await wait(500);
      const main = document.getElementById("cc-main");
      const over = [];
      main?.querySelectorAll(SEL).forEach((el) => {
        // Ellipsis is a deliberate choice of the design; a clipped box that says so
        // is not a spill. Everything else wider than itself is.
        const cs = getComputedStyle(el);
        if (cs.textOverflow === "ellipsis") return;
        if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0)
          over.push(`${describe(el)} ${el.scrollWidth}>${el.clientWidth}`);
      });
      const sideways = main && main.scrollWidth > main.clientWidth + 1;
      if (over.length || sideways) report[v] = { sideways, over: over.slice(0, 12), count: over.length };
    }
    const pre = document.createElement("pre");
    pre.id = "cc-audit";
    pre.textContent = JSON.stringify({ width: window.innerWidth, report });
    document.body.append(pre);
  });
}
