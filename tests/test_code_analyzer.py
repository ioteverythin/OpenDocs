"""Tests for the codebase analyzer module."""

from __future__ import annotations

import textwrap

from opendocs.core.code_analyzer import (
    CodebaseAnalyzer,
    CodebaseModel,
    FileAnalysis,
    _analyze_python,
    _detect_tech_stack,
    generate_codebase_markdown,
)

# ---------------------------------------------------------------------------
# Python AST analysis
# ---------------------------------------------------------------------------


class TestAnalyzePython:
    """Test deep Python file analysis."""

    def test_basic_module(self):
        source = textwrap.dedent('''\
            """My module docstring."""

            import os
            from pathlib import Path

            def hello(name: str) -> str:
                """Say hello."""
                return f"Hello, {name}"

            class Greeter:
                """A greeter class."""

                def greet(self, name: str) -> str:
                    """Greet someone."""
                    return f"Hi, {name}"
        ''')
        fa = _analyze_python(source, "mymod.py")

        assert fa.language == "python"
        assert fa.module_docstring == "My module docstring."
        assert "os" in fa.imports
        assert "pathlib" in fa.imports
        assert len(fa.functions) == 1
        assert fa.functions[0].name == "hello"
        assert fa.functions[0].return_type == "str"
        assert fa.functions[0].docstring == "Say hello."
        assert len(fa.classes) == 1
        assert fa.classes[0].name == "Greeter"
        assert fa.classes[0].docstring == "A greeter class."
        assert len(fa.classes[0].methods) == 1

    def test_async_function(self):
        source = textwrap.dedent('''\
            import asyncio

            async def fetch_data(url: str) -> dict:
                """Fetch data from URL."""
                pass
        ''')
        fa = _analyze_python(source, "fetcher.py")
        assert fa.functions[0].is_async is True
        assert fa.functions[0].name == "fetch_data"

    def test_entry_point_detection(self):
        source = textwrap.dedent("""\
            def main():
                pass
        """)
        fa = _analyze_python(source, "app.py")
        assert fa.is_entry_point is True

    def test_test_file_detection(self):
        source = "def test_something(): pass"
        fa = _analyze_python(source, "test_mymod.py")
        assert fa.is_test is True

    def test_syntax_error_handled(self):
        source = "def broken(:"
        fa = _analyze_python(source, "broken.py")
        assert fa.language == "python"
        assert fa.line_count == 1

    def test_line_counts(self):
        source = textwrap.dedent("""\
            # Comment line
            x = 1

            y = 2
        """)
        fa = _analyze_python(source, "counts.py")
        assert fa.line_count == 4  # textwrap.dedent strips trailing newline
        assert fa.blank_lines == 1
        assert fa.comment_lines == 1
        assert fa.code_lines == 2

    def test_decorators(self):
        source = textwrap.dedent("""\
            from functools import lru_cache

            @lru_cache
            def cached():
                pass
        """)
        fa = _analyze_python(source, "deco.py")
        assert "lru_cache" in fa.functions[0].decorators


# ---------------------------------------------------------------------------
# Tech stack detection
# ---------------------------------------------------------------------------


class TestTechDetection:
    def test_detects_fastapi(self):
        fa = FileAnalysis(path="server.py", language="python", imports=["fastapi", "uvicorn"])
        techs = _detect_tech_stack([fa])
        names = [t.name for t in techs]
        assert "FastAPI" in names
        assert "Uvicorn" in names

    def test_detects_react(self):
        fa = FileAnalysis(path="app.tsx", language="typescript", imports=["react", "next"])
        techs = _detect_tech_stack([fa])
        names = [t.name for t in techs]
        assert "React" in names

    def test_no_false_positives(self):
        fa = FileAnalysis(path="hello.py", language="python", imports=["os", "sys"])
        techs = _detect_tech_stack([fa])
        assert len(techs) == 0


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


