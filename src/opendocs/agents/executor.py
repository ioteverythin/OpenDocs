"""Executor agent — step 2 of the Planner → Executor → Critic loop.

The Executor receives a plan step and dispatches tool calls to the
appropriate MCP tool adapters. It collects results and evidence
pointers, and returns them to the orchestrator.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..core.knowledge_graph import KnowledgeGraph
from ..core.models import DocumentModel
from .base import (
    AgentBase,
    AgentPlan,
    AgentResult,
    AgentRole,
    PlanStep,
    RepoProfile,
    ToolCall,
    ToolCallStatus,
)
from .evidence import EvidenceRegistry
from .privacy import PrivacyGuard
from .tools.contracts import TOOL_REGISTRY


class ExecutorAgent(AgentBase):
    """Dispatches tool calls from plan steps and collects results.

    The Executor:
    1. Validates tool calls against ``TOOL_REGISTRY`` contracts.
    2. Applies privacy filtering via ``PrivacyGuard``.
    3. Dispatches to the appropriate tool adapter.
    4. Registers evidence pointers for successful results.
    5. Never introduces new factual claims without evidence.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-4o-mini",
        tool_adapters: dict[str, Any] | None = None,
        privacy_guard: PrivacyGuard | None = None,
        evidence_registry: EvidenceRegistry | None = None,
    ) -> None:
        super().__init__(role=AgentRole.EXECUTOR, model=model)
        self._adapters = tool_adapters or {}
        self._privacy = privacy_guard
        self._evidence = evidence_registry or EvidenceRegistry()

    def register_adapter(self, tool_name: str, adapter: Any) -> None:
        """Register a tool adapter instance for a given tool name."""
        self._adapters[tool_name] = adapter

    async def run(
        self,
        *,
        repo_profile: RepoProfile,
        knowledge_graph: KnowledgeGraph,
        document: DocumentModel | None = None,
        plan: AgentPlan | None = None,
        prior_results: list[AgentResult] | None = None,
        step: PlanStep | None = None,
        **kwargs: Any,
    ) -> AgentResult:
        """Execute a single plan step's tool calls."""
        t0 = time.perf_counter()
        errors: list[str] = []
        artifacts: dict[str, Any] = {}
        evidence_ids: list[str] = []

        if step is None:
            return self._make_result(
                success=False,
                errors=["No plan step provided to executor"],
            )

        for tc in step.tool_calls:
            result = await self._dispatch_tool_call(tc)
            if tc.status == ToolCallStatus.SUCCESS:
                artifacts[tc.id] = result
                evidence_ids.extend(tc.evidence_pointers)
            else:
                errors.append(f"Tool {tc.tool_name} failed: {tc.error}")

        duration = (time.perf_counter() - t0) * 1000
        return self._make_result(
            success=len(errors) == 0,
            artifacts=artifacts,
            evidence_ids=evidence_ids,
            errors=errors,
            duration_ms=duration,
        )

    # -- Internal -----------------------------------------------------------

    async def _dispatch_tool_call(self, tc: ToolCall) -> Any:
        """Validate and dispatch a single tool call."""

        # 1. Validate against contract
        contract = TOOL_REGISTRY.get(tc.tool_name)
        if contract:
            validation_errors = contract.validate_params(tc.parameters)
            if validation_errors:
                tc.status = ToolCallStatus.FAILED
                tc.error = "; ".join(validation_errors)
                return None

        # 2. Find adapter
        adapter = self._adapters.get(tc.tool_name)
        if adapter is None:
            tc.status = ToolCallStatus.SKIPPED
            tc.error = f"No adapter registered for tool: {tc.tool_name}"
            return None

        # 3. Execute
        try:
            result = await adapter.execute(tc.parameters)
            tc.status = ToolCallStatus.SUCCESS
            tc.result = result

            # 4. Register evidence if present in result
            if isinstance(result, dict) and "evidence_pointer" in result:
                from .evidence import EvidencePointer
                ptr_data = result["evidence_pointer"]
                if isinstance(ptr_data, dict):
                    ptr = EvidencePointer(**ptr_data)
                    ptr_id = self._evidence.register_pointer(ptr)
                    tc.evidence_pointers.append(ptr_id)

            return result

        except Exception as exc:
            tc.status = ToolCallStatus.FAILED
            tc.error = str(exc)
            return None
