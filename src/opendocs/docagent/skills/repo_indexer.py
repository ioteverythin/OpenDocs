"""repo.indexer — read and index key files from the repository."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseSkill
from ..tools.repo_tools import RepoTools
from ..tools.analysis_tools import AnalysisTools


class RepoIndexerSkill(BaseSkill):
    """Index the most important files in the repository."""

    name = "repo.indexer"

    # Files we always try to read
    _PRIORITY_FILES = [
        "README.md", "readme.md", "Readme.md",
        "package.json", "pyproject.toml", "setup.py", "setup.cfg",
        "Cargo.toml", "go.mod", "pom.xml",
        "Makefile", "Dockerfile",
        "docker-compose.yml", "docker-compose.yaml",
        ".github/workflows/ci.yml", ".github/workflows/main.yml",
        "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md",
    ]

    def run(
        self,
        *,
        repo_tools: RepoTools,
        analysis_tools: AnalysisTools,
        files: list[str],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Read key files and build an index.

        Returns
        -------
        dict with ``readme``, ``key_files``, ``tech_stack``, ``commands``
        """
        self.logger.info("Indexing %d files", len(files))

        # 1. Read priority files
        key_files: dict[str, str] = {}
        for pf in self._PRIORITY_FILES:
            if pf in files:
                try:
                    key_files[pf] = repo_tools.read_file(pf)
                except Exception:
                    pass

        # 2. Read top source files (by importance heuristic)
        source_exts = {".py", ".js", ".ts", ".go", ".rs", ".java"}
        source_files = [f for f in files if Path(f).suffix.lower() in source_exts]

        # Prioritise entry points and main files
        priority_names = {"main", "app", "index", "server", "cli", "__init__",
                          "manage", "wsgi", "asgi", "setup"}
        source_files.sort(key=lambda f: (
            0 if Path(f).stem.lower() in priority_names else 1,
            len(f.split("/")),  # prefer shallower files
        ))

        for sf in source_files[:20]:  # Read top 20 source files
            if sf not in key_files:
                try:
                    key_files[sf] = analysis_tools.summarize_file(sf)
                except Exception:
                    pass

        # 3. Detect tech stack
        tech_stack = analysis_tools.detect_stack()

        # 4. Extract commands
        commands = analysis_tools.extract_commands()

        # 5. Get README
        readme = ""
        for name in ("README.md", "readme.md", "Readme.md"):
            if name in key_files:
                readme = key_files[name]
                break

        self.logger.info(
            "Indexed: %d key files, %d techs, %d commands",
            len(key_files), len(tech_stack),
            sum(len(v) for v in commands.values()),
        )

        return {
            "readme": readme,
            "key_files": key_files,
            "tech_stack": tech_stack,
            "commands": commands,
        }
