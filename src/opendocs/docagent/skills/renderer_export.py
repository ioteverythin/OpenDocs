"""renderer.export — Export finalised drafts to output formats."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseSkill
from ..models.document_model import DraftDocument, ExportFormat
from ..tools.export_tools import ExportTools


class RendererExportSkill(BaseSkill):
    """Export a draft to one or more output formats."""

    name = "renderer.export"

    def run(
        self,
        *,
        draft: DraftDocument,
        export_tools: ExportTools,
        formats: list[ExportFormat] | None = None,
        **kwargs: Any,
    ) -> list[Path]:
        """Export the draft and return output file paths."""
        if formats is None:
            formats = list(ExportFormat)

        diagram_paths: dict = kwargs.get("diagram_paths", {})

        paths: list[Path] = []
        for fmt in formats:
            try:
                p = export_tools.export(draft, fmt, diagram_paths=diagram_paths)
                paths.append(p)
                self.logger.info("Exported %s → %s", fmt.value, p)
            except Exception as exc:
                self.logger.warning("Export failed (%s): %s", fmt.value, exc)

        return paths
