"""Configuration subsystem model -- one row per threshold catalog key.

Static metadata (label, description, bounds/choices, which pipeline
stage/kwarg a key maps to) lives in app.configuration.catalog, not here
-- only the mutable, DB-persisted piece (the current value, and when it
last changed) needs a table. Rows are seeded lazily
(app.configuration.service.ensure_seeded) from the catalog's own
defaults the first time GET/PUT /config, or a Run's execution, needs
them -- there's no separate migration/startup step for it, consistent
with how this app creates all its tables (Base.metadata.create_all in
app.main, no Alembic yet).

Two value columns, exactly one populated per row (see
app.configuration.service.value_of, the single place that reads either
one back): `value` for the catalog's numeric ("int"/"float") keys,
unchanged since this table's introduction; `value_text` for the
"enum"/"string" keys added for the remote-vs-local BLAST search decision
(blast.mode, blast.remote_database, blast.entrez_query) -- a plain
second column rather than widening `value` itself, so every existing
numeric row/query/test is untouched.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, String

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConfigThreshold(Base):
    __tablename__ = "config_thresholds"

    id = Column(String, primary_key=True, default=_uuid)
    key = Column(String, nullable=False, unique=True)
    value = Column(Float, nullable=True)
    value_text = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
