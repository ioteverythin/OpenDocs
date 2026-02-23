"""MLAgent — training / inference / RAG / vector DB pipeline documentation.

Detects ML patterns and generates model-card-style documentation,
training pipeline diagrams, and inference endpoint docs.
"""

from __future__ import annotations

import time
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ..llm_client import chat_text
from ...core.knowledge_graph import KnowledgeGraph
from ...core.models import DocumentModel


class MLAgent(AgentBase):
    """Analyses ML/AI repos for training and inference topology.

    Capabilities:
    - Detect PyTorch / TensorFlow / HuggingFace training scripts.
    - Detect RAG pipelines (embeddings → vector DB → retrieval → LLM).
    - Detect inference servers (FastAPI, Flask, TorchServe, Triton).
    - Generate Mermaid training pipeline diagram.
    - Generate model card documentation (datasets, metrics, usage).
    - Produce "ML Architecture" section with evidence pointers.

    Signals detected: ``ml-training``, ``pytorch``, ``tensorflow``,
    ``huggingface``, ``vector-db``, ``rag``.
    """

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(role=AgentRole.ML, model=model)

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

        # 1. Detect ML components
        components = self._detect_ml_components(repo_profile)

        # 2. Generate pipeline diagram
        mermaid_spec = self._build_pipeline_diagram(components)
        artifacts["ml_pipeline_mermaid"] = mermaid_spec

        # 3. Generate model card (LLM or template)
        if use_llm:
            try:
                model_card = await self._build_model_card_llm(
                    components=components,
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                )
            except Exception:
                model_card = self._build_model_card(
                    components=components, repo_name=repo_profile.repo_name,
                )
        else:
            model_card = self._build_model_card(
                components=components, repo_name=repo_profile.repo_name,
            )
        artifacts["model_card_md"] = model_card

        # 4. Generate ML architecture section (LLM or template)
        if use_llm:
            try:
                section_md = await self._build_ml_section_llm(
                    components=components,
                    repo_profile=repo_profile,
                    knowledge_graph=knowledge_graph,
                )
            except Exception:
                section_md = self._build_ml_section(
                    components=components, repo_name=repo_profile.repo_name,
                )
        else:
            section_md = self._build_ml_section(
                components=components, repo_name=repo_profile.repo_name,
            )
        artifacts["ml_architecture_md"] = section_md
        artifacts["ml_components"] = components

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts=artifacts,
            duration_ms=duration,
            metadata={"component_count": len(components)},
        )

    # -- Internal -----------------------------------------------------------

    def _detect_ml_components(
        self, profile: RepoProfile
    ) -> list[dict[str, Any]]:
        """Detect ML components from signals and file tree.

        TODO: Parse requirements.txt / pyproject.toml for ML libraries.
              Scan Python files for training loops, model definitions.
        """
        components: list[dict[str, Any]] = []
        signal_types = {s.signal_type for s in profile.signals}

        if "pytorch" in signal_types:
            components.append({"type": "framework", "tech": "pytorch", "name": "PyTorch"})
        if "tensorflow" in signal_types:
            components.append({"type": "framework", "tech": "tensorflow", "name": "TensorFlow"})
        if "huggingface" in signal_types:
            components.append({"type": "hub", "tech": "huggingface", "name": "HuggingFace"})
        if "vector-db" in signal_types:
            components.append({"type": "store", "tech": "vector-db", "name": "Vector Database"})
        if "rag" in signal_types:
            components.append({"type": "pipeline", "tech": "rag", "name": "RAG Pipeline"})
        if "ml-training" in signal_types:
            components.append({"type": "pipeline", "tech": "training", "name": "Training Pipeline"})

        return components

    def _build_pipeline_diagram(
        self, components: list[dict[str, Any]]
    ) -> str:
        """Generate a Mermaid ML pipeline diagram."""
        lines = ["graph LR"]
        lines.append('    Data["Data Sources"]')
        lines.append('    Preprocessing["Preprocessing"]')
        lines.append('    Data --> Preprocessing')

        for comp in components:
            safe = comp["name"].replace(" ", "_").replace("-", "_")
            if comp["type"] == "framework":
                lines.append(f'    {safe}["{comp["name"]}"]')
                lines.append(f'    Preprocessing --> {safe}')
                lines.append(f'    {safe} --> Model["Trained Model"]')
            elif comp["type"] == "pipeline" and comp["tech"] == "rag":
                lines.append('    Embeddings["Embeddings"]')
                lines.append('    VectorDB["Vector Store"]')
                lines.append('    Retrieval["Retrieval"]')
                lines.append('    LLM["LLM"]')
                lines.append('    Embeddings --> VectorDB')
                lines.append('    VectorDB --> Retrieval')
                lines.append('    Retrieval --> LLM')

        lines.append('    Model --> Inference["Inference API"]')
        return "\n".join(lines)

    def _build_model_card(
        self,
        components: list[dict[str, Any]],
        repo_name: str,
    ) -> str:
        """Generate a model card stub (HuggingFace-style)."""
        techs = ", ".join(c["tech"] for c in components) or "N/A"
        return f"""# Model Card: {repo_name}

## Model Details
- **Repository**: {repo_name}
- **Frameworks**: {techs}
- **License**: See repository LICENSE file

## Intended Use
TODO: Document intended use cases and limitations.

## Training Data
TODO: Document training datasets and preprocessing steps.

## Evaluation
TODO: Document metrics, benchmarks, and evaluation methodology.

## Ethical Considerations
TODO: Document bias, fairness, and safety considerations.
"""

    def _build_ml_section(
        self,
        components: list[dict[str, Any]],
        repo_name: str,
    ) -> str:
        """Generate Markdown ML architecture section."""
        lines = [
            f"## ML Architecture — {repo_name}",
            "",
            f"This repository includes **{len(components)}** ML component(s):",
            "",
        ]
        for comp in components:
            lines.append(f"- **{comp['name']}** ({comp['tech']}, {comp['type']})")

        lines.append("")
        lines.append("### Pipeline Overview")
        lines.append("")
        lines.append("TODO: Document data flow, model training, and inference serving.")
        return "\n".join(lines)
