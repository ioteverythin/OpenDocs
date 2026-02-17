"""Generate a PDF document from a DocumentModel using ReportLab."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Flowable,
    NextPageTemplate,
    Paragraph,
    PageTemplate,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Preformatted,
    PageBreak,
    HRFlowable,
    KeepTogether,
)
from reportlab.platypus.tableofcontents import TableOfContents

from ..core.models import (
    BlockquoteBlock,
    CodeBlock,
    ContentBlock,
    DocumentModel,
    GenerationResult,
    ImageBlock,
    ListBlock,
    MermaidBlock,
    OutputFormat,
    ParagraphBlock,
    Section,
    TableBlock,
    ThematicBreakBlock,
)
from .base import BaseGenerator
from .styles import Colors, Fonts


def _rgb(t: tuple) -> colors.Color:
    return colors.Color(t[0] / 255, t[1] / 255, t[2] / 255)


# ---------------------------------------------------------------------------
# Custom flowables for visual flair
# ---------------------------------------------------------------------------

class AccentBar(Flowable):
    """A thin colored bar used as a section accent / divider."""

    def __init__(self, width, height=3, color=Colors.ACCENT):
        super().__init__()
        self.width = width
        self.height = height
        self._color = color

    def draw(self):
        self.canv.setFillColor(_rgb(self._color))
        self.canv.roundRect(0, 0, self.width, self.height, radius=1.5, fill=1, stroke=0)

    def wrap(self, available_width, available_height):
        return self.width, self.height + 4


class ColoredBox(Flowable):
    """A colored background box behind text — used for code blocks."""

    def __init__(self, content: str, bg_color, text_color, font_name="Courier", font_size=8.5,
                 padding=10, label: str = ""):
        super().__init__()
        self._content = content
        self._bg = bg_color
        self._fg = text_color
        self._font = font_name
        self._font_size = font_size
        self._padding = padding
        self._label = label
        self._lines = content.split("\n")

    def _line_height(self):
        return self._font_size * 1.3

    def _label_height(self):
        return (self._font_size + 8) if self._label else 0

    def _natural_height(self):
        return (self._label_height()
                + len(self._lines) * self._line_height()
                + self._padding * 2)

    def wrap(self, available_width, available_height):
        return available_width, min(self._natural_height(), available_height)

    def split(self, available_width, available_height):
        """Allow ReportLab to split tall code blocks across pages."""
        natural = self._natural_height()
        if natural <= available_height:
            return [self]

        # How many lines fit on this page?
        lh = self._line_height()
        usable = available_height - self._label_height() - self._padding * 2
        if usable < lh * 2:
            # Not enough room for even 2 lines — push to next page
            return []

        n_fit = max(1, int(usable / lh))
        first_lines = self._lines[:n_fit]
        rest_lines = self._lines[n_fit:]

        part1 = ColoredBox(
            "\n".join(first_lines),
            bg_color=self._bg, text_color=self._fg,
            font_name=self._font, font_size=self._font_size,
            padding=self._padding, label=self._label,
        )
        part2 = ColoredBox(
            "\n".join(rest_lines),
            bg_color=self._bg, text_color=self._fg,
            font_name=self._font, font_size=self._font_size,
            padding=self._padding,
            label=f"{self._label} (cont.)" if self._label else "",
        )
        return [part1, part2]

    def draw(self):
        w, h = self.width, self.height
        p = self._padding
        lh = self._line_height()

        # Background
        self.canv.setFillColor(_rgb(self._bg))
        self.canv.roundRect(0, 0, w, h, radius=4, fill=1, stroke=0)

        # Label bar
        label_offset = 0
        if self._label:
            lab_h = self._label_height()
            self.canv.setFillColor(_rgb(Colors.PRIMARY_DARK))
            self.canv.roundRect(0, h - lab_h, w, lab_h, radius=4, fill=1, stroke=0)
            self.canv.setFillColor(_rgb(Colors.WHITE))
            self.canv.setFont(self._font, self._font_size - 1)
            self.canv.drawString(p, h - lab_h + 4, self._label)
            label_offset = lab_h + 2

        # Code text
        self.canv.setFillColor(_rgb(self._fg))
        self.canv.setFont(self._font, self._font_size)
        y = h - p - self._font_size - label_offset
        for line in self._lines:
            if y < p:
                break
            self.canv.drawString(p, y, line)
            y -= lh


class StatCard(Flowable):
    """A stat card flowable for the metadata page."""

    def __init__(self, label: str, value: str, width=120, height=70):
        super().__init__()
        self.label = label
        self.value = value
        self._width = width
        self._height = height

    def wrap(self, available_width, available_height):
        return self._width, self._height

    def draw(self):
        w, h = self._width, self._height
        self.canv.setFillColor(_rgb(Colors.BG_LIGHT))
        self.canv.roundRect(0, 0, w, h, radius=6, fill=1, stroke=0)
        # Value
        self.canv.setFillColor(_rgb(Colors.PRIMARY_DARK))
        self.canv.setFont("Helvetica-Bold", 22)
        self.canv.drawCentredString(w / 2, h * 0.45, self.value)
        # Label
        self.canv.setFillColor(_rgb(Colors.MUTED))
        self.canv.setFont("Helvetica", 9)
        self.canv.drawCentredString(w / 2, h * 0.15, self.label)


# ---------------------------------------------------------------------------
# Page decorations (header / footer / page numbers)
# ---------------------------------------------------------------------------

def _draw_page_decorations(canvas, doc_template, repo_name: str):
    """Draw header bar, footer line, and page number on every page."""
    canvas.saveState()
    w, h = A4

    # Top accent bar
    canvas.setFillColor(_rgb(Colors.PRIMARY_DARK))
    canvas.rect(0, h - 18, w, 18, fill=1, stroke=0)
    canvas.setFillColor(_rgb(Colors.ACCENT))
    canvas.rect(0, h - 22, w, 4, fill=1, stroke=0)

    # Header text
    canvas.setFillColor(_rgb(Colors.WHITE))
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(inch, h - 14, repo_name)
    canvas.drawRightString(w - inch, h - 14, "IoTEverything")

    # Footer line
    canvas.setStrokeColor(_rgb(Colors.TABLE_BORDER))
    canvas.setLineWidth(0.5)
    canvas.line(inch, 40, w - inch, 40)

    # Page number
    canvas.setFillColor(_rgb(Colors.MUTED))
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(w / 2, 26, f"— {canvas.getPageNumber()} —")

    canvas.restoreState()


class PdfGenerator(BaseGenerator):
    """Generates a beautifully styled ``.pdf`` document."""

    format = OutputFormat.PDF

    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        output_dir = self._ensure_dir(output_dir)
        fname = self._safe_filename(doc.metadata.repo_name or "document", "pdf")
        output_path = output_dir / fname
        self._mermaid_index = 0

        try:
            self._build(doc, output_path)
            return GenerationResult(format=self.format, output_path=output_path)
        except Exception as exc:
            return GenerationResult(
                format=self.format, output_path=output_path, success=False, error=str(exc)
            )

    # ------------------------------------------------------------------
    # Builder
    # ------------------------------------------------------------------

    def _build(self, doc: DocumentModel, output_path: Path) -> None:
        repo_name = doc.metadata.repo_name or "Document"

        pdf = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=inch + 10,
            bottomMargin=0.8 * inch,
        )

        styles = self._create_styles()
        story: list = []

        # -- Title page --
        self._build_title_page(story, doc, styles)
        story.append(PageBreak())

        # -- Body --
        for section in doc.sections:
            self._render_section(story, section, styles)

        # -- Knowledge Graph page (if available) --
        if self.kg and self.kg.entities:
            story.append(PageBreak())
            self._build_knowledge_graph_page(story, styles)

        # -- Metadata page --
        story.append(PageBreak())
        self._build_metadata_page(story, doc, styles)

        # Build with page decorations
        pdf.build(
            story,
            onFirstPage=lambda c, d: None,  # plain first page
            onLaterPages=lambda c, d: _draw_page_decorations(c, d, repo_name),
        )

    # ------------------------------------------------------------------
    # Title page
    # ------------------------------------------------------------------

    def _build_title_page(self, story: list, doc: DocumentModel, styles: dict) -> None:
        story.append(Spacer(1, 1.5 * inch))

        # Top accent bar
        story.append(AccentBar(width=4.5 * inch, height=4, color=Colors.ACCENT))
        story.append(Spacer(1, 0.4 * inch))

        # Title
        story.append(Paragraph(
            doc.metadata.repo_name or "Technical Documentation",
            styles["DocTitle"],
        ))
        story.append(Spacer(1, 0.15 * inch))

        # Accent underline
        story.append(AccentBar(width=2 * inch, height=3, color=Colors.PRIMARY))
        story.append(Spacer(1, 0.3 * inch))

        # Description
        if doc.metadata.description:
            safe_desc = (
                doc.metadata.description[:350]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe_desc, styles["Subtitle"]))
        story.append(Spacer(1, 0.8 * inch))

        # Info table
        info_data = [
            ["Repository", doc.metadata.repo_name or "—"],
            ["Source", doc.metadata.repo_url or doc.metadata.source_path or "—"],
            ["Generated", doc.metadata.generated_at[:19] if doc.metadata.generated_at else "—"],
            ["Tool", "IoTEverything v0.1"],
        ]
        info_table = Table(info_data, colWidths=[1.5 * inch, 4 * inch])
        info_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), _rgb(Colors.HEADING)),
            ("TEXTCOLOR", (1, 0), (1, -1), _rgb(Colors.TEXT)),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, _rgb(Colors.TABLE_BORDER)),
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("RIGHTPADDING", (0, 0), (0, -1), 12),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.5 * inch))

        # Bottom accent
        story.append(AccentBar(width=4.5 * inch, height=4, color=Colors.ACCENT))

    # ------------------------------------------------------------------
    # Metadata page
    # ------------------------------------------------------------------

    def _build_metadata_page(self, story: list, doc: DocumentModel, styles: dict) -> None:
        story.append(Paragraph("📎  Document Metadata", styles["Heading1"]))
        story.append(AccentBar(width=2 * inch, height=3, color=Colors.ACCENT))
        story.append(Spacer(1, 0.3 * inch))

        meta = doc.metadata
        items = [
            ("Repository", meta.repo_name or "—"),
            ("URL", meta.repo_url or "—"),
            ("Source Path", meta.source_path or "—"),
            ("Generated At", meta.generated_at or "—"),
            ("Generator", "IoTEverything v0.1"),
            ("Sections", str(len(doc.sections))),
            ("Content Blocks", str(len(doc.all_blocks))),
            ("Mermaid Diagrams", str(len(doc.mermaid_diagrams))),
            ("Source Length", f"{len(doc.raw_markdown):,} characters"),
        ]

        t = Table(items, colWidths=[2 * inch, 4 * inch])
        style_cmds = [
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (0, -1), _rgb(Colors.HEADING)),
            ("TEXTCOLOR", (1, 0), (1, -1), _rgb(Colors.TEXT)),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("ALIGN", (0, 0), (0, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, _rgb(Colors.TABLE_BORDER)),
        ]
        # Alternating row backgrounds
        for i in range(len(items)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), _rgb(Colors.BG_LIGHT)))

        t.setStyle(TableStyle(style_cmds))
        story.append(t)

    # ------------------------------------------------------------------
    # Knowledge Graph page
    # ------------------------------------------------------------------

    def _build_knowledge_graph_page(self, story: list, styles: dict) -> None:
        """Render an overview page for the extracted Knowledge Graph."""
        from ..core.knowledge_graph import EntityType

        kg = self.kg
        if not kg:
            return

        story.append(Paragraph("🧠  Knowledge Graph", styles["Heading1"]))
        story.append(AccentBar(width=2 * inch, height=3, color=Colors.ACCENT))
        story.append(Spacer(1, 0.25 * inch))

        # Executive summary (LLM-generated)
        if kg.executive_summary:
            story.append(Paragraph("📋  Executive Summary", styles["Heading2"]))
            story.append(Spacer(1, 0.08 * inch))
            safe_summary = (
                kg.executive_summary
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe_summary, styles["Blockquote"]))
            story.append(Spacer(1, 0.2 * inch))

        # Stakeholder summaries (LLM-generated)
        persona_labels = {
            "cto": "🔧 CTO / Technical Lead",
            "investor": "💰 Investor / Business",
            "developer": "💻 Developer Onboarding",
        }
        if kg.stakeholder_summaries:
            story.append(Paragraph("👥  Stakeholder Views", styles["Heading2"]))
            story.append(Spacer(1, 0.08 * inch))

            for persona, content in kg.stakeholder_summaries.items():
                if not content or content.startswith("["):
                    continue
                label = persona_labels.get(persona, persona.title())
                story.append(Paragraph(label, styles["Heading3"]))
                for line in content.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    safe_line = (
                        line.lstrip("- •* ")
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    is_bullet = line.startswith(("- ", "• ", "* "))
                    prefix = (
                        f'<font color="#{Colors.ACCENT[0]:02X}{Colors.ACCENT[1]:02X}{Colors.ACCENT[2]:02X}">●  </font>'
                        if is_bullet else ""
                    )
                    story.append(Paragraph(f"{prefix}{safe_line}", styles["ListItem"]))
                story.append(Spacer(1, 0.1 * inch))

        # Stats summary
        stats = kg.extraction_stats or kg.compute_stats()
        stats_items = [
            ["Total Entities", str(stats.get("total_entities", 0))],
            ["Total Relations", str(stats.get("total_relations", 0))],
            ["Deterministic", str(stats.get("deterministic_entities", 0))],
            ["LLM-Extracted", str(stats.get("llm_entities", 0))],
        ]
        st = Table(stats_items, colWidths=[2 * inch, 1.5 * inch])
        st.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (0, -1), _rgb(Colors.HEADING)),
            ("TEXTCOLOR", (1, 0), (1, -1), _rgb(Colors.TEXT)),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, _rgb(Colors.TABLE_BORDER)),
            ("BACKGROUND", (0, 0), (-1, 0), _rgb(Colors.BG_LIGHT)),
            ("BACKGROUND", (0, 2), (-1, 2), _rgb(Colors.BG_LIGHT)),
        ]))
        story.append(st)
        story.append(Spacer(1, 0.3 * inch))

        # Entity listing by type
        story.append(Paragraph("Discovered Entities", styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))

        for et in EntityType:
            entities = kg.entities_of_type(et)
            if not entities:
                continue

            label = et.value.replace("_", " ").title()
            story.append(Paragraph(
                f'<font color="#{Colors.PRIMARY[0]:02X}{Colors.PRIMARY[1]:02X}{Colors.PRIMARY[2]:02X}">'
                f"▸ {label}</font>",
                styles["Normal"],
            ))

            for e in entities[:8]:
                conf = e.confidence
                if conf >= 0.8:
                    dot_color = Colors.SUCCESS
                elif conf >= 0.5:
                    dot_color = Colors.WARNING
                else:
                    dot_color = Colors.DANGER
                dot_hex = f"#{dot_color[0]:02X}{dot_color[1]:02X}{dot_color[2]:02X}"
                safe_name = e.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(
                    f'&nbsp;&nbsp;&nbsp;&nbsp;<font color="{dot_hex}">●</font> '
                    f"{safe_name} "
                    f'<font size="8" color="#{Colors.MUTED[0]:02X}{Colors.MUTED[1]:02X}{Colors.MUTED[2]:02X}">'
                    f"({conf:.0%})</font>",
                    styles["Normal"],
                ))

            if len(entities) > 8:
                story.append(Paragraph(
                    f'&nbsp;&nbsp;&nbsp;&nbsp;<font color="#{Colors.MUTED[0]:02X}{Colors.MUTED[1]:02X}{Colors.MUTED[2]:02X}">'
                    f"… and {len(entities) - 8} more</font>",
                    styles["Normal"],
                ))
            story.append(Spacer(1, 0.06 * inch))

        # Auto-generated architecture graph
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("📐  Auto-Generated Architecture Graph", styles["Heading2"]))
        story.append(Spacer(1, 0.08 * inch))

        kg_img = self.image_cache.kg_diagram if self.image_cache else None
        if kg_img and kg_img.exists():
            from reportlab.platypus import Image as RLImage

            img = RLImage(str(kg_img), width=5.8 * inch, height=3.8 * inch)
            img.hAlign = "CENTER"
            story.append(img)
        else:
            # Fallback: show mermaid code
            mermaid_code = kg.to_mermaid()
            story.append(ColoredBox(
                mermaid_code,
                bg_color=Colors.CODE_BG,
                text_color=Colors.CODE_TEXT,
                label="MERMAID",
            ))
        story.append(Spacer(1, 0.1 * inch))

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    @staticmethod
    def _create_styles() -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        custom: dict[str, ParagraphStyle] = {
            "Normal": ParagraphStyle(
                "CustomNormal",
                parent=base["Normal"],
                fontSize=10.5,
                leading=15,
                textColor=_rgb(Colors.TEXT),
                spaceAfter=4,
            ),
        }

        custom["DocTitle"] = ParagraphStyle(
            "DocTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=34,
            leading=40,
            textColor=_rgb(Colors.PRIMARY_DARK),
            alignment=TA_LEFT,
        )
        custom["Subtitle"] = ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=13,
            leading=18,
            textColor=_rgb(Colors.MUTED),
            alignment=TA_LEFT,
        )
        custom["Meta"] = ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontSize=9,
            textColor=_rgb(Colors.MUTED),
            alignment=TA_LEFT,
        )
        custom["Heading1"] = ParagraphStyle(
            "Heading1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=27,
            textColor=_rgb(Colors.PRIMARY_DARK),
            spaceBefore=20,
            spaceAfter=6,
        )
        custom["Heading2"] = ParagraphStyle(
            "Heading2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=_rgb(Colors.HEADING),
            spaceBefore=16,
            spaceAfter=5,
        )
        custom["Heading3"] = ParagraphStyle(
            "Heading3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=_rgb(Colors.SECONDARY),
            spaceBefore=12,
            spaceAfter=4,
        )
        custom["Code"] = ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=8.5,
            leading=11,
            backColor=_rgb(Colors.CODE_BG_LIGHT),
            leftIndent=12,
            rightIndent=12,
            spaceBefore=6,
            spaceAfter=6,
        )
        custom["Blockquote"] = ParagraphStyle(
            "Blockquote",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=10.5,
            leading=15,
            leftIndent=20,
            textColor=_rgb(Colors.SECONDARY),
            backColor=_rgb(Colors.BG_LIGHT),
            borderColor=_rgb(Colors.PRIMARY),
            borderWidth=2,
            borderPadding=8,
            spaceBefore=6,
            spaceAfter=6,
        )
        custom["ListItem"] = ParagraphStyle(
            "ListItem",
            parent=custom["Normal"],
            leftIndent=20,
            bulletIndent=10,
            spaceBefore=2,
            spaceAfter=2,
        )

        return custom

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    def _render_section(self, story: list, section: Section, styles: dict) -> None:
        heading_key = f"Heading{min(section.level, 3)}"
        style = styles.get(heading_key, styles["Heading1"])

        # Section heading + accent bar as a kept-together block
        heading_block = [
            Paragraph(section.title, style),
        ]
        if section.level <= 2:
            heading_block.append(
                AccentBar(
                    width=1.5 * inch if section.level == 1 else inch,
                    height=3,
                    color=Colors.ACCENT if section.level == 1 else Colors.PRIMARY_LIGHT,
                )
            )
        heading_block.append(Spacer(1, 0.08 * inch))
        story.append(KeepTogether(heading_block))

        for block in section.blocks:
            self._render_block(story, block, styles)

        for sub in section.subsections:
            self._render_section(story, sub, styles)

    def _render_block(self, story: list, block: ContentBlock, styles: dict) -> None:
        if isinstance(block, ParagraphBlock):
            safe = (
                block.text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe, styles["Normal"]))
            story.append(Spacer(1, 0.06 * inch))

        elif isinstance(block, CodeBlock):
            label = block.language.upper() if block.language else ""
            story.append(ColoredBox(
                block.code.rstrip("\n"),
                bg_color=Colors.CODE_BG,
                text_color=Colors.CODE_TEXT,
                label=label,
            ))
            story.append(Spacer(1, 0.1 * inch))

        elif isinstance(block, MermaidBlock):
            idx = self._mermaid_index
            self._mermaid_index += 1

            img_path = self.image_cache.get_mermaid(idx) if self.image_cache else None
            if img_path and img_path.exists():
                from reportlab.platypus import Image as RLImage

                story.append(Paragraph(
                    f'<font color="#{Colors.INFO[0]:02X}{Colors.INFO[1]:02X}{Colors.INFO[2]:02X}">'
                    f"📐 DIAGRAM</font>",
                    styles["Normal"],
                ))
                img = RLImage(str(img_path), width=5.5 * inch, height=3.5 * inch)
                img.hAlign = "CENTER"
                story.append(img)
            else:
                story.append(ColoredBox(
                    block.code.rstrip("\n"),
                    bg_color=Colors.CODE_BG,
                    text_color=Colors.CODE_TEXT,
                    label="📐 MERMAID DIAGRAM",
                ))
            story.append(Spacer(1, 0.1 * inch))

        elif isinstance(block, TableBlock):
            self._render_table(story, block, styles)

        elif isinstance(block, ListBlock):
            prefix_fn = (lambda i: f"{i + 1}. ") if block.ordered else (lambda _: "●  ")
            for i, item in enumerate(block.items):
                safe = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                bullet = f'<font color="#{Colors.PRIMARY[0]:02X}{Colors.PRIMARY[1]:02X}{Colors.PRIMARY[2]:02X}">{prefix_fn(i)}</font>'
                story.append(Paragraph(
                    f"{bullet}{safe}",
                    styles["ListItem"],
                ))
            story.append(Spacer(1, 0.06 * inch))

        elif isinstance(block, BlockquoteBlock):
            safe = (
                block.text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe, styles["Blockquote"]))
            story.append(Spacer(1, 0.06 * inch))

        elif isinstance(block, ImageBlock):
            img_path = self.image_cache.get_external(block.src) if self.image_cache else None
            if img_path and img_path.exists():
                from reportlab.platypus import Image as RLImage

                if block.alt:
                    story.append(Paragraph(
                        f'<font color="#{Colors.PRIMARY[0]:02X}{Colors.PRIMARY[1]:02X}{Colors.PRIMARY[2]:02X}">'
                        f'<i>🖼  {block.alt}</i></font>',
                        styles["Normal"],
                    ))
                img = RLImage(str(img_path), width=5.0 * inch, height=3.0 * inch)
                img.hAlign = "CENTER"
                story.append(img)
                story.append(Spacer(1, 0.06 * inch))
            else:
                story.append(Paragraph(
                    f'<font color="#{Colors.INFO[0]:02X}{Colors.INFO[1]:02X}{Colors.INFO[2]:02X}">'
                    f"🖼  {block.alt or block.src}</font>",
                    styles["Normal"],
                ))

        elif isinstance(block, ThematicBreakBlock):
            story.append(HRFlowable(
                width="80%", thickness=1, color=_rgb(Colors.TABLE_BORDER),
                spaceBefore=8, spaceAfter=8,
            ))

    @staticmethod
    def _render_table(story: list, block: TableBlock, styles: dict) -> None:
        data: list[list[str]] = []
        if block.headers:
            data.append(block.headers)
        data.extend(block.rows)
        if not data:
            return

        # Calculate column widths
        num_cols = len(data[0]) if data else 0
        available = 6.3 * inch  # ~A4 width minus margins
        col_w = available / max(num_cols, 1)
        col_widths = [col_w] * num_cols

        t = Table(data, colWidths=col_widths, repeatRows=1 if block.headers else 0)

        style_cmds = [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, _rgb(Colors.TABLE_BORDER)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        if block.headers:
            style_cmds.extend([
                ("BACKGROUND", (0, 0), (-1, 0), _rgb(Colors.TABLE_HEADER_BG)),
                ("TEXTCOLOR", (0, 0), (-1, 0), _rgb(Colors.WHITE)),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9.5),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ])
            # Alternating row colors (skip header)
            for i in range(1, len(data)):
                if i % 2 == 0:
                    style_cmds.append(
                        ("BACKGROUND", (0, i), (-1, i), _rgb(Colors.TABLE_ALT_ROW))
                    )
        else:
            for i in range(len(data)):
                if i % 2 == 0:
                    style_cmds.append(
                        ("BACKGROUND", (0, i), (-1, i), _rgb(Colors.TABLE_ALT_ROW))
                    )

        t.setStyle(TableStyle(style_cmds))
        story.append(t)
        story.append(Spacer(1, 0.15 * inch))
