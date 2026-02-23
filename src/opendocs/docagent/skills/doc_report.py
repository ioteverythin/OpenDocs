"""doc.report — Generate a full technical report."""

from __future__ import annotations

from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel
from ..models.document_model import DraftDocument, DocumentType


class ReportSkill(BaseSkill):
    """Generate a comprehensive technical report."""

    name = "doc.report"

    def run(self, *, repo_model: RepoKnowledgeModel, **kwargs: Any) -> DraftDocument:
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        if use_llm:
            try:
                return self._run_llm(repo_model, llm_config)
            except Exception as exc:
                self.logger.warning("LLM Report failed (%s), falling back", exc)

        return self._run_deterministic(repo_model)

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _run_llm(self, m: RepoKnowledgeModel, llm_config: dict[str, Any]) -> DraftDocument:
        from ..llm_client import chat_text

        # Build rich context for the LLM
        key_file_summary = ""
        for path, content in list(m.key_files.items())[:10]:
            key_file_summary += f"\n--- {path} ---\n{content[:400]}\n"

        deps_summary = ", ".join(list(m.dependencies.keys())[:20])

        context = (
            f"Project: {m.project_name}\n"
            f"Description: {m.description}\n"
            f"Problem: {m.problem_statement}\n"
            f"Tech Stack: {', '.join(m.tech_stack)}\n"
            f"Features: {chr(10).join('- ' + f for f in m.features[:15])}\n"
            f"Architecture: {chr(10).join('- ' + c for c in m.architecture_components[:10])}\n"
            f"Data Flow: {chr(10).join('- ' + d for d in m.data_flow[:10])}\n"
            f"File Count: {len(m.file_tree)}\n"
            f"Dependencies ({len(m.dependencies)}): {deps_summary}\n"
            f"CI/CD: {chr(10).join(m.ci_cd[:5])}\n"
            f"API Endpoints: {len(m.api_endpoints)}\n"
            f"Risks: {chr(10).join('- ' + r for r in m.risks[:10])}\n"
            f"Key Files:\n{key_file_summary}\n"
            f"Repository: {m.repo_url}\n"
        )

        system = (
            "You are a senior software engineer writing a comprehensive Technical Report. "
            "Write a detailed, well-structured report in Markdown. Include:\n"
            "1. Executive Overview (summary, stats, tech stack)\n"
            "2. Problem & Motivation (why this project exists)\n"
            "3. Architecture (components, data flow, project structure)\n"
            "4. Modules & Key Files (analysis of important source files)\n"
            "5. API Surface (endpoints table if applicable)\n"
            "6. Dependencies (key packages table)\n"
            "7. CI/CD & Deployment\n"
            "8. Risks & Considerations\n"
            "9. Recommendations (actionable improvements)\n\n"
            "Be deeply technical. Reference actual files, modules, and code patterns. "
            "Start with a # heading."
        )

        content = chat_text(system, context, **{**llm_config, "max_tokens": 6000})
        self.logger.info("LLM-generated Report: %d chars", len(content))

        sections = [line.lstrip("# ").strip() for line in content.splitlines()
                     if line.startswith("## ")]

        return DraftDocument(
            doc_type=DocumentType.REPORT,
            title=f"Technical Report — {m.project_name}",
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

        parts.append(f"# Technical Report — {m.project_name}\n")

        # --- Executive Summary ---
        sections.append("Overview")
        parts.append("## 1. Executive Overview\n")
        parts.append(f"{m.description}\n")
        parts.append(f"- **Repository:** {m.repo_url}")
        parts.append(f"- **Total Files:** {len(m.file_tree)}")
        parts.append(f"- **Dependencies:** {len(m.dependencies)}")
        parts.append(f"- **Technology Stack:** {', '.join(m.tech_stack) if m.tech_stack else 'N/A'}")
        parts.append("")

        # --- Problem & Motivation ---
        if m.problem_statement:
            parts.append("## 2. Problem & Motivation\n")
            parts.append(f"{m.problem_statement}\n")

        # --- Architecture ---
        sections.append("Architecture")
        parts.append("## 3. Architecture\n")

        if m.architecture_components:
            parts.append("### 3.1 Components\n")
            for comp in m.architecture_components:
                parts.append(f"- {comp}")
            parts.append("")

        if m.data_flow:
            parts.append("### 3.2 Data Flow\n")
            for i, step in enumerate(m.data_flow, 1):
                parts.append(f"{i}. {step}")
            parts.append("")

        # --- File structure ---
        parts.append("### 3.3 Project Structure\n")
        parts.append("```")
        # Show top-level dirs and key files
        shown: set[str] = set()
        for f in m.file_tree[:50]:
            top = f.split("/")[0] if "/" in f else f
            if top not in shown:
                suffix = "/" if "/" in f else ""
                parts.append(f"  {top}{suffix}")
                shown.add(top)
        parts.append("```\n")

        # --- Modules ---
        sections.append("Modules")
        parts.append("## 4. Modules & Key Files\n")
        if m.key_files:
            for path, summary in list(m.key_files.items())[:15]:
                parts.append(f"### `{path}`\n")
                parts.append(f"{summary[:300]}\n")
        else:
            parts.append("*Module details will be populated during deeper analysis.*\n")

        # --- API Surface ---
        if m.api_endpoints:
            parts.append("## 5. API Surface\n")
            parts.append("| Method | Endpoint | Source |")
            parts.append("|--------|----------|--------|")
            for ep in m.api_endpoints[:25]:
                parts.append(f"| `{ep.method}` | `{ep.path}` | {ep.description} |")
            parts.append("")

        # --- Dependencies ---
        if m.dependencies:
            parts.append("## 6. Dependencies\n")
            parts.append("| Package | Version |")
            parts.append("|---------|---------|")
            for pkg, ver in list(m.dependencies.items())[:30]:
                parts.append(f"| {pkg} | {ver} |")
            parts.append("")

        # --- CI/CD & Deployment ---
        if m.ci_cd or m.deployment_info:
            parts.append("## 7. CI/CD & Deployment\n")
            if m.ci_cd:
                parts.append("### CI/CD\n")
                for ci in m.ci_cd:
                    parts.append(f"- {ci}")
                parts.append("")
            if m.deployment_info:
                parts.append("### Deployment\n")
                for dep in m.deployment_info:
                    parts.append(f"- {dep}")
                parts.append("")

        # --- Risks ---
        sections.append("Risks")
        parts.append("## 8. Risks & Considerations\n")
        if m.risks:
            for r in m.risks:
                parts.append(f"- ⚠️ {r}")
        else:
            parts.append("- No critical risks identified from static analysis.")
        parts.append("")

        # --- Recommendations ---
        parts.append("## 9. Recommendations\n")
        parts.append("- Ensure test coverage exceeds 80%")
        parts.append("- Add CI/CD pipeline if not present" if not m.ci_cd else "- Maintain CI/CD pipeline health")
        parts.append("- Document all API endpoints with examples")
        parts.append("- Set up monitoring and alerting for production")
        parts.append("")

        content = "\n".join(parts)
        self.logger.info("Generated Report: %d chars", len(content))

        return DraftDocument(
            doc_type=DocumentType.REPORT,
            title=f"Technical Report — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )
