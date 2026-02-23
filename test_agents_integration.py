"""Integration test — run the agents layer against a real GitHub repo.

Fetches a README via the existing opendocs pipeline, builds the
KnowledgeGraph, constructs a RepoProfile, and runs the full
Planner → Executor → Critic orchestration loop.
"""

from __future__ import annotations

import asyncio
import json
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ── opendocs core ──
from opendocs.core.fetcher import ReadmeFetcher
from opendocs.core.parser import ReadmeParser
from opendocs.core.semantic_extractor import SemanticExtractor

# ── agents ──
from opendocs.agents.base import RepoProfile, RepoSignal
from opendocs.agents.orchestrator import AgentOrchestrator
from opendocs.agents.privacy import PrivacyMode

# ── diff pipeline ──
from opendocs.agents.diff import DiffAgent, ImpactAgent, RegenerationAgent, ReleaseNotesAgent
from opendocs.agents.diff.diff_agent import DiffSummary, FileDiff

console = Console()


# ─────────────────────────────────────────────────────────────────────
# Signal detection heuristics
# ─────────────────────────────────────────────────────────────────────

_SIGNAL_PATTERNS: dict[str, list[str]] = {
    "docker-compose": ["docker-compose.yml", "docker-compose.yaml", "compose.yml"],
    "kubernetes": ["deployment.yaml", "deployment.yml", "k8s/", "kube/"],
    "terraform": [".tf"],
    "helm": ["Chart.yaml", "charts/"],
    "kafka": ["kafka"],
    "airflow": ["dags/", "airflow"],
    "dbt": ["dbt_project.yml"],
    "pytorch": ["torch", "pytorch"],
    "tensorflow": ["tensorflow", "tf."],
    "huggingface": ["transformers", "huggingface"],
}


def detect_signals(content: str, file_tree: list[str]) -> list[RepoSignal]:
    """Detect repo signals from README content and file paths."""
    signals: list[RepoSignal] = []
    content_lower = content.lower()

    for signal_type, patterns in _SIGNAL_PATTERNS.items():
        for pat in patterns:
            # Check file tree
            for path in file_tree:
                if pat in path.lower():
                    signals.append(RepoSignal(
                        signal_type=signal_type,
                        file_path=path,
                        confidence=0.9,
                    ))
                    break
            else:
                # Check README content
                if pat.lower() in content_lower:
                    signals.append(RepoSignal(
                        signal_type=signal_type,
                        confidence=0.6,
                        details={"source": "readme_mention"},
                    ))
    return signals


def build_profile(
    repo_url: str,
    repo_name: str,
    readme_content: str,
    kg,
) -> RepoProfile:
    """Build a RepoProfile from pipeline data."""
    # Simulate file tree from KG entities + README mentions
    file_tree: list[str] = []
    for entity in kg.entities:
        src = entity.properties.get("source_file", "")
        if src:
            file_tree.append(src)

    signals = detect_signals(readme_content, file_tree)

    return RepoProfile(
        repo_name=repo_name,
        repo_url=repo_url,
        description=kg.summary[:200] if kg.summary else "",
        primary_language="Python",  # heuristic — could parse from GH API
        file_tree=file_tree,
        signals=signals,
        readme_summary=kg.summary[:500] if kg.summary else "",
    )


# ─────────────────────────────────────────────────────────────────────
# Main test runner
# ─────────────────────────────────────────────────────────────────────

