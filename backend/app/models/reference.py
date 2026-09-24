"""
Models for Reference Database Setup (Part A) -- see
claude/reference-database-setup-status.md for the full design.

Two tables, matching the brief's "two artifacts, worth keeping distinct":
ReferenceEntry mirrors the curated FASTA's own header metadata (queryable/
UI-manageable without re-parsing files), while ReferenceDatabaseVersion
tracks each published snapshot and which one is currently active. Neither
table stores the BLAST index itself -- that's app.pipeline.blast's
build_reference_database() output on disk, at the path this table records.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReferenceEntry(Base):
    """
    One curated species entry from a published reference FASTA's header,
    per CLAUDE.md's Stage 9 description (species/taxonomy, accession,
    source). Scoped per `version`, not just per species -- CLAUDE.md
    requires the reference DB version used to be recorded per Run, and an
    older version's entries must stay intact and queryable after a newer
    version becomes active, for audit purposes. `accession` isn't named
    explicitly in Part A's brief but is included here since it's parsed
    for free from the header and is the natural key tying a BlastHit's own
    `accession` field back to its curated entry.
    """

    __tablename__ = "reference_entries"

    id = Column(String, primary_key=True, default=_uuid)
    version = Column(String, nullable=False, index=True)
    accession = Column(String, nullable=False)
    species = Column(String, nullable=False)
    taxonomy = Column(String, nullable=True)  # only when the header actually carries it
    source = Column(String, nullable=False)  # the source FASTA filename this entry was published from
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class ReferenceDatabaseVersion(Base):
    """
    One published reference-database snapshot. `is_active` marks which
    version new Runs' Stage 9 should search against -- exactly one row is
    kept active at a time (enforced in app.reference.publish, as a plain
    two-statement update, rather than a DB-specific partial unique index,
    since both SQLite and Postgres need to work per CLAUDE.md). Rows are
    never deleted once published -- a Run's recorded version string must
    always resolve back to a real, inspectable snapshot, even after a
    newer version becomes active.
    """

    __tablename__ = "reference_database_versions"

    id = Column(String, primary_key=True, default=_uuid)
    version = Column(String, nullable=False, unique=True)
    fasta_path = Column(String, nullable=False)
    db_prefix = Column(String, nullable=False)
    sequence_count = Column(Integer, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
