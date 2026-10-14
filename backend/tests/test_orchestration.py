"""Run/Stage orchestration (build-order item 9) -- function-level tests.

Written first, against the not-yet-existing app.orchestration.execute
module, to confirm red before implementing.

These tests exercise `continue_run_from_extraction()` directly, with
hand-built ReadExtraction objects, rather than going through real AB1
file uploads. That's a deliberate seam, not a shortcut: Biopython's AbiIO
module can only *read* the AB1 binary trace format, not write it (no
AbiWriter exists), so there is no way to construct a genuine two-read
AB1 pair with a real, known overlap in this repo -- the two real
fixtures on hand (3100.ab1, 3730.ab1) are confirmed unrelated (see
claude/stage-5-6-status.md). Stage 5/6's own test suite hit this same
wall and solved it the same way: a synthetic sequence template plus its
deliberately reverse-complemented twin, standing in for a genuine
matching pair. Reusing that exact pattern here (same seed=42 convention)
keeps this consistent with already-established precedent rather than
inventing a new one.

`execute_run()` itself -- the file-resolution + Stage 1/2 (format check,
extraction) wiring against real files, plus the run-not-found /
already-executed guards -- is tested separately, at the API level, in
test_api_execute.py, using the real fixtures that already exist.
"""
from pathlib import Path

import pytest
from Bio.Seq import Seq

from app.models.run import Run
from app.reference.publish import publish_reference_db
from app.schemas.ab1_extraction import ReadExtraction
from app.schemas.format_check import FileFormatCheck


def _true_pair(seed: int, length: int, split: int):
    """A synthetic forward/reverse pair with a known overlap, same
    construction Stage 5/6's own tests use. `split` is where the forward
    read ends and the reverse read (from the other end) begins -- the
    overlap is template[split:length-split] -- wait, simpler: forward =
    template[0:split], reverse = RC(template[length-split:length]) isn't
    quite it either; see the two call sites below for the exact slicing
    used, mirroring test_orientation.py's own helper.
    """
    import random

    rng = random.Random(seed)
    return "".join(rng.choice("ATGC") for _ in range(length))


def _make_run(db_session, sample_id="WILD_TEST", original_filenames=None, config_overrides=None) -> Run:
    # owner_id is required on every Run (see app.models.run.Run's own
    # docstring) but ownership isn't what these tests exercise -- they
    # call continue_run_from_extraction() directly, bypassing the API
    # layer (app.api.runs._get_owned_run) that actually enforces it --
    # so a fixed placeholder id is enough here.
    #
    # blast.mode defaults to "local" here (rather than the catalog's own
    # "remote" default) because this whole file is about pipeline
    # mechanics against the local reference DB fixture
    # (_publish_matching_reference), not about which BLAST mode gets
    # selected -- remote dispatch isn't implemented yet (see
    # RemoteBlastNotImplementedError), so leaving the global "remote"
    # default in place here would stop every one of these runs at Stage
    # 9 regardless of what's actually being tested. A test that wants
    # the real default (or a different override) passes its own
    # config_overrides.
    run = Run(
        sample_id=sample_id,
        original_filenames=original_filenames or ["forward.ab1", "reverse.ab1"],
        current_stage="import",
        status="in_progress",
        owner_id="test-owner-id",
        config_overrides=config_overrides if config_overrides is not None else {"blast.mode": "local"},
    )
    db_session.add(run)
    db_session.flush()
    return run


def _format_check(slots):
    return {slot: FileFormatCheck(filename=f"{slot}.ab1", valid=True) for slot in slots}


def _seed_stages_1_and_2(db_session, run, format_check, extractions):
    """This file's own established pattern calls continue_run_from_extraction()
    directly, bypassing execute_run() -- so Stage 1/2 rows are never
    persisted (see the module docstring). resume_run_after_blast() reads
    them back from storage, same as it does every other prior stage, so
    tests exercising it need those two rows to actually exist, matching
    what a real execute_run() call would have already written by the time
    Stage 9 is ever reached."""
    from app.orchestration.execute import _persist_stage

    _persist_stage(
        db_session, run, "format_check", status="completed",
        output={slot: result.model_dump() for slot, result in format_check.items()},
    )
    _persist_stage(
        db_session, run, "ab1_extraction", status="completed",
        output={slot: result.model_dump() for slot, result in extractions.items()},
    )


