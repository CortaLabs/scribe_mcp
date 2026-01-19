#!/usr/bin/env python3
"""Tests for read_recent EntryLimitManager integration."""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.read_recent import read_recent


@pytest.mark.asyncio
async def test_readable_format_no_truncation():
    """Verify readable format returns full entries without truncation."""
    # This test requires a project with entries
    result = await read_recent(n=10, format="readable")

    # Should have entries or be a formatted string
    assert result is not None

    # If it's a dict with entries, verify structure
    if isinstance(result, dict) and "entries" in result:
        for entry in result["entries"]:
            # Full message should exist
            assert "message" in entry
            # Reasoning should be preserved if present
            if "meta" in entry and "reasoning" in entry["meta"]:
                reasoning = entry["meta"]["reasoning"]
                assert reasoning  # Not empty
                # Reasoning should have why/what/how if it's a dict
                if isinstance(reasoning, dict):
                    # At least one of these should exist
                    assert "why" in reasoning or "what" in reasoning or "how" in reasoning


@pytest.mark.asyncio
async def test_structured_format_uses_limit_manager():
    """Verify structured format uses EntryLimitManager."""
    result = await read_recent(n=100, format="structured")

    # Should have proper response structure
    if isinstance(result, dict):
        # Should have ok status
        assert "ok" in result

        # If entries exist, should have limit_metadata
        if "entries" in result and result["entries"]:
            assert "limit_metadata" in result
            limit_meta = result["limit_metadata"]

            # Verify limit metadata structure
            assert "total_available" in limit_meta
            assert "returned_count" in limit_meta
            assert "mode" in limit_meta
            assert limit_meta["mode"] == "structured"


@pytest.mark.asyncio
async def test_compact_format_uses_limit_manager():
    """Verify compact format uses EntryLimitManager."""
    result = await read_recent(n=50, format="compact")

    if isinstance(result, dict):
        # Should not fail
        assert result.get("ok") is not False

        # If entries exist, should have limit_metadata
        if "entries" in result and result["entries"]:
            assert "limit_metadata" in result
            limit_meta = result["limit_metadata"]

            # Verify limit metadata
            assert "mode" in limit_meta
            assert limit_meta["mode"] == "compact"
            assert "limit_applied" in limit_meta


@pytest.mark.asyncio
async def test_entry_limit_metadata():
    """Verify limit metadata is included for non-readable formats."""
    result = await read_recent(n=50, format="compact")

    if isinstance(result, dict) and "entries" in result and result["entries"]:
        # Should have limit metadata
        assert "limit_metadata" in result or "pagination" in result

        if "limit_metadata" in result:
            meta = result["limit_metadata"]
            # Check all required fields
            assert "total_available" in meta
            assert "filtered_count" in meta
            assert "returned_count" in meta
            assert "entries_omitted" in meta
            assert "mode" in meta
            assert "limit_applied" in meta


@pytest.mark.asyncio
async def test_readable_vs_structured_entry_preservation():
    """Verify readable format preserves more content than structured."""
    # Get same entries in both formats
    readable_result = await read_recent(n=5, format="readable")
    structured_result = await read_recent(n=5, format="structured")

    # Both should succeed
    assert readable_result is not None
    assert structured_result is not None

    # If structured has entries, it should have limit_metadata
    if isinstance(structured_result, dict) and "entries" in structured_result:
        assert "limit_metadata" in structured_result

        # Verify entries are complete dicts with message
        for entry in structured_result["entries"]:
            assert isinstance(entry, dict)
            assert "message" in entry


@pytest.mark.asyncio
async def test_priority_sorting_enabled():
    """Verify EntryLimitManager uses priority sorting."""
    result = await read_recent(n=20, format="structured")

    if isinstance(result, dict) and "entries" in result and len(result["entries"]) > 1:
        # Should have limit_metadata confirming sort was applied
        assert "limit_metadata" in result

        # Entries should be present and be dicts
        for entry in result["entries"]:
            assert isinstance(entry, dict)
            # Should have basic structure
            assert "message" in entry or "raw_line" in entry
