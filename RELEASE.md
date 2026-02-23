# OpenDocs — Release Document

## Phase 2: Agentic Documentation Layer

**Version:** 0.5.0-alpha (internal)
**Date:** February 21, 2026
**Author:** ioteverythin
**Status:** Skeleton complete · Unit & integration tested · Pre-SaaS extraction

---

## Executive Summary

Phase 2 adds an **agentic AI layer** on top of the deterministic OpenDocs pipeline (v0.4.0). Instead of simply parsing a README and converting it, the system now runs a **Planner → Executor → Critic** loop that:

- **Detects** repo archetypes (microservices, ML, IaC, event-driven, data engineering)
- **Generates** domain-specific diagrams, model cards, and architecture sections
- **Validates** every generated claim against source evidence to prevent hallucinations
- **Produces** diff-aware incremental updates so docs stay in sync with code

This layer is designed as a **SaaS product** (not open-source) and will be extracted into a separate private repository.

---

## What's New

### Core Agent Architecture

| Component | File | Purpose |
|-----------|------|---------|
| **AgentBase** | `agents/base.py` | Abstract base class + shared Pydantic models (`ToolCall`, `PlanStep`, `AgentPlan`, `AgentResult`, `RepoProfile`, `RepoSignal`) |
| **PlannerAgent** | `agents/planner.py` | Reads repo signals + KG → builds step-by-step execution plan → routes to specialized sub-agents |
| **ExecutorAgent** | `agents/executor.py` | Dispatches `ToolCall` objects to registered MCP tool adapters, validates against contracts, registers evidence |
| **CriticAgent** | `agents/critic.py` | Evaluates evidence coverage across all artifacts, flags hallucinations, forces re-planning if below threshold |
| **AgentOrchestrator** | `agents/orchestrator.py` | Top-level coordinator: Plan → Execute → Critique → retry loop (configurable `max_retries`) |

### Evidence System

| Component | File | Purpose |
|-----------|------|---------|
| **EvidencePointer** | `agents/evidence.py` | Immutable reference linking a generated claim to its source (README section, code file, commit, API schema, etc.) |
| **Claim** | `agents/evidence.py` | A single generated assertion tied to evidence pointers — flagged as *assumption* if unsupported |
| **EvidenceCoverage** | `agents/evidence.py` | Per-artifact coverage scoring (% backed claims, confidence mean/min, trustworthiness heuristic) |
| **EvidenceRegistry** | `agents/evidence.py` | In-memory store for all pointers + claims during a pipeline run, with scoring queries |

### Privacy & Safety

| Mode | Behavior |
|------|----------|
| **STRICT** | No code content — agents see file *names*, section *titles*, and pre-computed summaries only. Code snippets replaced with `[code redacted]`. |
| **STANDARD** | Agents see RepoProfile, KG, section text, and short code snippets (≤ 20 lines). File names visible. |
| **PERMISSIVE** | Full file contents may be sent to agents. Use only for local/self-hosted LLM deployments. |

Implementation: `agents/privacy.py` — `PrivacyGuard` class with `sanitise_profile()`, `sanitise_evidence()`, `sanitise_context()`.

### MCP Tool Contracts (12 Tools)

| Tool Name | Category | Output | Auth |
|-----------|----------|--------|------|
| `repo.search` | repo | JSON | No |
| `repo.read` | repo | string | No |
| `repo.diff` | repo | JSON | No |
| `repo.summarize` | repo | markdown | No |
| `diagram.render` | diagram | SVG/PNG | No |
| `chart.generate` | chart | PNG/SVG | No |
| `figma.create_frame` | figma | JSON | Yes |
| `figma.add_nodes` | figma | JSON | Yes |
| `image.generate` | image | URL | Yes |
| `docx.refine` | doc | DOCX | No |
| `pptx.refine` | doc | PPTX | No |
| `confluence.publish` | publish | URL | Yes |

