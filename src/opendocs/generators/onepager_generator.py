"""Generate a single-page executive PDF (One-Pager / Datasheet).

Produces a compact, visually structured one-page PDF with:
- Project name and description
- Key stats (entities, sections, code blocks)
- Architecture diagram (if available)
- Quick-start install command
- Feature highlights
- Technology stack
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..core.knowledge_graph import EntityType, KnowledgeGraph
from ..core.models import (
    CodeBlock,
    DocumentModel,
    GenerationResult,
    ListBlock,
    OutputFormat,
    ParagraphBlock,
)
from .base import BaseGenerator

if TYPE_CHECKING:
    from .diagram_extractor import ImageCache


class OnePagerGenerator(BaseGenerator):
    """DocumentModel → Executive one-page PDF."""

    format = OutputFormat.ONEPAGER

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        filename = self._safe_filename(doc.metadata.repo_name or "onepager", "pdf")
        filename = f"onepager_{filename}"
        output_path = self._ensure_dir(output_dir) / filename

        try:
            self._build_pdf(doc, output_path)
            return GenerationResult(
                format=OutputFormat.ONEPAGER,
                output_path=output_path,
            )
        except Exception as exc:
            return GenerationResult(
                format=OutputFormat.ONEPAGER,
                output_path=output_path,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # PDF construction
    # ------------------------------------------------------------------

    def _build_pdf(self, doc: DocumentModel, output_path: Path) -> None:
        """Build the one-pager PDF using ReportLab."""
        page_w, page_h = A4
        margin = 15 * mm

        pdf = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
        )

        styles = self._build_styles()
        story: list = []
        name = doc.metadata.repo_name or "Project"
        url = doc.metadata.repo_url or ""

        # -- Header / Title ----------------------------------------------
        story.append(Paragraph(name, styles["title"]))
        story.append(Spacer(1, 4 * mm))

        # Subtitle / tagline
        tagline = self._build_tagline(doc)
        story.append(Paragraph(tagline, styles["subtitle"]))
        story.append(Spacer(1, 3 * mm))

        # -- Divider -----------------------------------------------------
        primary = self._theme_primary()
        story.append(HRFlowable(
            width="100%", thickness=2, color=primary,
            spaceAfter=3 * mm, spaceBefore=1 * mm,
        ))

        # -- Key Stats Table ---------------------------------------------
        stats_data = self._build_stats_table(doc)
        if stats_data:
            t = Table(stats_data, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, 0), primary),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(t)
            story.append(Spacer(1, 4 * mm))

        # -- Executive Summary -------------------------------------------
        summary = self._build_summary(doc)
        if summary:
            story.append(Paragraph("Executive Summary", styles["section"]))
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(summary, styles["body"]))
            story.append(Spacer(1, 4 * mm))

        # -- Features (2-column) ----------------------------------------
        features = self._extract_features(doc)
        if features:
            story.append(Paragraph("Key Features", styles["section"]))
            story.append(Spacer(1, 2 * mm))
            for feat in features[:8]:
                story.append(Paragraph(f"• {feat}", styles["bullet"]))
            story.append(Spacer(1, 4 * mm))

        # -- Tech Stack --------------------------------------------------
        techs = self._extract_techs()
        if techs:
            story.append(Paragraph("Technology Stack", styles["section"]))
            story.append(Spacer(1, 2 * mm))
            tech_text = " · ".join(techs[:12])
            story.append(Paragraph(tech_text, styles["body"]))
            story.append(Spacer(1, 4 * mm))

        # -- Quick Start -------------------------------------------------
        install_cmd = self._find_install_command(doc)
        if install_cmd:
            story.append(Paragraph("Quick Start", styles["section"]))
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                f'<font face="Courier" size="8" color="#333333">{install_cmd}</font>',
                styles["body"],
            ))
            story.append(Spacer(1, 4 * mm))

        # -- Architecture Diagram (if cached) ----------------------------
        if self.image_cache and self.image_cache.kg_diagram:
            try:
                from reportlab.platypus import Image as RLImage

                img_path = self.image_cache.kg_diagram
                if img_path.exists():
                    story.append(Paragraph("Architecture", styles["section"]))
                    story.append(Spacer(1, 2 * mm))
                    img = RLImage(str(img_path), width=5 * inch, height=2.5 * inch)
                    img.hAlign = "CENTER"
                    story.append(img)
                    story.append(Spacer(1, 4 * mm))
            except Exception:
                pass

        # -- Footer -------------------------------------------------------
        story.append(HRFlowable(
            width="100%", thickness=1, color=colors.grey,
            spaceAfter=2 * mm, spaceBefore=2 * mm,
        ))
        now = datetime.now().strftime("%Y-%m-%d")
        footer_parts = [f"Generated by opendocs · {now}"]
        if url:
            footer_parts.append(f' · <link href="{url}">{url}</link>')
        story.append(Paragraph(
            " ".join(footer_parts),
            styles["footer"],
        ))

        pdf.build(story)

    # ------------------------------------------------------------------
    # Style definitions
    # ------------------------------------------------------------------

    def _build_styles(self) -> dict[str, ParagraphStyle]:
        """Build custom styles for the one-pager."""
        primary = self._theme_primary()

        return {
            "title": ParagraphStyle(
                "OP_Title",
                fontName="Helvetica-Bold",
                fontSize=22,
                leading=26,
                textColor=primary,
                alignment=TA_LEFT,
            ),
            "subtitle": ParagraphStyle(
                "OP_Subtitle",
                fontName="Helvetica",
                fontSize=11,
                leading=14,
                textColor=colors.Color(0.3, 0.3, 0.3),
                alignment=TA_LEFT,
            ),
            "section": ParagraphStyle(
                "OP_Section",
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=15,
                textColor=primary,
                spaceBefore=2 * mm,
            ),
            "body": ParagraphStyle(
                "OP_Body",
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                textColor=colors.Color(0.15, 0.15, 0.15),
            ),
            "bullet": ParagraphStyle(
                "OP_Bullet",
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                leftIndent=10,
                textColor=colors.Color(0.15, 0.15, 0.15),
            ),
            "footer": ParagraphStyle(
                "OP_Footer",
                fontName="Helvetica",
                fontSize=7,
                leading=9,
                textColor=colors.grey,
                alignment=TA_CENTER,
            ),
        }

    # ------------------------------------------------------------------
    # Content helpers
    # ------------------------------------------------------------------

    def _theme_primary(self) -> colors.Color:
        """Get primary color from theme."""
        r, g, b = self.theme.colors.primary
        return colors.Color(r / 255, g / 255, b / 255)

    def _build_tagline(self, doc: DocumentModel) -> str:
        """Build a one-line tagline."""
        if doc.metadata.description:
            return doc.metadata.description[:150]
        paras = [
            b.text for b in doc.all_blocks
            if isinstance(b, ParagraphBlock) and 20 < len(b.text) < 200
        ]
        if paras:
            return paras[0][:150]
        return "An open-source project"

    def _build_stats_table(self, doc: DocumentModel) -> list[list[str]]:
        """Build a stats summary row."""
        n_sections = str(len(doc.sections))
        n_blocks = str(len(doc.all_blocks))
        n_code = str(sum(1 for b in doc.all_blocks if isinstance(b, CodeBlock)))
        n_entities = str(len(self.kg.entities)) if self.kg else "—"
        n_relations = str(len(self.kg.relations)) if self.kg else "—"

        return [
            ["Sections", "Blocks", "Code Examples", "Entities", "Relations"],
            [n_sections, n_blocks, n_code, n_entities, n_relations],
        ]

    def _build_summary(self, doc: DocumentModel) -> str:
        """Build executive summary text."""
        if self.kg and self.kg.executive_summary:
            return self.kg.executive_summary[:400]
        paras = [
            b.text for b in doc.all_blocks
            if isinstance(b, ParagraphBlock) and len(b.text) > 40
        ]
        if paras:
            return paras[0][:400]
        return ""

    def _extract_features(self, doc: DocumentModel) -> list[str]:
        """Extract feature list."""
        features: list[str] = []
        if self.kg:
            for e in self.kg.entities_of_type(EntityType.FEATURE):
                features.append(e.name)
        if not features:
            for sec in doc.sections:
                if "feature" in sec.title.lower():
                    for b in sec.blocks:
                        if isinstance(b, ListBlock):
                            features.extend(b.items[:8])
                    break
        return features[:8]

    def _extract_techs(self) -> list[str]:
        """Extract technology names from KG."""
        if not self.kg:
            return []
        techs: list[str] = []
        for e in self.kg.entities:
            if e.entity_type in (
                EntityType.TECHNOLOGY, EntityType.FRAMEWORK,
                EntityType.LANGUAGE, EntityType.DATABASE,
                EntityType.CLOUD_SERVICE, EntityType.PLATFORM,
            ):
                techs.append(e.name)
        return list(dict.fromkeys(techs))[:12]

    def _find_install_command(self, doc: DocumentModel) -> str:
        """Find an install command from code blocks."""
        install_keywords = (
            "pip install", "npm install", "cargo install",
            "brew install", "apt install", "go install",
            "git clone", "docker pull",
        )
        for b in doc.all_blocks:
            if isinstance(b, CodeBlock):
                lower = b.code.lower()
                if any(kw in lower for kw in install_keywords):
                    # Return first line of install block
                    first_line = b.code.strip().split("\n")[0]
                    return first_line[:120]
        return ""
