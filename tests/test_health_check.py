#!/usr/bin/env python3
"""Test health check functionality."""

import asyncio
import tempfile
from pathlib import Path

import os
import pytest
# Set the environment to use the local MCP_SPINE as the root
os.environ["SCRIBE_ROOT"] = str(Path(__file__).parent.parent)

# Import using the correct module path
import scribe_mcp.storage.sqlite
import scribe_mcp.state.manager
import scribe_mcp.state.agent_manager
import scribe_mcp.tools.health_check
import scribe_mcp.server


@pytest.mark.asyncio
async def test_health_check():
    """Test health check functionality."""
    print("🧪 Testing health check functionality...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = scribe_mcp.storage.sqlite.SQLiteStorage(db_path)
        await storage.setup()
        state_manager = scribe_mcp.state.manager.StateManager(state_path)
        agent_manager = scribe_mcp.state.agent_manager.AgentContextManager(storage, state_manager)

        # Mock the server module globals (preserve originals for cleanup)
        original_storage = getattr(scribe_mcp.server, "storage_backend", None)
        original_state_manager = getattr(scribe_mcp.server, "state_manager", None)
        original_get_agent_context_manager = getattr(scribe_mcp.server, "get_agent_context_manager", None)

        scribe_mcp.server.storage_backend = storage
        scribe_mcp.server.state_manager = state_manager

        def _agent_manager_proxy():
            return agent_manager

        scribe_mcp.server.get_agent_context_manager = _agent_manager_proxy

        # Create a project and session to generate activity
        project = await storage.upsert_project(
            name="HealthCheckTestProject",
            repo_root=str(temp_path / "health_test"),
            progress_log_path=str(temp_path / "health_test" / "log.md")
        )

        session_id = await agent_manager.start_session("HealthAgent")
        await agent_manager.set_current_project("HealthAgent", "HealthCheckTestProject", session_id)

        try:
            print("  ✓ Running health check...")
            health_result = await scribe_mcp.tools.health_check.health_check(agent="HealthAgent")

            print(f"  Overall status: {health_result['status']}")
            print(f"  Summary: {health_result['summary']}")

            # Check components
            for component, status in health_result['components'].items():
                print(f"  {component}: {status['status']} - {status['message']}")

            # Check metrics
            if health_result['metrics']:
                print("  Metrics:")
                for metric, value in health_result['metrics'].items():
                    print(f"    {metric}: {value}")

            # Check for issues
            if health_result['issues']:
                print("  Issues found:")
                for issue in health_result['issues']:
                    print(f"    - {issue}")

            # Check recommendations
            if health_result['recommendations']:
                print("  Recommendations:")
                for rec in health_result['recommendations']:
                    print(f"    - {rec}")

            # Validate health check
            if health_result['status'] in ['healthy', 'degraded']:
                print("  ✓ Health check completed successfully")
                if health_result['status'] == 'healthy':
                    print("  ✅ System is fully operational")
                else:
                    print("  ⚠️  System is operational with some issues")
            else:
                print("  ❌ Health check detected serious problems")
                return False
        finally:
            await storage.close()
            scribe_mcp.server.storage_backend = original_storage
            scribe_mcp.server.state_manager = original_state_manager
            if original_get_agent_context_manager is not None:
                scribe_mcp.server.get_agent_context_manager = original_get_agent_context_manager

    print("✅ Health check tests completed successfully!")
    return True


async def main():
    """Run health check test."""
    print("🚀 Starting health check test...\n")

    success = await test_health_check()

    if success:
        print("\n🎉 Health check test passed!")
        print("🏥 System monitoring is fully functional!")
    else:
        print("\n❌ Health check test failed!")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
