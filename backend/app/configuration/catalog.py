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
reasoning -- see that doc's own per-stage notes. All entries across 6
stages are catalogued here as one flat list, keyed
"<stage_type>.<param_name>" -- that key is what a per-run
config_overrides dict (POST /runs, POST /runs/{id}/rerun) and PUT
/config/{id} both address, and it's exactly the kwarg name each stage's
own pipeline function accepts (via app.configuration.service.kwargs_for_stage).

Most entries are numeric ("int"/"float", validated against `bounds`). The
three `blast.mode` / `blast.remote_database` / `blast.entrez_query`
entries are not -- they're the remote-vs-local BLAST search decision (see
claude/remote-blast-search.md): a fixed-choice ("enum", validated against
`choices`) or free-text ("string", unvalidated beyond type) value instead
of a number. `bounds` is meaningless for those two value_types and is
left at its (None, None) default.
"""
from dataclasses import dataclass
from typing import Any, Optional, Tuple

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
    default: Any  # float for "int"/"float"; str for "enum"/"string"
    value_type: str  # "int" | "float" | "enum" | "string"
    bounds: Tuple[Optional[float], Optional[float]] = (None, None)  # numeric only
    choices: Optional[Tuple[str, ...]] = None  # "enum" only -- the allowed values


def _entry(stage_type, param_name, default, label, description, bounds=(None, None), *, choices=None):
    if isinstance(default, str):
        value_type = "enum" if choices else "string"
        stored_default = default
    else:
        value_type = "int" if isinstance(default, int) else "float"
        stored_default = float(default)
    return ThresholdDefinition(
        key=f"{stage_type}.{param_name}",
        stage_type=stage_type,
        param_name=param_name,
        label=label,
        description=description,
        default=stored_default,
        value_type=value_type,
        bounds=bounds,
        choices=tuple(choices) if choices else None,
    )


CATALOG = [
    _entry(
        "sanity_check", "max_n_proportion", DEFAULT_MAX_N_PROPORTION,
        "Max N-proportion tolerated",
        "Reads with more N calls than this fraction are rejected outright "
        "as unreadable. A coarse filter only -- overall sequence quality "
        "is enforced later, at the usability check.",
        (0.0, 1.0),
    ),
    _entry(
        "sanity_check", "min_raw_length", DEFAULT_MIN_RAW_LENGTH,
        "Min raw length (bp)",
        "Reads shorter than this are rejected as too short to contain any "
        "usable sequence. A coarse floor, not the real length "
        "requirement -- that's set separately at the usability check.",
        (0, None),
    ),
    _entry(
        "trim", "quality_threshold", DEFAULT_QUALITY_THRESHOLD,
        "Trim quality threshold (Phred)",
        "Per-base Phred score below which a base is treated as unreliable "
        "when locating each read's trustworthy window. Q20 is the "
        "standard minimum for Sanger sequencing.",
        (0, None),
    ),
    _entry(
        "trim", "min_window_size", DEFAULT_MIN_WINDOW_SIZE,
        "Min trim window size (bp)",
        "If the reliable window found during trimming is shorter than "
        "this, the read is discarded -- there's nothing worth keeping.",
        (0, None),
    ),
    _entry(
        "orientation", "min_overlap_length", DEFAULT_MIN_OVERLAP_LENGTH,
        "Min overlap length (bp)",
        "Shortest forward/reverse overlap that counts as a genuine "
        "alignment rather than a chance match.",
        (0, None),
    ),
    _entry(
        "orientation", "min_identity", DEFAULT_MIN_IDENTITY,
        "Min overlap identity",
        "Minimum fraction of matching bases within the overlap for the "
        "two reads to be accepted as a genuine forward/reverse pair.",
        (0.0, 1.0),
    ),
    _entry(
        "usability_check", "min_length", DEFAULT_MIN_LENGTH,
        "Min final length (bp)",
        "Minimum length of the cleaned-up sequence (consensus or single "
        "trimmed read) required before it's searched. 500bp matches the "
        "standard full-length COI barcode and the FDA's fish-barcoding "
        "protocol.",
        (0, None),
    ),
    _entry(
        "usability_check", "min_mean_quality", DEFAULT_MIN_MEAN_QUALITY,
        "Min mean quality (Phred)",
        "Minimum mean Phred score across the final sequence, set above "
        "the Q20 trim threshold since every base reaching this point has "
        "already cleared that bar.",
        (0, None),
    ),
    _entry(
        "usability_check", "max_ambiguous_proportion", DEFAULT_MAX_AMBIGUOUS_PROPORTION,
        "Max ambiguous proportion",
        "Maximum proportion of unresolved ambiguous positions allowed in "
        "the final consensus sequence. Matches the FDA's fish-barcoding "
        "protocol cutoff of under 2% ambiguous bases.",
        (0.0, 1.0),
    ),
    _entry(
        "blast", "max_hits", DEFAULT_MAX_HITS,
        "Max BLAST hits returned",
        "Number of top-ranked BLAST hits kept for identification and "
        "shown in the report. Not a biological cutoff -- just how many "
        "candidates get evaluated.",
        (1, None),
    ),
    _entry(
        "blast", "mode", "remote",
        "Search mode",
        "Whether this run searches NCBI's live remote database (default) "
        "or this deployment's own curated, versioned local reference DB "
        "(selectable per run). A remote search's raw response is cached "
        "verbatim against this run for the audit trail -- NCBI's own "
        "databases change over time, so the search itself can't be "
        "guaranteed to reproduce identically later, unlike a local "
        "search against a pinned reference version. The report must "
        "make plain which mode a run used.",
        choices=("remote", "local"),
    ),
    _entry(
        "blast", "remote_database", "nt",
        "Remote NCBI database",
        "Which NCBI-hosted nucleotide database a remote search targets. "
        "nt is the full nucleotide collection (broadest, includes "
        "unfiltered environmental/metagenomic submissions); core_nt is a "
        "deduplicated/filtered nt; refseq_rna / refseq_genomic are "
        "curated RefSeq sets (narrower, cleaner, may miss species with "
        "no RefSeq entry). Ignored when blast.mode is 'local'.",
        choices=("nt", "core_nt", "refseq_rna", "refseq_genomic"),
    ),
    _entry(
        "blast", "entrez_query", "",
        "Entrez restriction query",
        "Optional NCBI Entrez-syntax filter applied at the remote search "
        "itself -- e.g. 'NOT environmental sample[filter] NOT "
        "uncultured[Organism]' to strip contamination-prone entries, or "
        "a taxonomy restriction like 'Chordata[Organism]'. Blank means "
        "no restriction. Ignored when blast.mode is 'local'.",
    ),
    _entry(
        "identification", "min_identity_pct", DEFAULT_MIN_IDENTITY_PCT,
        "Min identity % (PASS)",
        "Minimum percent identity the top BLAST hit must reach for a "
        "PASS. 98% follows the standard 2% divergence cutoff used for "
        "COI-based species identification.",
        (0.0, 100.0),
    ),
    _entry(
        "identification", "min_coverage_pct", DEFAULT_MIN_COVERAGE_PCT,
        "Min coverage % (PASS)",
        "Minimum percent of the query sequence that must be covered by "
        "the alignment. Required alongside identity so a short, "
        "high-identity match can't pass on its own.",
        (0.0, 100.0),
    ),
    _entry(
        "identification", "ambiguous_margin_pct", DEFAULT_AMBIGUOUS_MARGIN_PCT,
        "Ambiguous margin (identity points)",
        "How many identity points the top hit must lead the next-best "
        "candidate by before the result is called clear rather than "
        "ambiguous.",
        (0.0, 100.0),
    ),
]

CATALOG_BY_KEY = {definition.key: definition for definition in CATALOG}
