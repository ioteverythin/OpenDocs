"""Generate Jira-compatible tickets (JSON) from a DocumentModel.

Produces a JSON file containing an Epic and multiple Stories with
acceptance criteria, extracted from the README's structure and content.
The output is importable by Jira, Linear, and most project trackers.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..core.knowledge_graph import EntityType, KnowledgeGraph
from ..core.models import (
    CodeBlock,
    ContentBlock,
    DocumentModel,
    GenerationResult,
    ListBlock,
    OutputFormat,
    ParagraphBlock,
    Section,
    TableBlock,
)
from .base import BaseGenerator

if TYPE_CHECKING:
    from .diagram_extractor import ImageCache


class JiraGenerator(BaseGenerator):
    """DocumentModel → Jira-compatible JSON tickets."""

    format = OutputFormat.JIRA

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        filename = self._safe_filename(doc.metadata.repo_name or "project", "json")
        filename = f"jira_{filename}"
        output_path = self._ensure_dir(output_dir) / filename

        try:
            tickets = self._build_tickets(doc)
            output_path.write_text(
                json.dumps(tickets, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return GenerationResult(
                format=OutputFormat.JIRA,
                output_path=output_path,
            )
        except Exception as exc:
            return GenerationResult(
                format=OutputFormat.JIRA,
                output_path=output_path,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal – ticket building
    # ------------------------------------------------------------------

    def _build_tickets(self, doc: DocumentModel) -> dict[str, Any]:
        """Build the full Jira export structure."""
        name = doc.metadata.repo_name or "Project"
        now = datetime.now().isoformat()

        # Epic
        epic: dict[str, Any] = {
            "type": "Epic",
            "key": f"{self._project_key(name)}-1",
            "summary": f"Implement {name}",
            "description": self._build_epic_description(doc),
            "labels": ["opendocs-generated", "auto-import"],
            "created": now,
            "priority": "High",
        }

        # Stories – one per top-level section that has meaningful content
        stories: list[dict[str, Any]] = []
        story_idx = 2  # epic takes key -1

        for section in doc.sections:
            section_stories = self._section_to_stories(
                section, name, story_idx,
            )
            stories.extend(section_stories)
            story_idx += len(section_stories)

        # Extra stories from KG features
        if self.kg:
            feature_stories = self._features_to_stories(name, story_idx)
            stories.extend(feature_stories)
            story_idx += len(feature_stories)

        # Extra stories from KG prerequisites
        if self.kg:
            prereq_stories = self._prerequisites_to_stories(name, story_idx)
            stories.extend(prereq_stories)

        return {
            "project": name,
            "generated_by": "opendocs",
            "generated_at": now,
            "source": doc.metadata.repo_url or doc.metadata.source_path or "",
            "epic": epic,
            "stories": stories,
            "total_tickets": 1 + len(stories),
        }

    # ------------------------------------------------------------------
    # Epic description
    # ------------------------------------------------------------------

    def _build_epic_description(self, doc: DocumentModel) -> str:
        """Build a rich epic description."""
        parts: list[str] = []
        if self.kg and self.kg.executive_summary:
            parts.append(self._strip_html(self.kg.executive_summary))
            parts.append("")

        paras = [
            self._strip_html(b.text) for b in doc.all_blocks
            if isinstance(b, ParagraphBlock) and len(b.text) > 30
        ]
        if paras:
            parts.append(paras[0])

        if doc.metadata.repo_url:
            parts.append(f"\nSource: {doc.metadata.repo_url}")

        return "\n".join(parts) if parts else f"Epic for {doc.metadata.repo_name}"

    # ------------------------------------------------------------------
    # Section → Stories
    # ------------------------------------------------------------------

    def _section_to_stories(
        self,
        section: Section,
        project_name: str,
        start_idx: int,
    ) -> list[dict[str, Any]]:
        """Convert a section (and its subsections) into Jira stories."""
        stories: list[dict[str, Any]] = []
        key_prefix = self._project_key(project_name)

        if not section.title:
            return stories

        # Skip purely structural / empty sections
        if not section.blocks and not section.subsections:
            return stories

        # Classify the section to determine ticket type
        classification = self._classify_section(section.title)

        # Build acceptance criteria from section blocks
        criteria = self._extract_acceptance_criteria(section)

        if criteria or section.blocks:
            story: dict[str, Any] = {
                "type": "Story",
                "key": f"{key_prefix}-{start_idx}",
                "summary": self._section_to_summary(section.title, classification),
                "description": self._section_to_description(section),
                "acceptance_criteria": criteria,
                "labels": [
                    "opendocs-generated",
                    classification,
                ],
                "priority": self._classify_priority(section.title),
                "story_points": self._estimate_points(section),
            }
            stories.append(story)

        # Recurse into subsections
        for sub in section.subsections:
            sub_stories = self._section_to_stories(
                sub, project_name, start_idx + len(stories),
            )
            stories.extend(sub_stories)

        return stories

    # ------------------------------------------------------------------
    # Feature & prerequisite stories from KG
    # ------------------------------------------------------------------

    def _features_to_stories(
        self, project_name: str, start_idx: int,
    ) -> list[dict[str, Any]]:
        """Create stories from KG feature entities."""
        if not self.kg:
            return []

        stories: list[dict[str, Any]] = []
        key_prefix = self._project_key(project_name)
        features = self.kg.entities_of_type(EntityType.FEATURE)

        for i, feat in enumerate(features[:20]):  # cap at 20
            stories.append({
                "type": "Story",
                "key": f"{key_prefix}-{start_idx + i}",
                "summary": f"Implement feature: {feat.name}",
                "description": (
                    f"Implement the '{feat.name}' feature as described in the "
                    f"project documentation.\n\n"
                    f"Source section: {feat.source_section or 'N/A'}\n"
                    f"Confidence: {feat.confidence:.0%}"
                ),
                "acceptance_criteria": [
                    f"'{feat.name}' feature is fully implemented",
                    "Feature is covered by unit tests",
                    "Documentation is updated",
                ],
                "labels": ["opendocs-generated", "feature"],
                "priority": "Medium",
                "story_points": 3,
            })

        return stories

    def _prerequisites_to_stories(
        self, project_name: str, start_idx: int,
    ) -> list[dict[str, Any]]:
        """Create setup stories from KG prerequisite entities."""
        if not self.kg:
            return []

        stories: list[dict[str, Any]] = []
        key_prefix = self._project_key(project_name)
        prereqs = self.kg.entities_of_type(EntityType.PREREQUISITE)

        for i, prereq in enumerate(prereqs[:10]):
            stories.append({
                "type": "Story",
                "key": f"{key_prefix}-{start_idx + i}",
                "summary": f"Setup prerequisite: {prereq.name}",
                "description": (
                    f"Ensure the prerequisite '{prereq.name}' is properly "
                    f"set up in the development environment.\n\n"
                    f"Source: {prereq.source_section or 'N/A'}"
                ),
                "acceptance_criteria": [
                    f"'{prereq.name}' is installed / configured",
                    "Version requirements are met",
                    "Setup steps documented in wiki/runbook",
                ],
                "labels": ["opendocs-generated", "setup", "prerequisite"],
                "priority": "High",
                "story_points": 2,
            })

        return stories

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _project_key(name: str) -> str:
        """Derive a short project key (max 6 chars uppercase)."""
        clean = "".join(c for c in name if c.isalpha())
        return clean[:6].upper() or "PROJ"

    @staticmethod
    def _classify_section(title: str) -> str:
        """Classify a section title into a ticket label."""
        lower = title.lower()
        if any(w in lower for w in ("install", "setup", "getting started", "quickstart")):
            return "setup"
        if any(w in lower for w in ("api", "endpoint", "route")):
            return "api"
        if any(w in lower for w in ("feature", "capability", "highlight")):
            return "feature"
        if any(w in lower for w in ("test", "qa", "quality")):
            return "testing"
        if any(w in lower for w in ("deploy", "ci", "cd", "docker", "kubernetes")):
            return "devops"
        if any(w in lower for w in ("config", "environment", "setting")):
            return "configuration"
        if any(w in lower for w in ("architecture", "design", "diagram")):
            return "architecture"
        if any(w in lower for w in ("roadmap", "todo", "planned", "future")):
            return "roadmap"
        if any(w in lower for w in ("contributing", "community")):
            return "community"
        if any(w in lower for w in ("security", "auth", "permission")):
            return "security"
        return "documentation"

    @staticmethod
    def _classify_priority(title: str) -> str:
        """Estimate priority from section title."""
        lower = title.lower()
        if any(w in lower for w in ("install", "setup", "prerequisite", "security")):
            return "High"
        if any(w in lower for w in ("roadmap", "future", "contributing")):
            return "Low"
        return "Medium"

    @staticmethod
    def _section_to_summary(title: str, classification: str) -> str:
        """Create a story summary from a section title."""
        # Remove markdown heading prefixes if any leaked through
        clean_title = title.strip().lstrip("#").strip()
        action_map = {
            "setup": "Set up",
            "api": "Implement",
            "feature": "Implement",
            "testing": "Create tests for",
            "devops": "Configure",
            "configuration": "Configure",
            "architecture": "Design",
            "roadmap": "Plan",
            "community": "Establish",
            "security": "Implement security for",
            "documentation": "Document",
        }
        action = action_map.get(classification, "Implement")
        return f"{action}: {clean_title}"

    @staticmethod
    def _section_to_description(section: Section) -> str:
        """Build a story description from section blocks."""
        import re
        _html_re = re.compile(r"<[^>]+>")
        _multi_sp = re.compile(r"\s{2,}")
        parts: list[str] = []
        for block in section.blocks[:5]:  # cap context
            if isinstance(block, ParagraphBlock):
                cleaned = _html_re.sub("", block.text)
                cleaned = _multi_sp.sub(" ", cleaned).strip()
                if cleaned:
                    parts.append(cleaned)
            elif isinstance(block, ListBlock):
                for item in block.items[:8]:
                    cleaned = _html_re.sub("", item)
                    cleaned = _multi_sp.sub(" ", cleaned).strip()
                    if cleaned:
                        parts.append(f"* {cleaned}")
            elif isinstance(block, CodeBlock):
                parts.append(f"```{block.language}\n{block.code[:300]}\n```")
        return "\n\n".join(parts) if parts else section.title

    @staticmethod
    def _extract_acceptance_criteria(section: Section) -> list[str]:
        """Extract acceptance criteria from a section's content."""
        criteria: list[str] = []

        for block in section.blocks:
            if isinstance(block, ListBlock):
                for item in block.items[:10]:
                    # Capitalize first letter, ensure it reads like AC
                    ac = item.strip()
                    if ac:
                        criteria.append(ac)

        # If no list items, generate generic criteria from section title
        if not criteria and section.title:
            criteria = [
                f"'{section.title}' section is fully implemented",
                "Implementation matches README specification",
                "Covered by automated tests",
            ]

        return criteria[:10]

    @staticmethod
    def _estimate_points(section: Section) -> int:
        """Rough story point estimate based on content complexity."""
        n_blocks = len(section.blocks)
        n_subs = len(section.subsections)
        code_blocks = sum(
            1 for b in section.blocks if isinstance(b, CodeBlock)
        )
        # Simple heuristic
        if n_blocks + n_subs > 10 or code_blocks > 3:
            return 8
        if n_blocks + n_subs > 5:
            return 5
        if n_blocks > 2:
            return 3
        return 2
