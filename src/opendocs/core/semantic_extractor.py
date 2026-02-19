"""Deterministic semantic entity extractor (Mode 1).

Scans a ``DocumentModel`` and extracts typed entities and relationships
using pattern matching, curated dictionaries, and structural heuristics.
No LLM required — fast, free, and predictable.
"""

from __future__ import annotations

import re
from typing import Any

from .knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relation,
    RelationType,
)
from .models import (
    CodeBlock,
    ContentBlock,
    DocumentModel,
    HeadingBlock,
    ListBlock,
    MermaidBlock,
    ParagraphBlock,
    Section,
    TableBlock,
)


# ---------------------------------------------------------------------------
# Technology dictionaries (curated)
# ---------------------------------------------------------------------------

_LANGUAGES: dict[str, dict[str, Any]] = {
    "python": {"category": "language"},
    "javascript": {"category": "language"},
    "typescript": {"category": "language"},
    "java": {"category": "language"},
    "go": {"category": "language"},
    "golang": {"category": "language", "canonical": "Go"},
    "rust": {"category": "language"},
    "c++": {"category": "language"},
    "c#": {"category": "language"},
    "ruby": {"category": "language"},
    "php": {"category": "language"},
    "swift": {"category": "language"},
    "kotlin": {"category": "language"},
    "scala": {"category": "language"},
    "lua": {"category": "language"},
    "r": {"category": "language"},
    "dart": {"category": "language"},
    "elixir": {"category": "language"},
    "haskell": {"category": "language"},
    "perl": {"category": "language"},
    "shell": {"category": "language"},
    "bash": {"category": "language"},
}

_FRAMEWORKS: dict[str, dict[str, Any]] = {
    "react": {"category": "frontend"},
    "vue": {"category": "frontend"},
    "angular": {"category": "frontend"},
    "next.js": {"category": "fullstack"},
    "nextjs": {"category": "fullstack", "canonical": "Next.js"},
    "django": {"category": "backend"},
    "flask": {"category": "backend"},
    "fastapi": {"category": "backend"},
    "express": {"category": "backend"},
    "spring": {"category": "backend"},
    "spring boot": {"category": "backend"},
    "rails": {"category": "backend"},
    "laravel": {"category": "backend"},
    "tensorflow": {"category": "ml"},
    "pytorch": {"category": "ml"},
    "langchain": {"category": "llm"},
    "langgraph": {"category": "llm"},
    "streamlit": {"category": "frontend"},
    "gradio": {"category": "frontend"},
    "svelte": {"category": "frontend"},
    "tailwind": {"category": "css"},
    "bootstrap": {"category": "css"},
}

_DATABASES: dict[str, dict[str, Any]] = {
    "postgresql": {"type": "relational"},
    "postgres": {"type": "relational", "canonical": "PostgreSQL"},
    "mysql": {"type": "relational"},
    "sqlite": {"type": "relational"},
    "mongodb": {"type": "document"},
    "redis": {"type": "key-value"},
    "elasticsearch": {"type": "search"},
    "influxdb": {"type": "timeseries"},
    "dynamodb": {"type": "key-value"},
    "cassandra": {"type": "wide-column"},
    "neo4j": {"type": "graph"},
    "supabase": {"type": "baas"},
    "firebase": {"type": "baas"},
    "couchdb": {"type": "document"},
    "mariadb": {"type": "relational"},
    "clickhouse": {"type": "analytical"},
    "timescaledb": {"type": "timeseries"},
}

_PROTOCOLS: dict[str, dict[str, Any]] = {
    "mqtt": {"transport": "tcp", "pattern": "pub-sub"},
    "http": {"transport": "tcp", "pattern": "request-response"},
    "https": {"transport": "tcp", "pattern": "request-response"},
    "websocket": {"transport": "tcp", "pattern": "bidirectional"},
    "grpc": {"transport": "http2", "pattern": "rpc"},
    "graphql": {"transport": "http", "pattern": "query"},
    "rest": {"transport": "http", "pattern": "request-response"},
    "amqp": {"transport": "tcp", "pattern": "message-queue"},
    "coap": {"transport": "udp", "pattern": "request-response"},
    "zigbee": {"transport": "radio", "pattern": "mesh"},
    "ble": {"transport": "radio", "pattern": "short-range"},
    "bluetooth": {"transport": "radio", "pattern": "short-range"},
    "lora": {"transport": "radio", "pattern": "lpwan"},
    "lorawan": {"transport": "radio", "pattern": "lpwan"},
    "tcp": {"transport": "ip", "pattern": "stream"},
    "udp": {"transport": "ip", "pattern": "datagram"},
    "ssh": {"transport": "tcp", "pattern": "secure-shell"},
    "ftp": {"transport": "tcp", "pattern": "file-transfer"},
}

_CLOUD_SERVICES: dict[str, dict[str, Any]] = {
    "aws": {"provider": "amazon"},
    "aws iot core": {"provider": "amazon", "service": "iot"},
    "aws lambda": {"provider": "amazon", "service": "compute"},
    "aws s3": {"provider": "amazon", "service": "storage"},
    "aws sns": {"provider": "amazon", "service": "messaging"},
    "aws sqs": {"provider": "amazon", "service": "messaging"},
    "azure": {"provider": "microsoft"},
    "azure iot hub": {"provider": "microsoft", "service": "iot"},
    "gcp": {"provider": "google"},
    "google cloud": {"provider": "google"},
    "firebase": {"provider": "google", "service": "baas"},
    "heroku": {"provider": "salesforce"},
    "vercel": {"provider": "vercel"},
    "netlify": {"provider": "netlify"},
    "docker": {"provider": "docker", "service": "container"},
    "kubernetes": {"provider": "cncf", "service": "orchestration"},
    "k8s": {"provider": "cncf", "service": "orchestration", "canonical": "Kubernetes"},
    "terraform": {"provider": "hashicorp", "service": "iac"},
    "grafana": {"provider": "grafana", "service": "monitoring"},
    "prometheus": {"provider": "cncf", "service": "monitoring"},
    "nginx": {"provider": "f5", "service": "reverse-proxy"},
    "cloudflare": {"provider": "cloudflare", "service": "cdn"},
}

_HARDWARE: dict[str, dict[str, Any]] = {
    "raspberry pi": {"type": "sbc"},
    "arduino": {"type": "microcontroller"},
    "esp32": {"type": "microcontroller", "connectivity": "wifi+ble"},
    "esp8266": {"type": "microcontroller", "connectivity": "wifi"},
    "stm32": {"type": "microcontroller"},
    "jetson": {"type": "sbc", "gpu": True},
    "nvidia jetson": {"type": "sbc", "gpu": True},
    "ds18b20": {"type": "sensor", "measures": "temperature"},
    "dht22": {"type": "sensor", "measures": "temperature+humidity"},
    "dht11": {"type": "sensor", "measures": "temperature+humidity"},
    "bme280": {"type": "sensor", "measures": "temperature+humidity+pressure"},
    "bmp280": {"type": "sensor", "measures": "temperature+pressure"},
    "mpu6050": {"type": "sensor", "measures": "accelerometer+gyroscope"},
    "hc-sr04": {"type": "sensor", "measures": "distance"},
    "pir": {"type": "sensor", "measures": "motion"},
    "gps": {"type": "sensor", "measures": "location"},
    "gpio": {"type": "interface"},
    "i2c": {"type": "interface"},
    "spi": {"type": "interface"},
    "uart": {"type": "interface"},
}

_PLATFORMS: dict[str, dict[str, Any]] = {
    "linux": {"type": "os"},
    "ubuntu": {"type": "os"},
    "windows": {"type": "os"},
    "macos": {"type": "os"},
    "android": {"type": "os"},
    "ios": {"type": "os"},
    "docker": {"type": "container"},
    "npm": {"type": "package-manager"},
    "pip": {"type": "package-manager"},
    "conda": {"type": "package-manager"},
    "github actions": {"type": "ci-cd"},
    "jenkins": {"type": "ci-cd"},
    "gitlab ci": {"type": "ci-cd"},
}

_LICENSES: dict[str, str] = {
    "mit": "MIT",
    "apache 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "gpl": "GPL",
    "gpl-3.0": "GPL-3.0",
    "bsd": "BSD",
    "bsd-3-clause": "BSD-3-Clause",
    "lgpl": "LGPL",
    "mpl": "MPL-2.0",
    "isc": "ISC",
    "unlicense": "Unlicense",
    "agpl": "AGPL-3.0",
}


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?(?:[+-]\w+)?)")
_METRIC_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(%|ms|s|sec|seconds|min|minutes|hz|Hz|MB|GB|TB|KB"
    r"|req/s|rps|qps|tps|fps|Mbps|Gbps|rpm|k|K|M)",
)
_API_PATH_RE = re.compile(r"`?(/api/\S+|/v\d+/\S+)`?")
_HTTP_METHOD_RE = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\b")
_MERMAID_EDGE_RE = re.compile(r"(\w[\w\s]*?)\s*-->?\|?([^|]*?)\|?\s*(\w[\w\s]*?)$", re.MULTILINE)
_MERMAID_NODE_RE = re.compile(r"(\w+)\[([^\]]+)\]")


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class SemanticExtractor:
    """Deterministic semantic entity and relation extractor.

    Scans a ``DocumentModel`` for known technologies, patterns, and
    structural cues, and produces a ``KnowledgeGraph``.
    """

    def extract(self, doc: DocumentModel) -> KnowledgeGraph:
        """Run all extraction passes and return a merged KG."""
        kg = KnowledgeGraph()

        # Pass 1: Project entity
        self._extract_project(doc, kg)

        # Pass 2: Dictionary-based entity scanning
        self._extract_from_text(doc, kg)

        # Pass 3: Code block language → technology
        self._extract_from_code_blocks(doc, kg)

        # Pass 4: Table structure heuristics
        self._extract_from_tables(doc, kg)

        # Pass 5: Mermaid diagram → relationships
        self._extract_from_mermaid(doc, kg)

        # Pass 6: List items → features
        self._extract_from_lists(doc, kg)

        # Pass 7: Metrics
        self._extract_metrics(doc, kg)

        # Pass 8: API endpoints
        self._extract_api_endpoints(doc, kg)

        # Pass 9: Infer relationships
        self._infer_relations(kg)

        # Compute stats
        kg.compute_stats()
        kg.summary = self._generate_summary(kg, doc)

        return kg

    # ------------------------------------------------------------------
    # Pass 1: Project entity
    # ------------------------------------------------------------------

    def _extract_project(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        project = Entity(
            id="project_root",
            name=doc.metadata.repo_name or "Unknown Project",
            entity_type=EntityType.PROJECT,
            properties={
                "url": doc.metadata.repo_url,
                "description": doc.metadata.description,
            },
            source_section="metadata",
            confidence=1.0,
        )
        kg.add_entity(project)

    # ------------------------------------------------------------------
    # Pass 2: Dictionary scanning
    # ------------------------------------------------------------------

    def _extract_from_text(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        full_text = doc.raw_markdown.lower()

        for name, props in _LANGUAGES.items():
            if self._word_match(name, full_text):
                canonical = props.get("canonical", name.title())
                eid = self._make_id("lang", canonical)
                kg.add_entity(Entity(
                    id=eid, name=canonical,
                    entity_type=EntityType.LANGUAGE,
                    properties=props, confidence=0.9,
                ))
                kg.add_relation(Relation(
                    source_id="project_root", target_id=eid,
                    relation_type=RelationType.USES, confidence=0.9,
                ))

        for name, props in _FRAMEWORKS.items():
            if self._word_match(name, full_text):
                canonical = props.get("canonical", name.title())
                eid = self._make_id("fw", canonical)
                kg.add_entity(Entity(
                    id=eid, name=canonical,
                    entity_type=EntityType.FRAMEWORK,
                    properties=props, confidence=0.85,
                ))
                kg.add_relation(Relation(
                    source_id="project_root", target_id=eid,
                    relation_type=RelationType.USES, confidence=0.85,
                ))

        for name, props in _DATABASES.items():
            if self._word_match(name, full_text):
                canonical = props.get("canonical", name.title())
                eid = self._make_id("db", canonical)
                kg.add_entity(Entity(
                    id=eid, name=canonical,
                    entity_type=EntityType.DATABASE,
                    properties=props, confidence=0.9,
                ))
                kg.add_relation(Relation(
                    source_id="project_root", target_id=eid,
                    relation_type=RelationType.STORES_IN, confidence=0.8,
                ))

        for name, props in _PROTOCOLS.items():
            if self._word_match(name, full_text):
                canonical = props.get("canonical", name.upper())
                eid = self._make_id("proto", canonical)
                kg.add_entity(Entity(
                    id=eid, name=canonical,
                    entity_type=EntityType.PROTOCOL,
                    properties=props, confidence=0.9,
                ))
                kg.add_relation(Relation(
                    source_id="project_root", target_id=eid,
                    relation_type=RelationType.COMMUNICATES_VIA, confidence=0.85,
                ))

        for name, props in _CLOUD_SERVICES.items():
            if name.lower() in full_text:
                canonical = props.get("canonical", name.title())
                eid = self._make_id("cloud", canonical)
                kg.add_entity(Entity(
                    id=eid, name=canonical,
                    entity_type=EntityType.CLOUD_SERVICE,
                    properties=props, confidence=0.85,
                ))
                kg.add_relation(Relation(
                    source_id="project_root", target_id=eid,
                    relation_type=RelationType.INTEGRATES_WITH, confidence=0.8,
                ))

        for name, props in _HARDWARE.items():
            if self._word_match(name, full_text):
                canonical = props.get("canonical", name.title())
                eid = self._make_id("hw", canonical)
                kg.add_entity(Entity(
                    id=eid, name=canonical,
                    entity_type=EntityType.HARDWARE,
                    properties=props, confidence=0.9,
                ))
                kg.add_relation(Relation(
                    source_id="project_root", target_id=eid,
                    relation_type=RelationType.USES, confidence=0.85,
                ))

        for name, props in _PLATFORMS.items():
            if self._word_match(name, full_text):
                canonical = props.get("canonical", name.title())
                eid = self._make_id("plat", canonical)
                kg.add_entity(Entity(
                    id=eid, name=canonical,
                    entity_type=EntityType.PLATFORM,
                    properties=props, confidence=0.8,
                ))

        for name, canonical in _LICENSES.items():
            if name in full_text:
                eid = self._make_id("lic", canonical)
                kg.add_entity(Entity(
                    id=eid, name=canonical,
                    entity_type=EntityType.LICENSE_TYPE,
                    confidence=0.95,
                ))
                kg.add_relation(Relation(
                    source_id="project_root", target_id=eid,
                    relation_type=RelationType.LICENSED_UNDER, confidence=0.95,
                ))
                break  # Usually only one license

    # ------------------------------------------------------------------
    # Pass 3: Code blocks
    # ------------------------------------------------------------------

    def _extract_from_code_blocks(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        # Only real programming languages, not data formats
        lang_to_type = {
            "python": "Python", "py": "Python",
            "javascript": "JavaScript", "js": "JavaScript",
            "typescript": "TypeScript", "ts": "TypeScript",
            "java": "Java", "go": "Go", "rust": "Rust",
            "ruby": "Ruby", "php": "PHP", "bash": "Bash",
            "shell": "Shell", "dockerfile": "Docker",
        }

        for block in doc.all_blocks:
            if isinstance(block, CodeBlock) and block.language:
                lang_key = block.language.lower().strip()
                if lang_key in lang_to_type:
                    name = lang_to_type[lang_key]
                    eid = self._make_id("lang", name)
                    kg.add_entity(Entity(
                        id=eid, name=name,
                        entity_type=EntityType.LANGUAGE,
                        confidence=0.95,
                    ))

                # Extract config keys
                if lang_key in ("yaml", "yml", "json", "toml"):
                    self._extract_config_keys(block.code, kg)

    def _extract_config_keys(self, code: str, kg: KnowledgeGraph) -> None:
        """Extract top-level config keys from YAML/JSON."""
        config_re = re.compile(r"^(\w[\w_-]*):", re.MULTILINE)
        for m in config_re.finditer(code):
            key = m.group(1)
            if len(key) > 2 and key not in ("type", "name", "version", "description"):
                eid = self._make_id("cfg", key)
                kg.add_entity(Entity(
                    id=eid, name=key,
                    entity_type=EntityType.CONFIGURATION,
                    properties={"format": "yaml/json"},
                    confidence=0.7,
                ))

    # ------------------------------------------------------------------
    # Pass 4: Tables
    # ------------------------------------------------------------------

    def _extract_from_tables(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        for block in doc.all_blocks:
            if not isinstance(block, TableBlock) or not block.headers:
                continue

            headers_lower = [h.lower() for h in block.headers]

            # API endpoint tables
            if any(kw in " ".join(headers_lower) for kw in ["endpoint", "route", "path", "url"]):
                self._extract_api_table(block, kg)

            # Metric tables
            elif any(kw in " ".join(headers_lower) for kw in ["metric", "value", "performance"]):
                self._extract_metric_table(block, kg)

    def _extract_api_table(self, table: TableBlock, kg: KnowledgeGraph) -> None:
        headers_lower = [h.lower() for h in table.headers]
        path_col = next((i for i, h in enumerate(headers_lower) if "endpoint" in h or "path" in h or "route" in h), None)
        method_col = next((i for i, h in enumerate(headers_lower) if "method" in h), None)
        desc_col = next((i for i, h in enumerate(headers_lower) if "description" in h or "desc" in h), None)

        for row in table.rows:
            if path_col is not None and path_col < len(row):
                path = row[path_col].strip("`").strip()
                method = row[method_col].strip() if method_col is not None and method_col < len(row) else ""
                desc = row[desc_col].strip() if desc_col is not None and desc_col < len(row) else ""

                eid = self._make_id("api", f"{method}_{path}")
                kg.add_entity(Entity(
                    id=eid, name=f"{method} {path}" if method else path,
                    entity_type=EntityType.API_ENDPOINT,
                    properties={"path": path, "method": method, "description": desc},
                    confidence=0.95,
                ))
                kg.add_relation(Relation(
                    source_id="project_root", target_id=eid,
                    relation_type=RelationType.EXPOSES, confidence=0.95,
                ))

    def _extract_metric_table(self, table: TableBlock, kg: KnowledgeGraph) -> None:
        headers_lower = [h.lower() for h in table.headers]
        name_col = next((i for i, h in enumerate(headers_lower) if "metric" in h or "name" in h), 0)
        value_col = next((i for i, h in enumerate(headers_lower) if "value" in h), 1 if len(headers_lower) > 1 else None)

        for row in table.rows:
            if name_col < len(row):
                metric_name = row[name_col].strip()
                metric_val = row[value_col].strip() if value_col is not None and value_col < len(row) else ""

                eid = self._make_id("metric", metric_name)
                kg.add_entity(Entity(
                    id=eid, name=metric_name,
                    entity_type=EntityType.METRIC,
                    properties={"value": metric_val},
                    confidence=0.9,
                ))

    # ------------------------------------------------------------------
    # Pass 5: Mermaid diagrams
    # ------------------------------------------------------------------

    def _extract_from_mermaid(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        for code in doc.mermaid_diagrams:
            # Extract named nodes
            for m in _MERMAID_NODE_RE.finditer(code):
                node_id = m.group(1).strip()
                node_label = m.group(2).strip()
                eid = self._make_id("comp", node_label)
                kg.add_entity(Entity(
                    id=eid, name=node_label,
                    entity_type=EntityType.COMPONENT,
                    properties={"mermaid_id": node_id},
                    source_text=code,
                    confidence=0.85,
                ))

            # Extract edges
            for m in _MERMAID_EDGE_RE.finditer(code):
                src = m.group(1).strip()
                label = m.group(2).strip()
                tgt = m.group(3).strip()

                # Resolve to entity IDs
                src_id = self._find_mermaid_entity(src, kg) or self._make_id("comp", src)
                tgt_id = self._find_mermaid_entity(tgt, kg) or self._make_id("comp", tgt)

                # Ensure entities exist
                for eid, name in [(src_id, src), (tgt_id, tgt)]:
                    if not kg.get_entity(eid):
                        kg.add_entity(Entity(
                            id=eid, name=name,
                            entity_type=EntityType.COMPONENT,
                            confidence=0.7,
                        ))

                kg.add_relation(Relation(
                    source_id=src_id, target_id=tgt_id,
                    relation_type=RelationType.CONNECTS_TO,
                    properties={"label": label} if label else {},
                    confidence=0.8,
                ))

    def _find_mermaid_entity(self, mermaid_ref: str, kg: KnowledgeGraph) -> str | None:
        """Find an entity ID matching a mermaid node reference."""
        for e in kg.entities:
            if e.properties.get("mermaid_id") == mermaid_ref:
                return e.id
            if e.name.lower() == mermaid_ref.lower():
                return e.id
        return None

    # ------------------------------------------------------------------
    # Pass 6: Lists → features
    # ------------------------------------------------------------------

    def _extract_from_lists(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        in_features = False
        for block in doc.all_blocks:
            if isinstance(block, HeadingBlock):
                in_features = any(
                    kw in block.text.lower()
                    for kw in ["feature", "highlights", "capabilities", "what it does"]
                )
            elif isinstance(block, ListBlock) and in_features:
                for item in block.items[:15]:  # Cap at 15
                    # Strip bold markers, extract first meaningful phrase
                    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", item)
                    name = clean.split(":")[0].split("—")[0].split("–")[0].strip()[:80]
                    if len(name) > 3:
                        eid = self._make_id("feat", name)
                        kg.add_entity(Entity(
                            id=eid, name=name,
                            entity_type=EntityType.FEATURE,
                            properties={"description": clean[:200]},
                            confidence=0.75,
                        ))
                        kg.add_relation(Relation(
                            source_id="project_root", target_id=eid,
                            relation_type=RelationType.PROVIDES, confidence=0.75,
                        ))

    # ------------------------------------------------------------------
    # Pass 7: Metrics from text
    # ------------------------------------------------------------------

    def _extract_metrics(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        for block in doc.all_blocks:
            if isinstance(block, ParagraphBlock):
                for m in _METRIC_RE.finditer(block.text):
                    value = m.group(1)
                    unit = m.group(2)
                    context = block.text[max(0, m.start() - 30):m.end() + 20].strip()
                    eid = self._make_id("metric", f"{value}{unit}")
                    kg.add_entity(Entity(
                        id=eid, name=f"{value} {unit}",
                        entity_type=EntityType.METRIC,
                        properties={"value": value, "unit": unit, "context": context},
                        source_text=context,
                        confidence=0.7,
                    ))

    # ------------------------------------------------------------------
    # Pass 8: API endpoints from text
    # ------------------------------------------------------------------

    def _extract_api_endpoints(self, doc: DocumentModel, kg: KnowledgeGraph) -> None:
        for block in doc.all_blocks:
            text = ""
            if isinstance(block, ParagraphBlock):
                text = block.text
            elif isinstance(block, CodeBlock):
                text = block.code

            for m in _API_PATH_RE.finditer(text):
                path = m.group(1).strip("`").strip()
                # Check for adjacent HTTP method
                before = text[max(0, m.start() - 10):m.start()]
                method_m = _HTTP_METHOD_RE.search(before)
                method = method_m.group(1) if method_m else ""

                eid = self._make_id("api", f"{method}_{path}")
                if not kg.get_entity(eid):
                    kg.add_entity(Entity(
                        id=eid, name=f"{method} {path}" if method else path,
                        entity_type=EntityType.API_ENDPOINT,
                        properties={"path": path, "method": method},
                        confidence=0.8,
                    ))
                    kg.add_relation(Relation(
                        source_id="project_root", target_id=eid,
                        relation_type=RelationType.EXPOSES, confidence=0.8,
                    ))

    # ------------------------------------------------------------------
    # Pass 9: Infer relationships
    # ------------------------------------------------------------------

    def _infer_relations(self, kg: KnowledgeGraph) -> None:
        """Infer additional relations from entity co-occurrence and types."""
        components = kg.entities_of_type(EntityType.COMPONENT)
        databases = kg.entities_of_type(EntityType.DATABASE)
        protocols = kg.entities_of_type(EntityType.PROTOCOL)

        # Components → Databases
        for comp in components:
            for db in databases:
                if db.name.lower() in comp.name.lower() or comp.name.lower() in db.name.lower():
                    kg.add_relation(Relation(
                        source_id=comp.id, target_id=db.id,
                        relation_type=RelationType.STORES_IN,
                        confidence=0.6,
                    ))

        # Components → Protocols
        for comp in components:
            for proto in protocols:
                if proto.name.lower() in comp.name.lower():
                    kg.add_relation(Relation(
                        source_id=comp.id, target_id=proto.id,
                        relation_type=RelationType.COMMUNICATES_VIA,
                        confidence=0.6,
                    ))

        # Hardware → Platform (runs_on)
        hardware = kg.entities_of_type(EntityType.HARDWARE)
        platforms = kg.entities_of_type(EntityType.PLATFORM)
        for hw in hardware:
            for plat in platforms:
                if any(kw in plat.name.lower() for kw in ["linux", "ubuntu"]):
                    if hw.properties.get("type") == "sbc":
                        kg.add_relation(Relation(
                            source_id=hw.id, target_id=plat.id,
                            relation_type=RelationType.RUNS_ON,
                            confidence=0.5,
                        ))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_summary(kg: KnowledgeGraph, doc: DocumentModel) -> str:
        """Generate a human-readable summary of the KG."""
        parts = [f"Knowledge graph for '{doc.metadata.repo_name or 'project'}':\n"]

        stats = kg.extraction_stats
        parts.append(f"  • {stats.get('total_entities', 0)} entities extracted")
        parts.append(f"  • {stats.get('total_relations', 0)} relationships identified")

        type_summary = []
        for et in EntityType:
            count = stats.get(f"entities_{et.value}", 0)
            if count > 0:
                type_summary.append(f"{count} {et.value}(s)")
        if type_summary:
            parts.append(f"  • Types: {', '.join(type_summary)}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _make_id(prefix: str, name: str) -> str:
        """Create a stable entity ID from a prefix and name."""
        safe = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50]
        return f"{prefix}_{safe}"

    @staticmethod
    def _word_match(word: str, text: str) -> bool:
        """Check if *word* appears as a whole word in *text*.

        For very short words (<=3 chars) that are common English words,
        require them to appear in a technical context (e.g. code fences,
        backticks, alongside other tech terms) to avoid false positives
        like 'go' matching 'go to' or 'r' matching articles.
        """
        # Common English words that also happen to be language/tech names
        _AMBIGUOUS_SHORT = {"go", "r", "c", "dart"}
        pattern = r"\b" + re.escape(word) + r"\b"
        if len(word) <= 3 and word.lower() in _AMBIGUOUS_SHORT:
            # Require the word in a technical context:
            # - in a code fence: ```go
            # - in backticks: `go`
            # - preceded/followed by comma in a tech list
            # - in an install command
            tech_patterns = [
                r"```\s*" + re.escape(word) + r"\b",       # code fence
                r"`" + re.escape(word) + r"`",               # inline code
                r"(?:written\s+in|built\s+with|using|language[s]?[:\s]+\w*\s*)" + re.escape(word) + r"\b",
            ]
            for tp in tech_patterns:
                if re.search(tp, text, re.IGNORECASE):
                    return True
            return False
        return bool(re.search(pattern, text, re.IGNORECASE))
