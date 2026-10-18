import { api } from "./api/client.js";

/**
 * Ask, and show each lookup as the analyst makes it.
 *
 * The question goes to api.ask with an id the page chose; while that request is working,
 * the page polls for the steps the server records under the id. Nothing depends on a
 * background worker -- the first version ran questions as jobs, and on the live site
 * the queue was not serving, so the steps never appeared and questions fell back to a
 * direct request with no progress at all.
 *
 * The steps are a courtesy: a poll that fails is ignored, and the answer is whatever
 * the question request returns.
 */
// The page never waits longer than this for an answer. The server stops itself well
// before (agent.py's deadline); this is the backstop if the connection itself hangs --
// on 18 Oct 2026 a question sat at "thinking" for eleven minutes.
const ANSWER_LIMIT_MS = 150 * 1000;

export async function withSteps(args, signal, onSteps) {
  const askId = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  let done = false;
  let timedOut = false;
  const ctrl = new AbortController();
  const passOn = () => ctrl.abort();
  signal.addEventListener("abort", passOn, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    ctrl.abort();
  }, ANSWER_LIMIT_MS);
  const answer = api.ask({ ...args, ask_id: askId }, { signal: ctrl.signal })
    .catch((e) => {
      if (!timedOut) throw e;
      const err = new Error("This took longer than two and a half minutes, so it was stopped. "
        + "Ask again, or ask for less at once.");
      err.name = "TimeoutError";
      throw err;
    })
    .finally(() => {
      done = true;
      clearTimeout(timer);
      signal.removeEventListener("abort", passOn);
    });

  (async () => {
    for (let n = 0; !done && !signal.aborted; n++) {
      // Quick at first, so the first step shows almost as soon as it starts.
      await new Promise((r) => setTimeout(r, n < 4 ? 400 : 800));
      if (done || signal.aborted) break;
      try {
        const st = await api.askPoll(askId, { signal });
        if (!done && st?.steps) onSteps(st.steps);
      } catch {
        /* progress only -- the answer does not depend on it */
      }
    }
  })();

  return answer;
}

/**
 * Follow a deeper look: the background job that carries on a big question from where
 * the first answer stopped. Calls onSteps as it works, then onDone(fullerAnswer),
 * onFailed(reason), or onStuck() if no worker has picked the job up -- the first answer
 * stands in every case but the first. Returns a function that stops following.
 */
export function followDeep(askId, { onSteps, onDone, onFailed, onStuck }) {
  let stop = false;
  const t0 = Date.now();
  (async () => {
    for (let n = 0; !stop; n++) {
      await new Promise((r) => setTimeout(r, n < 6 ? 1500 : 3000));
      if (stop) break;
      let st;
      try {
        st = await api.askPoll(askId, {}, 1);
      } catch {
        continue;
      }
      if (stop) break;
      if (st?.steps) onSteps(st.steps);
      if (st?.state === "done") return onDone(st.result);
      if (st?.state === "failed") return onFailed(st.error || "the deeper look stopped");
      if (st?.state === "queued" && Date.now() - t0 > 45000) return onStuck();
      if (Date.now() - t0 > 22 * 60000) return onFailed("it took longer than twenty minutes");
    }
  })();
  return () => {
    stop = true;
  };
}
