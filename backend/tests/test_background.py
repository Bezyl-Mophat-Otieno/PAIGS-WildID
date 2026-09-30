"""app.orchestration.background -- the DB-backed poller behind blast.mode=
"remote"'s background execution.

_poll_once() is tested directly here, not the real start()/stop() thread
lifecycle -- that's thin plumbing (spin up a thread, sleep, repeat) not
worth its own test; the actual logic worth verifying is "does one poll
tick find the right rows and dispatch exactly one worker per run,
without double-dispatching a run that's already in flight." Real network/
BLAST+ calls are avoided entirely by monkeypatching
app.orchestration.execute.resume_run_after_blast, exactly like
test_orchestration.py's own remote-mode tests do for the level below this
one.
"""
import threading
import time

from app.models.stage import Stage
from app.orchestration import background


def _make_run_with_blast_stage(db_session, *, status) -> str:
    """Returns the run's id as a plain string, not the ORM object --
    _poll_once()'s own db.close() (against whatever session SessionLocal
    is monkeypatched to return, including this fixture's shared
    db_session in these tests) would otherwise leave a `Run` object
    detached, and any later attribute access (even `.id`) triggers a
    refresh against a session that's no longer open."""
    from tests.test_orchestration import _make_run

    run = _make_run(db_session, config_overrides={})
    run_id = run.id
    stage = Stage(
        run_id=run_id,
        stage_type="blast",
        status=status,
        started_at=None,
        completed_at=None,
        attempt_number=1,
        stage_metadata={"thresholds": {"mode": "remote"}, "effective": {}},
    )
    db_session.add(stage)
    db_session.commit()
    return run_id


class TestPollOnce:
    def test_dispatches_a_worker_thread_for_a_running_blast_stage(
        self, db_session, monkeypatch
    ):
        run_id = _make_run_with_blast_stage(db_session, status="running")

        processed = []
        monkeypatch.setattr(background, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(
            background, "_process_run", lambda run_id: processed.append(run_id)
        )

        background._poll_once()

        # _poll_once dispatches via a real thread -- give it a moment.
        deadline = time.time() + 2
        while not processed and time.time() < deadline:
            time.sleep(0.02)

        assert processed == [run_id]

    def test_ignores_stages_that_are_not_running(self, db_session, monkeypatch):
        _make_run_with_blast_stage(db_session, status="completed")

        processed = []
        monkeypatch.setattr(background, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(
            background, "_process_run", lambda run_id: processed.append(run_id)
        )

        background._poll_once()
        time.sleep(0.1)

        assert processed == []

    def test_does_not_double_dispatch_a_run_already_in_flight(self, db_session, monkeypatch):
        run_id = _make_run_with_blast_stage(db_session, status="running")

        started = threading.Event()
        release = threading.Event()
        call_count = {"n": 0}

        def _slow_process(run_id):
            call_count["n"] += 1
            started.set()
            release.wait(timeout=2)

        monkeypatch.setattr(background, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(background, "_process_run", _slow_process)

        background._poll_once()
        assert started.wait(timeout=2)

        # A second poll tick while the first dispatch is still "in
        # flight" (holding release) must not start a second worker for
        # the same run.
        background._poll_once()
        release.set()
        time.sleep(0.1)

        assert call_count["n"] == 1

        with background._in_flight_lock:
            background._in_flight.discard(run_id)


class TestProcessRun:
    def test_calls_resume_run_after_blast_and_clears_in_flight_on_success(
        self, db_session, monkeypatch
    ):
        import app.orchestration.execute as execute_module

        run_id = _make_run_with_blast_stage(db_session, status="running")
        with background._in_flight_lock:
            background._in_flight.add(run_id)

        called = []
        monkeypatch.setattr(background, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(
            execute_module, "resume_run_after_blast", lambda run_id, db: called.append(run_id)
        )

        background._process_run(run_id)

        assert called == [run_id]
        with background._in_flight_lock:
            assert run_id not in background._in_flight

    def test_clears_in_flight_even_if_resume_raises(self, db_session, monkeypatch):
        import app.orchestration.execute as execute_module

        run_id = _make_run_with_blast_stage(db_session, status="running")
        with background._in_flight_lock:
            background._in_flight.add(run_id)

        def _raise(run_id, db):
            raise RuntimeError("boom")

        monkeypatch.setattr(background, "SessionLocal", lambda: db_session)
        monkeypatch.setattr(execute_module, "resume_run_after_blast", _raise)

        background._process_run(run_id)  # must not raise

        with background._in_flight_lock:
            assert run_id not in background._in_flight


class TestStartStop:
    def test_start_is_a_no_op_when_disabled_via_env_var(self, monkeypatch):
        monkeypatch.setenv("PAIGS_DISABLE_BACKGROUND_WORKER", "1")
        monkeypatch.setattr(background, "_poller_thread", None)

        background.start()

        assert background._poller_thread is None
