"""Diagram rendering tool — diagram.render.

Renders Mermaid, PlantUML, or Graphviz source into SVG/PNG.
Uses local CLI tools when available, falls back to online APIs.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any


class DiagramRenderTool:
    """Render a diagram specification into an image.

    Supported backends:
    - **Mermaid**: ``mmdc`` (mermaid-cli) or Mermaid.ink API
    - **PlantUML**: ``plantuml`` JAR or PlantUML server
    - **Graphviz**: ``dot`` command
    """

    def __init__(self, output_dir: Path | str = ".") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        diagram_type: str = params["type"]           # mermaid | plantuml | graphviz
        spec: str = params["spec"]
        output_format: str = params.get("output_format", "svg")
        theme: str = params.get("theme", "default")

        renderer = {
            "mermaid": self._render_mermaid,
            "plantuml": self._render_plantuml,
            "graphviz": self._render_graphviz,
        }.get(diagram_type)

        if renderer is None:
            return {"error": f"Unsupported diagram type: {diagram_type}"}

        # TODO: implement each renderer
        return await renderer(spec, output_format, theme)

    async def _render_mermaid(
        self, spec: str, output_format: str, theme: str
    ) -> dict[str, Any]:
        """Render Mermaid diagram via mmdc CLI or Mermaid.ink API."""
        # TODO: check for `mmdc` on PATH
        # TODO: write spec to temp .mmd file
        # TODO: run `mmdc -i input.mmd -o output.{fmt} -t {theme}`
        # TODO: fallback to https://mermaid.ink/svg/{base64(spec)}
        return {
            "type": "mermaid",
            "output_format": output_format,
            "output_path": "",          # TODO: path to rendered image
            "svg_content": "",          # TODO: inline SVG (if svg format)
        }

    async def _render_plantuml(
        self, spec: str, output_format: str, theme: str
    ) -> dict[str, Any]:
        """Render PlantUML diagram via local JAR or server."""
        # TODO: check for plantuml.jar or use PlantUML server API
        # TODO: run `java -jar plantuml.jar -t{fmt} input.puml`
        return {
            "type": "plantuml",
            "output_format": output_format,
            "output_path": "",
        }

    async def _render_graphviz(
        self, spec: str, output_format: str, theme: str
    ) -> dict[str, Any]:
        """Render Graphviz diagram via dot CLI."""
        # TODO: write spec to temp .dot file
        # TODO: run `dot -T{fmt} -o output.{fmt} input.dot`
        return {
            "type": "graphviz",
            "output_format": output_format,
            "output_path": "",
        }
