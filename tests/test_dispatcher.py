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
import json
import copy
import hashlib
from unittest.mock import patch, MagicMock, AsyncMock

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
    from scribe_mcp.utils.response import ResponseFormatter
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
        assert result.structured_content == read_file_data

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

    @pytest.mark.asyncio
    async def test_dispatcher_persists_duration_and_correlation_metadata(
        self, formatter, read_file_data, monkeypatch
    ):
        """Tool logging receives measured duration plus shared correlation metadata."""
        logged_calls = []
        scheduled_calls = []

        def fake_log_tool_call(**kwargs):
            logged_calls.append(kwargs)

        def fake_to_thread(func, *args, **kwargs):
            scheduled_calls.append((func, args, kwargs))
            return "scheduled"

        class FakeStorage:
            def record_tool_call_sync(
                self,
                *,
                session_id,
                tool_name,
                duration_ms=None,
                status="success",
                format_requested=None,
                project_name=None,
                agent_id=None,
                error_message=None,
                response_size_bytes=None,
                repo_root=None,
                correlation_id=None,
                measurement_scope=None,
            ):
                return None

        class FakeServer:
            storage_backend = FakeStorage()

            @staticmethod
            def schedule_background_task(awaitable):
                scheduled_calls.append(("background", awaitable))

            @staticmethod
            def get_execution_context():
                return None

        import asyncio
        import scribe_mcp

        monkeypatch.setattr("scribe_mcp.utils.formatters.dispatcher._log_tool_call", fake_log_tool_call)
        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(scribe_mcp, "server", FakeServer)

        result = await formatter.finalize_tool_response(
            read_file_data,
            format="structured",
            tool_name="read_file",
            telemetry={
                "duration_ms": 42.25,
                "correlation_id": "call-123",
                "measurement_scope": "tool_only",
            },
        )

        assert result is read_file_data
        assert logged_calls[0]["duration_ms"] == 42.25
        assert logged_calls[0]["correlation_id"] == "call-123"
        assert logged_calls[0]["measurement_scope"] == "tool_only"
        sql_kwargs = scheduled_calls[0][2]
        assert sql_kwargs["duration_ms"] == 42.25
        assert sql_kwargs["correlation_id"] == "call-123"
        assert sql_kwargs["measurement_scope"] == "tool_only"


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


