#!/usr/bin/env python
"""Quick test to verify query_entries DB routing works."""

import asyncio
from pathlib import Path

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.query_entries import query_entries

pytestmark = pytest.mark.asyncio


def _as_dict(result):
    if isinstance(result, dict):
        return result
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    return {}


async def test_db_routing(monkeypatch):
    """Test that query_entries routes to database."""
    print("\n=== Testing query_entries DB Routing ===\n")

    # Initialize storage backend
    db_path = Path(".scribe") / "scribe.db"
    storage = SQLiteStorage(db_path=str(db_path))
    monkeypatch.setattr(server_module, "storage_backend", storage)
    await storage._initialise()

    # Create test project
    print("1. Creating test project...")
    result = await set_project(
        agent="TestAgent",
        name="db_routing_test",
        root=str(Path.cwd())
    )
    result_data = _as_dict(result)
    print(f"   ✓ Project created: {result_data.get('project', {}).get('name', 'unknown')}")

    # Add some test entries
    print("\n2. Adding test entries to database...")
    for i in range(5):
        await append_entry(
            agent="TestAgent",
            message=f"Test entry {i+1} for DB routing verification",
            status="info",
            meta={"test_id": i, "phase": "db_test"}
        )
    print(f"   ✓ Added 5 test entries")

    # Query entries - should hit DB
    print("\n3. Querying entries (should use database)...")
    result = await query_entries(
        agent="TestAgent",
        message="routing",
        page_size=10,
        format="structured"
    )
    result_data = _as_dict(result)

    # Check results
    print(f"\n4. Results:")
    print(f"   - OK: {result_data.get('ok')}")
    print(f"   - Entries found: {result_data.get('total_found', 0)}")
    print(f"   - Entries returned: {result_data.get('returned', 0)}")
    print(f"   - Source: {result_data.get('source', 'NOT SET - flat-file used')}")

    if result_data.get("validation_warnings"):
        print(f"   Warnings: {result_data['validation_warnings']}")

    assert result_data.get("source") == "database", "query_entries should route to database"
    print("\n✅ SUCCESS: Database routing is working!")


if __name__ == "__main__":
    asyncio.run(test_db_routing())
    sys.exit(0)
