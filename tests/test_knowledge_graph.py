"""Tests for the Knowledge Graph module."""

from __future__ import annotations

import pytest

from opendocs.core.knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relation,
    RelationType,
)


@pytest.fixture
def sample_kg():
    """Build a small KnowledgeGraph for testing."""
    kg = KnowledgeGraph()

    kg.add_entity(Entity(
        id="proj-1",
        name="SmartTemp",
        entity_type=EntityType.PROJECT,
        confidence=1.0,
        extraction_method="deterministic",
    ))
    kg.add_entity(Entity(
        id="tech-python",
        name="Python",
        entity_type=EntityType.LANGUAGE,
        confidence=0.9,
        extraction_method="deterministic",
    ))
    kg.add_entity(Entity(
        id="tech-mqtt",
        name="MQTT",
        entity_type=EntityType.PROTOCOL,
        confidence=0.85,
        extraction_method="deterministic",
    ))
    kg.add_entity(Entity(
        id="db-influx",
        name="InfluxDB",
        entity_type=EntityType.DATABASE,
        confidence=0.75,
        extraction_method="llm",
    ))

    kg.add_relation(Relation(
        source_id="proj-1",
        target_id="tech-python",
        relation_type=RelationType.USES,
        confidence=0.9,
    ))
    kg.add_relation(Relation(
        source_id="proj-1",
        target_id="tech-mqtt",
        relation_type=RelationType.COMMUNICATES_VIA,
        confidence=0.85,
    ))
    kg.add_relation(Relation(
        source_id="proj-1",
        target_id="db-influx",
        relation_type=RelationType.STORES_IN,
        confidence=0.75,
    ))

    return kg


class TestKnowledgeGraph:
    def test_add_entity(self, sample_kg: KnowledgeGraph):
        assert len(sample_kg.entities) == 4

    def test_get_entity(self, sample_kg: KnowledgeGraph):
        e = sample_kg.get_entity("proj-1")
        assert e is not None
        assert e.name == "SmartTemp"

    def test_get_entity_missing(self, sample_kg: KnowledgeGraph):
        assert sample_kg.get_entity("nonexistent") is None

    def test_entities_of_type(self, sample_kg: KnowledgeGraph):
        langs = sample_kg.entities_of_type(EntityType.LANGUAGE)
        assert len(langs) == 1
        assert langs[0].name == "Python"

    def test_relations_from(self, sample_kg: KnowledgeGraph):
        rels = sample_kg.relations_from("proj-1")
        assert len(rels) == 3

    def test_relations_to(self, sample_kg: KnowledgeGraph):
        rels = sample_kg.relations_to("tech-python")
        assert len(rels) == 1
        assert rels[0].relation_type == RelationType.USES

    def test_neighbors(self, sample_kg: KnowledgeGraph):
        n = sample_kg.neighbors("proj-1")
        assert len(n) == 3
        names = {e.name for e in n}
        assert "Python" in names
        assert "MQTT" in names
        assert "InfluxDB" in names

    def test_compute_stats(self, sample_kg: KnowledgeGraph):
        stats = sample_kg.compute_stats()
        assert stats["total_entities"] == 4
        assert stats["total_relations"] == 3
        assert stats["deterministic_entities"] == 3
        assert stats["llm_entities"] == 1

    def test_to_mermaid(self, sample_kg: KnowledgeGraph):
        mermaid = sample_kg.to_mermaid()
        assert mermaid.startswith("graph LR")
        assert "SmartTemp" in mermaid
        assert "subgraph" in mermaid

    def test_merge(self, sample_kg: KnowledgeGraph):
        other = KnowledgeGraph()
        other.add_entity(Entity(
            id="tech-docker",
            name="Docker",
            entity_type=EntityType.PLATFORM,
            confidence=0.8,
            extraction_method="llm",
        ))
        other.add_relation(Relation(
            source_id="proj-1",
            target_id="tech-docker",
            relation_type=RelationType.RUNS_ON,
            confidence=0.8,
        ))

        sample_kg.merge(other)
        assert len(sample_kg.entities) == 5
        assert len(sample_kg.relations) == 4
        assert sample_kg.get_entity("tech-docker") is not None
