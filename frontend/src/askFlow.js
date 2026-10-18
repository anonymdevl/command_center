import { api } from "./api/client.js";

/**
 * Ask through a job that reports each lookup, so the steps show as they happen.
 *
 * Falls back to the direct endpoint when the job route is not there (an older server)
 * or no worker picks the job up within a few seconds -- a question must never wait on
 * a queue that is not running.
 */
export async function withSteps(args, signal, onSteps) {
  let started;
  try {
    started = await api.askStart(args, { signal });
  } catch (e) {
    if (e?.name === "AbortError") throw e;
    return api.ask(args, { signal });
  }
  const t0 = Date.now();
  for (let n = 0; ; n++) {
    // Quick at first, so a fast answer is not held back by the polling itself.
    await new Promise((r) => setTimeout(r, n < 3 ? 350 : 700));
    if (signal.aborted) throw new DOMException("aborted", "AbortError");
    let st;
    try {
      st = await api.askPoll(started.ask_id, { signal });
    } catch (e) {
      if (e?.name === "AbortError") throw e;
      // The progress check failed -- on 18 Oct a half-restarted server knew start but
      // not poll. The question still gets answered, directly.
      return api.ask(args, { signal });
    }
    if (st?.steps) onSteps(st.steps);
    if (st?.state === "done") return st.result;
    if (st?.state === "failed") throw new Error(st.error || "The question could not be answered.");
    if (st?.state === "queued" && Date.now() - t0 > 6000) return api.ask(args, { signal });
    if (Date.now() - t0 > 240000) throw new Error("That took too long. Try asking it more narrowly.");
  }
}

