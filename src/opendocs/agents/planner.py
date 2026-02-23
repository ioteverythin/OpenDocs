"""Planner agent — step 1 of the Planner → Executor → Critic loop.

The Planner reads the ``RepoProfile`` + ``KnowledgeGraph`` + evidence
pointers, and produces a step-by-step ``AgentPlan`` (JSON) of tool
calls and expected outputs. It also chooses which specialized
sub-agents to activate based on detected repo signals.
"""

from __future__ import annotations

import json
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
    PlanStep,
    RepoProfile,
    ToolCall,
)


# ---------------------------------------------------------------------------
# Signal → sub-agent routing table
# ---------------------------------------------------------------------------

_SIGNAL_TO_AGENT: dict[str, AgentRole] = {
    "docker-compose": AgentRole.MICROSERVICES,
    "Dockerfile": AgentRole.MICROSERVICES,
    "kubernetes": AgentRole.MICROSERVICES,
    "k8s": AgentRole.MICROSERVICES,
    "helm": AgentRole.INFRA,
    "terraform": AgentRole.INFRA,
    "pulumi": AgentRole.INFRA,
    "cloudformation": AgentRole.INFRA,
    "kafka": AgentRole.EVENT_DRIVEN,
    "rabbitmq": AgentRole.EVENT_DRIVEN,
    "sqs": AgentRole.EVENT_DRIVEN,
    "eventbridge": AgentRole.EVENT_DRIVEN,
    "nats": AgentRole.EVENT_DRIVEN,
    "ml-training": AgentRole.ML,
    "pytorch": AgentRole.ML,
    "tensorflow": AgentRole.ML,
    "huggingface": AgentRole.ML,
    "vector-db": AgentRole.ML,
    "rag": AgentRole.ML,
    "airflow": AgentRole.DATA_ENGINEERING,
    "dbt": AgentRole.DATA_ENGINEERING,
    "spark": AgentRole.DATA_ENGINEERING,
    "warehouse": AgentRole.DATA_ENGINEERING,
}


