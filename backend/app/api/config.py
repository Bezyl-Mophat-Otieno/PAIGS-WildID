"""GET/PUT /config -- the Configuration subsystem's HTTP surface.

Per CLAUDE.md's API shape: `GET /config -> list current threshold
configs`, `PUT /config/{id} -> update a threshold config`. These global
values are what every new Run's effective thresholds fall back to unless
overridden at POST /runs or POST /runs/{id}/rerun time -- see
app.configuration.service.effective_thresholds(), which
app.orchestration.execute reads from at execute time.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.configuration import service as config_service
from app.configuration.catalog import CATALOG_BY_KEY
from app.configuration.errors import ConfigNotFoundError, ConfigValueOutOfBoundsError
from app.db import get_db
from app.models.config import ConfigThreshold
from app.schemas.config import ConfigThresholdRead, ConfigUpdate

router = APIRouter(prefix="/config", tags=["config"])


def _to_read(row: ConfigThreshold) -> ConfigThresholdRead:
    definition = CATALOG_BY_KEY[row.key]
    return ConfigThresholdRead(
        id=row.id,
        key=row.key,
        stage_type=definition.stage_type,
        param_name=definition.param_name,
        label=definition.label,
        description=definition.description,
        value=row.value,
        value_type=definition.value_type,
        default=definition.default,
        updated_at=row.updated_at,
    )


@router.get("", response_model=List[ConfigThresholdRead])
def list_config(db: Session = Depends(get_db)):
    rows = config_service.list_config(db)
    return [_to_read(row) for row in rows]


@router.put("/{config_id}", response_model=ConfigThresholdRead)
def update_config(config_id: str, payload: ConfigUpdate, db: Session = Depends(get_db)):
    try:
        row = config_service.update_config(db, config_id, payload.value)
    except ConfigNotFoundError:
        raise HTTPException(status_code=404, detail="Config threshold not found.")
    except ConfigValueOutOfBoundsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _to_read(row)
