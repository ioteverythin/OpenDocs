"""Tests for the new generators: blog, jira, changelog, latex, onepager, social."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opendocs.core.knowledge_graph import Entity, EntityType, KnowledgeGraph, Relation, RelationType
from opendocs.core.parser import ReadmeParser
from opendocs.generators.blog_generator import BlogGenerator
from opendocs.generators.changelog_generator import ChangelogGenerator
from opendocs.generators.jira_generator import JiraGenerator
from opendocs.generators.latex_generator import LatexGenerator
from opendocs.generators.onepager_generator import OnePagerGenerator
from opendocs.generators.social_generator import SocialGenerator


@pytest.fixture
def sample_doc():
    """Parse the sample README into a DocumentModel."""
    sample_path = Path(__file__).parent.parent / "examples" / "sample_readme.md"
    content = sample_path.read_text(encoding="utf-8")
    parser = ReadmeParser()
    return parser.parse(content, repo_name="SmartTemp", repo_url="https://github.com/test/smarttemp")


@pytest.fixture
def sample_kg():
    """Build a small knowledge graph for testing."""
    kg = KnowledgeGraph()
    kg.add_entity(Entity(
        id="proj-smarttemp", name="SmartTemp",
        entity_type=EntityType.PROJECT,
        confidence=1.0,
    ))
    kg.add_entity(Entity(
        id="tech-python", name="Python",
        entity_type=EntityType.LANGUAGE,
        confidence=0.95,
    ))
    kg.add_entity(Entity(
        id="fw-flask", name="Flask",
        entity_type=EntityType.FRAMEWORK,
        confidence=0.9,
    ))
    kg.add_entity(Entity(
        id="feat-dashboard", name="Dashboard",
        entity_type=EntityType.FEATURE,
        confidence=0.85,
    ))
    kg.add_entity(Entity(
        id="feat-alerts", name="Real-time Alerts",
        entity_type=EntityType.FEATURE,
        confidence=0.8,
    ))
    kg.add_entity(Entity(
        id="prereq-docker", name="Docker",
        entity_type=EntityType.PREREQUISITE,
        confidence=0.9,
    ))
    kg.add_relation(Relation(
        source_id="proj-smarttemp",
        target_id="tech-python",
        relation_type=RelationType.USES,
    ))
    kg.add_relation(Relation(
        source_id="proj-smarttemp",
        target_id="fw-flask",
        relation_type=RelationType.USES,
    ))
    kg.executive_summary = (
        "SmartTemp is an IoT temperature monitoring platform built with "
        "Python and Flask, featuring real-time dashboards and alerts."
    )
    return kg


# ---------------------------------------------------------------------------
# Blog Generator
# ---------------------------------------------------------------------------

class TestBlogGenerator:
    def test_generates_blog_md(self, sample_doc, tmp_path):
        gen = BlogGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.name.startswith("blog_")
        assert result.output_path.suffix == ".md"

    def test_blog_content_structure(self, sample_doc, tmp_path):
        gen = BlogGenerator()
        result = gen.generate(sample_doc, tmp_path)
        content = result.output_path.read_text(encoding="utf-8")
        # Should have front-matter
        assert "---" in content
        assert "title:" in content
        # Should have a hero heading
        assert "# " in content
        # Should have conclusion
        assert "Conclusion" in content

    def test_blog_with_kg(self, sample_doc, sample_kg, tmp_path):
        gen = BlogGenerator(knowledge_graph=sample_kg)
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        content = result.output_path.read_text(encoding="utf-8")
        # KG executive summary should appear
        assert "SmartTemp" in content

    def test_blog_with_empty_doc(self, tmp_path):
        parser = ReadmeParser()
        doc = parser.parse("# Empty\n\nNothing here.")
        gen = BlogGenerator()
        result = gen.generate(doc, tmp_path)
        assert result.success


# ---------------------------------------------------------------------------
# Jira Generator
# ---------------------------------------------------------------------------

class TestJiraGenerator:
    def test_generates_jira_json(self, sample_doc, tmp_path):
        gen = JiraGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.name.startswith("jira_")
        assert result.output_path.suffix == ".json"

    def test_jira_structure(self, sample_doc, tmp_path):
        gen = JiraGenerator()
        result = gen.generate(sample_doc, tmp_path)
        data = json.loads(result.output_path.read_text(encoding="utf-8"))
        assert "epic" in data
        assert "stories" in data
        assert "total_tickets" in data
        assert data["epic"]["type"] == "Epic"
        assert data["total_tickets"] == 1 + len(data["stories"])

    def test_jira_stories_have_acceptance_criteria(self, sample_doc, tmp_path):
        gen = JiraGenerator()
        result = gen.generate(sample_doc, tmp_path)
        data = json.loads(result.output_path.read_text(encoding="utf-8"))
        for story in data["stories"]:
            assert "acceptance_criteria" in story
            assert isinstance(story["acceptance_criteria"], list)

    def test_jira_with_kg_features(self, sample_doc, sample_kg, tmp_path):
        gen = JiraGenerator(knowledge_graph=sample_kg)
        result = gen.generate(sample_doc, tmp_path)
        data = json.loads(result.output_path.read_text(encoding="utf-8"))
        # Should have feature-based stories from KG
        summaries = [s["summary"] for s in data["stories"]]
        assert any("Dashboard" in s for s in summaries)


# ---------------------------------------------------------------------------
# Changelog Generator
# ---------------------------------------------------------------------------

class TestChangelogGenerator:
    def test_generates_changelog_md(self, sample_doc, tmp_path):
        gen = ChangelogGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.name.startswith("changelog_")
        assert result.output_path.suffix == ".md"

    def test_changelog_content(self, sample_doc, tmp_path):
        gen = ChangelogGenerator()
        result = gen.generate(sample_doc, tmp_path)
        content = result.output_path.read_text(encoding="utf-8")
        assert "# Changelog" in content
        assert "Unreleased" in content
        assert "opendocs" in content

    def test_changelog_with_kg(self, sample_doc, sample_kg, tmp_path):
        gen = ChangelogGenerator(knowledge_graph=sample_kg)
        result = gen.generate(sample_doc, tmp_path)
        content = result.output_path.read_text(encoding="utf-8")
        # Should have tech stack from KG
        assert "Tech Stack" in content


# ---------------------------------------------------------------------------
# LaTeX Generator
# ---------------------------------------------------------------------------

class TestLatexGenerator:
    def test_generates_latex_tex(self, sample_doc, tmp_path):
        gen = LatexGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.suffix == ".tex"

    def test_latex_content(self, sample_doc, tmp_path):
        gen = LatexGenerator()
        result = gen.generate(sample_doc, tmp_path)
        content = result.output_path.read_text(encoding="utf-8")
        assert r"\documentclass" in content
        assert r"\begin{document}" in content
        assert r"\end{document}" in content
        assert r"\maketitle" in content
        assert r"\begin{abstract}" in content

    def test_latex_escapes_special_chars(self, tmp_path):
        parser = ReadmeParser()
        doc = parser.parse("# Test & Demo\n\nPrice is $10 for 50% off")
        gen = LatexGenerator()
        result = gen.generate(doc, tmp_path)
        content = result.output_path.read_text(encoding="utf-8")
        # Should escape & $ %
        assert r"\&" in content

    def test_latex_with_kg(self, sample_doc, sample_kg, tmp_path):
        gen = LatexGenerator(knowledge_graph=sample_kg)
        result = gen.generate(sample_doc, tmp_path)
        content = result.output_path.read_text(encoding="utf-8")
        assert "Technology Stack" in content


# ---------------------------------------------------------------------------
# One-Pager Generator
# ---------------------------------------------------------------------------

class TestOnePagerGenerator:
    def test_generates_onepager_pdf(self, sample_doc, tmp_path):
        gen = OnePagerGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.name.startswith("onepager_")
        assert result.output_path.suffix == ".pdf"

    def test_onepager_with_kg(self, sample_doc, sample_kg, tmp_path):
        gen = OnePagerGenerator(knowledge_graph=sample_kg)
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()


# ---------------------------------------------------------------------------
# Social Generator
# ---------------------------------------------------------------------------

class TestSocialGenerator:
    def test_generates_social_json(self, sample_doc, tmp_path):
        gen = SocialGenerator()
        result = gen.generate(sample_doc, tmp_path)
        assert result.success
        assert result.output_path.exists()
        assert result.output_path.name.startswith("social_")
        assert result.output_path.suffix == ".json"

    def test_social_structure(self, sample_doc, tmp_path):
        gen = SocialGenerator()
        result = gen.generate(sample_doc, tmp_path)
        data = json.loads(result.output_path.read_text(encoding="utf-8"))
        assert "open_graph" in data
        assert "twitter_card" in data
        assert "posts" in data
        assert "twitter" in data["posts"]
        assert "linkedin" in data["posts"]
        assert "hackernews" in data["posts"]
        assert "reddit" in data["posts"]

    def test_twitter_post_length(self, sample_doc, tmp_path):
        gen = SocialGenerator()
        result = gen.generate(sample_doc, tmp_path)
        data = json.loads(result.output_path.read_text(encoding="utf-8"))
        tweet = data["posts"]["twitter"]
        assert len(tweet) <= 280

    def test_social_with_kg(self, sample_doc, sample_kg, tmp_path):
        gen = SocialGenerator(knowledge_graph=sample_kg)
        result = gen.generate(sample_doc, tmp_path)
        data = json.loads(result.output_path.read_text(encoding="utf-8"))
        # Should include KG-derived hashtags
        assert len(data["hashtags"]) > 0
        # Should have tech stack
        assert len(data["tech_stack"]) > 0

    def test_social_og_metadata(self, sample_doc, tmp_path):
        gen = SocialGenerator()
        result = gen.generate(sample_doc, tmp_path)
        data = json.loads(result.output_path.read_text(encoding="utf-8"))
        og = data["open_graph"]
        assert "og:title" in og
        assert "og:description" in og
        assert "og:type" in og
