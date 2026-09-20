/**
 * What the server put on the page before React started.
 *
 * Delivered inline by get_context so the greeting and the business scope are
 * right on first paint, rather than the screen flashing a placeholder and
 * correcting itself a moment later.
 */
const raw = typeof window !== "undefined" ? window.CC_BOOT : null;

export const boot = raw || {
  user: { id: "Guest", name: "Guest", initials: "?", roles: [] },
  site: "",
  businesses: [],
  scopes: [],
  as_of: null,
  live: [],
};

export const hasSession = Boolean(raw);

/** Is this view reading loaded facts, or still showing the demonstration extract? */
export function isLive(viewKey) {
  return (boot.live || []).includes(viewKey);
}
