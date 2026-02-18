"""Generate social media cards and post text from a DocumentModel.

Produces a JSON file containing:
- Open Graph (OG) metadata for link previews
- Twitter Card metadata
- LinkedIn post text
- Twitter/X post text (with character limit)
- Short description for Hacker News / Reddit
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..core.knowledge_graph import EntityType, KnowledgeGraph
from ..core.models import (
    CodeBlock,
    DocumentModel,
    GenerationResult,
    ListBlock,
    OutputFormat,
    ParagraphBlock,
)
from .base import BaseGenerator

if TYPE_CHECKING:
    from .diagram_extractor import ImageCache


class SocialGenerator(BaseGenerator):
    """DocumentModel → Social media cards & post text (JSON)."""

    format = OutputFormat.SOCIAL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        filename = self._safe_filename(doc.metadata.repo_name or "social", "json")
        filename = f"social_{filename}"
        output_path = self._ensure_dir(output_dir) / filename

        try:
            payload = self._build_social(doc)
            output_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return GenerationResult(
                format=OutputFormat.SOCIAL,
                output_path=output_path,
            )
        except Exception as exc:
            return GenerationResult(
                format=OutputFormat.SOCIAL,
                output_path=output_path,
                success=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_social(self, doc: DocumentModel) -> dict[str, Any]:
        """Build the full social media payload."""
        name = doc.metadata.repo_name or "Project"
        url = doc.metadata.repo_url or ""
        description = self._short_description(doc)
        long_description = self._long_description(doc)
        tags = self._build_hashtags(doc)
        now = datetime.now().isoformat()

        return {
            "generated_by": "opendocs",
            "generated_at": now,
            "project": name,
            "url": url,

            # -- Open Graph metadata ---
            "open_graph": {
                "og:title": f"{name} — {self._tagline(doc)}",
                "og:description": description,
                "og:type": "website",
                "og:url": url,
                "og:site_name": name,
                "og:locale": "en_US",
            },

            # -- Twitter Card ---
            "twitter_card": {
                "twitter:card": "summary_large_image",
                "twitter:title": name,
                "twitter:description": description,
                "twitter:url": url,
            },

            # -- Post templates ---
            "posts": {
                "twitter": self._twitter_post(name, url, description, tags),
                "linkedin": self._linkedin_post(name, url, long_description, tags),
                "hackernews": self._hn_post(name, url, description),
                "reddit": self._reddit_post(name, url, long_description, tags),
                "producthunt": self._ph_post(name, url, description, tags),
            },

            # -- Raw data ---
            "hashtags": tags,
            "short_description": description,
            "long_description": long_description,
            "features": self._extract_features(doc),
            "tech_stack": self._extract_techs(),
        }

    # ------------------------------------------------------------------
    # Post builders
    # ------------------------------------------------------------------

    def _twitter_post(
        self, name: str, url: str, desc: str, tags: list[str],
    ) -> str:
        """Build a Twitter/X post (≤280 chars)."""
        tag_str = " ".join(f"#{t}" for t in tags[:3])
        post = f"🚀 Check out {name}!\n\n{desc}\n\n{url}\n\n{tag_str}"
        # Trim to 280 chars
        if len(post) > 280:
            avail = 280 - len(f"🚀 {name}\n\n\n\n{url}\n\n{tag_str}") - 3
            short_desc = desc[:avail] + "..."
            post = f"🚀 {name}\n\n{short_desc}\n\n{url}\n\n{tag_str}"
        return post[:280]

    def _linkedin_post(
        self, name: str, url: str, desc: str, tags: list[str],
    ) -> str:
        """Build a LinkedIn post."""
        tag_str = " ".join(f"#{t}" for t in tags[:5])
        features = self._extract_features_text()

        post = f"""🚀 Excited to share {name}!

{desc}

{features}

Check it out here: {url}

{tag_str}

