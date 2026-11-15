"""Talking to Claude, Anthropic's model, through the official `anthropic` SDK.

The analyst's second provider, and since 14 Nov 2026 the one Gigmann's quote names. The
loop that uses it is agent.py's, shared with Gemini: this module only turns one round of
that loop into one Messages API request and its reply back into the loop's terms.

    bench --site <site> set-config command_center_anthropic_key "sk-ant-..."
    bench --site <site> set-config command_center_ai_provider claude

The key is read from site_config.json and never from the repository; preflight fails
the build on anything shaped like an Anthropic key in a tracked file.

Models, pinned rather than floating, so a deployed service does not change behaviour
with nobody deploying anything:

    everyday questions   claude-sonnet-5-5   command_center_claude_model
    the deeper look      claude-opus-5-5     command_center_claude_deep_model
    (and the reports, which are deep work by nature)

Effort is the depth control (thinking cannot be switched off on either model, and
adaptive thinking decides how much to think): medium for everyday questions, high for
the deeper look. command_center_claude_effort / command_center_claude_deep_effort.

What it costs, and why the opening is cached. Every request carries the same opening --
the tool catalogue, then the analyst's instructions with the data sets and the 85 figure
definitions -- and only the conversation after it changes. That opening is marked for
caching (cache_control on the last fixed system block, 1-hour life so managers who ask
an hour apart still hit it), and the growing conversation is cached automatically
behind it, so a follow-up round reads the opening and every earlier round at a tenth of
the input price. For that to work the opening must be byte-identical between requests:
the date, the data horizon and the business name are sent after the marker, never in
it, and the tools are converted in their registry order every time.
`usage.cache_read_input_tokens` above zero on a second question is the proof;
check_analyst reports it.

Strictly read-only. The tools sent are exactly tools.declarations() -- reads only, no
"call any method" tool -- and every call the model makes is run by agent.py through
tools.run. Nothing here can reach a write.

No forced tool use (Sonnet 5.5 and Opus 5.5 reject tool_choice any/tool): the model
decides when to look things up, agent.py sends a figure stated from memory back to be
looked up, and on the last round tool_choice "none" asks for the answer. The tool list
itself never changes between rounds -- changing it would be an edit to the history,
which breaks the cache and the model's own thinking.

Refusal fallbacks are on (server-side, "default"): if Anthropic's safety classifiers
decline a request -- unlikely for business figures, but possible -- the API retries it
on a model it chooses inside the same call. command_center_claude_fallbacks 0 turns
that off.
"""

from __future__ import annotations

import json
import time

import frappe

MODELS = {"analyst": "claude-sonnet-5-5", "deep": "claude-opus-5-5"}
EFFORT = {"analyst": "medium", "deep": "high"}
CONF_MODEL = {"analyst": "command_center_claude_model", "deep": "command_center_claude_deep_model"}
CONF_EFFORT = {"analyst": "command_center_claude_effort", "deep": "command_center_claude_deep_effort"}
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _key() -> str | None:
    return frappe.conf.get("command_center_anthropic_key")


def configured() -> bool:
    return bool(_key())


def model_for(kind: str = "analyst") -> str:
    return frappe.conf.get(CONF_MODEL[kind]) or MODELS[kind]


def effort_for(kind: str = "analyst") -> str:
    return frappe.conf.get(CONF_EFFORT[kind]) or EFFORT[kind]


def label(model: str) -> str:
    """claude-sonnet-5-5 -> Claude Sonnet 5.5, as a person would say it."""
    parts = (model or "").split("-")
    words = [p.capitalize() for p in parts if not p.isdigit()]
    digits = [p for p in parts if p.isdigit()]
    return " ".join(words + ([".".join(digits)] if digits else []))


def _client():
    import anthropic
    # Retries are ours (agent.py owns the question's deadline); the SDK's own two
    # retries could carry one call well past it.
    return anthropic.Anthropic(api_key=_key(), max_retries=0)


def tool_specs(declarations: list) -> list:
    """The read tools in Claude's shape, in registry order every time (the cache is a
    prefix match: a reordered list is a different opening)."""
    out = []
    for d in declarations:
        schema = d.get("parameters") or {"type": "object", "properties": {}}
        out.append({"name": d["name"], "description": d.get("description", ""),
                    "input_schema": schema})
    return out


def system_blocks(static: str, dynamic: str) -> list:
    """The fixed opening, marked for caching; then what changes, after the marker."""
    ttl = frappe.conf.get("command_center_claude_cache_ttl") or "1h"
    marker = {"type": "ephemeral", "ttl": ttl} if ttl in ("1h", "5m") else {"type": "ephemeral"}
    blocks = [{"type": "text", "text": static, "cache_control": marker}]
    if dynamic:
        blocks.append({"type": "text", "text": dynamic})
    return blocks


