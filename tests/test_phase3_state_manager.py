#!/usr/bin/env python3
"""Inline functional test for Phase 3 Tasks 3.3-3.4: StateManager database integration."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage

pytestmark = pytest.mark.asyncio


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