Each tool has a `ToolContract` with parameter schemas, validation, and privacy level. Contracts live in `agents/tools/contracts.py`. Adapter stubs in `agents/tools/`.

### Diff-Aware Pipeline

| Agent | File | Purpose |
|-------|------|---------|
| **DiffAgent** | `agents/diff/diff_agent.py` | Git diff between two refs → `DiffSummary` (files changed, additions/deletions) |
| **ImpactAgent** | `agents/diff/impact_agent.py` | Maps file diffs → KG entity/relation deltas (`ImpactReport`) |
| **RegenerationAgent** | `agents/diff/regen_agent.py` | Selectively rebuilds only impacted output formats |
| **ReleaseNotesAgent** | `agents/diff/release_notes_agent.py` | Generates Keep-a-Changelog Markdown from diff + impact data |

### Specialized Sub-Agents (5 Domains)

| Agent | Signals Detected | Artifacts Produced |
|-------|------------------|--------------------|
| **MicroservicesAgent** | `docker-compose`, `kubernetes`, `k8s` | Service dependency diagram (Mermaid), Architecture Overview section |
| **EventDrivenAgent** | `kafka`, `sqs`, `eventbridge`, `rabbitmq`, `nats` | Event flow diagram (Mermaid), Event Architecture section |
| **MLAgent** | `pytorch`, `tensorflow`, `huggingface`, `vector-db`, `rag` | ML pipeline diagram, Model Card (HuggingFace-style), ML Architecture section |
| **DataEngineeringAgent** | `airflow`, `dbt`, `spark`, `warehouse` | Data lineage diagram (Mermaid), Data Pipeline section |
| **InfraAgent** | `terraform`, `helm`, `pulumi`, `cloudformation` | Resource topology diagram (Mermaid), Infrastructure section |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  AgentOrchestrator                   │
│                                                     │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐      │
│   │ Planner  │──▶│ Executor │──▶│  Critic  │──┐   │
│   └──────────┘   └──────────┘   └──────────┘  │   │
│        ▲                                       │   │
│        └──────── retry if rejected ◀───────────┘   │
│                                                     │
│   ┌─────────────────────────────────────────────┐  │
│   │  Specialized Sub-Agents (activated by plan) │  │
│   │  Microservices · EventDriven · ML ·         │  │
│   │  DataEngineering · Infra                    │  │
│   └─────────────────────────────────────────────┘  │
│                                                     │
│   ┌─────────────────────────────────────────────┐  │
│   │  MCP Tool Bus (12 tool contracts)           │  │
│   │  repo.* · diagram.* · chart.* · figma.*     │  │
│   │  image.* · docx.* · pptx.* · confluence.*  │  │
│   └─────────────────────────────────────────────┘  │
│                                                     │
│   ┌──────────────┐  ┌────────────────────────┐     │
│   │ PrivacyGuard │  │  EvidenceRegistry      │     │
│   │ STRICT/STD/  │  │  Pointers → Claims →   │     │
│   │ PERMISSIVE   │  │  Coverage Scoring      │     │
│   └──────────────┘  └────────────────────────┘     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                Diff-Aware Pipeline                    │
│  DiffAgent → ImpactAgent → RegenAgent → ReleaseNotes │
└─────────────────────────────────────────────────────┘
```

---

## File Inventory

```
src/opendocs/agents/
├── __init__.py              # Package exports
├── base.py                  # AgentBase, AgentPlan, AgentResult, ToolCall, RepoProfile (~230 lines)
├── evidence.py              # EvidencePointer, Claim, EvidenceCoverage, EvidenceRegistry (~210 lines)
├── privacy.py               # PrivacyMode, PrivacyGuard (~156 lines)
├── planner.py               # PlannerAgent + signal-to-agent routing (~211 lines)
├── executor.py              # ExecutorAgent + tool dispatch (~140 lines)
├── critic.py                # CriticAgent + CriticVerdict
├── orchestrator.py          # AgentOrchestrator + OrchestrationResult (~299 lines)
├── diff/
│   ├── __init__.py
│   ├── diff_agent.py        # DiffAgent, FileDiff, DiffSummary (~124 lines)
│   ├── impact_agent.py      # ImpactAgent, EntityDelta, RelationDelta, ImpactReport (~217 lines)
│   ├── regen_agent.py       # RegenerationAgent (~108 lines)
│   └── release_notes_agent.py  # ReleaseNotesAgent, ReleaseNote, ReleaseNotes (~202 lines)
├── specialized/
│   ├── __init__.py
│   ├── microservices_agent.py   # MicroservicesAgent (~146 lines)
│   ├── event_driven_agent.py    # EventDrivenAgent (~133 lines)
│   ├── ml_agent.py              # MLAgent (~179 lines)
│   ├── data_engineering_agent.py # DataEngineeringAgent (~171 lines)
│   └── infra_agent.py           # InfraAgent (~186 lines)
└── tools/
    ├── __init__.py
    ├── contracts.py          # ToolContract, ToolParameter, TOOL_REGISTRY (12 tools, ~246 lines)
    ├── repo_tools.py         # RepoSearchTool, RepoReadTool, RepoDiffTool, RepoSummarizeTool (~172 lines)
    ├── diagram_tools.py      # DiagramRenderTool (~83 lines)
    ├── chart_tools.py        # ChartGenerateTool (~45 lines)
    ├── figma_tools.py        # FigmaCreateFrameTool, FigmaAddNodesTool (~59 lines)
    ├── image_tools.py        # ImageGenerateTool (~62 lines)
    ├── doc_tools.py          # DocxRefineTool, PptxRefineTool (~74 lines)
    └── publish_tools.py      # ConfluencePublishTool (~50 lines)

