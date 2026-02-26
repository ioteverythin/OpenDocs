"""LLM client for DocAgent — multi-provider wrapper.

Supports OpenAI, Anthropic (Claude), Google (Gemini), Ollama, and Azure OpenAI.
Falls back gracefully when the required provider package is not installed.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..llm.providers import (
    LLMProvider,
    get_provider,
    DEFAULT_PROVIDER,
)

logger = logging.getLogger("docagent.llm")

_provider: LLMProvider | None = None


def get_client(
    api_key: str | None = None,
    base_url: str | None = None,
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
) -> LLMProvider:
    """Return a cached LLM provider instance."""
    global _provider
    if _provider is not None:
        return _provider

    _provider = get_provider(
        provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
    return _provider


def reset_client() -> None:
    """Reset the cached client (useful for testing)."""
    global _provider
    _provider = None


def chat_text(
    system: str,
    user: str,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Send a chat completion and return the assistant's text reply."""
    client = get_client(api_key=api_key, base_url=base_url, provider=provider, model=model)
    logger.debug("LLM call: provider=%s, model=%s, system=%d chars, user=%d chars",
                 provider, model, len(system), len(user))

    text = client.chat(system, user)
    logger.debug("LLM response: %d chars", len(text))
    return text.strip()


def chat_json(
    system: str,
    user: str,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> dict:
    """Send a chat completion expecting JSON output.

    Each provider handles JSON mode natively where supported,
    with fallback to prompt-guided JSON extraction.
    """
    client = get_client(api_key=api_key, base_url=base_url, provider=provider, model=model)

    try:
        return client.chat_json(system, user)
    except Exception as exc:
        logger.warning("JSON mode failed, attempting text parse: %s", exc)
        # Fallback — get plain text and parse
        text = client.chat(system, user).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON response, returning raw text")
            return {"raw": text}
