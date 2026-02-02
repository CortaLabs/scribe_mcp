"""Tests for template entry filter in utils/logs.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logs import _is_template_entry


class TestTemplateEntryFilter:
    """Test suite for _is_template_entry function"""

    def test_legitimate_entry_with_template_word_not_filtered(self):
        """Legitimate entry with 'template' in message should NOT be filtered."""
        result = _is_template_entry(
            timestamp="2026-02-02 04:00:00",
            emoji="ℹ️",
            agent="CoderAgent",
            message="Implemented template rendering feature"
        )
        assert result is False, "Entry with 'template' in message should not be filtered"

    def test_legitimate_entry_with_message_word_not_filtered(self):
        """Legitimate entry with 'message' in content should NOT be filtered."""
        result = _is_template_entry(
            timestamp="2026-02-02 04:00:00",
            emoji="✅",
            agent="ResearchAgent",
            message="Fixed message handling in API"
        )
        assert result is False, "Entry with 'message' in content should not be filtered"

    def test_template_with_structural_indicators_filtered(self):
        """Actual template entry with 2+ structural indicators SHOULD be filtered."""
        result = _is_template_entry(
            timestamp="YYYY-MM-DD HH:MM:SS",
            emoji="EMOJI",
            agent="<name>",
            message="Message text here"
        )
        assert result is True, "Entry with 2+ structural indicators should be filtered"

    def test_template_with_yyyy_mm_dd_and_emoji_filtered(self):
        """Template with YYYY-MM-DD and EMOJI should be filtered."""
        result = _is_template_entry(
            timestamp="YYYY-MM-DD",
            emoji="EMOJI",
            agent="RealAgent",
            message="Real message"
        )
        assert result is True, "Template with 2 structural indicators should be filtered"

    def test_single_structural_indicator_not_filtered(self):
        """Single structural indicator alone should NOT filter."""
        result = _is_template_entry(
            timestamp="YYYY-MM-DD",
            emoji="✅",
            agent="RealAgent",
            message="Real work done"
        )
        assert result is False, "Single structural indicator insufficient"

    def test_one_structural_two_content_filtered(self):
        """1 structural + 2 content indicators SHOULD be filtered."""
        result = _is_template_entry(
            timestamp="YYYY-MM-DD",
            emoji="✅",
            agent="RealAgent",
            message="Message text here is placeholder"
        )
        assert result is True, "1 structural + 2 content indicators should filter"

    def test_real_entry_no_indicators(self):
        """Real entry with no indicators should not be filtered."""
        result = _is_template_entry(
            timestamp="2026-02-02 04:20:15",
            emoji="✅",
            agent="CoderAgent",
            message="Completed phase 1 implementation"
        )
        assert result is False, "Real entry with no indicators should pass through"

    def test_edge_case_partial_timestamp(self):
        """Partial timestamp pattern alone should not filter."""
        result = _is_template_entry(
            timestamp="2026-YYYY-DD",
            emoji="ℹ️",
            agent="TestAgent",
            message="Testing edge case"
        )
        assert result is False, "Partial pattern match should not filter"

    def test_multiple_content_indicators_no_structural(self):
        """Multiple content indicators without structural should not filter."""
        result = _is_template_entry(
            timestamp="2026-02-02 04:00:00",
            emoji="⚠️",
            agent="CoderAgent",
            message="This is a placeholder example message text"
        )
        assert result is False, "Content indicators alone insufficient without structural"

    def test_case_insensitive_matching(self):
        """Template matching should be case-insensitive."""
        result = _is_template_entry(
            timestamp="yyyy-mm-dd hh:mm:ss",
            emoji="emoji",
            agent="<NAME>",
            message="MESSAGE TEXT"
        )
        assert result is True, "Case-insensitive matching should detect templates"
