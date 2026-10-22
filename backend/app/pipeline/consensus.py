"""Stage 6 -- Consensus Building.

With both reads in the same orientation (per Stage 5's decision), aligns
them position by position and builds one merged sequence, picking the
more trustworthy base at each spot. Per CLAUDE.md:

- Both reads agree -> keep it.
- They disagree -> compare Phred quality scores at that position, keep
  the more confident one.
- One read gives a confident, definite base and the other an IUPAC
  ambiguity code consistent with it -> the definite base wins.
- Both confident but genuinely disagree -> flagged as an ambiguous
  position, never silently resolved.

Reading the middle two bullets as one rule (see `resolve_base`): when two
definite calls disagree and their qualities differ, the higher one wins;
when the qualities are exactly equal, there is no basis to call either
"more confident", so that's the ambiguous case CLAUDE.md's last bullet
describes.

Tool: built on the same Bio.Align alignment approach as Stage 5 (shared
config in app/pipeline/_alignment.py) plus a small IUPAC ambiguity-code
lookup table, per CLAUDE.md's own tooling note.

Gaps within the overlap (a real indel between the two reads -- most
often a homopolymer run miscalled a base or two different in length by
each read, a well-known Sanger artifact): the overlap alignment can come
back as more than one ungapped block, with a gap on one side between
consecutive blocks. Each block is merged exactly like a single-block
overlap always was (the same resolve_base() rules, unchanged); a gap
between two blocks has only one read with real bases there at all, so
there's nothing to reconcile -- that read's own call and quality are
used as-is, recorded with method="gap_single_read" (not "ambiguous":
there's no disagreement, just a position only one read can speak to).
`max_gap_length` bounds how large a single gap is trusted as routine
sequencing noise versus treated as evidence these reads may not be a
genuine single-fragment overlap at all -- `build_consensus` raises a
clear error rather than silently stitching together two reads across a
gap that large. A gap appearing on *both* sides between the same two
blocks (not a single-sided indel at all) also raises -- genuinely not
supported, rather than guessing which side to trust.

Per-position quality, carried forward alongside the merged base (added
because Stage 7's "minimum mean quality of the surviving sequence" rule
can't be computed on the two-read path without it -- the original
two-value resolve_base and quality-less ConsensusResult genuinely
couldn't support that): whenever the resolved base traces back to one
specific read's own definite call (a clean quality-based win, or that
call surviving an ambiguity-consistency/intersection check), that read's
own quality is used. In every other case -- outright agreement, a tie, or
a fallback to ambiguous -- max(quality_a, quality_b) is used as the best
evidence bound available, never inventing confidence beyond what either
read actually reported.

`resolve_base` also names *how* it resolved each position (its 4th
return value, `method`) and `build_consensus` records one
ResolvedPosition per resolved overlap position -- the complement of
ambiguous_positions, and the direct answer to "extend the Consensus
stage to record every resolved position, not just the unresolved ones
... to show an analyst 'here's what changed and why'". `method` is one
of this module's three per-position comparison rules (agreement,
ambiguity-consistency, quality-tiebreak), or "gap_single_read" for a
position inside a gap between aligned blocks, decided by the simpler
rule above (no comparison possible -- only one read has a call there).
"""
from typing import Dict, FrozenSet, List, Optional, Tuple

from app.pipeline._alignment import build_pairwise_aligner
from app.schemas.consensus import ConsensusResult, ResolvedPosition
from app.schemas.orientation import OrientationResult

IUPAC_TO_BASES: Dict[str, FrozenSet[str]] = {
    "A": frozenset("A"), "C": frozenset("C"), "G": frozenset("G"), "T": frozenset("T"),
    "R": frozenset("AG"), "Y": frozenset("CT"), "S": frozenset("GC"), "W": frozenset("AT"),
    "K": frozenset("GT"), "M": frozenset("AC"),
    "B": frozenset("CGT"), "D": frozenset("AGT"), "H": frozenset("ACT"), "V": frozenset("ACG"),
    "N": frozenset("ACGT"),
}
BASES_TO_IUPAC: Dict[FrozenSet[str], str] = {bases: code for code, bases in IUPAC_TO_BASES.items()}


