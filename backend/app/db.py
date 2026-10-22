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

A second, distinct Docker-bind-mount failure mode found in production
(recurring three separate times against the same dev deployment): the
underlying paigs.db file itself going missing out from under a still-
running process -- confirmed via the container's own open file
descriptors pointing at "paigs.db (deleted)" -- almost certainly Docker
Desktop's virtiofs layer losing track of a long-lived open handle on a
bind-mounted file across a host sleep/wake cycle, not anything this
app's own code does. On a real local filesystem a deleted-but-open file
keeps working fine (standard POSIX unlink semantics); over virtiofs it
doesn't, and every connection already in SQLAlchemy's pool that had
opened that now-gone file starts raising sqlite3.OperationalError("disk
I/O error") on every query, forever, since nothing was checking those
connections were still good before reusing them.

pool_pre_ping=True alone does NOT fix this, despite being the usual
answer to "a pooled connection went stale" -- verified directly against
this SQLAlchemy version: SQLiteDialect_pysqlite.is_disconnect() only
recognizes sqlite3.ProgrammingError("Cannot operate on a closed
database."), not OperationalError("disk I/O error"), so pre-ping's own
pre-flight check would hit the identical unrecognized error and not
trigger a reconnect. It's kept anyway (harmless, and it does cover that
other, real disconnect shape), but the actual fix for *this* error is
the handle_error listener below -- SQLAlchemy's docs are explicit that
pre-ping does not consult that event, so each failure mode needs its own
handling. Setting context.is_disconnect = True there invalidates the
whole pool on this specific error, so the very next request/poll tick
opens a fresh connection against whatever file exists now, instead of
reusing the same permanently-broken one -- turning "broken until a
manual restart" into "logs one error, self-heals within one poll
interval." See docker-compose.yml's own PAIGS_DATABASE_URL comment for
the complementary fix (keeping the file off the bind-mounted path
entirely, so this class of failure is avoided rather than just survived).
"""
import os
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("PAIGS_DATABASE_URL", "sqlite:///./paigs.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if IS_SQLITE else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

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

    @event.listens_for(engine, "handle_error")
    def _treat_disk_io_error_as_disconnect(context):
        """A stale connection pointing at a since-deleted/recreated
        paigs.db raises OperationalError("disk I/O error") on every
        query -- not a shape SQLite's own dialect recognizes as a
        disconnect (see module docstring), so without this, the same
        broken connection keeps getting reused from the pool forever.
        Marking it here invalidates the pool, so the next checkout opens
        a fresh connection instead of repeating the same failure.
        """
        original = context.original_exception
        if isinstance(original, sqlite3.OperationalError) and "disk I/O error" in str(original):
            context.is_disconnect = True


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