def request(messages: list, declarations: list, static: str, dynamic: str,
            kind: str = "analyst", timeout: float = 60, final: bool = False) -> dict:
    """The body of one request (without the client), so a test can see exactly what
    would be sent."""
    body = {
        "model": model_for(kind),
        "max_tokens": MAX_TOKENS,
        "system": system_blocks(static, dynamic),
        "tools": tool_specs(declarations),
        "messages": messages,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort_for(kind)},
        # The conversation tail, cached behind the opening's marker (5-minute life:
        # a longer life must come first, and the opening's does).
        "cache_control": {"type": "ephemeral"},
    }
    if final:
        body["tool_choice"] = {"type": "none"}
    if str(frappe.conf.get("command_center_claude_fallbacks", 1)) not in ("0", "false", "False"):
        body["betas"] = [FALLBACK_BETA]
        body["fallbacks"] = "default"
    return body


def chat(messages: list, declarations: list, static: str, dynamic: str,
         kind: str = "analyst", timeout: float = 60, final: bool = False) -> tuple:
    """One round: (content, error). content is the reply's blocks as plain dicts, in
    order, to be appended to the conversation unchanged -- thinking blocks included,
    which the model needs back exactly as it wrote them.

    Errors are returned in words, never raised and never logged here (agent.py logs
    after its write guard, so the guard cannot erase the record).
    """
    if not _key():
        return None, "no Anthropic key configured"
    try:
        import anthropic
    except ImportError:
        return None, ("The anthropic package is not installed on the server "
                      "(bench pip install anthropic).")
    body = request(messages, declarations, static, dynamic, kind, timeout, final)
    client = _client()
    for attempt in range(2):
        try:
            msg = client.with_options(timeout=max(5, timeout)).beta.messages.create(**body)
            break
        except anthropic.RateLimitError as e:
            wait = _retry_after(e)
            if attempt == 0 and 0 < wait <= 10 and _time_left(wait + 10):
                time.sleep(wait)
                continue
            return None, ("Claude's rate limit for this key is reached right now"
                          + (f"; it frees up in about {wait} seconds." if wait else ".")
                          + " A higher usage tier on the Anthropic account raises it.")
        except anthropic.APITimeoutError:
            return None, ("Claude, the AI model, did not reply in time -- Anthropic is "
                          "answering slowly right now.")
        except anthropic.APIConnectionError:
            return None, "Claude could not be reached from the server (a network problem)."
        except anthropic.AuthenticationError:
            return None, "The Anthropic key on this site was refused (wrong or revoked key)."
        except anthropic.PermissionDeniedError as e:
            return None, f"The Anthropic key may not use {body['model']}: {_words(e)}"
        except anthropic.NotFoundError as e:
            return None, f"Anthropic does not serve {body['model']} to this key: {_words(e)}"
        except anthropic.BadRequestError as e:
            return None, f"Claude refused the request ({body['model']}): {_words(e)}"
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 and attempt == 0 and _time_left(15):
                time.sleep(1.5)
                continue
            return None, f"Claude returned an error ({e.status_code}): {_words(e)}"
        except Exception as e:  # anything else, in words
            return None, f"Claude could not be reached ({type(e).__name__}: {str(e)[:200]})."
    _remember_usage(msg, body["model"])
    if msg.stop_reason == "refusal":
        cat = getattr(getattr(msg, "stop_details", None), "category", None)
        return None, ("Claude declined to answer this question"
                      + (f" (its safety check: {cat})" if cat else "") + ".")
    content = [_plain(b) for b in msg.content]
    if msg.stop_reason == "max_tokens" and not any(c.get("type") == "tool_use" for c in content):
        content.append({"type": "text", "text": "\n\n(The answer was cut short at its length limit.)"})
    return content, None


def complete(static: str, text: str, kind: str = "analyst", timeout: float = 90,
             max_tokens: int = 4000, schema: dict | None = None) -> tuple:
    """One request with no tools, for a piece of writing (the Daily Brief) or, with a
    JSON schema, a structured answer (the AI review: output_config.format, so the reply
    is JSON that fits it): (text, error). The same model, thinking, effort and
    fallbacks as a question (request() above); the fixed instructions (`static`) carry
    the cache marker."""
    if not _key():
        return None, "no Anthropic key configured"
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return None, "The anthropic package is not installed on the server."
    body = request([{"role": "user", "content": text}], [], static, "", kind, timeout)
    body.pop("tools", None)
    body["max_tokens"] = max_tokens
    if schema:
        body["output_config"] = {**body["output_config"],
                                 "format": {"type": "json_schema", "schema": schema}}
    try:
        msg = _client().with_options(timeout=max(5, timeout)).beta.messages.create(**body)
    except Exception as e:  # in words, as chat() does
        return None, f"Claude could not be reached ({type(e).__name__}: {_words(e)[:200]})."
    _remember_usage(msg, body["model"])
    if msg.stop_reason == "refusal":
        return None, "Claude declined to write it."
    out = "".join(getattr(b, "text", "") or "" for b in msg.content
                  if getattr(b, "type", "") == "text").strip()
    return (out, None) if out else (None, "Claude returned no text.")


