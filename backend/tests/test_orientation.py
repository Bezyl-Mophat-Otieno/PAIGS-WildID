"""Stage 5 (Orientation Detection) tests.

Written first, against the not-yet-existing app.pipeline.orientation
module, to confirm red before implementing.

Per the suggested build order: "needs a real or constructed forward/
reverse pair with a known overlap; synthetic fixtures (a sequence plus
its deliberately reverse-complemented, slightly mutated twin) are worth
building here." Every synthetic pair below is built from a known 180bp
template (fixed random seed, so it's reproducible) with a known 60bp
overlap region -- the expected overlap_length/identity/score for each
scenario were verified empirically against Biopython's PairwiseAligner
before being written into these assertions, not guessed.
"""
import random

import pytest
from Bio.Seq import Seq

from app.pipeline.ab1_extraction import extract_read
from app.pipeline.orientation import detect_orientation
from app.pipeline.trim import trim_read
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _template(seed: int, length: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ATGC") for _ in range(length))


class TestDetectOrientation:
    def test_detects_reverse_complement_orientation_for_a_true_pair(self):
        # Template positions 0-119 sequenced as "forward"; positions
        # 60-179 sequenced from the other end as "reverse" (reported, as
        # any Sanger read is, 5'->3' -- i.e. the reverse complement of
        # that template stretch). True overlap: template[60:120], 60bp,
        # perfect identity by construction.
        template = _template(seed=42, length=180)
        forward = template[0:120]
        reverse = str(Seq(template[60:180]).reverse_complement())

        result = detect_orientation(forward, reverse)

        assert result.orientation == "reverse_read_reverse_complemented"
        assert result.overlap_length == 60
        assert result.identity == pytest.approx(1.0)
        assert result.alignment_score == pytest.approx(60.0)
        assert result.label_orientation_mismatch is False

    def test_flags_label_mismatch_when_reverse_slot_is_already_forward_oriented(self):
        # Same template/overlap, but the "reverse" slot holds a same-
        # strand continuation instead of a true reverse-primer read --
        # as if the analyst uploaded two forward-direction reads, or the
        # files were swapped. The strong overlap now shows up as-is.
        template = _template(seed=42, length=180)
        forward = template[0:120]
        mislabeled_reverse = template[60:180]  # NOT reverse-complemented

        result = detect_orientation(forward, mislabeled_reverse)

        assert result.orientation == "as_is"
        assert result.overlap_length == 60
        assert result.identity == pytest.approx(1.0)
        assert result.label_orientation_mismatch is True

    def test_flags_no_overlap_for_genuinely_unrelated_reads(self):
        # Two independently-random 120bp sequences -- neither attempt
        # should clear the usable-overlap bar (verified empirically: the
        # best either attempt manages is a short, low-identity spurious
        # alignment).
        seq_a = _template(seed=1, length=120)
        seq_b = _template(seed=2, length=120)

        result = detect_orientation(seq_a, seq_b)

        assert result.orientation == "no_overlap_found"
        assert result.alignment_score is None
        assert result.overlap_length is None
        assert result.label_orientation_mismatch is None

    def test_relaxed_thresholds_can_turn_a_marginal_match_into_a_result(self):
        # Same unrelated pair as above, but with thresholds loosened far
        # enough that both spurious attempts now qualify -- the larger,
        # higher-scoring one (the reverse-complement attempt: 15bp/80%
        # identity vs the as-is attempt's 7bp/100% identity) should win
        # the tie-break deterministically.
        seq_a = _template(seed=1, length=120)
        seq_b = _template(seed=2, length=120)

        result = detect_orientation(seq_a, seq_b, min_overlap_length=5, min_identity=0.5)

        assert result.orientation == "reverse_read_reverse_complemented"
        assert result.overlap_length == 15

    def test_real_unrelated_fixtures_do_not_produce_a_false_overlap(self):
        # Sanity check against real (trimmed) AB1 data: 3100.ab1 and
        # 3730.ab1 are unrelated sample files, not a matched pair, so
        # orientation detection must not fabricate a match between them.
        forward = trim_read(extract_read(FIXTURES_DIR / "3100.ab1"))
        reverse = trim_read(extract_read(FIXTURES_DIR / "3730.ab1"))

        result = detect_orientation(forward.trimmed_sequence, reverse.trimmed_sequence)

        assert result.orientation == "no_overlap_found"
