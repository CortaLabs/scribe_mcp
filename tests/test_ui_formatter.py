"""Tests for utils/formatters/ui.py - UIFormatter class and standalone functions.

Phase 5 Task 5.1: UI Formatter extraction testing.
These tests verify that the extracted UIFormatter behaves identically
to the original ResponseFormatter methods.
"""

import pytest
from scribe_mcp.utils.formatters.ui import UIFormatter, format_header, add_tip


class TestUIFormatterLineNumbers:
    """Tests for UIFormatter.add_line_numbers method."""

    def test_basic_line_numbers(self):
        """Test basic line numbering."""
        ui = UIFormatter(use_colors=False)
        content = "line one\nline two\nline three"
        result = ui.add_line_numbers(content)

        assert "    1." in result
        assert "    2." in result
        assert "    3." in result
        assert "line one" in result
        assert "line two" in result
        assert "line three" in result

    def test_empty_content(self):
        """Test with empty content."""
        ui = UIFormatter(use_colors=False)
        assert ui.add_line_numbers("") == ""

    def test_single_line(self):
        """Test with single line."""
        ui = UIFormatter(use_colors=False)
        result = ui.add_line_numbers("single line")
        assert "    1." in result
        assert "single line" in result

    def test_start_offset(self):
        """Test with custom start line number."""
        ui = UIFormatter(use_colors=False)
        result = ui.add_line_numbers("a\nb\nc", start=10)
        assert "   10." in result
        assert "   11." in result
        assert "   12." in result

    def test_large_line_numbers(self):
        """Test padding with large line numbers."""
        ui = UIFormatter(use_colors=False)
        # 100 lines starting at 1
        content = "\n".join([f"line {i}" for i in range(100)])
        result = ui.add_line_numbers(content)
        # Should have 3-digit padding (100 lines)
        assert "  100." in result

    def test_colors_enabled(self):
        """Test that ANSI colors are included when enabled."""
        ui = UIFormatter(use_colors=True)
        result = ui.add_line_numbers("test")
        # Should contain ANSI green code
        assert "\033[32m" in result
        assert "\033[0m" in result

    def test_colors_disabled(self):
        """Test that ANSI colors are not included when disabled."""
        ui = UIFormatter(use_colors=False)
        result = ui.add_line_numbers("test")
        # Should not contain ANSI codes
        assert "\033[" not in result


class TestUIFormatterHeaderBox:
    """Tests for UIFormatter.create_header_box method."""

    def test_basic_header_box(self):
        """Test basic header box creation."""
        ui = UIFormatter(use_colors=False)
        result = ui.create_header_box("Test Title", {"key1": "value1"})

        # Check box characters
        assert "\u2554" in result  # Top-left corner
        assert "\u2557" in result  # Top-right corner
        assert "\u255a" in result  # Bottom-left corner
        assert "\u255d" in result  # Bottom-right corner
        assert "Test Title" in result
        assert "key1:" in result
        assert "value1" in result

    def test_header_box_multiple_metadata(self):
        """Test header box with multiple metadata entries."""
        ui = UIFormatter(use_colors=False)
        metadata = {"status": "active", "count": 42, "mode": "test"}
        result = ui.create_header_box("Dashboard", metadata)

        assert "Dashboard" in result
        assert "status:" in result
        assert "active" in result
        assert "count:" in result
        assert "42" in result

    def test_header_box_dict_value(self):
        """Test header box with dict value (should be JSON serialized)."""
        ui = UIFormatter(use_colors=False)
        result = ui.create_header_box("Title", {"data": {"nested": "value"}})
        assert '{"nested": "value"}' in result or '"nested"' in result

    def test_header_box_long_value_truncation(self):
        """Test that long values are truncated."""
        ui = UIFormatter(use_colors=False)
        long_value = "x" * 200
        result = ui.create_header_box("Title", {"long": long_value})
        # Should be truncated with ...
        assert "..." in result


