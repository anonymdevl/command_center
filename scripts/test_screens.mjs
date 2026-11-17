// Small pure parts of the screens that were wrong once (17 Nov 2026).
//
//     node scripts/test_screens.mjs
//
// Run by scripts/preflight.py.
//   money     the unit is chosen after rounding: 999,999 is "GHS 1.00M", never
//             "GHS 1,000.00k"; a figure that rounds to nothing is "GHS 0", never "GHS -0"
//   goTarget  where a designed tile navigates is read once and kept (data-go), so a
//             second draw -- after the onclick was removed -- still finds it; Today's
//             tiles lost their way to Outstanding Tasks on the second draw and opened
//             ERPNext's /app/todo instead
//   staleWords the quiet line a screen shows while a refresh has not come through
//   backstack the browser's Back closes the top drawer and stays on the screen; a drawer
//             closed by its own X takes its entry off again, so the next Back goes to the
//             screen before, never off the platform (a phone pressed Back with a drawer
//             open and left for the site before it)
import { magnitude, money } from "../frontend/src/format.js";
import { goTarget } from "../frontend/src/legacy/hydrate.js";
import { staleWords } from "../frontend/src/legacy/reach.js";
import { short } from "../frontend/src/legacy/vizoptions.js";
import { backstack } from "../frontend/src/backstack.js";

let failed = 0;
const check = (ok, what) => {
  if (!ok) {
    failed += 1;
    console.log("FAIL:", what);
  }
};
const shown = (n, opts) => {
  const m = money(n, "GHS", opts);
  return `${m.currency} ${m.figure}${m.suffix}`;
};

// money: the unit after rounding, and no "-0".
for (const [n, want] of [
  [999999, "GHS 1.00M"],
  [-999999, "GHS -1.00M"],
  [999994999, "GHS 999.99M"],
  [999995000, "GHS 1.00B"],
  [999.4, "GHS 999"],
  [999.6, "GHS 1.00k"],
  [9177568.91, "GHS 9.18M"],
  [1234, "GHS 1.23k"],
  [-1500, "GHS -1.50k"],
  [-0.004, "GHS 0"],
  [0.004, "GHS 0"],
  [-0.4, "GHS 0"],
  [0, "GHS 0"],
  [null, "GHS 0"],
]) check(shown(n) === want, `money(${n}) is ${want}, got ${shown(n)}`);
check(shown(999999, { decimals: 1 }) === "GHS 1.0M", `money(999999, 1 decimal) is GHS 1.0M, got ${shown(999999, { decimals: 1 })}`);
check(magnitude(999999).suffix === "M" && magnitude(5).suffix === "", "magnitude picks the unit after rounding");
// The charts' short form follows the same rule (vizoptions.short).
check(short(999990, "GHS") === "GHS 1M", `chart short(999990) is GHS 1M, got ${short(999990, "GHS")}`);
check(short(-0.004, "GHS") === "GHS 0", `chart short(-0.004) is GHS 0, got ${short(-0.004, "GHS")}`);

// goTarget: read once from the onclick, kept on the element.
function node(onclick) {
  const attrs = new Map(onclick == null ? [] : [["onclick", onclick]]);
  return {
    dataset: {},
    getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
    removeAttribute: (k) => attrs.delete(k),
  };
}
{
  const tile = node("go('delegation')");
  check(goTarget(tile) === "delegation", "a tile's go('delegation') is found");
  tile.removeAttribute("onclick"); // what Today's own wiring does on the first draw
  check(goTarget(tile) === "delegation", "and still found on the next draw, after its onclick was removed");
  check(goTarget(node("explain('unwired')")) === null, "an explain() placeholder navigates nowhere");
  check(goTarget(node(null)) === null, "no onclick, no target");
  check(goTarget(node('window.go("sales")')) === null, "only a bare go(), as the generator writes it");
  check(goTarget(node(' go( "sales" ) ')) === "sales", "either quote, any spacing");
}

// staleWords: when, and that it is tried again; signed out says to sign in.
{
  const at = new Date(2026, 10, 17, 9, 5).getTime();
  const w = staleWords(at);
  check(/^Last updated /.test(w) && /tried again/.test(w), `stale words: ${w}`);
  check(/sign in again/.test(staleWords(at, true)), "signed out says to sign in again");
}

