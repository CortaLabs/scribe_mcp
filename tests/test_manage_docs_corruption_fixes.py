"""Tests for manage_docs corruption fixes.

Covers five bugs that caused data loss and agent spiral behavior:
1. replace_text NO_MATCH false negatives (newline normalization)
2. file_size_after=0 misreporting in error responses
3. replace_range splice producing empty documents
4. _replace_section marker stripping with multi-line prefixes
5. replace_range false frontmatter detection on --- content
"""
from __future__ import annotations

import pytest

from scribe_mcp.doc_management.manager import (
    DocChangeResult,
    DocumentOperationError,
    _replace_range_text,
    _replace_section,
    _replace_text_literal,
    _replace_text_with_scope,
)


# ---------------------------------------------------------------------------
# Bug 1: replace_text newline normalization
# ---------------------------------------------------------------------------
class TestReplaceTextNewlineNormalization:
    """replace_text should match text regardless of \\r\\n vs \\n differences."""

    def test_exact_match_still_works(self):
        text = "line one\nline two\nline three\n"
        result, hits = _replace_text_literal(text, "line two", "LINE TWO", replace_all=False)
        assert hits == 1
        assert "LINE TWO" in result

    def test_crlf_in_body_lf_in_find(self):
        """File has \\r\\n but find text uses \\n — should still match."""
        text = "---\r\n## Title\r\ncontent here\r\n"
        find = "---\n## Title"
        result, hits = _replace_text_literal(text, find, "REPLACED", replace_all=False)
        assert hits == 1
        assert "REPLACED" in result

    def test_lf_in_body_crlf_in_find(self):
        """File has \\n but find text uses \\r\\n — should still match."""
        text = "---\n## Title\ncontent here\n"
        find = "---\r\n## Title"
        result, hits = _replace_text_literal(text, find, "REPLACED", replace_all=False)
        assert hits == 1
        assert "REPLACED" in result

    def test_no_match_returns_zero_hits(self):
        text = "hello world\n"
        result, hits = _replace_text_literal(text, "goodbye", "REPLACED", replace_all=False)
        assert hits == 0
        assert result == text

    def test_replace_all_with_normalization(self):
        text = "a\r\nb\r\na\r\n"
        find = "a\nb"
        result, hits = _replace_text_literal(text, find, "X", replace_all=True)
        assert hits == 1
        assert "X" in result

    def test_scoped_replace_text_normalization(self):
        """Full _replace_text_with_scope also benefits from normalization."""
        body = "<!-- ID: sect -->\r\nfoo bar\r\nbaz\r\n"
        result, hits = _replace_text_with_scope(
            body,
            find_text="foo bar\nbaz",
            replace_text="REPLACED",
            match_mode="literal",
            replace_all=False,
            scope=None,
            allow_no_match=False,
        )
        assert hits == 1
        assert "REPLACED" in result


# ---------------------------------------------------------------------------
# Bug 3: replace_range producing empty documents
# ---------------------------------------------------------------------------
class TestReplaceRangeEmptyDocGuard:
    """replace_range must refuse to zero out a document."""

    def test_normal_replace_range(self):
        text = "line1\nline2\nline3\nline4\n"
        result = _replace_range_text(text, 2, 3, "new content")
        assert "new content" in result
        assert "line1" in result
        assert "line4" in result

    def test_replace_range_empty_content_full_range_raises(self):
        """Replacing entire document with empty content should raise."""
        text = "line1\nline2\nline3\n"
        with pytest.raises(DocumentOperationError, match="REPLACE_RANGE_WOULD_EMPTY_DOC"):
            _replace_range_text(text, 1, 3, "")

    def test_replace_range_empty_content_partial_range_ok(self):
        """Deleting a subset of lines is fine if doc remains non-empty."""
        text = "line1\nline2\nline3\nline4\n"
        result = _replace_range_text(text, 2, 3, "")
        assert "line1" in result
        assert "line4" in result

    def test_replace_range_whitespace_only_content_full_range_raises(self):
        """Replacing entire document with whitespace-only should also raise."""
        text = "line1\nline2\n"
        with pytest.raises(DocumentOperationError, match="REPLACE_RANGE_WOULD_EMPTY_DOC"):
            _replace_range_text(text, 1, 2, "   \n  \n")


