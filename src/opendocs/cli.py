"""opendocs CLI — generate documentation from GitHub READMEs."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from .core.models import OutputFormat
from .generators.themes import list_themes, get_theme
from .pipeline import Pipeline

console = Console()

BANNER = r"""
  ___    _____   _____                      _   _     _
 |_ _|__|_   _| | ____|_   _____ _ __ _   _| |_| |__ (_)_ __   __ _
  | |/ _ \| |   |  _| \ \ / / _ \ '__| | | | __| '_ \| | '_ \ / _` |
  | | (_) | |   | |___ \ V /  __/ |  | |_| | |_| | | | | | | | (_| |
 |___\___/|_|   |_____| \_/ \___|_|   \__, |\__|_| |_|_|_| |_|\__, |
                                       |___/                   |___/
  README → Docs Pipeline  v0.1
"""

FORMAT_MAP = {
    "word": OutputFormat.WORD,
    "pdf": OutputFormat.PDF,
    "pptx": OutputFormat.PPTX,
    "all": OutputFormat.ALL,
}


@click.group()
@click.version_option(version="0.1.0", prog_name="opendocs")
def main():
    """opendocs — Convert GitHub READMEs into multi-format documentation."""
    pass


@main.command()
@click.argument("source")
@click.option(
    "-f", "--format",
    "fmt",
    type=click.Choice(["word", "pdf", "pptx", "all"], case_sensitive=False),
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
    "--sort-tables",
    "sort_tables",
    default="smart",
    help='Table sort strategy: smart (auto), alpha, numeric, column:N, column:N:desc, or none.',
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
    sort_tables: str,
):
    """Generate documentation from a GitHub README or local Markdown file.

    SOURCE can be a GitHub URL (e.g., https://github.com/owner/repo) or
    a local file path when used with --local.
    """
    console.print(BANNER)

    # Resolve formats
    chosen = FORMAT_MAP[fmt.lower()]
    if chosen == OutputFormat.ALL:
        formats = [OutputFormat.WORD, OutputFormat.PDF, OutputFormat.PPTX]
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
    """Fetch and parse a README, then display the structured representation."""
    from rich.tree import Tree
    from .core.fetcher import ReadmeFetcher
    from .core.parser import ReadmeParser

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
