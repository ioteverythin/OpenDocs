"""Configuration and workspace path management for DocAgent."""

from __future__ import annotations

import uuid
from pathlib import Path
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Default workspace root
# ---------------------------------------------------------------------------
DEFAULT_ROOT = Path.home() / ".docagent" / "workspace"


@dataclass
class WorkspaceConfig:
    """Manages the DocAgent workspace layout."""

    root: Path = field(default_factory=lambda: DEFAULT_ROOT)

    # Top-level directories
    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def templates_dir(self) -> Path:
        return self.root / "templates"

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    # ------------------------------------------------------------------
    # Session-specific paths
    # ------------------------------------------------------------------
    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def sources_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "sources"

    def index_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "index"

    def drafts_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "drafts"

    def outputs_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "outputs"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def create_session(self, session_id: str | None = None) -> str:
        """Create a new session directory tree and return its ID."""
        sid = session_id or uuid.uuid4().hex[:12]
        for d in (
            self.session_dir(sid),
            self.sources_dir(sid),
            self.index_dir(sid),
            self.drafts_dir(sid),
            self.outputs_dir(sid),
        ):
            d.mkdir(parents=True, exist_ok=True)
        return sid

    def ensure_workspace(self) -> None:
        """Create the top-level workspace directories."""
        for d in (self.skills_dir, self.templates_dir, self.memory_dir, self.sessions_dir):
            d.mkdir(parents=True, exist_ok=True)
