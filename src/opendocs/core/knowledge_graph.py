"""Knowledge Graph models for semantic document representation.

These models capture *typed semantic entities* and their *relationships*
extracted from README content — the core IP of opendocs.

The KG sits between the parser and generators:

    Markdown → DocumentModel → KnowledgeGraph → Generators
                 (syntax)        (semantics)     (output)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Entity types
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    """Classification of extracted entities."""

    PROJECT = "project"
    COMPONENT = "component"
    TECHNOLOGY = "technology"
    PROTOCOL = "protocol"
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    CLOUD_SERVICE = "cloud_service"
    API_ENDPOINT = "api_endpoint"
    METRIC = "metric"
    CONFIGURATION = "configuration"
    PREREQUISITE = "prerequisite"
    HARDWARE = "hardware"
    PERSON_ORG = "person_org"
    LICENSE_TYPE = "license"
    FEATURE = "feature"
    PLATFORM = "platform"


# ---------------------------------------------------------------------------
# Relation types
# ---------------------------------------------------------------------------

class RelationType(str, Enum):
    """Types of relationships between entities."""

    USES = "uses"
    CONNECTS_TO = "connects_to"
    EXPOSES = "exposes"
    REQUIRES = "requires"
    STORES_IN = "stores_in"
    COMMUNICATES_VIA = "communicates_via"
    DEPENDS_ON = "depends_on"
    RUNS_ON = "runs_on"
    LICENSED_UNDER = "licensed_under"
    PROVIDES = "provides"
    MEASURES = "measures"
    CONFIGURED_BY = "configured_by"
    INTEGRATES_WITH = "integrates_with"
    PART_OF = "part_of"


# ---------------------------------------------------------------------------
# Core KG models
# ---------------------------------------------------------------------------

class Entity(BaseModel):
    """A semantic entity extracted from the README."""

    id: str
    name: str
    entity_type: EntityType
    properties: dict[str, Any] = Field(default_factory=dict)
    source_section: str = ""
    source_text: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extraction_method: str = "deterministic"  # "deterministic" | "llm"

    def __hash__(self) -> int:
        return hash(self.id)


class Relation(BaseModel):
    """A directed relationship between two entities."""

    source_id: str
    target_id: str
    relation_type: RelationType
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extraction_method: str = "deterministic"

    @property
    def key(self) -> str:
        return f"{self.source_id}--{self.relation_type.value}-->{self.target_id}"


class KnowledgeGraph(BaseModel):
    """The semantic knowledge graph extracted from a README.

    Contains typed entities and their relationships, forming a
    structured representation of the project's architecture,
    tech stack, APIs, metrics, and dependencies.
    """

    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    summary: str = ""
    executive_summary: str = ""
    stakeholder_summaries: dict[str, str] = Field(default_factory=dict)
    extraction_stats: dict[str, int] = Field(default_factory=dict)

    # -- Query helpers ---------------------------------------------------

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Find an entity by ID."""
        for e in self.entities:
            if e.id == entity_id:
                return e
        return None

    def entities_of_type(self, entity_type: EntityType) -> list[Entity]:
        """Return all entities of a given type."""
        return [e for e in self.entities if e.entity_type == entity_type]

    def relations_from(self, entity_id: str) -> list[Relation]:
        """Return all relations originating from an entity."""
        return [r for r in self.relations if r.source_id == entity_id]

    def relations_to(self, entity_id: str) -> list[Relation]:
        """Return all relations pointing to an entity."""
        return [r for r in self.relations if r.target_id == entity_id]

    def neighbors(self, entity_id: str) -> list[Entity]:
        """Return all entities connected to a given entity."""
        connected_ids = set()
        for r in self.relations:
            if r.source_id == entity_id:
                connected_ids.add(r.target_id)
            elif r.target_id == entity_id:
                connected_ids.add(r.source_id)
        return [e for e in self.entities if e.id in connected_ids]

    def add_entity(self, entity: Entity) -> None:
        """Add entity if not already present (by ID)."""
        existing_ids = {e.id for e in self.entities}
        if entity.id not in existing_ids:
            self.entities.append(entity)

    def add_relation(self, relation: Relation) -> None:
        """Add relation if not duplicate."""
        existing_keys = {r.key for r in self.relations}
        if relation.key not in existing_keys:
            self.relations.append(relation)

    def merge(self, other: KnowledgeGraph) -> None:
        """Merge another KG into this one (deduplicating)."""
        for e in other.entities:
            self.add_entity(e)
        for r in other.relations:
            self.add_relation(r)

    def to_mermaid(self, *, max_entities: int = 0) -> str:
        """Export the knowledge graph as an architecture-style Mermaid diagram.

        Groups entities by type into subgraphs and shows only the most
        meaningful architectural relations.

        Parameters
        ----------
        max_entities
            If > 0, only include the *N* highest-confidence entities
            (and relations between them).  ``0`` means include all.
        """
        entities = self.entities
        if max_entities > 0 and len(entities) > max_entities:
            entities = sorted(
                entities, key=lambda e: e.confidence, reverse=True
            )[:max_entities]

        valid_ids = {e.id for e in entities}

        # Group entities by type
        groups: dict[str, list[Entity]] = {}
        for e in entities:
            label = e.entity_type.value.replace("_", " ").title()
            groups.setdefault(label, []).append(e)

        # Architectural group ordering (most important first)
        type_order = [
            "Project", "Component", "Feature", "Framework",
            "Technology", "Language", "Cloud Service", "Platform",
            "Database", "Api Endpoint", "Protocol", "Configuration",
            "Metric", "Hardware", "Person Org", "License",
            "Prerequisite",
        ]

        lines = ["graph LR"]

        # Subgraphs per entity type
        for type_label in type_order:
            ents = groups.pop(type_label, [])
            if not ents:
                continue
            safe_sg = type_label.replace(" ", "_")
            lines.append(f"    subgraph {safe_sg}[\"{type_label}\"]")
            for e in ents[:8]:  # cap per group for readability
                safe_id = e.id.replace("-", "_").replace(" ", "_")
                safe_name = e.name.replace('"', "'")
                lines.append(f'        {safe_id}["{safe_name}"]')
            lines.append("    end")

        # Any remaining types
        for type_label, ents in groups.items():
            if not ents:
                continue
            safe_sg = type_label.replace(" ", "_")
            lines.append(f"    subgraph {safe_sg}[\"{type_label}\"]")
            for e in ents[:8]:
                safe_id = e.id.replace("-", "_").replace(" ", "_")
                safe_name = e.name.replace('"', "'")
                lines.append(f'        {safe_id}["{safe_name}"]')
            lines.append("    end")

        # Edges — only between included nodes, deduplicate
        seen_edges: set[str] = set()
        for r in self.relations:
            if r.source_id in valid_ids and r.target_id in valid_ids:
                src = r.source_id.replace("-", "_").replace(" ", "_")
                tgt = r.target_id.replace("-", "_").replace(" ", "_")
                edge_key = f"{src}->{tgt}"
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    label = r.relation_type.value.replace("_", " ")
                    lines.append(f"    {src} -->|{label}| {tgt}")

        return "\n".join(lines)

    def compute_stats(self) -> dict[str, int]:
        """Compute and cache extraction statistics."""
        stats: dict[str, int] = {
            "total_entities": len(self.entities),
            "total_relations": len(self.relations),
        }
        for et in EntityType:
            count = len(self.entities_of_type(et))
            if count > 0:
                stats[f"entities_{et.value}"] = count
        deterministic = sum(1 for e in self.entities if e.extraction_method == "deterministic")
        llm_count = sum(1 for e in self.entities if e.extraction_method == "llm")
        stats["deterministic_entities"] = deterministic
        stats["llm_entities"] = llm_count
        self.extraction_stats = stats
        return stats
