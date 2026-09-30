from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReferenceEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    accession: str
    species: str
    taxonomy: Optional[str] = None
    source: str
    version: str


class PublishResult(BaseModel):
    version: str
    fasta_path: str
    db_prefix: str
    sequence_count: int


class ReferenceDatabaseVersionRead(BaseModel):
    """API read shape for a published ReferenceDatabaseVersion row --
    used by the /reference-database/versions and /active endpoints."""

    model_config = ConfigDict(from_attributes=True)

    version: str
    fasta_path: str
    db_prefix: str
    sequence_count: int
    is_active: bool
    published_at: datetime


class BoldFetchRequest(BaseModel):
    """POST /reference-database/drafts's body. `taxon` is unrestricted
    free text -- "no limitation as long as it's something we could
    pull" -- passed straight through to BOLD's own query API, which
    validates it against BOLD's controlled taxonomic vocabulary (an
    unrecognized taxon comes back as a 422, not a silent empty result).
    """

    taxon: str = Field(..., min_length=1)
    marker: Optional[str] = None
    # All four None by default -- omitted means "use the current global
    # bold_fetch.* default" (app.configuration.catalog), not a hardcoded
    # fallback duplicated here. See app.reference.drafts.create_draft's
    # own docstring for why these go through the Configuration subsystem
    # rather than being plain optional fields with their own defaults.
    max_records_per_species: Optional[int] = Field(None, ge=1)
    min_sequence_length: Optional[int] = Field(None, ge=1)
    max_n_proportion: Optional[float] = Field(None, ge=0.0, le=1.0)
    require_species_level: Optional[str] = None


class BoldSpeciesSummaryRead(BaseModel):
    species: str
    kept_count: int
    dropped_count: int
    bins: List[str]
    bin_consistent: bool
    identification_rank: str


class ReferenceDraftSummaryRead(BaseModel):
    total_fetched: int
    total_kept: int
    drop_reasons: Dict[str, int]
    species: List[BoldSpeciesSummaryRead]
    species_sharing_a_bin: List[List[str]]
    total_kept_at_lower_rank: int = 0


class ReferenceDraftRead(BaseModel):
    """API read shape for a ReferenceDatabaseDraft row -- a candidate
    reference set pending human review, never itself searchable/active
    (see app.models.reference.ReferenceDatabaseDraft's own docstring)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    taxon: str
    marker: str
    summary: ReferenceDraftSummaryRead
    status: str
    requested_by: Optional[str] = None
    fetched_at: datetime
    reviewed_at: Optional[datetime] = None
    published_as_version: Optional[str] = None


class ReferenceDraftPublish(BaseModel):
    version: str = Field(..., min_length=1)
