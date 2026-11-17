/**
 * How figures are written.
 *
 * Two rules carried over from the design, both the result of getting them wrong:
 *
 *   Money leads with its currency -- "GHS 9.18M", not "9.18M GHS" -- because at a
 *   glance a trailing code reads as part of the number rather than as money.
 *
 *   A figure derived from a point in time carries that point. On this dataset,
 *   measuring ageing against today rather than the date the data covers turned a
 *   stale snapshot into a false finding about how the client collects.
 */

const UNITS = [[1, ""], [1e3, "k"], [1e6, "M"], [1e9, "B"]];

/**
 * The unit a figure is written in, chosen AFTER rounding to the digits it is shown with
 * (17 Nov 2026): 999,999 is "1.00M", never "1,000.00k", and 999.6 is "1.00k", never
 * "1,000". `digits` is the decimals shown, or a function of the unit's suffix giving
 * them; a figure with no unit shows none by default. A figure that rounds to nothing is
 * 0, never "-0".
 */
export function magnitude(n, digits = (suffix) => (suffix ? 2 : 0)) {
  const x = Number(n) || 0;
  const places = (suffix) => (typeof digits === "function" ? digits(suffix) : suffix ? digits : 0);
  const shown = (v, i) => {
    const p = 10 ** places(UNITS[i][1]);
    return Math.round((Math.abs(v) / UNITS[i][0]) * p) / p;
  };
  let i = 0;
  while (i < UNITS.length - 1 && Math.abs(x) >= UNITS[i + 1][0]) i += 1;
  while (i < UNITS.length - 1 && shown(x, i) >= 1000) i += 1;
  const value = shown(x, i) === 0 ? 0 : x / UNITS[i][0];
  return { value, suffix: UNITS[i][1], digits: places(UNITS[i][1]) };
}

/** Compact money for a card: GHS 9.18M */
export function money(n, currency = "GHS", { decimals = 2 } = {}) {
  const { value, suffix, digits } = magnitude(n, decimals);
  const p = 10 ** digits;
  // Rounded before it is written, so a value that rounds to nothing is "0", not "-0".
  const rounded = Math.round(value * p) / p || 0;
  return {
    currency,
    figure: rounded.toLocaleString("en-GB", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }),
    suffix,
  };
}

/** Full money for a table or a drawer: 9,177,568.91 */
export function exact(n, { decimals = 2 } = {}) {
  return (Number(n) || 0).toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function count(n) {
  return (Number(n) || 0).toLocaleString("en-GB");
}

export function percent(part, whole, { decimals = 0 } = {}) {
  if (!whole) return "—";
  return `${((part / whole) * 100).toFixed(decimals)}%`;
}

export function shortDate(iso) {
  if (!iso) return null;
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
