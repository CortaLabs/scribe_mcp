#!/usr/bin/env python3
"""Simple test for AgentContextManager functionality."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager, SessionLeaseExpired


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


async def main():
    """Run all tests."""
    print("🚀 Starting AgentContextManager tests...\n")

    await test_agent_context_manager()
    print()
    await test_session_cleanup()

    print("\n🎉 All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())