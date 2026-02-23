"""DiffAgent — detect code changes between two commits.

Takes a base and head commit SHA (or branch names), runs ``git diff``,
and produces a structured summary of which files changed and how.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ...core.knowledge_graph import KnowledgeGraph
from ...core.models import DocumentModel


@dataclass
class FileDiff:
    """Structured representation of a single file's diff."""

    path: str
    status: str  # added | modified | deleted | renamed
    additions: int = 0
    deletions: int = 0
    old_path: str | None = None  # for renames
    hunks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DiffSummary:
    """Aggregated diff between two commits."""

    base_ref: str
    head_ref: str
    total_files: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    file_diffs: list[FileDiff] = field(default_factory=list)

    @property
    def changed_paths(self) -> list[str]:
        return [fd.path for fd in self.file_diffs]


class DiffAgent(AgentBase):
    """Analyses git diff between two refs and produces a ``DiffSummary``.

    This is the first step in the diff-aware pipeline:
    1. DiffAgent produces the raw diff summary.
    2. ImpactAgent maps file changes to KG deltas.
    3. RegenerationAgent rebuilds impacted artifacts.
    4. ReleaseNotesAgent writes the changelog.
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
        base_ref: str = "HEAD~1",
        head_ref: str = "HEAD",
        **kwargs: Any,
    ) -> AgentResult:
        t0 = time.perf_counter()

        # Use repo.diff tool to get the diff
        diff_summary = await self._compute_diff(
            repo_url=repo_profile.repo_url,
            base_ref=base_ref,
            head_ref=head_ref,
        )

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts={
                "diff_summary": {
                    "base_ref": diff_summary.base_ref,
                    "head_ref": diff_summary.head_ref,
                    "total_files": diff_summary.total_files,
                    "total_additions": diff_summary.total_additions,
                    "total_deletions": diff_summary.total_deletions,
                    "changed_paths": diff_summary.changed_paths,
                    "file_diffs": [
                        {
                            "path": fd.path,
                            "status": fd.status,
                            "additions": fd.additions,
                            "deletions": fd.deletions,
                        }
                        for fd in diff_summary.file_diffs
                    ],
                }
            },
            duration_ms=duration,
        )

    async def _compute_diff(
        self,
        repo_url: str,
        base_ref: str,
        head_ref: str,
    ) -> DiffSummary:
        """Compute diff between two refs.

        TODO: Execute ``repo.diff`` tool via executor adapter.
              Currently returns a placeholder.
        """
        # Placeholder — will be replaced by actual git diff execution
        return DiffSummary(
            base_ref=base_ref,
            head_ref=head_ref,
            total_files=0,
            total_additions=0,
            total_deletions=0,
            file_diffs=[],
        )
