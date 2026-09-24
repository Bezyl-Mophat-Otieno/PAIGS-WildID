"""POST /runs/{id}/rerun -- create a brand-new Run reusing an existing
run's stored AB1 file(s), with new (or no) config overrides.

Per CLAUDE.md's Configuration model: "trying different settings means
triggering a whole new Run (POST /runs/{id}/rerun, same file(s), adjusted
config) rather than editing/re-running any piece of the original -- the
two Runs sit side by side, fully independent and comparable." The new
Run's own `rerun_of` column records that lineage; the source Run is never
modified -- its own Stage rows, files, and config_overrides are all
untouched by this.

Deliberately mirrors create_run()'s own Stage 0 bookkeeping (app.api.runs)
rather than calling it directly, since there's no upload here -- the
files already exist on disk under the source Run's own directory and are
copied byte-for-byte into the new Run's own directory
(app.storage.copy_run_files), the same "stored permanently/untouched"
convention Stage 0 establishes for a fresh upload. The new Run is only
*created* here, exactly like create_run() -- it still needs its own
POST /runs/{id}/execute call to actually run the pipeline.
"""
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app import storage
from app.configuration import service as config_service
from app.models.run import Run
from app.models.stage import Stage
from app.naming import default_sample_id
from app.orchestration.execute import RunNotFoundError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_rerun(
    source_run_id: str,
    db: Session,
    *,
    config_overrides: Optional[Dict[str, float]] = None,
    sample_id: Optional[str] = None,
) -> Run:
    source = db.get(Run, source_run_id)
    if source is None:
        raise RunNotFoundError(source_run_id)

    if config_overrides:
        config_service.validate_overrides(config_overrides)

    import_stage = (
        db.query(Stage)
        .filter(Stage.run_id == source_run_id, Stage.stage_type == "import")
        .first()
    )
    if import_stage is None:
        # Should never happen -- create_run() always writes this stage
        # atomically alongside the Run itself.
        raise RuntimeError(f"Run '{source_run_id}' has no import stage recorded.")

    output = import_stage.output or {}
    slots = output.get("slots") or []
    stored_filenames = output.get("stored_filenames") or []
    original_filenames = output.get("original_filenames") or []

    now = _utcnow()
    new_run = Run(
        sample_id=sample_id.strip() if sample_id else default_sample_id(original_filenames),
        original_filenames=original_filenames,
        created_at=now,
        current_stage="import",
        status="in_progress",
        rerun_of=source.id,
        config_overrides=config_overrides or None,
    )
    db.add(new_run)
    db.flush()  # populate new_run.id before using it as the storage key

    new_stored_filenames = storage.copy_run_files(source.id, new_run.id, stored_filenames)

    stage = Stage(
        run_id=new_run.id,
        stage_type="import",
        status="completed",
        input_ref=None,
        output={
            "original_filenames": original_filenames,
            "stored_filenames": new_stored_filenames,
            "slots": slots,
        },
        started_at=now,
        completed_at=_utcnow(),
        attempt_number=1,
    )
    db.add(stage)
    db.commit()
    db.refresh(new_run)
    return new_run
