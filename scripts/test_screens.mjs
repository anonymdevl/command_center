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
import { magnitude, money } from "../frontend/src/format.js";
import { goTarget } from "../frontend/src/legacy/hydrate.js";
import { staleWords } from "../frontend/src/legacy/reach.js";
import { short } from "../frontend/src/legacy/vizoptions.js";

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

if (failed) {
  console.log(`screens: ${failed} failed`);
  process.exit(1);
}
console.log("screens: all passed");
