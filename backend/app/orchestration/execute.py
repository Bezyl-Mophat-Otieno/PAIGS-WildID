"""Run/Stage orchestration -- build-order item 9.

`POST /runs/{id}/execute` chains Stages 1-11 together for a real Run, in
the order and with the run-level branching decisions CLAUDE.md specifies:
Stage 1's hard stop, Stage 3's three-way branch (both PASS / one PASS one
FAIL / both FAIL), Orientation + Consensus running only when two reads
survive Trimming, and Stage 7's FAIL ending the run. Every stage's own
already-tested pipeline function does the real work; this module's job is
sequencing, persistence (one Stage row per stage_type, per CLAUDE.md's
Run/Stage model), and the run-level decisions no single stage has the
context to make on its own.

Two layers, split deliberately at the Stage 2/3 seam:

- execute_run(run_id, db): resolves the Run's real stored AB1 file(s)
  from Stage 0's output, runs Stage 1 (format check) and Stage 2
  (extraction) against them for real, then hands off.
- continue_run_from_extraction(run, format_check, extractions, db,
  run_dir, effective_thresholds=None): everything from Stage 3 onward.
  Exposed as its own function (not a private helper) specifically so
  it's testable with hand-built ReadExtraction data -- Biopython's AbiIO
  module can only *read* the AB1 binary format, not write it, so there
  is no way to construct a genuine two-read AB1 pair with a real, known
  overlap for a from-scratch-upload test. See tests/test_orchestration.py's
  own docstring.

Stage.status vs. Run.status: a Stage's own status reflects whether
*running that pipeline step* succeeded technically -- "completed" even
when the biological verdict inside its output is a FAIL/no-overlap/
REVIEW-worthy result (the stage still did its job and produced a valid,
typed result). "failed" is reserved for a stage whose underlying pipeline
function raised an unexpected exception (a genuine technical failure --
build_consensus()'s single-block MVP limit, or no reference database
having ever been published) rather than returning a defined outcome.
"skipped" marks Orientation/Consensus on the single-read path. Run.status
only becomes "failed" when the run-level branching decides the pipeline
cannot continue; it becomes "completed" once Stage 11 (Reporting) has
run, regardless of whether Stage 10's own verdict was PASS, AMBIGUOUS, or
REVIEW REQUIRED -- those are all legitimate, reportable outcomes, not
run-level failures.

Synchronous through Stage 8 (every stage there is a handful of
milliseconds of Biopython/NumPy work). Stage 9 branches on blast.mode:
local search stays fully synchronous, same as every earlier stage --
searching a small MVP-sized local index is fast. Remote search is a real
network round trip to NCBI that can legitimately run for minutes, so it
is *not* run inline: `_dispatch_blast` persists the Stage 9 row as
"running" and returns immediately, leaving the Run "in_progress" at
current_stage="blast" -- exactly the same state the frontend's existing
`GET /runs/{id}` stepper poll already knows how to watch and wait on.
app.orchestration.background's poller picks up that "running" row from a
separate thread and calls `resume_run_after_blast` to actually run the
search and finish Stages 9-11, entirely independent of whatever HTTP
request originally enqueued it (see that function's own docstring for
how it reconstructs everything Stage 10/11 need purely from already-
persisted Stage rows, since no Python state survives across that gap).
This is what CLAUDE.md's original synchronous design flagged as "worth
revisiting if... a very slow BLAST search ever makes a single /execute
call block for a long time" -- revisited in the smallest way that
actually fixes it (a DB-backed poller, no new message-queue
infrastructure), not a wholesale move to async everywhere.

Thresholds: resolved through the Configuration subsystem
(app.configuration.service.effective_thresholds), not hardcoded module
defaults -- the global config table's current values (GET/PUT /config),
with this Run's own config_overrides (set at POST /runs or POST
/runs/{id}/rerun time) layered on top. Each stage's actual effective
kwargs are recorded in its own Stage.stage_metadata["thresholds"] (audit
trail), and the stages whose own result schema doesn't already carry
them (sanity_check, usability_check, orientation, blast) are additionally
folded into the final report's ReportInput.thresholds_used -- trim's
TrimResult.trim_params and identification's IdentificationResult.
thresholds_applied already carry their own, so they aren't duplicated
there.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app import storage
from app.configuration import service as config_service
from app.models.run import Run
from app.models.stage import Stage
from app.pipeline.ab1_extraction import ReadExtraction, extract_reads_for_files
from app.pipeline.consensus import build_consensus
from app.pipeline.fasta import generate_fasta, write_fasta_file
from app.pipeline.format_check import check_format_for_files
from app.pipeline.identification import identify_species_from_blast_result
from app.pipeline.orientation import detect_orientation
from app.pipeline.report import generate_report, write_report_file
from app.pipeline.sanity_check import check_sanity_for_files
from app.pipeline.trim import trim_reads_for_files
from app.pipeline.usability_check import (
    check_usability_from_consensus,
    check_usability_from_single_read,
)
from app.reference.publish import search_active_reference_database
from app.schemas.consensus import ConsensusResult
from app.schemas.fasta import FastaResult
from app.schemas.format_check import FileFormatCheck
from app.schemas.orientation import OrientationResult
from app.schemas.report import ReportInput
from app.schemas.sanity_check import SanityCheckResult
from app.schemas.trim import TrimResult
from app.schemas.usability_check import UsabilityCheckResult


class RunNotFoundError(Exception):
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run '{run_id}' not found.")


class RunAlreadyExecutedError(Exception):
    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run '{run_id}' has already been executed.")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _persist_stage(
    db: Session,
    run: Run,
    stage_type: str,
    *,
    status: str,
    output: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> Stage:
    now = _utcnow()
    stage = Stage(
        run_id=run.id,
        stage_type=stage_type,
        status=status,
        input_ref=None,
        output=output,
        stage_metadata=metadata,
        started_at=now,
        completed_at=now,
        attempt_number=1,
    )
    db.add(stage)
    if status != "skipped":
        # A "skipped" stage (Orientation/Consensus on the single-read
        # path, or the bookkeeping row written for the sibling stage
        # right after a no-overlap-found stop) was never actually
        # reached as a real step -- it must not overwrite current_stage
        # and clobber the real stopping point a stop-triggering persist
        # just recorded.
        run.current_stage = stage_type
    # A real commit, not just a flush: each completed stage becomes
    # durable the moment it's recorded, rather than sitting inside one
    # long-lived transaction spanning the entire run. That distinction
    # didn't matter while every stage took milliseconds -- it matters a
    # lot now that Stage 9's remote BLAST search can legitimately block
    # for minutes; holding a write transaction open that whole time is
    # exactly what produced a genuine SQLite "disk I/O error" crash under
    # concurrent access (see app.db's own WAL-mode comment). Committing
    # here also means an unexpected crash mid-pipeline (this one, or any
    # future one) never loses stages that had already genuinely finished.
    db.commit()
    db.refresh(run)
    return stage


def _update_stage(
    db: Session,
    run: Run,
    stage: Stage,
    *,
    status: str,
    output: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> Stage:
    """Transitions an existing "running" stage row to its terminal state
    in place, rather than inserting a second row for the same stage_type
    the way _persist_stage always does. Only ever used for blast.mode=
    "remote"'s running -> completed/failed transition: a "running" row
    has no real output yet (output=None), so filling it in for the first
    time here doesn't conflict with CLAUDE.md's "a stage's output, once
    written, is never overwritten" -- nothing meaningful was written
    until now. Every other stage_type only ever has one attempt and one
    row, via _persist_stage(); this is the one exception, for the one
    stage that can be observed mid-flight before it resolves.
    """
    stage.status = status
    stage.output = output
    stage.stage_metadata = metadata
    stage.completed_at = _utcnow()
    run.current_stage = stage.stage_type
    db.commit()
    db.refresh(run)
    db.refresh(stage)
    return stage


def _stop_run(db: Session, run: Run) -> Run:
    """Ends the run here -- current_stage was already set to the stopping
    stage by the last _persist_stage() call."""
    run.status = "failed"
    db.commit()
    db.refresh(run)
    return run


def _resolve_file_paths(run: Run, import_stage: Stage) -> Dict[str, Path]:
    output = import_stage.output or {}
    slots = output.get("slots") or []
    stored_filenames = output.get("stored_filenames") or []
    run_dir = storage.run_dir(run.id)
    return {slot: run_dir / filename for slot, filename in zip(slots, stored_filenames)}


def execute_run(run_id: str, db: Session) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise RunNotFoundError(run_id)

    already_executed = (
        db.query(Stage)
        .filter(Stage.run_id == run_id, Stage.stage_type != "import")
        .count()
        > 0
    )
    if already_executed:
        raise RunAlreadyExecutedError(run_id)

    import_stage = (
        db.query(Stage)
        .filter(Stage.run_id == run_id, Stage.stage_type == "import")
        .first()
    )
    if import_stage is None:
        # Should never happen -- create_run() always writes this stage
        # atomically alongside the Run itself.
        raise RuntimeError(f"Run '{run_id}' has no import stage recorded.")

    file_paths = _resolve_file_paths(run, import_stage)

    # Global config, with this Run's own per-run overrides (if any --
    # set at POST /runs or POST /runs/{id}/rerun time) layered on top.
    # Resolved once, up front, and threaded through so every stage below
    # sees the exact same snapshot even if GET/PUT /config is edited
    # concurrently while this run is executing.
    effective = config_service.effective_thresholds(db, run.config_overrides)

    # ---- Stage 1: Format Validity Check (hard stop) ----
    format_check = check_format_for_files(file_paths)
    _persist_stage(
        db,
        run,
        "format_check",
        status="completed",
        output={slot: result.model_dump() for slot, result in format_check.items()},
    )

    invalid_slots = [slot for slot, result in format_check.items() if not result.valid]
    if invalid_slots:
        return _stop_run(db, run)

    # ---- Stage 2: AB1 Extraction ----
    try:
        extractions = extract_reads_for_files(file_paths)
    except Exception as exc:  # genuine, unexpected failure -- Stage 1 already
        # screened out files that can't parse, so reaching here means
        # something environmental (e.g. a file went missing on disk).
        _persist_stage(db, run, "ab1_extraction", status="failed", output={"error": str(exc)})
        return _stop_run(db, run)

    _persist_stage(
        db,
        run,
        "ab1_extraction",
        status="completed",
        output={slot: result.model_dump() for slot, result in extractions.items()},
    )

    run_dir = storage.run_dir(run.id)
    return continue_run_from_extraction(run, format_check, extractions, db, run_dir, effective)


def continue_run_from_extraction(
    run: Run,
    format_check: Dict[str, FileFormatCheck],
    extractions: Dict[str, ReadExtraction],
    db: Session,
    run_dir,
    effective_thresholds: Optional[Dict[str, float]] = None,
) -> Run:
    """Stage 3 onward. See module docstring for why this is its own,
    separately-testable entry point. `effective_thresholds` is the flat
    {catalog_key: value} dict app.configuration.service.effective_thresholds
    returns -- when omitted (every direct function-level test that
    predates the Configuration subsystem does this), it's computed here
    from the global config table (freshly seeded with catalog defaults on
    an empty DB) and this Run's own config_overrides, so behavior is
    unchanged for any caller that doesn't care about configuration."""
    run_dir = Path(run_dir)
    effective = (
        effective_thresholds
        if effective_thresholds is not None
        else config_service.effective_thresholds(db, run.config_overrides)
    )

    # ---- Stage 3: Coarse Sanity Check ----
    sanity_kwargs = config_service.kwargs_for_stage(effective, "sanity_check")
    sanity_results = check_sanity_for_files(extractions, **sanity_kwargs)

    surviving_slots = [slot for slot, result in sanity_results.items() if result.status == "PASS"]

    single_read_reason = None
    if len(extractions) == 1:
        single_read_reason = "single_file_provided" if surviving_slots else None
    elif len(surviving_slots) == 1:
        single_read_reason = "qc_failure"

    _persist_stage(
        db,
        run,
        "sanity_check",
        status="completed",
        output={slot: result.model_dump() for slot, result in sanity_results.items()},
        metadata={
            "single_read_reason": single_read_reason,
            "thresholds": sanity_kwargs,
        },
    )

    if not surviving_slots:
        return _stop_run(db, run)

    # ---- Stage 4: Trimming (surviving slots only) ----
    trim_kwargs = config_service.kwargs_for_stage(effective, "trim")
    trim_inputs = {slot: extractions[slot] for slot in surviving_slots}
    trims = trim_reads_for_files(trim_inputs, **trim_kwargs)
    _persist_stage(
        db,
        run,
        "trim",
        status="completed",
        output={slot: result.model_dump() for slot, result in trims.items()},
        metadata={"thresholds": trim_kwargs},
    )

    trimmed_quality = {
        slot: extractions[slot].quality_scores[trims[slot].trim_start : trims[slot].trim_end]
        for slot in surviving_slots
    }

    orientation_result = None
    orientation_kwargs = None
    consensus_result = None
    usability_kwargs = config_service.kwargs_for_stage(effective, "usability_check")

    if len(surviving_slots) == 2:
        orientation_kwargs = config_service.kwargs_for_stage(effective, "orientation")
        orientation_result = detect_orientation(
            trims["forward"].trimmed_sequence,
            trims["reverse"].trimmed_sequence,
            **orientation_kwargs,
        )
        _persist_stage(
            db,
            run,
            "orientation",
            status="completed",
            output=orientation_result.model_dump(),
            metadata={"thresholds": orientation_kwargs},
        )

        if orientation_result.orientation == "no_overlap_found":
            _persist_stage(db, run, "consensus", status="skipped")
            return _stop_run(db, run)

        try:
            consensus_result = build_consensus(
                trims["forward"].trimmed_sequence,
                trimmed_quality["forward"],
                trims["reverse"].trimmed_sequence,
                trimmed_quality["reverse"],
                orientation_result,
            )
        except ValueError as exc:
            _persist_stage(db, run, "consensus", status="failed", output={"error": str(exc)})
            return _stop_run(db, run)

        _persist_stage(
            db, run, "consensus", status="completed", output=consensus_result.model_dump()
        )
        usability = check_usability_from_consensus(consensus_result, **usability_kwargs)
        sequence_for_fasta = consensus_result.consensus_sequence
    else:
        _persist_stage(db, run, "orientation", status="skipped")
        _persist_stage(db, run, "consensus", status="skipped")
        only_slot = surviving_slots[0]
        usability = check_usability_from_single_read(
            trims[only_slot], trimmed_quality[only_slot], **usability_kwargs
        )
        sequence_for_fasta = trims[only_slot].trimmed_sequence

    # ---- Stage 7: Usability Check (the real accept/reject gate) ----
    _persist_stage(
        db,
        run,
        "usability_check",
        status="completed",
        output=usability.model_dump(),
        metadata={"thresholds": usability_kwargs},
    )

    if usability.status == "FAIL":
        return _stop_run(db, run)

    # ---- Stage 8: FASTA generation ----
    try:
        fasta_result = generate_fasta(run.sample_id, sequence_for_fasta)
    except ValueError as exc:
        # Defensive: unreachable through any real branching combination
        # given Stage 7's own min_length floor, but never silently skip
        # recording a genuine failure if it somehow happens.
        _persist_stage(db, run, "fasta", status="failed", output={"error": str(exc)})
        return _stop_run(db, run)

    query_fasta_path = run_dir / "query.fasta"
    write_fasta_file(fasta_result, query_fasta_path)
    _persist_stage(db, run, "fasta", status="completed", output=fasta_result.model_dump())

    # ---- Stage 9: BLAST comparison ----
    blast_kwargs = config_service.kwargs_for_stage(effective, "blast")
    blast_result = _dispatch_blast(db, run, query_fasta_path, blast_kwargs, effective)
    if blast_result is None:
        # Either a local-mode failure (already persisted/stopped inside
        # _dispatch_blast), or a remote-mode search just got handed off to
        # the background poller (Stage 9 is "running", Run is still
        # "in_progress") -- either way, there is nothing left to do in
        # this synchronous call. Stage 10/11 for the remote case happen
        # later, in resume_run_after_blast().
        return run

    _persist_stage(
        db,
        run,
        "blast",
        status="completed",
        output=blast_result.model_dump(),
        metadata={"thresholds": blast_kwargs},
    )

    thresholds_used = _build_thresholds_used(sanity_kwargs, usability_kwargs, blast_kwargs, orientation_kwargs)

    return _finish_identification_and_report(
        db,
        run,
        run_dir,
        blast_result=blast_result,
        format_check=format_check,
        sanity_results=sanity_results,
        trims=trims,
        ab1_extraction=extractions,
        single_read_reason=single_read_reason,
        orientation_result=orientation_result,
        consensus_result=consensus_result,
        usability=usability,
        fasta_result=fasta_result,
        effective=effective,
        thresholds_used=thresholds_used,
    )


