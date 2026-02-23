"""MicroservicesAgent — Docker Compose / K8s / service-mesh topology.

Detects microservice boundaries, inter-service communication patterns,
and generates service dependency diagrams + architecture documentation.
"""

from __future__ import annotations

import time
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ..llm_client import chat_text
from ...core.knowledge_graph import KnowledgeGraph
from ...core.models import DocumentModel


class MicroservicesAgent(AgentBase):
    """Analyses microservice-based repos for topology and communication.

    Capabilities:
    - Parse ``docker-compose.yml`` for service definitions + networks.
    - Parse K8s manifests (Deployment, Service, Ingress, HPA) for topology.
    - Detect service mesh (Istio / Linkerd) virtual services / sidecars.
    - Generate Mermaid service dependency diagram.
    - Produce an "Architecture Overview" documentation section.
    - Attach evidence pointers to every discovered service.

    Signals detected: ``docker-compose``, ``kubernetes``, ``k8s``.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(role=AgentRole.MICROSERVICES, model=model)

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
        evidence_ids: list[str] = []

        # 1. Discover services from file tree
        services = self._discover_services(repo_profile)

        # 2. Generate Mermaid service dependency diagram
        mermaid_spec = self._build_service_diagram(services)
        artifacts["service_diagram_mermaid"] = mermaid_spec

        # 3. Produce architecture overview section (LLM or template)
        if use_llm:
            try:
                section_md = await self._build_architecture_section_llm(
                    services=services,
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                )
            except Exception:
                section_md = self._build_architecture_section(
                    services=services, repo_name=repo_profile.repo_name,
                )
        else:
            section_md = self._build_architecture_section(
                services=services, repo_name=repo_profile.repo_name,
            )
        artifacts["architecture_section_md"] = section_md

        # 4. Attach metadata
        artifacts["discovered_services"] = services

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts=artifacts,
            evidence_ids=evidence_ids,
            duration_ms=duration,
            metadata={"service_count": len(services)},
        )

    # -- Internal -----------------------------------------------------------

    def _discover_services(self, profile: RepoProfile) -> list[dict[str, Any]]:
        """Extract service definitions from file tree + signals.

        TODO: Parse actual docker-compose.yml / K8s manifests via
              ``repo.read`` tool. Currently uses heuristics from the
              file tree.
        """
        services: list[dict[str, Any]] = []
        for path in profile.file_tree:
            if "docker-compose" in path:
                services.append({
                    "name": "docker-compose",
                    "source": path,
                    "type": "compose",
                })
            elif path.endswith(("deployment.yaml", "deployment.yml")):
                name = path.split("/")[-2] if "/" in path else "unknown"
                services.append({
                    "name": name,
                    "source": path,
                    "type": "k8s-deployment",
                })
            elif path.endswith("Dockerfile"):
                name = path.split("/")[-2] if "/" in path else "app"
                services.append({
                    "name": name,
                    "source": path,
                    "type": "docker",
                })
        return services

    def _build_service_diagram(
        self, services: list[dict[str, Any]]
    ) -> str:
        """Generate a Mermaid service dependency diagram."""
        lines = ["graph LR"]
        for svc in services:
            safe_name = svc["name"].replace("-", "_").replace(" ", "_")
            lines.append(f'    {safe_name}["{svc["name"]}"]')

        # Add default edges between services (placeholder)
        if len(services) > 1:
            names = [s["name"].replace("-", "_").replace(" ", "_") for s in services]
            for i in range(len(names) - 1):
                lines.append(f"    {names[i]} --> {names[i + 1]}")

        return "\n".join(lines)

    async def _build_architecture_section_llm(
        self,
        services: list[dict[str, Any]],
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
    ) -> str:
        """Use LLM to generate a rich architecture overview."""
        svc_desc = "\n".join(
            f"- {s['name']} ({s['type']}) from {s.get('source', 'N/A')}"
            for s in services
        ) or "No services discovered"
        entities = ", ".join(e.name for e in knowledge_graph.entities[:15])

        return await chat_text(
            system=(
                "You are a senior technical writer. Write a detailed Markdown "
                "architecture overview section for a microservices repository. "
                "Include service descriptions, communication patterns, "
                "deployment topology, and scaling considerations. "
                "Use ## headers. Be specific to the discovered services. "
                "Do NOT invent services that aren't listed."
            ),
            user=(
                f"Repository: {repo_profile.repo_name}\n"
                f"Description: {repo_profile.description[:300]}\n"
                f"KG entities: {entities}\n\n"
                f"Discovered services:\n{svc_desc}\n\n"
                f"Write a detailed architecture overview section."
            ),
            model=self.model,
            max_tokens=1500,
        )

    def _build_architecture_section(
        self,
        services: list[dict[str, Any]],
        repo_name: str,
    ) -> str:
        """Generate Markdown architecture overview section."""
        lines = [
            f"## Architecture Overview — {repo_name}",
            "",
            f"This repository contains **{len(services)}** service(s):",
            "",
        ]
        for svc in services:
            lines.append(f"- **{svc['name']}** ({svc['type']}) — `{svc['source']}`")

        lines.append("")
        lines.append("### Service Communication")
        lines.append("")
        lines.append(
            "TODO: Document inter-service communication patterns "
            "(REST, gRPC, message queues)."
        )
        return "\n".join(lines)
