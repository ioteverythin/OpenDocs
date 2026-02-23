"""Tests for the agents layer — base models, evidence, privacy, and pipeline.

These tests validate:
1. Pydantic models (ToolCall, PlanStep, AgentPlan, AgentResult, RepoProfile)
2. Evidence registry (pointers, claims, coverage scoring)
3. Privacy guard (STRICT / STANDARD / PERMISSIVE filtering)
4. Planner (signal detection, plan construction)
5. Executor (tool dispatch, error handling)
6. Critic (coverage evaluation, approval/rejection)
7. Orchestrator (full loop)
8. Diff pipeline (DiffAgent, ImpactAgent, RegenerationAgent, ReleaseNotesAgent)
9. Specialized agents (Microservices, EventDriven, ML, DataEngineering, Infra)
"""

from __future__ import annotations

import asyncio
import pytest

from opendocs.core.knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relation,
    RelationType,
)
from opendocs.core.models import DocumentModel

# -- Base models --

from opendocs.agents.base import (
    AgentPlan,
    AgentResult,
    AgentRole,
    PlanStep,
    RepoProfile,
    RepoSignal,
    ToolCall,
    ToolCallStatus,
)

# -- Evidence --

from opendocs.agents.evidence import (
    Claim,
    EvidenceCoverage,
    EvidencePointer,
    EvidenceRegistry,
    EvidenceType,
)

# -- Privacy --

from opendocs.agents.privacy import PrivacyGuard, PrivacyMode

# -- Core agents --

from opendocs.agents.planner import PlannerAgent
from opendocs.agents.executor import ExecutorAgent
from opendocs.agents.critic import CriticAgent, CriticVerdict
from opendocs.agents.orchestrator import AgentOrchestrator, OrchestrationResult

# -- Diff pipeline --

from opendocs.agents.diff import DiffAgent, ImpactAgent, RegenerationAgent, ReleaseNotesAgent
from opendocs.agents.diff.diff_agent import DiffSummary, FileDiff
from opendocs.agents.diff.impact_agent import DeltaKind, EntityDelta, ImpactReport

# -- Specialized --

from opendocs.agents.specialized import (
    MicroservicesAgent,
    EventDrivenAgent,
    MLAgent,
    DataEngineeringAgent,
    InfraAgent,
)

# -- Tool contracts --

from opendocs.agents.tools.contracts import TOOL_REGISTRY, ToolContract


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def sample_kg() -> KnowledgeGraph:
    """A small knowledge graph for testing."""
    return KnowledgeGraph(
        entities=[
            Entity(id="proj-1", name="MyApp", entity_type=EntityType.PROJECT,
                   properties={"source_file": "README.md"}),
            Entity(id="comp-1", name="API Server", entity_type=EntityType.COMPONENT,
                   properties={"source_file": "src/api/main.py"}),
            Entity(id="tech-1", name="FastAPI", entity_type=EntityType.TECHNOLOGY),
            Entity(id="tech-2", name="PostgreSQL", entity_type=EntityType.TECHNOLOGY),
        ],
        relations=[
            Relation(source_id="proj-1", target_id="comp-1", relation_type=RelationType.DEPENDS_ON),
            Relation(source_id="comp-1", target_id="tech-1", relation_type=RelationType.USES),
            Relation(source_id="comp-1", target_id="tech-2", relation_type=RelationType.USES),
        ],
        summary="MyApp is a FastAPI application with PostgreSQL.",
    )


@pytest.fixture
def sample_profile() -> RepoProfile:
    """A sample repo profile for testing."""
    return RepoProfile(
        repo_name="my-org/my-app",
        repo_url="https://github.com/my-org/my-app",
        description="A sample FastAPI app",
        primary_language="Python",
        languages=["Python", "SQL"],
        file_tree=[
            "README.md",
            "src/api/main.py",
            "src/api/models.py",
            "docker-compose.yml",
            "Dockerfile",
            "k8s/deployment.yaml",
            "terraform/main.tf",
        ],
        signals=[
            RepoSignal(signal_type="docker-compose", file_path="docker-compose.yml"),
            RepoSignal(signal_type="kubernetes", file_path="k8s/deployment.yaml"),
            RepoSignal(signal_type="terraform", file_path="terraform/main.tf"),
        ],
        readme_summary="A FastAPI CRUD app.",
        license="MIT",
    )


