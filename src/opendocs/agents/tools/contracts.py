"""MCP tool contract definitions and registry.

Each tool on the generation bus is described by a ``ToolContract`` that
specifies its name, description, parameter schema, and output schema.
The ``TOOL_REGISTRY`` maps tool names → contracts so the orchestrator
can validate plans before execution.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Parameter & contract models
# ---------------------------------------------------------------------------

class ToolParameter(BaseModel):
    """Schema for a single parameter of a tool."""
    name: str
    type: str                       # "string", "integer", "object", "array", etc.
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None   # allowed values (if constrained)


class ToolContract(BaseModel):
    """JSON-schema-style contract for an MCP tool.

    The Planner references these contracts when building plans;
    the Executor validates parameters before dispatching.
    """
    name: str                       # e.g. "diagram.render"
    description: str = ""
    category: str = ""              # e.g. "repo", "diagram", "publish"
    parameters: list[ToolParameter] = Field(default_factory=list)
    output_type: str = "json"       # "json", "svg", "png", "markdown", "url", "docx"
    output_schema: dict[str, Any] = Field(default_factory=dict)
    requires_auth: bool = False
    privacy_level: str = "standard" # "strict" | "standard" | "permissive"

    @property
    def param_names(self) -> list[str]:
        return [p.name for p in self.parameters]

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Return a list of validation errors (empty = valid)."""
        errors: list[str] = []
        for p in self.parameters:
            if p.required and p.name not in params:
                errors.append(f"Missing required parameter: {p.name}")
            if p.enum and p.name in params and params[p.name] not in p.enum:
                errors.append(
                    f"Parameter '{p.name}' must be one of {p.enum}, "
                    f"got '{params[p.name]}'"
                )
        return errors


# ---------------------------------------------------------------------------
# Tool registry — populated by each tool module at import time
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, ToolContract] = {}


def register_tool(contract: ToolContract) -> ToolContract:
    """Register a tool contract in the global registry."""
    TOOL_REGISTRY[contract.name] = contract
    return contract


# ---------------------------------------------------------------------------
# Pre-defined contracts for all MCP tools
# ---------------------------------------------------------------------------

# -- Repo tools -------------------------------------------------------------

