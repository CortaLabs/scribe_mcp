#!/usr/bin/env python3
"""
Test priority/category parameters for append_entry tool.

Tests the new priority, category, tags, and confidence parameters added
as part of scribe_tool_output_refinement project.
"""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import json
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.shared.log_enums import LogPriority, LogCategory


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


@pytest.mark.asyncio
async def test_explicit_priority():
    """Test explicit priority parameter."""
    raw_result = await append_entry(
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


@pytest.mark.asyncio
async def test_priority_from_status():
    """Test priority auto-inference from status."""
    # Bug status should infer high priority
    raw_result = await append_entry(
        message="Bug found in authentication module",
        status="bug",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Priority should be auto-inferred as 'high' from bug status
    assert "priority" in result.get("meta", {})
    assert result["meta"]["priority"] == "high"


@pytest.mark.asyncio
async def test_invalid_priority_defaults():
    """Test invalid priority defaults to medium."""
    raw_result = await append_entry(
        message="Test message with invalid priority",
        priority="invalid_priority_value",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Should default to medium for invalid priority
    assert "priority" in result.get("meta", {})
    assert result["meta"]["priority"] == "medium"


@pytest.mark.asyncio
async def test_category_validation():
    """Test category validation."""
    raw_result = await append_entry(
        message="Implemented new authentication flow",
        category="implementation",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    assert "category" in result.get("meta", {})
    assert result["meta"]["category"] == "implementation"


@pytest.mark.asyncio
async def test_invalid_category():
    """Test invalid category is rejected."""
    raw_result = await append_entry(
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


@pytest.mark.asyncio
async def test_tags_and_confidence():
    """Test tags and confidence parameters."""
    raw_result = await append_entry(
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


@pytest.mark.asyncio
async def test_bulk_mode_with_priority():
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
    raw_result = await append_entry(items_list=items, format="structured")
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    assert result.get("processed", 0) == 2
    assert result.get("successful", 0) == 2


@pytest.mark.asyncio
async def test_confidence_validation():
    """Test confidence range validation."""
    # Out of range should default to 1.0
    raw_result = await append_entry(
        message="Test confidence validation",
        confidence=1.5,  # Invalid, should default to 1.0
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Should be clamped/defaulted to 1.0
    assert result.get("meta", {}).get("confidence") == 1.0

    # Negative value should default to 1.0
    raw_result2 = await append_entry(
        message="Test negative confidence",
        confidence=-0.5,  # Invalid
        format="structured"
    )
    result2 = get_result_dict(raw_result2)
    assert result2["ok"] is True
    assert result2.get("meta", {}).get("confidence") == 1.0


@pytest.mark.asyncio
async def test_all_priority_levels():
    """Test all valid priority levels."""
    priorities = ["critical", "high", "medium", "low"]

    for priority in priorities:
        raw_result = await append_entry(
            message=f"Test message with {priority} priority",
            priority=priority,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("priority") == priority


@pytest.mark.asyncio
async def test_all_categories():
    """Test all valid categories."""
    categories = [
        "decision", "investigation", "bug", "implementation",
        "test", "milestone", "config", "security",
        "performance", "documentation"
    ]

    for category in categories:
        raw_result = await append_entry(
            message=f"Test message with {category} category",
            category=category,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("category") == category


@pytest.mark.asyncio
async def test_priority_status_mapping():
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
            message=f"Test {status} status",
            status=status,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("priority") == expected_priority


@pytest.mark.asyncio
async def test_backward_compatibility():
    """Test that existing code still works without new parameters."""
    # Old-style call without any new parameters
    raw_result = await append_entry(
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
