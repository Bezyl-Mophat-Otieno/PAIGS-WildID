import json
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import storage
from app.configuration import service as config_service
from app.configuration.errors import ConfigValueOutOfBoundsError, UnknownConfigKeyError
from app.db import get_db
from app.models.run import Run
from app.models.stage import STAGE_TYPES, Stage
from app.naming import default_sample_id
from app.orchestration.execute import RunAlreadyExecutedError, RunNotFoundError, execute_run
from app.orchestration.rerun import create_rerun
from app.schemas.run import RerunRequest, RunDetail, RunPatch, RunRead, StageDetail

router = APIRouter(prefix="/runs", tags=["runs"])

ALLOWED_EXTENSION = ".ab1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_config_overrides(raw: Optional[str]) -> Optional[dict]:
    """Shared by create_run below -- POST /runs is multipart/form-data
    (because of the file uploads), so config overrides travel as a JSON-
    encoded text field rather than a JSON request body. Raises
    HTTPException(422) for anything malformed; returns None if the field
    was omitted or blank."""
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="config_overrides must be valid JSON.")

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=422,
            detail="config_overrides must be a JSON object of {config key: value}.",
        )

    try:
        config_service.validate_overrides(parsed)
    except (UnknownConfigKeyError, ConfigValueOutOfBoundsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return parsed


@router.post("", response_model=RunRead, status_code=201)
def create_run(
    forward_read: Optional[UploadFile] = File(None),
    reverse_read: Optional[UploadFile] = File(None),
    sample_id: Optional[str] = Form(None),
    config_overrides: Optional[str] = Form(None),
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

    config_overrides is CLAUDE.md's "optional config overrides" for this
    specific run -- a JSON object of {config key: value} (see GET /config
    for the full list of valid keys), layered on top of the global
    Configuration subsystem's values when this run is later executed
    (POST /runs/{id}/execute). Omit it to use the global defaults
    unchanged.
    """
    slots_and_uploads = [
        (slot, f)
        for slot, f in (("forward", forward_read), ("reverse", reverse_read))
        if f is not None and f.filename
    ]
    slots = [slot for slot, _ in slots_and_uploads]
    uploads = [f for _, f in slots_and_uploads]

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

    parsed_overrides = _parse_config_overrides(config_overrides)

    original_filenames = [f.filename for f in uploads]
    now = _utcnow()

    run = Run(
        sample_id=sample_id.strip() if sample_id else default_sample_id(original_filenames),
        original_filenames=original_filenames,
        created_at=now,
        current_stage="import",
        status="in_progress",
        config_overrides=parsed_overrides,
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
            # Which upload slot each stored file actually came from, same
            # order as stored_filenames -- needed by orchestration
            # (POST /runs/{id}/execute) since a single-file run's
            # stored_filenames alone can't distinguish a lone forward_read
            # from a lone reverse_read.
            "slots": slots,
        },
        started_at=now,
        completed_at=_utcnow(),
        attempt_number=1,
    )
    db.add(stage)
    db.commit()
    db.refresh(run)

    return run


@router.post("/{run_id}/execute", response_model=RunDetail)
def execute_run_endpoint(run_id: str, db: Session = Depends(get_db)):
    """
    Run every stage through to completion automatically (build-order item
    9 -- see app.orchestration.execute for the full sequencing/branching
    logic). Always returns 200 with the Run's resulting state, whichever
    stage it stopped at -- a biological/QC stop (invalid file, sanity
    failure, no orientation overlap, usability failure) or an operational
    one (no reference database published) is data the caller reads off
    the Run/Stage response, not an HTTP error. 404/409 are reserved for
    genuine request problems: an unknown run, or one that's already been
    executed (no stage-level re-run for MVP -- see POST /runs/{id}/rerun
    for trying different configuration instead).
    """
    try:
        run = execute_run(run_id, db)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found.")
    except RunAlreadyExecutedError:
        raise HTTPException(
            status_code=409,
            detail="Run has already been executed. Use POST /runs/{id}/rerun to try "
            "different configuration on a brand-new Run instead.",
        )
    return run


@router.post("/{run_id}/rerun", response_model=RunRead, status_code=201)
def rerun_run(run_id: str, payload: Optional[RerunRequest] = None, db: Session = Depends(get_db)):
    """
    CLAUDE.md's Configuration model: "trying different settings means
    triggering a whole new Run... rather than editing/re-running any
    piece of the original -- the two Runs sit side by side, fully
    independent and comparable." Reuses `run_id`'s already-stored AB1
    file(s) byte-for-byte under a brand-new Run id; the source Run itself
    is never touched. The new Run is created but not executed -- call
    POST /runs/{new_id}/execute next, same as any freshly-uploaded run.
    """
    overrides = payload.config_overrides if payload else None
    new_sample_id = payload.sample_id if payload else None
    try:
        new_run = create_rerun(
            run_id, db, config_overrides=overrides, sample_id=new_sample_id
        )
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found.")
    except (UnknownConfigKeyError, ConfigValueOutOfBoundsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return new_run


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
