/**
 * A link into a business's own ERPNext.
 *
 * The platform is not a Frappe desk: on the standalone host a relative "/app/..." is a
 * 404 (17 Nov 2026: the alert's To-Do fallback, the change log's "load older", the
 * bell's "Adjust the rules"). A desk path goes in front of the business's own address
 * (its site_url, from the boot payload); an address that is already absolute is used as
 * it is; with no address to put in front, there is no link -- never a relative /app.
 * Preflight fails a relative /app/ link built anywhere in the frontend.
 */
import { boot } from "./api/boot.js";

/** The business's ERPNext address, without a trailing slash, or null. */
export function siteOf(code) {
  const b = (boot.businesses || []).find((x) => x.business_code === code)
    || ((boot.businesses || []).length === 1 ? boot.businesses[0] : null);
  const url = (b?.site_url || "").trim().replace(/\/+$/, "");
  return /^https?:\/\//i.test(url) ? url : null;
}

/** `path` ("/app/todo/TD-1", or a full URL) in the business's ERPNext, or null. */
export function erpUrl(path, code) {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  const site = siteOf(code);
  if (!site || !path.startsWith("/")) return null;
  return site + path;
}

/** A record's desk path, as Frappe builds it on every version. */
export function deskPath(doctype, name) {
  return `/${["app", String(doctype).toLowerCase().replace(/[ _]/g, "-"), encodeURIComponent(String(name))].join("/")}`;
}
