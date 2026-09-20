/**
 * Theme, accent and signal strength.
 *
 * These live on <html> as data attributes because the whole design system is
 * CSS custom properties keyed off them -- the same mechanism the prototype used,
 * kept deliberately so the approved palettes transfer without reinterpretation.
 *
 * Stored per browser. It is a preference, not a setting: two managers looking at
 * the same business should be able to disagree about dark mode.
 */
const KEYS = { theme: "icc-theme", accent: "icc-accent", signal: "icc-signal" };
const DEFAULTS = { theme: null, accent: "petrol", signal: "muted" };

function read(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private browsing: the choice simply does not persist */
  }
}

export function initAppearance() {
  const el = document.documentElement;
  el.setAttribute("data-accent", read(KEYS.accent, DEFAULTS.accent));
  el.setAttribute("data-signal", read(KEYS.signal, DEFAULTS.signal));
  const stored = read(KEYS.theme, null);
  const preferred =
    window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  el.setAttribute("data-theme", stored || preferred);
}

export function getAppearance() {
  const el = document.documentElement;
  return {
    theme: el.getAttribute("data-theme") || "dark",
    accent: el.getAttribute("data-accent") || DEFAULTS.accent,
    signal: el.getAttribute("data-signal") || DEFAULTS.signal,
  };
}

export function setAppearance(kind, value) {
  document.documentElement.setAttribute(`data-${kind}`, value);
  write(KEYS[kind], value);
}
