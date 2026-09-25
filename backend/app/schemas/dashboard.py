"""GET /dashboard/stats response shapes.

User's own words for why this exists: "The Run list endpoint only
returns raw, per-run data. Total samples processed, identification
rate, QC pass rate, pending-review count, species breakdown,
quality-score histogram -- none of that exists as a number the backend
hands over. It has to be computed server-side, not hacked together in
the frontend." See app.dashboard.stats for how each number is derived.
"""
from typing import List, Optional

from pydantic import BaseModel


class SpeciesCount(BaseModel):
    species: str
    count: int


class QualityHistogramBucket(BaseModel):
    label: str
    count: int


class DashboardStats(BaseModel):
    total_samples_processed: int
    # None (not 0.0) when no run has reached the relevant stage yet --
    # "0% of nothing" is a misleading number to hand a UI, distinct from
    # "0% of some".
    identification_rate: Optional[float] = None
    qc_pass_rate: Optional[float] = None
    pending_review_count: int
    species_breakdown: List[SpeciesCount]
    quality_score_histogram: List[QualityHistogramBucket]