@pytest.fixture
def microservices_profile() -> RepoProfile:
    return RepoProfile(
        repo_name="org/microservices",
        file_tree=["docker-compose.yml", "svc-a/Dockerfile", "svc-b/Dockerfile"],
        signals=[RepoSignal(signal_type="docker-compose")],
    )


@pytest.fixture
def event_driven_profile() -> RepoProfile:
    return RepoProfile(
        repo_name="org/events",
        signals=[
            RepoSignal(signal_type="kafka"),
            RepoSignal(signal_type="sqs"),
        ],
    )


@pytest.fixture
def ml_profile() -> RepoProfile:
    return RepoProfile(
        repo_name="org/ml-project",
        signals=[
            RepoSignal(signal_type="pytorch"),
            RepoSignal(signal_type="rag"),
        ],
    )


@pytest.fixture
def data_eng_profile() -> RepoProfile:
    return RepoProfile(
        repo_name="org/data-pipeline",
        file_tree=["dags/etl_dag.py", "dbt_project.yml"],
        signals=[
            RepoSignal(signal_type="airflow"),
            RepoSignal(signal_type="dbt"),
        ],
    )


@pytest.fixture
def infra_profile() -> RepoProfile:
    return RepoProfile(
        repo_name="org/infra",
        file_tree=["main.tf", "modules/vpc/vpc.tf", "charts/app/Chart.yaml"],
        signals=[
            RepoSignal(signal_type="terraform"),
            RepoSignal(signal_type="helm"),
        ],
    )


# ===================================================================
# 1. Base models
# ===================================================================

class TestBaseModels:
    """Test Pydantic data models instantiate and serialize correctly."""

    def test_tool_call_defaults(self):
        tc = ToolCall(tool_name="repo.search", parameters={"query": "test"})
        assert tc.tool_name == "repo.search"
        assert tc.status == ToolCallStatus.PENDING
        assert tc.result is None
        assert len(tc.id) == 12

    def test_plan_step_serialization(self):
        step = PlanStep(
            step_number=1,
            description="Search repo",
            agent_role=AgentRole.EXECUTOR,
            tool_calls=[
                ToolCall(tool_name="repo.search", parameters={"query": "x"})
            ],
        )
        d = step.model_dump()
        assert d["step_number"] == 1
        assert len(d["tool_calls"]) == 1
        assert d["completed"] is False

    def test_agent_plan_progress(self):
        plan = AgentPlan(
            goal="Test",
            steps=[
                PlanStep(step_number=1, description="a", agent_role=AgentRole.EXECUTOR, completed=True),
                PlanStep(step_number=2, description="b", agent_role=AgentRole.EXECUTOR, completed=False),
                PlanStep(step_number=3, description="c", agent_role=AgentRole.CRITIC, completed=False),
            ],
        )
        assert plan.total_steps == 3
        assert plan.completed_steps == 1
        assert plan.progress == pytest.approx(1 / 3, abs=0.01)

    def test_agent_result_fields(self):
        result = AgentResult(
            agent_role=AgentRole.PLANNER,
            success=True,
            artifacts={"plan": {}},
            duration_ms=42.5,
        )
        assert result.agent_role == AgentRole.PLANNER
        assert result.success is True
        assert result.duration_ms == 42.5

    def test_repo_profile_has_signal(self, sample_profile: RepoProfile):
        assert sample_profile.has_signal("docker-compose")
        assert sample_profile.has_signal("kubernetes")
        assert not sample_profile.has_signal("kafka")

    def test_repo_signal_defaults(self):
        sig = RepoSignal(signal_type="test")
        assert sig.confidence == 1.0
        assert sig.file_path == ""


# ===================================================================
# 2. Evidence registry
# ===================================================================

