#!/usr/bin/env python3
"""Test script to verify tool_calls table schema and methods."""

import asyncio
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.sqlite import SQLiteStorage

pytestmark = pytest.mark.asyncio


async def test_schema_creation():
    """Test that tool_calls table and indexes are created."""
    print("=" * 60)
    print("TEST 1: Schema Creation")
    print("=" * 60)

    # Create temporary database
    test_db = Path("/tmp/test_tool_calls.db")
    if test_db.exists():
        test_db.unlink()

    storage = SQLiteStorage(test_db)
    await storage.setup()

    # Check table exists
    conn = sqlite3.connect(test_db)
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='tool_calls';"
    )
    result = cursor.fetchone()
    conn.close()

    if result:
        print("✅ tool_calls table created successfully")
        print(f"\nTable schema:\n{result[0]}")
    else:
        print("❌ tool_calls table NOT found")
        pytest.fail("tool_calls schema behavior validation failed")

    # Check indexes exist
    conn = sqlite3.connect(test_db)
    cursor = conn.execute(
        """SELECT name FROM sqlite_master
           WHERE type='index' AND tbl_name='tool_calls'
           ORDER BY name;"""
    )
    indexes = cursor.fetchall()
    conn.close()

    expected_indexes = [
        'idx_tool_calls_project',
        'idx_tool_calls_session',
        'idx_tool_calls_timestamp',
        'idx_tool_calls_tool_name'
    ]

    found_indexes = [idx[0] for idx in indexes]
    print(f"\n✅ Found {len(found_indexes)} indexes:")
    for idx in found_indexes:
        print(f"   - {idx}")

    missing = set(expected_indexes) - set(found_indexes)
    if missing:
        print(f"\n❌ Missing indexes: {missing}")
        pytest.fail("tool_calls schema behavior validation failed")

    # Check foreign key constraint
    conn = sqlite3.connect(test_db)
    cursor = conn.execute("PRAGMA foreign_key_list(tool_calls);")
    fk = cursor.fetchone()
    conn.close()

    if fk and fk[2] == 'scribe_sessions':
        print(f"\n✅ Foreign key constraint verified: session_id → scribe_sessions")
    else:
        print("\n❌ Foreign key constraint NOT found")
        pytest.fail("tool_calls schema behavior validation failed")

    return


async def test_record_tool_call():
    """Test record_tool_call method."""
    print("\n" + "=" * 60)
    print("TEST 2: record_tool_call() Method")
    print("=" * 60)

    test_db = Path("/tmp/test_tool_calls.db")
    storage = SQLiteStorage(test_db)
    await storage.setup()

    # First create a test session (required by FK constraint)
    await storage.upsert_session(
        session_id="test-session-123",
        transport_session_id="transport-123",
        agent_id="test-agent",
        repo_root="/tmp/test",
        mode="sentinel"
    )

    # Record a tool call
    await storage.record_tool_call(
        session_id="test-session-123",
        tool_name="list_projects",
        duration_ms=45.2,
        status="success",
        format_requested="readable",
        project_name="test_project",
        agent_id="test-agent",
        response_size_bytes=1024
    )

    # Verify it was inserted
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM tool_calls WHERE session_id = 'test-session-123';"
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        print("✅ Tool call recorded successfully")
        print(f"\n   ID: {row['id']}")
        print(f"   Tool: {row['tool_name']}")
        print(f"   Duration: {row['duration_ms']}ms")
        print(f"   Status: {row['status']}")
        print(f"   Format: {row['format_requested']}")
        print(f"   Project: {row['project_name']}")
        print(f"   Agent: {row['agent_id']}")
        print(f"   Size: {row['response_size_bytes']} bytes")
        return
    else:
        print("❌ Tool call was NOT recorded")
        pytest.fail("tool_calls schema behavior validation failed")


