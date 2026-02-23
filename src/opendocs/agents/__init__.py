"""Agentic documentation layer for opendocs.

This package implements the Planner → Executor → Critic architecture
that differentiates opendocs from static doc generators like Mintlify,
GitBook AI, DocuWriter, and repo-diagram tools.

Key design principles:
    1. **Evidence-grounded** — every claim links to a source via EvidencePointer.
    2. **Tool-orchestrated** — MCP tool contracts serve as the generation bus.
    3. **Diff-aware** — only regenerate artifacts impacted by code changes.
    4. **Privacy-safe** — agents receive RepoProfile + KG, never raw code by default.

Modules
-------
base        — Agent base classes, plan/result models, evidence pointers
orchestrator — Planner → Executor → Critic loop
planner     — Step-by-step plan generation from RepoProfile + KG
executor    — Dispatches tool calls to specialized sub-agents
critic      — Validates evidence coverage, flags hallucinations
evidence    — Evidence pointer model, coverage scoring
privacy     — Privacy toggle, strict mode, snippet filtering
diff/       — Diff-aware continuous sync pipeline
specialized/ — Domain-specific sub-agents (microservices, ML, infra, etc.)
tools/      — MCP tool contracts and adapters
"""

from .base import AgentBase, AgentPlan, AgentResult, PlanStep, ToolCall
from .evidence import EvidencePointer, EvidenceCoverage
from .orchestrator import AgentOrchestrator
from .privacy import PrivacyMode, PrivacyGuard

__all__ = [
    "AgentBase",
    "AgentPlan",
    "AgentResult",
    "PlanStep",
    "ToolCall",
    "EvidencePointer",
    "EvidenceCoverage",
    "AgentOrchestrator",
    "PrivacyMode",
    "PrivacyGuard",
]
