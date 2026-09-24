"""Stage 7 (Usability Check) tests.

Written first, against the not-yet-existing app.pipeline.usability_check
module, to confirm red before implementing.

Per CLAUDE.md: the real accept/reject gate, distinct from Stage 3's
lenient pre-trim floor -- runs on whatever survived cleanup (Stage 6's
consensus, two-read path, or Stage 4's single trimmed read, single-read
path) and asks "is this good enough to search," not "was the raw input
catastrophically bad." Three rules: minimum length, minimum mean quality,
maximum unresolved ambiguous positions (two-read path only).

`check_usability` takes (sequence, quality_scores, ambiguous_positions)
directly -- the shape both Stage 6's ConsensusResult and a Stage 4
TrimResult (paired with its own sliced quality scores and an empty
ambiguous list, since single-read has no consensus-merge ambiguity
concept) reduce to. `check_usability_from_consensus` and
`check_usability_from_single_read` are the two thin, directly-testable
entry points matching CLAUDE.md's two named input paths.

Thresholds (min_length=500, min_mean_quality=25,
max_ambiguous_proportion=0.02) are the values already researched and
cited in claude/configuration-defaults.md.
"""
from pathlib import Path

import pytest

from app.pipeline.ab1_extraction import extract_read
from app.pipeline.trim import trim_read
from app.pipeline.usability_check import (
    check_usability,
    check_usability_from_consensus,
    check_usability_from_single_read,
)
from app.schemas.consensus import ConsensusResult

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestCheckUsability:
    def test_passes_when_all_thresholds_cleared(self):
        result = check_usability("A" * 600, [30] * 600, [])

        assert result.status == "PASS"
        assert result.final_length == 600
        assert result.mean_quality == pytest.approx(30.0)
        assert result.ambiguous_positions == 0
        assert result.reason is None

    def test_fails_on_too_short_length(self):
        result = check_usability("A" * 100, [30] * 100, [])

        assert result.status == "FAIL"
        assert "length" in result.reason.lower()

    def test_fails_on_low_mean_quality(self):
        result = check_usability("A" * 600, [10] * 600, [])

        assert result.status == "FAIL"
        assert "quality" in result.reason.lower()

    def test_fails_on_excessive_ambiguous_proportion(self):
        # 20 of 600 positions ambiguous = 3.33%, above the 2% ceiling.
        result = check_usability("A" * 600, [30] * 600, list(range(20)))

        assert result.status == "FAIL"
        assert "ambiguous" in result.reason.lower()

    def test_passes_at_exact_boundaries(self):
        # length exactly at the floor, mean quality exactly at the floor,
        # ambiguous proportion exactly at the ceiling (12/600 = 0.02) --
        # every threshold is inclusive.
        result = check_usability(
            "A" * 600, [25] * 600, list(range(12)), min_length=600
        )

        assert result.status == "PASS"

    def test_computes_mean_quality_correctly(self):
        result = check_usability("AAA", [10, 20, 30], [], min_length=1)

        assert result.mean_quality == pytest.approx(20.0)

    def test_combines_multiple_failure_reasons(self):
        result = check_usability("A" * 100, [10] * 100, [])

        assert result.status == "FAIL"
        assert "length" in result.reason.lower()
        assert "quality" in result.reason.lower()

    def test_custom_thresholds_override_defaults(self):
        lenient = check_usability("A" * 100, [10] * 100, [], min_length=1, min_mean_quality=1)
        strict = check_usability("A" * 100, [10] * 100, [], min_length=1000)

        assert lenient.status == "PASS"
        assert strict.status == "FAIL"

    def test_real_trimmed_fixtures_pass_under_default_thresholds(self):
        # 3100.ab1 trims to 667bp / mean quality ~53.6; 3730.ab1 to
        # 1073bp / ~47.8 -- both comfortably clear the defaults.
        for name in ["3100.ab1", "3730.ab1"]:
            extraction = extract_read(FIXTURES_DIR / name)
            trim = trim_read(extraction)
            trimmed_quality = extraction.quality_scores[trim.trim_start:trim.trim_end]

            result = check_usability(trim.trimmed_sequence, trimmed_quality, [])

            assert result.status == "PASS", f"{name} unexpectedly failed: {result.reason}"


class TestCheckUsabilityFromConsensus:
    def test_maps_consensus_fields_through(self):
        consensus = ConsensusResult(
            consensus_sequence="A" * 600,
            consensus_length=600,
            ambiguous_positions=[5, 10],
            quality_scores=[30] * 600,
        )

        result = check_usability_from_consensus(consensus)

        assert result.final_length == 600
        assert result.ambiguous_positions == 2
        assert result.status == "PASS"


class TestCheckUsabilityFromSingleRead:
    def test_maps_trim_and_quality_through_with_no_ambiguity_concept(self):
        extraction = extract_read(FIXTURES_DIR / "3100.ab1")
        trim = trim_read(extraction)
        trimmed_quality = extraction.quality_scores[trim.trim_start:trim.trim_end]

        result = check_usability_from_single_read(trim, trimmed_quality)

        assert result.final_length == trim.trimmed_length
        assert result.ambiguous_positions == 0
        assert result.status == "PASS"
