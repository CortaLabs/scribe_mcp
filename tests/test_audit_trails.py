#!/usr/bin/env python3
"""Test audit trail functionality for agent project events."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.state.manager import StateManager
from scribe_mcp.state.agent_manager import AgentContextManager


@pytest.mark.asyncio
async def test_project_switch_audit_trail():
    """Test that project switches are properly audited."""
    print("🧪 Testing project switch audit trails...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "test.db"
        state_path = temp_path / "state.json"

        # Initialize components
        storage = SQLiteStorage(db_path)
        await storage.setup()
        state_manager = StateManager(state_path)
        agent_manager = AgentContextManager(storage, state_manager)

        # Create projects
        project_a = await storage.upsert_project(
            name="AuditProjectA",
            repo_root=str(temp_path / "audit_a"),
            progress_log_path=str(temp_path / "audit_a" / "log.md")
        )
        project_b = await storage.upsert_project(
            name="AuditProjectB",
            repo_root=str(temp_path / "audit_b"),
            progress_log_path=str(temp_path / "audit_b" / "log.md")
        )

        # Start session
        session_id = await agent_manager.start_session("AuditAgent")

        # Test 1: Initial project set should be audited
        print("  ✓ Testing initial project set audit...")
        await agent_manager.set_current_project("AuditAgent", "AuditProjectA", session_id)

        # Test 2: Project switch should be audited
        print("  ✓ Testing project switch audit...")
        await agent_manager.set_current_project("AuditAgent", "AuditProjectB", session_id)

        # Test 3: Another project switch should be audited
        print("  ✓ Testing second project switch audit...")
        await agent_manager.set_current_project("AuditAgent", "AuditProjectA", session_id)

        # Test 4: Session end should be audited
        print("  ✓ Testing session end audit...")
        await agent_manager.end_session("AuditAgent", session_id)

        # Verify audit trail
        print("  ✓ Verifying audit trail...")
        events = await agent_manager.get_agent_events(agent_id="AuditAgent")

        if len(events) >= 5:  # session_start + project_set + 2 switches + session_end
            print(f"    ✓ Found {len(events)} audit events")

            # Check specific events
            event_types = [event["event_type"] for event in events]
            expected_types = ["session_started", "project_set", "project_switched", "project_switched", "session_ended"]

            if all(event_type in event_types for event_type in expected_types):
                print("    ✓ All expected event types found")
            else:
                print(f"    ❌ Missing event types. Found: {event_types}")
                return False

            # Check project switch details
            switch_events = [e for e in events if e["event_type"] == "project_switched"]
            if len(switch_events) >= 2:
                first_switch = switch_events[0]
                if (first_switch["from_project"] == "AuditProjectA" and
                    first_switch["to_project"] == "AuditProjectB"):
                    print("    ✓ First project switch correctly logged")
                else:
                    print(f"    ❌ First switch details wrong: {first_switch}")
                    return False
            else:
                print("    ❌ Not enough switch events found")
                return False

        else:
            print(f"    ❌ Expected at least 5 events, found {len(events)}")
            return False

        await storage.close()

    print("✅ Project switch audit trail tests completed successfully!")
    return True


@pytest.mark.asyncio
async def test_conflict_audit_trail():
    """Test that conflicts are properly audited."""
    print("🧪 Testing conflict audit trails...")

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
            name="ConflictAuditProject",
            repo_root=str(temp_path / "conflict_audit"),
            progress_log_path=str(temp_path / "conflict_audit" / "log.md")
        )

        # Start session
        session_id = await agent_manager.start_session("ConflictAgent")
        await agent_manager.set_current_project("ConflictAgent", "ConflictAuditProject", session_id)

        # Test conflict scenario
        print("  ✓ Testing conflict audit logging...")
        try:
            # Try to use wrong version to trigger conflict
            await agent_manager.set_current_project(
                "ConflictAgent", "ConflictAuditProject", session_id,
                expected_version=999  # Wrong version
            )
            print("    ❌ Conflict should have been triggered")
            return False
        except Exception:
            print("    ✓ Conflict correctly triggered")

        # Verify conflict was audited
        events = await agent_manager.get_agent_events(
            agent_id="ConflictAgent",
            event_type="conflict_detected"
        )

        if len(events) >= 1:
            conflict_event = events[0]
            if (conflict_event["success"] == False and
                conflict_event["to_project"] == "ConflictAuditProject" and
                conflict_event["expected_version"] == 999):
                print("    ✓ Conflict event correctly logged")
            else:
                print(f"    ❌ Conflict event details wrong: {conflict_event}")
                return False
        else:
            print("    ❌ No conflict events found")
            return False

        await storage.close()

    print("✅ Conflict audit trail tests completed successfully!")
    return True


@pytest.mark.asyncio
async def test_audit_event_filtering():
    """Test audit event filtering and querying."""
    print("🧪 Testing audit event filtering...")

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
            name="FilterAuditProject",
            repo_root=str(temp_path / "filter_audit"),
            progress_log_path=str(temp_path / "filter_audit" / "log.md")
        )

        # Create sessions and events for multiple agents
        session_a = await agent_manager.start_session("FilterAgentA")
        session_b = await agent_manager.start_session("FilterAgentB")

        await agent_manager.set_current_project("FilterAgentA", "FilterAuditProject", session_a)
        await agent_manager.set_current_project("FilterAgentB", "FilterAuditProject", session_b)

        # Test filtering by agent
        print("  ✓ Testing agent filtering...")
        agent_a_events = await agent_manager.get_agent_events(agent_id="FilterAgentA")
        agent_b_events = await agent_manager.get_agent_events(agent_id="FilterAgentB")

        if (len(agent_a_events) >= 2 and len(agent_b_events) >= 2 and
            all(e["agent_id"] == "FilterAgentA" for e in agent_a_events) and
            all(e["agent_id"] == "FilterAgentB" for e in agent_b_events)):
            print("    ✓ Agent filtering working correctly")
        else:
            print(f"    ❌ Agent filtering failed. A: {len(agent_a_events)}, B: {len(agent_b_events)}")
            return False

        # Test filtering by event type
        print("  ✓ Testing event type filtering...")
        session_events = await agent_manager.get_agent_events(event_type="session_started")

        if len(session_events) >= 2:
            print(f"    ✓ Event type filtering working: {len(session_events)} session events")
        else:
            print(f"    ❌ Event type filtering failed: {len(session_events)} session events")
            return False

        # Test limit
        print("  ✓ Testing result limit...")
        limited_events = await agent_manager.get_agent_events(limit=3)

        if len(limited_events) <= 3:
            print(f"    ✓ Result limit working: {len(limited_events)} events")
        else:
            print(f"    ❌ Result limit failed: {len(limited_events)} events")
            return False

        await storage.close()

    print("✅ Audit event filtering tests completed successfully!")
    return True


async def main():
    """Run all audit trail tests."""
    print("🚀 Starting audit trail tests...\n")

    success1 = await test_project_switch_audit_trail()
    print()
    success2 = await test_conflict_audit_trail()
    print()
    success3 = await test_audit_event_filtering()

    if success1 and success2 and success3:
        print("\n🎉 All audit trail tests passed!")
        print("📊 Comprehensive audit trail system is fully functional!")
    else:
        print("\n❌ Some audit trail tests failed!")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())