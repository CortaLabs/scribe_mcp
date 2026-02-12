#!/usr/bin/env python3
"""Test append_entry tool integration with AgentContextManager."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager


@pytest.mark.asyncio
async def test_append_entry_with_agent_context():
    """Test append_entry tool integration with agent context."""
    print("🧪 Testing append_entry with AgentContextManager integration...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        agent_manager = AgentContextManager(storage, state_manager)

        # Test 1: Set projects for different agents
        print("  ✓ Setting up projects for agents...")

        # Create projects
        project_a = await storage.upsert_project(
            name="AgentAProject",
            repo_root=str(temp_path / "project_a"),
            progress_log_path=str(temp_path / "project_a" / "PROGRESS_LOG.md")
        )

        project_b = await storage.upsert_project(
            name="AgentBProject",
            repo_root=str(temp_path / "project_b"),
            progress_log_path=str(temp_path / "project_b" / "PROGRESS_LOG.md")
        )

        # Create progress log directories and files
        (temp_path / "project_a").mkdir(parents=True, exist_ok=True)
        (temp_path / "project_b").mkdir(parents=True, exist_ok=True)
        (temp_path / "project_a" / "PROGRESS_LOG.md").touch()
        (temp_path / "project_b" / "PROGRESS_LOG.md").touch()

        # Set agent projects
        session_a = await agent_manager.start_session("AgentA")
        await agent_manager.set_current_project("AgentA", "AgentAProject", session_a)

        session_b = await agent_manager.start_session("AgentB")
        await agent_manager.set_current_project("AgentB", "AgentBProject", session_b)

        # Test 2: Verify agent isolation
        print("  ✓ Testing agent project isolation...")
        current_a = await agent_manager.get_current_project("AgentA")
        current_b = await agent_manager.get_current_project("AgentB")

        if current_a["project_name"] == "AgentAProject" and current_b["project_name"] == "AgentBProject":
            print("    ✓ Agent isolation confirmed")
        else:
            print("    ❌ Agent isolation failed")
            return False

        # Test 3: Simulate append_entry functionality
        print("  ✓ Testing agent-scoped project resolution...")

        # Simulate what append_entry would do for AgentA
        agent_project_a = await agent_manager.get_current_project("AgentA")
        if agent_project_a and agent_project_a.get("project_name") == "AgentAProject":
            print("    ✓ AgentA can resolve its project")
        else:
            print("    ❌ AgentA cannot resolve its project")
            return False

        # Simulate what append_entry would do for AgentB
        agent_project_b = await agent_manager.get_current_project("AgentB")
        if agent_project_b and agent_project_b.get("project_name") == "AgentBProject":
            print("    ✓ AgentB can resolve its project")
        else:
            print("    ❌ AgentB cannot resolve its project")
            return False

        # Test 4: Test agent with no project (fallback)
        print("  ✓ Testing fallback for agent with no project...")
        session_c = await agent_manager.start_session("AgentC")
        # Don't set a project for AgentC

        agent_project_c = await agent_manager.get_current_project("AgentC")
        if agent_project_c is None:
            print("    ✓ AgentC correctly returns None for no project")
        else:
            print("    ❌ AgentC should return None for no project")
            return False

        # Test 5: Session validation
        print("  ✓ Testing session validation...")
        await agent_manager.end_session("AgentA", session_a)

        try:
            await agent_manager.get_current_project("AgentA")
            # Should still work for reading, but setting would fail
            print("    ✓ Reading project after session end still works")
        except Exception as e:
            print(f"    ❌ Reading project should work after session end: {e}")
            return False

        await storage.close()

    print("✅ append_entry integration tests completed successfully!")
    return True


@pytest.mark.asyncio
async def test_agent_context_isolation():
    """Test that agents can't interfere with each other's projects."""
    print("🧪 Testing agent context isolation...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        agent_manager = AgentContextManager(storage, state_manager)

        # Create project
        project = await storage.upsert_project(
            name="SharedProject",
            repo_root=str(temp_path / "shared"),
            progress_log_path=str(temp_path / "shared" / "PROGRESS_LOG.md")
        )
        (temp_path / "shared").mkdir(parents=True, exist_ok=True)
        (temp_path / "shared" / "PROGRESS_LOG.md").touch()

        # Both agents set the same project
        session_a = await agent_manager.start_session("AgentA")
        session_b = await agent_manager.start_session("AgentB")

        result_a = await agent_manager.set_current_project("AgentA", "SharedProject", session_a)
        result_b = await agent_manager.set_current_project("AgentB", "SharedProject", session_b)

        # Both should be able to access the same project
        current_a = await agent_manager.get_current_project("AgentA")
        current_b = await agent_manager.get_current_project("AgentB")

        if (current_a["project_name"] == "SharedProject" and
            current_b["project_name"] == "SharedProject"):
            print("    ✓ Multiple agents can access the same project")
        else:
            print("    ❌ Agents should be able to access the same project")
            return False

        # Verify versioning works independently for each agent
        version_a = current_a["version"]
        version_b = current_b["version"]

        # AgentA updates project
        await agent_manager.set_current_project("AgentA", "SharedProject", session_a)
        updated_a = await agent_manager.get_current_project("AgentA")
        updated_b = await agent_manager.get_current_project("AgentB")

        # Each agent has its own version tracking (this is correct behavior)
        if (updated_a["version"] > version_a and
            updated_b["version"] == version_b):
            print("    ✓ Agent versioning works independently (correct behavior)")
            print(f"      AgentA version: {version_a} -> {updated_a['version']}")
            print(f"      AgentB version: {version_b} (unchanged)")
        else:
            print("    ❌ Agent versioning should work independently")
            return False

        await storage.close()

    print("✅ Agent context isolation tests completed successfully!")
    return True


async def main():
    """Run all append_entry integration tests."""
    print("🚀 Starting append_entry integration tests...\n")

    success1 = await test_append_entry_with_agent_context()
    print()
    success2 = await test_agent_context_isolation()

    if success1 and success2:
        print("\n🎉 All append_entry integration tests passed!")
    else:
        print("\n❌ Some tests failed!")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())