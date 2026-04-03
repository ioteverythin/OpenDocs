"""Narrative documentation generator — uses an LLM to produce prose from code analysis.

Given a ``CodebaseModel`` (from ``CodebaseAnalyzer``), this module generates
professional, narrative Markdown documentation in the style of the Dubai AI
Voice Agent pitch document:

- Executive Summary (prose, not bullet points)
- System Architecture (narrative with Mermaid diagrams)
- Codebase Status (module table with explanatory prose)
- Implementation Plan (phased priorities P0-P3)
- Priority Matrix (table with effort/impact)
- Technology Stack (table with rationale)
- Infrastructure Requirements
- Recommended Next Steps

Each section is generated via a focused LLM prompt so even a small 3.8B
model can produce quality output one section at a time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..llm.providers import LLMProvider
    from .code_analyzer import CodebaseModel

logger = logging.getLogger("opendocs.core.narrative_generator")

# ---------------------------------------------------------------------------
# Section-specific prompts
# ---------------------------------------------------------------------------

_EXECUTIVE_SUMMARY_PROMPT = """\
You are a senior technical writer creating an Executive Summary for a software project.

PROJECT: {project_name}
STATS:
- {total_files} source files, {total_lines} lines of code
- Languages: {languages}
- Key technologies: {technologies}
- Architecture layers: {layers}
- Entry points: {entry_points}

KEY MODULES:
{key_modules}

Write a 2-3 paragraph Executive Summary that:
1. Opens with what this project IS and its purpose
2. Describes the scale and scope (lines of code, modules, test coverage)
3. Highlights the core technology choices and architectural approach
4. Mentions readiness/maturity level

Write in confident professional prose. Be specific — cite actual module names, \
tech stack items, and concrete numbers. No bullet points — flowing paragraphs only."""

_ARCHITECTURE_PROMPT = """\
You are a senior software architect writing the System Architecture section of a technical document.

PROJECT: {project_name}

ARCHITECTURE LAYERS:
{layers_detail}

COMPONENT RELATIONSHIPS:
{relationships}

Write 2-3 paragraphs describing the system architecture:
1. Start with a high-level overview of the architecture pattern (layered, microservice, etc.)
2. Describe how data/requests flow through the layers
3. Explain key component interactions and dependencies

Reference specific module names and class names. Write in clear professional prose. \
Do NOT use bullet points — write flowing paragraphs that explain HOW things connect."""

_IMPLEMENTATION_PLAN_PROMPT = """\
You are a technical lead writing an Implementation Plan & Priority Matrix.

PROJECT: {project_name}

CURRENT STATE:
- Total modules: {total_modules}
- Test files: {test_count}
- Entry points: {entry_points}
- Config files: {config_count}

MODULES & STATUS:
{module_status}

TECHNOLOGY STACK:
{tech_stack}

Write:
1. An "Implementation Plan" section with 4 priority phases:
   - P0 — Critical (must fix now)
   - P1 — High Priority (next sprint)
   - P2 — Medium Priority (next quarter)
   - P3 — Nice to Have (backlog)

   For each phase, write 2-4 specific, actionable items with effort estimates.
   Reference actual module names and specific areas of the codebase.

2. A "Priority Matrix" as a Markdown table with columns:
   | Priority | Task | Effort | Impact | Module |
   Fill with 8-12 concrete tasks derived from the codebase analysis.

3. A "Recommended Next Steps" section (3-5 numbered items with rationale).

Be specific. Reference real module names, class names, and technologies found. \
These should be realistic recommendations based on the code you see."""

_INFRASTRUCTURE_PROMPT = """\
You are a DevOps architect writing Infrastructure Requirements for a software project.

PROJECT: {project_name}

TECHNOLOGY STACK:
{tech_stack}

ARCHITECTURE:
{architecture_summary}

CONFIG FILES PRESENT:
{config_files}

