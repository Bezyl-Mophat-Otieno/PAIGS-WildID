from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class StageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage_type: str
    status: str
    attempt_number: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class StageDetail(StageSummary):
    model_config = ConfigDict(from_attributes=True)

    input_ref: Optional[Any] = None
    output: Optional[Any] = None
    stage_metadata: Optional[Any] = None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sample_id: str
    original_filenames: List[str]
    created_at: datetime
    current_stage: str
    status: str
    # Per-run threshold overrides supplied at POST /runs or POST
    # /runs/{id}/rerun time -- null when the analyst didn't override
    # anything (see app.models.run.Run's own docstring). Values are
    # floats for numeric catalog keys, strings for "enum"/"string" keys
    # (e.g. blast.mode, blast.remote_database, blast.entrez_query).
    config_overrides: Optional[Dict[str, Union[float, str]]] = None
    # Set only on a Run created via POST /runs/{id}/rerun -- the
    # original Run this one reused the file(s) of.
    rerun_of: Optional[str] = None
    # The User who created (or reran) this Run -- see app.models.run.Run's
    # own docstring on owner_id for the current per-owner scoping rule.
    owner_id: str
    # This Run's completed identification stage's verdict ("PASS" |
    # "AMBIGUOUS" | "REVIEW REQUIRED"), or null if Stage 10 hasn't
    # completed yet. Mirrors app.dashboard.stats's own join, so a Run
    # listing's outcome stays consistent with the Dashboard's counts.
    identification_status: Optional[str] = None


class RunDetail(RunRead):
    model_config = ConfigDict(from_attributes=True)

    stages: List[StageSummary] = []


class RunPatch(BaseModel):
    sample_id: str = Field(..., min_length=1)


class RerunRequest(BaseModel):
    """POST /runs/{id}/rerun's optional JSON body. No files here -- the
    whole point is reusing the source Run's already-stored file(s)
    (app.orchestration.rerun.create_rerun); only what's different about
    the new attempt is supplied.

    auto_execute: when true, the endpoint also runs the new Run through
    to completion (or its stopping point) in the same call, exactly the
    "create, then immediately run" convenience CLAUDE.md's UI flow
    describes for a fresh upload ("Upload triggers POST /runs followed
    immediately by POST /runs/{id}/execute") -- built into the endpoint
    itself instead of left to the caller to wire up as two requests.
    Defaults to false, matching a fresh upload's own two-step API shape
    (POST /runs, then a separate POST /runs/{id}/execute) unless a
    caller explicitly opts into the shortcut.
    """

    config_overrides: Optional[Dict[str, Union[float, str]]] = None
    sample_id: Optional[str] = None
    auto_execute: bool = False
