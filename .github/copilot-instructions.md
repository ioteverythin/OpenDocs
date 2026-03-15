# OpenDocs — GitHub Copilot Instructions

When a user asks to generate documentation, convert a README, create a Word/PDF/blog
from a repo or package, use the `opendocs` CLI.

## Install

```bash
pip install opendocs
```

## Command Syntax

```bash
opendocs generate <SOURCE> [OPTIONS]
```

**Sources:**
- GitHub URL: `opendocs generate https://github.com/owner/repo`
- npm package: `opendocs generate npm:axios`
- Local file: `opendocs generate ./README.md --local`
- Folder: `opendocs generate ./docs/`

**Common options:**
- `--format word|pdf|pptx|blog|jira|faq|changelog|all` (default: all)
- `--output ./my-output` (default: ./output)
- `--theme corporate|ocean|sunset|forest|minimal`
- `--mode llm --api-key <key>` for AI-enhanced generation
- `--token <github-token>` for private repos

## Examples

```bash
opendocs generate https://github.com/owner/repo --format blog
opendocs generate npm:express --format word
opendocs generate ./README.md --local --format pdf
opendocs generate ./docs/ --output ./exported
```
