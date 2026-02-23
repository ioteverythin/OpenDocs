"""diagram.gen — Generate Mermaid diagrams via LLM and render to PNG.

Uses GPT to produce architecture, data flow, and component diagrams
as Mermaid syntax, then renders to PNG via the existing MermaidRenderer.
Falls back to deterministic Mermaid generation when LLM is unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel

logger = logging.getLogger("docagent.skill.diagram.gen")


class DiagramGenSkill(BaseSkill):
    """Generate Mermaid diagrams and render them to PNG images."""

    name = "diagram.gen"

    # Diagram types we produce
    DIAGRAM_TYPES = ("architecture", "data_flow", "component")

    def run(
        self,
        *,
        repo_model: RepoKnowledgeModel,
        diagrams_dir: Path,
        **kwargs: Any,
    ) -> dict[str, Path | None]:
        """Generate diagrams and return ``{diagram_type: png_path}``.

        Parameters
        ----------
        repo_model
            The repository knowledge model.
        diagrams_dir
            Directory to write rendered PNGs and Mermaid source.
        """
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        diagrams_dir.mkdir(parents=True, exist_ok=True)

        # Get a renderer
        from opendocs.generators.mermaid_renderer import MermaidRenderer
        renderer = MermaidRenderer(cache_dir=diagrams_dir, backend="ink")

        results: dict[str, Path | None] = {}

        for diagram_type in self.DIAGRAM_TYPES:
            try:
                if use_llm:
                    mermaid_src = self._gen_llm(repo_model, diagram_type, llm_config)
                else:
                    mermaid_src = self._gen_deterministic(repo_model, diagram_type)

                if not mermaid_src:
                    results[diagram_type] = None
                    continue

                # Save raw .mmd source
                mmd_path = diagrams_dir / f"{diagram_type}.mmd"
                mmd_path.write_text(mermaid_src, encoding="utf-8")

                # Render to PNG
                png_path = renderer.render(mermaid_src, label=diagram_type)
                results[diagram_type] = png_path

                if png_path:
                    self.logger.info("Rendered %s diagram → %s", diagram_type, png_path)
                else:
                    self.logger.warning("Failed to render %s diagram", diagram_type)

            except Exception as exc:
                self.logger.warning("Diagram %s failed: %s", diagram_type, exc)
                results[diagram_type] = None

        rendered = sum(1 for v in results.values() if v is not None)
        self.logger.info("Diagrams: %d/%d rendered", rendered, len(self.DIAGRAM_TYPES))
        return results

    # ------------------------------------------------------------------
    # LLM diagram generation
    # ------------------------------------------------------------------

    def _gen_llm(
        self,
        m: RepoKnowledgeModel,
        diagram_type: str,
        llm_config: dict[str, Any],
    ) -> str:
        from ..llm_client import chat_text

        prompts = {
            "architecture": (
                "Generate a Mermaid architecture diagram for this project. "
                "Use `graph TB` or `graph LR`. Show the main components, "
                "their relationships, and external services. Use subgraphs "
                "to group related components. Keep it clean (max 20 nodes)."
            ),
            "data_flow": (
                "Generate a Mermaid data flow diagram for this project. "
                "Use `flowchart LR` or `sequenceDiagram`. Show how data "
                "moves from input to output through the key components. "
                "Keep it clear and readable (max 15 nodes)."
            ),
            "component": (
                "Generate a Mermaid component/class diagram for this project. "
                "Use `classDiagram` or `graph TB`. Show the major modules, "
                "classes, or services and their dependencies. Group by layer "
                "(API, business logic, data). Keep it concise (max 15 nodes)."
            ),
        }

        context = (
            f"Project: {m.project_name}\n"
            f"Description: {m.description}\n"
            f"Tech Stack: {', '.join(m.tech_stack)}\n"
            f"Architecture: {chr(10).join('- ' + c for c in m.architecture_components[:12])}\n"
            f"Data Flow: {chr(10).join('- ' + d for d in m.data_flow[:10])}\n"
            f"Key Files: {', '.join(list(m.key_files.keys())[:15])}\n"
        )

        system = (
            "You are a software architect creating Mermaid diagrams. "
            "Return ONLY the raw Mermaid code — no markdown fences, "
            "no explanation, no ```mermaid tags. Just the diagram code.\n\n"
            f"{prompts.get(diagram_type, prompts['architecture'])}"
        )

        raw = chat_text(system, context, **llm_config)

        # Clean up: strip code fences if LLM included them
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            # Remove first and last fence lines
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        return cleaned

    # ------------------------------------------------------------------
    # Deterministic diagram generation
    # ------------------------------------------------------------------

    def _gen_deterministic(self, m: RepoKnowledgeModel, diagram_type: str) -> str:
        dispatch = {
            "architecture": self._arch_deterministic,
            "data_flow": self._flow_deterministic,
            "component": self._comp_deterministic,
        }
        builder = dispatch.get(diagram_type)
        return builder(m) if builder else ""

    def _arch_deterministic(self, m: RepoKnowledgeModel) -> str:
        """Build a simple architecture diagram from components."""
        if not m.architecture_components:
            return ""

        lines = ["graph TB"]
        safe = lambda s: s.replace('"', "'").replace("(", "").replace(")", "")

        # Create node for each component
        for i, comp in enumerate(m.architecture_components[:12]):
            node_id = f"C{i}"
            lines.append(f'    {node_id}["{safe(comp)}"]')

        # Connect sequentially as a simple flow
        for i in range(len(m.architecture_components[:12]) - 1):
            lines.append(f"    C{i} --> C{i + 1}")

        return "\n".join(lines)

    def _flow_deterministic(self, m: RepoKnowledgeModel) -> str:
        """Build a data flow diagram from the data_flow field."""
        if not m.data_flow:
            return ""

        lines = ["flowchart LR"]
        safe = lambda s: s.replace('"', "'").replace("(", "").replace(")", "")

        for i, step in enumerate(m.data_flow[:10]):
            node_id = f"S{i}"
            lines.append(f'    {node_id}["{safe(step)}"]')

        for i in range(len(m.data_flow[:10]) - 1):
            lines.append(f"    S{i} --> S{i + 1}")

        return "\n".join(lines)

    def _comp_deterministic(self, m: RepoKnowledgeModel) -> str:
        """Build a component diagram from tech stack + key files."""
        if not m.tech_stack and not m.key_files:
            return ""

        lines = ["graph TB"]
        safe = lambda s: s.replace('"', "'").replace("(", "").replace(")", "")

        # Tech stack as a subgraph
        if m.tech_stack:
            lines.append('    subgraph Stack["Tech Stack"]')
            for i, tech in enumerate(m.tech_stack[:8]):
                lines.append(f'        T{i}["{safe(tech)}"]')
            lines.append("    end")

        # Key files as another subgraph
        key_file_names = list(m.key_files.keys())[:8]
        if key_file_names:
            lines.append('    subgraph Modules["Key Modules"]')
            for i, fname in enumerate(key_file_names):
                short = fname.split("/")[-1]
                lines.append(f'        M{i}["{safe(short)}"]')
            lines.append("    end")

        # Connect stacks to modules
        if m.tech_stack and key_file_names:
            lines.append("    Stack --> Modules")

        return "\n".join(lines)
