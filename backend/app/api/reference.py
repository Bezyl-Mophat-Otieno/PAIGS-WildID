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
from app.db import get_db
from app.models.reference import ReferenceDatabaseVersion
from app.models.user import User
from app.reference.publish import InvalidReferenceFastaError, get_active_version, publish_reference_db
from app.schemas.reference import PublishResult, ReferenceDatabaseVersionRead

router = APIRouter(prefix="/reference-database", tags=["reference-database"])

ALLOWED_EXTENSIONS = (".fasta", ".fa", ".fna")


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
