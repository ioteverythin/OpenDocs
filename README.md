# � OpenDocs

> Convert any GitHub README into structured, multi-format documentation — instantly.

[![PyPI](https://img.shields.io/pypi/v/opendocs.svg)](https://pypi.org/project/opendocs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-136%20passed-brightgreen.svg)]()

## What is OpenDocs?

OpenDocs (by [ioteverythin](https://www.ioteverythin.com/)) takes a GitHub repository README and automatically generates beautiful, professional documentation in multiple formats:

| Output | Format | Status |
|--------|--------|--------|
| 📄 Technical Report | `.docx` (Word) | ✅ |
| 📊 Executive Deck | `.pptx` (PowerPoint) | ✅ |
| 📑 PDF Documentation | `.pdf` | ✅ |
| �️ Blog Post | `.md` (SEO-ready) | ✅ NEW |
| 🎫 Jira Tickets | `.json` (Epic + Stories) | ✅ NEW |
| 📝 Changelog / Release Notes | `.md` | ✅ NEW |
| 🎓 Academic Paper | `.tex` (LaTeX / IEEE) | ✅ NEW |
| 📋 One-Pager / Datasheet | `.pdf` (executive) | ✅ NEW |
| 📣 Social Cards | `.json` (OG + posts) | ✅ NEW |
| �📝 Analysis Report | `.md` (Markdown) | ✅ |
| 📐 Mermaid Diagrams | PNG rendering | ✅ |
| 🧠 Knowledge Graph | Entity extraction | ✅ |
| 🤖 LLM Summaries | Stakeholder views | ✅ |
| 🎨 7 Themes | corporate, ocean, sunset, dark, minimal, emerald, royal | ✅ |

## Two Modes

1. **Basic (Deterministic)** — Pure Markdown AST parsing, no LLM required. Fast, free, predictable.
2. **LLM (AI-Powered)** — Uses OpenAI to extract entities, build knowledge graphs, and generate executive summaries + stakeholder views (CTO, Investor, Developer).

## Quick Start

### Install from PyPI

```bash
pip install opendocs
```

For LLM features:

```bash
pip install opendocs[llm]
```

### Install from source

```bash
git clone https://github.com/ioteverythin/OpenDocs.git
cd OpenDocs
pip install -e ".[dev,llm]"
```

### Usage

**CLI:**

```bash
# Generate all formats from a GitHub README
opendocs generate https://github.com/owner/repo

# Generate specific format with a theme
opendocs generate https://github.com/owner/repo --format word --theme ocean

# Generate blog post only
opendocs generate https://github.com/owner/repo --format blog

# Generate Jira tickets from README
opendocs generate ./README.md --local --format jira

# Generate LaTeX academic paper
opendocs generate https://github.com/owner/repo --format latex

# Generate executive one-pager PDF
opendocs generate https://github.com/owner/repo --format onepager

# Generate social media cards & post text
opendocs generate https://github.com/owner/repo --format social

# Generate changelog / release notes
opendocs generate https://github.com/owner/repo --format changelog

# From a local README file
opendocs generate ./README.md --local

# LLM mode with knowledge graph + stakeholder summaries
opendocs generate ./README.md --local --mode llm --api-key sk-...

# Specify output directory
opendocs generate https://github.com/owner/repo -o ./my-docs

# List available themes
opendocs themes
```

**Python API:**

```python
from opendocs.pipeline import Pipeline

pipeline = Pipeline()
pipeline.run(
    "https://github.com/owner/repo",
    theme_name="ocean",
    mode="llm",
    api_key="sk-...",
)
```

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
| `all` | Everything above (default) | all formats |

**CLI examples:**

```bash
# Single format
opendocs generate https://github.com/owner/repo -f jira

# Default generates ALL formats
opendocs generate https://github.com/owner/repo
```

**Python API — pick your formats:**

```python
from opendocs.pipeline import Pipeline
from opendocs.core.models import OutputFormat

pipeline = Pipeline()

# Generate only Jira tickets
pipeline.run(
    "https://github.com/owner/repo",
    formats=[OutputFormat.JIRA],
)

# Generate blog + social cards
pipeline.run(
    "https://github.com/owner/repo",
    formats=[OutputFormat.BLOG, OutputFormat.SOCIAL],
)

# Classic trio only
pipeline.run(
    "https://github.com/owner/repo",
    formats=[OutputFormat.WORD, OutputFormat.PDF, OutputFormat.PPTX],
)

# All available OutputFormat values:
# OutputFormat.WORD, OutputFormat.PDF, OutputFormat.PPTX,
# OutputFormat.BLOG, OutputFormat.JIRA, OutputFormat.CHANGELOG,
# OutputFormat.LATEX, OutputFormat.ONEPAGER, OutputFormat.SOCIAL
```

## Features

- **9 Output Formats** — Word, PDF, PPTX, Blog Post, Jira Tickets, Changelog, LaTeX Paper, One-Pager PDF, Social Cards
- **7 Built-in Themes** — Corporate, Ocean, Sunset, Dark, Minimal, Emerald, Royal
- **Blog Post Generator** — SEO-friendly Markdown with front-matter, TOC, code examples, and CTA
- **Jira Ticket Export** — Epic + Stories with acceptance criteria, story points, and labels
- **Changelog Generator** — Categorized release notes (Features, Setup, API, DevOps, etc.)
- **LaTeX Paper** — IEEE/ACM-style academic paper with abstract, code listings, tables, bibliography
- **Executive One-Pager** — Single-page PDF datasheet with stats, features, tech stack, install command
- **Social Cards** — OG metadata + ready-to-post text for Twitter, LinkedIn, Reddit, HN, Product Hunt
- **Mermaid → PNG** — Renders mermaid diagrams to images via mermaid.ink API
- **Knowledge Graph** — Extracts 10+ entity types (projects, technologies, APIs, metrics, etc.)
- **Smart Table Sorting** — 6 strategies (smart, alpha, numeric, column:N, column:N:desc, none)
- **LLM Summaries** — Executive summary + CTO / Investor / Developer stakeholder views
- **Architecture Diagrams** — Auto-generated KG visualization as Mermaid graph

## Architecture

```
GitHub URL / Local .md
        │
        ▼
┌─────────────────┐
│   README Fetch   │  ← httpx + GitHub API
└────────┬────────┘
         ▼
┌─────────────────┐
│  Markdown Parser │  ← mistune 3.x AST
└────────┬────────┘
         ▼
┌─────────────────┐
│  Table Sorting   │  ← 6 strategies
└────────┬────────┘
         ▼
┌─────────────────┐
│  KG Extraction   │  ← Semantic + optional LLM
└────────┬────────┘
         ▼
┌─────────────────┐
│ Diagram Renderer │  ← mermaid.ink API
└────────┬────────┘
         │
    ┌────┼────┬────┬──────┬──────┬───────┬──────┬─────┬──────┐
    ▼    ▼    ▼    ▼      ▼      ▼       ▼      ▼     ▼
  Word  PDF  PPTX  Blog  Jira  Change  LaTeX  1-Pgr  Social
                                 log
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,llm]"

# Run tests (136 tests)
pytest

# Lint
ruff check src/
```

## Contributing

Contributions are welcome! Please open issues and PRs on [GitHub](https://github.com/ioteverythin/OpenDocs).

## License

MIT License — see [LICENSE](LICENSE) for details.
