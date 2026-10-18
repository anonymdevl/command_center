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
};

function figure(key) {
  const k = KPIS[key];
  if (!k) return null;
  const [label, unit, value, direction, fact] = k;
  return {
    key,
    label,
    value,
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
  "command_center.api.ask.answer": ({ question }) => ({
    answered: true,
    format: "markdown",
    mode: "analyst",
    planner: "gemini",
    model: "gemini-2.5-flash",
    question,
    answer: [
      `**Preview answer to “${question}”** — on the live site Gemini answers from the records.`,
      "",
      "Customers owe **GHS 9,177,568.91** across **806 unpaid invoices**, and **73.8%** of it " +
        "(GHS 6,777,142.92) is more than 90 days old, measured against 19 Aug 2025.",
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
    ].join("\n"),
    checked: [
      'get_figures({"keys":["ar_total","ar_count","ar_over_90"]})',
      'query_data({"fact":"fact_sales_invoice","group_by":["customer"],"limit":10})',
      'trend({"fact":"fact_payment_allocation","measure":"allocated_amount","period":"month"})',
    ],
    records: { fact: "fact_sales_invoice", filters: {} },
  }),
  // The same list engine.ANALYST_EXAMPLES serves on the site (copied: there is no
  // server here to ask).
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

  // A short delay so loading states are visible, as they are on the real site.
  // ?slow=N holds answers for N seconds, to look at the analyst's waiting state.
  const slow = Number(new URLSearchParams(window.location.search).get("slow") || 0);
  await new Promise((r) => setTimeout(r, method.endsWith("ask.answer") && slow ? slow * 1000 : 120));
  if (init.signal?.aborted) throw new DOMException("aborted", "AbortError");

  if (!handler) {
    console.warn(`[preview] no sample answer for ${method}`);
    return json(417, { message: `Preview has no sample data for ${method}.` });
  }
  return json(200, { message: handler(args) });
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
