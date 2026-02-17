"""Tests for Mermaid rendering and image embedding."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ioteverything.generators.mermaid_renderer import (
    MermaidRenderer,
    _diagram_hash,
    _pako_deflate_base64,
    _plain_base64,
)
from ioteverything.generators.diagram_extractor import DiagramExtractor, ImageCache
from ioteverything.core.models import (
    DocumentModel,
    DocumentMetadata,
    Section,
    MermaidBlock,
    ImageBlock,
    ParagraphBlock,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_MERMAID = "graph TD\n    A-->B\n    B-->C"
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200  # fake but valid-looking PNG header


# ---------------------------------------------------------------------------
# MermaidRenderer – encoding helpers
# ---------------------------------------------------------------------------

class TestEncodingHelpers:
    def test_pako_deflate_base64_returns_string(self):
        result = _pako_deflate_base64(SIMPLE_MERMAID)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_plain_base64_returns_string(self):
        result = _plain_base64(SIMPLE_MERMAID)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_diagram_hash_deterministic(self):
        h1 = _diagram_hash(SIMPLE_MERMAID)
        h2 = _diagram_hash(SIMPLE_MERMAID)
        assert h1 == h2
        assert len(h1) == 12

    def test_diagram_hash_different_input(self):
        h1 = _diagram_hash("graph TD\n    A-->B")
        h2 = _diagram_hash("graph LR\n    X-->Y")
        assert h1 != h2


# ---------------------------------------------------------------------------
# MermaidRenderer – render via mermaid.ink (mocked)
# ---------------------------------------------------------------------------

class TestMermaidRendererInk:
    def test_render_success(self, tmp_path):
        renderer = MermaidRenderer(cache_dir=tmp_path, backend="ink")

        mock_resp = MagicMock()
        mock_resp.content = FAKE_PNG
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "image/png"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_resp)

        with patch("ioteverything.generators.mermaid_renderer.httpx.Client", return_value=mock_client):
            result = renderer.render(SIMPLE_MERMAID, label="test")

        assert result is not None
        assert result.exists()
        assert result.read_bytes() == FAKE_PNG

    def test_render_caches_result(self, tmp_path):
        renderer = MermaidRenderer(cache_dir=tmp_path, backend="ink")

        # Pre-populate cache
        h = _diagram_hash(SIMPLE_MERMAID)
        cached_path = tmp_path / f"mermaid_{h}.png"
        cached_path.write_bytes(FAKE_PNG)

        # Should return cached result without making HTTP call
        result = renderer.render(SIMPLE_MERMAID)
        assert result == cached_path

    def test_render_failure_returns_none(self, tmp_path):
        renderer = MermaidRenderer(cache_dir=tmp_path, backend="ink")

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(side_effect=Exception("Connection failed"))

        with patch("ioteverything.generators.mermaid_renderer.httpx.Client", return_value=mock_client):
            result = renderer.render(SIMPLE_MERMAID)

        assert result is None

    def test_render_batch(self, tmp_path):
        renderer = MermaidRenderer(cache_dir=tmp_path, backend="ink")

        mock_resp = MagicMock()
        mock_resp.content = FAKE_PNG
        mock_resp.headers = {"content-type": "image/png"}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_resp)

        diagrams = [
            "graph TD\n    A-->B",
            "sequenceDiagram\n    Alice->>Bob: Hello",
        ]

        with patch("ioteverything.generators.mermaid_renderer.httpx.Client", return_value=mock_client):
            results = renderer.render_batch(diagrams)

        assert len(results) == 2
        assert 0 in results
        assert 1 in results


# ---------------------------------------------------------------------------
# MermaidRenderer – download_image
# ---------------------------------------------------------------------------

class TestDownloadImage:
    def test_download_success(self, tmp_path):
        renderer = MermaidRenderer(cache_dir=tmp_path, backend="ink")

        mock_resp = MagicMock()
        mock_resp.content = FAKE_PNG
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(return_value=mock_resp)

        with patch("ioteverything.generators.mermaid_renderer.httpx.Client", return_value=mock_client):
            result = renderer.download_image("https://example.com/diagram.png")

        assert result is not None
        assert result.exists()
        assert result.suffix == ".png"

    def test_download_failure_returns_none(self, tmp_path):
        renderer = MermaidRenderer(cache_dir=tmp_path, backend="ink")

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get = MagicMock(side_effect=Exception("Network error"))

        with patch("ioteverything.generators.mermaid_renderer.httpx.Client", return_value=mock_client):
            result = renderer.download_image("https://example.com/fail.png")

        assert result is None

    def test_download_caches(self, tmp_path):
        renderer = MermaidRenderer(cache_dir=tmp_path, backend="ink")
        url = "https://example.com/cached.png"
        h = _diagram_hash(url)
        cached = tmp_path / f"img_{h}.png"
        cached.write_bytes(FAKE_PNG)

        result = renderer.download_image(url)
        assert result == cached


# ---------------------------------------------------------------------------
# ImageCache
# ---------------------------------------------------------------------------

class TestImageCache:
    def test_get_mermaid(self, tmp_path):
        cache = ImageCache()
        path = tmp_path / "test.png"
        path.write_bytes(FAKE_PNG)
        cache.mermaid_images[0] = path
        assert cache.get_mermaid(0) == path
        assert cache.get_mermaid(1) is None

    def test_get_external(self, tmp_path):
        cache = ImageCache()
        path = tmp_path / "ext.png"
        path.write_bytes(FAKE_PNG)
        cache.external_images["https://example.com/img.png"] = path
        assert cache.get_external("https://example.com/img.png") == path
        assert cache.get_external("https://other.com/img.png") is None


# ---------------------------------------------------------------------------
# DiagramExtractor (mocked renderer)
# ---------------------------------------------------------------------------

class TestDiagramExtractorWithRenderer:
    def _make_doc_with_diagrams(self, n_diagrams=2, n_images=1):
        blocks = []
        diagrams = []
        for i in range(n_diagrams):
            code = f"graph TD\n    A{i}-->B{i}"
            blocks.append(MermaidBlock(code=code))
            diagrams.append(code)
        for i in range(n_images):
            blocks.append(ImageBlock(
                alt=f"Image {i}",
                src=f"https://example.com/img_{i}.png",
            ))

        return DocumentModel(
            metadata=DocumentMetadata(repo_name="Test"),
            sections=[Section(title="Test", level=1, blocks=blocks)],
            all_blocks=blocks,
            mermaid_diagrams=diagrams,
        )

    def test_extract_renders_diagrams(self, tmp_path):
        doc = self._make_doc_with_diagrams(2, 0)

        mock_renderer = MagicMock()
        mock_renderer.render_batch = MagicMock(return_value={
            0: tmp_path / "d0.png",
            1: tmp_path / "d1.png",
        })
        mock_renderer.render = MagicMock(return_value=None)

        extractor = DiagramExtractor(renderer=mock_renderer)
        paths, cache = extractor.extract(doc, tmp_path)

        assert len(paths) >= 2  # individual + combined
        assert len(cache.mermaid_images) == 2
        mock_renderer.render_batch.assert_called_once()

    def test_extract_downloads_images(self, tmp_path):
        doc = self._make_doc_with_diagrams(0, 2)

        img_path = tmp_path / "downloaded.png"
        img_path.write_bytes(FAKE_PNG)

        mock_renderer = MagicMock()
        mock_renderer.download_image = MagicMock(return_value=img_path)

        extractor = DiagramExtractor(renderer=mock_renderer)
        paths, cache = extractor.extract(doc, tmp_path)

        assert len(cache.external_images) == 2
        assert mock_renderer.download_image.call_count == 2

    def test_extract_renders_kg_diagram(self, tmp_path):
        doc = self._make_doc_with_diagrams(0, 0)
        kg_png = tmp_path / "kg.png"
        kg_png.write_bytes(FAKE_PNG)

        mock_renderer = MagicMock()
        mock_renderer.render = MagicMock(return_value=kg_png)

        extractor = DiagramExtractor(renderer=mock_renderer)
        paths, cache = extractor.extract(
            doc, tmp_path, kg_mermaid="graph TD\n    KG-->Entities",
        )

        assert cache.kg_diagram == kg_png
        mock_renderer.render.assert_called_once()

    def test_extract_empty_doc(self, tmp_path):
        doc = DocumentModel(
            metadata=DocumentMetadata(repo_name="Empty"),
        )

        mock_renderer = MagicMock()
        extractor = DiagramExtractor(renderer=mock_renderer)
        paths, cache = extractor.extract(doc, tmp_path)

        assert paths == []
        assert len(cache.mermaid_images) == 0
        assert len(cache.external_images) == 0
