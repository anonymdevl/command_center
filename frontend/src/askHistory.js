/**
 * The conversation with the analyst, shared by the top bar and the Ask AI screen.
 *
 * One list, so a follow-up asked in the bar knows what was asked on the screen and the
 * other way round. Kept for the page's life only: nothing about a question is written
 * to the browser. Each turn remembers its business, so a follow-up never carries
 * another company's context.
 */
const turns = [];

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
  }
}

/** The whole conversation for this business, oldest first -- the Ask AI screen's thread. */
export function turnsFor(scope) {
  return turns.filter((t) => t.scope === scope);
}

/** Start a new conversation for this business. */
export function clearTurns(scope) {
  for (let i = turns.length - 1; i >= 0; i--) if (turns[i].scope === scope) turns.splice(i, 1);
}

/** Questions asked this session, newest first, without repeats. */
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
