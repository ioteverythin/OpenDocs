"""repo.crawler — clone and discover repository files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseSkill
from ..tools.repo_tools import RepoTools


class RepoCrawlerSkill(BaseSkill):
    """Clone a GitHub repo and enumerate its files."""

    name = "repo.crawler"

    def run(self, *, repo_tools: RepoTools, url: str, **kwargs: Any) -> dict[str, Any]:
        """Clone the repo and return file listing.

        Returns
        -------
        dict with keys: ``repo_dir``, ``files``, ``file_count``
        """
        self.logger.info("Crawling %s", url)
        full_history = kwargs.get("full_history", False)
        repo_dir: Path = repo_tools.clone(url, full_history=full_history)

        all_files = repo_tools.list_files()
        self.logger.info("Found %d files", len(all_files))

        # Categorise files
        source_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
                       ".java", ".rb", ".cs", ".cpp", ".c", ".swift", ".kt"}
        config_files = {"package.json", "pyproject.toml", "setup.py", "Cargo.toml",
                        "go.mod", "pom.xml", "Makefile", "Dockerfile",
                        "docker-compose.yml", "docker-compose.yaml",
                        ".env.example", "tsconfig.json"}
        doc_exts = {".md", ".rst", ".txt"}

        categories = {
            "source": [f for f in all_files if Path(f).suffix.lower() in source_exts],
            "config": [f for f in all_files if Path(f).name in config_files],
            "docs": [f for f in all_files if Path(f).suffix.lower() in doc_exts],
            "other": [],
        }
        categorised = set(categories["source"] + categories["config"] + categories["docs"])
        categories["other"] = [f for f in all_files if f not in categorised]

        return {
            "repo_dir": str(repo_dir),
            "files": all_files,
            "file_count": len(all_files),
            "categories": categories,
        }
