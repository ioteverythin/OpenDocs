"""Tests for the narrative Markdown generator."""

from __future__ import annotations

import pytest

from opendocs.core.code_analyzer import (
    ArchitectureLayer,
    ClassInfo,
    CodebaseModel,
    FileAnalysis,
    FunctionInfo,
    TechStackItem,
)
from opendocs.core.narrative_generator import (
    _build_architecture_mermaid,
    _build_codebase_status_table,
    _build_context,
    _build_dependency_graph,
    _build_tech_stack_table,
    _static_executive_summary,
    generate_narrative_markdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model() -> CodebaseModel:
    """Return a small but realistic CodebaseModel for testing."""
    return CodebaseModel(
        root_path="/tmp/testproject",
        project_name="TestProject",
        description="A test project for unit testing",
        version="1.0.0",
        license="MIT",
        total_files=3,
        total_lines=250,
        total_code_lines=200,
        languages={"python": 3},
        files=[
            FileAnalysis(
                path="src/main.py",
                language="python",
                line_count=120,
                code_lines=100,
                module_docstring="Main entry point for TestProject.",
                imports=["src.utils"],
                classes=[
                    ClassInfo(
                        name="App",
                        docstring="Main application class.",
                        bases=["BaseApp"],
                        methods=[
                            FunctionInfo(name="__init__", args=["self", "config"]),
                            FunctionInfo(name="run", args=["self"], docstring="Run the app."),
                        ],
                    ),
                ],
                functions=[
                    FunctionInfo(name="main", args=[], docstring="Entry point."),
                ],
                is_entry_point=True,
                summary="Main entry point with App class",
            ),
            FileAnalysis(
                path="src/utils.py",
                language="python",
                line_count=80,
                code_lines=60,
                module_docstring="Utility helpers.",
                functions=[
                    FunctionInfo(name="load_config", args=["path"], docstring="Load config from YAML."),
                    FunctionInfo(name="validate", args=["data"], docstring="Validate input data."),
                ],
                summary="Utility and validation helpers",
            ),
            FileAnalysis(
                path="tests/test_main.py",
                language="python",
                line_count=50,
                code_lines=40,
                is_test=True,
            ),
        ],
        tech_stack=[
            TechStackItem(name="FastAPI", category="Web Framework", source_files=["src/main.py"]),
            TechStackItem(name="Pydantic", category="Data Validation", source_files=["src/utils.py"]),
        ],
        architecture_layers=[
            ArchitectureLayer(
                name="Entry / CLI",
                description="Application entry points and command-line interface.",
                modules=["src/main.py"],
            ),
            ArchitectureLayer(
                name="Utilities",
                description="Shared helper functions.",
                modules=["src/utils.py"],
            ),
        ],
        entry_points=["src/main.py"],
        config_files=["pyproject.toml", "requirements.txt"],
        test_files=["tests/test_main.py"],
    )


class FakeLLM:
    """A mock LLM provider for testing narrative generation."""

    def __init__(self, response: str = "This is a generated narrative section."):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response


# ---------------------------------------------------------------------------
# Tests: context builder
# ---------------------------------------------------------------------------


class TestBuildContext:
    def test_basic_fields(self):
        model = _make_model()
        ctx = _build_context(model)
        assert ctx["project_name"] == "TestProject"
        assert ctx["total_files"] == "3"  # 2 source + 1 test
        assert "python" in ctx["languages"].lower()

    def test_tech_stack_listed(self):
        model = _make_model()
        ctx = _build_context(model)
        assert "FastAPI" in ctx["technologies"]
        assert "Pydantic" in ctx["technologies"]

    def test_layers(self):
        model = _make_model()
        ctx = _build_context(model)
        assert "Entry" in ctx["layers"]
        assert "Utilities" in ctx["layers"]


# ---------------------------------------------------------------------------
# Tests: static builders
# ---------------------------------------------------------------------------


class TestStaticBuilders:
    def test_architecture_mermaid(self):
        model = _make_model()
        md = _build_architecture_mermaid(model)
        assert "```mermaid" in md
        assert "graph TB" in md
        assert "Entry" in md
        assert "-->" in md

    def test_codebase_status_table(self):
        model = _make_model()
        md = _build_codebase_status_table(model)
        assert "## Codebase Status" in md
        assert "src/main.py" in md
        assert "src/utils.py" in md
        # Test files should be excluded
        assert "test_main" not in md

    def test_tech_stack_table(self):
        model = _make_model()
        md = _build_tech_stack_table(model)
        assert "FastAPI" in md
        assert "Pydantic" in md
        assert "Web Framework" in md

    def test_empty_tech_stack(self):
        model = _make_model()
        model.tech_stack = []
        md = _build_tech_stack_table(model)
        assert md == ""

    def test_dependency_graph(self):
        model = _make_model()
        md = _build_dependency_graph(model)
        assert "```mermaid" in md
        assert "graph LR" in md

    def test_static_executive_summary(self):
        model = _make_model()
        ctx = _build_context(model)
        md = _static_executive_summary(model, ctx)
        assert "Executive Summary" in md
        assert "TestProject" in md


# ---------------------------------------------------------------------------
# Tests: full narrative generation with mock LLM
# ---------------------------------------------------------------------------


class TestNarrativeGeneration:
    def test_generates_all_sections(self):
        model = _make_model()
        llm = FakeLLM("This project is a sophisticated application framework.")
        md = generate_narrative_markdown(model, llm)

        # Should contain all key sections
        assert "# TestProject" in md
        assert "## Executive Summary" in md
        assert "## System Architecture" in md
        assert "## Codebase Status" in md
        assert "## Dependency Graph" in md
        assert "## Module Documentation" in md
        assert "## Test Files" in md
        assert "## Configuration Files" in md

    def test_llm_is_called(self):
        model = _make_model()
        llm = FakeLLM("AI-generated content here.")
        generate_narrative_markdown(model, llm)

        # Should have made multiple LLM calls (exec summary, architecture, infra, implementation)
        assert len(llm.calls) >= 3

    def test_progress_callback(self):
        model = _make_model()
        llm = FakeLLM("Some output.")
        progress_events = []

        def on_progress(name, idx, total):
            progress_events.append((name, idx, total))

        generate_narrative_markdown(model, llm, progress_callback=on_progress)
        assert len(progress_events) >= 4
        assert progress_events[0][0] == "Executive Summary"

    def test_fallback_on_empty_llm_response(self):
        model = _make_model()
        llm = FakeLLM("")  # Empty response → fallback
        md = generate_narrative_markdown(model, llm)

        # Static fallbacks should still produce valid content
        assert "## Executive Summary" in md
        assert "TestProject" in md
        assert "## System Architecture" in md

    def test_fallback_on_llm_exception(self):
        class BrokenLLM:
            def chat(self, system, user):
                raise RuntimeError("model crashed")

        model = _make_model()
        md = generate_narrative_markdown(model, BrokenLLM())

        # Should still produce a document with static fallbacks
        assert "## Executive Summary" in md
        assert "## System Architecture" in md

    def test_mermaid_diagrams_present(self):
        model = _make_model()
        llm = FakeLLM("Generated text.")
        md = generate_narrative_markdown(model, llm)

        # Should have Mermaid architecture diagram + dependency graph
        assert md.count("```mermaid") >= 2

    def test_tables_present(self):
        model = _make_model()
        llm = FakeLLM("Generated text.")
        md = generate_narrative_markdown(model, llm)

        # Should contain tables (pipe-delimited)
        assert "| Module |" in md or "| Test File |" in md
