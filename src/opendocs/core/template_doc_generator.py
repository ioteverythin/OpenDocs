"""Template-based documentation generator — no LLM required.

Generates professional, richly-formatted Markdown documentation from a
``CodebaseModel`` using pure data analysis and template-driven prose.
Produces output comparable in quality to the LLM-driven narrative
generator, including:

- Data-driven Executive Summary with project statistics
- Architecture diagrams (Mermaid: layered, class, sequence)
- Language breakdown pie chart (Mermaid)
- Codebase health / quality analysis
- Technology Stack with rationale
- Implementation Plan with data-driven priority matrix
- Risk Assessment based on code metrics
- Dependency graphs and module documentation

Usage::

    from opendocs.core.code_analyzer import CodebaseAnalyzer
    from opendocs.core.template_doc_generator import generate_template_documentation

    model = CodebaseAnalyzer().analyze("./my-project")
    markdown = generate_template_documentation(model)
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .code_analyzer import (
        CodebaseModel,
        FileAnalysis,
        TechStackItem,
    )

logger = logging.getLogger("opendocs.core.template_doc_generator")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mermaid_id(path: str) -> str:
    """Make a path safe for Mermaid node IDs."""
    return path.replace("/", "_").replace("\\", "_").replace(".", "_").replace("-", "_").replace(" ", "_")


def _pct(part: int, whole: int) -> str:
    """Format a percentage string."""
    if whole == 0:
        return "0%"
    return f"{part / whole * 100:.1f}%"


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    pl = plural or (singular + "s")
    return f"{n:,} {singular if n == 1 else pl}"


def _top_n(items: list, n: int = 5) -> list:
    return items[:n]


def _doc_coverage(files: list["FileAnalysis"]) -> tuple[int, int, float]:
    """Return (documented_count, total_count, percentage) for non-test files."""
    src = [f for f in files if not f.is_test]
    if not src:
        return 0, 0, 0.0
    documented = sum(1 for f in src if f.module_docstring or any(c.docstring for c in f.classes))
    return documented, len(src), (documented / len(src) * 100)


def _avg_complexity(files: list["FileAnalysis"]) -> float:
    """Rough complexity: average functions per file for non-test files."""
    src = [f for f in files if not f.is_test and (f.functions or f.classes)]
    if not src:
        return 0.0
    total_funcs = sum(len(f.functions) + sum(len(c.methods) for c in f.classes) for f in src)
    return total_funcs / len(src)


def _largest_files(files: list["FileAnalysis"], n: int = 5) -> list["FileAnalysis"]:
    src = [f for f in files if not f.is_test]
    return sorted(src, key=lambda f: f.line_count, reverse=True)[:n]


def _maturity_label(model: "CodebaseModel") -> str:
    """Infer a project maturity label from metrics."""
    doc_count, total, doc_pct = _doc_coverage(model.files)
    has_tests = len(model.test_files) > 0
    has_ci = any("docker" in c.lower() or "makefile" in c.lower() or "ci" in c.lower() for c in model.config_files)
    has_config = len(model.config_files) >= 3

    score = 0
    if doc_pct >= 60:
        score += 2
    elif doc_pct >= 30:
        score += 1
    if has_tests:
        score += 2
    if has_ci:
        score += 1
    if has_config:
        score += 1
    if model.total_code_lines > 2000:
        score += 1

    if score >= 6:
        return "Production-Ready"
    elif score >= 4:
        return "Mature"
    elif score >= 2:
        return "Active Development"
    else:
        return "Early Stage"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_header(model: "CodebaseModel") -> str:
    title = model.project_name or "Project"
    now = datetime.now(timezone.utc).strftime("%B %d, %Y")
    lines = [
        f"# {title} — Technical Documentation\n",
    ]
    if model.description:
        lines.append(f"> {model.description}\n")
    meta = []
    if model.version:
        meta.append(f"**Version:** {model.version}")
    if model.license:
        meta.append(f"**License:** {model.license}")
    meta.append(f"**Generated:** {now}")
    meta.append(f"**Source:** `{model.root_path}`")
    meta.append(f"**Status:** {_maturity_label(model)}")
    lines.append("  \n".join(meta))
    lines.append("")
    return "\n".join(lines)


def _build_table_of_contents(model: "CodebaseModel") -> str:
    """Generate a navigable table of contents."""
    sections = [
        "Executive Summary",
        "System Architecture",
        "Language & Codebase Breakdown",
        "Technology Stack",
        "Codebase Status",
        "Implementation Plan & Priority Matrix",
        "Risk Assessment",
        "Dependency Graph",
        "Module Documentation",
    ]
    if model.test_files:
        sections.append("Test Coverage")
    if model.config_files:
        sections.append("Configuration Files")
    sections.append("Recommended Next Steps")

    lines = ["## Table of Contents\n"]
    for i, s in enumerate(sections, 1):
        anchor = s.lower().replace(" ", "-").replace("&", "").replace("--", "-")
        lines.append(f"{i}. [{s}](#{anchor})")
    lines.append("")
    return "\n".join(lines)


def _build_executive_summary(model: "CodebaseModel") -> str:
    title = model.project_name or "Project"

    # Language breakdown prose
    lang_parts = []
    for lang, count in sorted(model.languages.items(), key=lambda x: -x[1]):
        lang_parts.append(f"{count} {lang.title()}")
    lang_prose = ", ".join(lang_parts) if lang_parts else "source"

    # Tech highlights
    tech_names = [t.name for t in model.tech_stack[:8]]
    tech_prose = ", ".join(tech_names) if tech_names else "standard library components"

    # Counts
    src_count = len([f for f in model.files if not f.is_test])
    test_count = len(model.test_files)
    doc_count, _, doc_pct = _doc_coverage(model.files)
    maturity = _maturity_label(model)
    total_classes = sum(len(f.classes) for f in model.files if not f.is_test)
    total_functions = sum(
        len(f.functions) + sum(len(c.methods) for c in f.classes) for f in model.files if not f.is_test
    )

    # Entry points prose
    if model.entry_points:
        ep_prose = (
            f"The system exposes {_plural(len(model.entry_points), 'entry point')}, "
            f"including {', '.join(f'`{ep}`' for ep in model.entry_points[:3])}"
        )
        if len(model.entry_points) > 3:
            ep_prose += f" and {len(model.entry_points) - 3} others"
        ep_prose += "."
    else:
        ep_prose = ""

    # Architecture prose
    if model.architecture_layers:
        arch_prose = (
            f"The codebase is organized into {_plural(len(model.architecture_layers), 'architectural layer')}: "
            f"{', '.join(layer.name for layer in model.architecture_layers)}."
        )
    else:
        arch_prose = "The codebase follows a flat module structure."

    lines = [
        "## Executive Summary\n",
        f"**{title}** is a {lang_prose.split(',')[0].strip().split(' ')[1].lower() if lang_parts else ''}-based "
        f"software system comprising **{model.total_files:,} source files** and "
        f"**{model.total_code_lines:,} lines of code** ({lang_prose} files). "
        f"The project is built on a technology stack that includes {tech_prose}, "
        f"reflecting a {'comprehensive' if len(tech_names) >= 5 else 'focused'} approach to "
        f"its problem domain.\n",
        f"At a structural level, the codebase contains **{src_count} source modules** defining "
        f"**{total_classes:,} classes** and **{total_functions:,} functions/methods**, "
        f"supported by **{test_count} test file{'s' if test_count != 1 else ''}** and "
        f"**{len(model.config_files)} configuration file{'s' if len(model.config_files) != 1 else ''}**. "
        f"Documentation coverage stands at **{doc_pct:.0f}%** ({doc_count} of {src_count} modules "
        f"have docstrings), placing the project at a **{maturity}** maturity level. "
        f"{ep_prose}\n",
        f"{arch_prose} "
        f"{'The architecture suggests a well-separated concern model with clear boundaries between layers.' if len(model.architecture_layers) >= 3 else 'The architecture provides a solid foundation for future growth.'}\n",
    ]
    return "\n".join(lines)


def _build_architecture_section(model: "CodebaseModel") -> str:
    lines = ["## System Architecture\n"]

    if model.architecture_layers:
        layer_names = [layer.name for layer in model.architecture_layers]
        lines.append(
            f"The system follows a **layered architecture** pattern with "
            f"{_plural(len(model.architecture_layers), 'distinct layer')}: "
            f"{', '.join(layer_names)}. "
            f"Data flows from the outermost interface layers through core business logic "
            f"to output and integration layers.\n"
        )

        # Describe each layer
        for layer in model.architecture_layers:
            n_mods = len(layer.modules)
            lines.append(
                f"The **{layer.name}** layer ({_plural(n_mods, 'module')}) "
                f"{layer.description.rstrip('.').lower()}. "
                f"Key components include {', '.join(f'`{m}`' for m in layer.modules[:4])}"
            )
            if n_mods > 4:
                lines.append(f" and {n_mods - 4} additional modules")
            lines.append(".\n")
    else:
        lines.append(
            "The project uses a flat module structure where components are organized "
            "at the top level without explicit architectural layering.\n"
        )

    # Architecture diagram
    lines.append("### Architecture Overview\n")
    lines.append("```mermaid")
    lines.append("graph TB")

    if model.architecture_layers:
        for i, layer in enumerate(model.architecture_layers):
            lid = f"L{i}"
            safe_name = layer.name.replace('"', "'")
            n_mods = len(layer.modules)
            # Use subgraph style for richer diagrams
            lines.append(f'    subgraph {lid}["{safe_name}"]')
            for j, mod in enumerate(layer.modules[:6]):
                mid = _mermaid_id(mod)
                label = Path(mod).stem
                lines.append(f'        {mid}["{label}"]')
            if n_mods > 6:
                lines.append(f'        {lid}_more["... +{n_mods - 6} more"]')
            lines.append("    end")

        # Connect layers top-down
        for i in range(len(model.architecture_layers) - 1):
            a_layer = model.architecture_layers[i]
            b_layer = model.architecture_layers[i + 1]
            if a_layer.modules and b_layer.modules:
                a_id = _mermaid_id(a_layer.modules[0])
                b_id = _mermaid_id(b_layer.modules[0])
                lines.append(f"    {a_id} --> {b_id}")
    else:
        for fa in model.files[:10]:
            if not fa.is_test:
                mid = _mermaid_id(fa.path)
                label = Path(fa.path).stem
                lines.append(f'    {mid}["{label}"]')

    lines.append("```\n")

    # Class diagram (if there are classes)
    all_classes = []
    for fa in model.files:
        if not fa.is_test:
            for ci in fa.classes:
                all_classes.append((fa, ci))

    if all_classes:
        lines.append("### Class Hierarchy\n")
        lines.append("```mermaid")
        lines.append("classDiagram")

        shown = set()
        for fa, ci in all_classes[:15]:
            cname = ci.name.replace(" ", "_")
            if cname in shown:
                continue
            shown.add(cname)

            # Add class with key methods
            public_methods = [m for m in ci.methods if not m.name.startswith("_") or m.name == "__init__"]
            lines.append(f"    class {cname} {{")
            for m in public_methods[:5]:
                args = ", ".join(a for a in m.args if a != "self")[:30]
                ret = f" {m.return_type}" if m.return_type else ""
                async_prefix = "async " if m.is_async else ""
                lines.append(f"        +{async_prefix}{m.name}({args}){ret}")
            if len(public_methods) > 5:
                lines.append(f"        +... {len(public_methods) - 5} more methods")
            lines.append("    }")

            # Inheritance
            for base in ci.bases:
                base_clean = base.replace(" ", "_")
                if base_clean in shown:
                    lines.append(f"    {base_clean} <|-- {cname}")

        lines.append("```\n")

    return "\n".join(lines)


def _build_language_breakdown(model: "CodebaseModel") -> str:
    if not model.languages:
        return ""

    lines = ["## Language & Codebase Breakdown\n"]

    # Pie chart
    lines.append("### Language Distribution\n")
    lines.append("```mermaid")
    lines.append("pie title Codebase Language Distribution")

    for lang, count in sorted(model.languages.items(), key=lambda x: -x[1]):
        pct = count / model.total_files * 100 if model.total_files else 0
        lines.append(f'    "{lang.title()}" : {pct:.1f}')

    lines.append("```\n")

    # Table with more detail
    lines.append("### Detailed Breakdown\n")
    lines.append("| Language | Files | Lines of Code | Avg Lines/File | Classes | Functions |")
    lines.append("|----------|------:|--------------:|---------------:|--------:|----------:|")

    for lang, count in sorted(model.languages.items(), key=lambda x: -x[1]):
        lang_files = [f for f in model.files if f.language == lang and not f.is_test]
        total_loc = sum(f.code_lines or f.line_count for f in lang_files)
        avg_loc = total_loc // len(lang_files) if lang_files else 0
        n_classes = sum(len(f.classes) for f in lang_files)
        n_funcs = sum(len(f.functions) + sum(len(c.methods) for c in f.classes) for f in lang_files)
        lines.append(f"| {lang.title()} | {count} | {total_loc:,} | {avg_loc:,} | {n_classes} | {n_funcs} |")

    lines.append("")

    # Code metrics summary
    src_files = [f for f in model.files if not f.is_test]
    total_blank = sum(f.blank_lines for f in src_files)
    total_comment = sum(f.comment_lines for f in src_files)
    total_code = sum(f.code_lines or f.line_count for f in src_files)
    total_all = sum(f.line_count for f in src_files)

    if total_all > 0:
        lines.append("### Code Composition\n")
        lines.append("```mermaid")
        lines.append("pie title Code vs Comments vs Blank Lines")
        lines.append(f'    "Code" : {total_code}')
        if total_comment > 0:
            lines.append(f'    "Comments" : {total_comment}')
        if total_blank > 0:
            lines.append(f'    "Blank Lines" : {total_blank}')
        lines.append("```\n")

    return "\n".join(lines)


def _build_tech_stack(model: "CodebaseModel") -> str:
    if not model.tech_stack:
        return ""

    lines = ["## Technology Stack\n"]

    # Group by category
    categories: dict[str, list["TechStackItem"]] = defaultdict(list)
    for tech in model.tech_stack:
        categories[tech.category].append(tech)

    lines.append(
        f"The project leverages **{len(model.tech_stack)} technologies** across "
        f"**{len(categories)} categories**, demonstrating a "
        f"{'broad' if len(categories) >= 4 else 'focused'} technology adoption.\n"
    )

    lines.append("| Technology | Category | Adoption | Used In |")
    lines.append("|-----------|----------|---------|---------|")

    for tech in model.tech_stack:
        used_in = ", ".join(f"`{f}`" for f in tech.source_files[:3])
        if len(tech.source_files) > 3:
            used_in += f" +{len(tech.source_files) - 3} more"
        n_files = len(tech.source_files)
        adoption = "Heavy" if n_files >= 5 else ("Moderate" if n_files >= 2 else "Light")
        lines.append(f"| **{tech.name}** | {tech.category} | {adoption} ({n_files} files) | {used_in} |")

    lines.append("")

    # Technology by category summary
    lines.append("### Technology by Category\n")
    lines.append("```mermaid")
    lines.append("pie title Technologies by Category")
    for cat, techs in sorted(categories.items(), key=lambda x: -len(x[1])):
        lines.append(f'    "{cat}" : {len(techs)}')
    lines.append("```\n")

    return "\n".join(lines)


def _build_codebase_status(model: "CodebaseModel") -> str:
    lines = [
        "## Codebase Status\n",
        "A thorough audit of the codebase reveals the following modules, "
        "their functionality, current status, and key metrics.\n",
    ]

    src_files = [f for f in sorted(model.files, key=lambda f: f.path) if not f.is_test]

    # Summary stats
    complete = 0
    needs_docs = 0
    skeleton = 0
    for fa in src_files:
        has_docs = bool(fa.module_docstring) or any(c.docstring for c in fa.classes)
        n_funcs = len(fa.functions) + sum(len(c.methods) for c in fa.classes)
        if has_docs and n_funcs > 0:
            complete += 1
        elif n_funcs > 0:
            needs_docs += 1
        else:
            skeleton += 1

    lines.append(
        f"Of {len(src_files)} source modules: "
        f"**{complete}** are fully documented (✅), "
        f"**{needs_docs}** need documentation (⚠️), and "
        f"**{skeleton}** are skeleton/minimal (📋).\n"
    )

    # Status pie chart
    if len(src_files) > 0:
        lines.append("```mermaid")
        lines.append("pie title Module Documentation Status")
        if complete > 0:
            lines.append(f'    "Documented" : {complete}')
        if needs_docs > 0:
            lines.append(f'    "Needs Docs" : {needs_docs}')
        if skeleton > 0:
            lines.append(f'    "Skeleton" : {skeleton}')
        lines.append("```\n")

    # Module table
    lines.append("| Module | Functionality | Lines | Classes | Functions | Status |")
    lines.append("|--------|--------------|------:|--------:|----------:|--------|")

    for fa in src_files:
        purpose = fa.summary or ""
        if not purpose and fa.module_docstring:
            purpose = fa.module_docstring.split("\n")[0][:60]
        if not purpose:
            purpose = f"{fa.language.title()} module"

        has_docs = bool(fa.module_docstring) or any(c.docstring for c in fa.classes)
        n_funcs = len(fa.functions) + sum(len(c.methods) for c in fa.classes)
        n_classes = len(fa.classes)
        if has_docs and n_funcs > 0:
            status = "✅ Complete"
        elif n_funcs > 0:
            status = "⚠️ Needs Docs"
        else:
            status = "📋 Skeleton"

        lines.append(f"| `{fa.path}` | {purpose} | {fa.line_count} | {n_classes} | {n_funcs} | {status} |")

    lines.append("")
    return "\n".join(lines)


def _build_implementation_plan(model: "CodebaseModel") -> str:
    """Data-driven implementation plan based on actual code metrics."""
    lines = ["## Implementation Plan & Priority Matrix\n"]

    src_files = [f for f in model.files if not f.is_test]
    doc_count, total_src, doc_pct = _doc_coverage(model.files)
    test_count = len(model.test_files)
    large_files = [f for f in src_files if f.line_count > 300]
    undoc_files = [
        f
        for f in src_files
        if not f.module_docstring and not any(c.docstring for c in f.classes) and (f.functions or f.classes)
    ]
    has_tests = test_count > 0
    has_ci = any("docker" in c.lower() or "makefile" in c.lower() for c in model.config_files)

    # P0 — Critical: based on actual gaps
    lines.append("### P0 — Critical (Immediate)\n")
    p0_items = []
    if undoc_files:
        top_undoc = undoc_files[:3]
        names = ", ".join(f"`{f.path}`" for f in top_undoc)
        p0_items.append(
            f"- **Add documentation to core modules** — "
            f"{len(undoc_files)} modules lack docstrings, starting with {names}. "
            f"Effort: {len(undoc_files) * 30} min | Impact: High"
        )
    if not has_tests:
        p0_items.append(
            "- **Establish test suite** — No test files detected. "
            "Add unit tests for core business logic modules. "
            "Effort: 2-4 hours | Impact: Critical"
        )
    if large_files:
        names = ", ".join(f"`{f.path}` ({f.line_count} lines)" for f in large_files[:2])
        p0_items.append(
            f"- **Refactor oversized modules** — "
            f"{len(large_files)} files exceed 300 lines: {names}. "
            f"Effort: 1-2 hours each | Impact: High"
        )
    if not p0_items:
        p0_items.append(
            "- **Maintain current standards** — The codebase is well-structured "
            "with good documentation and test coverage. Focus on continuous integration."
        )
    lines.extend(p0_items)
    lines.append("")

    # P1 — High Priority
    lines.append("### P1 — High Priority (Next Sprint)\n")
    p1_items = []
    if has_tests and test_count < total_src // 2:
        p1_items.append(
            f"- **Expand test coverage** — Currently {test_count} test files "
            f"for {total_src} source modules ({_pct(test_count, total_src)} coverage ratio). "
            f"Target 1:1 test-to-module ratio. Effort: 3-5 hours | Impact: High"
        )
    if doc_pct < 80:
        p1_items.append(
            f"- **Improve documentation** — {doc_pct:.0f}% of modules documented. "
            f"Add docstrings and usage examples to remaining modules. "
            f"Effort: 2-3 hours | Impact: Medium"
        )
    if not has_ci:
        p1_items.append(
            "- **Set up CI/CD pipeline** — No CI configuration detected. "
            "Add GitHub Actions / GitLab CI for automated testing and deployment. "
            "Effort: 2-3 hours | Impact: High"
        )
    if len(model.entry_points) == 0:
        p1_items.append(
            "- **Define clear entry points** — No CLI or API entry points detected. "
            "Add a well-documented main entry point. Effort: 1-2 hours | Impact: Medium"
        )
    if not p1_items:
        p1_items.append(
            "- **Performance optimization** — Profile critical paths and optimize hot loops. "
            "Effort: 3-5 hours | Impact: Medium"
        )
    lines.extend(p1_items)
    lines.append("")

    # P2 — Medium Priority
    lines.append("### P2 — Medium Priority (Next Quarter)\n")
    lines.append(
        "- **API documentation** — Generate OpenAPI/Swagger docs if applicable. Effort: 2-3 hours | Impact: Medium"
    )
    if len(model.architecture_layers) <= 2:
        lines.append(
            "- **Improve architecture separation** — "
            f"Currently {len(model.architecture_layers)} layer(s). "
            "Consider separating concerns into distinct layers. "
            "Effort: 4-8 hours | Impact: Medium"
        )
    lines.append(
        "- **Add integration tests** — Test cross-module interactions and "
        "external dependencies. Effort: 3-5 hours | Impact: Medium"
    )
    lines.append("")

    # P3 — Nice to Have
    lines.append("### P3 — Nice to Have (Backlog)\n")
    lines.append("- **Performance profiling** — Benchmark critical paths and optimize bottlenecks")
    lines.append("- **Dependency updates** — Audit and update third-party dependencies")
    lines.append("- **Code style enforcement** — Add linter configuration and pre-commit hooks")
    lines.append("")

    # Priority Matrix table
    lines.append("### Priority Matrix\n")
    lines.append("| Priority | Task | Effort | Impact | Target Module(s) |")
    lines.append("|----------|------|--------|--------|------------------|")

    matrix_rows = []
    if undoc_files:
        matrix_rows.append(
            (
                "P0",
                "Add module docstrings",
                f"{len(undoc_files) * 30}m",
                "High",
                ", ".join(f"`{f.path}`" for f in undoc_files[:2]),
            )
        )
    if large_files:
        matrix_rows.append(
            (
                "P0",
                "Refactor large modules",
                f"{len(large_files) * 90}m",
                "High",
                ", ".join(f"`{f.path}`" for f in large_files[:2]),
            )
        )
    if not has_tests:
        matrix_rows.append(("P0", "Create test suite", "4h", "Critical", "All core modules"))
    elif test_count < total_src // 2:
        matrix_rows.append(
            (
                "P1",
                "Expand test coverage",
                f"{(total_src - test_count) * 30}m",
                "High",
                "Untested modules",
            )
        )
    if not has_ci:
        matrix_rows.append(("P1", "CI/CD pipeline", "3h", "High", "Repository root"))
    matrix_rows.append(("P2", "Integration tests", "5h", "Medium", "Cross-module boundaries"))
    matrix_rows.append(("P2", "API documentation", "3h", "Medium", "Public interfaces"))
    matrix_rows.append(("P3", "Performance profiling", "4h", "Low", "Hot paths"))
    matrix_rows.append(("P3", "Dependency audit", "2h", "Low", "package config"))

    for priority, task, effort, impact, target in matrix_rows:
        lines.append(f"| **{priority}** | {task} | {effort} | {impact} | {target} |")

    lines.append("")
    return "\n".join(lines)


def _build_risk_assessment(model: "CodebaseModel") -> str:
    """Analyse codebase quality risks based on metrics."""
    lines = ["## Risk Assessment\n"]

    src_files = [f for f in model.files if not f.is_test]
    doc_count, total_src, doc_pct = _doc_coverage(model.files)
    test_count = len(model.test_files)
    large_files = [f for f in src_files if f.line_count > 300]
    _avg_complexity(model.files)

    risks = []

    # Documentation risk
    if doc_pct < 30:
        risks.append(
            (
                "🔴 High",
                "Low Documentation Coverage",
                f"Only {doc_pct:.0f}% of modules have docstrings. "
                "This increases onboarding time and maintenance burden.",
                "Add docstrings to all public modules and classes",
            )
        )
    elif doc_pct < 60:
        risks.append(
            (
                "🟡 Medium",
                "Moderate Documentation Gaps",
                f"{doc_pct:.0f}% of modules documented. Some modules lack sufficient documentation.",
                "Document remaining modules, prioritizing public APIs",
            )
        )
    else:
        risks.append(
            (
                "🟢 Low",
                "Good Documentation Coverage",
                f"{doc_pct:.0f}% of modules have documentation.",
                "Maintain current standards",
            )
        )

    # Test coverage risk
    if test_count == 0:
        risks.append(
            (
                "🔴 High",
                "No Test Coverage",
                "No test files detected in the project.",
                "Establish unit test suite for core modules",
            )
        )
    elif test_count < total_src * 0.3:
        risks.append(
            (
                "🟡 Medium",
                "Low Test-to-Source Ratio",
                f"{test_count} test files for {total_src} source modules ({_pct(test_count, total_src)}).",
                "Add tests for untested modules",
            )
        )
    else:
        risks.append(
            (
                "🟢 Low",
                "Adequate Test Coverage",
                f"{test_count} test files cover {total_src} source modules.",
                "Continue expanding tests with new features",
            )
        )

    # Complexity risk
    if large_files:
        risks.append(
            (
                "🟡 Medium",
                "Module Complexity",
                f"{len(large_files)} modules exceed 300 lines "
                f"(largest: `{large_files[0].path}` at {large_files[0].line_count} lines).",
                "Refactor into smaller, focused modules",
            )
        )
    else:
        risks.append(
            ("🟢 Low", "Module Size", "All modules are under 300 lines.", "Maintain current module boundaries")
        )

    # Architecture risk
    if len(model.architecture_layers) <= 1:
        risks.append(
            (
                "🟡 Medium",
                "Flat Architecture",
                "No clear architectural layering detected.",
                "Introduce separation of concerns with distinct layers",
            )
        )
    else:
        risks.append(
            (
                "🟢 Low",
                "Layered Architecture",
                f"{len(model.architecture_layers)} distinct layers identified.",
                "Maintain layer boundaries",
            )
        )

    # Dependency risk
    ext_deps = len(model.dependencies)
    if ext_deps > 20:
        risks.append(
            (
                "🟡 Medium",
                "Dependency Count",
                f"{ext_deps} external dependencies detected.",
                "Audit dependencies for security and necessity",
            )
        )

    lines.append("| Risk Level | Area | Finding | Mitigation |")
    lines.append("|-----------|------|---------|------------|")

    for level, area, finding, mitigation in risks:
        lines.append(f"| {level} | **{area}** | {finding} | {mitigation} |")

    lines.append("")

    # Overall risk score
    high_count = sum(1 for r in risks if "High" in r[0])
    med_count = sum(1 for r in risks if "Medium" in r[0])
    sum(1 for r in risks if "Low" in r[0])

    if high_count >= 2:
        overall = "🔴 **High** — Significant improvements needed before production deployment"
    elif high_count >= 1 or med_count >= 2:
        overall = "🟡 **Medium** — Some areas need attention but overall structure is sound"
    else:
        overall = "🟢 **Low** — The codebase demonstrates good engineering practices"

    lines.append(f"\n**Overall Risk Level:** {overall}\n")
    return "\n".join(lines)


def _build_dependency_graph(model: "CodebaseModel") -> str:
    lines = [
        "## Dependency Graph\n",
        "Internal module dependency graph based on import analysis:\n",
        "```mermaid",
        "graph TD",
    ]

    edges: set[tuple[str, str]] = set()
    edge_count = 0
    max_edges = 25

    for fa in model.files:
        if fa.is_test:
            continue
        src_id = _mermaid_id(fa.path)
        for imp in fa.imports:
            imp.replace(".", "/")
            for target in model.files:
                if target.is_test:
                    continue
                target_stem = target.path.replace("/", ".").replace("\\", ".").removesuffix(".py")
                if imp in target_stem or target_stem.endswith(imp):
                    edge = (src_id, _mermaid_id(target.path))
                    if edge not in edges and edge[0] != edge[1]:
                        edges.add(edge)
                        edge_count += 1
                        if edge_count >= max_edges:
                            break
            if edge_count >= max_edges:
                break
        if edge_count >= max_edges:
            break

    node_ids: set[str] = set()
    for a, b in edges:
        node_ids.add(a)
        node_ids.add(b)

    for fa in model.files:
        nid = _mermaid_id(fa.path)
        if nid in node_ids:
            label = Path(fa.path).stem
            lines.append(f'    {nid}["{label}"]')

    for a, b in sorted(edges):
        lines.append(f"    {a} --> {b}")

    if not edges:
        lines.append('    root["(no internal cross-imports detected)"]')

    lines.append("```\n")

    # Identify most-imported modules (hub modules)
    import_counts: Counter[str] = Counter()
    for _, b in edges:
        import_counts[b] += 1

    if import_counts:
        top_hubs = import_counts.most_common(5)
        lines.append("### Most-Connected Modules\n")
        lines.append("| Module | Imported By | Role |")
        lines.append("|--------|------------|------|")
        for nid, count in top_hubs:
            # Reverse-lookup the filename
            orig_path = ""
            for fa in model.files:
                if _mermaid_id(fa.path) == nid:
                    orig_path = fa.path
                    break
            role = "Core/Utility" if count >= 3 else "Shared Component"
            lines.append(f"| `{orig_path or nid}` | {count} modules | {role} |")
        lines.append("")

    return "\n".join(lines)


def _build_module_docs(model: "CodebaseModel") -> str:
    lines = ["## Module Documentation\n"]

    documented_files = [f for f in model.files if not f.is_test and (f.classes or f.functions or f.module_docstring)]

    if not documented_files:
        lines.append("_No documented modules found._\n")
        return "\n".join(lines)

    for fa in documented_files[:30]:
        lines.append(f"### `{fa.path}`\n")

        if fa.module_docstring:
            ds = fa.module_docstring
            if len(ds) > 500:
                ds = ds[:500] + "..."
            lines.append(f"{ds}\n")

        # File stats line
        n_classes = len(fa.classes)
        n_funcs = len(fa.functions)
        n_methods = sum(len(c.methods) for c in fa.classes)
        stats = f"**{fa.line_count} lines** | "
        if n_classes:
            stats += f"{_plural(n_classes, 'class', 'classes')} | "
        if n_funcs:
            stats += f"{_plural(n_funcs, 'function')} | "
        if n_methods:
            stats += f"{_plural(n_methods, 'method')} | "
        lines.append(stats.rstrip(" |") + "\n")

        if fa.classes:
            for ci in fa.classes:
                bases = f" *({', '.join(ci.bases)})*" if ci.bases else ""
                lines.append(f"**class `{ci.name}`**{bases}")
                if ci.docstring:
                    short_doc = ci.docstring.split("\n")[0]
                    lines.append(f": {short_doc}\n")
                else:
                    lines.append("")

                public_methods = [m for m in ci.methods if not m.name.startswith("_") or m.name == "__init__"]
                if public_methods:
                    lines.append("| Method | Async | Args | Returns | Description |")
                    lines.append("|--------|-------|------|---------|-------------|")
                    for m in public_methods[:10]:
                        is_async = "✓" if m.is_async else ""
                        args_str = ", ".join(a for a in m.args if a != "self")[:40]
                        ret = m.return_type or ""
                        desc = m.docstring.split("\n")[0][:60] if m.docstring else ""
                        lines.append(f"| `{m.name}` | {is_async} | {args_str} | {ret} | {desc} |")
                    if len(public_methods) > 10:
                        lines.append(f"| ... | | | | *+{len(public_methods) - 10} more methods* |")
                    lines.append("")

        if fa.functions:
            public_funcs = [f for f in fa.functions if not f.name.startswith("_")]
            if public_funcs:
                lines.append("| Function | Async | Args | Returns | Description |")
                lines.append("|----------|-------|------|---------|-------------|")
                for func in public_funcs[:10]:
                    is_async = "✓" if func.is_async else ""
                    args_str = ", ".join(func.args)[:40]
                    ret = func.return_type or ""
                    desc = func.docstring.split("\n")[0][:60] if func.docstring else ""
                    lines.append(f"| `{func.name}` | {is_async} | {args_str} | {ret} | {desc} |")
                if len(public_funcs) > 10:
                    lines.append(f"| ... | | | | *+{len(public_funcs) - 10} more functions* |")
                lines.append("")

    return "\n".join(lines)


def _build_test_section(model: "CodebaseModel") -> str:
    test_files = [f for f in model.files if f.is_test]
    if not test_files:
        return ""

    total_test_lines = sum(f.line_count for f in test_files)
    total_test_funcs = sum(len(f.functions) for f in test_files)

    lines = [
        "## Test Coverage\n",
        f"The project includes **{_plural(len(test_files), 'test file')}** "
        f"with **{total_test_lines:,} lines of test code** and an estimated "
        f"**{total_test_funcs} test functions**.\n",
        "| Test File | Lines | Functions | Description |",
        "|-----------|------:|----------:|-------------|",
    ]
    for fa in sorted(test_files, key=lambda f: f.path):
        n_funcs = len(fa.functions)
        desc = fa.summary or fa.module_docstring.split("\n")[0][:50] if fa.module_docstring else ""
        if not desc:
            desc = f"Tests for {Path(fa.path).stem.replace('test_', '')}"
        lines.append(f"| `{fa.path}` | {fa.line_count} | {n_funcs} | {desc} |")

    lines.append("")
    return "\n".join(lines)


def _build_config_section(model: "CodebaseModel") -> str:
    if not model.config_files:
        return ""

    lines = [
        "## Configuration Files\n",
        f"The project uses **{_plural(len(model.config_files), 'configuration file')}**:\n",
    ]
    for cf in sorted(model.config_files):
        # Infer purpose from filename
        purpose = _config_purpose(cf)
        lines.append(f"- `{cf}` — {purpose}")

    lines.append("")
    return "\n".join(lines)


def _config_purpose(filename: str) -> str:
    """Guess the purpose of a config file from its name."""
    mapping = {
        "pyproject.toml": "Python project configuration and build settings",
        "setup.py": "Python package setup script",
        "setup.cfg": "Python package configuration",
        "requirements.txt": "Python dependency pinning",
        "Pipfile": "Pipenv dependency management",
        "package.json": "Node.js package configuration and scripts",
        "tsconfig.json": "TypeScript compiler configuration",
        "Cargo.toml": "Rust project configuration",
        "go.mod": "Go module definition",
        "Dockerfile": "Container image build instructions",
        "docker-compose.yml": "Multi-container Docker orchestration",
        "docker-compose.yaml": "Multi-container Docker orchestration",
        "Makefile": "Build automation rules",
        ".env.example": "Environment variable template",
        ".env.sample": "Environment variable template",
        "vercel.json": "Vercel deployment configuration",
        "netlify.toml": "Netlify deployment configuration",
    }
    return mapping.get(filename, "Project configuration")


def _build_next_steps(model: "CodebaseModel") -> str:
    lines = ["## Recommended Next Steps\n"]

    doc_count, total_src, doc_pct = _doc_coverage(model.files)
    test_count = len(model.test_files)
    src_files = [f for f in model.files if not f.is_test]

    steps = []

    if doc_pct < 80:
        steps.append(
            f"**Improve documentation coverage** — Currently at {doc_pct:.0f}%. "
            f"Add module docstrings and class documentation to the "
            f"{total_src - doc_count} undocumented modules to reach 80%+ coverage."
        )

    if test_count == 0:
        steps.append(
            "**Establish testing infrastructure** — No tests detected. "
            "Start with unit tests for the most critical modules, "
            "then add integration tests for cross-module interactions."
        )
    elif test_count < total_src * 0.5:
        steps.append(
            f"**Expand test coverage** — {test_count} test files for {total_src} modules. "
            "Add tests focusing on untested core functionality."
        )

    large_files = [f for f in src_files if f.line_count > 300]
    if large_files:
        steps.append(
            f"**Refactor large modules** — {len(large_files)} modules exceed 300 lines. "
            f"Break `{large_files[0].path}` ({large_files[0].line_count} lines) into "
            f"smaller, focused components."
        )

    if not any("docker" in c.lower() for c in model.config_files):
        steps.append(
            "**Containerize the application** — Add Dockerfile for consistent development and deployment environments."
        )

    steps.append(
        "**Continuous integration** — Set up automated testing, linting, and documentation generation on every commit."
    )

    for i, step in enumerate(steps[:5], 1):
        lines.append(f"{i}. {step}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_template_documentation(
    model: "CodebaseModel",
    *,
    progress_callback=None,
) -> str:
    """Generate comprehensive documentation from code analysis — no LLM needed.

    Produces a rich, professional Markdown document with data-driven
    narrative prose, Mermaid architecture diagrams, pie charts, class
    diagrams, tables, risk assessment, and implementation plan.

    Parameters
    ----------
    model
        The analyzed codebase model from ``CodebaseAnalyzer``.
    progress_callback
        Optional callable(section_name, section_index, total_sections).

    Returns
    -------
    str
        Complete Markdown document.
    """
    total_sections = 11

    def _progress(name: str, idx: int):
        if progress_callback:
            progress_callback(name, idx, total_sections)

    sections: list[str] = []

    _progress("Header", 1)
    sections.append(_build_header(model))
    sections.append(_build_table_of_contents(model))

    _progress("Executive Summary", 2)
    sections.append(_build_executive_summary(model))

    _progress("System Architecture", 3)
    sections.append(_build_architecture_section(model))

    _progress("Language Breakdown", 4)
    lang_section = _build_language_breakdown(model)
    if lang_section:
        sections.append(lang_section)

    _progress("Technology Stack", 5)
    tech_section = _build_tech_stack(model)
    if tech_section:
        sections.append(tech_section)

    _progress("Codebase Status", 6)
    sections.append(_build_codebase_status(model))

    _progress("Implementation Plan", 7)
    sections.append(_build_implementation_plan(model))

    _progress("Risk Assessment", 8)
    sections.append(_build_risk_assessment(model))

    _progress("Dependency Graph", 9)
    sections.append(_build_dependency_graph(model))

    _progress("Module Documentation", 10)
    sections.append(_build_module_docs(model))

    _progress("Final Sections", 11)
    test_section = _build_test_section(model)
    if test_section:
        sections.append(test_section)

    config_section = _build_config_section(model)
    if config_section:
        sections.append(config_section)

    sections.append(_build_next_steps(model))

    logger.info("Template documentation generated: %d sections", len(sections))
    return "\n\n---\n\n".join(sections)
