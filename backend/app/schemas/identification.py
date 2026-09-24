from typing import Optional

from pydantic import BaseModel


class IdentificationResult(BaseModel):
    """Stage 10 output. Matches CLAUDE.md's own example shape
    (candidate_species, identity, coverage, status, thresholds_applied)
    plus `reason` (same convention as Stages 1/3/7's own result schemas)
    and `taxonomic_consistency_checked` -- see
    app/pipeline/identification.py's module docstring for why that's
    always False today."""

    candidate_species: Optional[str] = None
    identity: Optional[float] = None
    coverage: Optional[float] = None
    status: str  # "PASS" | "AMBIGUOUS" | "REVIEW REQUIRED"
    reason: Optional[str] = None
    thresholds_applied: dict
    taxonomic_consistency_checked: bool = False
