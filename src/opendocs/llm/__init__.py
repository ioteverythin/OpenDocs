"""LLM-powered extraction and generation (Mode 2).

Supports multiple providers: OpenAI, Anthropic (Claude), Google (Gemini),
Ollama (local), and Azure OpenAI.

Requires ``pip install opendocs[llm]`` for OpenAI/LangChain deps.
Additional providers: ``pip install anthropic``, ``pip install google-generativeai``.
Falls back gracefully if not installed.
"""

from .providers import (  # noqa: F401
    get_provider,
    get_async_provider,
    SUPPORTED_PROVIDERS,
    DEFAULT_PROVIDER,
    default_model_for,
    resolve_api_key,
)