def _build_thresholds_used(sanity_kwargs, usability_kwargs, blast_kwargs, orientation_kwargs):
    """Only the stages whose own result schema doesn't already carry the
    thresholds it used -- TrimResult.trim_params and IdentificationResult.
    thresholds_applied already do, so they aren't duplicated here."""
    thresholds_used = {
        "sanity_check": sanity_kwargs,
        "usability_check": usability_kwargs,
        "blast": blast_kwargs,
    }
    if orientation_kwargs is not None:
        thresholds_used["orientation"] = orientation_kwargs
    return thresholds_used


def _dispatch_blast(
    db: Session,
    run: Run,
    query_fasta_path: Path,
    blast_kwargs: dict,
    effective: Dict[str, object],
):
    """Returns the BlastSearchResult immediately for local mode (fast --
    runs exactly like every earlier stage). For remote mode, persists
    Stage 9 as "running" and returns None -- the caller must stop here;
    app.orchestration.background's poller picks this up from a separate
    thread and calls resume_run_after_blast() once the real NCBI search
    actually completes.

    `effective` (the full resolved {catalog_key: value} snapshot, not
    just blast's own slice) is stashed in the "running" stage's own
    metadata alongside blast_kwargs -- resume_run_after_blast() runs
    later, possibly after GET/PUT /config has changed the *global*
    defaults, and must still use the exact snapshot this run resolved at
    dispatch time (same "resolved once, up front" guarantee every other
    stage already gets), not whatever happens to be current by then.
    """
    if blast_kwargs.get("mode") == "remote":
        _persist_stage(
            db,
            run,
            "blast",
            status="running",
            metadata={"thresholds": blast_kwargs, "effective": effective},
        )
        return None

    try:
        return search_active_reference_database(query_fasta_path, db, **blast_kwargs)
    except RuntimeError as exc:
        # Deliberately the broad RuntimeError, not just
        # NoActiveReferenceDatabaseError/RemoteBlastSearchError (both of
        # which are themselves RuntimeErrors): the BLAST+ binary being
        # missing entirely (app.pipeline.blast._find_blast_binary, local
        # or remote path alike) is exactly the same class of operational,
        # not-biological stop -- a deployment/environment problem, not a
        # verdict about the sample's own DNA -- and must end the run the
        # same clean way rather than crash the request with an unhandled
        # exception.
        _persist_stage(db, run, "blast", status="failed", output={"error": str(exc)})
        _stop_run(db, run)
        return None


