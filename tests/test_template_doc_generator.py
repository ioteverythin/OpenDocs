"""Tests for the template-based documentation generator."""

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
from opendocs.core.template_doc_generator import (
    generate_template_documentation,
    _maturity_label,
    _doc_coverage,
    _build_executive_summary,
    _build_architecture_section,
    _build_language_breakdown,
    _build_tech_stack,
    _build_codebase_status,
    _build_implementation_plan,
    _build_risk_assessment,
    _build_dependency_graph,
    _build_module_docs,
    _build_test_section,
    _build_config_section,
    _build_next_steps,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_model() -> CodebaseModel:
    """Create a realistic sample CodebaseModel for testing."""
    return CodebaseModel(
        project_name="TestProject",
        root_path="/tmp/test-project",
        total_files=5,
        total_lines=800,
        total_code_lines=600,
        languages={"python": 4, "javascript": 1},
        files=[
            FileAnalysis(
                path="main.py",
                language="python",
                line_count=200,
                blank_lines=30,
                comment_lines=20,
                code_lines=150,
                module_docstring="Main application entry point.",
                imports=["utils", "models"],
                classes=[
                    ClassInfo(
                        name="App",
                        docstring="Main application class.",
                        bases=["BaseApp"],
                        methods=[
                            FunctionInfo(name="__init__", args=["self", "config"], return_type="None"),
                            FunctionInfo(name="run", args=["self"], return_type="None", docstring="Run the app."),
                            FunctionInfo(name="stop", args=["self"], return_type="None"),
                        ],
                    )
                ],
                functions=[
                    FunctionInfo(name="create_app", args=["config"], return_type="App", docstring="Factory function."),
                ],
                is_entry_point=True,
                summary="Main application entry point",
            ),
            FileAnalysis(
                path="utils.py",
                language="python",
                line_count=150,
                blank_lines=20,
                comment_lines=10,
                code_lines=120,
                module_docstring="Utility helpers.",
                imports=[],
                functions=[
                    FunctionInfo(name="format_output", args=["data", "fmt"], return_type="str"),
                    FunctionInfo(name="validate_input", args=["raw"], return_type="bool"),
                ],
                summary="Utility helpers",
            ),
            FileAnalysis(
                path="models.py",
                language="python",
                line_count=100,
                blank_lines=10,
                comment_lines=5,
                code_lines=85,
                module_docstring="Data models.",
                imports=[],
                classes=[
                    ClassInfo(name="User", docstring="User model.", bases=["BaseModel"]),
                    ClassInfo(name="Config", docstring="App configuration."),
                ],
                summary="Data models",
            ),
            FileAnalysis(
                path="test_main.py",
                language="python",
                line_count=250,
                code_lines=200,
                is_test=True,
                functions=[
                    FunctionInfo(name="test_create_app", args=[]),
                    FunctionInfo(name="test_run", args=[]),
                    FunctionInfo(name="test_stop", args=[]),
                ],
                summary="Tests for main module",
            ),
            FileAnalysis(
                path="frontend.js",
                language="javascript",
                line_count=100,
                code_lines=80,
                summary="Frontend script",
            ),
        ],
        tech_stack=[
            TechStackItem(name="FastAPI", category="Web Framework", language="python", source_files=["main.py"]),
            TechStackItem(name="Pydantic", category="Data Validation", language="python", source_files=["models.py", "main.py"]),
            TechStackItem(name="Pytest", category="Testing", language="python", source_files=["test_main.py"]),
        ],
        architecture_layers=[
            ArchitectureLayer(name="API Layer", description="HTTP endpoints and routing", modules=["main.py"]),
            ArchitectureLayer(name="Core Logic", description="Business rules and data models", modules=["models.py", "utils.py"]),
        ],
        entry_points=["main.py"],
        config_files=["pyproject.toml", "Dockerfile"],
        test_files=["test_main.py"],
        description="A test project for documentation generation.",
        version="1.0.0",
        license="MIT",
        dependencies=["fastapi", "pydantic", "pytest"],
    )


@pytest.fixture
def empty_model() -> CodebaseModel:
    """Minimal empty model."""
    return CodebaseModel(project_name="Empty", root_path="/tmp/empty")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMaturityLabel:
    def test_production_ready(self, sample_model):
        # Has docs, tests, config, ci-like files, enough code
        sample_model.config_files = ["pyproject.toml", "Dockerfile", "Makefile"]
        assert _maturity_label(sample_model) in ("Mature", "Production-Ready")

    def test_early_stage(self, empty_model):
        assert _maturity_label(empty_model) == "Early Stage"


class TestDocCoverage:
    def test_with_documented_files(self, sample_model):
        doc_count, total, pct = _doc_coverage(sample_model.files)
        assert doc_count == 3  # main.py, utils.py, models.py have docstrings
        assert total == 4  # 4 non-test files
        assert pct == 75.0

    def test_empty(self, empty_model):
        doc_count, total, pct = _doc_coverage(empty_model.files)
        assert doc_count == 0
        assert total == 0
        assert pct == 0.0


class TestExecutiveSummary:
    def test_contains_project_name(self, sample_model):
        result = _build_executive_summary(sample_model)
        assert "TestProject" in result

    def test_contains_file_count(self, sample_model):
        result = _build_executive_summary(sample_model)
        assert "5" in result  # total files
        assert "600" in result  # code lines

    def test_contains_tech_stack(self, sample_model):
        result = _build_executive_summary(sample_model)
        assert "FastAPI" in result

    def test_contains_entry_points(self, sample_model):
        result = _build_executive_summary(sample_model)
        assert "main.py" in result

    def test_contains_architecture_info(self, sample_model):
        result = _build_executive_summary(sample_model)
        assert "architectural layer" in result


class TestArchitectureSection:
    def test_has_mermaid_diagram(self, sample_model):
        result = _build_architecture_section(sample_model)
        assert "```mermaid" in result
        assert "graph TB" in result

    def test_describes_layers(self, sample_model):
        result = _build_architecture_section(sample_model)
        assert "API Layer" in result
        assert "Core Logic" in result

    def test_has_class_hierarchy(self, sample_model):
        result = _build_architecture_section(sample_model)
        assert "classDiagram" in result
        assert "App" in result

    def test_empty_model(self, empty_model):
        result = _build_architecture_section(empty_model)
        assert "flat module structure" in result


class TestLanguageBreakdown:
    def test_has_pie_chart(self, sample_model):
        result = _build_language_breakdown(sample_model)
        assert "pie title" in result
        assert "Python" in result

    def test_has_table(self, sample_model):
        result = _build_language_breakdown(sample_model)
        assert "| Language |" in result

    def test_empty_model(self, empty_model):
        result = _build_language_breakdown(empty_model)
        assert result == ""


class TestTechStack:
    def test_has_table(self, sample_model):
        result = _build_tech_stack(sample_model)
        assert "FastAPI" in result
        assert "Pydantic" in result
        assert "| Technology |" in result

    def test_has_pie_chart(self, sample_model):
        result = _build_tech_stack(sample_model)
        assert "pie title Technologies by Category" in result

    def test_empty_model(self, empty_model):
        result = _build_tech_stack(empty_model)
        assert result == ""


class TestCodebaseStatus:
    def test_has_module_table(self, sample_model):
        result = _build_codebase_status(sample_model)
        assert "| Module |" in result
        assert "main.py" in result

    def test_excludes_test_files(self, sample_model):
        result = _build_codebase_status(sample_model)
        assert "test_main.py" not in result

    def test_has_status_pie_chart(self, sample_model):
        result = _build_codebase_status(sample_model)
        assert "pie title Module Documentation Status" in result


class TestImplementationPlan:
    def test_has_priority_sections(self, sample_model):
        result = _build_implementation_plan(sample_model)
        assert "### P0" in result
        assert "### P1" in result
        assert "### P2" in result
        assert "### P3" in result

    def test_has_priority_matrix(self, sample_model):
        result = _build_implementation_plan(sample_model)
        assert "| Priority | Task |" in result

    def test_data_driven_recommendations(self, sample_model):
        # With 1 test file for 4 source modules, should recommend more tests
        result = _build_implementation_plan(sample_model)
        assert "test" in result.lower()


class TestRiskAssessment:
    def test_has_risk_table(self, sample_model):
        result = _build_risk_assessment(sample_model)
        assert "| Risk Level |" in result

    def test_has_overall_level(self, sample_model):
        result = _build_risk_assessment(sample_model)
        assert "Overall Risk Level" in result

    def test_identifies_documentation_status(self, sample_model):
        result = _build_risk_assessment(sample_model)
        # 75% documented — should be moderate or better
        assert "Documentation" in result


class TestDependencyGraph:
    def test_has_mermaid(self, sample_model):
        result = _build_dependency_graph(sample_model)
        assert "```mermaid" in result
        assert "graph TD" in result


class TestModuleDocs:
    def test_has_module_sections(self, sample_model):
        result = _build_module_docs(sample_model)
        assert "### `main.py`" in result
        assert "### `utils.py`" in result

    def test_has_class_info(self, sample_model):
        result = _build_module_docs(sample_model)
        assert "class `App`" in result

    def test_has_method_table(self, sample_model):
        result = _build_module_docs(sample_model)
        assert "| Method |" in result


class TestTestSection:
    def test_lists_test_files(self, sample_model):
        result = _build_test_section(sample_model)
        assert "test_main.py" in result

    def test_empty_when_no_tests(self, empty_model):
        result = _build_test_section(empty_model)
        assert result == ""


class TestConfigSection:
    def test_lists_config_files(self, sample_model):
        result = _build_config_section(sample_model)
        assert "pyproject.toml" in result
        assert "Dockerfile" in result

    def test_empty_when_no_config(self, empty_model):
        result = _build_config_section(empty_model)
        assert result == ""


class TestNextSteps:
    def test_has_numbered_steps(self, sample_model):
        result = _build_next_steps(sample_model)
        assert "1." in result


class TestGenerateTemplateDocumentation:
    def test_full_generation(self, sample_model):
        result = generate_template_documentation(sample_model)
        assert "# TestProject" in result
        assert "## Executive Summary" in result
        assert "## System Architecture" in result
        assert "## Codebase Status" in result
        assert "## Risk Assessment" in result
        assert "```mermaid" in result

    def test_progress_callback(self, sample_model):
        calls = []
        def cb(name, idx, total):
            calls.append((name, idx, total))

        generate_template_documentation(sample_model, progress_callback=cb)
        assert len(calls) == 11
        assert calls[0][0] == "Header"
        assert calls[-1][0] == "Final Sections"

    def test_empty_model(self, empty_model):
        result = generate_template_documentation(empty_model)
        assert "# Empty" in result
        assert "## Executive Summary" in result

    def test_output_is_string(self, sample_model):
        result = generate_template_documentation(sample_model)
        assert isinstance(result, str)
        assert len(result) > 1000  # Should be substantial
