"""ReleaseNotesAgent — generate human-readable release notes from diffs.

Takes a ``DiffSummary`` + ``ImpactReport`` and produces structured
release notes suitable for changelogs, slide decks, and Confluence pages.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ...core.knowledge_graph import KnowledgeGraph
from ...core.models import DocumentModel
from .diff_agent import DiffSummary
from .impact_agent import ImpactReport


@dataclass
class ReleaseNote:
    """A single release note entry."""
    category: str  # added | changed | fixed | removed | security
    title: str
    description: str
    files: list[str] = field(default_factory=list)
    breaking: bool = False


@dataclass
class ReleaseNotes:
    """Structured release notes for a version bump."""
    version: str = ""
    date: str = ""
    summary: str = ""
    notes: list[ReleaseNote] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render as Keep-a-Changelog Markdown."""
        lines = [f"## [{self.version}] - {self.date}", ""]
        if self.summary:
            lines.append(self.summary)
            lines.append("")

        by_category: dict[str, list[ReleaseNote]] = {}
        for note in self.notes:
            by_category.setdefault(note.category.title(), []).append(note)

        for cat in ("Added", "Changed", "Fixed", "Removed", "Security"):
            if cat in by_category:
                lines.append(f"### {cat}")
                for n in by_category[cat]:
                    prefix = "**BREAKING** " if n.breaking else ""
                    lines.append(f"- {prefix}{n.title}: {n.description}")
                lines.append("")

        return "\n".join(lines)


class ReleaseNotesAgent(AgentBase):
    """Generates structured release notes from diff and impact data.

    The agent:
    1. Reads DiffSummary + ImpactReport from prior results.
    2. Groups changes by category (added/changed/fixed/removed).
    3. Generates human-readable titles and descriptions.
    4. Produces Markdown, slide content, and Confluence-ready HTML.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(role=AgentRole.EXECUTOR, model=model)

    async def run(
        self,
        *,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        document: DocumentModel | None = None,
        plan: AgentPlan | None = None,
        prior_results: list[AgentResult] | None = None,
        diff_summary: DiffSummary | None = None,
        impact_report: ImpactReport | None = None,
        version: str = "",
        **kwargs: Any,
    ) -> AgentResult:
        t0 = time.perf_counter()

        # Extract from prior results if not provided directly
        if diff_summary is None:
            diff_summary = self._extract_diff(prior_results)
        if impact_report is None:
            impact_report = self._extract_impact(prior_results)

        if diff_summary is None:
            return self._make_result(
                success=False,
                errors=["No DiffSummary available"],
            )

        notes = self._build_release_notes(
            diff_summary=diff_summary,
            impact_report=impact_report,
            version=version,
        )

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts={
                "release_notes_md": notes.to_markdown(),
                "release_notes_data": {
                    "version": notes.version,
                    "summary": notes.summary,
                    "note_count": len(notes.notes),
                    "categories": list({n.category for n in notes.notes}),
                },
            },
            duration_ms=duration,
        )

    # -- Internal -----------------------------------------------------------

    def _build_release_notes(
        self,
        *,
        diff_summary: DiffSummary,
        impact_report: ImpactReport | None,
        version: str,
    ) -> ReleaseNotes:
        """Build release notes from diff data.

        TODO: Use LLM to generate human-readable descriptions from
              file diffs and KG entity changes. Currently uses simple
              heuristics.
        """
        notes: list[ReleaseNote] = []
        from datetime import date

        for fd in diff_summary.file_diffs:
            if fd.status == "added":
                notes.append(ReleaseNote(
                    category="added",
                    title=f"New file: {fd.path}",
                    description=f"Added {fd.additions} lines",
                    files=[fd.path],
                ))
            elif fd.status == "deleted":
                notes.append(ReleaseNote(
                    category="removed",
                    title=f"Removed: {fd.path}",
                    description=f"Deleted {fd.deletions} lines",
                    files=[fd.path],
                ))
            elif fd.status == "modified":
                notes.append(ReleaseNote(
                    category="changed",
                    title=f"Updated: {fd.path}",
                    description=f"+{fd.additions}/-{fd.deletions} lines",
                    files=[fd.path],
                ))

        summary_parts = []
        if diff_summary.total_files:
            summary_parts.append(f"{diff_summary.total_files} files changed")
        if impact_report and impact_report.total_deltas:
            summary_parts.append(f"{impact_report.total_deltas} KG entities affected")

        return ReleaseNotes(
            version=version or "unreleased",
            date=date.today().isoformat(),
            summary=", ".join(summary_parts) if summary_parts else "No changes",
            notes=notes,
        )

    def _extract_diff(
        self, prior_results: list[AgentResult] | None
    ) -> DiffSummary | None:
        if not prior_results:
            return None
        for r in prior_results:
            ds = r.artifacts.get("diff_summary")
            if ds and isinstance(ds, dict):
                return DiffSummary(
                    base_ref=ds.get("base_ref", ""),
                    head_ref=ds.get("head_ref", ""),
                    total_files=ds.get("total_files", 0),
                )
        return None

    def _extract_impact(
        self, prior_results: list[AgentResult] | None
    ) -> ImpactReport | None:
        if not prior_results:
            return None
        for r in prior_results:
            ir = r.artifacts.get("impact_report")
            if ir and isinstance(ir, dict):
                return ImpactReport(
                    impacted_output_formats=ir.get("impacted_formats", []),
                    confidence=ir.get("confidence", 0.0),
                )
        return None
