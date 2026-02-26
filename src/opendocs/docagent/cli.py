"""DocAgent CLI — generate structured documents from GitHub repos.

Usage:
    docagent generate <github_url> [--outputs all]
    docagent sessions
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table as RichTable
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .agent_loop import AgentLoop
from .config import WorkspaceConfig
from .models.document_model import DocumentType, ExportFormat
from .session import SessionManager

console = Console()

BANNER = r"""
  ____             _                    _
 |  _ \  ___   ___/ \   __ _  ___ _ __ | |_
 | | | |/ _ \ / __/ _ \ / _` |/ _ \ '_ \| __|
 | |_| | (_) | (__  __/| (_| |  __/ | | | |_
 |____/ \___/ \___\___| \__, |\___|_| |_|\__|
                        |___/
  Agentic Document Generation  v0.1.0
"""

# Maps for CLI choices → enums
_DOC_TYPE_MAP: dict[str, DocumentType] = {
    "prd": DocumentType.PRD,
    "proposal": DocumentType.PROPOSAL,
    "sop": DocumentType.SOP,
    "report": DocumentType.REPORT,
    "slides": DocumentType.SLIDES,
    "changelog": DocumentType.CHANGELOG,
    "onboarding": DocumentType.ONBOARDING,
    "tech-debt": DocumentType.TECH_DEBT,
    "all": None,  # type: ignore[dict-item]  # sentinel
}

_FORMAT_MAP: dict[str, ExportFormat] = {
    "word": ExportFormat.WORD,
    "pdf": ExportFormat.PDF,
    "pptx": ExportFormat.PPTX,
}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(version="0.1.0", prog_name="docagent")
def main():
    """docagent — Generate structured documents from any GitHub repository."""
    pass


@main.command()
@click.argument("url")
@click.option(
    "--outputs",
    "output_choice",
    type=click.Choice(["all", "word", "pdf", "pptx"], case_sensitive=False),
    default="all",
    help="Output format(s). 'all' generates Word + PDF + PPTX.",
)
@click.option(
    "--docs",
    "doc_choice",
    type=click.Choice(["all", "prd", "proposal", "sop", "report", "slides", "changelog", "onboarding", "tech-debt"], case_sensitive=False),
    default="all",
    help="Document type(s) to generate.",
)
@click.option(
    "--workspace",
    "workspace_path",
    type=click.Path(),
    default=None,
    help="Custom workspace root (default: ~/.docagent/workspace).",
)
@click.option(
    "--mode",
    type=click.Choice(["auto", "llm", "deterministic"], case_sensitive=False),
    default="auto",
    help="Generation mode. 'llm' uses GPT, 'deterministic' uses templates, 'auto' tries LLM first.",
)
@click.option(
    "--api-key",
    "api_key",
    default=None,
    envvar="OPENAI_API_KEY",
    help="OpenAI API key (defaults to OPENAI_API_KEY env var).",
)
@click.option(
    "--model",
    "llm_model",
    default="gpt-4o-mini",
    help="LLM model name (default: gpt-4o-mini).",
)
@click.option(
    "--base-url",
    "base_url",
    default=None,
    help="Custom OpenAI-compatible API base URL.",
)
@click.option(
    "--provider",
    "llm_provider",
    type=click.Choice(["openai", "anthropic", "google", "ollama", "azure"], case_sensitive=False),
    default="openai",
    help="LLM provider: openai (default), anthropic (Claude), google (Gemini), ollama (local), azure.",
)
@click.option(
    "--theme",
    "theme_name",
    type=click.Choice(
        [
            "corporate", "ocean", "sunset", "dark", "minimal", "emerald", "royal",
            "slate", "rose", "nordic", "cyber", "terracotta", "sapphire", "mint",
            "monochrome",
        ],
        case_sensitive=False,
    ),
    default="corporate",
    help="Visual theme for generated documents (default: corporate).",
)
@click.option(
    "--since",
    "since_date",
    default=None,
    help="Start date for git history (e.g. '2025-01-01' or '3 months ago'). Enables real changelog from commits.",
)
@click.option(
    "--until",
    "until_date",
    default=None,
    help="End date for git history (e.g. '2025-06-01'). Defaults to today.",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose logging.")
def generate(
    url: str,
    output_choice: str,
    doc_choice: str,
    workspace_path: str | None,
    mode: str,
    api_key: str | None,
    llm_model: str,
    base_url: str | None,
    llm_provider: str,
    theme_name: str,
    since_date: str | None,
    until_date: str | None,
    verbose: bool,
):
    """Generate documents from a GitHub repository.

    URL should be a GitHub repository URL, e.g.:
    https://github.com/owner/repo
    """
    _setup_logging(verbose)
    console.print(BANNER, style="bold cyan")

    # Resolve LLM mode
    import os
    if mode == "llm":
        use_llm = True
    elif mode == "deterministic":
        use_llm = False
    else:  # auto
        # Check for API key from any supported provider
        key_env_vars = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "ollama": "",
            "azure": "AZURE_OPENAI_API_KEY",
        }
        env_var = key_env_vars.get(llm_provider.lower(), "OPENAI_API_KEY")
        has_key = bool(api_key or (env_var and os.environ.get(env_var)))
        use_llm = has_key or llm_provider.lower() == "ollama"

    mode_label = "[bold green]LLM[/] 🧠" if use_llm else "[bold yellow]Deterministic[/] 📐"
    provider_label = f" ({llm_provider})" if use_llm else ""

    # Resolve workspace
    ws = WorkspaceConfig(root=Path(workspace_path)) if workspace_path else WorkspaceConfig()

    # Resolve export formats
    if output_choice == "all":
        export_formats = list(ExportFormat)
    else:
        export_formats = [_FORMAT_MAP[output_choice.lower()]]

    # Resolve document types
    if doc_choice == "all":
        doc_types = list(DocumentType)
    else:
        doc_types = [_DOC_TYPE_MAP[doc_choice.lower()]]

    history_label = ""
    if since_date:
        history_label = f"\n[bold]History:[/]    {since_date} → {until_date or 'now'}"

    console.print(Panel(
        f"[bold]Repository:[/] {url}\n"
        f"[bold]Documents:[/]  {', '.join(d.value for d in doc_types)}\n"
        f"[bold]Formats:[/]    {', '.join(f.value for f in export_formats)}\n"
        f"[bold]Theme:[/]      {theme_name}\n"
        f"[bold]Mode:[/]       {mode_label}{provider_label}"
        + (f"\n[bold]Model:[/]      {llm_model}" if use_llm else "")
        + history_label,
        title="[bold green]DocAgent — New Session[/]",
        border_style="green",
    ))

    # Run agent loop
    agent = AgentLoop(workspace=ws)
    session_mgr = SessionManager(workspace=ws)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Running agent loop...", total=None)

        try:
            result = agent.run(
                url,
                doc_types=doc_types,
                export_formats=export_formats,
                use_llm=use_llm,
                api_key=api_key,
                llm_model=llm_model,
                base_url=base_url,
                theme_name=theme_name,
                since=since_date,
                until=until_date,
                llm_provider=llm_provider,
            )
        except Exception as exc:
            progress.stop()
            console.print(f"\n[bold red]Agent failed:[/] {exc}")
            raise SystemExit(1)

        progress.update(task, description="[green]Complete!")

    # Save session
    session_mgr.save_result(result)

    # Print results
    console.print()
    if result.errors:
        for err in result.errors:
            console.print(f"[red]ERROR:[/] {err}")
        raise SystemExit(1)

    # Summary table
    table = RichTable(title="Generated Documents", show_lines=True)
    table.add_column("Document", style="bold cyan")
    table.add_column("Draft", style="dim")
    table.add_column("Outputs", style="green")

    for doc_type, draft_path in result.drafts.items():
        outputs = result.outputs.get(doc_type, [])
        output_str = "\n".join(str(Path(p).name) for p in outputs) or "—"
        table.add_row(doc_type.upper(), Path(draft_path).name, output_str)

    console.print(table)
    console.print(f"\n[bold]Session:[/]  {result.session_id}")
    console.print(f"[bold]Outputs:[/]  {ws.outputs_dir(result.session_id)}")
    console.print(f"[bold]Elapsed:[/]  {result.elapsed_seconds:.1f}s")
    console.print("\n[bold green]Done![/] 🚀\n")


@main.command()
@click.option(
    "--workspace",
    "workspace_path",
    type=click.Path(),
    default=None,
)
def sessions(workspace_path: str | None):
    """List all previous DocAgent sessions."""
    ws = WorkspaceConfig(root=Path(workspace_path)) if workspace_path else WorkspaceConfig()
    mgr = SessionManager(workspace=ws)
    all_sessions = mgr.list_sessions()

    if not all_sessions:
        console.print("[dim]No sessions found.[/]")
        return

    table = RichTable(title="DocAgent Sessions")
    table.add_column("Session ID", style="bold cyan")
    table.add_column("Repository", style="dim")
    table.add_column("Outputs", justify="right")
    table.add_column("Elapsed", justify="right")

    for s in all_sessions:
        table.add_row(
            s["id"],
            s.get("repo_url", "—"),
            str(s.get("output_count", "—")),
            f"{s.get('elapsed', 0):.1f}s" if s.get("elapsed") else "—",
        )

    console.print(table)


if __name__ == "__main__":
    main()
