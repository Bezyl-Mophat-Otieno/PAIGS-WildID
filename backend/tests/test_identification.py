"""Stage 10 (Identification engine) tests.

Written first, against the not-yet-existing app.pipeline.identification
module, to confirm red before implementing.

Per CLAUDE.md: the ranked BLAST hits (Stage 9's output) are run through a
rules layer deciding PASS / AMBIGUOUS / REVIEW REQUIRED -- the top hit is
never taken at face value. Three things this checks (per
claude/configuration-defaults.md's researched defaults, 98%/90%/1pt):
does the top hit clear the identity floor, does it clear the coverage
floor, and is the runner-up far enough behind it. NOT implemented: the
"taxonomically inconsistent" qualitative REVIEW REQUIRED trigger CLAUDE.md
names -- no numeric threshold covers it and no domain-provided taxonomy
consistency rules exist yet (see configuration-defaults.md's own caveat).
`taxonomic_consistency_checked` is always False, making that gap visible
in the output itself rather than just in documentation.
"""
import pytest

from app.pipeline.identification import (
    DEFAULT_AMBIGUOUS_MARGIN_PCT,
    DEFAULT_MIN_COVERAGE_PCT,
    DEFAULT_MIN_IDENTITY_PCT,
    identify_species,
    identify_species_from_blast_result,
)
from app.schemas.blast import BlastHit, BlastSearchResult


def _hit(rank, species, identity, coverage, accession="REFXXX", evalue=0.0, bit_score=1000.0):
    return BlastHit(
        rank=rank,
        species=species,
        identity=identity,
        coverage=coverage,
        evalue=evalue,
        bit_score=bit_score,
        accession=accession,
    )


class TestIdentifySpecies:
    def test_clear_pass_single_hit(self):
        hits = [_hit(1, "Panthera leo", 99.71, 98.2)]

        result = identify_species(hits)

        assert result.status == "PASS"
        assert result.candidate_species == "Panthera leo"
        assert result.identity == 99.71
        assert result.coverage == 98.2
        assert result.reason is None

    def test_pass_when_second_candidate_is_not_close(self):
        hits = [
            _hit(1, "Panthera leo", 99.71, 98.2),
            _hit(2, "Panthera pardus", 94.10, 96.7),
        ]

        result = identify_species(hits)

        assert result.status == "PASS"
        assert result.candidate_species == "Panthera leo"

    def test_ambiguous_when_second_candidate_is_close(self):
        hits = [
            _hit(1, "Panthera leo", 99.0, 95.0),
            _hit(2, "Panthera pardus", 98.5, 94.0),  # 0.5pt behind, below the 1pt margin
        ]

        result = identify_species(hits)

        assert result.status == "AMBIGUOUS"
        assert result.candidate_species == "Panthera leo"  # still the top hit
        assert "Panthera pardus" in result.reason

    def test_review_required_on_low_identity(self):
        hits = [_hit(1, "Panthera leo", 90.0, 95.0)]

        result = identify_species(hits)

        assert result.status == "REVIEW REQUIRED"
        assert result.candidate_species == "Panthera leo"  # reported, not hidden
        assert "identity" in result.reason.lower()

    def test_review_required_on_low_coverage(self):
        hits = [_hit(1, "Panthera leo", 99.0, 50.0)]

        result = identify_species(hits)

        assert result.status == "REVIEW REQUIRED"
        assert "coverage" in result.reason.lower()

    def test_review_required_combines_multiple_failure_reasons(self):
        hits = [_hit(1, "Panthera leo", 50.0, 50.0)]

        result = identify_species(hits)

        assert result.status == "REVIEW REQUIRED"
        assert "identity" in result.reason.lower()
        assert "coverage" in result.reason.lower()

    def test_review_required_on_zero_hits(self):
        result = identify_species([])

        assert result.status == "REVIEW REQUIRED"
        assert result.candidate_species is None
        assert result.identity is None
        assert result.coverage is None
        assert "no" in result.reason.lower()

    def test_failed_thresholds_take_priority_over_ambiguous_check(self):
        # Top hit fails coverage outright; a close second candidate exists
        # too, but REVIEW REQUIRED (thresholds not met) should win, not
        # AMBIGUOUS -- CLAUDE.md orders "thresholds aren't met" first.
        hits = [
            _hit(1, "Panthera leo", 99.0, 50.0),
            _hit(2, "Panthera pardus", 98.9, 96.0),
        ]

        result = identify_species(hits)

        assert result.status == "REVIEW REQUIRED"

    def test_boundaries_are_inclusive(self):
        # identity/coverage exactly at the floor, margin exactly at the
        # separation required -- every threshold is inclusive, same
        # convention as Stage 7's usability check.
        hits = [
            _hit(1, "Panthera leo", 98.0, 90.0),
            _hit(2, "Panthera pardus", 97.0, 85.0),  # exactly 1.0pt behind
        ]

        result = identify_species(hits)

        assert result.status == "PASS"

    def test_custom_thresholds_override_defaults(self):
        hits = [_hit(1, "Panthera leo", 95.0, 85.0)]

        lenient = identify_species(hits, min_identity_pct=90.0, min_coverage_pct=80.0)
        strict = identify_species(hits, min_identity_pct=99.0)

        assert lenient.status == "PASS"
        assert strict.status == "REVIEW REQUIRED"

    def test_thresholds_applied_reflects_what_was_actually_used(self):
        hits = [_hit(1, "Panthera leo", 99.0, 95.0)]

        result = identify_species(hits, min_identity_pct=97.0)

        assert result.thresholds_applied["min_identity_pct"] == 97.0
        assert result.thresholds_applied["min_coverage_pct"] == DEFAULT_MIN_COVERAGE_PCT
        assert result.thresholds_applied["ambiguous_margin_pct"] == DEFAULT_AMBIGUOUS_MARGIN_PCT

    def test_defaults_match_configuration_defaults_doc(self):
        assert DEFAULT_MIN_IDENTITY_PCT == 98.0
        assert DEFAULT_MIN_COVERAGE_PCT == 90.0
        assert DEFAULT_AMBIGUOUS_MARGIN_PCT == 1.0

    def test_taxonomic_consistency_is_honestly_reported_as_not_checked(self):
        hits = [_hit(1, "Panthera leo", 99.71, 98.2)]

        result = identify_species(hits)

        assert result.taxonomic_consistency_checked is False


class TestIdentifySpeciesFromBlastResult:
    def test_thin_wrapper_matches_stage_9_output_shape(self):
        search_result = BlastSearchResult(
            hits=[_hit(1, "Panthera leo", 99.71, 98.2)],
            database_version="v1",
            query_length=138,
        )

        result = identify_species_from_blast_result(search_result)

        assert result.status == "PASS"
        assert result.candidate_species == "Panthera leo"

    def test_thresholds_pass_through(self):
        search_result = BlastSearchResult(
            hits=[_hit(1, "Panthera leo", 95.0, 95.0)],
            database_version="v1",
            query_length=138,
        )

        result = identify_species_from_blast_result(search_result, min_identity_pct=99.0)

        assert result.status == "REVIEW REQUIRED"
