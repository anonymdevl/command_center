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

const CSRF = window.csrf_token || null;

export class ApiError extends Error {
  constructor(message, { status, method, exc } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.method = method;
    this.exc = exc;
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
        ...(CSRF ? { "X-Frappe-CSRF-Token": CSRF } : {}),
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
      ...(CSRF ? { "X-Frappe-CSRF-Token": CSRF } : {}),
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

function stripTags(s) {
  const d = document.createElement("div");
  d.innerHTML = s;
  return (d.textContent || "").trim();
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

  /* Figures. The screen names them; the server decides what they mean. */
  kpis: ({ keys, business_code }) =>
    call("command_center.api.kpi.get", { keys, business_code }),
  kpiCatalogue: () => call("command_center.api.kpi.catalogue"),
  kpiVerify: (business_code) => call("command_center.api.kpi.verify", { business_code }),

  /* The question box. Read-only: there is no path from here to actions.py. */
  ask: ({ question, business_code, history, ask_id }, opts) =>
    call("command_center.api.ask.answer", { question, business_code, history, ask_id }, opts),
  answerable: () => call("command_center.api.ask.answerable"),
  /* The lookups an ask has made so far, recorded under the id the page gave it. */
  askPoll: (ask_id, opts, deep = 0) => call("command_center.api.ask.poll", { ask_id, deep }, opts),

  /* Actions a manager takes, as themselves -- never the assistant (api/actions.py). */
  people: (business_code) => call("command_center.api.actions.people", { business_code }),
  createTask: ({ business_code, subject, description, allocated_to, due_date, priority,
                 reference_type, reference_name }) =>
    call("command_center.api.actions.create_task",
      { business_code, subject, description, allocated_to, due_date, priority,
        reference_type, reference_name }),

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

  /* Today, Approvals and Outstanding Tasks (api/work.py), and the decisions on them. */
  work: (business_code) => call("command_center.api.work.summary", { business_code }),
  decide: ({ business_code, doctype, name, action }) =>
    call("command_center.api.actions.apply_workflow_action", { business_code, doctype, name, action }),
  review: ({ todo, verdict, note }) => call("command_center.api.work.review", { todo, verdict, note }),

  /* Downloads. Reads only: nothing is written to the site, not even a File. */
  answerPdf: (args) => download("command_center.api.export.answer_pdf", args, "answer.pdf"),
  tablesXlsx: (args) => download("command_center.api.export.tables_xlsx", args, "tables.xlsx"),
  recordsXlsx: (args) => download("command_center.api.export.records_xlsx", args, "records.xlsx"),

  /* The nine management reports: started as a job, polled until written. */
  reportGenerate: ({ code, business_code }) =>
    call("command_center.api.reports.generate", { code, business_code }),
  reportStatus: (job_id) => call("command_center.api.reports.status", { job_id }),

  ingestStatus: () => call("command_center.api.ingest.status"),
  ingestHistory: (business_code) => call("command_center.api.ingest.history", { business_code }),
  ingestRefresh: (business_code) => call("command_center.api.ingest.refresh", { business_code }),
  reconcile: (business_code) =>
    call("command_center.api.ingest.reconcile", { business_code }),
};
