"""Scheduled generation and change detection daemon.

Monitors a repository (local clone) for changes to README.md or other
key files and automatically regenerates documentation when changes are
detected.  Can optionally open a pull request with updated outputs.

Modes:
    - **watch** — continuous file-system polling (no external deps)
    - **oneshot** — check once and regenerate if changed (for cron jobs)

Usage::

    # Continuous watching
    opendocs watch ./my-repo --interval 30

    # One-shot for cron
    opendocs watch ./my-repo --once

    # Watch + auto-PR
    opendocs watch ./my-repo --auto-pr --branch docs-update
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

log = logging.getLogger(__name__)
console = Console()

# Default files to monitor
DEFAULT_WATCH_PATTERNS = [
    "README.md",
    "readme.md",
    "Readme.md",
    "CHANGELOG.md",
    "docs/**/*.md",
    "*.ipynb",
]

# State file to track last known hashes
_STATE_FILENAME = ".opendocs-watch-state.json"


# ---------------------------------------------------------------------------
# Hashing / change detection
# ---------------------------------------------------------------------------

def _hash_file(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except (OSError, PermissionError):
        return ""
    return h.hexdigest()


def _discover_watched_files(
    repo_dir: Path,
    patterns: list[str] | None = None,
) -> list[Path]:
    """Find all files matching watch patterns in the repo directory."""
    patterns = patterns or DEFAULT_WATCH_PATTERNS
    found: list[Path] = []

    for pattern in patterns:
        if "**" in pattern or "*" in pattern:
            found.extend(repo_dir.glob(pattern))
        else:
            candidate = repo_dir / pattern
            if candidate.exists():
                found.append(candidate)

    # Deduplicate and sort
    return sorted(set(f for f in found if f.is_file()))


def _compute_state(files: list[Path]) -> dict[str, str]:
    """Compute a hash-state dict for a list of files."""
    return {str(f): _hash_file(f) for f in files}


def _load_state(repo_dir: Path) -> dict[str, str]:
    """Load previously saved state from the state file."""
    import json
    state_path = repo_dir / _STATE_FILENAME
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(repo_dir: Path, state: dict[str, str]) -> None:
    """Persist the current state to the state file."""
    import json
    state_path = repo_dir / _STATE_FILENAME
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def detect_changes(
    repo_dir: Path,
    patterns: list[str] | None = None,
) -> tuple[list[Path], list[Path], list[Path]]:
    """Detect changed, added, and removed files since last check.

    Returns
    -------
    tuple[list[Path], list[Path], list[Path]]
        (changed_files, added_files, removed_files)
    """
    files = _discover_watched_files(repo_dir, patterns)
    current_state = _compute_state(files)
    previous_state = _load_state(repo_dir)

    changed: list[Path] = []
    added: list[Path] = []
    removed: list[Path] = []

    for fpath, fhash in current_state.items():
        if fpath not in previous_state:
            added.append(Path(fpath))
        elif previous_state[fpath] != fhash:
            changed.append(Path(fpath))

    for fpath in previous_state:
        if fpath not in current_state:
            removed.append(Path(fpath))

    return changed, added, removed


# ---------------------------------------------------------------------------
# Git helpers (for auto-PR)
# ---------------------------------------------------------------------------

def _git_run(repo_dir: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in the repo directory."""
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _git_branch_exists(repo_dir: Path, branch: str) -> bool:
    """Check if a git branch exists locally."""
    result = _git_run(repo_dir, "branch", "--list", branch)
    return branch in result.stdout


