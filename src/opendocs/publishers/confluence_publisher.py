"""Publish generated Markdown documentation to a Confluence page.

Requirements
------------
Install the optional ``publish`` extra::

    pip install opendocs[publish]

which pulls in ``requests``.

Usage
-----
::

    from opendocs.publishers import ConfluencePublisher

    pub = ConfluencePublisher(
        url="https://yourorg.atlassian.net/wiki",
        username="you@example.com",
        token="<atlassian-api-token>",
        space_key="PROJ",
        parent_page_title="Documentation",   # optional
    )
    url = pub.publish("output/blog_post.md", title="MyProject Docs")
    print("Published →", url)

Or via the CLI::

    opendocs generate ./docs \\
        --publish-confluence PROJ \\
        --confluence-url https://yourorg.atlassian.net/wiki \\
        --confluence-user you@example.com \\
        --confluence-token <token>
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Markdown → Confluence storage format (XHTML-based) conversion
# ---------------------------------------------------------------------------


def _escape(text: str) -> str:
    """Escape HTML-special characters for Confluence storage format."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    """Convert inline Markdown (bold, italic, code, links) to Confluence XHTML."""
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Links: [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    return text


def markdown_to_confluence(markdown: str) -> str:
    """Convert a Markdown string to Confluence storage format (XHTML).

    Handles headings, paragraphs, fenced code blocks, bullet/numbered
    lists, blockquotes, horizontal rules, and inline formatting.
    """
    output: list[str] = []
    lines = markdown.splitlines()

    in_code = False
    code_lines: list[str] = []
    code_lang = ""

    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            output.append("</ul>")
            in_ul = False
        if in_ol:
            output.append("</ol>")
            in_ol = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # ---- Fenced code block -----------------------------------------
        if line.startswith("```"):
            if not in_code:
                close_lists()
                in_code = True
                code_lang = line[3:].strip()
                code_lines = []
            else:
                in_code = False
                code_str = _escape("\n".join(code_lines))
                lang_param = f'<ac:parameter ac:name="language">{code_lang}</ac:parameter>' if code_lang else ""
                output.append(
                    f'<ac:structured-macro ac:name="code">'
                    f"{lang_param}"
                    f"<ac:plain-text-body><![CDATA[{code_str}]]></ac:plain-text-body>"
                    f"</ac:structured-macro>"
                )
                code_lines = []
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # ---- Horizontal rule -------------------------------------------
        if re.match(r"^[-*_]{3,}\s*$", line.strip()):
            close_lists()
            output.append("<hr/>")
            i += 1
            continue

        # ---- Heading ---------------------------------------------------
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            close_lists()
            level = len(m.group(1))
            text = _inline(m.group(2).strip())
            output.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # ---- Bullet list item ------------------------------------------
        m = re.match(r"^[\*\-\+]\s+(.*)", line)
        if m:
            if in_ol:
                output.append("</ol>")
                in_ol = False
            if not in_ul:
                output.append("<ul>")
                in_ul = True
            output.append(f"<li>{_inline(m.group(1))}</li>")
            i += 1
            continue

        # ---- Numbered list item ----------------------------------------
        m = re.match(r"^\d+\.\s+(.*)", line)
        if m:
            if in_ul:
                output.append("</ul>")
                in_ul = False
            if not in_ol:
                output.append("<ol>")
                in_ol = True
            output.append(f"<li>{_inline(m.group(1))}</li>")
            i += 1
            continue

        # ---- Blockquote ------------------------------------------------
        m = re.match(r"^>\s+(.*)", line)
        if m:
            close_lists()
            output.append(
                f'<ac:structured-macro ac:name="info">'
                f"<ac:rich-text-body><p>{_inline(m.group(1))}</p></ac:rich-text-body>"
                f"</ac:structured-macro>"
            )
            i += 1
            continue

        # ---- Blank line ------------------------------------------------
        if not line.strip():
            close_lists()
            i += 1
            continue

        # ---- Paragraph -------------------------------------------------
        close_lists()
        para_parts: list[str] = []
        while i < len(lines):
            line = lines[i]
            if (
                not line.strip()
                or line.startswith("#")
                or line.startswith("```")
                or re.match(r"^[-*_]{3,}\s*$", line.strip())
                or re.match(r"^[\*\-\+]\s+", line)
                or re.match(r"^\d+\.\s+", line)
                or re.match(r"^>\s+", line)
            ):
                break
            para_parts.append(_inline(line.strip()))
            i += 1
        if para_parts:
            output.append(f"<p>{' '.join(para_parts)}</p>")

    # Close any open lists
    if in_ul:
        output.append("</ul>")
    if in_ol:
        output.append("</ol>")

    return "\n".join(output)


# ---------------------------------------------------------------------------
# ConfluencePublisher
# ---------------------------------------------------------------------------


class ConfluencePublisher:
    """Create or update a Confluence page with generated Markdown content.

    Parameters
    ----------
    url
        Confluence base URL, e.g. ``https://yourorg.atlassian.net/wiki``.
    username
        Atlassian account email address.
    token
        Atlassian API token (generate at https://id.atlassian.com/manage/api-tokens).
    space_key
        The Confluence space key, e.g. ``PROJ`` or ``~personalspace``.
    parent_page_title
        Optional title of an existing page to nest the new page under.
    """

    def __init__(
        self,
        url: str,
        username: str,
        token: str,
        space_key: str,
        parent_page_title: str | None = None,
    ) -> None:
        try:
            import requests  # noqa: F401 (just verify it's available)
        except ImportError:
            raise ImportError(
                "requests is required for Confluence publishing.\nInstall it with:  pip install opendocs[publish]"
            ) from None

        import requests as _requests

        self._base = url.rstrip("/")
        self._space_key = space_key
        self._parent_title = parent_page_title

        self._session = _requests.Session()
        self._session.auth = (username, token)
        self._session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

    # ------------------------------------------------------------------
    def _api(self, path: str) -> str:
        return f"{self._base}/rest/api/content{path}"

    def _get_page_id(self, title: str) -> str | None:
        """Return the page ID for *title* in the configured space, or ``None``."""
        r = self._session.get(
            self._api(""),
            params={"title": title, "spaceKey": self._space_key, "expand": "version"},
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0]["id"] if results else None

    # ------------------------------------------------------------------
    def publish(
        self,
        markdown_path: str | Path,
        title: str | None = None,
    ) -> str:
        """Create or update a Confluence page with the content of *markdown_path*.

        If a page with the same title already exists in the space it will
        be updated (version incremented); otherwise a new page is created.

        Parameters
        ----------
        markdown_path
            Path to a Markdown file — typically ``blog_post.md`` generated
            by the OpenDocs pipeline.
        title
            Page title.  Defaults to the file stem.

        Returns
        -------
        str
            URL of the created / updated Confluence page.
        """
        path = Path(markdown_path)
        page_title = title or path.stem.replace("-", " ").replace("_", " ").title()
        markdown = path.read_text(encoding="utf-8")
        storage_body = markdown_to_confluence(markdown)

        # Build ancestors list (parent page)
        ancestors: list[dict] = []
        if self._parent_title:
            parent_id = self._get_page_id(self._parent_title)
            if parent_id:
                ancestors = [{"id": parent_id}]

        existing_id = self._get_page_id(page_title)

        if existing_id:
            # Fetch current version number, then update
            r = self._session.get(self._api(f"/{existing_id}?expand=version"))
            r.raise_for_status()
            current_version: int = r.json()["version"]["number"]

            payload = {
                "version": {"number": current_version + 1},
                "title": page_title,
                "type": "page",
                "body": {
                    "storage": {
                        "value": storage_body,
                        "representation": "storage",
                    }
                },
            }
            r = self._session.put(
                self._api(f"/{existing_id}"),
                data=json.dumps(payload),
            )
            r.raise_for_status()
            return f"{self._base}/pages/viewpage.action?pageId={existing_id}"

        else:
            # Create a new page
            payload = {
                "type": "page",
                "title": page_title,
                "space": {"key": self._space_key},
                "ancestors": ancestors,
                "body": {
                    "storage": {
                        "value": storage_body,
                        "representation": "storage",
                    }
                },
            }
            r = self._session.post(self._api(""), data=json.dumps(payload))
            r.raise_for_status()
            page_id: str = r.json()["id"]
            return f"{self._base}/pages/viewpage.action?pageId={page_id}"
