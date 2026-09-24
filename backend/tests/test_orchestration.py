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


def _make_run(db_session, sample_id="WILD_TEST", original_filenames=None) -> Run:
    # owner_id is required on every Run (see app.models.run.Run's own
    # docstring) but ownership isn't what these tests exercise -- they
    # call continue_run_from_extraction() directly, bypassing the API
    # layer (app.api.runs._get_owned_run) that actually enforces it --
    # so a fixed placeholder id is enough here.
    run = Run(
        sample_id=sample_id,
        original_filenames=original_filenames or ["forward.ab1", "reverse.ab1"],
        current_stage="import",
        status="in_progress",
        owner_id="test-owner-id",
    )
    db_session.add(run)
    db_session.flush()
    return run


def _format_check(slots):
    return {slot: FileFormatCheck(filename=f"{slot}.ab1", valid=True) for slot in slots}


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
            db_session, {"usability_check.min_length": 800}
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
