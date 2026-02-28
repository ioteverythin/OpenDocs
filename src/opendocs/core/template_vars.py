"""Parameterized report templates — inject variables into generated documents.

Users can set variables like project name, author, version, release date,
and organisation via a YAML/JSON config file or CLI arguments. These values
are automatically inserted into document headers, footers, title pages, and
body content wherever ``{{variable}}`` placeholders appear.

Supported variables (with fallback defaults):
    - ``project_name``  — Name of the project
    - ``author``        — Document author / team
    - ``version``       — Document or project version
    - ``date``          — Release or generation date
    - ``organisation``  — Company / organisation name
    - ``confidentiality`` — e.g. "Internal", "Public", "Confidential"
    - ``department``    — Department / team
    - ``logo_path``     — Path to a logo image for headers
    - Any additional custom key-value pairs

Config file format (YAML or JSON)::

    # opendocs.yaml
    project_name: "My Project"
    author: "Jane Doe"
    version: "2.1.0"
    date: "2026-02-28"
    organisation: "Acme Corp"
    confidentiality: "Internal"
    department: "Engineering"
    logo_path: "./assets/logo.png"
    custom:
      reviewer: "John Smith"
      status: "Draft"
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class TemplateVars(BaseModel):
    """Variables that can be injected into generated documents."""

    project_name: str = ""
    author: str = ""
    version: str = ""
    date: str = ""
    organisation: str = ""
    confidentiality: str = ""
    department: str = ""
    logo_path: str = ""
    custom: dict[str, str] = Field(default_factory=dict)

    # Computed / auto-populated fields
    generated_at: str = Field(default="")

    def model_post_init(self, __context: Any) -> None:
        """Auto-fill generated_at if not set."""
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if not self.date:
            self.date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # Template substitution
    # ------------------------------------------------------------------

    def substitute(self, text: str) -> str:
        """Replace ``{{variable}}`` placeholders in *text* with values.

        Supports both standard fields and custom variables::

            "Report for {{project_name}} v{{version}}"
            "Reviewed by {{custom.reviewer}}"
        """
        if not text or "{{" not in text:
            return text

        lookup = self.as_flat_dict()

        def _replacer(match: re.Match) -> str:
            key = match.group(1).strip()
            return lookup.get(key, match.group(0))  # keep original if unknown

        return re.sub(r"\{\{([\w.]+)\}\}", _replacer, text)

    def as_flat_dict(self) -> dict[str, str]:
        """Return all variables as a flat key-value dict.

        Custom variables are accessible as both ``custom.key`` and ``key``.
        """
        d: dict[str, str] = {
            "project_name": self.project_name,
            "author": self.author,
            "version": self.version,
            "date": self.date,
            "organisation": self.organisation,
            "confidentiality": self.confidentiality,
            "department": self.department,
            "logo_path": self.logo_path,
            "generated_at": self.generated_at,
        }
        for k, v in self.custom.items():
            d[f"custom.{k}"] = v
            if k not in d:  # Don't override standard fields
                d[k] = v
        return d

    @property
    def has_values(self) -> bool:
        """True if at least one meaningful variable is set."""
        return bool(
            self.project_name or self.author or self.version
            or self.organisation or self.department
            or self.confidentiality or self.logo_path or self.custom
        )

    @property
    def header_text(self) -> str:
        """Build a header string from available variables."""
        parts = []
        if self.organisation:
            parts.append(self.organisation)
        if self.department:
            parts.append(self.department)
        if self.confidentiality:
            parts.append(f"[{self.confidentiality}]")
        return "  |  ".join(parts) if parts else ""

    @property
    def footer_text(self) -> str:
        """Build a footer string from available variables."""
        parts = []
        if self.project_name:
            parts.append(self.project_name)
        if self.version:
            parts.append(f"v{self.version}")
        if self.author:
            parts.append(f"Author: {self.author}")
        if self.date:
            parts.append(self.date)
        return "  |  ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Loader — config file (YAML / JSON) + CLI overrides
# ---------------------------------------------------------------------------

def load_template_vars(
    config_path: str | Path | None = None,
    *,
    project_name: str | None = None,
    author: str | None = None,
    version: str | None = None,
    date: str | None = None,
    organisation: str | None = None,
    confidentiality: str | None = None,
    department: str | None = None,
    logo_path: str | None = None,
) -> TemplateVars:
    """Load template variables from a config file with CLI overrides.

    CLI arguments take precedence over config file values.

    Parameters
    ----------
    config_path
        Path to a YAML or JSON config file.
    project_name, author, version, date, organisation, confidentiality,
    department, logo_path
        CLI overrides for individual variables.
    """
    data: dict[str, Any] = {}

    # -- Load from config file -------------------------------------------
    if config_path:
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        raw = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(raw) or {}
            except ImportError:
                raise ImportError(
                    "PyYAML is required to read YAML config files. "
                    "Install it with: pip install pyyaml"
                )
        elif path.suffix == ".json":
            data = json.loads(raw)
        elif path.suffix == ".toml":
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            data = tomllib.loads(raw)
        else:
            # Try JSON first, then YAML
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    import yaml
                    data = yaml.safe_load(raw) or {}
                except ImportError:
                    raise ValueError(
                        f"Cannot parse config file {path}. "
                        "Use .json, .yaml, or .toml format."
                    )

    # -- Apply CLI overrides (take precedence) ----------------------------
    overrides = {
        "project_name": project_name,
        "author": author,
        "version": version,
        "date": date,
        "organisation": organisation,
        "confidentiality": confidentiality,
        "department": department,
        "logo_path": logo_path,
    }

    for key, value in overrides.items():
        if value is not None:
            data[key] = value

    return TemplateVars(**data)


# ---------------------------------------------------------------------------
# Default — empty vars (no-op substitution)
# ---------------------------------------------------------------------------

EMPTY_VARS = TemplateVars()