#opensource #development #tech"""
        return post.strip()

    def _hn_post(self, name: str, url: str, desc: str) -> dict[str, str]:
        """Build a Hacker News submission."""
        return {
            "title": f"{name}: {desc[:80]}",
            "url": url,
        }

    def _reddit_post(
        self, name: str, url: str, desc: str, tags: list[str],
    ) -> dict[str, str]:
        """Build a Reddit post."""
        features = self._extract_features_text()
        body = f"""{desc}

{features}

**Links:**
- GitHub: {url}
- Install: `pip install {name.lower().replace(' ', '-')}`

Would love to hear your feedback!"""

        return {
            "title": f"{name} — {desc[:100]}",
            "body": body.strip(),
            "suggested_subreddits": self._suggest_subreddits(),
        }

    def _ph_post(
        self, name: str, url: str, desc: str, tags: list[str],
    ) -> dict[str, str]:
        """Build a Product Hunt launch post."""
        return {
            "name": name,
            "tagline": desc[:60],
            "description": self._long_description_for_ph(desc),
            "website": url,
            "topics": tags[:5],
        }

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _short_description(self, doc: DocumentModel) -> str:
        """Build a ≤160 char description."""
        if self.kg and self.kg.executive_summary:
            first = self.kg.executive_summary.split(". ")[0]
            return first[:160]
        if doc.metadata.description:
            return doc.metadata.description[:160]
        paras = [
            b.text for b in doc.all_blocks
            if isinstance(b, ParagraphBlock) and len(b.text) > 20
        ]
        if paras:
            return paras[0][:160]
        return f"{doc.metadata.repo_name or 'Project'} — an open-source tool"

    def _long_description(self, doc: DocumentModel) -> str:
        """Build a longer description (≤500 chars)."""
        if self.kg and self.kg.executive_summary:
            return self.kg.executive_summary[:500]
        paras = [
            b.text for b in doc.all_blocks
            if isinstance(b, ParagraphBlock) and len(b.text) > 30
        ]
        if paras:
            text = " ".join(paras[:3])
            return text[:500]
        return self._short_description(doc)

    def _long_description_for_ph(self, short: str) -> str:
        """Extended description for Product Hunt."""
        if self.kg and self.kg.executive_summary:
            return self.kg.executive_summary
        return short

    def _tagline(self, doc: DocumentModel) -> str:
        """Build a short tagline."""
        if doc.metadata.description:
            return doc.metadata.description[:60]
        return "an open-source project"

    def _build_hashtags(self, doc: DocumentModel) -> list[str]:
        """Generate hashtags from KG entities."""
        tags: list[str] = []
        if self.kg:
            for e in self.kg.entities:
                if e.entity_type in (
                    EntityType.TECHNOLOGY, EntityType.FRAMEWORK,
                    EntityType.LANGUAGE, EntityType.PLATFORM,
                ):
                    # Clean tag: no spaces, lowercase
                    tag = e.name.lower().replace(" ", "").replace("-", "").replace(".", "")
                    if tag and len(tag) > 1:
                        tags.append(tag)
        # Deduplicate
        tags = list(dict.fromkeys(tags))
        # Always include 'opensource'
        if "opensource" not in tags:
            tags.append("opensource")
        return tags[:10]

    def _extract_features(self, doc: DocumentModel) -> list[str]:
        """Extract feature names."""
        features: list[str] = []
        if self.kg:
            for e in self.kg.entities_of_type(EntityType.FEATURE):
                features.append(e.name)
        if not features:
            for sec in doc.sections:
                if "feature" in sec.title.lower():
                    for b in sec.blocks:
                        if isinstance(b, ListBlock):
                            features.extend(b.items[:6])
                    break
        return features[:10]

    def _extract_features_text(self) -> str:
        """Build a bullet list of features as text."""
        if not self.kg:
            return ""
        features = self.kg.entities_of_type(EntityType.FEATURE)
        if not features:
            return ""
        lines = ["Key features:"]
        for f in features[:5]:
            lines.append(f"✅ {f.name}")
        return "\n".join(lines)

    def _extract_techs(self) -> list[str]:
        """Extract technology names."""
        if not self.kg:
            return []
        techs: list[str] = []
        for e in self.kg.entities:
            if e.entity_type in (
                EntityType.TECHNOLOGY, EntityType.FRAMEWORK,
                EntityType.LANGUAGE, EntityType.DATABASE,
                EntityType.CLOUD_SERVICE, EntityType.PLATFORM,
            ):
                techs.append(e.name)
        return list(dict.fromkeys(techs))[:10]

    def _suggest_subreddits(self) -> list[str]:
        """Suggest relevant subreddits based on tech stack."""
        subs = ["r/programming", "r/opensource"]
        if self.kg:
            langs = {
                e.name.lower()
                for e in self.kg.entities_of_type(EntityType.LANGUAGE)
            }
            if "python" in langs:
                subs.append("r/Python")
            if "javascript" in langs or "typescript" in langs:
                subs.append("r/javascript")
            if "rust" in langs:
                subs.append("r/rust")
            if "go" in langs:
                subs.append("r/golang")

            frameworks = {
                e.name.lower()
                for e in self.kg.entities_of_type(EntityType.FRAMEWORK)
            }
            if any("react" in f for f in frameworks):
                subs.append("r/reactjs")
            if any("django" in f for f in frameworks):
                subs.append("r/django")
            if any("flask" in f for f in frameworks):
                subs.append("r/flask")

        return list(dict.fromkeys(subs))[:6]
