"""LLM-based semantic entity extraction.

Uses multi-provider LLM backends (OpenAI, Anthropic, Google, Ollama, Azure)
to extract entities and relations from README text with higher accuracy
than deterministic rules.

Requires: ``pip install opendocs[llm]``
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from .providers import LLMProvider, get_provider, DEFAULT_PROVIDER

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
You are a senior technical writer with deep software engineering expertise.
You write clear, specific, and insightful prose that references ACTUAL project
details — names, technologies, endpoints, features, and architecture patterns.

NEVER return JSON, code, or structured data.
NEVER write generic filler paragraphs that could apply to any project.
ALWAYS reference specific details from the README content provided.
Write in natural English paragraphs or bullet points as instructed.
"""

_SUMMARY_PROMPT = """\
You are writing a concise executive summary for a real open-source project.
Your summary MUST reference specific details from the README — not generic statements.

PROJECT: {project_name}
URL: {repo_url}

--- README CONTENT (condensed) ---
{readme_digest}
---

KNOWLEDGE GRAPH ENTITIES:
{entity_list}

RELATIONSHIPS:
{relation_list}

Write a 4-6 sentence executive summary that specifically covers:
1. What the project ACTUALLY does (reference specific features/capabilities from the README)
2. The exact technologies and frameworks used (name them)
3. How the architecture works (reference specific components, APIs, or patterns)
4. Who the target users are and what problem it solves
5. What makes it different (any unique selling points from the README)

IMPORTANT:
- Reference SPECIFIC project details, not generic platitudes
- If the README mentions specific APIs, endpoints, metrics, or configs — mention them
- If there are install commands or quick-start steps — summarize them
- Return ONLY plain English text. No JSON, no code blocks, no bullet points.
"""

_STAKEHOLDER_PROMPTS = {
    "cto": """\
Write a CTO-level technical assessment of this SPECIFIC project.
Your bullets MUST reference actual details from the README.

PROJECT: {project_name}
URL: {repo_url}

--- README CONTENT (condensed) ---
{readme_digest}
---

ENTITIES: {entity_list}
RELATIONSHIPS: {relation_list}

Write 5-8 bullet points covering:
- Architecture quality: What patterns/components does it use? (reference specifics)
- Tech stack assessment: Are the chosen technologies ({tech_names}) modern and appropriate?
- Scalability: Based on the architecture described, what are the scaling characteristics?
- Security considerations: Any auth, API keys, permissions mentioned?
- Integration points: What does it connect to? APIs, databases, external services?
- Technical debt risks: What's missing or concerning?
- Code quality signals: Are there tests, CI/CD, linting mentioned?

IMPORTANT: Return ONLY plain-text bullet points starting with "- ".
Reference SPECIFIC technologies, components, and patterns from the README.
Do NOT write generic bullets that could apply to any project.
No introduction line — jump straight into the bullets.""",

    "investor": """\
Write an investor-grade assessment of this SPECIFIC project.
Your bullets MUST reference actual details from the README.

PROJECT: {project_name}
URL: {repo_url}

--- README CONTENT (condensed) ---
{readme_digest}
---

ENTITIES: {entity_list}
RELATIONSHIPS: {relation_list}

Write 5-8 bullet points covering:
- Market opportunity: What problem does {project_name} specifically solve?
- Competitive advantage: What features or architecture make it unique?
- Adoption signals: Are there install commands, package managers, Docker support?
- Ecosystem fit: What technologies ({tech_names}) does it integrate with?
- Scalability potential: Based on the architecture, can it scale?
- Monetization pathways: Enterprise features, SaaS potential, support tiers?
- Risk factors: Dependencies, single points of failure, maintenance burden?

IMPORTANT: Return ONLY plain-text bullet points starting with "- ".
Reference SPECIFIC features, numbers, and technical details from the README.
No introduction line — jump straight into the bullets.""",

    "developer": """\
Write a developer onboarding guide for this SPECIFIC project.
Your bullets MUST reference actual details from the README.

PROJECT: {project_name}
URL: {repo_url}

--- README CONTENT (condensed) ---
{readme_digest}
---

ENTITIES: {entity_list}
RELATIONSHIPS: {relation_list}
INSTALL COMMANDS:
{install_commands}

Write 5-8 bullet points covering:
- Getting started: What are the EXACT install steps? (reference real commands)
- Prerequisites: What needs to be installed first? ({prereq_names})
- Architecture overview: How is the codebase structured? Key components?
- Key APIs/interfaces: What are the main entry points a developer would use?
- Configuration: What env vars, config files, or settings are needed?
- Testing: How to run tests? What test framework is used?
- Contribution workflow: Is there a CONTRIBUTING guide? PR process?
- Documentation quality: How well is the README structured?

IMPORTANT: Return ONLY plain-text bullet points starting with "- ".
Include ACTUAL commands, file paths, and package names from the README.
No introduction line — jump straight into the bullets.""",
}


