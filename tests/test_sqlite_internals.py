"""Unit tests for low-level SQLite internals lock/commit handling."""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from scribe_mcp.storage.sqlite.internals import SQLiteInternals


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
