"""Chart generation tool — chart.generate.

Converts structured data into chart images (bar, line, pie, etc.)
using matplotlib as the default backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ChartGenerateTool:
    """Generate chart images from structured data.

    Uses matplotlib for local rendering. Agents provide data + chart_type;
    this tool produces a PNG/SVG file.
    """

    def __init__(self, output_dir: Path | str = ".") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = params["data"]
        chart_type: str = params["chart_type"]
        title: str = params.get("title", "")
        output_format: str = params.get("output_format", "png")

        # TODO: validate data schema (labels, values, series)
        # TODO: dispatch to appropriate chart renderer:
        #   bar   → _render_bar(data, title)
        #   line  → _render_line(data, title)
        #   pie   → _render_pie(data, title)
        #   scatter → _render_scatter(data, title)
        #   heatmap → _render_heatmap(data, title)
        #   treemap → _render_treemap(data, title)
        # TODO: save to output_dir / f"chart_{uuid}.{output_format}"
        # TODO: return path + inline content for SVG
        return {
            "chart_type": chart_type,
            "output_format": output_format,
            "output_path": "",          # TODO: path to rendered chart
            "title": title,
        }
