"""Tests for document generators."""

from __future__ import annotations

from pathlib import Path

import pytest

from opendocs.core.parser import ReadmeParser
from opendocs.generators.diagram_extractor import DiagramExtractor
from opendocs.generators.pdf_generator import PdfGenerator
from opendocs.generators.pptx_generator import PptxGenerator
from opendocs.generators.word_generator import WordGenerator


@pytest.fixture
def sample_doc():
    """Parse the sample README into a DocumentModel."""
    sample_path = Path(__file__).parent.parent / "examples" / "sample_readme.md"
    content = sample_path.read_text(encoding="utf-8")
    parser = ReadmeParser()
    return parser.parse(content, repo_name="SmartTemp", repo_url="https://github.com/test/smarttemp")


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

class TestWordGenerator:
    def test_generates_docx(self, sample_doc, tmp_path):
        gen = WordGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.suffix == ".docx"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

class TestPdfGenerator:
    def test_generates_pdf(self, sample_doc, tmp_path):
        gen = PdfGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.suffix == ".pdf"


# ---------------------------------------------------------------------------
# PPTX
# ---------------------------------------------------------------------------

class TestPptxGenerator:
    def test_generates_pptx(self, sample_doc, tmp_path):
        gen = PptxGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.suffix == ".pptx"


# ---------------------------------------------------------------------------
# Diagram Extractor
# ---------------------------------------------------------------------------

class TestDiagramExtractor:
    def test_extracts_mermaid(self, sample_doc, tmp_path):
        extractor = DiagramExtractor()
        paths, cache = extractor.extract(sample_doc, tmp_path)
        assert len(paths) >= 1
        # Check that files actually exist and contain content
        for p in paths:
            assert p.exists()
            assert p.read_text(encoding="utf-8").strip() != ""

    def test_no_diagrams_returns_empty(self, tmp_path):
        parser = ReadmeParser()
        doc = parser.parse("# No diagrams here\n\nJust text.")
        extractor = DiagramExtractor()
        paths, cache = extractor.extract(doc, tmp_path)
        assert paths == []
        assert len(cache.mermaid_images) == 0
