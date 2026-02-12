#!/usr/bin/env python3
"""Comprehensive unit tests for QueryEntriesConfig.

Tests for all 26 parameters, validation logic, normalization, and utility methods.
"""

import pytest
from typing import Any, Dict

from scribe_mcp.tools.config.query_entries_config import (
    QueryEntriesConfig,
    create_query_config,
    create_search_config,
    VALID_MESSAGE_MODES,
    VALID_SEARCH_SCOPES,
    VALID_DOCUMENT_TYPES
)


class TestQueryEntriesConfigBasicFunctionality:
    """Test basic configuration creation and functionality."""

    def test_default_configuration(self):
        """Test creating configuration with all defaults."""
        config = QueryEntriesConfig()

        assert config.project is None
        assert config.start is None
        assert config.end is None
        assert config.message is None
        assert config.message_mode == "substring"
        assert config.case_sensitive is False
        assert config.emoji is None
        assert config.status is None
        assert config.agents is None
        assert config.meta_filters is None
        assert config.page == 1
        assert config.page_size == 50
        assert config.compact is False
        assert config.fields is None
        assert config.include_metadata is True
        assert config.search_scope == "project"
        assert config.document_types is None
        assert config.include_outdated is True
        assert config.verify_code_references is False
        assert config.time_range is None
        assert config.relevance_threshold == 0.0
        assert config.max_results is None

    def test_full_configuration(self):
        """Test creating configuration with all parameters specified."""
        config = QueryEntriesConfig(
            project="test_project",
            start="2025-01-01",
            end="2025-01-31",
            message="test message",
            message_mode="regex",
            case_sensitive=True,
            emoji=["✅", "🐞"],
            status=["success", "error"],
            agents=["Coder-A", "Coder-B"],
            meta_filters={"phase": "1"},
            limit=100,
            page=2,
            page_size=25,
            compact=True,
            fields=["message", "timestamp"],
            include_metadata=False,
            search_scope="all_projects",
            document_types=["progress", "bugs"],
            include_outdated=False,
            verify_code_references=True,
            time_range="last_7d",
            relevance_threshold=0.8,
            max_results=200
        )

        assert config.project == "test_project"
        assert config.message_mode == "regex"
        assert config.case_sensitive is True
        assert config.emoji == ["✅", "🐞"]
        assert config.search_scope == "all_projects"
        assert config.relevance_threshold == 0.8
        assert config.max_results == 200

    def test_pagination_mode_detection(self):
        """Test pagination vs legacy mode detection."""
        # Default should be legacy mode
        config = QueryEntriesConfig(page=1, page_size=50, limit=50)
        assert not config.is_pagination_mode()
        assert config.get_effective_limit() == 50

        # Page > 1 should trigger pagination mode
        config = QueryEntriesConfig(page=2, page_size=50)
        assert config.is_pagination_mode()
        assert config.get_effective_limit() == 50
        assert config.limit is None

        # Different page_size should trigger pagination mode
        config = QueryEntriesConfig(page=1, page_size=25)
        assert config.is_pagination_mode()
        assert config.get_effective_limit() == 25

    def test_string_parameter_conversion(self):
        """Test conversion of string parameters to appropriate types."""
        config = QueryEntriesConfig(
            page="1",
            page_size="50",
            limit="100"
        )

        assert isinstance(config.page, int)
        assert config.page == 1
        assert isinstance(config.page_size, int)
        assert config.page_size == 100  # Legacy mode sets page_size to limit
        assert isinstance(config.limit, int)
        assert config.limit == 100
        assert not config.is_pagination_mode()  # Should be legacy mode


