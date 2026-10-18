#!/usr/bin/env python3
"""
Test priority/category parameters for append_entry tool.

Tests the new priority, category, tags, and confidence parameters added
as part of scribe_tool_output_refinement project.
"""

import pytest
import pytest_asyncio
import json
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.config.settings import settings
from scribe_mcp.shared.log_enums import LogPriority, LogCategory


@pytest_asyncio.fixture(loop_scope="module")
async def test_project():
    """Bind a DB-backed project for the suite.

    append_entry resolves project context through the database/session path, so
    a project must be established via set_project first. The legacy state.json
    global-project default no longer satisfies this. The module-scoped loop keeps
    the loop-bound context binding valid across every test in this suite, matching
    the convention in test_query_priority_filters.py.
    """
    project_name = "test_append_entry_priority"
    await set_project(
        agent="test_agent",
        name=project_name,
        root=str(settings.project_root),
    )
    return project_name


def get_result_dict(result):
    """Extract dict from CallToolResult or return dict directly."""
    try:
        from mcp.types import CallToolResult, TextContent
        if isinstance(result, CallToolResult):
            # For structured format, parse the text content as JSON
            if len(result.content) == 1 and isinstance(result.content[0], TextContent):
                text = result.content[0].text
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # Return a dict with the text as a message
                    return {"ok": True, "text": text}
            return {"ok": True}
    except ImportError:
        pass

    # Already a dict
    if isinstance(result, dict):
        return result

    return {"ok": True}


@pytest.mark.asyncio(loop_scope="module")
async def test_explicit_priority(test_project):
    """Test explicit priority parameter."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Critical security issue detected",
        priority="critical",
        category="security",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Verify priority was set in metadata
    assert "priority" in result.get("meta", {})
    assert result["meta"]["priority"] == "critical"


@pytest.mark.asyncio(loop_scope="module")
async def test_priority_from_status(test_project):
    """Test priority auto-inference from status."""
    # Bug status should infer high priority
    raw_result = await append_entry(
        agent="test_agent",
        message="Bug found in authentication module",
        status="bug",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Priority should be auto-inferred as 'high' from bug status
    assert "priority" in result.get("meta", {})
    assert result["meta"]["priority"] == "high"


@pytest.mark.asyncio(loop_scope="module")
async def test_invalid_priority_defaults(test_project):
    """Test invalid priority defaults to medium."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Test message with invalid priority",
        priority="invalid_priority_value",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Should default to medium for invalid priority
    assert "priority" in result.get("meta", {})
    assert result["meta"]["priority"] == "medium"


@pytest.mark.asyncio(loop_scope="module")
async def test_category_validation(test_project):
    """Test category validation."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Implemented new authentication flow",
        category="implementation",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    assert "category" in result.get("meta", {})
    assert result["meta"]["category"] == "implementation"


@pytest.mark.asyncio(loop_scope="module")
async def test_invalid_category(test_project):
    """Test invalid category is rejected."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Test message",
        category="invalid_category",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Invalid category should be None (not stored)
    meta = result.get("meta", {})
    # Either not present or None
    assert meta.get("category") is None


@pytest.mark.asyncio(loop_scope="module")
async def test_tags_and_confidence(test_project):
    """Test tags and confidence parameters."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Refactored authentication module for better performance",
        tags=["refactor", "performance", "auth"],
        confidence=0.85,
        category="implementation",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    assert "tags" in result.get("meta", {})
    assert "confidence" in result.get("meta", {})
    assert result["meta"]["confidence"] == 0.85


@pytest.mark.asyncio(loop_scope="module")
async def test_bulk_mode_with_priority(test_project):
    """Test bulk mode with per-item priority."""
    items = [
        {
            "message": "Critical bug in payment processing",
            "priority": "critical",
            "category": "bug",
            "confidence": 0.95
        },
        {
            "message": "Minor documentation update",
            "priority": "low",
            "category": "documentation",
            "confidence": 1.0
        },
    ]
    raw_result = await append_entry(agent="test_agent", items_list=items, format="structured")
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    assert result.get("processed", 0) == 2
    assert result.get("successful", 0) == 2


@pytest.mark.asyncio(loop_scope="module")
async def test_confidence_validation(test_project):
    """Test confidence range validation (F6 clamp-toward-truth contract)."""
    # Out-of-range values clamp into [0.0, 1.0] rather than defaulting to MAX.
    raw_result = await append_entry(
        agent="test_agent",
        message="Test confidence validation",
        confidence=1.5,  # Above range -> clamps to ceiling 1.0
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # F6: above-range value clamps to the ceiling 1.0.
    assert result.get("meta", {}).get("confidence") == 1.0

    # F6 heals toward truth, not toward MAX: a negative value clamps to the
    # floor 0.0 (NOT silently promoted to 1.0, which was the prior bug).
    raw_result2 = await append_entry(
        agent="test_agent",
        message="Test negative confidence",
        confidence=-0.5,  # Out of range
        format="structured"
    )
    result2 = get_result_dict(raw_result2)
    assert result2["ok"] is True
    assert result2.get("meta", {}).get("confidence") == 0.0


@pytest.mark.asyncio(loop_scope="module")
async def test_all_priority_levels(test_project):
    """Test all valid priority levels."""
    priorities = ["critical", "high", "medium", "low"]

    for priority in priorities:
        raw_result = await append_entry(
            agent="test_agent",
            message=f"Test message with {priority} priority",
            priority=priority,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("priority") == priority


@pytest.mark.asyncio(loop_scope="module")
async def test_all_categories(test_project):
    """Test all valid categories."""
    categories = [
        "decision", "investigation", "bug", "implementation",
        "test", "milestone", "config", "security",
        "performance", "documentation"
    ]

    for category in categories:
        raw_result = await append_entry(
            agent="test_agent",
            message=f"Test message with {category} category",
            category=category,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("category") == category


@pytest.mark.asyncio(loop_scope="module")
async def test_priority_status_mapping(test_project):
    """Test priority auto-inference from different status values."""
    status_priority_map = {
        "error": "high",
        "bug": "high",
        "warn": "medium",
        "success": "medium",
        "info": "low",
        "plan": "medium"
    }

    for status, expected_priority in status_priority_map.items():
        raw_result = await append_entry(
            agent="test_agent",
            message=f"Test {status} status",
            status=status,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("priority") == expected_priority


@pytest.mark.asyncio(loop_scope="module")
async def test_backward_compatibility(test_project):
    """Test that existing code still works without new parameters."""
    # Old-style call without any new parameters
    raw_result = await append_entry(
        agent="test_agent",
        message="Test backward compatibility",
        status="success",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Should have auto-inferred priority from status
    assert "priority" in result.get("meta", {})


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
