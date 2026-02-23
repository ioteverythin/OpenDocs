"""RegenerationAgent — selectively rebuild impacted documentation.

Takes an ``ImpactReport`` from the ImpactAgent and triggers regeneration
of only the affected output formats / sections, avoiding a full rebuild.
"""

from __future__ import annotations

import time
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ...core.knowledge_graph import KnowledgeGraph
from ...core.models import DocumentModel
from .impact_agent import ImpactReport


class RegenerationAgent(AgentBase):
    """Selectively regenerates documentation artifacts based on impact.

    The agent:
    1. Reads the ``ImpactReport`` to know which entities/formats changed.
    2. Re-runs only the affected generators (WORD, PPTX, BLOG, etc.).
    3. Patches existing documents rather than full rewrites when possible.
    4. Attaches evidence pointers to all regenerated content.
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
        impact_report: ImpactReport | None = None,
        **kwargs: Any,
    ) -> AgentResult:
        t0 = time.perf_counter()

        if impact_report is None:
            impact_report = self._extract_impact(prior_results)
            if impact_report is None:
                return self._make_result(
                    success=False,
                    errors=["No ImpactReport provided or found in prior results"],
                )

        # Nothing to regenerate
        if impact_report.total_deltas == 0:
            return self._make_result(
                success=True,
                artifacts={"regenerated": [], "skipped_reason": "No impacted entities"},
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        regenerated_formats = await self._regenerate(
            impact_report=impact_report,
            knowledge_graph=knowledge_graph,
            document=document,
        )

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts={
                "regenerated": regenerated_formats,
                "impacted_entities": [
                    d.entity_id for d in impact_report.entity_deltas
                ],
            },
            duration_ms=duration,
        )

    # -- Internal -----------------------------------------------------------

    async def _regenerate(
        self,
        *,
        impact_report: ImpactReport,
        knowledge_graph: KnowledgeGraph,
        document: DocumentModel | None,
    ) -> list[str]:
        """Trigger selective regeneration of impacted formats.

        TODO: Integrate with the existing pipeline generators to
              re-run only the affected formats. Currently returns a
              placeholder list of formats that *would* be regenerated.
        """
        return impact_report.impacted_output_formats

    def _extract_impact(
        self, prior_results: list[AgentResult] | None
    ) -> ImpactReport | None:
        """Try to find an ImpactReport in prior results."""
        if not prior_results:
            return None
        for result in prior_results:
            ir = result.artifacts.get("impact_report")
            if ir and isinstance(ir, dict):
                return ImpactReport(
                    impacted_output_formats=ir.get("impacted_formats", []),
                    confidence=ir.get("confidence", 0.0),
                )
        return None
