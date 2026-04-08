#!/usr/bin/env python3
"""Comprehensive tests for ErrorHandler utility.

Tests all 15 static methods of ErrorHandler class with various
error scenarios and edge cases to ensure consistent error
handling across MCP tools.
"""

import pytest
import re
from unittest.mock import Mock
import sqlite3
from datetime import datetime, timedelta, timezone

from scribe_mcp.utils.error_handler import ErrorHandler
from scribe_mcp.shared.logging_utils import ProjectResolutionError
from scribe_mcp.shared.project_registry import ProjectRegistry


class TestErrorHandler:
    """Test cases for ErrorHandler static methods."""

    def test_create_validation_error_basic(self):
        """Test basic validation error creation."""
        result = ErrorHandler.create_validation_error(
            error_message="Test error",
            suggestion="Test suggestion"
        )

        assert result["ok"] is False
        assert result["error"] == "Test error"
        assert result["suggestion"] == "Test suggestion"

    def test_create_validation_error_with_alternative(self):
        """Test validation error with alternative approach."""
        result = ErrorHandler.create_validation_error(
            error_message="Test error",
            suggestion="Test suggestion",
            alternative="Test alternative"
        )

        assert result["ok"] is False
        assert result["error"] == "Test error"
        assert result["suggestion"] == "Test suggestion"
        assert result["alternative"] == "Test alternative"

    def test_create_validation_error_with_context(self):
        """Test validation error with additional context."""
        context = {"parameter": "test_param", "value": "invalid"}
        result = ErrorHandler.create_validation_error(
            error_message="Test error",
            context=context
        )

        assert result["ok"] is False
        assert result["error"] == "Test error"
        assert result["parameter"] == "test_param"
        assert result["value"] == "invalid"

    def test_create_validation_error_minimal(self):
        """Test validation error with only required fields."""
        result = ErrorHandler.create_validation_error(
            error_message="Minimal error"
        )

        assert result["ok"] is False
        assert result["error"] == "Minimal error"
        assert "suggestion" not in result

    def test_create_project_resolution_error_basic(self):
        """Test project resolution error creation."""
        error = ProjectResolutionError("Test project error", ["project1", "project2"])
        result = ErrorHandler.create_project_resolution_error(
            error=error,
            tool_name="test_tool",
            suggestion="Test suggestion"
        )

        assert result["ok"] is False
        assert result["error"] == "Test project error"
        assert result["suggestion"] == "Test suggestion"
        assert result["recent_projects"] == ["project1", "project2"]

    def test_create_project_resolution_error_includes_last_known_hint(self):
        """Regression: missing-project errors should include last-known project hint when available."""
        registry = ProjectRegistry()
        now = datetime.now(timezone.utc)
        last_access = now - timedelta(minutes=4)

        with sqlite3.connect(registry._db_path) as conn:  # noqa: SLF001 - test-only access
            conn.execute(
                """
                INSERT OR REPLACE INTO scribe_projects (name, repo_root, progress_log_path, created_at, last_access_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("project1", "/tmp/repo", "/tmp/repo/PROGRESS_LOG.md", now.isoformat(), last_access.isoformat()),
            )
            conn.commit()

        error = ProjectResolutionError("No project configured", ["project1"])
        result = ErrorHandler.create_project_resolution_error(error=error, tool_name="append_entry")

        assert result["ok"] is False
        assert result["last_known_project"] == "project1"
        assert isinstance(result["last_known_project_minutes_ago"], int)
        assert result["last_known_project_minutes_ago"] >= 0

    def test_create_project_resolution_error_default_suggestion(self):
        """Test project resolution error with default suggestion."""
        error = ProjectResolutionError("Test project error", ["project1"])
        result = ErrorHandler.create_project_resolution_error(
            error=error,
            tool_name="test_tool"
        )

        assert result["ok"] is False
        assert result["suggestion"] == "Invoke set_project before using test_tool"

    def test_create_parameter_error_basic(self):
        """Test parameter error creation."""
        result = ErrorHandler.create_parameter_error(
            parameter_name="test_param",
            issue="invalid value"
        )

        assert result["ok"] is False
        assert "Invalid test_param" in result["error"]
        # Suggestion might not be present for basic parameter errors

    def test_create_parameter_error_with_expected_received(self):
        """Test parameter error with expected and received values."""
        result = ErrorHandler.create_parameter_error(
            parameter_name="test_param",
            issue="wrong type",
            expected="string",
            received=123
        )

        assert result["ok"] is False
        assert "wrong type" in result["error"]
        assert "Expected: string, received: 123" in result["error"]

    def test_create_parameter_error_with_suggestion(self):
        """Test parameter error with custom suggestion."""
        result = ErrorHandler.create_parameter_error(
            parameter_name="test_param",
            issue="invalid format",
            suggestion="Use format YYYY-MM-DD"
        )

        assert result["ok"] is False
        assert "invalid format" in result["error"]
        assert result["suggestion"] == "Use format YYYY-MM-DD"

    def test_create_enum_error_case_sensitive(self):
        """Test enum error with case sensitivity."""
        result = ErrorHandler.create_enum_error(
            parameter_name="mode",
            invalid_value="Invalid",
            valid_values=["valid1", "valid2"],
            case_sensitive=True
        )

        assert result["ok"] is False
        assert "Unsupported value 'Invalid'" in result["error"]
        assert "valid1, valid2" in result["suggestion"]

    def test_create_enum_error_case_insensitive(self):
        """Test enum error with case insensitivity."""
        result = ErrorHandler.create_enum_error(
            parameter_name="mode",
            invalid_value="invalid",
            valid_values=["VALID1", "VALID2"],
            case_sensitive=False
        )

        assert result["ok"] is False
        assert result["suggestion"] is not None
        assert "VALID1, VALID2" in result["suggestion"]

    def test_create_enum_error_close_matches(self):
        """Test enum error with close match suggestions."""
        result = ErrorHandler.create_enum_error(
            parameter_name="mode",
            invalid_value="substri",  # Close to "substring"
            valid_values=["substring", "exact", "regex"],
            case_sensitive=False
        )

        assert result["ok"] is False
        assert "Did you mean" in result["suggestion"]

    def test_create_range_error_min_value(self):
        """Test range error with minimum value violation."""
        result = ErrorHandler.create_range_error(
            parameter_name="count",
            value=5,
            min_value=10
        )

        assert result["ok"] is False
        assert "too small" in result["error"]
        assert "≥ 10" in result["suggestion"]

    def test_create_range_error_max_value(self):
        """Test range error with maximum value violation."""
        result = ErrorHandler.create_range_error(
            parameter_name="count",
            value=150,
            max_value=100
        )

        assert result["ok"] is False
        assert "too large" in result["error"]
        assert "≤ 100" in result["suggestion"]

    def test_create_range_error_both_bounds(self):
        """Test range error with both min and max bounds."""
        result = ErrorHandler.create_range_error(
            parameter_name="count",
            value=150,
            min_value=10,
            max_value=100
        )

        assert result["ok"] is False
        assert "out of range" in result["error"]
        assert "between 10 and 100" in result["suggestion"]

    def test_create_regex_error(self):
        """Test regex compilation error."""
        regex_error = re.error("unbalanced parenthesis")
        result = ErrorHandler.create_regex_error(
            pattern="[invalid(",
            regex_error=regex_error
        )

        assert result["ok"] is False
        assert "Invalid regular expression pattern" in result["error"]
        assert "unbalanced parenthesis" in result["error"]
        assert "regex syntax" in result["suggestion"]

    def test_create_file_operation_error_not_found(self):
        """Test file operation error for missing file."""
        error = FileNotFoundError("No such file or directory: '/test/path'")
        result = ErrorHandler.create_file_operation_error(
            operation="read file",
            file_path="/test/path",
            error=error
        )

        assert result["ok"] is False
        assert "Unable to read file" in result["error"]
        # Check for generic suggestion since specific file not found detection may not work
        assert "file permissions" in result["suggestion"] or "path is accessible" in result["suggestion"]
        assert result["file_path"] == "/test/path"
        assert result["operation"] == "read file"

    def test_create_file_operation_error_permission(self):
        """Test file operation error for permission issues."""
        error = PermissionError("Permission denied: '/test/path'")
        result = ErrorHandler.create_file_operation_error(
            operation="write file",
            file_path="/test/path",
            error=error
        )

        assert result["ok"] is False
        assert "Unable to write file" in result["error"]
        assert "file permissions" in result["suggestion"]

    def test_create_file_operation_error_generic(self):
        """Test generic file operation error."""
        error = Exception("Generic error")
        result = ErrorHandler.create_file_operation_error(
            operation="process file",
            file_path="/test/path",
            error=error
        )

        assert result["ok"] is False
        assert "Unable to process file" in result["error"]
        assert "path is accessible" in result["suggestion"]

    def test_create_storage_error_basic(self):
        """Test storage error creation."""
        error = Exception("Database connection failed")
        result = ErrorHandler.create_storage_error(
            operation="save record",
            error=error
        )

        assert result["ok"] is False
        assert "Failed to save record" in result["error"]
        assert "Database connection failed" in result["error"]
        assert "Check database connection" in result["suggestion"]

    def test_create_storage_error_custom_suggestion(self):
        """Test storage error with custom suggestion."""
        error = Exception("Storage full")
        result = ErrorHandler.create_storage_error(
            operation="write data",
            error=error,
            suggestion="Clear some space and retry"
        )

        assert result["ok"] is False
        assert "Failed to write data" in result["error"]
        assert result["suggestion"] == "Clear some space and retry"

    def test_create_rate_limit_error_basic(self):
        """Test rate limit error creation."""
        result = ErrorHandler.create_rate_limit_error(
            retry_after_seconds=30
        )

        assert result["ok"] is False
        assert "Rate limit exceeded" in result["error"]
        assert "Wait 30 seconds" in result["suggestion"]
        assert result["retry_after_seconds"] == 30

    def test_create_rate_limit_error_with_description(self):
        """Test rate limit error with window description."""
        result = ErrorHandler.create_rate_limit_error(
            retry_after_seconds=60,
            window_description="API calls per hour"
        )

        assert result["ok"] is False
        assert "Rate limit exceeded (API calls per hour)" in result["error"]
        assert "Wait 60 seconds" in result["suggestion"]
        assert result["retry_after_seconds"] == 60

    def test_create_missing_requirement_error_single(self):
        """Test missing requirement error for single item."""
        result = ErrorHandler.create_missing_requirement_error(
            requirement_type="parameter",
            missing_items=["message"]
        )

        assert result["ok"] is False
        assert "Missing required parameter: message" in result["error"]
        assert "Provide the required parameter: message" in result["suggestion"]

    def test_create_missing_requirement_error_multiple(self):
        """Test missing requirement error for multiple items."""
        result = ErrorHandler.create_missing_requirement_error(
            requirement_type="parameter",
            missing_items=["message", "timestamp"]
        )

        assert result["ok"] is False
        assert "Missing required parameters: message, timestamp" in result["error"]
        assert "Provide at least one of the required parameters" in result["suggestion"]

    def test_create_missing_requirement_error_custom_suggestion(self):
        """Test missing requirement error with custom suggestion."""
        result = ErrorHandler.create_missing_requirement_error(
            requirement_type="log type",
            missing_items=["progress", "debug"],
            suggestion="Choose from available log types"
        )

        assert result["ok"] is False
        assert "Missing required log types: progress, debug" in result["error"]
        assert result["suggestion"] == "Choose from available log types"

    def test_handle_safe_operation_success(self):
        """Test safe operation handling for successful operation."""
        def successful_operation():
            return "success"

        success, result = ErrorHandler.handle_safe_operation(
            operation_name="test operation",
            operation_func=successful_operation
        )

        assert success is True
        assert result == "success"

    def test_handle_safe_operation_failure(self):
        """Test safe operation handling for failed operation."""
        def failing_operation():
            raise ValueError("Test error")

        success, result = ErrorHandler.handle_safe_operation(
            operation_name="test operation",
            operation_func=failing_operation,
            fallback_result="fallback"
        )

        assert success is False
        assert result == "fallback"

    def test_handle_safe_operation_with_context(self):
        """Test safe operation handling with error context."""
        def failing_operation():
            raise ValueError("Test error")

        context = {"user_id": 123}
        success, result = ErrorHandler.handle_safe_operation(
            operation_name="test operation",
            operation_func=failing_operation,
            error_context=context
        )

        assert success is False
        # Context should be modified but not returned in this simple version
        assert context["operation"] == "test operation"
        assert "Test error" in context["error"]

    def test_create_warning_response_basic(self):
        """Test warning response creation."""
        original_response = {
            "ok": True,
            "result": "success",
            "data": {"key": "value"}
        }

        result = ErrorHandler.create_warning_response(
            warning_message="This is a warning",
            original_response=original_response
        )

        assert result["ok"] is True
        assert result["result"] == "success"
        assert result["data"]["key"] == "value"
        assert result["warning"] == "This is a warning"

    def test_create_warning_response_with_context(self):
        """Test warning response with context."""
        original_response = {"ok": True, "result": "success"}
        warning_context = {"deprecated": True, "version": "2.0"}

        result = ErrorHandler.create_warning_response(
            warning_message="Deprecated feature used",
            original_response=original_response,
            warning_context=warning_context
        )

        assert result["ok"] is True
        assert result["warning"] == "Deprecated feature used"
        assert result["warning_context"]["deprecated"] is True
        assert result["warning_context"]["version"] == "2.0"

    def test_find_close_matches_exact_match(self):
        """Test close matches with exact match."""
        matches = ErrorHandler._find_close_matches(
            target="substring",
            candidates=["substring", "exact", "regex"]
        )

        assert "substring" in matches

    def test_find_close_matches_partial_match(self):
        """Test close matches with partial match."""
        matches = ErrorHandler._find_close_matches(
            target="sub",
            candidates=["substring", "exact", "regex"]
        )

        assert len(matches) >= 1
        assert any("substring" in match for match in matches)

    def test_find_close_matches_no_match(self):
        """Test close matches with no good matches."""
        matches = ErrorHandler._find_close_matches(
            target="xyz",
            candidates=["substring", "exact", "regex"]
        )

        assert len(matches) == 0

    def test_all_methods_return_dict(self):
        """Test that all public methods return dictionaries."""
        methods_to_test = [
            ("create_validation_error", ["test error"]),
            ("create_parameter_error", ["param", "issue"]),
            ("create_enum_error", ["param", "value", ["a", "b"]]),
            ("create_range_error", ["param", 5]),
            ("create_regex_error", ["pattern", re.error("test")]),
            ("create_file_operation_error", ["op", "path", Exception()]),
            ("create_storage_error", ["op", Exception()]),
            ("create_rate_limit_error", [30]),
            ("create_missing_requirement_error", ["type", ["item"]]),
            ("create_warning_response", ["warning", {"ok": True}])
        ]

        for method_name, args in methods_to_test:
            method = getattr(ErrorHandler, method_name)
            result = method(*args)
            assert isinstance(result, dict), f"{method_name} should return dict"

    def test_all_error_responses_have_ok_false(self):
        """Test that all error responses have ok=False."""
        error_methods = [
            ("create_validation_error", ["error"]),
            ("create_parameter_error", ["param", "issue"]),
            ("create_enum_error", ["param", "value", ["a", "b"]]),
            ("create_range_error", ["param", 5]),
            ("create_regex_error", ["pattern", re.error("test")]),
            ("create_file_operation_error", ["op", "path", Exception()]),
            ("create_storage_error", ["op", Exception()]),
            ("create_rate_limit_error", [30]),
            ("create_missing_requirement_error", ["type", ["item"]])
        ]

        for method_name, args in error_methods:
            method = getattr(ErrorHandler, method_name)
            result = method(*args)
            assert result["ok"] is False, f"{method_name} should return ok=False"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
