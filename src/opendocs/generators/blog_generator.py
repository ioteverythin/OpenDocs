"""Generate an SEO-friendly blog post from a DocumentModel.

Produces a Markdown file that reads like a polished technical blog post
with an engaging intro, feature highlights, code examples, and a CTA.
Optionally leverages LLM summaries when available in the KnowledgeGraph.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.knowledge_graph import EntityType, KnowledgeGraph
from ..core.models import (
    BlockType,
    CodeBlock,
    ContentBlock,
    DocumentModel,
    GenerationResult,
    ImageBlock,
    ListBlock,
    OutputFormat,
    ParagraphBlock,
    Section,
    TableBlock,
)
from .base import BaseGenerator

if TYPE_CHECKING:
    from .diagram_extractor import ImageCache


class BlogGenerator(BaseGenerator):
    """DocumentModel → Markdown blog post."""

    format = OutputFormat.BLOG

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        filename = self._safe_filename(doc.metadata.repo_name or "project", "md")
        # Prefix with "blog_" to distinguish from the analysis report
        filename = f"blog_{filename}"
        output_path = self._ensure_dir(output_dir) / filename

        try:
            content = self._build_blog(doc)
            output_path.write_text(content, encoding="utf-8")
            return GenerationResult(
                format=OutputFormat.BLOG,
                output_path=output_path,
            )
        except Exception as exc:
            return GenerationResult(
                format=OutputFormat.BLOG,
                output_path=output_path,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal – build the blog
    # ------------------------------------------------------------------

    def _build_blog(self, doc: DocumentModel) -> str:
        lines: list[str] = []
        name = doc.metadata.repo_name or "This Project"
        now = datetime.now().strftime("%B %d, %Y")
        url = doc.metadata.repo_url or ""

        # -- Front-matter / meta -----------------------------------------
        lines.append("---")
        lines.append(f"title: \"{name}: A Deep Dive\"")
        lines.append(f"date: {now}")
        lines.append(f"author: opendocs")
        lines.append(f"description: \"{self._build_meta_description(doc)}\"")
        if url:
            lines.append(f"canonical_url: {url}")
        lines.append(f"tags: [{self._build_tags(doc)}]")
        lines.append("---")
        lines.append("")

        # -- Hero title ---------------------------------------------------
        lines.append(f"# {name}: Everything You Need to Know")
        lines.append("")

        # -- Engaging intro paragraph ------------------------------------
        intro = self._build_intro(doc, name, url)
        lines.append(intro)
        lines.append("")

        # -- Table of Contents -------------------------------------------
        toc_entries = self._collect_toc(doc)
        if toc_entries:
            lines.append("## 📑 Table of Contents")
            lines.append("")
            for anchor, title in toc_entries:
                lines.append(f"- [{title}](#{anchor})")
            lines.append("")

        # -- Key Features / Highlights -----------------------------------
        features = self._extract_features(doc)
        if features:
            lines.append("## ✨ Key Features")
            lines.append("")
            for feat in features:
                lines.append(f"- **{feat}**")
            lines.append("")

        # -- Tech Stack --------------------------------------------------
        techs = self._extract_tech_stack()
        if techs:
            lines.append("## 🛠️ Tech Stack")
            lines.append("")
            lines.append("| Technology | Category |")
            lines.append("|-----------|----------|")
            for tech_name, category in techs:
                lines.append(f"| {tech_name} | {category} |")
            lines.append("")

        # -- Main content sections (rewrite from README) -----------------
        for section in doc.sections:
            self._render_section(lines, section, depth=2)

        # -- Code Examples (pull most interesting code blocks) -----------
        code_blocks = [
            b for b in doc.all_blocks
            if isinstance(b, CodeBlock) and len(b.code.strip()) > 20
        ]
        if code_blocks:
            lines.append("## 💻 Code Examples")
            lines.append("")
            for cb in code_blocks[:5]:  # cap at 5
                lang = cb.language or ""
                if lang:
                    lines.append(f"**{lang.title()} example:**")
                lines.append("")
                lines.append(f"```{lang}")
                lines.append(cb.code.rstrip())
                lines.append("```")
                lines.append("")

        # -- Getting Started quick section --------------------------------
        install_block = self._find_install_block(doc)
        if install_block:
            lines.append("## 🚀 Getting Started")
            lines.append("")
            lines.append(f"```{install_block.language}")
            lines.append(install_block.code.rstrip())
            lines.append("```")
            lines.append("")

        # -- Conclusion / CTA --------------------------------------------
        lines.append("## 🏁 Conclusion")
        lines.append("")
        lines.append(
            f"{name} is a powerful tool worth exploring. "
            "Whether you're building something new or extending an existing system, "
            "it has the features and flexibility to get the job done."
        )
        lines.append("")
        if url:
            lines.append(f"👉 **[Check out {name} on GitHub]({url})**")
            lines.append("")
            lines.append(f"⭐ If you find it useful, give it a star on [GitHub]({url})!")
        lines.append("")

        # -- Footer -------------------------------------------------------
        lines.append("---")
        lines.append(f"*This post was auto-generated by [opendocs](https://pypi.org/project/opendocs/) on {now}.*")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_meta_description(self, doc: DocumentModel) -> str:
        """Build a concise SEO meta description."""
        if self.kg and self.kg.executive_summary:
            # First sentence of executive summary
            first = self.kg.executive_summary.split(". ")[0]
            return first[:160]
        if doc.metadata.description:
            return doc.metadata.description[:160]
        # Fallback: first paragraph
        for b in doc.all_blocks:
            if isinstance(b, ParagraphBlock) and len(b.text) > 30:
                return b.text[:160]
        return f"A deep dive into {doc.metadata.repo_name or 'this project'}"

    def _build_tags(self, doc: DocumentModel) -> str:
        """Generate comma-separated tags."""
        tags: list[str] = []
        if self.kg:
            for e in self.kg.entities:
                if e.entity_type in (
                    EntityType.TECHNOLOGY, EntityType.FRAMEWORK,
                    EntityType.LANGUAGE, EntityType.PLATFORM,
                ):
                    tags.append(e.name.lower())
        if doc.metadata.repo_name:
            tags.insert(0, doc.metadata.repo_name.lower())
        tags = list(dict.fromkeys(tags))[:10]  # dedupe, cap at 10
        return ", ".join(f'"{t}"' for t in tags)

    def _build_intro(self, doc: DocumentModel, name: str, url: str) -> str:
        """Build an engaging intro paragraph."""
        if self.kg and self.kg.executive_summary:
            return self.kg.executive_summary

        # Fallback: synthesize from first paragraphs
        paras = [
            b.text for b in doc.all_blocks
            if isinstance(b, ParagraphBlock) and len(b.text) > 40
        ]
        if paras:
            intro = paras[0]
            if len(paras) > 1:
                intro += "\n\n" + paras[1]
            return intro

        return (
            f"**{name}** is an exciting project that solves real problems. "
            f"In this post, we'll explore what it does, how it works, and "
            f"how you can get started."
        )

    def _collect_toc(self, doc: DocumentModel) -> list[tuple[str, str]]:
        """Collect top-level sections as TOC entries."""
        entries: list[tuple[str, str]] = []
        for sec in doc.sections:
            if sec.title:
                anchor = sec.title.lower().replace(" ", "-")
                anchor = "".join(c for c in anchor if c.isalnum() or c == "-")
                entries.append((anchor, sec.title))
        return entries

    def _extract_features(self, doc: DocumentModel) -> list[str]:
        """Extract feature names from KG or list blocks."""
        features: list[str] = []
        if self.kg:
            for e in self.kg.entities_of_type(EntityType.FEATURE):
                features.append(e.name)
        if not features:
            # Fallback: look for a "features" section
            for sec in doc.sections:
                if "feature" in sec.title.lower():
                    for b in sec.blocks:
                        if isinstance(b, ListBlock):
                            features.extend(b.items[:10])
                    break
        return features[:15]

    def _extract_tech_stack(self) -> list[tuple[str, str]]:
        """Extract technologies from KG."""
        if not self.kg:
            return []
        techs: list[tuple[str, str]] = []
        for e in self.kg.entities:
            if e.entity_type in (
                EntityType.TECHNOLOGY, EntityType.FRAMEWORK,
                EntityType.LANGUAGE, EntityType.DATABASE,
                EntityType.CLOUD_SERVICE, EntityType.PLATFORM,
            ):
                category = e.entity_type.value.replace("_", " ").title()
                techs.append((e.name, category))
        return techs[:15]

    def _render_section(
        self, lines: list[str], section: Section, depth: int,
    ) -> None:
        """Recursively render a section as blog-style Markdown."""
        if section.title:
            prefix = "#" * min(depth, 4)
            lines.append(f"{prefix} {section.title}")
            lines.append("")

        for block in section.blocks:
            self._render_block(lines, block)

        for sub in section.subsections:
            self._render_section(lines, sub, depth + 1)

    def _render_block(self, lines: list[str], block: ContentBlock) -> None:
        """Render a single content block as Markdown."""
        if isinstance(block, ParagraphBlock):
            if block.spans:
                parts = []
                for s in block.spans:
                    txt = s.text
                    if s.code:
                        txt = f"`{txt}`"
                    if s.bold:
                        txt = f"**{txt}**"
                    if s.italic:
                        txt = f"*{txt}*"
                    if s.url:
                        txt = f"[{txt}]({s.url})"
                    parts.append(txt)
                lines.append("".join(parts))
            else:
                lines.append(block.text)
            lines.append("")

        elif isinstance(block, CodeBlock):
            lines.append(f"```{block.language}")
            lines.append(block.code.rstrip())
            lines.append("```")
            lines.append("")

        elif isinstance(block, ListBlock):
            for i, item in enumerate(block.items):
                prefix = f"{i + 1}." if block.ordered else "-"
                lines.append(f"{prefix} {item}")
            lines.append("")

        elif isinstance(block, TableBlock):
            if block.headers:
                lines.append("| " + " | ".join(block.headers) + " |")
                lines.append("| " + " | ".join("---" for _ in block.headers) + " |")
                for row in block.rows:
                    lines.append("| " + " | ".join(row) + " |")
                lines.append("")

        elif isinstance(block, ImageBlock):
            lines.append(f"![{block.alt}]({block.src})")
            lines.append("")

    def _find_install_block(self, doc: DocumentModel) -> CodeBlock | None:
        """Find the first code block that looks like an install command."""
        install_keywords = ("pip install", "npm install", "cargo install",
                            "brew install", "apt install", "go install",
                            "git clone", "docker pull")
        for b in doc.all_blocks:
            if isinstance(b, CodeBlock):
                lower = b.code.lower()
                if any(kw in lower for kw in install_keywords):
                    return b
        return None
