/**
 * The only way this interface talks to the server.
 *
 * Deliberately ours rather than a dependency. `frappe-react-sdk` does roughly
 * this, but it is community-maintained and can lag a Frappe release -- and what
 * it wraps is two stable things: a session cookie and POST /api/method. Owning
 * fifty lines is cheaper than being blocked by someone else's release schedule.
 *
 * No tokens, no CORS, no second login: the browser arrives at /command-center
 * with a Frappe session and every call carries it.
 */

// The request token is read when each request is made, from the session's csrftoken
// cookie, which is renewed at sign-in -- a token captured once at page load would go
// stale and every request would be refused. The page's own copy is the fallback.
function csrfToken() {
  const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return (m && decodeURIComponent(m[1])) || window.csrf_token || null;
}

export class ApiError extends Error {
  constructor(message, { status, method, exc, excType } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.method = method;
    this.exc = exc;
    // The server's exception class. "WriteUnconfirmed" (HTTP 504): the business's ERPNext
    // did not confirm a change in time and it may have gone through -- say so, and do
    // not offer to do it again without checking (connectors/base.py WriteUnconfirmed).
    this.excType = excType;
  }

  get unconfirmed() {
    return this.excType === "WriteUnconfirmed";
  }
}

/** Call a whitelisted method. Everything the interface reads goes through here. */
export async function call(method, args = {}, { signal } = {}) {
  let res;
  try {
    res = await fetch(`/api/method/${method}`, {
      method: "POST",
      credentials: "same-origin",
      signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(csrfToken() ? { "X-Frappe-CSRF-Token": csrfToken() } : {}),
      },
      body: JSON.stringify(args),
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError("The server could not be reached.", { method });
  }

  // A session that expired mid-session must not look like empty data.
  if (res.status === 401 || res.status === 403) {
    throw new ApiError(
      res.status === 401
        ? "Your session has ended. Sign in again to continue."
        : "You do not have permission for this.",
      { status: res.status, method }
    );
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    throw new ApiError("The server returned something unreadable.", {
      status: res.status,
      method,
    });
  }

  if (!res.ok) {
    throw new ApiError(serverMessage(body) || `Request failed (${res.status}).`, {
      status: res.status,
      method,
      exc: body?.exc,
      excType: body?.exc_type,
    });
  }
  return body.message;
}

/**
 * Call a whitelisted method that answers with a file, and save it.
 *
 * Same session and CSRF token as call(). The file name comes from the server's
 * Content-Disposition, so it says what is in it and when.
 */
export async function download(method, args = {}, fallbackName = "export") {
  const res = await fetch(`/api/method/${method}`, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken() ? { "X-Frappe-CSRF-Token": csrfToken() } : {}),
    },
    body: JSON.stringify(args),
  });
  if (!res.ok) {
    let msg = `Export failed (${res.status}).`;
    try {
      msg = serverMessage(await res.json()) || msg;
    } catch {
      /* not JSON */
    }
    throw new ApiError(msg, { status: res.status, method });
  }
  const disposition = res.headers.get("Content-Disposition") || "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const name = m ? decodeURIComponent(m[1]) : fallbackName;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
  return name;
}

/**
 * Frappe reports errors in several shapes depending on how they were raised.
 * Pulling the human sentence out of them is worth doing once, here, rather than
 * letting a raw traceback reach a manager's screen.
 */
function serverMessage(body) {
  if (!body) return null;
  const raw = body._server_messages;
  if (raw) {
    try {
      const msgs = JSON.parse(raw).map((m) => {
        try {
          return JSON.parse(m).message;
        } catch {
          return m;
        }
      });
      if (msgs.length) return stripTags(msgs.join(" "));
    } catch {
      /* fall through */
    }
  }
  if (body.message && typeof body.message === "string") return stripTags(body.message);
  if (body.exception) return String(body.exception).split("\n")[0];
  return null;
}

