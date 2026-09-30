"""
Database engine/session setup.

DATABASE_URL defaults to a local SQLite file for prototyping, per CLAUDE.md
("PostgreSQL (SQLite acceptable for early prototype)"). Set PAIGS_DATABASE_URL
to point at Postgres in real deployments.

A note on why per-stage durability (see app.orchestration.execute's
_persist_stage) is the load-bearing fix for the "disk I/O error under a
long-blocking Stage 9 remote search" problem, not this module: committing
after every stage means no write transaction is ever held open across
Stage 9's potentially minutes-long blastn subprocess call in the first
place, regardless of SQLite's journal mode. WAL mode was added here as
additional defense-in-depth for concurrent *reads* during that same
window (e.g. the frontend's `GET /runs/{id}` stepper poll) -- but WAL
requires shared-memory primitives (a memory-mapped `-shm` file between
processes) that not every filesystem supports, and it turned out to
outright break every single connection over one real deployment's Docker
bind-mount (`disk I/O error` on the `PRAGMA journal_mode=WAL` statement
itself, every time -- worse than the problem it was meant to help with,
since that failure hits *every* request, not just a slow one). So it's
attempted best-effort and silently left at SQLite's default
(rollback-journal) mode if the filesystem can't support it, rather than
assumed to always succeed. busy_timeout has no such filesystem
requirement and is kept unconditionally -- it just makes a transient lock
wait and retry instead of failing immediately, safe in either journal
mode.
"""
import os
import sqlite3

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
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            # Filesystem doesn't support WAL's shared-memory requirement
            # (some Docker bind-mount configurations, notably) -- fall
            # back to SQLite's default journal mode rather than making
            # every single connection this engine ever opens fail.
            pass
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
