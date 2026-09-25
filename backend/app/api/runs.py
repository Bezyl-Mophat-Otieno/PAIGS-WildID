import json
from datetime import datetime, timezone
from pathlib import Path as FilePath
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import storage
from app.auth.dependencies import get_current_user
from app.configuration import service as config_service
from app.configuration.errors import ConfigValueOutOfBoundsError, UnknownConfigKeyError
from app.db import get_db
from app.models.run import Run
from app.models.stage import STAGE_TYPES, Stage
from app.models.user import User
from app.naming import default_sample_id
from app.orchestration.execute import RunAlreadyExecutedError, RunNotFoundError, execute_run
from app.orchestration.rerun import create_rerun
from app.pipeline.chromatogram import extract_chromatogram
from app.schemas.chromatogram import ChromatogramResult
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


def _get_owned_run(run_id: str, current_user: User, db: Session) -> Run:
    """Looks up a Run and confirms `current_user` owns it, in one step --
    used by every endpoint below that *acts on* a specific run_id
    (execute, rerun, patch). Returns 404 (not 403) when the Run exists
    but belongs to someone else, same as when it doesn't exist at all: a
    caller shouldn't be able to tell the difference, and shouldn't be
    able to confirm another user's Run even exists. Strict owner-only
    even for an admin -- see _get_visible_run's docstring for why the
    two are deliberately different."""
    run = db.get(Run, run_id)
    if run is None or run.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


def _get_visible_run(run_id: str, current_user: User, db: Session) -> Run:
    """Like _get_owned_run, but an admin may also *view* (never act on)
    any user's Run -- the cross-tenant visibility the user asked for:
    "we will expand the admin to see all the runs and analysis of
    everyone." Used only by the read-only endpoints: GET /runs/{id},
    GET /runs/{id}/stages/{type}, GET /runs/{id}/report. Still 404 (not
    403) for anyone who can't see the Run, admin or not -- same
    can't-confirm-existence reasoning as _get_owned_run.

    Deliberately not used by execute/rerun/patch: "see all the runs and
    analysis of everyone" is a request to view everyone's work, not a
    request to let an admin mutate another user's data on their behalf
    -- especially with this pipeline headed toward forensic/evidentiary
    use, where a silent cross-user mutation would undermine the audit
    trail. Those three endpoints keep using _get_owned_run, so an admin
    is scoped exactly like an analyst for anything that writes."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


def _resolve_slot_path(run: Run, slot: str, db: Session) -> FilePath:
    """Finds the stored AB1 file for one of this Run's upload slots
    ("forward" or "reverse"), the same way
    app.orchestration.execute._resolve_file_paths does for orchestration
    itself -- reads Stage 0 (Import)'s own recorded slots/stored_filenames
    rather than guessing a filename. Raises 404 (not the caller's
    problem to distinguish from "run not found") when this Run never had
    that slot uploaded."""
    import_stage = (
        db.query(Stage)
        .filter(Stage.run_id == run.id, Stage.stage_type == "import")
        .order_by(Stage.attempt_number.desc())
        .first()
    )
    output = (import_stage.output or {}) if import_stage else {}
    slots = output.get("slots") or []
    stored_filenames = output.get("stored_filenames") or []
    mapping = dict(zip(slots, stored_filenames))
    if slot not in mapping:
        raise HTTPException(
            status_code=404, detail=f"No '{slot}' read was uploaded for this run."
        )
    return storage.run_dir(run.id) / mapping[slot]


@router.post("", response_model=RunRead, status_code=201)
def create_run(
    forward_read: Optional[UploadFile] = File(None),
    reverse_read: Optional[UploadFile] = File(None),
    sample_id: Optional[str] = Form(None),
    config_overrides: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
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
        owner_id=current_user.id,
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
def execute_run_endpoint(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run every stage through to completion automatically (build-order item
    9 -- see app.orchestration.execute for the full sequencing/branching
    logic). Always returns 200 with the Run's resulting state, whichever
    stage it stopped at -- a biological/QC stop (invalid file, sanity
    failure, no orientation overlap, usability failure) or an operational
    one (no reference database published) is data the caller reads off
    the Run/Stage response, not an HTTP error. 404/409 are reserved for
    genuine request problems: an unknown (or not-owned-by-the-caller)
    run, or one that's already been executed (no stage-level re-run for
    MVP -- see POST /runs/{id}/rerun for trying different configuration
    instead).
    """
    _get_owned_run(run_id, current_user, db)
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


