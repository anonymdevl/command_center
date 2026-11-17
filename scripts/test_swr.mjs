// The screens' last answers and their requests (frontend/src/swr.js, used by useApi.js).
//
//     node scripts/test_swr.mjs
//
// Run by scripts/preflight.py. swr.js is pure apart from sessionStorage, which is given
// a stand-in here: the minute's refresh never piles up behind a slow request, the latest
// answer wins, two identical calls at once are one request, and a kept answer is only
// ever shown for the same person, business and call.
import { MAX_AGE, _reset, answered, changed, failed as failedRead, keep, keptAt, keyFor, opened, peek, runner,
  shared } from "../frontend/src/swr.js";

let failed = 0;
const check = (ok, what) => {
  if (!ok) {
    failed += 1;
    console.log("FAIL:", what);
  }
};
const store = new Map();
globalThis.sessionStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
};
const later = (ms) => new Promise((r) => setTimeout(r, ms));
// A request that answers when told to.
function deferred() {
  let resolve;
  let reject;
  const p = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { p, resolve, reject };
}

// 1. The minute's refresh is skipped while the last request is still out.
{
  const r = runner();
  let started = 0;
  const first = deferred();
  const got = [];
  r.run(() => {
    started += 1;
    return first.p;
  }, { onData: (d) => got.push(d) });
  for (let i = 0; i < 5; i += 1) {
    const ran = r.run(() => {
      started += 1;
      return Promise.resolve("again");
    }, { background: true, onData: (d) => got.push(d) });
    check(ran === false, `a refresh while one is out does not start (tick ${i})`);
  }
  await later(5);
  check(started === 1, `one request while the screen is slow, not ${started}`);
  first.resolve("first");
  await later(5);
  check(got.join() === "first", `the slow answer is applied: ${got}`);
  check(!r.busy, "and the hook is free again");
  const ran = r.run(() => Promise.resolve("next"), { background: true, onData: (d) => got.push(d) });
  await later(5);
  check(ran === true && got.join() === "first,next", `the next refresh runs once it is free: ${got}`);
}

// 2. An explicit reload does start, and only the latest answer is applied.
{
  const r = runner();
  const slow = deferred();
  const got = [];
  r.run(() => slow.p, { onData: (d) => got.push(d) });
  r.run(() => Promise.resolve("new"), { onData: (d) => got.push(d) });
  slow.resolve("old");
  await later(5);
  check(got.join() === "new", `a slower earlier answer never lands last: ${got}`);
}

// 3. invalidate() (the business or screen changed) drops what is still out.
{
  const r = runner();
  const out = deferred();
  const got = [];
  r.run(() => out.p, { onData: (d) => got.push(d), onError: (e) => got.push(`error ${e}`) });
  r.invalidate();
  check(!r.busy, "an invalidated request does not hold back the next screen's refresh");
  out.resolve("previous business");
  await later(5);
  check(got.length === 0, `an answer for the previous business is not shown: ${got}`);
}

// 4. Two parts of the page asking the same thing at once make one request.
{
  _reset();
  let n = 0;
  const one = deferred();
  const k = keyFor("a@x.com", "biz_a", "alerts");
  const a = shared(k, () => {
    n += 1;
    return one.p;
  });
  const b = shared(k, () => {
    n += 1;
    return Promise.resolve("second");
  });
  one.resolve("first");
  check((await a) === "first" && (await b) === "first" && n === 1, `one request, n=${n}`);
  const c = await shared(k, () => {
    n += 1;
    return Promise.resolve("later");
  });
  check(c === "later" && n === 2, "once answered, the next call is a new request");
}

// 5. A kept answer is shown only for the same person, business and call; never too old.
{
  _reset();
  store.clear();
  const now = Date.now();
  const k = keyFor("a@x.com", "biz_a", "kpis", "ar_total");
  keep(k, { ar_total: 1 }, now);
  check(peek(k, now)?.ar_total === 1, "the same call gets its last answer");
  check(peek(keyFor("a@x.com", "biz_b", "kpis", "ar_total"), now) === null,
    "another business gets nothing");
  check(peek(keyFor("b@x.com", "biz_a", "kpis", "ar_total"), now) === null,
    "another person gets nothing");
  check(peek(keyFor("a@x.com", "biz_a", "kpis", "ar_total,ap_total"), now) === null,
    "another set of figures gets nothing");
  check(peek(k, now + MAX_AGE + 1) === null, "an answer older than MAX_AGE is not shown");
  _reset(); // a reload of the page: memory gone, this tab's sessionStorage kept
  check(peek(k, now)?.ar_total === 1, "after a reload of the page it is still there");
  check(peek(null) === null && shared(null, () => 5) instanceof Promise, "no key, no keeping");
}

// 6. A failed read keeps the last good answer to the same call, never another call's
//    (17 Nov 2026: one failed minute's refresh blanked every panel on a screen).
{
  const err = new Error("no reply");
  const good = answered({ ar: 1 }, 1000);
  let s = failedRead({ ...good, loading: true }, err);
  check(s.data?.ar === 1 && s.error === err && s.at === 1000 && !s.loading,
    "a failed refresh keeps the last answer, says when it was read, and carries the error");
  s = failedRead(changed(good), err);
  check(s.data === null && s.error === err, "a failed read after the call changed shows the failure, not the old answer");
  s = failedRead(opened(null), err);
  check(s.data === null && s.error === err, "a failed first read shows the failure");
  s = failedRead(opened({ ar: 2 }, 500), err);
  check(s.data?.ar === 2 && s.at === 500, "a kept answer to this same call (another visit) stays on a failure");
  s = answered({ ar: 3 }, 2000);
  check(s.own && s.error === null && s.at === 2000, "an answer clears the error");
  _reset();
  const k = keyFor("a@x.com", "biz_a", "kpis");
  keep(k, { ar: 1 }, 1234);
  check(keptAt(k, 1300) === 1234 && keptAt(keyFor("a@x.com", "biz_b", "kpis"), 1300) === null,
    "keptAt is when this call's kept answer was read");
}

if (failed) {
  console.log(`swr: ${failed} failed`);
  process.exit(1);
}
console.log("swr: all passed");