class TestMarkdownGeneration:
    def test_generates_title(self):
        model = CodebaseModel(project_name="MyProject", root_path="/tmp/test")
        md = generate_codebase_markdown(model)
        assert "# MyProject" in md

    def test_includes_executive_summary(self):
        model = CodebaseModel(
            project_name="Demo",
            root_path="/tmp/demo",
            total_files=10,
            total_code_lines=500,
            languages={"python": 8, "javascript": 2},
        )
        md = generate_codebase_markdown(model)
        assert "## Executive Summary" in md
        assert "10 source files" in md
        assert "500 lines of code" in md

    def test_includes_tech_stack_table(self):
        from opendocs.core.code_analyzer import TechStackItem

        model = CodebaseModel(
            project_name="Demo",
            root_path="/tmp/demo",
            tech_stack=[
                TechStackItem(name="FastAPI", category="Web Framework", source_files=["server.py"]),
            ],
        )
        md = generate_codebase_markdown(model)
        assert "## Technology Stack" in md
        assert "FastAPI" in md

    def test_includes_module_table(self):
        model = CodebaseModel(
            project_name="Demo",
            root_path="/tmp/demo",
            total_files=1,
            files=[
                FileAnalysis(
                    path="core/main.py",
                    language="python",
                    line_count=100,
                    summary="Main entry point",
                ),
            ],
        )
        md = generate_codebase_markdown(model)
        assert "## Codebase Status" in md
        assert "core/main.py" in md

    def test_includes_mermaid_diagram(self):
        from opendocs.core.code_analyzer import ArchitectureLayer

        model = CodebaseModel(
            project_name="Demo",
            root_path="/tmp/demo",
            architecture_layers=[
                ArchitectureLayer(name="API", description="API layer", modules=["api.py"]),
                ArchitectureLayer(name="Core", description="Core layer", modules=["core.py"]),
            ],
        )
        md = generate_codebase_markdown(model)
        assert "```mermaid" in md
        assert "graph TB" in md


# ---------------------------------------------------------------------------
# Full analyzer (integration-style with tmp directory)
# ---------------------------------------------------------------------------


class TestCodebaseAnalyzer:
    def test_analyze_empty_dir(self, tmp_path):
        analyzer = CodebaseAnalyzer()
        model = analyzer.analyze(tmp_path)
        assert model.total_files == 0

    def test_analyze_python_project(self, tmp_path):
        # Create a mini Python project
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test-proj"\nversion = "1.0.0"\ndescription = "A test project"\n'
        )
        (tmp_path / "main.py").write_text('"""Main module."""\n\nimport os\n\ndef main():\n    print("hi")\n')
        src = tmp_path / "src"
        src.mkdir()
        (src / "helper.py").write_text('"""Helper utilities."""\n\ndef add(a, b):\n    return a + b\n')

        analyzer = CodebaseAnalyzer()
        model = analyzer.analyze(tmp_path)

        assert model.project_name == "test-proj"
        assert model.version == "1.0.0"
        assert model.total_files == 2
        assert "python" in model.languages
        assert len(model.entry_points) >= 1

    def test_skips_ignored_dirs(self, tmp_path):
        venv = tmp_path / "venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "something.py").write_text("x = 1")

        (tmp_path / "real.py").write_text("y = 2")

        analyzer = CodebaseAnalyzer()
        model = analyzer.analyze(tmp_path)

        paths = [f.path for f in model.files]
        assert "real.py" in paths
        assert not any("venv" in p for p in paths)

    def test_end_to_end_markdown(self, tmp_path):
        (tmp_path / "app.py").write_text(
            '"""FastAPI application."""\n\n'
            "from fastapi import FastAPI\n\n"
            "app = FastAPI()\n\n"
            '@app.get("/")\n'
            "def root():\n"
            '    return {"msg": "hello"}\n'
        )
        analyzer = CodebaseAnalyzer()
        model = analyzer.analyze(tmp_path)
        md = generate_codebase_markdown(model)

        assert "## Executive Summary" in md
        assert "## System Architecture" in md
        assert "## Codebase Status" in md
        assert "app.py" in md