Write:
1. An "Infrastructure Requirements" section as a Markdown table:
   | Component | Requirement | Specification |
   Include compute, storage, runtime, deployment, and monitoring needs.
   Base these on the ACTUAL technologies detected (e.g. if using FastAPI, mention ASGI server needs).

2. A "Technology Stack" table:
   | Technology | Category | Purpose | Files |
   For each technology, explain WHY it's used based on context.

Keep it practical and specific to THIS project's needs."""


# ---------------------------------------------------------------------------
# Helper: build context strings from CodebaseModel
# ---------------------------------------------------------------------------


def _build_context(model: "CodebaseModel") -> dict[str, str]:
    """Build prompt-ready context strings from the analysis model."""
    ctx: dict[str, str] = {}

    ctx["project_name"] = model.project_name or "Project"
    ctx["total_files"] = str(model.total_files)
    ctx["total_lines"] = f"{model.total_code_lines:,}"

    ctx["languages"] = ", ".join(
        f"{lang} ({count} files)" for lang, count in sorted(model.languages.items(), key=lambda x: -x[1])
    )

    tech_names = [t.name for t in model.tech_stack[:12]]
    ctx["technologies"] = ", ".join(tech_names) if tech_names else "standard library"

    ctx["layers"] = ", ".join(layer.name for layer in model.architecture_layers) or "single layer"

    ctx["entry_points"] = ", ".join(model.entry_points[:5]) if model.entry_points else "none detected"

    # Key modules — top 8 non-test files with summaries
    key_parts = []
    for fa in model.files:
        if fa.is_test or not fa.summary:
            continue
        classes = ", ".join(c.name for c in fa.classes) if fa.classes else ""
        funcs = ", ".join(f.name for f in fa.functions if not f.name.startswith("_"))[:80] if fa.functions else ""
        line = f"- {fa.path} ({fa.line_count} lines): {fa.summary}"
        if classes:
            line += f"  Classes: {classes}"
        if funcs:
            line += f"  Functions: {funcs}"
        key_parts.append(line)
        if len(key_parts) >= 10:
            break
    ctx["key_modules"] = "\n".join(key_parts) if key_parts else "(no module summaries available)"

    # Architecture layers detail
    layer_parts = []
    for layer in model.architecture_layers:
        detail = f"### {layer.name}\n{layer.description}\nModules: "
        mods = layer.modules[:8]
        detail += ", ".join(mods)
        if len(layer.modules) > 8:
            detail += f" (+{len(layer.modules) - 8} more)"
        layer_parts.append(detail)
    ctx["layers_detail"] = "\n\n".join(layer_parts) if layer_parts else "(no layers detected)"

    # Relationships — internal imports between modules
    rel_parts = []
    {fa.path for fa in model.files}
    for fa in model.files[:20]:
        if fa.is_test:
            continue
        internal_imports = []
        for imp in fa.imports:
            imp.replace(".", "/")
            for target in model.files:
                if target.is_test:
                    continue
                target_stem = target.path.replace("/", ".").replace("\\", ".").removesuffix(".py")
                if imp in target_stem or target_stem.endswith(imp):
                    internal_imports.append(target.path)
                    break
        if internal_imports:
            rel_parts.append(f"- {fa.path} → {', '.join(internal_imports[:5])}")
    ctx["relationships"] = "\n".join(rel_parts[:15]) if rel_parts else "(no cross-module imports)"

    # Module status for implementation plan
    status_parts = []
    for fa in sorted(model.files, key=lambda f: f.path):
        if fa.is_test:
            continue
        purpose = fa.summary or (fa.module_docstring.split("\n")[0][:60] if fa.module_docstring else "")
        if not purpose:
            purpose = f"{fa.language} module"
        n_classes = len(fa.classes)
        n_funcs = len(fa.functions)
        has_docstrings = bool(fa.module_docstring) or any(c.docstring for c in fa.classes)
        status = "documented" if has_docstrings else "undocumented"
        status_parts.append(
            f"- {fa.path}: {purpose} ({fa.line_count} lines, {n_classes} classes, {n_funcs} functions, {status})"
        )
    ctx["module_status"] = "\n".join(status_parts[:25]) if status_parts else "(no modules)"
    ctx["total_modules"] = str(len([f for f in model.files if not f.is_test]))
    ctx["test_count"] = str(len(model.test_files))
    ctx["config_count"] = str(len(model.config_files))

    # Tech stack
    tech_parts = []
    for tech in model.tech_stack:
        used_in = ", ".join(tech.source_files[:3])
        if len(tech.source_files) > 3:
            used_in += f" +{len(tech.source_files) - 3} more"
        tech_parts.append(f"- {tech.name} ({tech.category}): found in {used_in}")
    ctx["tech_stack"] = "\n".join(tech_parts) if tech_parts else "(no frameworks detected)"

    # Architecture summary (shorter)
    ctx["architecture_summary"] = (
        ", ".join(f"{layer.name} ({len(layer.modules)} modules)" for layer in model.architecture_layers)
        or "flat structure"
    )

    # Config files
    ctx["config_files"] = ", ".join(sorted(model.config_files)[:10]) if model.config_files else "(none)"

    return ctx


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


