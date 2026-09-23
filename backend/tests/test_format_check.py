"""
Stage 1 (Format Validity Check) tests -- written first, against
CLAUDE.md's Stage 1 contract, before backend/app/pipeline/format_check.py
exists.

Deliberately NOT tested through an API route: per CLAUDE.md's own
suggested build order, stages 1-8 are built and unit-tested as standalone
pipeline functions first; orchestration (POST /runs/{id}/execute, the only
endpoint that triggers stages under the current API shape) is wired up
last, once the individual stages are proven.
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestCheckFormat:
    """The core per-file check: app.pipeline.format_check.check_format."""

    def test_valid_ab1_file_passes(self):
        from app.pipeline.format_check import check_format

        result = check_format(FIXTURES / "3100.ab1")

        assert result.valid is True
        assert result.reason is None
        assert result.filename == "3100.ab1"

    def test_second_valid_ab1_file_passes(self):
        from app.pipeline.format_check import check_format

        result = check_format(FIXTURES / "3730.ab1")

        assert result.valid is True
        assert result.reason is None

    def test_structurally_valid_but_low_quality_file_still_passes(self):
        """
        empty.ab1 is a real, structurally valid AB1 container -- it just
        contains an almost entirely N (unreadable) 5-base read. Stage 1
        only asks "is this a real AB1 file," not "is the read any good"
        (that's Stage 3, Coarse Sanity Check). This test documents and
        guards that distinction.
        """
        from app.pipeline.format_check import check_format

        result = check_format(FIXTURES / "empty.ab1")

        assert result.valid is True
        assert result.reason is None

    def test_plain_text_file_fails_with_plain_language_reason(self):
        from app.pipeline.format_check import check_format

        result = check_format(FIXTURES / "not_ab1_format.ab1")

        assert result.valid is False
        assert result.reason  # non-empty, plain-language explanation
        assert "AB1" in result.reason

    def test_truncated_ab1_file_fails(self):
        from app.pipeline.format_check import check_format

        result = check_format(FIXTURES / "truncated.ab1")

        assert result.valid is False
        assert result.reason

    def test_zero_byte_file_fails(self):
        from app.pipeline.format_check import check_format

        result = check_format(FIXTURES / "zero_byte.ab1")

        assert result.valid is False
        assert result.reason

    def test_missing_file_fails_rather_than_raising(self):
        """A missing/unreadable path is reported as a failed check, not an unhandled exception."""
        from app.pipeline.format_check import check_format

        result = check_format(FIXTURES / "does_not_exist.ab1")

        assert result.valid is False
        assert result.reason


class TestCheckFormatForFiles:
    """The stage-level entry point, keyed like Stage 0's forward/reverse slots."""

    def test_aggregates_both_slots_when_both_present(self):
        from app.pipeline.format_check import check_format_for_files

        results = check_format_for_files(
            {"forward": FIXTURES / "3100.ab1", "reverse": FIXTURES / "3730.ab1"}
        )

        assert set(results.keys()) == {"forward", "reverse"}
        assert results["forward"].valid is True
        assert results["reverse"].valid is True

    def test_reports_only_the_slot_that_was_provided(self):
        from app.pipeline.format_check import check_format_for_files

        results = check_format_for_files({"forward": FIXTURES / "3100.ab1"})

        assert set(results.keys()) == {"forward"}

    def test_mixed_valid_and_invalid_slots(self):
        from app.pipeline.format_check import check_format_for_files

        results = check_format_for_files(
            {"forward": FIXTURES / "3100.ab1", "reverse": FIXTURES / "not_ab1_format.ab1"}
        )

        assert results["forward"].valid is True
        assert results["reverse"].valid is False
