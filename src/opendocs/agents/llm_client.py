"""Shared async LLM client for the agents layer.

Provides a thin wrapper around the multi-provider LLM system with:
- Singleton provider management.
- Structured JSON output via ``chat_json()``.
- Plain text completions via ``chat_text()``.
- Support for OpenAI, Anthropic (Claude), Google (Gemini), Ollama, Azure.
- Graceful fallback when the API key is missing.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..llm.providers import (
    AsyncLLMProvider,
    get_async_provider,
    DEFAULT_PROVIDER,
)

# ---------------------------------------------------------------------------
# Singleton provider
# ---------------------------------------------------------------------------

_provider: AsyncLLMProvider | None = None


def get_client(
    api_key: str | None = None,
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    base_url: str | None = None,
) -> AsyncLLMProvider:
    """Return (and cache) an async LLM provider."""
    global _provider
    if _provider is None:
        _provider = get_async_provider(
            provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
        )
    return _provider


def reset_client() -> None:
    """Reset the cached provider (useful for testing)."""
    global _provider
    _provider = None


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

async def chat_text(
    *,
    system: str,
    user: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    max_tokens: int = 2048,
    api_key: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    base_url: str | None = None,
) -> str:
    """Return a plain-text completion."""
    client = get_client(api_key, provider=provider, model=model, base_url=base_url)
    return await client.chat(system, user)


async def chat_json(
    *,
    system: str,
    user: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    api_key: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Return a parsed JSON dict from the model.

    Each provider handles JSON mode differently:
    - OpenAI/Azure: native ``response_format``
    - Anthropic: guided via system prompt
    - Gemini: ``response_mime_type``
    - Ollama: ``response_format`` where supported
    """
    client = get_client(api_key, provider=provider, model=model, base_url=base_url)
    return await client.chat_json(system, user)
