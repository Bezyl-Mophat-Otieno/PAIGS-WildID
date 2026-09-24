"""Stage 5 -- Orientation Detection.

Only meaningful when two reads survived Trimming. A forward and reverse
read cover the same physical DNA fragment from opposite ends, opposite
strands -- so before they can be compared, the system needs to know which
orientation each is actually in.

Per CLAUDE.md: attempt a pairwise alignment of the two trimmed reads
as-is, and separately with one reverse-complemented; whichever attempt
produces a strong overlap reveals the correct orientation -- a
deterministic check, not a guess. This is independent of which upload
slot ("forward"/"reverse") each file was placed in: if the labels turn
out to disagree with what's actually detected, that's
label_orientation_mismatch, an informational note that never blocks the
run.

Concretely, exactly two attempts are made, always transforming the
"reverse" read (never "forward"):
  - "as_is": forward vs reverse, unchanged.
  - "reverse_read_reverse_complemented": forward vs revcomp(reverse).
Normal biology (both files correctly labeled) makes the second attempt
win -- a forward read and the reverse-complement of a true reverse read
should overlap directly on the same strand. If the *first* attempt wins
instead, that means the "reverse" slot's file was, in fact, already in
forward orientation (or vice versa) -- the labels don't match what was
actually detected, hence the mismatch flag. If neither attempt clears
the "usable overlap" bar, the run flags for review rather than guessing
-- most often means the two files aren't actually a matching pair.

Tool: Biopython's Bio.Align.PairwiseAligner (local mode) -- sufficient for
short Sanger reads, per CLAUDE.md's own tooling note.

The "usable overlap" bar (min_overlap_length, min_identity) isn't one of
the four threshold sets CLAUDE.md's Configuration model section names by
stage (3/4/7/10), and Stage 5's own section has no "Rules to configure"
callout the way those four do -- it reads more like an algorithm-tuning
parameter (did the alignment find a real signal) than a biological QC
judgment call. Kept as keyword overrides regardless, and -- at the user's
request, so a lab can tune this too if a marker or read length needs a
different bar -- now documented and sourced (reasoned, no external
citation applies) in claude/configuration-defaults.md alongside the
others.
"""
from typing import List, Tuple

from Bio.Seq import Seq

from app.pipeline._alignment import build_pairwise_aligner
from app.schemas.orientation import OrientationResult

DEFAULT_MIN_OVERLAP_LENGTH = 20
DEFAULT_MIN_IDENTITY = 0.9


def _score_alignment(target: str, query: str) -> Tuple[float, int, float, list]:
    """Runs one local alignment attempt; returns (score, overlap_length,
    identity, aligned_blocks). identity is computed by directly comparing
    the aligned characters in each block (not inferred from the scoring
    scheme), so it's meaningful regardless of match/mismatch weights.
    """
    alignments = build_pairwise_aligner().align(target, query)
    best = alignments[0]
    target_blocks, query_blocks = best.aligned

    if len(target_blocks) == 0:
        return best.score, 0, 0.0, []

    overlap_length = sum(t_end - t_start for t_start, t_end in target_blocks)
    matches = 0
    for (t_start, t_end), (q_start, q_end) in zip(target_blocks, query_blocks):
        t_segment = target[t_start:t_end]
        q_segment = query[q_start:q_end]
        matches += sum(1 for a, b in zip(t_segment, q_segment) if a == b)
    identity = matches / overlap_length if overlap_length else 0.0

    return best.score, overlap_length, identity, list(zip(target_blocks, query_blocks))


def detect_orientation(
    forward_sequence: str,
    reverse_sequence: str,
    *,
    min_overlap_length: int = DEFAULT_MIN_OVERLAP_LENGTH,
    min_identity: float = DEFAULT_MIN_IDENTITY,
) -> OrientationResult:
    as_is_score, as_is_len, as_is_identity, _ = _score_alignment(forward_sequence, reverse_sequence)
    reverse_rc = str(Seq(reverse_sequence).reverse_complement())
    rc_score, rc_len, rc_identity, _ = _score_alignment(forward_sequence, reverse_rc)

    def _qualifies(length: int, identity: float) -> bool:
        return length >= min_overlap_length and identity >= min_identity

    as_is_ok = _qualifies(as_is_len, as_is_identity)
    rc_ok = _qualifies(rc_len, rc_identity)

    if not as_is_ok and not rc_ok:
        return OrientationResult(orientation="no_overlap_found")

    if as_is_ok and rc_ok:
        # Both attempts happen to clear the bar (e.g. a repetitive/
        # palindromic region) -- prefer whichever aligned more bases with
        # higher confidence, a reasoned tie-break rather than an
        # arbitrary pick.
        as_is_wins = (as_is_len, as_is_score) >= (rc_len, rc_score)
    else:
        as_is_wins = as_is_ok

    if as_is_wins:
        return OrientationResult(
            orientation="as_is",
            alignment_score=as_is_score,
            overlap_length=as_is_len,
            identity=as_is_identity,
            label_orientation_mismatch=True,
        )
    return OrientationResult(
        orientation="reverse_read_reverse_complemented",
        alignment_score=rc_score,
        overlap_length=rc_len,
        identity=rc_identity,
        label_orientation_mismatch=False,
    )
