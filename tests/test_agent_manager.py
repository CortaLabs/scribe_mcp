#!/usr/bin/env python3
"""Simple test for AgentContextManager functionality."""

import asyncio
import tempfile
from pathlib import Path
from datetime import timedelta
import pytest
import pytest_asyncio

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import (
    AgentContextManager,
    SessionLeaseExpired,
    STALE_SESSION_REASON_EXPIRED,
    STALE_SESSION_REASON_MISMATCH,
    STALE_SESSION_REASON_NO_ACTIVE,
)
from scribe_mcp.state import agent_manager as agent_manager_module


@pytest_asyncio.fixture
async def agent_context():
    """Keep both managers on one disposable, real SQLite backend."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        storage = SQLiteStorage(temp_path / "test.db")
        try:
            await storage.setup()
            state_manager = StateManager(temp_path / "state.json", storage_backend=storage)
            manager = AgentContextManager(storage, state_manager)
            for name in ("TestProject", "ProjectA", "ProjectB"):
                repo_root = temp_path / name
                repo_root.mkdir()
                progress_log = repo_root / "PROGRESS_LOG.md"
                progress_log.touch()
                await storage.upsert_project(
                    name=name, repo_root=str(repo_root), progress_log_path=str(progress_log)
                )
            yield manager
        finally:
            await storage.close()
            assert storage._pool is None
    assert not temp_path.exists()


@pytest.mark.asyncio
@pytest.mark.regression
async def test_agent_context_manager(agent_context, test_agent, monkeypatch):
    """Assert the original session, project, isolation and heartbeat journey."""
    manager = agent_context
    storage = manager.storage
    agent_a, agent_b = test_agent, f"{test_agent}:client-b"
    now = agent_manager_module.utcnow()
    monkeypatch.setattr(agent_manager_module, "utcnow", lambda: now)

    session_id = await manager.start_session(agent_a, metadata={"test": True})
    assert isinstance(session_id, str) and session_id
    assert manager._session_leases[agent_a] == (
        session_id, now + timedelta(minutes=manager._session_ttl_minutes)
    )

    result = await manager.set_current_project(agent_a, "TestProject", session_id)
    assert result["project_name"] == "TestProject"
    assert result["version"] == 1
    assert result["session_id"] == session_id
    assert result["agent_id"] == result["updated_by"] == agent_a
    current = await manager.get_current_project(agent_a)
    assert current is not None
    assert current == result

    with pytest.raises(SessionLeaseExpired, match="Session ID mismatch") as invalid:
        await manager.set_current_project(agent_a, "OtherProject", "invalid-session")
    assert invalid.value.reason == STALE_SESSION_REASON_MISMATCH
    assert await manager.get_current_project(agent_a) == current

    session_b = await manager.start_session(agent_b)
    assert session_b != session_id
    results = await asyncio.gather(
        manager.set_current_project(agent_a, "ProjectA", session_id),
        manager.set_current_project(agent_b, "ProjectB", session_b),
    )
    project_a, project_b = await asyncio.gather(
        manager.get_current_project(agent_a), manager.get_current_project(agent_b)
    )
    assert project_a is not None and project_b is not None
    assert project_a["project_name"] == "ProjectA"
    assert project_b["project_name"] == "ProjectB"
    assert project_a["session_id"] == session_id
    assert project_b["session_id"] == session_b
    assert project_a["updated_by"] == agent_a
    assert project_b["updated_by"] == agent_b
    assert project_a["version"] == 2 and project_b["version"] == 1
    assert results == [project_a, project_b]

    # Age an input timestamp, then observe the real SQLite heartbeat write.
    await storage._execute(
        "UPDATE agent_sessions SET last_active_at = ? WHERE session_id = ?;",
        ("2000-01-01 00:00:00", session_id),
    )
    lease_b = manager._session_leases[agent_b]
    now += timedelta(minutes=1)
    await manager.heartbeat_session(session_id)
    heartbeat = await storage._fetchone(
        "SELECT last_active_at, expires_at FROM agent_sessions WHERE session_id = ?;",
        (session_id,),
    )
    assert heartbeat["last_active_at"] != "2000-01-01 00:00:00"
    assert heartbeat["expires_at"] is None
    assert manager._session_leases[agent_a] == (
        session_id, now + timedelta(minutes=manager._session_ttl_minutes)
    )
    assert manager._session_leases[agent_b] == lease_b

    await manager.end_session(agent_a, session_id)
    assert agent_a not in manager._session_leases
    ended = await storage._fetchone(
        "SELECT expires_at FROM agent_sessions WHERE session_id = ?;", (session_id,)
    )
    assert ended["expires_at"] is not None
    with pytest.raises(SessionLeaseExpired, match="No active session") as expired:
        await manager.set_current_project(agent_a, "NewProject", session_id)
    assert expired.value.reason == STALE_SESSION_REASON_NO_ACTIVE
    assert await manager.get_current_project(agent_b) == project_b


@pytest.mark.asyncio
@pytest.mark.regression
async def test_session_cleanup(agent_context, test_agent, monkeypatch):
    """Expire two real leases while preserving a fresh independent client."""
    manager = agent_context
    now = agent_manager_module.utcnow()
    monkeypatch.setattr(agent_manager_module, "utcnow", lambda: now)
    agents = (test_agent, f"{test_agent}:client-b")
    sessions = [await manager.start_session(agent) for agent in agents]
    assert sessions[0] != sessions[1]
    assert await manager.cleanup_expired_sessions() == 0

    ttl = timedelta(minutes=manager._session_ttl_minutes)
    now += ttl / 2
    active_agent = f"{test_agent}:active-client"
    active_session = await manager.start_session(active_agent)
    active_lease = manager._session_leases[active_agent]
    now += ttl / 2 + timedelta(seconds=1)

    cleaned = await manager.cleanup_expired_sessions()
    assert cleaned == 2
    assert manager._session_leases == {active_agent: active_lease}
    for agent, session_id in zip(agents, sessions):
        ended = await manager.storage._fetchone(
            "SELECT expires_at FROM agent_sessions WHERE session_id = ?;", (session_id,)
        )
        assert ended["expires_at"] is not None
        with pytest.raises(SessionLeaseExpired, match="No active session"):
            await manager.set_current_project(agent, "TestProject", session_id)
    active = await manager.storage._fetchone(
        "SELECT expires_at FROM agent_sessions WHERE session_id = ?;", (active_session,)
    )
    assert active["expires_at"] is None
    await manager._validate_session_lease(active_agent, active_session)
    assert await manager.cleanup_expired_sessions() == 0


@pytest.mark.asyncio
async def test_set_current_project_tolerates_none_storage_result(monkeypatch):
    """set_current_project should not crash if storage returns a non-dict payload."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        manager = AgentContextManager(storage, state_manager)

        session_id = await manager.start_session("AgentA")

        async def _return_none(**_kwargs):
            return None

        monkeypatch.setattr(storage, "set_agent_project", _return_none)

        result = await manager.set_current_project("AgentA", "RecoveredProject", session_id)
        assert isinstance(result, dict)
        assert result.get("project_name") == "RecoveredProject"
        assert result.get("session_id") == session_id
        assert result.get("updated_by") == "AgentA"

        await storage.close()