def resolve_base(
    base_a: str, quality_a: int, base_b: str, quality_b: int
) -> Tuple[str, int, bool, Optional[str]]:
    """Decides the consensus call at one position. Returns (resolved_base,
    quality, is_ambiguous, method). `resolved_base` is a definite base
    (A/C/G/T) whenever the call could be made with confidence, or an
    IUPAC ambiguity code (possibly N) when it genuinely couldn't.
    `quality` is that read's own quality when the resolved base traces
    back to one specific read's definite call, else
    max(quality_a, quality_b) -- see module docstring. `method` is
    "agreement" | "ambiguity_consistency" | "quality_tiebreak" when
    `is_ambiguous` is False, else None (nothing was actually resolved, so
    no method applies).

    Built around set intersection, which generalizes CLAUDE.md's explicit
    rules cleanly: two definite calls agreeing, and a definite call
    consistent with the other's ambiguity code, are both just special
    cases of "the set of bases consistent with both reads has exactly one
    member" -- so is any other combination (including two overlapping
    ambiguity codes) that happens to narrow down to one base.
    """
    a, b = base_a.upper(), base_b.upper()
    a_options = IUPAC_TO_BASES.get(a, frozenset(a))
    b_options = IUPAC_TO_BASES.get(b, frozenset(b))
    a_definite = len(a_options) == 1
    b_definite = len(b_options) == 1
    best_evidence = max(quality_a, quality_b)

    intersection = a_options & b_options
    if len(intersection) == 1:
        resolved = next(iter(intersection))
        if a_definite and b_definite:
            # Only possible when a == b: two distinct single-base sets
            # never intersect.
            return resolved, quality_a, False, "agreement"
        if a_definite and resolved == a:
            return resolved, quality_a, False, "ambiguity_consistency"
        if b_definite and resolved == b:
            return resolved, quality_b, False, "ambiguity_consistency"
        # Both sides are themselves ambiguity codes, but happen to narrow
        # to exactly one base together (e.g. R={A,G} + M={A,C} -> A).
        return resolved, best_evidence, False, "ambiguity_consistency"
    if intersection:
        # Narrowed but still not a single base (e.g. two overlapping,
        # non-singleton ambiguity codes) -- genuinely still ambiguous.
        return BASES_TO_IUPAC.get(intersection, "N"), best_evidence, True, None

    # No base is consistent with both calls at all -- a genuine conflict.
    if a_definite and b_definite:
        if quality_a > quality_b:
            return a, quality_a, False, "quality_tiebreak"
        if quality_b > quality_a:
            return b, quality_b, False, "quality_tiebreak"
        return BASES_TO_IUPAC.get(a_options | b_options, "N"), quality_a, True, None

    if a_definite and not b_definite:
        if quality_a > quality_b:
            return a, quality_a, False, "quality_tiebreak"
        return BASES_TO_IUPAC.get(a_options | b_options, "N"), best_evidence, True, None
    if b_definite and not a_definite:
        if quality_b > quality_a:
            return b, quality_b, False, "quality_tiebreak"
        return BASES_TO_IUPAC.get(a_options | b_options, "N"), best_evidence, True, None

    # Both ambiguous, no overlap at all -- no quality-based tiebreak makes
    # sense between two inherently multi-valued calls.
    return BASES_TO_IUPAC.get(a_options | b_options, "N"), best_evidence, True, None


def _oriented_reverse(
    reverse_sequence: str, reverse_quality: List[int], orientation: OrientationResult
) -> Tuple[str, List[int]]:
    if orientation.orientation == "no_overlap_found":
        raise ValueError(
            "Cannot build a consensus: Stage 5 found no usable overlap between the reads."
        )
    if orientation.orientation == "reverse_read_reverse_complemented":
        complement = {"A": "T", "T": "A", "G": "C", "C": "G", "N": "N"}
        rc_sequence = "".join(complement.get(b, "N") for b in reversed(reverse_sequence.upper()))
        return rc_sequence, list(reversed(reverse_quality))
    if orientation.orientation == "as_is":
        return reverse_sequence, reverse_quality
    raise ValueError(f"Unrecognized orientation value: {orientation.orientation!r}")


# Pending real domain review, same status as every other threshold in
# this app. A real Sanger homopolymer miscall is almost always off by
# just 1-2 bases; this leaves some headroom while still refusing a gap
# large enough to suggest the two reads aren't a genuine single-fragment
# overlap at all (see module docstring).
DEFAULT_MAX_GAP_LENGTH = 5


def _merge_block(
    forward_sequence: str,
    forward_quality: List[int],
    oriented_reverse_sequence: str,
    oriented_reverse_quality: List[int],
    t_start: int,
    q_start: int,
    length: int,
    offset: int,
    merged_overlap: List[str],
    merged_overlap_quality: List[int],
    ambiguous_offsets: List[int],
    resolved_offsets: List[ResolvedPosition],
) -> int:
    """Merges one ungapped aligned block via resolve_base()'s own
    per-position rules, exactly as the single-block case always has.
    Returns the next offset (this module's running position within the
    merged overlap, before the final prefix-length shift)."""
    for i in range(length):
        fwd_base = forward_sequence[t_start + i]
        fwd_quality = forward_quality[t_start + i]
        rev_base = oriented_reverse_sequence[q_start + i]
        rev_quality = oriented_reverse_quality[q_start + i]
        base, quality, is_ambiguous, method = resolve_base(
            fwd_base, fwd_quality, rev_base, rev_quality
        )
        merged_overlap.append(base)
        merged_overlap_quality.append(quality)
        if is_ambiguous:
            ambiguous_offsets.append(offset)
        else:
            resolved_offsets.append(
                ResolvedPosition(
                    position=offset,  # shifted to an absolute position below
                    forward_base=fwd_base,
                    forward_quality=fwd_quality,
                    reverse_base=rev_base,
                    reverse_quality=rev_quality,
                    resolved_base=base,
                    resolved_quality=quality,
                    changed=fwd_base.upper() != rev_base.upper(),
                    method=method,
                )
            )
        offset += 1
    return offset