@dataclass
class _SectionResult:
    """Result of generating a single section."""

    heading: str
    content: str
    is_generated: bool = True  # True = LLM produced, False = static fallback


def _generate_section(
    llm: "LLMProvider",
    system: str,
    user_prompt: str,
    section_name: str,
) -> str:
    """Call the LLM for a single section with error handling."""
    try:
        result = llm.chat(system, user_prompt)
        if result and len(result.strip()) > 50:
            return result.strip()
        logger.warning("LLM returned insufficient content for %s", section_name)
    except Exception as exc:
        logger.warning("LLM call failed for %s: %s", section_name, exc)
    return ""


_SYSTEM_ROLE = (
    "You are an expert technical documentation writer. "
    "Write in clear, confident professional prose. "
    "Be specific — reference actual module names, technologies, and numbers. "
    "Output Markdown-formatted text. Do NOT include the section heading — just the content."
)


def generate_narrative_markdown(
    model: "CodebaseModel",
    llm: "LLMProvider",
    *,
    progress_callback=None,
) -> str:
    """Generate a full narrative Markdown document from a codebase analysis.

    Uses the LLM to generate prose for each section independently,
    then assembles them with static tables and Mermaid diagrams.

    Parameters
    ----------
    model
        The analyzed codebase model from ``CodebaseAnalyzer``.
    llm
        Any LLM provider (SLM, OpenAI, etc.) that has a ``.chat()`` method.
    progress_callback
        Optional callable(section_name, section_index, total_sections) for
        progress reporting.

    Returns
    -------
    str
        Complete Markdown document.
    """

    ctx = _build_context(model)
    title = ctx["project_name"]

    sections: list[str] = []
    total_sections = 6  # number of LLM calls we'll make

    def _progress(name: str, idx: int):
        if progress_callback:
            progress_callback(name, idx, total_sections)

    # ── Title & metadata ─────────────────────────────────────────────
    header_lines = [f"# {title} — Technical Documentation", ""]
    if model.description:
        header_lines.append(f"> {model.description}")
        header_lines.append("")
    if model.version:
        header_lines.append(f"**Version:** {model.version}")
    if model.license:
        header_lines.append(f"**License:** {model.license}")
    header_lines.append(f"**Generated from:** codebase analysis of `{model.root_path}`")
    header_lines.append("")
    sections.append("\n".join(header_lines))

    # ── 1. Executive Summary (LLM) ──────────────────────────────────
    _progress("Executive Summary", 1)
    logger.info("Generating Executive Summary...")
    exec_prompt = _EXECUTIVE_SUMMARY_PROMPT.format(**ctx)
    exec_text = _generate_section(llm, _SYSTEM_ROLE, exec_prompt, "Executive Summary")

    if exec_text:
        sections.append(f"## Executive Summary\n\n{exec_text}\n")
    else:
        # Fallback: use static summary from code_analyzer
        sections.append(_static_executive_summary(model, ctx))

    # ── 2. System Architecture (LLM + Mermaid diagram) ──────────────
    _progress("System Architecture", 2)
    logger.info("Generating System Architecture...")
    arch_prompt = _ARCHITECTURE_PROMPT.format(**ctx)
    arch_text = _generate_section(llm, _SYSTEM_ROLE, arch_prompt, "System Architecture")

    arch_section = ["## System Architecture\n"]
    if arch_text:
        arch_section.append(arch_text)
        arch_section.append("")
    else:
        arch_section.append(
            "The architecture spans multiple layers, from entry points and CLI interfaces "
            "through core business logic to output generation and external integrations.\n"
        )

    # Always include the Mermaid diagram (deterministic)
    arch_section.append(_build_architecture_mermaid(model))
    sections.append("\n".join(arch_section))

    # ── 3. Codebase Status (static table — always accurate) ─────────
    _progress("Codebase Status", 3)
    sections.append(_build_codebase_status_table(model))

    # ── 4. Technology Stack (static table + LLM rationale) ──────────
    _progress("Technology Stack", 4)
    logger.info("Generating Infrastructure & Technology...")
    infra_prompt = _INFRASTRUCTURE_PROMPT.format(**ctx)
    infra_text = _generate_section(llm, _SYSTEM_ROLE, infra_prompt, "Infrastructure")

    if infra_text:
        sections.append(f"## Infrastructure Requirements\n\n{infra_text}\n")
    else:
        sections.append(_build_tech_stack_table(model))

    # ── 5. Implementation Plan & Priority Matrix (LLM) ──────────────
    _progress("Implementation Plan", 5)
    logger.info("Generating Implementation Plan...")
    impl_prompt = _IMPLEMENTATION_PLAN_PROMPT.format(**ctx)
    impl_text = _generate_section(llm, _SYSTEM_ROLE, impl_prompt, "Implementation Plan")

    if impl_text:
        sections.append(f"## Implementation Plan\n\n{impl_text}\n")
    else:
        sections.append(_static_implementation_plan(model, ctx))

    # ── 6. Dependency Graph (deterministic Mermaid) ──────────────────
    _progress("Dependency Graph", 6)
    sections.append(_build_dependency_graph(model))

    # ── 7. Detailed Module Documentation (static — always accurate) ──
    sections.append(_build_module_docs(model))

    # ── 8. Test Coverage & Config (static) ───────────────────────────
    if model.test_files:
        sections.append(_build_test_section(model))
    if model.config_files:
        sections.append(_build_config_section(model))

    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Static section builders — always accurate, used alongside or as fallbacks
