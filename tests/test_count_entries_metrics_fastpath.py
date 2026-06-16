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
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

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
