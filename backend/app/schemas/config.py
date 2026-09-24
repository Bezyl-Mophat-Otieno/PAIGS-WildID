from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConfigThresholdRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    stage_type: str
    param_name: str
    label: str
    description: str
    value: float
    value_type: str
    default: float
    updated_at: datetime


class ConfigUpdate(BaseModel):
    value: float = Field(..., description="The new threshold value.")
