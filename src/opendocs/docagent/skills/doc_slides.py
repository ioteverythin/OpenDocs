"""doc.slides — Generate a slide narrative for PowerPoint."""

from __future__ import annotations

from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel
from ..models.document_model import DraftDocument, DocumentType


class SlidesSkill(BaseSkill):
    """Generate an 8–12 slide narrative in bullet format."""

    name = "doc.slides"

    def run(self, *, repo_model: RepoKnowledgeModel, **kwargs: Any) -> DraftDocument:
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        if use_llm:
            try:
                return self._run_llm(repo_model, llm_config)
            except Exception as exc:
                self.logger.warning("LLM Slides failed (%s), falling back", exc)

        return self._run_deterministic(repo_model)

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _run_llm(self, m: RepoKnowledgeModel, llm_config: dict[str, Any]) -> DraftDocument:
        from ..llm_client import chat_text

        context = (
            f"Project: {m.project_name}\n"
            f"Description: {m.description}\n"
            f"Problem: {m.problem_statement}\n"
            f"Tech Stack: {', '.join(m.tech_stack)}\n"
            f"Features: {chr(10).join('- ' + f for f in m.features[:12])}\n"
            f"Target Users: {', '.join(m.target_users[:8])}\n"
            f"Architecture: {chr(10).join('- ' + c for c in m.architecture_components[:8])}\n"
            f"Data Flow: {chr(10).join('- ' + d for d in m.data_flow[:6])}\n"
            f"Risks: {chr(10).join('- ' + r for r in m.risks[:5])}\n"
            f"Roadmap: {chr(10).join('- ' + r for r in m.roadmap[:5])}\n"
            f"Repository: {m.repo_url}\n"
        )

        system = (
            "You are a presentation designer creating a 10-12 slide deck narrative. "
            "Write the slide content in Markdown where each slide is a ## heading. "
            "Format:\n"
            "## Slide N — Title\n"
            "- Bullet point\n"
            "- Bullet point\n\n"
            "Include these slides:\n"
            "1. Title slide\n"
            "2. The Problem\n"
            "3. Our Solution\n"
            "4. Key Features\n"
            "5. Architecture Overview\n"
            "6. Technology Stack\n"
            "7. How It Works (data flow)\n"
            "8. Target Users\n"
            "9. Getting Started\n"
            "10. Risks & Mitigations\n"
            "11. Roadmap\n"
            "12. Q&A\n\n"
            "Keep bullets concise (max 8 words each). "
            "Make it compelling and presentation-ready. Start with a # heading."
        )

        content = chat_text(system, context, **llm_config)
        self.logger.info("LLM-generated Slides: %d chars", len(content))

        slide_count = content.count("## Slide")
        return DraftDocument(
            doc_type=DocumentType.SLIDES,
            title=f"Slides — {m.project_name}",
            content=content,
            version=1,
            sections=[f"Slide {i}" for i in range(1, slide_count + 1)],
        )

    # ------------------------------------------------------------------
    # Deterministic path
    # ------------------------------------------------------------------

    def _run_deterministic(self, repo_model: RepoKnowledgeModel) -> DraftDocument:
        m = repo_model
        parts: list[str] = []

        parts.append(f"# {m.project_name}\n")

        # --- Slide 1: Title ---
        parts.append("## Slide 1 — Title\n")
        parts.append(f"- **{m.project_name}**")
        parts.append(f"- {m.description[:120]}")
        parts.append(f"- {m.repo_url}")
        parts.append("")

        # --- Slide 2: Problem ---
        parts.append("## Slide 2 — The Problem\n")
        if m.problem_statement:
            for sentence in m.problem_statement.split(". ")[:4]:
                parts.append(f"- {sentence.strip()}")
        else:
            parts.append("- Existing solutions are fragmented")
            parts.append("- Need for a unified approach")
        parts.append("")

        # --- Slide 3: Solution ---
        parts.append("## Slide 3 — Our Solution\n")
        parts.append(f"- {m.project_name}: {m.description[:100]}")
        if m.features:
            for f in m.features[:3]:
                parts.append(f"- {f}")
        parts.append("")

        # --- Slide 4: Key Features ---
        parts.append("## Slide 4 — Key Features\n")
        if m.features:
            for f in m.features[:6]:
                parts.append(f"- {f}")
        else:
            parts.append("- See repository documentation for features")
        parts.append("")

        # --- Slide 5: Architecture ---
        parts.append("## Slide 5 — Architecture\n")
        if m.tech_stack:
            parts.append(f"- Built with: {', '.join(m.tech_stack[:5])}")
        if m.architecture_components:
            for comp in m.architecture_components[:4]:
                parts.append(f"- {comp}")
        parts.append("")

        # --- Slide 6: Tech Stack ---
        parts.append("## Slide 6 — Technology Stack\n")
        if m.tech_stack:
            for tech in m.tech_stack[:8]:
                parts.append(f"- {tech}")
        parts.append("")

        # --- Slide 7: How It Works ---
        parts.append("## Slide 7 — How It Works\n")
        if m.data_flow:
            for i, step in enumerate(m.data_flow[:5], 1):
                parts.append(f"- Step {i}: {step}")
        else:
            parts.append("- Clone → Configure → Run → Deploy")
        parts.append("")

        # --- Slide 8: Target Users ---
        parts.append("## Slide 8 — Who Is It For?\n")
        for u in m.target_users:
            parts.append(f"- {u}")
        parts.append("")

        # --- Slide 9: Getting Started ---
        parts.append("## Slide 9 — Getting Started\n")
        if m.setup_instructions:
            for cmd in m.setup_instructions[:4]:
                parts.append(f"- `{cmd}`")
        else:
            parts.append(f"- `git clone {m.repo_url}`")
            parts.append(f"- `cd {m.project_name}`")
            parts.append("- Follow README for setup")
        parts.append("")

        # --- Slide 10: Risks & Challenges ---
        if m.risks:
            parts.append("## Slide 10 — Risks & Mitigations\n")
            for r in m.risks[:4]:
                parts.append(f"- {r}")
            parts.append("")

        # --- Slide 11: Roadmap ---
        parts.append("## Slide 11 — Roadmap\n")
        if m.roadmap:
            for item in m.roadmap[:5]:
                parts.append(f"- {item}")
        else:
            parts.append("- Phase 1: Core features")
            parts.append("- Phase 2: Integration & testing")
            parts.append("- Phase 3: Production readiness")
        parts.append("")

        # --- Slide 12: Q&A ---
        parts.append("## Slide 12 — Questions?\n")
        parts.append(f"- Repository: {m.repo_url}")
        parts.append("- Thank you!")
        parts.append("")

        content = "\n".join(parts)
        slide_count = content.count("## Slide")
        self.logger.info("Generated Slides: %d slides", slide_count)

        return DraftDocument(
            doc_type=DocumentType.SLIDES,
            title=f"Slides — {m.project_name}",
            content=content,
            version=1,
            sections=[f"Slide {i}" for i in range(1, slide_count + 1)],
        )
