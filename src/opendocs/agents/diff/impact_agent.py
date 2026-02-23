"""ImpactAgent — map file diffs to knowledge-graph deltas.

Takes a ``DiffSummary`` from the DiffAgent and determines which KG
entities and relations are affected. Produces an ``ImpactReport``
with lists of nodes/edges to add, update, or remove.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..base import AgentBase, AgentPlan, AgentResult, AgentRole, RepoProfile
from ...core.knowledge_graph import Entity, KnowledgeGraph, Relation
from ...core.models import DocumentModel
from .diff_agent import DiffSummary


class DeltaKind(str, Enum):
    """Type of change to a KG element."""
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"


@dataclass
class EntityDelta:
    """A planned change to a KG entity."""
    entity_id: str
    kind: DeltaKind
    entity_name: str = ""
    reason: str = ""
    affected_files: list[str] = field(default_factory=list)


@dataclass
class RelationDelta:
    """A planned change to a KG relation."""
    source_id: str
    target_id: str
    kind: DeltaKind
    relation_type: str = ""
    reason: str = ""


@dataclass
class ImpactReport:
    """The impact of a diff on the knowledge graph."""
    entity_deltas: list[EntityDelta] = field(default_factory=list)
    relation_deltas: list[RelationDelta] = field(default_factory=list)
    impacted_output_formats: list[str] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def total_deltas(self) -> int:
        return len(self.entity_deltas) + len(self.relation_deltas)


class ImpactAgent(AgentBase):
    """Maps file-level diffs to KG-level impact.

    For each changed file, the agent:
    1. Finds KG entities referencing that file (via source_file / file_path).
    2. Determines if the entity should be added, updated, or removed.
    3. Traces downstream relations to find transitive impact.
    4. Identifies which output formats are affected.
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
        diff_summary: DiffSummary | None = None,
        **kwargs: Any,
    ) -> AgentResult:
        t0 = time.perf_counter()

        if diff_summary is None:
            # Try to extract from prior results
            diff_summary = self._extract_diff_summary(prior_results)
            if diff_summary is None:
                return self._make_result(
                    success=False,
                    errors=["No DiffSummary provided or found in prior results"],
                )

        report = self._compute_impact(
            diff_summary=diff_summary,
            knowledge_graph=knowledge_graph,
        )

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=True,
            artifacts={
                "impact_report": {
                    "entity_deltas": [
                        {"id": d.entity_id, "kind": d.kind.value, "reason": d.reason}
                        for d in report.entity_deltas
                    ],
                    "relation_deltas": [
                        {"src": d.source_id, "tgt": d.target_id, "kind": d.kind.value}
                        for d in report.relation_deltas
                    ],
                    "impacted_formats": report.impacted_output_formats,
                    "total_deltas": report.total_deltas,
                    "confidence": report.confidence,
                }
            },
            duration_ms=duration,
        )

    # -- Internal -----------------------------------------------------------

    def _compute_impact(
        self,
        *,
        diff_summary: DiffSummary,
        knowledge_graph: KnowledgeGraph,
    ) -> ImpactReport:
        """Deterministic impact analysis based on file-to-entity mapping.

        TODO: Enhance with LLM-based semantic impact analysis for
              changes that don't directly map to KG entities.
        """
        entity_deltas: list[EntityDelta] = []
        relation_deltas: list[RelationDelta] = []
        impacted_formats: set[str] = set()

        # Build file → entity index
        file_to_entities: dict[str, list[Entity]] = {}
        for entity in knowledge_graph.entities:
            for attr_key in ("source_file", "file_path", "path"):
                val = entity.properties.get(attr_key, "")
                if val:
                    file_to_entities.setdefault(val, []).append(entity)

        # Map each changed file to affected entities
        for fd in diff_summary.file_diffs:
            matching_entities = file_to_entities.get(fd.path, [])
            for entity in matching_entities:
                if fd.status == "deleted":
                    kind = DeltaKind.REMOVE
                elif fd.status == "added":
                    kind = DeltaKind.ADD
                else:
                    kind = DeltaKind.UPDATE

                entity_deltas.append(EntityDelta(
                    entity_id=entity.id,
                    kind=kind,
                    entity_name=entity.name,
                    reason=f"File {fd.path} was {fd.status}",
                    affected_files=[fd.path],
                ))

            # If a changed file has no KG entity, it might be new → ADD
            if not matching_entities and fd.status == "added":
                entity_deltas.append(EntityDelta(
                    entity_id=f"new:{fd.path}",
                    kind=DeltaKind.ADD,
                    entity_name=fd.path,
                    reason=f"New file {fd.path} has no KG entity yet",
                    affected_files=[fd.path],
                ))

        # Trace downstream relations
        affected_entity_ids = {d.entity_id for d in entity_deltas}
        for relation in knowledge_graph.relations:
            if relation.source_id in affected_entity_ids or relation.target_id in affected_entity_ids:
                relation_deltas.append(RelationDelta(
                    source_id=relation.source_id,
                    target_id=relation.target_id,
                    kind=DeltaKind.UPDATE,
                    relation_type=relation.relation_type.value if hasattr(relation.relation_type, 'value') else str(relation.relation_type),
                    reason="Connected entity was modified",
                ))

        # All formats potentially impacted if any entity changed
        if entity_deltas:
            impacted_formats = {"WORD", "PPTX", "PDF", "BLOG", "LATEX"}

        confidence = 0.9 if entity_deltas else 0.5

        return ImpactReport(
            entity_deltas=entity_deltas,
            relation_deltas=relation_deltas,
            impacted_output_formats=sorted(impacted_formats),
            confidence=confidence,
        )

    def _extract_diff_summary(
        self, prior_results: list[AgentResult] | None
    ) -> DiffSummary | None:
        """Try to find a DiffSummary in prior results."""
        if not prior_results:
            return None
        for result in prior_results:
            ds = result.artifacts.get("diff_summary")
            if ds and isinstance(ds, dict):
                return DiffSummary(
                    base_ref=ds.get("base_ref", ""),
                    head_ref=ds.get("head_ref", ""),
                    total_files=ds.get("total_files", 0),
                    total_additions=ds.get("total_additions", 0),
                    total_deletions=ds.get("total_deletions", 0),
                )
        return None
