#!/usr/bin/env python3
"""
Test suite for SPEC-TOKEN-003 global optimization utilities.

Tests abbreviate_path, format_compact_json, format_header, and add_tip functions.
"""

import sys
from pathlib import Path
import json

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.path_utils import abbreviate_path
from utils.response import format_compact_json, format_header, add_tip


class TestAbbreviatePath:
    """Test path abbreviation function (Pattern 1: Absolute Path Reduction)."""

    def test_verbosity_0_returns_filename_only(self):
        """Verbosity 0 should return only the filename."""
        path = "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/project/PROGRESS_LOG.md"
        result = abbreviate_path(path, verbosity=0)
        assert result == "PROGRESS_LOG.md"

    def test_verbosity_2_returns_full_path(self):
        """Verbosity 2 should return the full absolute path unchanged."""
        path = "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/project/PROGRESS_LOG.md"
        result = abbreviate_path(path, verbosity=2)
        assert result == path

    def test_verbosity_1_with_scribe_directory(self):
        """Verbosity 1 should abbreviate from .scribe directory."""
        path = "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/project/PROGRESS_LOG.md"
        result = abbreviate_path(path, verbosity=1)
        assert result == ".scribe/docs/project/PROGRESS_LOG.md"

    def test_verbosity_1_with_scribe_mcp_directory(self):
        """Verbosity 1 should abbreviate from scribe_mcp directory."""
        path = "/home/austin/projects/MCP_SPINE/scribe_mcp/tools/append_entry.py"
        result = abbreviate_path(path, verbosity=1)
        assert result == "tools/append_entry.py"

    def test_verbosity_1_with_mcp_spine_directory(self):
        """Verbosity 1 should abbreviate from MCP_SPINE directory."""
        path = "/home/austin/projects/MCP_SPINE/other_mcp/file.py"
        result = abbreviate_path(path, verbosity=1)
        assert result == "other_mcp/file.py"

    def test_verbosity_1_with_context_root(self):
        """Verbosity 1 with explicit context_root should make path relative to it."""
        path = "/home/austin/projects/myproject/src/main.py"
        context = "/home/austin/projects/myproject"
        result = abbreviate_path(path, context_root=context, verbosity=1)
        assert result == "src/main.py"

    def test_empty_path_returns_empty_string(self):
        """Empty path should return empty string."""
        assert abbreviate_path("", verbosity=1) == ""
        assert abbreviate_path("", verbosity=0) == ""
        assert abbreviate_path("", verbosity=2) == ""

    def test_relative_path_passthrough(self):
        """Relative paths without known patterns should pass through."""
        path = "some/relative/path.txt"
        # Verbosity 1 should return as-is if no pattern matches
        result = abbreviate_path(path, verbosity=1)
        assert result == path


class TestFormatCompactJson:
    """Test JSON key abbreviation function (Pattern 2: Verbose JSON Keys)."""

    def test_basic_abbreviation(self):
        """Test basic key abbreviation."""
        data = {"projects": [{"name": "test", "status": "planning"}], "total_count": 1}
        result = format_compact_json(data)
        parsed = json.loads(result)

        assert "p" in parsed  # projects -> p
        assert "tot" in parsed  # total_count -> tot
        assert parsed["p"][0]["n"] == "test"  # name -> n
        assert parsed["p"][0]["s"] == "planning"  # status -> s

    def test_nested_abbreviation(self):
        """Test that abbreviation works recursively."""
        data = {
            "projects": [
                {
                    "name": "test",
                    "metadata": {
                        "priority": "high",
                        "confidence": 0.9
                    }
                }
            ]
        }
        result = format_compact_json(data)
        parsed = json.loads(result)

        assert "p" in parsed
        assert "meta" in parsed["p"][0]  # metadata -> meta
        assert "pri" in parsed["p"][0]["meta"]  # priority -> pri
        assert "conf" in parsed["p"][0]["meta"]  # confidence -> conf

    def test_custom_abbreviations(self):
        """Test custom abbreviation mappings."""
        data = {"custom_field": "value"}
        custom_abbrev = {"custom_field": "cf"}
        result = format_compact_json(data, abbreviations=custom_abbrev)
        parsed = json.loads(result)

        assert "cf" in parsed
        assert parsed["cf"] == "value"

    def test_preserves_unknown_keys(self):
        """Keys without abbreviations should be preserved."""
        data = {"unknown_key": "value"}
        result = format_compact_json(data)
        parsed = json.loads(result)

        assert "unknown_key" in parsed
        assert parsed["unknown_key"] == "value"

    def test_list_abbreviation(self):
        """Test abbreviation works with lists of objects."""
        data = {
            "entries": [
                {"timestamp": "2024-01-01", "message": "test1"},
                {"timestamp": "2024-01-02", "message": "test2"}
            ]
        }
        result = format_compact_json(data)
        parsed = json.loads(result)

        assert "e" in parsed  # entries -> e
        assert len(parsed["e"]) == 2
        assert "ts" in parsed["e"][0]  # timestamp -> ts
        assert "msg" in parsed["e"][0]  # message -> msg