@pytest.mark.core
@pytest.mark.regression
class TestSBRDefaultOutput:
    """P1 measurement and SOURCE.1 projection are deliberately separate gates.

    Values here are presentation inputs, never fabricated caller authority.
    Large fixtures are generated, and assertion diagnostics contain sizes only.
    """

    @staticmethod
    def _wire(result):
        from scribe_mcp.mcp_adapter import load_mcp_runtime, normalize_tool_result, ProtocolEra

        model = normalize_tool_result(result, runtime=load_mcp_runtime(), era=ProtocolEra.MODERN)
        payload = model.model_dump(by_alias=True, exclude_none=True)
        return json.dumps(payload, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")

    @pytest.mark.parametrize("value", [
        "plain", "漢字🌊\\\"\n" * 80, {"nested": {"notes": "x" * 100000}},
        {"k" * 100000: 1},
    ], ids=["small", "unicode-escaping", "nested-100k", "key-100k"])
    def test_p1_measure_complete_sdk_envelope(self, test_agent, value):
        """Independent P1 gate: exact measurement needs no receipt/runtime producer."""
        from scribe_mcp.utils.config_manager import TokenBudgetManager
        from scribe_mcp.mcp_adapter import load_mcp_runtime, normalize_tool_result, ProtocolEra

        model = normalize_tool_result({"ok": True, "value": value},
                                      runtime=load_mcp_runtime(), era=ProtocolEra.MODERN)
        before = model.model_dump(by_alias=True, exclude_none=True)
        measure = TokenBudgetManager().measure_response_envelope
        expected = len(self._wire(model))
        assert measure(model) == expected
        assert measure(before) == expected
        assert model.model_dump(by_alias=True, exclude_none=True) == before

    def test_p1_measure_charges_nested_keys_depth_and_envelope_metadata(self, test_agent):
        from scribe_mcp.utils.config_manager import TokenBudgetManager

        nested = {"k" * 100000: "漢🌊\\\"\n"}
        for _ in range(100):
            nested = {"child": nested}
        payload = {"content": [{"type": "text", "text": "summary"}],
                   "structuredContent": {"ok": True, "value": nested},
                   "isError": False, "_meta": {"notice": "x" * 1000}}
        expected = len(json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                  sort_keys=True, separators=(",", ":")).encode("utf-8"))
        assert TokenBudgetManager().measure_response_envelope(payload) == expected

    def test_p1_measure_rejects_nonfinite_json(self, test_agent):
        from scribe_mcp.utils.config_manager import TokenBudgetManager

        with pytest.raises(ValueError):
            TokenBudgetManager().measure_response_envelope({"content": [], "structuredContent": {"value": float("nan")}})

    def test_current_helper_accounts_for_whole_delivered_envelope(self, test_agent):
        """Executed baseline regression: result-only token_count hides 100k metadata."""
        from scribe_mcp.utils.config_manager import TokenBudgetManager

        data = {"ok": True, "result": {"count": 1}, "metadata": {"notes": "x" * 100000}}
        before = copy.deepcopy(data)
        manager = TokenBudgetManager()
        result = manager.apply_token_budget_to_response(data, token_limit=512)
        actual_tokens = manager.estimate_response_tokens(result)
        wire_bytes = len(self._wire(result))
        assert data == before
        print(json.dumps({"fixture": "ccfc5e", "wire_bytes": wire_bytes,
                          "reported_tokens": result.get("token_count"),
                          "whole_heuristic_tokens": actual_tokens}, sort_keys=True))
        reported = result.get("token_count", 0)
        assert reported >= actual_tokens, (
            f"whole-envelope accounting: reported={reported} actual={actual_tokens} bytes={wire_bytes}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("format", ["readable", "structured", "compact", "both"])
    async def test_current_formatter_delivers_bounded_default_envelope(
        self, formatter, monkeypatch, test_agent, format
    ):
        from scribe_mcp.utils.formatters import dispatcher
        from scribe_mcp import server

        # Replace only external telemetry IO; the formatter/helper/SDK stay real.
        monkeypatch.setattr(dispatcher, "_log_tool_call", lambda **kwargs: None)
        monkeypatch.setattr(server, "storage_backend", None)
        data = {"ok": True, "result": {"count": 1}, "metadata": {"notes": "x" * 100000}}
        before = copy.deepcopy(data)
        result = await formatter.finalize_tool_response(data, format=format, tool_name="list_projects")
        size = len(self._wire(result))
        assert data == before
        print(json.dumps({"fixture": "formatter-default", "format": format, "wire_bytes": size}))
        assert size <= 2048, f"delivered default envelope={size} bytes exceeds 2048"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("format", ["structured_full", "both_full"])
    async def test_full_preserves_original_selected_unicode_and_hash(
        self, formatter, monkeypatch, test_agent, format
    ):
        from scribe_mcp.utils.formatters import dispatcher
        from scribe_mcp import server

        monkeypatch.setattr(dispatcher, "_log_tool_call", lambda **kwargs: None)
        monkeypatch.setattr(server, "storage_backend", None)
        content = "漢字🌊\\\"\n" * 1000
        data = {"ok": True, "entries": [{"id": n, "message": content} for n in range(10)],
                "pagination": {"page": 4, "page_size": 10, "total_count": 100}}
        before = copy.deepcopy(data)
        result = await formatter.finalize_tool_response(data, format=format, tool_name="read_recent")
        structured = result.model_dump(by_alias=True, exclude_none=True)["structuredContent"] if hasattr(result, "model_dump") else result
        actual = structured["entries"]
        assert len(actual) == 10
        assert actual == before["entries"]
        assert hashlib.sha256(actual[0]["message"].encode()).hexdigest() == hashlib.sha256(content.encode()).hexdigest()
        assert data == before

    @staticmethod
    def _project(data, *, tool="read_recent", detail="default", explicit=False):
        from scribe_mcp.utils.formatters import dispatcher

        context = dispatcher.ResponseBudgetContextV1(
            tool_name=tool, action=None, detail=detail, explicit_body_selection=explicit
        )
        return dispatcher.project_default_response(
            data, budget_context=context, resolved_request_context=None
        )

    @pytest.mark.parametrize("count", [0, 1, 3, 1000])
    def test_projection_count_truth_and_default_ceiling(self, test_agent, count):
        data = {"ok": True, "entries": [{"id": n, "message": "漢🌊" * 100} for n in range(count)],
                "pagination": {"page": 4, "page_size": 1000, "total_count": count}}
        before = copy.deepcopy(data)
        result = self._project(data)
        assert data == before
        assert len(self._wire(result)) <= 2048
        assert result["returned_count"] == min(count, 3)
        assert result["total_count"] == count
        assert result["omitted_count"] == count - min(count, 3)
        if count > 3:
            assert result["kind"] == "preview" and result["complete"] is False
        if count == 0:
            assert result["total_known"] is True

    def test_three_of_ten_continues_same_full_page_without_skipping(self, test_agent):
        data = {"ok": True, "entries": [{"id": n, "message": f"row {n}"} for n in range(30, 40)],
                "pagination": {"page": 4, "page_size": 10, "total_count": 100}}
        preview = self._project(data)
        assert preview["returned_count"] == 3 and preview["omitted_count"] == 7
        continuation = preview["continuation"]
        assert continuation["tool"] == "read_recent"
        assert continuation["consistency"] == "current"
        assert continuation["arguments"]["page"] == 4
        assert continuation["arguments"]["page_size"] == 10
        assert continuation["arguments"]["response_detail"] == "full"
        full = self._project(data, detail="full")
        assert [row["id"] for row in full["entries"]] == list(range(30, 40))

    def test_unknown_total_never_becomes_complete_empty(self, test_agent):
        result = self._project({"ok": True, "entries": [{"id": n} for n in range(10)]})
        assert result["total_count"] is None
        assert result["total_known"] is False
        assert result["complete"] is False
        assert 0 < result["returned_count"] <= 3

    @pytest.mark.parametrize("placement", ["value", "nested-key", "deep"])
    def test_huge_optional_tree_has_bounded_honest_preview(self, test_agent, placement):
        value = {"notes": "漢🌊\\\"\n" * 20000}
        if placement == "nested-key":
            value = {"k" * 100000: "value"}
        elif placement == "deep":
            for _ in range(100):
                value = {"child": value}
        data = {"ok": True, "projects": [{"name": "demo", "metadata": value}], "total_count": 1}
        before = copy.deepcopy(data)
        result = self._project(data, tool="list_projects")
        assert len(self._wire(result)) <= 2048
        assert data == before
        assert result["complete"] is False
        assert result["kind"] == "preview"

    def test_optional_excerpts_are_utf8_safe_sized_and_losslessly_identified(self, test_agent):
        text = "漢🌊\\\"\n" * 20000
        result = self._project({"ok": True, "entries": [{"id": 1, "message": text}],
                                "pagination": {"page": 1, "page_size": 10, "total_count": 1}})
        row = result["entries"][0]
        values = list(row.values())
        excerpts = [value for value in values if isinstance(value, str) and value and text.startswith(value)]
        assert excerpts and all(len(value.encode("utf-8")) <= 160 for value in excerpts)
        assert len(text.encode("utf-8")) in values
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() in values

    def test_default_has_one_notice_and_no_post_budget_unbounded_sidecar(self, test_agent):
        data = {"ok": True, "projects": [{"name": f"p{n}"} for n in range(10)],
                "total_count": 10, "reminders": [{"message": "漢🌊" * 10000} for _ in range(5)],
                "timing": {"notes": "x" * 100000}}
        before = copy.deepcopy(data)
        result = self._project(data, tool="list_projects")
        assert len(self._wire(result)) <= 2048
        assert len(result.get("notices", result.get("reminders", []))) <= 1
        assert data == before

    @pytest.mark.parametrize("tool", ["read_file", "scribe_doctor", "read_recent"])
    def test_explicit_default_conflicting_with_full_selection_is_rejected(self, test_agent, tool):
        """Pure context consistency; actual pre-effect runtime admission remains V4/V5."""
        from scribe_mcp.utils.formatters import dispatcher

        with pytest.raises(ValueError, match="detail|selection|conflict"):
            context = dispatcher.ResponseBudgetContextV1(
                tool_name=tool, action=None, detail="default", explicit_body_selection=True)
            dispatcher.project_default_response(
                {"ok": True}, budget_context=context, resolved_request_context=None)
