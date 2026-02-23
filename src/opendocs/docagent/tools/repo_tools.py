"""Repository tools — clone, list, read, search, git history."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("docagent.tools.repo")


class RepoTools:
    """Low-level repository operations."""

    def __init__(self, sources_dir: Path) -> None:
        self._sources_dir = sources_dir
        self._repo_dir: Path | None = None

    @property
    def repo_dir(self) -> Path:
        if self._repo_dir is None:
            raise RuntimeError("No repository cloned yet. Call clone() first.")
        return self._repo_dir

    # ------------------------------------------------------------------
    # repo.clone
    # ------------------------------------------------------------------
    def clone(self, url: str, *, full_history: bool = False) -> Path:
        """Clone a GitHub repository into the session sources directory.

        Parameters
        ----------
        full_history
            If True, clone with full commit history (needed for git log).
            Otherwise uses ``--depth 1`` for speed.
        """
        # Normalise URL
        clean = url.rstrip("/")
        if clean.endswith(".git"):
            clean = clean[:-4]
        repo_name = clean.split("/")[-1]

        dest = self._sources_dir / repo_name
        if dest.exists():
            if full_history:
                # Unshallow an existing shallow clone
                self._repo_dir = dest
                self._unshallow()
            else:
                logger.info("Repo already cloned at %s", dest)
                self._repo_dir = dest
            return dest

        logger.info("Cloning %s → %s (full_history=%s)", url, dest, full_history)
        cmd = ["git", "clone"]
        if not full_history:
            cmd += ["--depth", "1"]
        cmd += [url, str(dest)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        except subprocess.CalledProcessError as exc:
            logger.error("Clone failed: %s", exc.stderr)
            raise RuntimeError(f"git clone failed: {exc.stderr}") from exc

        self._repo_dir = dest
        return dest

    def _unshallow(self) -> None:
        """Convert a shallow clone to a full clone."""
        shallow_file = self.repo_dir / ".git" / "shallow"
        if not shallow_file.exists():
            logger.debug("Already a full clone")
            return
        logger.info("Unshallowing clone for full git history...")
        try:
            subprocess.run(
                ["git", "fetch", "--unshallow"],
                cwd=str(self.repo_dir),
                check=True, capture_output=True, text=True, timeout=300,
            )
        except subprocess.CalledProcessError as exc:
            logger.warning("Unshallow failed: %s", exc.stderr)

    # ------------------------------------------------------------------
    # repo.git_log  — full commit history
    # ------------------------------------------------------------------
    def git_log(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        max_count: int = 500,
    ) -> list[dict[str, str]]:
        """Return git log as a list of dicts.

        Parameters
        ----------
        since / until
            ISO date strings, e.g. ``"2025-01-01"``.
        max_count
            Cap on number of commits returned.

        Returns
        -------
        List of ``{"hash", "short", "author", "date", "subject", "body"}``.
        """
        fmt = "%H%n%h%n%an%n%aI%n%s%n%b%n==END=="
        cmd = ["git", "log", f"--pretty=format:{fmt}", f"--max-count={max_count}"]
        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")

        raw = self._run_git(cmd)
        if not raw.strip():
            return []

        commits: list[dict[str, str]] = []
        for block in raw.split("==END=="):
            lines = block.strip().splitlines()
            if len(lines) < 5:
                continue
            commits.append({
                "hash": lines[0],
                "short": lines[1],
                "author": lines[2],
                "date": lines[3],
                "subject": lines[4],
                "body": "\n".join(lines[5:]).strip(),
            })
        logger.info("git_log: %d commits (since=%s, until=%s)", len(commits), since, until)
        return commits

    # ------------------------------------------------------------------
    # repo.git_merges  — only merge commits (≈ merged PRs)
    # ------------------------------------------------------------------
    def git_merges(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        max_count: int = 200,
    ) -> list[dict[str, str]]:
        """Return only merge commits (proxy for merged pull requests).

        Same return format as :meth:`git_log`.
        """
        fmt = "%H%n%h%n%an%n%aI%n%s%n%b%n==END=="
        cmd = [
            "git", "log", "--merges",
            f"--pretty=format:{fmt}",
            f"--max-count={max_count}",
        ]
        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")

        raw = self._run_git(cmd)
        if not raw.strip():
            return []

        merges: list[dict[str, str]] = []
        for block in raw.split("==END=="):
            lines = block.strip().splitlines()
            if len(lines) < 5:
                continue
            merges.append({
                "hash": lines[0],
                "short": lines[1],
                "author": lines[2],
                "date": lines[3],
                "subject": lines[4],
                "body": "\n".join(lines[5:]).strip(),
            })
        logger.info("git_merges: %d merge commits (since=%s, until=%s)",
                     len(merges), since, until)
        return merges

    # ------------------------------------------------------------------
    # repo.git_tags  — release tags
    # ------------------------------------------------------------------
    def git_tags(self, max_count: int = 50) -> list[dict[str, str]]:
        """Return annotated tags sorted by date (newest first).

        Returns list of ``{"tag", "date", "subject"}``.
        """
        cmd = [
            "git", "tag", "-l", "--sort=-creatordate",
            f"--format=%(refname:short)%09%(creatordate:iso-strict)%09%(subject)",
        ]
        raw = self._run_git(cmd)
        if not raw.strip():
            return []

        tags: list[dict[str, str]] = []
        for line in raw.strip().splitlines()[:max_count]:
            parts = line.split("\t", 2)
            tags.append({
                "tag": parts[0] if len(parts) > 0 else "",
                "date": parts[1] if len(parts) > 1 else "",
                "subject": parts[2] if len(parts) > 2 else "",
            })
        logger.info("git_tags: %d tags found", len(tags))
        return tags

    # ------------------------------------------------------------------
    # repo.git_shortstat  — diffstat summary
    # ------------------------------------------------------------------
    def git_shortstat(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, int]:
        """Return aggregate diff stats for the period.

        Returns ``{"commits": N, "files_changed": N, "insertions": N, "deletions": N}``.
        """
        cmd = ["git", "log", "--shortstat", "--oneline"]
        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")

        raw = self._run_git(cmd)
        total_files = total_ins = total_del = 0
        commit_count = 0
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Shortstat lines look like: "3 files changed, 10 insertions(+), 2 deletions(-)"
            m_files = re.search(r"(\d+) files? changed", line)
            m_ins = re.search(r"(\d+) insertions?", line)
            m_del = re.search(r"(\d+) deletions?", line)
            if m_files:
                total_files += int(m_files.group(1))
                if m_ins:
                    total_ins += int(m_ins.group(1))
                if m_del:
                    total_del += int(m_del.group(1))
            else:
                # It's a commit oneline
                commit_count += 1

        return {
            "commits": commit_count,
            "files_changed": total_files,
            "insertions": total_ins,
            "deletions": total_del,
        }

    # ------------------------------------------------------------------
    # repo.git_contributors — top contributors for period
    # ------------------------------------------------------------------
    def git_contributors(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        top_n: int = 15,
    ) -> list[dict[str, Any]]:
        """Return top contributors by commit count for the period."""
        cmd = ["git", "shortlog", "-sne", "--no-merges"]
        if since:
            cmd.append(f"--since={since}")
        if until:
            cmd.append(f"--until={until}")

        raw = self._run_git(cmd)
        contributors: list[dict[str, Any]] = []
        for line in raw.strip().splitlines()[:top_n]:
            m = re.match(r"\s*(\d+)\s+(.+)", line)
            if m:
                contributors.append({"commits": int(m.group(1)), "author": m.group(2).strip()})
        return contributors

    def _run_git(self, cmd: list[str]) -> str:
        """Run a git command in the repo directory and return stdout."""
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_dir),
                capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace",
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            logger.warning("git command failed: %s — %s", " ".join(cmd), exc.stderr)
            return ""
        except Exception as exc:
            logger.warning("git command error: %s — %s", " ".join(cmd), exc)
            return ""

    # ------------------------------------------------------------------
    # repo.list_files
    # ------------------------------------------------------------------
    def list_files(self, extensions: set[str] | None = None) -> list[str]:
        """Return all tracked files (relative paths).

        Parameters
        ----------
        extensions
            If provided, only return files with these extensions
            (e.g. ``{'.py', '.js'}``).
        """
        result: list[str] = []
        for p in sorted(self.repo_dir.rglob("*")):
            if not p.is_file():
                continue
            # Skip hidden / git dirs
            parts = p.relative_to(self.repo_dir).parts
            if any(part.startswith(".") for part in parts):
                continue
            # Skip common non-source dirs
            if any(part in ("node_modules", "__pycache__", ".git", "venv", ".venv") for part in parts):
                continue
            rel = str(p.relative_to(self.repo_dir)).replace("\\", "/")
            if extensions and p.suffix.lower() not in extensions:
                continue
            result.append(rel)
        return result

    # ------------------------------------------------------------------
    # repo.read_file
    # ------------------------------------------------------------------
    def read_file(self, path: str, max_bytes: int = 100_000) -> str:
        """Read a file's content from the cloned repo.

        Silently truncates at *max_bytes* to prevent memory blowout
        on very large files.
        """
        target = self.repo_dir / path
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = target.read_bytes()[:max_bytes].decode("utf-8", errors="replace")
        return text[:max_bytes]

    # ------------------------------------------------------------------
    # repo.search
    # ------------------------------------------------------------------
    def search(self, pattern: str, file_glob: str = "**/*") -> list[dict]:
        """Search files matching *pattern* (regex) and return matches.

        Returns list of ``{"file": ..., "line": ..., "match": ...}``.
        """
        regex = re.compile(pattern, re.IGNORECASE)
        hits: list[dict] = []
        for rel in self.list_files():
            fp = self.repo_dir / rel
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    hits.append({"file": rel, "line": i, "match": line.strip()})
                    if len(hits) >= 500:
                        return hits
        return hits
