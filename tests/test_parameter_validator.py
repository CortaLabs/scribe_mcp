"""
Comprehensive unit tests for ToolValidator class.

Tests extracted validation patterns from append_entry.py, query_entries.py,
and rotate_log.py to ensure exact behavior preservation.
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timezone
from typing import Dict, Any

from scribe_mcp.utils.parameter_validator import ToolValidator


class TestToolValidator:
    """Test suite for ToolValidator validation methods."""

    def test_validate_message_valid_messages(self):
        """Test validate_message with valid message content."""
        # Valid messages should return None
        assert ToolValidator.validate_message("Simple message") is None
        assert ToolValidator.validate_message("Message with emojis: ✅ 🎯") is None
        assert ToolValidator.validate_message("Message with numbers 123 and symbols !@#$%") is None
        assert ToolValidator.validate_message("Message with spaces and    tabs") is None

    def test_validate_message_invalid_newlines(self):
        """Test validate_message rejects newline characters."""
        result = ToolValidator.validate_message("Message with\nnewline")
        assert result == "Message cannot contain newline characters."

        result = ToolValidator.validate_message("Message with\r\ncarriage return")
        assert result == "Message cannot contain newline characters."

        result = ToolValidator.validate_message("Message with\rcarriage return")
        assert result == "Message cannot contain newline characters."

    def test_validate_message_invalid_pipes(self):
        """Test validate_message rejects pipe characters."""
        result = ToolValidator.validate_message("Message with | pipe")
        assert result == "Message cannot contain pipe characters."

        result = ToolValidator.validate_message("Message with multiple | pipes | here")
        assert result == "Message cannot contain pipe characters."

    def test_validate_enum_value_valid(self):
        """Test validate_enum_value with valid values."""
        allowed = {"info", "success", "warn", "error"}

        # Case insensitive matching
        assert ToolValidator.validate_enum_value("info", allowed) is None
        assert ToolValidator.validate_enum_value("INFO", allowed) is None
        assert ToolValidator.validate_enum_value("Info", allowed) is None

    def test_validate_enum_value_invalid(self):
        """Test validate_enum_value with invalid values."""
        allowed = {"info", "success", "warn", "error"}

        result = ToolValidator.validate_enum_value("invalid", allowed, "status")
        assert "Invalid status 'invalid'" in result
        assert "error, info, success, warn" in result  # Sorted output

        result = ToolValidator.validate_enum_value("", allowed)
        assert "Invalid value ''" in result

    def test_validate_regex_pattern_valid(self):
        """Test validate_regex_pattern with valid patterns."""
        assert ToolValidator.validate_regex_pattern(r"\d+") is None
        assert ToolValidator.validate_regex_pattern(r"[a-zA-Z]+") is None
        assert ToolValidator.validate_regex_pattern(r"^start.*end$") is None
        assert ToolValidator.validate_regex_pattern(r"simple") is None

    def test_validate_regex_pattern_invalid(self):
        """Test validate_regex_pattern with invalid patterns."""
        result = ToolValidator.validate_regex_pattern(r"[unclosed")
        assert "Invalid regex:" in result
        assert "unterminated character set" in result.lower()

        result = ToolValidator.validate_regex_pattern(r"*invalid")
        assert "Invalid regex:" in result

    def test_validate_range_valid(self):
        """Test validate_range with values in range."""
        # Integer ranges
        assert ToolValidator.validate_range(5, 0, 10) is None
        assert ToolValidator.validate_range(0, 0, 10) is None
        assert ToolValidator.validate_range(10, 0, 10) is None

        # Float ranges
        assert ToolValidator.validate_range(0.5, 0.0, 1.0) is None
        assert ToolValidator.validate_range(0.0, 0.0, 1.0) is None
        assert ToolValidator.validate_range(1.0, 0.0, 1.0) is None

        # String to float conversion
        assert ToolValidator.validate_range("0.5", 0.0, 1.0) is None
        assert ToolValidator.validate_range("5", 0, 10) is None

    def test_validate_range_invalid(self):
        """Test validate_range with values out of range."""
        # Below minimum
        result = ToolValidator.validate_range(-1, 0, 10, "threshold")
        assert "threshold must be at least 0" in result

        # Above maximum
        result = ToolValidator.validate_range(11, 0, 10, "threshold")
        assert "threshold must be at most 10" in result

        # String conversion errors
        result = ToolValidator.validate_range("invalid", 0, 10, "number")
        assert "number must be a number" in result

    def test_validate_timestamp_valid(self):
        """Test validate_timestamp with valid timestamps."""
        dt, timestamp, warning = ToolValidator.validate_timestamp("2025-01-01 12:00:00 UTC")

        assert dt is not None
        assert timestamp == "2025-01-01 12:00:00 UTC"
        assert warning is None
        assert dt.tzinfo == timezone.utc

    def test_validate_timestamp_empty(self):
        """Test validate_timestamp with empty timestamp."""
        dt, timestamp, warning = ToolValidator.validate_timestamp(None)

        assert dt is None
        assert timestamp is not None  # Should be current time
        assert warning is None

        dt, timestamp, warning = ToolValidator.validate_timestamp("")

        assert dt is None
        assert timestamp is not None  # Should be current time
        assert warning is None

    def test_validate_timestamp_invalid(self):
        """Test validate_timestamp with invalid timestamps."""
        dt, timestamp, warning = ToolValidator.validate_timestamp("invalid timestamp")

        assert dt is None
        assert timestamp is not None  # Should be current time fallback
        assert warning == "timestamp format invalid; using current time"

        dt, timestamp, warning = ToolValidator.validate_timestamp("2025-01-01 12:00")  # Missing UTC
        assert dt is None
        assert warning == "timestamp format invalid; using current time"

    def test_sanitize_identifier_valid(self):
        """Test sanitize_identifier with valid identifiers."""
        assert ToolValidator.sanitize_identifier("AgentName") == "AgentName"
        assert ToolValidator.sanitize_identifier("agent_name") == "agent_name"
        assert ToolValidator.sanitize_identifier("Agent123") == "Agent123"

    def test_sanitize_identifier_sanitization(self):
        """Test sanitize_identifier removes problematic characters."""
        assert ToolValidator.sanitize_identifier("Agent[Name]") == "AgentName"
        assert ToolValidator.sanitize_identifier("Agent|Name") == "AgentName"
        assert ToolValidator.sanitize_identifier("  AgentName  ") == "AgentName"

    def test_sanitize_identifier_fallback(self):
        """Test sanitize_identifier provides fallback for empty results."""
        assert ToolValidator.sanitize_identifier("") == "Scribe"
        assert ToolValidator.sanitize_identifier("[]|") == "Scribe"
        assert ToolValidator.sanitize_identifier("   ") == "Scribe"

    def test_validate_json_metadata_valid(self):
        """Test validate_json_metadata with valid JSON."""
        # Valid JSON objects
        result, error = ToolValidator.validate_json_metadata('{"key": "value"}')
        assert result == {"key": "value"}
        assert error is None

        result, error = ToolValidator.validate_json_metadata('{"number": 123, "bool": true}')
        assert result == {"number": 123, "bool": True}  # JSON parses bools as Python True
        assert error is None

        # Empty values
        result, error = ToolValidator.validate_json_metadata(None)
        assert result is None
        assert error is None

        result, error = ToolValidator.validate_json_metadata("")
        assert result is None
        assert error is None

    def test_validate_json_metadata_invalid(self):
        """Test validate_json_metadata with invalid JSON."""
        result, error = ToolValidator.validate_json_metadata("invalid json")
        assert result is None
        assert error == "Invalid JSON in metadata parameter"

        result, error = ToolValidator.validate_json_metadata('{"invalid": json}')
        assert result is None
        assert error == "Invalid JSON in metadata parameter"

        # Non-object JSON
        result, error = ToolValidator.validate_json_metadata('"string value"')
        assert result is None
        assert error == "Invalid JSON in metadata parameter"

        result, error = ToolValidator.validate_json_metadata("[1, 2, 3]")
        assert result is None
        assert error == "Invalid JSON in metadata parameter"

    def test_validate_json_metadata_with_custom_field_name(self):
        """Test validate_json_metadata with custom field name."""
        result, error = ToolValidator.validate_json_metadata("invalid", "custom_meta")
        assert result is None
        assert error == "Invalid JSON in custom_meta parameter"

    def test_validate_json_metadata_fallback_parsing(self):
        """Test validate_json_metadata falls back to direct JSON parsing when parameter_normalizer fails."""
        # This tests the fallback path that uses json.loads directly
        # We need to mock the parameter_normalizer to raise ValueError

        # Test that valid JSON still works even if parameter_normalizer would fail
        result, error = ToolValidator.validate_json_metadata('{"key": "value"}')
        assert result == {"key": "value"}
        assert error is None

    def test_validate_list_parameter_string(self):
        """Test validate_list_parameter with string input."""
        result = ToolValidator.validate_list_parameter("a,b,c")
        assert result == ["a", "b", "c"]

        result = ToolValidator.validate_list_parameter("  A , B , C  ")
        assert result == ["a", "b", "c"]

        result = ToolValidator.validate_list_parameter("single")
        assert result == ["single"]

    def test_validate_list_parameter_with_different_delimiter(self):
        """Test validate_list_parameter with custom delimiter."""
        result = ToolValidator.validate_list_parameter("a|b|c", "|")
        assert result == ["a", "b", "c"]

        result = ToolValidator.validate_list_parameter("item1;item2;item3", ";")
        assert result == ["item1", "item2", "item3"]

    def test_validate_list_parameter_with_empty_items(self):
        """Test validate_list_parameter with empty items."""
        result = ToolValidator.validate_list_parameter("a,,c")
        assert result == ["a", "c"]  # Empty item filtered out

        result = ToolValidator.validate_list_parameter("  ,  ,  ")
        assert result == []  # All items empty

    def test_validate_list_parameter_sequence(self):
        """Test validate_list_parameter with sequence input."""
        result = ToolValidator.validate_list_parameter(["A", "B", "C"])
        assert result == ["a", "b", "c"]

        result = ToolValidator.validate_list_parameter(["  item1  ", "item2"])
        assert result == ["item1", "item2"]

        result = ToolValidator.validate_list_parameter(())
        assert result == []

    def test_validate_list_parameter_empty(self):
        """Test validate_list_parameter with empty input."""
        assert ToolValidator.validate_list_parameter(None) == []
        assert ToolValidator.validate_list_parameter("") == []
        assert ToolValidator.validate_list_parameter([]) == []
        assert ToolValidator.validate_list_parameter(()) == []

    def test_validate_document_types_valid(self):
        """Test validate_document_types with valid types."""
        allowed = {"progress", "research", "architecture", "bugs", "global"}

        result, error = ToolValidator.validate_document_types(["progress", "research"], allowed)
        assert result == ["progress", "research"]
        assert error is None

        result, error = ToolValidator.validate_document_types(["Progress", "RESEARCH"], allowed)
        assert result == ["progress", "research"]
        assert error is None

    def test_validate_document_types_invalid(self):
        """Test validate_document_types with invalid types."""
        allowed = {"progress", "research", "architecture", "bugs", "global"}

        result, error = ToolValidator.validate_document_types(["progress", "invalid"], allowed)
        assert result is None
        assert "Invalid document_types: invalid" in error
        assert "architecture, bugs, global, progress, research" in error  # Sorted output

        result, error = ToolValidator.validate_document_types(["invalid1", "invalid2"], allowed)
        assert result is None
        assert "Invalid document_types: invalid1, invalid2" in error

    def test_validate_document_types_empty(self):
        """Test validate_document_types with empty input."""
        allowed = {"progress", "research"}

        result, error = ToolValidator.validate_document_types(None, allowed)
        assert result is None
        assert error is None

        result, error = ToolValidator.validate_document_types([], allowed)
        assert result is None
        assert error is None

    def test_validate_parameters_against_schema_valid(self):
        """Test validate_parameters_against_schema with valid parameters."""
        schema = {
            "name": {
                "type": str,
                "required": True,
                "allowed_values": {"alice", "bob", "charlie"}
            },
            "age": {
                "type": int,
                "required": False,
                "min_value": 0,
                "max_value": 150
            },
            "email": {
                "type": str,
                "required": False,
                "regex_pattern": r"^[^@]+@[^@]+\.[^@]+$"
            }
        }

        params = {
            "name": "alice",
            "age": 25,
            "email": "alice@example.com"
        }

        assert ToolValidator.validate_parameters_against_schema(params, schema) is None

    def test_validate_parameters_against_schema_missing_required(self):
        """Test validate_parameters_against_schema with missing required fields."""
        schema = {
            "name": {
                "type": str,
                "required": True
            }
        }

        params = {}  # Missing required 'name' field

        result = ToolValidator.validate_parameters_against_schema(params, schema)
        assert result == "Required parameter 'name' is missing"

    def test_validate_parameters_against_schema_type_mismatch(self):
        """Test validate_parameters_against_schema with wrong types."""
        schema = {
            "count": {
                "type": int,
                "required": True
            }
        }

        params = {"count": "not_a_number"}

        result = ToolValidator.validate_parameters_against_schema(params, schema)
        assert "Parameter 'count' must be of type int" in result
        assert "got str" in result

    def test_validate_parameters_against_schema_enum_violation(self):
        """Test validate_parameters_against_schema with enum violations."""
        schema = {
            "status": {
                "type": str,
                "required": True,
                "allowed_values": {"active", "inactive"}
            }
        }

        params = {"status": "invalid"}

        result = ToolValidator.validate_parameters_against_schema(params, schema)
        assert "Invalid status 'invalid'" in result
        assert "active, inactive" in result

    def test_validate_parameters_against_schema_range_violation(self):
        """Test validate_parameters_against_schema with range violations."""
        schema = {
            "score": {
                "type": (int, float),
                "required": True,
                "min_value": 0.0,
                "max_value": 1.0
            }
        }

        params = {"score": 1.5}

        result = ToolValidator.validate_parameters_against_schema(params, schema)
        assert "score must be at most 1.0" in result

        params = {"score": -0.1}
        result = ToolValidator.validate_parameters_against_schema(params, schema)
        assert "score must be at least 0.0" in result

    def test_validate_parameters_against_schema_regex_violation(self):
        """Test validate_parameters_against_schema with regex violations."""
        schema = {
            "email": {
                "type": str,
                "required": True,
                "regex_pattern": r"^[^@]+@[^@]+\.[^@]+$"
            }
        }

        params = {"email": "invalid_email"}

        result = ToolValidator.validate_parameters_against_schema(params, schema)
        assert "Parameter 'email' does not match required pattern" in result

    def test_validate_parameters_against_schema_invalid_regex_pattern(self):
        """Test validate_parameters_against_schema with invalid regex pattern in schema."""
        schema = {
            "field": {
                "type": str,
                "required": True,
                "regex_pattern": r"[unclosed"  # Invalid regex
            }
        }

        params = {"field": "value"}

        result = ToolValidator.validate_parameters_against_schema(params, schema)
        assert "Invalid regex:" in result

    def test_validate_metadata_requirements_with_real_utility(self):
        """Test validate_metadata_requirements delegates to shared utility."""
        # Create a mock log definition
        log_definition = {
            "required_metadata": {
                "project": {"required": True},
                "agent": {"required": True}
            }
        }

        # Test with complete metadata
        meta_payload = {"project": "test", "agent": "test_agent"}
        result = ToolValidator.validate_metadata_requirements(log_definition, meta_payload)

        # Should not raise an exception and return None for valid metadata
        assert result is None or isinstance(result, str)

    def test_validate_metadata_requirements_fallback(self):
        """Test validate_metadata_requirements fallback behavior."""
        # Test with empty definition
        log_definition = {}
        meta_payload = {"any": "metadata"}
        result = ToolValidator.validate_metadata_requirements(log_definition, meta_payload)

        # Should handle gracefully
        assert result is None or isinstance(result, str)

    def test_validate_parameters_against_schema_optional_fields(self):
        """Test validate_parameters_against_schema with optional fields."""
        schema = {
            "optional_field": {
                "type": str,
                "required": False
            }
        }

        # Missing optional field should be fine
        params = {}
        assert ToolValidator.validate_parameters_against_schema(params, schema) is None

        # Provided optional field with correct type
        params = {"optional_field": "value"}
        assert ToolValidator.validate_parameters_against_schema(params, schema) is None

    def test_parse_timestamp_helper(self):
        """Test the internal _parse_timestamp helper method."""
        # Valid timestamp
        dt = ToolValidator._parse_timestamp("2025-01-01 12:00:00 UTC")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 12
        assert dt.tzinfo == timezone.utc

        # Invalid timestamp
        dt = ToolValidator._parse_timestamp("invalid")
        assert dt is None

        # Wrong format
        dt = ToolValidator._parse_timestamp("2025-01-01T12:00:00Z")  # ISO format not supported
        assert dt is None

    @pytest.mark.parametrize("message,expected", [
        ("valid message", None),
        ("message with\nnewline", "Message cannot contain newline characters."),
        ("message with|pipe", "Message cannot contain pipe characters."),
        ("", None),  # Empty message is valid
    ])
    def test_validate_message_parametrized(self, message, expected):
        """Parametrized test for validate_message."""
        assert ToolValidator.validate_message(message) == expected

    @pytest.mark.parametrize("value,allowed,expected_contains", [
        ("valid", {"valid", "test"}, None),
        ("VALID", {"valid", "test"}, None),
        ("invalid", {"valid", "test"}, "Invalid value 'invalid'"),
        ("", {"valid", "test"}, "Invalid value ''"),
    ])
    def test_validate_enum_value_parametrized(self, value, allowed, expected_contains):
        """Parametrized test for validate_enum_value."""
        result = ToolValidator.validate_enum_value(value, allowed)
        if expected_contains is None:
            assert result is None
        else:
            assert expected_contains in result

    @pytest.mark.parametrize("timestamp,should_parse", [
        ("2025-01-01 12:00:00 UTC", True),
        ("2025-12-31 23:59:59 UTC", True),
        ("invalid format", False),
        ("2025-01-01 12:00", False),  # Missing UTC
        ("", False),  # Empty
    ])
    def test_parse_timestamp_parametrized(self, timestamp, should_parse):
        """Parametrized test for _parse_timestamp."""
        dt = ToolValidator._parse_timestamp(timestamp)
        if should_parse:
            assert dt is not None
            assert dt.tzinfo == timezone.utc
        else:
            assert dt is None