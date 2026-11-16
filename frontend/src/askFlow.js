import { api, call } from "./api/client.js";
import { stepOf } from "./legacy/steps.js";

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

export async function withSteps(args, signal, onSteps, askId = newAskId(), pollSignal = null) {
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
    const over = () => done || signal.aborted || pollSignal?.aborted;
    for (let n = 0; !over(); n++) {
      // Quick at first, so the first step shows almost as soon as it starts.
      await new Promise((r) => setTimeout(r, n < 4 ? 400 : 800));
      if (over()) break;
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

function newAskId() {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}

/* ------------------------------------------------------------------------- */
/*  One question at a time per conversation, and a Stop that keeps the work.   */
/* ------------------------------------------------------------------------- */

// After Stop, the server answers with what it had at its next check -- between rounds
// or lookups, so at once unless a model call is under way. The page waits this long
// for that answer, then shows the steps it already has, so Stop never means waiting.
const STOP_GRACE_MS = 5000;
const running = new Map(); // scope -> the question being worked out there

export const STOPPED_NOTE = "Stopped — here is what I had so far.";

/** The question running in this conversation (the bar or the Ask AI screen), if any. */
export function runningFor(scope) {
  return running.get(scope || "") || null;
}

/** Stop whatever is running in this conversation. */
export function stopRunning(scope) {
  runningFor(scope)?.stop();
}

function changed() {
  window.dispatchEvent(new CustomEvent("cc-ask-running"));
}

/**
 * Ask in a conversation: {askId, answer, stop}, or null when a question is already
 * running there (one at a time, so a follow-up cannot overtake the question it follows).
 * `answer` resolves to the server's payload -- after Stop, its partial answer, or, if
 * that does not come back within a few seconds, one made here from the steps so far.
 */
export function runAsk(scope, args, onSteps) {
  const key = scope || "";
  if (running.has(key)) return null;
  const ctrl = new AbortController();
  const polling = new AbortController();
  const askId = newAskId();
  let steps = [];
  let settle;
  const handle = { askId, scope: key, question: args.question, stopped: false };
  handle.answer = new Promise((resolve, reject) => {
    settle = { resolve, reject };
  });
  const finish = (fn, v) => {
    if (running.get(key) === handle) {
      running.delete(key);
      changed();
    }
    fn(v);
  };
  withSteps(args, ctrl.signal, (st) => {
    steps = st;
    if (!handle.stopped) onSteps?.(st);
  }, askId, polling.signal).then(
    (payload) => finish(settle.resolve, payload),
    (e) => {
      if (handle.stopped && e?.name === "AbortError") return; // answered from the steps
      finish(settle.reject, e);
    },
  );
  handle.stop = () => {
    if (handle.stopped) return;
    handle.stopped = true;
    polling.abort();
    changed();
    call("command_center.api.ask.stop", { ask_id: askId }).catch(() => {});
    setTimeout(() => {
      finish(settle.resolve, stoppedHere(args.question, steps));
      ctrl.abort();
    }, STOP_GRACE_MS);
  };
  running.set(key, handle);
  changed();
  return handle;
}

/** A question stopped before the server could say what it had: its steps, as taken. */
function stoppedHere(question, steps) {
  const done = (steps || []).map((s) => stepOf(s).text).filter(Boolean);
  return {
    answered: true,
    stopped: true,
    format: "markdown",
    mode: "analyst",
    question,
    answer: `**${STOPPED_NOTE}**\n\n`
      + (done.length
        ? "It was still working out its answer, so no figures had come back yet. "
          + "The lookups it had started are listed under what it checked."
        : "It had not looked anything up yet."),
    checked: done.length ? done : ["nothing -- it was stopped before the first lookup"],
  };
}

/** The questions to start with, for this person and business (api/starters.py). */
export function fetchStarters(scope) {
  return call("command_center.api.starters.starters", { business_code: scope })
    .then((r) => (r?.starters || []).filter((s) => s?.q));
}

/** Stop a deeper look that is still working (the first answer stands). */
export function stopDeepLook(askId) {
  return call("command_center.api.ask.stop", { ask_id: askId }).catch(() => {});
}

/**
 * Follow a deeper look: the background job that carries on a big question from where
 * the first answer stopped. Calls onSteps as it works, then onDone(fullerAnswer),
 * onFailed(reason), or onStuck() if no worker has picked the job up -- the first answer
 * stands in every case but the first. Returns a function that stops following.
 */
export function followDeep(askId, { onSteps, onDone, onFailed, onStuck, onStopped }) {
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
      if (st?.state === "stopped") return (onStopped || onFailed)("you stopped it");
      if (st?.state === "queued" && Date.now() - t0 > 45000) return onStuck();
      if (Date.now() - t0 > 22 * 60000) return onFailed("it took longer than twenty minutes");
    }
  })();
  return () => {
    stop = true;
  };
}
