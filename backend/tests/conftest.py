import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app import storage  # noqa: E402


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
    """A TestClient wired to an isolated, per-test SQLite database and storage dir."""
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
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


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
