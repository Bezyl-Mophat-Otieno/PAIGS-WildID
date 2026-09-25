"""Dashboard aggregation -- build-order item 4 on the user's punch list
(see claude/api-hardening-status.md and claude/admin-run-visibility-status.md
for items 1-3).

Every number here is derived from data the pipeline already records on
each Run's Stages (app.orchestration.execute persists a Stage row per
stage it runs, with the pipeline result's own model_dump() as `output`)
-- nothing new is tracked, this just aggregates what already exists.

Scoping matches GET /runs (see app.api.runs.list_runs): an admin's
numbers cover every user's Runs; anyone else's numbers cover only their
own. Visibility only, consistent with claude/admin-run-visibility-status.md
-- these are read-only aggregate counts, there's no "act on" concept here
to restrict further.

Design calls made here, since CLAUDE.md doesn't define any of these
precisely and the user's punch list only named the six numbers, not
their exact formulas:

- "Total samples processed" = count of this caller's visible Runs whose
  `status` is no longer "in_progress" -- i.e., POST /runs/{id}/execute
  has actually been called and the pipeline reached some conclusion
  (completed OR failed/stopped early). A Run that's only been uploaded
  (Stage 0 Import) hasn't been "processed" yet in any meaningful sense.

- "Identification rate" = PASS-status identification stages / all
  completed identification stages. Denominator is deliberately *not*
  "all processed Runs" -- many Runs never reach Stage 10 at all (a bad
  file stops at sanity_check, a too-short consensus stops at
  usability_check, etc.), and diluting the rate with those would make
  it a measure of "how often does the whole pipeline succeed
  end-to-end" rather than "of the samples that got identified, how many
  were confident calls" -- the latter is what "identification rate"
  means to an analyst reading the dashboard.

- "QC pass rate" = PASS-status usability_check stages / all completed
  usability_check stages (Stage 7, CLAUDE.md's "real accept/reject
  gate" -- the natural QC checkpoint to report a pass rate for, as
  opposed to Stage 3's lenient pre-trim sanity floor).

- "Pending-review count" = count of identification stages whose status
  is exactly "REVIEW REQUIRED" (Stage 10's own vocabulary -- see
  app.pipeline.identification). Deliberately excludes "AMBIGUOUS": that
  status means a specific, if uncertain, call was still made, whereas
  REVIEW REQUIRED is the pipeline explicitly saying it couldn't clear
  its own quality bar and a human needs to look. If the product instead
  wants AMBIGUOUS counted as "pending review" too, that's a one-line
  change here.

- "Species breakdown" = candidate_species counts, PASS-status
  identifications only. An AMBIGUOUS or REVIEW REQUIRED result's
  candidate_species (when set at all) is not yet a confirmed
  identification, so counting it here would overstate confidence in the
  breakdown.

- "Quality-score histogram" = usability_check stage's mean_quality,
  bucketed against this app's own existing quality conventions (Stage 4
  Trim's Q20 floor, Stage 7's own default Q25 usability floor -- see
  app.pipeline.usability_check) rather than arbitrary round numbers:
  <20 (below even the trim floor -- shouldn't really occur, but not
  excluded), 20-25 (trimmed but below the usability floor), 25-30,
  30-35, 35+. Covers every usability_check stage regardless of
  PASS/FAIL, since this is about the raw quality distribution, not the
  pass/fail gate itself.
"""
from collections import Counter
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.run import Run
from app.models.stage import Stage
from app.models.user import User
from app.schemas.dashboard import DashboardStats, QualityHistogramBucket, SpeciesCount

# (label, inclusive lower bound or None, exclusive upper bound or None)
QUALITY_HISTOGRAM_BUCKETS = [
    ("<20", None, 20.0),
    ("20-25", 20.0, 25.0),
    ("25-30", 25.0, 30.0),
    ("30-35", 30.0, 35.0),
    ("35+", 35.0, None),
]


def _bucket_label(mean_quality: float) -> str:
    for label, low, high in QUALITY_HISTOGRAM_BUCKETS:
        if low is not None and mean_quality < low:
            continue
        if high is not None and mean_quality >= high:
            continue
        return label
    return QUALITY_HISTOGRAM_BUCKETS[-1][0]  # defensive; every real number matches a bucket above


def compute_dashboard_stats(db: Session, current_user: User) -> DashboardStats:
    run_query = db.query(Run)
    if current_user.role != "admin":
        run_query = run_query.filter(Run.owner_id == current_user.id)
    run_ids = [run.id for run in run_query.all()]

    if not run_ids:
        return DashboardStats(
            total_samples_processed=0,
            identification_rate=None,
            qc_pass_rate=None,
            pending_review_count=0,
            species_breakdown=[],
            quality_score_histogram=[
                QualityHistogramBucket(label=label, count=0) for label, _, _ in QUALITY_HISTOGRAM_BUCKETS
            ],
        )

    total_samples_processed = (
        db.query(Run).filter(Run.id.in_(run_ids), Run.status != "in_progress").count()
    )

    usability_stages = (
        db.query(Stage)
        .filter(
            Stage.run_id.in_(run_ids),
            Stage.stage_type == "usability_check",
            Stage.status == "completed",
        )
        .all()
    )
    identification_stages = (
        db.query(Stage)
        .filter(
            Stage.run_id.in_(run_ids),
            Stage.stage_type == "identification",
            Stage.status == "completed",
        )
        .all()
    )

    qc_pass_rate: Optional[float] = None
    histogram_counter: Counter = Counter()
    if usability_stages:
        pass_count = 0
        for stage in usability_stages:
            output = stage.output or {}
            if output.get("status") == "PASS":
                pass_count += 1
            mean_quality = output.get("mean_quality")
            if mean_quality is not None:
                histogram_counter[_bucket_label(mean_quality)] += 1
        qc_pass_rate = pass_count / len(usability_stages)

    identification_rate: Optional[float] = None
    pending_review_count = 0
    species_counter: Counter = Counter()
    if identification_stages:
        pass_count = 0
        for stage in identification_stages:
            output = stage.output or {}
            status = output.get("status")
            if status == "PASS":
                pass_count += 1
                species = output.get("candidate_species")
                if species:
                    species_counter[species] += 1
            elif status == "REVIEW REQUIRED":
                pending_review_count += 1
        identification_rate = pass_count / len(identification_stages)

    quality_score_histogram = [
        QualityHistogramBucket(label=label, count=histogram_counter.get(label, 0))
        for label, _, _ in QUALITY_HISTOGRAM_BUCKETS
    ]
    species_breakdown = [
        SpeciesCount(species=species, count=count)
        for species, count in sorted(species_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return DashboardStats(
        total_samples_processed=total_samples_processed,
        identification_rate=identification_rate,
        qc_pass_rate=qc_pass_rate,
        pending_review_count=pending_review_count,
        species_breakdown=species_breakdown,
        quality_score_histogram=quality_score_histogram,
    )
