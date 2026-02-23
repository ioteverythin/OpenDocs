"""DataEngineeringAgent — Airflow / dbt / Spark / data warehouse lineage.

Detects data pipeline patterns, maps DAG lineage, and generates
data flow diagrams + documentation.
"""

from __future__ import annotations

import time
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ..llm_client import chat_text
from ...core.knowledge_graph import KnowledgeGraph
from ...core.models import DocumentModel


class DataEngineeringAgent(AgentBase):
    """Analyses data engineering repos for pipeline topology.

    Capabilities:
    - Detect Airflow DAGs from Python files + ``dags/`` folders.
    - Detect dbt models from ``models/`` + ``dbt_project.yml``.
    - Detect Spark jobs from PySpark / Scala Spark patterns.
    - Map data lineage: source → transform → sink.
    - Generate Mermaid data flow diagram.
    - Produce "Data Pipeline" documentation section.

    Signals detected: ``airflow``, ``dbt``, ``spark``, ``warehouse``.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(role=AgentRole.DATA_ENGINEERING, model=model)

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

        # 1. Detect data engineering components
        components = self._detect_components(repo_profile)

        # 2. Generate data lineage diagram
        mermaid_spec = self._build_lineage_diagram(components)
        artifacts["data_lineage_mermaid"] = mermaid_spec

        # 3. Produce data pipeline section (LLM or template)
        if use_llm:
            try:
                section_md = await self._build_data_section_llm(
                    components=components,
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                )
            except Exception:
                section_md = self._build_data_section(
                    components=components, repo_name=repo_profile.repo_name,
                )
        else:
            section_md = self._build_data_section(
                components=components, repo_name=repo_profile.repo_name,
            )
        artifacts["data_pipeline_md"] = section_md
        artifacts["data_components"] = components

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts=artifacts,
            duration_ms=duration,
            metadata={"component_count": len(components)},
        )

    # -- Internal -----------------------------------------------------------

    def _detect_components(
        self, profile: RepoProfile
    ) -> list[dict[str, Any]]:
        """Detect data engineering components from signals and file tree.

        TODO: Parse actual DAG files, dbt_project.yml, Spark configs.
        """
        components: list[dict[str, Any]] = []
        signal_types = {s.signal_type for s in profile.signals}

        if "airflow" in signal_types:
            components.append({
                "type": "orchestrator",
                "tech": "airflow",
                "name": "Apache Airflow",
            })
        if "dbt" in signal_types:
            components.append({
                "type": "transform",
                "tech": "dbt",
                "name": "dbt Models",
            })
        if "spark" in signal_types:
            components.append({
                "type": "compute",
                "tech": "spark",
                "name": "Apache Spark",
            })
        if "warehouse" in signal_types:
            components.append({
                "type": "storage",
                "tech": "warehouse",
                "name": "Data Warehouse",
            })

        # Detect from file tree
        for path in profile.file_tree:
            if "dags/" in path and path.endswith(".py"):
                components.append({
                    "type": "dag",
                    "tech": "airflow",
                    "name": f"DAG: {path.split('/')[-1]}",
                    "source": path,
                })

        return components

    def _build_lineage_diagram(
        self, components: list[dict[str, Any]]
    ) -> str:
        """Generate a Mermaid data lineage diagram."""
        lines = ["graph LR"]
        lines.append('    Sources["Data Sources"]')
        lines.append('    Landing["Landing Zone"]')
        lines.append('    Sources --> Landing')

        has_transform = any(c["type"] == "transform" for c in components)
        has_compute = any(c["type"] == "compute" for c in components)
        has_warehouse = any(c["type"] == "storage" for c in components)

        if has_transform:
            lines.append('    Transform["dbt Transform"]')
            lines.append('    Landing --> Transform')
        if has_compute:
            lines.append('    Spark["Spark Processing"]')
            prev = "Transform" if has_transform else "Landing"
            lines.append(f'    {prev} --> Spark')
        if has_warehouse:
            prev = "Spark" if has_compute else ("Transform" if has_transform else "Landing")
            lines.append('    Warehouse["Data Warehouse"]')
            lines.append(f'    {prev} --> Warehouse')
            lines.append('    Warehouse --> Analytics["Analytics / BI"]')

        return "\n".join(lines)

    async def _build_data_section_llm(
        self,
        components: list[dict[str, Any]],
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
    ) -> str:
        """Use LLM to generate rich data pipeline documentation."""
        comp_desc = ", ".join(f"{c['name']} ({c['tech']})" for c in components)
        entities = ", ".join(e.name for e in knowledge_graph.entities[:15])

        return await chat_text(
            system=(
                "You are a data engineering documentation specialist. Write a "
                "detailed Markdown section about the data pipeline. Include "
                "data sources, transformations, lineage, partitioning, SLAs, "
                "and monitoring. Use ## headers. Be specific to detected components."
            ),
            user=(
                f"Repository: {repo_profile.repo_name}\n"
                f"Description: {repo_profile.description[:300]}\n"
                f"Data components: {comp_desc}\n"
                f"KG entities: {entities}\n\n"
                f"Write detailed data pipeline documentation."
            ),
            model=self.model,
            max_tokens=1500,
        )

    def _build_data_section(
        self,
        components: list[dict[str, Any]],
        repo_name: str,
    ) -> str:
        """Generate Markdown data pipeline section."""
        lines = [
            f"## Data Pipeline — {repo_name}",
            "",
            f"This repository includes **{len(components)}** data component(s):",
            "",
        ]
        for comp in components:
            source = comp.get("source", "")
            suffix = f" — `{source}`" if source else ""
            lines.append(f"- **{comp['name']}** ({comp['tech']}, {comp['type']}){suffix}")

        lines.append("")
        lines.append("### Data Lineage")
        lines.append("")
        lines.append(
            "TODO: Document data sources, transformation logic, "
            "partitioning strategy, and SLAs."
        )
        return "\n".join(lines)