Total: ~27 files, ~3,200+ lines of agent code
```

---

## Test Coverage

### Unit Tests — 55 tests (`tests/test_agents.py`)

| Test Class | Tests | What's Covered |
|------------|-------|----------------|
| `TestBaseModels` | 6 | ToolCall defaults, PlanStep serialization, AgentPlan progress, AgentResult fields, RepoProfile signals, RepoSignal defaults |
| `TestEvidenceRegistry` | 7 | Pointer register/retrieve, claims with/without evidence, coverage computation, empty artifact, all-coverage, summary dict |
| `TestPrivacyGuard` | 8 | STRICT file-tree stripping, STANDARD preservation, PERMISSIVE passthrough, snippet redaction, snippet truncation, context sanitization, mode checks |
| `TestToolContracts` | 5 | 12-tool registry, expected tool names, valid params, missing required param, enum validation |
| `TestPlannerAgent` | 4 | Signal-to-agent detection, plain repo (no agents), plan production, activated agents metadata |
| `TestExecutorAgent` | 4 | No-step failure, unregistered tool skip, mock adapter success, adapter exception handling |
| `TestCriticAgent` | 4 | Good coverage approval, low coverage rejection, no-claims vacuous approval, verdict serialization |
| `TestDiffPipeline` | 8 | DiffAgent summary, ImpactAgent matching entities, ImpactAgent no-diff failure, RegenAgent empty impact, RegenAgent with impact, ReleaseNotes generation, DiffSummary paths, ImpactReport deltas |
| `TestSpecializedAgents` | 5×2 | Each of the 5 specialized agents: component/resource discovery + Mermaid diagram validation |
| `TestOrchestrator` | 3 | Full loop execution, summary output, STRICT privacy mode |

### Integration Tests — 3 repos (`test_agents_integration.py`)

| Repository | Signals Detected | Sub-Agents Activated | Artifacts Produced | Status |
|------------|-----------------|---------------------|-------------------|--------|
| [fastapi/fastapi](https://github.com/fastapi/fastapi) | None | — (base plan only) | Plan: 4 steps | ✅ Pass |
| [langgenius/dify](https://github.com/langgenius/dify) | `docker-compose`, `helm` | InfraAgent, MicroservicesAgent | `infra_topology_mermaid`, `infrastructure_md`, `service_diagram_mermaid`, `architecture_section_md` | ✅ Pass |
| [huggingface/transformers](https://github.com/huggingface/transformers) | `pytorch`, `huggingface` | MLAgent | `ml_pipeline_mermaid`, `model_card_md`, `ml_architecture_md` | ✅ Pass |

### Full Suite

```
191 tests passed (136 original pipeline + 55 agents) in ~7s
```

---

## Dependencies Added

```toml
[project.optional-dependencies]
agents = [
    "openai>=1.12",
    "langchain>=0.1",
    "langgraph>=0.0.30",
    "matplotlib>=3.8",
    "httpx>=0.27",
]
```

Install: `pip install opendocs[agents]`

---

## Known Limitations & TODOs

### Tool Adapters (Placeholder Status)

All 12 MCP tool adapters have interface stubs but lack real backend implementations:

| Adapter | Status | Next Step |
|---------|--------|-----------|
| `repo.search` | Stub | Wire ripgrep or `git grep` |
| `repo.read` | Partial (reads files) | Add privacy-filtered line range |
| `repo.diff` | Stub | Parse `git diff --stat` output |
| `repo.summarize` | Stub | Integrate OpenAI for summarization |
| `diagram.render` | Stub | Wire `mmdc` (mermaid-cli) or Mermaid.ink API |
| `chart.generate` | Stub | Wire matplotlib rendering |
| `figma.*` | Stub | Figma REST API integration |
| `image.generate` | Stub | DALL-E / Stable Diffusion API |
| `docx.refine` | Stub | LLM-guided section rewriting |
| `pptx.refine` | Stub | LLM-guided slide improvement |
| `confluence.publish` | Stub | Atlassian REST API |

### Signal Detection

- Duplicate signals possible (e.g., `['pytorch', 'pytorch']`) — needs deduplication
- File tree is empty when built from KG only (no GitHub API file listing)
- Pattern matching is keyword-based — could benefit from AST analysis

### LLM Integration

- Planner currently uses deterministic heuristics, not LLM-based planning
- Critic validation is coverage-metric-based, not semantic review
- Sub-agent descriptions are template-based, not LLM-generated

---

## Migration Plan

### Phase 2a: Extract to Private SaaS Repo

1. Create a new private repository (e.g., `ioteverythin/opendocs-agents`)
2. Move `src/opendocs/agents/` → new repo
3. Move `tests/test_agents.py` → new repo
4. Move `test_agents_integration.py` → new repo
5. Remove `[agents]` dependency group from open-source `pyproject.toml`
6. Set up new repo with its own `pyproject.toml`, CI/CD, and API layer

### Phase 2b: Wire Real Backends

1. Implement `repo.*` tools with local git CLI
2. Implement `diagram.render` with mermaid-cli
3. Implement `docx.refine` / `pptx.refine` with OpenAI API
4. Add GitHub API integration for file tree discovery
5. Replace deterministic planner with LLM-based planning

### Phase 2c: SaaS API

1. FastAPI endpoint wrapping `AgentOrchestrator.run()`
2. Webhook listener for GitHub push events → diff-aware pipeline
3. Authentication + usage metering
4. Dashboard for evidence coverage + artifact preview

---

## Baseline (v0.4.0 — Open Source)

For reference, the open-source release (v0.4.0 on PyPI) includes:

- 11 output formats (Word, PPTX, PDF, Blog, Jira, Changelog, LaTeX, One-Pager, Social Cards, Analysis, Mermaid)
- 7 themes (corporate, ocean, sunset, dark, minimal, emerald, royal)
- Knowledge graph extraction with entity/relation modeling
- LLM-powered summaries (optional, via `opendocs[llm]`)
- 136 passing tests
- CLI: `opendocs generate <url>`
- PyPI: `pip install opendocs`
- Repo: https://github.com/ioteverythin/OpenDocs

---

*This document was generated on February 21, 2026.*