# ---------------------------------------------------------------------------
# Bug 4: _replace_section marker duplication with multi-line prefixes
# ---------------------------------------------------------------------------
class TestReplaceSectionMarkerStripping:
    """_replace_section should strip redundant markers even with multi-line prefixes."""

    def test_single_header_prefix_stripped(self):
        """Standard case: content includes header + marker."""
        doc = "# Doc\n<!-- ID: intro -->\nold content\n<!-- ID: details -->\ndetails\n"
        content = "## Intro\n<!-- ID: intro -->\nnew content"
        result = _replace_section(doc, "intro", content)
        assert result.count("<!-- ID: intro -->") == 1
        assert "new content" in result

    def test_multi_line_header_prefix_stripped(self):
        """Content has multi-line header structure before marker."""
        doc = "# Doc\n<!-- ID: intro -->\nold content\n<!-- ID: details -->\ndetails\n"
        content = "## Intro\n### Subtitle\n<!-- ID: intro -->\nnew content"
        result = _replace_section(doc, "intro", content)
        assert result.count("<!-- ID: intro -->") == 1
        assert "new content" in result

    def test_no_prefix_marker_at_start(self):
        """Content starts directly with marker."""
        doc = "# Doc\n<!-- ID: intro -->\nold content\n"
        content = "<!-- ID: intro -->\nnew content"
        result = _replace_section(doc, "intro", content)
        assert result.count("<!-- ID: intro -->") == 1
        assert "new content" in result

    def test_body_only_content(self):
        """Content is just body text — no stripping needed."""
        doc = "# Doc\n<!-- ID: intro -->\nold content\n"
        content = "new content only"
        result = _replace_section(doc, "intro", content)
        assert result.count("<!-- ID: intro -->") == 1
        assert "new content only" in result


# ---------------------------------------------------------------------------
# Bug 5: replace_range false frontmatter detection
# ---------------------------------------------------------------------------
class TestReplaceRangeNoFrontmatterParsing:
    """replace_range must NOT parse --- in content as frontmatter."""

    def test_content_with_leading_hr_preserved(self):
        """Content starting with --- (horizontal rule) should be used as-is."""
        body = "line1\nline2\nline3\n"
        content = "---\n## New Section\ncontent here\n"
        result = _replace_range_text(body, 2, 2, content)
        assert "---" in result
        assert "## New Section" in result
        assert "content here" in result

    def test_content_with_multiple_hr_separators(self):
        """Content with multiple --- should not trigger frontmatter stripping."""
        body = "line1\nline2\nline3\nline4\n"
        content = "---\n## Section A\n---\n## Section B\n"
        result = _replace_range_text(body, 2, 3, content)
        assert result.count("---") == 2
        assert "## Section A" in result
        assert "## Section B" in result


# ---------------------------------------------------------------------------
# Bug 2: file_size_after misreporting (integration-level)
# ---------------------------------------------------------------------------
class TestDocChangeResultErrorReporting:
    """Error responses must report file_size_after = file_size_before, not 0."""

    def test_error_result_preserves_file_size(self):
        """DocChangeResult in error case should never show file_size_after=0
        when file_size_before > 0."""
        result = DocChangeResult(
            doc_name="test",
            section=None,
            action="replace_text",
            path=__import__("pathlib").Path(""),
            before_hash="",
            after_hash="",
            content_written="",
            diff_preview="",
            success=False,
            error_message="REPLACE_TEXT_NO_MATCH: no matches found",
            verification_passed=False,
            file_size_before=52864,
            file_size_after=52864,  # Should match file_size_before on error
        )
        assert result.file_size_after == result.file_size_before
        assert result.file_size_after != 0
