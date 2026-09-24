import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
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

    config_overrides: the per-run threshold overrides supplied at creation
    (POST /runs) or rerun (POST /runs/{id}/rerun) time, layered on top of
    the global Configuration subsystem's values at execute time (see
    app.configuration.service.effective_thresholds) -- null when the
    analyst didn't override anything, in which case the run's effective
    thresholds are whatever the global config held at execute time.
    Recorded on the Run itself (not just used transiently) so it's
    visible in the audit trail and in the run history list, per
    CLAUDE.md's "a deliberate choice, not silent inheritance."

    rerun_of: set only on a Run created via POST /runs/{id}/rerun --
    the original Run this one reused the file(s) of, to try different
    configuration. Null for a normal upload-created Run. CLAUDE.md's
    "no stage-level re-run for MVP... the two Runs sit side by side,
    fully independent and comparable" -- this column is what lets an
    analyst (or the UI) actually find that sibling pair again later;
    the original Run itself is never modified by a rerun.

    owner_id: whichever User created this Run (via POST /runs) or
    triggered its rerun (via POST /runs/{id}/rerun) -- required, every
    Run has exactly one owner. Runs are scoped per-owner for now: an
    admin's own view of /runs is restricted to their own Runs exactly
    like an analyst's, per the product decision that cross-tenant admin
    visibility ("let an admin see everyone's runs") is a deliberate
    later step, not this one. See app.api.runs._get_owned_run.
    """

    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=_uuid)
    sample_id = Column(String, nullable=False)
    original_filenames = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    current_stage = Column(String, nullable=False, default="import")
    status = Column(String, nullable=False, default="in_progress")
    config_overrides = Column(JSON, nullable=True)
    rerun_of = Column(String, ForeignKey("runs.id"), nullable=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)

    stages = relationship(
        "Stage",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="Stage.started_at",
    )