class PlannerAgent(AgentBase):
    """Analyses repo signals and KG to produce an execution plan.

    The plan includes:
    1. Which specialized sub-agents to activate.
    2. What diagrams to generate (and from what KG data).
    3. What document sections to enhance.
    4. What evidence to gather first.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(role=AgentRole.PLANNER, model=model)

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

        # 1. Detect which sub-agents to activate
        activated_agents = self._detect_sub_agents(repo_profile)

        # 2. Build the execution plan (LLM-enhanced or deterministic)
        llm_used = False
        if use_llm:
            try:
                built_plan = await self._build_plan_llm(
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                    activated_agents=activated_agents,
                )
                llm_used = True
            except Exception as exc:
                # Fallback to deterministic
                built_plan = self._build_plan(
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                    activated_agents=activated_agents,
                )
        else:
            built_plan = self._build_plan(
                repo_profile=repo_profile,
                knowledge_graph=knowledge_graph,
                activated_agents=activated_agents,
            )

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts={"plan": built_plan.model_dump()},
            duration_ms=duration,
            metadata={
                "activated_agents": [a.value for a in activated_agents],
                "llm_used": llm_used,
            },
        )

    # -- Internal -----------------------------------------------------------

    def _detect_sub_agents(self, profile: RepoProfile) -> list[AgentRole]:
        """Map repo signals to specialized sub-agents."""
        agents: set[AgentRole] = set()
        for signal in profile.signals:
            role = _SIGNAL_TO_AGENT.get(signal.signal_type)
            if role:
                agents.add(role)
        return sorted(agents, key=lambda r: r.value)

    async def _build_plan_llm(
        self,
        *,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        activated_agents: list[AgentRole],
    ) -> AgentPlan:
        """LLM-powered plan construction."""
        entities_str = ", ".join(e.name for e in knowledge_graph.entities[:25])
        relations_str = ", ".join(
            f"{r.source_id}->{r.target_id}" for r in knowledge_graph.relations[:20]
        )
        signals_str = ", ".join(s.signal_type for s in repo_profile.signals) or "none"
        agents_str = ", ".join(a.value for a in activated_agents) or "none"
        mermaid_spec = knowledge_graph.to_mermaid(max_entities=30)

        system = (
            "You are a documentation planning agent. You produce JSON execution plans "
            "for generating enhanced documentation from a GitHub repository.\n\n"
            "Available tools: repo.search, repo.read, repo.diff, repo.summarize, "
            "diagram.render, chart.generate, docx.refine, pptx.refine.\n"
            "Available specialized sub-agents: " + agents_str + "\n\n"
            "IMPORTANT RULES:\n"
            "1. You MUST use the specialized sub-agent roles for steps they can handle.\n"
            "   - Use \"microservices\" role for Docker, K8s, service architecture steps.\n"
            "   - Use \"ml\" role for ML models, training, inference steps.\n"
            "   - Use \"infra\" role for Terraform, Helm, cloud infra steps.\n"
            "   - Use \"event_driven\" role for Kafka, SQS, message queue steps.\n"
            "   - Use \"data_engineering\" role for Airflow, dbt, Spark, pipeline steps.\n"
            "2. Only use \"executor\" role for generic steps not covered by a specialized agent.\n"
            "3. Always end with a \"critic\" step.\n"
            "4. Each step should produce a concrete documentation artifact.\n\n"
            "Return JSON with keys: goal (string), reasoning (string), "
            "steps (array of objects with: step_number, description, agent_role "
            "[one of: " + agents_str + ", executor, critic], "
            "tool_calls (array of {tool_name, parameters}), expected_output)."
        )

        user = (
            f"Repository: {repo_profile.repo_name}\n"
            f"URL: {repo_profile.repo_url}\n"
            f"Description: {repo_profile.description[:300]}\n"
            f"Language: {repo_profile.primary_language}\n"
            f"Signals detected: {signals_str}\n"
            f"KG entities: {entities_str}\n"
            f"KG relations: {relations_str}\n"
            f"File tree ({len(repo_profile.file_tree)} files): "
            f"{', '.join(repo_profile.file_tree[:30])}\n\n"
            f"Create an optimal documentation enhancement plan. "
            f"Always end with a critic validation step."
        )

        data = await chat_json(
            system=system, user=user, model=self.model, max_tokens=4096,
        )

        # Parse LLM response into AgentPlan
        steps: list[PlanStep] = []
        for raw_step in data.get("steps", []):
            role_str = raw_step.get("agent_role", "executor")
            try:
                role = AgentRole(role_str)
            except ValueError:
                role = AgentRole.EXECUTOR

            tool_calls = []
            for raw_tc in raw_step.get("tool_calls", []):
                tool_calls.append(ToolCall(
                    tool_name=raw_tc.get("tool_name", ""),
                    parameters=raw_tc.get("parameters", {}),
                ))

            steps.append(PlanStep(
                step_number=raw_step.get("step_number", len(steps) + 1),
                description=raw_step.get("description", ""),
                agent_role=role,
                tool_calls=tool_calls,
                expected_output=raw_step.get("expected_output", ""),
            ))

        # Ensure we have a critic step at the end
        if not steps or steps[-1].agent_role != AgentRole.CRITIC:
            steps.append(PlanStep(
                step_number=len(steps) + 1,
                description="Validate all artifacts against evidence pointers",
                agent_role=AgentRole.CRITIC,
                expected_output="Evidence coverage report",
            ))

        return AgentPlan(
            goal=data.get("goal", f"Enhanced docs for {repo_profile.repo_name}"),
            steps=steps,
            metadata={
                "repo": repo_profile.repo_name,
                "entity_count": len(knowledge_graph.entities),
                "activated_agents": [a.value for a in activated_agents],
                "llm_reasoning": data.get("reasoning", ""),
            },
        )

    def _build_plan(
        self,
        *,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        activated_agents: list[AgentRole],
    ) -> AgentPlan:
        """Deterministic fallback plan construction."""
        steps: list[PlanStep] = []
        step_num = 0

        # Step 1: Gather evidence from repo
        step_num += 1
        steps.append(PlanStep(
            step_number=step_num,
            description="Search repo for architecture-relevant files",
            agent_role=AgentRole.EXECUTOR,
            tool_calls=[
                ToolCall(
                    tool_name="repo.search",
                    parameters={"query": "docker|kubernetes|terraform|setup|config", "max_results": 50},
                    expected_output_type="json",
                ),
            ],
            expected_output="List of architecture-relevant file paths",
        ))

        # Step 2: Generate KG-based architecture diagram
        step_num += 1
        mermaid_spec = knowledge_graph.to_mermaid(max_entities=30)
        steps.append(PlanStep(
            step_number=step_num,
            description="Render architecture diagram from knowledge graph",
            agent_role=AgentRole.EXECUTOR,
            tool_calls=[
                ToolCall(
                    tool_name="diagram.render",
                    parameters={"type": "mermaid", "spec": mermaid_spec, "output_format": "svg"},
                    expected_output_type="svg",
                ),
            ],
            depends_on=[],
            expected_output="SVG architecture diagram",
        ))

        # Step 3: Activate each specialized sub-agent
        for agent_role in activated_agents:
            step_num += 1
            steps.append(PlanStep(
                step_number=step_num,
                description=f"Run {agent_role.value} sub-agent for domain-specific analysis",
                agent_role=agent_role,
                tool_calls=[],  # sub-agents generate their own tool calls
                depends_on=[1],
                expected_output=f"Domain diagrams + sections from {agent_role.value}",
            ))

        # Step 4: Refine documents with enhanced content
        step_num += 1
        steps.append(PlanStep(
            step_number=step_num,
            description="Refine Word document with agent-generated content",
            agent_role=AgentRole.EXECUTOR,
            tool_calls=[
                ToolCall(
                    tool_name="docx.refine",
                    parameters={
                        "instructions": "Incorporate architecture diagrams and domain-specific sections",
                        "references_to_KG": [e.id for e in knowledge_graph.entities[:20]],
                    },
                    expected_output_type="docx",
                ),
            ],
            depends_on=[s.step_number for s in steps[1:]],
            expected_output="Enhanced Word document",
        ))

        # Step 5: Critic validation
        step_num += 1
        steps.append(PlanStep(
            step_number=step_num,
            description="Validate all artifacts against evidence pointers",
            agent_role=AgentRole.CRITIC,
            tool_calls=[],
            depends_on=[step_num - 1],
            expected_output="Evidence coverage report",
        ))

        return AgentPlan(
            goal=f"Generate enhanced documentation for {repo_profile.repo_name}",
            steps=steps,
            metadata={
                "repo": repo_profile.repo_name,
                "entity_count": len(knowledge_graph.entities),
                "activated_agents": [a.value for a in activated_agents],
            },
        )