REPO_SEARCH = register_tool(ToolContract(
    name="repo.search",
    description="Search repository files by keyword or regex pattern.",
    category="repo",
    parameters=[
        ToolParameter(name="query", type="string", description="Search query or regex"),
        ToolParameter(name="file_pattern", type="string", description="Glob pattern", required=False, default="**/*"),
        ToolParameter(name="max_results", type="integer", required=False, default=20),
    ],
    output_type="json",
    output_schema={"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "line": {"type": "integer"}, "snippet": {"type": "string"}}}},
))

REPO_READ = register_tool(ToolContract(
    name="repo.read",
    description="Read a file or file range from the repository.",
    category="repo",
    parameters=[
        ToolParameter(name="path", type="string", description="Relative file path"),
        ToolParameter(name="start_line", type="integer", required=False),
        ToolParameter(name="end_line", type="integer", required=False),
    ],
    output_type="string",
    privacy_level="permissive",  # needs code access
))

REPO_DIFF = register_tool(ToolContract(
    name="repo.diff",
    description="Get the diff between two git refs (commits, branches, tags).",
    category="repo",
    parameters=[
        ToolParameter(name="ref1", type="string", description="Base ref (commit SHA, branch, tag)"),
        ToolParameter(name="ref2", type="string", description="Head ref", required=False, default="HEAD"),
    ],
    output_type="json",
    output_schema={"type": "object", "properties": {"files_changed": {"type": "array"}, "summary": {"type": "string"}, "additions": {"type": "integer"}, "deletions": {"type": "integer"}}},
))

REPO_SUMMARIZE = register_tool(ToolContract(
    name="repo.summarize",
    description="Generate a concise summary of a file or directory.",
    category="repo",
    parameters=[
        ToolParameter(name="path", type="string", description="Relative path to file or directory"),
        ToolParameter(name="max_tokens", type="integer", required=False, default=500),
    ],
    output_type="markdown",
))

# -- Diagram tools ----------------------------------------------------------

DIAGRAM_RENDER = register_tool(ToolContract(
    name="diagram.render",
    description="Render a diagram from Mermaid, PlantUML, or Graphviz source.",
    category="diagram",
    parameters=[
        ToolParameter(name="type", type="string", description="Diagram language", enum=["mermaid", "plantuml", "graphviz"]),
        ToolParameter(name="spec", type="string", description="Diagram source code"),
        ToolParameter(name="output_format", type="string", required=False, default="svg", enum=["svg", "png", "pdf"]),
        ToolParameter(name="theme", type="string", required=False, default="default"),
    ],
    output_type="svg",
))

# -- Chart tools ------------------------------------------------------------

CHART_GENERATE = register_tool(ToolContract(
    name="chart.generate",
    description="Generate a chart image from structured data.",
    category="chart",
    parameters=[
        ToolParameter(name="data", type="object", description="Chart data (labels, values, series)"),
        ToolParameter(name="chart_type", type="string", enum=["bar", "line", "pie", "scatter", "heatmap", "treemap"]),
        ToolParameter(name="title", type="string", required=False, default=""),
        ToolParameter(name="output_format", type="string", required=False, default="png", enum=["png", "svg"]),
    ],
    output_type="png",
))

# -- Figma tools ------------------------------------------------------------

FIGMA_CREATE_FRAME = register_tool(ToolContract(
    name="figma.create_frame",
    description="Create a new Figma frame with specified layout.",
    category="figma",
    parameters=[
        ToolParameter(name="layout", type="object", description="Frame layout config (width, height, background)"),
        ToolParameter(name="name", type="string", description="Frame name"),
        ToolParameter(name="file_key", type="string", description="Figma file key", required=False),
    ],
    output_type="json",
    output_schema={"type": "object", "properties": {"frame_id": {"type": "string"}, "figma_url": {"type": "string"}}},
    requires_auth=True,
))

FIGMA_ADD_NODES = register_tool(ToolContract(
    name="figma.add_nodes",
    description="Add visual nodes (boxes, arrows, text) to a Figma frame.",
    category="figma",
    parameters=[
        ToolParameter(name="frame_id", type="string", description="Target frame ID"),
        ToolParameter(name="nodes", type="array", description="List of node specs (type, position, content, style)"),
    ],
    output_type="json",
    output_schema={"type": "object", "properties": {"node_ids": {"type": "array"}, "figma_url": {"type": "string"}}},
    requires_auth=True,
))

# -- Image tools ------------------------------------------------------------

IMAGE_GENERATE = register_tool(ToolContract(
    name="image.generate",
    description="Generate an icon or illustration via AI image generation.",
    category="image",
    parameters=[
        ToolParameter(name="prompt", type="string", description="Image generation prompt"),
        ToolParameter(name="style", type="string", required=False, default="flat-icon", enum=["flat-icon", "isometric", "hand-drawn", "technical", "photo-realistic"]),
        ToolParameter(name="size", type="string", required=False, default="512x512", enum=["256x256", "512x512", "1024x1024"]),
    ],
    output_type="url",
    output_schema={"type": "object", "properties": {"image_url": {"type": "string"}, "local_path": {"type": "string"}}},
    requires_auth=True,
))

# -- Document refinement tools ----------------------------------------------

DOCX_REFINE = register_tool(ToolContract(
    name="docx.refine",
    description="Refine/improve a Word document while retaining evidence links.",
    category="doc",
    parameters=[
        ToolParameter(name="instructions", type="string", description="What to improve (e.g. 'expand executive summary')"),
        ToolParameter(name="references_to_KG", type="array", description="KG entity/relation IDs to reference"),
        ToolParameter(name="source_path", type="string", description="Path to existing docx", required=False),
    ],
    output_type="docx",
))

PPTX_REFINE = register_tool(ToolContract(
    name="pptx.refine",
    description="Refine/improve a PowerPoint deck while retaining evidence links.",
    category="doc",
    parameters=[
        ToolParameter(name="instructions", type="string", description="What to improve"),
        ToolParameter(name="references_to_KG", type="array", description="KG entity/relation IDs to reference"),
        ToolParameter(name="source_path", type="string", description="Path to existing pptx", required=False),
    ],
    output_type="pptx",
))

# -- Publishing tools -------------------------------------------------------

CONFLUENCE_PUBLISH = register_tool(ToolContract(
    name="confluence.publish",
    description="Publish a page tree to Confluence.",
    category="publish",
    parameters=[
        ToolParameter(name="page_tree_model", type="object", description="Hierarchical page tree with title, body, children"),
        ToolParameter(name="space_key", type="string", description="Confluence space key"),
        ToolParameter(name="parent_page_id", type="string", required=False),
    ],
    output_type="url",
    output_schema={"type": "object", "properties": {"page_url": {"type": "string"}, "page_id": {"type": "string"}}},
    requires_auth=True,
))
