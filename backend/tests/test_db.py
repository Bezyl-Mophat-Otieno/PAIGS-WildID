"""app.db's connect-time SQLite PRAGMA setup.

WAL mode requires shared-memory primitives some filesystems don't
support (notably some Docker bind-mount configurations -- see
app.db's own module docstring for the real incident this guards
against: PRAGMA journal_mode=WAL itself raised sqlite3.OperationalError
on every single connection over one such deployment, which is strictly
worse than the problem WAL mode was meant to help with). These tests
exercise _set_sqlite_pragmas directly against a fake DBAPI connection,
not a real one -- reproducing a filesystem that genuinely can't support
WAL isn't practical to set up in a normal test environment.
"""
import sqlite3

from app.db import _set_sqlite_pragmas


class _FakeCursor:
    def __init__(self, *, fail_on=()):
        self.fail_on = fail_on
        self.executed = []
        self.closed = False

    def execute(self, sql):
        self.executed.append(sql)
        if any(sql.startswith(prefix) for prefix in self.fail_on):
            raise sqlite3.OperationalError("disk I/O error")

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self, *, fail_on=()):
        self._cursor = _FakeCursor(fail_on=fail_on)

    def cursor(self):
        return self._cursor


class TestSetSqlitePragmas:
    def test_sets_wal_mode_and_busy_timeout_when_both_succeed(self):
        conn = _FakeConnection()

        _set_sqlite_pragmas(conn, None)

        assert "PRAGMA journal_mode=WAL" in conn._cursor.executed
        assert "PRAGMA busy_timeout=30000" in conn._cursor.executed
        assert conn._cursor.closed

    def test_falls_back_gracefully_when_wal_mode_is_unsupported(self):
        """The real incident: PRAGMA journal_mode=WAL itself raised
        sqlite3.OperationalError('disk I/O error') on a filesystem that
        can't support WAL's shared-memory requirement -- this must not
        propagate and break every connection the engine ever opens."""
        conn = _FakeConnection(fail_on=("PRAGMA journal_mode",))

        _set_sqlite_pragmas(conn, None)  # must not raise

        assert "PRAGMA journal_mode=WAL" in conn._cursor.executed

    def test_busy_timeout_still_applied_even_when_wal_mode_fails(self):
        conn = _FakeConnection(fail_on=("PRAGMA journal_mode",))

        _set_sqlite_pragmas(conn, None)

        assert "PRAGMA busy_timeout=30000" in conn._cursor.executed
        assert conn._cursor.closed