def _finish_identification_and_report(
    db: Session,
    run: Run,
    run_dir: Path,
    *,
    blast_result,
    format_check,
    sanity_results,
    trims,
    ab1_extraction,
    single_read_reason,
    orientation_result,
    consensus_result,
    usability,
    fasta_result,
    effective,
    thresholds_used,
) -> Run:
    """Stages 10-11, shared by the synchronous local-mode path
    (continue_run_from_extraction, called immediately) and the
    background remote-mode path (resume_run_after_blast, called later,
    once the real NCBI search actually returns) -- identical logic
    either way once a BlastSearchResult exists, regardless of how it was
    obtained."""
    # ---- Stage 10: Identification engine ----
    identification_kwargs = config_service.kwargs_for_stage(effective, "identification")
    identification_result = identify_species_from_blast_result(
        blast_result, **identification_kwargs
    )
    _persist_stage(
        db, run, "identification", status="completed", output=identification_result.model_dump()
    )

    # ---- Stage 11: Reporting ----
    report_input = ReportInput(
        run_id=run.id,
        sample_id=run.sample_id,
        original_filenames=list(run.original_filenames or []),
        generated_at=_utcnow(),
        format_check=format_check,
        sanity_check=sanity_results,
        trim=trims,
        ab1_extraction=ab1_extraction,
        single_read_reason=single_read_reason,
        orientation=orientation_result,
        consensus=consensus_result,
        usability_check=usability,
        fasta=fasta_result,
        blast=blast_result,
        identification=identification_result,
        thresholds_used=thresholds_used,
    )
    pdf_bytes = generate_report(report_input)
    report_path = run_dir / "report.pdf"
    write_report_file(pdf_bytes, report_path)
    _persist_stage(db, run, "report", status="completed", output={"report_path": str(report_path)})

    run.status = "completed"
    db.commit()
    db.refresh(run)
    return run