# ---------------------------------------------------------------------------
# LLM Client wrapper (delegates to unified provider)
# ---------------------------------------------------------------------------

class LLMClient:
    """Thin wrapper that delegates to the unified multi-provider system.

    Backward-compatible interface: ``LLMClient(api_key, model, base_url)``
    still works.  New ``provider`` param selects the backend.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        temperature: float = 0.1,
        max_retries: int = 3,
        provider: str = DEFAULT_PROVIDER,
    ):
        self._provider = get_provider(
            provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            temperature=temperature,
            max_retries=max_retries,
        )

    def chat(self, system: str, user: str) -> str:
        """Send a chat completion with retry (handled by provider)."""
        return self._provider.chat(system, user)


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
        provider: str = DEFAULT_PROVIDER,
    ):
        self.llm = LLMClient(api_key=api_key, model=model, base_url=base_url, provider=provider)
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

    Now sends the ACTUAL README content, section structure, code examples,
    install commands, and KG entities+relations to the LLM — so the output
    references real project details instead of generic paragraphs.

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
        provider: str = DEFAULT_PROVIDER,
    ):
        self.llm = LLMClient(api_key=api_key, model=model, base_url=base_url, provider=provider)

    def enrich(
        self,
        doc: DocumentModel,
        kg: KnowledgeGraph,
        *,
        personas: list[str] | None = None,
    ) -> None:
        """Generate summaries and store them directly in the KG."""
        # Build rich context once — shared across all prompts
        ctx = self._build_context(doc, kg)

        kg.executive_summary = self._executive_summary(ctx)

        for persona in (personas or list(self.PERSONAS)):
            summary = self._stakeholder_summary(ctx, persona)
            kg.stakeholder_summaries[persona] = summary

    # -- Public aliases for backwards compat -----------------------------

    def executive_summary(self, doc: DocumentModel, kg: KnowledgeGraph) -> str:
        ctx = self._build_context(doc, kg)
        return self._executive_summary(ctx)

    def stakeholder_summary(
        self, doc: DocumentModel, kg: KnowledgeGraph, persona: str = "cto",
    ) -> str:
        ctx = self._build_context(doc, kg)
        return self._stakeholder_summary(ctx, persona)

    # -- Internal --------------------------------------------------------

    def _executive_summary(self, ctx: dict[str, str]) -> str:
        prompt = _SUMMARY_PROMPT.format(**ctx)
        try:
            return self.llm.chat(_SUMMARY_SYSTEM_PROMPT, prompt).strip()
        except Exception as e:
            logger.error("Executive summary generation failed: %s", e)
            return f"[Summary generation failed: {e}]"

    def _stakeholder_summary(self, ctx: dict[str, str], persona: str) -> str:
        template = _STAKEHOLDER_PROMPTS.get(persona.lower())
        if not template:
            return f"[Unknown persona: {persona}]"

        prompt = template.format(**ctx)
        try:
            return self.llm.chat(_SUMMARY_SYSTEM_PROMPT, prompt).strip()
        except Exception as e:
            logger.error("Stakeholder summary (%s) failed: %s", persona, e)
            return f"[Stakeholder summary failed: {e}]"

    # -- Context builder -------------------------------------------------

    @staticmethod
    def _build_context(doc: DocumentModel, kg: KnowledgeGraph) -> dict[str, str]:
        """Build a rich context dict that all prompts can reference.

        Includes: project name, URL, condensed README, section outline,
        features, code examples, install commands, entities, relations,
        tech names, and prerequisite names.
        """
        from ..core.models import (
            CodeBlock, ListBlock, ParagraphBlock, TableBlock,
        )

        project_name = doc.metadata.repo_name or "Unknown"
        repo_url = doc.metadata.repo_url or ""

        # -- Condensed README digest (most important content) --
        digest_parts: list[str] = []

        # Section outline
        digest_parts.append("## Section Structure:")
        for sec in doc.sections:
            LLMSummarizer._outline_section(digest_parts, sec, indent=0)

        # First paragraphs (project description)
        digest_parts.append("\n## Key Paragraphs:")
        para_count = 0
        for b in doc.all_blocks:
            if isinstance(b, ParagraphBlock) and len(b.text) > 30:
                digest_parts.append(b.text[:300])
                para_count += 1
                if para_count >= 8:
                    break

        # Feature lists
        features: list[str] = []
        for sec in doc.sections:
            LLMSummarizer._collect_features(sec, features)
        if features:
            digest_parts.append("\n## Features mentioned:")
            for f in features[:20]:
                digest_parts.append(f"- {f}")

        # Tables (headers + first rows)
        for b in doc.all_blocks:
            if isinstance(b, TableBlock) and b.headers:
                digest_parts.append(
                    f"\n## Table: {' | '.join(b.headers)}"
                )
                for row in b.rows[:5]:
                    digest_parts.append("  " + " | ".join(row))

        # Code blocks (install commands + key examples)
        install_cmds: list[str] = []
        code_examples: list[str] = []
        install_keywords = (
            "pip install", "npm install", "cargo install",
            "brew install", "apt install", "go install",
            "git clone", "docker pull", "docker run",
            "yarn add", "gem install",
        )
        for b in doc.all_blocks:
            if isinstance(b, CodeBlock) and b.code.strip():
                lower = b.code.lower()
                if any(kw in lower for kw in install_keywords):
                    install_cmds.append(b.code.strip()[:200])
                elif len(b.code.strip()) > 20:
                    code_examples.append(
                        f"```{b.language}\n{b.code.strip()[:300]}\n```"
                    )

        if install_cmds:
            digest_parts.append("\n## Install Commands:")
            for cmd in install_cmds[:5]:
                digest_parts.append(cmd)

        if code_examples:
            digest_parts.append("\n## Code Examples:")
            for ex in code_examples[:5]:
                digest_parts.append(ex)

        readme_digest = "\n".join(digest_parts)
        # Cap total digest to ~4000 chars to fit in context window
        if len(readme_digest) > 4000:
            readme_digest = readme_digest[:4000] + "\n[... truncated]"

        # -- Entity list --
        entity_lines: list[str] = []
        for e in kg.entities[:50]:
            props = ""
            if e.properties:
                props = " (" + ", ".join(
                    f"{k}={v}" for k, v in e.properties.items()
                    if v and str(v) != ""
                ) + ")"
            entity_lines.append(
                f"- {e.name} [{e.entity_type.value}]{props}"
            )
        entity_list = "\n".join(entity_lines) or "(no entities extracted)"

        # -- Relation list --
        relation_lines: list[str] = []
        for r in kg.relations[:30]:
            src = kg.get_entity(r.source_id)
            tgt = kg.get_entity(r.target_id)
            if src and tgt:
                relation_lines.append(
                    f"- {src.name} --{r.relation_type.value}--> {tgt.name}"
                )
        relation_list = "\n".join(relation_lines) or "(no relations)"

        # -- Named tech and prereqs --
        tech_names = ", ".join(
            e.name for e in kg.entities
            if e.entity_type in (
                EntityType.TECHNOLOGY, EntityType.FRAMEWORK,
                EntityType.LANGUAGE, EntityType.DATABASE,
                EntityType.CLOUD_SERVICE, EntityType.PLATFORM,
            )
        )[:300] or "not specified"

        prereq_names = ", ".join(
            e.name for e in kg.entities
            if e.entity_type == EntityType.PREREQUISITE
        )[:200] or "not specified"

        return {
            "project_name": project_name,
            "repo_url": repo_url,
            "readme_digest": readme_digest,
            "entity_list": entity_list,
            "relation_list": relation_list,
            "tech_names": tech_names,
            "prereq_names": prereq_names,
            "install_commands": "\n".join(install_cmds[:3]) or "(none found)",
        }

    @staticmethod
    def _outline_section(
        parts: list[str], section: Section, indent: int,
    ) -> None:
        """Recursively build section outline."""
        if section.title:
            prefix = "  " * indent
            n_blocks = len(section.blocks)
            parts.append(f"{prefix}- {section.title} ({n_blocks} blocks)")
        for sub in section.subsections:
            LLMSummarizer._outline_section(parts, sub, indent + 1)

    @staticmethod
    def _collect_features(section: Section, features: list[str]) -> None:
        """Recursively collect list items from feature-like sections."""
        from ..core.models import ListBlock

        lower = section.title.lower()
        is_feature_section = any(
            w in lower
            for w in ("feature", "highlight", "capability", "what",
                       "overview", "key", "benefit")
        )
        if is_feature_section:
            for b in section.blocks:
                if isinstance(b, ListBlock):
                    features.extend(b.items[:15])
        for sub in section.subsections:
            LLMSummarizer._collect_features(sub, features)


# ---------------------------------------------------------------------------
# LLM Content Enhancer — blog, FAQ, rewritten sections
# ---------------------------------------------------------------------------

_BLOG_SYSTEM = """\
You are a world-class technical blogger. You write engaging, informative,
and well-structured blog posts about open-source software projects.
Your writing style is conversational yet authoritative — like the best
posts on the Vercel or Stripe engineering blogs.

