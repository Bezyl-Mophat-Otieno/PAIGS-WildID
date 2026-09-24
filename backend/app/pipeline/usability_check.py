"""Stage 7 -- Usability Check.

The real accept/reject gate, distinct from Stage 3's lenient pre-trim
floor: runs on whatever actually survived cleanup -- Stage 6's consensus
sequence (two-read path) or Stage 4's single trimmed read (single-read
path, whether that's because only one file was uploaded or the other
failed Stage 3) -- and asks "is this good enough to trust for a search,"
not "was the raw input catastrophically bad."

Three rules per CLAUDE.md: minimum length of the surviving sequence,
minimum mean quality of the surviving sequence, maximum unresolved
ambiguous positions tolerated (two-read path only -- naturally a no-op on
the single-read path, since there's no consensus-merge ambiguity concept
there; it's always evaluated as 0 ambiguous positions).

Defaults (min_length=500, min_mean_quality=25, max_ambiguous_proportion=
0.02) are the values researched and cited in
claude/configuration-defaults.md: 500bp / <2% ambiguous bases from the
FDA's Single-Laboratory-Validated fish DNA-barcoding method; Q25 reasoned
as a middle point between Stage 4's Q20 trim floor and the commonly-cited
Q30 "preferred" convention. max_ambiguous_proportion is evaluated as a
proportion of final_length, not a fixed count, per that doc's own note.
"""
from typing import List

from app.schemas.consensus import ConsensusResult
from app.schemas.trim import TrimResult
from app.schemas.usability_check import UsabilityCheckResult

DEFAULT_MIN_LENGTH = 500
DEFAULT_MIN_MEAN_QUALITY = 25.0
DEFAULT_MAX_AMBIGUOUS_PROPORTION = 0.02


def check_usability(
    sequence: str,
    quality_scores: List[int],
    ambiguous_positions: List[int],
    *,
    min_length: int = DEFAULT_MIN_LENGTH,
    min_mean_quality: float = DEFAULT_MIN_MEAN_QUALITY,
    max_ambiguous_proportion: float = DEFAULT_MAX_AMBIGUOUS_PROPORTION,
) -> UsabilityCheckResult:
    final_length = len(sequence)
    mean_quality = (sum(quality_scores) / len(quality_scores)) if quality_scores else 0.0
    ambiguous_count = len(ambiguous_positions)
    ambiguous_proportion = (ambiguous_count / final_length) if final_length else 1.0

    failures = []
    if final_length < min_length:
        failures.append(
            f"Final length {final_length} is below the minimum of {min_length}."
        )
    if mean_quality < min_mean_quality:
        failures.append(
            f"Mean quality {mean_quality:.1f} is below the minimum of {min_mean_quality}."
        )
    if ambiguous_proportion > max_ambiguous_proportion:
        failures.append(
            f"{ambiguous_proportion:.1%} of positions are unresolved ambiguous calls, "
            f"above the {max_ambiguous_proportion:.0%} limit."
        )

    return UsabilityCheckResult(
        final_length=final_length,
        mean_quality=mean_quality,
        ambiguous_positions=ambiguous_count,
        status="FAIL" if failures else "PASS",
        reason=" ".join(failures) if failures else None,
    )


def check_usability_from_consensus(
    consensus: ConsensusResult,
    *,
    min_length: int = DEFAULT_MIN_LENGTH,
    min_mean_quality: float = DEFAULT_MIN_MEAN_QUALITY,
    max_ambiguous_proportion: float = DEFAULT_MAX_AMBIGUOUS_PROPORTION,
) -> UsabilityCheckResult:
    """Two-read path: Stage 6's consensus sequence is the surviving sequence."""
    return check_usability(
        consensus.consensus_sequence,
        consensus.quality_scores,
        consensus.ambiguous_positions,
        min_length=min_length,
        min_mean_quality=min_mean_quality,
        max_ambiguous_proportion=max_ambiguous_proportion,
    )


def check_usability_from_single_read(
    trim: TrimResult,
    trimmed_quality_scores: List[int],
    *,
    min_length: int = DEFAULT_MIN_LENGTH,
    min_mean_quality: float = DEFAULT_MIN_MEAN_QUALITY,
    max_ambiguous_proportion: float = DEFAULT_MAX_AMBIGUOUS_PROPORTION,
) -> UsabilityCheckResult:
    """Single-read path: Stage 4's trimmed read is the surviving sequence, paired
    with its own sliced quality scores (extraction.quality_scores[trim.trim_start:
    trim.trim_end]) since Stage 4's TrimResult doesn't carry quality itself.
    No consensus-merge ambiguity concept applies here, so ambiguous_positions is
    always empty -- the check still runs, it's just a no-op on that rule.
    """
    return check_usability(
        trim.trimmed_sequence,
        trimmed_quality_scores,
        [],
        min_length=min_length,
        min_mean_quality=min_mean_quality,
        max_ambiguous_proportion=max_ambiguous_proportion,
    )
