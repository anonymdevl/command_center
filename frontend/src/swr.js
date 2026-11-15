/**
 * The last answer to each of a screen's calls, shown at once when the screen is opened
 * again while the new answer is read (stale while revalidate), and one request at a time
 * per call.
 *
 * An answer is kept under a key that names the person, the business and the call
 * (useApi's `key` option, see keyFor), so it is only ever shown for that same call by that
 * same person: never another business's figures, never someone else's. It is kept in
 * memory, and in this tab's sessionStorage so a reload of the page is filled at once too;
 * answers older than MAX_AGE are not shown. sessionStorage may be missing or full (a
 * private window, a large screen): then it is simply not used.
 *
 * Pure apart from sessionStorage, so scripts/test_swr.mjs tests it under Node.
 */

export const MAX_AGE = 30 * 60 * 1000;
const PREFIX = "cc-swr:";
const LARGEST = 400 * 1024; // characters: a screen's answer larger than this stays in memory
const memory = new Map();
const inflight = new Map();

function store() {
  try {
    return typeof sessionStorage !== "undefined" ? sessionStorage : null;
  } catch {
    return null;
  }
}

/** The key for one call: whose, which business, what. */
export function keyFor(user, scope, ...what) {
  return JSON.stringify([user || "", scope || "__all__", ...what]);
}

/** The answer kept for a key, or null. */
export function peek(key, now = Date.now()) {
  if (!key) return null;
  let got = memory.get(key);
  if (!got) {
    const s = store();
    try {
      const raw = s && s.getItem(PREFIX + key);
      got = raw ? JSON.parse(raw) : null;
    } catch {
      got = null;
    }
    if (got) memory.set(key, got);
  }
  if (!got || now - got.at > MAX_AGE) return null;
  return got.data;
}

/** Keep the answer for a key. */
export function keep(key, data, now = Date.now()) {
  if (!key || data == null) return;
  const entry = { at: now, data };
  memory.set(key, entry);
  const s = store();
  if (!s) return;
  try {
    const raw = JSON.stringify(entry);
    if (raw.length <= LARGEST) s.setItem(PREFIX + key, raw);
  } catch {
    /* full or refused: memory only */
  }
}

/**
 * fn() for a key, unless the same call is already on its way: then that one's answer.
 * Two parts of the page asking the same thing at the same moment make one request.
 */
export function shared(key, fn) {
  if (!key) return Promise.resolve().then(fn);
  const going = inflight.get(key);
  if (going) return going;
  const p = Promise.resolve()
    .then(fn)
    .finally(() => {
      if (inflight.get(key) === p) inflight.delete(key);
    });
  inflight.set(key, p);
  return p;
}

/**
 * One hook's requests, in order. The latest request's answer is the one applied
 * (switching business twice quickly must not let the slower answer land last); a
 * background refresh (the minute's tick) is skipped while the last request is still on
 * its way, so a slow screen never has refreshes piling up behind it; invalidate() drops
 * the answers still out (the screen or the business changed).
 */
export function runner() {
  let seq = 0;
  let pending = null;
  return {
    get busy() {
      return pending !== null;
    },
    run(fn, { background = false, onStart, onData, onError } = {}) {
      if (background && pending !== null) return false;
      const mine = ++seq;
      const token = {};
      pending = token;
      onStart?.();
      Promise.resolve()
        .then(fn)
        .then(
          (data) => {
            if (mine === seq) onData?.(data);
          },
          (error) => {
            if (mine === seq) onError?.(error);
          }
        )
        .finally(() => {
          if (pending === token) pending = null;
        });
      return true;
    },
    invalidate() {
      seq += 1;
      pending = null;
    },
  };
}

/** For the tests: forget everything. */
export function _reset() {
  memory.clear();
  inflight.clear();
}
