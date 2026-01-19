#!/usr/bin/env python3
"""
Unit tests for ResponseFormatter readable format functionality (Phase 0).

Tests cover:
- Line numbering with various line counts
- ASCII box generation and width calculations
- Format routing logic
- Tool-specific formatters
- Integration with existing ResponseFormatter functionality
"""

import re
import sys
from pathlib import Path

# Add MCP_SPINE root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from utils.response import ResponseFormatter


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text for testing.

    Phase 1.6: Colors are now enabled by default. Tests need to strip
    ANSI codes when checking structural assertions.
    """
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_pattern.sub('', text)


class TestLineNumbering:
    """Test _add_line_numbers helper method."""

    def test_single_line(self):
        """Test line numbering with single line (5-char min padding like Claude)."""
        formatter = ResponseFormatter()
        content = "Hello, World!"
        result = formatter._add_line_numbers(content)
        # Minimum 5-char padding, green line numbers with dot separator
        # Strip ANSI for comparison (Phase 1.6: colors enabled by default)
        clean_result = strip_ansi(result)
        assert clean_result == "    1. Hello, World!"

    def test_ten_lines(self):
        """Test line numbering with 10 lines (5-char min padding)."""
        formatter = ResponseFormatter()
        lines = [f"Line {i}" for i in range(1, 11)]
        content = '\n'.join(lines)
        result = formatter._add_line_numbers(content)
        clean_result = strip_ansi(result)

        # Check first line (5-char width minimum)
        assert clean_result.startswith("    1. Line 1")
        # Check last line
        assert "   10. Line 10" in clean_result
        # Verify all lines present
        assert clean_result.count('. ') == 10

    def test_hundred_lines(self):
        """Test line numbering with 100 lines (5-char min padding)."""
        formatter = ResponseFormatter()
        lines = [f"Line {i}" for i in range(1, 101)]
        content = '\n'.join(lines)
        result = formatter._add_line_numbers(content)
        clean_result = strip_ansi(result)

        # Check first line (5-char width minimum)
        assert clean_result.startswith("    1. Line 1")
        # Check last line
        assert "  100. Line 100" in clean_result
        # Verify all lines present
        assert clean_result.count('. ') == 100

    def test_thousand_lines(self):
        """Test line numbering with 1000 lines (5-char min padding)."""
        formatter = ResponseFormatter()
        lines = [f"Line {i}" for i in range(1, 1001)]
        content = '\n'.join(lines)
        result = formatter._add_line_numbers(content)
        clean_result = strip_ansi(result)

        # Check first line (5-char width minimum)
        assert clean_result.startswith("    1. Line 1")
        # Check last line
        assert " 1000. Line 1000" in clean_result
        # Verify all lines present
        assert clean_result.count('. ') == 1000

    def test_ten_thousand_lines(self):
        """Test line numbering with 10000 lines (5-digit padding)."""
        formatter = ResponseFormatter()
        lines = [f"Line {i}" for i in range(1, 10001)]
        content = '\n'.join(lines)
        result = formatter._add_line_numbers(content)
        clean_result = strip_ansi(result)

        # Check first line (should have 5-char width)
        assert clean_result.startswith("    1. Line 1")
        # Check last line
        assert "10000. Line 10000" in clean_result
        # Verify all lines present
        assert clean_result.count('. ') == 10000

    def test_custom_start_line(self):
        """Test line numbering with custom start line number."""
        formatter = ResponseFormatter()
        content = "Line A\nLine B\nLine C"
        result = formatter._add_line_numbers(content, start=100)
        clean_result = strip_ansi(result)

        assert "100. Line A" in clean_result
        assert "101. Line B" in clean_result
        assert "102. Line C" in clean_result

    def test_empty_content(self):
        """Test line numbering with empty content."""
        formatter = ResponseFormatter()
        result = formatter._add_line_numbers("")
        assert result == ""

    def test_single_newline(self):
        """Test line numbering with just a newline."""
        formatter = ResponseFormatter()
        content = "\n"
        result = formatter._add_line_numbers(content)
        clean_result = strip_ansi(result)
        # Should have two lines: one empty, one empty
        assert clean_result.count('. ') == 2


class TestASCIIBoxes:
    """Test ASCII box generation methods."""

    def test_header_box_basic(self):
        """Test basic header box generation."""
        formatter = ResponseFormatter()
        result = formatter._create_header_box("TEST TITLE", {"key1": "value1"})

        # Strip ANSI codes for structure checks (Phase 1.6: colors enabled by default)
        clean_result = strip_ansi(result)

        # Check structure
        assert clean_result.startswith("╔")
        assert "═" in clean_result
        assert "TEST TITLE" in clean_result
        assert "key1: value1" in clean_result
        assert clean_result.endswith("╝")

        # Check all lines are same width (strip ANSI first)
        lines = clean_result.split('\n')
        widths = [len(line) for line in lines]
        assert len(set(widths)) == 1  # All lines same width

    def test_header_box_width(self):
        """Test header box is 80 characters wide."""
        formatter = ResponseFormatter()
        result = formatter._create_header_box("TITLE", {})

        # Strip ANSI codes for width check (Phase 1.6: colors enabled by default)
        clean_result = strip_ansi(result)
        lines = clean_result.split('\n')
        for line in lines:
            assert len(line) == 80

    def test_footer_box_basic(self):
        """Test basic footer box generation."""
        formatter = ResponseFormatter()
        result = formatter._create_footer_box({"audit_key": "audit_value"})

        # Strip ANSI codes for content check (Phase 1.6: colors enabled by default)
        clean_result = strip_ansi(result)
        assert "METADATA" in clean_result
        assert "audit_key: audit_value" in clean_result

        # Check structure (strip ANSI for width check)
        lines = clean_result.split('\n')
        widths = [len(line) for line in lines]
        assert len(set(widths)) == 1  # All lines same width

    def test_footer_box_with_reminders(self):
        """Test footer box with reminders section."""
        formatter = ResponseFormatter()
        reminders = [
            {"emoji": "🔔", "message": "Reminder 1"},
            {"emoji": "⚠️", "message": "Reminder 2"}
        ]
        result = formatter._create_footer_box({"key": "value"}, reminders)

        assert "METADATA" in result
        assert "REMINDERS" in result
        assert "🔔 Reminder 1" in result
        assert "⚠️ Reminder 2" in result

    def test_box_long_values(self):
        """Test box handles long values with truncation."""
        formatter = ResponseFormatter()
        long_value = "x" * 200  # Very long value
        result = formatter._create_header_box("TITLE", {"key": long_value})

        # Strip ANSI codes for structure check (Phase 1.6: colors enabled by default)
        clean_result = strip_ansi(result)

        # Should truncate with "..."
        assert "..." in clean_result

        # All lines still 80 chars
        lines = clean_result.split('\n')
        for line in lines:
            assert len(line) == 80

    def test_box_dict_values(self):
        """Test box handles dict/list values."""
        formatter = ResponseFormatter()
        result = formatter._create_header_box("TITLE", {
            "dict_key": {"nested": "value"},
            "list_key": [1, 2, 3]
        })

        # Should JSON-serialize complex values
        assert '"nested"' in result or "'nested'" in result
        assert "[1, 2, 3]" in result or "[1,2,3]" in result


class TestTableFormatting:
    """Test _format_table helper method."""

    def test_basic_table(self):
        """Test basic table generation."""
        formatter = ResponseFormatter()
        headers = ["Col1", "Col2", "Col3"]
        rows = [
            ["A", "B", "C"],
            ["D", "E", "F"]
        ]
        result = formatter._format_table(headers, rows)

        # Check structure
        assert "┌" in result  # Top left
        assert "┐" in result  # Top right
        assert "└" in result  # Bottom left
        assert "┘" in result  # Bottom right
        assert "│" in result  # Vertical
        assert "─" in result  # Horizontal

        # Check content
        assert "Col1" in result
        assert "A" in result
        assert "F" in result

    def test_table_alignment(self):
        """Test table column alignment."""
        formatter = ResponseFormatter()
        headers = ["Short", "VeryLongHeader"]
        rows = [
            ["A", "B"],
            ["C", "D"]
        ]
        result = formatter._format_table(headers, rows)

        # Column widths should be based on longest content
        lines = result.split('\n')
        # All separators should align
        for line in lines:
            if '┬' in line or '┼' in line or '┴' in line:
                # Check consistent structure
                assert line.count('─') > 0

    def test_empty_table(self):
        """Test empty table returns empty string."""
        formatter = ResponseFormatter()
        assert formatter._format_table([], []) == ""
        assert formatter._format_table(["H1"], []) == ""

    def test_table_with_varying_lengths(self):
        """Test table handles rows with varying cell counts."""
        formatter = ResponseFormatter()
        headers = ["A", "B", "C"]
        rows = [
            ["1", "2"],  # Missing third column
            ["3", "4", "5"]
        ]
        result = formatter._format_table(headers, rows)

        # Should handle gracefully
        assert "1" in result
        assert "5" in result


class TestCoreFormatters:
    """Test tool-specific formatting methods."""

    def test_format_readable_file_content(self):
        """Test read_file content formatting with actual response structure."""
        formatter = ResponseFormatter()
        # Use actual read_file response structure
        data = {
            'ok': True,
            'mode': 'chunk',
            'scan': {
                'absolute_path': '/test/file.txt',
                'repo_relative_path': 'file.txt',
                'byte_size': 100,
                'line_count': 3,
                'sha256': 'abc123def456',
                'encoding': 'utf-8',
                'estimated_chunk_count': 1
            },
            'chunks': [
                {
                    'chunk_index': 0,
                    'line_start': 1,
                    'line_end': 3,
                    'content': 'Line 1\nLine 2\nLine 3'
                }
            ]
        }
        result = formatter.format_readable_file_content(data)

        # Should have header box
        assert "FILE CONTENT" in result
        assert "file.txt" in result

        # Should have line-numbered content (strip ANSI for check)
        clean_result = strip_ansi(result)
        assert "1. Line 1" in clean_result
        assert "2. Line 2" in clean_result
        assert "3. Line 3" in clean_result

        # Should have footer
        assert "METADATA" in result

    def test_format_readable_log_entries(self):
        """Test log entries formatting with Phase 3a enhancements."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2025-01-02T14:30:00.000Z',
                'agent': 'TestAgent',
                'emoji': '✅',
                'status': 'success',
                'message': 'Test message 1',
                'meta': {}
            },
            {
                'timestamp': '2025-01-02T14:31:00.000Z',
                'agent': 'OtherAgent',
                'emoji': 'ℹ️',
                'status': 'info',
                'message': 'Test message 2',
                'meta': {}
            }
        ]
        pagination = {
            'total_count': 25,
            'page': 1,
            'page_size': 10
        }
        result = formatter.format_readable_log_entries(entries, pagination)

        # Should have header with pagination (Phase 3a)
        assert "RECENT LOG ENTRIES" in result
        assert "Page 1 of 3" in result  # 25 total / 10 per page = 3 pages
        assert "(2/25)" in result  # showing 2 of 25

        # Should have compact timestamps (HH:MM format, Phase 3a)
        clean_result = strip_ansi(result)
        assert "14:30" in clean_result
        assert "14:31" in clean_result

        # Should have data
        assert "TestAgent" in result
        assert "Test message 1" in result

    def test_format_readable_log_entries_empty(self):
        """Test log entries formatting with no entries."""
        formatter = ResponseFormatter()
        result = formatter.format_readable_log_entries([], {})
        assert result == "No log entries found."

    def test_format_readable_projects(self):
        """Test projects formatting."""
        formatter = ResponseFormatter()
        projects = [
            {
                'name': 'project1',
                'lifecycle_status': 'in_progress',
                'root': '/path/to/project1',
                'last_entry_at': '2025-01-02T14:30:00.000Z'
            },
            {
                'name': 'project2',
                'lifecycle_status': 'complete',
                'root': '/path/to/project2',
                'last_entry_at': 'never'
            }
        ]
        result = formatter.format_readable_projects(projects, active='project1')

        # Should have header
        assert "PROJECTS" in result

        # Should have table
        assert "│" in result
        assert "Name" in result
        assert "Status" in result

        # Should mark active project
        assert "* project1" in result
        assert "project2" in result  # No asterisk

    def test_format_readable_projects_empty(self):
        """Test projects formatting with no projects."""
        formatter = ResponseFormatter()
        result = formatter.format_readable_projects([])
        assert result == "No projects found."

    def test_format_readable_confirmation(self):
        """Test operation confirmation formatting."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'written_line': '[✅] Test entry written',
            'path': '/test/PROGRESS_LOG.md',
            'id': 'abc123',
            'meta': {'phase': 'test'}
        }
        result = formatter.format_readable_confirmation('append_entry', data)

        # Should have header
        assert "OPERATION RESULT" in result
        assert "success" in result

        # Should have content
        assert "Entry written" in result
        assert "Test entry written" in result
        assert "/test/PROGRESS_LOG.md" in result

        # Should have footer with audit data
        assert "METADATA" in result
        assert "abc123" in result

    def test_format_readable_error(self):
        """Test error formatting."""
        formatter = ResponseFormatter()
        result = formatter.format_readable_error(
            "Something went wrong",
            {'error_type': 'ValidationError', 'field': 'name'}
        )

        # Should have header
        assert "ERROR" in result
        assert "ValidationError" in result

        # Should have error message
        assert "❌ Something went wrong" in result

        # Should have footer
        assert "METADATA" in result
        assert "field" in result


class TestFormatRouter:
    """Test finalize_tool_response format routing."""

    @pytest.mark.asyncio
    async def test_router_readable_format(self):
        """Test router returns string for readable format."""
        formatter = ResponseFormatter()
        data = {
            'content': 'Test content',
            'path': '/test.txt',
            'mode': 'chunk',
            'start_line': 1
        }

        # Mock append_entry to avoid actual logging during test
        # In real usage, this would log to tool_logs
        result = await formatter.finalize_tool_response(
            data,
            format="readable",
            tool_name="read_file"
        )

        # Should return CallToolResult with TextContent (Issue #9962 fix)
        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert "FILE CONTENT" in result.content[0].text

    @pytest.mark.asyncio
    async def test_router_structured_format(self):
        """Test router returns dict for structured format."""
        formatter = ResponseFormatter()
        data = {'test': 'data'}

        result = await formatter.finalize_tool_response(
            data,
            format="structured",
            tool_name="test_tool"
        )

        # Should return dict unchanged
        assert isinstance(result, dict)
        assert result == data

    @pytest.mark.asyncio
    async def test_router_compact_format(self):
        """Test router returns dict for compact format."""
        formatter = ResponseFormatter()
        data = {'test': 'data'}

        result = await formatter.finalize_tool_response(
            data,
            format="compact",
            tool_name="test_tool"
        )

        # Should return dict
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_router_default_format(self):
        """Test router defaults to readable format."""
        formatter = ResponseFormatter()
        data = {
            'content': 'Test',
            'path': '/test.txt',
            'mode': 'chunk',
            'start_line': 1
        }

        # No format parameter should default to readable
        result = await formatter.finalize_tool_response(
            data,
            tool_name="read_file"
        )

        # Should return CallToolResult (readable is default, Issue #9962 fix)
        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)

    @pytest.mark.asyncio
    async def test_router_unknown_tool(self):
        """Test router handles unknown tools gracefully."""
        formatter = ResponseFormatter()
        data = {'test': 'data'}

        result = await formatter.finalize_tool_response(
            data,
            format="readable",
            tool_name="unknown_tool"
        )

        # Should return CallToolResult with JSON content for unknown tools (Issue #9962 fix)
        from mcp.types import CallToolResult, TextContent
        assert isinstance(result, CallToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert '"test"' in result.content[0].text or "'test'" in result.content[0].text


class TestFormatConstants:
    """Test format constants are defined correctly."""

    def test_format_constants_exist(self):
        """Test all format constants are defined."""
        assert hasattr(ResponseFormatter, 'FORMAT_READABLE')
        assert hasattr(ResponseFormatter, 'FORMAT_STRUCTURED')
        assert hasattr(ResponseFormatter, 'FORMAT_COMPACT')

    def test_format_constant_values(self):
        """Test format constant values are correct."""
        assert ResponseFormatter.FORMAT_READABLE == "readable"
        assert ResponseFormatter.FORMAT_STRUCTURED == "structured"
        assert ResponseFormatter.FORMAT_COMPACT == "compact"


class TestBackwardCompatibility:
    """Test that existing ResponseFormatter functionality still works."""

    def test_existing_format_entry(self):
        """Test existing format_entry method still works."""
        formatter = ResponseFormatter()
        entry = {
            'id': '123',
            'message': 'Test',
            'timestamp': '2025-01-02T14:30:00Z',
            'emoji': '✅',
            'agent': 'TestAgent'
        }

        # Should still work in full mode
        result = formatter.format_entry(entry, compact=False)
        assert isinstance(result, dict)
        assert result['message'] == 'Test'

        # Should still work in compact mode
        compact_result = formatter.format_entry(entry, compact=True)
        assert isinstance(compact_result, dict)

    def test_existing_format_response(self):
        """Test existing format_response method still works."""
        formatter = ResponseFormatter()
        entries = [
            {'id': '1', 'message': 'Test 1'},
            {'id': '2', 'message': 'Test 2'}
        ]

        result = formatter.format_response(entries)
        assert isinstance(result, dict)
        assert result['ok'] is True
        assert result['count'] == 2

    def test_existing_format_projects_response(self):
        """Test existing format_projects_response method still works."""
        formatter = ResponseFormatter()
        projects = [
            {'name': 'project1', 'root': '/path1'},
            {'name': 'project2', 'root': '/path2'}
        ]

        result = formatter.format_projects_response(projects)
        assert isinstance(result, dict)
        assert result['ok'] is True
        assert result['count'] == 2


class TestAppendEntryFormatting:
    """Test Phase 2 append_entry readable formatting functionality."""

    def test_single_entry_basic(self):
        """Test basic single entry formatting."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'written_line': '[ℹ️] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] Investigation complete',
            'path': '/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/project/PROGRESS_LOG.md',
            'meta': {}
        }

        result = formatter.format_readable_append_entry(data)

        # Check basic structure
        assert '✅ Entry written to progress log' in result
        assert '[ℹ️]' in result
        assert 'Investigation complete' in result
        assert '📁' in result
        assert 'PROGRESS_LOG.md' in result

    def test_single_entry_with_reasoning(self):
        """Test single entry formatting with reasoning block."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'written_line': '[ℹ️] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] Investigation complete',
            'path': '/.scribe/docs/dev_plans/project/PROGRESS_LOG.md',
            'meta': {
                'reasoning': '{"why": "Need to understand append_entry structure", "what": "Analyzed return values", "how": "Read source code"}'
            }
        }

        result = formatter.format_readable_append_entry(data)

        # Check reasoning block is present and formatted
        assert 'Reasoning:' in result
        assert '├─ Why:' in result
        assert 'Need to understand append_entry structure' in result
        assert '├─ What:' in result
        assert 'Analyzed return values' in result
        assert '└─ How:' in result
        assert 'Read source code' in result

    def test_single_entry_with_dict_reasoning(self):
        """Test single entry formatting with reasoning as dict (not JSON string)."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'written_line': '[ℹ️] Investigation complete',
            'path': '/.scribe/docs/PROGRESS_LOG.md',
            'meta': {
                'reasoning': {
                    'why': 'Testing dict format',
                    'what': 'Direct dict instead of JSON string',
                    'how': 'Pass dict directly'
                }
            }
        }

        result = formatter.format_readable_append_entry(data)

        # Check reasoning block parses dict correctly
        assert 'Reasoning:' in result
        assert 'Testing dict format' in result
        assert 'Direct dict instead of JSON string' in result
        assert 'Pass dict directly' in result

    def test_single_entry_with_reminders(self):
        """Test single entry formatting with reminders."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'written_line': '[ℹ️] Investigation complete',
            'path': '/.scribe/docs/PROGRESS_LOG.md',
            'meta': {},
            'reminders': [
                {'emoji': '⏰', 'message': "It's been 15 minutes since the last log entry."},
                {'emoji': '🎯', 'message': 'Project: scribe_tool_output_refinement'}
            ]
        }

        result = formatter.format_readable_append_entry(data)

        # Check reminders section is present
        assert '⏰ Reminders:' in result
        assert "It's been 15 minutes" in result
        assert 'Project: scribe_tool_output_refinement' in result

    def test_single_entry_without_reminders(self):
        """Test single entry formatting without reminders (conditional display)."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'written_line': '[ℹ️] Investigation complete',
            'path': '/.scribe/docs/PROGRESS_LOG.md',
            'meta': {},
            'reminders': []
        }

        result = formatter.format_readable_append_entry(data)

        # Check reminders section is NOT present when empty
        assert '⏰ Reminders:' not in result

    def test_single_entry_failed(self):
        """Test single entry formatting when write fails."""
        formatter = ResponseFormatter()
        data = {
            'ok': False,
            'error': 'Permission denied',
            'path': '/.scribe/docs/PROGRESS_LOG.md',
            'meta': {}
        }

        result = formatter.format_readable_append_entry(data)

        # Check failure indicator
        assert '❌ Entry write failed' in result

    def test_bulk_entry_success(self):
        """Test bulk entry formatting with all successes."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'written_count': 15,
            'failed_count': 0,
            'written_lines': [
                '[ℹ️] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] [Project: test] Investigation started | phase=research',
                '[ℹ️] [2026-01-03 02:46:01 UTC] [Agent: ResearchAgent] [Project: test] Found 14 tools | count=14',
                '[✅] [2026-01-03 02:46:02 UTC] [Agent: ResearchAgent] [Project: test] Analysis complete | confidence=0.95',
                '[ℹ️] [2026-01-03 02:46:03 UTC] [Agent: ResearchAgent] [Project: test] Creating research document',
                '[✅] [2026-01-03 02:46:04 UTC] [Agent: ResearchAgent] [Project: test] Research document created | size=15KB'
            ],
            'failed_items': [],
            'paths': ['/.scribe/docs/PROGRESS_LOG.md'],
            'performance': {'items_per_second': 45.2}
        }

        result = formatter.format_readable_append_entry(data)

        # Check bulk header
        assert 'BULK APPEND RESULT' in result
        assert 'status: success' in result
        assert 'written: 15 / 15' in result
        assert 'failed: 0' in result
        assert 'performance: 45.2 items/sec' in result

        # Check sample entries (first 5)
        assert '✅ Successfully Written (first 5 of 15):' in result
        assert '[ℹ️] Investigation started' in result
        assert '[✅] Analysis complete' in result

        # Check metadata footer
        assert 'METADATA' in result
        assert 'paths: 1 log file written' in result

    def test_bulk_entry_partial_success(self):
        """Test bulk entry formatting with partial success."""
        formatter = ResponseFormatter()
        data = {
            'ok': False,
            'written_count': 15,
            'failed_count': 3,
            'written_lines': [
                '[ℹ️] Investigation started',
                '[ℹ️] Found 14 tools'
            ],
            'failed_items': [
                {'index': 7, 'error': "Missing required field 'message'"},
                {'index': 12, 'error': 'JSON parsing error in metadata'},
                {'index': 15, 'error': 'Permission denied writing to log file'}
            ],
            'paths': ['/.scribe/docs/PROGRESS_LOG.md', '/.scribe/docs/BUG_LOG.md']
        }

        result = formatter.format_readable_append_entry(data)

        # Check partial success status
        assert 'status: partial success' in result
        assert 'written: 15 / 18' in result
        assert 'failed: 3' in result

        # Check failed entries section
        assert '❌ Failed Entries (3):' in result
        assert "7. Missing required field 'message'" in result
        assert '12. JSON parsing error in metadata' in result
        assert '15. Permission denied writing to log file' in result

        # Check multiple paths
        assert 'paths: 2 log files written' in result

    def test_parse_reasoning_block_json_string(self):
        """Test _parse_reasoning_block with JSON string."""
        formatter = ResponseFormatter()
        meta = {
            'reasoning': '{"why": "test why", "what": "test what", "how": "test how"}'
        }

        result = formatter._parse_reasoning_block(meta)

        assert result is not None
        assert result['why'] == 'test why'
        assert result['what'] == 'test what'
        assert result['how'] == 'test how'

    def test_parse_reasoning_block_dict(self):
        """Test _parse_reasoning_block with dict."""
        formatter = ResponseFormatter()
        meta = {
            'reasoning': {'why': 'test why', 'what': 'test what', 'how': 'test how'}
        }

        result = formatter._parse_reasoning_block(meta)

        assert result is not None
        assert result['why'] == 'test why'

    def test_parse_reasoning_block_missing(self):
        """Test _parse_reasoning_block with no reasoning field."""
        formatter = ResponseFormatter()
        meta = {}

        result = formatter._parse_reasoning_block(meta)

        assert result is None

    def test_parse_reasoning_block_malformed_json(self):
        """Test _parse_reasoning_block with malformed JSON."""
        formatter = ResponseFormatter()
        meta = {
            'reasoning': '{invalid json'
        }

        result = formatter._parse_reasoning_block(meta)

        # Should return None for malformed JSON
        assert result is None

    def test_extract_compact_log_line(self):
        """Test _extract_compact_log_line extracts emoji and message."""
        formatter = ResponseFormatter()
        full_line = '[ℹ️] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] [Project: test] Investigation complete | confidence=0.95'

        result = formatter._extract_compact_log_line(full_line)

        # Should extract emoji and message part
        assert '[ℹ️]' in result
        assert 'Investigation complete' in result
        assert 'confidence=0.95' in result
        # Should NOT include timestamp/agent/project
        assert '2026-01-03' not in result
        assert 'ResearchAgent' not in result
        assert '[Project:' not in result

    def test_extract_compact_log_line_fallback(self):
        """Test _extract_compact_log_line fallback for unexpected format."""
        formatter = ResponseFormatter()
        short_line = 'Simple message'

        result = formatter._extract_compact_log_line(short_line)

        # Should return original line if not enough parts
        assert result == 'Simple message'

    def test_no_ansi_colors_in_append_entry(self):
        """Test that NO ANSI color codes appear in append_entry output (user design)."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'written_line': '[ℹ️] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] Investigation complete',
            'path': '/.scribe/docs/PROGRESS_LOG.md',
            'meta': {
                'reasoning': {'why': 'test', 'what': 'test', 'how': 'test'}
            },
            'reminders': [{'emoji': '⏰', 'message': 'Test reminder'}]
        }

        result = formatter.format_readable_append_entry(data)

        # Check NO ANSI codes present (critical design decision)
        assert '\033[' not in result  # No ANSI escape sequences