class TestEvidenceRegistry:
    """Test evidence pointer registration and coverage scoring."""

    def test_register_and_retrieve_pointer(self):
        reg = EvidenceRegistry()
        ptr = EvidencePointer(
            evidence_type=EvidenceType.README_SECTION,
            source_path="README.md",
            section="Installation",
            snippet="pip install myapp",
        )
        ptr_id = reg.register_pointer(ptr)
        assert reg.get_pointer(ptr_id) is ptr
        assert len(reg.all_pointers()) == 1

    def test_register_claim_with_evidence(self):
        reg = EvidenceRegistry()
        ptr = EvidencePointer(evidence_type=EvidenceType.CODE_FILE, source_path="main.py")
        pid = reg.register_pointer(ptr)

        claim = Claim(text="The API uses FastAPI", artifact_id="doc-1", evidence_ids=[pid])
        reg.register_claim(claim)
        assert claim.is_assumption is False

    def test_register_claim_without_evidence(self):
        reg = EvidenceRegistry()
        claim = Claim(text="Performance is excellent", artifact_id="doc-1")
        reg.register_claim(claim)
        assert claim.is_assumption is True

    def test_coverage_computation(self):
        reg = EvidenceRegistry()
        ptr = EvidencePointer(evidence_type=EvidenceType.README_SECTION, source_path="README.md")
        pid = reg.register_pointer(ptr)

        # 2 backed, 1 assumption
        reg.register_claim(Claim(text="Claim A", artifact_id="art-1", evidence_ids=[pid]))
        reg.register_claim(Claim(text="Claim B", artifact_id="art-1", evidence_ids=[pid]))
        reg.register_claim(Claim(text="Claim C", artifact_id="art-1"))  # no evidence

        cov = reg.compute_coverage("art-1")
        assert cov.total_claims == 3
        assert cov.backed_claims == 2
        assert cov.assumption_count == 1
        assert cov.coverage_pct == pytest.approx(66.67, abs=0.1)
        assert cov.is_trustworthy is False  # < 80%

    def test_coverage_empty_artifact(self):
        reg = EvidenceRegistry()
        cov = reg.compute_coverage("nonexistent")
        assert cov.total_claims == 0
        assert cov.coverage_pct == 100.0  # vacuously true

    def test_compute_all_coverage(self):
        reg = EvidenceRegistry()
        ptr = EvidencePointer(evidence_type=EvidenceType.CODE_FILE, source_path="x.py")
        pid = reg.register_pointer(ptr)

        reg.register_claim(Claim(text="A", artifact_id="doc-1", evidence_ids=[pid]))
        reg.register_claim(Claim(text="B", artifact_id="doc-2"))

        coverages = reg.compute_all_coverage()
        assert len(coverages) == 2
        ids = [c.artifact_id for c in coverages]
        assert "doc-1" in ids
        assert "doc-2" in ids

    def test_evidence_coverage_summary(self):
        cov = EvidenceCoverage(
            artifact_id="test",
            total_claims=10,
            backed_claims=8,
            assumption_count=2,
            confidence_mean=0.85,
            confidence_min=0.4,
        )
        s = cov.summary()
        assert s["coverage"] == "80.0%"
        assert s["trustworthy"] is True


# ===================================================================
# 3. Privacy guard
# ===================================================================

