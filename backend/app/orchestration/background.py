"""Stage 9's background execution for blast.mode="remote": a real network
round trip to NCBI that can legitimately take minutes must not block the
HTTP request/worker thread/DB connection that started it -- see
app.orchestration.execute's own module docstring, and the incident that
prompted this: a genuine SQLite "disk I/O error" crash under a long-held-
open transaction spanning exactly this kind of block.

Deliberately a DB-backed poller, not a new message-queue dependency
(Celery/RQ + Redis): a Stage row already *is* the job record
(status="running" is the queue), so "enqueueing" a job
(app.orchestration.execute._dispatch_blast) is nothing more than the same
_persist_stage() call every other stage already makes. Matches this app's
current single-process, single-lab deployment scale -- CLAUDE.md's own
"no background-job infrastructure exists in this app yet... worth
revisiting" note, revisited here in the smallest way that actually fixes
the blocking problem, not a move to Celery/RQ this app's actual job
volume doesn't yet justify.

Concurrency model: the poller thread only *detects* running blast stages;
each one is handed to its own short-lived worker thread, so multiple
analysts' remote searches can run concurrently rather than queueing
behind each other. `_in_flight` tracks which run ids already have a
worker thread dispatched, so the next poll tick doesn't double-dispatch
the same job while it's still running. `_is_due` additionally skips
dispatching at all for a run that isn't actually due for its next check
yet (per app.orchestration.execute's own submit -> poll -> fetch state
machine) -- without it, every single tick would open a fresh worker
thread/SQLite connection for every in-progress remote search for its
entire duration, not just when there's real work to do; that sharp
increase in connection churn compared to this module's original
single-long-blocking-call design is exactly the kind of concurrent-
access pressure that re-triggered the SQLite incident above once this
state machine shipped.

Known limitation: assumes a single application process. A multi-worker
or multi-replica deployment would need an atomic claim step (e.g. an
UPDATE ... WHERE status='running' AND claimed_at IS NULL) to stop two
processes both picking up the same job -- not needed at this app's
current single-instance deployment scale (see docker-compose.yml: one
wildid-backend service, uvicorn with no --workers flag).

Disabled entirely when PAIGS_DISABLE_BACKGROUND_WORKER is set (tests set
this in conftest.py): a real poller thread would connect via this
module's own SessionLocal -- the production engine, bound to whatever
PAIGS_DATABASE_URL resolves to for the whole test process -- not any
individual test's isolated per-test database, so it has no useful work
to do there and is just thread churn/noise across the suite.
"""
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Set

from app.db import SessionLocal
from app.models.stage import Stage

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 2.0

_stop_event = threading.Event()
_in_flight: Set[str] = set()
_in_flight_lock = threading.Lock()
_poller_thread: threading.Thread | None = None


def _is_due(stage: Stage) -> bool:
    """Whether this "running" blast stage is actually due for a check
    this tick -- not just present. app.orchestration.execute's own
    submit -> poll -> fetch state machine (see _advance_remote_blast)
    stashes a next_check_at on the stage's own metadata precisely so this
    decision can be made here, from data already loaded by _poll_once's
    single query, with no extra DB round trip.

    This matters well beyond efficiency: without it, every tick (every
    POLL_INTERVAL_SECONDS) would dispatch a fresh worker thread -- and a
    fresh SQLite connection -- for every in-progress remote search, for
    its entire duration, even though most ticks have nothing to do until
    next_check_at arrives (RTOE first, then ~60s after that). That's a
    sharp increase in short-lived concurrent SQLite connections compared
    to the old design's single long-held one, and it's exactly the kind
    of concurrent-access pressure that already broke this app's SQLite
    setup once before under a Docker bind-mount (see app.db's own
    docstring on the WAL-mode incident) -- skipping the dispatch
    entirely when nothing is due keeps connection churn back down to
    "once per real check," not "once per tick."
    """
    job = (stage.stage_metadata or {}).get("remote_job")
    if job is None:
        return True  # not yet submitted -- always worth a dispatch
    try:
        next_check_at = datetime.fromisoformat(job["next_check_at"])
    except (KeyError, TypeError, ValueError):
        return True  # malformed/missing -- fail open rather than wedge the run
    return datetime.now(timezone.utc) >= next_check_at


def _process_run(run_id: str) -> None:
    # Imported inside the function, not at module load -- avoids a
    # circular import (app.orchestration.execute doesn't need to know
    # this module exists; this module is the only side that needs to
    # know about resume_run_after_blast).
    from app.orchestration.execute import resume_run_after_blast

    db = SessionLocal()
    try:
        resume_run_after_blast(run_id, db)
    except Exception:  # noqa: BLE001 -- must not crash the poller thread itself
        logger.exception("Background BLAST resume failed for run %s", run_id)
    finally:
        db.close()
        with _in_flight_lock:
            _in_flight.discard(run_id)


def _poll_once() -> None:
    db = SessionLocal()
    try:
        pending = (
            db.query(Stage)
            .filter(Stage.stage_type == "blast", Stage.status == "running")
            .all()
        )
        for stage in pending:
            if not _is_due(stage):
                continue
            with _in_flight_lock:
                if stage.run_id in _in_flight:
                    continue
                _in_flight.add(stage.run_id)
            threading.Thread(
                target=_process_run, args=(stage.run_id,), daemon=True
            ).start()
    finally:
        db.close()


def _run_loop() -> None:
    while not _stop_event.is_set():
        try:
            _poll_once()
        except Exception:  # noqa: BLE001 -- one bad poll tick must not kill the loop
            logger.exception("Background BLAST poller iteration failed")
        _stop_event.wait(POLL_INTERVAL_SECONDS)


def start() -> None:
    """Called once from app.main's lifespan startup. A no-op if
    PAIGS_DISABLE_BACKGROUND_WORKER is set (see module docstring) or if
    already running (defensive -- FastAPI's lifespan only enters once per
    process in practice)."""
    global _poller_thread
    if os.environ.get("PAIGS_DISABLE_BACKGROUND_WORKER"):
        return
    if _poller_thread is not None and _poller_thread.is_alive():
        return
    _stop_event.clear()
    _poller_thread = threading.Thread(target=_run_loop, daemon=True)
    _poller_thread.start()


def stop() -> None:
    """Called from app.main's lifespan shutdown."""
    _stop_event.set()
