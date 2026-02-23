"""Abstract base class for document generators."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..core.knowledge_graph import KnowledgeGraph
from ..core.models import DocumentModel, GenerationResult, OutputFormat
from .themes import DEFAULT_THEME, Theme
from .styles import apply_theme

# Pre-compiled regex for stripping HTML tags
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# Collapse whitespace runs into a single space
_MULTI_SPACE_RE = re.compile(r"\s{2,}")

if TYPE_CHECKING:
    from .diagram_extractor import ImageCache


class BaseGenerator(ABC):
    """Every generator inherits from this class.

    Generators accept an optional ``Theme`` to control colors/fonts,
    an optional ``KnowledgeGraph`` for semantic-enriched output, and
    an optional ``ImageCache`` for embedding rendered diagrams and
    downloaded images.
    """

    format: OutputFormat  # set by subclasses

    def __init__(
        self,
        theme: Theme | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
        image_cache: "ImageCache | None" = None,
    ) -> None:
        self.theme = theme or DEFAULT_THEME
        apply_theme(self.theme)
        self.kg = knowledge_graph
        self.image_cache = image_cache

    @abstractmethod
    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        """Generate the output file and return a ``GenerationResult``."""
        ...

    # -- Helpers ---------------------------------------------------------

    @staticmethod
    def _safe_filename(name: str, ext: str) -> str:
        """Create a filesystem-safe filename."""
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
        safe = safe.strip().replace(" ", "_")[:80] or "document"
        return f"{safe}.{ext}"

    @staticmethod
    def _ensure_dir(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags and collapse whitespace.

        Turns ``<a href="...">link text</a>`` into ``link text``, etc.
        """
        cleaned = _HTML_TAG_RE.sub("", text)
        cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
        return cleaned.strip()
