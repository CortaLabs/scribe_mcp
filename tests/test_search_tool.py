"""Tests for tools/search.py Phase 2 features: context lines, multiline, binary detection."""

import re
import tempfile
import textwrap
from pathlib import Path

import pytest

# Import internals directly for unit testing
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.search import (
    Match,
    FileResult,
    TraversalStats,
    _is_binary_content,
    _is_binary_extension,
    _search_file,
    _search_file_multiline,
    _build_structured_result,
    _format_search_readable,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_file(tmp_path):
    """Create a sample Python file for testing."""
    content = textwrap.dedent("""\
        import os
        import sys

        def hello():
            print("hello world")

        def goodbye():
            print("goodbye world")

        class MyClass:
            def method_one(self):
                return 1

            def method_two(self):
                return 2

        if __name__ == "__main__":
            hello()
            goodbye()
    """)
    f = tmp_path / "sample.py"
    f.write_text(content)
    return f


@pytest.fixture
def binary_file(tmp_path):
    """Create a file with null bytes (binary content)."""
    f = tmp_path / "binary.dat"
    f.write_bytes(b"header\x00\x01\x02binary content\x00")
    return f


@pytest.fixture
def text_file_no_nulls(tmp_path):
    """Create a plain text file without null bytes."""
    f = tmp_path / "plain.txt"
    f.write_text("just plain text\nno nulls here\n")
    return f


# ---------------------------------------------------------------------------
# Task 2.1: Context Lines
# ---------------------------------------------------------------------------

class TestContextLines:
    def test_no_context(self, sample_file):
        """Without context, matches have empty context lists."""
        pat = re.compile(r"def hello")
        matches = _search_file(sample_file, pat, before=0, after=0)
        assert len(matches) == 1
        assert matches[0].line_number == 4
        assert matches[0].context_before == []
        assert matches[0].context_after == []

    def test_before_context(self, sample_file):
        """Before context returns N lines before the match."""
        pat = re.compile(r"def hello")
        matches = _search_file(sample_file, pat, before=2, after=0)
        assert len(matches) == 1
        m = matches[0]
        assert m.line_number == 4
        assert len(m.context_before) == 2
        # Lines 2 and 3 (import sys, empty line)
        assert "import sys" in m.context_before[0]
        assert m.context_after == []

    def test_after_context(self, sample_file):
        """After context returns N lines after the match."""
        pat = re.compile(r"def hello")
        matches = _search_file(sample_file, pat, before=0, after=2)
        assert len(matches) == 1
        m = matches[0]
        assert len(m.context_after) == 2
        assert 'print("hello world")' in m.context_after[0]

    def test_both_context(self, sample_file):
        """Both before and after context."""
        pat = re.compile(r"def goodbye")
        matches = _search_file(sample_file, pat, before=1, after=1)
        assert len(matches) == 1
        m = matches[0]
        assert len(m.context_before) == 1
        assert len(m.context_after) == 1

    def test_context_at_file_start(self, sample_file):
        """Context at start of file doesn't underflow."""
        pat = re.compile(r"import os")
        matches = _search_file(sample_file, pat, before=5, after=0)
        assert len(matches) == 1
        assert matches[0].context_before == []  # Line 1, no lines before

    def test_context_at_file_end(self, sample_file):
        """Context at end of file doesn't overflow."""
        pat = re.compile(r"if __name__")
        matches = _search_file(sample_file, pat, before=0, after=10)
        assert len(matches) == 1
        # Should get however many lines are left (2: hello() and goodbye()), not crash
        assert len(matches[0].context_after) <= 10
        assert len(matches[0].context_after) >= 1

    def test_multiple_matches_with_context(self, sample_file):
        """Multiple matches each get their own context."""
        pat = re.compile(r"def \w+")
        matches = _search_file(sample_file, pat, before=1, after=1)
        assert len(matches) >= 3  # hello, goodbye, method_one, method_two
        for m in matches:
            # Each match should have context (except possibly first/last)
            assert isinstance(m.context_before, list)
            assert isinstance(m.context_after, list)


# ---------------------------------------------------------------------------
# Task 2.2: Multiline Search
# ---------------------------------------------------------------------------

class TestMultilineSearch:
    def test_multiline_pattern(self, tmp_path):
        """Pattern spanning multiple lines."""
        content = "def foo():\n    return 42\n\ndef bar():\n    return 99\n"
        f = tmp_path / "multi.py"
        f.write_text(content)

        pat = re.compile(r"def foo\(\):\n\s+return 42", re.DOTALL | re.MULTILINE)
        matches = _search_file_multiline(f, pat)
        assert len(matches) == 1
        assert matches[0].line_number == 1
        assert "+1 lines" in matches[0].line  # indicates multi-line match

    def test_multiline_single_line_match(self, tmp_path):
        """Multiline search still works for single-line patterns."""
        content = "hello\nworld\nfoo\n"
        f = tmp_path / "simple.txt"
        f.write_text(content)

        pat = re.compile(r"world")
        matches = _search_file_multiline(f, pat)
        assert len(matches) == 1
        assert matches[0].line_number == 2
        assert matches[0].line == "world"

    def test_multiline_max_matches(self, tmp_path):
        """Multiline search respects max_matches."""
        content = "a\nb\nc\nd\ne\n"
        f = tmp_path / "letters.txt"
        f.write_text(content)

        pat = re.compile(r"\w")
        matches = _search_file_multiline(f, pat, max_matches=2)
        assert len(matches) == 2

    def test_multiline_no_match(self, tmp_path):
        """No matches returns empty list."""
        f = tmp_path / "empty_match.txt"
        f.write_text("nothing here\n")

        pat = re.compile(r"class\s+\w+.*:\n.*def", re.DOTALL | re.MULTILINE)
        matches = _search_file_multiline(f, pat)
        assert matches == []


# ---------------------------------------------------------------------------
# Task 2.3: Binary Detection
# ---------------------------------------------------------------------------

class TestBinaryDetection:
    def test_binary_content_detected(self, binary_file):
        assert _is_binary_content(binary_file) is True

    def test_text_not_detected_as_binary(self, text_file_no_nulls):
        assert _is_binary_content(text_file_no_nulls) is False

    def test_binary_extension(self):
        assert _is_binary_extension(Path("image.png")) is True
        assert _is_binary_extension(Path("code.py")) is False
        assert _is_binary_extension(Path("data.sqlite")) is True

    def test_nonexistent_file(self, tmp_path):
        """Non-existent file returns False (not binary)."""
        assert _is_binary_content(tmp_path / "nope.txt") is False


# ---------------------------------------------------------------------------
# TraversalStats
# ---------------------------------------------------------------------------

class TestTraversalStats:
    def test_skip_stats_in_structured_result(self):
        stats = TraversalStats(skipped_binary=3, skipped_size=1, skipped_denied=0)
        result = _build_structured_result(
            results=[], output_mode="content", pattern="test",
            files_searched=10, total_matches=0, line_numbers=True,
            traversal_stats=stats,
        )
        assert result["files_skipped"] == 4
        assert result["skip_details"]["binary"] == 3
        assert result["skip_details"]["too_large"] == 1
        assert "denied" not in result["skip_details"]

    def test_no_stats_when_nothing_skipped(self):
        stats = TraversalStats()
        result = _build_structured_result(
            results=[], output_mode="content", pattern="test",
            files_searched=10, total_matches=0, line_numbers=True,
            traversal_stats=stats,
        )
        assert "files_skipped" not in result


# ---------------------------------------------------------------------------
# Readable formatting
# ---------------------------------------------------------------------------

class TestReadableFormatting:
    def test_header_format(self):
        data = {
            "ok": True, "output_mode": "content", "pattern": "foo",
            "files_searched": 5, "files_with_matches": 2, "total_matches": 3,
            "matches": [],
        }
        text = _format_search_readable(data, line_numbers=True)
        assert "SEARCH RESULTS" in text
        assert "pattern: foo" in text
        assert "matches: 3 in 2 files" in text

    def test_skip_info_displayed(self):
        data = {
            "ok": True, "output_mode": "content", "pattern": "x",
            "files_searched": 10, "files_with_matches": 0, "total_matches": 0,
            "files_skipped": 5, "skip_details": {"binary": 3, "too_large": 2},
            "matches": [],
        }
        text = _format_search_readable(data, line_numbers=True)
        assert "Files skipped: 5" in text
        assert "binary=3" in text
        assert "too_large=2" in text

    def test_separator_style(self):
        """Output uses box-drawing characters for separators."""
        data = {
            "ok": True, "output_mode": "content", "pattern": "x",
            "files_searched": 1, "files_with_matches": 1, "total_matches": 1,
            "matches": [{"file": "test.py", "matches": [{"line_number": 1, "line": "x = 1"}]}],
        }
        text = _format_search_readable(data, line_numbers=True)
        assert "\u2500" in text  # Box-drawing horizontal line

    def test_context_lines_in_readable(self):
        data = {
            "ok": True, "output_mode": "content", "pattern": "target",
            "files_searched": 1, "files_with_matches": 1, "total_matches": 1,
            "matches": [{
                "file": "test.py",
                "matches": [{
                    "line_number": 5,
                    "line": "target line",
                    "context_before": ["line before"],
                    "context_after": ["line after"],
                }],
            }],
        }
        text = _format_search_readable(data, line_numbers=True)
        assert "target line" in text
        assert "line before" in text
        assert "line after" in text
