"""MCP tool contracts and adapters.

This sub-package defines the JSON schemas for every tool available on
the MCP generation bus, plus adapter classes that bridge from the
contract to the actual implementation (local library, API call, etc.).

Tool categories
---------------
repo_tools     — repo.search, repo.read, repo.diff, repo.summarize
diagram_tools  — diagram.render (Mermaid / PlantUML / Graphviz)
chart_tools    — chart.generate (data → chart image)
figma_tools    — figma.create_frame, figma.add_nodes
image_tools    — image.generate (icon/illustration via DALL-E / SD)
doc_tools      — docx.refine, pptx.refine
publish_tools  — confluence.publish
"""

from .chart_tools import ChartGenerateTool
from .contracts import TOOL_REGISTRY, ToolContract, ToolParameter
from .diagram_tools import DiagramRenderTool
from .doc_tools import DocxRefineTool, PptxRefineTool
from .figma_tools import FigmaAddNodesTool, FigmaCreateFrameTool
from .image_tools import ImageGenerateTool
from .publish_tools import ConfluencePublishTool
from .repo_tools import RepoDiffTool, RepoReadTool, RepoSearchTool, RepoSummarizeTool

__all__ = [
    "ToolContract",
    "ToolParameter",
    "TOOL_REGISTRY",
    "RepoSearchTool",
    "RepoReadTool",
    "RepoDiffTool",
    "RepoSummarizeTool",
    "DiagramRenderTool",
    "ChartGenerateTool",
    "FigmaCreateFrameTool",
    "FigmaAddNodesTool",
    "ImageGenerateTool",
    "DocxRefineTool",
    "PptxRefineTool",
    "ConfluencePublishTool",
]
