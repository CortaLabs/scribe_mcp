"""Unit tests for utils/formatters/base.py - Base Formatter Module.

Tests for Phase 5 Task 5.2: Base formatter extraction from ResponseFormatter.
Covers:
- get_use_ansi_colors() function
- create_pagination_info() function
- format_compact_json() function
- BaseFormatter class with all methods
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.formatters.base import (
    BaseFormatter,
    get_use_ansi_colors,
    create_pagination_info,
    format_compact_json,
)
from utils.estimator import PaginationInfo


class TestGetUseAnsiColors:
    """Tests for get_use_ansi_colors() function."""

    def test_returns_boolean(self):
        """Test that function returns a boolean value."""
        result = get_use_ansi_colors()
        assert isinstance(result, bool)

    def test_callable(self):
        """Test that get_use_ansi_colors is callable and consistent."""
        # Call multiple times - should return consistent value
        result1 = get_use_ansi_colors()
        result2 = get_use_ansi_colors()
        assert result1 == result2
        assert isinstance(result1, bool)


class TestCreatePaginationInfo:
    """Tests for create_pagination_info() function."""

    def test_returns_pagination_info(self):
        """Test that function returns PaginationInfo object."""
        result = create_pagination_info(1, 10, 100)
        assert isinstance(result, PaginationInfo)

    def test_basic_pagination(self):
        """Test basic pagination calculation."""
        result = create_pagination_info(1, 10, 100)
        assert result.page == 1
        assert result.page_size == 10
        assert result.total_count == 100
        assert result.has_next is True
        assert result.has_prev is False

    def test_middle_page(self):
        """Test pagination for middle page."""
        result = create_pagination_info(5, 10, 100)
        assert result.page == 5
        assert result.has_next is True
        assert result.has_prev is True

    def test_last_page(self):
        """Test pagination for last page."""
        result = create_pagination_info(10, 10, 100)
        assert result.page == 10
        assert result.has_next is False
        assert result.has_prev is True

    def test_single_page(self):
        """Test pagination with single page."""
        result = create_pagination_info(1, 10, 5)
        assert result.page == 1
        assert result.has_next is False
        assert result.has_prev is False

    def test_empty_results(self):
        """Test pagination with empty results."""
        result = create_pagination_info(1, 10, 0)
        assert result.total_count == 0
        assert result.has_next is False
        assert result.has_prev is False


class TestFormatCompactJson:
    """Tests for format_compact_json() function."""

    def test_basic_abbreviation(self):
        """Test basic key abbreviation."""
        data = {"status": "ok", "message": "test"}
        result = format_compact_json(data)
        assert '"s":"ok"' in result
        assert '"msg":"test"' in result

    def test_project_fields(self):
        """Test project field abbreviations."""
        data = {"projects": [{"name": "test", "status": "planning"}]}
        result = format_compact_json(data)
        assert '"p":[' in result
        assert '"n":"test"' in result
        assert '"s":"planning"' in result

    def test_pagination_fields(self):
        """Test pagination field abbreviations."""
        data = {
            "pagination": {
                "page": 1,
                "page_size": 10,
                "total_count": 100,
                "has_next": True,
                "has_prev": False
            }
        }
        result = format_compact_json(data)
        assert '"pg":{' in result
        assert '"i":1' in result
        assert '"sz":10' in result
        assert '"tot":100' in result
        assert '"nx":true' in result
        assert '"pv":false' in result

    def test_nested_structures(self):
        """Test nested structure abbreviation."""
        data = {
            "entries": [
                {"message": "entry1", "status": "info"},
                {"message": "entry2", "status": "success"}
            ],
            "count": 2
        }
        result = format_compact_json(data)
        assert '"e":[' in result
        assert '"msg":"entry1"' in result
        assert '"c":2' in result

    def test_custom_abbreviations(self):
        """Test custom abbreviation overrides."""
        data = {"custom_field": "value"}
        custom_abbrev = {"custom_field": "cf"}
        result = format_compact_json(data, abbreviations=custom_abbrev)
        assert '"cf":"value"' in result

    def test_unknown_keys_preserved(self):
        """Test that unknown keys are preserved unchanged."""
        data = {"unknown_key": "value"}
        result = format_compact_json(data)
        assert '"unknown_key":"value"' in result

    def test_no_spaces_separator(self):
        """Test that output uses compact separators (no spaces)."""
        data = {"key1": "value1", "key2": "value2"}
        result = format_compact_json(data)
        # Should not have spaces after colons or commas
        assert '": "' not in result
        assert '", "' not in result

    def test_metadata_fields(self):
        """Test metadata field abbreviations."""
        data = {
            "metadata": {"confidence": 0.9, "priority": "high", "category": "bug"}
        }
        result = format_compact_json(data)
        assert '"meta":{' in result
        assert '"conf":0.9' in result
        assert '"pri":"high"' in result
        assert '"cat":"bug"' in result


class TestBaseFormatter:
    """Tests for BaseFormatter class."""

    def test_initialization(self):
        """Test BaseFormatter initialization."""
        bf = BaseFormatter()
        assert bf._token_warning_threshold == 4000
        assert isinstance(bf._use_colors, bool)

    def test_custom_threshold(self):
        """Test custom token warning threshold."""
        bf = BaseFormatter(token_warning_threshold=8000)
        assert bf._token_warning_threshold == 8000

    def test_use_colors_property(self):
        """Test USE_COLORS property getter."""
        bf = BaseFormatter()
        assert bf.USE_COLORS == bf._use_colors

    def test_use_colors_setter(self):
        """Test USE_COLORS property setter."""
        bf = BaseFormatter()
        bf.USE_COLORS = True
        assert bf._use_colors is True
        bf.USE_COLORS = False
        assert bf._use_colors is False


class TestBaseFormatterAnsiConstants:
    """Tests for ANSI constants on BaseFormatter."""

    def test_ansi_constants_defined(self):
        """Test that ANSI constants are defined on the class."""
        assert hasattr(BaseFormatter, 'ANSI_CYAN')
        assert hasattr(BaseFormatter, 'ANSI_GREEN')
        assert hasattr(BaseFormatter, 'ANSI_YELLOW')
        assert hasattr(BaseFormatter, 'ANSI_BLUE')
        assert hasattr(BaseFormatter, 'ANSI_MAGENTA')
        assert hasattr(BaseFormatter, 'ANSI_BOLD')
        assert hasattr(BaseFormatter, 'ANSI_DIM')
        assert hasattr(BaseFormatter, 'ANSI_RESET')

    def test_ansi_constants_values(self):
        """Test that ANSI constants have correct escape codes."""
        assert BaseFormatter.ANSI_CYAN == "\033[36m"
        assert BaseFormatter.ANSI_GREEN == "\033[32m"
        assert BaseFormatter.ANSI_YELLOW == "\033[33m"
        assert BaseFormatter.ANSI_BLUE == "\033[34m"
        assert BaseFormatter.ANSI_MAGENTA == "\033[35m"
        assert BaseFormatter.ANSI_BOLD == "\033[1m"
        assert BaseFormatter.ANSI_DIM == "\033[2m"
        assert BaseFormatter.ANSI_RESET == "\033[0m"


class TestBaseFormatterEstimateTokens:
    """Tests for BaseFormatter.estimate_tokens() method."""

    def test_estimate_tokens_string(self):
        """Test token estimation for string input."""
        bf = BaseFormatter()
        result = bf.estimate_tokens("hello world")
        assert isinstance(result, int)
        assert result > 0

    def test_estimate_tokens_dict(self):
        """Test token estimation for dict input."""
        bf = BaseFormatter()
        result = bf.estimate_tokens({"key": "value", "nested": {"deep": "data"}})
        assert isinstance(result, int)
        assert result > 0

    def test_estimate_tokens_list(self):
        """Test token estimation for list input."""
        bf = BaseFormatter()
        result = bf.estimate_tokens(["item1", "item2", "item3"])
        assert isinstance(result, int)
        assert result > 0

    def test_larger_data_more_tokens(self):
        """Test that larger data produces higher token estimate."""
        bf = BaseFormatter()
        small = bf.estimate_tokens("small")
        large = bf.estimate_tokens("this is a much larger string with more content")
        assert large > small


class TestBaseFormatterFormatRelativeTime:
    """Tests for BaseFormatter.format_relative_time() method."""

    def test_just_now(self):
        """Test 'just now' for very recent timestamps."""
        bf = BaseFormatter()
        ts = datetime.utcnow().isoformat() + 'Z'
        result = bf.format_relative_time(ts)
        assert result == "just now"

    def test_minutes_ago(self):
        """Test minutes ago formatting."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(minutes=5)).isoformat() + 'Z'
        result = bf.format_relative_time(ts)
        assert "minute" in result
        assert "ago" in result

    def test_hours_ago(self):
        """Test hours ago formatting."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(hours=3)).isoformat() + 'Z'
        result = bf.format_relative_time(ts)
        assert "3 hours ago" in result

    def test_days_ago(self):
        """Test days ago formatting."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(days=4)).isoformat() + 'Z'
        result = bf.format_relative_time(ts)
        assert "4 days ago" in result

    def test_weeks_ago(self):
        """Test weeks ago formatting."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(days=14)).isoformat() + 'Z'
        result = bf.format_relative_time(ts)
        assert "week" in result
        assert "ago" in result

    def test_months_ago(self):
        """Test months ago formatting."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(days=90)).isoformat() + 'Z'
        result = bf.format_relative_time(ts)
        assert "month" in result
        assert "ago" in result

    def test_utc_suffix_format(self):
        """Test parsing timestamp with ' UTC' suffix."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S') + ' UTC'
        result = bf.format_relative_time(ts)
        assert "2 hours ago" in result

    def test_iso_format_with_z(self):
        """Test parsing ISO format with Z suffix."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(days=1)).isoformat() + 'Z'
        result = bf.format_relative_time(ts)
        assert "1 day ago" in result

    def test_iso_format_with_offset(self):
        """Test parsing ISO format with +00:00 offset."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(hours=1)).isoformat() + '+00:00'
        result = bf.format_relative_time(ts)
        assert "1 hour ago" in result

    def test_invalid_timestamp_returns_original(self):
        """Test that invalid timestamps return the original string."""
        bf = BaseFormatter()
        invalid = "not-a-timestamp"
        result = bf.format_relative_time(invalid)
        assert result == invalid

    def test_1_minute_ago_singular(self):
        """Test singular minute formatting."""
        bf = BaseFormatter()
        ts = (datetime.utcnow() - timedelta(minutes=1, seconds=30)).isoformat() + 'Z'
        result = bf.format_relative_time(ts)
        assert "1 minute ago" in result


class TestBaseFormatterFormatReadableError:
    """Tests for BaseFormatter.format_readable_error() method."""

    def test_basic_error_format(self):
        """Test basic error formatting."""
        bf = BaseFormatter()
        result = bf.format_readable_error("Test error", {"error_type": "validation"})
        assert "ERROR" in result
        assert "Test error" in result

    def test_error_with_context(self):
        """Test error formatting with context."""
        bf = BaseFormatter()
        context = {"error_type": "permission", "file": "/test/path"}
        result = bf.format_readable_error("Access denied", context)
        assert "Access denied" in result
        assert "file" in result or "/test/path" in result

    def test_error_with_empty_context(self):
        """Test error formatting with empty context."""
        bf = BaseFormatter()
        result = bf.format_readable_error("Error message", {})
        assert "Error message" in result


class TestBaseFormatterBoxMethods:
    """Tests for BaseFormatter fallback box methods."""

    def test_create_header_box_fallback(self):
        """Test fallback header box implementation."""
        bf = BaseFormatter()
        result = bf._create_header_box("TEST", {"key": "value"})
        assert "TEST" in result
        assert "key" in result
        assert "value" in result

    def test_create_footer_box_fallback(self):
        """Test fallback footer box implementation."""
        bf = BaseFormatter()
        result = bf._create_footer_box({"meta_key": "meta_value"})
        assert "meta_key" in result
        assert "meta_value" in result


class TestBaseFormatterInheritance:
    """Tests verifying inheritance relationships."""

    def test_ui_formatter_inherits_base(self):
        """Test that UIFormatter inherits from BaseFormatter."""
        from utils.formatters.ui import UIFormatter
        assert issubclass(UIFormatter, BaseFormatter)

    def test_ui_formatter_has_ansi_constants(self):
        """Test that UIFormatter has ANSI constants via inheritance."""
        from utils.formatters.ui import UIFormatter
        uf = UIFormatter()
        assert hasattr(uf, 'ANSI_CYAN')
        assert uf.ANSI_CYAN == BaseFormatter.ANSI_CYAN

    def test_ui_formatter_has_estimate_tokens(self):
        """Test that UIFormatter has estimate_tokens via inheritance."""
        from utils.formatters.ui import UIFormatter
        uf = UIFormatter()
        result = uf.estimate_tokens("test")
        assert isinstance(result, int)

    def test_ui_formatter_has_format_relative_time(self):
        """Test that UIFormatter has format_relative_time via inheritance."""
        from utils.formatters.ui import UIFormatter
        uf = UIFormatter()
        ts = datetime.utcnow().isoformat() + 'Z'
        result = uf.format_relative_time(ts)
        assert result == "just now"


class TestBackwardCompatibility:
    """Tests for backward compatibility with response module."""

    def test_response_module_imports(self):
        """Test that response module imports work correctly."""
        from utils.response import create_pagination_info, format_compact_json
        # Just verify they're callable
        assert callable(create_pagination_info)
        assert callable(format_compact_json)

    def test_response_create_pagination_info(self):
        """Test create_pagination_info from response module."""
        from utils.response import create_pagination_info
        result = create_pagination_info(1, 10, 100)
        assert result.page == 1
        assert result.total_count == 100

    def test_response_format_compact_json(self):
        """Test format_compact_json from response module."""
        from utils.response import format_compact_json
        data = {"status": "ok"}
        result = format_compact_json(data)
        assert '"s":"ok"' in result

    def test_response_formatter_has_base(self):
        """Test that ResponseFormatter has _base attribute."""
        from utils.response import ResponseFormatter
        rf = ResponseFormatter()
        assert hasattr(rf, '_base')
        assert isinstance(rf._base, BaseFormatter)

    def test_response_formatter_format_relative_time_delegation(self):
        """Test that ResponseFormatter delegates _format_relative_time."""
        from utils.response import ResponseFormatter
        rf = ResponseFormatter()
        ts = (datetime.utcnow() - timedelta(hours=2)).isoformat() + 'Z'
        result = rf._format_relative_time(ts)
        assert "2 hours ago" in result
