from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
