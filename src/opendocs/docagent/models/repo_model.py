"""Repository Knowledge Model — the structured understanding of a repo."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class APIEndpoint(BaseModel):
    """A single API endpoint discovered in the repository."""
    method: str = ""
    path: str = ""
    description: str = ""


class GitCommit(BaseModel):
    """A single git commit entry."""
    hash: str = ""
    short: str = ""
    author: str = ""
    date: str = ""
    subject: str = ""
    body: str = ""


class GitHistory(BaseModel):
    """Git history extracted for a date range."""
    since: str = ""
    until: str = ""
    commits: list[GitCommit] = Field(default_factory=list)
    merges: list[GitCommit] = Field(default_factory=list)
    tags: list[dict[str, str]] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)  # commits, files_changed, insertions, deletions
    contributors: list[dict[str, Any]] = Field(default_factory=list)


class RepoKnowledgeModel(BaseModel):
    """Structured knowledge extracted from a GitHub repository.

    Stored at ``sessions/<id>/index/repo_model.json``.
    """

    project_name: str = ""
    description: str = ""
    problem_statement: str = ""
    features: list[str] = Field(default_factory=list)
    target_users: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    architecture_components: list[str] = Field(default_factory=list)
    data_flow: list[str] = Field(default_factory=list)
    setup_instructions: list[str] = Field(default_factory=list)
    api_endpoints: list[APIEndpoint] = Field(default_factory=list)
    dependencies: dict[str, str] = Field(default_factory=dict)
    deployment_info: list[str] = Field(default_factory=list)
    ci_cd: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    roadmap: list[str] = Field(default_factory=list)

    # Git history (populated when --since/--until is used)
    git_history: GitHistory | None = None

    # Additional metadata
    repo_url: str = ""
    default_branch: str = "main"
    languages: dict[str, float] = Field(default_factory=dict)
    file_tree: list[str] = Field(default_factory=list)
    readme_content: str = ""
    key_files: dict[str, str] = Field(default_factory=dict)  # path → content summary
