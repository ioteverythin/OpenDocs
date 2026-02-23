"""Base agent interfaces and shared data models.

Every agent in the system inherits from ``AgentBase`` and communicates
via the standardised ``AgentPlan`` / ``AgentResult`` / ``ToolCall`` models.
This ensures uniform logging, evidence tracking, and error handling
across the Planner → Executor → Critic pipeline.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..core.knowledge_graph import KnowledgeGraph
from ..core.models import DocumentModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    """Well-known roles in the Planner → Executor → Critic loop."""
    PLANNER = "planner"
    EXECUTOR = "executor"
    CRITIC = "critic"
    DIFF = "diff"
    IMPACT = "impact"
    REGEN = "regen"
    RELEASE_NOTES = "release_notes"
    # Specialized
    MICROSERVICES = "microservices"
    EVENT_DRIVEN = "event_driven"
    ML = "ml"
    DATA_ENGINEERING = "data_engineering"
    INFRA = "infra"


class ToolCallStatus(str, Enum):
    """Outcome of a single tool invocation."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Tool call model
# ---------------------------------------------------------------------------

class ToolCall(BaseModel):
    """A single MCP tool invocation requested by an agent.

    Agents produce ToolCall objects; the Executor dispatches them
    to the appropriate tool adapter and fills in the result.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    tool_name: str                    # e.g. "diagram.render", "repo.search"
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_output_type: str = ""    # e.g. "svg", "json", "markdown"
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    evidence_pointers: list[str] = Field(default_factory=list)  # IDs


# ---------------------------------------------------------------------------
# Plan models
# ---------------------------------------------------------------------------

class PlanStep(BaseModel):
    """One step in an agent's execution plan."""

    step_number: int
    description: str
    agent_role: AgentRole
    tool_calls: list[ToolCall] = Field(default_factory=list)
    depends_on: list[int] = Field(default_factory=list)  # step_numbers
    expected_output: str = ""
    completed: bool = False


class AgentPlan(BaseModel):
    """A structured, JSON-serialisable execution plan.

    The Planner agent emits this; the Orchestrator walks it
    step-by-step, dispatching each to the Executor.
    """

    plan_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    goal: str = ""
    steps: list[PlanStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.completed)

    @property
    def progress(self) -> float:
        return self.completed_steps / self.total_steps if self.steps else 0.0


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class AgentResult(BaseModel):
    """The output of a single agent execution."""

    agent_role: AgentRole
    success: bool = True
    artifacts: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Repo profile — lightweight repo summary fed to agents
# ---------------------------------------------------------------------------

class RepoSignal(BaseModel):
    """A detected signal about the repo (e.g. 'has docker-compose')."""
    signal_type: str          # e.g. "docker-compose", "terraform", "ml-training"
    file_path: str = ""       # evidence source
    confidence: float = 1.0
    details: dict[str, Any] = Field(default_factory=dict)


class RepoProfile(BaseModel):
    """A privacy-safe summary of a repository, consumed by agents.

    Contains only structural metadata and detected signals —
    never raw source code (unless privacy mode permits).
    """

    repo_name: str = ""
    repo_url: str = ""
    description: str = ""
    primary_language: str = ""
    languages: list[str] = Field(default_factory=list)
    file_tree: list[str] = Field(default_factory=list)     # path list
    signals: list[RepoSignal] = Field(default_factory=list)
    readme_summary: str = ""
    license: str = ""
    topics: list[str] = Field(default_factory=list)

    def has_signal(self, signal_type: str) -> bool:
        """Check if a specific signal was detected."""
        return any(s.signal_type == signal_type for s in self.signals)


# ---------------------------------------------------------------------------
# Abstract base agent
# ---------------------------------------------------------------------------

class AgentBase(ABC):
    """Base class for all agents in the agentic pipeline.

    Subclasses must implement ``run()`` which receives context and
    returns an ``AgentResult``.

    Parameters
    ----------
    role : AgentRole
        The well-known role of this agent.
    model : str
        The LLM model identifier to use (e.g. "gpt-4o-mini").
    """

    def __init__(self, role: AgentRole, model: str = "gpt-4o-mini") -> None:
        self.role = role
        self.model = model

    @abstractmethod
    async def run(
        self,
        *,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        document: DocumentModel | None = None,
        plan: AgentPlan | None = None,
        prior_results: list[AgentResult] | None = None,
        **kwargs: Any,
    ) -> AgentResult:
        """Execute this agent's task.

        Parameters
        ----------
        repo_profile
            Privacy-safe repo summary.
        knowledge_graph
            Semantic KG extracted from the README.
        document
            Parsed document model (optional — some agents don't need it).
        plan
            The current execution plan (available to Executor/Critic).
        prior_results
            Results from previously-executed agents in the pipeline.

        Returns
        -------
        AgentResult
            The outcome, including artifacts and evidence IDs.
        """
        ...

    def _make_result(self, **kwargs: Any) -> AgentResult:
        """Convenience factory for building an AgentResult with this agent's role."""
        return AgentResult(agent_role=self.role, **kwargs)
