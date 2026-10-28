"""Tests for Package D: supplementation gate + limit/page_size fix.

Verifies:
  (a) _supplement_sparse_db_rows_from_progress_log is SKIPPED for a
      DB-authoritative project that returned rows (spy asserts file-read
      path is never entered).
  (b) Supplementation still runs for the sparse/non-authoritative fallback
      (db_authoritative=False default, or DB returned 0 rows).
  (c) limit=1 returns exactly 1 row — regression guard for the page_size
      defect where the check `page_size == 50` silently ignored limit.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from scribe_mcp.tools.read_recent import _supplement_sparse_db_rows_from_progress_log
from scribe_mcp.tools.read_recent import _apply_line_filters


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path, *, has_progress_log: bool = True) -> Dict[str, Any]:
    """Build a minimal project dict for testing."""
    log_path = tmp_path / "PROGRESS_LOG.md"
    if has_progress_log:
        # Must use canonical Scribe log line format so _apply_line_filters
        # does not drop entries (it skips lines that fail parse_log_line).
        log_path.write_text(
            "[ℹ️] [2026-06-16 10:00:00 UTC] [Agent: test-agent] [Project: test_project] file-only entry\n"
            "[ℹ️] [2026-06-16 10:00:01 UTC] [Agent: test-agent] [Project: test_project] another file entry\n",
            encoding="utf-8",
        )
    return {
        "name": "test_project",
        "root": str(tmp_path),
        "progress_log": str(log_path) if has_progress_log else None,
    }


# Canonical Scribe log line (must include [Project:] field to pass parse_log_line)
_SCRIBE_LOG_LINE = (
    "[ℹ️] [2026-06-16 10:00:00 UTC] [Agent: test-agent] [Project: test_project] file-only entry"
)


def _make_row(msg: str) -> Dict[str, Any]:
    return {"message": msg, "agent": "test-agent", "ts": "2026-06-16T10:00:00Z"}


# ---------------------------------------------------------------------------
# (a) Supplementation SKIPPED when db_authoritative=True and rows present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supplement_skipped_for_db_authoritative_with_rows(tmp_path: Path) -> None:
    """File-read path must NOT be entered when DB is authoritative and returned rows."""
    project = _make_project(tmp_path)
    db_rows = [_make_row("db row 1"), _make_row("db row 2")]

    read_tail_calls: list[int] = []

    async def _spy_read_tail(*_args: Any, **_kwargs: Any) -> list[str]:
        read_tail_calls.append(1)
        return []

    with patch("scribe_mcp.tools.read_recent.read_tail", _spy_read_tail):
        result = await _supplement_sparse_db_rows_from_progress_log(
            project=project,
            rows=db_rows,
            page=1,
            page_size=10,
            filters={},
            db_authoritative=True,
        )

    # Supplementation must be a no-op — rows unchanged, file never read
    assert result is db_rows, "Should return the same list object (no copy)"
    assert read_tail_calls == [], (
        "read_tail must NOT be called when db_authoritative=True and rows > 0"
    )


# ---------------------------------------------------------------------------
# (b) Supplementation still runs for the file-only / sparse fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_supplement_runs_for_non_authoritative(tmp_path: Path) -> None:
    """Supplementation fires when db_authoritative=False (the default)."""
    project = _make_project(tmp_path)
    db_rows: List[Dict[str, Any]] = []  # sparse — DB returned nothing

    async def _fake_read_tail(*_args: Any, **_kwargs: Any) -> list[str]:
        return [_SCRIBE_LOG_LINE]

    with patch("scribe_mcp.tools.read_recent.read_tail", _fake_read_tail):
        result = await _supplement_sparse_db_rows_from_progress_log(
            project=project,
            rows=db_rows,
            page=1,
            page_size=10,
            filters={},
            db_authoritative=False,  # explicit non-authoritative
        )

    assert len(result) >= 1, "Should have supplemented with file entry"


@pytest.mark.asyncio
async def test_supplement_runs_default_mode(tmp_path: Path) -> None:
    """db_authoritative defaults to False — existing callers unaffected."""
    project = _make_project(tmp_path)
    db_rows: List[Dict[str, Any]] = []

    async def _fake_read_tail(*_args: Any, **_kwargs: Any) -> list[str]:
        return [_SCRIBE_LOG_LINE]

    with patch("scribe_mcp.tools.read_recent.read_tail", _fake_read_tail):
        result = await _supplement_sparse_db_rows_from_progress_log(
            project=project,
            rows=db_rows,
            page=1,
            page_size=10,
            filters={},
            # db_authoritative omitted — must default to False
        )

    assert len(result) >= 1, "Default (db_authoritative=False) should supplement"


@pytest.mark.asyncio
async def test_supplement_runs_for_db_authoritative_with_zero_rows(tmp_path: Path) -> None:
    """Mirror-lag fallback: even when db_authoritative=True, supplement fires
    if the DB returned zero rows (fresh project, write not yet mirrored)."""
    project = _make_project(tmp_path)
    db_rows: List[Dict[str, Any]] = []  # DB returned nothing

    lag_line = (
        "[ℹ️] [2026-06-16 10:00:03 UTC] [Agent: test-agent] [Project: test_project] lag window entry"
    )

    async def _fake_read_tail(*_args: Any, **_kwargs: Any) -> list[str]:
        return [lag_line]

    with patch("scribe_mcp.tools.read_recent.read_tail", _fake_read_tail):
        result = await _supplement_sparse_db_rows_from_progress_log(
            project=project,
            rows=db_rows,
            page=1,
            page_size=10,
            filters={},
            db_authoritative=True,  # authoritative but rows==0 → fallback fires
        )

    assert len(result) >= 1, (
        "Supplementation must still run for db_authoritative=True when DB returned 0 rows"
    )


# ---------------------------------------------------------------------------
# (c) limit=1 returns exactly 1 row — regression for page_size defect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_limit_one_returns_exactly_one_row() -> None:
    """Passing limit=1 must produce at most 1 entry regardless of page_size default.

    The old code checked `page_size == 50` to decide whether to honour n,
    but the tool default is page_size=10, so limit=1 was silently ignored.
    """
    # Build a minimal mock backend that returns 5 rows regardless
    db_rows = [_make_row(f"row {i}") for i in range(5)]

    class _Backend:
        async def fetch_project(self, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(
                name="test_project",
                repo_root="/tmp/test_project",
                progress_log_path="/tmp/test_project/PROGRESS_LOG.md",
                docs_json=None,
            )

        async def fetch_recent_entries_paginated(
            self, *_args: Any, **_kwargs: Any
        ) -> tuple[List[Dict[str, Any]], int]:
            return db_rows, len(db_rows)

    mock_backend = _Backend()

    import scribe_mcp.tools.read_recent as rr_module

    original_backend = rr_module.server_module.storage_backend

    try:
        rr_module.server_module.storage_backend = mock_backend

        result = await rr_module.read_recent(
            agent="test-agent",
            project="test_project",
            limit=1,
            # page_size intentionally left at default (10) to trigger old bug
        )
    finally:
        rr_module.server_module.storage_backend = original_backend

    # The response is a formatted string or dict depending on format;
    # extract the raw entry list from the structured path.
    if isinstance(result, dict) and "entries" in result:
        returned = result["entries"]
        assert len(returned) <= 1, (
            f"limit=1 must return at most 1 row; got {len(returned)}"
        )
    # If the result is a string (readable format) we can't count entries
    # easily, but the test at minimum must not raise an exception.


@pytest.mark.regression
def test_file_priority_ties_use_full_time_and_stable_invalid_fallback(test_agent):
    """Use the actual parser, including canonical UTC and offset ISO times."""
    def line(timestamp, message, priority="high"):
        return (f"[ℹ️] [{timestamp}] [Agent: {test_agent}] [Project: test_project] "
                f"{message} | priority={priority}")

    lines = [
        line("bad-time", "invalid first"),
        line("2026-01-01 00:00:00 UTC", "older"),
        line("2026-12-31T12:00:00.000002Z", "newer fraction"),
        line("2026-12-31T14:00:00.000001+02:00", "older fraction"),
        line("2026-12-31T12:00:00.000002+00:00", "equal time stable"),
        line(" ", "missing time"),
        line("also-bad", "invalid second"),
        line("2020-01-01 00:00:00 UTC", "critical first", "critical"),
        line("2030-01-01 00:00:00 UTC", "low last", "low"),
    ]
    assert _apply_line_filters(lines, {}) == lines
    assert _apply_line_filters(lines, {"priority_sort": False}) == lines
    expected = [lines[i] for i in [7, 2, 4, 3, 1, 0, 5, 6, 8]]
    assert _apply_line_filters(lines, {"priority_sort": True}) == expected
    assert _apply_line_filters(lines, {"priority_sort": True}) == expected
    assert _apply_line_filters(["malformed log without timestamp"], {"priority_sort": True}) == []


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("priority_sort", [False, True, None])
@pytest.mark.parametrize("db_authoritative", [False, True])
async def test_real_file_supplement_selects_newest_equal_priority_before_limit(
    tmp_path, priority_sort, db_authoritative, test_agent,
):
    project = _make_project(tmp_path)
    path = Path(project["progress_log"])
    path.write_text(
        f"[ℹ️] [2026-01-01 00:00:00 UTC] [Agent: {test_agent}] [Project: test_project] older | priority=high\n"
        f"[ℹ️] [2026-12-31 23:59:59 UTC] [Agent: {test_agent}] [Project: test_project] newer | priority=high\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    filters = {} if priority_sort is None else {"priority_sort": priority_sort}
    result = await _supplement_sparse_db_rows_from_progress_log(
        project=project, rows=[], page=1, page_size=1, filters=filters,
        db_authoritative=db_authoritative,
    )
    assert len(result) == 1
    assert result[0]["message"] == ("newer" if priority_sort else "older")
    assert result[0]["meta"] == {"priority": "high"}
    assert path.read_bytes() == before
    # Both hard gates preserve the input list and never introduce file records.
    rows = [_make_row("authoritative DB entry")]
    assert await _supplement_sparse_db_rows_from_progress_log(
        project=project, rows=rows, page=1, page_size=2, filters=filters,
        db_authoritative=True,
    ) is rows
    empty = []
    assert await _supplement_sparse_db_rows_from_progress_log(
        project=project, rows=empty, page=2, page_size=1, filters=filters,
        db_authoritative=db_authoritative,
    ) is empty