class TestQueryEntriesConfigValidation:
    """Test validation logic for all parameters."""

    def test_valid_message_modes(self):
        """Test all valid message_mode values."""
        for mode in VALID_MESSAGE_MODES:
            config = QueryEntriesConfig(message_mode=mode)
            is_valid, error = config.validate()
            assert is_valid, f"Valid message_mode '{mode}' should pass validation"
            assert error is None

    def test_invalid_message_mode(self):
        """Test invalid message_mode values."""
        config = QueryEntriesConfig(message_mode="invalid_mode")
        is_valid, error = config.validate()

        assert not is_valid
        assert error is not None
        assert error["error_type"] == "enum_validation_error"
        assert "message_mode" in error["context"]["parameter"]

    def test_valid_search_scopes(self):
        """Test all valid search_scope values."""
        for scope in VALID_SEARCH_SCOPES:
            config = QueryEntriesConfig(search_scope=scope)
            is_valid, error = config.validate()
            assert is_valid, f"Valid search_scope '{scope}' should pass validation"
            assert error is None

    def test_invalid_search_scope(self):
        """Test invalid search_scope values."""
        config = QueryEntriesConfig(search_scope="invalid_scope")
        is_valid, error = config.validate()

        assert not is_valid
        assert error is not None
        assert error["error_type"] == "enum_validation_error"
        assert "search_scope" in error["context"]["parameter"]

    def test_valid_document_types(self):
        """Test valid document_types values."""
        config = QueryEntriesConfig(document_types=["progress", "research"])
        is_valid, error = config.validate()

        assert is_valid
        assert error is None

    def test_invalid_document_types(self):
        """Test invalid document_types values."""
        config = QueryEntriesConfig(document_types=["progress", "invalid_type"])
        is_valid, error = config.validate()

        assert not is_valid
        assert error is not None
        assert error["error_type"] == "enum_validation_error"
        assert "document_types" in error["context"]["parameter"]

    def test_valid_relevance_threshold(self):
        """Test valid relevance_threshold values."""
        test_values = [0.0, 0.1, 0.5, 0.9, 1.0]
        for value in test_values:
            config = QueryEntriesConfig(relevance_threshold=value)
            is_valid, error = config.validate()
            assert is_valid, f"Valid relevance_threshold '{value}' should pass validation"
            assert error is None

    def test_invalid_relevance_threshold(self):
        """Test invalid relevance_threshold values."""
        test_values = [-0.1, 1.1, 2.0]
        for value in test_values:
            config = QueryEntriesConfig(relevance_threshold=value)
            is_valid, error = config.validate()

            assert not is_valid, f"Invalid relevance_threshold '{value}' should fail validation"
            assert error is not None
            assert error["error_type"] == "validation_error"
            assert "relevance_threshold" in error["context"]["parameter"]

    def test_valid_regex_pattern(self):
        """Test valid regex patterns."""
        patterns = [r".*test.*", r"^start", r"end$", r"\d+"]
        for pattern in patterns:
            config = QueryEntriesConfig(message=pattern, message_mode="regex")
            is_valid, error = config.validate()
            assert is_valid, f"Valid regex pattern '{pattern}' should pass validation"
            assert error is None

    def test_invalid_regex_pattern(self):
        """Test invalid regex patterns."""
        patterns = [r"[", r"*invalid", r"("]
        for pattern in patterns:
            config = QueryEntriesConfig(message=pattern, message_mode="regex")
            is_valid, error = config.validate()

            assert not is_valid, f"Invalid regex pattern '{pattern}' should fail validation"
            assert error is not None
            assert error["error_type"] == "regex_error"

    def test_valid_pagination_parameters(self):
        """Test valid pagination parameters."""
        config = QueryEntriesConfig(page=1, page_size=50)
        is_valid, error = config.validate()
        assert is_valid
        assert error is None

    def test_invalid_page_parameter(self):
        """Test invalid page values."""
        config = QueryEntriesConfig(page=0)
        is_valid, error = config.validate()

        assert not is_valid
        assert error is not None
        assert error["error_type"] == "validation_error"
        assert "page" in error["context"]["parameter"]

    def test_invalid_page_size_parameters(self):
        """Test invalid page_size values."""
        test_values = [0, -1, 501, 1000]
        for value in test_values:
            config = QueryEntriesConfig(page_size=value)
            is_valid, error = config.validate()

            assert not is_valid, f"Invalid page_size '{value}' should fail validation"
            assert error is not None
            assert error["error_type"] == "validation_error"
            assert "page_size" in error["context"]["parameter"]

    def test_valid_time_ranges(self):
        """Test valid time_range values."""
        valid_ranges = ["today", "last_7d", "last_30d", "this_week", "last_month"]
        for time_range in valid_ranges:
            config = QueryEntriesConfig(time_range=time_range)
            is_valid, error = config.validate()
            assert is_valid, f"Valid time_range '{time_range}' should pass validation"
            assert error is None

    def test_invalid_time_range(self):
        """Test invalid time_range values."""
        config = QueryEntriesConfig(time_range="invalid_range")
        is_valid, error = config.validate()

        assert not is_valid
        assert error is not None
        assert error["error_type"] == "enum_validation_error"
        assert "time_range" in error["context"]["parameter"]


class TestQueryEntriesConfigNormalization:
    """Test parameter normalization functionality."""

    def test_message_mode_normalization(self):
        """Test message_mode normalization."""
        config = QueryEntriesConfig(message_mode="SUBSTRING")
        assert config.message_mode == "substring"

        config = QueryEntriesConfig(message_mode=None)
        assert config.message_mode == "substring"  # Default value

    def test_search_scope_normalization(self):
        """Test search_scope normalization."""
        config = QueryEntriesConfig(search_scope="ALL_PROJECTS")
        assert config.search_scope == "all_projects"

    def test_list_parameter_normalization(self):
        """Test list parameter normalization."""
        # String lists should be converted
        config = QueryEntriesConfig(emoji="✅,🐞")
        assert config.emoji == ["✅", "🐞"]

        config = QueryEntriesConfig(status="success,error")
        assert config.status == ["success", "error"]

        # None values should remain None
        config = QueryEntriesConfig(emoji=None)
        assert config.emoji is None

    def test_pagination_mode_resolution(self):
        """Test pagination mode resolution logic."""
        # Legacy mode: page=1, page_size=50, limit specified
        config = QueryEntriesConfig(page=1, page_size=50, limit=100)
        assert config.limit == 100
        assert config.page_size == 100
        assert not config.is_pagination_mode()

        # Pagination mode: page > 1
        config = QueryEntriesConfig(page=2, page_size=50)
        assert config.limit is None
        assert config.page_size == 50
        assert config.is_pagination_mode()

        # Pagination mode: page_size != 50
        config = QueryEntriesConfig(page=1, page_size=25)
        assert config.limit is None
        assert config.page_size == 25
        assert config.is_pagination_mode()


