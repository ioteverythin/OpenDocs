"""Pydantic models for structured document representation.

These models form the intermediate representation (IR) between
the Markdown parser and the output generators. Every generator
consumes a DocumentModel and produces a file in its target format.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OutputFormat(str, Enum):
    """Supported output formats."""
    WORD = "word"
    PDF = "pdf"
    PPTX = "pptx"
    ALL = "all"


class BlockType(str, Enum):
    """Types of content blocks extracted from the README."""
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE = "code"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"
    BLOCKQUOTE = "blockquote"
    MERMAID = "mermaid"
    THEMATIC_BREAK = "thematic_break"


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------

class HeadingBlock(BaseModel):
    """A heading (h1–h6)."""
    type: BlockType = BlockType.HEADING
    level: int = Field(ge=1, le=6)
    text: str


class ParagraphBlock(BaseModel):
    """A paragraph of text (may contain inline markdown)."""
    type: BlockType = BlockType.PARAGRAPH
    text: str


class CodeBlock(BaseModel):
    """A fenced code block."""
    type: BlockType = BlockType.CODE
    language: str = ""
    code: str


class TableBlock(BaseModel):
    """A markdown table."""
    type: BlockType = BlockType.TABLE
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)


class ListBlock(BaseModel):
    """An ordered or unordered list."""
    type: BlockType = BlockType.LIST
    ordered: bool = False
    items: list[str] = Field(default_factory=list)


class ImageBlock(BaseModel):
    """An image reference."""
    type: BlockType = BlockType.IMAGE
    alt: str = ""
    src: str = ""


class BlockquoteBlock(BaseModel):
    """A blockquote."""
    type: BlockType = BlockType.BLOCKQUOTE
    text: str


class MermaidBlock(BaseModel):
    """A Mermaid diagram block (extracted from code fences)."""
    type: BlockType = BlockType.MERMAID
    code: str


class ThematicBreakBlock(BaseModel):
    """A thematic break / horizontal rule."""
    type: BlockType = BlockType.THEMATIC_BREAK


# Union of all block types
ContentBlock = (
    HeadingBlock
    | ParagraphBlock
    | CodeBlock
    | TableBlock
    | ListBlock
    | ImageBlock
    | BlockquoteBlock
    | MermaidBlock
    | ThematicBreakBlock
)


# ---------------------------------------------------------------------------
# Section & Document
# ---------------------------------------------------------------------------

class Section(BaseModel):
    """A logical section of the document (headed by a heading block)."""
    title: str = ""
    level: int = 1
    blocks: list[ContentBlock] = Field(default_factory=list)
    subsections: list[Section] = Field(default_factory=list)


class DocumentMetadata(BaseModel):
    """Metadata about the source repository / README."""
    repo_name: str = ""
    repo_url: str = ""
    description: str = ""
    source_path: str = ""
    generated_at: str = ""


class DocumentModel(BaseModel):
    """The top-level intermediate representation of a parsed README.

    Every generator receives an instance of this model and produces
    its output format from it.
    """
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    sections: list[Section] = Field(default_factory=list)
    all_blocks: list[ContentBlock] = Field(default_factory=list)
    mermaid_diagrams: list[str] = Field(default_factory=list)
    raw_markdown: str = ""


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

class GenerationResult(BaseModel):
    """Result of a single generator run."""
    format: OutputFormat
    output_path: Path
    success: bool = True
    error: Optional[str] = None


class PipelineResult(BaseModel):
    """Aggregate result of the full pipeline."""
    source: str = ""
    results: list[GenerationResult] = Field(default_factory=list)

    @property
    def word_path(self) -> Optional[Path]:
        return self._path_for(OutputFormat.WORD)

    @property
    def pdf_path(self) -> Optional[Path]:
        return self._path_for(OutputFormat.PDF)

    @property
    def pptx_path(self) -> Optional[Path]:
        return self._path_for(OutputFormat.PPTX)

    def _path_for(self, fmt: OutputFormat) -> Optional[Path]:
        for r in self.results:
            if r.format == fmt and r.success:
                return r.output_path
        return None
