/**
 * The conversation with the analyst, shared by the top bar and the Ask AI screen.
 *
 * One list, so a follow-up asked in the bar knows what was asked on the screen and the
 * other way round. Each turn remembers its business, so a follow-up never carries
 * another company's context.
 *
 * Kept on the server, per person (api/conversations.py), since 18 Oct 2026: it used to
 * live only in the page and vanished on a refresh or a sign-out. When the page opens,
 * the person's latest conversation for the business is loaded back; "New conversation"
 * starts another, and the earlier ones stay listed on the Ask AI screen.
 */
import { api } from "./api/client.js";

const turns = [];
const current = {};   // scope -> the conversation being added to
const loaded = {};    // scope -> a promise, so the latest is fetched once
let saving = Promise.resolve();

/** redraw: the turns themselves changed (a conversation opened or cleared), not just
 *  which conversation a new turn was saved into. */
function changed(redraw = true) {
  window.dispatchEvent(new CustomEvent("cc-history-changed", { detail: { redraw } }));
}

/** Bring back the person's latest conversation for this business (once per page). */
export function restore(scope) {
  if (loaded[scope]) return loaded[scope];
  loaded[scope] = api.convRecent(scope)
    .then((list) => (list && list[0] && !turns.some((t) => t.scope === scope) ? open(list[0].name, scope) : null))
    .catch(() => null);
  return loaded[scope];
}

/** Open one of the person's conversations in place of the current one. */
export async function open(name, scope) {
  const c = await api.convLoad(name);
  for (let i = turns.length - 1; i >= 0; i--) if (turns[i].scope === scope) turns.splice(i, 1);
  (c?.turns || []).forEach((t) => turns.push({ q: t.q, a: t.payload?.answer || "", scope, payload: t.payload || {} }));
  current[scope] = c?.name || null;
  changed();
  return c;
}

export function currentConversation(scope) {
  return current[scope] || null;
}

/** The last few turns for this business, in the shape api.ask sends. */
export function historyFor(scope) {
  return turns
    .filter((t) => t.scope === scope)
    .slice(-4)
    .map(({ q, a }) => ({ q, a }));
}

export function remember(scope, question, payload) {
  if (payload?.answered && payload.answer) {
    turns.push({ q: question, a: payload.answer, scope, payload });
    save(scope, question, payload, false);
  }
}

/** A deeper look finished: its fuller answer replaces the first one for that question. */
export function replaceAnswer(scope, question, payload) {
  for (let i = turns.length - 1; i >= 0; i--) {
    const t = turns[i];
    if (t.scope === scope && t.q === question) {
      turns[i] = { q: question, a: payload.answer, scope, payload };
      save(scope, question, payload, true);
      return;
    }
  }
  remember(scope, question, payload);
}

/** The whole conversation for this business, oldest first -- the Ask AI screen's thread. */
export function turnsFor(scope) {
  return turns.filter((t) => t.scope === scope);
}

/** Start a new conversation for this business. The previous one stays on the server. */
export function clearTurns(scope) {
  for (let i = turns.length - 1; i >= 0; i--) if (turns[i].scope === scope) turns.splice(i, 1);
  current[scope] = null;
  changed();
}

/** Questions asked in this conversation, newest first, without repeats. */
export function recentQuestions(scope, limit = 4) {
  const seen = new Set();
  const out = [];
  for (let i = turns.length - 1; i >= 0 && out.length < limit; i--) {
    const t = turns[i];
    if (t.scope !== scope || seen.has(t.q)) continue;
    seen.add(t.q);
    out.push(t.q);
  }
  return out;
}

/** Saved in order, one after another, so the second question cannot start a second
 *  conversation while the first is still being created. A failed save loses nothing on
 *  the screen; it only means that turn will not be there next time. */
function save(scope, question, payload, replace) {
  saving = saving
    .then(() => api.convAdd({ question, payload, business_code: scope, name: current[scope], replace }))
    .then((r) => {
      if (r?.name && current[scope] !== r.name) {
        current[scope] = r.name;
        changed(false);
      }
    })
    .catch(() => {});
}
