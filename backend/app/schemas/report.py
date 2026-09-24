"""Stage 11 -- Reporting: input schema.

Per CLAUDE.md, Reporting "aggregates every other stage's finalized
schema" -- ReportInput doesn't introduce any new computed data, it's a
plain aggregate of the already-typed outputs every prior stage already
produces (FileFormatCheck, SanityCheckResult, TrimResult, ...). Building
this report is purely a lay-out problem, not a decision-making one.

Matches the two-path shape Stages 5-7 already established: `orientation`
and `consensus` are None on the single-read path (a Stage 3 QC failure on
one read, or only one file was ever uploaded to begin with), and
`single_read_reason` records which of those two applies.

`thresholds_used` is a free-form audit dict for the stages whose own
result schema doesn't already carry the parameters used (SanityCheckResult
and UsabilityCheckResult only ever return a status + reason, not the
thresholds compared against -- unlike TrimResult's own `trim_params` or
IdentificationResult's own `thresholds_applied`, which need no
duplication here). Whoever assembles a ReportInput already has these
values in hand (they're what was passed as keyword thresholds into
check_sanity_for_files / check_usability_from_*), so this is just a place
to carry them through rather than a new source of truth.
"""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.blast import BlastSearchResult
from app.schemas.consensus import ConsensusResult
from app.schemas.fasta import FastaResult
from app.schemas.format_check import FileFormatCheck
from app.schemas.identification import IdentificationResult
from app.schemas.orientation import OrientationResult
from app.schemas.sanity_check import SanityCheckResult
from app.schemas.trim import TrimResult
from app.schemas.usability_check import UsabilityCheckResult

DEFAULT_LIMITATION = "This is an expert-assistance result, not a standalone forensic conclusion."


class ReportInput(BaseModel):
    run_id: str
    sample_id: str
    original_filenames: List[str]
    generated_at: datetime

    # Keyed "forward"/"reverse", matching every prior stage's own
    # per-slot convention -- only whichever slot(s) survived are present.
    format_check: Dict[str, FileFormatCheck]
    sanity_check: Dict[str, SanityCheckResult]
    trim: Dict[str, TrimResult]

    # None on the two-read path; set on the single-read path along with
    # single_read_reason ("qc_failure" | "single_file_provided", per
    # CLAUDE.md's Stage 3 branching table).
    single_read_reason: Optional[str] = None
    orientation: Optional[OrientationResult] = None
    consensus: Optional[ConsensusResult] = None

    usability_check: UsabilityCheckResult
    fasta: FastaResult
    blast: BlastSearchResult
    identification: IdentificationResult

    thresholds_used: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=lambda: [DEFAULT_LIMITATION])
