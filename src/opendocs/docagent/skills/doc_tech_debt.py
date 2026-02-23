"""doc.tech_debt — Generate a Tech Debt Assessment Report."""

from __future__ import annotations

from typing import Any

from .base import BaseSkill
from ..models.repo_model import RepoKnowledgeModel
from ..models.document_model import DraftDocument, DocumentType


class TechDebtSkill(BaseSkill):
    """Generate a comprehensive tech debt assessment report."""

    name = "doc.tech_debt"

    def run(self, *, repo_model: RepoKnowledgeModel, **kwargs: Any) -> DraftDocument:
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        if use_llm:
            try:
                return self._run_llm(repo_model, llm_config)
            except Exception as exc:
                self.logger.warning("LLM Tech Debt failed (%s), falling back", exc)

        return self._run_deterministic(repo_model)

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _run_llm(self, m: RepoKnowledgeModel, llm_config: dict[str, Any]) -> DraftDocument:
        from ..llm_client import chat_text

        # Build rich context with signals the LLM can analyze for debt
        key_file_summary = ""
        for path, content in list(m.key_files.items())[:15]:
            key_file_summary += f"\n--- {path} ---\n{content[:500]}\n"

        deps_summary = "\n".join(
            f"- {k}: {v}" for k, v in list(m.dependencies.items())[:30]
        )

        # Compute basic structural signals
        file_count = len(m.file_tree)
        test_files = [f for f in m.file_tree if "test" in f.lower()]
        config_files = [f for f in m.file_tree if any(
            f.endswith(ext) for ext in [".yml", ".yaml", ".toml", ".cfg", ".ini", ".json"]
        ) and not f.startswith(".git")]
        doc_files = [f for f in m.file_tree if any(
            f.lower().endswith(ext) for ext in [".md", ".rst", ".txt"]
        )]

        structural_signals = (
            f"Total files: {file_count}\n"
            f"Test files: {len(test_files)} ({100*len(test_files)/max(file_count,1):.0f}%)\n"
            f"Config files: {len(config_files)}\n"
            f"Documentation files: {len(doc_files)}\n"
            f"Has CI/CD: {'Yes' if m.ci_cd else 'No'}\n"
            f"Has deployment config: {'Yes' if m.deployment_info else 'No'}\n"
            f"Test file paths: {chr(10).join(test_files[:10])}\n"
        )

        context = (
            f"Project: {m.project_name}\n"
            f"Description: {m.description}\n"
            f"Tech Stack: {', '.join(m.tech_stack)}\n"
            f"Features: {chr(10).join('- ' + f for f in m.features[:10])}\n"
            f"Architecture: {chr(10).join('- ' + c for c in m.architecture_components[:10])}\n"
            f"Risks already identified: {chr(10).join('- ' + r for r in m.risks[:10])}\n"
            f"\n=== STRUCTURAL SIGNALS ===\n{structural_signals}\n"
            f"\n=== DEPENDENCIES ===\n{deps_summary}\n"
            f"\n=== CI/CD ===\n{chr(10).join(m.ci_cd[:5]) or 'None detected'}\n"
            f"\n=== KEY FILES ===\n{key_file_summary}\n"
            f"Repository: {m.repo_url}\n"
        )

        system = (
            "You are a senior software architect conducting a Tech Debt Assessment for a "
            "CTO/VP Engineering audience. Analyse the repository data and produce a "
            "comprehensive, actionable report in Markdown. Include:\n\n"
            "1. Executive Summary (overall health score 1-10, top 3 debt areas, risk level)\n"
            "2. Health Scorecard (table with dimensions: Testing, Documentation, Dependencies, "
            "   Architecture, Security, CI/CD, Code Quality — each scored 1-5 with rationale)\n"
            "3. Dependency Health (outdated/deprecated deps, version pinning, vulnerability signals, "
            "   licence risks, transitive dependency concerns)\n"
            "4. Testing & Quality Gaps (test coverage ratio, missing test types, areas without tests)\n"
            "5. Architecture Debt (tight coupling signals, missing abstractions, monolith patterns, "
            "   God classes/modules, circular dependencies)\n"
            "6. Documentation Debt (missing docs, stale docs, undocumented APIs)\n"
            "7. CI/CD & DevOps Debt (missing pipelines, manual processes, deployment risks)\n"
            "8. Security Considerations (dependency vulnerabilities, missing auth patterns, "
            "   hardcoded secrets signals, OWASP concerns)\n"
            "9. Prioritised Remediation Roadmap (table with: Issue, Severity, Effort, Impact, "
            "   Recommended Timeline — sorted by ROI)\n"
            "10. Cost Estimation (rough effort in dev-days for top remediation items)\n"
            "11. Recommendations for Leadership (strategic decisions, build vs buy, "
            "    team capacity implications)\n\n"
            "Be brutally honest but constructive. Use data from the repo to back up claims. "
            "Avoid generic advice — be specific to THIS codebase. "
            "Use 🟢 🟡 🔴 indicators for health scores. Start with a # heading."
        )

        content = chat_text(system, context, **{**llm_config, "max_tokens": 6000})
        self.logger.info("LLM-generated Tech Debt Report: %d chars", len(content))

        sections = [line.lstrip("# ").strip() for line in content.splitlines()
                     if line.startswith("## ")]

        return DraftDocument(
            doc_type=DocumentType.TECH_DEBT,
            title=f"Tech Debt Assessment — {m.project_name}",
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

        file_count = len(m.file_tree)
        test_files = [f for f in m.file_tree if "test" in f.lower()]
        test_ratio = len(test_files) / max(file_count, 1) * 100
        has_ci = bool(m.ci_cd)
        has_deploy = bool(m.deployment_info)
        dep_count = len(m.dependencies)

        # Compute simple health scores
        def _score_testing() -> tuple[int, str]:
            if test_ratio >= 20:
                return 4, "Good test coverage ratio"
            if test_ratio >= 10:
                return 3, "Moderate test coverage"
            if test_ratio > 0:
                return 2, "Limited test coverage"
            return 1, "No test files detected"

        def _score_ci() -> tuple[int, str]:
            if has_ci and has_deploy:
                return 5, "CI/CD + deployment configured"
            if has_ci:
                return 3, "CI present but no deployment config"
            return 1, "No CI/CD detected"

        def _score_docs() -> tuple[int, str]:
            doc_files = [f for f in m.file_tree if f.lower().endswith((".md", ".rst"))]
            if len(doc_files) >= 5:
                return 4, f"{len(doc_files)} documentation files"
            if len(doc_files) >= 2:
                return 3, f"{len(doc_files)} documentation files"
            return 1, "Minimal documentation"

        def _score_deps() -> tuple[int, str]:
            if dep_count == 0:
                return 3, "No dependencies detected (or self-contained)"
            if dep_count > 50:
                return 2, f"{dep_count} dependencies — potential supply chain risk"
            return 4, f"{dep_count} dependencies — manageable"

        def _score_arch() -> tuple[int, str]:
            if m.architecture_components and len(m.architecture_components) >= 3:
                return 4, "Clear component architecture"
            if m.architecture_components:
                return 3, "Basic architecture detected"
            return 2, "Architecture not clearly defined"

        def _indicator(score: int) -> str:
            if score >= 4:
                return "🟢"
            if score >= 3:
                return "🟡"
            return "🔴"

        test_score, test_note = _score_testing()
        ci_score, ci_note = _score_ci()
        doc_score, doc_note = _score_docs()
        dep_score, dep_note = _score_deps()
        arch_score, arch_note = _score_arch()
        overall = (test_score + ci_score + doc_score + dep_score + arch_score) / 5

        parts.append(f"# Tech Debt Assessment — {m.project_name}\n")

        # --- Executive Summary ---
        sections.append("Executive Summary")
        parts.append("## Executive Summary\n")
        overall_indicator = "🟢" if overall >= 3.5 else ("🟡" if overall >= 2.5 else "🔴")
        parts.append(f"**Overall Health Score:** {overall_indicator} {overall:.1f} / 5.0\n")
        parts.append(f"**Repository:** {m.repo_url}")
        parts.append(f"**Total Files:** {file_count}")
        parts.append(f"**Dependencies:** {dep_count}")
        parts.append(f"**Test Files:** {len(test_files)} ({test_ratio:.0f}% of total)")
        parts.append("")

        # --- Health Scorecard ---
        sections.append("Health Scorecard")
        parts.append("## Health Scorecard\n")
        parts.append("| Dimension | Score | Status | Notes |")
        parts.append("|-----------|-------|--------|-------|")
        parts.append(f"| Testing | {test_score}/5 | {_indicator(test_score)} | {test_note} |")
        parts.append(f"| CI/CD | {ci_score}/5 | {_indicator(ci_score)} | {ci_note} |")
        parts.append(f"| Documentation | {doc_score}/5 | {_indicator(doc_score)} | {doc_note} |")
        parts.append(f"| Dependencies | {dep_score}/5 | {_indicator(dep_score)} | {dep_note} |")
        parts.append(f"| Architecture | {arch_score}/5 | {_indicator(arch_score)} | {arch_note} |")
        parts.append("")

        # --- Dependency Health ---
        sections.append("Dependency Health")
        parts.append("## 📦 Dependency Health\n")
        if m.dependencies:
            parts.append(f"**{dep_count} dependencies** detected:\n")
            parts.append("| Package | Version | Notes |")
            parts.append("|---------|---------|-------|")
            for pkg, ver in list(m.dependencies.items())[:30]:
                note = "⚠️ Unpinned" if ver in ("*", "latest", "") else "✅"
                parts.append(f"| {pkg} | {ver or 'unspecified'} | {note} |")
        else:
            parts.append("No dependencies detected from static analysis.\n")
        parts.append("")

        # --- Testing Gaps ---
        sections.append("Testing Gaps")
        parts.append("## 🧪 Testing & Quality Gaps\n")
        parts.append(f"- **Test file count:** {len(test_files)}")
        parts.append(f"- **Test/total ratio:** {test_ratio:.1f}%")
        if test_files:
            parts.append("\n**Test files found:**\n")
            for tf in test_files[:15]:
                parts.append(f"- `{tf}`")
        else:
            parts.append("\n⚠️ **No test files detected.** This is a critical gap.\n")
        parts.append("")

        # --- Architecture Debt ---
        sections.append("Architecture Debt")
        parts.append("## 🏗️ Architecture Debt\n")
        if m.architecture_components:
            parts.append("**Detected components:**\n")
            for comp in m.architecture_components:
                parts.append(f"- {comp}")
        else:
            parts.append("⚠️ No clear architecture components detected — may indicate a "
                         "monolithic or poorly structured codebase.\n")
        parts.append("")

        # --- CI/CD Debt ---
        sections.append("CI/CD Debt")
        parts.append("## ⚙️ CI/CD & DevOps Debt\n")
        if m.ci_cd:
            parts.append("**Detected CI/CD:**\n")
            for ci in m.ci_cd:
                parts.append(f"- ✅ {ci}")
        else:
            parts.append("🔴 **No CI/CD pipeline detected.**\n")
            parts.append("Recommendation: Set up automated testing and deployment.\n")
        if not m.deployment_info:
            parts.append("⚠️ No deployment configuration detected.\n")
        parts.append("")

        # --- Risks ---
        sections.append("Risks")
        parts.append("## ⚠️ Risks & Security Considerations\n")
        if m.risks:
            for r in m.risks:
                parts.append(f"- 🔴 {r}")
        else:
            parts.append("- No critical risks identified from static analysis.")
        parts.append("")

        # --- Remediation Roadmap ---
        sections.append("Remediation Roadmap")
        parts.append("## 🗺️ Prioritised Remediation Roadmap\n")
        parts.append("| # | Issue | Severity | Effort | Impact | Timeline |")
        parts.append("|---|-------|----------|--------|--------|----------|")
        row = 1
        if not test_files:
            parts.append(f"| {row} | Add test suite | 🔴 Critical | 5-10 days | High | Sprint 1 |")
            row += 1
        elif test_ratio < 10:
            parts.append(f"| {row} | Increase test coverage | 🟡 Medium | 3-5 days | High | Sprint 1-2 |")
            row += 1
        if not has_ci:
            parts.append(f"| {row} | Set up CI/CD pipeline | 🔴 Critical | 2-3 days | High | Sprint 1 |")
            row += 1
        if not has_deploy:
            parts.append(f"| {row} | Add deployment config | 🟡 Medium | 1-2 days | Medium | Sprint 2 |")
            row += 1
        for r in m.risks[:3]:
            parts.append(f"| {row} | {r[:60]} | 🟡 Medium | 2-3 days | Medium | Sprint 2-3 |")
            row += 1
        parts.append("")

        # --- Recommendations ---
        sections.append("Recommendations")
        parts.append("## 💡 Recommendations for Leadership\n")
        parts.append("1. **Invest in testing** — Every untested module is a deployment risk")
        parts.append("2. **Automate CI/CD** — Manual deployments are error-prone and slow")
        parts.append("3. **Pin dependencies** — Unpinned deps lead to surprise breakages")
        parts.append("4. **Document architecture decisions** — Future devs will thank you")
        parts.append("5. **Schedule regular tech debt sprints** — Allocate 20% of capacity")
        parts.append("")

        content = "\n".join(parts)
        self.logger.info("Generated Tech Debt Report: %d chars", len(content))

        return DraftDocument(
            doc_type=DocumentType.TECH_DEBT,
            title=f"Tech Debt Assessment — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )
