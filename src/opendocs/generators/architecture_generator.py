"""Auto-generate architecture Mermaid diagrams from the Knowledge Graph.

Produces multiple architecture views as ``.mmd`` (Mermaid source) files,
renders them to PNG, and writes a combined Markdown report with all
diagrams embedded.

Diagram types generated:

1. **System Architecture** — C4-style component diagram showing the
   project, its major components/features, and external integrations.
2. **Tech Stack Layers** — Layered view grouping technologies by role
   (frontend, backend, data, infrastructure, tooling).
3. **Data Flow** — How data moves between components (stores_in,
   connects_to, communicates_via relations).
4. **Dependency Tree** — What depends on what (requires, depends_on).
5. **Deployment View** — Cloud services, platforms, and what runs on them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ..core.knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relation,
    RelationType,
)
from ..core.models import DocumentModel, GenerationResult, OutputFormat
from .base import BaseGenerator
from .mermaid_renderer import MermaidRenderer

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_id(raw: str) -> str:
    """Make a string safe for use as a Mermaid node ID."""
    return raw.replace("-", "_").replace(" ", "_").replace(".", "_").replace("/", "_")


def _safe_label(raw: str) -> str:
    """Escape quotes for Mermaid labels."""
    return raw.replace('"', "'").replace("\n", " ")


def _entity_icon(etype: EntityType) -> str:
    """Return a small prefix icon string for entity types."""
    icons = {
        EntityType.PROJECT: "fas:fa-cube",
        EntityType.COMPONENT: "fas:fa-puzzle-piece",
        EntityType.TECHNOLOGY: "fas:fa-microchip",
        EntityType.LANGUAGE: "fas:fa-code",
        EntityType.FRAMEWORK: "fas:fa-layer-group",
        EntityType.DATABASE: "fas:fa-database",
        EntityType.CLOUD_SERVICE: "fas:fa-cloud",
        EntityType.API_ENDPOINT: "fas:fa-plug",
        EntityType.PROTOCOL: "fas:fa-exchange-alt",
        EntityType.PLATFORM: "fas:fa-server",
        EntityType.HARDWARE: "fas:fa-hdd",
        EntityType.FEATURE: "fas:fa-star",
    }
    return icons.get(etype, "")


# ── Shape helpers for different entity types ──────────────────────────────

def _node(entity: Entity, *, shape: str = "default") -> str:
    """Return a Mermaid node declaration with an appropriate shape."""
    nid = _safe_id(entity.id)
    label = _safe_label(entity.name)
    if shape == "stadium":
        return f'{nid}(["{label}"])'
    elif shape == "cylinder":
        return f'{nid}[("{label}")]'
    elif shape == "hexagon":
        return f'{nid}{{{{"{label}"}}}}'
    elif shape == "parallelogram":
        return f'{nid}[/"{label}"/]'
    elif shape == "subroutine":
        return f'{nid}[["{label}"]]'
    elif shape == "trapezoid":
        return f'{nid}[/"{label}"\\]'
    else:
        return f'{nid}["{label}"]'


def _shape_for(etype: EntityType) -> str:
    """Pick a Mermaid node shape based on entity type."""
    mapping = {
        EntityType.PROJECT: "stadium",
        EntityType.DATABASE: "cylinder",
        EntityType.CLOUD_SERVICE: "parallelogram",
        EntityType.API_ENDPOINT: "subroutine",
        EntityType.PLATFORM: "hexagon",
        EntityType.HARDWARE: "hexagon",
    }
    return mapping.get(etype, "default")


# ── Relation labels ───────────────────────────────────────────────────────

_EDGE_STYLE: dict[RelationType, str] = {
    RelationType.USES: "-->",
    RelationType.CONNECTS_TO: "<-->",
    RelationType.EXPOSES: "-..->",
    RelationType.REQUIRES: "-->",
    RelationType.STORES_IN: "-->",
    RelationType.COMMUNICATES_VIA: "<-->",
    RelationType.DEPENDS_ON: "-->",
    RelationType.RUNS_ON: "-->",
    RelationType.PROVIDES: "-..->",
    RelationType.INTEGRATES_WITH: "<-->",
    RelationType.PART_OF: "-->",
}


# ═══════════════════════════════════════════════════════════════════════════
# Diagram builders
# ═══════════════════════════════════════════════════════════════════════════

def _build_system_architecture(kg: KnowledgeGraph, project_name: str) -> str | None:
    """C4-style system context / component diagram.

    Shows the project at the center, its components/features around it,
    and external technologies/services at the periphery.
    """
    projects = kg.entities_of_type(EntityType.PROJECT)
    components = kg.entities_of_type(EntityType.COMPONENT)
    features = kg.entities_of_type(EntityType.FEATURE)
    frameworks = kg.entities_of_type(EntityType.FRAMEWORK)
    databases = kg.entities_of_type(EntityType.DATABASE)
    cloud = kg.entities_of_type(EntityType.CLOUD_SERVICE)
    apis = kg.entities_of_type(EntityType.API_ENDPOINT)

    # Need at least a project + some substance
    if not projects and not components and not features:
        return None

    lines = [
        "graph TB",
        f'    classDef project fill:#4A90D9,stroke:#2C5F8A,color:#fff,stroke-width:3px',
        f'    classDef component fill:#67B7DC,stroke:#4A90D9,color:#fff,stroke-width:2px',
        f'    classDef feature fill:#7EC8E3,stroke:#67B7DC,color:#333',
        f'    classDef framework fill:#F5A623,stroke:#D4891C,color:#fff',
        f'    classDef database fill:#50C878,stroke:#3BA35C,color:#fff',
        f'    classDef cloud fill:#9B59B6,stroke:#7D3C98,color:#fff',
        f'    classDef api fill:#E74C3C,stroke:#C0392B,color:#fff',
    ]

    # Project node
    proj_entity = projects[0] if projects else None
    proj_label = _safe_label(proj_entity.name if proj_entity else project_name)
    proj_id = _safe_id(proj_entity.id if proj_entity else "project_main")
    lines.append(f'    {proj_id}(["{proj_label}"]):::project')

    # Components subgraph
    if components:
        lines.append('    subgraph Components["Core Components"]')
        for e in components[:10]:
            lines.append(f'        {_node(e, shape="default")}:::component')
        lines.append("    end")
        lines.append(f"    {proj_id} --> Components")

    # Features subgraph
    if features:
        lines.append('    subgraph Features["Key Features"]')
        for e in features[:10]:
            lines.append(f'        {_node(e)}:::feature')
        lines.append("    end")
        if not components:
            lines.append(f"    {proj_id} --> Features")
        else:
            lines.append("    Components --> Features")

    # External services on the right
    external_nodes = []
    if frameworks:
        lines.append('    subgraph Frameworks["Frameworks & Libraries"]')
        for e in frameworks[:8]:
            lines.append(f'        {_node(e)}:::framework')
            external_nodes.append(e)
        lines.append("    end")

    if databases:
        lines.append('    subgraph DataStores["Data Stores"]')
        for e in databases[:6]:
            lines.append(f'        {_node(e, shape="cylinder")}:::database')
            external_nodes.append(e)
        lines.append("    end")

    if cloud:
        lines.append('    subgraph Cloud["Cloud & Infrastructure"]')
        for e in cloud[:6]:
            lines.append(f'        {_node(e, shape="parallelogram")}:::cloud')
            external_nodes.append(e)
        lines.append("    end")

    if apis:
        lines.append('    subgraph APIs["API Endpoints"]')
        for e in apis[:6]:
            lines.append(f'        {_node(e, shape="subroutine")}:::api')
            external_nodes.append(e)
        lines.append("    end")

    # Draw relations between included nodes
    included_ids = {e.id for e in (
        projects + components + features + frameworks
        + databases + cloud + apis
    )}
    seen_edges: set[str] = set()
    for r in kg.relations:
        if r.source_id in included_ids and r.target_id in included_ids:
            src = _safe_id(r.source_id)
            tgt = _safe_id(r.target_id)
            edge_key = f"{src}->{tgt}"
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                arrow = _EDGE_STYLE.get(r.relation_type, "-->")
                label = r.relation_type.value.replace("_", " ")
                lines.append(f"    {src} {arrow}|{label}| {tgt}")

    return "\n".join(lines)


def _build_tech_stack(kg: KnowledgeGraph) -> str | None:
    """Layered tech-stack diagram grouping by role.

    Layers (top → bottom): Frontend → Backend → Data → Infrastructure → Tooling
    """
    languages = kg.entities_of_type(EntityType.LANGUAGE)
    frameworks = kg.entities_of_type(EntityType.FRAMEWORK)
    databases = kg.entities_of_type(EntityType.DATABASE)
    cloud = kg.entities_of_type(EntityType.CLOUD_SERVICE)
    platforms = kg.entities_of_type(EntityType.PLATFORM)
    technologies = kg.entities_of_type(EntityType.TECHNOLOGY)
    protocols = kg.entities_of_type(EntityType.PROTOCOL)

    total = (len(languages) + len(frameworks) + len(databases)
             + len(cloud) + len(platforms) + len(technologies))
    if total < 2:
        return None

    # Classify frameworks by category
    frontend_fw, backend_fw, ml_fw, other_fw = [], [], [], []
    for f in frameworks:
        cat = f.properties.get("category", "")
        if cat in ("frontend", "css"):
            frontend_fw.append(f)
        elif cat in ("backend", "fullstack"):
            backend_fw.append(f)
        elif cat in ("ml", "llm"):
            ml_fw.append(f)
        else:
            other_fw.append(f)

    lines = [
        "graph TB",
        '    classDef frontend fill:#61DAFB,stroke:#21A1C4,color:#333',
        '    classDef backend fill:#68A063,stroke:#4A7A45,color:#fff',
        '    classDef data fill:#336791,stroke:#1E3F5A,color:#fff',
        '    classDef infra fill:#FF9900,stroke:#CC7A00,color:#fff',
        '    classDef lang fill:#F7DF1E,stroke:#C4B118,color:#333',
        '    classDef tool fill:#8E8E93,stroke:#636366,color:#fff',
    ]

    subgraph_ids = []

    # Frontend layer
    fe_items = frontend_fw
    if fe_items:
        lines.append('    subgraph Frontend["Frontend"]')
        for e in fe_items[:6]:
            lines.append(f'        {_node(e)}:::frontend')
        lines.append("    end")
        subgraph_ids.append("Frontend")

    # Backend layer
    be_items = backend_fw + ml_fw + other_fw
    if be_items:
        lines.append('    subgraph Backend["Backend & Frameworks"]')
        for e in be_items[:8]:
            lines.append(f'        {_node(e)}:::backend')
        lines.append("    end")
        subgraph_ids.append("Backend")

    # Languages
    if languages:
        lines.append('    subgraph Languages["Languages"]')
        for e in languages[:8]:
            lines.append(f'        {_node(e)}:::lang')
        lines.append("    end")
        subgraph_ids.append("Languages")

    # Data layer
    data_items = databases
    if data_items:
        lines.append('    subgraph Data["Data Layer"]')
        for e in data_items[:6]:
            lines.append(f'        {_node(e, shape="cylinder")}:::data')
        lines.append("    end")
        subgraph_ids.append("Data")

    # Infrastructure layer
    infra_items = cloud + platforms
    if infra_items:
        lines.append('    subgraph Infrastructure["Infrastructure"]')
        for e in infra_items[:6]:
            lines.append(f'        {_node(e, shape="parallelogram")}:::infra')
        lines.append("    end")
        subgraph_ids.append("Infrastructure")

    # Protocols / Technologies as tooling
    tool_items = technologies + protocols
    if tool_items:
        lines.append('    subgraph Tooling["Protocols & Tools"]')
        for e in tool_items[:6]:
            lines.append(f'        {_node(e)}:::tool')
        lines.append("    end")
        subgraph_ids.append("Tooling")

    # Connect layers top-to-bottom
    for i in range(len(subgraph_ids) - 1):
        lines.append(f"    {subgraph_ids[i]} ~~~ {subgraph_ids[i + 1]}")

    return "\n".join(lines)


def _build_data_flow(kg: KnowledgeGraph) -> str | None:
    """Data-flow diagram showing storage, communication, and integration edges."""
    data_relations = {
        RelationType.STORES_IN,
        RelationType.CONNECTS_TO,
        RelationType.COMMUNICATES_VIA,
        RelationType.EXPOSES,
        RelationType.INTEGRATES_WITH,
    }

    relevant = [r for r in kg.relations if r.relation_type in data_relations]
    if len(relevant) < 2:
        return None

    # Collect involved entities
    involved_ids = set()
    for r in relevant:
        involved_ids.add(r.source_id)
        involved_ids.add(r.target_id)

    entities_map = {e.id: e for e in kg.entities if e.id in involved_ids}

    lines = [
        "graph LR",
        '    classDef source fill:#4A90D9,stroke:#2C5F8A,color:#fff',
        '    classDef store fill:#50C878,stroke:#3BA35C,color:#fff',
        '    classDef service fill:#9B59B6,stroke:#7D3C98,color:#fff',
    ]

    # Declare nodes
    for eid, e in entities_map.items():
        shape = _shape_for(e.entity_type)
        cls = "store" if e.entity_type == EntityType.DATABASE else (
            "service" if e.entity_type in (EntityType.CLOUD_SERVICE, EntityType.API_ENDPOINT)
            else "source"
        )
        lines.append(f"    {_node(e, shape=shape)}:::{cls}")

    # Edges
    seen: set[str] = set()
    for r in relevant:
        src = _safe_id(r.source_id)
        tgt = _safe_id(r.target_id)
        key = f"{src}->{tgt}"
        if key not in seen:
            seen.add(key)
            arrow = _EDGE_STYLE.get(r.relation_type, "-->")
            label = r.relation_type.value.replace("_", " ")
            lines.append(f"    {src} {arrow}|{label}| {tgt}")

    return "\n".join(lines)


def _build_dependency_tree(kg: KnowledgeGraph) -> str | None:
    """Dependency tree showing requires / depends_on / uses."""
    dep_relations = {
        RelationType.REQUIRES,
        RelationType.DEPENDS_ON,
        RelationType.USES,
    }

    relevant = [r for r in kg.relations if r.relation_type in dep_relations]
    if len(relevant) < 2:
        return None

    involved_ids = set()
    for r in relevant:
        involved_ids.add(r.source_id)
        involved_ids.add(r.target_id)

    entities_map = {e.id: e for e in kg.entities if e.id in involved_ids}

    lines = [
        "graph TD",
        '    classDef core fill:#4A90D9,stroke:#2C5F8A,color:#fff,stroke-width:2px',
        '    classDef dep fill:#F5A623,stroke:#D4891C,color:#fff',
        '    classDef prereq fill:#E74C3C,stroke:#C0392B,color:#fff',
    ]

    for eid, e in entities_map.items():
        shape = _shape_for(e.entity_type)
        cls = "prereq" if e.entity_type == EntityType.PREREQUISITE else (
            "core" if e.entity_type in (EntityType.PROJECT, EntityType.COMPONENT)
            else "dep"
        )
        lines.append(f"    {_node(e, shape=shape)}:::{cls}")

    seen: set[str] = set()
    for r in relevant:
        src = _safe_id(r.source_id)
        tgt = _safe_id(r.target_id)
        key = f"{src}->{tgt}"
        if key not in seen:
            seen.add(key)
            label = r.relation_type.value.replace("_", " ")
            lines.append(f"    {src} -->|{label}| {tgt}")

    return "\n".join(lines)


def _build_deployment_view(kg: KnowledgeGraph) -> str | None:
    """Deployment diagram: what runs on which platform / cloud service."""
    cloud = kg.entities_of_type(EntityType.CLOUD_SERVICE)
    platforms = kg.entities_of_type(EntityType.PLATFORM)
    hardware = kg.entities_of_type(EntityType.HARDWARE)

    hosts = cloud + platforms + hardware
    if not hosts:
        return None

    # Find RUNS_ON relations
    runs_on = [r for r in kg.relations if r.relation_type == RelationType.RUNS_ON]

    # Also gather anything that connects to these hosts
    host_ids = {e.id for e in hosts}
    host_relations = [
        r for r in kg.relations
        if r.target_id in host_ids or r.source_id in host_ids
    ]
    if not host_relations and len(hosts) < 2:
        return None

    involved_ids = set()
    for r in host_relations:
        involved_ids.add(r.source_id)
        involved_ids.add(r.target_id)
    for e in hosts:
        involved_ids.add(e.id)

    entities_map = {e.id: e for e in kg.entities if e.id in involved_ids}

    lines = [
        "graph TB",
        '    classDef host fill:#FF9900,stroke:#CC7A00,color:#fff,stroke-width:2px',
        '    classDef app fill:#4A90D9,stroke:#2C5F8A,color:#fff',
        '    classDef hw fill:#8E8E93,stroke:#636366,color:#fff',
    ]

    # Host subgraph
    lines.append('    subgraph Hosts["Deployment Targets"]')
    for e in hosts[:8]:
        shape = "hexagon" if e.entity_type == EntityType.HARDWARE else "parallelogram"
        cls = "hw" if e.entity_type == EntityType.HARDWARE else "host"
        lines.append(f'        {_node(e, shape=shape)}:::{cls}')
    lines.append("    end")

    # App nodes
    app_entities = [
        entities_map[eid] for eid in involved_ids
        if eid not in host_ids and eid in entities_map
    ]
    if app_entities:
        lines.append('    subgraph Applications["Applications & Services"]')
        for e in app_entities[:10]:
            lines.append(f'        {_node(e)}:::app')
        lines.append("    end")

    # Edges
    seen: set[str] = set()
    for r in host_relations:
        src = _safe_id(r.source_id)
        tgt = _safe_id(r.target_id)
        key = f"{src}->{tgt}"
        if key not in seen:
            seen.add(key)
            arrow = _EDGE_STYLE.get(r.relation_type, "-->")
            label = r.relation_type.value.replace("_", " ")
            lines.append(f"    {src} {arrow}|{label}| {tgt}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════════

# Diagram spec: (builder_function, filename_stem, title)
_DIAGRAM_SPECS: list[tuple] = [
    (_build_system_architecture, "system_architecture", "System Architecture"),
    (_build_tech_stack, "tech_stack", "Technology Stack"),
    (_build_data_flow, "data_flow", "Data Flow"),
    (_build_dependency_tree, "dependency_tree", "Dependency Tree"),
    (_build_deployment_view, "deployment_view", "Deployment View"),
]


class ArchitectureGenerator(BaseGenerator):
    """Generate architecture Mermaid diagrams from the Knowledge Graph.

    Produces:
      - Individual ``.mmd`` source files
      - Rendered ``.png`` images for each diagram
      - A combined ``_architecture.md`` report with all diagrams
    """

    format = OutputFormat.ARCHITECTURE

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.renderer: MermaidRenderer | None = None

    def generate(self, doc: DocumentModel, output_dir: Path) -> GenerationResult:
        output_dir = Path(output_dir)
        arch_dir = output_dir / "architecture"
        arch_dir.mkdir(parents=True, exist_ok=True)

        if not self.kg or not self.kg.entities:
            return GenerationResult(
                format=self.format,
                output_path=arch_dir,
                success=False,
                error="No knowledge graph entities — cannot generate architecture diagrams.",
            )

        project_name = doc.metadata.repo_name or "Project"

        # Initialise the Mermaid renderer
        renderer = self.renderer or MermaidRenderer(
            cache_dir=arch_dir / "rendered",
        )

        diagrams_built: list[dict] = []

        for builder, stem, title in _DIAGRAM_SPECS:
            # _build_system_architecture needs extra arg
            if builder is _build_system_architecture:
                mermaid_src = builder(self.kg, project_name)
            else:
                mermaid_src = builder(self.kg)

            if mermaid_src is None:
                logger.debug("Skipped %s — not enough data", stem)
                continue

            # Write .mmd file
            mmd_path = arch_dir / f"{stem}.mmd"
            mmd_path.write_text(mermaid_src, encoding="utf-8")

            # Render to PNG
            png_path = renderer.render(mermaid_src, label=stem)

            diagrams_built.append({
                "title": title,
                "stem": stem,
                "mmd_path": mmd_path,
                "png_path": png_path,
                "mermaid_src": mermaid_src,
            })

        if not diagrams_built:
            return GenerationResult(
                format=self.format,
                output_path=arch_dir,
                success=False,
                error="Not enough entity/relation data to generate any architecture diagrams.",
            )

        # Build combined Markdown report
        md_lines = [
            f"# Architecture Diagrams — {project_name}",
            "",
            f"> Auto-generated by OpenDocs from the project's README.",
            f"> {len(diagrams_built)} architecture view(s) produced.",
            "",
            "---",
            "",
        ]

        for d in diagrams_built:
            md_lines.append(f"## {d['title']}")
            md_lines.append("")

            if d["png_path"]:
                rel = Path(d["png_path"]).relative_to(arch_dir)
                md_lines.append(f"![{d['title']}]({rel})")
            else:
                md_lines.append("*(PNG rendering unavailable — raw Mermaid below)*")

            md_lines.append("")
            md_lines.append(f'<details><summary>Mermaid source</summary>')
            md_lines.append("")
            md_lines.append("```mermaid")
            md_lines.append(d["mermaid_src"])
            md_lines.append("```")
            md_lines.append("")
            md_lines.append("</details>")
            md_lines.append("")
            md_lines.append("---")
            md_lines.append("")

        # Stats footer
        if self.kg:
            stats = self.kg.compute_stats()
            md_lines.append("## Generation Stats")
            md_lines.append("")
            md_lines.append(f"| Metric | Value |")
            md_lines.append(f"|--------|-------|")
            md_lines.append(f"| Entities | {stats.get('total_entities', 0)} |")
            md_lines.append(f"| Relations | {stats.get('total_relations', 0)} |")
            md_lines.append(f"| Diagrams generated | {len(diagrams_built)} |")
            md_lines.append(
                f"| Diagrams rendered (PNG) | "
                f"{sum(1 for d in diagrams_built if d['png_path'])} |"
            )
            md_lines.append("")

        report_path = output_dir / self._safe_filename(project_name, "architecture.md")
        report_path.write_text("\n".join(md_lines), encoding="utf-8")

        n_rendered = sum(1 for d in diagrams_built if d["png_path"])
        logger.info(
            "Architecture diagrams: %d built, %d rendered to PNG",
            len(diagrams_built), n_rendered,
        )

        return GenerationResult(
            format=self.format,
            output_path=report_path,
            success=True,
        )
