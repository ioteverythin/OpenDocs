"""Publish generated Markdown documentation to a Notion page.

Requirements
------------
Install the optional ``publish`` extra::

    pip install opendocs[publish]

which pulls in ``notion-client``.

Usage
-----
::

    from opendocs.publishers import NotionPublisher

    publisher = NotionPublisher(token="secret_...", page_id="<page-id-or-url>")
    url = publisher.publish("output/blog_post.md", title="MyProject Docs")
    print("Published →", url)

Or via the CLI::

    opendocs generate ./docs --publish-notion <page-id> --notion-token secret_...
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Markdown → Notion blocks conversion
# ---------------------------------------------------------------------------


def _rich_text(text: str) -> list[dict[str, Any]]:
    """Build a Notion ``rich_text`` array for plain text (≤ 2 000 chars)."""
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _heading_block(text: str, level: int) -> dict[str, Any]:
    kind = {1: "heading_1", 2: "heading_2"}.get(level, "heading_3")
    return {"object": "block", "type": kind, kind: {"rich_text": _rich_text(text)}}


def _paragraph_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(text)},
    }


def _divider_block() -> dict[str, Any]:
    return {"object": "block", "type": "divider", "divider": {}}


def _code_block(code: str, language: str = "plain text") -> dict[str, Any]:
    _SUPPORTED_LANGS = {
        "abap",
        "arduino",
        "bash",
        "basic",
        "c",
        "clojure",
        "coffeescript",
        "c++",
        "c#",
        "css",
        "dart",
        "diff",
        "docker",
        "elixir",
        "elm",
        "erlang",
        "flow",
        "fortran",
        "f#",
        "gherkin",
        "glsl",
        "go",
        "graphql",
        "groovy",
        "haskell",
        "html",
        "java",
        "javascript",
        "json",
        "julia",
        "kotlin",
        "latex",
        "less",
        "lisp",
        "livescript",
        "lua",
        "makefile",
        "markdown",
        "markup",
        "matlab",
        "mermaid",
        "nix",
        "objective-c",
        "ocaml",
        "pascal",
        "perl",
        "php",
        "plain text",
        "powershell",
        "prolog",
        "protobuf",
        "python",
        "r",
        "reason",
        "ruby",
        "rust",
        "sass",
        "scala",
        "scheme",
        "scss",
        "shell",
        "sql",
        "swift",
        "typescript",
        "vb.net",
        "verilog",
        "vhdl",
        "visual basic",
        "webassembly",
        "xml",
        "yaml",
    }
    lang = language.lower()
    if lang not in _SUPPORTED_LANGS:
        lang = "plain text"
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [{"type": "text", "text": {"content": code[:2000]}}],
            "language": lang,
        },
    }


def _bulleted_item(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(text)},
    }


def _numbered_item(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": _rich_text(text)},
    }


def markdown_to_notion_blocks(markdown: str) -> list[dict[str, Any]]:
    """Convert a Markdown string into a flat list of Notion API block objects.

    Handles headings (h1–h6), paragraphs, fenced code blocks, bullet lists,
    numbered lists, and horizontal rules.  Inline formatting (bold, italic,
    links) is preserved as plain text — Notion rich_text annotations are
    applied for ``**bold**`` and ``*italic*`` spans.
    """
    blocks: list[dict[str, Any]] = []
    lines = markdown.splitlines()

    in_code = False
    code_lines: list[str] = []
    code_lang = "plain text"

    i = 0
    while i < len(lines):
        line = lines[i]

        # ---- Fenced code block -----------------------------------------
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip() or "plain text"
                code_lines = []
            else:
                in_code = False
                blocks.append(_code_block("\n".join(code_lines), code_lang))
                code_lines = []
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # ---- Headings --------------------------------------------------
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = min(len(m.group(1)), 3)  # Notion only has h1–h3
            blocks.append(_heading_block(m.group(2).strip(), level))
            i += 1
            continue

        # ---- Horizontal rule -------------------------------------------
        if re.match(r"^[-*_]{3,}\s*$", line.strip()):
            blocks.append(_divider_block())
            i += 1
            continue

        # ---- Bullet list -----------------------------------------------
        m = re.match(r"^[\*\-\+]\s+(.*)", line)
        if m:
            while i < len(lines):
                bm = re.match(r"^[\*\-\+]\s+(.*)", lines[i])
                if bm:
                    blocks.append(_bulleted_item(bm.group(1)))
                    i += 1
                else:
                    break
            continue

        # ---- Numbered list ---------------------------------------------
        m = re.match(r"^\d+\.\s+(.*)", line)
        if m:
            while i < len(lines):
                nm = re.match(r"^\d+\.\s+(.*)", lines[i])
                if nm:
                    blocks.append(_numbered_item(nm.group(1)))
                    i += 1
                else:
                    break
            continue

        # ---- Blank line ------------------------------------------------
        if not line.strip():
            i += 1
            continue

        # ---- Paragraph -------------------------------------------------
        # Collect consecutive non-blank, non-special lines as one paragraph
        para_lines: list[str] = []
        while i < len(lines):
            line = lines[i]
            if (
                not line.strip()
                or line.startswith("#")
                or line.startswith("```")
                or re.match(r"^[-*_]{3,}\s*$", line.strip())
                or re.match(r"^[\*\-\+]\s+", line)
                or re.match(r"^\d+\.\s+", line)
            ):
                break
            # Strip inline markdown (bold / italic) for plain text
            clean = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", line)
            clean = re.sub(r"`([^`]+)`", r"\1", clean)
            para_lines.append(clean.strip())
            i += 1
        if para_lines:
            blocks.append(_paragraph_block(" ".join(para_lines)))

    return blocks


# ---------------------------------------------------------------------------
# NotionPublisher
# ---------------------------------------------------------------------------


class NotionPublisher:
    """Publish a Markdown file as a new child page in Notion.

    Parameters
    ----------
    token
        Notion integration token (starts with ``secret_...``).
        Can also be set via the ``NOTION_TOKEN`` environment variable.
    page_id
        The parent Notion page ID or full page URL.  New content is
        created as a child of this page.
    """

    def __init__(self, token: str, page_id: str) -> None:
        try:
            from notion_client import Client  # type: ignore[import]
        except ImportError:
            raise ImportError(
                "notion-client is required for Notion publishing.\nInstall it with:  pip install opendocs[publish]"
            ) from None

        self._client = Client(auth=token)
        self._page_id = self._normalise_page_id(page_id)

    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_page_id(raw: str) -> str:
        """Extract a clean UUID from a Notion URL or a bare 32-char hex ID."""
        # Strip query string / fragment, then look for 32 hex chars
        stripped = re.sub(r"[?#].*$", "", raw).replace("-", "")
        m = re.search(r"[0-9a-f]{32}", stripped, re.IGNORECASE)
        if m:
            h = m.group(0).lower()
            return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
        return raw  # pass through if it already looks like a UUID

    # ------------------------------------------------------------------
    def publish(
        self,
        markdown_path: str | Path,
        title: str | None = None,
    ) -> str:
        """Create a Notion page with the content of *markdown_path*.

        Parameters
        ----------
        markdown_path
            Path to a Markdown (.md) file — typically the ``blog_post.md``
            generated by the OpenDocs pipeline.
        title
            Page title shown in Notion.  Defaults to the file stem.

        Returns
        -------
        str
            Public URL of the newly created Notion page.
        """
        path = Path(markdown_path)
        page_title = title or path.stem.replace("-", " ").replace("_", " ").title()
        markdown = path.read_text(encoding="utf-8")
        blocks = markdown_to_notion_blocks(markdown)

        # Create the page (initially empty)
        response = self._client.pages.create(
            parent={"type": "page_id", "page_id": self._page_id},
            properties={"title": [{"type": "text", "text": {"content": page_title}}]},
        )
        new_page_id: str = response["id"]

        # Append blocks in batches of 100 (Notion API limit)
        for start in range(0, len(blocks), 100):
            batch = blocks[start : start + 100]
            self._client.blocks.children.append(block_id=new_page_id, children=batch)

        url: str = response.get(
            "url",
            f"https://notion.so/{new_page_id.replace('-', '')}",
        )
        return url
