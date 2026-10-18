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
export async function withSteps(args, signal, onSteps) {
  const askId = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  let done = false;
  const answer = api.ask({ ...args, ask_id: askId }, { signal }).finally(() => {
    done = true;
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