CRITICAL RULES:
- Write in Markdown format
- Reference SPECIFIC project details — feature names, API endpoints, tech stack
- Include code snippets inline when relevant (use fenced code blocks)
- Never write generic filler — every sentence must add value
- Use short paragraphs (2-3 sentences max) for web readability
- Include section headers (##) to break up the content
- No emojis
"""

_BLOG_PROMPT = """\
Write a polished, publication-ready technical blog post about this project.

PROJECT: {project_name}
URL: {repo_url}

--- README CONTENT ---
{readme_digest}
---

KNOWLEDGE GRAPH:
Entities: {entity_list}
Relations: {relation_list}
Tech stack: {tech_names}

STRUCTURE (follow this exactly):
1. Opening hook — a compelling 2-3 sentence intro that explains what the project does and why it matters
2. ## What is {project_name}? — clear explanation with specific features
3. ## Key Features — highlight 5-8 specific features with brief explanations
4. ## Architecture & Tech Stack — explain how it's built (reference actual technologies)
5. ## Getting Started — practical getting-started guide using ACTUAL install commands from the README
6. ## Code Examples — show 2-3 practical code examples from the README
7. ## Why {project_name} Stands Out — what makes it unique (reference specific differentiators)
8. ## Conclusion — 2-3 sentences wrapping up with a call to action

IMPORTANT:
- The post should be 800-1200 words
- Reference ACTUAL details from the README
- Include real code examples from the README content
- Do NOT include YAML front-matter or metadata — start directly with the hook paragraph
- Do NOT add a title line (# Title) — the generator handles that
"""

_FAQ_SYSTEM = """\
You are a helpful technical documentation expert. You anticipate the
questions that developers, architects, and decision-makers would ask
about an open-source project after reading its README.

CRITICAL RULES:
- Every answer must reference SPECIFIC details from the README content
- Answers should be 2-4 sentences, concise and actionable
- Include actual commands, file paths, or config values when relevant
- Never give generic answers — every answer must be project-specific
- Return valid JSON only
"""

_FAQ_PROMPT = """\
Generate 8-10 frequently asked questions and answers for this project.
The questions should cover what real users would ask.

PROJECT: {project_name}
URL: {repo_url}

--- README CONTENT ---
{readme_digest}
---

Tech stack: {tech_names}
Prerequisites: {prereq_names}
Install commands: {install_commands}

Generate questions covering:
- What the project does / when to use it
- Installation and setup
- Key features and capabilities
- Architecture and tech decisions
- Integration with other tools
- Performance and scalability
- Common gotchas or requirements
- How to contribute or get support

Return a JSON array of objects:
[
  {{"q": "What is {project_name} and what problem does it solve?", "a": "..."}},
  ...
]

IMPORTANT: Return ONLY the JSON array. No markdown, no commentary.
"""

_SECTION_REWRITE_SYSTEM = """\
You are a senior technical writer. You take raw README sections and
rewrite them into polished, professional documentation prose suitable
for a Word/PDF technical report.

CRITICAL RULES:
- Preserve ALL technical accuracy and specific details
- Improve clarity, flow, and readability
- Use professional but accessible language
- Keep the same information — do not invent new content
- Combine choppy bullet points into flowing paragraphs where appropriate
- Keep code references and commands exactly as they are
- 2-4 paragraphs per section, concise
- No emojis, no markdown formatting (output plain text)
"""

_SECTION_REWRITE_PROMPT = """\
Rewrite the following README sections into polished technical report prose.

PROJECT: {project_name}

For EACH section below, produce a clean rewrite. Return a JSON object where
each key is the exact section title and the value is the rewritten text.

SECTIONS:
{sections_text}

Return ONLY a JSON object like:
{{
  "Section Title 1": "Rewritten prose...",
  "Section Title 2": "Rewritten prose...",
  ...
}}

IMPORTANT:
- Keep ALL technical details, commands, and specifics intact
- Improve readability and professional tone
- Combine fragmented bullets into coherent paragraphs
- Return valid JSON only — no markdown fences, no commentary
"""


class LLMContentEnhancer:
    """Generates LLM-enhanced content for blog, FAQ, and Word documents.

    Called after ``LLMSummarizer`` in the pipeline.  Stores results
    directly on the ``KnowledgeGraph`` instance.

    Usage::

        enhancer = LLMContentEnhancer(api_key="sk-...")
        enhancer.enrich(doc, kg)
        print(kg.llm_blog)      # Full blog post
        print(kg.llm_faq)       # List of {q:, a:} dicts
        print(kg.llm_sections)  # Dict of title -> rewritten prose
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        provider: str = DEFAULT_PROVIDER,
    ):
        self.llm = LLMClient(api_key=api_key, model=model, base_url=base_url, provider=provider)

    def enrich(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        """Generate blog, FAQ, and rewritten sections.  Stores on KG."""
        ctx = LLMSummarizer._build_context(doc, kg)

        # 1) Blog post
        kg.llm_blog = self._generate_blog(ctx)
        logger.info("LLM blog generated (%d chars)", len(kg.llm_blog))

        # 2) FAQ
        kg.llm_faq = self._generate_faq(ctx)
        logger.info("LLM FAQ generated (%d items)", len(kg.llm_faq))

        # 3) Rewritten sections for Word/PDF
        kg.llm_sections = self._rewrite_sections(doc, ctx)
        logger.info("LLM rewrote %d sections", len(kg.llm_sections))

    # -- Blog ------------------------------------------------------------

    def _generate_blog(self, ctx: dict[str, str]) -> str:
        prompt = _BLOG_PROMPT.format(**ctx)
        try:
            return self.llm.chat(_BLOG_SYSTEM, prompt).strip()
        except Exception as e:
            logger.error("Blog generation failed: %s", e)
            return ""

    # -- FAQ -------------------------------------------------------------

    def _generate_faq(self, ctx: dict[str, str]) -> list[dict[str, str]]:
        prompt = _FAQ_PROMPT.format(**ctx)
        try:
            raw = self.llm.chat(_FAQ_SYSTEM, prompt).strip()
            # Strip code fences
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [
                    {"q": item.get("q", ""), "a": item.get("a", "")}
                    for item in parsed
                    if item.get("q") and item.get("a")
                ]
            return []
        except Exception as e:
            logger.error("FAQ generation failed: %s", e)
            return []

    # -- Section rewrites ------------------------------------------------

    def _rewrite_sections(
        self, doc: DocumentModel, ctx: dict[str, str],
    ) -> dict[str, str]:
        """Rewrite top-level README sections into polished prose.

        Batches sections into groups to minimize API calls.
        """
        from ..core.models import CodeBlock, ListBlock, ParagraphBlock

        # Collect section summaries
        section_texts: list[tuple[str, str]] = []
        for sec in doc.sections:
            if not sec.title:
                continue
            text_parts: list[str] = []
            for block in sec.blocks:
                if hasattr(block, "text"):
                    text_parts.append(block.text[:300])
                elif hasattr(block, "items"):
                    text_parts.extend(item[:100] for item in block.items[:10])
                elif hasattr(block, "code"):
                    text_parts.append(f"[code: {block.code[:150]}]")
            # Include subsection content
            for sub in sec.subsections:
                text_parts.append(f"### {sub.title}")
                for block in sub.blocks:
                    if hasattr(block, "text"):
                        text_parts.append(block.text[:200])
                    elif hasattr(block, "items"):
                        text_parts.extend(item[:80] for item in block.items[:8])

            combined = "\n".join(text_parts).strip()
            if len(combined) > 30:
                section_texts.append((sec.title, combined[:800]))

        if not section_texts:
            return {}

        # Batch into chunks of ~5 sections per call
        result: dict[str, str] = {}
        batch_size = 5
        for i in range(0, len(section_texts), batch_size):
            batch = section_texts[i : i + batch_size]
            sections_formatted = "\n\n".join(
                f"--- {title} ---\n{text}" for title, text in batch
            )
            prompt = _SECTION_REWRITE_PROMPT.format(
                project_name=ctx["project_name"],
                sections_text=sections_formatted,
            )
            try:
                raw = self.llm.chat(_SECTION_REWRITE_SYSTEM, prompt).strip()
                raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
                raw = re.sub(r"\n?```\s*$", "", raw)
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    result.update(parsed)
            except Exception as e:
                logger.warning("Section rewrite batch failed: %s", e)
                continue

        return result

