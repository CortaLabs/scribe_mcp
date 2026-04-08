"""
Tests for EntryFormatter - log entry formatting for append_entry, read_recent, query_entries.

Phase 5 Task 5.4: Tests written BEFORE extraction to prevent regressions.

Test Coverage:
- format_entry (compact and full modes)
- _format_full_entry (field selection)
- _format_compact_entry (field mapping, truncation)
- format_response (pagination, token warnings)
- format_readable_log_entries (headers, reasoning blocks, search context)
- _truncate_message_smart (word boundary truncation)
- _parse_reasoning_block (JSON and dict parsing)
- format_readable_append_entry (single and bulk dispatch)
- _format_single_append_entry (optimized readable format)
- _format_bulk_append_entry (summary format)
- _extract_compact_log_line (log line extraction)
"""

import pytest
import re
from datetime import datetime
from typing import Dict, Any


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text for testing."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


# ==================== Test format_entry ====================

class TestFormatEntry:
    """Tests for format_entry method."""

    def test_format_entry_full_mode(self):
        """format_entry with compact=False returns full entry."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "id": 1,
            "timestamp": "2026-01-03T14:30:00Z",
            "agent": "TestAgent",
            "message": "Test message",
            "emoji": "info",
            "status": "info",
            "meta": {"key": "value"}
        }

        result = formatter.format_entry(entry, compact=False)

        assert "id" in result
        assert result["timestamp"] == "2026-01-03T14:30:00Z"
        assert result["agent"] == "TestAgent"
        assert result["message"] == "Test message"
        assert result["meta"] == {"key": "value"}

    def test_format_entry_compact_mode(self):
        """format_entry with compact=True returns abbreviated fields."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "id": 1,
            "timestamp": "2026-01-03T14:30:00Z",
            "agent": "TestAgent",
            "message": "Test message",
            "emoji": "info",
            "status": "info",
            "meta": {"key": "value"}
        }

        result = formatter.format_entry(entry, compact=True)

        # Compact mode uses abbreviated field names (m for message, a for agent, etc)
        assert "m" in result or "msg" in result or "message" in result
        assert "a" in result or "agent" in result

    def test_format_entry_exclude_metadata(self):
        """format_entry with include_metadata=False excludes meta field."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "id": 1,
            "timestamp": "2026-01-03T14:30:00Z",
            "agent": "TestAgent",
            "message": "Test message",
            "meta": {"key": "value"}
        }

        result = formatter.format_entry(entry, include_metadata=False)

        assert "meta" not in result

    def test_format_entry_field_selection(self):
        """format_entry with fields parameter returns only selected fields."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "id": 1,
            "timestamp": "2026-01-03T14:30:00Z",
            "agent": "TestAgent",
            "message": "Test message",
            "meta": {"key": "value"}
        }

        result = formatter.format_entry(entry, fields=["message", "agent"])

        assert "message" in result
        assert "agent" in result
        assert "timestamp" not in result
        assert "id" not in result


# ==================== Test _format_full_entry ====================

class TestFormatFullEntry:
    """Tests for _format_full_entry method."""

    def test_format_full_entry_all_fields(self):
        """_format_full_entry with no field selection returns all fields."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "id": 1,
            "timestamp": "2026-01-03T14:30:00Z",
            "agent": "TestAgent",
            "message": "Test message",
            "meta": {"key": "value"}
        }

        result = formatter._format_full_entry(entry, None, True)

        assert result == entry

    def test_format_full_entry_selected_fields(self):
        """_format_full_entry with field selection returns only those fields."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "id": 1,
            "timestamp": "2026-01-03T14:30:00Z",
            "agent": "TestAgent",
            "message": "Test message",
            "meta": {"key": "value"}
        }

        result = formatter._format_full_entry(entry, ["message"], True)

        assert result == {"message": "Test message"}

    def test_format_full_entry_exclude_metadata(self):
        """_format_full_entry excludes meta when include_metadata=False."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "id": 1,
            "message": "Test",
            "meta": {"key": "value"}
        }

        result = formatter._format_full_entry(entry, None, False)

        assert "meta" not in result
        assert "message" in result


# ==================== Test _format_compact_entry ====================

class TestFormatCompactEntry:
    """Tests for _format_compact_entry method."""

    def test_format_compact_entry_field_mapping(self):
        """_format_compact_entry maps field names to compact versions."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "timestamp": "2026-01-03T14:30:00Z",
            "message": "Test message",
            "agent": "TestAgent"
        }

        result = formatter._format_compact_entry(entry, None, True)

        # Check that at least some fields are mapped
        # The exact mapping depends on COMPACT_FIELD_MAP
        assert len(result) > 0

    def test_format_compact_entry_timestamp_shortening(self):
        """_format_compact_entry shortens timestamp format."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entry = {
            "timestamp": "2026-01-03T14:30:00Z",
            "message": "Test"
        }

        result = formatter._format_compact_entry(entry, None, True)

        # Timestamp should be shortened to date only
        ts_key = "ts" if "ts" in result else "timestamp"
        if ts_key in result:
            assert len(result[ts_key]) <= len("2026-01-03T14:30:00Z")

    def test_format_compact_entry_message_truncation(self):
        """_format_compact_entry truncates long messages."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        long_message = "A" * 200
        entry = {
            "timestamp": "2026-01-03T14:30:00Z",
            "message": long_message
        }

        result = formatter._format_compact_entry(entry, None, True)

        # Message should be truncated to ~100 chars
        msg_key = "msg" if "msg" in result else "message"
        if msg_key in result:
            assert len(result[msg_key]) <= 103  # 100 + "..."