async def test_get_session_tool_calls():
    """Test get_session_tool_calls method."""
    print("\n" + "=" * 60)
    print("TEST 3: get_session_tool_calls() Method")
    print("=" * 60)

    test_db = Path("/tmp/test_tool_calls.db")
    storage = SQLiteStorage(test_db)
    await storage.setup()

    # Record multiple tool calls
    tools = ["append_entry", "list_projects", "get_project", "query_entries"]
    for i, tool in enumerate(tools):
        await storage.record_tool_call(
            session_id="test-session-123",
            tool_name=tool,
            duration_ms=10.0 + i * 5,
            status="success",
            format_requested="readable"
        )

    # Retrieve them
    results = await storage.get_session_tool_calls("test-session-123")

    if results and len(results) >= 4:  # At least 4 new + 1 from previous test
        print(f"✅ Retrieved {len(results)} tool calls")
        print(f"\nLast 5 calls (newest first):")
        for call in results[:5]:
            print(f"   - {call['tool_name']} ({call['duration_ms']}ms)")
        return
    else:
        print(f"❌ Expected at least 4 calls, got {len(results) if results else 0}")
        pytest.fail("tool_calls schema behavior validation failed")


async def test_get_tool_metrics():
    """Test get_tool_metrics method."""
    print("\n" + "=" * 60)
    print("TEST 4: get_tool_metrics() Method")
    print("=" * 60)

    test_db = Path("/tmp/test_tool_calls.db")
    storage = SQLiteStorage(test_db)
    await storage.setup()

    # Get metrics for all tools
    metrics = await storage.get_tool_metrics()

    print(f"✅ Metrics retrieved successfully")
    print(f"\n   Total calls: {metrics['total_calls']}")
    print(f"   Success count: {metrics['success_count']}")
    print(f"   Error count: {metrics['error_count']}")
    print(f"   Avg duration: {metrics['avg_duration_ms']:.2f}ms" if metrics['avg_duration_ms'] else "   Avg duration: N/A")
    print(f"   P95 duration: {metrics['p95_duration_ms']:.2f}ms" if metrics['p95_duration_ms'] else "   P95 duration: N/A")
    print(f"   Total bytes: {metrics['total_response_bytes']}" if metrics['total_response_bytes'] else "   Total bytes: N/A")

    # Get metrics for specific tool
    list_metrics = await storage.get_tool_metrics(tool_name="list_projects")
    print(f"\n✅ Tool-specific metrics (list_projects):")
    print(f"   Total calls: {list_metrics['total_calls']}")

    return


async def test_cascade_delete():
    """Test that tool_calls are deleted when session is deleted."""
    print("\n" + "=" * 60)
    print("TEST 5: Cascade Delete (FK Constraint)")
    print("=" * 60)

    test_db = Path("/tmp/test_tool_calls.db")
    storage = SQLiteStorage(test_db)
    await storage.setup()

    # Count tool calls before deletion
    calls_before = await storage.get_session_tool_calls("test-session-123")
    print(f"Tool calls before session deletion: {len(calls_before)}")

    # Actually DELETE the session from scribe_sessions table (end_session only marks expired)
    # Need to use direct SQL to test CASCADE DELETE
    conn = sqlite3.connect(test_db)
    conn.execute("PRAGMA foreign_keys = ON;")  # Enable FK constraints
    conn.execute("DELETE FROM scribe_sessions WHERE session_id = 'test-session-123';")
    conn.commit()
    conn.close()

    # Count tool calls after deletion
    calls_after = await storage.get_session_tool_calls("test-session-123")
    print(f"Tool calls after session deletion: {len(calls_after)}")

    if len(calls_after) == 0:
        print("✅ CASCADE DELETE working - tool_calls cleaned up with session")
        return
    else:
        print("❌ CASCADE DELETE failed - orphaned tool_calls remain")
        pytest.fail("tool_calls schema behavior validation failed")


async def main():
    """Run all tests."""
    print("\n🧪 Testing Tool Calls Schema and Storage Methods\n")

    tests = [
        test_schema_creation,
        test_record_tool_call,
        test_get_session_tool_calls,
        test_get_tool_metrics,
        test_cascade_delete
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✅ All tests PASSED!")
        return 0
    else:
        print(f"❌ {total - passed} test(s) FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
