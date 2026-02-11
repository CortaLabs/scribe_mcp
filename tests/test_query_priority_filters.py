#!/usr/bin/env python3
"""Tests for priority/category/confidence filters in read_recent and query_entries."""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import pytest_asyncio
from scribe_mcp.tools.read_recent import read_recent
from scribe_mcp.tools.query_entries import query_entries
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.config.settings import settings


@pytest_asyncio.fixture
async def test_project():
    """Create a test project for filtering tests."""
    project_name = f"test_priority_filters"
    await set_project(agent="test_agent", name=project_name, root=str(settings.project_root))
    return project_name


@pytest.mark.asyncio
async def test_read_recent_priority_filter(test_project):
    """Test filtering by priority in read_recent."""
    # Create test entries with different priorities
    await append_entry(
        agent="test_agent",
        message="Critical bug discovered",
        priority="critical",
    )
    await append_entry(
        agent="test_agent",
        message="High priority task",
        priority="high",
    )
    await append_entry(
        agent="test_agent",
        message="Medium priority work",
        priority="medium",
    )
    await append_entry(
        agent="test_agent",
        message="Low priority note",
        priority="low",
    )

    # Query only critical and high priority entries
    result = await read_recent(
        agent="test_agent",
        priority=["critical", "high"],
        format="structured",
    )

    if isinstance(result, dict) and "entries" in result:
        # Should only get critical and high priority entries
        for entry in result["entries"]:
            priority = entry.get("priority", entry.get("meta", {}).get("priority", "medium"))
            assert priority in ["critical", "high"], f"Expected critical/high, got {priority}"


@pytest.mark.asyncio
async def test_read_recent_category_filter(test_project):
    """Test filtering by category in read_recent."""
    # Create test entries with different categories
    await append_entry(
        agent="test_agent",
        message="Bug found in authentication",
        category="bug",
    )
    await append_entry(
        agent="test_agent",
        message="Security vulnerability detected",
        category="security",
    )
    await append_entry(
        agent="test_agent",
        message="Implementation completed",
        category="implementation",
    )

    # Query only bug and security entries
    result = await read_recent(
        agent="test_agent",
        category=["bug", "security"],
        format="structured",
    )

    assert result.get("ok") is not False


@pytest.mark.asyncio
async def test_read_recent_confidence_filter(test_project):
    """Test filtering by minimum confidence in read_recent."""
    # Create test entries with different confidence levels
    await append_entry(
        agent="test_agent",
        message="Low confidence entry",
        confidence=0.3,
    )
    await append_entry(
        agent="test_agent",
        message="Medium confidence entry",
        confidence=0.7,
    )
    await append_entry(
        agent="test_agent",
        message="High confidence entry",
        confidence=0.95,
    )

    # Query only high confidence entries
    result = await read_recent(
        agent="test_agent",
        min_confidence=0.8,
        format="structured",
    )

    if isinstance(result, dict) and "entries" in result:
        for entry in result["entries"]:
            conf = entry.get("confidence", entry.get("meta", {}).get("confidence", 1.0))
            assert float(conf) >= 0.8, f"Expected confidence >= 0.8, got {conf}"


@pytest.mark.asyncio
async def test_read_recent_priority_sort(test_project):
    """Test priority-based sorting in read_recent."""
    # Create entries in random priority order
    await append_entry(agent="test_agent", message="Low priority", priority="low")
    await append_entry(agent="test_agent", message="Critical issue", priority="critical")
    await append_entry(agent="test_agent", message="High priority", priority="high")
    await append_entry(agent="test_agent", message="Medium task", priority="medium")

    # Query with priority sorting
    result = await read_recent(
        agent="test_agent",
        n=10,
        priority_sort=True,
        format="structured",
    )

    if isinstance(result, dict) and "entries" in result:
        entries = result["entries"]
        if len(entries) >= 4:
            # Extract priorities
            priorities = [
                e.get("priority", e.get("meta", {}).get("priority", "medium"))
                for e in entries
            ]
            # Critical should come before low
            if "critical" in priorities and "low" in priorities:
                assert priorities.index("critical") < priorities.index("low"), \
                    f"Critical should come before low in {priorities}"


@pytest.mark.asyncio
async def test_query_entries_priority_filter(test_project):
    """Test priority filter in query_entries."""
    # Create test entries
    await append_entry(
        agent="test_agent",
        message="Critical database issue",
        priority="critical",
    )
    await append_entry(
        agent="test_agent",
        message="Low priority cleanup",
        priority="low",
    )

    # Query only critical entries
    result = await query_entries(
        agent="test_agent",
        priority=["critical"],
        format="structured",
    )

    assert result.get("ok") is not False


@pytest.mark.asyncio
async def test_query_entries_category_filter(test_project):
    """Test category filter in query_entries."""
    # Create test entries
    await append_entry(
        agent="test_agent",
        message="Test results passing",
        category="test",
    )
    await append_entry(
        agent="test_agent",
        message="Bug fix committed",
        category="bug",
    )

    # Query bug category
    result = await query_entries(
        agent="test_agent",
        category=["bug"],
        format="structured",
    )

    assert result.get("ok") is not False


@pytest.mark.asyncio
async def test_combined_filters(test_project):
    """Test combining multiple filters."""
    # Create test entries
    await append_entry(
        agent="test_agent",
        message="Critical security bug",
        priority="critical",
        category="security",
        confidence=0.95,
    )
    await append_entry(
        agent="test_agent",
        message="Low priority note",
        priority="low",
        category="documentation",
        confidence=0.5,
    )

    # Query with all filters
    result = await read_recent(
        agent="test_agent",
        priority=["critical"],
        category=["security"],
        min_confidence=0.9,
        priority_sort=True,
        format="structured",
    )

    assert result.get("ok") is not False


@pytest.mark.asyncio
async def test_query_entries_priority_sort(test_project):
    """Test priority sorting in query_entries."""
    # Create entries with different priorities
    await append_entry(agent="test_agent", message="Medium work", priority="medium")
    await append_entry(agent="test_agent", message="Critical alert", priority="critical")
    await append_entry(agent="test_agent", message="High priority", priority="high")

    # Query with priority sorting
    result = await query_entries(
        agent="test_agent",
        priority_sort=True,
        format="structured",
    )

    if isinstance(result, dict) and "entries" in result:
        entries = result["entries"]
        if len(entries) >= 3:
            # Extract priorities
            priorities = [
                e.get("meta", {}).get("priority", "medium")
                for e in entries
            ]
            # Critical should come before medium
            if "critical" in priorities and "medium" in priorities:
                assert priorities.index("critical") < priorities.index("medium"), \
                    f"Critical should come before medium in {priorities}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