class TestPrivacyGuard:
    """Test privacy filtering in all three modes."""

    def test_strict_strips_file_tree(self, sample_profile: RepoProfile):
        guard = PrivacyGuard(mode=PrivacyMode.STRICT)
        safe = guard.sanitise_profile(sample_profile)
        # STRICT: only top-level dirs
        for path in safe.file_tree:
            assert path.endswith("/")
        assert safe.repo_name == sample_profile.repo_name

    def test_standard_preserves_file_tree(self, sample_profile: RepoProfile):
        guard = PrivacyGuard(mode=PrivacyMode.STANDARD)
        safe = guard.sanitise_profile(sample_profile)
        assert safe.file_tree == sample_profile.file_tree

    def test_permissive_returns_unchanged(self, sample_profile: RepoProfile):
        guard = PrivacyGuard(mode=PrivacyMode.PERMISSIVE)
        safe = guard.sanitise_profile(sample_profile)
        assert safe is sample_profile  # identity — no copy

    def test_strict_redacts_evidence_snippet(self):
        guard = PrivacyGuard(mode=PrivacyMode.STRICT)
        ptr = EvidencePointer(
            evidence_type=EvidenceType.CODE_SNIPPET,
            source_path="main.py",
            snippet="def hello():\n    return 'world'",
        )
        safe = guard.sanitise_evidence(ptr)
        assert safe.snippet == "[code redacted]"

    def test_standard_truncates_long_snippet(self):
        guard = PrivacyGuard(mode=PrivacyMode.STANDARD)
        long_snippet = "\n".join([f"line {i}" for i in range(50)])
        ptr = EvidencePointer(
            evidence_type=EvidenceType.CODE_SNIPPET,
            source_path="main.py",
            snippet=long_snippet,
        )
        safe = guard.sanitise_evidence(ptr)
        lines = safe.snippet.splitlines()
        assert len(lines) == 21  # 20 lines + "[truncated]"
        assert lines[-1] == "[truncated]"

    def test_strict_sanitise_context(self):
        guard = PrivacyGuard(mode=PrivacyMode.STRICT)
        ctx = {"title": "Hello", "code": "print('hi')", "nested": {"source_code": "x = 1"}}
        safe = guard.sanitise_context(ctx)
        assert safe["title"] == "Hello"
        assert safe["code"] == "[redacted]"
        assert safe["nested"]["source_code"] == "[redacted]"

    def test_allows_code_modes(self):
        assert PrivacyGuard(mode=PrivacyMode.STRICT).allows_code() is False
        assert PrivacyGuard(mode=PrivacyMode.STANDARD).allows_code() is True
        assert PrivacyGuard(mode=PrivacyMode.PERMISSIVE).allows_code() is True

    def test_allows_full_files_modes(self):
        assert PrivacyGuard(mode=PrivacyMode.STRICT).allows_full_files() is False
        assert PrivacyGuard(mode=PrivacyMode.STANDARD).allows_full_files() is False
        assert PrivacyGuard(mode=PrivacyMode.PERMISSIVE).allows_full_files() is True


# ===================================================================
# 4. Tool contracts
# ===================================================================

class TestToolContracts:
    """Test MCP tool contract registry and parameter validation."""

    def test_registry_has_12_tools(self):
        assert len(TOOL_REGISTRY) == 12

    def test_expected_tools_registered(self):
        expected = {
            "repo.search", "repo.read", "repo.diff", "repo.summarize",
            "diagram.render", "chart.generate",
            "figma.create_frame", "figma.add_nodes",
            "image.generate", "docx.refine", "pptx.refine",
            "confluence.publish",
        }
        assert set(TOOL_REGISTRY.keys()) == expected

    def test_valid_params_pass(self):
        contract = TOOL_REGISTRY["repo.search"]
        errors = contract.validate_params({"query": "test", "max_results": 10})
        assert errors == []

    def test_missing_required_param(self):
        contract = TOOL_REGISTRY["repo.search"]
        errors = contract.validate_params({})  # 'query' is required
        assert len(errors) == 1
        assert "query" in errors[0]

    def test_diagram_render_type_enum(self):
        contract = TOOL_REGISTRY["diagram.render"]
        errors = contract.validate_params({"type": "mermaid", "spec": "graph LR; A-->B"})
        assert errors == []
        errors_bad = contract.validate_params({"type": "invalid_type", "spec": "x"})
        assert len(errors_bad) == 1


# ===================================================================
# 5. Planner agent
# ===================================================================

class TestPlannerAgent:
    """Test planner signal detection and plan construction."""

    def test_detect_sub_agents(self, sample_profile: RepoProfile):
        planner = PlannerAgent()
        agents = planner._detect_sub_agents(sample_profile)
        roles = {a.value for a in agents}
        assert "microservices" in roles   # docker-compose + kubernetes
        assert "infra" in roles           # terraform

    def test_detect_no_agents_for_plain_repo(self):
        planner = PlannerAgent()
        plain = RepoProfile(repo_name="plain", signals=[])
        agents = planner._detect_sub_agents(plain)
        assert agents == []

    @pytest.mark.asyncio
    async def test_planner_run_produces_plan(self, sample_profile, sample_kg):
        planner = PlannerAgent()
        result = await planner.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is True
        assert "plan" in result.artifacts
        plan_data = result.artifacts["plan"]
        assert plan_data["goal"]
        assert len(plan_data["steps"]) >= 3  # search + diagram + sub-agents + refine + critic

    @pytest.mark.asyncio
    async def test_planner_activated_agents_in_metadata(self, sample_profile, sample_kg):
        planner = PlannerAgent()
        result = await planner.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        activated = result.metadata.get("activated_agents", [])
        assert "microservices" in activated
        assert "infra" in activated


