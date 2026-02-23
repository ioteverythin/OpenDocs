"""Generate a PDF document from a DocumentModel.

Primary approach: build a Word doc via WordGenerator, then convert to PDF
with ``docx2pdf`` (requires Microsoft Word on Windows / LibreOffice on Linux).

Fallback: if ``docx2pdf`` is unavailable the generator uses ReportLab to
produce a standalone PDF directly.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..core.models import (
    DocumentModel,
    GenerationResult,
    OutputFormat,
)
from .base import BaseGenerator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature-detect docx2pdf at import time
# ---------------------------------------------------------------------------
try:
    from docx2pdf import convert as _docx2pdf_convert  # type: ignore[import-untyped]

    _HAS_DOCX2PDF = True
except ImportError:
    _HAS_DOCX2PDF = False


class PdfGenerator(BaseGenerator):
    """Generates a ``.pdf`` document.

    The preferred path creates an intermediate ``.docx`` using
    :class:`WordGenerator` and converts it with *docx2pdf*.  This ensures the
    PDF looks identical to the Word output the user already approved.

    When *docx2pdf* is not installed (or conversion fails), the generator
    falls back to a pure-ReportLab build so the pipeline never breaks.
    """

    format = OutputFormat.PDF

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        output_dir = self._ensure_dir(output_dir)
        fname = self._safe_filename(doc.metadata.repo_name or "document", "pdf")
        output_path = output_dir / fname

        # Try the Word -> PDF path first
        if _HAS_DOCX2PDF:
            result = self._generate_via_word(doc, output_dir, output_path)
            if result.success:
                return result
            log.warning(
                "docx2pdf conversion failed (%s) -- falling back to ReportLab",
                result.error,
            )

        # Fallback: pure ReportLab
        return self._generate_via_reportlab(doc, output_path)

    # ------------------------------------------------------------------
    # Path 1 -- Word -> PDF (preferred)
    # ------------------------------------------------------------------

    def _generate_via_word(
        self, doc: DocumentModel, output_dir: Path, output_path: Path
    ) -> GenerationResult:
        """Build a .docx with WordGenerator, convert to PDF, clean up."""
        from .word_generator import WordGenerator

        tmp_docx: Path | None = None
        try:
            # Create a temporary .docx in the same output directory
            word_gen = WordGenerator(
                theme=self.theme,
                image_cache=self.image_cache,
                knowledge_graph=self.kg,
            )
            tmp_docx = output_dir / f"_tmp_{output_path.stem}.docx"

            docx_obj = word_gen._build(doc)
            docx_obj.save(str(tmp_docx))

            # Convert .docx -> .pdf
            _docx2pdf_convert(str(tmp_docx), str(output_path))

            # Clean up temporary .docx
            try:
                tmp_docx.unlink()
            except OSError:
                pass

            if output_path.exists():
                return GenerationResult(format=self.format, output_path=output_path)
            else:
                return GenerationResult(
                    format=self.format,
                    output_path=output_path,
                    success=False,
                    error="docx2pdf produced no output file",
                )
        except Exception as exc:
            # Clean up temp file on failure
            try:
                if tmp_docx and tmp_docx.exists():
                    tmp_docx.unlink()
            except OSError:
                pass
            return GenerationResult(
                format=self.format,
                output_path=output_path,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Path 2 -- Pure ReportLab fallback
    # ------------------------------------------------------------------

    def _generate_via_reportlab(
        self, doc: DocumentModel, output_path: Path
    ) -> GenerationResult:
        """Build a PDF directly with ReportLab (fallback)."""
        try:
            self._mermaid_index = 0
            self._build_reportlab(doc, output_path)
            return GenerationResult(format=self.format, output_path=output_path)
        except Exception as exc:
            return GenerationResult(
                format=self.format,
                output_path=output_path,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # ReportLab builder (kept for environments without MS Word)
    # ------------------------------------------------------------------

    def _build_reportlab(self, doc: DocumentModel, output_path: Path) -> None:  # noqa: C901
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            Flowable,
            HRFlowable,
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        from ..core.models import (
            BlockquoteBlock,
            CodeBlock,
            ContentBlock,
            ImageBlock,
            InlineSpan,
            ListBlock,
            MermaidBlock,
            ParagraphBlock,
            Section,
            TableBlock,
            ThematicBreakBlock,
        )
        from .styles import Colors, Fonts

        # -- helpers ----------------------------------------------------------
        def _rgb(t: tuple) -> colors.Color:
            return colors.Color(t[0] / 255, t[1] / 255, t[2] / 255)

        def _spans_to_html(spans: list[InlineSpan]) -> str:
            parts: list[str] = []
            for span in spans:
                text = (
                    span.text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                if span.is_link:
                    parts.append(f'<a href="{span.url}" color="#1565C0"><u>{text}</u></a>')
                elif span.bold:
                    parts.append(f"<b>{text}</b>")
                elif span.italic:
                    parts.append(f"<i>{text}</i>")
                elif span.code:
                    parts.append(
                        f'<font face="{Fonts.CODE}" size="{Fonts.CODE_SIZE_PT}">'
                        f"{text}</font>"
                    )
                else:
                    parts.append(text)
            return "".join(parts)

        # -- custom flowables -------------------------------------------------
        class AccentBar(Flowable):
            def __init__(self, width, height=3, color=Colors.ACCENT):
                super().__init__()
                self.width = width
                self.height = height
                self._color = color

            def draw(self):
                self.canv.setFillColor(_rgb(self._color))
                self.canv.roundRect(
                    0, 0, self.width, self.height, radius=1.5, fill=1, stroke=0
                )

            def wrap(self, available_width, available_height):
                return self.width, self.height + 4

        class ColoredBox(Flowable):
            def __init__(
                self,
                content,
                bg_color,
                text_color,
                font_name="Courier",
                font_size=8.5,
                padding=10,
                label="",
            ):
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
                return (
                    self._label_height()
                    + len(self._lines) * self._line_height()
                    + self._padding * 2
                )

            def wrap(self, available_width, available_height):
                return available_width, min(self._natural_height(), available_height)

            def split(self, available_width, available_height):
                natural = self._natural_height()
                if natural <= available_height:
                    return [self]
                lh = self._line_height()
                usable = available_height - self._label_height() - self._padding * 2
                if usable < lh * 2:
                    return []
                n_fit = max(1, int(usable / lh))
                part1 = ColoredBox(
                    "\n".join(self._lines[:n_fit]),
                    bg_color=self._bg,
                    text_color=self._fg,
                    font_name=self._font,
                    font_size=self._font_size,
                    padding=self._padding,
                    label=self._label,
                )
                part2 = ColoredBox(
                    "\n".join(self._lines[n_fit:]),
                    bg_color=self._bg,
                    text_color=self._fg,
                    font_name=self._font,
                    font_size=self._font_size,
                    padding=self._padding,
                    label=f"{self._label} (cont.)" if self._label else "",
                )
                return [part1, part2]

            def draw(self):
                w, h = self.width, self.height
                p = self._padding
                lh = self._line_height()
                self.canv.setFillColor(_rgb(self._bg))
                self.canv.roundRect(0, 0, w, h, radius=4, fill=1, stroke=0)
                label_offset = 0
                if self._label:
                    lab_h = self._label_height()
                    self.canv.setFillColor(_rgb(Colors.PRIMARY_DARK))
                    self.canv.roundRect(
                        0, h - lab_h, w, lab_h, radius=4, fill=1, stroke=0
                    )
                    self.canv.setFillColor(_rgb(Colors.WHITE))
                    self.canv.setFont(self._font, self._font_size - 1)
                    self.canv.drawString(p, h - lab_h + 4, self._label)
                    label_offset = lab_h + 2
                self.canv.setFillColor(_rgb(self._fg))
                self.canv.setFont(self._font, self._font_size)
                y = h - p - self._font_size - label_offset
                for line in self._lines:
                    if y < p:
                        break
                    self.canv.drawString(p, y, line)
                    y -= lh

        # -- page decorations -------------------------------------------------
        repo_name = doc.metadata.repo_name or "Document"

        def _draw_page_decorations(canvas, _doc_template):
            canvas.saveState()
            w, h = A4
            canvas.setFillColor(_rgb(Colors.PRIMARY_DARK))
            canvas.rect(0, h - 18, w, 18, fill=1, stroke=0)
            canvas.setFillColor(_rgb(Colors.ACCENT))
            canvas.rect(0, h - 22, w, 4, fill=1, stroke=0)
            canvas.setFillColor(_rgb(Colors.WHITE))
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawString(inch, h - 14, repo_name)
            canvas.drawRightString(w - inch, h - 14, "opendocs")
            canvas.setStrokeColor(_rgb(Colors.TABLE_BORDER))
            canvas.setLineWidth(0.5)
            canvas.line(inch, 40, w - inch, 40)
            canvas.setFillColor(_rgb(Colors.MUTED))
            canvas.setFont("Helvetica", 8)
            canvas.drawCentredString(w / 2, 26, f"— {canvas.getPageNumber()} —")
            canvas.restoreState()

        # -- styles -----------------------------------------------------------
        base = getSampleStyleSheet()
        styles = {
            "Normal": ParagraphStyle(
                "CustomNormal",
                parent=base["Normal"],
                fontSize=10.5,
                leading=15,
                textColor=_rgb(Colors.TEXT),
                spaceAfter=4,
            ),
            "DocTitle": ParagraphStyle(
                "DocTitle",
                parent=base["Title"],
                fontName="Helvetica-Bold",
                fontSize=34,
                leading=40,
                textColor=_rgb(Colors.PRIMARY_DARK),
                alignment=TA_LEFT,
            ),
            "Subtitle": ParagraphStyle(
                "Subtitle",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=13,
                leading=18,
                textColor=_rgb(Colors.MUTED),
                alignment=TA_LEFT,
            ),
            "Heading1": ParagraphStyle(
                "Heading1",
                parent=base["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=22,
                leading=27,
                textColor=_rgb(Colors.PRIMARY_DARK),
                spaceBefore=20,
                spaceAfter=6,
            ),
            "Heading2": ParagraphStyle(
                "Heading2",
                parent=base["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=17,
                leading=21,
                textColor=_rgb(Colors.HEADING),
                spaceBefore=16,
                spaceAfter=5,
            ),
            "Heading3": ParagraphStyle(
                "Heading3",
                parent=base["Heading3"],
                fontName="Helvetica-Bold",
                fontSize=13,
                leading=16,
                textColor=_rgb(Colors.SECONDARY),
                spaceBefore=12,
                spaceAfter=4,
            ),
            "Blockquote": ParagraphStyle(
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
            ),
            "ListItem": ParagraphStyle(
                "ListItem",
                parent=base["Normal"],
                fontSize=10.5,
                leading=15,
                textColor=_rgb(Colors.TEXT),
                leftIndent=20,
                bulletIndent=10,
                spaceBefore=2,
                spaceAfter=2,
            ),
        }

        # -- build document ---------------------------------------------------
        pdf = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=inch + 10,
            bottomMargin=0.8 * inch,
        )

        story: list = []

        # Title page
        story.append(Spacer(1, 1.5 * inch))
        story.append(AccentBar(width=4.5 * inch, height=4, color=Colors.ACCENT))
        story.append(Spacer(1, 0.4 * inch))
        story.append(
            Paragraph(
                doc.metadata.repo_name or "Technical Documentation",
                styles["DocTitle"],
            )
        )
        story.append(Spacer(1, 0.15 * inch))
        story.append(AccentBar(width=2 * inch, height=3, color=Colors.PRIMARY))
        story.append(Spacer(1, 0.3 * inch))
        if doc.metadata.description:
            safe_desc = (
                doc.metadata.description[:350]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe_desc, styles["Subtitle"]))
        story.append(Spacer(1, 0.8 * inch))

        info_data = [
            ["Repository", doc.metadata.repo_name or "—"],
            ["Source", doc.metadata.repo_url or doc.metadata.source_path or "—"],
            [
                "Generated",
                doc.metadata.generated_at[:19] if doc.metadata.generated_at else "—",
            ],
            ["Tool", "opendocs v0.1"],
        ]
        info_table = Table(info_data, colWidths=[1.5 * inch, 4 * inch])
        info_table.setStyle(
            TableStyle(
                [
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
                ]
            )
        )
        story.append(info_table)
        story.append(Spacer(1, 0.5 * inch))
        story.append(AccentBar(width=4.5 * inch, height=4, color=Colors.ACCENT))
        story.append(PageBreak())

        # Body sections
        def render_section(section: Section) -> None:
            heading_key = f"Heading{min(section.level, 3)}"
            style = styles.get(heading_key, styles["Heading1"])
            heading_block = [Paragraph(section.title, style)]
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
                render_block(block)
            for sub in section.subsections:
                render_section(sub)

        def render_block(block: ContentBlock) -> None:
            if isinstance(block, ParagraphBlock):
                if block.spans:
                    html = _spans_to_html(block.spans)
                else:
                    html = (
                        block.text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                story.append(Paragraph(html, styles["Normal"]))
                story.append(Spacer(1, 0.06 * inch))

            elif isinstance(block, CodeBlock):
                label = block.language.upper() if block.language else ""
                story.append(
                    ColoredBox(
                        block.code.rstrip("\n"),
                        bg_color=Colors.CODE_BG,
                        text_color=Colors.CODE_TEXT,
                        label=label,
                    )
                )
                story.append(Spacer(1, 0.1 * inch))

            elif isinstance(block, MermaidBlock):
                idx = self._mermaid_index
                self._mermaid_index += 1
                img_path = (
                    self.image_cache.get_mermaid(idx) if self.image_cache else None
                )
                if img_path and img_path.exists():
                    from reportlab.platypus import Image as RLImage

                    img = RLImage(str(img_path), width=5.5 * inch, height=3.5 * inch)
                    img.hAlign = "CENTER"
                    story.append(img)
                else:
                    story.append(
                        ColoredBox(
                            block.code.rstrip("\n"),
                            bg_color=Colors.CODE_BG,
                            text_color=Colors.CODE_TEXT,
                            label="MERMAID DIAGRAM",
                        )
                    )
                story.append(Spacer(1, 0.1 * inch))

            elif isinstance(block, TableBlock):
                render_table(block)

            elif isinstance(block, ListBlock):
                pfn = (
                    (lambda i: f"{i + 1}. ")
                    if block.ordered
                    else (lambda _: "●  ")
                )
                for i, item in enumerate(block.items):
                    bullet = (
                        f'<font color="#{Colors.PRIMARY[0]:02X}'
                        f"{Colors.PRIMARY[1]:02X}{Colors.PRIMARY[2]:02X}\">"
                        f"{pfn(i)}</font>"
                    )
                    if block.rich_items and i < len(block.rich_items):
                        content = _spans_to_html(block.rich_items[i])
                    else:
                        content = (
                            item.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        )
                    story.append(
                        Paragraph(f"{bullet}{content}", styles["ListItem"])
                    )
                story.append(Spacer(1, 0.06 * inch))

            elif isinstance(block, BlockquoteBlock):
                safe = (
                    block.text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                story.append(Paragraph(safe, styles["Blockquote"]))
                story.append(Spacer(1, 0.06 * inch))

            elif isinstance(block, ImageBlock):
                img_path = (
                    self.image_cache.get_external(block.src)
                    if self.image_cache
                    else None
                )
                if img_path and img_path.exists():
                    from reportlab.platypus import Image as RLImage

                    if block.alt:
                        story.append(
                            Paragraph(f"<i>{block.alt}</i>", styles["Normal"])
                        )
                    img = RLImage(str(img_path), width=5.0 * inch, height=3.0 * inch)
                    img.hAlign = "CENTER"
                    story.append(img)
                    story.append(Spacer(1, 0.06 * inch))
                else:
                    story.append(
                        Paragraph(
                            f"<i>{block.alt or block.src}</i>", styles["Normal"]
                        )
                    )

            elif isinstance(block, ThematicBreakBlock):
                story.append(
                    HRFlowable(
                        width="80%",
                        thickness=1,
                        color=_rgb(Colors.TABLE_BORDER),
                        spaceBefore=8,
                        spaceAfter=8,
                    )
                )

        def render_table(block: TableBlock) -> None:
            def _esc(t: str) -> str:
                return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            def _cell_to_markup(text: str, spans: list | None) -> str:
                """Convert cell spans to ReportLab HTML markup (with links)."""
                if not spans:
                    return _esc(text)
                parts = []
                for span in spans:
                    t = _esc(span.text) if span.text else ""
                    if not t:
                        continue
                    if span.is_link:
                        parts.append(f'<a href="{span.url}" color="#1565C0"><u>{t}</u></a>')
                    elif span.bold:
                        parts.append(f"<b>{t}</b>")
                    elif span.italic:
                        parts.append(f"<i>{t}</i>")
                    elif span.code:
                        parts.append(f'<font face="Courier" size="8">{t}</font>')
                    else:
                        parts.append(t)
                return "".join(parts) if parts else _esc(text)

            tbl_style = styles["Normal"]

            data: list[list] = []
            if block.headers:
                row_markup = []
                for j, h in enumerate(block.headers):
                    spans = (
                        block.rich_headers[j]
                        if block.rich_headers and j < len(block.rich_headers)
                        else None
                    )
                    row_markup.append(Paragraph(_cell_to_markup(h, spans), tbl_style))
                data.append(row_markup)
            for row_i, row in enumerate(block.rows):
                row_markup = []
                for j, val in enumerate(row):
                    spans = (
                        block.rich_rows[row_i][j]
                        if (
                            block.rich_rows
                            and row_i < len(block.rich_rows)
                            and j < len(block.rich_rows[row_i])
                        )
                        else None
                    )
                    row_markup.append(Paragraph(_cell_to_markup(val, spans), tbl_style))
                data.append(row_markup)
            if not data:
                return
            num_cols = len(data[0])
            col_w = (6.3 * inch) / max(num_cols, 1)
            t = Table(
                data,
                colWidths=[col_w] * num_cols,
                repeatRows=1 if block.headers else 0,
            )
            cmds = [
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
                cmds += [
                    ("BACKGROUND", (0, 0), (-1, 0), _rgb(Colors.TABLE_HEADER_BG)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), _rgb(Colors.WHITE)),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9.5),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ]
                for i in range(1, len(data)):
                    if i % 2 == 0:
                        cmds.append(
                            ("BACKGROUND", (0, i), (-1, i), _rgb(Colors.TABLE_ALT_ROW))
                        )
            else:
                for i in range(len(data)):
                    if i % 2 == 0:
                        cmds.append(
                            ("BACKGROUND", (0, i), (-1, i), _rgb(Colors.TABLE_ALT_ROW))
                        )
            t.setStyle(TableStyle(cmds))
            story.append(t)
            story.append(Spacer(1, 0.15 * inch))

        for section in doc.sections:
            render_section(section)

        # KG page
        if self.kg and self.kg.entities:
            story.append(PageBreak())
            self._build_kg_reportlab(
                story,
                styles,
                _rgb,
                AccentBar,
                ColoredBox,
                Paragraph,
                Spacer,
                Table,
                TableStyle,
            )

        # Metadata page
        story.append(PageBreak())
        story.append(Paragraph("Document Metadata", styles["Heading1"]))
        story.append(AccentBar(width=2 * inch, height=3, color=Colors.ACCENT))
        story.append(Spacer(1, 0.3 * inch))

        meta = doc.metadata
        items = [
            ("Repository", meta.repo_name or "—"),
            ("URL", meta.repo_url or "—"),
            ("Source Path", meta.source_path or "—"),
            ("Generated At", meta.generated_at or "—"),
            ("Generator", "opendocs v0.1"),
            ("Sections", str(len(doc.sections))),
            ("Content Blocks", str(len(doc.all_blocks))),
        ]
        mt = Table(items, colWidths=[2 * inch, 4 * inch])
        mcmds = [
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
        for i in range(len(items)):
            if i % 2 == 0:
                mcmds.append(("BACKGROUND", (0, i), (-1, i), _rgb(Colors.BG_LIGHT)))
        mt.setStyle(TableStyle(mcmds))
        story.append(mt)

        pdf.build(
            story,
            onFirstPage=lambda c, d: None,
            onLaterPages=_draw_page_decorations,
        )

    # ------------------------------------------------------------------
    # KG page (ReportLab fallback helper)
    # ------------------------------------------------------------------

    def _build_kg_reportlab(
        self, story, styles, _rgb, AccentBar, ColoredBox,
        Paragraph, Spacer, Table, TableStyle,
    ):
        from reportlab.lib.units import inch

        from ..core.knowledge_graph import EntityType
        from .styles import Colors

        kg = self.kg
        if not kg:
            return

        story.append(Paragraph("Knowledge Graph", styles["Heading1"]))
        story.append(AccentBar(width=2 * inch, height=3, color=Colors.ACCENT))
        story.append(Spacer(1, 0.25 * inch))

        if kg.executive_summary:
            story.append(Paragraph("Executive Summary", styles["Heading2"]))
            story.append(Spacer(1, 0.08 * inch))
            safe = (
                kg.executive_summary.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe, styles["Blockquote"]))
            story.append(Spacer(1, 0.2 * inch))

        persona_labels = {
            "cto": "CTO / Technical Lead",
            "investor": "Investor / Business",
            "developer": "Developer Onboarding",
        }
        if kg.stakeholder_summaries:
            story.append(Paragraph("Stakeholder Views", styles["Heading2"]))
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
                        f'<font color="#{Colors.ACCENT[0]:02X}{Colors.ACCENT[1]:02X}'
                        f'{Colors.ACCENT[2]:02X}">●  </font>'
                        if is_bullet
                        else ""
                    )
                    story.append(Paragraph(f"{prefix}{safe_line}", styles["ListItem"]))
                story.append(Spacer(1, 0.1 * inch))

        stats = kg.extraction_stats or kg.compute_stats()
        stats_items = [
            ["Total Entities", str(stats.get("total_entities", 0))],
            ["Total Relations", str(stats.get("total_relations", 0))],
            ["Deterministic", str(stats.get("deterministic_entities", 0))],
            ["LLM-Extracted", str(stats.get("llm_entities", 0))],
        ]
        st = Table(stats_items, colWidths=[2 * inch, 1.5 * inch])
        st.setStyle(
            TableStyle(
                [
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
                ]
            )
        )
        story.append(st)
        story.append(Spacer(1, 0.3 * inch))

        story.append(Paragraph("Discovered Entities", styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))
        for et in EntityType:
            entities = kg.entities_of_type(et)
            if not entities:
                continue
            label = et.value.replace("_", " ").title()
            story.append(
                Paragraph(
                    f'<font color="#{Colors.PRIMARY[0]:02X}{Colors.PRIMARY[1]:02X}'
                    f'{Colors.PRIMARY[2]:02X}">▸ {label}</font>',
                    styles["Normal"],
                )
            )
            for e in entities[:8]:
                conf = e.confidence
                dot_color = (
                    Colors.SUCCESS
                    if conf >= 0.8
                    else Colors.WARNING if conf >= 0.5 else Colors.DANGER
                )
                dot_hex = f"#{dot_color[0]:02X}{dot_color[1]:02X}{dot_color[2]:02X}"
                safe_name = (
                    e.name.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                story.append(
                    Paragraph(
                        f'&nbsp;&nbsp;&nbsp;&nbsp;<font color="{dot_hex}">●</font> '
                        f"{safe_name} "
                        f'<font size="8" color="#{Colors.MUTED[0]:02X}'
                        f'{Colors.MUTED[1]:02X}{Colors.MUTED[2]:02X}">'
                        f"({conf:.0%})</font>",
                        styles["Normal"],
                    )
                )
            if len(entities) > 8:
                story.append(
                    Paragraph(
                        f'&nbsp;&nbsp;&nbsp;&nbsp;<font color="#{Colors.MUTED[0]:02X}'
                        f'{Colors.MUTED[1]:02X}{Colors.MUTED[2]:02X}">'
                        f"… and {len(entities) - 8} more</font>",
                        styles["Normal"],
                    )
                )
            story.append(Spacer(1, 0.06 * inch))

        story.append(Spacer(1, 0.2 * inch))
        story.append(
            Paragraph("Auto-Generated Architecture Graph", styles["Heading2"])
        )
        story.append(Spacer(1, 0.08 * inch))
        kg_img = self.image_cache.kg_diagram if self.image_cache else None
        if kg_img and kg_img.exists():
            from reportlab.platypus import Image as RLImage

            img = RLImage(str(kg_img), width=5.8 * inch, height=3.8 * inch)
            img.hAlign = "CENTER"
            story.append(img)
        else:
            mermaid_code = kg.to_mermaid()
            story.append(
                ColoredBox(
                    mermaid_code,
                    bg_color=Colors.CODE_BG,
                    text_color=Colors.CODE_TEXT,
                    label="MERMAID",
                )
            )
        story.append(Spacer(1, 0.1 * inch))