class TestUIFormatterFooterBox:
    """Tests for UIFormatter.create_footer_box method."""

    def test_basic_footer_box(self):
        """Test basic footer box creation."""
        ui = UIFormatter(use_colors=False)
        result = ui.create_footer_box({"path": "/test/path", "size": "1.5KB"})

        assert "METADATA" in result
        assert "path:" in result
        assert "/test/path" in result
        assert "size:" in result

    def test_footer_box_with_reminders(self):
        """Test footer box with reminders section."""
        ui = UIFormatter(use_colors=False)
        reminders = [
            {"emoji": "\ud83d\udca1", "message": "Remember to save"},
            {"emoji": "\u26a0\ufe0f", "message": "Check your settings"}
        ]
        result = ui.create_footer_box({"status": "ok"}, reminders=reminders)

        assert "REMINDERS" in result
        assert "Remember to save" in result
        assert "Check your settings" in result

    def test_footer_box_no_reminders(self):
        """Test footer box without reminders."""
        ui = UIFormatter(use_colors=False)
        result = ui.create_footer_box({"key": "value"})

        # Should not have REMINDERS section
        assert result.count("REMINDERS") == 0


class TestUIFormatterTable:
    """Tests for UIFormatter.format_table method."""

    def test_basic_table(self):
        """Test basic table creation."""
        ui = UIFormatter(use_colors=False)
        headers = ["Name", "Value"]
        rows = [["foo", "bar"], ["baz", "qux"]]
        result = ui.format_table(headers, rows)

        # Check table characters
        assert "\u250c" in result  # Top-left
        assert "\u2510" in result  # Top-right
        assert "\u2514" in result  # Bottom-left
        assert "\u2518" in result  # Bottom-right
        assert "\u2502" in result  # Vertical
        assert "\u2500" in result  # Horizontal
        assert "Name" in result
        assert "Value" in result
        assert "foo" in result
        assert "bar" in result

    def test_empty_table(self):
        """Test with empty input."""
        ui = UIFormatter(use_colors=False)
        assert ui.format_table([], []) == ""
        assert ui.format_table(["A"], []) == ""

    def test_table_alignment(self):
        """Test that columns are properly aligned."""
        ui = UIFormatter(use_colors=False)
        headers = ["Short", "LongHeader"]
        rows = [["x", "y"], ["longer", "z"]]
        result = ui.format_table(headers, rows)

        # Headers and cells should be padded
        lines = result.split("\n")
        # All data rows should have same length
        assert len(lines[1]) == len(lines[3])

    def test_table_with_varying_row_lengths(self):
        """Test table with rows of different lengths."""
        ui = UIFormatter(use_colors=False)
        headers = ["A", "B", "C"]
        rows = [["1", "2"], ["x", "y", "z"]]  # First row missing column
        result = ui.format_table(headers, rows)

        # Should handle gracefully
        assert "A" in result
        assert "B" in result
        assert "C" in result


class TestFormatHeader:
    """Tests for format_header standalone function."""

    def test_verbosity_0_minimal(self):
        """Test minimal format with verbosity 0."""
        result = format_header("Projects", emoji="\ud83d\udccb", metadata="10 total", verbosity=0)
        assert result == "\ud83d\udccb Projects"

    def test_verbosity_1_standard(self):
        """Test standard format with verbosity 1."""
        result = format_header("Projects", emoji="\ud83d\udccb", metadata="10 total", verbosity=1)
        assert result == "\ud83d\udccb Projects (10 total)"

    def test_verbosity_2_box(self):
        """Test box drawing with verbosity 2."""
        result = format_header("Projects", emoji="\ud83d\udccb", metadata="10 total", verbosity=2)
        # Should have box characters
        assert "\u2554" in result
        assert "\u2550" in result
        assert "\u255d" in result
        assert "PROJECTS" in result  # Title should be uppercase

    def test_no_emoji(self):
        """Test without emoji."""
        result = format_header("Title", verbosity=0)
        assert result == "Title"

    def test_no_metadata(self):
        """Test without metadata."""
        result = format_header("Title", emoji="\ud83d\udc4d", verbosity=1)
        assert result == "\ud83d\udc4d Title"

    def test_box_drawing_override_true(self):
        """Test forcing box drawing with override."""
        result = format_header("Test", verbosity=0, box_drawing=True)
        assert "\u2554" in result

    def test_box_drawing_override_false(self):
        """Test disabling box drawing with override."""
        result = format_header("Test", verbosity=2, box_drawing=False)
        assert "\u2554" not in result


