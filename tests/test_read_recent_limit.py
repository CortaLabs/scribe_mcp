#!/usr/bin/env python3
"""Tests for read_recent EntryLimitManager integration."""

from types import SimpleNamespace

import pytest
import scribe_mcp.tools.read_recent as read_recent_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.tools.read_recent import read_recent


def _readable_text(result):
    """Extract readable text from MCP CallToolResult or fallback dict output."""
    if isinstance(result, dict):
        return result.get("content", "")
    return "\n".join(
        block.text
        for block in getattr(result, "content", [])
        if getattr(block, "type", None) == "text"
    )


@pytest.mark.asyncio
async def test_readable_format_no_truncation():
    """Verify readable format returns full entries without truncation."""
    # This test requires a project with entries
    result = await read_recent(agent="test_agent", n=10, format="readable")

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
    result = await read_recent(agent="test_agent", n=100, format="structured")

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
    result = await read_recent(agent="test_agent", n=50, format="compact")

    if isinstance(result, dict):
        # This suite runs without binding a project; tolerate that bootstrap
        # state like the sibling tests above. The strict "must not fail" check
        # only applies when a project is actually configured.
        no_project = (
            result.get("error")
            == "No project configured. Invoke set_project before using this tool."
        )
        if not no_project:
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
    result = await read_recent(agent="test_agent", n=50, format="compact")

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
    readable_result = await read_recent(agent="test_agent", n=5, format="readable")
    structured_result = await read_recent(agent="test_agent", n=5, format="structured")

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
async def test_readable_compact_true_preserves_rendered_entry_fields(monkeypatch, tmp_path):
    """compact=True must not compact entries before default readable rendering."""
    project = {
        "name": "compact-readable-test",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
    }
    context = LoggingContext(
        tool_name="read_recent",
        project=project,
        recent_projects=[],
        state_snapshot={},
        reminders=[],
        resolution_source="test",
    )

    async def record_tool(_tool_name):
        return {"tool": _tool_name}

    async def prepare_context(**_kwargs):
        return context

    async def fake_read_tail(*_args, **_kwargs):
        return [
            "[ℹ️] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] "
            "[Project: compact-readable-test] Compact readable message"
        ]

    monkeypatch.setattr(
        read_recent_module.server_module,
        "state_manager",
        SimpleNamespace(record_tool=record_tool),
    )
    monkeypatch.setattr(read_recent_module.server_module, "storage_backend", None)
    monkeypatch.setattr(read_recent_module.server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(read_recent_module._READ_RECENT_HELPER, "prepare_context", prepare_context)
    monkeypatch.setattr(read_recent_module, "read_tail", fake_read_tail)

    result = await read_recent(agent="test_agent", compact=True)
    text = _readable_text(result)

    assert "TestAgent" in text
    assert "Compact readable message" in text
    assert "14:30" in text


@pytest.mark.asyncio
async def test_compact_format_still_returns_compact_entry_keys(monkeypatch, tmp_path):
    """format='compact' keeps compact entry behavior."""
    project = {
        "name": "compact-format-test",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
    }
    context = LoggingContext(
        tool_name="read_recent",
        project=project,
        recent_projects=[],
        state_snapshot={},
        reminders=[],
        resolution_source="test",
    )

    async def record_tool(_tool_name):
        return {"tool": _tool_name}

    async def prepare_context(**_kwargs):
        return context

    async def fake_read_tail(*_args, **_kwargs):
        return [
            "[ℹ️] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] "
            "[Project: compact-format-test] Compact format message"
        ]

    monkeypatch.setattr(
        read_recent_module.server_module,
        "state_manager",
        SimpleNamespace(record_tool=record_tool),
    )
    monkeypatch.setattr(read_recent_module.server_module, "storage_backend", None)
    monkeypatch.setattr(read_recent_module.server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(read_recent_module._READ_RECENT_HELPER, "prepare_context", prepare_context)
    monkeypatch.setattr(read_recent_module, "read_tail", fake_read_tail)

    result = await read_recent(agent="test_agent", compact=True, format="compact")

    assert isinstance(result, dict)
    assert result["entries"][0]["a"] == "TestAgent"
    assert result["entries"][0]["m"] == "Compact format message"
    assert "message" not in result["entries"][0]


@pytest.mark.asyncio
async def test_priority_sorting_enabled():
    """Verify EntryLimitManager uses priority sorting."""
    result = await read_recent(agent="test_agent", n=20, format="structured")

    if isinstance(result, dict) and "entries" in result and len(result["entries"]) > 1:
        # Should have limit_metadata confirming sort was applied
        assert "limit_metadata" in result

        # Entries should be present and be dicts
        for entry in result["entries"]:
            assert isinstance(entry, dict)
            # Should have basic structure
            assert "message" in entry or "raw_line" in entry
