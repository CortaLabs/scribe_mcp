#!/usr/bin/env python3
"""Simple test for AgentContextManager functionality."""

import asyncio
import tempfile
from pathlib import Path
from datetime import timedelta
import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager, SessionLeaseExpired
from scribe_mcp.state import agent_manager as agent_manager_module


@pytest.mark.asyncio
async def test_agent_context_manager():
    """Test basic AgentContextManager functionality."""
    print("🧪 Testing AgentContextManager...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize storage and state manager
        storage = SQLiteStorage(db_path)
        await storage.setup()

        state_manager = StateManager(state_path)

        # Create agent context manager
        manager = AgentContextManager(storage, state_manager)

        # Test 1: Start session
        print("  ✓ Starting session for AgentA...")
        session_id = await manager.start_session("AgentA", {"test": True})
        print(f"    Session ID: {session_id}")

        # Test 2: Set current project
        print("  ✓ Setting current project...")

        # First create a project to reference
        project = await storage.upsert_project(
            name="TestProject",
            repo_root="/tmp/test",
            progress_log_path="/tmp/test/log.md"
        )

        result = await manager.set_current_project("AgentA", "TestProject", session_id)
        print(f"    Project set: {result['project_name']} (version {result['version']})")

        # Test 3: Get current project
        print("  ✓ Getting current project...")
        current = await manager.get_current_project("AgentA")
        print(f"    Current project: {current['project_name'] if current else None}")

        # Test 4: Session validation
        print("  ✓ Testing session validation...")
        try:
            await manager.set_current_project("AgentA", "OtherProject", "invalid-session")
            print("    ❌ Should have failed with invalid session")
        except SessionLeaseExpired:
            print("    ✓ Correctly rejected invalid session")

        # Test 5: Concurrent operations
        print("  ✓ Testing concurrent operations...")

        # Start session for AgentB
        session_b = await manager.start_session("AgentB")

        # Create projects first
        project_a = await storage.upsert_project(
            name="ProjectA",
            repo_root="/tmp/project_a",
            progress_log_path="/tmp/project_a/log.md"
        )
        project_b = await storage.upsert_project(
            name="ProjectB",
            repo_root="/tmp/project_b",
            progress_log_path="/tmp/project_b/log.md"
        )

        # Set different projects for different agents
        await manager.set_current_project("AgentA", "ProjectA", session_id)
        await manager.set_current_project("AgentB", "ProjectB", session_b)

        # Verify isolation
        project_a = await manager.get_current_project("AgentA")
        project_b = await manager.get_current_project("AgentB")

        if project_a["project_name"] == "ProjectA" and project_b["project_name"] == "ProjectB":
            print("    ✓ Agent isolation working correctly")
        else:
            print("    ❌ Agent isolation failed")

        # Test 6: Session heartbeat
        print("  ✓ Testing session heartbeat...")
        await manager.heartbeat_session(session_id)
        print("    ✓ Session heartbeat successful")

        # Test 7: End session
        print("  ✓ Testing session end...")
        await manager.end_session("AgentA", session_id)

        try:
            await manager.set_current_project("AgentA", "NewProject", session_id)
            print("    ❌ Should have failed with expired session")
        except SessionLeaseExpired:
            print("    ✓ Correctly rejected expired session")

        # Cleanup
        await storage.close()

    print("✅ AgentContextManager tests completed successfully!")


@pytest.mark.asyncio
async def test_session_cleanup():
    """Test session cleanup functionality."""
    print("🧪 Testing session cleanup...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        manager = AgentContextManager(storage, state_manager)

        # Start sessions
        session1 = await manager.start_session("TestAgent1")
        session2 = await manager.start_session("TestAgent2")

        # Manually expire sessions by setting short TTL
        manager._session_ttl_minutes = -1  # Expire immediately

        # Run cleanup
        cleaned = await manager.cleanup_expired_sessions()
        print(f"  ✓ Cleaned up {cleaned} expired sessions")

        await storage.close()

    print("✅ Session cleanup tests completed successfully!")


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


async def main():
    """Run all tests."""
    print("🚀 Starting AgentContextManager tests...\n")

    await test_agent_context_manager()
    print()
    await test_session_cleanup()

    print("\n🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
