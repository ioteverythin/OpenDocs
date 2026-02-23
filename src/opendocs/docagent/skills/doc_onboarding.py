"""doc.onboarding — Generate a Developer Onboarding Pack."""

from __future__ import annotations

from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel
from ..models.document_model import DraftDocument, DocumentType


class OnboardingSkill(BaseSkill):
    """Generate a comprehensive developer onboarding guide."""

    name = "doc.onboarding"

    def run(self, *, repo_model: RepoKnowledgeModel, **kwargs: Any) -> DraftDocument:
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        if use_llm:
            try:
                return self._run_llm(repo_model, llm_config)
            except Exception as exc:
                self.logger.warning("LLM Onboarding failed (%s), falling back", exc)

        return self._run_deterministic(repo_model)

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _run_llm(self, m: RepoKnowledgeModel, llm_config: dict[str, Any]) -> DraftDocument:
        from ..llm_client import chat_text

        # Build rich context for the LLM
        key_file_summary = ""
        for path, content in list(m.key_files.items())[:15]:
            key_file_summary += f"\n--- {path} ---\n{content[:500]}\n"

        deps_summary = ", ".join(f"{k} {v}" for k, v in list(m.dependencies.items())[:25])
        setup_summary = "\n".join(f"- {s}" for s in m.setup_instructions[:10]) if m.setup_instructions else "Not detected"

        # Categorise files for the "read these first" section
        file_tree_sample = "\n".join(m.file_tree[:60])

        context = (
            f"Project: {m.project_name}\n"
            f"Description: {m.description}\n"
            f"Problem: {m.problem_statement}\n"
            f"Tech Stack: {', '.join(m.tech_stack)}\n"
            f"Features: {chr(10).join('- ' + f for f in m.features[:15])}\n"
            f"Architecture: {chr(10).join('- ' + c for c in m.architecture_components[:10])}\n"
            f"Data Flow: {chr(10).join('- ' + d for d in m.data_flow[:10])}\n"
            f"Setup Instructions: {setup_summary}\n"
            f"Dependencies ({len(m.dependencies)}): {deps_summary}\n"
            f"CI/CD: {chr(10).join(m.ci_cd[:5])}\n"
            f"Deployment: {chr(10).join(m.deployment_info[:5])}\n"
            f"API Endpoints: {len(m.api_endpoints)}\n"
            f"File Count: {len(m.file_tree)}\n"
            f"File Tree (first 60):\n{file_tree_sample}\n"
            f"Key Files:\n{key_file_summary}\n"
            f"Repository: {m.repo_url}\n"
        )

        system = (
            "You are a senior engineering manager writing a Developer Onboarding Pack for "
            "new team members joining this project. Write a comprehensive, welcoming, and "
            "practical guide in Markdown. Include:\n\n"
            "1. Welcome & Project Overview (what this is, why it matters, who uses it)\n"
            "2. Architecture at a Glance (high-level architecture with component descriptions)\n"
            "3. Getting Started (prerequisites, environment setup, first run — step-by-step)\n"
            "4. Repository Structure (annotated directory tree — what lives where)\n"
            "5. Key Files to Read First (the 5-10 most important files a new dev should read, "
            "   with WHY each one matters)\n"
            "6. Development Workflow (branching strategy, PR process, code review, testing)\n"
            "7. Coding Conventions & Patterns (detected patterns, naming conventions, "
            "   design patterns used)\n"
            "8. API Quick Reference (if applicable, summarise key endpoints)\n"
            "9. Common Tasks (how to add a new feature, fix a bug, run tests, deploy)\n"
            "10. Glossary (domain-specific terms and abbreviations)\n"
            "11. FAQ (common questions new devs ask)\n"
            "12. Resources & Links (docs, Slack channels, dashboards, CI/CD links)\n\n"
            "Tone: friendly, practical, assume smart engineers who are new to THIS codebase. "
            "Use actual file paths, module names, and code patterns from the repo. "
            "Include checkboxes for setup steps. Start with a # heading."
        )

        content = chat_text(system, context, **{**llm_config, "max_tokens": 6000})
        self.logger.info("LLM-generated Onboarding Pack: %d chars", len(content))

        sections = [line.lstrip("# ").strip() for line in content.splitlines()
                     if line.startswith("## ")]

        return DraftDocument(
            doc_type=DocumentType.ONBOARDING,
            title=f"Developer Onboarding — {m.project_name}",
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

        parts.append(f"# Developer Onboarding Pack — {m.project_name}\n")

        # --- Welcome ---
        sections.append("Welcome")
        parts.append("## 👋 Welcome & Project Overview\n")
        parts.append(f"Welcome to **{m.project_name}**!\n")
        parts.append(f"{m.description}\n")
        parts.append(f"**Repository:** {m.repo_url}\n")
        if m.target_users:
            parts.append(f"**Users:** {', '.join(m.target_users)}\n")
        parts.append("")

        # --- Architecture ---
        sections.append("Architecture")
        parts.append("## 🏗️ Architecture at a Glance\n")
        if m.tech_stack:
            parts.append(f"**Tech Stack:** {', '.join(m.tech_stack)}\n")
        if m.architecture_components:
            for comp in m.architecture_components:
                parts.append(f"- {comp}")
            parts.append("")
        if m.data_flow:
            parts.append("### Data Flow\n")
            for i, step in enumerate(m.data_flow, 1):
                parts.append(f"{i}. {step}")
            parts.append("")

        # --- Getting Started ---
        sections.append("Getting Started")
        parts.append("## 🚀 Getting Started\n")
        parts.append("### Prerequisites\n")
        if m.tech_stack:
            for tech in m.tech_stack[:5]:
                parts.append(f"- [ ] {tech} installed")
        parts.append("")

        parts.append("### Setup Steps\n")
        if m.setup_instructions:
            for i, step in enumerate(m.setup_instructions, 1):
                parts.append(f"{i}. {step}")
        else:
            parts.append("1. Clone the repository:")
            parts.append(f"   ```bash\n   git clone {m.repo_url}\n   cd {m.project_name}\n   ```")
            parts.append("2. Install dependencies (check `requirements.txt` or `package.json`)")
            parts.append("3. Run the project (check `README.md` for run commands)")
        parts.append("")

        # --- Repository Structure ---
        sections.append("Repository Structure")
        parts.append("## 📁 Repository Structure\n")
        parts.append("```")
        shown: set[str] = set()
        for f in m.file_tree[:80]:
            top = f.split("/")[0] if "/" in f else f
            if top not in shown:
                suffix = "/" if "/" in f else ""
                parts.append(f"  {top}{suffix}")
                shown.add(top)
        parts.append("```\n")

        # --- Key Files ---
        sections.append("Key Files")
        parts.append("## 📖 Key Files to Read First\n")
        parts.append("Start your code exploration here:\n")
        priority_files = [
            "README.md", "CONTRIBUTING.md", "setup.py", "pyproject.toml",
            "package.json", "Makefile", "Dockerfile", "docker-compose.yml",
        ]
        shown_keys: set[str] = set()
        for pf in priority_files:
            for path in m.key_files:
                if path.endswith(pf) and path not in shown_keys:
                    shown_keys.add(path)
                    parts.append(f"### `{path}`\n")
                    summary = m.key_files[path][:300]
                    parts.append(f"{summary}\n")
        # Add remaining key files
        for path, summary in list(m.key_files.items())[:10]:
            if path not in shown_keys:
                shown_keys.add(path)
                parts.append(f"### `{path}`\n")
                parts.append(f"{summary[:300]}\n")
        parts.append("")

        # --- Development Workflow ---
        sections.append("Development Workflow")
        parts.append("## 🔄 Development Workflow\n")
        parts.append("1. Create a feature branch from `main`")
        parts.append("2. Make changes with clear, atomic commits")
        parts.append("3. Run tests locally before pushing")
        parts.append("4. Open a Pull Request with a clear description")
        parts.append("5. Address code review feedback")
        parts.append("6. Merge after approval + CI passes")
        parts.append("")

        if m.ci_cd:
            parts.append("### CI/CD\n")
            for ci in m.ci_cd:
                parts.append(f"- {ci}")
            parts.append("")

        # --- Dependencies ---
        if m.dependencies:
            sections.append("Dependencies")
            parts.append("## 📦 Dependencies\n")
            parts.append("| Package | Version |")
            parts.append("|---------|---------|")
            for pkg, ver in list(m.dependencies.items())[:25]:
                parts.append(f"| {pkg} | {ver} |")
            parts.append("")

        # --- API Reference ---
        if m.api_endpoints:
            sections.append("API Reference")
            parts.append("## 🔌 API Quick Reference\n")
            parts.append("| Method | Endpoint | Description |")
            parts.append("|--------|----------|-------------|")
            for ep in m.api_endpoints[:20]:
                parts.append(f"| `{ep.method}` | `{ep.path}` | {ep.description} |")
            parts.append("")

        # --- Common Tasks ---
        sections.append("Common Tasks")
        parts.append("## 🛠️ Common Tasks\n")
        parts.append("### Adding a New Feature\n")
        parts.append("1. Understand the relevant module in the codebase")
        parts.append("2. Write tests first (TDD approach recommended)")
        parts.append("3. Implement the feature")
        parts.append("4. Update documentation if needed")
        parts.append("5. Open a PR\n")
        parts.append("### Running Tests\n")
        parts.append("```bash\n# Check README.md or Makefile for project-specific test commands\n```\n")

        # --- Glossary ---
        sections.append("Glossary")
        parts.append("## 📚 Glossary\n")
        if m.tech_stack:
            for tech in m.tech_stack:
                parts.append(f"- **{tech}** — Part of the project's technology stack")
        parts.append("")

        # --- Resources ---
        sections.append("Resources")
        parts.append("## 🔗 Resources & Links\n")
        parts.append(f"- **Repository:** {m.repo_url}")
        parts.append(f"- **Branch:** `{m.default_branch}`")
        parts.append("")

        content = "\n".join(parts)
        self.logger.info("Generated Onboarding Pack: %d chars", len(content))

        return DraftDocument(
            doc_type=DocumentType.ONBOARDING,
            title=f"Developer Onboarding — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )
