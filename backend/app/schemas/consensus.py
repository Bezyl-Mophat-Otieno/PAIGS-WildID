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
    plain agreement or a gap position (there's only one read's call to
    begin with, so nothing to differ from). `method` is the punch-list
    ask's "and why": "agreement" (the reads agreed outright),
    "ambiguity_consistency" (one read's IUPAC ambiguity code was
    consistent with the other's definite call, or two ambiguity codes
    narrowed to one base between them), "quality_tiebreak" (a genuine
    conflict, decided by which read reported the higher Phred quality) --
    CLAUDE.md's own three consensus rules, named directly -- or
    "gap_single_read" (this position falls in a real gap between aligned
    blocks, i.e. an indel: only one read has a base here at all, so
    there's nothing to reconcile -- that read's own call is used as-is).
    See app.pipeline.consensus's module docstring and resolve_base for
    exactly how each is decided.

    `forward_base`/`forward_quality`/`reverse_base`/`reverse_quality` are
    None on whichever side has no base at a "gap_single_read" position --
    the one case where a read genuinely has nothing to say at this
    position, rather than an unknown/placeholder value.
    """

    position: int
    forward_base: Optional[str] = None
    forward_quality: Optional[int] = None
    reverse_base: Optional[str] = None
    reverse_quality: Optional[int] = None
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