def _publish_matching_reference(db_session, temp_reference_data_root, tmp_path, sequence, species="Testus syntheticus"):
    fasta_path = tmp_path / "reference.fasta"
    fasta_path.write_text(f">TESTREF001 {species}\n{sequence}\n")
    return publish_reference_db(
        fasta_path, "v1", db=db_session, reference_data_root=temp_reference_data_root
    )


class TestContinueRunFromExtractionTwoReadSuccess:
    """A genuine two-read pair (via the synthetic-template technique) that
    clears every stage all the way through to a completed report."""

    def test_full_pipeline_success_produces_a_completed_run_and_report(
        self, db_session, temp_reference_data_root, tmp_path
    ):
        from app.orchestration.execute import continue_run_from_extraction

        template = _true_pair(seed=42, length=700, split=400)
        forward_seq = template[0:400]
        reverse_seq = str(Seq(template[300:700]).reverse_complement())

        extractions = {
            "forward": ReadExtraction(
                raw_sequence=forward_seq, raw_length=400, quality_scores=[40] * 400
            ),
            "reverse": ReadExtraction(
                raw_sequence=reverse_seq, raw_length=400, quality_scores=[40] * 400
            ),
        }
        format_check = _format_check(["forward", "reverse"])
        run = _make_run(db_session, original_filenames=["forward.ab1", "reverse.ab1"])

        # The reference DB entry is the exact 700bp template -- guarantees
        # a clean, unambiguous 100%-identity/coverage BLAST hit.
        _publish_matching_reference(db_session, temp_reference_data_root, tmp_path, template)

        run_dir = tmp_path / "run_storage"
        result = continue_run_from_extraction(run, format_check, extractions, db_session, run_dir)

        assert result.status == "completed"
        assert result.current_stage == "report"

        from app.models.stage import Stage

        stages = {
            s.stage_type: s
            for s in db_session.query(Stage).filter(Stage.run_id == run.id).all()
        }
        assert set(stages) == {
            "sanity_check",
            "trim",
            "orientation",
            "consensus",
            "usability_check",
            "fasta",
            "blast",
            "identification",
            "report",
        }
        assert stages["orientation"].status == "completed"
        assert stages["orientation"].output["orientation"] == "reverse_read_reverse_complemented"
        assert stages["consensus"].status == "completed"
        assert stages["consensus"].output["consensus_length"] == 700
        assert stages["consensus"].output["ambiguous_positions"] == []
        assert stages["usability_check"].output["status"] == "PASS"
        assert stages["identification"].output["status"] == "PASS"
        assert stages["identification"].output["candidate_species"] == "Testus syntheticus"

        report_path = Path(stages["report"].output["report_path"])
        assert report_path.is_file()
        assert report_path.read_bytes().startswith(b"%PDF")

    def test_sanity_check_metadata_records_no_single_read_reason_on_two_read_path(
        self, db_session, temp_reference_data_root, tmp_path
    ):
        from app.orchestration.execute import continue_run_from_extraction

        template = _true_pair(seed=42, length=700, split=400)
        forward_seq = template[0:400]
        reverse_seq = str(Seq(template[300:700]).reverse_complement())
        extractions = {
            "forward": ReadExtraction(
                raw_sequence=forward_seq, raw_length=400, quality_scores=[40] * 400
            ),
            "reverse": ReadExtraction(
                raw_sequence=reverse_seq, raw_length=400, quality_scores=[40] * 400
            ),
        }
        format_check = _format_check(["forward", "reverse"])
        run = _make_run(db_session)
        _publish_matching_reference(db_session, temp_reference_data_root, tmp_path, template)

        continue_run_from_extraction(run, format_check, extractions, db_session, tmp_path / "run_storage")

        from app.models.stage import Stage

        sanity_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "sanity_check")
            .one()
        )
        assert sanity_stage.stage_metadata.get("single_read_reason") is None