# ---------------------------------------------------------------------------


def _static_executive_summary(model: "CodebaseModel", ctx: dict) -> str:
    """Fallback executive summary when LLM fails."""
    lines = ["## Executive Summary\n"]
    lines.append(
        f"The **{ctx['project_name']}** codebase consists of **{model.total_files:,} source files** "
        f"comprising **{model.total_code_lines:,} lines of code** ({ctx['languages']}). "
        f"The project leverages {ctx['technologies']} as its core technology stack.\n"
    )
    src_count = len([f for f in model.files if not f.is_test])
    test_count = len(model.test_files)
    lines.append(
        f"The codebase contains **{src_count} source modules** and "
        f"**{test_count} test file{'s' if test_count != 1 else ''}**, "
        f"with **{len(model.config_files)} configuration file{'s' if len(model.config_files) != 1 else ''}** "
        f"and **{len(model.entry_points)} identified entry point{'s' if len(model.entry_points) != 1 else ''}**.\n"
    )
    return "\n".join(lines)


def _build_architecture_mermaid(model: "CodebaseModel") -> str:
    """Build a Mermaid C4 architecture diagram."""
    lines = ["```mermaid", "graph TB"]

    layer_ids: dict[str, str] = {}
    for i, layer in enumerate(model.architecture_layers):
        lid = f"L{i}"
        layer_ids[layer.name] = lid
        safe_name = layer.name.replace('"', "'")
        n_mods = len(layer.modules)
        lines.append(f'    {lid}["{safe_name}<br/><i>{n_mods} module(s)</i>"]')

    if len(model.architecture_layers) > 1:
        layer_keys = list(layer_ids.keys())
        for i in range(len(layer_keys) - 1):
            a = layer_ids[layer_keys[i]]
            b = layer_ids[layer_keys[i + 1]]
            lines.append(f"    {a} --> {b}")

    lines.append("```")
    return "\n".join(lines)


