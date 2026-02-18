"""LLM-based semantic entity extraction.

Uses OpenAI (or compatible) structured outputs to extract entities and
relations from README text with higher accuracy than deterministic rules.

Requires: ``pip install opendocs[llm]``
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from ..core.knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relation,
    RelationType,
)
from ..core.models import DocumentModel, Section

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a technical documentation analyst. You extract structured semantic
entities and their relationships from software project README files.

You MUST return valid JSON matching the schema below. Do not include
markdown formatting or commentary — only the JSON object.

Entity types: project, component, technology, protocol, language, framework,
database, cloud_service, api_endpoint, metric, configuration, prerequisite,
hardware, person_org, license, feature, platform.

Relation types: uses, connects_to, exposes, requires, stores_in,
communicates_via, depends_on, runs_on, licensed_under, provides, measures,
configured_by, integrates_with, part_of.
"""

_EXTRACTION_PROMPT = """\
Analyze the following README section and extract ALL semantic entities and
their relationships.

Section title: {section_title}
Section content:
---
{section_text}
---

Return a JSON object with this exact structure:
{{
  "entities": [
    {{
      "name": "string",
      "entity_type": "string (from entity types list)",
      "properties": {{}},
      "confidence": 0.0-1.0
    }}
  ],
  "relations": [
    {{
      "source": "entity name",
      "target": "entity name",
      "relation_type": "string (from relation types list)",
      "confidence": 0.0-1.0
    }}
  ]
}}
"""

_SUMMARY_SYSTEM_PROMPT = """\
You are a senior technical writer. You write clear, concise, human-readable
prose and bullet-point summaries. NEVER return JSON, code, or structured data.
Write in natural English paragraphs or bullet points as instructed.
"""

_SUMMARY_PROMPT = """\
You are writing a concise executive summary for a technical project.

Project: {project_name}
Description: {description}

Based on the following knowledge graph entities:
{entity_list}

Write a 3-5 sentence executive summary in plain English paragraphs that captures:
1. What the project does
2. Key technologies used
3. Architecture highlights
4. Primary value proposition

IMPORTANT: Return ONLY plain English text. Do NOT return JSON, code blocks,
or structured data. Just write natural prose paragraphs.
"""

_STAKEHOLDER_PROMPTS = {
    "cto": """\
Write a 4-6 bullet-point CTO-level technical assessment of this project.
Focus on: architecture quality, scalability concerns, tech stack modernity,
security considerations, and technical debt risks.

Project: {project_name}
Description: {description}
Entities: {entity_list}

IMPORTANT: Return ONLY plain-text bullet points starting with "- ".
Do NOT return JSON, code blocks, or any structured data format.
No introduction line — jump straight into the bullets.""",

    "investor": """\
Write a 4-6 bullet-point investor summary for this project.
Focus on: market opportunity, competitive advantage, scalability potential,
team capability signals, and monetization pathways.

Project: {project_name}
Description: {description}
Entities: {entity_list}

IMPORTANT: Return ONLY plain-text bullet points starting with "- ".
Do NOT return JSON, code blocks, or any structured data format.
No introduction line — jump straight into the bullets.""",

    "developer": """\
Write a 4-6 bullet-point developer onboarding summary for this project.
Focus on: getting started steps, architecture overview, key dependencies,
contribution guidelines signals, and documentation quality.

Project: {project_name}
Description: {description}
Entities: {entity_list}

IMPORTANT: Return ONLY plain-text bullet points starting with "- ".
Do NOT return JSON, code blocks, or any structured data format.
No introduction line — jump straight into the bullets.""",
}


# ---------------------------------------------------------------------------
# LLM Client wrapper with retry
# ---------------------------------------------------------------------------

