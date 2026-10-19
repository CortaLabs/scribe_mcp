"""Current verified binding reads must revalidate storage; cached labels are hints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from test_get_project_integration import reader_environment, verified_reader_context
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.regression
async def test_current_project_rechecks_binding_on_each_read(reader_environment, monkeypatch):
    """Fresh reads preserve identity and reject an immutable context after rebinding."""
    env = reader_environment
    original = env.storage.get_session_project
    calls = []
    async def read_binding(session_id):
        calls.append(session_id)
        return await original(session_id)
    monkeypatch.setattr(env.storage, "get_session_project", read_binding)
    token = env.router.set_current(env.context)
    try:
        projects = {}
        for _ in range(3):
            name, bindings = await env.manager._resolve_current_project(env.session_id, projects)
            assert name == env.record.name
            assert bindings[env.session_id]["project_key"] == env.record.project_key
            assert bindings[env.session_id]["root"] == str(env.root)
        assert calls == [env.session_id] * 3
        await env.storage.upsert_project(
            name="other", repo_root=str(env.root), progress_log_path=str(env.root / "OTHER.md"),
        )
        await env.storage.set_session_project(env.session_id, "other")
        changed = await original(env.session_id)
        env.manager._session_projects_cache[env.session_id] = dict(projects["demo"])
        name, bindings = await env.manager._resolve_current_project(env.session_id, projects)
        assert name is None
        assert bindings == {}
        assert await original(env.session_id) == changed
    finally:
        env.router.reset(token)

    fresh = await verified_reader_context(
        env.storage, env.router, env.root, env.session_id, env.agent, "other",
    )
    token = env.router.set_current(fresh)
    try:
        state = await env.manager.load()
        assert state.current_project == "other"
        assert state.get_session_project(env.session_id)["project_key"] == changed.project_key
        assert state.get_project("other")["root"] == str(env.root)
    finally:
        env.router.reset(token)


@pytest.mark.asyncio
@pytest.mark.regression
async def test_different_sessions_each_resolve_once(reader_environment, monkeypatch) -> None:
    """Interleaved sessions revalidate identity; cached hints cannot rescue stale authority."""
    env = reader_environment
    session_a = env.session_id
    session_b = "session-beta"
    record_b = await env.storage.upsert_project(
        name="project_beta", repo_root=str(env.root),
        progress_log_path=str(env.root / "BETA.md"),
    )
    await env.storage.upsert_session(
        session_id=session_b, agent_id=env.agent, repo_root=str(env.root), mode="project",
    )
    await env.storage.set_session_project(session_b, record_b.name)
    context_b = await verified_reader_context(
        env.storage, env.router, env.root, session_b, env.agent, record_b.name,
    )
    original = env.storage.get_session_project
    binding_a = await original(session_a)
    binding_b = await original(session_b)
    before = await env.snapshot()
    assert env.record.project_key != record_b.project_key

    # Deliberately swap advisory cache entries between two legitimate sessions.
    hint_a = {"name": env.record.name, "project_key": env.record.project_key, "root": str(env.root)}
    hint_b = {"name": record_b.name, "project_key": record_b.project_key, "root": str(env.root)}
    hints = {session_a: dict(hint_b), session_b: dict(hint_a)}
    env.manager._session_projects_cache = {sid: dict(hint) for sid, hint in hints.items()}
    env.manager._projects_cache = {env.record.name: dict(hint_b), record_b.name: dict(hint_a)}
    env.manager._projects_cache_at = float("inf")
    project_hints = {name: dict(hint) for name, hint in env.manager._projects_cache.items()}
    projects = {name: dict(hint) for name, hint in project_hints.items()}
    calls = []

    async def read_binding(session_id):
        calls.append(session_id)
        return await original(session_id)

    monkeypatch.setattr(env.storage, "get_session_project", read_binding)

    async def resolve(session_id, context, record):
        reads_before = len(calls)
        token = env.router.set_current(context)
        try:
            name, bindings = await env.manager._resolve_current_project(session_id, projects)
        finally:
            env.router.reset(token)
        assert name == record.name
        assert set(bindings) == {session_id}
        assert bindings[session_id]["name"] == record.name
        assert bindings[session_id]["project_key"] == record.project_key
        assert bindings[session_id]["root"] == str(env.root)
        assert projects[name]["project_key"] == record.project_key
        assert len(calls) == reads_before + 1
        assert calls[-1] == session_id

    for _ in range(2):
        await resolve(session_a, env.context, env.record)
        await resolve(session_b, context_b, record_b)
    assert calls == [session_a, session_b, session_a, session_b]
    assert env.manager._session_projects_cache == hints
    assert env.manager._projects_cache == project_hints
    assert await original(session_a) == binding_a
    assert await original(session_b) == binding_b
    assert await env.snapshot() == before

    # Warm canonical results and hints are inert when authority is absent.
    reads_before_absent = list(calls)
    for session_id in (session_a, session_b):
        assert await env.manager._resolve_current_project(session_id, projects) == (None, {})
    assert calls == reads_before_absent

    await env.storage.set_session_project(session_a, record_b.name)
    changed = await original(session_a)
    after_change = await env.snapshot()
    reads_before_stale = list(calls)
    token = env.router.set_current(env.context)
    try:
        assert await env.manager._resolve_current_project(session_a, projects) == (None, {})
    finally:
        env.router.reset(token)
    assert calls == reads_before_stale + [session_a]
    assert changed.project_key == record_b.project_key
    assert changed.binding_generation != binding_a.binding_generation
    assert await original(session_a) == changed
    assert await original(session_b) == binding_b
    await resolve(session_b, context_b, record_b)

    fresh_a = await verified_reader_context(
        env.storage, env.router, env.root, session_a, env.agent, record_b.name,
    )
    await resolve(session_a, fresh_a, record_b)
    assert env.manager._session_projects_cache == hints
    assert env.manager._projects_cache == project_hints
    assert await env.snapshot() == after_change


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
@pytest.mark.regression
async def test_warm_cache_cannot_override_current_verified_binding(reader_environment):
    """Foreign cached payloads stay inert under both current and absent authority."""
    env = reader_environment
    stale = {"name": "foreign", "root": "/foreign", "project_key": "foreign-key"}
    env.manager._session_projects_cache[env.session_id] = dict(stale)
    env.manager._projects_cache = {"foreign": dict(stale)}
    env.manager._projects_cache_at = float("inf")
    before = await env.snapshot()
    token = env.router.set_current(env.context)
    try:
        state = await env.manager.load()
        assert state.current_project == env.record.name
        assert state.get_session_project(env.session_id)["project_key"] == env.record.project_key
        assert state.get_project(env.record.name)["root"] == str(env.root)
        assert "foreign" not in state.projects
    finally:
        env.router.reset(token)
    unverified = await env.manager.load()
    assert unverified.current_project is None
    assert unverified.session_projects == {}
    assert env.manager._session_projects_cache[env.session_id] == stale
    assert await env.snapshot() == before
