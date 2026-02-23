"""LLM client for DocAgent — OpenAI-compatible wrapper.

Supports both synchronous and async usage. Falls back gracefully
when the ``openai`` package is not installed or no API key is set.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("docagent.llm")

_client: Any = None


def get_client(
    api_key: str | None = None,
    base_url: str | None = None,
):
    """Return a cached OpenAI client instance."""
    global _client
    if _client is not None:
        return _client

    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package is required for LLM mode. "
            "Install it with: pip install openai"
        )

    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "No OpenAI API key found. Pass --api-key or set OPENAI_API_KEY."
        )

    kwargs: dict[str, Any] = {"api_key": key}
    if base_url:
        kwargs["base_url"] = base_url

    _client = OpenAI(**kwargs)
    return _client


def reset_client() -> None:
    """Reset the cached client (useful for testing)."""
    global _client
    _client = None


def chat_text(
    system: str,
    user: str,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Send a chat completion and return the assistant's text reply."""
    client = get_client(api_key=api_key, base_url=base_url)
    logger.debug("LLM call: model=%s, system=%d chars, user=%d chars",
                 model, len(system), len(user))

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = response.choices[0].message.content or ""
    logger.debug("LLM response: %d chars", len(text))
    return text.strip()


def chat_json(
    system: str,
    user: str,
    *,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> dict:
    """Send a chat completion expecting JSON output.

    Tries ``response_format={"type": "json_object"}`` first,
    falls back to parsing the text as JSON.
    """
    client = get_client(api_key=api_key, base_url=base_url)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or "{}"
    except Exception:
        # Fallback — no JSON mode support
        text = chat_text(
            system, user,
            model=model, api_key=api_key, base_url=base_url,
            temperature=temperature, max_tokens=max_tokens,
        )

    # Parse JSON from response (handle markdown code fences)
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM JSON response, returning raw text")
        return {"raw": text}
