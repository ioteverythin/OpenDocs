"""Repository tool adapters — repo.search, repo.read, repo.diff, repo.summarize.

These tools interact with the local git clone (or GitHub API) to provide
evidence-grounded data to agents. They are the most commonly used tools
in the generation bus.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from ..evidence import EvidencePointer, EvidenceType


class _RepoToolBase(ABC):
    """Shared state for repo tools — the local repo path."""

    def __init__(self, repo_path: Path | str) -> None:
        self.repo_path = Path(repo_path)

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> Any:
        ...


# ---------------------------------------------------------------------------
# repo.search
# ---------------------------------------------------------------------------

class RepoSearchTool(_RepoToolBase):
    """Search repository files by keyword / regex.

    Returns matching file paths, line numbers, and short snippets,
    each wrapped in an EvidencePointer.
    """

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query: str = params["query"]
        file_pattern: str = params.get("file_pattern", "**/*")
        max_results: int = params.get("max_results", 20)

        # TODO: implement actual grep/ripgrep search over repo_path
        #       For now, return a placeholder structure.
        results: list[dict[str, Any]] = []

        # Placeholder — in production, use subprocess + ripgrep:
        # rg --json -m {max_results} -g '{file_pattern}' '{query}' {repo_path}
        return {
            "query": query,
            "matches": results,
            "total": len(results),
            "evidence_pointers": [],  # list[EvidencePointer] serialised
        }


# ---------------------------------------------------------------------------
# repo.read
# ---------------------------------------------------------------------------

class RepoReadTool(_RepoToolBase):
    """Read a file or line range from the repository.

    Returns the file content and a corresponding EvidencePointer.
    """

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        rel_path: str = params["path"]
        start_line: Optional[int] = params.get("start_line")
        end_line: Optional[int] = params.get("end_line")

        full_path = self.repo_path / rel_path
        if not full_path.exists():
            return {"error": f"File not found: {rel_path}", "content": ""}

        # TODO: implement line-range slicing and privacy filtering
        content = ""
        try:
            raw = full_path.read_text(encoding="utf-8", errors="replace")
            lines = raw.splitlines()
            if start_line is not None and end_line is not None:
                content = "\n".join(lines[start_line - 1 : end_line])
            else:
                content = raw
        except Exception as exc:
            return {"error": str(exc), "content": ""}

        pointer = EvidencePointer(
            evidence_type=EvidenceType.CODE_FILE,
            source_path=rel_path,
            snippet=content[:200],
            line_start=start_line,
            line_end=end_line,
        )
        return {
            "content": content,
            "path": rel_path,
            "evidence_pointer": pointer.model_dump(),
        }


# ---------------------------------------------------------------------------
# repo.diff
# ---------------------------------------------------------------------------

class RepoDiffTool(_RepoToolBase):
    """Get the diff between two git refs.

    Returns changed files, summary, and evidence pointers for each
    modified region.
    """

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        ref1: str = params["ref1"]
        ref2: str = params.get("ref2", "HEAD")

        # TODO: implement via `git diff --stat` + `git diff` parsing
        #       For now, use subprocess placeholder.
        try:
            stat_result = subprocess.run(
                ["git", "diff", "--stat", ref1, ref2],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff_stat = stat_result.stdout.strip()
        except Exception as exc:
            return {"error": str(exc), "files_changed": [], "summary": ""}

        # TODO: parse diff_stat into structured file list
        #       Parse full diff to create per-hunk evidence pointers
        return {
            "ref1": ref1,
            "ref2": ref2,
            "files_changed": [],        # TODO: list of {path, additions, deletions}
            "summary": diff_stat,
            "additions": 0,
            "deletions": 0,
            "evidence_pointers": [],    # per-hunk evidence
        }


# ---------------------------------------------------------------------------
# repo.summarize
# ---------------------------------------------------------------------------

class RepoSummarizeTool(_RepoToolBase):
    """Generate a concise summary of a file or directory.

    Uses the LLM to produce a natural-language summary, attaching
    the source as an evidence pointer.
    """

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        rel_path: str = params["path"]
        max_tokens: int = params.get("max_tokens", 500)

        full_path = self.repo_path / rel_path
        if not full_path.exists():
            return {"error": f"Path not found: {rel_path}", "summary": ""}

        # TODO: if directory, list contents and summarise structure
        # TODO: if file, read content and call LLM with max_tokens
        # TODO: attach evidence pointer to source file/dir
        return {
            "path": rel_path,
            "summary": "",              # TODO: LLM-generated summary
            "evidence_pointer": None,   # TODO: EvidencePointer
        }
