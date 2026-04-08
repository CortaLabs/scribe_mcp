"""Comprehensive tests for ConfigManager utilities.

Tests cover all extracted configuration management patterns to ensure
backward compatibility and correct functionality.
"""

import pytest
import tempfile
import json
from pathlib import Path
from typing import Any, Dict

from scribe_mcp.utils.config_manager import (
    ConfigManager,
    apply_parameter_defaults,
    resolve_fallback_chain,
    validate_enum_value,
    validate_range,
    build_response_payload,
    apply_response_defaults,
)


class TestConfigManager:
    """Test suite for ConfigManager class and its utilities."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config_manager = ConfigManager("test")

    def test_apply_parameter_defaults_basic(self):
        """Test basic parameter defaults application."""
        params = {"param1": "value1", "param2": None}
        defaults = {"param1": "default1", "param2": "default2", "param3": "default3"}

        result = self.config_manager.apply_parameter_defaults(params, defaults)

        assert result["param1"] == "value1"  # Preserved original
        assert result["param2"] == "default2"  # None replaced with default
        assert result["param3"] == "default3"  # Added default

    def test_apply_parameter_defaults_with_required_keys(self):
        """Test parameter defaults with required keys validation."""
        params = {"param1": "value1"}
        defaults = {"param2": "default2"}
        required_keys = ["param1", "param2"]

        result = self.config_manager.apply_parameter_defaults(params, defaults, required_keys)

        assert result["param1"] == "value1"
        assert result["param2"] == "default2"

    def test_apply_parameter_defaults_missing_required(self):
        """Test parameter defaults with missing required keys."""
        params = {"param1": "value1"}
        defaults = {"param2": "default2"}
        required_keys = ["param1", "param3"]  # param3 is missing

        with pytest.raises(ValueError, match="Missing required parameters: param3"):
            self.config_manager.apply_parameter_defaults(params, defaults, required_keys)

    def test_resolve_fallback_chain_basic(self):
        """Test basic fallback chain resolution."""
        result = resolve_fallback_chain(None, None, "default")
        assert result == "default"

        result = resolve_fallback_chain("value", None, "default")
        assert result == "value"

        result = resolve_fallback_chain(None, "fallback", "default")
        assert result == "fallback"

    def test_resolve_fallback_chain_with_none_and_empty(self):
        """Test fallback chain with None and empty values."""
        # Empty string should be returned (not treated as falsy)
        result = resolve_fallback_chain("", "fallback", "default")
        assert result == ""

        # Zero should be returned (not treated as falsy)
        result = resolve_fallback_chain(0, "fallback", "default")
        assert result == 0

        # False should be returned (not treated as falsy)
        result = resolve_fallback_chain(False, "fallback", "default")
        assert result is False

    def test_merge_project_settings_basic(self):
        """Test basic project settings merging."""
        project_config = {
            "name": "test_project",
            "defaults": {"agent": "TestAgent", "emoji": "🧪"}
        }
        tool_defaults = {"agent": "ToolAgent", "timeout": 30}

        result = self.config_manager.merge_project_settings(project_config, tool_defaults)

        assert result["name"] == "test_project"
        assert result["defaults"]["agent"] == "TestAgent"  # Project defaults win
        assert result["defaults"]["emoji"] == "🧪"
        assert result["defaults"]["timeout"] == 30  # Tool defaults added

    def test_merge_project_settings_no_defaults(self):
        """Test project settings merging with no existing defaults."""
        project_config = {"name": "test_project"}
        tool_defaults = {"agent": "ToolAgent", "timeout": 30}

        result = self.config_manager.merge_project_settings(project_config, tool_defaults)

        assert result["name"] == "test_project"
        assert result["defaults"]["agent"] == "ToolAgent"
        assert result["defaults"]["timeout"] == 30

    def test_validate_enum_value_valid(self):
        """Test enum validation with valid values."""
        allowed = ["option1", "option2", "option3"]

        result = self.config_manager.validate_enum_value("option1", allowed, "test_param")
        assert result == "option1"

        result = self.config_manager.validate_enum_value("OPTION1", allowed, "test_param")
        assert result == "option1"  # Should be lowercase

    def test_validate_enum_value_invalid(self):
        """Test enum validation with invalid values."""
        allowed = ["option1", "option2", "option3"]

        with pytest.raises(ValueError, match="Invalid test_param 'invalid'"):
            self.config_manager.validate_enum_value("invalid", allowed, "test_param")

    def test_validate_enum_value_non_string(self):
        """Test enum validation with non-string input."""
        allowed = ["option1", "option2", "option3"]

        with pytest.raises(ValueError, match="test_param must be a string"):
            self.config_manager.validate_enum_value(123, allowed, "test_param")

    def test_validate_range_valid_int(self):
        """Test range validation with valid integers."""
        result = self.config_manager.validate_range(5, min_val=0, max_val=10, param_name="test")
        assert result == 5

        result = self.config_manager.validate_range("5", min_val=0, max_val=10, param_name="test")
        assert result == 5

    def test_validate_range_valid_float(self):
        """Test range validation with valid floats."""
        result = self.config_manager.validate_range(0.5, min_val=0.0, max_val=1.0, param_name="test")
        assert result == 0.5

        result = self.config_manager.validate_range("0.5", min_val=0.0, max_val=1.0, param_name="test")
        assert result == 0.5

    def test_validate_range_out_of_bounds(self):
        """Test range validation with out-of-bounds values."""
        with pytest.raises(ValueError, match="test must be >= 0"):
            self.config_manager.validate_range(-5, min_val=0, max_val=10, param_name="test")

        with pytest.raises(ValueError, match="test must be <= 10"):
            self.config_manager.validate_range(15, min_val=0, max_val=10, param_name="test")

    def test_validate_range_invalid_string(self):
        """Test range validation with invalid string values."""
        with pytest.raises(ValueError, match="test must be numeric"):
            self.config_manager.validate_range("invalid", min_val=0, max_val=10, param_name="test")

    def test_build_response_payload_basic(self):
        """Test basic response payload building."""
        base = {"ok": True, "message": "base"}
        updates = {"data": "value", "ok": False}

        result = self.config_manager.build_response_payload(base, **updates)

        assert result["ok"] is False  # Should be ANDed
        assert result["message"] == "base"
        assert result["data"] == "value"

    def test_build_response_payload_ok_override(self):
        """Test response payload building with ok override logic."""
        base = {"ok": True}
        updates = {"ok": True}

        result = self.config_manager.build_response_payload(base, **updates)
        assert result["ok"] is True

        base = {"ok": True}
        updates = {"ok": False}

        result = self.config_manager.build_response_payload(base, **updates)
        assert result["ok"] is False

        base = {"ok": False}
        updates = {"ok": True}

        result = self.config_manager.build_response_payload(base, **updates)
        assert result["ok"] is False  # Should preserve False

    def test_apply_response_defaults_basic(self):
        """Test basic response defaults application."""
        payload = {"message": "test"}
        defaults = {"suggestion": "try again", "retry": True}

        result = self.config_manager.apply_response_defaults(payload, defaults)

        assert result["message"] == "test"
        assert result["suggestion"] == "try again"
        assert result["retry"] is True
        assert result["ok"] is False  # Standard default
        assert result["reminders"] == []  # Standard default

    def test_apply_response_defaults_no_overwrite(self):
        """Test response defaults don't overwrite existing values."""
        payload = {"ok": True, "reminders": ["existing"]}
        defaults = {"ok": False, "reminders": ["default"]}

        result = self.config_manager.apply_response_defaults(payload, defaults)

        assert result["ok"] is True  # Preserved
        assert result["reminders"] == ["existing"]  # Preserved

    def test_normalize_json_parameter_dict(self):
        """Test JSON parameter normalization with dict input."""
        param = {"key": "value"}
        result = self.config_manager.normalize_json_parameter(param, "test")
        assert result == param

    def test_normalize_json_parameter_string(self):
        """Test JSON parameter normalization with JSON string."""
        param = '{"key": "value"}'
        result = self.config_manager.normalize_json_parameter(param, "test")
        assert result == {"key": "value"}

    def test_normalize_json_parameter_invalid_json(self):
        """Test JSON parameter normalization with invalid JSON."""
        param = '{"invalid": json}'
        with pytest.raises(ValueError):
            self.config_manager.normalize_json_parameter(param, "test")

    def test_normalize_json_parameter_none(self):
        """Test JSON parameter normalization with None."""
        result = self.config_manager.normalize_json_parameter(None, "test")
        assert result is None

    def test_create_template_context_basic(self):
        """Test basic template context creation."""
        result = self.config_manager.create_template_context(
            "test_project",
            author="TestAuthor",
            extra="value"
        )

        assert result["project_name"] == "test_project"
        assert result["author"] == "TestAuthor"
        assert result["extra"] == "value"

    def test_create_template_context_default_author(self):
        """Test template context creation with default author."""
        result = self.config_manager.create_template_context("test_project")

        assert result["project_name"] == "test_project"
        assert result["author"] == "Scribe"  # Default value

    def test_load_config_with_cache_file_exists(self):
        """Test configuration loading with caching when file exists."""
        config_data = {"key": "value", "number": 42}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            result = self.config_manager.load_config_with_cache(config_path)
            assert result == config_data

            # Second call should use cache
            result2 = self.config_manager.load_config_with_cache(config_path)
            assert result2 == config_data
        finally:
            config_path.unlink()

    def test_load_config_with_cache_file_not_exists(self):
        """Test configuration loading when file doesn't exist."""
        config_data = {"key": "default"}

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "nonexistent.json"

            result = self.config_manager.load_config_with_cache(config_path, config_data)
            assert result == config_data

            # File should be created
            assert config_path.exists()

    def test_load_config_with_cache_invalid_json(self):
        """Test configuration loading with invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"invalid": json}')
            config_path = Path(f.name)

        try:
            result = self.config_manager.load_config_with_cache(config_path, {"fallback": True})
            assert result == {"fallback": True}
        finally:
            config_path.unlink()

    def test_validate_and_normalize_list_string(self):
        """Test list validation and normalization with string input."""
        result = self.config_manager.validate_and_normalize_list("item1,item2,item3")
        assert result == ["item1", "item2", "item3"]

        result = self.config_manager.validate_and_normalize_list("item1, item2 , item3")
        assert result == ["item1", "item2", "item3"]

    def test_validate_and_normalize_list_list(self):
        """Test list validation and normalization with list input."""
        result = self.config_manager.validate_and_normalize_list(["item1", "item2", "item3"])
        assert result == ["item1", "item2", "item3"]

    def test_validate_and_normalize_list_none(self):
        """Test list validation and normalization with None input."""
        result = self.config_manager.validate_and_normalize_list(None)
        assert result == []

    def test_apply_configuration_overrides_all_allowed(self):
        """Test configuration overrides with all allowed."""
        base = {"key1": "value1", "key2": "value2"}
        overrides = {"key1": "new1", "key3": "new3"}

        result = self.config_manager.apply_configuration_overrides(base, overrides)

        assert result["key1"] == "new1"  # Overridden
        assert result["key2"] == "value2"  # Preserved
        assert result["key3"] == "new3"  # Added

    def test_apply_configuration_overrides_with_allowlist(self):
        """Test configuration overrides with allowed keys list."""
        base = {"key1": "value1", "key2": "value2"}
        overrides = {"key1": "new1", "key2": "new2", "key3": "new3"}
        allowed = ["key1", "key3"]

        result = self.config_manager.apply_configuration_overrides(base, overrides, allowed)

        assert result["key1"] == "new1"  # Allowed override
        assert result["key2"] == "value2"  # Not allowed, preserved
        assert "key3" not in result  # Not allowed, not added


class TestConvenienceFunctions:
    """Test suite for global convenience functions."""

    def test_apply_parameter_defaults_function(self):
        """Test global apply_parameter_defaults function."""
        params = {"param1": "value1"}
        defaults = {"param1": "default1", "param2": "default2"}

        result = apply_parameter_defaults(params, defaults)
        assert result["param1"] == "value1"
        assert result["param2"] == "default2"

    def test_resolve_fallback_chain_function(self):
        """Test global resolve_fallback_chain function."""
        result = resolve_fallback_chain(None, "fallback", "default")
        assert result == "fallback"

    def test_validate_enum_value_function(self):
        """Test global validate_enum_value function."""
        result = validate_enum_value("option1", ["option1", "option2"], "test")
        assert result == "option1"

    def test_validate_range_function(self):
        """Test global validate_range function."""
        result = validate_range(5, min_val=0, max_val=10, param_name="test")
        assert result == 5

    def test_build_response_payload_function(self):
        """Test global build_response_payload function."""
        base = {"message": "test"}
        result = build_response_payload(base, data="value")
        assert result["message"] == "test"
        assert result["data"] == "value"

    def test_apply_response_defaults_function(self):
        """Test global apply_response_defaults function."""
        payload = {"message": "test"}
        result = apply_response_defaults(payload)
        assert result["message"] == "test"
        assert result["ok"] is False
        assert result["reminders"] == []


if __name__ == "__main__":
    pytest.main([__file__])