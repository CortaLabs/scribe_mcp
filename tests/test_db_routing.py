#!/usr/bin/env python
"""Quick test to verify query_entries DB routing works."""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp import server as server_module
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.query_entries import query_entries


async def test_db_routing():
    """Test that query_entries routes to database."""
    print("\n=== Testing query_entries DB Routing ===\n")

    # Initialize storage backend
    db_path = Path(".scribe") / "scribe.db"
    storage = SQLiteStorage(db_path=str(db_path))
    server_module.storage_backend = storage
    await storage._initialise()

    # Create test project
    print("1. Creating test project...")
    result = await set_project(
        agent="TestAgent",
        name="db_routing_test",
        root="/home/austin/projects/MCP_SPINE/scribe_mcp"
    )
    print(f"   ✓ Project created: {result.get('project', {}).get('name')}")

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

    # Check results
    print(f"\n4. Results:")
    print(f"   - OK: {result.get('ok')}")
    print(f"   - Entries found: {result.get('total_found', 0)}")
    print(f"   - Entries returned: {result.get('returned', 0)}")
    print(f"   - Source: {result.get('source', 'NOT SET - flat-file used')}")

    if result.get("source") == "database":
        print("\n✅ SUCCESS: Database routing is working!")
        return True
    else:
        print("\n❌ FAILURE: Still using flat-file fallback")
        if result.get("validation_warnings"):
            print(f"   Warnings: {result['validation_warnings']}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_db_routing())
    sys.exit(0 if success else 1)