def _build_codebase_status_table(model: "CodebaseModel") -> str:
    """Build the Codebase Status section with a module table."""
    lines = [
        "## Codebase Status\n",
        "A thorough audit of the codebase reveals the following modules, their purpose, and current status.\n",
        "| Module | Functionality | Lines | Status |",
        "|--------|--------------|------:|--------|",
    ]

    for fa in sorted(model.files, key=lambda f: f.path):
        if fa.is_test:
            continue
        purpose = fa.summary or ""
        if not purpose and fa.module_docstring:
            purpose = fa.module_docstring.split("\n")[0][:60]
        if not purpose:
            purpose = f"{fa.language.title()} module"

        # Determine status
        has_docs = bool(fa.module_docstring) or any(c.docstring for c in fa.classes)
        n_funcs = len(fa.functions) + sum(len(c.methods) for c in fa.classes)
        if has_docs and n_funcs > 0:
            status = "✅ Complete"
        elif n_funcs > 0:
            status = "⚠️ Needs Documentation"
        else:
            status = "📋 Skeleton"

        lines.append(f"| `{fa.path}` | {purpose} | {fa.line_count} | {status} |")

    lines.append("")
    return "\n".join(lines)


def _build_tech_stack_table(model: "CodebaseModel") -> str:
    """Build Technology Stack table (static fallback)."""
    if not model.tech_stack:
        return ""

    lines = [
        "## Technology Stack\n",
        "| Technology | Category | Used In |",
        "|-----------|----------|---------|",
    ]

    for tech in model.tech_stack:
        used_in = ", ".join(f"`{f}`" for f in tech.source_files[:3])
        if len(tech.source_files) > 3:
            used_in += f" +{len(tech.source_files) - 3} more"
        lines.append(f"| {tech.name} | {tech.category} | {used_in} |")

    lines.append("")
    return "\n".join(lines)


def _static_implementation_plan(model: "CodebaseModel", ctx: dict) -> str:
    """Fallback implementation plan when LLM fails."""
    lines = [
        "## Implementation Plan\n",
        "### P0 — Critical\n",
        "- Complete documentation for all public modules and classes",
        "- Add type annotations to undocumented functions",
        "",
        "### P1 — High Priority\n",
        "- Expand test coverage for core modules",
        "- Set up CI/CD pipeline with automated testing",
        "",
        "### P2 — Medium Priority\n",
        "- Refactor large modules (>300 lines) into smaller components",
        "- Add integration tests for external dependencies",
        "",
        "### P3 — Nice to Have\n",
        "- Performance profiling and optimization",
        "- Expand documentation with usage examples",
        "",
        "## Recommended Next Steps\n",
        "1. **Improve documentation coverage** — Several modules lack docstrings",
        f"2. **Expand test suite** — Currently {ctx['test_count']} test files",
        f"3. **Review architecture** — {len(model.architecture_layers)} layers identified for potential consolidation",
        "",
    ]
    return "\n".join(lines)