def _merge_gap(
    side: str,
    sequence: str,
    quality: List[int],
    start: int,
    length: int,
    offset: int,
    merged_overlap: List[str],
    merged_overlap_quality: List[int],
    resolved_offsets: List[ResolvedPosition],
) -> int:
    """Fills a gap between two aligned blocks -- only `side` has a real
    base here, so there's nothing to reconcile; that read's own call and
    quality are used as-is. Never ambiguous (no disagreement exists)."""
    for i in range(length):
        base = sequence[start + i]
        base_quality = quality[start + i]
        merged_overlap.append(base)
        merged_overlap_quality.append(base_quality)
        resolved_offsets.append(
            ResolvedPosition(
                position=offset,
                forward_base=base if side == "forward" else None,
                forward_quality=base_quality if side == "forward" else None,
                reverse_base=base if side == "reverse" else None,
                reverse_quality=base_quality if side == "reverse" else None,
                resolved_base=base,
                resolved_quality=base_quality,
                changed=False,
                method="gap_single_read",
            )
        )
        offset += 1
    return offset


def build_consensus(
    forward_sequence: str,
    forward_quality: List[int],
    reverse_sequence: str,
    reverse_quality: List[int],
    orientation: OrientationResult,
    *,
    max_gap_length: int = DEFAULT_MAX_GAP_LENGTH,
) -> ConsensusResult:
    oriented_reverse_sequence, oriented_reverse_quality = _oriented_reverse(
        reverse_sequence, reverse_quality, orientation
    )

    alignment = build_pairwise_aligner().align(forward_sequence, oriented_reverse_sequence)[0]
    target_blocks, query_blocks = alignment.aligned
    if len(target_blocks) == 0:
        raise ValueError("Consensus building found no aligned overlap at all between the reads.")

    merged_overlap: List[str] = []
    merged_overlap_quality: List[int] = []
    ambiguous_offsets: List[int] = []
    resolved_offsets: List[ResolvedPosition] = []
    offset = 0

    for block_index, ((t_start, t_end), (q_start, q_end)) in enumerate(
        zip(target_blocks, query_blocks)
    ):
        offset = _merge_block(
            forward_sequence, forward_quality, oriented_reverse_sequence, oriented_reverse_quality,
            t_start, q_start, t_end - t_start, offset,
            merged_overlap, merged_overlap_quality, ambiguous_offsets, resolved_offsets,
        )

        if block_index + 1 == len(target_blocks):
            break

        next_t_start, _ = target_blocks[block_index + 1]
        next_q_start, _ = query_blocks[block_index + 1]
        forward_gap_length = next_t_start - t_end
        reverse_gap_length = next_q_start - q_end

        if forward_gap_length > 0 and reverse_gap_length > 0:
            # A true single-sided indel never produces a gap on both
            # sides between the same two blocks -- not supported, rather
            # than guessing which side to trust.
            raise ValueError(
                "Consensus building found a gap on both reads between aligned "
                "blocks -- not a simple single-sided indel; not supported in "
                "this MVP."
            )

        gap_length = max(forward_gap_length, reverse_gap_length)
        if gap_length > max_gap_length:
            raise ValueError(
                f"Consensus building found a {gap_length}bp gap between aligned "
                f"blocks, exceeding the configured max_gap_length of "
                f"{max_gap_length}bp -- too large to treat as routine Sanger "
                "sequencing noise."
            )

        if forward_gap_length > 0:
            offset = _merge_gap(
                "forward", forward_sequence, forward_quality, t_end, forward_gap_length,
                offset, merged_overlap, merged_overlap_quality, resolved_offsets,
            )
        elif reverse_gap_length > 0:
            offset = _merge_gap(
                "reverse", oriented_reverse_sequence, oriented_reverse_quality, q_end,
                reverse_gap_length, offset, merged_overlap, merged_overlap_quality, resolved_offsets,
            )
        # else: adjacent blocks with no real gap at all -- shouldn't occur
        # from Biopython's own block-splitting, but a no-op is safe either way.

    first_t_start = target_blocks[0][0]
    last_q_end = query_blocks[-1][1]
    prefix = forward_sequence[:first_t_start]
    suffix = oriented_reverse_sequence[last_q_end:]
    consensus_sequence = prefix + "".join(merged_overlap) + suffix

    prefix_quality = forward_quality[:first_t_start]
    suffix_quality = oriented_reverse_quality[last_q_end:]
    quality_scores = prefix_quality + merged_overlap_quality + suffix_quality

    resolved_positions = [
        resolved.model_copy(update={"position": len(prefix) + resolved.position})
        for resolved in resolved_offsets
    ]

    return ConsensusResult(
        consensus_sequence=consensus_sequence,
        consensus_length=len(consensus_sequence),
        ambiguous_positions=[len(prefix) + i for i in ambiguous_offsets],
        quality_scores=quality_scores,
        resolved_positions=resolved_positions,
    )
