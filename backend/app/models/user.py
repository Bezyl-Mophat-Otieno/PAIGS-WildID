"""User accounts for the authentication subsystem.

Invite-only, per the product decision: there is no self-registration
endpoint. Exactly one account is seeded automatically (the default
admin, see app.auth.service.ensure_default_admin) -- every other User
row is created by an admin via POST /admin/invite, which is also this
codebase's only admin-related feature for now (more admin capabilities
are a deliberate later step, not built yet).

role is a plain string, not a separate table -- "simple roles driving
the UI" only needs two values today ("admin", "analyst"; see
app.auth.service.VALID_ROLES), not a full RBAC/permissions model.

invited_by_id is null only for the seeded default admin; every invited
user's own id traces back to the admin who created it, the same
audit-trail habit the rest of this codebase follows (e.g. Run.rerun_of
in app/models/run.py).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, nullable=False, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    invited_by_id = Column(String, ForeignKey("users.id"), nullable=True)

    invited_by = relationship("User", remote_side=[id])