@pytest.mark.asyncio
async def test_log_agent_event_uses_postgres_parameter_style(tmp_path):
    class _FakePostgresStorage:
        __module__ = "scribe_mcp.storage.postgres.fake"

        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[object, ...]]] = []

        async def _execute(self, query: str, *params: object) -> str:
            self.calls.append((query, params))
            return "INSERT 0 1"

    state_path = tmp_path / "state.json"
    manager = AgentContextManager(_FakePostgresStorage(), StateManager(state_path))

    await manager.log_agent_event(
        agent_id="agent-1",
        session_id="sess-1",
        event_type="project_set",
        to_project="demo",
        metadata={"source": "test"},
    )

    query, params = manager.storage.calls[0]
    assert "$1" in query
    assert "?" not in query
    assert len(params) == 11


@pytest.mark.asyncio
async def test_get_agent_events_uses_postgres_fetch_api(tmp_path):
    class _FakePostgresStorage:
        __module__ = "scribe_mcp.storage.postgres.fake"

        def __init__(self) -> None:
            self.last_query = ""
            self.last_params: tuple[object, ...] = ()

        async def _fetch(self, query: str, *params: object):
            self.last_query = query
            self.last_params = params
            return [
                {
                    "id": 1,
                    "agent_id": "agent-1",
                    "session_id": "sess-1",
                    "event_type": "project_set",
                    "from_project": None,
                    "to_project": "demo",
                    "expected_version": None,
                    "actual_version": 1,
                    "success": True,
                    "error_message": None,
                    "metadata": "{}",
                    "created_at": "2026-02-15T00:00:00+00:00",
                }
            ]

    state_path = tmp_path / "state.json"
    storage = _FakePostgresStorage()
    manager = AgentContextManager(storage, StateManager(state_path))

    rows = await manager.get_agent_events(agent_id="agent-1", event_type="project_set", limit=5)

    assert rows and rows[0]["agent_id"] == "agent-1"
    assert "LIMIT $3" in storage.last_query
    assert storage.last_params == ("agent-1", "project_set", 5)


