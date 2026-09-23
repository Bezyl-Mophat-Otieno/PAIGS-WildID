import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, JSON, String
from sqlalchemy.orm import relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Run(Base):
    """
    One analyst's attempt to identify one sample.

    status is the overall Run lifecycle: in_progress | paused | completed | failed.
    It only becomes "completed" once every stage through Reporting has finished
    (see docs/PLAN.md Run/Stage data model) -- it is NOT the same as an individual
    stage's own status.
    """

    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=_uuid)
    sample_id = Column(String, nullable=False)
    original_filenames = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    current_stage = Column(String, nullable=False, default="import")
    status = Column(String, nullable=False, default="in_progress")

    stages = relationship(
        "Stage",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="Stage.started_at",
    )