class TestStagesAreDurablyCommittedNotJustFlushed:
    """Each _persist_stage() call now commits, not just flushes -- proven
    here by reading the row back through a completely separate connection
    to the same on-disk SQLite file, not just the same session's identity
    map (which a flush alone would already satisfy). This durability
    matters specifically because a slow later stage (Stage 9's remote
    BLAST search can legitimately block for minutes) must not hold
    earlier, genuinely-finished stages hostage inside one long-lived,
    uncommitted transaction -- see app.orchestration.execute's own
    _persist_stage docstring and app.db's WAL-mode comment for the
    concrete failure this caused."""

    def test_an_earlier_completed_stage_survives_an_unhandled_crash_in_a_later_one(
        self, db_session, tmp_path, monkeypatch
    ):
        """The real bug this guards against: Stage 9's remote BLAST search
        raising an exception that never reaches _stop_run()/the final
        success commit at all (this test's stand-in for that -- a bare,
        uncaught exception genuinely propagating out, same as the actual
        production crash did) must not roll back Stage 3's already-genuine
        "sanity_check completed" result along with it. A same-session
        query wouldn't prove this (flush alone already satisfies that) --
        only a totally separate connection, opened *after* the crash,
        proves the earlier stage's row was actually committed to disk
        rather than sitting in a transaction that just got discarded.
        """
        import app.orchestration.execute as execute_module
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.models.stage import Stage
        from app.orchestration.execute import continue_run_from_extraction

        def _crash(*args, **kwargs):
            raise Exception("simulated unhandled crash, e.g. a real disk I/O error")

        # trim_reads_for_files runs right after sanity_check completes --
        # by the time this raises, sanity_check's own _persist_stage() call
        # has already happened, but nothing has reached _stop_run() or the
        # final success commit.
        monkeypatch.setattr(execute_module, "trim_reads_for_files", _crash)

        good_seq = "".join(["ATCG"[i % 4] for i in range(700)])
        good = ReadExtraction(raw_sequence=good_seq, raw_length=700, quality_scores=[40] * 700)
        extractions = {"forward": good}
        format_check = _format_check(["forward"])
        run = _make_run(db_session, original_filenames=["forward.ab1"])

        with pytest.raises(Exception, match="simulated unhandled crash"):
            continue_run_from_extraction(
                run, format_check, extractions, db_session, tmp_path / "run_storage"
            )

        # A brand-new engine/session against the same file, opened after
        # the crash -- if sanity_check had only been flushed (not
        # committed), this independent connection would see nothing, since
        # the crash never reached a commit point.
        other_engine = create_engine(
            f"sqlite:///{tmp_path / 'test_reference.db'}",
            connect_args={"check_same_thread": False},
        )
        OtherSession = sessionmaker(bind=other_engine)
        other_session = OtherSession()
        try:
            stage = (
                other_session.query(Stage)
                .filter(Stage.run_id == run.id, Stage.stage_type == "sanity_check")
                .one()
            )
            assert stage.status == "completed"
        finally:
            other_session.close()
            other_engine.dispose()


