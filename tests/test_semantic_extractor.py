"""Tests for the Semantic Extractor."""

from __future__ import annotations

from pathlib import Path

import pytest

from opendocs.core.parser import ReadmeParser
from opendocs.core.semantic_extractor import SemanticExtractor


@pytest.fixture
def sample_doc():
    """Parse the sample README for extraction tests."""
    sample_path = Path(__file__).parent.parent / "examples" / "sample_readme.md"
    content = sample_path.read_text(encoding="utf-8")
    parser = ReadmeParser()
    return parser.parse(
        content,
        repo_name="SmartTemp",
        repo_url="https://github.com/test/smarttemp",
    )


class TestSemanticExtractor:
    def test_extract_produces_non_empty_graph(self, sample_doc):
        extractor = SemanticExtractor()
        kg = extractor.extract(sample_doc)
        assert len(kg.entities) > 0
        assert len(kg.relations) > 0

    def test_project_entity_extracted(self, sample_doc):
        from opendocs.core.knowledge_graph import EntityType

        extractor = SemanticExtractor()
        kg = extractor.extract(sample_doc)
        projects = kg.entities_of_type(EntityType.PROJECT)
        assert len(projects) == 1
        assert projects[0].name == "SmartTemp"

    def test_technologies_discovered(self, sample_doc):
        """The sample README mentions Python, MQTT, etc."""
        from opendocs.core.knowledge_graph import EntityType

        extractor = SemanticExtractor()
        kg = extractor.extract(sample_doc)
        names = {e.name.lower() for e in kg.entities}
        # The sample README should mention at least Python
        assert "python" in names or any("python" in n for n in names)

    def test_extraction_stats(self, sample_doc):
        extractor = SemanticExtractor()
        kg = extractor.extract(sample_doc)
        stats = kg.compute_stats()
        assert stats["total_entities"] >= 1
        assert "deterministic_entities" in stats

    def test_all_entities_are_deterministic(self, sample_doc):
        """Without LLM, all entities should be deterministic."""
        extractor = SemanticExtractor()
        kg = extractor.extract(sample_doc)
        for entity in kg.entities:
            assert entity.extraction_method == "deterministic"

    def test_relations_reference_existing_entities(self, sample_doc):
        """Every relation should point to entities that exist in the graph."""
        extractor = SemanticExtractor()
        kg = extractor.extract(sample_doc)
        entity_ids = {e.id for e in kg.entities}
        for rel in kg.relations:
            assert rel.source_id in entity_ids, f"Dangling source: {rel.source_id}"
            assert rel.target_id in entity_ids, f"Dangling target: {rel.target_id}"