/**
 * The text of a server message, without its markup. The message can carry a business's
 * ERPNext's own words (connectors/remote.py copies them in), so it is never written into
 * this page: an <img onerror> fires even on an element that is never attached. DOMParser
 * builds an inert document instead -- no script runs, no handler fires, nothing loads.
 */
export function stripTags(s) {
  const text = String(s ?? "");
  if (typeof DOMParser !== "undefined") {
    try {
      const doc = new DOMParser().parseFromString(text, "text/html");
      return (doc.body?.textContent || "").trim();
    } catch {
      /* fall through to the plain-text way */
    }
  }
  return text.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

/* ---------------------------------------------------------------------------
   The platform's endpoints, named. A typo becomes an import error here rather
   than a silent 404 at the moment a manager opens a screen.
   ------------------------------------------------------------------------- */
export const api = {
  businesses: () => call("command_center.api.businesses.get_visible_businesses"),

  facts: ({ fact, measures, group_by, filters, business_code, limit }) =>
    call("command_center.api.facts.query", {
      fact,
      measures,
      group_by,
      filters,
      business_code,
      limit,
    }),

  /* What is behind a figure: the summary, the concentration, the records. */
  records: ({ fact, filters, business_code, limit }) =>
    call("command_center.api.facts.records", { fact, filters, business_code, limit }),
  /* A promise split by what covers it: stock, on order, not ordered (api/coverage.py). */
  coverSummary: ({ business_code, late_only }) =>
    call("command_center.api.coverage.summary", { business_code, late_only: late_only ? 1 : 0 }),

  /* Figures. The screen names them; the server decides what they mean. */
  kpis: ({ keys, business_code }) =>
    call("command_center.api.kpi.get", { keys, business_code }),
  kpiCatalogue: () => call("command_center.api.kpi.catalogue"),
  /* A figure's drawer: what it is, what it should be, why, and what to do (api/insight.py). */
  insight: ({ key, business_code }, opts) =>
    call("command_center.api.insight.understand", { key, business_code }, opts),
  insightExplain: ({ key, business_code }) =>
    call("command_center.api.insight.explain", { key, business_code }),
  insightXlsx: (args) => download("command_center.api.insight.xlsx", args, "figure.xlsx"),
  /* The designed screens' charts and tables, by panel heading (api/panels.py). */
  panels: (view, business_code) => call("command_center.api.panels.get", { view, business_code }),
  /* Finances' financial statements, as the business's ERPNext draws them (api/statements.py). */
  statements: ({ business_code, period, from_date, to_date, section }) =>
    call("command_center.api.statements.get", { business_code, period, from_date, to_date, section }),
  kpiVerify: (business_code) => call("command_center.api.kpi.verify", { business_code }),

  /* The question box. Read-only: there is no path from here to actions.py. */
  ask: ({ question, business_code, history, ask_id }, opts) =>
    call("command_center.api.ask.answer", { question, business_code, history, ask_id }, opts),
  answerable: () => call("command_center.api.ask.answerable"),
  /* The lookups an ask has made so far, recorded under the id the page gave it. */
  askPoll: (ask_id, opts, deep = 0) => call("command_center.api.ask.poll", { ask_id, deep }, opts),

  /* Actions a manager takes, as themselves -- never the assistant (api/actions.py). */
  people: (business_code) => call("command_center.api.actions.people", { business_code }),
  /* Assigned on the ERPNext document when there is one, else a To-Do; either way the
     person is notified in ERPNext, and the answer says whether they were. */
  createTask: ({ business_code, subject, description, allocated_to, due_date, priority,
                 reference_type, reference_name, alert, escalate_of, escalate_todo }) =>
    call("command_center.api.actions.create_task",
      { business_code, subject, description, allocated_to, due_date, priority,
        reference_type, reference_name, alert, escalate_of, escalate_todo }),
  /* Escalate: who the work is with now, and their manager in ERPNext (Reports To). */
  whoseWork: ({ business_code, doctype, name, todo, alert }) =>
    call("command_center.api.actions.whose_work", { business_code, doctype, name, todo, alert }),
  managerOf: ({ business_code, user }) =>
    call("command_center.api.actions.manager_of", { business_code, user }),

  /* Conversations with the AI, kept per person on the server (api/conversations.py). */
  convRecent: (business_code) => call("command_center.api.conversations.recent", { business_code }),
  convLoad: (name) => call("command_center.api.conversations.load", { name }),
  convAdd: ({ question, payload, business_code, name, replace }) =>
    call("command_center.api.conversations.add",
      { question, payload: JSON.stringify(payload || {}), business_code, name, replace: replace ? 1 : 0 }),
  convRemove: (name) => call("command_center.api.conversations.remove", { name }),

  /* Report schedules (api/reports.py): when each report is written and who gets it. */
  schedules: (business_code) => call("command_center.api.reports.schedules", { business_code }),
  saveSchedule: (args) => call("command_center.api.reports.save_schedule", args),
  sendNow: ({ code, business_code }) => call("command_center.api.reports.send_now", { code, business_code }),

  /* Home's two lists (api/home.py). */
  homeDebtors: ({ business_code, mode }) => call("command_center.api.home.debtors", { business_code, mode }),
  topCustomers: ({ business_code }) => call("command_center.api.home.top_customers", { business_code }),

  /* Alerts (api/alerts.py): read, and what the manager decided about one. */
  alerts: (business_code) => call("command_center.api.alerts.open_alerts", { business_code }),
  alertAct: ({ name, action, reason, until, todo }) =>
    call("command_center.api.alerts.act", { name, action, reason, until, todo }),

  /* Recommendations (api/recommend.py): read, the bell's critical ones, and the decisions. */
  recommendations: (business_code) =>
    call("command_center.api.recommend.current", { business_code }),
  recCritical: (business_code) =>
    call("command_center.api.recommend.critical", { business_code }),
  recAct: ({ name, action, reason, days }) =>
    call("command_center.api.recommend.act", { name, action, reason, days }),

  /* Today, Approvals and Outstanding Tasks (api/work.py), and the decisions on them. */
  work: (business_code) => call("command_center.api.work.summary", { business_code }),
  decide: ({ business_code, doctype, name, action }) =>
    call("command_center.api.actions.apply_workflow_action", { business_code, doctype, name, action }),
  review: ({ business_code, todo, verdict, note }) =>
    call("command_center.api.work.review", { business_code, todo, verdict, note }),
  /* One task handed out, for its drawer: details, dates, document, comments. */
  task: ({ business_code, todo }) => call("command_center.api.work.task", { business_code, todo }),
  /* Managing work handed out, as the manager, in the business's ERPNext (api/actions). */
  reassignTask: ({ business_code, todo, to_user, note }) =>
    call("command_center.api.actions.reassign_task", { business_code, todo, to_user, note }),
  cancelTask: ({ business_code, todo, reason }) =>
    call("command_center.api.actions.cancel_task", { business_code, todo, reason }),
  closeTask: ({ business_code, todo, note }) =>
    call("command_center.api.actions.close_task", { business_code, todo, note }),
  /* Close or cancel many at once, one by one: {done: [...], failed: [{todo, reason}], said}. */
  bulkTasks: ({ business_code, action, todos, note }) =>
    call("command_center.api.actions.bulk_tasks", { business_code, action, todos, note }),
  updateTask: ({ business_code, todo, due_date, priority }) =>
    call("command_center.api.actions.update_task", { business_code, todo, due_date, priority }),

  /* Downloads. Reads only: nothing is written to the site, not even a File. */
  answerPdf: (args) => download("command_center.api.export.answer_pdf", args, "answer.pdf"),
  tablesXlsx: (args) => download("command_center.api.export.tables_xlsx", args, "tables.xlsx"),
  statementsPdf: (args) => download("command_center.api.statements.pdf", args, "statements.pdf"),
  recordsXlsx: (args) => download("command_center.api.export.records_xlsx", args, "records.xlsx"),

  /* The nine management reports: started as a job, followed until written. */
  reportGenerate: ({ code, business_code }) =>
    call("command_center.api.reports.generate", { code, business_code }),
  reportStatus: (job_id) => call("command_center.api.reports.status", { job_id }),
  /* Every run is kept on the server: each report's latest, a written one to read again,
     and this person's own -- finished and not yet seen, or still being written (the bell). */
  reportLatest: (business_code) => call("command_center.api.reports.latest", { business_code }),
  reportOpen: (run) => call("command_center.api.reports.open_run", { run }),
  reportMine: () => call("command_center.api.reports.mine"),
  reportSeen: (run) => call("command_center.api.reports.mark_seen", { run }),

  ingestStatus: () => call("command_center.api.ingest.status"),
  ingestHistory: (business_code) => call("command_center.api.ingest.history", { business_code }),
  /* Business Health's last eight weeks of stored snapshots (api/health.py). */
  healthHistory: (business_code) => call("command_center.api.health.history", { business_code }),
  /* The Executive Summary's memo (api/summary.py): the memo, Waiting On You read on its own
     so the memo never waits on ERPNext, and today's AI paragraph, written when it is not. */
  summaryMemo: (business_code) => call("command_center.api.summary.memo", { business_code }),
  summaryWaiting: (business_code) => call("command_center.api.summary.waiting", { business_code }),
  summaryWrite: (business_code) => call("command_center.api.summary.write", { business_code }),
  ingestRefresh: (business_code) => call("command_center.api.ingest.refresh", { business_code }),
  reconcile: (business_code) =>
    call("command_center.api.ingest.reconcile", { business_code }),
};

/* ---------------------------------------------------------------------------
   Settings (insights/core/platform_settings.py): the platform administrator's
   screen. Every call is refused by the server to anyone who is not one. Secrets
   go in only; nothing here ever reads one back.
   ------------------------------------------------------------------------- */
const PS = "insights.core.platform_settings";
export const settingsApi = {
  people: () => call(`${PS}.people`),
  addPerson: (args) => call(`${PS}.add_person`, args),
  updatePerson: (username, full_name) => call(`${PS}.update_person`, { username, full_name }),
  setManager: (username, on) => call(`${PS}.set_manager`, { username, on: on ? 1 : 0 }),
  setAdmin: (username, on) => call(`${PS}.set_admin`, { username, on: on ? 1 : 0 }),
  setActive: (username, on) => call(`${PS}.set_active`, { username, on: on ? 1 : 0 }),
  resetPassword: (args) => call(`${PS}.reset_password`, args),
  sendSetPasswordLink: (username) => call(`${PS}.send_set_password_link`, { username }),

  businesses: () => call(`${PS}.businesses`),
  addBusiness: (args) => call(`${PS}.add_business`, args),
  updateBusiness: (args) => call(`${PS}.update_business`, args),
  testBusiness: (name) => call(`${PS}.test_business`, { name }),
  setPaused: (name, paused) => call(`${PS}.set_paused`, { name, paused: paused ? 1 : 0 }),
  reloadBusiness: (name) => call(`${PS}.reload_business`, { name }),
  checkFigures: (name) => call(`${PS}.check_figures`, { name }),

  claude: () => call(`${PS}.claude`),
  setClaudeKey: (key) => call(`${PS}.set_claude_key`, { key }),
  checkClaude: () => call(`${PS}.check_claude`),

  credentials: () => call(`${PS}.credentials`),
  setCredential: (args) => call(`${PS}.set_credential`, args),
  removeCredential: (name) => call(`${PS}.remove_credential`, { name }),
  testCredential: (name) => call(`${PS}.test_credential`, { name }),

  changes: () => call(`${PS}.changes`),
};

/* Settings access for delegates, Email and the Notifications status. Delegated calls
   are refused by the server unless the administrator gave that section. */
Object.assign(settingsApi, {
  setSettingsAccess: (username, sections) =>
    call(`${PS}.set_settings_access`, { username, sections: JSON.stringify(sections) }),

  email: () => call(`${PS}.email`),
  setEmail: (args) => call(`${PS}.set_email`, args),
  testEmail: (to) => call(`${PS}.test_email`, { to }),
  emailLog: (status) => call(`${PS}.email_log`, { status: status || "" }),
  resendEmail: (id) => call(`${PS}.resend_email`, { id }),
  notifications: () => call(`${PS}.notifications`),

  recommend: (business_code) => call(`${PS}.recommendations`, { business_code }),
  setRecommend: ({ business_code, rules, digest, brief, anomalies, ai_review }) =>
    call(`${PS}.set_recommendations`, { business_code, rules: JSON.stringify(rules || {}),
      digest: digest === undefined ? undefined : digest ? 1 : 0,
      brief: brief === undefined ? undefined : brief ? 1 : 0,
      anomalies: anomalies === undefined ? undefined : anomalies ? 1 : 0,
      ai_review: ai_review === undefined ? undefined : ai_review ? 1 : 0 }),
  writeBriefNow: (business_code) => call(`${PS}.write_brief_now`, { business_code }),
  runReviewNow: (business_code) => call(`${PS}.run_review_now`, { business_code }),
});

/* Branding (administrator only) and a business's co-brand (Businesses). Logos are sent
   as data: URLs; the server checks what they are, never trusting the file's name. */
Object.assign(settingsApi, {
  brand: () => call(`${PS}.brand`),
  setBrand: (args) => call(`${PS}.set_brand`, args),
  uploadBrandLogo: (kind, data) => call(`${PS}.upload_brand_logo`, { kind, data }),
  removeBrandLogo: (kind) => call(`${PS}.remove_brand_logo`, { kind }),
  setBusinessBrand: (name, display_name) => call(`${PS}.set_business_brand`, { name, display_name }),
  uploadBusinessLogo: (name, data) => call(`${PS}.upload_business_logo`, { name, data }),
  removeBusinessLogo: (name) => call(`${PS}.remove_business_logo`, { name }),
  setReportStyle: (name, style, credit) =>
    call(`${PS}.set_business_report_style`, { name, style, credit }),
  uploadLetterhead: (name, part, data) =>
    call(`${PS}.upload_business_letterhead`, { name, part, data }),
  removeLetterhead: (name, part) => call(`${PS}.remove_business_letterhead`, { name, part }),
  previewReportStyle: (name, style, credit) =>
    call(`${PS}.preview_report_style`, { name, style, credit }),
});

/* Settings -> Security (insights/core/security.py): the platform administrator's only,
   never given to anyone else; the server refuses every call to anyone who is not one. */
const SEC = "insights.core.security";
export const securityApi = {
  overview: () => call(`${SEC}.overview`),
  signIns: (days) => call(`${SEC}.sign_ins`, { days }),
  unlock: (kind, username, ip) => call(`${SEC}.unlock`, { kind, username, ip }),
  sessions: () => call(`${SEC}.sessions`),
  signOutEverywhere: (username) => call(`${SEC}.sign_out_everywhere`, { username }),
  changes: () => call(`${SEC}.changes`),
  watch: (status) => call(`${SEC}.watch`, { status }),
  runWatch: (business_code) => call(`${SEC}.run_watch`, { business_code }),
  acknowledge: (id) => call(`${SEC}.acknowledge`, { id }),
  incidents: () => call(`${SEC}.incidents`),
  incident: (id) => call(`${SEC}.incident`, { id }),
  openIncident: (args) =>
    call(`${SEC}.open_incident`, { ...args, businesses: JSON.stringify(args.businesses || []) }),
  updateIncident: (args) =>
    call(`${SEC}.update_incident`, {
      ...args, businesses: args.businesses ? JSON.stringify(args.businesses) : undefined,
    }),
  setIncidentStatus: (id, status, note) => call(`${SEC}.set_incident_status`, { id, status, note }),
  addIncidentNote: (id, text) => call(`${SEC}.add_incident_note`, { id, text }),
  linkFinding: (id, finding_id) => call(`${SEC}.link_finding`, { id, finding_id }),
  incidentPdf: (id) => download(`${SEC}.incident_pdf`, { id }, "incident-report.pdf"),
  incidentXlsx: (id) => download(`${SEC}.incident_xlsx`, { id }, "incident-events.xlsx"),
  posture: () => call(`${SEC}.posture`),
};

export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
/* What the PDF engine can draw: it cannot draw WebP. */
export const PRINT_TYPES = ["image/png", "image/jpeg"];

/** A chosen file as a data: URL, refused here first if it is plainly too large or not
 *  one of `types` (the server checks again, by content). */
export function readImage(file, maxKb = 1024, types = IMAGE_TYPES) {
  return new Promise((resolve, reject) => {
    if (!file) return reject(new Error("Choose an image file."));
    if (!types.includes(file.type)) {
      return reject(new Error(types.includes("image/webp")
        ? "Choose a PNG, JPEG or WebP image. SVG is not accepted."
        : "Choose a PNG or JPEG image. PDFs cannot show WebP, and SVG is not accepted."));
    }
    if (file.size > maxKb * 1024) {
      return reject(new Error(`That image is too large. The most it may be is ${maxKb} KB.`));
    }
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ""));
    r.onerror = () => reject(new Error("That file could not be read."));
    r.readAsDataURL(file);
  });
}

