"""Stage 4 -- Trimming.

Sequencers are least reliable at the leading and trailing ends of a read.
This stage runs on each Stage-3-passed read independently -- before the two
reads are ever compared to each other -- and uses the per-base Phred quality
scores to find where the reliable stretch of the read begins and ends,
cutting off everything outside that window.

Algorithm: a Kadane's-maximum-subarray scan over (quality[i] -
quality_threshold) -- the standard "modified Mott" trimming approach used
by tools like phred/phrap and CodonCode Aligner. This needs no new library
(CLAUDE.md: "simple logic over the quality scores already extracted"),
just plain arithmetic over Stage 2's already-extracted quality scores.

Why logged, not applied silently: trimming changes the exact data that
later gets compared against the reference database, so trim_params (and
the exact trim_start/trim_end boundaries) are part of this stage's output,
feeding the audit trail per CLAUDE.md's Stage 4 section.

Threshold defaults (quality_threshold=20, min_window_size=50) are sourced
in the PAIGS project doc `claude/configuration-defaults.md`: Q20 is both
the standard Sanger-QC trimming convention and CLAUDE.md's own illustrative
example; min_window_size=50 mirrors Stage 3's own "absurdly-low floor" for
consistency, pending real domain review, same as Stage 3.
"""
from typing import Dict, Tuple

from app.schemas.ab1_extraction import ReadExtraction
from app.schemas.trim import TrimResult

# Pending real domain review -- see module docstring and
# claude/configuration-defaults.md for sourcing.
DEFAULT_QUALITY_THRESHOLD = 20
DEFAULT_MIN_WINDOW_SIZE = 50


def _best_window(quality_scores) -> Tuple[int, int, int]:
    """Kadane's maximum-subarray scan. Returns (start, end_exclusive, sum).

    Ties are resolved in favor of the earliest-found maximal window (a
    strict `>` comparison never lets a later, equally-good window replace
    an earlier one) so the result is deterministic run to run -- required
    for an audit trail, not just a nicety.
    """
    best_sum = current_sum = quality_scores[0]
    best_start = best_end = current_start = 0

    for i in range(1, len(quality_scores)):
        if current_sum <= 0:
            current_start = i
            current_sum = quality_scores[i]
        else:
            current_sum += quality_scores[i]
        if current_sum > best_sum:
            best_sum = current_sum
            best_start = current_start
            best_end = i

    return best_start, best_end + 1, best_sum


def trim_read(
    extraction: ReadExtraction,
    *,
    quality_threshold: int = DEFAULT_QUALITY_THRESHOLD,
    min_window_size: int = DEFAULT_MIN_WINDOW_SIZE,
) -> TrimResult:
    trim_params = {"quality_threshold": quality_threshold, "min_window_size": min_window_size}

    if not extraction.quality_scores:
        return TrimResult(
            trimmed_sequence="", trimmed_length=0, trim_start=0, trim_end=0, trim_params=trim_params
        )

    transformed = [q - quality_threshold for q in extraction.quality_scores]
    start, end, window_sum = _best_window(transformed)

    if window_sum <= 0 or (end - start) < min_window_size:
        return TrimResult(
            trimmed_sequence="", trimmed_length=0, trim_start=0, trim_end=0, trim_params=trim_params
        )

    return TrimResult(
        trimmed_sequence=extraction.raw_sequence[start:end],
        trimmed_length=end - start,
        trim_start=start,
        trim_end=end,
        trim_params=trim_params,
    )


def trim_reads_for_files(
    extractions: Dict[str, ReadExtraction],
    *,
    quality_threshold: int = DEFAULT_QUALITY_THRESHOLD,
    min_window_size: int = DEFAULT_MIN_WINDOW_SIZE,
) -> Dict[str, TrimResult]:
    return {
        slot: trim_read(
            extraction,
            quality_threshold=quality_threshold,
            min_window_size=min_window_size,
        )
        for slot, extraction in extractions.items()
    }
