"""Merge multiple Markdown / Jupyter Notebook files from a folder into a
single unified ``DocumentModel``.

This enables passing an entire ``docs/`` directory to the pipeline and
generating one combined document from all source files.

File ordering
-------------
By default files are sorted: root-level files first, then subdirectories,
alphabetically within each level.

You can override the order by placing a ``.opendocs-order`` file in the
folder root — one relative path per line::

    README.md
    docs/installation.md
    docs/usage.md
    # lines starting with # are comments
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from .models import (
    BlockType,
    ContentBlock,
    DocumentMetadata,
    DocumentModel,
    HeadingBlock,
    Section,
    ThematicBreakBlock,
)
from .notebook_parser import NotebookParser, is_notebook
from .parser import ReadmeParser

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "site-packages",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}

_DOC_EXTENSIONS = {".md", ".markdown", ".ipynb"}


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _iter_doc_files(folder: Path, recursive: bool = True) -> Iterator[Path]:
    """Yield .md/.ipynb files from *folder* in stable sorted order.

    Root-level files come first, then sub-directory files, alphabetically
    within each group.
    """
    pattern = "**/*" if recursive else "*"
    collected: list[Path] = []

    for ext in _DOC_EXTENSIONS:
        for f in folder.glob(f"{pattern}{ext}"):
            if f.is_file():
                # Skip any path whose parts contain an ignored directory name
                rel = f.relative_to(folder)
                if any(part in _IGNORE_DIRS for part in rel.parts):
                    continue
                collected.append(f)

    # Stable sort: depth first (shallowest = lowest index), then alpha
    collected.sort(key=lambda p: (len(p.relative_to(folder).parts), str(p)))

    # Deduplicate while preserving order
    seen: set[Path] = set()
    for f in collected:
        if f not in seen:
            seen.add(f)
            yield f


def _read_order_file(folder: Path) -> list[Path] | None:
    """Return an explicit file list from ``.opendocs-order`` if it exists."""
    order_file = folder / ".opendocs-order"
    if not order_file.exists():
        return None

    paths: list[Path] = []
    for raw_line in order_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        candidate = (folder / line).resolve()
        if candidate.exists() and candidate.suffix in _DOC_EXTENSIONS:
            paths.append(candidate)

    return paths if paths else None


# ---------------------------------------------------------------------------
# Title helpers
# ---------------------------------------------------------------------------


def _file_title(path: Path, folder: Path) -> str:
    """Turn a file path into a human-readable section title."""
    # Use the relative stem, convert separators to spaces, title-case it
    rel = path.relative_to(folder)
    stem = rel.with_suffix("").as_posix()  # e.g.  "docs/getting-started"
    stem = re.sub(r"[\-_/]", " ", stem)  # "docs getting started"
    # Drop leading digits that look like ordering prefixes (e.g. "01 intro")
    stem = re.sub(r"^\d+\s+", "", stem)
    return stem.strip().title()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def merge_folder(
    folder: str | Path,
    *,
    recursive: bool = True,
    title: str | None = None,
) -> DocumentModel:
    """Parse every .md/.ipynb file in *folder* and merge into one ``DocumentModel``.

    Parameters
    ----------
    folder
        Path to the directory containing source files.
    recursive
        When *True* (default) scan sub-directories as well.
    title
        Override the merged document's ``repo_name``.
        Defaults to the folder's own name.

    Returns
    -------
    DocumentModel
        A unified document where each source file becomes a top-level
        ``Section``.  A ``ThematicBreakBlock`` separates each file.

    Raises
    ------
    ValueError
        If *folder* is not a directory or contains no supported files.
    """
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")

    # Determine file list (explicit order file or auto-discovered)
    ordered = _read_order_file(folder)
    files: list[Path] = ordered if ordered else list(_iter_doc_files(folder, recursive=recursive))

    if not files:
        raise ValueError(f"No Markdown (.md) or Notebook (.ipynb) files found in {folder}")

    md_parser = ReadmeParser()
    nb_parser = NotebookParser()

    merged_sections: list[Section] = []
    merged_blocks: list[ContentBlock] = []
    merged_mermaid: list[str] = []
    raw_parts: list[str] = []

    repo_name = title or folder.name

    for i, path in enumerate(files):
        file_title = _file_title(path, folder)

        # Parse the file
        if is_notebook(str(path)):
            doc = nb_parser.parse(str(path), repo_name=path.stem)
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
            doc = md_parser.parse(content, repo_name=path.stem, repo_url="")

        # Build a synthetic heading block so generators produce a proper header
        heading = HeadingBlock(type=BlockType.HEADING, level=1, text=file_title)

        # Wrap into a Section
        section = Section(
            title=file_title,
            level=1,
            blocks=[heading, *doc.all_blocks],
            subsections=doc.sections,
        )
        merged_sections.append(section)

        # Flat block list — add a divider between files (not before the first)
        if i > 0:
            merged_blocks.append(ThematicBreakBlock(type=BlockType.THEMATIC_BREAK))
        merged_blocks.append(heading)
        merged_blocks.extend(doc.all_blocks)

        merged_mermaid.extend(doc.mermaid_diagrams)
        raw_parts.append(f"# {file_title}\n\n{doc.raw_markdown}")

    metadata = DocumentMetadata(
        repo_name=repo_name,
        repo_url="",
        description=(f"Unified documentation merged from {len(files)} source file(s) in {folder.name}/"),
        source_path=str(folder),
    )

    return DocumentModel(
        metadata=metadata,
        sections=merged_sections,
        all_blocks=merged_blocks,
        mermaid_diagrams=merged_mermaid,
        raw_markdown="\n\n---\n\n".join(raw_parts),
    )
