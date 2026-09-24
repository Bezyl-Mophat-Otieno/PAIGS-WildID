"""
The full catalog of configurable pipeline thresholds -- the single source
of truth for what CLAUDE.md's Configuration model calls "a config table
with sensible starting defaults (pending real domain review)."

Every default value below is imported directly from its own pipeline
module's DEFAULT_* constant (never retyped here), so this catalog can
never drift out of sync with what each stage function actually falls
back to when called with no explicit threshold. See
claude/configuration-defaults.md for the full research/citations behind
each default value and each label/description below.

CLAUDE.md's own Configuration model section names four stages explicitly
by number (3, 4, 7, 10); Stage 5's orientation-overlap bar and Stage 9's
max_hits were added on the user's explicit request during that doc's
review, on the same "a deliberate choice, not silent inheritance"
reasoning -- see that doc's own per-stage notes. All 13 thresholds across
6 stages are catalogued here as one flat list, keyed
"<stage_type>.<param_name>" -- that key is what a per-run
config_overrides dict (POST /runs, POST /runs/{id}/rerun) and PUT
/config/{id} both address, and it's exactly the kwarg name each stage's
own pipeline function accepts (via app.configuration.service.kwargs_for_stage).
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from app.pipeline.blast import DEFAULT_MAX_HITS
from app.pipeline.identification import (
    DEFAULT_AMBIGUOUS_MARGIN_PCT,
    DEFAULT_MIN_COVERAGE_PCT,
    DEFAULT_MIN_IDENTITY_PCT,
)
from app.pipeline.orientation import DEFAULT_MIN_IDENTITY, DEFAULT_MIN_OVERLAP_LENGTH
from app.pipeline.sanity_check import DEFAULT_MAX_N_PROPORTION, DEFAULT_MIN_RAW_LENGTH
from app.pipeline.trim import DEFAULT_MIN_WINDOW_SIZE, DEFAULT_QUALITY_THRESHOLD
from app.pipeline.usability_check import (
    DEFAULT_MAX_AMBIGUOUS_PROPORTION,
    DEFAULT_MIN_LENGTH,
    DEFAULT_MIN_MEAN_QUALITY,
)


@dataclass(frozen=True)
class ThresholdDefinition:
    key: str  # "<stage_type>.<param_name>" -- stable identifier used everywhere
    stage_type: str
    param_name: str  # exact kwarg name the pipeline function accepts
    label: str
    description: str
    default: float
    value_type: str  # "int" | "float" -- how to cast a stored/override value back
    bounds: Tuple[Optional[float], Optional[float]]  # (low, high); either may be None


def _entry(stage_type, param_name, default, label, description, bounds):
    value_type = "int" if isinstance(default, int) else "float"
    return ThresholdDefinition(
        key=f"{stage_type}.{param_name}",
        stage_type=stage_type,
        param_name=param_name,
        label=label,
        description=description,
        default=float(default),
        value_type=value_type,
        bounds=bounds,
    )


CATALOG = [
    _entry(
        "sanity_check", "max_n_proportion", DEFAULT_MAX_N_PROPORTION,
        "Max N-proportion tolerated",
        "Stage 3 (Coarse Sanity Check): a read whose proportion of N "
        "(unresolved) bases exceeds this is treated as containing no real "
        "signal. Deliberately lenient -- catches only genuinely broken "
        "reads, not normal noisy edges (the real accept/reject gate is "
        "Stage 7's max_ambiguous_proportion).",
        (0.0, 1.0),
    ),
    _entry(
        "sanity_check", "min_raw_length", DEFAULT_MIN_RAW_LENGTH,
        "Min raw length (bp)",
        "Stage 3: an absurdly-low floor below which a read is essentially "
        "content-free, regardless of quality. Not a real usability bar -- "
        "see Stage 7's own min_length for that.",
        (0, None),
    ),
    _entry(
        "trim", "quality_threshold", DEFAULT_QUALITY_THRESHOLD,
        "Trim quality threshold (Phred)",
        "Stage 4 (Trimming): the per-base Phred score below which a base "
        "is considered unreliable when finding each read's trustworthy "
        "window. Q20 is the standard Sanger-sequencing minimum-acceptable "
        "convention.",
        (0, None),
    ),
    _entry(
        "trim", "min_window_size", DEFAULT_MIN_WINDOW_SIZE,
        "Min trim window size (bp)",
        "Stage 4: below this, a read's reliable window is treated as "
        "nothing worth keeping at all.",
        (0, None),
    ),
    _entry(
        "orientation", "min_overlap_length", DEFAULT_MIN_OVERLAP_LENGTH,
        "Min overlap length (bp)",
        "Stage 5 (Orientation Detection): the shortest forward/reverse "
        "alignment overlap treated as a real signal rather than a chance "
        "collision.",
        (0, None),
    ),
    _entry(
        "orientation", "min_identity", DEFAULT_MIN_IDENTITY,
        "Min overlap identity",
        "Stage 5: the minimum fraction of matching bases within the "
        "overlap region for it to count as a genuine forward/reverse pair "
        "rather than a spurious partial match.",
        (0.0, 1.0),
    ),
    _entry(
        "usability_check", "min_length", DEFAULT_MIN_LENGTH,
        "Min final length (bp)",
        "Stage 7 (Usability Check), the real accept/reject gate: minimum "
        "length of the cleaned-up sequence (consensus or single trimmed "
        "read) for it to be considered trustworthy enough to search. "
        "500bp matches the standard full-length COI barcode convention "
        "and the FDA SLV fish-barcoding protocol's own floor.",
        (0, None),
    ),
    _entry(
        "usability_check", "min_mean_quality", DEFAULT_MIN_MEAN_QUALITY,
        "Min mean quality (Phred)",
        "Stage 7: minimum mean Phred score across the final sequence, set "
        "above Stage 4's own Q20 trim bar since everything reaching here "
        "already cleared that.",
        (0, None),
    ),
    _entry(
        "usability_check", "max_ambiguous_proportion", DEFAULT_MAX_AMBIGUOUS_PROPORTION,
        "Max ambiguous proportion",
        "Stage 7: maximum proportion of unresolved ambiguous positions "
        "allowed in the final sequence (two-read/consensus path only). "
        "Directly from the FDA SLV protocol's '<2% ambiguous bases' "
        "cutoff.",
        (0.0, 1.0),
    ),
    _entry(
        "blast", "max_hits", DEFAULT_MAX_HITS,
        "Max BLAST hits returned",
        "Stage 9 (BLAST comparison): how many ranked candidate hits Stage "
        "10 gets to evaluate (and an analyst ultimately sees in the "
        "report). An engineering judgment call, not a biological "
        "threshold -- worth revisiting once the real reference database's "
        "size/diversity is known.",
        (1, None),
    ),
    _entry(
        "identification", "min_identity_pct", DEFAULT_MIN_IDENTITY_PCT,
        "Min identity % (PASS)",
        "Stage 10 (Identification): minimum top-hit identity percent "
        "required for a PASS. 98% matches the FDA SLV protocol's "
        "generalized 2%-divergence cutoff for species delimitation via "
        "COI.",
        (0.0, 100.0),
    ),
    _entry(
        "identification", "min_coverage_pct", DEFAULT_MIN_COVERAGE_PCT,
        "Min coverage % (PASS)",
        "Stage 10: minimum percent of the query sequence actually "
        "included in the alignment, required alongside identity so a "
        "short, high-identity alignment can't pass on its own.",
        (0.0, 100.0),
    ),
    _entry(
        "identification", "ambiguous_margin_pct", DEFAULT_AMBIGUOUS_MARGIN_PCT,
        "Ambiguous margin (identity points)",
        "Stage 10: how many identity points the top hit must lead the "
        "runner-up by to be called clear, rather than AMBIGUOUS -- "
        "CLAUDE.md's own 'no other candidate is close' language, "
        "translated into a number.",
        (0.0, 100.0),
    ),
]

CATALOG_BY_KEY = {definition.key: definition for definition in CATALOG}
