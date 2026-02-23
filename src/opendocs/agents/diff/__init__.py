"""Diff-aware pipeline agents.

Agents that detect code changes (git diffs) and selectively regenerate
only the impacted documentation artifacts. This keeps docs in sync
without wasteful full rebuilds.

Sub-agents:
- **DiffAgent**: git diff → impacted file list + change summary.
- **ImpactAgent**: file diffs → KG node/edge deltas.
- **RegenerationAgent**: re-generate only impacted artifacts.
- **ReleaseNotesAgent**: produce changelog and slide updates.
"""

from .diff_agent import DiffAgent
from .impact_agent import ImpactAgent
from .regen_agent import RegenerationAgent
from .release_notes_agent import ReleaseNotesAgent

__all__ = [
    "DiffAgent",
    "ImpactAgent",
    "RegenerationAgent",
    "ReleaseNotesAgent",
]
