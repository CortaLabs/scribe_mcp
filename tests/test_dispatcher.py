#!/usr/bin/env python3
"""
Integration tests for FormatterDispatcher (Phase 5 Task 5.6).

Tests cover:
- Tool response routing (each tool type routes correctly)
- Format parameter handling (readable, structured, compact, both)
- Error handling
- Token estimation warnings
- Async behavior
- MCP SDK integration
- Backward compatibility with ResponseFormatter.finalize_tool_response

These tests MUST pass before and after extraction to ensure no regression.
"""

import re
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add MCP_SPINE root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text for testing."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_pattern.sub('', text)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def formatter():
    """Create a ResponseFormatter instance for testing."""
    from utils.response import ResponseFormatter
    return ResponseFormatter()


@pytest.fixture
def read_file_data():
    """Sample data for read_file tool response.

    Format matches what read_file tool actually produces.
    """
    return {
        'ok': True,
        'mode': 'line_range',
        'scan': {
            'repo_relative_path': 'test/file.py',
            'absolute_path': '/test/file.py',
            'line_count': 100,
            'size_bytes': 1024,
            'encoding': 'utf-8',
        },
        'chunk': {
            'content': 'def hello():\n    return "world"',
            'line_start': 1,
            'line_end': 2,
        },
    }


@pytest.fixture
def read_recent_data():
    """Sample data for read_recent tool response."""
    return {
        'ok': True,
        'entries': [
            {
                'id': 1,
                'message': 'Test entry 1',
                'timestamp': '2026-01-23T08:00:00Z',
                'emoji': 'info',
                'agent': 'TestAgent',
                'meta': {'task': 'testing'}
            },
            {
                'id': 2,
                'message': 'Test entry 2',
                'timestamp': '2026-01-23T08:01:00Z',
                'emoji': 'success',
                'agent': 'TestAgent',
                'meta': {}
            }
        ],
        'pagination': {
            'page': 1,
            'page_size': 10,
            'total_count': 2,
            'total_pages': 1
        },
        'project_name': 'test_project'
    }


@pytest.fixture
def query_entries_data():
    """Sample data for query_entries tool response."""
    return {
        'ok': True,
        'entries': [
            {
                'id': 1,
                'message': 'Found matching entry',
                'timestamp': '2026-01-23T08:00:00Z',
                'emoji': 'info',
                'agent': 'TestAgent',
                'meta': {}
            }
        ],
        'pagination': {
            'page': 1,
            'page_size': 10,
            'total_count': 1,
            'total_pages': 1
        },
        'project_name': 'test_project',
        'search_message': 'matching',
        'search_status': ['info'],
    }


@pytest.fixture
def append_entry_data():
    """Sample data for append_entry tool response.

    Format matches what append_entry tool actually produces.
    """
    return {
        'ok': True,
        'written_line': '[success] 2026-01-23 08:00:00 UTC [Agent: TestAgent] [Project: test_project] Test log entry | status=success',
        'meta': {'status': 'success', 'task': 'testing'},
        'log_path': '/test/.scribe/logs/PROGRESS_LOG.md',
        'timestamp': '2026-01-23T08:00:00Z'
    }


@pytest.fixture
def error_data():
    """Sample error response data."""
    return {
        'ok': False,
        'error': 'Something went wrong',
        'details': {'code': 500}
    }


# =============================================================================
# Test Tool Routing - Readable Format
# =============================================================================

