"""Warm actual DB-query timing, excluding SDK startup, setup and seeding."""

import time

import pytest

# The two legacy query modules share one SDK isolation/DB observation fixture.
from test_db_routing import (
    _entries,
    _missing_result_control,
    anyio_backend,
    query_project,
)


pytestmark = [pytest.mark.anyio, pytest.mark.regression, pytest.mark.storage]


async def _warm_query(call, threshold, **arguments):
    await call("query_entries", **arguments)
    start = time.perf_counter()
    result = await call("query_entries", **arguments)
    elapsed = time.perf_counter() - start
    print(f"Warm query: {elapsed:.6f}s; limit {threshold:.1f}s")
    assert elapsed < threshold, f"Query took {elapsed:.3f}s, expected < {threshold}s"
    return result


async def test_query_entries_performance(query_project):
    """The original 20-entry query must return every row within 500ms."""
    messages = [f"Test entry {i}" for i in range(20)]
    for message in messages:
        await query_project("append_entry", message=message, status="info")
    query_project.database_only(messages)
    result = await _warm_query(query_project, 0.5, message="Test entry",
                               message_mode="substring", page_size=50)
    _entries(result, messages)
    subset = await query_project("query_entries", message="Test entry 1",
                                  message_mode="substring", page_size=50)
    _entries(subset, [message for message in messages if "Test entry 1" in message])
    with pytest.raises(AssertionError):
        _entries(subset, messages)
    await _missing_result_control(query_project, messages)


async def test_query_entries_pagination_performance(query_project):
    """The original 100-entry corpus has exact, disjoint 10-row pages in 300ms."""
    messages = [f"Pagination test entry {i}" for i in range(100)]
    for i, message in enumerate(messages):
        await query_project("append_entry", message=message, status="info",
                            timestamp_utc=f"2026-01-03 14:{i // 60:02d}:{i % 60:02d} UTC")
    query_project.database_only(messages)
    newest = list(reversed(messages))
    result = await _warm_query(query_project, 0.3, page=1, page_size=10, limit=100)
    _entries(result, newest[:10], total=100, ordered=True)
    for page, current in ((1, result), (2, await query_project(
            "query_entries", page=2, page_size=10, limit=100)), (10, await query_project(
            "query_entries", page=10, page_size=10, limit=100))):
        _entries(current, newest[(page - 1) * 10:page * 10], total=100, ordered=True)
        pagination = current["pagination"]
        assert pagination["page"] == page and pagination["page_size"] == 10
        assert pagination["total_count"] == 100
        assert pagination["has_next"] is (page < 10)
        assert pagination["has_prev"] is (page > 1)
    second = await query_project("query_entries", page=2, page_size=10, limit=100)
    with pytest.raises(AssertionError):
        _entries(second, newest[:10], total=100, ordered=True)
    await _missing_result_control(query_project, newest[:10])


async def test_query_entries_with_filters_performance(query_project):
    """Original 50 mixed statuses: exactly 25 info matches within 500ms."""
    messages = [f"Filter test entry {i}" for i in range(50)]
    for i, message in enumerate(messages):
        await query_project("append_entry", message=message,
                            status="info" if i % 2 == 0 else "success")
    query_project.database_only(messages)
    result = await _warm_query(query_project, 0.5, message="entry",
                               message_mode="substring", status=["info"], page_size=50)
    _entries(result, messages[::2])
    unfiltered = await query_project("query_entries", message="entry", page_size=50)
    _entries(unfiltered, messages)
    excluded = await query_project("query_entries", message="entry",
                                    status=["success"], page_size=50)
    _entries(excluded, messages[1::2])
    with pytest.raises(AssertionError):
        _entries(excluded, messages[::2])
    await _missing_result_control(query_project, messages[::2])
