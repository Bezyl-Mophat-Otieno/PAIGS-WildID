"""Stage 3 (Coarse Sanity Check) tests.

Written first, against the not-yet-existing app.pipeline.sanity_check module,
to confirm red before implementing.

Per CLAUDE.md: a deliberately *lenient* hard stop -- catches genuinely broken
reads (near-total N, absurdly short), not the normal noisy edges every raw
Sanger read has. Input is Stage 2's extracted read(s); this stage does not
touch files or re-parse AB1 data.

Threshold values are "sensible starting defaults, pending real domain
review" per CLAUDE.md's Configuration model section -- there is no
Configuration subsystem yet, so check_sanity/check_sanity_for_files accept
thresholds as keyword overrides with module-level defaults, ready to be fed
by real config once that subsystem exists.

Branching across multiple reads (single-read fallback, whole-run stop) is
explicitly orchestration's job (build-order step 9) once actual Stage/Run
records exist to update -- not something a per-file sanity check computes on
its own. Only the per-file and per-run-of-slots check functions are built
here, consistent with Stage 1 and Stage 2.
"""
from pathlib import Path

import pytest

from app.pipeline.ab1_extraction import extract_read
from app.pipeline.sanity_check import check_sanity, check_sanity_for_files
from app.schemas.ab1_extraction import ReadExtraction

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _extraction(raw_sequence: str) -> ReadExtraction:
    # quality_scores' content isn't inspected by Stage 3, only sequence and
    # length -- fill with a flat, plausible score per base.
    return ReadExtraction(
        raw_sequence=raw_sequence,
        raw_length=len(raw_sequence),
        quality_scores=[30] * len(raw_sequence),
    )


class TestCheckSanity:
    def test_real_fixture_with_clean_signal_passes(self):
        extraction = extract_read(FIXTURES_DIR / "3100.ab1")

        result = check_sanity(extraction)

        assert result.status == "PASS"
        assert result.raw_length == 795
        assert result.n_proportion == 0.0

    def test_second_real_fixture_passes(self):
        extraction = extract_read(FIXTURES_DIR / "3730.ab1")

        result = check_sanity(extraction)

        assert result.status == "PASS"
        assert result.raw_length == 1165
        assert result.n_proportion == 0.0

    def test_known_catastrophic_fixture_fails(self):
        # empty.ab1: 5bp, 100% N -- structurally valid AB1 (passed Stage 1),
        # a real read (passed Stage 2), but exactly the kind of unusable
        # signal Stage 3 exists to catch.
        extraction = extract_read(FIXTURES_DIR / "empty.ab1")

        result = check_sanity(extraction)

        assert result.status == "FAIL"
        assert result.raw_length == 5
        assert result.n_proportion == 1.0

    def test_computes_n_proportion_correctly(self):
        extraction = _extraction("ATGCNNATGC")  # 2 of 10 bases are N

        result = check_sanity(extraction)

        assert result.n_proportion == pytest.approx(0.2)

    def test_fails_on_excessive_n_proportion_even_with_ample_length(self):
        # Long enough to clear the length floor, but mostly N.
        sequence = "N" * 60 + "ATGC" * 10
        extraction = _extraction(sequence)

        result = check_sanity(extraction, max_n_proportion=0.5)

        assert result.status == "FAIL"

    def test_fails_on_too_short_raw_length_even_with_zero_n(self):
        extraction = _extraction("ATGC")  # clean, but far too short

        result = check_sanity(extraction, min_raw_length=20)

        assert result.status == "FAIL"

    def test_passes_at_exactly_the_n_proportion_threshold(self):
        # 15 of 60 bases are N -> exactly 0.25; threshold is inclusive.
        # (Length kept >= the default min_raw_length so only the
        # N-proportion boundary is under test here.)
        sequence = "N" * 15 + "A" * 45
        extraction = _extraction(sequence)

        result = check_sanity(extraction, max_n_proportion=0.25)

        assert result.n_proportion == pytest.approx(0.25)
        assert result.status == "PASS"

    def test_passes_at_exactly_the_length_floor(self):
        extraction = _extraction("A" * 20)

        result = check_sanity(extraction, min_raw_length=20)

        assert result.status == "PASS"

    def test_custom_thresholds_override_defaults(self):
        # A read that would PASS under lenient defaults must FAIL once a
        # stricter, run-specific override is supplied -- mirrors CLAUDE.md's
        # "analyst can override defaults for a run" capability.
        extraction = _extraction("N" * 2 + "ATGC" * 12)  # 2/50 = 0.04 N, length clears the default floor

        lenient = check_sanity(extraction, max_n_proportion=0.5)
        strict = check_sanity(extraction, max_n_proportion=0.01)

        assert lenient.status == "PASS"
        assert strict.status == "FAIL"


class TestCheckSanityForFiles:
    def test_aggregates_both_slots_when_both_present(self):
        extractions = {
            "forward": extract_read(FIXTURES_DIR / "3100.ab1"),
            "reverse": extract_read(FIXTURES_DIR / "3730.ab1"),
        }

        results = check_sanity_for_files(extractions)

        assert set(results.keys()) == {"forward", "reverse"}
        assert results["forward"].status == "PASS"
        assert results["reverse"].status == "PASS"

    def test_reports_only_the_slot_that_was_provided(self):
        extractions = {"forward": extract_read(FIXTURES_DIR / "3100.ab1")}

        results = check_sanity_for_files(extractions)

        assert set(results.keys()) == {"forward"}
