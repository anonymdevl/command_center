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
  settings_sections: [],
};

export const hasSession = Boolean(raw);


/**
 * The product's brand (Settings -> Branding, command_center/branding.py): its name,
 * tagline, logos and the vendor's footer lines. The server always sends it; the
 * fallback is only for a page with no payload.
 */
export const brand = {
  product: "Insights", tagline: "", footer: "", prepared: "",
  logo_light_url: null, logo_dark_url: null,
  ...((boot && boot.brand) || {}),
};

/** A business's co-brand -- the name and logo its documents are prepared for -- or null. */
export function clientBrand(code) {
  return ((boot && boot.clients) || {})[code] || null;
}
