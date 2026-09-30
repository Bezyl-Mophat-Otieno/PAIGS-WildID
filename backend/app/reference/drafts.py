"""Reference database drafts -- the human review/approve gate between
app.reference.bold's automated fetch and app.reference.publish's existing,
unchanged publish_reference_db(). See app.models.reference.
ReferenceDatabaseDraft's own docstring for why this is a separate table
and workflow rather than auto-publishing a BOLD pull directly.

Three actions, matching the three things a reviewer can do with a draft:
create it (fetch + filter, produces a pending_review row), publish it
(hands its FASTA to the real publish path, exactly as if a person had
uploaded it by hand), or discard it (rejected, nothing further happens).
No "edit the draft's FASTA in place" action -- a reviewer who wants to
hand-edit the candidate set downloads it (the stored fasta_path) and uses
the existing manual publish flow instead, same as any other curated
FASTA.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from app.configuration import service as config_service
from app.models.reference import ReferenceDatabaseDraft
from app.reference.bold import BoldApiError, fetch_bold_taxon
from app.reference.publish import REFERENCE_DATA_ROOT, publish_reference_db
from app.schemas.reference import PublishResult


class DraftNotFoundError(Exception):
    def __init__(self, draft_id: str):
        self.draft_id = draft_id
        super().__init__(f"Reference database draft '{draft_id}' not found.")


class DraftNotPendingError(Exception):
    """Raised when publish/discard is attempted on a draft that's already
    been published or discarded -- both are terminal; a reviewer who
    wants a different outcome fetches a new draft rather than reusing an
    old one."""

    def __init__(self, draft_id: str, status: str):
        self.draft_id = draft_id
        self.status = status
        super().__init__(f"Draft '{draft_id}' is already {status!r}, not pending review.")


def _drafts_root(reference_data_root: Optional[Path] = None) -> Path:
    root = Path(reference_data_root) if reference_data_root is not None else REFERENCE_DATA_ROOT
    return root / "drafts"


def create_draft(
    taxon: str,
    db: Session,
    *,
    marker: Optional[str] = None,
    max_records_per_species: Optional[int] = None,
    min_sequence_length: Optional[int] = None,
    max_n_proportion: Optional[float] = None,
    require_species_level: Optional[str] = None,
    requested_by: Optional[str] = None,
    reference_data_root: Optional[Path] = None,
) -> ReferenceDatabaseDraft:
    """Fetches from BOLD (app.reference.bold.fetch_bold_taxon) and writes
    a pending_review draft row -- never touches ReferenceDatabaseVersion
    or the active reference database. Raises BoldApiError unchanged (the
    caller, e.g. the API layer, maps it to an HTTP status) for a genuine
    fetch failure; a recognized taxon with zero usable records after
    filtering still produces a real draft (total_kept == 0 is visible in
    its summary), not an error, since that's itself useful information
    for the reviewer (e.g. "this taxon has almost no species-level BOLD
    records yet").

    The four filtering knobs (max_records_per_species, min_sequence_length,
    max_n_proportion, require_species_level) go through the same
    Configuration subsystem every Run stage's own thresholds do
    (app.configuration.catalog's "bold_fetch" entries): omitted here means
    the current global default; passed here means a deliberate, one-fetch
    override -- never silently different between two callers who both
    left it unset. Reusing this machinery also gets bounds/choices
    validation (a bad max_n_proportion, or a require_species_level value
    that isn't one of the two real choices) for free, the same
    UnknownConfigKeyError/ConfigValueOutOfBoundsError/
    ConfigValueNotAllowedError the rest of the app already raises for it.
    """
    overrides = {}
    if max_records_per_species is not None:
        overrides["bold_fetch.max_records_per_species"] = max_records_per_species
    if min_sequence_length is not None:
        overrides["bold_fetch.min_sequence_length"] = min_sequence_length
    if max_n_proportion is not None:
        overrides["bold_fetch.max_n_proportion"] = max_n_proportion
    if require_species_level is not None:
        overrides["bold_fetch.require_species_level"] = require_species_level

    # effective_thresholds() alone only checks that each override key is
    # recognized -- it does not check the *value* against bounds/choices
    # (that's what POST /runs' own config_overrides handling calls
    # validate_overrides() separately for). Doing the same here explicitly
    # is what actually makes good on this function's own docstring promise
    # of bounds/choices validation.
    config_service.validate_overrides(overrides)
    effective = config_service.effective_thresholds(db, overrides)
    kwargs = config_service.kwargs_for_stage(effective, "bold_fetch")
    if marker is not None:
        kwargs["marker"] = marker

    result = fetch_bold_taxon(taxon, **kwargs)

    draft = ReferenceDatabaseDraft(
        source="bold",
        taxon=result.taxon,
        marker=result.marker,
        fasta_path="",  # filled in below, once we have the draft's own id
        summary={
            "total_fetched": result.total_fetched,
            "total_kept": result.total_kept,
            "drop_reasons": result.drop_reasons,
            "species": [
                {
                    "species": s.species,
                    "kept_count": s.kept_count,
                    "dropped_count": s.dropped_count,
                    "bins": s.bins,
                    "bin_consistent": s.bin_consistent,
                    "identification_rank": s.identification_rank,
                }
                for s in result.species
            ],
            "species_sharing_a_bin": result.species_sharing_a_bin,
            "total_kept_at_lower_rank": result.total_kept_at_lower_rank,
        },
        status="pending_review",
        requested_by=requested_by,
    )
    db.add(draft)
    db.flush()  # populate draft.id before using it as the storage key

    draft_dir = _drafts_root(reference_data_root) / draft.id
    draft_dir.mkdir(parents=True, exist_ok=True)
    fasta_path = draft_dir / "candidate.fasta"
    fasta_path.write_text(result.fasta_content)
    draft.fasta_path = str(fasta_path)

    db.commit()
    db.refresh(draft)
    return draft


def list_drafts(db: Session) -> List[ReferenceDatabaseDraft]:
    return db.query(ReferenceDatabaseDraft).order_by(ReferenceDatabaseDraft.fetched_at.desc()).all()


def get_draft(draft_id: str, db: Session) -> ReferenceDatabaseDraft:
    draft = db.get(ReferenceDatabaseDraft, draft_id)
    if draft is None:
        raise DraftNotFoundError(draft_id)
    return draft


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def publish_draft(draft_id: str, version: str, db: Session) -> PublishResult:
    """The actual "go live" action -- a human, reviewing this draft's
    summary, decided it's trustworthy. Hands the draft's already-written
    FASTA to the exact same publish_reference_db() a manually-curated
    upload goes through (see app.reference.publish); no logic is
    duplicated or special-cased for a BOLD-sourced draft."""
    draft = get_draft(draft_id, db)
    if draft.status != "pending_review":
        raise DraftNotPendingError(draft_id, draft.status)

    result = publish_reference_db(Path(draft.fasta_path), version, db=db)

    draft.status = "published"
    draft.published_as_version = result.version
    draft.reviewed_at = _utcnow()
    db.commit()
    db.refresh(draft)
    return result


def discard_draft(draft_id: str, db: Session) -> ReferenceDatabaseDraft:
    draft = get_draft(draft_id, db)
    if draft.status != "pending_review":
        raise DraftNotPendingError(draft_id, draft.status)

    draft.status = "discarded"
    draft.reviewed_at = _utcnow()
    db.commit()
    db.refresh(draft)
    return draft
