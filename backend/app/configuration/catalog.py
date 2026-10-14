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
Run stages plus one non-Run workflow (`bold_fetch` -- see below) are
catalogued here as one flat list, keyed "<stage_type>.<param_name>" --
that key is what a per-run config_overrides dict (POST /runs, POST
/runs/{id}/rerun) and PUT /config/{id} both address, and it's exactly the
kwarg name each stage's own pipeline function accepts (via
app.configuration.service.kwargs_for_stage).

Most entries are numeric ("int"/"float", validated against `bounds`). The
`blast.mode` / `blast.remote_database` / `bold_fetch.require_species_level`
entries are "enum" (validated against `choices`); `blast.entrez_query` is
free-text ("string", unvalidated beyond type). `bounds` is meaningless
for either of those value_types and is left at its (None, None) default.

`bold_fetch.*` is not a pipeline Run stage at all -- it's the same
global-default-plus-per-action-override mechanism reused for a different
workflow: automated candidate-record fetching from BOLD Systems for
building the local reference database (see app.reference.bold and
app.reference.drafts). Reused deliberately rather than inventing a
second config mechanism, since the actual need -- "a sensible default,
deliberately overridable per action, never silently different between
two callers" -- is identical.
"""
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from app.pipeline.blast import DEFAULT_MAX_HITS, DEFAULT_REMOTE_TIMEOUT_SECONDS
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
from app.reference.bold import (
    DEFAULT_MAX_N_PROPORTION as BOLD_DEFAULT_MAX_N_PROPORTION,
    DEFAULT_MAX_RECORDS_PER_SPECIES as BOLD_DEFAULT_MAX_RECORDS_PER_SPECIES,
    DEFAULT_MIN_SEQUENCE_LENGTH as BOLD_DEFAULT_MIN_SEQUENCE_LENGTH,
    DEFAULT_REQUIRE_SPECIES_LEVEL as BOLD_DEFAULT_REQUIRE_SPECIES_LEVEL,
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
        "blast", "remote_database", "core_nt",
        "Remote NCBI database",
        "Which NCBI-hosted nucleotide database a remote search targets. "
        "core_nt (the default) is NCBI's own deduplicated/filtered "
        "version of nt -- meaningfully fewer redundant/environmental "
        "records for NCBI to search, which in practice means faster "
        "results with little real coverage lost; nt is the full, "
        "unfiltered nucleotide collection (broadest, but includes noisy "
        "environmental/metagenomic submissions, and can take "
        "significantly longer under real load); refseq_rna / "
        "refseq_genomic are curated RefSeq sets (narrower, cleaner, may "
        "miss species with no RefSeq entry). Ignored when blast.mode is "
        "'local'.",
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
        "blast", "remote_timeout_seconds", DEFAULT_REMOTE_TIMEOUT_SECONDS,
        "Remote search timeout (seconds)",
        "How long to wait for NCBI's remote BLAST service before giving "
        "up and stopping the run at Stage 9. An engineering/operational "
        "judgment call (network conditions, NCBI queue depth), not a "
        "biological threshold. Ignored when blast.mode is 'local', which "
        "has no network round trip to bound.",
        (1, None),
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
    _entry(
        "bold_fetch", "min_sequence_length", BOLD_DEFAULT_MIN_SEQUENCE_LENGTH,
        "Min sequence length (bp)",
        "A candidate BOLD record's sequence shorter than this is dropped "
        "as a partial/truncated read, not a reliable enough fingerprint "
        "to trust as reference ground truth. A full COI barcode is "
        "normally ~650bp; lower this for a taxon whose marker region is "
        "naturally shorter.",
        (1, None),
    ),
    _entry(
        "bold_fetch", "max_n_proportion", BOLD_DEFAULT_MAX_N_PROPORTION,
        "Max ambiguous (N) proportion",
        "Maximum proportion of unreadable \"N\" positions tolerated in a "
        "candidate record's own sequence before it's dropped as too "
        "degraded to trust -- the same idea as Stage 3's own sanity "
        "check on an uploaded sample, applied here to BOLD's data "
        "instead.",
        (0.0, 1.0),
    ),
    _entry(
        "bold_fetch", "max_records_per_species", BOLD_DEFAULT_MAX_RECORDS_PER_SPECIES,
        "Max records kept per species",
        "How many BOLD records survive per species once a fetch is "
        "otherwise clean -- keeping every specimen BOLD has for a common "
        "species bloats the local BLAST index and over-represents it "
        "relative to rarer ones, without making the reference set more "
        "accurate. An engineering/practical judgment call, not a "
        "biological one.",
        (1, None),
    ),
    _entry(
        "bold_fetch", "require_species_level", BOLD_DEFAULT_REQUIRE_SPECIES_LEVEL,
        "Species-level identification",
        "\"required\" (default) drops any BOLD record not confirmed to "
        "species level -- a genus/family-only identification isn't a "
        "trustworthy species-level answer-key entry. \"allow_lower_rank\" "
        "is a deliberate risk trade, not a threshold tweak: it admits "
        "lower-confidence identifications into the draft, clearly "
        "flagged, rather than screening them out entirely. Reviewed "
        "manually either way before anything is published.",
        choices=("required", "allow_lower_rank"),
    ),
]

CATALOG_BY_KEY = {definition.key: definition for definition in CATALOG}