def resume_run_after_blast(run_id: str, db: Session) -> Run:
    """Called by app.orchestration.background's poller once blast.mode=
    "remote"'s real NCBI search is actually ready to run -- entirely
    separate from whatever HTTP request originally called
    continue_run_from_extraction() and enqueued it (that request has long
    since returned). Nothing from that request's Python call stack
    survives to here, so everything Stage 9-11 need is reconstructed
    purely from this Run's own already-persisted Stage rows -- exactly
    the same data _finish_identification_and_report() would have received
    inline, just read back from storage instead of still sitting in local
    variables.

    Idempotent against being invoked twice for the same run (e.g. a
    process restart mid-poll): a no-op if Stage 9 isn't sitting at
    status="running" any more.
    """
    run = db.get(Run, run_id)
    if run is None:
        raise RunNotFoundError(run_id)

    stages = {s.stage_type: s for s in db.query(Stage).filter(Stage.run_id == run_id).all()}
    blast_stage = stages["blast"]
    if blast_stage.status != "running":
        return run

    run_dir = Path(storage.run_dir(run.id))
    blast_kwargs = blast_stage.stage_metadata["thresholds"]
    effective = blast_stage.stage_metadata["effective"]
    query_fasta_path = run_dir / "query.fasta"

    try:
        blast_result = search_active_reference_database(query_fasta_path, db, **blast_kwargs)
    except RuntimeError as exc:
        _update_stage(db, run, blast_stage, status="failed", output={"error": str(exc)})
        return _stop_run(db, run)

    _update_stage(
        db,
        run,
        blast_stage,
        status="completed",
        output=blast_result.model_dump(),
        metadata={"thresholds": blast_kwargs},
    )

    def _per_slot(stage_type, schema_cls):
        stage = stages.get(stage_type)
        return {slot: schema_cls(**data) for slot, data in (stage.output or {}).items()}

    def _single(stage_type, schema_cls):
        stage = stages.get(stage_type)
        if stage is None or stage.status == "skipped":
            return None
        return schema_cls(**stage.output)

    sanity_stage = stages["sanity_check"]
    usability_stage = stages["usability_check"]
    orientation_stage = stages.get("orientation")

    sanity_kwargs = sanity_stage.stage_metadata["thresholds"]
    usability_kwargs = usability_stage.stage_metadata["thresholds"]
    orientation_kwargs = (
        orientation_stage.stage_metadata["thresholds"]
        if orientation_stage is not None and orientation_stage.status != "skipped"
        else None
    )
    thresholds_used = _build_thresholds_used(sanity_kwargs, usability_kwargs, blast_kwargs, orientation_kwargs)

    return _finish_identification_and_report(
        db,
        run,
        run_dir,
        blast_result=blast_result,
        format_check=_per_slot("format_check", FileFormatCheck),
        sanity_results=_per_slot("sanity_check", SanityCheckResult),
        trims=_per_slot("trim", TrimResult),
        ab1_extraction=_per_slot("ab1_extraction", ReadExtraction),
        single_read_reason=sanity_stage.stage_metadata.get("single_read_reason"),
        orientation_result=_single("orientation", OrientationResult),
        consensus_result=_single("consensus", ConsensusResult),
        usability=UsabilityCheckResult(**usability_stage.output),
        fasta_result=FastaResult(**stages["fasta"].output),
        effective=effective,
        thresholds_used=thresholds_used,
    )
