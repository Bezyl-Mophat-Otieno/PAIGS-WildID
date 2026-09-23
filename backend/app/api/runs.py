from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import storage
from app.db import get_db
from app.models.run import Run
from app.models.stage import STAGE_TYPES, Stage
from app.schemas.run import RunDetail, RunPatch, RunRead, StageDetail

router = APIRouter(prefix="/runs", tags=["runs"])

ALLOWED_EXTENSION = ".ab1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_sample_id(filenames: List[str]) -> str:
    """Filenames + timestamp become the default sample label (CLAUDE.md Stage 0)."""
    stems = [Path(name).stem for name in filenames]
    timestamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
    return "_".join([*stems, timestamp])


@router.post("", response_model=RunRead, status_code=201)
def create_run(
    forward_read: Optional[UploadFile] = File(None),
    reverse_read: Optional[UploadFile] = File(None),
    sample_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Stage 0 -- Import. Upload into two labeled, independently-optional slots:
    forward_read and reverse_read. Both single-file and two-file are
    first-class entry points -- a single file is not a degraded fallback.
    Labels aren't validated for correctness here (which one is truly forward
    vs. reverse is confirmed later, in Stage 5 Orientation Detection); a
    mismatch there is only ever noted, never blocking. Creates the Run (and
    its completed "import" Stage) immediately, before any parsing happens.
    """
    uploads = [f for f in (forward_read, reverse_read) if f is not None and f.filename]

    if not uploads:
        raise HTTPException(
            status_code=422,
            detail="At least one AB1 file is required (forward_read and/or reverse_read).",
        )

    for upload in uploads:
        if not (upload.filename or "").lower().endswith(ALLOWED_EXTENSION):
            raise HTTPException(
                status_code=422,
                detail=f"'{upload.filename}' is not a .ab1 file.",
            )

    if sample_id is not None and not sample_id.strip():
        raise HTTPException(status_code=422, detail="sample_id cannot be empty.")

    original_filenames = [f.filename for f in uploads]
    now = _utcnow()

    run = Run(
        sample_id=sample_id.strip() if sample_id else _default_sample_id(original_filenames),
        original_filenames=original_filenames,
        created_at=now,
        current_stage="import",
        status="in_progress",
    )
    db.add(run)
    db.flush()  # populate run.id before using it as the storage key

    stored_names = storage.save_uploaded_files(run.id, uploads)

    stage = Stage(
        run_id=run.id,
        stage_type="import",
        status="completed",
        input_ref=None,
        output={
            "original_filenames": original_filenames,
            "stored_filenames": stored_names,
        },
        started_at=now,
        completed_at=_utcnow(),
        attempt_number=1,
    )
    db.add(stage)
    db.commit()
    db.refresh(run)

    return run


@router.get("", response_model=List[RunRead])
def list_runs(db: Session = Depends(get_db)):
    return db.query(Run).order_by(Run.created_at.desc()).all()


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.get("/{run_id}/stages/{stage_type}", response_model=StageDetail)
def get_stage(run_id: str, stage_type: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    if stage_type not in STAGE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown stage_type '{stage_type}'.")

    stage = (
        db.query(Stage)
        .filter(Stage.run_id == run_id, Stage.stage_type == stage_type)
        .order_by(Stage.attempt_number.desc())
        .first()
    )
    if stage is None:
        raise HTTPException(status_code=404, detail=f"Stage '{stage_type}' has not been run yet.")
    return stage


@router.patch("/{run_id}", response_model=RunRead)
def patch_run(run_id: str, payload: RunPatch, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    run.sample_id = payload.sample_id
    db.commit()
    db.refresh(run)
    return run