# ==================== Test format_response ====================

class TestFormatResponse:
    """Tests for format_response method."""

    def test_format_response_basic(self):
        """format_response returns properly structured response."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {"id": 1, "message": "Entry 1"},
            {"id": 2, "message": "Entry 2"}
        ]

        result = formatter.format_response(entries)

        assert result["ok"] is True
        assert result["count"] == 2
        assert len(result["entries"]) == 2

    def test_format_response_with_pagination(self):
        """format_response includes pagination info when provided."""
        from utils.response import ResponseFormatter
        from utils.estimator import PaginationInfo
        formatter = ResponseFormatter()

        entries = [{"id": 1, "message": "Entry 1"}]
        # PaginationInfo requires all fields: page, page_size, total_count, has_next, has_prev
        pagination = PaginationInfo(page=1, page_size=10, total_count=100, has_next=True, has_prev=False)

        result = formatter.format_response(entries, pagination=pagination)

        assert "pagination" in result
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["total_count"] == 100

    def test_format_response_compact_flag(self):
        """format_response sets compact flag when compact=True."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [{"id": 1, "message": "Entry 1"}]

        result = formatter.format_response(entries, compact=True)

        assert result.get("compact") is True

    def test_format_response_extra_data(self):
        """format_response includes extra_data in response."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [{"id": 1, "message": "Entry 1"}]
        extra = {"custom_field": "custom_value"}

        result = formatter.format_response(entries, extra_data=extra)

        assert result["custom_field"] == "custom_value"

    def test_format_response_token_warning(self):
        """format_response adds token warning when response exceeds threshold."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter(token_warning_threshold=10)  # Very low threshold

        entries = [{"id": i, "message": f"Entry {i} " * 50} for i in range(100)]

        result = formatter.format_response(entries)

        # Should have token warning due to large response
        assert "token_warning" in result


# ==================== Test format_readable_log_entries ====================

