#!/usr/bin/env python3
"""
Comprehensive tests for format_project_context() formatter method.

Tests Phase 3 implementation: "Where am I?" context hydration with:
- Full message display (NO truncation!)
- Timestamp parsing (ISO and UTC formats)
- Footer hint when showing < 5 entries
- Missing documents handling
- Edge cases
"""

import sys
from pathlib import Path

# Add scribe_mcp to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from utils.response import ResponseFormatter


class TestFormatProjectContext:
    """Test suite for format_project_context() method."""

    @pytest.fixture
    def formatter(self):
        """Create ResponseFormatter instance for testing."""
        return ResponseFormatter()

    @pytest.fixture
    def sample_project(self):
        """Sample project data."""
        return {
            "name": "scribe_tool_output_refinement",
            "root": "/home/austin/projects/MCP_SPINE/scribe_mcp",
            "progress_log": "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/scribe_tool_output_refinement/PROGRESS_LOG.md"
        }

    @pytest.fixture
    def sample_docs_info(self):
        """Sample document info."""
        return {
            "architecture": {"exists": True, "lines": 1274},
            "phase_plan": {"exists": True, "lines": 542},
            "checklist": {"exists": True, "lines": 356},
            "progress": {"exists": True, "entries": 298}
        }

    @pytest.fixture
    def sample_activity(self):
        """Sample activity data."""
        return {
            "status": "in_progress",
            "total_entries": 298,
            "last_entry_at": "2026-01-03T08:15:30Z"
        }

    @pytest.fixture
    def sample_entries_5(self):
        """Sample with 5 recent entries (full set)."""
        return [
            {
                "timestamp": "2026-01-03T09:53:42Z",
                "emoji": "🧭",
                "agent": "Orchestrator",
                "message": "Refined approach: Use existing format parameter in list_projects tool instead of creating new tool"
            },
            {
                "timestamp": "2026-01-03 09:48:15 UTC",
                "emoji": "🧭",
                "agent": "Orchestrator",
                "message": "Code audit complete: list_projects returns massive JSON blob - must add context hydration"
            },
            {
                "ts": "2026-01-03T09:45:00Z",
                "emoji": "🧭",
                "agent": "Orchestrator",
                "message": "Planning session started: Phase 4 continuation after test fixes"
            },
            {
                "timestamp": "2026-01-03T05:24:18Z",
                "emoji": "✅",
                "agent": "Orchestrator",
                "message": "Fixed test_query_priority_filters.py - Root cause was default priority filtering in query_entries"
            },
            {
                "timestamp": "2026-01-03T05:18:42Z",
                "emoji": "⚠️",
                "agent": "Orchestrator",
                "message": "Batch 3 Complete (with test issues) - 5 tests passing, 1 failing (investigating)"
            }
        ]

    @pytest.fixture
    def sample_entries_2(self):
        """Sample with 2 recent entries (fewer than 5)."""
        return [
            {
                "timestamp": "2026-01-03T09:53:42Z",
                "emoji": "🧭",
                "agent": "Orchestrator",
                "message": "Refined approach: Use existing format parameter"
            },
            {
                "timestamp": "2026-01-03 09:48:15 UTC",
                "emoji": "🧭",
                "agent": "Orchestrator",
                "message": "Code audit complete"
            }
        ]

    def test_with_5_entries(self, formatter, sample_project, sample_docs_info, sample_activity, sample_entries_5):
        """Test with 5 recent entries - should show all without hint."""
        result = formatter.format_project_context(
            sample_project,
            sample_entries_5,
            sample_docs_info,
            sample_activity
        )

        # Verify project name in header
        assert "scribe_tool_output_refinement" in result

        # Verify all 5 entries displayed
        assert "    1." in result
        assert "    2." in result
        assert "    3." in result
        assert "    4." in result
        assert "    5." in result

        # Verify NO truncation of messages (full messages present)
        assert "Refined approach: Use existing format parameter in list_projects tool instead of creating new tool" in result
        assert "Code audit complete: list_projects returns massive JSON blob - must add context hydration" in result

        # Verify NO hint when showing 5 entries
        assert "💡 Use read_recent(limit=20) for more entries" not in result

    def test_with_fewer_than_5_entries(self, formatter, sample_project, sample_docs_info, sample_activity, sample_entries_2):
        """Test with 2 recent entries - should show all and display hint."""
        result = formatter.format_project_context(
            sample_project,
            sample_entries_2,
            sample_docs_info,
            sample_activity
        )

        # Verify only 2 entries displayed
        assert "    1." in result
        assert "    2." in result
        assert "    3." not in result

        # Verify full messages (no truncation!)
        assert "Refined approach: Use existing format parameter" in result
        assert "Code audit complete" in result

        # Verify hint appears
        assert "💡 Use read_recent(limit=20) for more entries" in result

    def test_with_no_entries(self, formatter, sample_project, sample_docs_info, sample_activity):
        """Test with no recent entries - should show "No entries yet"."""
        result = formatter.format_project_context(
            sample_project,
            [],
            sample_docs_info,
            sample_activity
        )

        # Verify "no entries" message
        assert "No entries yet - new project" in result

        # Verify NO hint
        assert "💡 Use read_recent(limit=20) for more entries" not in result

    def test_timestamp_parsing_iso_format(self, formatter, sample_project, sample_docs_info, sample_activity):
        """Test timestamp parsing for ISO format (YYYY-MM-DDTHH:MM:SSZ)."""
        entries = [
            {
                "timestamp": "2026-01-03T15:42:37.123456Z",
                "emoji": "✅",
                "agent": "Test",
                "message": "Test message"
            }
        ]

        result = formatter.format_project_context(
            sample_project,
            entries,
            sample_docs_info,
            sample_activity
        )

        # Verify timestamp formatted as HH:MM (no seconds)
        assert "15:42" in result
        assert "15:42:37" not in result  # No seconds

    def test_timestamp_parsing_utc_format(self, formatter, sample_project, sample_docs_info, sample_activity):
        """Test timestamp parsing for UTC format (YYYY-MM-DD HH:MM:SS UTC)."""
        entries = [
            {
                "timestamp": "2026-01-03 14:30:45 UTC",
                "emoji": "✅",
                "agent": "Test",
                "message": "Test message"
            }
        ]

        result = formatter.format_project_context(
            sample_project,
            entries,
            sample_docs_info,
            sample_activity
        )

        # Verify timestamp formatted as HH:MM (no seconds)
        assert "14:30" in result
        assert "14:30:45" not in result  # No seconds

    def test_with_long_messages_no_truncation(self, formatter, sample_project, sample_docs_info, sample_activity):
        """Test with very long messages - CRITICAL: must NOT truncate!"""
        long_message = "This is a very long message that goes on and on with lots of detail about what was done and why and how it was implemented and what the results were and what the next steps should be"

        entries = [
            {
                "timestamp": "2026-01-03T10:00:00Z",
                "emoji": "✅",
                "agent": "Test",
                "message": long_message
            }
        ]

        result = formatter.format_project_context(
            sample_project,
            entries,
            sample_docs_info,
            sample_activity
        )

        # CRITICAL: Full message must be present (NO truncation!)
        assert long_message in result
        assert "..." not in result.split(long_message)[1].split("\n")[0]  # No ellipsis after message

    def test_with_missing_docs(self, formatter, sample_project, sample_activity, sample_entries_2):
        """Test with some documents missing - should skip them."""
        docs_info = {
            "architecture": {"exists": True, "lines": 1274},
            "phase_plan": {"exists": False, "lines": 0},  # Missing
            "checklist": {"exists": True, "lines": 356},
            "progress": {"exists": True, "entries": 298}
        }

        result = formatter.format_project_context(
            sample_project,
            sample_entries_2,
            docs_info,
            sample_activity
        )

        # Verify existing docs shown
        assert "ARCHITECTURE_GUIDE.md" in result
        assert "CHECKLIST.md" in result
        assert "PROGRESS_LOG.md" in result

        # Verify missing doc NOT shown
        assert "PHASE_PLAN.md" not in result

    def test_agent_name_truncation(self, formatter, sample_project, sample_docs_info, sample_activity):
        """Test that very long agent names get truncated."""
        entries = [
            {
                "timestamp": "2026-01-03T10:00:00Z",
                "emoji": "✅",
                "agent": "VeryLongAgentNameThatExceedsFifteenCharacters",
                "message": "Test message"
            }
        ]

        result = formatter.format_project_context(
            sample_project,
            entries,
            sample_docs_info,
            sample_activity
        )

        # Verify agent name truncated to 15 chars (12 + "...")
        assert "VeryLongAgen..." in result
        assert "VeryLongAgentNameThatExceedsFifteenCharacters" not in result

    def test_location_section_dev_plan_path(self, formatter, sample_project, sample_docs_info, sample_activity, sample_entries_2):
        """Test that dev plan path is properly extracted and made relative."""
        result = formatter.format_project_context(
            sample_project,
            sample_entries_2,
            sample_docs_info,
            sample_activity
        )

        # Verify location section exists
        assert "📂 Location:" in result
        assert "Root:" in result

        # Verify dev plan path is relative
        assert "Dev Plan:" in result
        assert ".scribe/docs/dev_plans/scribe_tool_output_refinement/" in result

    def test_footer_status_with_timestamp(self, formatter, sample_project, sample_docs_info, sample_entries_2):
        """Test footer status line with timestamp (uses relative time)."""
        activity = {
            "status": "in_progress",
            "total_entries": 298,
            "last_entry_at": "2026-01-03T08:15:30Z"
        }

        result = formatter.format_project_context(
            sample_project,
            sample_entries_2,
            sample_docs_info,
            activity
        )

        # Verify footer line exists
        assert "⏰ Status: in_progress" in result
        assert "Entries: 298" in result
        assert "Last:" in result  # Relative time will vary

    def test_footer_status_without_timestamp(self, formatter, sample_project, sample_docs_info, sample_entries_2):
        """Test footer status line without timestamp."""
        activity = {
            "status": "planning",
            "total_entries": 5,
            "last_entry_at": ""  # No timestamp
        }

        result = formatter.format_project_context(
            sample_project,
            sample_entries_2,
            sample_docs_info,
            activity
        )

        # Verify footer line exists without "Last:"
        assert "⏰ Status: planning" in result
        assert "Entries: 5" in result
        assert "Last:" not in result

    def test_document_counts_display(self, formatter, sample_project, sample_activity, sample_entries_2):
        """Test that document line/entry counts are displayed correctly."""
        docs_info = {
            "architecture": {"exists": True, "lines": 1500},
            "phase_plan": {"exists": True, "lines": 800},
            "checklist": {"exists": True, "lines": 400},
            "progress": {"exists": True, "entries": 500}
        }

        result = formatter.format_project_context(
            sample_project,
            sample_entries_2,
            docs_info,
            sample_activity
        )

        # Verify counts displayed
        assert "ARCHITECTURE_GUIDE.md (1500 lines)" in result
        assert "PHASE_PLAN.md (800 lines)" in result
        assert "CHECKLIST.md (400 lines)" in result
        assert "PROGRESS_LOG.md (500 entries)" in result

    def test_header_box_formatting(self, formatter, sample_project, sample_docs_info, sample_activity, sample_entries_2):
        """Test that header box is properly formatted."""
        result = formatter.format_project_context(
            sample_project,
            sample_entries_2,
            sample_docs_info,
            sample_activity
        )

        # Verify box characters present (may have ANSI codes)
        assert "╔" in result
        assert "╚" in result
        assert "║" in result
        assert "═" in result
        assert "🎯 CURRENT PROJECT:" in result

    def test_emoji_display_in_entries(self, formatter, sample_project, sample_docs_info, sample_activity):
        """Test that emojis are properly displayed in entries."""
        entries = [
            {"timestamp": "2026-01-03T10:00:00Z", "emoji": "✅", "agent": "Test1", "message": "Success"},
            {"timestamp": "2026-01-03T09:00:00Z", "emoji": "⚠️", "agent": "Test2", "message": "Warning"},
            {"timestamp": "2026-01-03T08:00:00Z", "emoji": "🐞", "agent": "Test3", "message": "Bug"}
        ]

        result = formatter.format_project_context(
            sample_project,
            entries,
            sample_docs_info,
            sample_activity
        )

        # Verify emojis present in brackets
        assert "[✅]" in result
        assert "[⚠️]" in result
        assert "[🐞]" in result

    def test_default_emoji_when_missing(self, formatter, sample_project, sample_docs_info, sample_activity):
        """Test that default emoji (ℹ️) is used when emoji field missing."""
        entries = [
            {
                "timestamp": "2026-01-03T10:00:00Z",
                # No emoji field
                "agent": "Test",
                "message": "Test message"
            }
        ]

        result = formatter.format_project_context(
            sample_project,
            entries,
            sample_docs_info,
            sample_activity
        )

        # Verify default emoji used
        assert "[ℹ️]" in result


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v"])
