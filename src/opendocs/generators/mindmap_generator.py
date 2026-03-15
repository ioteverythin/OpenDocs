"""Generate a Mermaid mindmap diagram and hierarchical JSON from the document tree.

Produces two artifacts inside a single Markdown report:

1. **Mermaid mindmap** — rendered from the Section tree using Mermaid's
   ``mindmap`` diagram type.  Indentation depth tracks section nesting.
2. **JSON tree** — hierarchical ``{ name, children[] }`` structure that
   matches the output shape used by notebooklm-py's ``download_mind_map()``,
   so downstream tools (visualization libraries, other pipelines) can consume
   it directly.

Both artifacts are embedded in the output ``.md`` file.  The raw JSON is
also written as a companion ``_mindmap.json`` file for easy programmatic use.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ..core.models import (
    DocumentModel,
    GenerationResult,
    ListBlock,
    OutputFormat,
    ParagraphBlock,
    Section,
)
from .base import BaseGenerator

# Max section depth to include in the diagram (avoids unreadably large maps)
_MAX_DEPTH = 4
# Max characters per node label in the Mermaid diagram
_MAX_LABEL = 48
# Max list-item child nodes to pull from a section's content
_MAX_LIST_CHILDREN = 5

# Characters that confuse Mermaid node labels — strip them
_MERMAID_UNSAFE_RE = re.compile(r'["\(\)\[\]\{\}]')


def _safe_mermaid_label(text: str) -> str:
    """Return a label safe for embedding in a Mermaid mindmap node."""
    cleaned = _MERMAID_UNSAFE_RE.sub("", text).strip()
    if len(cleaned) > _MAX_LABEL:
        cleaned = cleaned[:_MAX_LABEL].rstrip() + "…"
    return cleaned or "…"


def _list_items_from_section(section: Section) -> list[str]:
    """Extract the first few list items from a section's blocks as child hints."""
    items: list[str] = []
    for block in section.blocks:
        if isinstance(block, ListBlock):
            for item in block.items[:_MAX_LIST_CHILDREN]:
                # Strip inline markdown and leading bullets/numbers
                clean = re.sub(r"^\s*[-*\d.]+\s*", "", item).strip()
                clean = re.sub(r"`([^`]+)`", r"\1", clean)
                if clean:
                    items.append(clean)
            if items:
                break  # only use the first list block
    return items[:_MAX_LIST_CHILDREN]


def _first_paragraph(section: Section) -> str:
    """Return the first short paragraph from a section, or ''."""
    for block in section.blocks:
        if isinstance(block, ParagraphBlock) and block.text:
            text = block.text.strip()
            if len(text) > _MAX_LABEL:
                text = text[:_MAX_LABEL].rstrip() + "…"
            return text
    return ""


# ---------------------------------------------------------------------------
# JSON tree builder
# ---------------------------------------------------------------------------

def _section_to_json(section: Section, depth: int = 1) -> dict:
    """Recursively convert a Section to a ``{ name, description, children }`` dict."""
    node: dict = {"name": section.title or "(untitled)"}

    # Add a short description hint from the first paragraph
    desc = _first_paragraph(section)
    if desc:
        node["description"] = desc

    children: list[dict] = []

    # Recurse into subsections first
    if depth < _MAX_DEPTH:
        for sub in section.subsections:
            children.append(_section_to_json(sub, depth + 1))

    # If no subsections, surface list items as leaf nodes
    if not children:
        for item in _list_items_from_section(section):
            children.append({"name": item})

    if children:
        node["children"] = children

    return node


def _doc_to_json(doc: DocumentModel) -> dict:
    """Build the full JSON tree from the DocumentModel."""
    name = doc.metadata.repo_name or "Document"
    root: dict = {
        "name": name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "children": [_section_to_json(s) for s in doc.sections],
    }
    if doc.metadata.description:
        root["description"] = doc.metadata.description
    return root


# ---------------------------------------------------------------------------
# Mermaid mindmap builder
# ---------------------------------------------------------------------------

def _render_mermaid(doc: DocumentModel) -> str:
    """Render the document section tree as a Mermaid mindmap string."""
    lines: list[str] = ["mindmap"]

    root_label = _safe_mermaid_label(doc.metadata.repo_name or "Document")
    # Root node uses double-circle shape
    lines.append(f"  root(({root_label}))")

    def _render_section(section: Section, indent: int, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        pad = "  " * indent
        label = _safe_mermaid_label(section.title or "(untitled)")
        lines.append(f"{pad}{label}")

        # Subsections recurse
        if section.subsections:
            for sub in section.subsections:
                _render_section(sub, indent + 1, depth + 1)
        else:
            # Leaf: show list items as child nodes
            child_pad = "  " * (indent + 1)
            for item in _list_items_from_section(section):
                lines.append(f"{child_pad}{_safe_mermaid_label(item)}")

    for section in doc.sections:
        _render_section(section, indent=2, depth=1)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class MindmapGenerator(BaseGenerator):
    """DocumentModel → Mermaid mindmap + hierarchical JSON."""

    format = OutputFormat.MINDMAP

    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        stem = self._safe_filename(doc.metadata.repo_name or "mindmap", "md")
        stem = f"mindmap_{stem}"
        output_path = self._ensure_dir(output_dir) / stem

        try:
            tree = _doc_to_json(doc)
            mermaid = _render_mermaid(doc)
            content = self._build_markdown(doc, mermaid, tree)
            output_path.write_text(content, encoding="utf-8")

            # Also write companion JSON file
            json_path = output_path.with_suffix(".json")
            json_path.write_text(
                json.dumps(tree, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            return GenerationResult(format=self.format, output_path=output_path)
        except Exception as exc:
            return GenerationResult(
                format=self.format,
                output_path=output_path,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Markdown report builder
    # ------------------------------------------------------------------

    def _build_markdown(self, doc: DocumentModel, mermaid: str, tree: dict) -> str:
        name = doc.metadata.repo_name or "Document"
        now = datetime.now().strftime("%B %d, %Y")
        url = doc.metadata.repo_url or ""

        lines: list[str] = []
        lines.append(f"# {name} — Mind Map")
        lines.append("")
        if doc.metadata.description:
            lines.append(f"> {self._strip_html(doc.metadata.description[:200])}")
            lines.append("")

        lines.append(f"*Generated {now}*")
        if url:
            lines.append(f"*Source: [{url}]({url})*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Stats
        total_sections = len(doc.sections)
        total_nodes = sum(1 + len(s.subsections) for s in doc.sections)
        lines.append(
            f"**{total_sections} top-level sections · {total_nodes} nodes · "
            f"{len(doc.all_blocks)} content blocks**"
        )
        lines.append("")

        # Mermaid diagram
        lines.append("## Document Structure")
        lines.append("")
        lines.append("```mermaid")
        lines.append(mermaid)
        lines.append("```")
        lines.append("")

        # Section index as a plain text reference
        lines.append("## Section Index")
        lines.append("")
        for i, section in enumerate(doc.sections, 1):
            lines.append(f"{i}. **{section.title or '(untitled)'}**")
            for sub in section.subsections:
                lines.append(f"   - {sub.title or '(untitled)'}")
                for subsub in sub.subsections:
                    lines.append(f"     - {subsub.title or '(untitled)'}")
        lines.append("")

        # JSON tree
        lines.append("## JSON Tree")
        lines.append("")
        lines.append(
            "> This JSON structure matches the output shape of "
            "notebooklm-py's `download_mind_map()` — compatible with "
            "D3.js, Observable, and other tree-visualization libraries."
        )
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(tree, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

        return "\n".join(lines)
