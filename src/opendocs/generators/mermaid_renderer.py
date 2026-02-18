"""Render Mermaid diagram code to PNG images.

Two rendering backends are supported:

1. **mermaid.ink** (default) – zero-dependency HTTP-based renderer.
   Encodes the diagram as base64 and fetches a PNG from
   ``https://mermaid.ink/img/{encoded}``.

2. **mmdc** (optional) – the official Mermaid CLI
   (``@mermaid-js/mermaid-cli``).  Used automatically when
   ``npx mmdc`` is available on the system, or when explicitly
   requested.  Produces higher-quality SVG/PNG output.

The module also provides helpers to download external images
referenced in ``ImageBlock`` nodes so they can be embedded inline
in generated documents.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import shutil
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MERMAID_INK_BASE = "https://mermaid.ink"
_REQUEST_TIMEOUT = 30.0
_IMAGE_DOWNLOAD_TIMEOUT = 20.0

# Mermaid.ink uses pako (zlib deflate) + base64url
_MERMAID_INK_MAX_CHARS = 8_000  # rough safe limit before URL-length issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pako_deflate_base64(text: str) -> str:
    """Compress text using zlib deflate (pako-compatible) and return
    URL-safe base64 encoding — the format mermaid.ink expects.
    """
    compressed = zlib.compress(text.encode("utf-8"), level=9)
    # Strip zlib header (first 2 bytes) and checksum (last 4 bytes)
    # to match pako's raw deflate output
    raw = compressed[2:-4]
    b64 = base64.urlsafe_b64encode(raw).decode("ascii")
    return b64


def _plain_base64(text: str) -> str:
    """Simple base64 encoding (fallback for mermaid.ink ``/img/`` route)."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def _diagram_hash(code: str) -> str:
    """Deterministic short hash for cache filenames."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]


def _mmdc_available() -> bool:
    """Check whether ``npx mmdc`` is available on the system."""
    if shutil.which("mmdc"):
        return True
    # Try npx
    try:
        result = subprocess.run(
            ["npx", "--yes", "@mermaid-js/mermaid-cli", "--version"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

class MermaidRenderer:
    """Render Mermaid diagrams to PNG image files.

    Parameters
    ----------
    cache_dir
        Directory for caching rendered images.  If *None* a temp
        directory is created.
    backend
        ``"auto"`` tries *mmdc* first, falls back to *mermaid.ink*.
        ``"mmdc"`` forces the CLI. ``"ink"`` forces the HTTP API.
    theme
        Mermaid theme passed to both backends (``default``,
        ``dark``, ``forest``, ``neutral``).
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        backend: Literal["auto", "mmdc", "ink"] = "ink",
        theme: str = "default",
    ) -> None:
        if cache_dir is None:
            self._tmp = tempfile.mkdtemp(prefix="opendocs_diagrams_")
            self.cache_dir = Path(self._tmp)
        else:
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._tmp = None

        self.theme = theme

        # Resolve backend
        if backend == "auto":
            self._use_mmdc = _mmdc_available()
        elif backend == "mmdc":
            self._use_mmdc = True
        else:
            self._use_mmdc = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, code: str, *, label: str = "") -> Path | None:
        """Render a single Mermaid diagram and return the path to the
        generated PNG file, or *None* on failure.

        Results are cached by content hash so duplicate diagrams are
        rendered only once.
        """
        h = _diagram_hash(code)
        cached = self.cache_dir / f"mermaid_{h}.png"
        if cached.exists() and cached.stat().st_size > 0:
            return cached

        if self._use_mmdc:
            result = self._render_mmdc(code, cached)
        else:
            result = self._render_ink(code, cached)

        if result and result.exists() and result.stat().st_size > 100:
            logger.info("Rendered mermaid diagram (%s) → %s", label or h, result)
            return result

        logger.warning("Failed to render mermaid diagram: %s", label or h)
        return None

    def render_batch(self, diagrams: list[str]) -> dict[int, Path]:
        """Render multiple diagrams. Returns ``{index: path}`` for
        successfully rendered diagrams.
        """
        results: dict[int, Path] = {}
        for idx, code in enumerate(diagrams):
            path = self.render(code, label=f"diagram_{idx + 1}")
            if path is not None:
                results[idx] = path
        return results

    def download_image(self, url: str) -> Path | None:
        """Download an external image URL and cache it locally.

        Returns the local path on success, or *None* on failure.
        """
        h = _diagram_hash(url)
        # Guess extension from URL
        ext = "png"
        for candidate in ("png", "jpg", "jpeg", "gif", "svg", "webp"):
            if f".{candidate}" in url.lower():
                ext = candidate
                break
        cached = self.cache_dir / f"img_{h}.{ext}"
        if cached.exists() and cached.stat().st_size > 0:
            return cached

        try:
            with httpx.Client(timeout=_IMAGE_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                cached.write_bytes(resp.content)
                logger.info("Downloaded image %s → %s", url, cached)
                return cached
        except Exception as exc:
            logger.warning("Failed to download image %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Backend: mermaid.ink
    # ------------------------------------------------------------------

    def _render_ink(self, code: str, output_path: Path) -> Path | None:
        """Render via the mermaid.ink HTTP API.

        Uses plain URL-safe base64 encoding — the ``/img/{base64}``
        route is the most reliable across mermaid.ink versions.
        """
        encoded = _plain_base64(code)
        url = f"{_MERMAID_INK_BASE}/img/{encoded}"

        try:
            with httpx.Client(timeout=_REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if "image" not in content_type and len(resp.content) < 200:
                    logger.warning(
                        "mermaid.ink returned unexpected content-type: %s",
                        content_type,
                    )
                    return None

                output_path.write_bytes(resp.content)
                return output_path
        except Exception as exc:
            logger.warning("mermaid.ink render failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Backend: mmdc (Mermaid CLI)
    # ------------------------------------------------------------------

    def _render_mmdc(self, code: str, output_path: Path) -> Path | None:
        """Render via the ``mmdc`` CLI."""
        # Write code to a temp .mmd file
        tmp_input = self.cache_dir / f"_tmp_{_diagram_hash(code)}.mmd"
        tmp_input.write_text(code, encoding="utf-8")

        cmd: list[str] = []
        if shutil.which("mmdc"):
            cmd = ["mmdc"]
        else:
            cmd = ["npx", "--yes", "@mermaid-js/mermaid-cli"]

        cmd.extend([
            "-i", str(tmp_input),
            "-o", str(output_path),
            "-t", self.theme,
            "-b", "transparent",
            "--scale", "2",
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Clean up temp
            tmp_input.unlink(missing_ok=True)

            if result.returncode == 0 and output_path.exists():
                return output_path
            else:
                logger.warning("mmdc failed: %s", result.stderr[:500])
                return None
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("mmdc execution failed: %s", exc)
            tmp_input.unlink(missing_ok=True)
            return None
