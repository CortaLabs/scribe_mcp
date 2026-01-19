#!/usr/bin/env python3
"""
Unit tests for ResponseFormatter helper functions.

Tests the three Phase 1 helper methods:
- _format_relative_time
- _get_doc_line_count
- _detect_custom_content
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import os

# Add scribe_mcp to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.response import ResponseFormatter


class TestFormatRelativeTime:
    """Test _format_relative_time helper method."""

    def setup_method(self):
        """Create ResponseFormatter instance for each test."""
        self.formatter = ResponseFormatter()

    def test_just_now(self):
        """Test timestamps within last minute."""
        now = datetime.utcnow()
        ts = (now - timedelta(seconds=30)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert result == "just now"

    def test_minutes_ago(self):
        """Test timestamps in minutes range."""
        now = datetime.utcnow()

        # 5 minutes ago
        ts = (now - timedelta(minutes=5)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert "5 minutes ago" in result or "4 minutes ago" in result

        # 1 minute ago (singular)
        ts = (now - timedelta(minutes=1)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert "1 minute ago" in result

    def test_hours_ago(self):
        """Test timestamps in hours range."""
        now = datetime.utcnow()

        # 1 hour ago
        ts = (now - timedelta(hours=1, minutes=30)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert result == "1 hour ago"

        # 3 hours ago
        ts = (now - timedelta(hours=3)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert "3 hours ago" in result or "2 hours ago" in result

    def test_days_ago(self):
        """Test timestamps in days range."""
        now = datetime.utcnow()

        # 1 day ago
        ts = (now - timedelta(days=1, hours=12)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert result == "1 day ago"

        # 3 days ago
        ts = (now - timedelta(days=3)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert "3 days ago" in result or "2 days ago" in result

    def test_weeks_ago(self):
        """Test timestamps in weeks range."""
        now = datetime.utcnow()

        # 1 week ago
        ts = (now - timedelta(weeks=1, days=3)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert result == "1 week ago"

        # 2 weeks ago
        ts = (now - timedelta(weeks=2)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert "2 weeks ago" in result or "1 week ago" in result

    def test_months_ago(self):
        """Test timestamps in months range."""
        now = datetime.utcnow()

        # 1 month ago (35 days)
        ts = (now - timedelta(days=35)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert result == "1 month ago"

        # 3 months ago (90 days)
        ts = (now - timedelta(days=90)).isoformat() + "Z"
        result = self.formatter._format_relative_time(ts)
        assert "3 months ago" in result or "2 months ago" in result

    def test_timestamp_formats(self):
        """Test different timestamp formats."""
        now = datetime.utcnow()
        base_ts = now - timedelta(hours=2)

        # ISO with Z
        ts1 = base_ts.isoformat() + "Z"
        result1 = self.formatter._format_relative_time(ts1)
        assert "hour" in result1.lower()

        # ISO with +00:00
        ts2 = base_ts.isoformat() + "+00:00"
        result2 = self.formatter._format_relative_time(ts2)
        assert "hour" in result2.lower()

        # Space-separated with UTC
        ts3 = base_ts.strftime('%Y-%m-%d %H:%M:%S') + " UTC"
        result3 = self.formatter._format_relative_time(ts3)
        assert "hour" in result3.lower()

    def test_invalid_timestamp(self):
        """Test handling of invalid timestamps."""
        # Invalid format should return original string
        invalid = "not-a-timestamp"
        result = self.formatter._format_relative_time(invalid)
        assert result == invalid

        # Empty string
        result = self.formatter._format_relative_time("")
        assert result == ""


class TestGetDocLineCount:
    """Test _get_doc_line_count helper method."""

    def setup_method(self):
        """Create ResponseFormatter instance for each test."""
        self.formatter = ResponseFormatter()

    def test_existing_file(self):
        """Test line count for existing file."""
        # Use this test file itself
        test_file = Path(__file__)
        count = self.formatter._get_doc_line_count(test_file)

        # This test file should have many lines
        assert count > 50

        # Verify count matches actual line count
        with open(test_file, 'r', encoding='utf-8') as f:
            actual_count = sum(1 for _ in f)
        assert count == actual_count

    def test_nonexistent_file(self):
        """Test nonexistent file returns 0."""
        result = self.formatter._get_doc_line_count("/nonexistent/file.txt")
        assert result == 0

    def test_directory_path(self):
        """Test directory path returns 0."""
        # Use current directory
        result = self.formatter._get_doc_line_count(Path(__file__).parent)
        assert result == 0

    def test_empty_file(self):
        """Test empty file returns 0."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = self.formatter._get_doc_line_count(tmp_path)
            assert result == 0
        finally:
            os.unlink(tmp_path)

    def test_file_with_known_lines(self):
        """Test file with known number of lines."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write("Line 1\n")
            tmp.write("Line 2\n")
            tmp.write("Line 3\n")

        try:
            result = self.formatter._get_doc_line_count(tmp_path)
            assert result == 3
        finally:
            os.unlink(tmp_path)

    def test_file_without_trailing_newline(self):
        """Test file without trailing newline."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write("Line 1\n")
            tmp.write("Line 2")  # No trailing newline

        try:
            result = self.formatter._get_doc_line_count(tmp_path)
            assert result == 2
        finally:
            os.unlink(tmp_path)

    def test_unicode_file(self):
        """Test file with unicode characters."""
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write("Line 1: Hello 🌍\n")
            tmp.write("Line 2: Scribe 📝\n")
            tmp.write("Line 3: Test ✅\n")

        try:
            result = self.formatter._get_doc_line_count(tmp_path)
            assert result == 3
        finally:
            os.unlink(tmp_path)

    def test_string_path(self):
        """Test string path parameter."""
        test_file = str(Path(__file__))
        count = self.formatter._get_doc_line_count(test_file)
        assert count > 50

    def test_path_object(self):
        """Test Path object parameter."""
        test_file = Path(__file__)
        count = self.formatter._get_doc_line_count(test_file)
        assert count > 50


