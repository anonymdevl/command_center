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

  lineage: ({ fact, filters, business_code, limit }) =>
    call("command_center.api.facts.lineage", { fact, filters, business_code, limit }),

  /* Figures. The screen names them; the server decides what they mean. */
  kpis: ({ keys, business_code }) =>
    call("command_center.api.kpi.get", { keys, business_code }),
  kpiCatalogue: () => call("command_center.api.kpi.catalogue"),
  kpiVerify: (business_code) => call("command_center.api.kpi.verify", { business_code }),

  ingestStatus: () => call("command_center.api.ingest.status"),
  reconcile: (business_code) =>
    call("command_center.api.ingest.reconcile", { business_code }),
};