def _plain(block) -> dict:
    """A reply block as the API sent it, as plain JSON: what it returned is what it
    accepts back."""
    try:
        return block.to_dict(mode="json")
    except TypeError:
        return json.loads(block.to_json())


def _words(e) -> str:
    try:
        return str(e.body.get("error", {}).get("message") or e.message)[:600]
    except Exception:
        return str(e)[:600]


def _retry_after(e) -> int:
    try:
        return int(float(e.response.headers.get("retry-after") or 0))
    except Exception:
        return 0


def _time_left(seconds: float) -> bool:
    end = getattr(frappe.local, "cc_deadline", None)
    return not end or end - time.monotonic() > seconds


def _remember_usage(msg, model):
    """Kept on the request, so the answer can say what it cost in tokens and whether
    the cache was read (the caching proof), and recorded in the usage ledger, which the
    monthly usage statement is built from. Called after every reply (chat, complete,
    limits)."""
    u = getattr(msg, "usage", None)
    if not u:
        return
    tally = getattr(frappe.local, "cc_claude_usage", None)
    if tally is None:
        tally = frappe.local.cc_claude_usage = {"input": 0, "output": 0, "cache_read": 0,
                                                "cache_write": 0, "requests": 0, "model": model}
    tally["input"] += int(getattr(u, "input_tokens", 0) or 0)
    tally["output"] += int(getattr(u, "output_tokens", 0) or 0)
    tally["cache_read"] += int(getattr(u, "cache_read_input_tokens", 0) or 0)
    tally["cache_write"] += int(getattr(u, "cache_creation_input_tokens", 0) or 0)
    tally["requests"] += 1
    tally["model"] = getattr(msg, "model", None) or model
    # The usage ledger (command_center/metering.py): every reply, here, the one place a
    # reply comes back -- so no call escapes it, a refused or failed question's tokens
    # included. It never stops an answer.
    from command_center import metering
    metering.tokens(tally["model"],
                    input=int(getattr(u, "input_tokens", 0) or 0),
                    output=int(getattr(u, "output_tokens", 0) or 0),
                    cache_read=int(getattr(u, "cache_read_input_tokens", 0) or 0),
                    cache_write=int(getattr(u, "cache_creation_input_tokens", 0) or 0),
                    requests=1)


def usage() -> dict | None:
    return getattr(frappe.local, "cc_claude_usage", None)


def limits() -> dict:
    """The key's rate limits, read from the headers of one tiny request -- so the
    questions a minute the key allows can be stated from Anthropic's own numbers."""
    import anthropic
    client = _client()
    raw = client.with_options(timeout=30).messages.with_raw_response.create(
        model=model_for("analyst"), max_tokens=16,
        messages=[{"role": "user", "content": "Reply with the word OK."}],
        output_config={"effort": "low"})
    h = raw.headers
    msg = raw.parse()
    _remember_usage(msg, model_for("analyst"))
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")

    def num(name):
        v = h.get(name)
        try:
            return int(v) if v is not None else None
        except ValueError:
            return None

    out = {"model": msg.model, "reply": text[:40],
           "requests_per_minute": num("anthropic-ratelimit-requests-limit"),
           "input_tokens_per_minute": num("anthropic-ratelimit-input-tokens-limit"),
           "output_tokens_per_minute": num("anthropic-ratelimit-output-tokens-limit"),
           "sdk": getattr(anthropic, "__version__", None)}
    out["questions_per_minute"] = questions_per_minute(out)
    return out


# One everyday question, measured on the scorecard's shape: about four requests, each
# sending ~3k uncached input tokens once the opening is cached (cache reads do not count
# toward the input-token limit), and ~1.5k output tokens with thinking, in all.
PER_QUESTION = {"requests": 4, "input": 12000, "output": 6000}


def questions_per_minute(lim: dict) -> int | None:
    caps = []
    for key, per in (("requests_per_minute", "requests"), ("input_tokens_per_minute", "input"),
                     ("output_tokens_per_minute", "output")):
        if lim.get(key):
            caps.append(lim[key] // PER_QUESTION[per])
    return min(caps) if caps else None