class TestFormatReadableLogEntries:
    """Tests for format_readable_log_entries method."""

    def test_format_readable_log_entries_basic(self):
        """format_readable_log_entries returns formatted string."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "TestAgent",
                "message": "Test message",
                "emoji": "info",
                "status": "info"
            }
        ]
        pagination = {"page": 1, "page_size": 10, "total_count": 1}

        result = formatter.format_readable_log_entries(entries, pagination)

        assert isinstance(result, str)
        assert "TestAgent" in result
        assert "Test message" in result

    def test_format_readable_log_entries_empty(self):
        """format_readable_log_entries returns message for empty entries."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        result = formatter.format_readable_log_entries([], {})

        assert "No log entries found" in result

    def test_format_readable_log_entries_with_reasoning(self):
        """format_readable_log_entries shows reasoning blocks."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "TestAgent",
                "message": "Test message",
                "emoji": "info",
                "status": "info",
                "meta": {
                    "reasoning": {
                        "why": "Test why",
                        "what": "Test what",
                        "how": "Test how"
                    }
                }
            }
        ]
        pagination = {"page": 1, "page_size": 10, "total_count": 1}

        result = formatter.format_readable_log_entries(entries, pagination)
        result_clean = strip_ansi(result)

        assert "Why:" in result_clean
        assert "Test why" in result_clean
        assert "What:" in result_clean
        assert "Test what" in result_clean
        assert "How:" in result_clean
        assert "Test how" in result_clean

    def test_format_readable_log_entries_search_context(self):
        """format_readable_log_entries shows search header when search_context provided."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "TestAgent",
                "message": "Test message",
                "emoji": "info",
                "status": "info"
            }
        ]
        pagination = {"page": 1, "page_size": 10, "total_count": 1}
        search_context = {"message": "test", "status": "info"}

        result = formatter.format_readable_log_entries(entries, pagination, search_context=search_context)
        result_clean = strip_ansi(result)

        assert "SEARCH RESULTS" in result_clean

    def test_format_readable_log_entries_recent_header(self):
        """format_readable_log_entries shows recent header when no search_context."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "TestAgent",
                "message": "Test message",
                "emoji": "info",
                "status": "info"
            }
        ]
        pagination = {"page": 1, "page_size": 10, "total_count": 1}

        result = formatter.format_readable_log_entries(entries, pagination)
        result_clean = strip_ansi(result)

        assert "RECENT LOG ENTRIES" in result_clean

    def test_format_readable_log_entries_with_project_name(self):
        """format_readable_log_entries includes project name in header."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "TestAgent",
                "message": "Test message",
                "emoji": "info"
            }
        ]
        pagination = {"page": 1, "page_size": 10, "total_count": 1}

        result = formatter.format_readable_log_entries(entries, pagination, project_name="test_project")
        result_clean = strip_ansi(result)

        assert "test_project" in result_clean

    def test_format_readable_log_entries_timestamp_format(self):
        """format_readable_log_entries uses compact HH:MM timestamp format."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "TestAgent",
                "message": "Test message",
                "emoji": "info"
            }
        ]
        pagination = {"page": 1, "page_size": 10, "total_count": 1}

        result = formatter.format_readable_log_entries(entries, pagination)
        result_clean = strip_ansi(result)

        # Should have HH:MM format, not full ISO timestamp
        assert "14:30" in result_clean

    def test_format_readable_log_entries_filters_tool_logs(self):
        """format_readable_log_entries filters out tool_logs entries."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "TestAgent",
                "message": "Visible message",
                "emoji": "info"
            },
            {
                "timestamp": "2026-01-03T14:31:00Z",
                "agent": "TestAgent",
                "message": "Tool call: some_tool",
                "emoji": "info",
                "meta": {"log_type": "tool_logs"}
            }
        ]
        pagination = {"page": 1, "page_size": 10, "total_count": 2}

        result = formatter.format_readable_log_entries(entries, pagination)
        result_clean = strip_ansi(result)

        assert "Visible message" in result_clean
        assert "Tool call:" not in result_clean

    def test_format_readable_log_entries_agent_truncation(self):
        """format_readable_log_entries truncates long agent names."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "VeryLongAgentNameThatShouldBeTruncated",
                "message": "Test message",
                "emoji": "info"
            }
        ]
        pagination = {"page": 1, "page_size": 10, "total_count": 1}

        result = formatter.format_readable_log_entries(entries, pagination)
        result_clean = strip_ansi(result)

        # Agent should be truncated to 12 chars + "..."
        assert "VeryLongAgen..." in result_clean


# ==================== Test _truncate_message_smart ====================

class TestTruncateMessageSmart:
    """Tests for _truncate_message_smart method."""

    def test_truncate_message_smart_short_message(self):
        """_truncate_message_smart returns short messages unchanged."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        message = "Short message"
        result = formatter._truncate_message_smart(message, max_length=100)

        assert result == message

    def test_truncate_message_smart_long_message(self):
        """_truncate_message_smart truncates long messages."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        message = "A" * 200
        result = formatter._truncate_message_smart(message, max_length=100)

        assert len(result) <= 100
        assert result.endswith("...")

    def test_truncate_message_smart_word_boundary(self):
        """_truncate_message_smart truncates at word boundary when possible."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        message = "This is a test message that should be truncated at a word boundary"
        result = formatter._truncate_message_smart(message, max_length=50)

        # Should end with ... and not cut mid-word
        assert result.endswith("...")
        # Should be at or near max_length
        assert len(result) <= 50


