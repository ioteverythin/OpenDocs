"""Export the knowledge graph as a queryable JSON file.

Produces a ``graph.json`` that can be loaded weeks later without
re-processing the source.  The format is compatible with popular
graph visualisation tools and contains communities, provenance
labels, god nodes, surprising connections, and suggested questions.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.knowledge_graph import KnowledgeGraph
from ..core.models import DocumentModel, GenerationResult, OutputFormat


def generate_graph_json(
    doc: DocumentModel,
    kg: KnowledgeGraph,
    output_dir: Path,
) -> GenerationResult:
    """Write a comprehensive ``graph.json`` to *output_dir*.

    Parameters
    ----------
    doc
        Parsed document model (metadata used for the header).
    kg
        Populated knowledge graph.
    output_dir
        Directory where ``graph.json`` will be written.

    Returns
    -------
    GenerationResult
    """
    name = doc.metadata.repo_name or "project"
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
    safe = safe.strip().replace(" ", "_")[:80] or "project"
    output_path = output_dir / f"{safe}_graph.json"

    try:
        payload = _build_payload(doc, kg)
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return GenerationResult(
            format=OutputFormat.ARCHITECTURE,
            output_path=output_path,
        )
    except Exception as exc:
        return GenerationResult(
            format=OutputFormat.ARCHITECTURE,
            output_path=output_path,
            success=False,
            error=str(exc),
        )


# -- Internal helpers -----------------------------------------------------


def _build_payload(doc: DocumentModel, kg: KnowledgeGraph) -> dict[str, Any]:
    """Build the full JSON payload."""
    # Ensure communities are detected
    if not kg.communities:
        kg.detect_communities()

    nodes = _build_nodes(kg)
    edges = _build_edges(kg)
    communities = kg.community_summary()
    god_nodes = _build_god_nodes(kg)
    surprises = _build_surprises(kg)
    questions = kg.suggested_questions(top_n=5)
    stats = kg.extraction_stats or kg.compute_stats()

    return {
        "version": "1.0",
        "generator": "opendocs",
        "generated_at": datetime.now().isoformat(),
        "project": {
            "name": doc.metadata.repo_name or "unknown",
            "url": doc.metadata.repo_url or doc.metadata.source_path or "",
            "description": doc.metadata.description or "",
        },
        "stats": {
            "total_nodes": len(kg.entities),
            "total_edges": len(kg.relations),
            "communities": len(communities),
            "entity_types": len({e.entity_type for e in kg.entities}),
            "extracted": sum(1 for e in kg.entities if e.provenance == "EXTRACTED"),
            "inferred": sum(1 for e in kg.entities if e.provenance == "INFERRED"),
            "ambiguous": sum(1 for e in kg.entities if e.provenance == "AMBIGUOUS"),
            **stats,
        },
        "nodes": nodes,
        "edges": edges,
        "communities": communities,
        "god_nodes": god_nodes,
        "surprising_connections": surprises,
        "suggested_questions": questions,
    }


def _build_nodes(kg: KnowledgeGraph) -> list[dict[str, Any]]:
    """Serialise entities with community and provenance info."""
    degrees = kg.node_degrees()
    nodes = []
    for e in kg.entities:
        nodes.append(
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type.value,
                "confidence": round(e.confidence, 3),
                "provenance": e.provenance,
                "extraction_method": e.extraction_method,
                "community": kg.communities.get(e.id, -1),
                "degree": degrees.get(e.id, 0),
                "source_section": e.source_section,
                "properties": e.properties,
            }
        )
    return nodes


def _build_edges(kg: KnowledgeGraph) -> list[dict[str, Any]]:
    """Serialise relations with provenance labels."""
    edges = []
    for r in kg.relations:
        edges.append(
            {
                "source": r.source_id,
                "target": r.target_id,
                "relation": r.relation_type.value,
                "confidence": round(r.confidence, 3),
                "provenance": r.provenance,
                "extraction_method": r.extraction_method,
                "properties": r.properties,
            }
        )
    return edges


def _build_god_nodes(kg: KnowledgeGraph, top_n: int = 5) -> list[dict[str, Any]]:
    """Top-N highest-degree entities."""
    result = []
    for ent, deg in kg.god_nodes(top_n=top_n):
        result.append(
            {
                "name": ent.name,
                "type": ent.entity_type.value,
                "degree": deg,
                "community": kg.communities.get(ent.id, -1),
                "provenance": ent.provenance,
            }
        )
    return result


def _build_surprises(kg: KnowledgeGraph, top_n: int = 5) -> list[dict[str, Any]]:
    """Cross-type edges ranked by surprise score."""
    result = []
    for score, rel in kg.surprising_connections(top_n=top_n):
        src = kg.get_entity(rel.source_id)
        tgt = kg.get_entity(rel.target_id)
        if src and tgt:
            result.append(
                {
                    "source": src.name,
                    "source_type": src.entity_type.value,
                    "target": tgt.name,
                    "target_type": tgt.entity_type.value,
                    "relation": rel.relation_type.value,
                    "score": round(score, 3),
                }
            )
    return result
