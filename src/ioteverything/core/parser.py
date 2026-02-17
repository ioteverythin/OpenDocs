"""Deterministic Markdown → DocumentModel parser (Mode 1).

Uses *mistune 3.x* to build a Markdown AST then walks it to produce
a structured ``DocumentModel``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import mistune

from .models import (
    BlockquoteBlock,
    CodeBlock,
    ContentBlock,
    DocumentMetadata,
    DocumentModel,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    MermaidBlock,
    ParagraphBlock,
    Section,
    TableBlock,
    ThematicBreakBlock,
)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _extract_text(node: dict[str, Any]) -> str:
    """Recursively extract plain text from an AST node."""
    if isinstance(node, str):
        return node

    text_parts: list[str] = []

    # Direct text / raw content
    if "raw" in node:
        text_parts.append(node["raw"])
    if "text" in node:
        text_parts.append(node["text"])

    # Children
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            text_parts.append(_extract_text(child))
    elif isinstance(children, str):
        text_parts.append(children)

    return "".join(text_parts)


def _extract_table_cells(row_children: list[dict]) -> list[str]:
    """Extract cell text from a table row's children."""
    return [_extract_text(cell).strip() for cell in row_children]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class ReadmeParser:
    """Parse raw Markdown into a ``DocumentModel``."""

    def __init__(self) -> None:
        self._md = mistune.create_markdown(renderer="ast", plugins=["table"])

    def parse(
        self,
        markdown: str,
        *,
        repo_name: str = "",
        repo_url: str = "",
        source_path: str = "",
    ) -> DocumentModel:
        """Parse *markdown* text and return a ``DocumentModel``."""
        ast_nodes: list[dict[str, Any]] = self._md(markdown)  # type: ignore[assignment]

        all_blocks = self._walk_ast(ast_nodes)
        sections = self._build_sections(all_blocks)
        mermaid_diagrams = [
            b.code for b in all_blocks if isinstance(b, MermaidBlock)
        ]

        # Derive description from first paragraph
        description = ""
        for b in all_blocks:
            if isinstance(b, ParagraphBlock):
                description = b.text[:300]
                break

        metadata = DocumentMetadata(
            repo_name=repo_name,
            repo_url=repo_url,
            description=description,
            source_path=source_path,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        return DocumentModel(
            metadata=metadata,
            sections=sections,
            all_blocks=all_blocks,
            mermaid_diagrams=mermaid_diagrams,
            raw_markdown=markdown,
        )

    # ------------------------------------------------------------------
    # AST walking
    # ------------------------------------------------------------------

    def _walk_ast(self, nodes: list[dict[str, Any]]) -> list[ContentBlock]:
        """Convert a flat mistune AST into a list of ContentBlock objects."""
        blocks: list[ContentBlock] = []
        for node in nodes:
            block = self._node_to_block(node)
            if block is not None:
                blocks.append(block)
        return blocks

    def _node_to_block(self, node: dict[str, Any]) -> ContentBlock | None:  # noqa: PLR0911
        ntype = node.get("type", "")

        if ntype == "heading":
            return HeadingBlock(
                level=node.get("attrs", {}).get("level", 1),
                text=_extract_text(node).strip(),
            )

        if ntype == "paragraph":
            text = _extract_text(node).strip()
            if text:
                return ParagraphBlock(text=text)
            return None

        if ntype == "code_block":
            raw = node.get("raw", "") or node.get("text", "")
            info = node.get("attrs", {}).get("info", "") or ""
            lang = info.split()[0] if info else ""
            # Detect mermaid diagrams
            if lang.lower() == "mermaid":
                return MermaidBlock(code=raw)
            return CodeBlock(language=lang, code=raw)

        if ntype == "block_code":
            raw = node.get("raw", "") or _extract_text(node)
            info = node.get("attrs", {}).get("info", "") or ""
            lang = info.split()[0] if info else ""
            if lang.lower() == "mermaid":
                return MermaidBlock(code=raw)
            return CodeBlock(language=lang, code=raw)

        if ntype == "table":
            return self._parse_table(node)

        if ntype in ("list", "bullet_list", "ordered_list"):
            return self._parse_list(node)

        if ntype == "block_quote":
            text = _extract_text(node).strip()
            return BlockquoteBlock(text=text)

        if ntype == "image":
            attrs = node.get("attrs", {})
            return ImageBlock(
                alt=attrs.get("alt", ""),
                src=attrs.get("src", "") or attrs.get("url", ""),
            )

        if ntype == "thematic_break":
            return ThematicBreakBlock()

        return None

    # ------------------------------------------------------------------
    # Composite blocks
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_table(node: dict[str, Any]) -> TableBlock:
        children = node.get("children", [])
        headers: list[str] = []
        rows: list[list[str]] = []

        for child in children:
            ctype = child.get("type", "")
            child_children = child.get("children", [])
            if ctype in ("table_head", "thead"):
                # In mistune 3.x, table_head children can be:
                #   - table_cell nodes directly (no row wrapper), or
                #   - table_row nodes containing table_cell children
                if child_children and child_children[0].get("type") in ("table_cell",):
                    # Cells are direct children — no row wrapper
                    headers = _extract_table_cells(child_children)
                else:
                    # Row wrappers present
                    for row in child_children:
                        headers = _extract_table_cells(row.get("children", []))
            elif ctype in ("table_body", "tbody"):
                for row in child_children:
                    row_children = row.get("children", [])
                    rows.append(_extract_table_cells(row_children))

        return TableBlock(headers=headers, rows=rows)

    @staticmethod
    def _parse_list(node: dict[str, Any]) -> ListBlock:
        ordered = node.get("type") == "ordered_list" or node.get("attrs", {}).get(
            "ordered", False
        )
        items: list[str] = []
        for child in node.get("children", []):
            items.append(_extract_text(child).strip())
        return ListBlock(ordered=ordered, items=items)

    # ------------------------------------------------------------------
    # Section builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_sections(blocks: list[ContentBlock]) -> list[Section]:
        """Group blocks into a hierarchical section tree based on headings."""
        root_sections: list[Section] = []
        section_stack: list[Section] = []

        for block in blocks:
            if isinstance(block, HeadingBlock):
                new_section = Section(
                    title=block.text,
                    level=block.level,
                    blocks=[],
                )
                # Pop stack until we find a parent with a lower level
                while section_stack and section_stack[-1].level >= block.level:
                    section_stack.pop()

                if section_stack:
                    section_stack[-1].subsections.append(new_section)
                else:
                    root_sections.append(new_section)

                section_stack.append(new_section)
            else:
                if section_stack:
                    section_stack[-1].blocks.append(block)
                # else: content before any heading — skip or attach to a virtual root

        return root_sections
