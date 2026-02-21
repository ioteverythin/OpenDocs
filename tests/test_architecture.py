"""Tests for the architecture diagram generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from opendocs.core.knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relation,
    RelationType,
)
from opendocs.core.parser import ReadmeParser
from opendocs.generators.architecture_generator import (
    ArchitectureGenerator,
    _build_data_flow,
    _build_dependency_tree,
    _build_deployment_view,
    _build_system_architecture,
    _build_tech_stack,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_doc():
    """Parse the sample README into a DocumentModel."""
    sample_path = Path(__file__).parent.parent / "examples" / "sample_readme.md"
    content = sample_path.read_text(encoding="utf-8")
    parser = ReadmeParser()
    return parser.parse(content, repo_name="SmartTemp", repo_url="https://github.com/test/smarttemp")


@pytest.fixture
def rich_kg():
    """Build a knowledge graph with enough variety to trigger all diagram types."""
    kg = KnowledgeGraph()

    # Project
    kg.add_entity(Entity(
        id="proj-smarttemp", name="SmartTemp",
        entity_type=EntityType.PROJECT, confidence=1.0,
    ))

    # Components
    kg.add_entity(Entity(
        id="comp-api", name="REST API",
        entity_type=EntityType.COMPONENT, confidence=0.95,
    ))
    kg.add_entity(Entity(
        id="comp-worker", name="Background Worker",
        entity_type=EntityType.COMPONENT, confidence=0.9,
    ))

    # Features
    kg.add_entity(Entity(
        id="feat-dashboard", name="Dashboard",
        entity_type=EntityType.FEATURE, confidence=0.85,
    ))
    kg.add_entity(Entity(
        id="feat-alerts", name="Real-time Alerts",
        entity_type=EntityType.FEATURE, confidence=0.8,
    ))

    # Languages
    kg.add_entity(Entity(
        id="lang-python", name="Python",
        entity_type=EntityType.LANGUAGE, confidence=0.95,
    ))
    kg.add_entity(Entity(
        id="lang-typescript", name="TypeScript",
        entity_type=EntityType.LANGUAGE, confidence=0.85,
    ))

    # Frameworks
    kg.add_entity(Entity(
        id="fw-flask", name="Flask",
        entity_type=EntityType.FRAMEWORK, confidence=0.9,
        properties={"category": "backend"},
    ))
    kg.add_entity(Entity(
        id="fw-react", name="React",
        entity_type=EntityType.FRAMEWORK, confidence=0.85,
        properties={"category": "frontend"},
    ))

    # Databases
    kg.add_entity(Entity(
        id="db-postgres", name="PostgreSQL",
        entity_type=EntityType.DATABASE, confidence=0.9,
    ))
    kg.add_entity(Entity(
        id="db-redis", name="Redis",
        entity_type=EntityType.DATABASE, confidence=0.8,
    ))

    # Cloud / Platform
    kg.add_entity(Entity(
        id="cloud-aws", name="AWS",
        entity_type=EntityType.CLOUD_SERVICE, confidence=0.85,
    ))
    kg.add_entity(Entity(
        id="plat-docker", name="Docker",
        entity_type=EntityType.PLATFORM, confidence=0.9,
    ))

    # API endpoint
    kg.add_entity(Entity(
        id="api-health", name="/api/health",
        entity_type=EntityType.API_ENDPOINT, confidence=0.7,
    ))

    # Protocol
    kg.add_entity(Entity(
        id="proto-mqtt", name="MQTT",
        entity_type=EntityType.PROTOCOL, confidence=0.8,
    ))

    # Hardware
    kg.add_entity(Entity(
        id="hw-rpi", name="Raspberry Pi",
        entity_type=EntityType.HARDWARE, confidence=0.75,
    ))

    # Prerequisites
    kg.add_entity(Entity(
        id="prereq-node", name="Node.js 18+",
        entity_type=EntityType.PREREQUISITE, confidence=0.8,
    ))

    # ── Relations ─────────────────────────────────────────────────────
    kg.add_relation(Relation(
        source_id="proj-smarttemp", target_id="lang-python",
        relation_type=RelationType.USES,
    ))
    kg.add_relation(Relation(
        source_id="proj-smarttemp", target_id="fw-flask",
        relation_type=RelationType.USES,
    ))
    kg.add_relation(Relation(
        source_id="proj-smarttemp", target_id="fw-react",
        relation_type=RelationType.USES,
    ))
    kg.add_relation(Relation(
        source_id="comp-api", target_id="db-postgres",
        relation_type=RelationType.STORES_IN,
    ))
    kg.add_relation(Relation(
        source_id="comp-api", target_id="db-redis",
        relation_type=RelationType.CONNECTS_TO,
    ))
    kg.add_relation(Relation(
        source_id="comp-worker", target_id="proto-mqtt",
        relation_type=RelationType.COMMUNICATES_VIA,
    ))
    kg.add_relation(Relation(
        source_id="proj-smarttemp", target_id="prereq-node",
        relation_type=RelationType.REQUIRES,
    ))
    kg.add_relation(Relation(
        source_id="proj-smarttemp", target_id="lang-python",
        relation_type=RelationType.DEPENDS_ON,
    ))
    kg.add_relation(Relation(
        source_id="comp-api", target_id="cloud-aws",
        relation_type=RelationType.RUNS_ON,
    ))
    kg.add_relation(Relation(
        source_id="comp-worker", target_id="plat-docker",
        relation_type=RelationType.RUNS_ON,
    ))
    kg.add_relation(Relation(
        source_id="comp-api", target_id="api-health",
        relation_type=RelationType.EXPOSES,
    ))
    kg.add_relation(Relation(
        source_id="proj-smarttemp", target_id="cloud-aws",
        relation_type=RelationType.INTEGRATES_WITH,
    ))

    return kg


@pytest.fixture
def empty_kg():
    """KG with no entities."""
    return KnowledgeGraph()


@pytest.fixture
def minimal_kg():
    """KG with just a project — not enough for most diagrams."""
    kg = KnowledgeGraph()
    kg.add_entity(Entity(
        id="proj-x", name="ProjectX",
        entity_type=EntityType.PROJECT, confidence=1.0,
    ))
    return kg


# ── Unit tests for individual diagram builders ───────────────────────────


class TestSystemArchitecture:
    def test_builds_with_full_kg(self, rich_kg):
        result = _build_system_architecture(rich_kg, "SmartTemp")
        assert result is not None
        assert "graph TB" in result
        assert "SmartTemp" in result
        assert "Components" in result or "Features" in result

    def test_includes_component_nodes(self, rich_kg):
        result = _build_system_architecture(rich_kg, "SmartTemp")
        assert "REST API" in result
        assert "Background Worker" in result

    def test_includes_frameworks(self, rich_kg):
        result = _build_system_architecture(rich_kg, "SmartTemp")
        assert "Flask" in result
        assert "React" in result

    def test_includes_databases(self, rich_kg):
        result = _build_system_architecture(rich_kg, "SmartTemp")
        assert "PostgreSQL" in result

    def test_returns_none_with_empty_kg(self, empty_kg):
        result = _build_system_architecture(empty_kg, "Empty")
        assert result is None


class TestTechStack:
    def test_builds_layered_diagram(self, rich_kg):
        result = _build_tech_stack(rich_kg)
        assert result is not None
        assert "graph TB" in result

    def test_has_frontend_layer(self, rich_kg):
        result = _build_tech_stack(rich_kg)
        assert "Frontend" in result
        assert "React" in result

    def test_has_backend_layer(self, rich_kg):
        result = _build_tech_stack(rich_kg)
        assert "Backend" in result
        assert "Flask" in result

    def test_has_data_layer(self, rich_kg):
        result = _build_tech_stack(rich_kg)
        assert "Data Layer" in result
        assert "PostgreSQL" in result

    def test_has_infrastructure(self, rich_kg):
        result = _build_tech_stack(rich_kg)
        assert "Infrastructure" in result

    def test_returns_none_with_one_entity(self, minimal_kg):
        result = _build_tech_stack(minimal_kg)
        assert result is None


class TestDataFlow:
    def test_builds_data_flow(self, rich_kg):
        result = _build_data_flow(rich_kg)
        assert result is not None
        assert "graph LR" in result

    def test_includes_storage_relations(self, rich_kg):
        result = _build_data_flow(rich_kg)
        assert "stores in" in result

    def test_includes_communication_relations(self, rich_kg):
        result = _build_data_flow(rich_kg)
        assert "communicates via" in result

    def test_returns_none_with_no_data_relations(self, minimal_kg):
        result = _build_data_flow(minimal_kg)
        assert result is None


class TestDependencyTree:
    def test_builds_dependency_tree(self, rich_kg):
        result = _build_dependency_tree(rich_kg)
        assert result is not None
        assert "graph TD" in result

    def test_includes_requires_relations(self, rich_kg):
        result = _build_dependency_tree(rich_kg)
        assert "requires" in result or "depends on" in result or "uses" in result

    def test_returns_none_with_no_deps(self, minimal_kg):
        result = _build_dependency_tree(minimal_kg)
        assert result is None


class TestDeploymentView:
    def test_builds_deployment(self, rich_kg):
        result = _build_deployment_view(rich_kg)
        assert result is not None
        assert "graph TB" in result
        assert "Deployment Targets" in result

    def test_includes_cloud_and_platform(self, rich_kg):
        result = _build_deployment_view(rich_kg)
        assert "AWS" in result
        assert "Docker" in result

    def test_returns_none_with_no_hosts(self, minimal_kg):
        result = _build_deployment_view(minimal_kg)
        assert result is None


# ── Integration test for the full generator ──────────────────────────────


class TestArchitectureGenerator:
    def test_generates_report_and_mmd_files(self, sample_doc, rich_kg, tmp_path):
        gen = ArchitectureGenerator(knowledge_graph=rich_kg)
        result = gen.generate(sample_doc, tmp_path)
        assert result.success is True
        assert result.output_path.exists()
        # Should produce .architecture.md report
        report = result.output_path.read_text(encoding="utf-8")
        assert "Architecture Diagrams" in report
        # Should have generated .mmd files in architecture/
        arch_dir = tmp_path / "architecture"
        assert arch_dir.exists()
        mmd_files = list(arch_dir.glob("*.mmd"))
        assert len(mmd_files) >= 1

    def test_fails_with_empty_kg(self, sample_doc, empty_kg, tmp_path):
        gen = ArchitectureGenerator(knowledge_graph=empty_kg)
        result = gen.generate(sample_doc, tmp_path)
        assert result.success is False

    def test_report_contains_mermaid_source(self, sample_doc, rich_kg, tmp_path):
        gen = ArchitectureGenerator(knowledge_graph=rich_kg)
        result = gen.generate(sample_doc, tmp_path)
        report = result.output_path.read_text(encoding="utf-8")
        assert "```mermaid" in report
        assert "graph" in report

    def test_report_has_stats_table(self, sample_doc, rich_kg, tmp_path):
        gen = ArchitectureGenerator(knowledge_graph=rich_kg)
        result = gen.generate(sample_doc, tmp_path)
        report = result.output_path.read_text(encoding="utf-8")
        assert "Generation Stats" in report
        assert "Entities" in report
        assert "Relations" in report

    def test_individual_mmd_files_valid(self, sample_doc, rich_kg, tmp_path):
        """Each .mmd file should start with a valid Mermaid graph directive."""
        gen = ArchitectureGenerator(knowledge_graph=rich_kg)
        gen.generate(sample_doc, tmp_path)
        arch_dir = tmp_path / "architecture"
        for mmd in arch_dir.glob("*.mmd"):
            content = mmd.read_text(encoding="utf-8")
            assert content.startswith("graph "), f"{mmd.name} doesn't start with 'graph '"

    def test_no_kg_returns_failure(self, sample_doc, tmp_path):
        gen = ArchitectureGenerator(knowledge_graph=None)
        result = gen.generate(sample_doc, tmp_path)
        assert result.success is False
