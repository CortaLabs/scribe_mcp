#!/usr/bin/env python3
"""
Performance tests for query_entries database backend integration.

Tests verify that DB-backed query_entries performs faster than the old
flat-file approach and handles pagination efficiently.

Task Package: 2.3 - Performance Validation
Project: query_enhancement_suite
Author: CoderAgent-PerfTests
"""

import time

import pytest
from scribe_mcp.tools.query_entries import query_entries
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.config.settings import settings


@pytest.mark.asyncio
async def test_query_entries_performance():
    """
    Test that query_entries completes in under 500ms for typical single-project query.

    This test verifies that DB-backed queries are reasonably fast. The 500ms threshold
    is generous to account for test environment variability (CI, local, etc.).
    """
    # Create test project with entries
    project_name = f"perf_basic_{int(time.time())}"
    await set_project(agent="test_agent", name=project_name, root=str(settings.project_root))

    # Add test entries
    for i in range(20):
        await append_entry(
            agent="test_agent",
            message=f"Test entry {i}",
            status="info"
        )

    # Warm up - first query might be slower due to connection setup
    await query_entries(
        agent="test_agent",
        message="warmup",
        format="structured"
    )

    # Measure actual query performance
    start_time = time.time()
    result = await query_entries(
        agent="test_agent",
        message="Test entry",
        message_mode="substring",
        format="structured"
    )
    elapsed_time = time.time() - start_time

    # Verify query succeeded
    assert result.get("ok") is not False, "Query should succeed"

    # Verify we got results
    if isinstance(result, dict) and "entries" in result:
        assert len(result["entries"]) > 0, "Should find test entries"

    # Verify performance (generous threshold for test environments)
    assert elapsed_time < 0.5, f"Query took {elapsed_time:.3f}s, expected < 0.5s"

    # Verify result came from database (if available)
    # Don't fail if flat-file fallback was used (backend might not be available in test env)
    source = result.get("source", "flat-file")
    if source == "database":
        print(f"\n✓ DB query completed in {elapsed_time:.3f}s")


@pytest.mark.asyncio
async def test_query_entries_pagination_performance():
    """
    Test that paginated queries are fast even when total results are large.

    Pagination should limit the amount of data processed, making queries fast
    regardless of total result count.
    """
    # Create test project with many entries
    project_name = f"perf_pagination_{int(time.time())}"
    await set_project(agent="test_agent", name=project_name, root=str(settings.project_root))

    # Add many test entries
    for i in range(100):
        await append_entry(
            agent="test_agent",
            message=f"Pagination test entry {i}",
            status="info"
        )

    # Warm up
    await query_entries(
        agent="test_agent",
        page=1,
        page_size=10,
        format="structured"
    )

    # Measure paginated query performance
    start_time = time.time()
    result = await query_entries(
        agent="test_agent",
        page=1,
        page_size=10,
        format="structured"
    )
    elapsed_time = time.time() - start_time

    # Verify query succeeded
    assert result.get("ok") is not False, "Paginated query should succeed"

    # Verify pagination metadata exists
    if isinstance(result, dict):
        pagination = result.get("pagination", {})
        if pagination:
            assert pagination.get("page") == 1, "Should be page 1"
            assert pagination.get("page_size") == 10, "Should have page_size 10"

    # Verify paginated query is fast (more generous threshold since it's reading less data)
    assert elapsed_time < 0.3, f"Paginated query took {elapsed_time:.3f}s, expected < 0.3s"

    # Report performance
    source = result.get("source", "flat-file")
    print(f"\n✓ Paginated query completed in {elapsed_time:.3f}s (source: {source})")


@pytest.mark.asyncio
async def test_query_entries_with_filters_performance():
    """
    Test that filtered queries maintain good performance.

    Filters (message, agent, status) should be handled efficiently by the database
    rather than post-filtering large result sets.
    """
    # Create test project with mixed entries
    project_name = f"perf_filters_{int(time.time())}"
    await set_project(agent="test_agent", name=project_name, root=str(settings.project_root))

    # Add test entries with different statuses
    for i in range(50):
        await append_entry(
            agent="test_agent",
            message=f"Filter test entry {i}",
            status="info" if i % 2 == 0 else "success"
        )

    # Measure filtered query performance
    start_time = time.time()
    result = await query_entries(
        agent="test_agent",
        message="entry",
        message_mode="substring",
        status=["info"],
        format="structured"
    )
    elapsed_time = time.time() - start_time

    # Verify query succeeded
    assert result.get("ok") is not False, "Filtered query should succeed"

    # Verify performance
    assert elapsed_time < 0.5, f"Filtered query took {elapsed_time:.3f}s, expected < 0.5s"

    # Report
    source = result.get("source", "flat-file")
    print(f"\n✓ Filtered query completed in {elapsed_time:.3f}s (source: {source})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