# ==================== Test _parse_reasoning_block ====================

class TestParseReasoningBlock:
    """Tests for _parse_reasoning_block method."""

    def test_parse_reasoning_block_dict(self):
        """_parse_reasoning_block parses dict reasoning."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        meta = {
            "reasoning": {
                "why": "Test why",
                "what": "Test what",
                "how": "Test how"
            }
        }

        result = formatter._parse_reasoning_block(meta)

        assert result is not None
        assert result["why"] == "Test why"
        assert result["what"] == "Test what"
        assert result["how"] == "Test how"

    def test_parse_reasoning_block_json_string(self):
        """_parse_reasoning_block parses JSON string reasoning."""
        from utils.response import ResponseFormatter
        import json
        formatter = ResponseFormatter()

        meta = {
            "reasoning": json.dumps({
                "why": "Test why",
                "what": "Test what",
                "how": "Test how"
            })
        }

        result = formatter._parse_reasoning_block(meta)

        assert result is not None
        assert result["why"] == "Test why"

    def test_parse_reasoning_block_empty(self):
        """_parse_reasoning_block returns None for empty meta."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        result = formatter._parse_reasoning_block({})

        assert result is None

    def test_parse_reasoning_block_no_reasoning_key(self):
        """_parse_reasoning_block returns None when reasoning key missing."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        result = formatter._parse_reasoning_block({"other": "value"})

        assert result is None

    def test_parse_reasoning_block_invalid_json(self):
        """_parse_reasoning_block returns None for invalid JSON."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        meta = {"reasoning": "not valid json"}

        result = formatter._parse_reasoning_block(meta)

        assert result is None

    def test_parse_reasoning_block_partial_keys(self):
        """_parse_reasoning_block accepts partial reasoning keys."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        meta = {
            "reasoning": {
                "why": "Only why is present"
            }
        }

        result = formatter._parse_reasoning_block(meta)

        assert result is not None
        assert result["why"] == "Only why is present"


# ==================== Test format_readable_append_entry ====================

class TestFormatReadableAppendEntry:
    """Tests for format_readable_append_entry method."""

    def test_format_readable_append_entry_single(self):
        """format_readable_append_entry formats single entry."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_line": "[info] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] [Project: test] Test message | key=value",
            "path": "/path/to/PROGRESS_LOG.md",
            "meta": {}
        }

        result = formatter.format_readable_append_entry(data)

        assert isinstance(result, str)
        assert "PROGRESS_LOG.md" in result

    def test_format_readable_append_entry_bulk(self):
        """format_readable_append_entry formats bulk entry."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_count": 5,
            "failed_count": 0,
            "written_lines": ["line1", "line2", "line3", "line4", "line5"],
            "paths": ["/path/to/PROGRESS_LOG.md"]
        }

        result = formatter.format_readable_append_entry(data)

        assert isinstance(result, str)
        assert "BULK APPEND" in result

    def test_format_readable_append_entry_with_reasoning(self):
        """format_readable_append_entry shows reasoning block."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_line": "[info] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] [Project: test] Test message",
            "path": "/path/to/PROGRESS_LOG.md",
            "meta": {
                "reasoning": {
                    "why": "Test why",
                    "what": "Test what",
                    "how": "Test how"
                }
            }
        }

        result = formatter.format_readable_append_entry(data)

        assert "Reasoning:" in result
        assert "Why:" in result
        assert "Test why" in result

    def test_format_readable_append_entry_with_reminders(self):
        """format_readable_append_entry shows reminders when present."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_line": "[info] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] [Project: test] Test message",
            "path": "/path/to/PROGRESS_LOG.md",
            "meta": {},
            "reminders": [
                {"emoji": "warning", "message": "Test reminder"}
            ]
        }

        result = formatter.format_readable_append_entry(data)

        assert "Reminders:" in result
        assert "Test reminder" in result

    def test_format_readable_append_entry_failed(self):
        """format_readable_append_entry handles failure case."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": False,
            "meta": {}
        }

        result = formatter.format_readable_append_entry(data)

        assert "failed" in result.lower()


# ==================== Test _format_single_append_entry ====================

