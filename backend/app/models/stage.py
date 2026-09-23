import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.db import Base

STAGE_TYPES = (
    "import",
    "format_check",
    "ab1_extraction",
    "sanity_check",
    "trim",
    "orientation",
    "consensus",
    "usability_check",
    "fasta",
    "blast",
    "identification",
    "report",
)

STAGE_STATUSES = ("pending", "running", "completed", "failed", "skipped")


def _uuid() -> str:
    return str(uuid.uuid4())


class Stage(Base):
    """
    One persisted step of a Run. Never overwritten. Per the 2026-09-23
    CLAUDE.md, there is no stage-level re-run for MVP -- trying different
    config creates a whole new Run instead (POST /runs/{id}/rerun, not yet
    built), so attempt_number stays 1 for every stage today. The column is
    kept since CLAUDE.md's Stage schema still lists it, but nothing in the
    current API increments it.
    """

    __tablename__ = "stages"

    id = Column(String, primary_key=True, default=_uuid)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    stage_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    input_ref = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # Column named "metadata" per CLAUDE.md's schema; the Python attribute is
    # renamed since `metadata` is reserved on SQLAlchemy's declarative Base.
    stage_metadata = Column("metadata", JSON, nullable=True)
    attempt_number = Column(Integer, nullable=False, default=1)

    run = relationship("Run", back_populates="stages")