class LLMClient:
    """Thin wrapper around OpenAI's chat completion API with retry logic."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        temperature: float = 0.1,
        max_retries: int = 3,
    ):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "LLM mode requires the 'openai' package. "
                "Install with: pip install opendocs[llm]"
            )

        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.client = OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
        )

    def chat(self, system: str, user: str) -> str:
        """Send a chat completion with exponential backoff retry."""
        last_exc: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                return response.choices[0].message.content or ""
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "LLM request failed (attempt %d/%d): %s — retrying in %ds",
                    attempt + 1, self.max_retries, exc, wait,
                )
                time.sleep(wait)

        raise RuntimeError(
            f"LLM request failed after {self.max_retries} attempts: {last_exc}"
        )


# ---------------------------------------------------------------------------
# LLM Entity Extractor
# ---------------------------------------------------------------------------

class LLMExtractor:
    """Uses an LLM to extract entities and relations from README content.

    Usage::

        extractor = LLMExtractor(api_key="sk-...")
        kg = extractor.extract(document_model)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
    ):
        self.llm = LLMClient(api_key=api_key, model=model, base_url=base_url)
        self._id_counter = 0

    def extract(self, doc: DocumentModel) -> KnowledgeGraph:
        """Extract entities and relations from all sections using the LLM."""
        kg = KnowledgeGraph()

        # Project root entity
        kg.add_entity(Entity(
            id="project_root",
            name=doc.metadata.repo_name or "Unknown Project",
            entity_type=EntityType.PROJECT,
            properties={"url": doc.metadata.repo_url, "description": doc.metadata.description},
            confidence=1.0,
            extraction_method="llm",
        ))

        # Process each section
        for section in doc.sections:
            self._extract_section(section, kg)

        kg.compute_stats()
        return kg

    def _extract_section(self, section: Section, kg: KnowledgeGraph) -> None:
        """Extract entities from a single section."""
        # Build text from section blocks
        text_parts = []
        for block in section.blocks:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif hasattr(block, "code"):
                text_parts.append(block.code)
            elif hasattr(block, "items"):
                text_parts.extend(block.items)

        section_text = "\n".join(text_parts)
        if len(section_text.strip()) < 20:
            # Skip near-empty sections
            for sub in section.subsections:
                self._extract_section(sub, kg)
            return

        # Truncate very long sections
        if len(section_text) > 3000:
            section_text = section_text[:3000] + "\n[... truncated]"

        prompt = _EXTRACTION_PROMPT.format(
            section_title=section.title,
            section_text=section_text,
        )

        try:
            response = self.llm.chat(_SYSTEM_PROMPT, prompt)
            parsed = self._parse_response(response)
            self._merge_parsed(parsed, section.title, kg)
        except Exception:
            pass  # Graceful degradation — skip this section

        # Recurse
        for sub in section.subsections:
            self._extract_section(sub, kg)

    def _parse_response(self, response: str) -> dict[str, Any]:
        """Parse the LLM JSON response, handling markdown code blocks."""
        text = response.strip()
        # Strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        return json.loads(text)

    def _merge_parsed(
        self,
        parsed: dict[str, Any],
        section_title: str,
        kg: KnowledgeGraph,
    ) -> None:
        """Merge parsed entities and relations into the KG."""
        entity_name_to_id: dict[str, str] = {}

        for e_data in parsed.get("entities", []):
            name = e_data.get("name", "").strip()
            if not name:
                continue

            # Map entity type
            try:
                etype = EntityType(e_data.get("entity_type", "component"))
            except ValueError:
                etype = EntityType.COMPONENT

            eid = self._make_id(etype.value, name)
            entity_name_to_id[name.lower()] = eid

            kg.add_entity(Entity(
                id=eid,
                name=name,
                entity_type=etype,
                properties=e_data.get("properties", {}),
                source_section=section_title,
                confidence=min(float(e_data.get("confidence", 0.8)), 1.0),
                extraction_method="llm",
            ))

        for r_data in parsed.get("relations", []):
            src_name = r_data.get("source", "").strip().lower()
            tgt_name = r_data.get("target", "").strip().lower()

            src_id = entity_name_to_id.get(src_name)
            tgt_id = entity_name_to_id.get(tgt_name)

            if not src_id or not tgt_id:
                continue

            try:
                rtype = RelationType(r_data.get("relation_type", "uses"))
            except ValueError:
                rtype = RelationType.USES

            kg.add_relation(Relation(
                source_id=src_id,
                target_id=tgt_id,
                relation_type=rtype,
                confidence=min(float(r_data.get("confidence", 0.7)), 1.0),
                extraction_method="llm",
            ))

    def _make_id(self, prefix: str, name: str) -> str:
        safe = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50]
        return f"llm_{prefix}_{safe}"


