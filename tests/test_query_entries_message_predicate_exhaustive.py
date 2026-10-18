"""Anti-windowing tests for the in-SQL message predicate (P4.1 / WS2 F1+F5).

These tests protect the headline production bug fixed in P4.1: message search
used to filter in Python over only the newest ~1000-row window, so any matching
entry older than that window was *silently* missed on BOTH backends, and
``count_query_entries`` used a different (10k, unordered) window than the page
fetch (≤1k, newest-first) so ``total_count`` could lie.

Contract proven here:
  - ``query_entries`` with a ``message`` predicate FINDS matches that live far
    outside the old newest-~1000-row window (rows seeded as the OLDEST entries).
  - ``count_query_entries`` returns the TRUE match count, sharing the same
    predicate + ordering as the page fetch.
  - Holds for substring (case-insensitive + case-sensitive) and exact modes.
  - Verified on SQLite always and on Postgres when ``SCRIBE_TEST_POSTGRES_URL``
    is set (the live production backend). The two backends are exercised through
    the IDENTICAL test body so cross-backend parity is mechanically enforced.

Bounded-op: a single pass of bulk inserts + a handful of queries. No sleeps, no
per-row assertions in a hot loop beyond the seeded markers.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio

from scribe_mcp.storage.sqlite import SQLiteStorage

try:  # asyncpg/Postgres are optional in some environments
    import asyncpg

    _HAVE_ASYNCPG = True
except Exception:  # pragma: no cover - import guard
    _HAVE_ASYNCPG = False


# Total rows seeded. Must exceed the old fetch window (~1000) by a wide margin so
# the OLDEST seeded markers are far outside it. Kept modest to stay fast.
_TOTAL_ROWS = 2200
# Unique markers seeded as the two OLDEST rows (indices 0 and 1) — i.e. the rows
# the old newest-first window could never reach.
_MARKER_A = f"ZQX-marker-alpha-{uuid.uuid4().hex}"
_MARKER_B = f"ZQX-marker-beta-{uuid.uuid4().hex}"


def _replace_db_name(dsn: str, db_name: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, f"/{db_name}", parts.query, parts.fragment))


async def _seed(storage, project) -> None:
    """Insert _TOTAL_ROWS entries; the two unique markers are the OLDEST rows.

    Timestamps increase with index, so the markers (index 0,1) sort LAST under
    ``ORDER BY ts_iso DESC`` — exactly where the old windowed scan dropped them.
    """
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(_TOTAL_ROWS):
        ts = base + timedelta(minutes=i)
        if i == 0:
            message = f"oldest entry {_MARKER_A} sentinel"
        elif i == 1:
            message = f"second oldest {_MARKER_B} SENTINEL"
        else:
            message = f"routine log line number {i} no marker here"
        await storage.insert_entry(
            entry_id=str(uuid.uuid4()),
            project=project,
            ts=ts,
            emoji="ℹ️",
            agent="test-agent",
            message=message,
            meta={},
            raw_line=message,
            sha256=str(uuid.uuid4()),
            log_type="progress",
        )


async def _assert_exhaustive(storage, project) -> None:
    """Backend-agnostic body: the markers are findable and counts are true."""
    # --- substring, case-insensitive (default) ------------------------------
    rows = await storage.query_entries(
        project=project, limit=50, message=_MARKER_A, message_mode="substring"
    )
    assert any(_MARKER_A in r["message"] for r in rows), (
        "substring search must FIND the OLDEST marker (was silently windowed out)"
    )
    count = await storage.count_query_entries(
        project=project, message=_MARKER_A, message_mode="substring"
    )
    assert count == 1, f"count must be the TRUE match count (1), got {count}"

    # Token shared by exactly the two markers' lines ("sentinel", any case).
    rows = await storage.query_entries(
        project=project, limit=50, message="sentinel", message_mode="substring"
    )
    found = {r["message"] for r in rows}
    assert any(_MARKER_A in m for m in found)
    assert any(_MARKER_B in m for m in found)
    count = await storage.count_query_entries(
        project=project, message="sentinel", message_mode="substring"
    )
    assert count == 2, (
        f"case-insensitive substring count must be 2 (matches 'sentinel' and "
        f"'SENTINEL' on the two oldest rows), got {count}"
    )

    # --- substring, case-sensitive ------------------------------------------
    # Only the second marker line contains uppercase 'SENTINEL'.
    rows = await storage.query_entries(
        project=project,
        limit=50,
        message="SENTINEL",
        message_mode="substring",
        case_sensitive=True,
    )
    assert any(_MARKER_B in r["message"] for r in rows)
    assert all("sentinel" not in r["message"] or "SENTINEL" in r["message"] for r in rows)
    count = await storage.count_query_entries(
        project=project, message="SENTINEL", message_mode="substring", case_sensitive=True
    )
    assert count == 1, f"case-sensitive substring count must be 1, got {count}"

    # --- exact, case-insensitive --------------------------------------------
    exact_text = f"oldest entry {_MARKER_A} sentinel"
    rows = await storage.query_entries(
        project=project, limit=50, message=exact_text.upper(), message_mode="exact"
    )
    assert len(rows) == 1 and _MARKER_A in rows[0]["message"], (
        "exact (case-insensitive) must match the full oldest line regardless of case"
    )
    count = await storage.count_query_entries(
        project=project, message=exact_text.upper(), message_mode="exact"
    )
    assert count == 1, f"exact count must be 1, got {count}"

    # --- no message: predicate absent, totals unaffected --------------------
    total = await storage.count_query_entries(project=project)
    assert total == _TOTAL_ROWS, f"unfiltered count must be {_TOTAL_ROWS}, got {total}"


@pytest.mark.asyncio
async def test_message_predicate_exhaustive_sqlite(tmp_path) -> None:
    storage = SQLiteStorage(db_path=tmp_path / "exhaustive.sqlite3")
    await storage.setup()
    try:
        project = await storage.upsert_project(
            name="msg_exhaustive_sqlite",
            repo_root=str(tmp_path),
            progress_log_path=str(tmp_path / "log.md"),
        )
        await _seed(storage, project)
        await _assert_exhaustive(storage, project)
    finally:
        await storage.close()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_message_predicate_exhaustive_postgres() -> None:
    if not _HAVE_ASYNCPG:
        pytest.skip("asyncpg not installed")
    base_dsn = os.getenv("SCRIBE_TEST_POSTGRES_URL")
    if not base_dsn:
        pytest.skip("Set SCRIBE_TEST_POSTGRES_URL to enable the Postgres parity test")

    from scribe_mcp.storage.postgres import PostgresStorage

    admin_dsn = os.getenv(
        "SCRIBE_TEST_POSTGRES_ADMIN_URL", _replace_db_name(base_dsn, "postgres")
    )
    db_name = f"scribe_p41_{uuid.uuid4().hex[:10]}"

    using_shared_db = False
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{db_name}";')
        test_dsn = _replace_db_name(base_dsn, db_name)
    except asyncpg.InsufficientPrivilegeError:
        using_shared_db = True
        test_dsn = base_dsn
    finally:
        await admin.close()

    storage = PostgresStorage(test_dsn)
    await storage.setup()
    try:
        project = await storage.upsert_project(
            name=f"msg_exhaustive_pg_{uuid.uuid4().hex[:8]}",
            repo_root="/tmp/msg_exhaustive_pg",
            progress_log_path="/tmp/msg_exhaustive_pg/log.md",
        )
        await _seed(storage, project)
        await _assert_exhaustive(storage, project)
        if using_shared_db:
            await storage.delete_project(project.name)
    finally:
        await storage.close()
        if not using_shared_db:
            admin = await asyncpg.connect(admin_dsn)
            try:
                await admin.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = $1 AND pid <> pg_backend_pid();
                    """,
                    db_name,
                )
                await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}";')
            finally:
                await admin.close()