def _create_docs_pr(
    repo_dir: Path,
    output_dir: Path,
    branch_name: str = "docs/auto-update",
    commit_message: str | None = None,
) -> bool:
    """Create a git branch with updated docs and push it.

    This creates a branch, commits the generated output files, and
    pushes to the remote.  The actual PR creation requires either
    ``gh`` CLI or GitHub API — we attempt ``gh`` first.

    Returns True if the branch was pushed successfully.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    branch = f"{branch_name}-{timestamp}"
    message = commit_message or f"docs: auto-update generated documentation ({timestamp})"

    try:
        # Ensure we're on a clean state
        _git_run(repo_dir, "stash", "--include-untracked")

        # Create and switch to new branch
        result = _git_run(repo_dir, "checkout", "-b", branch)
        if result.returncode != 0:
            log.error("Failed to create branch %s: %s", branch, result.stderr)
            return False

        # Add output files
        _git_run(repo_dir, "add", str(output_dir))
        _git_run(repo_dir, "add", _STATE_FILENAME)

        # Commit
        result = _git_run(repo_dir, "commit", "-m", message)
        if result.returncode != 0:
            log.warning("Nothing to commit: %s", result.stderr)
            _git_run(repo_dir, "checkout", "-")
            return False

        # Push
        result = _git_run(repo_dir, "push", "-u", "origin", branch)
        if result.returncode != 0:
            log.error("Failed to push branch: %s", result.stderr)
            _git_run(repo_dir, "checkout", "-")
            return False

        console.print(f"[green]✓[/] Pushed branch [bold]{branch}[/] to origin")

        # Try to create a PR using gh CLI
        try:
            pr_result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", f"📄 Auto-update documentation ({timestamp})",
                    "--body", (
                        "This PR was automatically generated by **OpenDocs** watcher.\n\n"
                        f"**Branch:** `{branch}`\n"
                        f"**Generated at:** {timestamp}\n\n"
                        "Review the updated documentation and merge when ready."
                    ),
                    "--base", "main",
                ],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if pr_result.returncode == 0:
                console.print(f"[green]✓[/] Pull request created: {pr_result.stdout.strip()}")
            else:
                console.print(
                    f"[yellow]⚠[/] Branch pushed but PR creation failed "
                    f"(install `gh` CLI for auto-PR): {pr_result.stderr.strip()}"
                )
        except FileNotFoundError:
            console.print(
                f"[yellow]⚠[/] Branch [bold]{branch}[/] pushed. "
                "Install GitHub CLI (`gh`) to auto-create pull requests."
            )

        # Switch back to previous branch
        _git_run(repo_dir, "checkout", "-")
        _git_run(repo_dir, "stash", "pop")
        return True

    except Exception as exc:
        log.error("Auto-PR failed: %s", exc)
        # Try to recover
        _git_run(repo_dir, "checkout", "-")
        try:
            _git_run(repo_dir, "stash", "pop")
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Regeneration callback
# ---------------------------------------------------------------------------

def _regenerate(
    repo_dir: Path,
    changed_files: list[Path],
    *,
    output_dir: str = "./output",
    formats: list[str] | None = None,
    theme: str = "corporate",
    mode: str = "basic",
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
    provider: str = "openai",
    config_path: str | None = None,
) -> bool:
    """Regenerate documentation for changed files.

    Returns True if generation was successful.
    """
    from ..pipeline import Pipeline
    from ..core.models import OutputFormat

    format_map = {
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
    }

    out_formats = None
    if formats:
        out_formats = [format_map[f] for f in formats if f in format_map]

    pipeline = Pipeline()
    success = True

    for fpath in changed_files:
        source = str(fpath)
        console.print(f"\n[bold blue]Regenerating docs for:[/] {fpath.name}")

        try:
            result = pipeline.run(
                source,
                output_dir=output_dir,
                formats=out_formats,
                local=True,
                theme_name=theme,
                mode=mode,
                api_key=api_key,
                model=model,
                provider=provider,
            )

            if not any(r.success for r in result.results):
                console.print(f"[red]✗[/] Generation failed for {fpath.name}")
                success = False
        except Exception as exc:
            console.print(f"[red]✗[/] Error processing {fpath.name}: {exc}")
            success = False

    return success


# ---------------------------------------------------------------------------
# Main watcher loop
# ---------------------------------------------------------------------------

class FileWatcher:
    """Watches a repository directory for changes and triggers regeneration.

    Parameters
    ----------
    repo_dir
        Path to the repository root to watch.
    output_dir
        Directory where generated docs will be placed.
    interval
        Seconds between change-detection checks.
    patterns
        File patterns to watch (default: README.md, CHANGELOG.md, docs/, *.ipynb).
    auto_pr
        If True, create a git branch + PR when changes are detected.
    branch_name
        Base name for auto-PR branches.
    formats
        Output formats to generate (default: all).
    theme
        Document theme name.
    mode
        Generation mode: 'basic' or 'llm'.
    api_key
        LLM API key (for 'llm' mode).
    model
        LLM model name.
    provider
        LLM provider name.
    config_path
        Path to template variables config file.
    """

    def __init__(
        self,
        repo_dir: str | Path,
        *,
        output_dir: str = "./output",
        interval: int = 30,
        patterns: list[str] | None = None,
        auto_pr: bool = False,
        branch_name: str = "docs/auto-update",
        formats: list[str] | None = None,
        theme: str = "corporate",
        mode: str = "basic",
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        provider: str = "openai",
        config_path: str | None = None,
    ) -> None:
        self.repo_dir = Path(repo_dir).expanduser().resolve()
        self.output_dir = output_dir
        self.interval = interval
        self.patterns = patterns
        self.auto_pr = auto_pr
        self.branch_name = branch_name
        self.formats = formats
        self.theme = theme
        self.mode = mode
        self.api_key = api_key
        self.model = model
        self.provider = provider
        self.config_path = config_path

        if not self.repo_dir.is_dir():
            raise NotADirectoryError(f"Repository directory not found: {self.repo_dir}")

    def check_once(self) -> bool:
        """Run a single change-detection + regeneration cycle.

        Returns True if changes were detected and processed.
        """
        console.print(f"[dim]Checking for changes in {self.repo_dir}...[/]")

        changed, added, removed = detect_changes(self.repo_dir, self.patterns)

        if not changed and not added:
            console.print("[dim]No changes detected.[/]")
            return False

        # Report what changed
        all_changed = changed + added
        console.print(f"\n[bold yellow]📝 Changes detected:[/]")
        for f in changed:
            console.print(f"  [yellow]Modified:[/] {f.relative_to(self.repo_dir)}")
        for f in added:
            console.print(f"  [green]Added:[/] {f.relative_to(self.repo_dir)}")
        for f in removed:
            console.print(f"  [red]Removed:[/] {f.relative_to(self.repo_dir)}")

        # Regenerate
        out_path = Path(self.output_dir)
        if not out_path.is_absolute():
            out_path = self.repo_dir / out_path

        success = _regenerate(
            self.repo_dir,
            all_changed,
            output_dir=str(out_path),
            formats=self.formats,
            theme=self.theme,
            mode=self.mode,
            api_key=self.api_key,
            model=self.model,
            provider=self.provider,
            config_path=self.config_path,
        )

        # Update state
        files = _discover_watched_files(self.repo_dir, self.patterns)
        _save_state(self.repo_dir, _compute_state(files))

        # Auto-PR
        if success and self.auto_pr:
            console.print("\n[bold blue]Creating pull request...[/]")
            _create_docs_pr(
                self.repo_dir,
                out_path,
                branch_name=self.branch_name,
            )

        return success

    def watch(self) -> None:
        """Run the continuous watch loop.

        This blocks indefinitely, checking for changes every ``interval``
        seconds.  Press Ctrl+C to stop.
        """
        console.print(f"\n[bold green]🔍 OpenDocs Watcher[/]")
        console.print(f"   Repository: [bold]{self.repo_dir}[/]")
        console.print(f"   Output:     [bold]{self.output_dir}[/]")
        console.print(f"   Interval:   [bold]{self.interval}s[/]")
        console.print(f"   Auto-PR:    [bold]{'yes' if self.auto_pr else 'no'}[/]")

        watched = _discover_watched_files(self.repo_dir, self.patterns)
        console.print(f"   Watching:   [bold]{len(watched)} file(s)[/]")
        for f in watched[:10]:
            console.print(f"     • {f.relative_to(self.repo_dir)}")
        if len(watched) > 10:
            console.print(f"     ... and {len(watched) - 10} more")

        console.print(f"\n[dim]Press Ctrl+C to stop.[/]\n")

        # Initialize state on first run
        state = _compute_state(watched)
        _save_state(self.repo_dir, state)

        cycle = 0
        try:
            while True:
                time.sleep(self.interval)
                cycle += 1

                try:
                    self.check_once()
                except Exception as exc:
                    console.print(f"[red]Error in watch cycle {cycle}: {exc}[/]")
                    log.exception("Watch cycle %d failed", cycle)

        except KeyboardInterrupt:
            console.print("\n[bold yellow]⏹  Watcher stopped.[/]")
