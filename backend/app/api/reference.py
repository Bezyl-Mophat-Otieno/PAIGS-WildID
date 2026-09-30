"""
Reference Database Setup (Part A) -- admin HTTP endpoints.

The HTTP equivalent of running scripts/publish_reference_db.py by hand,
so a curator doesn't have to have terminal/repo access to publish a new
reference database version. Calls the exact same
app.reference.publish.publish_reference_db() the CLI script calls --
per Part A's own design, no logic is duplicated here, only the upload
handling and HTTP status-code mapping.

Runs synchronously, like every other endpoint in this app today -- there
is no background-job infrastructure yet. For a small curated reference
set (the realistic MVP size) this completes within a normal request; a
very large FASTA would make the request slow. The original Part A brief
names a background-job version as a later step -- not built here, since
it would mean adding job-queue infrastructure this app doesn't have
anywhere yet, well beyond what was asked.

GET /versions and GET /active require only an authenticated caller (any
role) -- an analyst needs to see which reference database is active
when interpreting a run. POST /publish is admin-only: publishing a new
version changes what every future Run's Stage 9 search sees for every
user, not just the caller's own, not merely something scoped to the
caller the way a Run is.
"""
import shutil
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin
from app.configuration.errors import ConfigValueNotAllowedError, ConfigValueOutOfBoundsError
from app.db import get_db
from app.models.reference import ReferenceDatabaseVersion
from app.models.user import User
from app.reference import drafts as draft_service
from app.reference.bold import BoldApiError
from app.reference.drafts import DraftNotFoundError, DraftNotPendingError
from app.reference.publish import InvalidReferenceFastaError, get_active_version, publish_reference_db
from app.schemas.reference import (
    BoldFetchRequest,
    PublishResult,
    ReferenceDatabaseVersionRead,
    ReferenceDraftPublish,
    ReferenceDraftRead,
)

router = APIRouter(prefix="/reference-database", tags=["reference-database"])

ALLOWED_EXTENSIONS = (".fasta", ".fa", ".fna")

# Convenience examples for the "pick from a list, or type your own"
# taxon input CLAUDE.md asked for -- purely a UI suggestion list, never a
# server-side restriction: BOLD's own query API (app.reference.bold)
# accepts any taxon it recognizes, not just these.
SUGGESTED_TAXA = [
    "Panthera",
    "Elephantidae",
    "Rhinocerotidae",
    "Manis",
    "Testudinidae",
    "Ursidae",
    "Falconidae",
]


@router.post("/publish", response_model=PublishResult, status_code=201)
def publish(
    fasta: UploadFile = File(...),
    version: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Publish a new reference database version from an uploaded curated
    FASTA -- validates it, builds a real BLAST index via makeblastdb,
    records one ReferenceEntry per species, and marks this version
    active. See publish_reference_db()'s own docstring for the full
    behavior; this endpoint only adds upload handling on top of it.
    """
    if not (fasta.filename or "").lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=422,
            detail=f"'{fasta.filename}' doesn't look like a FASTA file "
            f"(expected one of {ALLOWED_EXTENSIONS}).",
        )
    if not version.strip():
        raise HTTPException(status_code=422, detail="version cannot be empty.")

    # publish_reference_db shells out to makeblastdb, which needs a real
    # file on disk -- the CLI script's argparse already hands it one;
    # here the uploaded file is spooled to a temp path first, the one
    # piece of glue an HTTP upload needs that the CLI path doesn't.
    with tempfile.NamedTemporaryFile(suffix=".fasta", delete=False) as tmp:
        shutil.copyfileobj(fasta.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        result = publish_reference_db(tmp_path, version.strip(), db=db)
    except InvalidReferenceFastaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return result


@router.get("/versions", response_model=List[ReferenceDatabaseVersionRead])
def list_versions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(ReferenceDatabaseVersion)
        .order_by(ReferenceDatabaseVersion.published_at.desc())
        .all()
    )


@router.get("/active", response_model=ReferenceDatabaseVersionRead)
def active_version(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    active = get_active_version(db)
    if active is None:
        raise HTTPException(
            status_code=404, detail="No reference database has been published yet."
        )
    return active


@router.get("/suggested-taxa", response_model=List[str])
def suggested_taxa(current_user: User = Depends(get_current_user)):
    """A short list of example taxa for the "fetch from BOLD" screen's
    input to suggest -- convenience only, never a restriction (see
    SUGGESTED_TAXA's own comment)."""
    return SUGGESTED_TAXA


@router.post("/drafts", response_model=ReferenceDraftRead, status_code=201)
def create_draft(
    payload: BoldFetchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Fetches candidate records from BOLD for `payload.taxon` and writes
    a pending-review draft -- never touches the active reference
    database (see app.reference.drafts.create_draft's own docstring).
    Admin-only for the same reason POST /publish is: this is part of the
    curation workflow that ultimately changes what every future Run
    searches against, not something scoped to the caller alone.
    """
    try:
        draft = draft_service.create_draft(
            payload.taxon,
            db,
            marker=payload.marker,
            max_records_per_species=payload.max_records_per_species,
            min_sequence_length=payload.min_sequence_length,
            max_n_proportion=payload.max_n_proportion,
            require_species_level=payload.require_species_level,
            requested_by=current_user.id,
        )
    except BoldApiError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ConfigValueOutOfBoundsError, ConfigValueNotAllowedError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return draft


@router.get("/drafts", response_model=List[ReferenceDraftRead])
def list_drafts(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return draft_service.list_drafts(db)


@router.get("/drafts/{draft_id}", response_model=ReferenceDraftRead)
def get_draft(
    draft_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    try:
        return draft_service.get_draft(draft_id, db)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/drafts/{draft_id}/publish", response_model=PublishResult)
def publish_draft(
    draft_id: str,
    payload: ReferenceDraftPublish,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """The human review/approve step: a reviewer has looked at this
    draft's summary (species kept, BIN-consistency flags, drop reasons)
    and decided it's trustworthy. This is the only path that turns a BOLD
    fetch into something Runs can actually search against -- it hands the
    draft's FASTA to the exact same publish_reference_db() a manually-
    curated upload goes through, with no special-casing."""
    try:
        return draft_service.publish_draft(draft_id, payload.version.strip(), db)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DraftNotPendingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidReferenceFastaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/drafts/{draft_id}/discard", response_model=ReferenceDraftRead)
def discard_draft(
    draft_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    try:
        return draft_service.discard_draft(draft_id, db)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DraftNotPendingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