# ===================================================================
# 6. Executor agent
# ===================================================================

class TestExecutorAgent:
    """Test executor tool dispatch and error handling."""

    @pytest.mark.asyncio
    async def test_executor_no_step_returns_failure(self, sample_profile, sample_kg):
        executor = ExecutorAgent()
        result = await executor.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is False
        assert "No plan step" in result.errors[0]

    @pytest.mark.asyncio
    async def test_executor_skips_unregistered_tool(self, sample_profile, sample_kg):
        executor = ExecutorAgent()
        step = PlanStep(
            step_number=1,
            description="Test",
            agent_role=AgentRole.EXECUTOR,
            tool_calls=[ToolCall(tool_name="nonexistent.tool", parameters={})],
        )
        result = await executor.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
            step=step,
        )
        # Tool was skipped (no adapter), so there should be an error
        assert result.success is False or step.tool_calls[0].status == ToolCallStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_executor_with_mock_adapter(self, sample_profile, sample_kg):
        """Test that a registered adapter gets called."""
        class MockAdapter:
            async def execute(self, params):
                return {"results": ["file1.py", "file2.py"]}

        executor = ExecutorAgent()
        executor.register_adapter("repo.search", MockAdapter())

        step = PlanStep(
            step_number=1,
            description="Search",
            agent_role=AgentRole.EXECUTOR,
            tool_calls=[ToolCall(tool_name="repo.search", parameters={"query": "test"})],
        )
        result = await executor.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
            step=step,
        )
        assert result.success is True
        # The mock result should be in artifacts
        assert any("file1.py" in str(v) for v in result.artifacts.values())

    @pytest.mark.asyncio
    async def test_executor_handles_adapter_exception(self, sample_profile, sample_kg):
        """Adapter that raises an exception should be caught."""
        class FailingAdapter:
            async def execute(self, params):
                raise RuntimeError("Connection failed")

        executor = ExecutorAgent()
        executor.register_adapter("repo.search", FailingAdapter())

        step = PlanStep(
            step_number=1,
            description="Search",
            agent_role=AgentRole.EXECUTOR,
            tool_calls=[ToolCall(tool_name="repo.search", parameters={"query": "x"})],
        )
        result = await executor.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
            step=step,
        )
        assert result.success is False
        assert "Connection failed" in result.errors[0]


# ===================================================================
# 7. Critic agent
# ===================================================================

class TestCriticAgent:
    """Test critic evidence validation and approval logic."""

    @pytest.mark.asyncio
    async def test_critic_approves_good_coverage(self, sample_profile, sample_kg):
        registry = EvidenceRegistry()
        ptr = EvidencePointer(evidence_type=EvidenceType.README_SECTION, source_path="README.md")
        pid = registry.register_pointer(ptr)

        # All claims backed
        for i in range(5):
            registry.register_claim(
                Claim(text=f"Claim {i}", artifact_id="doc", evidence_ids=[pid])
            )

        critic = CriticAgent(evidence_registry=registry, min_coverage_pct=80.0)
        result = await critic.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is True
        assert result.artifacts["verdict"]["approved"] is True

    @pytest.mark.asyncio
    async def test_critic_rejects_low_coverage(self, sample_profile, sample_kg):
        registry = EvidenceRegistry()
        # 10 claims, all assumptions (no evidence)
        for i in range(10):
            registry.register_claim(Claim(text=f"Claim {i}", artifact_id="doc"))

        critic = CriticAgent(evidence_registry=registry, min_coverage_pct=80.0, max_assumptions=5)
        result = await critic.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is False
        verdict = result.artifacts["verdict"]
        assert verdict["approved"] is False
        assert verdict["replan_reason"]

    @pytest.mark.asyncio
    async def test_critic_with_no_claims_approves(self, sample_profile, sample_kg):
        """No claims = vacuous coverage = approved."""
        critic = CriticAgent(evidence_registry=EvidenceRegistry())
        result = await critic.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is True

    def test_critic_verdict_to_dict(self):
        verdict = CriticVerdict(
            approved=True,
            coverage_scores=[],
            flagged_claims=[],
            replan_reason="",
        )
        d = verdict.to_dict()
        assert d["approved"] is True
        assert d["replan_reason"] == ""


