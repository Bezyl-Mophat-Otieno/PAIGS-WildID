"""Stage 3 -- Coarse Sanity Check.

A deliberately lenient hard stop: catches genuinely broken reads (near-total
N, absurdly short), not the normal noisy edges every raw Sanger read has.
The real accept/reject decision happens later, in Stage 7 (Usability Check),
after trimming/orientation/consensus have had a chance to clean things up.

Threshold values below are sensible starting defaults, pending real domain
review, per CLAUDE.md's Configuration model -- there is no Configuration
subsystem yet, so callers (eventually: run orchestration, sourcing an
analyst's per-run override or the global default from that subsystem) can
override either threshold as a keyword argument.
"""
from typing import Dict

import numpy as np

from app.schemas.ab1_extraction import ReadExtraction
from app.schemas.sanity_check import SanityCheckResult

# Pending real domain review (CLAUDE.md, Configuration model).
DEFAULT_MAX_N_PROPORTION = 0.5
DEFAULT_MIN_RAW_LENGTH = 20


def check_sanity(
    extraction: ReadExtraction,
    *,
    max_n_proportion: float = DEFAULT_MAX_N_PROPORTION,
    min_raw_length: int = DEFAULT_MIN_RAW_LENGTH,
) -> SanityCheckResult:
    bases = np.frombuffer(extraction.raw_sequence.upper().encode("ascii"), dtype="S1")
    n_count = int(np.count_nonzero(bases == b"N")) if bases.size else 0
    n_proportion = (n_count / extraction.raw_length) if extraction.raw_length else 1.0

    failures = []
    if n_proportion > max_n_proportion:
        failures.append(
            f"{n_proportion:.0%} of bases are N, above the {max_n_proportion:.0%} limit."
        )
    if extraction.raw_length < min_raw_length:
        failures.append(
            f"Raw read length {extraction.raw_length} is below the minimum of {min_raw_length}."
        )

    return SanityCheckResult(
        n_proportion=n_proportion,
        raw_length=extraction.raw_length,
        status="FAIL" if failures else "PASS",
        reason=" ".join(failures) if failures else None,
    )


def check_sanity_for_files(
    extractions: Dict[str, ReadExtraction],
    *,
    max_n_proportion: float = DEFAULT_MAX_N_PROPORTION,
    min_raw_length: int = DEFAULT_MIN_RAW_LENGTH,
) -> Dict[str, SanityCheckResult]:
    return {
        slot: check_sanity(
            extraction,
            max_n_proportion=max_n_proportion,
            min_raw_length=min_raw_length,
        )
        for slot, extraction in extractions.items()
    }
