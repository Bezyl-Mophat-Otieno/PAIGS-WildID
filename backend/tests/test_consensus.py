"""Stage 6 (Consensus Building) tests.

Written first, against the not-yet-existing app.pipeline.consensus
module, to confirm red before implementing.

Per CLAUDE.md, per position: both reads agree -> keep it; they disagree
-> compare Phred quality, keep the more confident one; one gives a
confident base and the other an IUPAC ambiguity code consistent with it
-> the confident base wins; both confident but genuinely disagree ->
flagged ambiguous, never silently resolved.

Reading "compare quality, keep the more confident one" and "both
confident but genuinely disagree -> ambiguous" as two branches of the
same rule (documented in app/pipeline/consensus.py): when qualities
differ, the higher one wins; when they're exactly equal, there's no
basis to call either "more confident", so it's the ambiguous case.

`resolve_base` (the per-position decision) is tested directly first,
with every branch hand-verified; `build_consensus` (the full merge) is
then tested end-to-end against a hand-verified synthetic overlap whose
expected mismatches/resolutions were worked out and confirmed against a
real Biopython alignment call before being written into these
assertions (single-block coordinates, exact resolved bases at each
seeded conflict) -- not just asserted against whatever the
implementation happens to produce.
"""
import random

import pytest
from Bio.Seq import Seq

from app.pipeline.consensus import build_consensus, resolve_base
from app.schemas.orientation import OrientationResult


def _template(seed: int, length: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ATGC") for _ in range(length))


class TestResolveBase:
    def test_agreeing_definite_bases_returns_that_base_not_ambiguous(self):
        base, is_ambiguous = resolve_base("A", 30, "A", 10)

        assert base == "A"
        assert is_ambiguous is False

    def test_disagreeing_definite_bases_picks_higher_quality(self):
        base, is_ambiguous = resolve_base("A", 40, "C", 10)

        assert base == "A"
        assert is_ambiguous is False

        base2, is_ambiguous2 = resolve_base("A", 10, "C", 40)

        assert base2 == "C"
        assert is_ambiguous2 is False

    def test_disagreeing_definite_bases_with_equal_quality_is_ambiguous(self):
        # A and C, equal confidence -> genuinely can't be resolved.
        # IUPAC code for {A, C} is M.
        base, is_ambiguous = resolve_base("A", 30, "C", 30)

        assert base == "M"
        assert is_ambiguous is True

    def test_ambiguity_code_consistent_with_confident_base_lets_confident_base_win(self):
        # W = A or T. A confident "A" is consistent with it -> A wins,
        # regardless of the relative quality scores.
        base, is_ambiguous = resolve_base("A", 5, "W", 60)

        assert base == "A"
        assert is_ambiguous is False

    def test_n_is_treated_as_consistent_with_any_confident_base(self):
        base, is_ambiguous = resolve_base("G", 5, "N", 60)

        assert base == "G"
        assert is_ambiguous is False

    def test_ambiguity_code_inconsistent_with_confident_base_falls_back_to_quality(self):
        # Y = C or T. A confident "A" is NOT consistent with it -> a
        # genuine conflict, resolved the same way two definite bases
        # disagreeing would be.
        base, is_ambiguous = resolve_base("A", 40, "Y", 10)

        assert base == "A"
        assert is_ambiguous is False


class TestBuildConsensus:
    def test_perfect_agreement_across_the_full_overlap(self):
        template = _template(seed=42, length=180)
        forward_sequence = template[0:120]
        reverse_sequence = str(Seq(template[60:180]).reverse_complement())
        orientation = OrientationResult(
            orientation="reverse_read_reverse_complemented",
            alignment_score=60.0,
            overlap_length=60,
            identity=1.0,
            label_orientation_mismatch=False,
        )

        result = build_consensus(
            forward_sequence, [40] * 120, reverse_sequence, [40] * 120, orientation
        )

        assert result.consensus_sequence == template
        assert result.consensus_length == 180
        assert result.ambiguous_positions == []

    def test_merges_mixed_resolution_cases_at_hand_verified_positions(self):
        # 60bp overlap "ACGTACGT..." (template[i] = "ACGT"[i % 4]),
        # forward carries a 10bp unique prefix, reverse (already in "as
        # is" orientation for this test) carries a 10bp unique suffix.
        # Confirmed via a real PairwiseAligner call beforehand that this
        # produces a single ungapped 60bp block at forward[10:70] /
        # reverse[0:60] despite the seeded mismatches below.
        overlap_template = "ACGT" * 15  # template[10]='G', [20]='A', [30]='G', [40]='A'
        forward_prefix = "T" * 10
        forward_sequence = forward_prefix + overlap_template
        forward_quality = [40] * 70

        overlap_mutated = list(overlap_template)
        overlap_mutated[10] = "C"  # definite mismatch, reverse loses on quality
        overlap_mutated[20] = "C"  # definite mismatch, equal quality -> ambiguous
        overlap_mutated[30] = "R"  # A/G, consistent with forward's 'G' -> forward wins
        overlap_mutated[40] = "N"  # consistent with anything -> forward wins
        reverse_suffix = "G" * 10
        reverse_sequence = "".join(overlap_mutated) + reverse_suffix

        reverse_quality = [35] * 70
        reverse_quality[10] = 10  # clearly lower than forward's 40
        reverse_quality[20] = 40  # tied with forward's 40
        reverse_quality[30] = 25  # irrelevant -- ambiguity-consistency short-circuits
        reverse_quality[40] = 5  # irrelevant -- N is always consistent

        orientation = OrientationResult(
            orientation="as_is",
            alignment_score=52.0,
            overlap_length=60,
            identity=56 / 60,
            label_orientation_mismatch=True,
        )

        result = build_consensus(
            forward_sequence, forward_quality, reverse_sequence, reverse_quality, orientation
        )

        expected_overlap = list(overlap_template)
        expected_overlap[20] = "M"  # {A, C} -- the only unresolved position
        expected_consensus = forward_prefix + "".join(expected_overlap) + reverse_suffix

        assert result.consensus_sequence == expected_consensus
        assert result.consensus_length == len(expected_consensus)
        assert result.ambiguous_positions == [10 + 20]  # prefix length + overlap index

    def test_raises_when_orientation_found_no_usable_overlap(self):
        orientation = OrientationResult(orientation="no_overlap_found")

        with pytest.raises(ValueError):
            build_consensus("ATGC", [30] * 4, "ATGC", [30] * 4, orientation)
