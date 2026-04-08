"""Generate an interactive HTML knowledge-graph visualisation.

Produces a self-contained HTML file powered by vis-network (CDN) that
lets users pan, zoom, click nodes, search, and filter by entity type.
No local JavaScript toolchain is required.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from ..core.knowledge_graph import EntityType, KnowledgeGraph, Relation
from ..core.models import DocumentModel, GenerationResult, OutputFormat

# -- Colour palette per entity type (hex) --------------------------------

_TYPE_COLOURS: dict[EntityType, str] = {
    EntityType.PROJECT: "#6366f1",
    EntityType.COMPONENT: "#8b5cf6",
    EntityType.TECHNOLOGY: "#06b6d4",
    EntityType.PROTOCOL: "#14b8a6",
    EntityType.LANGUAGE: "#f59e0b",
    EntityType.FRAMEWORK: "#ec4899",
    EntityType.DATABASE: "#10b981",
    EntityType.CLOUD_SERVICE: "#3b82f6",
    EntityType.API_ENDPOINT: "#f97316",
    EntityType.METRIC: "#ef4444",
    EntityType.CONFIGURATION: "#64748b",
    EntityType.PREREQUISITE: "#a855f7",
    EntityType.HARDWARE: "#78716c",
    EntityType.PERSON_ORG: "#0ea5e9",
    EntityType.LICENSE_TYPE: "#84cc16",
    EntityType.FEATURE: "#d946ef",
    EntityType.PLATFORM: "#2563eb",
}

_DEFAULT_COLOUR = "#94a3b8"


# -- Public API -----------------------------------------------------------


def generate_interactive_graph(
    doc: DocumentModel,
    kg: KnowledgeGraph,
    output_dir: Path,
) -> GenerationResult:
    """Build an interactive HTML graph and write it to *output_dir*.

    Parameters
    ----------
    doc
        Parsed document model (used for the page title).
    kg
        Populated knowledge graph.
    output_dir
        Directory where ``graph.html`` will be written.

    Returns
    -------
    GenerationResult
    """
    name = doc.metadata.repo_name or "project"
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
    safe = safe.strip().replace(" ", "_")[:80] or "project"
    output_path = output_dir / f"{safe}_graph.html"

    try:
        html_content = _build_html(kg, name)
        output_path.write_text(html_content, encoding="utf-8")
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


def _node_degree(kg: KnowledgeGraph) -> dict[str, int]:
    """Compute the degree (in + out) of every entity."""
    deg: dict[str, int] = {e.id: 0 for e in kg.entities}
    for r in kg.relations:
        deg[r.source_id] = deg.get(r.source_id, 0) + 1
        deg[r.target_id] = deg.get(r.target_id, 0) + 1
    return deg


def _build_nodes_json(kg: KnowledgeGraph) -> str:
    """Serialise entities as a vis-network DataSet array."""
    degrees = _node_degree(kg)
    nodes = []
    for e in kg.entities:
        deg = degrees.get(e.id, 0)
        size = max(12, min(40, 12 + deg * 4))
        colour = _TYPE_COLOURS.get(e.entity_type, _DEFAULT_COLOUR)
        label = e.name[:32] + ("…" if len(e.name) > 32 else "")
        title_text = (
            f"<b>{html.escape(e.name)}</b><br>"
            f"Type: {e.entity_type.value.replace('_', ' ').title()}<br>"
            f"Degree: {deg}<br>"
            f"Confidence: {e.confidence:.0%}<br>"
            f"Method: {e.extraction_method}"
        )
        nodes.append(
            {
                "id": e.id,
                "label": label,
                "title": title_text,
                "color": colour,
                "size": size,
                "font": {"size": 11, "color": "#e2e8f0"},
                "group": e.entity_type.value,
            }
        )
    return json.dumps(nodes)


def _build_edges_json(kg: KnowledgeGraph) -> str:
    """Serialise relations as a vis-network DataSet array."""
    edges = []
    seen: set[str] = set()
    for r in kg.relations:
        key = f"{r.source_id}|{r.target_id}|{r.relation_type.value}"
        if key in seen:
            continue
        seen.add(key)
        label = r.relation_type.value.replace("_", " ")
        edges.append(
            {
                "from": r.source_id,
                "to": r.target_id,
                "label": label,
                "title": f"{label} (conf: {r.confidence:.0%})",
                "arrows": "to",
                "color": {"color": "#475569", "highlight": "#6366f1"},
                "font": {"size": 9, "color": "#94a3b8", "strokeWidth": 0},
            }
        )
    return json.dumps(edges)


def _god_nodes_json(kg: KnowledgeGraph, top_n: int = 5) -> str:
    """Return the top-N god nodes (highest degree) as JSON."""
    degrees = _node_degree(kg)
    ranked = sorted(degrees.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    result = []
    for eid, deg in ranked:
        ent = kg.get_entity(eid)
        if ent:
            result.append({"name": ent.name, "type": ent.entity_type.value, "degree": deg})
    return json.dumps(result)


def _surprising_connections_json(kg: KnowledgeGraph, top_n: int = 5) -> str:
    """Find cross-type edges ranked by surprise score."""
    scored: list[tuple[float, Relation]] = []
    for r in kg.relations:
        src = kg.get_entity(r.source_id)
        tgt = kg.get_entity(r.target_id)
        if not src or not tgt:
            continue
        if src.entity_type == tgt.entity_type:
            continue
        # Score: lower confidence = more surprising; cross-domain bonus
        score = (1.0 - r.confidence) + 0.3
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    result = []
    for score, r in scored[:top_n]:
        src = kg.get_entity(r.source_id)
        tgt = kg.get_entity(r.target_id)
        if src and tgt:
            result.append(
                {
                    "source": src.name,
                    "sourceType": src.entity_type.value,
                    "target": tgt.name,
                    "targetType": tgt.entity_type.value,
                    "relation": r.relation_type.value,
                    "score": round(score, 2),
                }
            )
    return json.dumps(result)


def _legend_items(kg: KnowledgeGraph) -> str:
    """Build HTML legend items for entity types present in the graph."""
    types_present: set[EntityType] = {e.entity_type for e in kg.entities}
    items = []
    for et in EntityType:
        if et not in types_present:
            continue
        colour = _TYPE_COLOURS.get(et, _DEFAULT_COLOUR)
        label = et.value.replace("_", " ").title()
        count = sum(1 for e in kg.entities if e.entity_type == et)
        items.append(
            f'<span class="leg-item"><span class="leg-dot" style="background:{colour}"></span>{label} ({count})</span>'
        )
    return "\n".join(items)


def _build_html(kg: KnowledgeGraph, project_name: str) -> str:
    """Assemble the full self-contained HTML page."""
    nodes_json = _build_nodes_json(kg)
    edges_json = _build_edges_json(kg)
    god_json = _god_nodes_json(kg)
    surprise_json = _surprising_connections_json(kg)
    legend_html = _legend_items(kg)
    title = html.escape(project_name)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title} Knowledge Graph</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;overflow:hidden}}
#app{{display:flex;height:100vh}}
.sidebar{{width:320px;background:#1e293b;border-right:1px solid #334155;display:flex;flex-direction:column;overflow-y:auto}}
.sidebar h2{{padding:1rem 1.25rem 0.5rem;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em;color:#64748b}}
.sidebar-header{{padding:1.25rem;border-bottom:1px solid #334155}}
.sidebar-header h1{{font-size:1.1rem;font-weight:700;color:#f8fafc}}
.sidebar-header p{{font-size:0.78rem;color:#94a3b8;margin-top:0.25rem}}
#search{{width:100%;padding:0.5rem 0.75rem;border:1px solid #334155;border-radius:6px;background:#0f172a;color:#e2e8f0;font-size:0.82rem;margin-top:0.75rem}}
#search:focus{{outline:none;border-color:#6366f1}}
.legend{{padding:0 1.25rem 1rem;display:flex;flex-wrap:wrap;gap:0.4rem}}
.leg-item{{display:inline-flex;align-items:center;gap:0.3rem;font-size:0.72rem;color:#94a3b8;cursor:pointer;padding:0.15rem 0.4rem;border-radius:4px;transition:background 0.15s}}
.leg-item:hover{{background:#334155}}
.leg-item.dimmed{{opacity:0.3}}
.leg-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.panel{{padding:0.75rem 1.25rem}}
.panel-card{{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:0.75rem;margin-bottom:0.5rem}}
.panel-card h4{{font-size:0.78rem;font-weight:600;color:#f8fafc;margin-bottom:0.25rem}}
.panel-card p,.panel-card span{{font-size:0.72rem;color:#94a3b8}}
.panel-card .badge{{display:inline-block;padding:0.1rem 0.4rem;border-radius:3px;font-size:0.65rem;background:#334155;color:#cbd5e1;margin-right:0.25rem}}
#graph-container{{flex:1;position:relative}}
#graph{{width:100%;height:100%}}
.stats-bar{{position:absolute;bottom:1rem;left:1rem;display:flex;gap:0.75rem;background:rgba(30,41,59,0.9);border:1px solid #334155;border-radius:8px;padding:0.5rem 1rem}}
.stat{{text-align:center}}
.stat-val{{font-size:1.1rem;font-weight:700;color:#f8fafc}}
.stat-lbl{{font-size:0.65rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em}}
</style>
</head>
<body>
<div id="app">
  <div class="sidebar">
    <div class="sidebar-header">
      <h1>{title}</h1>
      <p>Interactive Knowledge Graph</p>
      <input id="search" type="text" placeholder="Search nodes..."/>
    </div>
    <h2>Entity Types</h2>
    <div class="legend" id="legend">{legend_html}</div>
    <h2>God Nodes</h2>
    <div class="panel" id="god-nodes"></div>
    <h2>Surprising Connections</h2>
    <div class="panel" id="surprises"></div>
  </div>
  <div id="graph-container">
    <div id="graph"></div>
    <div class="stats-bar">
      <div class="stat"><div class="stat-val">{len(kg.entities)}</div><div class="stat-lbl">Nodes</div></div>
      <div class="stat"><div class="stat-val">{len(kg.relations)}</div><div class="stat-lbl">Edges</div></div>
      <div class="stat"><div class="stat-val">{len({e.entity_type for e in kg.entities})}</div><div class="stat-lbl">Types</div></div>
    </div>
  </div>
</div>
<script>
var nodesData = new vis.DataSet({nodes_json});
var edgesData = new vis.DataSet({edges_json});
var godNodes  = {god_json};
var surprises = {surprise_json};

var container = document.getElementById('graph');
var network = new vis.Network(container, {{nodes: nodesData, edges: edgesData}}, {{
  physics: {{
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{gravitationalConstant: -40, centralGravity: 0.005, springLength: 120, springConstant: 0.06}},
    stabilization: {{iterations: 150}}
  }},
  interaction: {{hover: true, tooltipDelay: 100, navigationButtons: false, keyboard: true}},
  edges: {{smooth: {{type: 'continuous'}}}},
  layout: {{improvedLayout: true}}
}});

// God nodes panel
var gp = document.getElementById('god-nodes');
godNodes.forEach(function(g) {{
  var d = document.createElement('div');
  d.className = 'panel-card';
  d.innerHTML = '<h4>' + g.name + '</h4><span class="badge">' + g.type.replace(/_/g,' ') + '</span> <span>Degree: ' + g.degree + '</span>';
  gp.appendChild(d);
}});

// Surprises panel
var sp = document.getElementById('surprises');
surprises.forEach(function(s) {{
  var d = document.createElement('div');
  d.className = 'panel-card';
  d.innerHTML = '<h4>' + s.source + ' \\u2194 ' + s.target + '</h4><p>' + s.relation.replace(/_/g,' ') + ' <span class="badge">score ' + s.score + '</span></p>';
  sp.appendChild(d);
}});

// Search
document.getElementById('search').addEventListener('input', function(e) {{
  var q = e.target.value.toLowerCase();
  nodesData.forEach(function(n) {{
    var match = !q || n.label.toLowerCase().indexOf(q) !== -1;
    nodesData.update({{id: n.id, hidden: !match && q.length > 0}});
  }});
}});

// Legend filter
document.querySelectorAll('.leg-item').forEach(function(el) {{
  el.addEventListener('click', function() {{
    el.classList.toggle('dimmed');
    var dimmed = new Set();
    document.querySelectorAll('.leg-item.dimmed').forEach(function(d) {{
      var txt = d.textContent.trim().split('(')[0].trim().toLowerCase().replace(/ /g,'_');
      dimmed.add(txt);
    }});
    nodesData.forEach(function(n) {{
      nodesData.update({{id: n.id, hidden: dimmed.has(n.group)}});
    }});
  }});
}});
</script>
</body>
</html>"""
