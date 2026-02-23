"""Critic / Verifier agent — step 3 of the Planner → Executor → Critic loop.

The Critic validates every generated artifact against the evidence
registry. It computes evidence coverage scores, flags hallucinations,
and can force re-planning when evidence is insufficient.
"""

from __future__ import annotations

import time
from typing import Any

from ..core.knowledge_graph import KnowledgeGraph
from ..core.models import DocumentModel
from .llm_client import chat_json
from .base import (
    AgentBase,
    AgentPlan,
    AgentResult,
    AgentRole,
    RepoProfile,
)
from .evidence import Claim, EvidenceCoverage, EvidenceRegistry


# ---------------------------------------------------------------------------
# Verdict model
# ---------------------------------------------------------------------------

class CriticVerdict:
    """The Critic's assessment of an artifact set.

    Attributes
    ----------
    approved : bool
        True if evidence coverage meets the threshold.
    coverage_scores : list[EvidenceCoverage]
        Per-artifact coverage details.
    flagged_claims : list[Claim]
        Claims flagged as potential hallucinations.
    replan_reason : str
        If not approved, the reason re-planning is needed.
    """

    def __init__(
        self,
        approved: bool = True,
        coverage_scores: list[EvidenceCoverage] | None = None,
        flagged_claims: list[Claim] | None = None,
        replan_reason: str = "",
    ) -> None:
        self.approved = approved
        self.coverage_scores = coverage_scores or []
        self.flagged_claims = flagged_claims or []
        self.replan_reason = replan_reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "coverage_scores": [s.summary() for s in self.coverage_scores],
            "flagged_claims": [c.model_dump() for c in self.flagged_claims],
            "replan_reason": self.replan_reason,
        }


class CriticAgent(AgentBase):
    """Validates artifacts against evidence and computes coverage scores.

    The Critic:
    1. Scans all claims registered during execution.
    2. Checks each claim has ≥1 evidence pointer.
    3. Flags claims without evidence as assumptions/hallucinations.
    4. Computes per-artifact coverage percentage.
    5. Rejects the batch and triggers re-planning if coverage < threshold.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        evidence_registry: EvidenceRegistry | None = None,
        min_coverage_pct: float = 80.0,
        max_assumptions: int = 5,
    ) -> None:
        super().__init__(role=AgentRole.CRITIC, model=model)
        self._evidence = evidence_registry or EvidenceRegistry()
        self._min_coverage = min_coverage_pct
        self._max_assumptions = max_assumptions

    async def run(
        self,
        *,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        document: DocumentModel | None = None,
        plan: AgentPlan | None = None,
        prior_results: list[AgentResult] | None = None,
        use_llm: bool = True,
        **kwargs: Any,
    ) -> AgentResult:
        t0 = time.perf_counter()

        verdict = self._evaluate(prior_results or [])

        # LLM semantic review of artifacts
        llm_review = ""
        if use_llm and prior_results:
            try:
                llm_review = await self._llm_review(
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                    prior_results=prior_results,
                    verdict=verdict,
                )
            except Exception:
                llm_review = "(LLM review unavailable)"

        verdict_dict = verdict.to_dict()
        verdict_dict["llm_review"] = llm_review

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=verdict.approved,
            artifacts={"verdict": verdict_dict},
            errors=[verdict.replan_reason] if not verdict.approved else [],
            duration_ms=duration,
            metadata={
                "total_claims": sum(s.total_claims for s in verdict.coverage_scores),
                "flagged_count": len(verdict.flagged_claims),
                "llm_reviewed": bool(llm_review and "unavailable" not in llm_review),
            },
        )

    def _evaluate(self, prior_results: list[AgentResult]) -> CriticVerdict:
        """Evaluate all claims and compute coverage scores."""

        # 1. Compute per-artifact coverage
        coverage_scores = self._evidence.compute_all_coverage()

        # 2. Find flagged claims (assumptions without evidence)
        all_claims = self._evidence.all_claims()
        flagged = [c for c in all_claims if c.is_assumption]

        # 3. Check global thresholds
        total_claims = sum(s.total_claims for s in coverage_scores)
        total_backed = sum(s.backed_claims for s in coverage_scores)
        global_coverage = (total_backed / total_claims * 100) if total_claims else 100.0

        approved = True
        replan_reason = ""

        if global_coverage < self._min_coverage:
            approved = False
            replan_reason = (
                f"Evidence coverage {global_coverage:.1f}% is below threshold "
                f"{self._min_coverage}%. {len(flagged)} unsupported claims found."
            )

        if len(flagged) > self._max_assumptions:
            approved = False
            replan_reason = (
                f"Too many assumptions ({len(flagged)}) exceed limit "
                f"({self._max_assumptions}). Re-planning required."
            )

        return CriticVerdict(
            approved=approved,
            coverage_scores=coverage_scores,
            flagged_claims=flagged,
            replan_reason=replan_reason,
        )

    async def _llm_review(
        self,
        *,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        prior_results: list[AgentResult],
        verdict: CriticVerdict,
    ) -> str:
        """Use LLM to semantically review generated artifacts."""
        # Collect artifact summaries
        artifact_summaries: list[str] = []
        for r in prior_results:
            for key, val in r.artifacts.items():
                if isinstance(val, str) and len(val) > 20:
                    artifact_summaries.append(f"- {key}: {val[:300]}")
                elif isinstance(val, dict):
                    artifact_summaries.append(f"- {key}: {str(val)[:200]}")

        artifacts_text = "\n".join(artifact_summaries[:15]) or "No artifacts generated"
        entities_str = ", ".join(e.name for e in knowledge_graph.entities[:20])

        data = await chat_json(
            system=(
                "You are a documentation quality critic. Review generated artifacts "
                "for accuracy, completeness, and hallucination risks.\n"
                "Return JSON with: quality_score (1-10), strengths (list of strings), "
                "weaknesses (list of strings), recommendations (list of strings), "
                "hallucination_risks (list of strings), summary (string)."
            ),
            user=(
                f"Repository: {repo_profile.repo_name}\n"
                f"KG entities: {entities_str}\n"
                f"Coverage approved: {verdict.approved}\n"
                f"Flagged assumptions: {len(verdict.flagged_claims)}\n\n"
                f"Generated artifacts:\n{artifacts_text}\n\n"
                f"Evaluate the quality and trustworthiness of these artifacts."
            ),
            model=self.model,
            max_tokens=1024,
        )

        # Format as readable summary
        score = data.get("quality_score", "?")
        summary = data.get("summary", "")
        strengths = data.get("strengths", [])
        weaknesses = data.get("weaknesses", [])
        recommendations = data.get("recommendations", [])
        risks = data.get("hallucination_risks", [])

        lines = [f"Quality Score: {score}/10", summary]
        if strengths:
            lines.append("Strengths: " + "; ".join(strengths[:3]))
        if weaknesses:
            lines.append("Weaknesses: " + "; ".join(weaknesses[:3]))
        if risks:
            lines.append("Hallucination risks: " + "; ".join(risks[:3]))
        if recommendations:
            lines.append("Recommendations: " + "; ".join(recommendations[:3]))

        return " | ".join(lines)

    def compute_artifact_score(
        self, artifact_id: str, artifact_type: str = ""
    ) -> EvidenceCoverage:
        """Public API: compute coverage for a specific artifact."""
        return self._evidence.compute_coverage(artifact_id, artifact_type)
