"""doc.prd — Generate a Product Requirements Document."""

from __future__ import annotations

from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel
from ..models.document_model import DraftDocument, DocumentType


class PRDSkill(BaseSkill):
    """Generate a PRD from the repository knowledge model."""

    name = "doc.prd"

    def run(self, *, repo_model: RepoKnowledgeModel, **kwargs: Any) -> DraftDocument:
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        if use_llm:
            try:
                return self._run_llm(repo_model, llm_config)
            except Exception as exc:
                self.logger.warning("LLM PRD generation failed (%s), falling back to deterministic", exc)

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
            f"Target Users: {', '.join(m.target_users[:10])}\n"
            f"Architecture: {chr(10).join('- ' + c for c in m.architecture_components[:10])}\n"
            f"API Endpoints: {len(m.api_endpoints)}\n"
            f"Dependencies: {len(m.dependencies)}\n"
            f"Risks: {chr(10).join('- ' + r for r in m.risks[:10])}\n"
            f"Repository: {m.repo_url}\n"
        )

        system = (
            "You are a senior product manager writing a Product Requirements Document (PRD). "
            "Write a comprehensive, professional PRD in Markdown. Include these sections:\n"
            "1. Overview (project description, tech stack, repo link)\n"
            "2. Problem Statement (what problem this solves, why it matters)\n"
            "3. Target Users (who benefits, user personas)\n"
            "4. Features (detailed feature list with descriptions)\n"
            "5. Architecture Components (system design overview)\n"
            "6. API Endpoints (if applicable, in a table)\n"
            "7. User Stories (concrete user stories in 'As a... I want... So that...' format)\n"
            "8. Acceptance Criteria (checkboxes)\n"
            "9. Dependencies (key packages)\n"
            "10. Risks & Mitigations\n"
            "11. Assumptions\n\n"
            "Be specific and technical. Use real data from the repository. "
            "Do NOT use generic filler text. Start with a # heading."
        )

        content = chat_text(system, context, **llm_config)
        self.logger.info("LLM-generated PRD: %d chars", len(content))

        sections = [line.lstrip("# ").strip() for line in content.splitlines()
                     if line.startswith("## ")]

        return DraftDocument(
            doc_type=DocumentType.PRD,
            title=f"PRD — {m.project_name}",
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

        # --- Title ---
        parts.append(f"# Product Requirements Document — {m.project_name}\n")

        # --- Overview ---
        sections.append("Overview")
        parts.append("## Overview\n")
        parts.append(f"{m.description}\n")
        if m.tech_stack:
            parts.append(f"**Tech Stack:** {', '.join(m.tech_stack)}\n")
        parts.append(f"**Repository:** {m.repo_url}\n")

        # --- Problem ---
        sections.append("Problem")
        parts.append("## Problem Statement\n")
        parts.append(f"{m.problem_statement}\n")

        # --- Users ---
        sections.append("Users")
        parts.append("## Target Users\n")
        if m.target_users:
            for u in m.target_users:
                parts.append(f"- {u}")
            parts.append("")
        else:
            parts.append("- Software developers\n")

        # --- Features ---
        sections.append("Features")
        parts.append("## Features\n")
        if m.features:
            for i, f in enumerate(m.features, 1):
                parts.append(f"{i}. {f}")
            parts.append("")
        else:
            parts.append("*Features to be documented from codebase analysis.*\n")

        # --- Architecture ---
        if m.architecture_components:
            parts.append("## Architecture Components\n")
            for comp in m.architecture_components:
                parts.append(f"- {comp}")
            parts.append("")

        # --- API Endpoints ---
        if m.api_endpoints:
            parts.append("## API Endpoints\n")
            parts.append("| Method | Path | Description |")
            parts.append("|--------|------|-------------|")
            for ep in m.api_endpoints[:20]:
                parts.append(f"| {ep.method} | `{ep.path}` | {ep.description} |")
            parts.append("")

        # --- User Stories ---
        sections.append("User Stories")
        parts.append("## User Stories\n")
        if m.features:
            for i, f in enumerate(m.features[:8], 1):
                parts.append(f"**US-{i:03d}:** As a user, I want to {f.lower().rstrip('.')}"
                             f" so that I can benefit from this capability.\n")
        else:
            parts.append("- As a user, I want to use this project to solve my problem.\n")

        # --- Acceptance Criteria ---
        sections.append("Acceptance Criteria")
        parts.append("## Acceptance Criteria\n")
        parts.append("- [ ] All documented features are functional")
        parts.append("- [ ] Setup instructions are reproducible")
        parts.append("- [ ] Tests pass on CI/CD pipeline")
        if m.api_endpoints:
            parts.append("- [ ] All API endpoints return expected responses")
        parts.append("")

        # --- Dependencies ---
        if m.dependencies:
            parts.append("## Dependencies\n")
            for pkg, ver in list(m.dependencies.items())[:20]:
                parts.append(f"- `{pkg}` {ver}")
            parts.append("")

        # --- Risks ---
        if m.risks:
            parts.append("## Risks & Mitigations\n")
            for r in m.risks:
                parts.append(f"- ⚠️ {r}")
            parts.append("")

        # --- Assumptions ---
        if m.assumptions:
            parts.append("## Assumptions\n")
            for a in m.assumptions:
                parts.append(f"- {a}")
            parts.append("")

        content = "\n".join(parts)
        self.logger.info("Generated PRD: %d chars, %d sections", len(content), len(sections))

        return DraftDocument(
            doc_type=DocumentType.PRD,
            title=f"PRD — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )
