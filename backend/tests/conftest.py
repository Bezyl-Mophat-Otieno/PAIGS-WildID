import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set before importing anything under app.* -- app.auth.security reads
# this into a module-level constant at import time. See its own comment
# on BCRYPT_ROUNDS: the real default (12) is deliberately slow, and the
# `client` fixture below logs in for real on every single test.
os.environ.setdefault("PAIGS_BCRYPT_ROUNDS", "4")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app import storage  # noqa: E402
from app.auth import service as auth_service  # noqa: E402


@pytest.fixture()
def temp_storage_root(tmp_path, monkeypatch):
    """Redirect the storage module's root to an isolated per-test directory."""
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setattr(storage, "STORAGE_ROOT", storage_root)
    return storage_root


@pytest.fixture()
def temp_reference_data_root(tmp_path, monkeypatch):
    """Redirect app.reference.publish's REFERENCE_DATA_ROOT to an isolated
    per-test directory, same treatment as temp_storage_root above."""
    from app.reference import publish as reference_publish

    root = tmp_path / "reference_data"
    root.mkdir()
    monkeypatch.setattr(reference_publish, "REFERENCE_DATA_ROOT", root)
    return root


@pytest.fixture()
def client(tmp_path, temp_storage_root):
    """A TestClient wired to an isolated, per-test SQLite database and
    storage dir -- authenticated as the seeded default admin by default
    (every existing test that predates the auth subsystem assumed an
    unauthenticated caller; auto-logging in here, rather than touching
    every one of those test files, is what keeps them green now that
    /runs requires a token). Tests that need a *different* identity use
    analyst_client below; tests that need *no* identity use anon_client.
    """
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        login = test_client.post(
            "/auth/login",
            data={"username": auth_service.ADMIN_EMAIL, "password": auth_service.ADMIN_PASSWORD},
        )
        test_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def anon_client(client):
    """A second TestClient with no Authorization header at all, sharing
    the client fixture's isolated per-test database (same overridden
    get_db, still active on the app singleton for the life of this
    test) -- for asserting an endpoint actually requires
    authentication."""
    with TestClient(app) as unauth_client:
        yield unauth_client


@pytest.fixture()
def analyst_client(client):
    """A second TestClient, authenticated as a freshly-invited analyst
    (not the default admin the client fixture is authenticated as),
    sharing the same isolated per-test database -- for asserting
    per-owner run scoping and role restrictions (see e.g.
    test_api_runs_ownership.py)."""
    invite = client.post(
        "/admin/invite", json={"email": "fixture-analyst@example.com", "role": "analyst"}
    ).json()
    with TestClient(app) as second_client:
        login = second_client.post(
            "/auth/login",
            data={
                "username": "fixture-analyst@example.com",
                "password": invite["temporary_password"],
            },
        )
        second_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        yield second_client


@pytest.fixture()
def fixtures_dir():
    return BACKEND_ROOT / "tests" / "fixtures"


@pytest.fixture()
def db_session(tmp_path):
    """
    A raw SQLAlchemy session against an isolated per-test SQLite database,
    for tests that touch models directly (e.g. Reference Database Setup's
    publish_reference_db) rather than through the HTTP API, which is what
    the `client` fixture above is for.
    """
    db_path = tmp_path / "test_reference.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
