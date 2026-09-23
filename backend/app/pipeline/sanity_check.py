"""Stage 3 -- Coarse Sanity Check.

A deliberately lenient hard stop: catches genuinely broken reads (near-total
N, absurdly short), not the normal noisy edges every raw Sanger read has.
The real accept/reject decision happens later, in Stage 7 (Usability Check),
after trimming/orientation/consensus have had a chance to clean things up.

Threshold values below are informed starting defaults, pending real domain
review, per CLAUDE.md's Configuration model ("Rules to configure (with
domain experts, not guessed)"). There is no Configuration subsystem yet
(its config table + GET/PUT /config endpoints are tied to Run/Stage
orchestration, build-order step 9), so callers can override either
threshold as a keyword argument today, and will source it from that
subsystem's global default or a per-run override once it exists.

Sourcing for the specific numbers below -- and for Stage 4/7/10's, ahead of
building those stages -- is written up in full, with citations, in the
PAIGS project doc `claude/configuration-defaults.md`. Short version: this
particular check (raw, *pre-trim* signal/length) has no external industry
standard to cite -- it is unique to this pipeline's two-tier QC design
(coarse pre-trim floor here, the real literature-grounded gate at Stage 7)
-- so these two values are reasoned defaults, not sourced ones:
- max_n_proportion=0.5: CLAUDE.md's own framing is "not almost entirely N";
  0.5 is a literal reading of that ("almost entirely" implies well above
  half), lenient enough that ordinary noisy-edge N's from ends that haven't
  been trimmed yet never trip it.
- min_raw_length=50: an "absurdly-low floor" per CLAUDE.md -- our own real
  fixtures run 795-1165bp raw, and a good Sanger read is typically
  hundreds of bp, so 50bp is well below anything Stage 4's trimming could
  turn into a usable window; it exists only to catch reads that are
  structurally valid AB1 (passed Stage 1) but essentially content-free.
"""
from typing import Dict

import numpy as np

from app.schemas.ab1_extraction import ReadExtraction
from app.schemas.sanity_check import SanityCheckResult

# Informed defaults, pending real domain review -- see module docstring and
# claude/configuration-defaults.md for sourcing.
DEFAULT_MAX_N_PROPORTION = 0.5
DEFAULT_MIN_RAW_LENGTH = 50


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