@pytest.mark.asyncio
async def test_session_lifecycle_roundtrip_with_explicit_session_id(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    state_path = tmp_path / "state.json"
    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    project_name = "LifecycleProject"
    await storage.upsert_project(
        name=project_name,
        repo_root=str(tmp_path),
        progress_log_path=str(tmp_path / "PROGRESS_LOG.md"),
    )

    session_id = await manager.start_session(
        "LifecycleAgent",
        session_id="stable-session-001",
        metadata={"source": "unit-test"},
    )
    assert session_id == "stable-session-001"
    assert manager._session_leases["LifecycleAgent"][0] == "stable-session-001"

    await manager.set_current_project("LifecycleAgent", project_name, session_id)
    await manager.heartbeat_session(session_id)

    await manager.end_session("LifecycleAgent", session_id)
    assert "LifecycleAgent" not in manager._session_leases

    with pytest.raises(SessionLeaseExpired, match="No active session"):
        await manager.set_current_project("LifecycleAgent", project_name, session_id)

    await storage.close()


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_only_expires_stale_leases(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    state_path = tmp_path / "state.json"
    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    stale_session_id = await manager.start_session("StaleAgent")
    active_session_id = await manager.start_session("ActiveAgent")
    now = agent_manager_module.utcnow()
    manager._session_leases["StaleAgent"] = (stale_session_id, now - timedelta(minutes=1))
    manager._session_leases["ActiveAgent"] = (active_session_id, now + timedelta(minutes=5))

    cleaned = await manager.cleanup_expired_sessions()
    assert cleaned == 1
    assert "StaleAgent" not in manager._session_leases
    assert manager._session_leases["ActiveAgent"][0] == active_session_id

    await storage.close()


@pytest.mark.asyncio
async def test_session_binding_keeps_agent_session_ids_isolated(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    state_path = tmp_path / "state.json"
    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    await storage.upsert_project(
        name="SharedProject",
        repo_root=str(tmp_path / "repo"),
        progress_log_path=str(tmp_path / "repo" / "PROGRESS_LOG.md"),
    )

    # Metadata is accepted for compatibility, but this test verifies binding via
    # authoritative session IDs and lease ownership boundaries.
    session_cli = await manager.start_session(
        "CoderAgent-cli",
        session_id="sess-cli-001",
        metadata={"client": "codex-cli", "workspace": "/workspace/a", "transport_session_id": "transport-cli"},
    )
    session_api = await manager.start_session(
        "CoderAgent-api",
        session_id="sess-api-001",
        metadata={"client": "sdk-api", "workspace": "/workspace/b", "transport_session_id": "transport-api"},
    )

    cli_result = await manager.set_current_project("CoderAgent-cli", "SharedProject", session_cli)
    api_result = await manager.set_current_project("CoderAgent-api", "SharedProject", session_api)
    cli_current = await manager.get_current_project("CoderAgent-cli")
    api_current = await manager.get_current_project("CoderAgent-api")

    assert cli_result["session_id"] == "sess-cli-001"
    assert api_result["session_id"] == "sess-api-001"
    assert cli_current is not None and cli_current["session_id"] == "sess-cli-001"
    assert api_current is not None and api_current["session_id"] == "sess-api-001"
    assert cli_current["updated_by"] == "CoderAgent-cli"
    assert api_current["updated_by"] == "CoderAgent-api"
    assert manager._session_leases["CoderAgent-cli"][0] == "sess-cli-001"
    assert manager._session_leases["CoderAgent-api"][0] == "sess-api-001"

    with pytest.raises(SessionLeaseExpired, match="Session ID mismatch"):
        await manager.set_current_project("CoderAgent-api", "SharedProject", "sess-cli-001")

    await storage.close()


@pytest.mark.asyncio
async def test_session_lease_error_taxonomy_exposes_typed_reasons(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    state_path = tmp_path / "state.json"
    storage = SQLiteStorage(db_path)
    await storage.setup()
    manager = AgentContextManager(storage, StateManager(state_path))

    session_id = await manager.start_session("AgentX", session_id="sess-001")

    with pytest.raises(SessionLeaseExpired, match="No active session") as no_active:
        await manager._validate_session_lease("UnknownAgent", "sess-001")
    assert no_active.value.reason == STALE_SESSION_REASON_NO_ACTIVE
    assert no_active.value.agent_id == "UnknownAgent"

    with pytest.raises(SessionLeaseExpired, match="Session ID mismatch") as mismatch:
        await manager._validate_session_lease("AgentX", "wrong-session")
    assert mismatch.value.reason == STALE_SESSION_REASON_MISMATCH
    assert mismatch.value.agent_id == "AgentX"
    assert mismatch.value.session_id == "wrong-session"

    manager._session_leases["AgentX"] = (
        session_id,
        agent_manager_module.utcnow() - timedelta(seconds=1),
    )
    with pytest.raises(SessionLeaseExpired, match="Session lease expired") as expired:
        await manager._validate_session_lease("AgentX", "sess-001")
    assert expired.value.reason == STALE_SESSION_REASON_EXPIRED
    assert expired.value.agent_id == "AgentX"
    assert expired.value.session_id == "sess-001"

    await storage.close()


def main():
    """Run the same pytest journeys and fixtures, preserving its exit status."""
    return pytest.main(["-q", "-n0", str(Path(__file__).resolve())])


if __name__ == "__main__":
    raise SystemExit(main())
