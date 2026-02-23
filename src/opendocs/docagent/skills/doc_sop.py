"""doc.sop — Generate a Standard Operating Procedure document."""

from __future__ import annotations

from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel
from ..models.document_model import DraftDocument, DocumentType


class SOPSkill(BaseSkill):
    """Generate an SOP from the repository knowledge model."""

    name = "doc.sop"

    def run(self, *, repo_model: RepoKnowledgeModel, **kwargs: Any) -> DraftDocument:
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        if use_llm:
            try:
                return self._run_llm(repo_model, llm_config)
            except Exception as exc:
                self.logger.warning("LLM SOP failed (%s), falling back", exc)

        return self._run_deterministic(repo_model)

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _run_llm(self, m: RepoKnowledgeModel, llm_config: dict[str, Any]) -> DraftDocument:
        from ..llm_client import chat_text

        context = (
            f"Project: {m.project_name}\n"
            f"Description: {m.description}\n"
            f"Tech Stack: {', '.join(m.tech_stack)}\n"
            f"Setup Instructions: {chr(10).join(m.setup_instructions[:10])}\n"
            f"CI/CD: {chr(10).join(m.ci_cd[:5])}\n"
            f"Deployment: {chr(10).join(m.deployment_info[:5])}\n"
            f"API Endpoints: {len(m.api_endpoints)}\n"
            f"Dependencies: {len(m.dependencies)} packages\n"
            f"Repository: {m.repo_url}\n"
        )

        system = (
            "You are a DevOps engineer writing a Standard Operating Procedure (SOP). "
            "Write a comprehensive, step-by-step SOP in Markdown. Include:\n"
            "1. Setup & Prerequisites (required tools, installation steps)\n"
            "2. Environment Configuration (env vars, config files)\n"
            "3. Run Instructions (dev mode, production mode)\n"
            "4. Deployment (step-by-step deployment procedure, CI/CD)\n"
            "5. Monitoring (health checks, logs, alerts)\n"
            "6. Troubleshooting (common issues table, log locations)\n"
            "7. Rollback Procedures\n\n"
            "Include actual bash commands where appropriate. "
            "Be specific to THIS project's tech stack. Start with a # heading."
        )

        content = chat_text(system, context, **llm_config)
        self.logger.info("LLM-generated SOP: %d chars", len(content))

        sections = [line.lstrip("# ").strip() for line in content.splitlines()
                     if line.startswith("## ")]

        return DraftDocument(
            doc_type=DocumentType.SOP,
            title=f"SOP — {m.project_name}",
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

        parts.append(f"# Standard Operating Procedure — {m.project_name}\n")

        # --- Setup ---
        sections.append("Setup")
        parts.append("## 1. Setup & Prerequisites\n")
        parts.append("### Prerequisites\n")
        if m.tech_stack:
            for tech in m.tech_stack[:8]:
                parts.append(f"- {tech} installed and configured")
        parts.append("")
        parts.append("### Installation\n")
        if m.setup_instructions:
            parts.append("```bash")
            for cmd in m.setup_instructions:
                parts.append(cmd)
            parts.append("```\n")
        else:
            parts.append("```bash")
            parts.append(f"git clone {m.repo_url}")
            parts.append(f"cd {m.project_name}")
            if "Python" in m.tech_stack:
                parts.append("pip install -r requirements.txt")
            if "Node.js" in m.tech_stack:
                parts.append("npm install")
            parts.append("```\n")

        # --- Environment Configuration ---
        parts.append("### Environment Configuration\n")
        parts.append("1. Copy the example environment file (if available)")
        parts.append("2. Set required environment variables")
        parts.append("3. Verify database/service connections\n")

        # --- Run Instructions ---
        sections.append("Run Instructions")
        parts.append("## 2. Run Instructions\n")
        parts.append("### Development Mode\n")
        if "Python" in m.tech_stack:
            if "FastAPI" in m.tech_stack:
                parts.append("```bash\nuvicorn app.main:app --reload\n```\n")
            elif "Django" in m.tech_stack:
                parts.append("```bash\npython manage.py runserver\n```\n")
            elif "Flask" in m.tech_stack:
                parts.append("```bash\nflask run --debug\n```\n")
            else:
                parts.append("```bash\npython main.py\n```\n")
        if "Node.js" in m.tech_stack:
            parts.append("```bash\nnpm run dev\n```\n")

        parts.append("### Production Mode\n")
        if "Docker" in m.tech_stack:
            parts.append("```bash\ndocker-compose up -d\n```\n")
        else:
            parts.append("*Refer to deployment section for production setup.*\n")

        # --- Deployment ---
        sections.append("Deployment")
        parts.append("## 3. Deployment\n")
        if m.deployment_info:
            for info in m.deployment_info:
                parts.append(f"- {info}")
            parts.append("")
        else:
            parts.append("### Deployment Steps\n")
            parts.append("1. Build the application for production")
            parts.append("2. Run tests to verify build integrity")
            parts.append("3. Deploy to target environment")
            parts.append("4. Verify deployment health checks\n")

        if m.ci_cd:
            parts.append("### CI/CD Pipeline\n")
            for ci in m.ci_cd:
                parts.append(f"- {ci}")
            parts.append("")

        # --- Monitoring ---
        sections.append("Monitoring")
        parts.append("## 4. Monitoring\n")
        parts.append("### Health Checks\n")
        if m.api_endpoints:
            parts.append("- Verify API endpoints are responding")
        parts.append("- Monitor application logs for errors")
        parts.append("- Check resource utilisation (CPU, memory, disk)")
        parts.append("- Set up alerts for critical failures\n")

        # --- Troubleshooting ---
        sections.append("Troubleshooting")
        parts.append("## 5. Troubleshooting\n")
        parts.append("### Common Issues\n")
        parts.append("| Issue | Possible Cause | Resolution |")
        parts.append("|-------|---------------|------------|")
        parts.append("| Application won't start | Missing dependencies | Re-run install commands |")
        parts.append("| Connection refused | Service not running | Check service status |")
        parts.append("| Build failure | Incompatible versions | Verify dependency versions |")
        if "Docker" in m.tech_stack:
            parts.append("| Container crash | Resource limits | Increase Docker resource allocation |")
        parts.append("")

        parts.append("### Log Locations\n")
        parts.append("- Application logs: `./logs/` or stdout")
        if "Docker" in m.tech_stack:
            parts.append("- Container logs: `docker logs <container>`")
        parts.append("")

        content = "\n".join(parts)
        self.logger.info("Generated SOP: %d chars", len(content))

        return DraftDocument(
            doc_type=DocumentType.SOP,
            title=f"SOP — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )
