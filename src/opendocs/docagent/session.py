"""Session management for DocAgent."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

from .config import WorkspaceConfig
from .agent_loop import AgentResult

logger = logging.getLogger("docagent.session")


class SessionManager:
    """Manage DocAgent sessions — create, list, inspect."""

    def __init__(self, workspace: WorkspaceConfig | None = None) -> None:
        self._ws = workspace or WorkspaceConfig()

    def list_sessions(self) -> list[dict]:
        """List all sessions with basic info."""
        sessions_dir = self._ws.sessions_dir
        if not sessions_dir.exists():
            return []

        result: list[dict] = []
        for d in sorted(sessions_dir.iterdir()):
            if not d.is_dir():
                continue
            info: dict = {"id": d.name}
            result_file = d / "result.json"
            if result_file.exists():
                try:
                    data = json.loads(result_file.read_text())
                    info["repo_url"] = data.get("repo_url", "")
                    info["elapsed"] = data.get("elapsed_seconds", 0)
                except Exception:
                    pass

            outputs_dir = d / "outputs"
            if outputs_dir.exists():
                info["output_count"] = len(list(outputs_dir.iterdir()))
            result.append(info)

        return result

    def save_result(self, result: AgentResult) -> Path:
        """Persist an AgentResult to the session directory."""
        session_dir = self._ws.session_dir(result.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / "result.json"
        path.write_text(
            json.dumps(asdict(result), indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Saved session result → %s", path)
        return path

    def get_session_outputs(self, session_id: str) -> list[Path]:
        """Return all output file paths for a session."""
        outputs_dir = self._ws.outputs_dir(session_id)
        if not outputs_dir.exists():
            return []
        return sorted(outputs_dir.iterdir())
