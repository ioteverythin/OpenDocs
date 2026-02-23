"""Agent orchestrator — the Planner → Executor → Critic loop.

This is the top-level entry point for the agentic layer. It:
1. Builds a ``RepoProfile`` from the existing pipeline data.
2. Runs the **Planner** to create an execution plan.
3. Walks the plan step-by-step through the **Executor**.
4. Passes all results to the **Critic** for validation.
5. If the Critic rejects, loops back to the Planner (up to max_retries).
6. Returns the final enhanced artifacts + evidence coverage report.

The orchestrator produces "enhanced" artifacts *separately* from
the deterministic baseline — it never overwrites existing pipeline output.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from rich.console import Console

from ..core.knowledge_graph import KnowledgeGraph
from ..core.models import DocumentModel
from .base import AgentPlan, AgentResult, AgentRole, PlanStep, RepoProfile
from .critic import CriticAgent
from .evidence import EvidenceRegistry
from .executor import ExecutorAgent
from .planner import PlannerAgent
from .privacy import PrivacyGuard, PrivacyMode

# Lazy imports for specialized sub-agents
from .specialized import (
    DataEngineeringAgent,
    EventDrivenAgent,
    InfraAgent,
    MicroservicesAgent,
    MLAgent,
)

console = Console()


# ---------------------------------------------------------------------------
# Sub-agent dispatch table
# ---------------------------------------------------------------------------

_SUB_AGENT_CLASSES: dict[AgentRole, type] = {
    AgentRole.MICROSERVICES: MicroservicesAgent,
    AgentRole.EVENT_DRIVEN: EventDrivenAgent,
    AgentRole.ML: MLAgent,
    AgentRole.DATA_ENGINEERING: DataEngineeringAgent,
    AgentRole.INFRA: InfraAgent,
}


# ---------------------------------------------------------------------------
# Orchestrator result
# ---------------------------------------------------------------------------

class OrchestrationResult:
    """The final output of the agentic pipeline.

    Contains enhanced artifacts, the execution plan, evidence coverage,
    and the Critic's verdict — all separate from the deterministic baseline.
    """

    def __init__(
        self,
        *,
        plan: AgentPlan | None = None,
        step_results: list[AgentResult] | None = None,
        critic_result: AgentResult | None = None,
        enhanced_artifacts: dict[str, Any] | None = None,
        total_duration_ms: float = 0.0,
        iterations: int = 0,
    ) -> None:
        self.plan = plan
        self.step_results = step_results or []
        self.critic_result = critic_result
        self.enhanced_artifacts = enhanced_artifacts or {}
        self.total_duration_ms = total_duration_ms
        self.iterations = iterations

    @property
    def approved(self) -> bool:
        if self.critic_result is None:
            return False
        return self.critic_result.success

    def summary(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "iterations": self.iterations,
            "total_steps": self.plan.total_steps if self.plan else 0,
            "completed_steps": self.plan.completed_steps if self.plan else 0,
            "duration_ms": round(self.total_duration_ms, 1),
            "artifacts": list(self.enhanced_artifacts.keys()),
            "verdict": (
                self.critic_result.artifacts.get("verdict")
                if self.critic_result else None
            ),
        }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

class AgentOrchestrator:
    """Top-level coordinator for the Planner → Executor → Critic loop.

    Usage::

        orch = AgentOrchestrator(privacy_mode=PrivacyMode.STANDARD)
        result = await orch.run(
            repo_profile=profile,
            knowledge_graph=kg,
            document=doc,
        )
        print(result.summary())
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        privacy_mode: PrivacyMode = PrivacyMode.STANDARD,
        max_retries: int = 2,
        output_dir: Path | str = ".",
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.output_dir = Path(output_dir)

        # Shared state across agents
        self._evidence = EvidenceRegistry()
        self._privacy = PrivacyGuard(mode=privacy_mode)

        # Core agents
        self._planner = PlannerAgent(model=model)
        self._executor = ExecutorAgent(
            model=model,
            privacy_guard=self._privacy,
            evidence_registry=self._evidence,
        )
        self._critic = CriticAgent(
            model=model,
            evidence_registry=self._evidence,
        )

        # Sub-agent cache (instantiated on demand)
        self._sub_agents: dict[AgentRole, Any] = {}

    async def run(
        self,
        *,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        document: DocumentModel | None = None,
        use_llm: bool = True,
    ) -> OrchestrationResult:
        """Execute the full Planner → Executor → Critic loop."""
        t0 = time.perf_counter()
        iterations = 0
        all_step_results: list[AgentResult] = []
        current_plan: AgentPlan | None = None
        critic_result: AgentResult | None = None

        # Apply privacy filtering to the profile
        safe_profile = self._privacy.sanitise_profile(repo_profile)

        for attempt in range(1, self.max_retries + 2):  # +1 for initial + retries
            iterations = attempt
            console.print(
                f"[bold cyan]Agent loop iteration {attempt}[/bold cyan]"
            )

            # ── 1. PLAN ──────────────────────────────────────────────
            console.print("  [dim]Planning...[/dim]")
            planner_result = await self._planner.run(
                repo_profile=safe_profile,
                knowledge_graph=knowledge_graph,
                document=document,
                prior_results=all_step_results if attempt > 1 else None,
                use_llm=use_llm,
            )
            if not planner_result.success:
                console.print("[red]  Planner failed[/red]")
                break

            current_plan = AgentPlan(**planner_result.artifacts["plan"])
            console.print(
                f"  Plan: {current_plan.total_steps} steps, "
                f"goal: {current_plan.goal}"
            )

            # ── 2. EXECUTE ───────────────────────────────────────────
            step_results: list[AgentResult] = []
            for step in current_plan.steps:
                if step.agent_role == AgentRole.CRITIC:
                    continue  # Critic runs after all execution steps

                console.print(
                    f"  [dim]Step {step.step_number}: {step.description}[/dim]"
                )

                result = await self._execute_step(
                    step=step,
                    repo_profile=safe_profile,
                    knowledge_graph=knowledge_graph,
                    document=document,
                    plan=current_plan,
                    prior_results=step_results,
                    use_llm=use_llm,
                )
                step_results.append(result)
                step.completed = result.success

            all_step_results.extend(step_results)

            # ── 3. CRITIQUE ──────────────────────────────────────────
            console.print("  [dim]Validating evidence coverage...[/dim]")
            critic_result = await self._critic.run(
                repo_profile=safe_profile,
                knowledge_graph=knowledge_graph,
                document=document,
                plan=current_plan,
                prior_results=all_step_results,
                use_llm=use_llm,
            )

            verdict = critic_result.artifacts.get("verdict", {})
            if critic_result.success:
                console.print(
                    "[green]  ✓ Critic approved — evidence coverage OK[/green]"
                )
                break
            else:
                console.print(
                    f"[yellow]  ✗ Critic rejected: {verdict.get('replan_reason', '?')}[/yellow]"
                )
                if attempt > self.max_retries:
                    console.print("[red]  Max retries reached[/red]")
                    break
                console.print("  [dim]Re-planning...[/dim]")

        # ── 4. COLLECT ENHANCED ARTIFACTS ─────────────────────────────
        enhanced: dict[str, Any] = {}
        for sr in all_step_results:
            enhanced.update(sr.artifacts)

        total_ms = (time.perf_counter() - t0) * 1000
        return OrchestrationResult(
            plan=current_plan,
            step_results=all_step_results,
            critic_result=critic_result,
            enhanced_artifacts=enhanced,
            total_duration_ms=total_ms,
            iterations=iterations,
        )

    # -- Internal -----------------------------------------------------------

    async def _execute_step(
        self,
        *,
        step: PlanStep,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        document: DocumentModel | None,
        plan: AgentPlan,
        prior_results: list[AgentResult],
        use_llm: bool = True,
    ) -> AgentResult:
        """Route a plan step to the appropriate agent."""

        # If the step is for a specialized sub-agent, delegate to it
        if step.agent_role in _SUB_AGENT_CLASSES:
            agent = self._get_sub_agent(step.agent_role)
            return await agent.run(
                repo_profile=repo_profile,
                knowledge_graph=knowledge_graph,
                document=document,
                plan=plan,
                prior_results=prior_results,
                use_llm=use_llm,
            )

        # Otherwise, use the generic executor
        return await self._executor.run(
            repo_profile=repo_profile,
            knowledge_graph=knowledge_graph,
            document=document,
            plan=plan,
            prior_results=prior_results,
            step=step,
        )

    def _get_sub_agent(self, role: AgentRole) -> Any:
        """Lazily instantiate a specialized sub-agent."""
        if role not in self._sub_agents:
            cls = _SUB_AGENT_CLASSES[role]
            self._sub_agents[role] = cls(model=self.model)
        return self._sub_agents[role]
