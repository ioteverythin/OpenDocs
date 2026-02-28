"""Jupyter Notebook (.ipynb) → DocumentModel parser.

Reads a ``.ipynb`` file and converts its cells (Markdown, Code, outputs)
into the same ``DocumentModel`` IR consumed by all generators.

Supports:
- Markdown cells → parsed via ``ReadmeParser`` into headings, paragraphs, etc.
- Code cells → ``CodeBlock`` with detected language
- Cell outputs (text, images, HTML, errors) → rendered as appropriate blocks
- Notebook-level metadata (kernel, language) extraction
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    BlockquoteBlock,
    CodeBlock,
    ContentBlock,
    DocumentMetadata,
    DocumentModel,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    Section,
    TableBlock,
    ThematicBreakBlock,
)


# ---------------------------------------------------------------------------
# Output renderers — turn cell outputs into ContentBlocks
# ---------------------------------------------------------------------------

def _render_stream_output(output: dict[str, Any]) -> list[ContentBlock]:
    """Render ``stream`` output (stdout / stderr)."""
    text = "".join(output.get("text", []))
    if not text.strip():
        return []
    return [CodeBlock(language="text", code=text.rstrip())]


def _render_execute_result(output: dict[str, Any]) -> list[ContentBlock]:
    """Render ``execute_result`` or ``display_data`` outputs."""
    data: dict[str, Any] = output.get("data", {})
    blocks: list[ContentBlock] = []

    # Prefer image output (PNG > SVG > JPEG)
    for mime in ("image/png", "image/svg+xml", "image/jpeg"):
        if mime in data:
            b64 = data[mime]
            if isinstance(b64, list):
                b64 = "".join(b64)
            # Store as data-URI so generators can inline it
            blocks.append(ImageBlock(
                alt="Cell output",
                src=f"data:{mime};base64,{b64.strip()}",
            ))
            return blocks

    # HTML output (render as blockquote with truncated preview)
    if "text/html" in data:
        html = data["text/html"]
        if isinstance(html, list):
            html = "".join(html)
        # Strip tags for plain-text preview
        plain = re.sub(r"<[^>]+>", "", html).strip()
        if plain:
            blocks.append(BlockquoteBlock(text=f"[HTML output] {plain[:500]}"))
            return blocks

    # LaTeX / math output
    if "text/latex" in data:
        latex = data["text/latex"]
        if isinstance(latex, list):
            latex = "".join(latex)
        blocks.append(CodeBlock(language="latex", code=latex.strip()))
        return blocks

    # Plain text fallback
    if "text/plain" in data:
        text = data["text/plain"]
        if isinstance(text, list):
            text = "".join(text)
        if text.strip():
            blocks.append(CodeBlock(language="text", code=text.strip()))

    return blocks


def _render_error_output(output: dict[str, Any]) -> list[ContentBlock]:
    """Render ``error`` output (tracebacks)."""
    # ANSI escape codes are common in tracebacks — strip them
    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    traceback_lines = output.get("traceback", [])
    cleaned = [ansi_re.sub("", line) for line in traceback_lines]
    text = "\n".join(cleaned)
    if text.strip():
        return [CodeBlock(language="text", code=f"[Error] {text.strip()}")]
    return []


def _render_outputs(outputs: list[dict[str, Any]]) -> list[ContentBlock]:
    """Convert a cell's output list into ContentBlocks."""
    blocks: list[ContentBlock] = []
    for output in outputs:
        otype = output.get("output_type", "")
        if otype == "stream":
            blocks.extend(_render_stream_output(output))
        elif otype in ("execute_result", "display_data"):
            blocks.extend(_render_execute_result(output))
        elif otype == "error":
            blocks.extend(_render_error_output(output))
    return blocks


# ---------------------------------------------------------------------------
# Notebook parser
# ---------------------------------------------------------------------------

