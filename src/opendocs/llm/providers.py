"""Unified multi-LLM provider abstraction.

Supports OpenAI, Anthropic (Claude), Google (Gemini), Ollama, and Azure OpenAI.
Each provider exposes a consistent ``chat()`` and ``chat_json()`` interface so
every part of the pipeline can use any backend without code changes.

Usage::

    from opendocs.llm.providers import get_provider

    # OpenAI (default)
    llm = get_provider("openai", api_key="sk-...", model="gpt-4o-mini")

    # Anthropic / Claude
    llm = get_provider("anthropic", api_key="sk-ant-...", model="claude-sonnet-4-20250514")

    # Google Gemini
    llm = get_provider("google", api_key="AIza...", model="gemini-1.5-flash")

    # Ollama (local)
    llm = get_provider("ollama", model="llama3.1")

    # Azure OpenAI
    llm = get_provider("azure", api_key="...", model="gpt-4o-mini",
                        base_url="https://YOUR.openai.azure.com/",
                        api_version="2024-02-15-preview")

    text = llm.chat("You are helpful.", "Explain asyncio.")
    data = llm.chat_json("Return JSON.", "List 3 colors.")
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("opendocs.llm.providers")

# ── Defaults ──────────────────────────────────────────────────────────────

DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_RETRIES = 3

# Provider → env-var mapping for API keys
_KEY_ENV_VARS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "ollama": "",  # no key needed
    "azure": "AZURE_OPENAI_API_KEY",
}

# Provider → default model
_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-1.5-flash",
    "gemini": "gemini-1.5-flash",
    "ollama": "llama3.1",
    "azure": "gpt-4o-mini",
}


# ══════════════════════════════════════════════════════════════════════════
# Base class
# ══════════════════════════════════════════════════════════════════════════


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **kwargs: Any,
    ):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.extra = kwargs

    # ── Public API ────────────────────────────────────────────────────

    def chat(self, system: str, user: str) -> str:
        """Send a chat completion with retry.  Returns plain text."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self._call(system, user)
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "LLM request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, self.max_retries, exc, wait,
                )
                time.sleep(wait)
        raise RuntimeError(
            f"LLM request failed after {self.max_retries} attempts: {last_exc}"
        )

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        """Send a chat completion expecting JSON output.

        Each provider implements its own JSON-mode strategy.
        Falls back to parsing raw text as JSON.
        """
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                raw = self._call_json(system, user)
                return self._parse_json(raw)
            except json.JSONDecodeError as exc:
                last_exc = exc
                logger.warning("JSON parse failed (attempt %d): %s", attempt + 1, exc)
                time.sleep(1)
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "LLM JSON request failed (attempt %d/%d): %s",
                    attempt + 1, self.max_retries, exc,
                )
                time.sleep(wait)
        raise RuntimeError(
            f"LLM JSON request failed after {self.max_retries} attempts: {last_exc}"
        )

    # ── Subclass hooks ────────────────────────────────────────────────

    @abstractmethod
    def _call(self, system: str, user: str) -> str:
        """Provider-specific chat completion → plain text."""

    def _call_json(self, system: str, user: str) -> str:
        """Provider-specific JSON-mode call → raw text.

        Default implementation just calls ``_call()`` with a JSON hint
        appended to the system prompt.
        """
        json_hint = (
            "\n\nIMPORTANT: You MUST respond with valid JSON only. "
            "No markdown fences, no commentary — just the JSON object."
        )
        return self._call(system + json_hint, user)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Parse JSON from LLM output, stripping markdown code fences."""
        text = raw.strip()
        # Strip ```json ... ``` wrappers
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first line (```json) and last line (```)
            if lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
            else:
                text = "\n".join(lines[1:])
            text = text.strip()
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        # If the model returned a list, wrap it
        return {"items": result}

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__.replace("Provider", "").lower()


# ══════════════════════════════════════════════════════════════════════════
# OpenAI
# ══════════════════════════════════════════════════════════════════════════


class OpenAIProvider(LLMProvider):
    """Standard OpenAI API (also used for generic OpenAI-compatible servers)."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI provider requires the 'openai' package. "
                "Install with: pip install opendocs[llm]"
            )
        key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key and not self.base_url:
            raise RuntimeError(
                "No OpenAI API key found. Pass --api-key or set OPENAI_API_KEY."
            )
        ctor_kwargs: dict[str, Any] = {"api_key": key or "not-needed"}
        if self.base_url:
            ctor_kwargs["base_url"] = self.base_url
        self._client = OpenAI(**ctor_kwargs)

    def _call(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def _call_json(self, system: str, user: str) -> str:
        """OpenAI supports native JSON mode."""
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content or "{}"
        except Exception:
            # Fallback for models that don't support response_format
            return super()._call_json(system, user)


# ══════════════════════════════════════════════════════════════════════════
# Anthropic (Claude)
# ══════════════════════════════════════════════════════════════════════════


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.model = self.model if self.model != DEFAULT_MODEL else _DEFAULT_MODELS["anthropic"]
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "Anthropic provider requires the 'anthropic' package. "
                "Install with: pip install anthropic"
            )
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError(
                "No Anthropic API key found. Pass --api-key or set ANTHROPIC_API_KEY."
            )
        ctor_kwargs: dict[str, Any] = {"api_key": key}
        if self.base_url:
            ctor_kwargs["base_url"] = self.base_url
        self._client = Anthropic(**ctor_kwargs)

    def _call(self, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Anthropic returns content blocks
        return resp.content[0].text if resp.content else ""

    def _call_json(self, system: str, user: str) -> str:
        """Claude doesn't have a native JSON mode; we guide via system prompt."""
        json_system = (
            system
            + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
            "No markdown fences, no commentary, no explanation — just the JSON object or array."
        )
        return self._call(json_system, user)


# ══════════════════════════════════════════════════════════════════════════
# Google Gemini
# ══════════════════════════════════════════════════════════════════════════


class GoogleProvider(LLMProvider):
    """Google Generative AI (Gemini) API."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.model = self.model if self.model != DEFAULT_MODEL else _DEFAULT_MODELS["google"]
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "Google provider requires the 'google-generativeai' package. "
                "Install with: pip install google-generativeai"
            )
        key = self.api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not key:
            raise RuntimeError(
                "No Google API key found. Pass --api-key or set GOOGLE_API_KEY."
            )
        genai.configure(api_key=key)
        self._genai = genai
        self._gmodel = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=None,  # set per-call
            generation_config=genai.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )

    def _call(self, system: str, user: str) -> str:
        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system,
            generation_config=self._genai.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )
        resp = model.generate_content(user)
        return resp.text or ""

    def _call_json(self, system: str, user: str) -> str:
        """Gemini supports response_mime_type for JSON."""
        json_system = (
            system
            + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
            "No markdown fences, no commentary — just the JSON object."
        )
        try:
            model = self._genai.GenerativeModel(
                model_name=self.model,
                system_instruction=json_system,
                generation_config=self._genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    response_mime_type="application/json",
                ),
            )
            resp = model.generate_content(user)
            return resp.text or "{}"
        except Exception:
            # Fallback — some Gemini models don't support response_mime_type
            return self._call(json_system, user)


# ══════════════════════════════════════════════════════════════════════════
# Ollama (local models)
# ══════════════════════════════════════════════════════════════════════════


class OllamaProvider(LLMProvider):
    """Ollama local inference — uses the OpenAI-compatible endpoint.

    By default connects to ``http://localhost:11434/v1``.
    No API key required.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.model = self.model if self.model != DEFAULT_MODEL else _DEFAULT_MODELS["ollama"]
        if not self.base_url:
            self.base_url = "http://localhost:11434/v1"
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "Ollama provider requires the 'openai' package for its "
                "OpenAI-compatible endpoint. Install with: pip install openai"
            )
        self._client = OpenAI(
            api_key=self.api_key or "ollama",  # Ollama ignores the key
            base_url=self.base_url,
        )

    def _call(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def _call_json(self, system: str, user: str) -> str:
        """Ollama supports JSON mode via format param in some versions."""
        json_system = (
            system
            + "\n\nIMPORTANT: You MUST respond with valid JSON only. "
            "No markdown fences, no commentary — just the JSON object."
        )
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": json_system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content or "{}"
        except Exception:
            return self._call(json_system, user)


# ══════════════════════════════════════════════════════════════════════════
# Azure OpenAI
# ══════════════════════════════════════════════════════════════════════════


class AzureProvider(LLMProvider):
    """Azure OpenAI Service.

    Requires ``base_url`` (your Azure endpoint) and optionally
    ``api_version`` in kwargs.
    """

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        try:
            from openai import AzureOpenAI
        except ImportError:
            raise ImportError(
                "Azure provider requires the 'openai' package. "
                "Install with: pip install openai"
            )
        key = self.api_key or os.environ.get("AZURE_OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError(
                "No Azure OpenAI API key found. Pass --api-key or set AZURE_OPENAI_API_KEY."
            )
        if not self.base_url:
            self.base_url = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if not self.base_url:
            raise RuntimeError(
                "Azure provider requires --base-url or AZURE_OPENAI_ENDPOINT."
            )
        api_version = self.extra.get(
            "api_version",
            os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        )
        self._client = AzureOpenAI(
            api_key=key,
            azure_endpoint=self.base_url,
            api_version=api_version,
        )

    def _call(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,  # This is the deployment name in Azure
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def _call_json(self, system: str, user: str) -> str:
        """Azure OpenAI supports native JSON mode."""
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content or "{}"
        except Exception:
            return super()._call_json(system, user)


# ══════════════════════════════════════════════════════════════════════════
# Async wrappers (for the agents layer)
# ══════════════════════════════════════════════════════════════════════════


class AsyncLLMProvider(ABC):
    """Async base class for providers used in the agents layer."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        **kwargs: Any,
    ):
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra = kwargs

    @abstractmethod
    async def chat(self, system: str, user: str) -> str:
        """Async chat completion → plain text."""

    @abstractmethod
    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        """Async chat completion → parsed JSON dict."""

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        return LLMProvider._parse_json(raw)


class AsyncOpenAIProvider(AsyncLLMProvider):
    """Async OpenAI provider for the agents layer."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "OpenAI provider requires the 'openai' package. "
                "Install with: pip install opendocs[llm]"
            )
        key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key and not self.base_url:
            raise RuntimeError(
                "No OpenAI API key found. Pass --api-key or set OPENAI_API_KEY."
            )
        ctor_kwargs: dict[str, Any] = {"api_key": key or "not-needed"}
        if self.base_url:
            ctor_kwargs["base_url"] = self.base_url
        self._client = AsyncOpenAI(**ctor_kwargs)

    async def chat(self, system: str, user: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
        except Exception:
            raw = await self.chat(
                system + "\n\nRespond with valid JSON only.",
                user,
            )
        return self._parse_json(raw)


class AsyncAnthropicProvider(AsyncLLMProvider):
    """Async Anthropic (Claude) provider for the agents layer."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.model = self.model if self.model != DEFAULT_MODEL else _DEFAULT_MODELS["anthropic"]
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError(
                "Anthropic provider requires the 'anthropic' package. "
                "Install with: pip install anthropic"
            )
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("No Anthropic API key. Set ANTHROPIC_API_KEY.")
        ctor_kwargs: dict[str, Any] = {"api_key": key}
        if self.base_url:
            ctor_kwargs["base_url"] = self.base_url
        self._client = AsyncAnthropic(**ctor_kwargs)

    async def chat(self, system: str, user: str) -> str:
        resp = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text if resp.content else ""

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        json_system = (
            system
            + "\n\nRespond with valid JSON only. No markdown, no commentary."
        )
        raw = await self.chat(json_system, user)
        return self._parse_json(raw)


class AsyncGoogleProvider(AsyncLLMProvider):
    """Async Google Gemini provider for the agents layer."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.model = self.model if self.model != DEFAULT_MODEL else _DEFAULT_MODELS["google"]
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "Google provider requires the 'google-generativeai' package. "
                "Install with: pip install google-generativeai"
            )
        key = self.api_key or os.environ.get("GOOGLE_API_KEY", "")
        if not key:
            raise RuntimeError("No Google API key. Set GOOGLE_API_KEY.")
        genai.configure(api_key=key)
        self._genai = genai

    async def chat(self, system: str, user: str) -> str:
        # google-generativeai is sync; we run it in the default executor
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_call, system, user)

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        import asyncio
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None, self._sync_call_json, system, user,
        )
        return self._parse_json(raw)

    def _sync_call(self, system: str, user: str) -> str:
        model = self._genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system,
            generation_config=self._genai.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )
        resp = model.generate_content(user)
        return resp.text or ""

    def _sync_call_json(self, system: str, user: str) -> str:
        json_system = (
            system + "\n\nRespond with valid JSON only. No markdown, no commentary."
        )
        try:
            model = self._genai.GenerativeModel(
                model_name=self.model,
                system_instruction=json_system,
                generation_config=self._genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    response_mime_type="application/json",
                ),
            )
            resp = model.generate_content(user)
            return resp.text or "{}"
        except Exception:
            return self._sync_call(json_system, user)