class TestPhase3aReadRecentEnhancements:
    """Test Phase 3a enhancements for read_recent readable output."""

    def test_log_entries_with_reasoning_blocks(self):
        """Test that reasoning blocks are parsed and displayed inline."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2026-01-03T03:30:00.000Z',
                'agent': 'CoderAgent',
                'emoji': '✅',
                'status': 'success',
                'message': 'Implementation complete',
                'meta': {
                    'reasoning': {
                        'why': 'User requested Phase 3a implementation',
                        'what': 'Enhanced read_recent with readable output',
                        'how': 'Modified defaults, added formatter integration'
                    }
                }
            }
        ]
        pagination = {'total_count': 1, 'page': 1, 'page_size': 10}
        result = formatter.format_readable_log_entries(entries, pagination)

        # Should have reasoning tree under entry
        assert '├─ Why:' in result
        assert 'User requested Phase 3a implementation' in result
        assert '├─ What:' in result
        assert 'Enhanced read_recent with readable output' in result
        assert '└─ How:' in result
        assert 'Modified defaults, added formatter integration' in result

    def test_log_entries_without_reasoning(self):
        """Test entries without reasoning blocks display normally."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2026-01-03T03:30:00.000Z',
                'agent': 'TestAgent',
                'emoji': 'ℹ️',
                'status': 'info',
                'message': 'Simple message without reasoning',
                'meta': {}
            }
        ]
        pagination = {'total_count': 1, 'page': 1, 'page_size': 10}
        result = formatter.format_readable_log_entries(entries, pagination)

        # Should NOT have reasoning markers
        assert '├─ Why:' not in result
        assert '├─ What:' not in result
        assert '└─ How:' not in result

    def test_smart_message_truncation(self):
        """Test _truncate_message_smart truncates at word boundaries."""
        formatter = ResponseFormatter()

        # Short message (no truncation)
        short = "This is a short message"
        assert formatter._truncate_message_smart(short, 100) == short

        # Long message (should truncate at word boundary)
        long = "This is a very long message that should be truncated at a word boundary instead of cutting in the middle of a word"
        result = formatter._truncate_message_smart(long, 50)
        assert len(result) <= 50
        assert result.endswith("...")
        assert not result[:-3].endswith(" ")  # No trailing space before ...

    def test_smart_truncation_fallback(self):
        """Test smart truncation falls back if no good word boundary exists."""
        formatter = ResponseFormatter()

        # Message with no spaces in truncation zone
        no_spaces = "A" * 100 + " word"
        result = formatter._truncate_message_smart(no_spaces, 50)
        # Should still truncate even without good boundary
        assert len(result) <= 50
        assert result.endswith("...")

    def test_compact_timestamp_format(self):
        """Test timestamps are formatted as HH:MM."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2026-01-03T15:42:37.123456Z',  # ISO format
                'agent': 'Agent1',
                'emoji': 'ℹ️',
                'message': 'Test 1',
                'meta': {}
            },
            {
                'timestamp': '2026-01-03T16:55:23.000Z',  # ISO format
                'agent': 'Agent2',
                'emoji': 'ℹ️',
                'message': 'Test 2',
                'meta': {}
            }
        ]
        pagination = {'total_count': 2, 'page': 1, 'page_size': 10}
        result = formatter.format_readable_log_entries(entries, pagination)

        # Strip ANSI for timestamp check
        clean_result = strip_ansi(result)

        # Should show HH:MM format only
        assert '15:42' in clean_result
        assert '16:55' in clean_result
        # Should NOT show seconds
        assert ':37' not in clean_result
        assert ':23' not in clean_result

    def test_pagination_display(self):
        """Test pagination is displayed clearly in header."""
        formatter = ResponseFormatter()
        entries = [{'timestamp': '2026-01-03T15:00:00Z', 'agent': 'A', 'emoji': 'ℹ️', 'message': 'M', 'meta': {}}]

        # Page 1 of 5 (10 entries shown of 47 total)
        pagination = {'total_count': 47, 'page': 1, 'page_size': 10}
        result = formatter.format_readable_log_entries(entries, pagination)

        assert 'Page 1 of 5' in result  # 47 / 10 = 5 pages
        assert '(1/47)' in result  # showing 1 of 47

    def test_ansi_colors_enabled_for_read_recent(self):
        """Test ANSI colors ARE present in read_recent output (display-heavy tool)."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2026-01-03T15:00:00Z',
                'agent': 'TestAgent',
                'emoji': '✅',
                'status': 'success',
                'message': 'Test message',
                'meta': {}
            }
        ]
        pagination = {'total_count': 1, 'page': 1, 'page_size': 10}
        result = formatter.format_readable_log_entries(entries, pagination)

        # If USE_COLORS is enabled (config-driven), should have ANSI codes
        # Note: This test may pass or fail depending on repo config
        if formatter.USE_COLORS:
            assert '\033[' in result  # ANSI escape codes present
        else:
            assert '\033[' not in result  # No ANSI codes when disabled

    def test_uuid_agent_truncation(self):
        """Test long UUID agent names are truncated."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2026-01-03T15:00:00Z',
                'agent': 'a4b53654-fafd-48d2-8846-abeae72d565c',  # 36 char UUID
                'emoji': 'ℹ️',
                'message': 'Test',
                'meta': {}
            }
        ]
        pagination = {'total_count': 1, 'page': 1, 'page_size': 10}
        result = formatter.format_readable_log_entries(entries, pagination)

        clean_result = strip_ansi(result)

        # Should truncate UUID to first 12 chars + ...
        assert 'a4b53654-faf...' in clean_result
        # Should NOT show full UUID
        assert 'a4b53654-fafd-48d2-8846-abeae72d565c' not in clean_result


class TestPhase3bQueryEntriesEnhancements:
    """Test Phase 3b enhancements for query_entries search results formatting."""

    def test_query_results_header_with_message_filter(self):
        """Test search results header shows message filter."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2026-01-03T03:30:00Z',
                'agent': 'CoderAgent',
                'emoji': '✅',
                'status': 'success',
                'message': 'Bug fixed in authentication',
                'meta': {}
            }
        ]
        pagination = {'total_count': 5, 'page': 1, 'page_size': 10}
        search_context = {'message': 'bug'}

        result = formatter.format_readable_log_entries(entries, pagination, search_context)
        clean_result = strip_ansi(result)

        # Should show search header instead of recent entries
        assert '🔍 SEARCH RESULTS' in clean_result
        assert 'Found 1 of 5 matches' in clean_result
        # Should show filter
        assert 'Filter:' in clean_result
        assert 'message="bug"' in clean_result

    def test_query_results_multiple_filters(self):
        """Test search results header shows multiple filters."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2026-01-03T03:30:00Z',
                'agent': 'CoderAgent',
                'emoji': '⚠️',
                'status': 'error',
                'message': 'Error in processing',
                'meta': {}
            }
        ]
        pagination = {'total_count': 3, 'page': 1, 'page_size': 10}
        search_context = {
            'message': 'error',
            'status': ['error', 'bug'],
            'agents': ['CoderAgent']
        }

        result = formatter.format_readable_log_entries(entries, pagination, search_context)
        clean_result = strip_ansi(result)

        # Should show all filters (may be truncated if too long)
        assert 'message="error"' in clean_result
        assert "status=['error', 'bug']" in clean_result
        # agents filter may be truncated, just check for presence
        assert "agents=" in clean_result or 'Code...' in clean_result

    def test_query_results_no_search_context(self):
        """Test that read_recent (no search_context) shows normal header."""
        formatter = ResponseFormatter()
        entries = [
            {
                'timestamp': '2026-01-03T03:30:00Z',
                'agent': 'TestAgent',
                'emoji': 'ℹ️',
                'status': 'info',
                'message': 'Normal log entry',
                'meta': {}
            }
        ]
        pagination = {'total_count': 10, 'page': 1, 'page_size': 10}

        # No search_context = read_recent mode
        result = formatter.format_readable_log_entries(entries, pagination, search_context=None)
        clean_result = strip_ansi(result)

        # Should show recent entries header
        assert '📋 RECENT LOG ENTRIES' in clean_result
        assert 'Page 1 of 1' in clean_result
        # Should NOT show search header
        assert '🔍 SEARCH RESULTS' not in clean_result
        assert 'Filter:' not in clean_result

    def test_query_results_empty_results(self):
        """Test search with no results returns appropriate message."""
        formatter = ResponseFormatter()
        entries = []
        pagination = {'total_count': 0, 'page': 1, 'page_size': 10}
        search_context = {'message': 'nonexistent'}

        result = formatter.format_readable_log_entries(entries, pagination, search_context)

        # Should return "No log entries found" message
        assert result == "No log entries found."

    def test_query_filter_truncation(self):
        """Test long filter strings are truncated."""
        formatter = ResponseFormatter()
        entries = [{'timestamp': '2026-01-03T03:30:00Z', 'agent': 'A', 'emoji': 'ℹ️', 'message': 'M', 'meta': {}}]
        pagination = {'total_count': 1, 'page': 1, 'page_size': 10}

        # Very long message filter
        long_message = "This is a very long search query that should be truncated to fit within the header box width limit"
        search_context = {'message': long_message}

        result = formatter.format_readable_log_entries(entries, pagination, search_context)
        clean_result = strip_ansi(result)

        # Filter should be truncated with ...
        assert 'Filter:' in clean_result
        assert '...' in clean_result
        # Should NOT show full filter
        assert long_message not in clean_result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