/* ---------------------------------------------------------------------------
   Plans, licences and usage (insights/core/plans.py). A customer's Account
   Managers read their own plan and counts; everything with money in it is the
   administrator's, and the server refuses it to anyone else.
   ------------------------------------------------------------------------- */
const PL = "insights.core.plans";
export const plansApi = {
  mine: (client_id) => call(`${PL}.my_plan`, { client_id }),
  tiers: () => call(`${PL}.plans`),
  requestQuote: (args) => call(`${PL}.request_quote`, args),
  statementPdf: (client_id, period) =>
    download(`${PL}.usage_statement`, { client_id, period, format: "pdf" }, "usage-statement.pdf"),
  statementXlsx: (client_id, period) =>
    download(`${PL}.usage_statement`, { client_id, period, format: "xlsx" }, "usage-statement.xlsx"),
  notices: () => call(`${PL}.notices`),
  dismiss: (id) => call(`${PL}.dismiss_notice`, { id }),

  customers: () => call(`${PL}.customers`),
  saveCustomer: (args) =>
    call(`${PL}.save_customer`, {
      ...args,
      limits: JSON.stringify(args.limits || {}),
      rates: JSON.stringify(args.rates || {}),
      businesses: JSON.stringify(args.businesses || []),
    }),
  extend: (id, days) => call(`${PL}.extend_licence`, { id, days }),
  remove: (id) => call(`${PL}.remove_customer`, { id }),
  setMember: (args) => call(`${PL}.set_member`, args),
  correction: (args) => call(`${PL}.record_correction`, args),
  billing: (id, period) => call(`${PL}.billing_statement`, { id, period }),
  billingPdf: (id, period) =>
    download(`${PL}.billing_statement`, { id, period, format: "pdf" }, "usage-statement.pdf"),
  billingXlsx: (id, period) =>
    download(`${PL}.billing_statement`, { id, period, format: "xlsx" }, "usage-statement.xlsx"),
  planSettings: () => call(`${PL}.plan_settings`),
  savePlan: (args) =>
    call(`${PL}.save_plan`, {
      ...args,
      limits: JSON.stringify(args.limits || {}),
      overage: JSON.stringify(args.overage || {}),
    }),
  savePrices: (prices) => call(`${PL}.save_prices`, { prices: JSON.stringify(prices || {}) }),
  clientChoices: () => call(`${PL}.client_choices`),
};
