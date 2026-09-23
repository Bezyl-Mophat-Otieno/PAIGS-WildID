from datetime import datetime
from typing import Any, List, Optional

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


class RunDetail(RunRead):
    model_config = ConfigDict(from_attributes=True)

    stages: List[StageSummary] = []


class RunPatch(BaseModel):
    sample_id: str = Field(..., min_length=1)
