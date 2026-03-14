# OpenDocs Roadmap

This document outlines the planned direction for OpenDocs. Items are grouped by milestone. Priorities may shift based on community feedback — open an issue or vote with 👍 to influence the roadmap.

---

## ✅ Released

### v0.1.0 — Initial Release
- Core pipeline: Markdown → DOCX + PDF
- Jinja2 template engine
- Basic CLI (`opendocs generate`)

### v0.2.0 — LLM Enhancement
- AI-powered content enrichment via OpenAI GPT-4o
- `--local` flag to skip LLM and run offline
- Notebook (`.ipynb`) input support

### v0.3.0 — Multi-Theme System
- 25 built-in themes (aurora, midnight, ocean, corporate, minimal, …)
- `--theme` CLI flag
- Per-theme fonts, colors, and layout controls

### v0.4.0 — Multi-Format Output
- DOCX, PDF, HTML, Markdown, TXT, EPUB output formats
- `--format` CLI flag
- Batch format generation with `--format all`

### v0.5.0 — Polish & Publishing
- PyPI package published (`pip install opendocs-gen`)
- Improved error messages and logging
- README and documentation overhaul

### v0.5.1 — Bug Fixes
- Fixed template rendering edge cases
- Resolved emoji encoding issues on Windows

---

## 🚧 In Progress

### v0.6.0 — REST API & Deployment
- **FastAPI wrapper** with `/generate` endpoint
- **Docker image** for self-hosting
- **Railway** one-click deploy
- Multipart file upload endpoint (`POST /generate/upload`)
- Health check + metadata endpoints

### v0.1.0 — VS Code Extension
- Generate documents from within VS Code
- Right-click context menu on `.md` / `.ipynb` files
- Theme + format picker
- Status bar integration
- Published at: https://github.com/ioteverythin/Opendocs-ext

---

## 🗺️ Planned

### v0.7.0 — Web Application
- Full Next.js/React web UI hosted on Vercel / Railway
- Drag-and-drop Markdown / notebook upload
- Theme preview grid
- Download ZIP of generated documents
- GitHub URL input (generate from any public repo file)

### v0.8.0 — More LLM Providers
- [ ] Anthropic Claude support
- [ ] Google Gemini support
- [ ] Ollama (local LLM) support
- [ ] Provider selection via `--llm-provider` flag
- [ ] Token budget + cost estimation flag

### v0.9.0 — Templates & Customization
- [ ] User-defined Jinja2 templates (`--template ./my-template.j2`)
- [ ] Custom CSS injection for HTML output
- [ ] Header / footer customization per document
- [ ] Company logo embedding

### v1.0.0 — Stable Release
- [ ] Stable public API
- [ ] Full type-annotated SDK for Python embedding
- [ ] Comprehensive test suite (>90% coverage)
- [ ] Complete documentation site (MkDocs or Sphinx)
- [ ] GitHub Actions CI/CD pipeline

---

## 💡 Ideas Under Consideration

These are not committed — open an issue to discuss!

| Idea | Status |
|---|---|
| PowerPoint (`.pptx`) output | 💬 Evaluating |
| Google Docs export via API | 💬 Evaluating |
| Confluence / Notion publish integration | 💬 Evaluating |
| Batch processing multiple files at once | 💬 Evaluating |
| Watch mode (`--watch`) for live re-generation | 💬 Evaluating |
| Document diff / changelog generation | 💡 Idea |
| VS Code Marketplace publish | ⏳ Pending Azure DevOps setup |
| GitHub Actions workflow for auto-generation | 💡 Idea |

---

## Contributing to the Roadmap

Have an idea that isn't listed? Open an issue with the `enhancement` label. 

Have bandwidth to work on something? Look for [`help wanted`](https://github.com/ioteverythin/OpenDocs/labels/help%20wanted) issues or comment on any roadmap item — we'll guide you through it.

See [CONTRIBUTING.md](./CONTRIBUTING.md) to get started.
