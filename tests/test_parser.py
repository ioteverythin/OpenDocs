"""Tests for the Markdown parser."""

from __future__ import annotations

import pytest

from ioteverything.core.models import (
    BlockquoteBlock,
    CodeBlock,
    HeadingBlock,
    ListBlock,
    MermaidBlock,
    ParagraphBlock,
    TableBlock,
)
from ioteverything.core.parser import ReadmeParser


@pytest.fixture
def parser():
    return ReadmeParser()


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------

class TestBasicParsing:
    def test_parse_heading(self, parser):
        doc = parser.parse("# Hello World")
        assert len(doc.sections) == 1
        assert doc.sections[0].title == "Hello World"
        assert doc.sections[0].level == 1

    def test_parse_paragraph(self, parser):
        doc = parser.parse("# Title\n\nThis is a paragraph.")
        blocks = doc.sections[0].blocks
        assert any(isinstance(b, ParagraphBlock) for b in blocks)

    def test_parse_code_block(self, parser):
        md = "# Code\n\n```python\nprint('hello')\n```"
        doc = parser.parse(md)
        code_blocks = [b for b in doc.all_blocks if isinstance(b, CodeBlock)]
        assert len(code_blocks) == 1
        assert code_blocks[0].language == "python"
        assert "print" in code_blocks[0].code

    def test_parse_multiple_sections(self, parser):
        md = "# Section 1\n\nText 1\n\n# Section 2\n\nText 2"
        doc = parser.parse(md)
        assert len(doc.sections) == 2

    def test_nested_headings(self, parser):
        md = "# H1\n\n## H2\n\n### H3\n\nDeep content"
        doc = parser.parse(md)
        assert len(doc.sections) == 1  # one root
        assert len(doc.sections[0].subsections) == 1  # H2
        assert len(doc.sections[0].subsections[0].subsections) == 1  # H3


# ---------------------------------------------------------------------------
# Mermaid detection
# ---------------------------------------------------------------------------

class TestMermaidDetection:
    def test_mermaid_block_extracted(self, parser):
        md = "# Arch\n\n```mermaid\ngraph TD\n  A-->B\n```"
        doc = parser.parse(md)
        assert len(doc.mermaid_diagrams) == 1
        assert "A-->B" in doc.mermaid_diagrams[0]

    def test_mermaid_appears_in_all_blocks(self, parser):
        md = "# X\n\n```mermaid\nflowchart LR\n  X-->Y\n```"
        doc = parser.parse(md)
        mermaid_blocks = [b for b in doc.all_blocks if isinstance(b, MermaidBlock)]
        assert len(mermaid_blocks) == 1


# ---------------------------------------------------------------------------
# Tables & Lists
# ---------------------------------------------------------------------------

class TestComplex:
    def test_list_block(self, parser):
        md = "# Items\n\n- Alpha\n- Beta\n- Gamma"
        doc = parser.parse(md)
        lists = [b for b in doc.all_blocks if isinstance(b, ListBlock)]
        assert len(lists) == 1
        assert len(lists[0].items) == 3

    def test_blockquote(self, parser):
        md = "# Q\n\n> This is a quote"
        doc = parser.parse(md)
        quotes = [b for b in doc.all_blocks if isinstance(b, BlockquoteBlock)]
        assert len(quotes) == 1


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_repo_name_set(self, parser):
        doc = parser.parse("# Hello", repo_name="test/repo")
        assert doc.metadata.repo_name == "test/repo"

    def test_description_from_first_paragraph(self, parser):
        md = "# Title\n\nThis is the description."
        doc = parser.parse(md)
        assert "description" in doc.metadata.description.lower()

    def test_generated_at_present(self, parser):
        doc = parser.parse("# X")
        assert doc.metadata.generated_at != ""
