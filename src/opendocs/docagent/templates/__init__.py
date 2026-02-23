"""Bundled Markdown templates for document generation."""

from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent

def get_template(name: str) -> str:
    """Load a bundled template by name (without extension)."""
    path = _TEMPLATE_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {name}")
    return path.read_text(encoding="utf-8")

def list_templates() -> list[str]:
    """Return names of all bundled templates."""
    return [p.stem for p in _TEMPLATE_DIR.glob("*.md")]
