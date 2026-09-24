"""Stage 10 -- Identification engine.

The ranked BLAST hits (Stage 9's output) are run through a rules layer
deciding a final category -- per CLAUDE.md, "the top hit is never taken
at face value." Three checks, using the values researched and cited in
claude/configuration-defaults.md (98% identity / 90% coverage / 1-point
separation): does the top hit clear the identity floor, does it clear
the coverage floor, and is the runner-up far enough behind it that the
call isn't a coin flip.

Priority order (per CLAUDE.md's own bullet ordering): a hit that fails
the identity/coverage floors is REVIEW REQUIRED even if there's also a
close runner-up -- failing the baseline quality bar is evaluated before
asking whether the call is ambiguous, not after.

NOT implemented: CLAUDE.md's other REVIEW REQUIRED trigger, "the result
looks taxonomically inconsistent." No numeric threshold covers it --
configuration-defaults.md's own Stage 10 section says so explicitly
("will need real rule logic, not just these three numbers") -- and no
domain-provided taxonomic consistency rules exist to encode yet. Rather
than silently skip it, `taxonomic_consistency_checked` is always False
on the result, so the gap is visible in every single output (and,
eventually, in Stage 11's report) rather than only in this docstring.
"""
from typing import List

from app.schemas.blast import BlastHit, BlastSearchResult
from app.schemas.identification import IdentificationResult

DEFAULT_MIN_IDENTITY_PCT = 98.0
DEFAULT_MIN_COVERAGE_PCT = 90.0
DEFAULT_AMBIGUOUS_MARGIN_PCT = 1.0

STATUS_PASS = "PASS"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_REVIEW_REQUIRED = "REVIEW REQUIRED"


def identify_species(
    hits: List[BlastHit],
    *,
    min_identity_pct: float = DEFAULT_MIN_IDENTITY_PCT,
    min_coverage_pct: float = DEFAULT_MIN_COVERAGE_PCT,
    ambiguous_margin_pct: float = DEFAULT_AMBIGUOUS_MARGIN_PCT,
) -> IdentificationResult:
    thresholds_applied = {
        "min_identity_pct": min_identity_pct,
        "min_coverage_pct": min_coverage_pct,
        "ambiguous_margin_pct": ambiguous_margin_pct,
    }

    if not hits:
        return IdentificationResult(
            status=STATUS_REVIEW_REQUIRED,
            reason="No BLAST hits were found -- nothing to identify against.",
            thresholds_applied=thresholds_applied,
        )

    top = hits[0]

    failures = []
    if top.identity < min_identity_pct:
        failures.append(
            f"Top match identity {top.identity:.2f}% is below the minimum of {min_identity_pct}%."
        )
    if top.coverage < min_coverage_pct:
        failures.append(
            f"Top match coverage {top.coverage:.2f}% is below the minimum of {min_coverage_pct}%."
        )

    if failures:
        return IdentificationResult(
            candidate_species=top.species,
            identity=top.identity,
            coverage=top.coverage,
            status=STATUS_REVIEW_REQUIRED,
            reason=" ".join(failures),
            thresholds_applied=thresholds_applied,
        )

    second = hits[1] if len(hits) > 1 else None
    if second is not None:
        margin = top.identity - second.identity
        if margin < ambiguous_margin_pct:
            return IdentificationResult(
                candidate_species=top.species,
                identity=top.identity,
                coverage=top.coverage,
                status=STATUS_AMBIGUOUS,
                reason=(
                    f"Second-best candidate {second.species!r} is only {margin:.2f} identity "
                    f"point(s) behind the top match ({second.identity:.2f}% vs {top.identity:.2f}%), "
                    f"below the {ambiguous_margin_pct}-point separation required to call it clear."
                ),
                thresholds_applied=thresholds_applied,
            )

    return IdentificationResult(
        candidate_species=top.species,
        identity=top.identity,
        coverage=top.coverage,
        status=STATUS_PASS,
        thresholds_applied=thresholds_applied,
    )


def identify_species_from_blast_result(
    result: BlastSearchResult, **thresholds
) -> IdentificationResult:
    """Thin wrapper matching Stage 9's actual output shape -- orchestration
    will have a BlastSearchResult in hand, not a bare hit list."""
    return identify_species(result.hits, **thresholds)
