# � OpenDocs

> Convert any GitHub README into structured, multi-format documentation — instantly.

[![PyPI](https://img.shields.io/pypi/v/opendocs.svg)](https://pypi.org/project/opendocs/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-114%20passed-brightgreen.svg)]()

## What is OpenDocs?

OpenDocs (by IoTEverything) takes a GitHub repository README and automatically generates beautiful, professional documentation in multiple formats:

| Output | Format | Status |
|--------|--------|--------|
| 📄 Technical Report | `.docx` (Word) | ✅ |
| 📊 Executive Deck | `.pptx` (PowerPoint) | ✅ |
| 📑 PDF Documentation | `.pdf` | ✅ |
| 📝 Analysis Report | `.md` (Markdown) | ✅ |
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

## Features

- **7 Built-in Themes** — Corporate, Ocean, Sunset, Dark, Minimal, Emerald, Royal
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
    ┌────┼────┬────┬──────┐
    ▼    ▼    ▼    ▼      ▼
  Word  PDF  PPTX  MD  Diagrams
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,llm]"

# Run tests (114 tests)
pytest

# Lint
ruff check src/
```

## Contributing

Contributions are welcome! Please open issues and PRs on [GitHub](https://github.com/ioteverythin/OpenDocs).

## License

MIT License — see [LICENSE](LICENSE) for details.
