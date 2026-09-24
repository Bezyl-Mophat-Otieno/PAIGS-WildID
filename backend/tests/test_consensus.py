"""Stage 6 (Consensus Building) tests.

resolve_base now returns (base, quality, is_ambiguous) -- a three-way
extension made necessary by Stage 7's own contract, not scope creep:
CLAUDE.md's Stage 7 rules require "minimum mean quality of the surviving
sequence," and that's only computable on the two-read path if Stage 6
carries per-position quality forward. The original two-value signature
(and ConsensusResult with no quality_scores field) genuinely couldn't
support that, so both are extended here, test-first as usual.

Effective quality per position, precisely: whenever the resolved base can
be traced to one specific read's own definite call being confirmed as the
answer (a clean quality-based win, or that read's call surviving an
ambiguity-consistency/intersection check), that read's own quality is
used -- it's genuinely that read's own confidence being kept. In every
other case (both reads agreeing outright, a tie, or a fallback to
ambiguous), max(quality_a, quality_b) is used as the best evidence bound
available, never inventing confidence beyond what either read reported.

Every expected value below (including the full quality_scores arrays in
the two build_consensus end-to-end tests) was hand-derived from this rule
before being written into the assertions.
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
    def test_agreeing_definite_bases_returns_max_quality_not_ambiguous(self):
        base, quality, is_ambiguous = resolve_base("A", 30, "A", 10)

        assert base == "A"
        assert quality == 30  # max(30, 10) -- both reads corroborate the call
        assert is_ambiguous is False

    def test_disagreeing_definite_bases_picks_higher_quality(self):
        base, quality, is_ambiguous = resolve_base("A", 40, "C", 10)

        assert base == "A"
        assert quality == 40  # the winner's own quality
        assert is_ambiguous is False

        base2, quality2, is_ambiguous2 = resolve_base("A", 10, "C", 40)

        assert base2 == "C"
        assert quality2 == 40
        assert is_ambiguous2 is False

    def test_disagreeing_definite_bases_with_equal_quality_is_ambiguous(self):
        # A and C, equal confidence -> genuinely can't be resolved.
        # IUPAC code for {A, C} is M.
        base, quality, is_ambiguous = resolve_base("A", 30, "C", 30)

        assert base == "M"
        assert quality == 30
        assert is_ambiguous is True

    def test_ambiguity_code_consistent_with_confident_base_lets_confident_base_win(self):
        # W = A or T. A confident "A" is consistent with it -> A wins,
        # using A's own quality regardless of W's reported quality.
        base, quality, is_ambiguous = resolve_base("A", 5, "W", 60)

        assert base == "A"
        assert quality == 5
        assert is_ambiguous is False

    def test_n_is_treated_as_consistent_with_any_confident_base(self):
        base, quality, is_ambiguous = resolve_base("G", 5, "N", 60)

        assert base == "G"
        assert quality == 5
        assert is_ambiguous is False

    def test_ambiguity_code_inconsistent_with_confident_base_falls_back_to_quality(self):
        # Y = C or T. A confident "A" is NOT consistent with it -> a
        # genuine conflict, resolved the same way two definite bases
        # disagreeing would be.
        base, quality, is_ambiguous = resolve_base("A", 40, "Y", 10)

        assert base == "A"
        assert quality == 40
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
        assert result.quality_scores == [40] * 180

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

        # Every overlap position resolves to quality 40: the 56 agreeing
        # positions via max(40, 35); idx10 via forward's own winning
        # quality (40 > 10); idx20 (the tie) via quality_a, which is 40;
        # idx30/idx40 via forward's own quality since forward's definite
        # call is what's kept (25 and 5 on the reverse side are
        # irrelevant, exactly as for the base itself). Prefix keeps
        # forward's own quality (40); suffix keeps reverse's own,
        # untouched, quality (35) -- neither was part of any comparison.
        assert result.quality_scores == [40] * 70 + [35] * 10

    def test_raises_when_orientation_found_no_usable_overlap(self):
        orientation = OrientationResult(orientation="no_overlap_found")

        with pytest.raises(ValueError):
            build_consensus("ATGC", [30] * 4, "ATGC", [30] * 4, orientation)