class TestQueryEntriesConfigUtilityMethods:
    """Test utility methods and convenience functions."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = QueryEntriesConfig(
            message="test",
            search_scope="all_projects",
            relevance_threshold=0.8
        )

        result = config.to_dict()
        assert isinstance(result, dict)
        assert result["message"] == "test"
        assert result["search_scope"] == "all_projects"
        assert result["relevance_threshold"] == 0.8
        assert "_config_manager" not in result  # Private attributes excluded

    def test_to_tool_params(self):
        """Test conversion to tool parameters."""
        config = QueryEntriesConfig(
            message="test",
            limit=50,
            max_results=100
        )

        params = config.to_tool_params()
        assert params["message"] == "test"
        assert params["limit"] == 100  # max_results overrides limit
        assert "max_results" not in params  # Internal parameter excluded

    def test_from_legacy_params(self):
        """Test creation from legacy parameters."""
        legacy_params = {
            "message": "test message",
            "search_scope": "global",
            "relevance_threshold": 0.7,
            "invalid_param": "should_be_ignored"
        }

        config = QueryEntriesConfig.from_legacy_params(**legacy_params)
        assert config.message == "test message"
        assert config.search_scope == "global"
        assert config.relevance_threshold == 0.7
        assert not hasattr(config, "invalid_param")

    def test_create_search_config(self):
        """Test search-focused configuration creation."""
        config = QueryEntriesConfig.create_search_config(
            query="error message",
            scope="bugs",
            filters={"status": ["bug"], "emoji": ["🐞"]}
        )

        assert config.message == "error message"
        assert config.search_scope == "bugs"
        assert config.status == ["bug"]
        assert config.emoji == ["🐞"]
        assert config.message_mode == "substring"
        assert config.include_metadata is True

    def test_get_search_description(self):
        """Test search description generation."""
        config = QueryEntriesConfig(
            message="test error",
            message_mode="regex",
            search_scope="bugs",
            status=["error"],
            relevance_threshold=0.8
        )

        description = config.get_search_description()
        assert "test error" in description
        assert "regex" in description
        assert "bugs" in description
        assert "relevance≥0.8" in description

    def test_get_search_description_empty(self):
        """Test search description for empty configuration."""
        config = QueryEntriesConfig()
        description = config.get_search_description()
        assert description == "all entries"


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_query_config(self):
        """Test create_query_config convenience function."""
        config = create_query_config(
            message="test",
            search_scope="global"
        )

        assert isinstance(config, QueryEntriesConfig)
        assert config.message == "test"
        assert config.search_scope == "global"

    def test_create_search_config_function(self):
        """Test create_search_config convenience function."""
        config = create_search_config(
            query="test query",
            scope="all_projects",
            relevance_threshold=0.5
        )

        assert isinstance(config, QueryEntriesConfig)
        assert config.message == "test query"
        assert config.search_scope == "all_projects"
        assert config.relevance_threshold == 0.5


class TestComplexSearchScenarios:
    """Test complex search scenarios and parameter combinations."""

    def test_complex_search_configuration(self):
        """Test complex search with multiple parameters."""
        config = QueryEntriesConfig(
            message=r"\[ERROR\].*database",
            message_mode="regex",
            case_sensitive=True,
            search_scope="all_projects",
            document_types=["progress", "bugs"],
            agents=["Coder-A", "Coder-B"],
            time_range="last_7d",
            relevance_threshold=0.7,
            page=2,
            page_size=25
        )

        # Should be valid
        is_valid, error = config.validate()
        assert is_valid
        assert error is None

        # Should be in pagination mode
        assert config.is_pagination_mode()

        # Should have comprehensive search description
        description = config.get_search_description()
        assert "regex" in description
        assert "all_projects" in description
        assert "last_7d" in description
        assert "relevance≥0.7" in description

    def test_edge_case_parameters(self):
        """Test edge case parameter values."""
        config = QueryEntriesConfig(
            message="",  # Empty message
            message_mode="exact",
            search_scope="global",
            relevance_threshold=0.0,  # Minimum threshold
            page=1,  # First page
            page_size=1,  # Minimum page size
            include_metadata=False,
            compact=True
        )

        is_valid, error = config.validate()
        assert is_valid
        assert error is None

    def test_maximum_boundary_values(self):
        """Test maximum boundary values."""
        config = QueryEntriesConfig(
            relevance_threshold=1.0,  # Maximum threshold
            page=1,
            page_size=500,  # Maximum page size
            limit=500  # Maximum limit
        )

        is_valid, error = config.validate()
        assert is_valid
        assert error is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])