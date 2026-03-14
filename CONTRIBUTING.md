# Contributing to OpenDocs

Thank you for your interest in contributing! OpenDocs is an open-source project and we welcome contributions of all kinds — bug fixes, new features, themes, output formats, documentation improvements, and more.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Code Style](#code-style)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Adding a New Theme](#adding-a-new-theme)
- [Adding a New Output Format](#adding-a-new-output-format)
- [Reporting Bugs](#reporting-bugs)
- [Feature Requests](#feature-requests)

---

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/OpenDocs.git
   cd OpenDocs
   ```
3. **Create a branch** for your change:
   ```bash
   git checkout -b feat/my-feature
   ```

---

## Development Setup

**Requirements:** Python 3.10+, pip

```bash
# Install in editable mode with dev + LLM dependencies
pip install -e ".[dev,llm,templates]"

# Run the test suite
pytest

# Lint
ruff check src/
```

**Run the CLI locally:**
```bash
opendocs generate ./README.md --local --format word --theme aurora
```

---

## How to Contribute

### Good First Issues
Look for issues labelled [`good first issue`](https://github.com/ioteverythin/OpenDocs/labels/good%20first%20issue) — these are small, well-scoped tasks ideal for first-time contributors.

### Help Wanted
Issues labelled [`help wanted`](https://github.com/ioteverythin/OpenDocs/labels/help%20wanted) are things the core team would love community help with.

---

## Code Style

- **Formatter / linter:** `ruff` (configured in `pyproject.toml`)
- **Type hints:** required for all public functions and classes
- **Docstrings:** Google-style for public APIs
- **Line length:** 100 characters

Run before committing:
```bash
ruff check src/ --fix
```

---

## Submitting a Pull Request

1. Make sure all tests pass: `pytest`
2. Make sure lint is clean: `ruff check src/`
3. Write a clear PR title using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add X format generator`
   - `fix: handle empty notebook cells`
   - `docs: update README`
   - `chore: bump dependencies`
4. Reference any related issues: `Closes #42`
5. Open the PR against the `main` branch

---

## Adding a New Theme

Themes live in `src/opendocs/generators/themes.py`.

1. Create a new `Theme` instance following the pattern of existing themes:
   ```python
   MY_THEME = Theme(
       name="mytheme",
       description="A short description",
       colors=ThemeColors(
           primary=(R, G, B),
           ...
       ),
       fonts=ThemeFonts(...),
       layout=ThemeLayout(...),
   )
   ```
2. Register it in `_THEME_REGISTRY` at the bottom of the file
3. Add it to the `Choice` list in `src/opendocs/docagent/cli.py`
4. Add it to `ALL_THEMES` in the VS Code extension (`src/config.ts`)
5. Add a test in `tests/test_themes.py`

---

## Adding a New Output Format

1. Create `src/opendocs/generators/<name>_generator.py` inheriting from `BaseGenerator`
2. Add the new `OutputFormat` enum value in `src/opendocs/core/models.py`
3. Register it in `_GENERATORS` dict in `src/opendocs/pipeline.py`
4. Add the CLI flag in `src/opendocs/cli.py`
5. Add tests in `tests/`

---

## Reporting Bugs

Please open an issue with:
- **OpenDocs version:** `opendocs --version`
- **Python version:** `python --version`
- **OS:** Windows / macOS / Linux
- **What you ran** and the **full error output**

---

## Feature Requests

Open an issue with the `enhancement` label and describe:
- What you want to do
- Why it would be useful
- Any ideas on how to implement it

We read every issue. Thank you for helping make OpenDocs better!
