#!/usr/bin/env python3
"""Integration tests for read_file tool with readable format output."""

import pytest
from pathlib import Path

from mcp.types import CallToolResult, TextContent
from scribe_mcp import server as server_module
from scribe_mcp.shared.execution_context import AgentIdentity, ExecutionContext
from scribe_mcp.tools.read_file import read_file


def get_readable_content(result) -> str:
    """Extract text content from CallToolResult (Issue #9962 fix)."""
    if isinstance(result, CallToolResult):
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        return result.content[0].text
    elif isinstance(result, dict):
        # Fallback for dict responses (structured format)
        return result.get("content", str(result))
    else:
        return str(result)


def _install_execution_context(tmp_path) -> object:
    """Install execution context for testing."""
    context = ExecutionContext(
        repo_root=str(tmp_path),
        mode="sentinel",
        session_id="session-1",
        execution_id="exec-1",
        agent_identity=AgentIdentity(
            agent_kind="test",
            model=None,
            instance_id="agent-1",
            sub_id=None,
            display_name=None,
        ),
        intent="read_file_tests",
        timestamp_utc="2026-01-02T00:00:00+00:00",
        affected_dev_projects=[],
        sentinel_day="2026-01-02",
    )
    return server_module.router_context_manager.set_current(context)


# ==================== Test Each Mode with Readable Format ====================


@pytest.mark.asyncio
async def test_scan_only_readable(tmp_path):
    """Test scan_only mode returns readable output."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        result = await read_file(path=str(target), mode="scan_only", format="readable")

        # Should return CallToolResult with TextContent (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should contain box characters
        assert "╔" in content
        assert "║" in content
        assert "╚" in content

        # Should contain file info
        assert "FILE CONTENT" in content
        assert "[scan only - no content requested]" in content

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_chunk_readable(tmp_path):
    """Test chunk mode returns readable output with line numbers."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        result = await read_file(path=str(target), mode="chunk", chunk_index=[0], format="readable")

        # Should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should have line numbers (cat -n style)
        assert "1." in content  # Green line numbers with dot separator

        # Should contain box characters
        assert "╔" in content

        # Should contain actual content
        assert "line 1" in content
        assert "line 2" in content

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_line_range_readable(tmp_path):
    """Test line_range mode returns readable output."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")

        result = await read_file(
            path=str(target),
            mode="line_range",
            start_line=2,
            end_line=4,
            format="readable"
        )

        # Should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should have line numbers starting from 2
        assert "2." in content

        # Should contain requested lines only
        assert "line 2" in content
        assert "line 3" in content
        assert "line 4" in content

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_page_readable(tmp_path):
    """Test page mode returns readable output."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        lines = [f"line {i}" for i in range(1, 101)]
        target.write_text("\n".join(lines), encoding="utf-8")

        result = await read_file(
            path=str(target),
            mode="page",
            page_number=1,
            page_size=10,
            format="readable"
        )

        # Should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should have line numbers
        assert "1." in content

        # Should contain pagination info in footer
        assert "page" in content.lower()

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_full_stream_readable(tmp_path):
    """Test full_stream mode returns readable output."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        result = await read_file(
            path=str(target),
            mode="full_stream",
            start_chunk=0,
            max_chunks=1,
            format="readable"
        )

        # Should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should have line numbers
        assert "1." in content

        # Should contain content
        assert "line 1" in content

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_search_readable(tmp_path):
    """Test search mode returns readable output."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("alpha\nbeta\ngamma\ndelta\nbeta\n", encoding="utf-8")

        result = await read_file(
            path=str(target),
            mode="search",
            search="beta",
            format="readable"
        )

        # Should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should contain search results
        assert "beta" in content

        # Should have match info in footer
        assert "matches_found" in content.lower() or "match" in content.lower()

    finally:
        server_module.router_context_manager.reset(token)


# ==================== Test Structured Format (Backward Compatibility) ====================


@pytest.mark.asyncio
async def test_chunk_structured(tmp_path):
    """Test chunk mode with structured format returns dict."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        result = await read_file(path=str(target), mode="chunk", chunk_index=[0], format="structured")

        # Should return dict (not string)
        assert isinstance(result, dict)

        # Should have expected structure
        assert result["ok"] == True
        assert "chunks" in result
        assert len(result["chunks"]) > 0
        assert "content" in result["chunks"][0]

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_line_range_structured(tmp_path):
    """Test line_range mode with structured format returns dict."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        result = await read_file(
            path=str(target),
            mode="line_range",
            start_line=1,
            end_line=2,
            format="structured"
        )

        # Should return dict
        assert isinstance(result, dict)
        assert result["ok"] == True
        assert "chunk" in result
        assert "content" in result["chunk"]

    finally:
        server_module.router_context_manager.reset(token)


# ==================== Test Default Format ====================


@pytest.mark.asyncio
async def test_default_format_is_readable(tmp_path):
    """Test that default format is 'readable' (not 'structured')."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        # Call without explicit format parameter
        result = await read_file(path=str(target), mode="chunk", chunk_index=[0])

        # Should return CallToolResult (readable format is default, Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should contain readable formatting
        assert "╔" in content

    finally:
        server_module.router_context_manager.reset(token)


# ==================== Test Line Number Visibility ====================


@pytest.mark.asyncio
async def test_line_numbers_visible(tmp_path):
    """Test that line numbers are visible in readable output."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        lines = [f"line {i}" for i in range(1, 11)]
        target.write_text("\n".join(lines), encoding="utf-8")

        result = await read_file(path=str(target), mode="chunk", chunk_index=[0], format="readable")

        # Should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Line numbers should be present with dot separator
        assert "1." in content
        assert "5." in content
        assert "10." in content

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_actual_line_breaks(tmp_path):
    """Test that readable output has actual line breaks (not escaped \\n)."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        result = await read_file(path=str(target), mode="chunk", chunk_index=[0], format="readable")

        # Should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should NOT contain escaped newlines
        assert "\\n" not in content

        # Should contain actual newlines (multiple lines)
        lines_in_output = content.split('\n')
        assert len(lines_in_output) > 5  # Header + content + footer

    finally:
        server_module.router_context_manager.reset(token)


# ==================== Test Metadata Separation ====================


@pytest.mark.asyncio
async def test_metadata_in_boxes(tmp_path):
    """Test that metadata is in header/footer boxes, not mixed with content."""
    token = _install_execution_context(tmp_path)
    try:
        target = tmp_path / "test.py"
        target.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

        result = await read_file(path=str(target), mode="chunk", chunk_index=[0], format="readable")

        # Should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should have header box
        assert "FILE CONTENT" in content

        # Should have footer box with METADATA
        assert "METADATA" in content

        # Path should be in header, not in content area
        lines = content.split('\n')
        content_started = False
        for line in lines:
            if "1." in line:
                content_started = True
            if content_started and "line 1" in line:
                # This is the content area - should NOT contain metadata like "path:"
                assert "path:" not in line.lower()
                assert "mode:" not in line.lower()

    finally:
        server_module.router_context_manager.reset(token)


# ==================== Test Error Handling ====================


@pytest.mark.asyncio
async def test_error_readable(tmp_path):
    """Test that errors are formatted readably too."""
    token = _install_execution_context(tmp_path)
    try:
        # Try to read non-existent file
        result = await read_file(path=str(tmp_path / "nonexistent.txt"), format="readable")

        # Even errors should return CallToolResult (Issue #9962 fix)
        assert isinstance(result, CallToolResult)
        content = get_readable_content(result)

        # Should indicate error
        assert "error" in content.lower() or "not found" in content.lower()

    finally:
        server_module.router_context_manager.reset(token)