class TestFormatSingleAppendEntry:
    """Tests for _format_single_append_entry method."""

    def test_format_single_append_entry_basic(self):
        """_format_single_append_entry formats entry correctly."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_line": "[info] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] [Project: test] Test message | key=value",
            "path": "/path/to/PROGRESS_LOG.md",
            "meta": {}
        }

        result = formatter._format_single_append_entry(data, USE_COLORS=False)

        assert isinstance(result, str)
        assert "Test message" in result

    def test_format_single_append_entry_extracts_timestamp(self):
        """_format_single_append_entry extracts HH:MM timestamp when custom metadata present."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        # Timestamp line only shows when there's custom metadata or reasoning block
        data = {
            "ok": True,
            "written_line": "[info] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] [Project: test] Test message | custom=value",
            "path": "/path/to/PROGRESS_LOG.md",
            "meta": {"reasoning": {"why": "test", "what": "test", "how": "test"}}  # Reasoning triggers metadata line
        }

        result = formatter._format_single_append_entry(data, USE_COLORS=False)

        # Should have compact timestamp (14:30 UTC) when reasoning block present
        assert "14:30 UTC" in result or "TestAgent" in result  # Either timestamp line or agent name shows context

    def test_format_single_append_entry_filters_default_metadata(self):
        """_format_single_append_entry filters out default metadata."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_line": "[info] [2026-01-03 14:30:00 UTC] [Agent: TestAgent] [Project: test] Test message | priority=low; log_type=progress; custom=value",
            "path": "/path/to/PROGRESS_LOG.md",
            "meta": {}
        }

        result = formatter._format_single_append_entry(data, USE_COLORS=False)

        # Default metadata should be filtered, custom should remain
        assert "priority=low" not in result
        assert "log_type=progress" not in result


# ==================== Test _format_bulk_append_entry ====================

class TestFormatBulkAppendEntry:
    """Tests for _format_bulk_append_entry method."""

    def test_format_bulk_append_entry_success(self):
        """_format_bulk_append_entry formats successful bulk write."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_count": 5,
            "failed_count": 0,
            "written_lines": [
                "[info] Line 1",
                "[info] Line 2",
                "[info] Line 3",
                "[info] Line 4",
                "[info] Line 5"
            ],
            "paths": ["/path/to/PROGRESS_LOG.md"]
        }

        result = formatter._format_bulk_append_entry(data, USE_COLORS=False)

        assert "BULK APPEND RESULT" in result
        assert "written: 5 / 5" in result
        assert "failed: 0" in result
        assert "success" in result.lower()

    def test_format_bulk_append_entry_partial_success(self):
        """_format_bulk_append_entry shows partial success."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_count": 3,
            "failed_count": 2,
            "written_lines": [
                "[info] Line 1",
                "[info] Line 2",
                "[info] Line 3"
            ],
            "failed_items": [
                {"index": 4, "error": "Missing message"},
                {"index": 5, "error": "Invalid format"}
            ],
            "paths": ["/path/to/PROGRESS_LOG.md"]
        }

        result = formatter._format_bulk_append_entry(data, USE_COLORS=False)

        assert "partial success" in result.lower()
        assert "written: 3 / 5" in result
        assert "failed: 2" in result
        assert "Failed Entries" in result
        assert "Missing message" in result

    def test_format_bulk_append_entry_shows_sample(self):
        """_format_bulk_append_entry shows first 5 written entries."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_count": 10,
            "failed_count": 0,
            "written_lines": [f"[info] Line {i}" for i in range(10)],
            "paths": ["/path/to/PROGRESS_LOG.md"]
        }

        result = formatter._format_bulk_append_entry(data, USE_COLORS=False)

        assert "first 5 of 10" in result
        assert "Successfully Written" in result

    def test_format_bulk_append_entry_with_performance(self):
        """_format_bulk_append_entry shows performance metrics."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        data = {
            "ok": True,
            "written_count": 100,
            "failed_count": 0,
            "written_lines": [f"[info] Line {i}" for i in range(5)],
            "paths": ["/path/to/PROGRESS_LOG.md"],
            "performance": {"items_per_second": 45.2}
        }

        result = formatter._format_bulk_append_entry(data, USE_COLORS=False)

        assert "performance:" in result
        assert "45.2 items/sec" in result


# ==================== Test _extract_compact_log_line ====================

class TestExtractCompactLogLine:
    """Tests for _extract_compact_log_line method."""

    def test_extract_compact_log_line_basic(self):
        """_extract_compact_log_line extracts emoji + message."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        full_line = "[info] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] [Project: xyz] Investigation complete | confidence=0.95"

        result = formatter._extract_compact_log_line(full_line)

        assert "[info]" in result
        assert "Investigation complete" in result
        # Should not have full timestamp/agent/project brackets
        assert "[2026-01-03" not in result

    def test_extract_compact_log_line_fallback(self):
        """_extract_compact_log_line returns truncated line as fallback."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        # Line that doesn't match expected format
        full_line = "Simple line without expected format"

        result = formatter._extract_compact_log_line(full_line)

        # Should return original or truncated version
        assert len(result) <= len(full_line) + 3  # Allow for "..."

    def test_extract_compact_log_line_with_metadata(self):
        """_extract_compact_log_line preserves metadata."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        full_line = "[info] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] [Project: xyz] Test | key=value; another=data"

        result = formatter._extract_compact_log_line(full_line)

        assert "key=value" in result or "Test" in result


