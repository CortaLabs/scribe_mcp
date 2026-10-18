"""Tests for session-binding cache in StateManager._resolve_current_project.

Acceptance criteria (p0-c5):
  - get_session_project is called AT MOST ONCE per session across multiple
    _resolve_current_project (load) calls within the same StateManager instance.

Strategy: monkeypatch get_session_project on the storage backend to count calls;
exercise _resolve_current_project multiple times and assert DB call count <= 1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _setup_storage(tmp_path: Path, session_id: str, project_name: str) -> SQLiteStorage:
    """Create a SQLiteStorage with a session and project binding already registered."""
    db_path = tmp_path / "state.db"
    storage = SQLiteStorage(db_path)
    await storage.setup()

    # Create project
    await storage.upsert_project(
        name=project_name,
        repo_root=str(tmp_path),
        progress_log_path=str(tmp_path / "log.md"),
    )

    # Create session row (required before set_session_project)
    await storage.upsert_session(session_id=session_id, agent_id="test-agent", mode="project")

    # Bind session to project
    await storage.set_session_project(session_id, project_name)

    return storage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_session_project_called_at_most_once(tmp_path: Path) -> None:
    """Repeated _resolve calls must not re-query get_session_project after the first hit."""
    session_id = "test-session-abc123"
    project_name = "cache_test_project"

    storage = await _setup_storage(tmp_path, session_id, project_name)

    call_count = 0
    original_gsp = storage.get_session_project

    async def counting_gsp(sid: str) -> Optional[str]:
        nonlocal call_count
        call_count += 1
        return await original_gsp(sid)

    storage.get_session_project = counting_gsp  # type: ignore[method-assign]

    manager = StateManager(storage_backend=storage)

    # Call _resolve_current_project three times with the same session_id.
    # First call hits DB; subsequent calls must hit in-memory cache only.
    async with manager._lock:
        await manager._ensure_backend_ready()
        await manager._run_legacy_migration_once()
        projects = await manager._load_projects()

        p1, _ = await manager._resolve_current_project(session_id, projects)
        p2, _ = await manager._resolve_current_project(session_id, projects)
        p3, _ = await manager._resolve_current_project(session_id, projects)

    assert p1 == project_name, f"Expected {project_name!r}, got {p1!r}"
    assert p2 == project_name, f"Expected {project_name!r}, got {p2!r}"
    assert p3 == project_name, f"Expected {project_name!r}, got {p3!r}"

    # DB must have been queried AT MOST ONCE across all three _resolve calls
    assert call_count <= 1, (
        f"get_session_project was called {call_count} times across 3 _resolve calls; "
        "expected at most 1 (cache should prevent repeated DB round-trips)"
    )


@pytest.mark.asyncio
async def test_different_sessions_each_resolve_once(tmp_path: Path) -> None:
    """Each distinct session_id gets its own cache entry after first resolution."""
    session_a = "session-alpha"
    session_b = "session-beta"
    project_a = "project_alpha"
    project_b = "project_beta"

    db_path = tmp_path / "state.db"
    storage = SQLiteStorage(db_path)
    await storage.setup()

    for name in (project_a, project_b):
        await storage.upsert_project(
            name=name,
            repo_root=str(tmp_path),
            progress_log_path=str(tmp_path / "log.md"),
        )

    await storage.upsert_session(session_id=session_a, agent_id="test-agent", mode="project")
    await storage.upsert_session(session_id=session_b, agent_id="test-agent", mode="project")
    await storage.set_session_project(session_a, project_a)
    await storage.set_session_project(session_b, project_b)

    call_counts: Dict[str, int] = {session_a: 0, session_b: 0}
    original_gsp = storage.get_session_project

    async def counting_gsp(sid: str) -> Optional[str]:
        if sid in call_counts:
            call_counts[sid] += 1
        return await original_gsp(sid)

    storage.get_session_project = counting_gsp  # type: ignore[method-assign]

    manager = StateManager(storage_backend=storage)

    async with manager._lock:
        await manager._ensure_backend_ready()
        await manager._run_legacy_migration_once()
        projects = await manager._load_projects()

        # Two rounds for each session (interleaved)
        await manager._resolve_current_project(session_a, projects)
        await manager._resolve_current_project(session_b, projects)
        await manager._resolve_current_project(session_a, projects)
        await manager._resolve_current_project(session_b, projects)

    assert call_counts[session_a] <= 1, (
        f"session_a DB calls: {call_counts[session_a]} (expected <= 1)"
    )
    assert call_counts[session_b] <= 1, (
        f"session_b DB calls: {call_counts[session_b]} (expected <= 1)"
    )


@pytest.mark.asyncio
async def test_no_session_id_skips_get_session_project(tmp_path: Path) -> None:
    """When session_id is None, get_session_project must not be called at all."""
    db_path = tmp_path / "state.db"
    storage = SQLiteStorage(db_path)
    await storage.setup()

    call_count = 0
    original_gsp = storage.get_session_project

    async def counting_gsp(sid: str) -> Optional[str]:
        nonlocal call_count
        call_count += 1
        return await original_gsp(sid)

    storage.get_session_project = counting_gsp  # type: ignore[method-assign]

    manager = StateManager(storage_backend=storage)

    async with manager._lock:
        await manager._ensure_backend_ready()
        await manager._run_legacy_migration_once()
        projects = await manager._load_projects()
        await manager._resolve_current_project(None, projects)
        await manager._resolve_current_project(None, projects)

    assert call_count == 0, (
        f"get_session_project must not be called when session_id is None, "
        f"but was called {call_count} times"
    )


@pytest.mark.asyncio
async def test_cache_populated_after_first_db_call(tmp_path: Path) -> None:
    """After the first DB resolution, the cache entry must be present in _session_projects_cache."""
    session_id = "populate-test-session"
    project_name = "populate_cache_project"

    storage = await _setup_storage(tmp_path, session_id, project_name)
    manager = StateManager(storage_backend=storage)

    # Cache starts empty
    assert session_id not in manager._session_projects_cache

    async with manager._lock:
        await manager._ensure_backend_ready()
        await manager._run_legacy_migration_once()
        projects = await manager._load_projects()
        await manager._resolve_current_project(session_id, projects)

    # After first resolution, cache must be populated
    assert session_id in manager._session_projects_cache, (
        "Cache must be populated after first DB resolution "
        "so subsequent calls skip the DB round-trip"
    )
    cached = manager._session_projects_cache[session_id]
    resolved_name = manager._resolve_project_name(cached)
    assert resolved_name == project_name
