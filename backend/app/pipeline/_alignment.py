"""Shared Bio.Align.PairwiseAligner configuration for Stage 5 (Orientation
Detection) and Stage 6 (Consensus Building) -- both need the identical
local-alignment scoring scheme, so it lives in one place rather than being
duplicated (and risking drift) between the two modules.
"""
from Bio import Align


def build_pairwise_aligner() -> Align.PairwiseAligner:
    aligner = Align.PairwiseAligner()
    aligner.mode = "local"
    aligner.match_score = 1
    aligner.mismatch_score = -1
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -1
    return aligner