# ===================================================================
# 8. Diff pipeline
# ===================================================================

class TestDiffPipeline:
    """Test DiffAgent, ImpactAgent, RegenerationAgent, ReleaseNotesAgent."""

    @pytest.mark.asyncio
    async def test_diff_agent_returns_summary(self, sample_profile, sample_kg):
        agent = DiffAgent()
        result = await agent.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
            base_ref="HEAD~1",
            head_ref="HEAD",
        )
        assert result.success is True
        assert "diff_summary" in result.artifacts
        ds = result.artifacts["diff_summary"]
        assert "base_ref" in ds
        assert "changed_paths" in ds

    @pytest.mark.asyncio
    async def test_impact_agent_with_matching_entities(self, sample_profile, sample_kg):
        """ImpactAgent should detect deltas for entities with matching source files."""
        diff_summary = DiffSummary(
            base_ref="abc",
            head_ref="def",
            total_files=1,
            total_additions=10,
            total_deletions=2,
            file_diffs=[
                FileDiff(path="src/api/main.py", status="modified", additions=10, deletions=2),
            ],
        )
        agent = ImpactAgent()
        result = await agent.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
            diff_summary=diff_summary,
        )
        assert result.success is True
        report = result.artifacts["impact_report"]
        assert report["total_deltas"] > 0
        # comp-1 has source_file="src/api/main.py" which was modified
        entity_ids = [d["id"] for d in report["entity_deltas"]]
        assert "comp-1" in entity_ids

    @pytest.mark.asyncio
    async def test_impact_agent_no_diff_fails(self, sample_profile, sample_kg):
        agent = ImpactAgent()
        result = await agent.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_regen_agent_no_impact_succeeds(self, sample_profile, sample_kg):
        """With zero deltas, nothing to regenerate."""
        empty_impact = ImpactReport()
        agent = RegenerationAgent()
        result = await agent.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
            impact_report=empty_impact,
        )
        assert result.success is True
        assert result.artifacts["regenerated"] == []

    @pytest.mark.asyncio
    async def test_regen_agent_with_impact(self, sample_profile, sample_kg):
        impact = ImpactReport(
            entity_deltas=[EntityDelta(entity_id="comp-1", kind=DeltaKind.UPDATE)],
            impacted_output_formats=["WORD", "PPTX"],
        )
        agent = RegenerationAgent()
        result = await agent.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
            impact_report=impact,
        )
        assert result.success is True
        assert "WORD" in result.artifacts["regenerated"]

    @pytest.mark.asyncio
    async def test_release_notes_agent(self, sample_profile, sample_kg):
        diff_summary = DiffSummary(
            base_ref="v1.0",
            head_ref="v1.1",
            total_files=2,
            file_diffs=[
                FileDiff(path="src/new_module.py", status="added", additions=100),
                FileDiff(path="src/api/main.py", status="modified", additions=5, deletions=3),
            ],
        )
        agent = ReleaseNotesAgent()
        result = await agent.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
            diff_summary=diff_summary,
            version="1.1.0",
        )
        assert result.success is True
        md = result.artifacts["release_notes_md"]
        assert "1.1.0" in md
        assert "Added" in md or "added" in md.lower()
        assert "Changed" in md or "changed" in md.lower()

    def test_diff_summary_changed_paths(self):
        ds = DiffSummary(
            base_ref="a", head_ref="b",
            file_diffs=[
                FileDiff(path="x.py", status="modified"),
                FileDiff(path="y.py", status="added"),
            ],
        )
        assert ds.changed_paths == ["x.py", "y.py"]

    def test_impact_report_total_deltas(self):
        report = ImpactReport(
            entity_deltas=[EntityDelta(entity_id="e1", kind=DeltaKind.ADD)],
            relation_deltas=[],
        )
        assert report.total_deltas == 1


# ===================================================================
# 9. Specialized agents
# ===================================================================

