/**
 * The one way the screens say that the business's ERPNext has not answered a read
 * (16 Nov 2026). It is most often only slow -- a large ERPNext working through a heavy
 * query, or a screen being read while a refresh is running -- and a client reading
 * "can't reach" thinks the connection is broken. So the words are calm and honest: what
 * is shown is from the last read, the newest figures are on their way, and when.
 *
 * The data keeps its state names ("unreachable"); only the words are here. The server's
 * own sentences come from kpi/live_departments.waiting_words, in the same voice.
 */

/** A part with no figure yet: the pill, a card's or tile's footnote, a row's reason. */
export const WAITING = {
  pill: "updating",
  foot: "waiting for ERPNext to answer",
  line: "Waiting for ERPNext to answer",
};

/** While a screen's reads are on their way: a read in flight is loading, never "not
 *  answered". */
export const UPDATING = "Updating from ERPNext…";

/** "14 Nov, 18:46" (or "18:46" today) from a server timestamp, or null. */
export function readAt(v) {
  if (!v) return null;
  const d = new Date(String(v).replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return null;
  return new Date().toDateString() === d.toDateString()
    ? d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** "Test Medical Ltd's ERPNext is taking longer than usual to answer" */
export function slowWords(business) {
  return `${business ? `${business}'s` : "The business's"} ERPNext is taking longer than usual to answer`;
}

/** A panel's, statement's or profile's line in place of what it could not read yet. */
export function waitingLine(business, lastLoaded) {
  const at = readAt(lastLoaded);
  return `Not updated yet: ${slowWords(business)}. This fills in as soon as it does.`
    + (at ? ` The last read was at ${at}.` : "");
}

/**
 * A refresh that did not come through while the last answers are still on screen
 * (useApi keeps them, 17 Nov 2026): when they were read, and that it is tried again --
 * or, signed out, that signing in again brings the screen up to date.
 */
export function staleWords(at, signedOut = false) {
  const when = readAt(new Date(at).toISOString());
  const shown = when ? `Last updated ${when}` : "Showing the last figures read";
  return signedOut
    ? `${shown}. You have been signed out: sign in again to see the latest.`
    : `${shown}. The latest refresh did not come through; it is tried again in a minute.`;
}
