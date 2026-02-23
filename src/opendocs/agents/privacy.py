"""Privacy and safety controls for the agentic layer.

By default agents receive only the ``RepoProfile`` + ``KnowledgeGraph`` +
small evidence snippets — never full source code. This module implements
the privacy toggle that controls what data flows to LLM calls.

Privacy modes
-------------
STANDARD
    Agents see RepoProfile, KG, section text, and short code snippets
    (≤20 lines) attached to evidence pointers. File names are visible.

STRICT
    No code content at all — agents only see file *names*, section
    *titles*, and pre-computed summaries. Code snippets in evidence
    pointers are replaced with ``"[code redacted]"``.

PERMISSIVE
    Full file contents may be sent to agents when needed.  Use only
    for local/self-hosted LLM deployments.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .base import RepoProfile, RepoSignal
from .evidence import EvidencePointer


# ---------------------------------------------------------------------------
# Privacy modes
# ---------------------------------------------------------------------------

class PrivacyMode(str, Enum):
    """Controls how much repo data agents can access."""
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"


# ---------------------------------------------------------------------------
# Privacy guard
# ---------------------------------------------------------------------------

class PrivacyGuard:
    """Filters data flowing to agents according to the active privacy mode.

    Instantiate once per pipeline run and pass to the orchestrator.
    All data leaving the pipeline toward an LLM must pass through
    ``sanitise_*`` methods.
    """

    def __init__(self, mode: PrivacyMode = PrivacyMode.STANDARD) -> None:
        self.mode = mode
        self._max_snippet_lines = self._snippet_limit()

    def _snippet_limit(self) -> int:
        if self.mode == PrivacyMode.STRICT:
            return 0
        if self.mode == PrivacyMode.STANDARD:
            return 20
        return 9999  # PERMISSIVE — effectively unlimited

    # -- Sanitisers ---------------------------------------------------------

    def sanitise_profile(self, profile: RepoProfile) -> RepoProfile:
        """Return a privacy-filtered copy of the RepoProfile."""
        if self.mode == PrivacyMode.PERMISSIVE:
            return profile

        # In STRICT mode, strip file tree to just top-level dirs
        file_tree = profile.file_tree
        if self.mode == PrivacyMode.STRICT:
            top_dirs = sorted({p.split("/")[0] for p in file_tree if "/" in p})
            file_tree = [f"{d}/" for d in top_dirs]

        return RepoProfile(
            repo_name=profile.repo_name,
            repo_url=profile.repo_url,
            description=profile.description,
            primary_language=profile.primary_language,
            languages=profile.languages,
            file_tree=file_tree,
            signals=profile.signals,          # signals are metadata, always safe
            readme_summary=profile.readme_summary,
            license=profile.license,
            topics=profile.topics,
        )

    def sanitise_evidence(self, pointer: EvidencePointer) -> EvidencePointer:
        """Return a privacy-filtered copy of an evidence pointer."""
        if self.mode == PrivacyMode.PERMISSIVE:
            return pointer

        snippet = pointer.snippet
        if self.mode == PrivacyMode.STRICT:
            # Redact code content entirely
            snippet = "[code redacted]" if snippet else ""
        elif self.mode == PrivacyMode.STANDARD:
            # Truncate snippets to max_snippet_lines
            lines = snippet.splitlines()
            if len(lines) > self._max_snippet_lines:
                snippet = "\n".join(lines[: self._max_snippet_lines]) + "\n[truncated]"

        return EvidencePointer(
            id=pointer.id,
            evidence_type=pointer.evidence_type,
            source_path=pointer.source_path,
            section=pointer.section,
            snippet=snippet,
            line_start=pointer.line_start,
            line_end=pointer.line_end,
            commit_sha=pointer.commit_sha,
            url=pointer.url,
            confidence=pointer.confidence,
            metadata=pointer.metadata,
        )

    def sanitise_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generic context dict sanitiser for arbitrary payloads.

        Recursively strips keys containing ``code``, ``source``, or
        ``raw`` when in STRICT mode.
        """
        if self.mode == PrivacyMode.PERMISSIVE:
            return context

        banned_keys = {"code", "source_code", "raw_content", "raw_markdown", "file_content"}
        if self.mode != PrivacyMode.STRICT:
            return context

        def _strip(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {
                    k: "[redacted]" if k in banned_keys else _strip(v)
                    for k, v in obj.items()
                }
            if isinstance(obj, list):
                return [_strip(item) for item in obj]
            return obj

        return _strip(context)  # type: ignore[return-value]

    # -- Convenience --------------------------------------------------------

    def allows_code(self) -> bool:
        """Whether the current mode permits sending code to agents."""
        return self.mode != PrivacyMode.STRICT

    def allows_full_files(self) -> bool:
        """Whether agents may receive complete file contents."""
        return self.mode == PrivacyMode.PERMISSIVE
