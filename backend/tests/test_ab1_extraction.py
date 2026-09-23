"""
Stage 2 (AB1 extraction) tests -- written first, against CLAUDE.md's Stage 2
contract, before backend/app/pipeline/ab1_extraction.py exists.

Like Stage 1, built and tested as a standalone pipeline function, not yet
wired into any API route (see backend/tests/test_format_check.py's module
docstring for why).

Pure extraction, no judgment: per CLAUDE.md, Stage 2 runs "for each file
that passed Stage 1" -- it is not responsible for handling invalid files
gracefully (that's Stage 1's job, upstream of this one).
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestExtractRead:
    def test_extracts_sequence_and_length(self):
        from app.pipeline.ab1_extraction import extract_read

        result = extract_read(FIXTURES / "3100.ab1")

        assert isinstance(result.raw_sequence, str)
        assert len(result.raw_sequence) == 795
        assert result.raw_length == 795
        assert result.raw_length == len(result.raw_sequence)

    def test_extracts_quality_scores_matching_sequence_length(self):
        from app.pipeline.ab1_extraction import extract_read

        result = extract_read(FIXTURES / "3100.ab1")

        assert len(result.quality_scores) == result.raw_length
        assert all(isinstance(q, int) for q in result.quality_scores)
        assert all(q >= 0 for q in result.quality_scores)

    def test_extracts_second_fixture(self):
        from app.pipeline.ab1_extraction import extract_read

        result = extract_read(FIXTURES / "3730.ab1")

        assert result.raw_length == 1165
        assert len(result.quality_scores) == 1165

    def test_extraction_applies_no_judgment_even_to_a_bad_read(self):
        """
        empty.ab1 is a structurally valid but essentially unreadable AB1
        (5 bases, all N, 0 Phred quality). Stage 2 is pure extraction --
        it reports what's there, it doesn't reject or flag it. That's
        Stage 3 (Coarse Sanity Check)'s job.
        """
        from app.pipeline.ab1_extraction import extract_read

        result = extract_read(FIXTURES / "empty.ab1")

        assert result.raw_length == 5
        assert result.raw_sequence == "NNNNN"
        assert result.quality_scores == [0, 0, 0, 0, 0]

    def test_raises_on_a_file_that_failed_format_validity(self):
        """
        Not Stage 2's job to handle gracefully -- orchestration only calls
        this on files that already passed Stage 1. Documented here as an
        explicit contract rather than left undefined.
        """
        from app.pipeline.ab1_extraction import extract_read

        with pytest.raises(Exception):
            extract_read(FIXTURES / "not_ab1_format.ab1")


class TestExtractReadsForFiles:
    def test_aggregates_both_slots_when_both_present(self):
        from app.pipeline.ab1_extraction import extract_reads_for_files

        results = extract_reads_for_files(
            {"forward": FIXTURES / "3100.ab1", "reverse": FIXTURES / "3730.ab1"}
        )

        assert set(results.keys()) == {"forward", "reverse"}
        assert results["forward"].raw_length == 795
        assert results["reverse"].raw_length == 1165

    def test_reports_only_the_slot_that_was_provided(self):
        from app.pipeline.ab1_extraction import extract_reads_for_files

        results = extract_reads_for_files({"reverse": FIXTURES / "3730.ab1"})

        assert set(results.keys()) == {"reverse"}
        assert results["reverse"].raw_length == 1165