class TestContinueRunFromExtractionBranching:
    def test_both_reads_failing_sanity_stops_the_run(self, db_session, tmp_path):
        from app.orchestration.execute import continue_run_from_extraction

        bad = ReadExtraction(raw_sequence="N" * 10, raw_length=10, quality_scores=[0] * 10)
        extractions = {"forward": bad, "reverse": bad}
        format_check = _format_check(["forward", "reverse"])
        run = _make_run(db_session)

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage"
        )

        assert result.status == "failed"
        assert result.current_stage == "sanity_check"

        from app.models.stage import Stage

        stage_types = {
            s.stage_type
            for s in db_session.query(Stage).filter(Stage.run_id == run.id).all()
        }
        assert stage_types == {"sanity_check"}

    def test_single_file_that_fails_sanity_stops_the_run(self, db_session, tmp_path):
        from app.orchestration.execute import continue_run_from_extraction

        bad = ReadExtraction(raw_sequence="N" * 10, raw_length=10, quality_scores=[0] * 10)
        extractions = {"forward": bad}
        format_check = _format_check(["forward"])
        run = _make_run(db_session, original_filenames=["forward.ab1"])

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage"
        )

        assert result.status == "failed"
        assert result.current_stage == "sanity_check"

    def test_one_of_two_failing_sanity_continues_single_read_with_reason_recorded(
        self, db_session, temp_reference_data_root, tmp_path
    ):
        from app.orchestration.execute import continue_run_from_extraction

        good_seq = "".join(["ATCG"[i % 4] for i in range(700)])
        good = ReadExtraction(raw_sequence=good_seq, raw_length=700, quality_scores=[40] * 700)
        bad = ReadExtraction(raw_sequence="N" * 10, raw_length=10, quality_scores=[0] * 10)
        extractions = {"forward": good, "reverse": bad}
        format_check = _format_check(["forward", "reverse"])
        run = _make_run(db_session)
        _publish_matching_reference(db_session, temp_reference_data_root, tmp_path, good_seq)

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage"
        )

        from app.models.stage import Stage

        sanity_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "sanity_check")
            .one()
        )
        assert sanity_stage.stage_metadata.get("single_read_reason") == "qc_failure"

        orientation_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "orientation")
            .one()
        )
        assert orientation_stage.status == "skipped"
        consensus_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "consensus")
            .one()
        )
        assert consensus_stage.status == "skipped"

        assert result.status == "completed"

    def test_single_file_provided_reason_recorded_on_full_success(
        self, db_session, temp_reference_data_root, tmp_path
    ):
        from app.orchestration.execute import continue_run_from_extraction

        good_seq = "".join(["ATCG"[i % 4] for i in range(700)])
        good = ReadExtraction(raw_sequence=good_seq, raw_length=700, quality_scores=[40] * 700)
        extractions = {"forward": good}
        format_check = _format_check(["forward"])
        run = _make_run(db_session, original_filenames=["forward.ab1"])
        _publish_matching_reference(db_session, temp_reference_data_root, tmp_path, good_seq)

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage"
        )

        from app.models.stage import Stage

        sanity_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "sanity_check")
            .one()
        )
        assert sanity_stage.stage_metadata.get("single_read_reason") == "single_file_provided"
        assert result.status == "completed"

    def test_usability_check_failure_stops_the_run_before_fasta(
        self, db_session, tmp_path
    ):
        from app.orchestration.execute import continue_run_from_extraction

        # The Stage 5/6 status doc's own 180bp true-pair template: clears
        # orientation/consensus cleanly, but 180bp is well under Stage 7's
        # default 500bp floor -- FAILs usability, which must end the run
        # before Stage 8 (FASTA) ever runs.
        template = _true_pair(seed=42, length=180, split=120)
        forward_seq = template[0:120]
        reverse_seq = str(Seq(template[60:180]).reverse_complement())
        extractions = {
            "forward": ReadExtraction(
                raw_sequence=forward_seq, raw_length=120, quality_scores=[40] * 120
            ),
            "reverse": ReadExtraction(
                raw_sequence=reverse_seq, raw_length=120, quality_scores=[40] * 120
            ),
        }
        format_check = _format_check(["forward", "reverse"])
        run = _make_run(db_session)

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage"
        )

        assert result.status == "failed"
        assert result.current_stage == "usability_check"

        from app.models.stage import Stage

        stage_types = {
            s.stage_type
            for s in db_session.query(Stage).filter(Stage.run_id == run.id).all()
        }
        assert "fasta" not in stage_types
        assert "blast" not in stage_types

        usability_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "usability_check")
            .one()
        )
        assert usability_stage.output["status"] == "FAIL"

    def test_consensus_error_is_caught_and_stops_the_run(
        self, db_session, tmp_path, monkeypatch
    ):
        """build_consensus() already raises ValueError for its one
        documented MVP limit (an indel inside the overlap breaks the
        single-block assumption -- see test_consensus.py for that case
        proven directly against the real function). This test is about
        orchestration's *handling* of that failure, not re-deriving the
        exact biological conditions that trigger it -- so the real
        function is monkeypatched to raise it here, consistent with this
        conftest's own use of monkeypatch for test isolation elsewhere.
        """
        import app.orchestration.execute as execute_module
        from app.orchestration.execute import continue_run_from_extraction

        def _raise(*args, **kwargs):
            raise ValueError("Consensus building only supports a single ungapped overlap region.")

        monkeypatch.setattr(execute_module, "build_consensus", _raise)

        template = _true_pair(seed=42, length=700, split=400)
        forward_seq = template[0:400]
        reverse_seq = str(Seq(template[300:700]).reverse_complement())
        extractions = {
            "forward": ReadExtraction(
                raw_sequence=forward_seq, raw_length=400, quality_scores=[40] * 400
            ),
            "reverse": ReadExtraction(
                raw_sequence=reverse_seq, raw_length=400, quality_scores=[40] * 400
            ),
        }
        format_check = _format_check(["forward", "reverse"])
        run = _make_run(db_session)

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage"
        )

        assert result.status == "failed"
        assert result.current_stage == "consensus"

        from app.models.stage import Stage

        consensus_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "consensus")
            .one()
        )
        assert consensus_stage.status == "failed"
        assert "single ungapped overlap" in consensus_stage.output["error"]

    def test_no_active_reference_database_stops_the_run_at_blast(
        self, db_session, temp_reference_data_root, tmp_path
    ):
        from app.orchestration.execute import continue_run_from_extraction

        good_seq = "".join(["ATCG"[i % 4] for i in range(700)])
        good = ReadExtraction(raw_sequence=good_seq, raw_length=700, quality_scores=[40] * 700)
        extractions = {"forward": good}
        format_check = _format_check(["forward"])
        run = _make_run(db_session, original_filenames=["forward.ab1"])
        # Deliberately no publish_reference_db() call here.

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage"
        )

        assert result.status == "failed"
        assert result.current_stage == "blast"

        from app.models.stage import Stage

        blast_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "blast")
            .one()
        )
        assert blast_stage.status == "failed"
        assert "reference database" in blast_stage.output["error"].lower()
        stage_types = {
            s.stage_type
            for s in db_session.query(Stage).filter(Stage.run_id == run.id).all()
        }
        assert "identification" not in stage_types
        assert "report" not in stage_types


