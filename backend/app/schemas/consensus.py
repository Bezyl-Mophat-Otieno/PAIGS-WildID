from typing import List, Optional

from pydantic import BaseModel


class ResolvedPosition(BaseModel):
    """One overlap position (two-read consensus only) that Stage 6 was
    able to resolve to a definite call -- the complement of
    ConsensusResult.ambiguous_positions, which only lists the positions
    it couldn't. `position` uses the same indexing as
    ambiguous_positions (into the final consensus_sequence, not the raw
    overlap slice), so the two lists line up against the same sequence.

    `changed` is whether the two reads' own raw base calls literally
    differed at this position -- True whenever there was something to
    reconcile at all, regardless of how it was resolved; False for a
    plain agreement. `method` is the punch-list ask's "and why":
    "agreement" (the reads agreed outright), "ambiguity_consistency"
    (one read's IUPAC ambiguity code was consistent with the other's
    definite call, or two ambiguity codes narrowed to one base between
    them), or "quality_tiebreak" (a genuine conflict, decided by which
    read reported the higher Phred quality) -- CLAUDE.md's own three
    consensus rules, named directly. See app.pipeline.consensus's module
    docstring and resolve_base for exactly how each is decided.
    """

    position: int
    forward_base: str
    forward_quality: int
    reverse_base: str
    reverse_quality: int
    resolved_base: str
    resolved_quality: int
    changed: bool
    method: str


class ConsensusResult(BaseModel):
    consensus_sequence: str
    consensus_length: int
    ambiguous_positions: List[int]
    quality_scores: List[int]
    resolved_positions: List[ResolvedPosition] = []