class NotebookParser:
    """Parse a Jupyter Notebook (``.ipynb``) into a ``DocumentModel``.

    Usage::

        parser = NotebookParser()
        doc = parser.parse("path/to/notebook.ipynb")
    """

    def __init__(self) -> None:
        # Lazy import — only needed when notebook contains markdown cells
        self._md_parser = None

    @property
    def md_parser(self):
        """Lazily create a ReadmeParser for markdown cells."""
        if self._md_parser is None:
            from .parser import ReadmeParser
            self._md_parser = ReadmeParser()
        return self._md_parser

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(
        self,
        source: str | Path,
        *,
        repo_name: str = "",
        repo_url: str = "",
        include_outputs: bool = True,
    ) -> DocumentModel:
        """Parse a ``.ipynb`` file and return a ``DocumentModel``.

        Parameters
        ----------
        source
            Path to the ``.ipynb`` file.
        repo_name
            Optional repository / project name for metadata.
        repo_url
            Optional repository URL for metadata.
        include_outputs
            If True (default), cell outputs are included in the document.
        """
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Notebook not found: {path}")

        with open(path, encoding="utf-8") as f:
            nb = json.load(f)

        return self._parse_notebook(nb, path, repo_name=repo_name,
                                     repo_url=repo_url,
                                     include_outputs=include_outputs)

    def parse_content(
        self,
        content: str,
        *,
        repo_name: str = "",
        repo_url: str = "",
        source_path: str = "",
        include_outputs: bool = True,
    ) -> DocumentModel:
        """Parse notebook JSON content (as string) into a ``DocumentModel``."""
        nb = json.loads(content)
        return self._parse_notebook(nb, source_path=source_path,
                                     repo_name=repo_name,
                                     repo_url=repo_url,
                                     include_outputs=include_outputs)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_notebook(
        self,
        nb: dict[str, Any],
        path: Path | None = None,
        *,
        source_path: str = "",
        repo_name: str = "",
        repo_url: str = "",
        include_outputs: bool = True,
    ) -> DocumentModel:
        """Core parsing logic for a notebook dict."""
        # Extract notebook metadata
        nb_meta = nb.get("metadata", {})
        kernel_info = nb_meta.get("kernelspec", {})
        language_info = nb_meta.get("language_info", {})
        language = (
            language_info.get("name", "")
            or kernel_info.get("language", "")
            or "python"
        )
        kernel_display = kernel_info.get("display_name", "")

        cells = nb.get("cells", [])

        all_blocks: list[ContentBlock] = []
        cell_count = {"markdown": 0, "code": 0, "output": 0}

        for cell in cells:
            cell_type = cell.get("cell_type", "")
            cell_source = "".join(cell.get("source", []))

            if cell_type == "markdown":
                cell_count["markdown"] += 1
                md_blocks = self._parse_markdown_cell(cell_source)
                all_blocks.extend(md_blocks)

            elif cell_type == "code":
                cell_count["code"] += 1
                if cell_source.strip():
                    # Add execution count indicator
                    exec_count = cell.get("execution_count")
                    label = f"In [{exec_count or ' '}]" if exec_count is not None else ""

                    code_block = CodeBlock(
                        language=language,
                        code=cell_source,
                    )
                    all_blocks.append(code_block)

                # Process outputs
                if include_outputs:
                    outputs = cell.get("outputs", [])
                    if outputs:
                        cell_count["output"] += len(outputs)
                        output_blocks = _render_outputs(outputs)
                        all_blocks.extend(output_blocks)

            elif cell_type == "raw":
                # Raw cells → code blocks with no language
                if cell_source.strip():
                    all_blocks.append(CodeBlock(language="", code=cell_source))

        # Build section hierarchy
        sections = self._build_sections(all_blocks)

        # Derive description
        description = ""
        for b in all_blocks:
            if isinstance(b, ParagraphBlock):
                description = b.text[:300]
                break
        if not description and kernel_display:
            description = f"Jupyter Notebook ({kernel_display})"

        # Derive repo_name from path if not provided
        if not repo_name and path:
            repo_name = path.stem

        metadata = DocumentMetadata(
            repo_name=repo_name,
            repo_url=repo_url,
            description=description,
            source_path=source_path or (str(path) if path else ""),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Collect mermaid diagrams
        from .models import MermaidBlock
        mermaid_diagrams = [
            b.code for b in all_blocks if isinstance(b, MermaidBlock)
        ]

        # Reconstruct raw markdown from markdown cells for fallback use
        raw_parts: list[str] = []
        for cell in cells:
            if cell.get("cell_type") == "markdown":
                raw_parts.append("".join(cell.get("source", [])))
            elif cell.get("cell_type") == "code":
                src = "".join(cell.get("source", []))
                if src.strip():
                    raw_parts.append(f"```{language}\n{src}\n```")
        raw_markdown = "\n\n".join(raw_parts)

        return DocumentModel(
            metadata=metadata,
            sections=sections,
            all_blocks=all_blocks,
            mermaid_diagrams=mermaid_diagrams,
            raw_markdown=raw_markdown,
        )

    def _parse_markdown_cell(self, source: str) -> list[ContentBlock]:
        """Parse a single markdown cell into ContentBlocks via ReadmeParser."""
        if not source.strip():
            return []

        # Use the existing Markdown parser to get blocks
        doc = self.md_parser.parse(source, repo_name="", repo_url="")
        return list(doc.all_blocks)

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
                else:
                    # Content before any heading → wrap in a virtual section
                    if not root_sections or root_sections[-1].title:
                        root_sections.append(Section(
                            title="",
                            level=0,
                            blocks=[block],
                        ))
                    else:
                        root_sections[-1].blocks.append(block)

        return root_sections


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def is_notebook(path: str | Path) -> bool:
    """Return True if the given path points to a Jupyter Notebook."""
    return str(path).lower().endswith(".ipynb")
