from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ConfigThresholdRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    stage_type: str
    param_name: str
    label: str
    description: str
    value: Union[float, str]
    value_type: str
    default: Union[float, str]
    # Only set for "enum"-typed keys (e.g. blast.mode, blast.remote_database)
    # -- the fixed set of allowed values a PUT /config/{id} or per-run
    # config_overrides entry must pick from. Null for "int"/"float"/"string".
    choices: Optional[List[str]] = None
    updated_at: datetime


class ConfigUpdate(BaseModel):
    value: Union[float, str] = Field(..., description="The new threshold value.")