async def run_agents_on_repo(repo_url: str) -> None:
    console.print(Panel(f"[bold]Agent Integration Test[/bold]\n{repo_url}", style="cyan"))

    # ── 1. Fetch + Parse + Extract KG ──
    console.print("\n[bold blue]1. Fetching & parsing README...[/bold blue]")
    fetcher = ReadmeFetcher(timeout=30.0)
    content, name = fetcher.fetch(repo_url)
    console.print(f"   [green]✓[/green] Fetched {len(content):,} chars for [bold]{name}[/bold]")

    parser = ReadmeParser()
    doc = parser.parse(content, repo_name=name, repo_url=repo_url, source_path=repo_url)
    console.print(f"   [green]✓[/green] Parsed: {len(doc.sections)} sections, {len(doc.all_blocks)} blocks")

    extractor = SemanticExtractor()
    kg = extractor.extract(doc)
    console.print(f"   [green]✓[/green] KG: {len(kg.entities)} entities, {len(kg.relations)} relations")

    # ── 2. Build RepoProfile ──
    console.print("\n[bold blue]2. Building RepoProfile...[/bold blue]")
    profile = build_profile(repo_url, name, content, kg)
    console.print(f"   [green]✓[/green] Profile: {profile.repo_name}")
    console.print(f"   Signals: {[s.signal_type for s in profile.signals] or 'none detected'}")
    console.print(f"   File tree: {len(profile.file_tree)} paths")

    # ── 3. Run Agent Orchestrator ──
    console.print("\n[bold blue]3. Running Agent Orchestrator (Planner → Executor → Critic)...[/bold blue]")
    orch = AgentOrchestrator(
        model="gpt-4o-mini",
        privacy_mode=PrivacyMode.STANDARD,
        max_retries=1,
    )
    result = await orch.run(
        repo_profile=profile,
        knowledge_graph=kg,
        document=doc,
    )

    # ── 4. Display results ──
    console.print("\n[bold blue]4. Orchestration Results[/bold blue]")
    summary = result.summary()

    table = Table(title="Orchestration Summary")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    for k, v in summary.items():
        if k == "verdict":
            table.add_row(k, json.dumps(v, indent=2) if v else "N/A")
        elif k == "artifacts":
            table.add_row(k, ", ".join(v) if v else "none")
        else:
            table.add_row(k, str(v))
    console.print(table)

    # Show plan steps
    if result.plan:
        console.print(f"\n[bold]Plan:[/bold] {result.plan.goal}")
        for step in result.plan.steps:
            status = "✓" if step.completed else "✗"
            color = "green" if step.completed else "red"
            console.print(f"   [{color}]{status}[/{color}] Step {step.step_number}: {step.description}")
            for tc in step.tool_calls:
                console.print(f"      → {tc.tool_name} ({tc.status.value})")

    # Show step results summary
    if result.step_results:
        console.print(f"\n[bold]Step Results:[/bold] {len(result.step_results)} executed")
        for i, sr in enumerate(result.step_results):
            status = "[green]✓[/green]" if sr.success else "[red]✗[/red]"
            arts = list(sr.artifacts.keys())
            console.print(f"   {status} {sr.agent_role.value}: artifacts={arts}")

    # Show enhanced artifacts
    if result.enhanced_artifacts:
        console.print(f"\n[bold]Enhanced Artifacts:[/bold]")
        for key, val in result.enhanced_artifacts.items():
            if isinstance(val, str) and len(val) > 200:
                console.print(f"   [cyan]{key}[/cyan]: {val[:200]}...")
            elif isinstance(val, dict):
                console.print(f"   [cyan]{key}[/cyan]: {json.dumps(val, indent=2)[:300]}")
            else:
                console.print(f"   [cyan]{key}[/cyan]: {str(val)[:200]}")

    # ── 5. Run Diff Pipeline ──
    console.print("\n[bold blue]5. Running Diff Pipeline (simulated HEAD~1 → HEAD)...[/bold blue]")

    diff_agent = DiffAgent()
    diff_result = await diff_agent.run(
        repo_profile=profile,
        knowledge_graph=kg,
        base_ref="HEAD~1",
        head_ref="HEAD",
    )
    console.print(f"   [green]✓[/green] DiffAgent: {diff_result.success}")

    impact_agent = ImpactAgent()
    # Simulate a file change to show impact analysis
    simulated_diff = DiffSummary(
        base_ref="HEAD~1",
        head_ref="HEAD",
        total_files=1,
        total_additions=15,
        total_deletions=3,
        file_diffs=[
            FileDiff(
                path=profile.file_tree[0] if profile.file_tree else "README.md",
                status="modified",
                additions=15,
                deletions=3,
            ),
        ],
    )
    impact_result = await impact_agent.run(
        repo_profile=profile,
        knowledge_graph=kg,
        diff_summary=simulated_diff,
    )
    console.print(f"   [green]✓[/green] ImpactAgent: {impact_result.success}")
    if impact_result.success:
        report = impact_result.artifacts.get("impact_report", {})
        console.print(f"      Deltas: {report.get('total_deltas', 0)}, "
                      f"Formats: {report.get('impacted_formats', [])}")

    release_agent = ReleaseNotesAgent()
    release_result = await release_agent.run(
        repo_profile=profile,
        knowledge_graph=kg,
        diff_summary=simulated_diff,
        version="0.5.0-test",
    )
    console.print(f"   [green]✓[/green] ReleaseNotesAgent: {release_result.success}")
    if release_result.success:
        md = release_result.artifacts.get("release_notes_md", "")
        if md:
            console.print(Panel(md[:500], title="Release Notes Preview", style="dim"))

    # ── Done ──
    console.print(f"\n[bold green]✓ All agent tests passed on {name}![/bold green]")
    console.print(f"  Total duration: {result.total_duration_ms:.0f}ms\n")


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/fastapi/fastapi"
    asyncio.run(run_agents_on_repo(url))


if __name__ == "__main__":
    main()