@router.post("/{run_id}/rerun", response_model=RunDetail, status_code=201)
def rerun_run(
    run_id: str,
    payload: Optional[RerunRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    CLAUDE.md's Configuration model: "trying different settings means
    triggering a whole new Run... rather than editing/re-running any
    piece of the original -- the two Runs sit side by side, fully
    independent and comparable." Reuses `run_id`'s already-stored AB1
    file(s) byte-for-byte under a brand-new Run id; the source Run itself
    is never touched. Only the source Run's own owner may rerun it; the
    new Run is owned by that same caller.

    By default the new Run is only created, not executed -- call
    POST /runs/{new_id}/execute next, same two-step shape as any
    freshly-uploaded run. Pass `auto_execute: true` in the body to run it
    through to completion (or its stopping point) in this same call
    instead -- see RerunRequest's own docstring. Either way the response
    is a RunDetail, so a fully-executed rerun's stages are visible
    immediately, without a follow-up GET.
    """
    _get_owned_run(run_id, current_user, db)

    overrides = payload.config_overrides if payload else None
    new_sample_id = payload.sample_id if payload else None
    auto_execute = payload.auto_execute if payload else False
    try:
        new_run = create_rerun(
            run_id,
            db,
            owner_id=current_user.id,
            config_overrides=overrides,
            sample_id=new_sample_id,
        )
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found.")
    except (UnknownConfigKeyError, ConfigValueOutOfBoundsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if auto_execute:
        new_run = execute_run(new_run.id, db)

    return new_run


@router.get("", response_model=List[RunRead])
def list_runs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """An admin sees every user's Runs; anyone else sees only their own
    -- see _get_visible_run's docstring for the same rule applied to a
    single Run."""
    query = db.query(Run)
    if current_user.role != "admin":
        query = query.filter(Run.owner_id == current_user.id)
    return query.order_by(Run.created_at.desc()).all()


@router.get("/{run_id}", response_model=RunDetail)
def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _get_visible_run(run_id, current_user, db)


@router.get("/{run_id}/stages/{stage_type}", response_model=StageDetail)
def get_stage(
    run_id: str,
    stage_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_visible_run(run_id, current_user, db)

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


@router.get("/{run_id}/chromatogram/{slot}", response_model=ChromatogramResult)
def get_chromatogram(
    run_id: str,
    slot: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Raw AB1 chromatogram/peak data for one of this Run's upload slots --
    build-order item "expose the raw AB1 chromatogram/peak data ...
    needed so an analyst can visually double-check a flagged or
    low-confidence base call instead of just trusting a number." Not in
    CLAUDE.md's original API shape (docs/PLAN.md's own "Chromatogram
    viewer" future-frontend note already flagged that this needed a new
    endpoint, since nothing served it before). Visibility rules match
    every other read-only single-run endpoint here (_get_visible_run):
    an admin can view any user's chromatogram, an analyst only their
    own. Every stored AB1 file already has this data (it's part of the
    ABIF format itself) -- this is pure extraction, nothing computed.
    """
    run = _get_visible_run(run_id, current_user, db)
    if slot not in ("forward", "reverse"):
        raise HTTPException(status_code=422, detail="slot must be 'forward' or 'reverse'.")

    file_path = _resolve_slot_path(run, slot, db)
    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Stored AB1 file for the '{slot}' slot is missing on disk.",
        )
    return extract_chromatogram(file_path)


@router.get("/{run_id}/report")
def download_report(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Stream Stage 11's generated PDF back to the caller.

    GET /runs/{id}/stages/report (above) already exposes the report
    Stage's *audit-trail* output -- {"report_path": "..."} -- but that's
    a server-side filesystem path, not something a browser or analyst
    can actually fetch; nothing in the API surface let anyone retrieve
    the PDF itself. Not in CLAUDE.md's original API shape list, but a
    necessary complement to it -- a report nobody can download isn't yet
    a usable Stage 11 output. Deliberately its own endpoint (GET
    /runs/{id}/report) rather than a query param on the stage endpoint,
    since the two return fundamentally different content types (JSON
    metadata vs. a PDF file) for different callers (an inspector UI vs.
    a literal file download).
    """
    run = _get_visible_run(run_id, current_user, db)

    stage = (
        db.query(Stage)
        .filter(
            Stage.run_id == run_id,
            Stage.stage_type == "report",
            Stage.status == "completed",
        )
        .order_by(Stage.attempt_number.desc())
        .first()
    )
    if stage is None:
        raise HTTPException(
            status_code=404,
            detail="This run has no completed report yet -- it either hasn't been "
            "executed, or stopped before Stage 11 (Reporting).",
        )

    report_path = FilePath((stage.output or {}).get("report_path", ""))
    if not report_path.is_file():
        # Defensive: the Stage row says Reporting completed, but its file
        # is missing from disk (e.g. storage was reset independently of
        # the database -- exactly what happened locally after a `rm
        # paigs.db` without also clearing storage/). Surfaced as a clear
        # 404 rather than a raw FileResponse crash.
        raise HTTPException(
            status_code=404,
            detail=f"Report stage completed but its PDF file is missing on disk "
            f"({report_path}).",
        )

    filename = f"{run.sample_id}_report.pdf"
    return FileResponse(report_path, media_type="application/pdf", filename=filename)


@router.patch("/{run_id}", response_model=RunRead)
def patch_run(
    run_id: str,
    payload: RunPatch,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _get_owned_run(run_id, current_user, db)

    run.sample_id = payload.sample_id
    db.commit()
    db.refresh(run)
    return run
