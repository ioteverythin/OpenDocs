"""doc.changelog — Generate Changelog / Release Notes."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .base import BaseSkill
from ..models.repo_model import GitHistory, RepoKnowledgeModel
from ..models.document_model import DraftDocument, DocumentType


# PR title prefixes → category mapping
_CATEGORY_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)^feat|^add|^new|^implement", "✨ Features"),
    (r"(?i)^fix|^bug|^patch|^hotfix", "🐛 Bug Fixes"),
    (r"(?i)^refactor|^clean|^improve", "♻️ Refactors"),
    (r"(?i)^doc|^readme|^comment", "📝 Documentation"),
    (r"(?i)^test|^spec|^coverage", "🧪 Tests"),
    (r"(?i)^perf|^optim|^speed|^fast", "⚡ Performance"),
    (r"(?i)^ci|^build|^deploy|^release|^workflow", "🏗️ CI / Build"),
    (r"(?i)^dep|^bump|^upgrad|^update", "📦 Dependencies"),
    (r"(?i)^break|^remov|^deprecat", "⚠️ Breaking Changes"),
    (r"(?i)^sec|^vuln|^cve", "🔒 Security"),
    (r"(?i)^style|^lint|^format", "🎨 Style"),
    (r"(?i)^chore|^misc|^maint", "🔧 Chores"),
]


def _categorise_subject(subject: str) -> str:
    """Map a commit/PR subject line to an emoji category."""
    # Strip "Merge pull request #NNN from ..." prefix
    clean = re.sub(r"^Merge pull request #\d+ from \S+\s*", "", subject).strip()
    if not clean:
        clean = subject
    for pattern, category in _CATEGORY_PATTERNS:
        if re.search(pattern, clean):
            return category
    return "🔀 Other"


def _extract_pr_number(subject: str) -> str | None:
    """Try to extract '#123' from a merge commit subject."""
    m = re.search(r"#(\d+)", subject)
    return m.group(0) if m else None


class ChangelogSkill(BaseSkill):
    """Generate changelog / release notes from the repository knowledge model."""

    name = "doc.changelog"

    def run(self, *, repo_model: RepoKnowledgeModel, **kwargs: Any) -> DraftDocument:
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}
        has_history = repo_model.git_history and (
            repo_model.git_history.commits or repo_model.git_history.merges
        )

        if has_history:
            self.logger.info("Git history available — generating real changelog")
            if use_llm:
                try:
                    return self._run_history_llm(repo_model, llm_config)
                except Exception as exc:
                    self.logger.warning("LLM history changelog failed (%s), falling back", exc)
            return self._run_history_deterministic(repo_model)

        # Fallback: no git history → snapshot-based changelog (original behaviour)
        if use_llm:
            try:
                return self._run_llm(repo_model, llm_config)
            except Exception as exc:
                self.logger.warning("LLM Changelog failed (%s), falling back", exc)
        return self._run_deterministic(repo_model)

    # ==================================================================
    # History-based (real git data) — LLM path
    # ==================================================================

    def _run_history_llm(
        self, m: RepoKnowledgeModel, llm_config: dict[str, Any],
    ) -> DraftDocument:
        from ..llm_client import chat_text

        hist = m.git_history
        assert hist is not None

        # Build a structured summary of commits/merges for the LLM
        merge_lines = []
        for mg in hist.merges[:100]:
            pr = _extract_pr_number(mg.subject) or ""
            merge_lines.append(f"- [{mg.date[:10]}] {mg.subject} ({mg.author}) {pr}")

        commit_lines = []
        for c in hist.commits[:150]:
            commit_lines.append(f"- [{c.date[:10]}] {c.short} {c.subject} ({c.author})")

        tag_lines = [f"- {t['tag']} ({t.get('date', '')[:10]})" for t in hist.tags[:20]]

        contrib_lines = [
            f"- {c['author']}: {c['commits']} commits" for c in hist.contributors[:15]
        ]

        stats = hist.stats
        stats_summary = (
            f"Commits: {stats.get('commits', '?')}, "
            f"Files changed: {stats.get('files_changed', '?')}, "
            f"+{stats.get('insertions', '?')} / -{stats.get('deletions', '?')} lines"
        )

        period = f"{hist.since or 'beginning'} → {hist.until or 'now'}"

        context = (
            f"Project: {m.project_name}\n"
            f"Repository: {m.repo_url}\n"
            f"Period: {period}\n"
            f"Stats: {stats_summary}\n\n"
            f"## Merged Pull Requests / Merge Commits ({len(hist.merges)} total)\n"
            + "\n".join(merge_lines[:100]) + "\n\n"
            f"## All Commits ({len(hist.commits)} total, showing first 150)\n"
            + "\n".join(commit_lines[:150]) + "\n\n"
            f"## Tags / Releases ({len(hist.tags)} total)\n"
            + "\n".join(tag_lines) + "\n\n"
            f"## Contributors ({len(hist.contributors)})\n"
            + "\n".join(contrib_lines) + "\n"
        )

        system = (
            "You are a release manager writing a professional Changelog from REAL git history data.\n\n"
            "Analyse the merged PRs and commits and produce a structured Changelog in Markdown:\n\n"
            "1. **Release Header** — project name, period covered, date range\n"
            "2. **Summary Stats** — table with commits, files changed, insertions, deletions\n"
            "3. **Highlights** — 3-5 most impactful changes (from the merge list)\n"
            "4. **Changes by Category** — group each change into categories:\n"
            "   ✨ Features, 🐛 Bug Fixes, ♻️ Refactors, 📝 Documentation, "
            "🧪 Tests, ⚡ Performance, 🏗️ CI/Build, 📦 Dependencies, "
            "⚠️ Breaking Changes, 🔒 Security, 🔧 Chores\n"
            "   List the PR # when available.\n"
            "5. **Contributors** — list contributors with commit counts\n"
            "6. **Release Tags** — any tags/releases in this period\n\n"
            "Use the ACTUAL commit messages and PR titles — do NOT invent changes.\n"
            "If a section has no items, omit it. Be specific, cite real commit subjects.\n"
            "Start with a # heading."
        )

        content = chat_text(system, context, **{**llm_config, "max_tokens": 5000})
        self.logger.info("LLM history-based changelog: %d chars", len(content))

        sections = [line.lstrip("# ").strip() for line in content.splitlines()
                     if line.startswith("## ")]

        return DraftDocument(
            doc_type=DocumentType.CHANGELOG,
            title=f"Changelog — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )

    # ==================================================================
    # History-based — deterministic path
    # ==================================================================

    def _run_history_deterministic(self, repo_model: RepoKnowledgeModel) -> DraftDocument:
        m = repo_model
        hist = m.git_history
        assert hist is not None

        sections: list[str] = []
        parts: list[str] = []

        period = f"{hist.since or 'beginning'} → {hist.until or 'now'}"
        parts.append(f"# Changelog — {m.project_name}\n")
        parts.append(f"**Repository:** {m.repo_url}  ")
        parts.append(f"**Period:** {period}\n")

        # --- Summary Stats ---
        stats = hist.stats
        sections.append("Summary")
        parts.append("## 📊 Summary\n")
        parts.append("| Metric | Count |")
        parts.append("|--------|-------|")
        parts.append(f"| Total Commits | {stats.get('commits', 0)} |")
        parts.append(f"| Merged PRs | {len(hist.merges)} |")
        parts.append(f"| Files Changed | {stats.get('files_changed', 0)} |")
        parts.append(f"| Lines Added | +{stats.get('insertions', 0)} |")
        parts.append(f"| Lines Removed | -{stats.get('deletions', 0)} |")
        parts.append(f"| Contributors | {len(hist.contributors)} |")
        parts.append(f"| Tags/Releases | {len(hist.tags)} |")
        parts.append("")

        # --- Changes by Category ---
        # Use merges if available, otherwise all commits
        entries = hist.merges if hist.merges else hist.commits
        categorised: dict[str, list[str]] = defaultdict(list)
        for entry in entries:
            cat = _categorise_subject(entry.subject)
            pr_num = _extract_pr_number(entry.subject) or ""
            # Clean up merge commit subjects
            clean_subject = re.sub(
                r"^Merge pull request #\d+ from \S+\s*", "", entry.subject,
            ).strip() or entry.subject
            line = f"- {clean_subject}"
            if pr_num:
                line += f" ({pr_num})"
            line += f" — *{entry.author}, {entry.date[:10]}*"
            categorised[cat].append(line)

        sections.append("Changes")
        parts.append("## 📋 Changes\n")
        # Sort categories: features first, chores last
        priority = [
            "✨ Features", "🐛 Bug Fixes", "⚡ Performance", "🔒 Security",
            "⚠️ Breaking Changes", "♻️ Refactors", "📝 Documentation",
            "🧪 Tests", "🏗️ CI / Build", "📦 Dependencies",
            "🎨 Style", "🔧 Chores", "🔀 Other",
        ]
        for cat in priority:
            items = categorised.get(cat, [])
            if items:
                parts.append(f"### {cat}\n")
                parts.extend(items)
                parts.append("")

        # --- Top Contributors ---
        if hist.contributors:
            sections.append("Contributors")
            parts.append("## 👥 Contributors\n")
            parts.append("| Author | Commits |")
            parts.append("|--------|---------|")
            for c in hist.contributors:
                parts.append(f"| {c['author']} | {c['commits']} |")
            parts.append("")

        # --- Tags/Releases ---
        if hist.tags:
            sections.append("Releases")
            parts.append("## 🏷️ Tags & Releases\n")
            for t in hist.tags[:20]:
                parts.append(f"- **{t['tag']}** — {t.get('date', '')[:10]}  {t.get('subject', '')}")
            parts.append("")

        # --- Recent Commits (detail) ---
        if hist.commits:
            sections.append("Commit Log")
            parts.append("## 📝 Commit Log (recent)\n")
            parts.append("| Date | Hash | Author | Subject |")
            parts.append("|------|------|--------|---------|")
            for c in hist.commits[:50]:
                parts.append(
                    f"| {c.date[:10]} | `{c.short}` | {c.author} | {c.subject} |"
                )
            if len(hist.commits) > 50:
                parts.append(f"\n*...and {len(hist.commits) - 50} more commits*")
            parts.append("")

        content = "\n".join(parts)
        self.logger.info("Deterministic history changelog: %d chars", len(content))

        return DraftDocument(
            doc_type=DocumentType.CHANGELOG,
            title=f"Changelog — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------

    def _run_llm(self, m: RepoKnowledgeModel, llm_config: dict[str, Any]) -> DraftDocument:
        from ..llm_client import chat_text

        # Build rich context
        key_file_summary = ""
        for path, content in list(m.key_files.items())[:10]:
            key_file_summary += f"\n--- {path} ---\n{content[:400]}\n"

        deps_summary = ", ".join(f"{k} {v}" for k, v in list(m.dependencies.items())[:20])
        ci_summary = "\n".join(m.ci_cd[:5]) if m.ci_cd else "Not detected"

        context = (
            f"Project: {m.project_name}\n"
            f"Description: {m.description}\n"
            f"Tech Stack: {', '.join(m.tech_stack)}\n"
            f"Features: {chr(10).join('- ' + f for f in m.features[:15])}\n"
            f"Architecture: {chr(10).join('- ' + c for c in m.architecture_components[:10])}\n"
            f"API Endpoints: {len(m.api_endpoints)}\n"
            f"Dependencies ({len(m.dependencies)}): {deps_summary}\n"
            f"CI/CD: {ci_summary}\n"
            f"File Count: {len(m.file_tree)}\n"
            f"Key Files:\n{key_file_summary}\n"
            f"Repository: {m.repo_url}\n"
        )

        system = (
            "You are a release manager writing professional Release Notes / Changelog "
            "for a software project. Based on the repository analysis, write a comprehensive "
            "changelog in Markdown covering what this project offers. Structure it as:\n\n"
            "1. Release Header (project name, version tag if detectable, date)\n"
            "2. Highlights (3-5 bullet executive summary of the most impactful capabilities)\n"
            "3. Features (categorised: Core, API, Developer Experience, Performance, Security)\n"
            "4. Architecture & Infrastructure (what's under the hood)\n"
            "5. Dependencies & Compatibility (key deps, Python/Node version requirements)\n"
            "6. Breaking Changes / Migration Notes (anything that needs attention)\n"
            "7. Known Issues & Limitations\n"
            "8. What's Next (based on roadmap signals in the codebase)\n\n"
            "Use emoji prefixes: ✨ Features, 🏗️ Architecture, 📦 Dependencies, "
            "⚠️ Breaking, 🐛 Known Issues, 🔮 Roadmap.\n"
            "Be specific — reference actual modules, endpoints, and config. "
            "Write for PMs, developers, and stakeholders. Start with a # heading."
        )

        content = chat_text(system, context, **{**llm_config, "max_tokens": 5000})
        self.logger.info("LLM-generated Changelog: %d chars", len(content))

        sections = [line.lstrip("# ").strip() for line in content.splitlines()
                     if line.startswith("## ")]

        return DraftDocument(
            doc_type=DocumentType.CHANGELOG,
            title=f"Changelog — {m.project_name}",
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

        parts.append(f"# Changelog — {m.project_name}\n")

        # --- Release Header ---
        parts.append(f"**Repository:** {m.repo_url}\n")

        # --- Highlights ---
        sections.append("Highlights")
        parts.append("## ✨ Highlights\n")
        for feat in m.features[:5]:
            parts.append(f"- {feat}")
        if not m.features:
            parts.append("- Initial release")
        parts.append("")

        # --- Core Features ---
        sections.append("Features")
        parts.append("## 🚀 Features\n")

        if m.features:
            parts.append("### Core Capabilities\n")
            for feat in m.features:
                parts.append(f"- ✨ {feat}")
            parts.append("")

        if m.api_endpoints:
            parts.append("### API Surface\n")
            parts.append(f"- {len(m.api_endpoints)} endpoints available")
            for ep in m.api_endpoints[:10]:
                parts.append(f"  - `{ep.method} {ep.path}` — {ep.description}")
            parts.append("")

        # --- Architecture ---
        sections.append("Architecture")
        parts.append("## 🏗️ Architecture & Infrastructure\n")
        if m.architecture_components:
            for comp in m.architecture_components:
                parts.append(f"- {comp}")
        else:
            parts.append("- Standard project structure")
        parts.append("")

        if m.data_flow:
            parts.append("### Data Flow\n")
            for i, step in enumerate(m.data_flow, 1):
                parts.append(f"{i}. {step}")
            parts.append("")

        # --- Dependencies ---
        sections.append("Dependencies")
        parts.append("## 📦 Dependencies & Compatibility\n")
        if m.tech_stack:
            parts.append(f"**Tech Stack:** {', '.join(m.tech_stack)}\n")
        if m.dependencies:
            parts.append("| Package | Version |")
            parts.append("|---------|---------|")
            for pkg, ver in list(m.dependencies.items())[:20]:
                parts.append(f"| {pkg} | {ver} |")
        parts.append("")

        # --- CI/CD ---
        if m.ci_cd:
            parts.append("## ⚙️ CI/CD & Deployment\n")
            for ci in m.ci_cd:
                parts.append(f"- {ci}")
            parts.append("")

        # --- Known Issues ---
        sections.append("Known Issues")
        parts.append("## 🐛 Known Issues & Limitations\n")
        if m.risks:
            for r in m.risks:
                parts.append(f"- ⚠️ {r}")
        else:
            parts.append("- No critical issues identified.")
        parts.append("")

        # --- Roadmap ---
        if m.roadmap:
            sections.append("Roadmap")
            parts.append("## 🔮 What's Next\n")
            for item in m.roadmap:
                parts.append(f"- {item}")
            parts.append("")

        content = "\n".join(parts)
        self.logger.info("Generated Changelog: %d chars", len(content))

        return DraftDocument(
            doc_type=DocumentType.CHANGELOG,
            title=f"Changelog — {m.project_name}",
            content=content,
            version=1,
            sections=sections,
        )
