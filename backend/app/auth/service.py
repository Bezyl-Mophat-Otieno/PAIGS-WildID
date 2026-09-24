"""DB-backed operations for the auth subsystem: seeding the default
admin, authenticating a login attempt, and creating an admin-invited
user. Same lazy-lifecycle spirit as app.configuration.service --
ensure_default_admin() is idempotent and cheap, and is called by
authenticate() itself rather than needing a separate startup step (no
Alembic/migration story in this app yet, see app/db.py) -- a fresh
database always has a working login on the very first attempt.
"""
import os
import secrets
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.auth.errors import EmailAlreadyExistsError, InvalidCredentialsError, InvalidRoleError
from app.auth.security import hash_password, verify_password
from app.models.user import User

VALID_ROLES = ("admin", "analyst")

ADMIN_EMAIL = os.environ.get("PAIGS_ADMIN_EMAIL", "admin@paigs.local")
# Insecure on purpose -- same "clearly-labeled prototype fallback" spirit
# as PAIGS_JWT_SECRET's default in app/auth/security.py. Set
# PAIGS_ADMIN_PASSWORD (and PAIGS_ADMIN_EMAIL) outside of local
# prototyping; see README for how.
ADMIN_PASSWORD = os.environ.get("PAIGS_ADMIN_PASSWORD", "paigs-admin-dev")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_default_admin(db: Session) -> None:
    """Seeds exactly one admin account, keyed by PAIGS_ADMIN_EMAIL --
    idempotent, never touches an existing row (so an admin who changed
    their own password later never has it silently reset back to the
    env default)."""
    existing = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if existing is not None:
        return
    db.add(
        User(
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            role="admin",
            is_active=True,
            invited_by_id=None,
        )
    )
    db.commit()


def authenticate(db: Session, email: str, password: str) -> User:
    ensure_default_admin(db)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        # Same error either way -- a login attempt can't be used to
        # enumerate which emails have accounts.
        raise InvalidCredentialsError()
    return user


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(9)


def create_invited_user(
    db: Session, email: str, role: str, invited_by_id: Optional[str] = None
) -> Tuple[User, str]:
    if role not in VALID_ROLES:
        raise InvalidRoleError(role)
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise EmailAlreadyExistsError(email)
    temporary_password = generate_temporary_password()
    user = User(
        email=email,
        hashed_password=hash_password(temporary_password),
        role=role,
        is_active=True,
        invited_by_id=invited_by_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, temporary_password


def list_users(db: Session) -> List[User]:
    return db.query(User).order_by(User.created_at).all()