class TestAddTip:
    """Tests for add_tip standalone function."""

    def test_show_tips_true(self):
        """Test tip display when enabled."""
        result = add_tip("Use filter to narrow results", show_tips=True)
        assert result == "\U0001f4a1 Tip: Use filter to narrow results"

    def test_show_tips_false(self):
        """Test tip hidden when disabled."""
        result = add_tip("Some tip", show_tips=False)
        assert result == ""

    def test_category_accepted(self):
        """Test that category parameter is accepted (for future use)."""
        # Should not raise
        result = add_tip("Tip text", category="navigation", show_tips=True)
        assert "\U0001f4a1 Tip:" in result


class TestUIFormatterColorToggle:
    """Tests for UIFormatter color toggle functionality."""

    def test_use_colors_property_getter(self):
        """Test getting use_colors property."""
        ui = UIFormatter(use_colors=True)
        assert ui.use_colors is True

        ui2 = UIFormatter(use_colors=False)
        assert ui2.use_colors is False

    def test_use_colors_property_setter(self):
        """Test setting use_colors property."""
        ui = UIFormatter(use_colors=False)
        ui.use_colors = True
        assert ui.use_colors is True

        # Verify it affects output
        result_with_colors = ui.add_line_numbers("test")
        assert "\033[32m" in result_with_colors

        ui.use_colors = False
        result_without_colors = ui.add_line_numbers("test")
        assert "\033[32m" not in result_without_colors

    def test_default_colors_from_config(self):
        """Test that colors are auto-detected from config.

        Since Phase 5 Task 5.2, UIFormatter inherits from BaseFormatter
        which auto-detects colors from config. The value depends on
        the .scribe/config/scribe.yaml setting (use_ansi_colors).
        """
        ui = UIFormatter()
        # use_colors should be a boolean (auto-detected from config)
        assert isinstance(ui.use_colors, bool)

    def test_explicit_colors_override(self):
        """Test that explicit use_colors parameter overrides auto-detect."""
        ui_with_colors = UIFormatter(use_colors=True)
        assert ui_with_colors.use_colors is True

        ui_without_colors = UIFormatter(use_colors=False)
        assert ui_without_colors.use_colors is False


class TestUIFormatterAnsiConstants:
    """Tests to verify ANSI constants are present."""

    def test_ansi_constants_defined(self):
        """Test that ANSI constants are defined on the class."""
        assert hasattr(UIFormatter, 'ANSI_CYAN')
        assert hasattr(UIFormatter, 'ANSI_GREEN')
        assert hasattr(UIFormatter, 'ANSI_YELLOW')
        assert hasattr(UIFormatter, 'ANSI_BLUE')
        assert hasattr(UIFormatter, 'ANSI_MAGENTA')
        assert hasattr(UIFormatter, 'ANSI_BOLD')
        assert hasattr(UIFormatter, 'ANSI_DIM')
        assert hasattr(UIFormatter, 'ANSI_RESET')

    def test_ansi_constants_values(self):
        """Test ANSI constant values are correct."""
        assert UIFormatter.ANSI_GREEN == "\033[32m"
        assert UIFormatter.ANSI_CYAN == "\033[36m"
        assert UIFormatter.ANSI_RESET == "\033[0m"
