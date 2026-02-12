#!/usr/bin/env python3
"""Test set_project tool integration with AgentContextManager."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager


@pytest.mark.asyncio
async def test_set_project_with_agent_context():
    """Test set_project tool integration with agent context."""
    print("🧪 Testing set_project with AgentContextManager integration...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        agent_manager = AgentContextManager(storage, state_manager)

        # Test 1: Set project for AgentA
        print("  ✓ Setting project for AgentA...")
        session_a = await agent_manager.start_session("AgentA")

        # Create project record first
        project = await storage.upsert_project(
            name="TestProjectA",
            repo_root=str(temp_path / "project_a"),
            progress_log_path=str(temp_path / "project_a" / "log.md")
        )

        result = await agent_manager.set_current_project("AgentA", "TestProjectA", session_a)
        print(f"    AgentA project: {result['project_name']} (version {result['version']})")

        # Test 2: Set different project for AgentB
        print("  ✓ Setting different project for AgentB...")
        session_b = await agent_manager.start_session("AgentB")

        project_b = await storage.upsert_project(
            name="TestProjectB",
            repo_root=str(temp_path / "project_b"),
            progress_log_path=str(temp_path / "project_b" / "log.md")
        )

        result_b = await agent_manager.set_current_project("AgentB", "TestProjectB", session_b)
        print(f"    AgentB project: {result_b['project_name']} (version {result_b['version']})")

        # Test 3: Verify agent isolation
        print("  ✓ Verifying agent isolation...")
        current_a = await agent_manager.get_current_project("AgentA")
        current_b = await agent_manager.get_current_project("AgentB")

        if current_a["project_name"] == "TestProjectA" and current_b["project_name"] == "TestProjectB":
            print("    ✓ Agent isolation working correctly")
        else:
            print("    ❌ Agent isolation failed")
            return False

        # Test 4: Version conflict detection
        print("  ✓ Testing version conflict detection...")
        try:
            # Try to update with wrong version
            await agent_manager.set_current_project(
                "AgentA", "NewProject", session_a, expected_version=999
            )
            print("    ❌ Should have detected version conflict")
            return False
        except Exception as e:
            print(f"    ✓ Correctly detected version conflict: {type(e).__name__}")

        # Test 5: Session validation
        print("  ✓ Testing session validation...")
        expired_session = await agent_manager.start_session("TestAgent")
        await agent_manager.end_session("TestAgent", expired_session)

        try:
            await agent_manager.set_current_project("TestAgent", "TestProject", expired_session)
            print("    ❌ Should have rejected expired session")
            return False
        except Exception as e:
            print(f"    ✓ Correctly rejected expired session: {type(e).__name__}")

        await storage.close()

    print("✅ set_project integration tests completed successfully!")
    return True


@pytest.mark.asyncio
async def test_agent_context_migration():
    """Test legacy state migration to agent context."""
    print("🧪 Testing legacy state migration...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)

        # Set up legacy state
        legacy_state = await state_manager.load()
        legacy_state.current_project = "LegacyProject"
        await state_manager.persist(legacy_state)

        # Initialize agent manager and run migration
        agent_manager = AgentContextManager(storage, state_manager)

        from scribe_mcp.state.agent_manager import migrate_legacy_state
        await migrate_legacy_state(state_manager, storage)

        # Verify migration
        scribe_project = await agent_manager.get_current_project("Scribe")
        if scribe_project and scribe_project["project_name"] == "LegacyProject":
            print("    ✓ Legacy state migrated successfully")
        else:
            print("    ❌ Legacy state migration failed")
            return False

        # Verify legacy state was cleared
        current_state = await state_manager.load()
        if current_state.current_project is None:
            print("    ✓ Legacy global state cleared")
        else:
            print("    ❌ Legacy global state not cleared")
            return False

        await storage.close()

    print("✅ Legacy migration tests completed successfully!")
    return True


async def main():
    """Run all integration tests."""
    print("🚀 Starting set_project integration tests...\n")

    success1 = await test_set_project_with_agent_context()
    print()
    success2 = await test_agent_context_migration()

    if success1 and success2:
        print("\n🎉 All integration tests passed!")
    else:
        print("\n❌ Some tests failed!")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
