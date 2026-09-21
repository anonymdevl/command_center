"""Gemini as the router, and only as the router.

What the model does: reads the question, the list of intents with one-line descriptions,
and the entity names already resolved from the user's own words, then names one intent
and at most one subject.

What the model does not do: compute, state, adjust, round or phrase a single figure.
Every number still comes out of intents.py reading the fact tables. That separation is
not fussiness -- every honesty rule in this app depends on the figure and the sentence
coming from different places, so a model that is confidently wrong can change which
question was answered but never what a number says.

What leaves the site is therefore small: the question the user typed, the fixed list of
intent names and descriptions, and candidate entity names that were found *in the
question itself*. No figures, no totals, no record contents, no customer list.

The model's answer is validated against the registry. An intent it invents is discarded
and the patterns take over, which is also what happens when there is no key, no network,
a slow reply or a malformed one.
"""

from __future__ import annotations

from command_center.ask import gemini, intents, resolve

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "subject": {"type": "string"},
        "confident": {"type": "boolean"},
    },
    "required": ["intent", "confident"],
}

PROMPT = """You route a question to one handler. You do not answer it.

The question comes from a company director looking at their own ERP data.

Handlers:
{handlers}

Names found in the question, which may be the subject:
{entities}

Question: {question}

Rules:
- Choose exactly one handler name from the list above, copied exactly.
- If none of them fits the question, return "none".
- If the question names one of the entities above, copy that name exactly into subject.
- Set confident to false if you are guessing.
- Never invent a handler name. Never answer the question. Never state any number.
"""


def route(question: str, business_code: str | None = None) -> dict | None:
    """Ask Gemini which intent applies. None means "fall back to the patterns"."""
    if not gemini.configured():
        return None

    names = [f.__name__ for f in intents.INTENTS]
    handlers = "\n".join(
        f"- {n}: {intents.DESCRIPTIONS.get(n, '(no description)')}" for n in names)

    found = resolve.resolve(question, business_code)[:8]
    entities = ("\n".join(f"- {m['name']} ({m['kind']})" for m in found)
                or "- none found")

    answer = gemini.ask_json(
        PROMPT.format(handlers=handlers, entities=entities, question=question), SCHEMA)
    if not answer:
        return None

    chosen = (answer.get("intent") or "").strip()
    if chosen in ("", "none"):
        return None
    if chosen not in names:
        # An invented handler name is discarded rather than guessed at. Falling back to
        # the patterns is always safe; acting on a name nobody defined is not.
        return None

    subject = (answer.get("subject") or "").strip() or None
    if subject and not any(m["name"] == subject for m in found):
        # A subject the model did not get from the question is not trusted either: it
        # would make the answer about a company the user never mentioned.
        subject = None

    return {"intent": chosen, "subject": subject,
            "confident": bool(answer.get("confident"))}
