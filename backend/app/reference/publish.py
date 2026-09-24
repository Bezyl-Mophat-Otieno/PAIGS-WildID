"""
Reference Database Setup -- Part A.

Produces the one thing Stage 9 (BLAST comparison) depends on but that no
Run ever creates: a BLAST-searchable reference index. It's prepared ahead
of time by a curator (a genomics lead maintaining the species reference
set), not by a lab analyst running samples -- a genuinely different
workflow from the rest of the pipeline: infrequent (only when the
reference species set changes), administrative rather than per-sample,
and for MVP, script-driven (scripts/publish_reference_db.py is a thin
argument-parsing wrapper around publish_reference_db() below) rather than
UI-driven.

The core logic lives here as a plain importable function specifically so
a future admin-UI endpoint (POST /reference-database/publish) can call
the exact same code path the CLI script calls today, with no duplicated
logic and no risk of the two paths drifting apart -- see
claude/reference-database-setup-status.md for the full design and the
planned MVP-to-admin-UI swap.

Two artifacts, kept deliberately distinct, per the brief:
- The FASTA file: the curated, human-editable source of truth for what's
  in the reference set. Copied into a permanent, version-labeled location
  (REFERENCE_DATA_ROOT/<version>/reference.fasta) and never modified
  again once published.
- The BLAST index (.nin/.nsq/.nhr and friends): a derived, disposable
  build artifact, regenerated from the FASTA via
  app.pipeline.blast.build_reference_database (the makeblastdb wrapper
  already built for Stage 9) -- safe to delete and rebuild at any time,
  as long as the FASTA is kept.
"""
import os
import shutil
from pathlib import Path
from typing import List, Optional

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from sqlalchemy.orm import Session

from app.models.reference import ReferenceDatabaseVersion, ReferenceEntry
from app.pipeline.blast import build_reference_database
from app.schemas.reference import PublishResult

REFERENCE_DATA_ROOT = Path(
    os.environ.get(
        "PAIGS_REFERENCE_DATA_ROOT",
        Path(__file__).resolve().parent.parent.parent / "reference_data",
    )
)


class InvalidReferenceFastaError(ValueError):
    """Raised when the given FASTA doesn't parse, or parses to zero usable records."""


def _validate_fasta(fasta_path: Path) -> List[SeqRecord]:
    """
    Attempt to parse the FASTA -- the parse attempt is the check, same
    "attempting the parse itself is the check" philosophy CLAUDE.md
    states for Stage 1's AB1 format check, plus an explicit non-empty
    check (Bio.SeqIO.parse doesn't error on a file with zero records, or
    on a record with an empty sequence -- both need to be caught here
    rather than silently producing an empty or broken reference DB).
    """
    try:
        records = list(SeqIO.parse(str(fasta_path), "fasta"))
    except Exception as exc:  # noqa: BLE001 -- any parse failure is a fail, same as Stage 1
        raise InvalidReferenceFastaError(
            f"{fasta_path} could not be parsed as FASTA: {exc}"
        ) from exc

    if not records:
        raise InvalidReferenceFastaError(
            f"{fasta_path} contains no sequences -- nothing to publish."
        )
    for record in records:
        if not str(record.seq):
            raise InvalidReferenceFastaError(
                f"{fasta_path} contains an empty sequence for record {record.id!r}."
            )
    return records


def _parse_entry(record: SeqRecord, *, version: str, source: str) -> ReferenceEntry:
    """
    Header convention: `>ACCESSION Species name` or
    `>ACCESSION Species name | taxonomy string` -- matching the same
    `>ACCESSION description` shape app.pipeline.blast's species-parsing
    already assumes on the BLAST-output side (search_blast strips the
    leading accession token off blastn's `stitle` field). The optional
    `| taxonomy` segment is genuinely optional, per the brief ("taxonomy
    if present in the header") -- most curated entries won't have it.
    """
    description = record.description
    if description.startswith(record.id):
        description = description[len(record.id):].strip()

    if "|" in description:
        species_part, taxonomy_part = description.split("|", 1)
        species = species_part.strip()
        taxonomy = taxonomy_part.strip() or None
    else:
        species = description.strip()
        taxonomy = None

    return ReferenceEntry(
        version=version,
        accession=record.id,
        species=species or record.id,
        taxonomy=taxonomy,
        source=source,
    )


def publish_reference_db(
    fasta_path: Path,
    version: str,
    *,
    db: Session,
    reference_data_root: Optional[Path] = None,
) -> PublishResult:
    """
    Publish a new reference database version: validate the curated FASTA,
    copy it into its permanent version-labeled location, build a fresh
    BLAST index from it, record one ReferenceEntry per species, and mark
    this version active (demoting whichever version was active before).

    Re-publishing the same `version` string is idempotent for its own
    entries (they're replaced wholesale) but never touches another
    version's rows -- see ReferenceEntry's docstring for why those must
    survive a newer version going active.
    """
    fasta_path = Path(fasta_path)
    root = Path(reference_data_root) if reference_data_root is not None else REFERENCE_DATA_ROOT

    records = _validate_fasta(fasta_path)

    version_dir = root / version
    version_dir.mkdir(parents=True, exist_ok=True)
    canonical_fasta = version_dir / "reference.fasta"
    shutil.copyfile(fasta_path, canonical_fasta)

    db_prefix = version_dir / f"wildlife_db_{version}"
    build_reference_database(
        canonical_fasta, db_prefix, title=f"PAIGS WildID reference DB {version}"
    )

    # Replace this version's own entries wholesale -- makes re-publishing
    # the same version idempotent without needing per-row conflict
    # resolution. Other versions' entries are untouched by this filter.
    db.query(ReferenceEntry).filter(ReferenceEntry.version == version).delete()
    entries = [
        _parse_entry(record, version=version, source=fasta_path.name) for record in records
    ]
    db.add_all(entries)

    existing = (
        db.query(ReferenceDatabaseVersion).filter_by(version=version).one_or_none()
    )
    if existing is None:
        existing = ReferenceDatabaseVersion(version=version)
        db.add(existing)
    existing.fasta_path = str(canonical_fasta)
    existing.db_prefix = str(db_prefix)
    existing.sequence_count = len(records)

    # Exactly one active version at a time.
    db.query(ReferenceDatabaseVersion).filter(
        ReferenceDatabaseVersion.version != version
    ).update({ReferenceDatabaseVersion.is_active: False})
    existing.is_active = True

    db.commit()
    db.refresh(existing)

    return PublishResult(
        version=version,
        fasta_path=str(canonical_fasta),
        db_prefix=str(db_prefix),
        sequence_count=len(records),
    )


def get_active_version(db: Session) -> Optional[ReferenceDatabaseVersion]:
    """
    What Stage 9 orchestration will call to find the currently active
    reference database's path/version -- not wired into Stage 9 itself
    yet (Stage 9 isn't wired into Run orchestration at all yet), but
    built now since it's the natural, one-line counterpart to publishing.
    """
    return db.query(ReferenceDatabaseVersion).filter_by(is_active=True).one_or_none()
