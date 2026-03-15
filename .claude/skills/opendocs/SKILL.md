---
name: opendocs
description: >
  Generates multi-format documentation (Word, PDF, PPTX, Markdown blog post,
  JIRA ticket, FAQ, changelog, LaTeX, social snippet, architecture diagram) from a
  GitHub README, npm package, local Markdown file, Jupyter Notebook, or a folder of
  .md/.ipynb files. Use when a user asks to "generate docs", "convert the README",
  "create a Word doc from the repo", "export to PDF", or any variant of turning
  existing content into formatted documentation.
user-invocable: true
allowed-tools: "Bash, Read"
metadata:
  version: "1.0.0"
---

# OpenDocs

Turn any GitHub README, npm package, Markdown file, or Jupyter Notebook into
Word, PDF, PPTX, blog posts, JIRA tickets, and more — in one command.

## Install

```bash
pip install opendocs
```

## Core Command

```bash
opendocs generate <SOURCE> [OPTIONS]
```

## Sources

| Source type | Example |
|---|---|
| GitHub URL | `opendocs generate https://github.com/owner/repo` |
| npm package | `opendocs generate npm:axios` |
| Local file | `opendocs generate ./README.md --local` |
| Jupyter Notebook | `opendocs generate ./notebook.ipynb --local` |
| Folder of .md/.ipynb | `opendocs generate ./docs/` |

## Key Options

| Option | Default | Description |
|---|---|---|
| `-f`, `--format` | `all` | Output format: `word`, `pdf`, `pptx`, `blog`, `jira`, `changelog`, `latex`, `onepager`, `social`, `faq`, `architecture`, `all` |
| `-o`, `--output` | `./output` | Directory for generated files |
| `--local` | off | Treat SOURCE as a local path |
| `--token` | `$GITHUB_TOKEN` | GitHub token for private repos |
| `--theme` | `corporate` | Color theme: `corporate`, `ocean`, `sunset`, `forest`, `minimal` |
| `--mode` | `basic` | `basic` (fast, no API key) or `llm` (AI-enhanced, needs `--api-key`) |
| `--api-key` | `$OPENAI_API_KEY` | API key for LLM mode |

## Common Usage

```bash
# Generate all formats from a GitHub repo
opendocs generate https://github.com/owner/repo

# Generate only a blog post from an npm package
opendocs generate npm:express --format blog

# Generate a Word doc from a local README
opendocs generate ./README.md --local --format word

# Generate docs from a whole folder, output to ./docs-out
opendocs generate ./docs/ --output ./docs-out

# AI-enhanced generation (richer content)
opendocs generate https://github.com/owner/repo --mode llm --api-key sk-...

# Use ocean theme, PDF only
opendocs generate https://github.com/owner/repo --format pdf --theme ocean
```

## Output Files

All files are written to `--output` (default: `./output/`).
File names follow the pattern `<repo_name>_<format>.<ext>`.

## When to Use

- User asks: *"generate docs for this repo"* → `opendocs generate <url>`
- User asks: *"make a Word doc from the README"* → `opendocs generate <url> --format word`
- User asks: *"create a blog post from npm:axios"* → `opendocs generate npm:axios --format blog`
- User asks: *"export all the markdown files in ./docs"* → `opendocs generate ./docs/`
