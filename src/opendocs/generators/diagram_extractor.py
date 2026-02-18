"""Extract, render, and catalog Mermaid diagrams from the parsed document.

In addition to saving raw ``.mmd`` text files, the extractor now
renders diagrams to PNG images via :class:`MermaidRenderer` and
downloads external images referenced by ``ImageBlock`` nodes.

The resulting :class:`ImageCache` is passed to all generators so they
can embed actual images rather than text placeholders.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..core.models import DocumentModel, ImageBlock
from .mermaid_renderer import MermaidRenderer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Image cache — shared across generators
# ---------------------------------------------------------------------------

@dataclass
class ImageCache:
    """Holds paths to rendered diagram images and downloaded external images.

    Generators look up images by index (for Mermaid diagrams) or by
    source URL (for external images).
    """

    #: ``{mermaid_diagram_index: local_png_path}``
    mermaid_images: dict[int, Path] = field(default_factory=dict)

    #: ``{original_src_url: local_image_path}``
    external_images: dict[str, Path] = field(default_factory=dict)

    #: ``{kg_mermaid_hash: local_png_path}`` for auto-generated KG diagram
    kg_diagram: Path | None = None

    def get_mermaid(self, index: int) -> Path | None:
        return self.mermaid_images.get(index)

    def get_external(self, src: str) -> Path | None:
        return self.external_images.get(src)


class DiagramExtractor:
    """Extracts Mermaid diagrams from a ``DocumentModel``, renders them
    to PNG images, and downloads external images.

    The :meth:`extract` method returns both the list of raw ``.mmd``
    files *and* an :class:`ImageCache` that generators use to embed
    rendered images.
    """

    def __init__(self, renderer: MermaidRenderer | None = None) -> None:
        self.renderer = renderer or MermaidRenderer()

    def extract(
        self,
        doc: DocumentModel,
        output_dir: Path,
        *,
        kg_mermaid: str | None = None,
    ) -> tuple[list[Path], ImageCache]:
        """Write raw ``.mmd`` files, render PNGs, and download images.

        Parameters
        ----------
        doc
            The parsed document model.
        output_dir
            Root output directory (diagrams are saved under
            ``output_dir/diagrams/``).
        kg_mermaid
            Optional Mermaid source from the auto-generated Knowledge
            Graph diagram.  If provided it is also rendered to a PNG.

        Returns
        -------
        (mmd_paths, image_cache)
            *mmd_paths* lists the raw ``.mmd`` files written.
            *image_cache* contains mappings from diagram indices and
            image URLs to local file paths.
        """
        diagrams_dir = output_dir / "diagrams"
        diagrams_dir.mkdir(parents=True, exist_ok=True)
        self.renderer.cache_dir = diagrams_dir

        cache = ImageCache()
        mmd_paths: list[Path] = []

        # ── 1.  Save raw .mmd files ──────────────────────────────────
        if doc.mermaid_diagrams:
            for idx, code in enumerate(doc.mermaid_diagrams):
                path = diagrams_dir / f"diagram_{idx + 1}.mmd"
                path.write_text(code, encoding="utf-8")
                mmd_paths.append(path)

            combined = diagrams_dir / "all_diagrams.mmd"
            combined.write_text(
                "\n\n%% --- diagram separator ---\n\n".join(doc.mermaid_diagrams),
                encoding="utf-8",
            )
            mmd_paths.append(combined)

        # ── 2.  Render Mermaid diagrams to PNG ────────────────────────
        if doc.mermaid_diagrams:
            logger.info("Rendering %d Mermaid diagram(s) to PNG…", len(doc.mermaid_diagrams))
            rendered = self.renderer.render_batch(doc.mermaid_diagrams)
            cache.mermaid_images = rendered

        # ── 3.  Render KG diagram if provided ────────────────────────
        if kg_mermaid:
            kg_png = self.renderer.render(kg_mermaid, label="knowledge_graph")
            if kg_png:
                cache.kg_diagram = kg_png

        # ── 4.  Download external images ─────────────────────────────
        seen_urls: set[str] = set()
        for block in doc.all_blocks:
            if isinstance(block, ImageBlock) and block.src:
                src = block.src
                if src in seen_urls:
                    continue
                seen_urls.add(src)

                # Only download http(s) URLs
                if src.startswith(("http://", "https://")):
                    local = self.renderer.download_image(src)
                    if local:
                        cache.external_images[src] = local

        return mmd_paths, cache
