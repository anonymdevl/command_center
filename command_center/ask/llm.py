"""Which model provider answers: Claude or Gemini. One definition.

    bench --site <site> set-config command_center_ai_provider claude    # or gemini

Unset, the provider is whichever has a key on the site, Claude first (Gigmann's
approved provider from 14 Nov 2026). A provider named but without its key is not used:
the question box falls back to the patterns and says why, rather than calling a model
with no key.
"""

from __future__ import annotations

import frappe

from command_center.ask import claude, gemini

PROVIDERS = ("claude", "gemini")


def provider() -> str | None:
    named = (frappe.conf.get("command_center_ai_provider") or "").strip().lower()
    if named in PROVIDERS:
        return named if _has_key(named) else None
    if claude.configured():
        return "claude"
    if gemini.configured():
        return "gemini"
    return None


def _has_key(name: str) -> bool:
    return claude.configured() if name == "claude" else gemini.configured()


def configured() -> bool:
    return provider() is not None


def analyst_model(deep: bool = False) -> str | None:
    p = provider()
    if p == "claude":
        return claude.model_for("deep" if deep else "analyst")
    if p == "gemini":
        return gemini.analyst_model()
    return None


def label(model: str | None) -> str:
    if not model:
        return ""
    return claude.label(model) if model.startswith("claude") else gemini.label(model)


def name() -> str:
    """The provider as a person would say it."""
    return {"claude": "Claude (Anthropic)", "gemini": "Gemini (Google)"}.get(provider() or "", "none")