class TestMicroservicesAgent:
    @pytest.mark.asyncio
    async def test_discovers_services(self, microservices_profile, sample_kg):
        agent = MicroservicesAgent()
        result = await agent.run(
            repo_profile=microservices_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is True
        services = result.artifacts["discovered_services"]
        assert len(services) >= 1  # docker-compose at minimum
        assert "service_diagram_mermaid" in result.artifacts
        assert "architecture_section_md" in result.artifacts

    @pytest.mark.asyncio
    async def test_mermaid_diagram_is_valid(self, microservices_profile, sample_kg):
        agent = MicroservicesAgent()
        result = await agent.run(
            repo_profile=microservices_profile,
            knowledge_graph=sample_kg,
        )
        mermaid = result.artifacts["service_diagram_mermaid"]
        assert mermaid.startswith("graph LR")


class TestEventDrivenAgent:
    @pytest.mark.asyncio
    async def test_discovers_event_components(self, event_driven_profile, sample_kg):
        agent = EventDrivenAgent()
        result = await agent.run(
            repo_profile=event_driven_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is True
        comps = result.artifacts["event_components"]
        techs = {c["tech"] for c in comps}
        assert "kafka" in techs
        assert "sqs" in techs
        assert "event_flow_mermaid" in result.artifacts


class TestMLAgent:
    @pytest.mark.asyncio
    async def test_discovers_ml_components(self, ml_profile, sample_kg):
        agent = MLAgent()
        result = await agent.run(
            repo_profile=ml_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is True
        comps = result.artifacts["ml_components"]
        techs = {c["tech"] for c in comps}
        assert "pytorch" in techs
        assert "rag" in techs
        assert "model_card_md" in result.artifacts
        assert "ml_pipeline_mermaid" in result.artifacts


class TestDataEngineeringAgent:
    @pytest.mark.asyncio
    async def test_discovers_data_components(self, data_eng_profile, sample_kg):
        agent = DataEngineeringAgent()
        result = await agent.run(
            repo_profile=data_eng_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is True
        comps = result.artifacts["data_components"]
        techs = {c["tech"] for c in comps}
        assert "airflow" in techs
        assert "dbt" in techs
        assert "data_lineage_mermaid" in result.artifacts


class TestInfraAgent:
    @pytest.mark.asyncio
    async def test_discovers_infra_resources(self, infra_profile, sample_kg):
        agent = InfraAgent()
        result = await agent.run(
            repo_profile=infra_profile,
            knowledge_graph=sample_kg,
        )
        assert result.success is True
        resources = result.artifacts["infra_resources"]
        techs = {r["tech"] for r in resources}
        assert "terraform" in techs
        assert "helm" in techs
        assert "infra_topology_mermaid" in result.artifacts
        assert "infrastructure_md" in result.artifacts


# ===================================================================
# 10. Orchestrator (integration-level)
# ===================================================================

class TestOrchestrator:
    """Integration tests for the full Planner → Executor → Critic loop."""

    @pytest.mark.asyncio
    async def test_orchestrator_runs_full_loop(self, sample_profile, sample_kg):
        orch = AgentOrchestrator(
            model="gpt-4o-mini",
            privacy_mode=PrivacyMode.STANDARD,
            max_retries=0,  # don't retry for test speed
        )
        result = await orch.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        assert isinstance(result, OrchestrationResult)
        assert result.iterations >= 1
        # Plan should exist
        assert result.plan is not None
        assert result.plan.total_steps >= 1

    @pytest.mark.asyncio
    async def test_orchestrator_summary(self, sample_profile, sample_kg):
        orch = AgentOrchestrator(max_retries=0)
        result = await orch.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        summary = result.summary()
        assert "approved" in summary
        assert "iterations" in summary
        assert "duration_ms" in summary

    @pytest.mark.asyncio
    async def test_orchestrator_respects_privacy_strict(self, sample_profile, sample_kg):
        orch = AgentOrchestrator(
            privacy_mode=PrivacyMode.STRICT,
            max_retries=0,
        )
        # Should not crash in strict mode
        result = await orch.run(
            repo_profile=sample_profile,
            knowledge_graph=sample_kg,
        )
        assert isinstance(result, OrchestrationResult)