class AsyncOllamaProvider(AsyncLLMProvider):
    """Async Ollama provider using OpenAI-compatible endpoint."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.model = self.model if self.model != DEFAULT_MODEL else _DEFAULT_MODELS["ollama"]
        if not self.base_url:
            self.base_url = "http://localhost:11434/v1"
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("Ollama provider requires the 'openai' package.")
        self._client = AsyncOpenAI(
            api_key=self.api_key or "ollama",
            base_url=self.base_url,
        )

    async def chat(self, system: str, user: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        json_system = (
            system + "\n\nRespond with valid JSON only. No markdown, no commentary."
        )
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": json_system},
                    {"role": "user", "content": user},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
        except Exception:
            raw = await self.chat(json_system, user)
        return self._parse_json(raw)


class AsyncAzureProvider(AsyncLLMProvider):
    """Async Azure OpenAI provider for the agents layer."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        try:
            from openai import AsyncAzureOpenAI
        except ImportError:
            raise ImportError("Azure provider requires the 'openai' package.")
        key = self.api_key or os.environ.get("AZURE_OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("No Azure OpenAI API key. Set AZURE_OPENAI_API_KEY.")
        endpoint = self.base_url or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if not endpoint:
            raise RuntimeError("Azure provider requires --base-url or AZURE_OPENAI_ENDPOINT.")
        api_version = self.extra.get(
            "api_version",
            os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        )
        self._client = AsyncAzureOpenAI(
            api_key=key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    async def chat(self, system: str, user: str) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            raw = resp.choices[0].message.content or "{}"
        except Exception:
            raw = await self.chat(
                system + "\n\nRespond with valid JSON only.", user,
            )
        return self._parse_json(raw)


# ══════════════════════════════════════════════════════════════════════════
# Factory functions
# ══════════════════════════════════════════════════════════════════════════

_SYNC_PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "google": GoogleProvider,
    "gemini": GoogleProvider,
    "ollama": OllamaProvider,
    "azure": AzureProvider,
}

_ASYNC_PROVIDERS: dict[str, type[AsyncLLMProvider]] = {
    "openai": AsyncOpenAIProvider,
    "anthropic": AsyncAnthropicProvider,
    "claude": AsyncAnthropicProvider,
    "google": AsyncGoogleProvider,
    "gemini": AsyncGoogleProvider,
    "ollama": AsyncOllamaProvider,
    "azure": AsyncAzureProvider,
}

SUPPORTED_PROVIDERS = sorted(set(_SYNC_PROVIDERS.keys()) - {"claude", "gemini"})


def get_provider(
    provider: str = DEFAULT_PROVIDER,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    **kwargs: Any,
) -> LLMProvider:
    """Create a sync LLM provider instance.

    Parameters
    ----------
    provider
        Provider name: openai, anthropic, google, ollama, azure.
    api_key
        API key (falls back to provider-specific env var).
    model
        Model name (falls back to provider-specific default).
    base_url
        Custom API endpoint.
    """
    name = provider.lower().strip()
    cls = _SYNC_PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    return cls(
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=max_retries,
        **kwargs,
    )


def get_async_provider(
    provider: str = DEFAULT_PROVIDER,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    **kwargs: Any,
) -> AsyncLLMProvider:
    """Create an async LLM provider instance (for the agents layer)."""
    name = provider.lower().strip()
    cls = _ASYNC_PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown async provider '{provider}'. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    return cls(
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def resolve_api_key(provider: str, api_key: str | None = None) -> str | None:
    """Resolve API key from argument or environment variable."""
    if api_key:
        return api_key
    env_var = _KEY_ENV_VARS.get(provider.lower(), "")
    if env_var:
        return os.environ.get(env_var)
    return None


def default_model_for(provider: str) -> str:
    """Return the default model name for a given provider."""
    return _DEFAULT_MODELS.get(provider.lower(), DEFAULT_MODEL)