class TestContinueRunFromExtractionWithConfigOverrides:
    """Proves the Configuration subsystem is actually wired into
    orchestration, not just built alongside it: passing a non-default
    `effective_thresholds` dict changes both what gets recorded in a
    Stage's metadata and the run-level outcome, using the exact same
    input data a default-config run would otherwise pass.
    """

    def test_custom_thresholds_are_used_and_recorded_in_stage_metadata(
        self, db_session, tmp_path
    ):
        from app.configuration import service as config_service
        from app.orchestration.execute import continue_run_from_extraction

        good_seq = "".join(["ATCG"[i % 4] for i in range(700)])
        good = ReadExtraction(raw_sequence=good_seq, raw_length=700, quality_scores=[40] * 700)
        extractions = {"forward": good}
        format_check = _format_check(["forward"])
        run = _make_run(db_session, original_filenames=["forward.ab1"])

        effective = config_service.effective_thresholds(
            db_session, {"sanity_check.min_raw_length": 10}
        )

        continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage", effective
        )

        from app.models.stage import Stage

        sanity_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "sanity_check")
            .one()
        )
        assert sanity_stage.stage_metadata["thresholds"]["min_raw_length"] == 10
        assert isinstance(sanity_stage.stage_metadata["thresholds"]["min_raw_length"], int)

    def test_overriding_usability_min_length_turns_a_would_be_pass_into_a_fail(
        self, db_session, temp_reference_data_root, tmp_path
    ):
        """The exact same 700bp single read that
        test_single_file_provided_reason_recorded_on_full_success (above)
        proves completes the full pipeline under default config -- here,
        overriding usability_check.min_length above 700 stops it at
        usability_check instead. Same input, different (worse) outcome,
        purely from a per-run config override.
        """
        from app.configuration import service as config_service
        from app.orchestration.execute import continue_run_from_extraction

        good_seq = "".join(["ATCG"[i % 4] for i in range(700)])
        good = ReadExtraction(raw_sequence=good_seq, raw_length=700, quality_scores=[40] * 700)
        extractions = {"forward": good}
        format_check = _format_check(["forward"])
        run = _make_run(db_session, original_filenames=["forward.ab1"])
        _publish_matching_reference(db_session, temp_reference_data_root, tmp_path, good_seq)

        effective = config_service.effective_thresholds(
            db_session, {"usability_check.min_length": 800, "blast.mode": "local"}
        )

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage", effective
        )

        assert result.status == "failed"
        assert result.current_stage == "usability_check"

        from app.models.stage import Stage

        usability_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "usability_check")
            .one()
        )
        assert usability_stage.output["status"] == "FAIL"
        assert usability_stage.stage_metadata["thresholds"]["min_length"] == 800

    def test_no_explicit_effective_thresholds_falls_back_to_global_config(
        self, db_session, tmp_path
    ):
        """When called without the 6th argument (every pre-existing test
        in this file does exactly that), behavior must be unchanged --
        the function computes effective thresholds itself from the
        (freshly-seeded, all-defaults) global config table."""
        from app.orchestration.execute import continue_run_from_extraction

        bad = ReadExtraction(raw_sequence="N" * 10, raw_length=10, quality_scores=[0] * 10)
        extractions = {"forward": bad, "reverse": bad}
        format_check = _format_check(["forward", "reverse"])
        run = _make_run(db_session)

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, tmp_path / "run_storage"
        )

        assert result.status == "failed"
        assert result.current_stage == "sanity_check"

        from app.models.stage import Stage

        sanity_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "sanity_check")
            .one()
        )
        # DEFAULT_MIN_RAW_LENGTH -- confirms the fallback path used the
        # real global config (seeded with catalog defaults), not some
        # empty/zeroed-out dict.
        assert sanity_stage.stage_metadata["thresholds"]["min_raw_length"] == 50