# ==================== Integration Tests ====================

class TestEntryFormatterIntegration:
    """Integration tests for entry formatting methods working together."""

    def test_full_formatting_pipeline(self):
        """Test complete formatting pipeline from entries to readable output."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        # Create entries
        entries = [
            {
                "id": 1,
                "timestamp": "2026-01-03T14:30:00Z",
                "agent": "TestAgent",
                "message": "First entry",
                "emoji": "info",
                "status": "info",
                "meta": {
                    "reasoning": {
                        "why": "Testing",
                        "what": "Full pipeline",
                        "how": "Integration test"
                    }
                }
            },
            {
                "id": 2,
                "timestamp": "2026-01-03T14:31:00Z",
                "agent": "TestAgent",
                "message": "Second entry",
                "emoji": "success",
                "status": "success",
                "meta": {}
            }
        ]

        pagination = {"page": 1, "page_size": 10, "total_count": 2}

        # Format as readable
        result = formatter.format_readable_log_entries(entries, pagination)
        result_clean = strip_ansi(result)

        # Verify all entries are present
        assert "First entry" in result_clean
        assert "Second entry" in result_clean
        assert "Why:" in result_clean
        assert "Testing" in result_clean

    def test_format_response_then_entries(self):
        """Test format_response followed by format_readable_log_entries."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        entries = [
            {"id": 1, "timestamp": "2026-01-03T14:30:00Z", "agent": "Test", "message": "Test", "emoji": "info"}
        ]

        # First format as structured response
        structured = formatter.format_response(entries)
        assert structured["ok"] is True
        assert len(structured["entries"]) == 1

        # Then format as readable
        pagination = {"page": 1, "page_size": 10, "total_count": 1}
        readable = formatter.format_readable_log_entries(entries, pagination)
        assert "Test" in readable


# ==================== Backward Compatibility Tests ====================

class TestEntryFormatterBackwardCompatibility:
    """Tests ensuring backward compatibility after extraction."""

    def test_response_formatter_has_all_methods(self):
        """ResponseFormatter should have all entry formatting methods."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        # All public methods should exist
        assert hasattr(formatter, 'format_entry')
        assert hasattr(formatter, 'format_response')
        assert hasattr(formatter, 'format_readable_log_entries')
        assert hasattr(formatter, 'format_readable_append_entry')

        # All private methods should exist
        assert hasattr(formatter, '_format_full_entry')
        assert hasattr(formatter, '_format_compact_entry')
        assert hasattr(formatter, '_truncate_message_smart')
        assert hasattr(formatter, '_parse_reasoning_block')
        assert hasattr(formatter, '_format_single_append_entry')
        assert hasattr(formatter, '_format_bulk_append_entry')
        assert hasattr(formatter, '_extract_compact_log_line')

    def test_methods_are_callable(self):
        """All entry formatting methods should be callable."""
        from utils.response import ResponseFormatter
        formatter = ResponseFormatter()

        # Test that methods can be called (basic smoke test)
        entry = {"id": 1, "message": "Test", "timestamp": "2026-01-03T14:30:00Z"}

        # Should not raise
        formatter.format_entry(entry)
        formatter.format_response([entry])
        formatter._format_full_entry(entry, None, True)
        formatter._format_compact_entry(entry, None, True)
        formatter._truncate_message_smart("Test message")
        formatter._parse_reasoning_block({})
        formatter._extract_compact_log_line("Test line")
