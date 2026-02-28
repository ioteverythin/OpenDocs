# OpenDocs

> Convert GitHub READMEs, Markdown files, and Jupyter Notebooks into structured, multi-format documentation -- instantly.

[![PyPI](https://img.shields.io/pypi/v/opendocs.svg)](https://pypi.org/project/opendocs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## What is OpenDocs?

OpenDocs (by [ioteverythin](https://www.ioteverythin.com/)) takes a GitHub repository README, local Markdown file, or **Jupyter Notebook (.ipynb)** and automatically generates beautiful, professional documentation in multiple formats:

| Output | Format | Status |
|--------|--------|--------|
| Technical Report | `.docx` (Word) | Available |
| Executive Deck | `.pptx` (PowerPoint) | Available |
| PDF Documentation | `.pdf` | Available |
| Blog Post | `.md` (SEO-ready) | Available |
| Jira Tickets | `.json` (Epic + Stories) | Available |
| Changelog / Release Notes | `.md` | Available |
| Academic Paper | `.tex` (LaTeX / IEEE) | Available |
| One-Pager / Datasheet | `.pdf` (executive) | Available |
| Social Cards | `.json` (OG + posts) | Available |
| FAQ Document | `.md` | Available |
| Analysis Report | `.md` (Markdown) | Available |
| Architecture Diagrams | `.mmd` + `.png` (5 views) | Available |
| Mermaid Diagrams | PNG rendering | Available |
| Knowledge Graph | Entity extraction | Available |
| LLM Summaries | Stakeholder views | Available |

### What's New in v0.5.0

- **Jupyter Notebook Ingestion** -- Parse `.ipynb` files and convert markdown cells, code cells, and outputs into polished reports
- **Parameterized Report Templates** -- Inject project name, author, version, date, and organisation into document headers, footers, and title pages via `--config` YAML/JSON or CLI flags
- **File Watcher + Auto-PR** -- `opendocs watch` daemon monitors repos for changes and auto-regenerates docs; supports cron mode (`--once`) and automatic pull requests (`--auto-pr`)
- **5 LLM Providers** -- OpenAI, Anthropic (Claude), Google (Gemini), Ollama (local), Azure OpenAI
- **25 Built-in Themes** -- 15 original + 10 new modern themes (Aurora, Carbon, Lavender, Graphite, Obsidian, Coral, Zen, Nebula, Sand, Glacier)

## Two Engines

### 1. Pipeline (Deterministic + LLM)

The core pipeline parses Markdown/Notebooks and generates all 11 output formats:

- **Basic mode** -- Pure Markdown AST parsing, no LLM required. Fast, free, predictable.
- **LLM mode** -- Uses any supported LLM provider to extract entities, build knowledge graphs, and generate executive summaries + stakeholder views (CTO, Investor, Developer).

### 2. DocAgent (Agentic)

A full LangGraph-powered agent that generates 8 enterprise document types (PRD, Proposal, SOP, Report, Slides, Changelog, Onboarding, Tech Debt) from any GitHub repo.

## Quick Start

### Install from PyPI

```bash
pip install opendocs
```

For LLM features:

```bash
pip install opendocs[llm]
```

For all LLM providers:

```bash
pip install opendocs[all-providers]
```

For YAML config file support:

```bash
pip install opendocs[templates]
```

### Install from source

```bash
git clone https://github.com/ioteverythin/OpenDocs.git
cd OpenDocs
pip install -e ".[dev,llm]"
```

### Basic Usage

```bash
# Generate all formats from a GitHub README
opendocs generate https://github.com/owner/repo

# Generate specific format with a theme
opendocs generate https://github.com/owner/repo --format word --theme aurora

# From a local Markdown file
opendocs generate ./README.md --local

# LLM mode with knowledge graph + stakeholder summaries
opendocs generate ./README.md --local --mode llm --api-key sk-...

# Use Claude instead of OpenAI
opendocs generate ./README.md --local --mode llm --provider anthropic

# List available themes (25 themes)
opendocs themes
```

### Jupyter Notebook Ingestion

Generate polished reports from research notebooks and data-science projects:

```bash
# Generate docs from a Jupyter Notebook
opendocs generate ./analysis.ipynb --local

# Generate only Word report from notebook
opendocs generate ./research.ipynb --local --format word --theme carbon

# Exclude cell outputs
opendocs generate ./notebook.ipynb --local --no-outputs
```

The notebook parser extracts:
- **Markdown cells** -- parsed into headings, paragraphs, lists, tables, etc.
- **Code cells** -- preserved with language detection and execution count
- **Cell outputs** -- text output, images (PNG/SVG/JPEG as data URIs), HTML previews, error tracebacks

### Parameterized Report Templates

Inject variables into document headers, footers, and title pages:

```bash
# Via CLI flags
opendocs generate ./README.md --local \
  --project-name "My Project" \
  --author "Jane Doe" \
  --doc-version "2.1.0" \
  --org "Acme Corp" \
  --department "Engineering" \
  --confidentiality "Internal"

# Via YAML/JSON config file
opendocs generate ./README.md --local --config opendocs.yaml
```

Example `opendocs.yaml`:

```yaml
project_name: "My Project"
author: "Jane Doe"
version: "2.1.0"
date: "2026-02-28"
organisation: "Acme Corp"
department: "Engineering"
confidentiality: "Internal"
custom:
  reviewer: "John Smith"
  status: "Draft"
```

These values automatically appear in:
- **Word (.docx)** -- document header, footer, and expanded metadata table on title page
- **PowerPoint (.pptx)** -- title slide footer with org, author, version, and date
- **PDF** -- inherits from Word generator

### File Watcher + Auto-PR

Monitor a repository for changes and auto-regenerate documentation:

```bash
# Continuous watch (checks every 30 seconds)
opendocs watch ./my-repo

# One-shot mode for cron jobs
opendocs watch ./my-repo --once

# Watch + auto-create pull requests
opendocs watch ./my-repo --auto-pr --branch docs-update

# Custom interval and file patterns
opendocs watch ./my-repo --interval 60 --patterns "README.md,docs/*.md,*.ipynb"
```

**Cron integration** -- add to crontab for hourly checks:

```
0 * * * * cd /path/to/repo && opendocs watch . --once --auto-pr
```

How it works:
1. Discovers files matching watch patterns (`README.md`, `CHANGELOG.md`, `docs/**/*.md`, `*.ipynb`)
2. Computes SHA-256 hashes and compares against saved state (`.opendocs-watch-state.json`)
3. If changes detected: runs the full pipeline for each changed file
4. If `--auto-pr`: creates a timestamped git branch, commits outputs, pushes, and opens a PR via GitHub CLI (`gh`)

### Multi-LLM Provider Support

Use any of the 5 supported LLM providers:

```bash
# OpenAI (default)
opendocs generate ./README.md --local --mode llm --provider openai --api-key sk-...

# Anthropic Claude
opendocs generate ./README.md --local --mode llm --provider anthropic

# Google Gemini
opendocs generate ./README.md --local --mode llm --provider google

# Ollama (local, no API key needed)
opendocs generate ./README.md --local --mode llm --provider ollama

# Azure OpenAI
opendocs generate ./README.md --local --mode llm --provider azure --base-url https://your-resource.openai.azure.com/
```

| Provider | Models | Env Variable |
|----------|--------|-------------|
| `openai` | gpt-4o-mini (default), gpt-4o, etc. | `OPENAI_API_KEY` |
| `anthropic` | claude-sonnet-4-20250514, claude-3-haiku, etc. | `ANTHROPIC_API_KEY` |
| `google` | gemini-1.5-flash (default), gemini-pro, etc. | `GOOGLE_API_KEY` |
| `ollama` | llama3.1 (default), any local model | None (local) |
| `azure` | Any Azure-deployed model | `AZURE_OPENAI_API_KEY` |

### Format Flags Reference

Use `-f` / `--format` to generate only what you need:

| Flag | Output | File |
|------|--------|------|
| `word` | Word document | `.docx` |
| `pdf` | PDF document | `.pdf` |
| `pptx` | PowerPoint deck | `.pptx` |
| `blog` | SEO blog post | `.md` (with front-matter) |
| `jira` | Jira tickets (Epic + Stories) | `.json` |
| `changelog` | Release notes | `.md` |
| `latex` | IEEE-style academic paper | `.tex` |
| `onepager` | Executive one-pager | `.pdf` |
| `social` | Social cards + post text | `.json` (OG, Twitter, LinkedIn, Reddit) |
| `faq` | FAQ document | `.md` |
| `architecture` | Architecture diagrams (5 views) | `.mmd` + `.png` + `.md` report |
| `all` | Everything above (default) | all formats |

### 25 Built-in Themes

| Category | Themes |
|----------|--------|
| Classic | corporate, ocean, sunset, dark, minimal, emerald, royal |
| Professional | slate, rose, nordic, cyber, terracotta, sapphire, mint, monochrome |
| Modern | aurora, carbon, lavender, graphite, obsidian, coral, zen, nebula, sand, glacier |

```bash
# List all themes with color previews
opendocs themes
```

### Python API

```python
from opendocs.pipeline import Pipeline
from opendocs.core.models import OutputFormat
from opendocs.core.template_vars import TemplateVars

# Basic usage
pipeline = Pipeline()
pipeline.run("https://github.com/owner/repo", theme_name="aurora")

# From a Jupyter Notebook with template variables
tvars = TemplateVars(
    project_name="Q4 Analysis",
    author="Data Team",
    version="1.0",
    organisation="Acme Corp",
)
pipeline.run(
    "./notebook.ipynb",
    local=True,
    formats=[OutputFormat.WORD, OutputFormat.PDF],
    template_vars=tvars,
)

# LLM mode with Claude
pipeline.run(
    "./README.md",
    local=True,
    mode="llm",
    api_key="sk-ant-...",
    provider="anthropic",
)
```

## Features

- **11 Output Formats** -- Word, PDF, PPTX, Blog Post, Jira Tickets, Changelog, LaTeX Paper, One-Pager PDF, Social Cards, FAQ, Architecture Diagrams
- **Jupyter Notebook Support** -- Parse `.ipynb` files including markdown cells, code cells, and outputs (images, tables, text)
- **Parameterized Templates** -- Inject project name, author, version, org, date into headers/footers via config file or CLI
- **File Watcher + Auto-PR** -- Monitor repos for changes, auto-regenerate docs, and create pull requests
- **5 LLM Providers** -- OpenAI, Anthropic (Claude), Google (Gemini), Ollama (local), Azure OpenAI
- **25 Built-in Themes** -- Classic, Professional, and Modern theme categories
- **Smart Table Sorting** -- 6 strategies (smart, alpha, numeric, column:N, column:N:desc, none)
- **Knowledge Graph** -- Extracts 10+ entity types (projects, technologies, APIs, metrics, etc.)
- **Architecture Diagrams** -- 5 auto-generated views: System Architecture (C4-style), Tech Stack Layers, Data Flow, Dependency Tree, Deployment View
- **Mermaid -> PNG** -- Renders mermaid diagrams to images via mermaid.ink API
- **LLM Summaries** -- Executive summary + CTO / Investor / Developer stakeholder views

## Architecture

```
GitHub URL / Local .md / .ipynb
        |
        v
+-------------------+
|  README Fetch /   |  <-- httpx + GitHub API
|  Notebook Parser  |  <-- .ipynb cell extraction
+--------+----------+
         v
+-------------------+
|  Markdown Parser  |  <-- mistune 3.x AST
+--------+----------+
         v
+-------------------+
|  Template Vars    |  <-- YAML/JSON config or CLI flags
+--------+----------+
         v
+-------------------+
|  Table Sorting    |  <-- 6 strategies
+--------+----------+
         v
+-------------------+
|  KG Extraction    |  <-- Semantic + optional LLM (5 providers)
+--------+----------+
         v
+-------------------+
|  Diagram Renderer |  <-- mermaid.ink API
+--------+----------+
         |
    +----+----+----+----+------+------+-------+------+-----+------+------+
    v    v    v    v    v      v      v       v      v     v      v
  Word  PDF  PPTX  Blog  Jira  Change  LaTeX  1-Pgr  Social  FAQ  Arch
                                 log                              Diag
```

### File Watcher Flow

```
opendocs watch ./repo
        |
        v
  Discover watched files (README.md, *.ipynb, docs/)
        |
        v
  SHA-256 hash each file
        |
        v
  Compare against .opendocs-watch-state.json
        |
        v
  If changed --> Pipeline.run() for each file
        |
        v
  Update state file
        |
        v
  If --auto-pr --> git branch + commit + push + gh pr create
```

## Optional Dependencies

```bash
pip install opendocs[llm]             # OpenAI LLM features
pip install opendocs[anthropic]       # Claude support
pip install opendocs[google]          # Gemini support
pip install opendocs[all-providers]   # All LLM providers
pip install opendocs[templates]       # YAML config file support
pip install opendocs[agents]          # DocAgent (agentic system)
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,llm,templates]"

# Run tests
pytest

# Lint
ruff check src/
```

## Contributing

Contributions are welcome! Please open issues and PRs on [GitHub](https://github.com/ioteverythin/OpenDocs).

## License

MIT License -- see [LICENSE](LICENSE) for details.
