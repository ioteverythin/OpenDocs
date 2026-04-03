"""opendocs CLI — generate documentation from GitHub READMEs, Markdown files, and Jupyter Notebooks."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from .core.models import OutputFormat
from .core.template_vars import load_template_vars
from .generators.themes import list_themes
from .pipeline import Pipeline

console = Console()

BANNER = r"""
  ___                   ____
 / _ \ _ __   ___ _ __ |  _ \  ___   ___ ___
| | | | '_ \ / _ \ '_ \| | | |/ _ \ / __/ __|
| |_| | |_) |  __/ | | | |_| | (_) | (__\__ \
 \___/| .__/ \___|_| |_|____/ \___/ \___|___/
      |_|
  README → Docs Pipeline  v0.9.0
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
    "mindmap": OutputFormat.MINDMAP,
    "all": OutputFormat.ALL,
}


@click.group()
@click.version_option(version="0.9.0", prog_name="opendocs")
def main():
    """opendocs — Convert GitHub READMEs, npm packages, Markdown files, and Jupyter Notebooks into multi-format documentation."""
    pass


@main.command()
@click.argument("source", metavar="SOURCE")
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(
        [
            "word",
            "pdf",
            "pptx",
            "blog",
            "jira",
            "changelog",
            "latex",
            "onepager",
            "social",
            "faq",
            "architecture",
            "all",
        ],
        case_sensitive=False,
    ),
    default="all",
    help="Output format (default: all).",
)
@click.option(
    "-o",
    "--output",
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
    type=click.Choice(["basic", "llm", "template"], case_sensitive=False),
    default="basic",
    help="Mode: basic (minimal), template (rich docs, no LLM), or llm (AI-enhanced).",
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
    help="Table sort strategy: smart (auto), alpha, numeric, column:N, column:N:desc, or none.",
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
@click.option(
    "--confidentiality",
    default=None,
    help="Classification label (e.g. Internal, Confidential, Public).",
)
@click.option(
    "--include-outputs/--no-outputs",
    "include_outputs",
    default=True,
    help="Include cell outputs when parsing Jupyter Notebooks (default: yes).",
)
@click.option(
    "--folder-recursive/--no-folder-recursive",
    "folder_recursive",
    default=True,
    help="When SOURCE is a folder, scan sub-directories too (default: yes).",
)
@click.option(
    "--folder-title",
    default=None,
    help="Override the merged document title when SOURCE is a folder.",
)
# ---- Notion publish --------------------------------------------------
@click.option(
    "--publish-notion",
    "notion_page_id",
    default=None,
    envvar="NOTION_PAGE_ID",
    help="Publish generated docs to this Notion page ID or URL.",
)
@click.option(
    "--notion-token",
    envvar="NOTION_TOKEN",
    default=None,
    help="Notion integration token (or set NOTION_TOKEN env var).",
)
# ---- Confluence publish ----------------------------------------------
@click.option(
    "--publish-confluence",
    "confluence_space",
    default=None,
    envvar="CONFLUENCE_SPACE",
    help="Publish generated docs to this Confluence space key (e.g. PROJ).",
)
@click.option(
    "--confluence-url",
    envvar="CONFLUENCE_URL",
    default=None,
    help="Confluence base URL, e.g. https://yourorg.atlassian.net/wiki",
)
@click.option(
    "--confluence-user",
    envvar="CONFLUENCE_USER",
    default=None,
    help="Confluence account email (or set CONFLUENCE_USER env var).",
)
@click.option(
    "--confluence-token",
    envvar="CONFLUENCE_TOKEN",
    default=None,
    help="Atlassian API token (or set CONFLUENCE_TOKEN env var).",
)
@click.option(
    "--confluence-parent",
    default=None,
    help="Confluence parent page title to nest new page under.",
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
    folder_recursive: bool,
    folder_title: str | None,
    notion_page_id: str | None,
    notion_token: str | None,
    confluence_space: str | None,
    confluence_url: str | None,
    confluence_user: str | None,
    confluence_token: str | None,
    confluence_parent: str | None,
):
    """Generate documentation from a GitHub README, npm package, local Markdown file,
    Jupyter Notebook, or an entire folder of .md/.ipynb files.

    SOURCE can be:
      - A GitHub URL        (e.g., https://github.com/owner/repo)
      - An npm package      (e.g., npm:axios  or  npm:@scope/pkg)
      - A local file/notebook  (use --local flag)
      - A local folder path — all .md/.ipynb files will be merged
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
            OutputFormat.WORD,
            OutputFormat.PDF,
            OutputFormat.PPTX,
            OutputFormat.BLOG,
            OutputFormat.JIRA,
            OutputFormat.CHANGELOG,
            OutputFormat.LATEX,
            OutputFormat.ONEPAGER,
            OutputFormat.SOCIAL,
            OutputFormat.FAQ,
            OutputFormat.ARCHITECTURE,
            OutputFormat.MINDMAP,
        ]
    else:
        formats = [chosen]

    # Run pipeline — folder path or single file/URL
    pipeline = Pipeline(github_token=token)
    source_path = Path(source)

    if source_path.is_dir():
        # Multi-file folder mode
        result = pipeline.run_folder(
            source_path,
            output_dir=output_dir,
            formats=formats,
            title=folder_title,
            recursive=folder_recursive,
            theme_name=theme_name,
            mode=mode,
            api_key=api_key,
            model=model,
            base_url=base_url,
            sort_tables=sort_tables,
            provider=llm_provider,
            template_vars=tvars,
        )
    else:
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

    # ---- AI Reader files summary ------------------------------------
    if result.ai_reader_files:
        console.print("\n[bold cyan]AI Reader Files Generated:[/]")
        for af in result.ai_reader_files:
            console.print(f"  [green]✓[/] {af.name}")

    # ---- Post-generation publishing ------------------------------------
    # Find the best Markdown file to publish (blog_post.md preferred)
    def _find_markdown_output() -> Path | None:
        md_candidates = [r.output_path for r in result.results if r.success and r.output_path.suffix == ".md"]
        # Prefer blog_post over analysis_report over any other .md
        for candidate in md_candidates:
            if "blog" in candidate.stem.lower():
                return candidate
        return md_candidates[0] if md_candidates else None

    if notion_page_id:
        if not notion_token:
            console.print(
                "[yellow]WARNING: --publish-notion requires --notion-token (or NOTION_TOKEN env var). Skipping.[/]"
            )
        else:
            md_file = _find_markdown_output()
            if not md_file:
                console.print("[yellow]WARNING: No Markdown output found to publish to Notion.[/]")
            else:
                try:
                    from .publishers import NotionPublisher

                    console.print("[bold blue]Publishing to Notion...[/]")
                    pub = NotionPublisher(token=notion_token, page_id=notion_page_id)
                    url = pub.publish(md_file)
                    console.print(f"[green][OK][/] Notion page created → {url}")
                except ImportError:
                    console.print("[red]notion-client not installed. Run: pip install opendocs[publish][/]")
                except Exception as exc:
                    console.print(f"[red]Notion publish failed: {exc}[/]")

    if confluence_space:
        missing = [
            n
            for n, v in [
                ("--confluence-url", confluence_url),
                ("--confluence-user", confluence_user),
                ("--confluence-token", confluence_token),
            ]
            if not v
        ]
        if missing:
            console.print(f"[yellow]WARNING: Confluence publish requires {', '.join(missing)}. Skipping.[/]")
        else:
            md_file = _find_markdown_output()
            if not md_file:
                console.print("[yellow]WARNING: No Markdown output found to publish to Confluence.[/]")
            else:
                try:
                    from .publishers import ConfluencePublisher

                    console.print("[bold blue]Publishing to Confluence...[/]")
                    pub = ConfluencePublisher(
                        url=confluence_url,
                        username=confluence_user,
                        token=confluence_token,
                        space_key=confluence_space,
                        parent_page_title=confluence_parent,
                    )
                    url = pub.publish(md_file)
                    console.print(f"[green][OK][/] Confluence page created/updated → {url}")
                except ImportError:
                    console.print("[red]requests not installed. Run: pip install opendocs[publish][/]")
                except Exception as exc:
                    console.print(f"[red]Confluence publish failed: {exc}[/]")

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
    from .core.notebook_parser import NotebookParser, is_notebook
    from .core.parser import ReadmeParser

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
    "-o",
    "--output",
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
    "-f",
    "--format",
    "fmt",
    type=click.Choice(
        [
            "word",
            "pdf",
            "pptx",
            "blog",
            "jira",
            "changelog",
            "latex",
            "onepager",
            "social",
            "faq",
            "architecture",
            "all",
        ],
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
    type=click.Choice(["basic", "llm", "template"], case_sensitive=False),
    default="basic",
    help="Mode: basic (minimal), template (rich docs, no LLM), or llm (AI-enhanced).",
)
@click.option("--api-key", envvar="OPENAI_API_KEY", default=None)
@click.option("--model", default="gpt-4o-mini")
@click.option(
    "--provider",
    "llm_provider",
    type=click.Choice(["openai", "anthropic", "google", "ollama", "azure"], case_sensitive=False),
    default="openai",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Template variables config file.",
)
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
    node = parent.add(f"[blue]H{section.level}:[/blue] {section.title} [dim]({len(section.blocks)} blocks)[/dim]")
    for sub in section.subsections:
        _add_section_tree(node, sub)


@main.command()
@click.argument("codebase_dir", type=click.Path(exists=True))
@click.option(
    "-f",
    "--format",
    "fmt",
    type=click.Choice(
        [
            "word",
            "pdf",
            "pptx",
            "blog",
            "jira",
            "changelog",
            "latex",
            "onepager",
            "social",
            "faq",
            "architecture",
            "all",
        ],
        case_sensitive=False,
    ),
    default="all",
    help="Output format (default: all).",
)
@click.option(
    "-o",
    "--output",
    "output_dir",
    type=click.Path(),
    default="./output",
    help="Output directory (default: ./output).",
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
    type=click.Choice(["basic", "llm", "template"], case_sensitive=False),
    default="template",
    help="Mode: basic (minimal), template (rich docs, no LLM), or llm (AI-enhanced).",
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
    help="LLM model name (default: gpt-4o-mini).",
)
@click.option(
    "--base-url",
    default=None,
    help="Custom OpenAI-compatible API base URL.",
)
@click.option(
    "--provider",
    "llm_provider",
    type=click.Choice(["openai", "anthropic", "google", "ollama", "azure", "slm"], case_sensitive=False),
    default="openai",
    help="LLM provider. Use 'slm' for local Phi-3.5-mini model.",
)
@click.option(
    "--sort-tables",
    "sort_tables",
    default="smart",
    help="Table sort strategy: smart (auto), alpha, numeric, column:N, column:N:desc, or none.",
)
@click.option(
    "--adapter-path",
    "adapter_path",
    default=None,
    help="Path to a fine-tuned LoRA adapter directory (for --provider slm).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to YAML/JSON config file with template variables.",
)
@click.option("--project-name", default=None, help="Project name for document titles and headers.")
@click.option("--author", default=None, help="Document author name.")
@click.option("--doc-version", "doc_version", default=None, help="Document / project version string.")
@click.option("--org", "organisation", default=None, help="Organisation name for headers and footers.")
def codebase(
    codebase_dir: str,
    fmt: str,
    output_dir: str,
    theme_name: str,
    mode: str,
    api_key: str | None,
    model: str,
    base_url: str | None,
    llm_provider: str,
    sort_tables: str,
    adapter_path: str | None,
    config_path: str | None,
    project_name: str | None,
    author: str | None,
    doc_version: str | None,
    organisation: str | None,
):
    """Analyze a codebase directory and generate documentation from source code.

    Unlike the 'generate' command which requires a README or Markdown file,
    this command walks the actual source code in CODEBASE_DIR, extracts
    structure, tech stack, architecture, classes, functions, and
    dependencies, then generates comprehensive documentation.

    The default mode is 'template' which generates rich documentation with
    architecture diagrams, pie charts, risk assessment, and data-driven
    prose — entirely from code analysis, no LLM required.

    Use --mode llm (or --provider slm) for AI-enhanced narrative prose.

    \b
    Examples:
      opendocs codebase ./my-project                              # rich template docs (default)
      opendocs codebase ./my-project -f word                      # just Word doc
      opendocs codebase ./my-project --mode basic                 # minimal report
      opendocs codebase ./my-project --mode llm --provider slm    # local AI model
      opendocs codebase ./my-project --theme ocean                # with theme
    """
    console.print(BANNER)

    # Resolve template variables
    tvars = load_template_vars(
        config_path,
        project_name=project_name,
        author=author,
        version=doc_version,
        organisation=organisation,
    )

    # Resolve formats
    chosen = FORMAT_MAP[fmt.lower()]
    if chosen == OutputFormat.ALL:
        formats = [
            OutputFormat.WORD,
            OutputFormat.PDF,
            OutputFormat.PPTX,
            OutputFormat.BLOG,
            OutputFormat.JIRA,
            OutputFormat.CHANGELOG,
            OutputFormat.LATEX,
            OutputFormat.ONEPAGER,
            OutputFormat.SOCIAL,
            OutputFormat.FAQ,
            OutputFormat.ARCHITECTURE,
            OutputFormat.MINDMAP,
        ]
    else:
        formats = [chosen]

    pipeline = Pipeline()

    # When using SLM provider with basic mode, auto-switch to LLM mode.
    # Template mode is the recommended no-LLM approach.
    effective_mode = mode
    if llm_provider == "slm" and mode == "basic":
        effective_mode = "llm"

    result = pipeline.run_codebase(
        codebase_dir,
        output_dir=output_dir,
        formats=formats,
        theme_name=theme_name,
        mode=effective_mode,
        api_key=api_key,
        model=model,
        base_url=base_url,
        sort_tables=sort_tables,
        provider=llm_provider,
        adapter_path=adapter_path,
        template_vars=tvars,
    )

    if not any(r.success for r in result.results):
        raise SystemExit(1)


# ─── SLM commands ────────────────────────────────────────────────────────


@main.command("download-model")
@click.option(
    "--model",
    default="microsoft/Phi-3.5-mini-instruct",
    help="Hugging Face model ID to download.",
)
@click.option(
    "--cache-dir",
    default=None,
    help="Directory to cache the model (default: ~/.cache/opendocs/models).",
)
def download_model(model: str, cache_dir: str | None):
    """Pre-download an SLM model so the first inference is fast.

    \b
    Examples:
      opendocs download-model
      opendocs download-model --model microsoft/Phi-3.5-mini-instruct
    """
    console.print(BANNER)
    console.print(f"[bold blue]Downloading model:[/] {model}")

    try:
        from .llm.slm_provider import SLMProvider

        path = SLMProvider.download_model(model, cache_dir=cache_dir)
        console.print(f"[green][OK][/] Model downloaded to: {path}")
    except ImportError:
        console.print("[bold red]SLM dependencies not installed.[/]\nRun: pip install opendocs[slm]")
        raise SystemExit(1)
    except Exception as exc:
        console.print(f"[bold red]Download failed:[/] {exc}")
        raise SystemExit(1)


@main.command("finetune")
@click.argument("codebase_dir", type=click.Path(exists=True))
@click.option(
    "--reference-doc",
    "reference_doc",
    type=click.Path(exists=True),
    default=None,
    help="Reference .docx or .md file as the target documentation style.",
)
@click.option(
    "--output-dir",
    "-o",
    default="./opendocs-adapter",
    help="Directory to save the trained LoRA adapter.",
)
@click.option(
    "--base-model",
    default="microsoft/Phi-3.5-mini-instruct",
    help="Hugging Face base model ID.",
)
@click.option("--epochs", default=3, help="Number of training epochs.")
@click.option("--batch-size", default=1, help="Per-device batch size (1 for 6-8 GB VRAM).")
@click.option("--lora-r", default=16, help="LoRA rank.")
@click.option("--lora-alpha", default=32, help="LoRA alpha scaling factor.")
@click.option("--learning-rate", default=2e-4, help="Training learning rate.")
@click.option(
    "--examples-file",
    type=click.Path(exists=True),
    default=None,
    help="JSONL file with additional training examples.",
)
def finetune(
    codebase_dir: str,
    reference_doc: str | None,
    output_dir: str,
    base_model: str,
    epochs: int,
    batch_size: int,
    lora_r: int,
    lora_alpha: int,
    learning_rate: float,
    examples_file: str | None,
):
    """Fine-tune Phi-3.5-mini on codebase-to-documentation examples.

    Analyzes CODEBASE_DIR and (optionally) pairs it with a reference
    document to create training data, then runs QLoRA fine-tuning.

    The resulting adapter (~50 MB) can be loaded with:
      opendocs codebase ./project --provider slm --adapter-path ./opendocs-adapter/adapter

    \b
    Examples:
      opendocs finetune ./my-project --reference-doc ./my-doc.docx
      opendocs finetune ./my-project -o ./my-adapter --epochs 5
      opendocs finetune ./my-project --examples-file ./training.jsonl
    """
    console.print(BANNER)

    try:
        from .llm.slm_finetune import SLMFineTuner, generate_training_data_from_codebase
    except ImportError:
        console.print("[bold red]SLM dependencies not installed.[/]\nRun: pip install opendocs[slm]")
        raise SystemExit(1)

    console.print(f"[bold blue]Preparing fine-tuning data from:[/] {codebase_dir}")

    tuner = SLMFineTuner(
        base_model=base_model,
        output_dir=output_dir,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        learning_rate=learning_rate,
    )

    # Generate training example from codebase + optional reference
    try:
        example = generate_training_data_from_codebase(codebase_dir, reference_doc)
        if example.documentation:
            tuner.add_example(
                code_context=example.code_context,
                documentation=example.documentation,
                project_name=example.project_name,
            )
            console.print(
                f"[green][OK][/] Created training pair from codebase{' + reference doc' if reference_doc else ''}"
            )
        else:
            console.print(
                "[bold yellow]Warning:[/] No reference document provided. "
                "Add examples via --examples-file or provide a --reference-doc."
            )
    except Exception as exc:
        console.print(f"[bold yellow]Warning:[/] Could not analyze codebase: {exc}")

    # Load additional examples if provided
    if examples_file:
        n = tuner.add_examples_from_file(examples_file)
        console.print(f"[green][OK][/] Loaded {n} additional examples from {examples_file}")

    if not tuner.examples:
        console.print("[bold red]No training examples available. Provide a --reference-doc or --examples-file.[/]")
        raise SystemExit(1)

    console.print(
        f"\n[bold blue]Starting QLoRA fine-tuning:[/]\n"
        f"  Base model: {base_model}\n"
        f"  Examples: {len(tuner.examples)}\n"
        f"  Epochs: {epochs}\n"
        f"  LoRA rank: {lora_r}, alpha: {lora_alpha}\n"
        f"  Output: {output_dir}"
    )

    try:
        adapter_path = tuner.train(epochs=epochs, batch_size=batch_size)
        console.print(f"\n[green][OK][/] Fine-tuning complete! Adapter saved to: {adapter_path}")
        console.print(
            f"\n[dim]Use it with:[/]\n  opendocs codebase ./your-project --provider slm --adapter-path {adapter_path}"
        )
    except Exception as exc:
        console.print(f"[bold red]Fine-tuning failed:[/] {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