# ---------------------------------------------------------------------------
# LLM Summarizer
# ---------------------------------------------------------------------------

class LLMSummarizer:
    """Generates executive summaries and stakeholder-specific content
    using an LLM and a populated KnowledgeGraph.

    Usage::

        summarizer = LLMSummarizer(api_key="sk-...")
        summarizer.enrich(doc, kg)      # modifies kg in place
        print(kg.executive_summary)
        print(kg.stakeholder_summaries["cto"])
    """

    PERSONAS = ("cto", "investor", "developer")

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
    ):
        self.llm = LLMClient(api_key=api_key, model=model, base_url=base_url)

    def enrich(
        self,
        doc: DocumentModel,
        kg: KnowledgeGraph,
        *,
        personas: list[str] | None = None,
    ) -> None:
        """Generate summaries and store them directly in the KG.

        Parameters
        ----------
        doc
            The parsed document model.
        kg
            Knowledge graph to enrich with summaries.
        personas
            Which stakeholder personas to generate (default: all).
        """
        kg.executive_summary = self.executive_summary(doc, kg)

        for persona in (personas or list(self.PERSONAS)):
            summary = self.stakeholder_summary(doc, kg, persona)
            kg.stakeholder_summaries[persona] = summary

    def executive_summary(self, doc: DocumentModel, kg: KnowledgeGraph) -> str:
        """Generate a concise executive summary."""
        entity_list = self._format_entities(kg)
        prompt = _SUMMARY_PROMPT.format(
            project_name=doc.metadata.repo_name,
            description=doc.metadata.description or "(no description)",
            entity_list=entity_list,
        )
        try:
            return self.llm.chat(_SUMMARY_SYSTEM_PROMPT, prompt).strip()
        except Exception as e:
            logger.error("Executive summary generation failed: %s", e)
            return f"[Summary generation failed: {e}]"

    def stakeholder_summary(
        self,
        doc: DocumentModel,
        kg: KnowledgeGraph,
        persona: str = "cto",
    ) -> str:
        """Generate a stakeholder-specific summary.

        Supported personas: ``cto``, ``investor``, ``developer``.
        """
        template = _STAKEHOLDER_PROMPTS.get(persona.lower())
        if not template:
            return f"[Unknown persona: {persona}]"

        entity_list = self._format_entities(kg)
        prompt = template.format(
            project_name=doc.metadata.repo_name or "Unknown",
            description=(doc.metadata.description or "(no description)")[:300],
            entity_list=entity_list,
        )
        try:
            return self.llm.chat(_SUMMARY_SYSTEM_PROMPT, prompt).strip()
        except Exception as e:
            logger.error("Stakeholder summary (%s) failed: %s", persona, e)
            return f"[Stakeholder summary failed: {e}]"

    @staticmethod
    def _format_entities(kg: KnowledgeGraph) -> str:
        """Format entities for prompt injection."""
        lines = []
        for e in kg.entities[:50]:  # Cap to avoid token overflow
            props = ", ".join(f"{k}={v}" for k, v in e.properties.items()) if e.properties else ""
            lines.append(f"- {e.name} [{e.entity_type.value}] {props}")
        return "\n".join(lines) or "(no entities extracted)"
