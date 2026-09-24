"""Password hashing + JWT access tokens for the auth subsystem.

bcrypt directly (not passlib) -- one well-maintained library is enough
when this app only ever hashes with one algorithm; passlib's broader
multi-scheme abstraction isn't needed. PyJWT for tokens -- the smaller
and more common of the two usual FastAPI choices (the other being
python-jose); nothing here needs python-jose's wider crypto-backend
flexibility.

PAIGS_JWT_SECRET should always be set outside of local prototyping --
the fallback below is deliberately labeled insecure so it's never
mistaken for a real deployment value, same spirit as PAIGS_DATABASE_URL's
own SQLite fallback in app/db.py.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import bcrypt
import jwt

JWT_SECRET = os.environ.get("PAIGS_JWT_SECRET", "dev-insecure-jwt-secret-change-me-before-deploying")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("PAIGS_ACCESS_TOKEN_EXPIRE_MINUTES", "720"))  # 12h

# bcrypt's own default (12) is deliberately slow -- ~200-300ms per hash,
# by design, to resist brute-forcing a stolen hashed_password column.
# That's the right default for real accounts, but every test that logs
# in (most of the suite, via the `client` fixture) pays that cost on a
# freshly-seeded admin every single time, since each test gets its own
# throwaway database -- multiplied across ~300 tests, that's minutes,
# not seconds. Tests lower this via PAIGS_BCRYPT_ROUNDS (see
# tests/conftest.py); nothing about the security property being tested
# depends on the real cost factor.
BCRYPT_ROUNDS = int(os.environ.get("PAIGS_BCRYPT_ROUNDS", "12"))


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode(
        "utf-8"
    )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Raises jwt.PyJWTError (or a subclass -- ExpiredSignatureError,
    InvalidSignatureError, DecodeError, ...) for any invalid/expired/
    tampered token. Callers (app.auth.dependencies.get_current_user)
    translate that into a 401."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
