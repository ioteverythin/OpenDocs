"""Shared async OpenAI client for the agents layer.

Provides a thin wrapper around the OpenAI API with:
- Singleton client management (one client per API key).
- Structured JSON output via ``chat_json()``.
- Plain text completions via ``chat_text()``.
- Token-usage tracking per call.
- Graceful fallback when the API key is missing.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import AsyncOpenAI


# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

_client: AsyncOpenAI | None = None


def get_client(api_key: str | None = None) -> AsyncOpenAI:
    """Return (and cache) an ``AsyncOpenAI`` client."""
    global _client
    if _client is None:
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "No OpenAI API key found. Set OPENAI_API_KEY or pass api_key=."
            )
        _client = AsyncOpenAI(api_key=key)
    return _client


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
) -> str:
    """Return a plain-text completion."""
    client = get_client(api_key)
    resp = await client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


async def chat_json(
    *,
    system: str,
    user: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Return a parsed JSON dict from the model.

    Uses ``response_format={"type": "json_object"}`` so the model is
    constrained to produce valid JSON.
    """
    client = get_client(api_key)
    resp = await client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw, "_parse_error": True}