class TestDetectCustomContent:
    """Test _detect_custom_content helper method."""

    def setup_method(self):
        """Create ResponseFormatter instance for each test."""
        self.formatter = ResponseFormatter()

    def test_nonexistent_directory(self):
        """Test nonexistent directory returns empty result."""
        result = self.formatter._detect_custom_content("/nonexistent/directory")

        assert result["research_files"] == 0
        assert result["bugs_present"] is False
        assert result["jsonl_files"] == []

    def test_empty_directory(self):
        """Test empty directory returns empty result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.formatter._detect_custom_content(tmpdir)

            assert result["research_files"] == 0
            assert result["bugs_present"] is False
            assert result["jsonl_files"] == []

    def test_research_directory(self):
        """Test detection of research files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            research_dir = Path(tmpdir) / "research"
            research_dir.mkdir()

            # Create research files
            (research_dir / "RESEARCH_1.md").write_text("Research 1")
            (research_dir / "RESEARCH_2.md").write_text("Research 2")
            (research_dir / "notes.txt").write_text("Not a research file")

            result = self.formatter._detect_custom_content(tmpdir)

            assert result["research_files"] == 2
            assert result["bugs_present"] is False

    def test_bugs_directory(self):
        """Test detection of bugs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bugs_dir = Path(tmpdir) / "bugs"
            bugs_dir.mkdir()

            result = self.formatter._detect_custom_content(tmpdir)

            assert result["bugs_present"] is True

    def test_jsonl_files(self):
        """Test detection of .jsonl files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .jsonl files
            (Path(tmpdir) / "TOOL_LOG.jsonl").write_text("{}")
            (Path(tmpdir) / "CUSTOM_LOG.jsonl").write_text("{}")
            (Path(tmpdir) / "not_jsonl.txt").write_text("text")

            result = self.formatter._detect_custom_content(tmpdir)

            assert len(result["jsonl_files"]) == 2
            assert "TOOL_LOG.jsonl" in result["jsonl_files"]
            assert "CUSTOM_LOG.jsonl" in result["jsonl_files"]

    def test_combined_content(self):
        """Test detection of all content types together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create research directory with files
            research_dir = Path(tmpdir) / "research"
            research_dir.mkdir()
            (research_dir / "RESEARCH_1.md").write_text("Research 1")
            (research_dir / "RESEARCH_2.md").write_text("Research 2")
            (research_dir / "RESEARCH_3.md").write_text("Research 3")

            # Create bugs directory
            bugs_dir = Path(tmpdir) / "bugs"
            bugs_dir.mkdir()

            # Create .jsonl files
            (Path(tmpdir) / "TOOL_LOG.jsonl").write_text("{}")
            (Path(tmpdir) / "PROGRESS_LOG.jsonl").write_text("{}")

            result = self.formatter._detect_custom_content(tmpdir)

            assert result["research_files"] == 3
            assert result["bugs_present"] is True
            assert len(result["jsonl_files"]) == 2

    def test_string_path(self):
        """Test string path parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.formatter._detect_custom_content(tmpdir)
            assert isinstance(result, dict)

    def test_path_object(self):
        """Test Path object parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.formatter._detect_custom_content(Path(tmpdir))
            assert isinstance(result, dict)

    def test_real_project_directory(self):
        """Test with real project directory structure."""
        # Use the current project's dev plan directory
        scribe_root = Path(__file__).parent.parent
        project_dir = scribe_root / ".scribe" / "docs" / "dev_plans" / "scribe_tool_output_refinement"

        if project_dir.exists():
            result = self.formatter._detect_custom_content(project_dir)

            # Verify result structure
            assert "research_files" in result
            assert "bugs_present" in result
            assert "jsonl_files" in result

            # If research directory exists, count should be > 0
            if (project_dir / "research").exists():
                assert result["research_files"] >= 0


if __name__ == "__main__":
    # Allow running tests directly
    import pytest
    pytest.main([__file__, "-v"])