def _build_dependency_graph(model: "CodebaseModel") -> str:
    """Build the Mermaid dependency graph."""
    from pathlib import Path as _Path

    lines = [
        "## Dependency Graph\n",
        "Internal module dependency graph based on import analysis:\n",
        "```mermaid",
        "graph LR",
    ]

    edges: set[tuple[str, str]] = set()
    edge_count = 0
    max_edges = 40

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

    node_ids = set()
    for a, b in edges:
        node_ids.add(a)
        node_ids.add(b)

    for fa in model.files:
        nid = _mermaid_id(fa.path)
        if nid in node_ids:
            label = _Path(fa.path).stem
            lines.append(f'    {nid}["{label}"]')

    for a, b in sorted(edges):
        lines.append(f"    {a} --> {b}")

    if not edges:
        lines.append('    root["(no internal cross-imports detected)"]')

    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _build_module_docs(model: "CodebaseModel") -> str:
    """Build detailed module-by-module documentation."""
    lines = ["## Module Documentation\n"]

    documented_files = [f for f in model.files if not f.is_test and (f.classes or f.functions or f.module_docstring)]

    for fa in documented_files[:30]:
        lines.append(f"### `{fa.path}`\n")

        if fa.module_docstring:
            ds = fa.module_docstring
            if len(ds) > 500:
                ds = ds[:500] + "..."
            lines.append(f"{ds}\n")

        if fa.classes:
            for ci in fa.classes:
                bases = f" ({', '.join(ci.bases)})" if ci.bases else ""
                lines.append(f"**class `{ci.name}`**{bases}")
                if ci.docstring:
                    short_doc = ci.docstring.split("\n")[0]
                    lines.append(f": {short_doc}\n")
                else:
                    lines.append("")

                public_methods = [m for m in ci.methods if not m.name.startswith("_") or m.name == "__init__"]
                if public_methods:
                    lines.append("| Method | Async | Args | Description |")
                    lines.append("|--------|-------|------|-------------|")
                    for m in public_methods[:10]:
                        is_async = "Yes" if m.is_async else "No"
                        args_str = ", ".join(a for a in m.args if a != "self")[:40]
                        desc = m.docstring.split("\n")[0][:60] if m.docstring else ""
                        lines.append(f"| `{m.name}` | {is_async} | {args_str} | {desc} |")
                    lines.append("")

        if fa.functions:
            public_funcs = [f for f in fa.functions if not f.name.startswith("_")]
            if public_funcs:
                lines.append("| Function | Async | Args | Description |")
                lines.append("|----------|-------|------|-------------|")
                for func in public_funcs[:10]:
                    is_async = "Yes" if func.is_async else "No"
                    args_str = ", ".join(func.args)[:40]
                    desc = func.docstring.split("\n")[0][:60] if func.docstring else ""
                    lines.append(f"| `{func.name}` | {is_async} | {args_str} | {desc} |")
                lines.append("")

    return "\n".join(lines)


def _build_test_section(model: "CodebaseModel") -> str:
    """Build test files section."""
    lines = [
        "## Test Files\n",
        "| Test File | Lines |",
        "|-----------|------:|",
    ]
    for fa in model.files:
        if fa.is_test:
            lines.append(f"| `{fa.path}` | {fa.line_count} |")
    lines.append("")
    return "\n".join(lines)


def _build_config_section(model: "CodebaseModel") -> str:
    """Build configuration files section."""
    lines = ["## Configuration Files\n"]
    for cf in sorted(model.config_files):
        lines.append(f"- `{cf}`")
    lines.append("")
    return "\n".join(lines)


def _mermaid_id(path: str) -> str:
    """Make a path safe for Mermaid node IDs."""
    return path.replace("/", "_").replace("\\", "_").replace(".", "_").replace("-", "_").replace(" ", "_")