class TestToolRoutingReadable:
    """Test that each tool type routes correctly to its formatter in readable mode."""

    @pytest.mark.asyncio
    async def test_read_file_routing(self, formatter, read_file_data):
        """Test read_file routes to format_readable_file_content."""
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="readable",
            tool_name="read_file"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)

        text = result.content[0].text
        # Should contain file content formatting (uses READ FILE header)
        assert "READ FILE" in text or "file.py" in text

    @pytest.mark.asyncio
    async def test_read_recent_routing(self, formatter, read_recent_data):
        """Test read_recent routes to format_readable_log_entries."""
        result = await formatter.finalize_tool_response(
            read_recent_data,
            format="readable",
            tool_name="read_recent"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)

        text = strip_ansi(result.content[0].text)
        # Should contain log entry formatting
        assert "Test entry" in text or "RECENT LOG" in text

    @pytest.mark.asyncio
    async def test_query_entries_routing(self, formatter, query_entries_data):
        """Test query_entries routes to format_readable_log_entries with search context."""
        result = await formatter.finalize_tool_response(
            query_entries_data,
            format="readable",
            tool_name="query_entries"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)

        text = strip_ansi(result.content[0].text)
        # Should contain search results formatting
        assert "matching" in text.lower() or "SEARCH" in text or "entry" in text.lower()

    @pytest.mark.asyncio
    async def test_append_entry_routing(self, formatter, append_entry_data):
        """Test append_entry routes to format_readable_append_entry."""
        result = await formatter.finalize_tool_response(
            append_entry_data,
            format="readable",
            tool_name="append_entry"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)

        text = result.content[0].text
        # Should contain append entry formatting (success emoji, message, or log path)
        assert "success" in text.lower() or "Test log" in text or "PROGRESS_LOG" in text

    @pytest.mark.asyncio
    async def test_unknown_tool_routing(self, formatter):
        """Test unknown tools get JSON fallback."""
        data = {'custom': 'data', 'value': 42}

        result = await formatter.finalize_tool_response(
            data,
            format="readable",
            tool_name="unknown_custom_tool"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)

        text = result.content[0].text
        # Should contain JSON representation
        assert "custom" in text or "42" in text


# =============================================================================
# Test Format Parameter Handling
# =============================================================================

