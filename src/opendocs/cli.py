"""opendocs CLI — generate documentation from GitHub READMEs, Markdown files, and Jupyter Notebooks."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from .core.models import OutputFormat
from .core.template_vars import load_template_vars
from .generators.themes import list_themes, get_theme
from .pipeline import Pipeline

console = Console()

BANNER = r"""
  ___                   ____
 / _ \ _ __   ___ _ __ |  _ \  ___   ___ ___
| | | | '_ \ / _ \ '_ \| | | |/ _ \ / __/ __|
| |_| | |_) |  __/ | | | |_| | (_) | (__\__ \
 \___/| .__/ \___|_| |_|____/ \___/ \___|___/
      |_|
  README → Docs Pipeline  v0.5.0
"""

FORMAT_MAP = {
    "word": OutputFormat.WORD,
    "pdf": OutputFormat.PDF,
    "pptx": OutputFormat.PPTX,
    "blog": OutputFormat.BLOG,
    "jira": OutputFormat.JIRA,
    "changelog": OutputFormat.CHANGELOG,
    "latex": OutputFormat.LATEX,
    "onepager": OutputFormat.ONEPAGER,
    "social": OutputFormat.SOCIAL,
    "faq": OutputFormat.FAQ,
    "architecture": OutputFormat.ARCHITECTURE,
    "all": OutputFormat.ALL,
}


@click.group()
@click.version_option(version="0.5.0", prog_name="opendocs")
def main():
    """opendocs — Convert GitHub READMEs, Markdown files, and Jupyter Notebooks into multi-format documentation."""
    pass


@main.command()
@click.argument("source")
@click.option(
    "-f", "--format",
    "fmt",
    type=click.Choice(
        ["word", "pdf", "pptx", "blog", "jira", "changelog",
         "latex", "onepager", "social", "faq", "architecture", "all"],
        case_sensitive=False,
    ),
    default="all",
    help="Output format (default: all).",
)
@click.option(
    "-o", "--output",
    "output_dir",
    type=click.Path(),
    default="./output",
    help="Output directory (default: ./output).",
)
@click.option(
    "--local",
    is_flag=True,
    default=False,
    help="Treat SOURCE as a local file path.",
)
@click.option(
    "--token",
    envvar="GITHUB_TOKEN",
    default=None,
    help="GitHub personal access token (or set GITHUB_TOKEN env var).",
)
@click.option(
    "--theme",
    "theme_name",
    type=click.Choice([t.name for t in list_themes()], case_sensitive=False),
    default="corporate",
    help="Color theme for generated documents.",
)
@click.option(
    "--mode",
    type=click.Choice(["basic", "llm"], case_sensitive=False),
    default="basic",
    help="Extraction mode: basic (deterministic) or llm (OpenAI-enhanced).",
)
@click.option(
    "--api-key",
    envvar="OPENAI_API_KEY",
    default=None,
    help="OpenAI API key for LLM mode (or set OPENAI_API_KEY env var).",
)
@click.option(
    "--model",
    default="gpt-4o-mini",
    help="LLM model name (default: gpt-4o-mini). Any OpenAI-compatible model.",
)
@click.option(
    "--base-url",
    default=None,
    help="Custom OpenAI-compatible API base URL (e.g. http://localhost:11434/v1 for Ollama).",
)
@click.option(
    "--provider",
    "llm_provider",
    type=click.Choice(["openai", "anthropic", "google", "ollama", "azure"], case_sensitive=False),
    default="openai",
    help="LLM provider: openai (default), anthropic (Claude), google (Gemini), ollama (local), azure.",
)
@click.option(
    "--sort-tables",
    "sort_tables",
    default="smart",
    help='Table sort strategy: smart (auto), alpha, numeric, column:N, column:N:desc, or none.',
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to YAML/JSON config file with template variables (project_name, author, version, etc.).",
)
@click.option("--project-name", default=None, help="Project name for document titles and headers.")
@click.option("--author", default=None, help="Document author name.")
@click.option("--doc-version", "doc_version", default=None, help="Document / project version string.")
@click.option("--org", "organisation", default=None, help="Organisation name for headers and footers.")
@click.option("--department", default=None, help="Department / team name.")
@click.option("--confidentiality", default=None, help="Classification label (e.g. Internal, Confidential, Public).")
@click.option(
    "--include-outputs/--no-outputs",
    "include_outputs",
    default=True,
    help="Include cell outputs when parsing Jupyter Notebooks (default: yes).",
)
def generate(
    source: str,
    fmt: str,
    output_dir: str,
    local: bool,
    token: str | None,
    theme_name: str,
    mode: str,
    api_key: str | None,
    model: str,
    base_url: str | None,
    llm_provider: str,
    sort_tables: str,
    config_path: str | None,
    project_name: str | None,
    author: str | None,
    doc_version: str | None,
    organisation: str | None,
    department: str | None,
    confidentiality: str | None,
    include_outputs: bool,
):
    """Generate documentation from a GitHub README, local Markdown file, or Jupyter Notebook.

    SOURCE can be a GitHub URL (e.g., https://github.com/owner/repo),
    a local Markdown file, or a .ipynb notebook when used with --local.
    """
    console.print(BANNER)

    # Resolve template variables (config file + CLI overrides)
    tvars = load_template_vars(
        config_path,
        project_name=project_name,
        author=author,
        version=doc_version,
        organisation=organisation,
        department=department,
        confidentiality=confidentiality,
    )

    # Auto-detect notebooks
    from .core.notebook_parser import is_notebook
    if is_notebook(source) and not local:
        local = True  # Notebooks are always local files

    # Resolve formats
    chosen = FORMAT_MAP[fmt.lower()]
    if chosen == OutputFormat.ALL:
        formats = [
            OutputFormat.WORD, OutputFormat.PDF, OutputFormat.PPTX,
            OutputFormat.BLOG, OutputFormat.JIRA, OutputFormat.CHANGELOG,
            OutputFormat.LATEX, OutputFormat.ONEPAGER, OutputFormat.SOCIAL,
            OutputFormat.FAQ, OutputFormat.ARCHITECTURE,
        ]
    else:
        formats = [chosen]

    # Run pipeline
    pipeline = Pipeline(github_token=token)
    result = pipeline.run(
        source,
        output_dir=output_dir,
        formats=formats,
        local=local,
        theme_name=theme_name,
        mode=mode,
        api_key=api_key,
        model=model,
        base_url=base_url,
        sort_tables=sort_tables,
        provider=llm_provider,
        template_vars=tvars,
    )

    # Exit code
    if not any(r.success for r in result.results):
        raise SystemExit(1)


@main.command()
def themes():
    """List available document themes."""
    from rich.table import Table as RichTable

    table = RichTable(title="Available Themes", show_lines=False)
    table.add_column("Name", style="bold cyan")
    table.add_column("Primary Color", style="bold")
    table.add_column("Accent Color", style="bold")
    table.add_column("Heading Font")
    table.add_column("Body Font")

    for t in list_themes():
        p = t.colors.primary
        a = t.colors.accent
        p_hex = f"#{p[0]:02X}{p[1]:02X}{p[2]:02X}"
        a_hex = f"#{a[0]:02X}{a[1]:02X}{a[2]:02X}"
        table.add_row(
            t.name,
            f"[{p_hex}]██ {p_hex}[/]",
            f"[{a_hex}]██ {a_hex}[/]",
            t.fonts.heading,
            t.fonts.body,
        )

    console.print(table)


@main.command()
@click.argument("source")
@click.option("--local", is_flag=True, default=False, help="Treat SOURCE as a local file.")
@click.option("--token", envvar="GITHUB_TOKEN", default=None)
def inspect(source: str, local: bool, token: str | None):
    """Fetch and parse a README or Jupyter Notebook, then display the structured representation."""
    from rich.tree import Tree
    from .core.fetcher import ReadmeFetcher
    from .core.parser import ReadmeParser
    from .core.notebook_parser import NotebookParser, is_notebook

    if is_notebook(source):
        parser = NotebookParser()
        doc = parser.parse(source, repo_name=Path(source).stem)
    else:
        fetcher = ReadmeFetcher(github_token=token)
        if local:
            content, name = fetcher._fetch_local(source)
        else:
            content, name = fetcher.fetch(source)

        parser = ReadmeParser()
        doc = parser.parse(content, repo_name=name, repo_url=source if not local else "")

    tree = Tree(f"[bold]{name}[/bold]")
    tree.add(f"[dim]Blocks: {len(doc.all_blocks)}[/dim]")
    tree.add(f"[dim]Diagrams: {len(doc.mermaid_diagrams)}[/dim]")

    sections_node = tree.add("[bold]Sections[/bold]")
    for sec in doc.sections:
        _add_section_tree(sections_node, sec)

    console.print(tree)


@main.command()
@click.argument("repo_dir", type=click.Path(exists=True))
@click.option(
    "-o", "--output",
    "output_dir",
    default="./output",
    help="Output directory for generated docs (default: ./output).",
)
@click.option(
    "--interval",
    type=int,
    default=30,
    help="Seconds between change-detection checks (default: 30).",
)
@click.option(
    "--once",
    is_flag=True,
    default=False,
    help="Run a single check-and-regenerate cycle, then exit (for cron).",
)
@click.option(
    "--auto-pr",
    is_flag=True,
    default=False,
    help="Automatically create a git branch + pull request when docs are regenerated.",
)
@click.option(
    "--branch",
    "branch_name",
    default="docs/auto-update",
    help="Base branch name for auto-PR (default: docs/auto-update).",
)
@click.option(
    "--patterns",
    default=None,
    help="Comma-separated file patterns to watch (e.g. 'README.md,docs/*.md,*.ipynb').",
)
@click.option(
    "-f", "--format",
    "fmt",
    type=click.Choice(
        ["word", "pdf", "pptx", "blog", "jira", "changelog",
         "latex", "onepager", "social", "faq", "architecture", "all"],
        case_sensitive=False,
    ),
    default="all",
    help="Output format (default: all).",
)
@click.option(
    "--theme",
    "theme_name",
    type=click.Choice([t.name for t in list_themes()], case_sensitive=False),
    default="corporate",
    help="Color theme for generated documents.",
)
@click.option(
    "--mode",
    type=click.Choice(["basic", "llm"], case_sensitive=False),
    default="basic",
    help="Extraction mode.",
)
@click.option("--api-key", envvar="OPENAI_API_KEY", default=None)
@click.option("--model", default="gpt-4o-mini")
@click.option(
    "--provider",
    "llm_provider",
    type=click.Choice(["openai", "anthropic", "google", "ollama", "azure"], case_sensitive=False),
    default="openai",
)
@click.option("--config", "config_path", type=click.Path(exists=True), default=None,
              help="Template variables config file.")
def watch(
    repo_dir: str,
    output_dir: str,
    interval: int,
    once: bool,
    auto_pr: bool,
    branch_name: str,
    patterns: str | None,
    fmt: str,
    theme_name: str,
    mode: str,
    api_key: str | None,
    model: str,
    llm_provider: str,
    config_path: str | None,
):
    """Watch a repository for changes and auto-regenerate documentation.

    REPO_DIR is the path to a local git repository to monitor.

    \b
    Examples:
      opendocs watch ./my-repo                    # continuous watch
      opendocs watch ./my-repo --once             # one-shot (for cron)
      opendocs watch ./my-repo --auto-pr          # watch + auto pull requests
      opendocs watch ./my-repo --interval 60      # check every 60 seconds
      opendocs watch ./my-repo --patterns "README.md,docs/*.md"
    """
    console.print(BANNER)

    from .core.watcher import FileWatcher

    # Parse patterns
    pattern_list = None
    if patterns:
        pattern_list = [p.strip() for p in patterns.split(",") if p.strip()]

    # Parse formats
    fmt_list = None
    if fmt.lower() != "all":
        fmt_list = [fmt.lower()]

    watcher = FileWatcher(
        repo_dir=repo_dir,
        output_dir=output_dir,
        interval=interval,
        patterns=pattern_list,
        auto_pr=auto_pr,
        branch_name=branch_name,
        formats=fmt_list,
        theme=theme_name,
        mode=mode,
        api_key=api_key,
        model=model,
        provider=llm_provider,
        config_path=config_path,
    )

    if once:
        changed = watcher.check_once()
        if not changed:
            console.print("[dim]No changes detected. Nothing to regenerate.[/]")
        raise SystemExit(0 if changed else 0)  # Success either way for cron
    else:
        watcher.watch()


def _add_section_tree(parent, section):
    """Recursively add sections to a Rich tree."""
    node = parent.add(
        f"[blue]H{section.level}:[/blue] {section.title} "
        f"[dim]({len(section.blocks)} blocks)[/dim]"
    )
    for sub in section.subsections:
        _add_section_tree(node, sub)


if __name__ == "__main__":
    main()
