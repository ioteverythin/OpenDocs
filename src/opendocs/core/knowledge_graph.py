"""Knowledge Graph models for semantic document representation.

These models capture *typed semantic entities* and their *relationships*
extracted from README content — the core IP of opendocs.

The KG sits between the parser and generators:

    Markdown → DocumentModel → KnowledgeGraph → Generators
                 (syntax)        (semantics)     (output)
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
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

    @property
    def provenance(self) -> str:
        """Return a Graphify-style provenance label.

        - EXTRACTED: deterministic, high-confidence findings
        - INFERRED: LLM-derived, with a confidence score
        - AMBIGUOUS: low-confidence findings flagged for review
        """
        if self.confidence < 0.5:
            return "AMBIGUOUS"
        if self.extraction_method == "llm":
            return "INFERRED"
        return "EXTRACTED"

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
    def provenance(self) -> str:
        """Return a Graphify-style provenance label."""
        if self.confidence < 0.5:
            return "AMBIGUOUS"
        if self.extraction_method == "llm":
            return "INFERRED"
        return "EXTRACTED"

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

    # -- Community detection results ------------------------------------
    communities: dict[str, int] = Field(default_factory=dict)  # entity_id -> community_id

    # -- LLM-enhanced content (populated by LLMContentEnhancer) ----------
    llm_blog: str = ""  # Full blog post prose
    llm_faq: list[dict[str, str]] = Field(default_factory=list)  # [{q:, a:}]
    llm_sections: dict[str, str] = Field(default_factory=dict)  # title -> rewritten prose

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
            entities = sorted(entities, key=lambda e: e.confidence, reverse=True)[:max_entities]

        valid_ids = {e.id for e in entities}

        # Group entities by type
        groups: dict[str, list[Entity]] = {}
        for e in entities:
            label = e.entity_type.value.replace("_", " ").title()
            groups.setdefault(label, []).append(e)

        # Architectural group ordering (most important first)
        type_order = [
            "Project",
            "Component",
            "Feature",
            "Framework",
            "Technology",
            "Language",
            "Cloud Service",
            "Platform",
            "Database",
            "Api Endpoint",
            "Protocol",
            "Configuration",
            "Metric",
            "Hardware",
            "Person Org",
            "License",
            "Prerequisite",
        ]

        lines = ["graph LR"]

        # Subgraphs per entity type
        for type_label in type_order:
            ents = groups.pop(type_label, [])
            if not ents:
                continue
            safe_sg = type_label.replace(" ", "_")
            lines.append(f'    subgraph {safe_sg}["{type_label}"]')
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
            lines.append(f'    subgraph {safe_sg}["{type_label}"]')
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

    # -- Graph analysis --------------------------------------------------

    def node_degrees(self) -> dict[str, int]:
        """Return the degree (in + out edges) of every entity."""
        deg: dict[str, int] = {e.id: 0 for e in self.entities}
        for r in self.relations:
            deg[r.source_id] = deg.get(r.source_id, 0) + 1
            deg[r.target_id] = deg.get(r.target_id, 0) + 1
        return deg

    def god_nodes(self, top_n: int = 5) -> list[tuple[Entity, int]]:
        """Return the *top_n* highest-degree entities (god nodes).

        A god node is a concept that everything connects through.
        """
        degrees = self.node_degrees()
        ranked = sorted(degrees.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        result: list[tuple[Entity, int]] = []
        for eid, deg in ranked:
            ent = self.get_entity(eid)
            if ent:
                result.append((ent, deg))
        return result

    def surprising_connections(self, top_n: int = 5) -> list[tuple[float, Relation]]:
        """Find cross-type edges ranked by a surprise score.

        Edges linking different entity types are more surprising.
        Lower confidence further boosts the surprise score.
        """
        scored: list[tuple[float, Relation]] = []
        for r in self.relations:
            src = self.get_entity(r.source_id)
            tgt = self.get_entity(r.target_id)
            if not src or not tgt:
                continue
            if src.entity_type == tgt.entity_type:
                continue
            score = (1.0 - r.confidence) + 0.3
            scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_n]

    # -- Community detection ---------------------------------------------

    def detect_communities(self, max_iterations: int = 50) -> dict[str, int]:
        """Detect communities using label propagation.

        A lightweight, dependency-free community detection algorithm.
        Each node starts in its own community, then iteratively adopts
        the most common community among its neighbours.  Converges
        when no labels change.

        Returns
        -------
        dict[str, int]
            Mapping of entity ID to community ID (0-indexed).
        """
        if not self.entities:
            self.communities = {}
            return self.communities

        # Build adjacency list
        adj: dict[str, list[str]] = defaultdict(list)
        for r in self.relations:
            adj[r.source_id].append(r.target_id)
            adj[r.target_id].append(r.source_id)

        # Initialise: each node in its own community
        labels: dict[str, int] = {e.id: i for i, e in enumerate(self.entities)}
        ids = [e.id for e in self.entities]

        for _ in range(max_iterations):
            changed = False
            random.shuffle(ids)  # randomised order for convergence
            for nid in ids:
                nbrs = adj.get(nid, [])
                if not nbrs:
                    continue
                # Most common label among neighbours
                counts: Counter[int] = Counter(labels[n] for n in nbrs if n in labels)
                if not counts:
                    continue
                best_label = counts.most_common(1)[0][0]
                if labels[nid] != best_label:
                    labels[nid] = best_label
                    changed = True
            if not changed:
                break

        # Renumber communities to 0..N-1
        unique = sorted(set(labels.values()))
        remap = {old: new for new, old in enumerate(unique)}
        self.communities = {nid: remap[lbl] for nid, lbl in labels.items()}
        return self.communities

    def community_members(self, community_id: int) -> list[Entity]:
        """Return all entities belonging to a community."""
        member_ids = {eid for eid, cid in self.communities.items() if cid == community_id}
        return [e for e in self.entities if e.id in member_ids]

    def community_summary(self) -> list[dict[str, Any]]:
        """Return a list of community summaries.

        Each dict contains: id, size, members (entity names),
        dominant_type, and internal_edges count.
        """
        if not self.communities:
            self.detect_communities()

        num_communities = max(self.communities.values(), default=-1) + 1
        summaries = []
        for cid in range(num_communities):
            members = self.community_members(cid)
            if not members:
                continue
            # Dominant entity type
            type_counts: Counter[str] = Counter(e.entity_type.value for e in members)
            dominant = type_counts.most_common(1)[0][0] if type_counts else "unknown"
            # Internal edges
            member_ids = {e.id for e in members}
            internal = sum(1 for r in self.relations if r.source_id in member_ids and r.target_id in member_ids)
            summaries.append(
                {
                    "id": cid,
                    "size": len(members),
                    "members": [e.name for e in members],
                    "dominant_type": dominant.replace("_", " ").title(),
                    "internal_edges": internal,
                }
            )
        return summaries

    # -- Suggested questions ---------------------------------------------

    def suggested_questions(self, top_n: int = 5) -> list[str]:
        """Generate questions the graph is well-positioned to answer.

        Uses structural signals (god nodes, communities, cross-type
        edges) to formulate insightful questions about the project.
        """
        questions: list[str] = []

        # God-node questions
        gods = self.god_nodes(top_n=3)
        for ent, deg in gods:
            questions.append(
                f"What role does {ent.name} play in the architecture, and why do {deg} other concepts depend on it?"
            )

        # Community questions
        if not self.communities:
            self.detect_communities()
        summaries = self.community_summary()
        if len(summaries) >= 2:
            biggest = max(summaries, key=lambda s: s["size"])
            questions.append(
                f"What holds the {biggest['dominant_type']}-dominated cluster "
                f"({biggest['size']} entities) together, and could it be split?"
            )

        # Cross-type surprise questions
        surprises = self.surprising_connections(top_n=2)
        for _score, rel in surprises:
            src = self.get_entity(rel.source_id)
            tgt = self.get_entity(rel.target_id)
            if src and tgt:
                questions.append(
                    f"Why does {src.name} ({src.entity_type.value.replace('_', ' ')}) "
                    f"connect to {tgt.name} ({tgt.entity_type.value.replace('_', ' ')})?"
                )

        # Provenance question
        ambiguous = [e for e in self.entities if e.provenance == "AMBIGUOUS"]
        if ambiguous:
            questions.append(
                f"Are the {len(ambiguous)} ambiguous entities (e.g. {ambiguous[0].name}) correctly classified?"
            )

        return questions[:top_n]
