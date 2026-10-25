#!/usr/bin/env python3
"""Inline functional test for Phase 3 Tasks 3.3-3.4: StateManager database integration."""

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
import sqlite3

import pytest

from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage

pytestmark = pytest.mark.asyncio


@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize("heartbeat", ["activity", "identity"])
async def test_identity_heartbeats_preserve_durable_binding(
    tmp_path, monkeypatch, test_agent, heartbeat,
):
    """Identity bookkeeping must not replay a cached selection into storage."""
    from scribe_mcp import server
    from scribe_mcp.shared.execution_context import RouterContextManager
    from scribe_mcp.state import agent_identity as identity_module

    storage = SQLiteStorage(tmp_path / "heartbeat.sqlite3")
    await storage.setup()
    router = RouterContextManager(storage_backend=storage)
    monkeypatch.setattr(server, "router_context_manager", router)
    manager = StateManager(tmp_path / "state.json", storage_backend=storage)
    clock = [1000.0]
    # Change only identity scheduling, never the router/session/authority result.
    monkeypatch.setattr(identity_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.delenv("SCRIBE_AGENT_ACTIVITY_PERSIST_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("SCRIBE_AGENT_ID_PERSIST_INTERVAL_SECONDS", raising=False)
    identity = identity_module.AgentIdentity(manager)
    context = await router.build_execution_context({
        "transport_session_id": "heartbeat-owner", "repo_root": str(tmp_path),
        "mode": "project", "intent": "heartbeat regression",
    })
    sibling = await router.get_or_create_session_id("heartbeat-sibling")
    for key in (context.session_id, sibling):
        await storage.upsert_session(session_id=key, repo_root=str(tmp_path), mode="project")
    token = router.set_current(context)

    def rows():
        with sqlite3.connect(tmp_path / "heartbeat.sqlite3") as connection:
            return connection.execute("SELECT * FROM session_projects ORDER BY session_id").fetchall()

    try:
        actor = await identity.get_or_create_agent_id({"agent_id": test_agent})
        await identity.update_agent_activity(actor, "initial")
        for name in ("heartbeat_default", "heartbeat_sibling", "heartbeat_rebound"):
            await storage.upsert_project(name=name, repo_root=str(tmp_path),
                progress_log_path=str(tmp_path / name / "PROGRESS_LOG.md"))
        await manager.set_current_project("heartbeat_default", {"root": str(tmp_path)},
                                          session_id=context.session_id)
        await storage.set_session_project(sibling, "heartbeat_sibling")
        before = rows()
        original = await storage.get_session_project(context.session_id)
        assert original.binding_generation == 1
        # SQLite timestamps have one-second precision. Only this short boundary
        # wait uses wall time; heartbeat scheduling uses the controlled clock.
        await asyncio.sleep(1.05)
        clock[0] += 61 if heartbeat == "activity" else 301
        if heartbeat == "activity":
            await identity.update_agent_activity(actor, "append_entry")
            state = await manager.load()
            assert state.agent_state["last_activity"] == "append_entry"
            assert state.agent_state["activity_log"][-1]["agent_id"] == actor
        else:
            assert await identity.get_or_create_agent_id({"agent_id": test_agent}) == actor
            state = await manager.load()
            assert state.agent_state["last_agent_id"] == actor
            assert identity._last_persisted_at == clock[0]
        assert rows() == before, "heartbeat rewrote a durable caller or sibling binding"
        assert state.get_session_project(context.session_id)["name"] == "heartbeat_default"

        await manager.set_current_project("heartbeat_rebound", {"root": str(tmp_path)},
                                          session_id=context.session_id)
        rebound = await storage.get_session_project(context.session_id)
        assert rebound.binding_generation == 2 and rebound.project_key != original.project_key
        sibling_binding = await storage.get_session_project(sibling)
        await storage.set_session_project(context.session_id, None)
        revoked = rows()
        clock[0] += 301
        await identity.update_agent_activity(actor, "after_revocation")
        assert rows() == revoked, "heartbeat resurrected a revoked cached binding"
        assert await storage.get_session_project(context.session_id) is None
        assert await storage.delete_project("heartbeat_rebound")
        await manager.persist(await manager.load())
        assert await storage.fetch_project("heartbeat_rebound") is None
        assert await storage.get_session_project(sibling) == sibling_binding
    finally:
        router.reset(token)
        await storage.close()


async def test_record_tool_database_integration(monkeypatch):
    """Test that record_tool writes and reads session activity from database."""
    print("=" * 70)
    print("PHASE 3 STATE MANAGER DATABASE INTEGRATION TEST")
    print("=" * 70)

    # Create temporary database and state file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        db_path = tmppath / "test.db"
        state_path = tmppath / "state.json"

        # Initialize storage backend
        storage = SQLiteStorage(str(db_path))
        await storage._initialise()

        print("\n1. Storage backend initialized")
        print(f"   Database: {db_path}")

        # Create a test session in agent_sessions table
        test_session_id = "test-session-123"
        await storage._execute(
            """INSERT INTO agent_sessions
               (session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (test_session_id, "test-key", "TestAgent", "TestAgent", "/tmp/test", "project", "2026-01-23")
        )
        print(f"   Created test session: {test_session_id}")

        # Mock the server module to provide storage backend
        import scribe_mcp.server as server_module
        monkeypatch.setattr(server_module, "storage_backend", storage)

        # Create mock router context manager
        class MockExecutionContext:
            def __init__(self):
                self.session_id = test_session_id
                self.stable_session_id = test_session_id

        class MockRouterContext:
            def get_current(self):
                return MockExecutionContext()

        monkeypatch.setattr(server_module, "router_context_manager", MockRouterContext())

        print("\n2. Mock server context set up")

        # Initialize StateManager using explicit backend injection (Phase 7 contract)
        manager = StateManager(state_path, storage_backend=storage)

        # Test 1: record_tool should write to database
        print("\n3. Testing record_tool() - should write to database")
        state = await manager.record_tool("test_tool_1")
        print(f"   ✓ record_tool() succeeded")
        print(f"   Recent tools: {state.recent_tools}")

        # Verify database was written to
        activity = await storage.get_session_activity(test_session_id)
        assert activity is not None, "Database should have session activity"
        assert "test_tool_1" in activity["recent_tools"], "Database should contain test_tool_1"
        print(f"   ✓ Database contains: {activity['recent_tools']}")

        # Test 2: record another tool
        print("\n4. Testing second tool call")
        state = await manager.record_tool("test_tool_2")
        assert len(state.recent_tools) >= 1, "Should have recent tools"
        print(f"   ✓ State has {len(state.recent_tools)} recent tools")

        # Verify database has both tools
        activity = await storage.get_session_activity(test_session_id)
        assert "test_tool_2" in activity["recent_tools"], "Database should contain test_tool_2"
        assert "test_tool_1" in activity["recent_tools"], "Database should still contain test_tool_1"
        print(f"   ✓ Database contains: {activity['recent_tools']}")

        # Test 3: Verify no legacy state-file writes are performed
        await asyncio.sleep(0.1)
        await manager.record_tool("test_tool_3")
        print("\n5. Verifying legacy state file is not written")
        assert not state_path.exists()
        print("   ✓ No legacy state-file writes in database-only mode")

        await storage.close()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        print("\nVerified:")
        print("  • Database writes work correctly")
        print("  • Multiple tool calls accumulate in database")
        print("  • legacy state file is NOT written to (database-only mode)")


if __name__ == "__main__":
    asyncio.run(test_record_tool_database_integration())
