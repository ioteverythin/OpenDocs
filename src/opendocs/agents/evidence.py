"""Evidence pointer model and coverage scoring.

Every factual claim, diagram node, or generated sentence must reference
an ``EvidencePointer`` that traces back to the source repo. The
``EvidenceCoverage`` model aggregates per-artifact scores.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Evidence pointer
# ---------------------------------------------------------------------------

class EvidenceType(str, Enum):
    """The kind of source material backing a claim."""
    README_SECTION = "readme_section"
    CODE_FILE = "code_file"
    CODE_SNIPPET = "code_snippet"
    CONFIG_FILE = "config_file"
    COMMIT = "commit"
    ISSUE = "issue"
    PR = "pr"
    API_SCHEMA = "api_schema"
    DIAGRAM_SOURCE = "diagram_source"
    EXTERNAL_DOC = "external_doc"


class EvidencePointer(BaseModel):
    """An immutable reference linking a generated claim to its source.

    Every assertion emitted by an agent or tool must carry at least
    one EvidencePointer. The Critic agent validates these and flags
    claims that lack evidence as potential hallucinations.

    Examples
    --------
    >>> ptr = EvidencePointer(
    ...     evidence_type=EvidenceType.README_SECTION,
    ...     source_path="README.md",
    ...     section="Installation",
    ...     snippet="pip install fastapi[standard]",
    ...     line_start=42,
    ...     line_end=42,
    ... )
    """

    id: str = Field(default_factory=lambda: f"ev-{uuid.uuid4().hex[:10]}")
    evidence_type: EvidenceType
    source_path: str = ""                  # relative file path in repo
    section: str = ""                      # README section title
    snippet: str = ""                      # short excerpt (≤200 chars)
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    commit_sha: str = ""                   # git commit for traceability
    url: str = ""                          # link to source (GH permalink)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Claim model (generated assertion + evidence links)
# ---------------------------------------------------------------------------

class Claim(BaseModel):
    """A single generated assertion tied to evidence.

    The Critic agent evaluates each Claim. Claims without evidence
    are flagged as *assumptions* and counted against the coverage score.
    """

    id: str = Field(default_factory=lambda: f"cl-{uuid.uuid4().hex[:8]}")
    text: str                              # the generated assertion
    artifact_id: str = ""                  # which artifact contains this
    evidence_ids: list[str] = Field(default_factory=list)
    is_assumption: bool = False            # True if no evidence found
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Evidence coverage score
# ---------------------------------------------------------------------------

class EvidenceCoverage(BaseModel):
    """Aggregate evidence coverage score for an artifact.

    Exposed in the API and UI so users can gauge trustworthiness.
    """

    artifact_id: str
    artifact_type: str = ""                # e.g. "word", "pptx", "diagram"
    total_claims: int = 0
    backed_claims: int = 0
    assumption_count: int = 0
    assumptions: list[str] = Field(default_factory=list)  # claim texts
    evidence_ids: list[str] = Field(default_factory=list)
    confidence_mean: float = 0.0
    confidence_min: float = 0.0

    @property
    def coverage_pct(self) -> float:
        """Percentage of claims backed by evidence (0–100)."""
        if self.total_claims == 0:
            return 100.0
        return (self.backed_claims / self.total_claims) * 100.0

    @property
    def is_trustworthy(self) -> bool:
        """Heuristic: ≥80% coverage and no <0.3 confidence claims."""
        return self.coverage_pct >= 80.0 and self.confidence_min >= 0.3

    def summary(self) -> dict[str, Any]:
        """Human-readable summary dict for API/UI."""
        return {
            "artifact": self.artifact_id,
            "type": self.artifact_type,
            "coverage": f"{self.coverage_pct:.1f}%",
            "total_claims": self.total_claims,
            "backed_claims": self.backed_claims,
            "assumptions": self.assumption_count,
            "confidence_mean": round(self.confidence_mean, 2),
            "confidence_min": round(self.confidence_min, 2),
            "trustworthy": self.is_trustworthy,
        }


# ---------------------------------------------------------------------------
# Evidence registry (in-memory store for a pipeline run)
# ---------------------------------------------------------------------------

class EvidenceRegistry:
    """Collects all evidence pointers and claims during a pipeline run.

    Agents register evidence as they produce it; the Critic queries
    the registry to compute coverage scores.
    """

    def __init__(self) -> None:
        self._pointers: dict[str, EvidencePointer] = {}
        self._claims: list[Claim] = []

    # -- Registration -------------------------------------------------------

    def register_pointer(self, pointer: EvidencePointer) -> str:
        """Store a pointer and return its ID."""
        self._pointers[pointer.id] = pointer
        return pointer.id

    def register_claim(self, claim: Claim) -> None:
        """Register a claim (with or without evidence)."""
        # Mark as assumption if no evidence attached
        if not claim.evidence_ids:
            claim.is_assumption = True
        self._claims.append(claim)

    # -- Queries ------------------------------------------------------------

    def get_pointer(self, pointer_id: str) -> Optional[EvidencePointer]:
        return self._pointers.get(pointer_id)

    def claims_for_artifact(self, artifact_id: str) -> list[Claim]:
        return [c for c in self._claims if c.artifact_id == artifact_id]

    def all_pointers(self) -> list[EvidencePointer]:
        return list(self._pointers.values())

    def all_claims(self) -> list[Claim]:
        return list(self._claims)

    # -- Scoring ------------------------------------------------------------

    def compute_coverage(self, artifact_id: str, artifact_type: str = "") -> EvidenceCoverage:
        """Compute evidence coverage for a specific artifact."""
        claims = self.claims_for_artifact(artifact_id)
        if not claims:
            return EvidenceCoverage(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
            )

        backed = [c for c in claims if not c.is_assumption]
        assumptions = [c for c in claims if c.is_assumption]
        confidences = [c.confidence for c in claims]
        ev_ids: set[str] = set()
        for c in backed:
            ev_ids.update(c.evidence_ids)

        return EvidenceCoverage(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            total_claims=len(claims),
            backed_claims=len(backed),
            assumption_count=len(assumptions),
            assumptions=[a.text for a in assumptions],
            evidence_ids=sorted(ev_ids),
            confidence_mean=sum(confidences) / len(confidences),
            confidence_min=min(confidences),
        )

    def compute_all_coverage(self) -> list[EvidenceCoverage]:
        """Compute coverage for every artifact that has claims."""
        artifact_ids = sorted({c.artifact_id for c in self._claims})
        return [self.compute_coverage(aid) for aid in artifact_ids]
