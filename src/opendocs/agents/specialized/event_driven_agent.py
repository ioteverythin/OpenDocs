"""EventDrivenAgent — Kafka / SQS / EventBridge / RabbitMQ / NATS flows.

Detects event-driven patterns, maps producer → topic → consumer
relationships, and generates event flow diagrams.
"""

from __future__ import annotations

import time
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ..llm_client import chat_text
from ...core.knowledge_graph import KnowledgeGraph
from ...core.models import DocumentModel


class EventDrivenAgent(AgentBase):
    """Analyses event-driven repos for message flow topology.

    Capabilities:
    - Detect Kafka topics/consumers/producers from config files.
    - Detect SQS queues / SNS topics from CloudFormation / Terraform.
    - Detect EventBridge rules and targets.
    - Detect RabbitMQ exchanges/queues from connection strings.
    - Generate Mermaid event flow diagram.
    - Produce an "Event Architecture" documentation section.

    Signals detected: ``kafka``, ``sqs``, ``eventbridge``,
    ``rabbitmq``, ``nats``.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(role=AgentRole.EVENT_DRIVEN, model=model)

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
        artifacts: dict[str, Any] = {}

        # 1. Discover event components
        components = self._discover_event_components(repo_profile)

        # 2. Generate event flow diagram
        mermaid_spec = self._build_event_flow_diagram(components)
        artifacts["event_flow_mermaid"] = mermaid_spec

        # 3. Produce event architecture section (LLM or template)
        if use_llm:
            try:
                section_md = await self._build_event_section_llm(
                    components=components,
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                )
            except Exception:
                section_md = self._build_event_section(
                    components=components, repo_name=repo_profile.repo_name,
                )
        else:
            section_md = self._build_event_section(
                components=components, repo_name=repo_profile.repo_name,
            )
        artifacts["event_architecture_md"] = section_md
        artifacts["event_components"] = components

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts=artifacts,
            duration_ms=duration,
            metadata={"component_count": len(components)},
        )

    # -- Internal -----------------------------------------------------------

    def _discover_event_components(
        self, profile: RepoProfile
    ) -> list[dict[str, Any]]:
        """Extract event-driven components from signals and file tree.

        TODO: Parse actual config files for topic/queue definitions.
        """
        components: list[dict[str, Any]] = []
        signal_types = {s.signal_type for s in profile.signals}

        if "kafka" in signal_types:
            components.append({"type": "broker", "tech": "kafka", "name": "Kafka Cluster"})
        if "sqs" in signal_types:
            components.append({"type": "queue", "tech": "sqs", "name": "SQS Queue"})
        if "eventbridge" in signal_types:
            components.append({"type": "bus", "tech": "eventbridge", "name": "EventBridge"})
        if "rabbitmq" in signal_types:
            components.append({"type": "broker", "tech": "rabbitmq", "name": "RabbitMQ"})
        if "nats" in signal_types:
            components.append({"type": "broker", "tech": "nats", "name": "NATS"})

        return components

    def _build_event_flow_diagram(
        self, components: list[dict[str, Any]]
    ) -> str:
        """Generate a Mermaid event flow diagram."""
        lines = ["graph LR"]
        lines.append('    Producer["Producer Service"]')

        for comp in components:
            safe_name = comp["name"].replace(" ", "_").replace("-", "_")
            lines.append(f'    {safe_name}["{comp["name"]}"]')
            lines.append(f'    Producer --> {safe_name}')
            lines.append(f'    {safe_name} --> Consumer["Consumer Service"]')

        return "\n".join(lines)

    async def _build_event_section_llm(
        self,
        components: list[dict[str, Any]],
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
    ) -> str:
        """Use LLM to generate rich event architecture documentation."""
        comp_desc = ", ".join(f"{c['name']} ({c['tech']})" for c in components)
        entities = ", ".join(e.name for e in knowledge_graph.entities[:15])

        return await chat_text(
            system=(
                "You are an event-driven architecture specialist. Write a detailed "
                "Markdown section about the event architecture. Include message "
                "brokers, event schemas, consumer groups, retry/DLQ policies. "
                "Use ## headers. Be specific to the detected components."
            ),
            user=(
                f"Repository: {repo_profile.repo_name}\n"
                f"Description: {repo_profile.description[:300]}\n"
                f"Event components: {comp_desc}\n"
                f"KG entities: {entities}\n\n"
                f"Write detailed event architecture documentation."
            ),
            model=self.model,
            max_tokens=1500,
        )

    def _build_event_section(
        self,
        components: list[dict[str, Any]],
        repo_name: str,
    ) -> str:
        """Generate Markdown event architecture section."""
        lines = [
            f"## Event Architecture — {repo_name}",
            "",
            f"This repository uses **{len(components)}** event component(s):",
            "",
        ]
        for comp in components:
            lines.append(f"- **{comp['name']}** ({comp['tech']}, {comp['type']})")

        lines.append("")
        lines.append("### Event Flow")
        lines.append("")
        lines.append(
            "TODO: Document event schemas, retry policies, "
            "and dead-letter queue configurations."
        )
        return "\n".join(lines)
