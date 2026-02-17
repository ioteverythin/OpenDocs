# 🔄 IoTEverything

> Convert any GitHub README into structured, multi-format documentation — instantly.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## What is IoTEverything?

IoTEverything takes a GitHub repository README and automatically generates:

| Output | Format | Status |
|--------|--------|--------|
| 📄 Technical Report | `.docx` (Word) | ✅ MVP |
| 📊 Executive Deck | `.pptx` (PowerPoint) | ✅ MVP |
| 📑 PDF Documentation | `.pdf` | ✅ MVP |
| 📐 Architecture Diagrams | Mermaid extraction | ✅ MVP |
| 📝 Academic Paper Draft | LaTeX | 🔜 Planned |
| 📈 Auto-generated Charts | Plotly/Matplotlib | 🔜 Planned |
| 🎨 Figma Components | Figma API/MCP | 🔜 Planned |

## Two Modes

1. **Basic (Deterministic)** — Pure Markdown AST parsing, no LLM required. Fast, free, predictable.
2. **Advanced (Multi-Agent LLM)** — Uses AI agents to extract entities, generate summaries, draft research papers, and create intelligent visualizations. *(Coming soon)*

## Quick Start

### Installation

```bash
pip install ioteverything
```

Or install from source:

```bash
git clone https://github.com/ioteverything/ioteverything.git
cd ioteverything
pip install -e ".[dev]"
```

### Usage

**CLI:**

```bash
# Generate all formats from a GitHub README
ioteverything generate https://github.com/owner/repo

# Generate specific format
ioteverything generate https://github.com/owner/repo --format word
ioteverything generate https://github.com/owner/repo --format pdf
ioteverything generate https://github.com/owner/repo --format pptx

# From a local README file
ioteverything generate ./README.md --local

# Specify output directory
ioteverything generate https://github.com/owner/repo -o ./my-docs
```

**Python API:**

```python
from ioteverything import Pipeline

pipeline = Pipeline()
results = pipeline.run("https://github.com/owner/repo")

# Access individual outputs
results.word_path   # Path to generated .docx
results.pdf_path    # Path to generated .pdf
results.pptx_path   # Path to generated .pptx
```

## Architecture

```
GitHub URL / Local .md
        │
        ▼
┌─────────────────┐
│   README Fetch   │  ← httpx + GitHub API
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Markdown Parser │  ← mistune AST
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Structured Model │  ← Pydantic models (DocumentModel)
└────────┬────────┘
         │
    ┌────┼────┬──────────┐
    ▼    ▼    ▼          ▼
  Word  PDF  PPTX   Diagrams
```

## GitHub Action

```yaml
- name: Generate Docs
  uses: ioteverything/generate-docs@v1
  with:
    readme-path: ./README.md
    formats: word,pdf,pptx
    output-dir: ./docs
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](LICENSE) for details.
