#!/usr/bin/env python3
"""Test versioning behavior with multiple agents."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager


@pytest.mark.asyncio
async def test_multi_agent_versioning():
    """Test versioning behavior with multiple agents."""
    print("🧪 Testing multi-agent versioning behavior...")

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
            name="TestProject",
            repo_root=str(temp_path / "test"),
            progress_log_path=str(temp_path / "test" / "PROGRESS_LOG.md")
        )

        # Test 1: Two agents set the same project
        print("  ✓ Setting project for two agents...")
        session_a = await agent_manager.start_session("AgentA")
        session_b = await agent_manager.start_session("AgentB")

        result_a = await agent_manager.set_current_project("AgentA", "TestProject", session_a)
        result_b = await agent_manager.set_current_project("AgentB", "TestProject", session_b)

        print(f"    AgentA version: {result_a['version']}")
        print(f"    AgentB version: {result_b['version']}")

        # Test 2: Check if they share the same agent_projects record
        print("  ✓ Checking database state...")
        current_a = await agent_manager.get_current_project("AgentA")
        current_b = await agent_manager.get_current_project("AgentB")

        print(f"    AgentA current: {current_a}")
        print(f"    AgentB current: {current_b}")

        # Test 3: AgentA updates project
        print("  ✓ AgentA updates project...")
        result_a2 = await agent_manager.set_current_project("AgentA", "TestProject", session_a, expected_version=current_a["version"])
        print(f"    AgentA new version: {result_a2['version']}")

        # Test 4: Check AgentB's view
        print("  ✓ Checking AgentB's view after AgentA's update...")
        updated_b = await agent_manager.get_current_project("AgentB")
        print(f"    AgentB sees version: {updated_b['version']}")

        # Test 5: Try to understand the database structure
        print("  ✓ Examining database directly...")
        try:
            # Check agent_projects table
            agent_projects = await storage._fetchall("SELECT * FROM agent_projects")
            print(f"    Agent projects in DB: {agent_projects}")

            # Check scribe_projects table
            scribe_projects = await storage._fetchall("SELECT * FROM scribe_projects")
            print(f"    Scribe projects in DB: {scribe_projects}")

        except Exception as e:
            print(f"    Database examination failed: {e}")

        await storage.close()

    print("✅ Multi-agent versioning test completed!")
    return True


async def main():
    """Run versioning test."""
    print("🚀 Starting versioning behavior test...\n")

    await test_multi_agent_versioning()
    print("\n🎉 Versioning test completed!")


if __name__ == "__main__":
    asyncio.run(main())