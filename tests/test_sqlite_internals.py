"""Unit tests for low-level SQLite internals lock/commit handling."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import threading

import pytest

from scribe_mcp.storage.sqlite.internals import SQLiteInternals


class BootstrapAbort(BaseException):
    """A driver failure outside the normal Exception hierarchy."""


@pytest.mark.storage
@pytest.mark.regression
@pytest.mark.parametrize("fetch_type", [sqlite3.OperationalError, BootstrapAbort])
@pytest.mark.parametrize("cursor_close_type", [RuntimeError, BootstrapAbort])
@pytest.mark.parametrize("connection_close_fails", [False, True])
@pytest.mark.asyncio
async def test_bootstrap_fetch_error_survives_cursor_and_connection_close_errors(
    tmp_path, monkeypatch, fetch_type, cursor_close_type, connection_close_fails,
):
    internals = SQLiteInternals(tmp_path / "fetch_cleanup.db")
    primary = fetch_type("primary schema fetch failure")
    secondary = cursor_close_type("secondary cursor close failure")
    cursors = []
    connections = []
    closed_cursors = []
    closed_connections = []
    connect = sqlite3.connect

    class FailingCursor(sqlite3.Cursor):
        def fetchone(self):
            super().fetchone()
            raise primary

        def close(self):
            closed_cursors.append(self)
            super().close()
            raise secondary

    class FailingConnection(sqlite3.Connection):
        def execute(self, query, *args, **kwargs):
            if query.strip().upper().startswith("SELECT COUNT(*) FROM SQLITE_MASTER"):
                cursor = self.cursor(factory=FailingCursor)
                cursors.append(cursor)
                return cursor.execute(query, *args, **kwargs)
            return super().execute(query, *args, **kwargs)

        def close(self):
            closed_connections.append(self)
            super().close()
            if connection_close_fails:
                raise RuntimeError("tertiary connection close failure")

    def observed_connect(*args, **kwargs):
        kwargs["factory"] = FailingConnection
        conn = connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    with pytest.raises(fetch_type) as caught:
        async with internals.bootstrap_connection():
            pytest.fail("failed activation must not enter the bootstrap body")
    assert caught.value is primary
    assert closed_cursors == cursors and len(cursors) == 1
    assert closed_connections == connections and len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


@pytest.mark.storage
@pytest.mark.regression
@pytest.mark.parametrize("close_type", [RuntimeError, BootstrapAbort])
@pytest.mark.asyncio
async def test_bootstrap_cursor_close_only_failure_preserves_error_and_closes_handle(
    tmp_path, monkeypatch, close_type,
):
    internals = SQLiteInternals(tmp_path / "cursor_close_only.db")
    failure = close_type("cursor close failure")
    closed = []
    connections = []
    connect = sqlite3.connect

    class FailingCursor(sqlite3.Cursor):
        def close(self):
            super().close()
            raise failure

    class FailingConnection(sqlite3.Connection):
        def execute(self, query, *args, **kwargs):
            if query.strip().upper().startswith("SELECT COUNT(*) FROM SQLITE_MASTER"):
                return self.cursor(factory=FailingCursor).execute(query, *args, **kwargs)
            return super().execute(query, *args, **kwargs)

        def close(self):
            closed.append(self)
            return super().close()

    def observed_connect(*args, **kwargs):
        kwargs["factory"] = FailingConnection
        conn = connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    with pytest.raises(close_type) as caught:
        async with internals.bootstrap_connection():
            pytest.fail("failed cursor cleanup must not enter bootstrap body")
    assert caught.value is failure
    assert closed == connections and len(closed) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


@pytest.mark.storage
@pytest.mark.regression
@pytest.mark.parametrize("failure_type", [sqlite3.OperationalError, BootstrapAbort])
@pytest.mark.asyncio
async def test_bootstrap_original_cancellation_survives_late_activation_failure(
    tmp_path, monkeypatch, failure_type,
):
    internals = SQLiteInternals(tmp_path / "cancel_then_fail.db")
    entered = threading.Event()
    release = threading.Event()
    primary = failure_type("late schema activation failure")
    closed = []
    connections = []
    original_cancellation = []
    connect = sqlite3.connect
    bootstrap_code = SQLiteInternals.bootstrap_connection.__wrapped__.__code__

    class FailingConnection(sqlite3.Connection):
        def execute(self, query, *args, **kwargs):
            if query.strip().upper().startswith("SELECT COUNT(*) FROM SQLITE_MASTER"):
                entered.set()
                assert release.wait(5), "test did not release activation worker"
                raise primary
            return super().execute(query, *args, **kwargs)

        def close(self):
            closed.append(self)
            return super().close()

    def observed_connect(*args, **kwargs):
        kwargs["factory"] = FailingConnection
        conn = connect(*args, **kwargs)
        connections.append(conn)
        return conn

    def observe_cancellation(frame, event, arg):
        # Observe the actual delivered object without replacing asyncio's shield.
        if event == "exception" and frame.f_code is bootstrap_code:
            error = arg[1]
            if isinstance(error, asyncio.CancelledError) and not original_cancellation:
                original_cancellation.append(error)
        return observe_cancellation

    monkeypatch.setattr(sqlite3, "connect", observed_connect)

    async def bootstrap():
        async with internals.bootstrap_connection():
            pytest.fail("cancelled activation must not enter bootstrap body")

    previous_trace = sys.gettrace()
    sys.settrace(observe_cancellation)
    task = asyncio.create_task(bootstrap())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel("original cancellation")
        await asyncio.sleep(0)
        task.cancel("second cancellation")
        await asyncio.sleep(0)
        assert not task.done(), "worker ownership must be drained before returning"
        release.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert original_cancellation
        assert caught.value is original_cancellation[0]
        assert caught.value.args == ("original cancellation",)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        sys.settrace(previous_trace)
    assert closed == connections and len(closed) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


@pytest.mark.storage
@pytest.mark.regression
@pytest.mark.asyncio
async def test_bootstrap_keeper_retains_wal_without_holding_transaction(tmp_path, monkeypatch):
    internals = SQLiteInternals(tmp_path / "bootstrap_wal.db")
    connections = []
    connect = internals.connect

    def observed_connect():
        conn = connect()
        connections.append(conn)
        return conn

    monkeypatch.setattr(internals, "connect", observed_connect)
    wal = tmp_path / "bootstrap_wal.db-wal"
    async with internals.bootstrap_connection():
        keeper = connections[0]
        assert not keeper.in_transaction
        await internals.execute_many(["CREATE TABLE items (id INTEGER PRIMARY KEY)"])
        assert wal.exists(), "helper close must not checkpoint and remove bootstrap WAL"
        await internals.execute("INSERT INTO items VALUES (?)", (7,))
        assert wal.exists()
        assert not keeper.in_transaction
        assert keeper.execute("SELECT id FROM items").fetchall()[0][0] == 7
        assert not keeper.in_transaction
        # A separate observer sees each helper's commit; the keeper holds no snapshot.
        with sqlite3.connect(internals.db_path) as observer:
            assert observer.execute("SELECT id FROM items").fetchall() == [(7,)]
        observer.close()
    assert not wal.exists()
    assert internals.pool is None
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        keeper.execute("SELECT 1")


@pytest.mark.storage
@pytest.mark.regression
@pytest.mark.parametrize("close_fails", [False, True])
@pytest.mark.parametrize("base_exception", [False, True])
@pytest.mark.asyncio
async def test_bootstrap_wal_activation_failure_closes_handle(
    tmp_path, monkeypatch, close_fails, base_exception,
):
    internals = SQLiteInternals(tmp_path / "bootstrap_activation_failure.db")
    error_type = BaseException if base_exception else sqlite3.OperationalError
    failure = error_type("injected bootstrap schema read failure")
    connections = []
    closed = []
    connect = sqlite3.connect

    class FailingConnection(sqlite3.Connection):
        def execute(self, query, *args, **kwargs):
            if query.strip().upper().startswith("SELECT COUNT(*) FROM SQLITE_MASTER"):
                raise failure
            return super().execute(query, *args, **kwargs)

        def close(self):
            closed.append(self)
            super().close()
            if close_fails:
                raise RuntimeError("injected close failure")

    def observed_connect(*args, **kwargs):
        kwargs["factory"] = FailingConnection
        conn = connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", observed_connect)
    with pytest.raises(error_type) as caught:
        async with internals.bootstrap_connection():
            pytest.fail("bootstrap cannot advertise readiness after activation failure")
    assert caught.value is failure
    assert closed == connections
    assert len(closed) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


@pytest.mark.storage
@pytest.mark.regression
@pytest.mark.asyncio
async def test_bootstrap_cancellation_drains_wal_activation(tmp_path, monkeypatch):
    internals = SQLiteInternals(tmp_path / "bootstrap_activation_cancel.db")
    entered = threading.Event()
    release = threading.Event()
    connections = []
    connect = sqlite3.connect

    class BlockingConnection(sqlite3.Connection):
        def execute(self, query, *args, **kwargs):
            if query.strip().upper().startswith("SELECT COUNT(*) FROM SQLITE_MASTER"):
                entered.set()
                assert release.wait(5), "test did not release WAL activation"
            return super().execute(query, *args, **kwargs)

    def observed_connect(*args, **kwargs):
        kwargs["factory"] = BlockingConnection
        conn = connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", observed_connect)

    async def bootstrap():
        async with internals.bootstrap_connection():
            pytest.fail("cancelled opening must not enter bootstrap body")

    task = asyncio.create_task(bootstrap())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        if not entered.is_set():
            await asyncio.gather(task, return_exceptions=True)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


@pytest.mark.storage
@pytest.mark.regression
@pytest.mark.asyncio
async def test_bootstrap_preserves_explicit_transactions_and_mixed_batches(tmp_path):
    internals = SQLiteInternals(tmp_path / "bootstrap_transactions.db")
    async with internals.bootstrap_connection():
        await internals.execute_many([
            "BEGIN IMMEDIATE",
            "CREATE TABLE explicit_items (id INTEGER PRIMARY KEY)",
            "INSERT INTO explicit_items VALUES (1)",
            "COMMIT",
        ])
        with pytest.raises(sqlite3.IntegrityError):
            await internals.execute_many([
                "BEGIN IMMEDIATE",
                "CREATE TABLE rolled_back (id INTEGER)",
                "INSERT INTO explicit_items VALUES (2)",
                "INSERT INTO explicit_items VALUES (1)",
                "COMMIT",
            ])
        await internals.execute_many([
            "CREATE TABLE mixed_items (id INTEGER PRIMARY KEY)",
            "INSERT INTO mixed_items VALUES (3)",
        ])
        with sqlite3.connect(internals.db_path) as observer:
            assert observer.execute("SELECT id FROM explicit_items").fetchall() == [(1,)]
            assert observer.execute("SELECT id FROM mixed_items").fetchall() == [(3,)]
            assert observer.execute(
                "SELECT name FROM sqlite_master WHERE name='rolled_back'"
            ).fetchall() == []
        observer.close()


def test_fetchone_write_query_commits_transaction(tmp_path):
    db_path = tmp_path / "internals_commit_fetchone.db"
    internals = SQLiteInternals(db_path)

    internals.execute_sync(
        "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)",
        (),
    )

    row = internals.fetchone_sync(
        "INSERT INTO items (name) VALUES (?) RETURNING id, name",
        ("alpha",),
    )
    assert row is not None
    assert row["name"] == "alpha"

    count = internals.fetchone_sync("SELECT COUNT(*) AS c FROM items", ())
    assert count is not None
    assert count["c"] == 1


def test_fetchall_write_query_commits_transaction(tmp_path):
    db_path = tmp_path / "internals_commit_fetchall.db"
    internals = SQLiteInternals(db_path)

    internals.execute_sync(
        "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)",
        (),
    )

    rows = internals.fetchall_sync(
        "INSERT INTO items (name) VALUES (?), (?) RETURNING id, name",
        ("beta", "gamma"),
    )
    assert len(rows) == 2

    count = internals.fetchone_sync("SELECT COUNT(*) AS c FROM items", ())
    assert count is not None
    assert count["c"] == 2


def test_is_write_query_detects_cte_writes():
    assert SQLiteInternals._is_write_query(
        "WITH new_row AS (SELECT 1) INSERT INTO t(v) SELECT * FROM new_row"
    )
    assert not SQLiteInternals._is_write_query(
        "WITH nums AS (SELECT 1 AS v) SELECT v FROM nums"
    )


def test_lock_retry_retries_then_succeeds(monkeypatch, tmp_path):
    internals = SQLiteInternals(tmp_path / "retry.db")
    attempts = {"count": 0}

    def _flaky() -> int:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise sqlite3.OperationalError("database is locked")
        return 42

    monkeypatch.setattr("scribe_mcp.storage.sqlite.internals.time.sleep", lambda _s: None)

    result = internals._with_lock_retry(_flaky, query="INSERT INTO t VALUES (1)", is_write=True)
    assert result == 42
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_insert_bridge_upserts_without_unique_conflict(tmp_path):
    from scribe_mcp.storage.sqlite import SQLiteStorage

    storage = SQLiteStorage(tmp_path / "bridge_upsert.db")
    await storage.setup()
    try:
        await storage.insert_bridge(
            bridge_id="example_bridge",
            name="Example Bridge",
            version="1.0.0",
            manifest_json='{"bridge_id":"example_bridge","version":"1.0.0"}',
            state="registered",
        )
        await storage.insert_bridge(
            bridge_id="example_bridge",
            name="Example Bridge",
            version="1.0.1",
            manifest_json='{"bridge_id":"example_bridge","version":"1.0.1"}',
            state="active",
        )

        bridge = await storage.fetch_bridge("example_bridge")
        assert bridge is not None
        assert bridge["version"] == "1.0.1"
        assert bridge["state"] == "active"
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_concurrent_bridge_writes_are_serialized_without_lock_errors(tmp_path):
    from scribe_mcp.storage.sqlite import SQLiteStorage

    storage = SQLiteStorage(tmp_path / "bridge_concurrency.db")
    await storage.setup()
    try:
        async def _insert(idx: int) -> None:
            bridge_id = f"bridge_{idx:03d}"
            await storage.insert_bridge(
                bridge_id=bridge_id,
                name=f"Bridge {idx}",
                version="1.0.0",
                manifest_json=f'{{"bridge_id":"{bridge_id}","version":"1.0.0"}}',
                state="registered",
            )

        await asyncio.gather(*[_insert(i) for i in range(40)])

        bridges = await storage.list_bridges()
        assert len(bridges) == 40
    finally:
        await storage.close()