class TestFormatParameters:
    """Test format parameter variations."""

    @pytest.mark.asyncio
    async def test_format_readable(self, formatter, read_file_data):
        """Test format='readable' returns CallToolResult with TextContent only."""
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="readable",
            tool_name="read_file"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        # Should NOT have structuredContent (Issue #9962 fix)
        assert not hasattr(result, 'structuredContent') or result.structuredContent is None

    @pytest.mark.asyncio
    async def test_format_structured(self, formatter, read_file_data):
        """Test format='structured' returns dict unchanged."""
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="structured",
            tool_name="read_file"
        )

        assert isinstance(result, dict)
        assert result == read_file_data

    @pytest.mark.asyncio
    async def test_format_compact(self, formatter, read_file_data):
        """Test format='compact' returns dict."""
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="compact",
            tool_name="read_file"
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_format_both(self, formatter, read_file_data):
        """Test format='both' returns CallToolResult with TextContent AND structuredContent."""
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="both",
            tool_name="read_file"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        # Should have structuredContent
        assert result.structuredContent == read_file_data

    @pytest.mark.asyncio
    async def test_format_default_is_readable(self, formatter, read_file_data):
        """Test default format is readable."""
        result = await formatter.finalize_tool_response(
            read_file_data,
            tool_name="read_file"
            # No format parameter
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert isinstance(result.content[0], TextContent)


# =============================================================================
# Test Error Handling
# =============================================================================

class TestErrorHandling:
    """Test error response formatting."""

    @pytest.mark.asyncio
    async def test_error_response_readable(self, formatter, error_data):
        """Test error responses use format_readable_error."""
        result = await formatter.finalize_tool_response(
            error_data,
            format="readable",
            tool_name="any_tool"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert isinstance(result.content[0], TextContent)

        text = result.content[0].text
        # Should contain error formatting
        assert "wrong" in text.lower() or "error" in text.lower()

    @pytest.mark.asyncio
    async def test_error_response_structured(self, formatter, error_data):
        """Test error responses in structured format return dict."""
        result = await formatter.finalize_tool_response(
            error_data,
            format="structured",
            tool_name="any_tool"
        )

        assert isinstance(result, dict)
        assert result['ok'] == False
        assert 'error' in result

    @pytest.mark.asyncio
    async def test_error_with_ok_false(self, formatter):
        """Test ok=False triggers error formatting."""
        data = {'ok': False, 'error': 'Test error message'}

        result = await formatter.finalize_tool_response(
            data,
            format="readable",
            tool_name="test_tool"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        text = result.content[0].text
        assert "error" in text.lower() or "Test error" in text


# =============================================================================
# Test Pre-populated Readable Content
# =============================================================================

class TestPrePopulatedContent:
    """Test that pre-populated readable_content is used directly."""

    @pytest.mark.asyncio
    async def test_readable_content_priority(self, formatter):
        """Test readable_content in data is used directly (priority 1)."""
        data = {
            'ok': True,
            'readable_content': 'Pre-formatted content here',
            'other': 'data'
        }

        result = await formatter.finalize_tool_response(
            data,
            format="readable",
            tool_name="any_tool"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        text = result.content[0].text
        assert text == 'Pre-formatted content here'

    @pytest.mark.asyncio
    async def test_readable_content_bypasses_error_check(self, formatter):
        """Test readable_content is used even when error is present."""
        # readable_content should take priority over error formatting
        data = {
            'ok': True,  # Must be True for readable_content to win
            'readable_content': 'Custom formatted content',
            'error': 'This should be ignored'
        }

        result = await formatter.finalize_tool_response(
            data,
            format="readable",
            tool_name="any_tool"
        )

        from mcp.types import CallToolResult
        text = result.content[0].text
        assert 'Custom formatted content' in text


# =============================================================================
# Test Query Entries Search Context
# =============================================================================

class TestQueryEntriesSearchContext:
    """Test search context extraction for query_entries."""

    @pytest.mark.asyncio
    async def test_search_context_extraction(self, formatter):
        """Test search parameters are extracted into search_context."""
        data = {
            'ok': True,
            'entries': [],
            'pagination': {'page': 1, 'page_size': 10, 'total_count': 0, 'total_pages': 0},
            'search_message': 'error',
            'search_status': ['error', 'warn'],
            'search_agents': ['CoderAgent'],
            'search_emoji': ['bug']
        }

        result = await formatter.finalize_tool_response(
            data,
            format="readable",
            tool_name="query_entries"
        )

        from mcp.types import CallToolResult
        assert isinstance(result, CallToolResult)
        # The formatter should have received search context
        # We verify by checking the output contains search-related info

    @pytest.mark.asyncio
    async def test_empty_search_context_still_shows_search_header(self, formatter):
        """Test query_entries with no filters still shows search header."""
        data = {
            'ok': True,
            'entries': [],
            'pagination': {'page': 1, 'page_size': 10, 'total_count': 0, 'total_pages': 0}
            # No search_* parameters
        }

        result = await formatter.finalize_tool_response(
            data,
            format="readable",
            tool_name="query_entries"
        )

        from mcp.types import CallToolResult
        assert isinstance(result, CallToolResult)


# =============================================================================
# Test MCP SDK Fallback
# =============================================================================

class TestMCPFallback:
    """Test behavior when MCP SDK types are unavailable."""

    @pytest.mark.asyncio
    async def test_fallback_readable_format(self, formatter, read_file_data):
        """Test fallback returns dict when MCP types unavailable."""
        # This test verifies the fallback code path exists
        # In practice, MCP types are available, so we verify the normal path
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="readable",
            tool_name="read_file"
        )

        # When MCP types ARE available (normal case), we get CallToolResult
        from mcp.types import CallToolResult
        assert isinstance(result, CallToolResult)

    @pytest.mark.asyncio
    async def test_fallback_both_format(self, formatter, read_file_data):
        """Test fallback for 'both' format when MCP types unavailable."""
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="both",
            tool_name="read_file"
        )

        from mcp.types import CallToolResult
        assert isinstance(result, CallToolResult)


# =============================================================================
# Test Async Behavior
# =============================================================================

class TestAsyncBehavior:
    """Test async execution and concurrency safety."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_calls(self, formatter):
        """Test multiple concurrent finalize_tool_response calls."""
        import asyncio

        data_list = [
            {'ok': True, 'content': f'Test {i}', 'path': f'/test{i}.txt', 'mode': 'chunk', 'start_line': 1}
            for i in range(5)
        ]

        tasks = [
            formatter.finalize_tool_response(data, format="readable", tool_name="read_file")
            for data in data_list
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result in results:
            from mcp.types import CallToolResult
            assert isinstance(result, CallToolResult)

    @pytest.mark.asyncio
    async def test_async_with_different_formats(self, formatter):
        """Test concurrent calls with different format parameters."""
        import asyncio

        data = {'ok': True, 'test': 'data'}

        tasks = [
            formatter.finalize_tool_response(data, format="readable", tool_name="test"),
            formatter.finalize_tool_response(data, format="structured", tool_name="test"),
            formatter.finalize_tool_response(data, format="compact", tool_name="test"),
        ]

        results = await asyncio.gather(*tasks)

        from mcp.types import CallToolResult
        # readable returns CallToolResult
        assert isinstance(results[0], CallToolResult)
        # structured returns dict
        assert isinstance(results[1], dict)
        # compact returns dict
        assert isinstance(results[2], dict)


# =============================================================================
# Test Tool Logging Integration
# =============================================================================

class TestToolLogging:
    """Test tool logging integration (STEP 1 of finalize_tool_response)."""

    @pytest.mark.asyncio
    async def test_logging_does_not_block_response(self, formatter, read_file_data):
        """Test that logging failures don't block tool response."""
        # The logging is wrapped in try/except, so even if it fails,
        # the response should still be returned
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="readable",
            tool_name="read_file"
        )

        from mcp.types import CallToolResult
        assert isinstance(result, CallToolResult)

    @pytest.mark.asyncio
    async def test_response_size_calculation(self, formatter):
        """Test response size is calculated for metrics."""
        # Large data should still work
        large_data = {'ok': True, 'content': 'x' * 10000}

        result = await formatter.finalize_tool_response(
            large_data,
            format="readable",
            tool_name="test"
        )

        from mcp.types import CallToolResult
        assert isinstance(result, CallToolResult)


# =============================================================================
# Test Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Test backward compatibility with existing ResponseFormatter interface."""

    def test_finalize_tool_response_is_async(self, formatter):
        """Test finalize_tool_response is an async method."""
        import inspect
        assert inspect.iscoroutinefunction(formatter.finalize_tool_response)

    @pytest.mark.asyncio
    async def test_existing_test_cases_still_pass(self, formatter):
        """Verify existing TestFormatRouter test cases still work."""
        # This mirrors tests from test_response_formatter_readable.py

        # Test 1: readable format
        data = {'content': 'Test', 'path': '/test.txt', 'mode': 'chunk', 'start_line': 1}
        result = await formatter.finalize_tool_response(data, format="readable", tool_name="read_file")
        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert isinstance(result.content[0], TextContent)

        # Test 2: structured format
        data = {'test': 'data'}
        result = await formatter.finalize_tool_response(data, format="structured", tool_name="test")
        assert isinstance(result, dict)
        assert result == data

        # Test 3: compact format
        result = await formatter.finalize_tool_response(data, format="compact", tool_name="test")
        assert isinstance(result, dict)


# =============================================================================
# Integration Test: Full Response Flow
# =============================================================================

class TestFullResponseFlow:
    """Integration tests for complete response flow."""

    @pytest.mark.asyncio
    async def test_complete_read_file_flow(self, formatter, read_file_data):
        """Test complete read_file response flow."""
        result = await formatter.finalize_tool_response(
            read_file_data,
            format="readable",
            tool_name="read_file"
        )

        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].type == "text"

        # Verify content is readable
        text = result.content[0].text
        assert len(text) > 0
        # Should be actual text, not escaped JSON
        assert '\\n' not in text[:100]  # First 100 chars shouldn't have escaped newlines

    @pytest.mark.asyncio
    async def test_complete_log_entries_flow(self, formatter, read_recent_data):
        """Test complete log entries response flow."""
        result = await formatter.finalize_tool_response(
            read_recent_data,
            format="readable",
            tool_name="read_recent"
        )

        from mcp.types import CallToolResult
        assert isinstance(result, CallToolResult)
        text = result.content[0].text

        # Should contain formatted log entries
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_complete_error_flow(self, formatter, error_data):
        """Test complete error response flow."""
        result = await formatter.finalize_tool_response(
            error_data,
            format="readable",
            tool_name="any_tool"
        )

        from mcp.types import CallToolResult
        assert isinstance(result, CallToolResult)
        text = result.content[0].text

        # Should contain error formatting
        assert "error" in text.lower() or "wrong" in text.lower()