// backstack: a stand-in browser history -- entries, pushState, an asynchronous go() that
// fires popstate as a browser does -- and the screens as App.jsx uses them.
{
  const fake = () => {
    const entries = [{ url: "https://site/before", state: null, page: "before" },
      { url: "/app#command", state: null }];
    let at = 1;
    const listeners = [];
    const win = {
      location: { get hash() { const u = entries[at].url; return u.includes("#") ? u.slice(u.indexOf("#")) : ""; } },
      history: {
        get state() { return entries[at].state; },
        get length() { return entries.length; },
        pushState(state, _t, url) {
          entries.splice(at + 1);
          entries.push({ url: url ? `/app${url}` : entries[at].url, state });
          at += 1;
        },
        replaceState(state, _t, url) { entries[at] = { url: url ? `/app${url}` : entries[at].url, state }; },
        go(n) {
          setTimeout(() => {
            const to = Math.max(0, Math.min(entries.length - 1, at + n));
            if (to === at) return;
            at = to;
            listeners.forEach((f) => f({ state: entries[at].state }));
          }, 5);
        },
        back() { this.go(-1); },
      },
      addEventListener: (k, f) => k === "popstate" && listeners.push(f),
      removeEventListener: () => {},
    };
    return { win, entries, where: () => entries[at], index: () => at };
  };
  const settle = () => new Promise((r) => setTimeout(r, 40));
  const b = fake();
  const s = backstack(b.win);
  const open = [];
  const drawer = (name) => {
    open.push(name);
    s.open(() => open.splice(open.indexOf(name)), "drawer");
  };

  // Back with a drawer open closes it and stays on the screen.
  drawer("task");
  check(b.entries.length === 3 && b.where().state?.ccLayer === 1, "opening a drawer adds one entry at the same address");
  b.win.history.back();
  await settle();
  check(open.length === 0, "Back closes the drawer");
  check(b.where().url === "/app#command", `Back stays on the screen, at ${b.where().url}`);

  // Two drawers: Back closes the top one only.
  drawer("records");
  drawer("customer");
  b.win.history.back();
  await settle();
  check(open.join() === "records", `Back closes only the top drawer, left ${open.join()}`);
  b.win.history.back();
  await settle();
  check(open.length === 0 && b.where().url === "/app#command", "and the next Back the one under it");

  // Closed with its own X: its entry goes too, so the next Back is the screen before.
  s.screen("myday");
  check(b.where().url === "/app#myday", "a screen is its own entry");
  drawer("task");
  s.closeKind("drawer", "first");
  check(open.length === 0, "X closes the drawer at once");
  await settle();
  check(b.where().url === "/app#myday" && !b.where().state, "X takes the drawer's entry off again");
  b.win.history.back();
  await settle();
  check(b.where().url === "/app#command", `the next Back is the screen before, at ${b.where().url}`);
  check(b.where().page !== "before", "never the site before the platform");

  // Another screen chosen with drawers open: they close, and the screen lands where they were.
  drawer("records");
  drawer("customer");
  s.screen("delegation");
  check(open.length === 0, "choosing a screen closes the drawers");
  await settle();
  await settle();
  check(b.where().url === "/app#delegation" && b.entries.length === b.index() + 1, "the new screen is the last entry");
  check(b.entries.filter((e) => e.state?.ccLayer).length === 0, `no drawer entry left behind: ${JSON.stringify(b.entries)}`);
  b.win.history.back();
  await settle();
  check(b.where().url === "/app#command", `Back from the new screen is the one before, at ${b.where().url}`);

  // A drawer opened while an X's move is still under way gets its entry after it.
  drawer("one");
  s.closeKind("drawer", "first");
  drawer("two");
  await settle();
  await settle();
  check(open.join() === "two" && b.where().state?.ccLayer === 1, "a drawer opened mid-move has its own entry");
  b.win.history.back();
  await settle();
  check(open.length === 0 && b.where().url === "/app#command", "and Back closes it, on the screen");

  // Forward into an entry whose drawer is gone is passed over.
  drawer("gone");
  s.closeKind("drawer", "first");
  await settle();
  b.win.history.go(1);
  await settle();
  await settle();
  check(!b.where().state?.ccLayer, "Forward into a closed drawer's entry comes back");
  s.stop();

  // Reloaded with a drawer open (its entry is current, nothing is open): back to the screen.
  const r = fake();
  r.win.history.pushState({ ccLayer: 1 }, "");
  const again = backstack(r.win);
  await settle();
  check(!r.where().state?.ccLayer && r.where().url === "/app#command", "a reload on a drawer's entry steps back to the screen's");
  again.stop();
}

if (failed) {
  console.log(`screens: ${failed} failed`);
  process.exit(1);
}
console.log("screens: all passed");
