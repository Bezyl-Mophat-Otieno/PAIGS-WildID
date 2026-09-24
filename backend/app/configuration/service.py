"""DB-backed operations over the Configuration subsystem's catalog
(app.configuration.catalog) -- seeding, listing, updating the global
config table, resolving a Run's *effective* thresholds (global config +
that Run's own per-run overrides), and mapping the result back to the
exact kwargs each pipeline stage function accepts.

There is deliberately no separate migration/startup step to populate
config_thresholds -- ensure_seeded() is idempotent and cheap (one SELECT,
and only writes anything the first time a given key is seen), and every
entry point below calls it first, the same lazy-table-creation spirit
app.main already uses for Base.metadata.create_all.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.configuration.catalog import CATALOG, CATALOG_BY_KEY, ThresholdDefinition
from app.configuration.errors import (
    ConfigNotFoundError,
    ConfigValueOutOfBoundsError,
    UnknownConfigKeyError,
)
from app.models.config import ConfigThreshold


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _check_bounds(definition: ThresholdDefinition, value: float) -> None:
    low, high = definition.bounds
    if low is not None and value < low:
        raise ConfigValueOutOfBoundsError(definition.key, value, low, high)
    if high is not None and value > high:
        raise ConfigValueOutOfBoundsError(definition.key, value, low, high)


def validate_overrides(overrides: Dict[str, float]) -> None:
    """Raises UnknownConfigKeyError / ConfigValueOutOfBoundsError for a
    per-run or rerun config_overrides payload, before it's ever stored on
    a Run -- used by both POST /runs and POST /runs/{id}/rerun."""
    for key, value in overrides.items():
        definition = CATALOG_BY_KEY.get(key)
        if definition is None:
            raise UnknownConfigKeyError(key)
        _check_bounds(definition, value)


def ensure_seeded(db: Session) -> None:
    """Insert one row per catalog key, using its module-level default,
    for any key that doesn't have a row yet. Idempotent, and never
    touches a row that already exists -- an analyst's PUT /config/{id}
    edit is never silently reverted by a later seed call."""
    existing_keys = {row.key for row in db.query(ConfigThreshold).all()}
    missing = [definition for definition in CATALOG if definition.key not in existing_keys]
    if not missing:
        return
    now = _utcnow()
    for definition in missing:
        db.add(ConfigThreshold(key=definition.key, value=definition.default, updated_at=now))
    db.commit()


def list_config(db: Session) -> List[ConfigThreshold]:
    ensure_seeded(db)
    return db.query(ConfigThreshold).order_by(ConfigThreshold.key).all()


def update_config(db: Session, config_id: str, value: float) -> ConfigThreshold:
    ensure_seeded(db)
    row = db.get(ConfigThreshold, config_id)
    if row is None:
        raise ConfigNotFoundError(config_id)
    definition = CATALOG_BY_KEY[row.key]
    _check_bounds(definition, value)
    row.value = value
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def effective_thresholds(
    db: Session, overrides: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """The global config's current values (seeded defaults, possibly
    edited via PUT /config/{id}), with `overrides` (a Run's own
    config_overrides, if any) layered on top for just this call --
    "Global defaults apply unless overridden" (CLAUDE.md's Configuration
    model). Returns a flat {catalog_key: value} dict."""
    ensure_seeded(db)
    values = {row.key: row.value for row in db.query(ConfigThreshold).all()}
    for key, value in (overrides or {}).items():
        if key not in CATALOG_BY_KEY:
            raise UnknownConfigKeyError(key)
        values[key] = value
    return values


def kwargs_for_stage(effective: Dict[str, float], stage_type: str) -> Dict[str, Any]:
    """This stage's slice of `effective`, mapped to the exact kwarg names
    its pipeline function accepts, cast back to int where the catalog
    says so (every stored/overridden value round-trips as a float through
    the DB and through a JSON config_overrides payload)."""
    result: Dict[str, Any] = {}
    for definition in CATALOG:
        if definition.stage_type != stage_type:
            continue
        value = effective[definition.key]
        result[definition.param_name] = int(value) if definition.value_type == "int" else value
    return result
