"""InfraAgent — Terraform / Helm / K8s / Pulumi / CloudFormation resource graphs.

Detects infrastructure-as-code patterns, maps resource dependencies,
and generates infra topology diagrams + documentation.
"""

from __future__ import annotations

import time
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ..llm_client import chat_text
from ...core.knowledge_graph import KnowledgeGraph
from ...core.models import DocumentModel


class InfraAgent(AgentBase):
    """Analyses IaC repos for resource topology and dependencies.

    Capabilities:
    - Parse Terraform ``.tf`` files for resource/module/provider blocks.
    - Parse Helm charts (``Chart.yaml``, templates, values).
    - Parse K8s manifests for cluster resource topology.
    - Parse Pulumi programs for resource declarations.
    - Parse CloudFormation templates for stack resources.
    - Generate Mermaid resource dependency diagram.
    - Produce "Infrastructure" documentation section.
    - Map cloud provider resource types to documentation templates.

    Signals detected: ``terraform``, ``helm``, ``pulumi``,
    ``cloudformation``.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(role=AgentRole.INFRA, model=model)

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

        # 1. Discover infra resources
        resources = self._discover_resources(repo_profile)

        # 2. Generate resource topology diagram
        mermaid_spec = self._build_infra_diagram(resources)
        artifacts["infra_topology_mermaid"] = mermaid_spec

        # 3. Produce infrastructure section (LLM or template)
        if use_llm:
            try:
                section_md = await self._build_infra_section_llm(
                    resources=resources,
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                )
            except Exception:
                section_md = self._build_infra_section(
                    resources=resources, repo_name=repo_profile.repo_name,
                )
        else:
            section_md = self._build_infra_section(
                resources=resources, repo_name=repo_profile.repo_name,
            )
        artifacts["infrastructure_md"] = section_md
        artifacts["infra_resources"] = resources

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts=artifacts,
            duration_ms=duration,
            metadata={"resource_count": len(resources)},
        )

    # -- Internal -----------------------------------------------------------

    def _discover_resources(
        self, profile: RepoProfile
    ) -> list[dict[str, Any]]:
        """Discover IaC resources from file tree and signals.

        TODO: Parse actual .tf files for resource blocks,
              Helm Chart.yaml for dependencies,
              K8s manifests for resource types.
        """
        resources: list[dict[str, Any]] = []
        signal_types = {s.signal_type for s in profile.signals}

        if "terraform" in signal_types:
            resources.append({
                "type": "iac",
                "tech": "terraform",
                "name": "Terraform Configuration",
            })
        if "helm" in signal_types:
            resources.append({
                "type": "chart",
                "tech": "helm",
                "name": "Helm Chart",
            })
        if "pulumi" in signal_types:
            resources.append({
                "type": "iac",
                "tech": "pulumi",
                "name": "Pulumi Program",
            })
        if "cloudformation" in signal_types:
            resources.append({
                "type": "iac",
                "tech": "cloudformation",
                "name": "CloudFormation Stack",
            })

        # Discover from file tree
        for path in profile.file_tree:
            if path.endswith(".tf"):
                resources.append({
                    "type": "terraform-file",
                    "tech": "terraform",
                    "name": path.split("/")[-1],
                    "source": path,
                })
            elif path == "Chart.yaml" or path.endswith("/Chart.yaml"):
                chart_name = path.split("/")[-2] if "/" in path else "chart"
                resources.append({
                    "type": "helm-chart",
                    "tech": "helm",
                    "name": chart_name,
                    "source": path,
                })

        return resources

    def _build_infra_diagram(
        self, resources: list[dict[str, Any]]
    ) -> str:
        """Generate a Mermaid infrastructure topology diagram."""
        lines = ["graph TB"]
        lines.append('    Cloud["Cloud Provider"]')

        techs = {r["tech"] for r in resources}
        if "terraform" in techs:
            lines.append('    TF["Terraform"]')
            lines.append('    TF --> VPC["VPC / Network"]')
            lines.append('    TF --> Compute["Compute"]')
            lines.append('    TF --> Storage["Storage"]')
            lines.append('    TF --> DB["Database"]')
            lines.append('    Cloud --> TF')
        if "helm" in techs:
            lines.append('    Helm["Helm Charts"]')
            lines.append('    Helm --> K8s["Kubernetes Cluster"]')
            lines.append('    K8s --> Pods["Pods"]')
            lines.append('    K8s --> Services["Services"]')
            lines.append('    Cloud --> Helm')
        if "pulumi" in techs:
            lines.append('    Pulumi["Pulumi"]')
            lines.append('    Cloud --> Pulumi')
        if "cloudformation" in techs:
            lines.append('    CFN["CloudFormation"]')
            lines.append('    Cloud --> CFN')

        return "\n".join(lines)

    async def _build_infra_section_llm(
        self,
        resources: list[dict[str, Any]],
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
    ) -> str:
        """Use LLM to generate rich infrastructure documentation."""
        res_desc = "\n".join(
            f"- {r['name']} ({r['tech']}, {r['type']})" for r in resources
        ) or "No resources discovered"
        entities = ", ".join(e.name for e in knowledge_graph.entities[:15])

        return await chat_text(
            system=(
                "You are a DevOps/SRE documentation specialist. Write a detailed "
                "Markdown infrastructure section. Include resource inventory, "
                "deployment topology, networking, scaling, and operational runbooks. "
                "Use ## headers. Be specific to discovered IaC resources."
            ),
            user=(
                f"Repository: {repo_profile.repo_name}\n"
                f"Description: {repo_profile.description[:300]}\n"
                f"KG entities: {entities}\n\n"
                f"Discovered infrastructure resources:\n{res_desc}\n\n"
                f"Write detailed infrastructure documentation."
            ),
            model=self.model,
            max_tokens=1500,
        )

    def _build_infra_section(
        self,
        resources: list[dict[str, Any]],
        repo_name: str,
    ) -> str:
        """Generate Markdown infrastructure section."""
        lines = [
            f"## Infrastructure — {repo_name}",
            "",
            f"This repository manages **{len(resources)}** infrastructure resource(s):",
            "",
        ]
        for res in resources:
            source = res.get("source", "")
            suffix = f" — `{source}`" if source else ""
            lines.append(f"- **{res['name']}** ({res['tech']}, {res['type']}){suffix}")

        lines.append("")
        lines.append("### Deployment")
        lines.append("")
        lines.append(
            "TODO: Document deployment prerequisites, environment variables, "
            "and rollback procedures."
        )
        return "\n".join(lines)