class TestRemoteBlastModeDispatch:
    """blast.mode="remote" is the catalog's own default -- Stage 9 must
    not block the synchronous call at all when it's selected. It persists
    a "running" stage and returns immediately, leaving Stage 10/11 for
    resume_run_after_blast() (app.orchestration.background's poller) to
    finish later, once the real NCBI search actually completes. Covered
    here at the orchestration-function level, without a real network
    call -- see test_reference_publish.py's own remote-mode tests for the
    actual blastn -remote command construction/parsing.
    """

    def test_dispatching_remote_search_persists_a_running_stage_and_leaves_run_in_progress(
        self, db_session, temp_storage_root, tmp_path
    ):
        from app import storage
        from app.orchestration.execute import continue_run_from_extraction

        good_seq = "".join(["ATCG"[i % 4] for i in range(700)])
        good = ReadExtraction(raw_sequence=good_seq, raw_length=700, quality_scores=[40] * 700)
        extractions = {"forward": good}
        format_check = _format_check(["forward"])
        # config_overrides={} (not None) so _make_run's own local-mode
        # default is bypassed -- this test is specifically about the real
        # "remote" catalog default.
        run = _make_run(db_session, original_filenames=["forward.ab1"], config_overrides={})

        result = continue_run_from_extraction(
            run, format_check, extractions, db_session, storage.run_dir(run.id)
        )

        assert result.status == "in_progress"
        assert result.current_stage == "blast"

        from app.models.stage import Stage

        blast_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "blast")
            .one()
        )
        assert blast_stage.status == "running"
        assert blast_stage.output is None
        assert blast_stage.stage_metadata["thresholds"]["mode"] == "remote"
        assert "effective" in blast_stage.stage_metadata

        stage_types = {
            s.stage_type for s in db_session.query(Stage).filter(Stage.run_id == run.id).all()
        }
        assert "identification" not in stage_types
        assert "report" not in stage_types


