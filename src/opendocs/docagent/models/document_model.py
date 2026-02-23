"""Document-related models for DocAgent."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Supported document types."""
    PRD = "prd"
    PROPOSAL = "proposal"
    SOP = "sop"
    REPORT = "report"
    SLIDES = "slides"
    CHANGELOG = "changelog"
    ONBOARDING = "onboarding"
    TECH_DEBT = "tech_debt"


class ExportFormat(str, Enum):
    """Output file formats."""
    WORD = "word"
    PDF = "pdf"
    PPTX = "pptx"


class DraftDocument(BaseModel):
    """A draft document produced by a skill."""
    doc_type: DocumentType
    title: str = ""
    content: str = ""          # Markdown content
    version: int = 1
    sections: list[str] = Field(default_factory=list)  # section titles for tracking


class ReviewFeedback(BaseModel):
    """Feedback from the reviewer skill."""
    issues: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    clarity_score: float = 0.0   # 0–1
    suggestions: list[str] = Field(default_factory=list)
    passed: bool = False