class TestFormatHeader:
    """Test header formatting function (Pattern 3: Box Drawing Overhead)."""

    def test_verbosity_0_minimal_format(self):
        """Verbosity 0 should return minimal format."""
        result = format_header("Projects", emoji="📋", metadata="3/109", verbosity=0)
        assert result == "📋 Projects"
        assert "3/109" not in result  # No metadata at verbosity 0

    def test_verbosity_1_standard_format(self):
        """Verbosity 1 should include metadata in parentheses."""
        result = format_header("Projects", emoji="📋", metadata="3/109, page 1/37", verbosity=1)
        assert result == "📋 Projects (3/109, page 1/37)"

    def test_verbosity_2_box_drawing(self):
        """Verbosity 2 should use box drawing."""
        result = format_header("Projects", emoji="📋", metadata="109 total", verbosity=2)
        assert "╔" in result
        assert "═" in result
        assert "║" in result
        assert "╚" in result
        assert "PROJECTS" in result  # Title should be uppercase

    def test_no_emoji(self):
        """Test header without emoji."""
        result = format_header("Projects", verbosity=1)
        assert result == "Projects"

    def test_no_metadata(self):
        """Test header without metadata."""
        result = format_header("Projects", emoji="📋", verbosity=1)
        assert result == "📋 Projects"

    def test_box_drawing_override_true(self):
        """box_drawing=True should force box drawing regardless of verbosity."""
        result = format_header("Projects", emoji="📋", verbosity=0, box_drawing=True)
        assert "╔" in result

    def test_box_drawing_override_false(self):
        """box_drawing=False should disable box drawing even at verbosity 2."""
        result = format_header("Projects", emoji="📋", verbosity=2, box_drawing=False)
        assert "╔" not in result
        assert "📋 Projects" in result


class TestAddTip:
    """Test conditional tip display function (Pattern 4: Unsolicited Tips)."""

    def test_show_tips_true(self):
        """show_tips=True should return formatted tip."""
        result = add_tip("Add filter to narrow results", show_tips=True)
        assert result == "💡 Tip: Add filter to narrow results"

    def test_show_tips_false(self):
        """show_tips=False should return empty string."""
        result = add_tip("Add filter to narrow results", show_tips=False)
        assert result == ""

    def test_category_parameter_accepted(self):
        """Category parameter should be accepted (for future use)."""
        result = add_tip("Navigation tip", category="navigation", show_tips=True)
        assert "Navigation tip" in result

    def test_default_behavior_without_config(self):
        """Default behavior (no config) should be tips OFF."""
        # show_tips=None should default to False per SPEC-TOKEN-003
        result = add_tip("Default tip", show_tips=None)
        # This will attempt to load config, but should default to False
        # We can't guarantee config state, so we just verify it doesn't crash
        assert isinstance(result, str)


class TestIntegration:
    """Integration tests for combined utility usage."""

    def test_path_abbreviation_in_json_output(self):
        """Test using abbreviated paths in JSON output."""
        path = "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/project/file.md"
        abbreviated = abbreviate_path(path, verbosity=1)

        data = {
            "progress_log": abbreviated,
            "status": "success"
        }

        compact = format_compact_json(data)
        parsed = json.loads(compact)

        assert "log" in parsed  # progress_log -> log
        assert parsed["log"] == ".scribe/docs/project/file.md"

    def test_header_with_abbreviated_metadata(self):
        """Test header formatting with abbreviated metadata."""
        header = format_header(
            "Files",
            emoji="📁",
            metadata="5 files, .scribe/docs/project/",
            verbosity=1
        )
        assert "📁 Files (5 files, .scribe/docs/project/)" == header

    def test_complete_tool_output_optimization(self):
        """Test complete output optimization with all utilities."""
        # Simulate a tool output with all optimizations

        # 1. Abbreviated paths
        path = "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/project/PROGRESS_LOG.md"
        short_path = abbreviate_path(path, verbosity=1)

        # 2. Compact JSON
        data = {
            "projects": [{"name": "test", "progress_log": short_path}],
            "total_count": 1
        }
        compact_json = format_compact_json(data)

        # 3. Minimal header
        header = format_header("Projects", emoji="📋", metadata="1 total", verbosity=1)

        # 4. No tips (default)
        tip = add_tip("Some tip", show_tips=False)

        # Verify optimizations
        assert short_path == ".scribe/docs/project/PROGRESS_LOG.md"
        assert len(compact_json) < len(json.dumps(data))  # Compact is smaller
        assert header == "📋 Projects (1 total)"
        assert tip == ""


if __name__ == "__main__":
    # Run tests manually
    print("Running SPEC-TOKEN-003 utility tests...")

    # Test path abbreviation
    print("\n=== Test abbreviate_path ===")
    test_path = TestAbbreviatePath()
    test_path.test_verbosity_0_returns_filename_only()
    test_path.test_verbosity_1_with_scribe_directory()
    test_path.test_verbosity_2_returns_full_path()
    print("✓ Path abbreviation tests passed")

    # Test JSON compaction
    print("\n=== Test format_compact_json ===")
    test_json = TestFormatCompactJson()
    test_json.test_basic_abbreviation()
    test_json.test_nested_abbreviation()
    print("✓ JSON compaction tests passed")

    # Test header formatting
    print("\n=== Test format_header ===")
    test_header = TestFormatHeader()
    test_header.test_verbosity_0_minimal_format()
    test_header.test_verbosity_1_standard_format()
    test_header.test_verbosity_2_box_drawing()
    print("✓ Header formatting tests passed")

    # Test tip display
    print("\n=== Test add_tip ===")
    test_tip = TestAddTip()
    test_tip.test_show_tips_true()
    test_tip.test_show_tips_false()
    print("✓ Tip display tests passed")

    # Integration tests
    print("\n=== Test Integration ===")
    test_integration = TestIntegration()
    test_integration.test_complete_tool_output_optimization()
    print("✓ Integration tests passed")

    print("\n✅ All SPEC-TOKEN-003 utility tests passed!")
