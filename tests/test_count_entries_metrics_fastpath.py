"""Tests for the scribe_metrics fast path in count_entries.

Acceptance criteria (p0-c4):
  - Empty/None filters -> uses scribe_metrics.total_entries (no COUNT(*) issued)
  - log_type filter -> falls through to COUNT(*) (correctness preserved)
  - No metrics row for project -> falls through to COUNT(*) (no spurious 0)

Strategy: monkeypatch the fetchone function to spy on SQL issued; assert that
COUNT(*) is (or is not) present in the SQL text depending on the case.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, call, patch

import asyncpg
import pytest

from integration.storage.conftest import backend

from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.storage.sqlite import entries as entry_ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(project_id: int = 1, name: str = "test_proj") -> ProjectRecord:
    return ProjectRecord(
        id=project_id,
        name=name,
        repo_root="/tmp/test",
        progress_log_path="/tmp/test/log.md",
    )


async def _insert_entries(storage: SQLiteStorage, project: ProjectRecord, n: int) -> None:
    """Insert n log entries, each with a unique id."""
    for i in range(n):
        ts = datetime(2026, 1, 1, 0, 0, i % 60, tzinfo=timezone.utc)
        await storage.insert_entry(
            entry_id=str(uuid.uuid4()),
            project=project,
            ts=ts,
            emoji="ℹ️",
            agent="test-agent",
            message=f"entry {i}",
            meta={},
            raw_line=f"entry {i}",
            sha256=str(uuid.uuid4()),
            log_type="progress",
        )


# ---------------------------------------------------------------------------
# Unit tests — spy on SQL via monkeypatched fetchone
# ---------------------------------------------------------------------------

class TestMetricsCounterForFilters:
    """Unit-test _metrics_counter_for_filters directly."""

    def test_none_filters_returns_total_entries(self) -> None:
        result = entry_ops._metrics_counter_for_filters(None)
        assert result == "total_entries"

    def test_empty_dict_returns_total_entries(self) -> None:
        result = entry_ops._metrics_counter_for_filters({})
        assert result == "total_entries"

    def test_log_type_filter_returns_none(self) -> None:
        result = entry_ops._metrics_counter_for_filters({"log_type": ["progress"]})
        assert result is None

    def test_agent_filter_returns_none(self) -> None:
        result = entry_ops._metrics_counter_for_filters({"agent": "bob"})
        assert result is None

    def test_priority_filter_returns_none(self) -> None:
        result = entry_ops._metrics_counter_for_filters({"priority": ["high"]})
        assert result is None

    def test_category_filter_returns_none(self) -> None:
        result = entry_ops._metrics_counter_for_filters({"category": ["bug"]})
        assert result is None

    def test_min_confidence_filter_returns_none(self) -> None:
        result = entry_ops._metrics_counter_for_filters({"min_confidence": 0.5})
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests — real SQLite DB, spy on SQL text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_filter_uses_metrics_not_count_star(tmp_path: Path) -> None:
    """Empty filter: COUNT(*) must NOT be issued; scribe_metrics row is used."""
    storage = SQLiteStorage(tmp_path / "test.db")
    await storage.setup()

    project = await storage.upsert_project(
        name="fastpath_test",
        repo_root=str(tmp_path),
        progress_log_path=str(tmp_path / "log.md"),
    )
    # Insert 3 entries so metrics row is populated
    await _insert_entries(storage, project, 3)

    # Spy on fetchone: track every SQL string issued
    sql_calls: List[str] = []
    original_fetchone = storage._fetchone

    async def spy_fetchone(sql: str, params: tuple) -> Any:
        sql_calls.append(sql.strip())
        return await original_fetchone(sql, params)

    with patch.object(storage, "_fetchone", side_effect=spy_fetchone):
        count = await storage.count_entries(project, filters=None)

    assert count == 3, f"Expected 3 entries, got {count}"

    # Verify no COUNT(*) was issued
    count_star_calls = [s for s in sql_calls if "COUNT(*)" in s.upper()]
    assert count_star_calls == [], (
        f"Expected no COUNT(*) SQL for empty filter, but got: {count_star_calls}"
    )

    # Verify scribe_metrics was queried
    metrics_calls = [s for s in sql_calls if "scribe_metrics" in s.lower()]
    assert metrics_calls, "Expected a query against scribe_metrics for fast path"


@pytest.mark.asyncio
async def test_log_type_filter_still_uses_count_star(tmp_path: Path) -> None:
    """log_type filter: must fall through to COUNT(*) and return correct count."""
    storage = SQLiteStorage(tmp_path / "test.db")
    await storage.setup()

    project = await storage.upsert_project(
        name="fallthrough_test",
        repo_root=str(tmp_path),
        progress_log_path=str(tmp_path / "log.md"),
    )
    # Insert 4 "progress" entries and 2 "doc_updates" entries
    for i in range(4):
        ts = datetime(2026, 1, 1, 0, 0, i, tzinfo=timezone.utc)
        await storage.insert_entry(
            entry_id=str(uuid.uuid4()),
            project=project,
            ts=ts,
            emoji="ℹ️",
            agent="test-agent",
            message=f"progress {i}",
            meta={},
            raw_line=f"prog {i}",
            sha256=str(uuid.uuid4()),
            log_type="progress",
        )
    for i in range(2):
        ts = datetime(2026, 1, 1, 0, 1, i, tzinfo=timezone.utc)
        await storage.insert_entry(
            entry_id=str(uuid.uuid4()),
            project=project,
            ts=ts,
            emoji="ℹ️",
            agent="test-agent",
            message=f"doc {i}",
            meta={},
            raw_line=f"doc {i}",
            sha256=str(uuid.uuid4()),
            log_type="doc_updates",
        )

    sql_calls: List[str] = []
    original_fetchone = storage._fetchone

    async def spy_fetchone(sql: str, params: tuple) -> Any:
        sql_calls.append(sql.strip())
        return await original_fetchone(sql, params)

    with patch.object(storage, "_fetchone", side_effect=spy_fetchone):
        count = await storage.count_entries(
            project, filters={"log_type": ["progress"]}
        )

    assert count == 4, f"Expected 4 progress entries, got {count}"

    # Verify COUNT(*) WAS issued for filtered call
    count_star_calls = [s for s in sql_calls if "COUNT(*)" in s.upper()]
    assert count_star_calls, (
        "Expected COUNT(*) SQL for log_type filter, but none was issued"
    )


@pytest.mark.asyncio
async def test_no_metrics_row_falls_through_to_count_star(tmp_path: Path) -> None:
    """No scribe_metrics row: must fall through to COUNT(*), not return 0 spuriously."""
    storage = SQLiteStorage(tmp_path / "test.db")
    await storage.setup()

    project = await storage.upsert_project(
        name="no_metrics_test",
        repo_root=str(tmp_path),
        progress_log_path=str(tmp_path / "log.md"),
    )
    # Do NOT insert any entries — no metrics row exists

    sql_calls: List[str] = []
    original_fetchone = storage._fetchone

    async def spy_fetchone(sql: str, params: tuple) -> Any:
        sql_calls.append(sql.strip())
        return await original_fetchone(sql, params)

    with patch.object(storage, "_fetchone", side_effect=spy_fetchone):
        count = await storage.count_entries(project, filters=None)

    # Correct count is 0 (no entries), verified via COUNT(*)
    assert count == 0

    # Verify COUNT(*) was issued as fallback (metrics row absent)
    count_star_calls = [s for s in sql_calls if "COUNT(*)" in s.upper()]
    assert count_star_calls, (
        "Expected COUNT(*) fallback when no metrics row exists"
    )


@pytest.mark.asyncio
async def test_empty_filter_count_matches_count_star(tmp_path: Path) -> None:
    """Correctness: metrics fast path and COUNT(*) agree for various entry counts."""
    storage = SQLiteStorage(tmp_path / "test.db")
    await storage.setup()

    project = await storage.upsert_project(
        name="correctness_test",
        repo_root=str(tmp_path),
        progress_log_path=str(tmp_path / "log.md"),
    )
    await _insert_entries(storage, project, 7)

    # Fast path result
    fast_count = await storage.count_entries(project, filters=None)

    # Force COUNT(*) path by using a filter that doesn't apply any restriction
    # but still triggers the fallback (agent filter with a value that matches all)
    # Actually: use a known filter (log_type=progress) which we know hits COUNT(*)
    # and compare total from the DB directly.
    direct_count = await storage.count_entries(
        project, filters={"log_type": ["progress"]}
    )

    assert fast_count == 7
    assert direct_count == 7  # all entries are progress log_type


# Real-backend regressions: do not replace insert_entry, its executor, or commits.
async def _metric_project(storage, kind, root):
    if kind == "postgres":
        assert storage._conformance_isolated_db, "Metric faults require a disposable database"
    project = await storage.upsert_project(
        name=f"metric_{uuid.uuid4().hex}", repo_root=str(root),
        progress_log_path=str(root / "PROGRESS_LOG.md"),
    )
    if kind == "postgres":
        storage._conformance_projects.append(project.name)
    return project


def _metric_entry(project, agent, *, emoji="✅", **overrides):
    message = "atomic metric entry"
    values = dict(
        entry_id=uuid.uuid4().hex, project=project,
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc), emoji=emoji,
        agent=agent, message=message, raw_line=message,
        sha256=hashlib.sha256(message.encode()).hexdigest(),
        meta={"category": "regression"}, log_type="progress",
    )
    values.update(overrides)
    return values


async def _metric_row(storage, kind, sql, project):
    if kind == "sqlite":
        return await storage._fetchone(sql.replace("$1", "?"), (project.id,))
    return await storage._fetchrow(sql, project.id)


async def _metric_state(storage, kind, project):
    row = await _metric_row(
        storage, kind,
        "SELECT total_entries, success_count, warn_count, error_count, last_update "
        "FROM scribe_metrics WHERE project_id = $1", project,
    )
    return dict(row) if row is not None else None


async def _assert_metric_counts(storage, kind, project, expected):
    # COUNT(*) is an independent physical-row observation, not the metrics fast path.
    physical = await _metric_row(
        storage, kind,
        "SELECT COUNT(*) AS total_entries, "
        "COALESCE(SUM(CASE WHEN emoji = '✅' THEN 1 ELSE 0 END), 0) AS success_count, "
        "COALESCE(SUM(CASE WHEN emoji = '⚠️' THEN 1 ELSE 0 END), 0) AS warn_count, "
        "COALESCE(SUM(CASE WHEN emoji = '❌' THEN 1 ELSE 0 END), 0) AS error_count "
        "FROM scribe_entries WHERE project_id = $1", project,
    )
    keys = ("total_entries", "success_count", "warn_count", "error_count")
    assert tuple(physical[key] for key in keys) == expected
    state = await _metric_state(storage, kind, project)
    observed = tuple(state[key] for key in keys) if state else (0, 0, 0, 0)
    assert observed == expected
    assert await storage.count_entries(project=project) == expected[0]
    return state


async def _metric_sql(storage, kind, sql):
    if kind == "sqlite":
        await storage._execute(sql, ())
    else:
        await storage._execute(sql)


@asynccontextmanager
async def _metric_trigger(storage, kind, project, *, sqlite_body, postgres_body):
    """Real SQL trigger at the row/metrics boundary, only in the fixture DB."""
    name = f"metric_cut_{uuid.uuid4().hex}"
    if kind == "sqlite":
        names = [f"{name}_insert", f"{name}_update"]
        for trigger, operation in zip(names, ("INSERT", "UPDATE")):
            await _metric_sql(
                storage, kind,
                f"CREATE TRIGGER {trigger} BEFORE {operation} ON scribe_metrics "
                f"WHEN NEW.project_id = {int(project.id)} BEGIN {sqlite_body}; END",
            )
    else:
        await _metric_sql(
            storage, kind,
            f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN {postgres_body}; RETURN NEW; END; $$",
        )
        await _metric_sql(
            storage, kind,
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE ON scribe_metrics "
            f"FOR EACH ROW WHEN (NEW.project_id = {int(project.id)}) "
            f"EXECUTE FUNCTION {name}()",
        )
    try:
        yield
    finally:
        if kind == "sqlite":
            for trigger in names:
                await _metric_sql(storage, kind, f"DROP TRIGGER {trigger}")
        else:
            await _metric_sql(storage, kind, f"DROP TRIGGER {name} ON scribe_metrics")
            await _metric_sql(storage, kind, f"DROP FUNCTION {name}()")


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.storage
class TestInsertMetricAtomicity:
    @pytest.mark.parametrize(
        "emoji,expected", [("✅", (1, 1, 0, 0)), ("⚠️", (1, 0, 1, 0)),
                           ("❌", (1, 0, 0, 1)), ("ℹ️", (1, 0, 0, 0))],
    )
    async def test_first_insert_tracks_only_its_emoji_category(
        self, backend, tmp_path, test_agent, emoji, expected,
    ):
        storage, kind = backend
        project = await _metric_project(storage, kind, tmp_path)
        entry = _metric_entry(project, test_agent, emoji=emoji)
        before = datetime.now(timezone.utc)
        assert await storage.insert_entry(**entry) is None  # existing public API
        state = await _assert_metric_counts(storage, kind, project, expected)
        updated = state["last_update"]
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        assert before <= updated <= datetime.now(timezone.utc)
        rows = await storage.fetch_recent_entries(project=project, limit=2)
        assert [(r["id"], r["message"], r["category"]) for r in rows] == [
            (entry["entry_id"], entry["message"], "regression")
        ]

    @pytest.mark.parametrize("unequal", [False, True], ids=["identical", "unequal"])
    async def test_duplicate_id_is_legacy_noop_including_metrics_and_last_update(
        self, backend, tmp_path, test_agent, unequal,
    ):
        storage, kind = backend
        project = await _metric_project(storage, kind, tmp_path)
        entry = _metric_entry(project, test_agent)
        await storage.insert_entry(**entry)
        before = await _assert_metric_counts(storage, kind, project, (1, 1, 0, 0))
        original_rows = await storage.fetch_recent_entries(project=project, limit=2)
        duplicate = dict(entry)
        if unequal:
            duplicate.update(emoji="⚠️", message="different", raw_line="different",
                             meta={"category": "other"}, category="other",
                             log_type="doc_updates", sha256="different")
        assert await storage.insert_entry(**duplicate) is None
        assert await storage.fetch_recent_entries(project=project, limit=2) == original_rows
        after = await _metric_state(storage, kind, project)
        assert after == before, "Ignored IDs must not change counters or last_update"
        await _assert_metric_counts(storage, kind, project, (1, 1, 0, 0))

    async def test_different_ids_with_same_content_each_count_once(
        self, backend, tmp_path, test_agent,
    ):
        storage, kind = backend
        project = await _metric_project(storage, kind, tmp_path)
        first = _metric_entry(project, test_agent, emoji="❌")
        second = dict(first, entry_id=uuid.uuid4().hex)
        await storage.insert_entry(**first)
        await storage.insert_entry(**second)
        await _assert_metric_counts(storage, kind, project, (2, 0, 0, 2))

    async def test_sibling_connections_duplicate_race_has_one_metric_winner(
        self, backend, tmp_path, test_agent,
    ):
        storage, kind = backend
        project = await _metric_project(storage, kind, tmp_path)
        sibling = SQLiteStorage(storage._path) if kind == "sqlite" else storage
        if sibling is not storage:
            await sibling.setup()
        entry = _metric_entry(project, test_agent, emoji="⚠️")
        ready = [asyncio.Event(), asyncio.Event()]
        start = asyncio.Event()

        async def insert(writer, index):
            ready[index].set()
            await start.wait()
            return await writer.insert_entry(**entry)

        tasks = [asyncio.create_task(insert(writer, i))
                 for i, writer in enumerate((storage, sibling))]
        try:
            await asyncio.wait_for(asyncio.gather(*(event.wait() for event in ready)), 5)
            start.set()
            assert await asyncio.wait_for(asyncio.gather(*tasks), 15) == [None, None]
        finally:
            start.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            if sibling is not storage:
                await sibling.close()
        rows = await storage.fetch_recent_entries(project=project, limit=3)
        assert [row["id"] for row in rows] == [entry["entry_id"]]
        await _assert_metric_counts(storage, kind, project, (1, 0, 1, 0))

    @pytest.mark.parametrize("seeded", [False, True], ids=["new_metrics", "existing_metrics"])
    async def test_metric_sql_failure_rolls_back_entry_then_retry_has_one_effect(
        self, backend, tmp_path, test_agent, seeded,
    ):
        storage, kind = backend
        project = await _metric_project(storage, kind, tmp_path)
        if seeded:
            await storage.insert_entry(**_metric_entry(project, test_agent, emoji="⚠️"))
        before = await _metric_state(storage, kind, project)
        entry = _metric_entry(project, test_agent)
        async with _metric_trigger(
            storage, kind, project,
            sqlite_body="SELECT RAISE(ABORT, 'metric fault')",
            postgres_body="RAISE EXCEPTION 'metric fault'",
        ):
            with pytest.raises((sqlite3.IntegrityError, asyncpg.RaiseError), match="metric fault"):
                await asyncio.wait_for(storage.insert_entry(**entry), 10)
            failed_rows = await storage.fetch_recent_entries(project=project, limit=3)
            failed_metrics = await _metric_state(storage, kind, project)
        # Always run the retry, even on the broken baseline; assert both observations.
        await asyncio.wait_for(storage.insert_entry(**entry), 10)
        await _assert_metric_counts(storage, kind, project, (1 + int(seeded), 1, int(seeded), 0))
        assert entry["entry_id"] not in [row["id"] for row in failed_rows], (
            "Metric SQL failure must roll back the physical entry"
        )
        assert failed_metrics == before, "Failure must preserve counters and last_update"

    async def test_cancelled_metric_write_drains_worker_and_returns_clean_connection(
        self, backend, tmp_path, test_agent,
    ):
        storage, kind = backend
        project = await _metric_project(storage, kind, tmp_path)
        entry = _metric_entry(project, test_agent)
        early_return = False
        if kind == "sqlite":
            entered, release, finished = threading.Event(), threading.Event(), threading.Event()

            def cut():
                entered.set()
                try:
                    if not release.wait(10):
                        raise RuntimeError("metric cut release timed out")
                    # Real-driver failure after cancellation, not a mocked executor.
                    raise sqlite3.IntegrityError("cancel metric cut")
                finally:
                    finished.set()

            # Register the trigger function on every real pooled connection, without
            # replacing pool/execute/transaction behavior or adding a storage engine.
            pool = storage._pool
            connections = [pool.acquire(timeout=2) for _ in range(pool.stats()["max_size"])]
            try:
                for connection in connections:
                    connection.create_function("metric_cancel_cut", 0, cut)
            finally:
                for connection in connections:
                    pool.release(connection)
            try:
                async with _metric_trigger(
                    storage, kind, project, sqlite_body="SELECT metric_cancel_cut()",
                    postgres_body="RAISE EXCEPTION 'unused'",
                ):
                    task = asyncio.create_task(storage.insert_entry(**entry))
                    try:
                        assert await asyncio.to_thread(entered.wait, 5), "Metric SQL cut was not reached"
                        task.cancel()
                        done, _ = await asyncio.wait([task], timeout=0.1)
                        early_return = bool(done)
                    finally:
                        release.set()
                        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 10)
                        assert await asyncio.to_thread(finished.wait, 5)
                    assert task.cancelled()
            finally:
                release.set()
                for connection in connections:
                    connection.create_function("metric_cancel_cut", 0, None)
        else:
            # Server-side advisory lock proves cancellation occurs inside metric SQL.
            pool = await storage._ensure_pool()
            async with pool.acquire() as blocker:
                key = int(uuid.uuid4().hex[:7], 16)
                await blocker.execute("SELECT pg_advisory_lock($1)", key)
                try:
                    async with _metric_trigger(
                        storage, kind, project, sqlite_body="SELECT 1",
                        postgres_body=f"PERFORM pg_advisory_xact_lock({key})",
                    ):
                        task = asyncio.create_task(storage.insert_entry(**entry))
                        try:
                            async def blocked():
                                while not task.done():
                                    waiting = await blocker.fetchval(
                                        "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE "
                                        "locktype = 'advisory' AND objid = $1 AND NOT granted)", key,
                                    )
                                    if waiting:
                                        return
                                    await asyncio.sleep(0.01)
                                raise AssertionError("Metric lock was not reached")
                            await asyncio.wait_for(blocked(), 5)
                            task.cancel()
                            with pytest.raises(asyncio.CancelledError):
                                await asyncio.wait_for(task, 10)
                        finally:
                            if not task.done():
                                task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                finally:
                    await blocker.execute("SELECT pg_advisory_unlock($1)", key)
        cancelled_rows = await storage.fetch_recent_entries(project=project, limit=3)
        cancelled_metrics = await _metric_state(storage, kind, project)
        # Reuse the connection and retry the original ID after the worker is gone.
        await asyncio.wait_for(storage.insert_entry(**entry), 10)
        await _assert_metric_counts(storage, kind, project, (1, 1, 0, 0))
        assert (len(cancelled_rows), cancelled_metrics, early_return) == (0, None, False), (
            "Cancellation must leave no partial row/metrics and retain unfinished worker custody"
        )

    @pytest.mark.parametrize("seeded", [False, True], ids=["empty", "populated"])
    async def test_tool_logs_change_neither_entries_nor_metrics(
        self, backend, tmp_path, test_agent, seeded,
    ):
        storage, kind = backend
        project = await _metric_project(storage, kind, tmp_path)
        if seeded:
            await storage.insert_entry(**_metric_entry(project, test_agent))
        before = await _metric_state(storage, kind, project)
        rows = await storage.fetch_recent_entries(project=project, limit=3)
        ignored = _metric_entry(project, test_agent, emoji="❌", log_type="tool_logs")
        assert await storage.insert_entry(**ignored) is None
        assert await storage.fetch_recent_entries(project=project, limit=3) == rows
        assert await _metric_state(storage, kind, project) == before
        await _assert_metric_counts(storage, kind, project, (int(seeded), int(seeded), 0, 0))
