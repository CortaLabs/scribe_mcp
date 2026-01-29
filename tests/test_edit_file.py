"""Tests for edit_file tool — replacement logic, diff generation, backup, read-before-edit."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure scribe_mcp is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from scribe_mcp.tools.edit_file import (
    ReplaceResult,
    _generate_diff,
    _perform_replacement,
)


# ---------------------------------------------------------------------------
# _perform_replacement tests
# ---------------------------------------------------------------------------


class TestPerformReplacement:
    """Unit tests for exact string replacement logic."""

    def test_replace_first_single_occurrence(self):
        content = "hello world"
        modified, result = _perform_replacement(content, "world", "earth", False)
        assert modified == "hello earth"
        assert result.occurrences_found == 1
        assert result.occurrences_replaced == 1
        assert result.lines_affected == [1]

    def test_replace_first_multiple_occurrences(self):
        content = "foo bar foo baz foo"
        modified, result = _perform_replacement(content, "foo", "qux", False)
        assert modified == "qux bar foo baz foo"
        assert result.occurrences_found == 3
        assert result.occurrences_replaced == 1
        assert result.lines_affected == [1]  # only first

    def test_replace_all(self):
        content = "foo bar foo baz foo"
        modified, result = _perform_replacement(content, "foo", "qux", True)
        assert modified == "qux bar qux baz qux"
        assert result.occurrences_found == 3
        assert result.occurrences_replaced == 3

    def test_not_found(self):
        content = "hello world"
        modified, result = _perform_replacement(content, "missing", "x", False)
        assert modified == content
        assert result.occurrences_found == 0
        assert result.occurrences_replaced == 0
        assert result.lines_affected == []

    def test_multiline_content(self):
        content = "line1\nline2 target\nline3\nline4 target"
        modified, result = _perform_replacement(content, "target", "replaced", True)
        assert "line2 replaced" in modified
        assert "line4 replaced" in modified
        assert result.occurrences_found == 2
        assert result.occurrences_replaced == 2
        assert result.lines_affected == [2, 4]

    def test_replace_first_multiline_tracks_first_line_only(self):
        content = "a target\nb target\nc target"
        modified, result = _perform_replacement(content, "target", "X", False)
        assert modified == "a X\nb target\nc target"
        assert result.lines_affected == [1]

    def test_empty_new_string_deletes(self):
        content = "remove_this rest"
        modified, result = _perform_replacement(content, "remove_this ", "", False)
        assert modified == "rest"
        assert result.occurrences_replaced == 1

    def test_multiline_old_string(self):
        content = "start\nold line 1\nold line 2\nend"
        old = "old line 1\nold line 2"
        modified, result = _perform_replacement(content, old, "new single line", False)
        assert modified == "start\nnew single line\nend"
        assert result.occurrences_found == 1


# ---------------------------------------------------------------------------
# _generate_diff tests
# ---------------------------------------------------------------------------


class TestGenerateDiff:
    """Unit tests for unified diff generation."""

    def test_basic_diff(self):
        original = "line1\nline2\nline3\n"
        modified = "line1\nline2_changed\nline3\n"
        diff = _generate_diff(original, modified, "test.py")
        assert "--- a/test.py" in diff
        assert "+++ b/test.py" in diff
        assert "-line2" in diff
        assert "+line2_changed" in diff

    def test_no_changes_empty_diff(self):
        content = "same\n"
        diff = _generate_diff(content, content, "test.py")
        assert diff == ""

    def test_addition_diff(self):
        original = "line1\nline3\n"
        modified = "line1\nline2\nline3\n"
        diff = _generate_diff(original, modified, "test.py")
        assert "+line2" in diff


# ---------------------------------------------------------------------------
# Integration-style tests (using tmp_path)
# ---------------------------------------------------------------------------


class TestEditFileBackup:
    """Test backup creation logic."""

    def test_backup_creates_file(self, tmp_path):
        from scribe_mcp.tools.edit_file import _backup_file

        # Create a source file
        src = tmp_path / "src" / "test.py"
        src.parent.mkdir(parents=True)
        src.write_text("original content")

        # Use tmp_path as repo_root
        backup_path = _backup_file(src, tmp_path)
        assert backup_path.exists()
        assert backup_path.read_text() == "original content"
        assert ".scribe/backups/" in str(backup_path)
        assert "test.py." in backup_path.name
        assert backup_path.name.endswith(".bak")
