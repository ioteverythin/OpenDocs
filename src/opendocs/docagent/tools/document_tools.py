"""Document tools — generate, review, refine drafts."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models.document_model import DraftDocument, DocumentType, ReviewFeedback

logger = logging.getLogger("docagent.tools.document")


class DocumentTools:
    """Mid-level document manipulation tools used by the agent loop."""

    def __init__(self, drafts_dir: Path) -> None:
        self._drafts_dir = drafts_dir

    # ------------------------------------------------------------------
    # doc.generate  (called by skills → save draft)
    # ------------------------------------------------------------------
    def save_draft(self, draft: DraftDocument) -> Path:
        """Persist a draft to the session drafts directory."""
        fname = f"{draft.doc_type.value}_v{draft.version}.md"
        path = self._drafts_dir / fname
        path.write_text(draft.content, encoding="utf-8")
        logger.info("Saved draft: %s", path)
        return path

    def load_draft(self, doc_type: DocumentType, version: int = 1) -> DraftDocument | None:
        """Load a previously saved draft."""
        fname = f"{doc_type.value}_v{version}.md"
        path = self._drafts_dir / fname
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        return DraftDocument(
            doc_type=doc_type,
            title=f"{doc_type.value.upper()} v{version}",
            content=content,
            version=version,
        )

    # ------------------------------------------------------------------
    # doc.review  (deterministic quality check)
    # ------------------------------------------------------------------
    def review(self, draft: DraftDocument) -> ReviewFeedback:
        """Run deterministic quality checks on a draft."""
        issues: list[str] = []
        missing: list[str] = []

        lines = draft.content.splitlines()
        headings = [l.strip() for l in lines if l.strip().startswith("#")]

        # Check minimum length
        word_count = len(draft.content.split())
        if word_count < 100:
            issues.append(f"Document is very short ({word_count} words)")

        # Check for expected sections per document type
        expected = _EXPECTED_SECTIONS.get(draft.doc_type, [])
        heading_text_lower = " ".join(headings).lower()
        for section in expected:
            if section.lower() not in heading_text_lower:
                missing.append(section)

        # Check for empty sections
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                # Look ahead — if next non-blank line is another heading, section is empty
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and lines[j].strip().startswith("#"):
                    issues.append(f"Empty section: {line.strip()}")

        # Clarity score (simple heuristic)
        clarity = 1.0
        if word_count < 100:
            clarity -= 0.3
        if len(missing) > 2:
            clarity -= 0.2 * min(len(missing), 3)
        if len(issues) > 3:
            clarity -= 0.1 * min(len(issues), 3)
        clarity = max(0.0, min(1.0, clarity))

        passed = clarity >= 0.6 and len(missing) <= 1

        suggestions: list[str] = []
        if missing:
            suggestions.append(f"Add missing sections: {', '.join(missing)}")
        if word_count < 200:
            suggestions.append("Expand content — document seems too brief")

        return ReviewFeedback(
            issues=issues,
            missing_sections=missing,
            clarity_score=clarity,
            suggestions=suggestions,
            passed=passed,
        )

    # ------------------------------------------------------------------
    # doc.refine  (apply feedback to produce v2)
    # ------------------------------------------------------------------
    def refine(
        self,
        draft: DraftDocument,
        feedback: ReviewFeedback,
        *,
        use_llm: bool = False,
        llm_config: dict | None = None,
    ) -> DraftDocument:
        """Produce an improved draft by addressing missing sections.

        When *use_llm* is True the LLM is asked to write real content for
        each missing section.  Falls back to a clean note when the LLM is
        unavailable.
        """
        content = draft.content

        if feedback.missing_sections:
            generated = self._generate_missing_sections(
                draft, feedback.missing_sections,
                use_llm=use_llm, llm_config=llm_config or {},
            )
            if generated:
                content += "\n\n---\n\n"
                content += generated

        return DraftDocument(
            doc_type=draft.doc_type,
            title=draft.title,
            content=content,
            version=draft.version + 1,
            sections=draft.sections + feedback.missing_sections,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_missing_sections(
        draft: DraftDocument,
        missing: list[str],
        *,
        use_llm: bool = False,
        llm_config: dict | None = None,
    ) -> str:
        """Generate Markdown for missing sections via LLM or a short note."""
        if not missing:
            return ""

        section_list = ", ".join(missing)

        if use_llm:
            try:
                from ..llm_client import chat_text as chat  # type: ignore[import-untyped]

                system = (
                    "You are a technical writer expanding an existing document. "
                    "The reviewer identified missing sections that need to be added. "
                    "Write ONLY the new sections in Markdown (## headings). "
                    "Use concrete, specific content — NEVER output TODO or "
                    "placeholder text. Match the tone and depth of the existing "
                    "document. Be concise but thorough."
                )
                user = (
                    f"Document type: {draft.doc_type.value}\n"
                    f"Title: {draft.title}\n\n"
                    f"=== EXISTING CONTENT (for context) ===\n"
                    f"{draft.content[:4000]}\n\n"
                    f"=== SECTIONS TO ADD ===\n{section_list}\n\n"
                    "Write each missing section now."
                )
                result = chat(system, user, **(llm_config or {}))
                if result and len(result.strip()) > 20:
                    logger.info("LLM generated %d chars for %d missing sections",
                                len(result), len(missing))
                    return result.strip()
            except Exception as exc:
                logger.warning("LLM refinement failed (%s), using short notes", exc)

        # Fallback: short informational notes (NOT empty TODO stubs)
        parts: list[str] = []
        for section in missing:
            parts.append(f"## {section}\n")
            parts.append(
                f"*This section was identified as a potential addition by the "
                f"automated review process. Run with `--mode llm` to have it "
                f"generated automatically.*\n"
            )
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Expected sections per document type
# ---------------------------------------------------------------------------
_EXPECTED_SECTIONS: dict[DocumentType, list[str]] = {
    DocumentType.PRD: [
        "Overview", "Problem", "Users", "Features",
        "User Stories", "Acceptance Criteria",
    ],
    DocumentType.PROPOSAL: [
        "Value Proposition", "Solution Overview", "Architecture",
        "Timeline", "Effort Estimate",
    ],
    DocumentType.SOP: [
        "Setup", "Run Instructions", "Deployment",
        "Monitoring", "Troubleshooting",
    ],
    DocumentType.REPORT: [
        "Overview", "Architecture", "Modules", "Risks",
    ],
    DocumentType.SLIDES: [
        "Slide",
    ],
    DocumentType.CHANGELOG: [
        "Highlights", "Features", "Architecture",
        "Dependencies", "Known Issues",
    ],
    DocumentType.ONBOARDING: [
        "Welcome", "Architecture", "Getting Started",
        "Repository Structure", "Key Files", "Development Workflow",
    ],
    DocumentType.TECH_DEBT: [
        "Executive Summary", "Health Scorecard", "Testing",
        "Architecture Debt", "Remediation", "Recommendations",
    ],
}