class TestResumeRunAfterBlast:
    """The other half: once app.orchestration.background's poller picks
    up Stage 9's "running" row, resume_run_after_blast() drives
    app.pipeline.ncbi_remote's submit -> poll -> fetch state machine one
    non-blocking tick at a time (see _advance_remote_blast's own
    docstring) -- unlike the old one-shot blocking subprocess design,
    most real calls here are genuinely called many times per run, not
    once. Once a result is actually in hand, it reconstructs everything
    Stage 10/11 need purely from this run's own already-persisted Stage
    rows (no Python state survives from the original request that
    enqueued it) and finishes the run exactly as the synchronous
    local-mode path always has.

    app.pipeline.ncbi_remote itself is mocked here (submit_search /
    check_status / fetch_result) -- its own real HTTP parsing is covered
    by test_ncbi_remote.py against genuinely-captured NCBI responses; the
    fallback-to-subprocess path (when submission itself fails) is covered
    separately below.
    """

    @staticmethod
    def _blast_stage(db_session, run):
        from app.models.stage import Stage

        return (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "blast")
            .one()
        )

    @staticmethod
    def _make_due(db_session, blast_stage):
        """Rewrites the running stage's own stashed next_check_at into
        the past, so the next resume_run_after_blast() tick treats its
        pending poll as due -- without an actual wall-clock sleep in a
        test. A real poller tick naturally becomes due this way as time
        actually passes; this is just that same condition, forced."""
        from datetime import datetime, timedelta, timezone

        metadata = dict(blast_stage.stage_metadata)
        job = dict(metadata["remote_job"])
        job["next_check_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        metadata["remote_job"] = job
        blast_stage.stage_metadata = metadata
        db_session.commit()

    def _start_run(self, db_session, temp_storage_root):
        from app import storage
        from app.orchestration.execute import continue_run_from_extraction

        good_seq = "".join(["ATCG"[i % 4] for i in range(700)])
        good = ReadExtraction(raw_sequence=good_seq, raw_length=700, quality_scores=[40] * 700)
        extractions = {"forward": good}
        format_check = _format_check(["forward"])
        run = _make_run(db_session, original_filenames=["forward.ab1"], config_overrides={})
        _seed_stages_1_and_2(db_session, run, format_check, extractions)

        continue_run_from_extraction(
            run, format_check, extractions, db_session, storage.run_dir(run.id)
        )
        return run

    def test_first_tick_submits_and_stays_running_without_checking_status_yet(
        self, db_session, temp_storage_root, monkeypatch
    ):
        import app.pipeline.ncbi_remote as ncbi_remote
        from app.orchestration.execute import resume_run_after_blast

        run = self._start_run(db_session, temp_storage_root)

        monkeypatch.setattr(
            ncbi_remote,
            "submit_search",
            lambda *a, **k: ncbi_remote.NcbiSubmission(rid="FAKE123", rtoe=30, raw_response="put"),
        )
        status_calls = []
        monkeypatch.setattr(
            ncbi_remote, "check_status", lambda rid, **k: status_calls.append(rid) or "READY"
        )

        result = resume_run_after_blast(run.id, db_session)

        assert result.status == "in_progress"
        assert status_calls == []  # RTOE=30s hasn't elapsed -- no status check yet

        blast_stage = self._blast_stage(db_session, run)
        assert blast_stage.status == "running"
        assert blast_stage.stage_metadata["remote_job"]["rid"] == "FAKE123"
        assert blast_stage.stage_metadata["remote_job"]["transport"] == "http"

    def test_resumes_and_completes_the_run_once_the_search_is_ready(
        self, db_session, temp_storage_root, monkeypatch
    ):
        import app.pipeline.ncbi_remote as ncbi_remote
        from app.models.stage import Stage
        from app.orchestration.execute import resume_run_after_blast
        from app.schemas.blast import BlastHit

        run = self._start_run(db_session, temp_storage_root)

        monkeypatch.setattr(
            ncbi_remote,
            "submit_search",
            lambda *a, **k: ncbi_remote.NcbiSubmission(rid="FAKE123", rtoe=0, raw_response="put"),
        )
        monkeypatch.setattr(ncbi_remote, "check_status", lambda rid, **k: "READY")
        monkeypatch.setattr(
            ncbi_remote,
            "fetch_result",
            lambda rid, *, max_hits, **k: ncbi_remote.NcbiFetchedResult(
                query_length=700,
                hits=[
                    BlastHit(
                        rank=1, species="Testus syntheticus", identity=99.0, coverage=98.0,
                        evalue=0.0, bit_score=500.0, accession="REF001",
                    )
                ],
                raw_response="<xml/>",
            ),
        )

        resume_run_after_blast(run.id, db_session)  # tick 1: submit
        self._make_due(db_session, self._blast_stage(db_session, run))
        result = resume_run_after_blast(run.id, db_session)  # tick 2: ready -> finish

        assert result.status == "completed"
        assert result.current_stage == "report"

        blast_stage = self._blast_stage(db_session, run)
        assert blast_stage.status == "completed"
        assert blast_stage.output["search_mode"] == "remote"
        assert blast_stage.output["remote_transport"] == "http"

        identification_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "identification")
            .one()
        )
        assert identification_stage.output["candidate_species"] == "Testus syntheticus"

        report_stage = (
            db_session.query(Stage)
            .filter(Stage.run_id == run.id, Stage.stage_type == "report")
            .one()
        )
        report_path = Path(report_stage.output["report_path"])
        assert report_path.is_file()
        assert report_path.read_bytes().startswith(b"%PDF")

    def test_a_search_failure_reported_by_ncbi_stops_the_run_cleanly(
        self, db_session, temp_storage_root, monkeypatch
    ):
        import app.pipeline.ncbi_remote as ncbi_remote
        from app.orchestration.execute import resume_run_after_blast

        run = self._start_run(db_session, temp_storage_root)

        monkeypatch.setattr(
            ncbi_remote,
            "submit_search",
            lambda *a, **k: ncbi_remote.NcbiSubmission(rid="FAKE123", rtoe=0, raw_response="put"),
        )
        resume_run_after_blast(run.id, db_session)  # tick 1: submit
        self._make_due(db_session, self._blast_stage(db_session, run))

        def _raise(*args, **kwargs):
            raise ncbi_remote.NcbiSearchFailedError(
                "NCBI reported the BLAST search (RID FAKE123) failed."
            )

        monkeypatch.setattr(ncbi_remote, "check_status", _raise)

        result = resume_run_after_blast(run.id, db_session)  # tick 2: NCBI says no

        assert result.status == "failed"
        assert result.current_stage == "blast"

        blast_stage = self._blast_stage(db_session, run)
        assert blast_stage.status == "failed"
        assert "failed" in blast_stage.output["error"]

    def test_an_unrecognized_ncbi_response_stops_the_run_with_a_distinct_message(
        self, db_session, temp_storage_root, monkeypatch
    ):
        """NCBI changing its response format must never be silently
        misread as a biological result -- see
        app.pipeline.ncbi_remote.UnrecognizedNcbiResponseError's own
        docstring. This is the mitigation for exactly that risk."""
        import app.pipeline.ncbi_remote as ncbi_remote
        from app.orchestration.execute import resume_run_after_blast

        run = self._start_run(db_session, temp_storage_root)

        monkeypatch.setattr(
            ncbi_remote,
            "submit_search",
            lambda *a, **k: ncbi_remote.NcbiSubmission(rid="FAKE123", rtoe=0, raw_response="put"),
        )
        resume_run_after_blast(run.id, db_session)  # tick 1: submit
        self._make_due(db_session, self._blast_stage(db_session, run))

        def _raise(*args, **kwargs):
            raise ncbi_remote.UnrecognizedNcbiResponseError("response shape never seen before")

        monkeypatch.setattr(ncbi_remote, "check_status", _raise)

        result = resume_run_after_blast(run.id, db_session)

        assert result.status == "failed"
        blast_stage = self._blast_stage(db_session, run)
        assert "didn't match any known shape" in blast_stage.output["error"]

    def test_falls_back_to_the_subprocess_path_when_http_submission_fails(
        self, db_session, temp_storage_root, monkeypatch
    ):
        """The one safe fallback trigger: submission itself never
        reached NCBI in any form we could use, so nothing is lost by
        trying the older blastn -remote subprocess path instead of
        failing the run outright."""
        import app.orchestration.execute as execute_module
        import app.pipeline.ncbi_remote as ncbi_remote
        from app.orchestration.execute import resume_run_after_blast
        from app.schemas.blast import BlastHit, BlastSearchResult

        run = self._start_run(db_session, temp_storage_root)

        def _raise(*args, **kwargs):
            raise ncbi_remote.NcbiSubmissionFailedError("NCBI did not return a Request ID (RID).")

        monkeypatch.setattr(ncbi_remote, "submit_search", _raise)

        fake_result = BlastSearchResult(
            hits=[
                BlastHit(
                    rank=1, species="Testus syntheticus", identity=99.0, coverage=98.0,
                    evalue=0.0, bit_score=500.0, accession="REF001",
                )
            ],
            database_version="NCBI nt (remote, live -- not version-pinned)",
            query_length=700,
            search_mode="remote",
            remote_database="nt",
        )
        monkeypatch.setattr(
            execute_module, "search_active_reference_database", lambda *a, **k: fake_result
        )

        result = resume_run_after_blast(run.id, db_session)

        assert result.status == "completed"
        blast_stage = self._blast_stage(db_session, run)
        assert blast_stage.output["remote_transport"] == "subprocess_fallback"

    def test_is_a_no_op_once_the_blast_stage_is_no_longer_running(
        self, db_session, temp_storage_root, monkeypatch
    ):
        """Guards against double-processing -- e.g. a process restart
        that picks the same "running" row up twice."""
        import app.pipeline.ncbi_remote as ncbi_remote
        from app.orchestration.execute import resume_run_after_blast
        from app.schemas.blast import BlastHit

        run = self._start_run(db_session, temp_storage_root)

        monkeypatch.setattr(
            ncbi_remote,
            "submit_search",
            lambda *a, **k: ncbi_remote.NcbiSubmission(rid="FAKE123", rtoe=0, raw_response="put"),
        )
        monkeypatch.setattr(ncbi_remote, "check_status", lambda rid, **k: "READY")
        call_count = {"fetch": 0}

        def _fetch(rid, *, max_hits, **k):
            call_count["fetch"] += 1
            return ncbi_remote.NcbiFetchedResult(
                query_length=700,
                hits=[
                    BlastHit(
                        rank=1, species="Testus syntheticus", identity=99.0, coverage=98.0,
                        evalue=0.0, bit_score=500.0, accession="REF001",
                    )
                ],
                raw_response="<xml/>",
            )

        monkeypatch.setattr(ncbi_remote, "fetch_result", _fetch)

        resume_run_after_blast(run.id, db_session)  # tick 1: submit
        self._make_due(db_session, self._blast_stage(db_session, run))
        resume_run_after_blast(run.id, db_session)  # tick 2: ready -> finish
        result = resume_run_after_blast(run.id, db_session)  # tick 3: already completed -- no-op

        assert call_count["fetch"] == 1
        assert result.status == "completed"
