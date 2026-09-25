"""GET /dashboard/stats -- aggregate numbers a UI needs (totals, rates,
breakdowns) that GET /runs' raw per-run list doesn't provide on its own.
See app.dashboard.stats.compute_dashboard_stats for exactly how each
number is derived and the design calls behind each one.

Scoped like GET /runs (app.api.runs.list_runs): an admin's numbers cover
every user's Runs, per claude/admin-run-visibility-status.md's
visibility-not-authority split; anyone else's numbers cover only their
own Runs.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.dashboard.stats import compute_dashboard_stats
from app.db import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return compute_dashboard_stats(db, current_user)
