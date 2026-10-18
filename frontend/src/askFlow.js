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
  for (;;) {
    await new Promise((r) => setTimeout(r, 900));
    if (signal.aborted) throw new DOMException("aborted", "AbortError");
    const st = await api.askPoll(started.ask_id, { signal });
    if (st?.steps) onSteps(st.steps);
    if (st?.state === "done") return st.result;
    if (st?.state === "failed") throw new Error(st.error || "The question could not be answered.");
    if (st?.state === "queued" && Date.now() - t0 > 6000) return api.ask(args, { signal });
    if (Date.now() - t0 > 240000) throw new Error("That took too long. Try asking it more narrowly.");
  }
}

