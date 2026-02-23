"""doc.proposal — Generate a technical/business proposal."""

from __future__ import annotations

from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel
from ..models.document_model import DraftDocument, DocumentType


class ProposalSkill(BaseSkill):
    """Generate a Proposal document from the repository knowledge model."""

    name = "doc.proposal"

    def run(self, *, repo_model: RepoKnowledgeModel, **kwargs: Any) -> DraftDocument:
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        if use_llm:
            try:
                return self._run_llm(repo_model, llm_config)
            except Exception as exc:
                self.logger.warning("LLM Proposal failed (%s), falling back", exc)

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
            f"Features: {chr(10).join('- ' + f for f in m.features[:15])}\n"
            f"Architecture: {chr(10).join('- ' + c for c in m.architecture_components[:10])}\n"
            f"Data Flow: {chr(10).join('- ' + d for d in m.data_flow[:10])}\n"
            f"File Count: {len(m.file_tree)}\n"
            f"Dependencies: {len(m.dependencies)}\n"
            f"Risks: {chr(10).join('- ' + r for r in m.risks[:10])}\n"
            f"Repository: {m.repo_url}\n"
        )

        system = (
            "You are a senior solutions architect writing a Technical Proposal. "
            "Write a professional, persuasive proposal in Markdown. Include:\n"
            "1. Value Proposition (what value this delivers)\n"
            "2. Solution Overview (capabilities, approach)\n"
            "3. Architecture (components, data flow, tech stack table)\n"
            "4. Timeline (phased delivery with durations)\n"
            "5. Effort Estimate (complexity analysis, person-weeks)\n"
            "6. Risks & Mitigations\n"
            "7. Success Criteria\n\n"
            "Be specific to THIS project. Use real data. Start with a # heading."
        )

        content = chat_text(system, context, **llm_config)
        self.logger.info("LLM-generated Proposal: %d chars", len(content))

        sections = [line.lstrip("# ").strip() for line in content.splitlines()
                     if line.startswith("## ")]

        return DraftDocument(
            doc_type=DocumentType.PROPOSAL,
            title=f"Proposal — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )

    # ------------------------------------------------------------------
    # Deterministic path
    # ------------------------------------------------------------------

    def _run_deterministic(self, repo_model: RepoKnowledgeModel) -> DraftDocument:
        m = repo_model
        sections: list[str] = []
        parts: list[str] = []

        parts.append(f"# Technical Proposal — {m.project_name}\n")

        # --- Value Proposition ---
        sections.append("Value Proposition")
        parts.append("## Value Proposition\n")
        parts.append(f"{m.description}\n")
        if m.problem_statement:
            parts.append(f"**Problem Addressed:** {m.problem_statement}\n")

        # --- Solution Overview ---
        sections.append("Solution Overview")
        parts.append("## Solution Overview\n")
        parts.append(f"**{m.project_name}** provides a comprehensive solution "
                     f"built with {', '.join(m.tech_stack[:5]) if m.tech_stack else 'modern technologies'}.\n")
        if m.features:
            parts.append("### Key Capabilities\n")
            for f in m.features[:10]:
                parts.append(f"- {f}")
            parts.append("")

        # --- Architecture ---
        sections.append("Architecture")
        parts.append("## Architecture\n")
        if m.architecture_components:
            parts.append("### Components\n")
            for comp in m.architecture_components:
                parts.append(f"- {comp}")
            parts.append("")
        if m.data_flow:
            parts.append("### Data Flow\n")
            for step in m.data_flow:
                parts.append(f"1. {step}")
            parts.append("")

        # --- Technology Stack ---
        if m.tech_stack:
            parts.append("### Technology Stack\n")
            parts.append("| Category | Technology |")
            parts.append("|----------|-----------|")
            for tech in m.tech_stack:
                parts.append(f"| Core | {tech} |")
            parts.append("")

        # --- Timeline ---
        sections.append("Timeline")
        parts.append("## Timeline\n")
        parts.append("| Phase | Duration | Deliverables |")
        parts.append("|-------|----------|-------------|")
        parts.append("| Phase 1: Setup & Architecture | 1-2 weeks | Environment setup, architecture review |")
        parts.append("| Phase 2: Core Development | 2-4 weeks | Core feature implementation |")
        parts.append("| Phase 3: Integration & Testing | 1-2 weeks | Integration tests, QA |")
        parts.append("| Phase 4: Deployment & Launch | 1 week | Production deployment |")
        parts.append("")

        # --- Effort Estimate ---
        sections.append("Effort Estimate")
        parts.append("## Effort Estimate\n")
        file_count = len(m.file_tree)
        dep_count = len(m.dependencies)
        complexity = "High" if file_count > 100 else "Medium" if file_count > 30 else "Low"
        parts.append(f"- **Codebase Size:** {file_count} files")
        parts.append(f"- **Dependencies:** {dep_count} packages")
        parts.append(f"- **Complexity:** {complexity}")
        parts.append(f"- **Estimated Effort:** {'8-12' if complexity == 'High' else '4-8' if complexity == 'Medium' else '2-4'} person-weeks")
        parts.append("")

        # --- Risks ---
        if m.risks:
            parts.append("## Risks\n")
            for r in m.risks:
                parts.append(f"- {r}")
            parts.append("")

        content = "\n".join(parts)
        self.logger.info("Generated Proposal: %d chars", len(content))

        return DraftDocument(
            doc_type=DocumentType.PROPOSAL,
            title=f"Proposal — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )
