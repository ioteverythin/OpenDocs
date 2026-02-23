"""reviewer.qa — Quality assurance review of draft documents."""

from __future__ import annotations

from typing import Any

from .base import BaseSkill
from ..models.document_model import DraftDocument, ReviewFeedback
from ..tools.document_tools import DocumentTools


class ReviewerQASkill(BaseSkill):
    """Review a draft and produce structured feedback."""

    name = "reviewer.qa"

    def run(
        self,
        *,
        draft: DraftDocument,
        doc_tools: DocumentTools,
        **kwargs: Any,
    ) -> ReviewFeedback:
        """Run quality checks and return feedback."""
        use_llm: bool = kwargs.get("use_llm", False)
        llm_config: dict[str, Any] = kwargs.get("llm_config") or {}

        if use_llm:
            try:
                return self._run_llm(draft, doc_tools, llm_config)
            except Exception as exc:
                self.logger.warning("LLM review failed (%s), falling back", exc)

        self.logger.info("Reviewing %s v%d", draft.doc_type.value, draft.version)
        feedback = doc_tools.review(draft)

        self.logger.info(
            "Review result: passed=%s, clarity=%.2f, issues=%d, missing=%d",
            feedback.passed, feedback.clarity_score,
            len(feedback.issues), len(feedback.missing_sections),
        )
        return feedback

    # ------------------------------------------------------------------
    # LLM-enhanced review
    # ------------------------------------------------------------------

    def _run_llm(
        self,
        draft: DraftDocument,
        doc_tools: DocumentTools,
        llm_config: dict[str, Any],
    ) -> ReviewFeedback:
        from ..llm_client import chat_json

        # First run deterministic checks
        base_feedback = doc_tools.review(draft)

        system = (
            "You are a technical editor reviewing a document for quality. "
            "Analyse the document and return a JSON object with:\n"
            "- issues (array of strings): specific problems found\n"
            "- missing_sections (array of strings): sections that should be added\n"
            "- clarity_score (float 0-1): overall clarity rating\n"
            "- suggestions (array of strings): improvement suggestions\n"
            "- passed (boolean): true if document is publication-ready\n\n"
            "Be thorough but fair. Focus on: completeness, accuracy, "
            "clarity, structure, and actionability."
        )

        user = (
            f"Document Type: {draft.doc_type.value}\n"
            f"Title: {draft.title}\n"
            f"Version: {draft.version}\n"
            f"Sections: {', '.join(draft.sections)}\n\n"
            f"=== CONTENT ===\n{draft.content[:8000]}\n"
        )

        data = chat_json(system, user, **llm_config)

        # Merge LLM feedback with deterministic
        all_issues = list(set(
            base_feedback.issues + data.get("issues", [])
        ))
        all_missing = list(set(
            base_feedback.missing_sections + data.get("missing_sections", [])
        ))
        clarity = data.get("clarity_score", base_feedback.clarity_score)
        suggestions = data.get("suggestions", base_feedback.suggestions)
        passed = data.get("passed", False) and base_feedback.passed

        feedback = ReviewFeedback(
            issues=all_issues,
            missing_sections=all_missing,
            clarity_score=float(clarity) if isinstance(clarity, (int, float)) else 0.7,
            suggestions=suggestions,
            passed=passed,
        )

        self.logger.info(
            "LLM review: passed=%s, clarity=%.2f, issues=%d",
            feedback.passed, feedback.clarity_score, len(feedback.issues),
        )
        return feedback
