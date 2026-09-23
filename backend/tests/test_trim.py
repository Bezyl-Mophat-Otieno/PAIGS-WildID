"""Stage 4 (Trimming) tests.

Written first, against the not-yet-existing app.pipeline.trim module, to
confirm red before implementing.

Per CLAUDE.md: trimming finds the reliable window of a read using its
per-base Phred quality scores and cuts off everything outside it, runs on
each Stage-3-passed read independently, and must log the exact parameters
used (this data feeds the audit trail). Per the suggested build order:
"test with synthetic quality-score arrays so exact trim boundaries can be
asserted, not just 'it ran.'" -- every synthetic case below has its
expected window hand-computed and explained, not just asserted against
whatever the implementation happens to produce.

Algorithm: a Kadane's-maximum-subarray scan over (quality[i] -
quality_threshold), i.e. the standard "modified Mott" trimming approach --
plain arithmetic over already-extracted quality scores, no new library,
matching CLAUDE.md's own tooling note for this stage.
"""
from pathlib import Path

import pytest

from app.pipeline.ab1_extraction import extract_read
from app.pipeline.trim import trim_read, trim_reads_for_files
from app.schemas.ab1_extraction import ReadExtraction

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _extraction(sequence: str, scores: list) -> ReadExtraction:
    assert len(sequence) == len(scores)
    return ReadExtraction(raw_sequence=sequence, raw_length=len(sequence), quality_scores=scores)


class TestTrimRead:
    def test_keeps_the_whole_read_when_uniformly_above_threshold(self):
        sequence = "ATGCATGCAT"
        scores = [30] * 10
        extraction = _extraction(sequence, scores)

        result = trim_read(extraction, quality_threshold=20, min_window_size=1)

        assert result.trimmed_sequence == sequence
        assert result.trimmed_length == 10
        assert result.trim_start == 0
        assert result.trim_end == 10

    def test_trims_a_noisy_head_and_tail_around_a_clean_middle(self):
        # quality - threshold(20): [-15,-15,-15, 10,10,10,10, -15,-15,-15]
        # Kadane's max-sum contiguous window is indices 3..6 (sum 40) --
        # hand-computed, not just whatever the code happens to produce.
        sequence = "AAAGGGGTTT"
        scores = [5, 5, 5, 30, 30, 30, 30, 5, 5, 5]
        extraction = _extraction(sequence, scores)

        result = trim_read(extraction, quality_threshold=20, min_window_size=1)

        assert result.trim_start == 3
        assert result.trim_end == 7
        assert result.trimmed_sequence == "GGGG"
        assert result.trimmed_length == 4

    def test_treats_a_below_floor_window_as_nothing_left_to_keep(self):
        # Same shape as the case above (a real, positive-sum window exists
        # at indices 3..6, length 4) but min_window_size now excludes it.
        sequence = "AAAGGGGTTT"
        scores = [5, 5, 5, 30, 30, 30, 30, 5, 5, 5]
        extraction = _extraction(sequence, scores)

        result = trim_read(extraction, quality_threshold=20, min_window_size=50)

        assert result.trimmed_sequence == ""
        assert result.trimmed_length == 0

    def test_uniformly_below_threshold_yields_nothing_to_keep(self):
        sequence = "AAAAAAAAAA"
        scores = [2] * 10
        extraction = _extraction(sequence, scores)

        result = trim_read(extraction, quality_threshold=20, min_window_size=1)

        assert result.trimmed_sequence == ""
        assert result.trimmed_length == 0

    def test_ties_pick_the_earliest_maximal_window_deterministically(self):
        # Two equally-good windows of quality 30 (sum surplus 10 each over
        # threshold 20), separated by a dip back to exactly the threshold
        # (surplus 0, never lets the running sum go negative, so a naive
        # scan could keep extending into the second peak). Reproducibility
        # for an audit trail requires a single, deterministic answer.
        sequence = "AAAAGGGGAAAAGGGGAAAA"
        scores = [5, 5, 5, 5, 30, 30, 30, 30, 20, 20, 20, 20, 5, 5, 5, 5, 30, 30, 30, 30]
        extraction = _extraction(sequence, scores)

        result = trim_read(extraction, quality_threshold=20, min_window_size=1)

        assert result.trim_start == 4
        assert result.trim_end == 8
        assert result.trimmed_length == 4

    def test_captures_the_parameters_used_for_the_audit_trail(self):
        extraction = _extraction("ATGCATGCAT", [30] * 10)

        result = trim_read(extraction, quality_threshold=25, min_window_size=3)

        assert result.trim_params == {"quality_threshold": 25, "min_window_size": 3}

    def test_defaults_match_the_documented_configuration_defaults(self):
        extraction = _extraction("A" * 60, [30] * 60)

        result = trim_read(extraction)

        assert result.trim_params == {"quality_threshold": 20, "min_window_size": 50}

    def test_real_fixture_trims_to_a_shorter_but_nonempty_window(self):
        extraction = extract_read(FIXTURES_DIR / "3100.ab1")

        result = trim_read(extraction, quality_threshold=20, min_window_size=50)

        assert 0 < result.trimmed_length <= extraction.raw_length
        assert result.trimmed_sequence == extraction.raw_sequence[result.trim_start:result.trim_end]

    def test_empty_read_yields_nothing_to_keep(self):
        extraction = _extraction("", [])

        result = trim_read(extraction, quality_threshold=20, min_window_size=1)

        assert result.trimmed_sequence == ""
        assert result.trimmed_length == 0


class TestTrimReadsForFiles:
    def test_aggregates_both_slots_when_both_present(self):
        extractions = {
            "forward": extract_read(FIXTURES_DIR / "3100.ab1"),
            "reverse": extract_read(FIXTURES_DIR / "3730.ab1"),
        }

        results = trim_reads_for_files(extractions)

        assert set(results.keys()) == {"forward", "reverse"}
        assert results["forward"].trimmed_length > 0
        assert results["reverse"].trimmed_length > 0

    def test_reports_only_the_slot_that_was_provided(self):
        extractions = {"forward": extract_read(FIXTURES_DIR / "3100.ab1")}

        results = trim_reads_for_files(extractions)

        assert set(results.keys()) == {"forward"}
