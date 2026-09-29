"""
Database engine/session setup.

DATABASE_URL defaults to a local SQLite file for prototyping, per CLAUDE.md
("PostgreSQL (SQLite acceptable for early prototype)"). Set PAIGS_DATABASE_URL
to point at Postgres in real deployments.

WAL mode + a busy_timeout (SQLite only): SQLite's default rollback-journal
mode takes an exclusive file lock for the whole duration of a write
transaction, which serializes concurrent readers/writers at the OS file
level -- fragile over a Docker bind-mounted filesystem (the local dev
compose setup's own `./backend:/app` mount) once anything holds a
transaction open for more than an instant, e.g. a request that's slow for
a real reason (Stage 9's remote BLAST search, which can legitimately run
for minutes) while another request concurrently reads the same Run (the
frontend's own `GET /runs/{id}` stepper poll). WAL mode lets readers and
a single writer proceed without blocking each other; busy_timeout makes a
transient lock wait briefly and retry instead of failing immediately.
Applied via a connect-time PRAGMA rather than per-session, so every
connection this engine ever opens gets it, including ones opened by
future code that doesn't know to ask.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("PAIGS_DATABASE_URL", "sqlite:///./paigs.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
