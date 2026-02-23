"""DocAgent agent loop — the core orchestration engine.

Implements a modular 7-step pipeline:
    1. Interpret  — understand the user request
    2. Plan       — decide which documents to generate
    3. Gather     — crawl + index the repository
    4. Model      — build the RepoKnowledgeModel
    5. Draft      — generate document drafts via skills
    6. Review     — QA review + refinement loop
    7. Export     — render final outputs (Word, PDF, PPTX)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import WorkspaceConfig
from .models.document_model import DocumentType, DraftDocument, ExportFormat, ReviewFeedback
from .models.repo_model import GitHistory, RepoKnowledgeModel
from .tools.repo_tools import RepoTools
from .tools.analysis_tools import AnalysisTools
from .tools.document_tools import DocumentTools
from .tools.export_tools import ExportTools
from .skills.repo_crawler import RepoCrawlerSkill
from .skills.repo_indexer import RepoIndexerSkill
from .skills.model_builder import ModelBuilderSkill
from .skills.doc_prd import PRDSkill
from .skills.doc_proposal import ProposalSkill
from .skills.doc_sop import SOPSkill
from .skills.doc_report import ReportSkill
from .skills.doc_slides import SlidesSkill
from .skills.doc_changelog import ChangelogSkill
from .skills.doc_onboarding import OnboardingSkill
from .skills.doc_tech_debt import TechDebtSkill
from .skills.reviewer_qa import ReviewerQASkill
from .skills.renderer_export import RendererExportSkill
from .skills.diagram_gen import DiagramGenSkill

logger = logging.getLogger("docagent.loop")

# Map document type → skill class
_DOC_SKILLS: dict[DocumentType, type] = {
    DocumentType.PRD: PRDSkill,
    DocumentType.PROPOSAL: ProposalSkill,
    DocumentType.SOP: SOPSkill,
    DocumentType.REPORT: ReportSkill,
    DocumentType.SLIDES: SlidesSkill,
    DocumentType.CHANGELOG: ChangelogSkill,
    DocumentType.ONBOARDING: OnboardingSkill,
    DocumentType.TECH_DEBT: TechDebtSkill,
}


@dataclass
class AgentResult:
    """Final result of an agent run."""
    session_id: str = ""
    repo_url: str = ""
    repo_model_path: str = ""
    drafts: dict[str, str] = field(default_factory=dict)       # type → draft path
    outputs: dict[str, list[str]] = field(default_factory=dict) # type → [output paths]
    diagrams: dict[str, str] = field(default_factory=dict)      # type → diagram png path
    reviews: dict[str, dict] = field(default_factory=dict)      # type → review summary
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


class AgentLoop:
    """The main DocAgent orchestration loop."""

    def __init__(self, workspace: WorkspaceConfig | None = None) -> None:
        self._workspace = workspace or WorkspaceConfig()
        self._workspace.ensure_workspace()

    def run(
        self,
        url: str,
        *,
        doc_types: list[DocumentType] | None = None,
        export_formats: list[ExportFormat] | None = None,
        session_id: str | None = None,
        max_review_rounds: int = 2,
        use_llm: bool = False,
        api_key: str | None = None,
        llm_model: str = "gpt-4o-mini",
        base_url: str | None = None,
        theme_name: str = "corporate",
        since: str | None = None,
        until: str | None = None,
    ) -> AgentResult:
        """Execute the full agent loop.

        Parameters
        ----------
        url
            GitHub repository URL.
        doc_types
            Which documents to generate (default: all).
        export_formats
            Which output formats (default: Word + PPTX).
        session_id
            Optional session ID (auto-generated if omitted).
        max_review_rounds
            Maximum review-refine iterations per document.
        use_llm
            Whether to use LLM for intelligent generation.
        api_key
            OpenAI API key (falls back to OPENAI_API_KEY env var).
        llm_model
            LLM model name (default: gpt-4o-mini).
        base_url
            Custom OpenAI-compatible API base URL.
        theme_name
            Visual theme for output documents (default: corporate).
        since
            Start date for git history, e.g. '2025-01-01' or '3 months ago'.
        until
            End date for git history (default: today).
        """
        t0 = time.time()
        result = AgentResult(repo_url=url)

        # Build LLM config dict passed to skills
        llm_config: dict[str, Any] = {}
        if use_llm:
            if api_key:
                llm_config["api_key"] = api_key
            if base_url:
                llm_config["base_url"] = base_url
            llm_config["model"] = llm_model
            logger.info("LLM mode enabled: model=%s", llm_model)

        if doc_types is None:
            doc_types = list(DocumentType)
        if export_formats is None:
            export_formats = [ExportFormat.WORD, ExportFormat.PPTX]

        # ── Step 0: Create session ────────────────────────────────────
        sid = self._workspace.create_session(session_id)
        result.session_id = sid
        logger.info("Session %s started for %s", sid, url)

        # ── Initialise tools ──────────────────────────────────────────
        repo_tools = RepoTools(self._workspace.sources_dir(sid))
        analysis_tools = AnalysisTools(repo_tools)
        doc_tools = DocumentTools(self._workspace.drafts_dir(sid))
        export_tools = ExportTools(self._workspace.outputs_dir(sid), theme_name=theme_name)

        # ══════════════════════════════════════════════════════════════
        # STEP 1: Interpret
        # ══════════════════════════════════════════════════════════════
        logger.info("[Step 1/7] Interpret — parsing request")
        request = self._step_interpret(url, doc_types, export_formats)
        logger.info("  → Will generate: %s", [d.value for d in request["doc_types"]])

        # ══════════════════════════════════════════════════════════════
        # STEP 2: Plan
        # ══════════════════════════════════════════════════════════════
        logger.info("[Step 2/7] Plan — building execution plan")
        plan = self._step_plan(request)

        # ══════════════════════════════════════════════════════════════
        # STEP 3: Gather — crawl + index
        # ══════════════════════════════════════════════════════════════
        logger.info("[Step 3/7] Gather — cloning & indexing repository")
        # Full-depth clone when git history is requested
        needs_history = bool(since) and DocumentType.CHANGELOG in doc_types
        if needs_history:
            logger.info("  Full-depth clone for git history (--since=%s)", since)
        try:
            gather_result = self._step_gather(
                url, repo_tools, analysis_tools,
                full_history=needs_history,
            )
        except Exception as exc:
            result.errors.append(f"Gather failed: {exc}")
            result.elapsed_seconds = time.time() - t0
            return result

        # ══════════════════════════════════════════════════════════════
        # STEP 4: Model — build RepoKnowledgeModel
        # ══════════════════════════════════════════════════════════════
        logger.info("[Step 4/7] Model — building repository knowledge model")
        try:
            repo_model = self._step_model(
                url, gather_result,
                self._workspace.index_dir(sid),
                use_llm=use_llm,
                llm_config=llm_config,
            )
            result.repo_model_path = str(
                self._workspace.index_dir(sid) / "repo_model.json"
            )
        except Exception as exc:
            result.errors.append(f"Model building failed: {exc}")
            result.elapsed_seconds = time.time() - t0
            return result

        # ── Step 4.1: Collect git history (when --since is used) ──────
        if needs_history:
            logger.info("[Step 4.1] Collecting git history (since=%s, until=%s)", since, until)
            try:
                git_hist = self._step_git_history(repo_tools, since=since, until=until)
                repo_model.git_history = git_hist
                logger.info(
                    "  Git history: %d commits, %d merges, %d tags, %d contributors",
                    len(git_hist.commits), len(git_hist.merges),
                    len(git_hist.tags), len(git_hist.contributors),
                )
            except Exception as exc:
                logger.warning("Git history collection failed: %s", exc)
                result.errors.append(f"Git history warning: {exc}")

        # ══════════════════════════════════════════════════════════════
        # STEP 4.5: Diagrams — generate Mermaid diagrams → PNG
        # ══════════════════════════════════════════════════════════════
        logger.info("[Step 4.5] Diagrams — generating architecture diagrams")
        diagrams_dir = self._workspace.index_dir(sid) / "diagrams"
        diagram_paths = self._step_diagrams(
            repo_model, diagrams_dir,
            use_llm=use_llm, llm_config=llm_config,
        )
        for dtype, dpath in diagram_paths.items():
            if dpath:
                result.diagrams[dtype] = str(dpath)

        # ══════════════════════════════════════════════════════════════
        # STEP 5: Draft — generate documents
        # ══════════════════════════════════════════════════════════════
        logger.info("[Step 5/7] Draft — generating documents")
        drafts = self._step_draft(
            request["doc_types"], repo_model, doc_tools,
            use_llm=use_llm, llm_config=llm_config,
            diagram_paths=diagram_paths,
        )

        for draft in drafts:
            result.drafts[draft.doc_type.value] = str(
                self._workspace.drafts_dir(sid) / f"{draft.doc_type.value}_v{draft.version}.md"
            )

        # ══════════════════════════════════════════════════════════════
        # STEP 6: Review — QA + refine
        # ══════════════════════════════════════════════════════════════
        logger.info("[Step 6/7] Review — running QA checks")
        final_drafts = self._step_review(
            drafts, doc_tools, max_rounds=max_review_rounds,
            use_llm=use_llm, llm_config=llm_config,
        )
        for draft in final_drafts:
            result.drafts[draft.doc_type.value] = str(
                self._workspace.drafts_dir(sid) / f"{draft.doc_type.value}_v{draft.version}.md"
            )

        # ══════════════════════════════════════════════════════════════
        # STEP 7: Export — render outputs
        # ══════════════════════════════════════════════════════════════
        logger.info("[Step 7/7] Export — rendering output files")
        for draft in final_drafts:
            paths = self._step_export(
                draft, export_tools, request["export_formats"],
                diagram_paths=diagram_paths,
            )
            result.outputs[draft.doc_type.value] = [str(p) for p in paths]

        result.elapsed_seconds = time.time() - t0
        logger.info("Agent loop completed in %.1fs", result.elapsed_seconds)
        return result

    # ==================================================================
    # Step implementations
    # ==================================================================

    def _step_interpret(
        self,
        url: str,
        doc_types: list[DocumentType],
        export_formats: list[ExportFormat],
    ) -> dict[str, Any]:
        """Step 1: Interpret the user request into a structured plan input."""
        return {
            "url": url,
            "doc_types": doc_types,
            "export_formats": export_formats,
        }

    def _step_plan(self, request: dict[str, Any]) -> list[str]:
        """Step 2: Build an ordered execution plan."""
        plan: list[str] = [
            "crawl_repo",
            "index_files",
            "build_model",
        ]
        for dt in request["doc_types"]:
            plan.append(f"draft_{dt.value}")
        plan.append("review_all")
        for dt in request["doc_types"]:
            plan.append(f"export_{dt.value}")
        logger.info("  Plan: %s", plan)
        return plan

    def _step_gather(
        self,
        url: str,
        repo_tools: RepoTools,
        analysis_tools: AnalysisTools,
        *,
        full_history: bool = False,
    ) -> dict[str, Any]:
        """Step 3: Crawl and index the repository."""
        # Crawl
        crawler = RepoCrawlerSkill()
        crawl_result = crawler.run(
            repo_tools=repo_tools, url=url,
            full_history=full_history,
        )

        # Index
        indexer = RepoIndexerSkill()
        index_result = indexer.run(
            repo_tools=repo_tools,
            analysis_tools=analysis_tools,
            files=crawl_result["files"],
        )

        return {**crawl_result, **index_result}

    def _step_model(
        self,
        url: str,
        gather_result: dict[str, Any],
        index_dir: Path,
        *,
        use_llm: bool = False,
        llm_config: dict[str, Any] | None = None,
    ) -> RepoKnowledgeModel:
        """Step 4: Build the RepoKnowledgeModel."""
        builder = ModelBuilderSkill()
        return builder.run(
            url=url,
            files=gather_result["files"],
            readme=gather_result["readme"],
            key_files=gather_result["key_files"],
            tech_stack=gather_result["tech_stack"],
            commands=gather_result["commands"],
            index_dir=index_dir,
            use_llm=use_llm,
            llm_config=llm_config or {},
        )

    def _step_draft(
        self,
        doc_types: list[DocumentType],
        repo_model: RepoKnowledgeModel,
        doc_tools: DocumentTools,
        *,
        use_llm: bool = False,
        llm_config: dict[str, Any] | None = None,
        diagram_paths: dict[str, Path | None] | None = None,
    ) -> list[DraftDocument]:
        """Step 5: Generate drafts for all requested document types."""
        drafts: list[DraftDocument] = []
        for dt in doc_types:
            skill_cls = _DOC_SKILLS.get(dt)
            if skill_cls is None:
                logger.warning("No skill for document type: %s", dt.value)
                continue
            skill = skill_cls()
            draft = skill.run(
                repo_model=repo_model,
                use_llm=use_llm,
                llm_config=llm_config or {},
            )
            # Inject diagram references into the draft Markdown
            if diagram_paths:
                draft = self._inject_diagrams(draft, diagram_paths)
            doc_tools.save_draft(draft)
            drafts.append(draft)
            logger.info("  Drafted: %s (%d chars)", dt.value, len(draft.content))
        return drafts

    def _step_review(
        self,
        drafts: list[DraftDocument],
        doc_tools: DocumentTools,
        max_rounds: int = 2,
        *,
        use_llm: bool = False,
        llm_config: dict[str, Any] | None = None,
    ) -> list[DraftDocument]:
        """Step 6: Review and refine each draft."""
        reviewer = ReviewerQASkill()
        final: list[DraftDocument] = []

        for draft in drafts:
            current = draft
            for round_num in range(1, max_rounds + 1):
                feedback: ReviewFeedback = reviewer.run(
                    draft=current, doc_tools=doc_tools,
                    use_llm=use_llm, llm_config=llm_config or {},
                )
                if feedback.passed:
                    logger.info("  %s passed review (round %d)", current.doc_type.value, round_num)
                    break
                logger.info(
                    "  %s needs refinement (round %d): %d issues, %d missing",
                    current.doc_type.value, round_num,
                    len(feedback.issues), len(feedback.missing_sections),
                )
                current = doc_tools.refine(
                    current, feedback,
                    use_llm=use_llm, llm_config=llm_config or {},
                )
                doc_tools.save_draft(current)
            final.append(current)

        return final

    def _step_export(
        self,
        draft: DraftDocument,
        export_tools: ExportTools,
        formats: list[ExportFormat],
        *,
        diagram_paths: dict[str, Path | None] | None = None,
    ) -> list[Path]:
        """Step 7: Export a draft to all requested formats."""
        renderer = RendererExportSkill()
        return renderer.run(
            draft=draft,
            export_tools=export_tools,
            formats=formats,
            diagram_paths=diagram_paths or {},
        )

    # ------------------------------------------------------------------
    # Git history support
    # ------------------------------------------------------------------

    def _step_git_history(
        self,
        repo_tools: RepoTools,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> GitHistory:
        """Step 4.1: Collect git commit history for a date range."""
        commits = repo_tools.git_log(since=since, until=until, max_count=500)
        merges = repo_tools.git_merges(since=since, until=until, max_count=200)
        tags = repo_tools.git_tags(max_count=50)
        stats = repo_tools.git_shortstat(since=since, until=until)
        contributors = repo_tools.git_contributors(since=since, until=until)

        from .models.repo_model import GitCommit

        return GitHistory(
            since=since or "",
            until=until or "",
            commits=[GitCommit(**c) for c in commits],
            merges=[GitCommit(**c) for c in merges],
            tags=tags,
            stats=stats,
            contributors=contributors,
        )

    # ------------------------------------------------------------------
    # Diagram support
    # ------------------------------------------------------------------

    def _step_diagrams(
        self,
        repo_model: RepoKnowledgeModel,
        diagrams_dir: Path,
        *,
        use_llm: bool = False,
        llm_config: dict[str, Any] | None = None,
    ) -> dict[str, Path | None]:
        """Step 4.5: Generate Mermaid diagrams and render to PNG."""
        gen = DiagramGenSkill()
        return gen.run(
            repo_model=repo_model,
            diagrams_dir=diagrams_dir,
            use_llm=use_llm,
            llm_config=llm_config or {},
        )

    def _inject_diagrams(
        self,
        draft: DraftDocument,
        diagram_paths: dict[str, Path | None],
    ) -> DraftDocument:
        """Inject diagram image references into the draft Markdown."""
        # Only inject for doc types that benefit from diagrams
        if draft.doc_type not in (
            DocumentType.PRD, DocumentType.PROPOSAL,
            DocumentType.REPORT, DocumentType.SLIDES,
        ):
            return draft

        diagram_md = "\n\n---\n\n## Architecture Diagrams\n\n"
        has_diagrams = False

        labels = {
            "architecture": "System Architecture",
            "data_flow": "Data Flow",
            "component": "Component Overview",
        }

        for dtype, label in labels.items():
            path = diagram_paths.get(dtype)
            if path and Path(path).exists():
                abs_path = str(Path(path).resolve()).replace("\\", "/")
                diagram_md += f"### {label}\n\n"
                diagram_md += f"![{label}]({abs_path})\n\n"
                has_diagrams = True

        if has_diagrams:
            # Insert before the last --- or at the end
            content = draft.content.rstrip() + diagram_md
            return DraftDocument(
                doc_type=draft.doc_type,
                title=draft.title,
                content=content,
                version=draft.version,
                sections=draft.sections + ["Architecture Diagrams"],
            )

        return draft
