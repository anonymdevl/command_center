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

export function magnitude(n) {
  const v = Math.abs(Number(n) || 0);
  if (v >= 1e9) return { value: n / 1e9, suffix: "B" };
  if (v >= 1e6) return { value: n / 1e6, suffix: "M" };
  if (v >= 1e3) return { value: n / 1e3, suffix: "k" };
  return { value: n, suffix: "" };
}

/** Compact money for a card: GHS 9.18M */
export function money(n, currency = "GHS", { decimals = 2 } = {}) {
  const { value, suffix } = magnitude(n);
  const digits = suffix ? decimals : 0;
  return {
    currency,
    figure: value.toLocaleString("en-GB", {
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
