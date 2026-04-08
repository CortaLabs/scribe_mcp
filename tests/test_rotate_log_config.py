"""
Comprehensive unit tests for RotateLogConfig configuration class.

Tests cover all aspects of the RotateLogConfig class including:
- Parameter validation using Phase 1 utilities
- Configuration normalization and defaults
- Business logic validation for rotation scenarios
- Error handling and edge cases
- Backward compatibility methods
- Factory methods for common scenarios

Phase 2 Task 2.3 - Configuration Objects implementation.
"""

import pytest
from typing import Any, Dict, List, Optional

from scribe_mcp.tools.config.rotate_log_config import (
    RotateLogConfig,
    create_rotate_log_config,
    validate_rotate_log_params
)


class TestRotateLogConfigBasics:
    """Test basic RotateLogConfig functionality."""

    def test_default_configuration(self):
        """Test default configuration values."""
        config = RotateLogConfig(
            log_type="progress"  # Must specify at least one log selection
        )

        assert config.suffix is None
        assert config.custom_metadata is None
        assert config.confirm is False
        assert config.dry_run is True  # Should default to True when confirm=False
        assert config.dry_run_mode == "estimate"
        assert config.log_type == "progress"
        assert config.log_types is None
        assert config.rotate_all is False
        assert config.auto_threshold is False
        assert config.threshold_entries == 500

    def test_post_initialization_validation(self):
        """Test that validation runs during initialization."""
        # Valid configuration should not raise
        config = RotateLogConfig(
            log_type="progress",
            confirm=True
        )
        assert config.log_type == "progress"
        assert config.confirm == True

    def test_invalid_dry_run_mode(self):
        """Test validation of dry_run_mode parameter."""
        with pytest.raises(ValueError, match="Invalid dry_run_mode"):
            RotateLogConfig(dry_run_mode="invalid_mode")

    def test_invalid_custom_metadata(self):
        """Test validation of custom_metadata parameter."""
        with pytest.raises(ValueError, match="Invalid custom_metadata"):
            RotateLogConfig(custom_metadata="invalid json {")

    def test_invalid_threshold_entries(self):
        """Test validation of threshold_entries parameter."""
        with pytest.raises(ValueError, match="threshold_entries must be greater than 0"):
            RotateLogConfig(threshold_entries=-1)

    def test_invalid_log_selection_combination(self):
        """Test validation of log selection parameter combinations."""
        with pytest.raises(ValueError, match="Cannot specify multiple log selection options"):
            RotateLogConfig(
                log_type="progress",
                log_types=["progress", "doc_updates"]
            )

        with pytest.raises(ValueError, match="Cannot specify multiple log selection options"):
            RotateLogConfig(
                rotate_all=True,
                log_type="progress"
            )

    def test_no_log_selection(self):
        """Test validation when no log selection is specified."""
        with pytest.raises(ValueError, match="Must specify one of"):
            RotateLogConfig()

    def test_invalid_suffix(self):
        """Test validation of suffix parameter."""
        with pytest.raises(ValueError, match="suffix cannot exceed 64 characters"):
            RotateLogConfig(
                suffix="x" * 65,  # Too long
                log_type="progress"
            )

    def test_invalid_bytes_per_line_bounds(self):
        """Test validation of bytes-per-line configuration bounds."""
        with pytest.raises(ValueError, match="default_bytes_per_line .* cannot be less than"):
            RotateLogConfig(
                log_type="progress",
                default_bytes_per_line=10.0,  # Less than min (16.0)
                min_bytes_per_line=16.0
            )

        with pytest.raises(ValueError, match="default_bytes_per_line .* cannot be greater than"):
            RotateLogConfig(
                log_type="progress",
                default_bytes_per_line=600.0,  # Greater than max (512.0)
                max_bytes_per_line=512.0
            )

    def test_invalid_estimation_band_ratio(self):
        """Test validation of estimation_band_ratio parameter."""
        with pytest.raises(ValueError, match="estimation_band_ratio must be between 0.0 and 1.0"):
            RotateLogConfig(
                log_type="progress",
                estimation_band_ratio=1.5
            )

        with pytest.raises(ValueError, match="estimation_band_ratio must be between 0.0 and 1.0"):
            RotateLogConfig(
                log_type="progress",
                estimation_band_ratio=0.0
            )

    def test_invalid_estimation_band_min(self):
        """Test validation of estimation_band_min parameter."""
        with pytest.raises(ValueError, match="estimation_band_min must be non-negative"):
            RotateLogConfig(
                log_type="progress",
                estimation_band_min=-1
            )


class TestRotateLogConfigNormalization:
    """Test parameter normalization functionality."""

    def test_dry_run_mode_normalization(self):
        """Test dry_run_mode normalization to lowercase."""
        config = RotateLogConfig(
            log_type="progress",
            dry_run_mode="ESTIMATE"
        )
        assert config.dry_run_mode == "estimate"

    def test_dry_run_mode_default(self):
        """Test dry_run_mode defaults to 'estimate'."""
        config = RotateLogConfig(
            log_type="progress",
            dry_run_mode=None
        )
        assert config.dry_run_mode == "estimate"

    def test_log_types_normalization(self):
        """Test log_types list normalization."""
        config = RotateLogConfig(
            log_types="progress,doc_updates,bugs",
            dry_run_mode="estimate"
        )
        assert config.log_types == ["progress", "doc_updates", "bugs"]

    def test_dry_run_default_from_confirm(self):
        """Test dry_run defaults based on confirm flag."""
        # When confirm=True, dry_run should default to False
        config = RotateLogConfig(
            log_type="progress",
            confirm=True,
            dry_run=None
        )
        assert config.dry_run is False

        # When confirm=False, dry_run should default to True
        config = RotateLogConfig(
            log_type="progress",
            confirm=False,
            dry_run=None
        )
        assert config.dry_run is True

    def test_threshold_entries_default(self):
        """Test threshold_entries gets default value."""
        config = RotateLogConfig(
            log_type="progress",
            threshold_entries=None
        )
        assert config.threshold_entries == 500


class TestRotateLogConfigMethods:
    """Test RotateLogConfig methods and utilities."""

    def test_to_dict(self):
        """Test conversion to dictionary format."""
        config = RotateLogConfig(
            suffix="test",
            log_type="progress",
            confirm=True,
            auto_threshold=True
        )

        result = config.to_dict()

        assert result["suffix"] == "test"
        assert result["log_type"] == "progress"
        assert result["confirm"] is True
        assert result["auto_threshold"] is True
        assert "dry_run" in result
        assert "dry_run_mode" in result

    def test_to_dict_omits_defaults(self):
        """Test to_dict omits default values."""
        config = RotateLogConfig(
            log_type="progress",
            threshold_entries=500  # This is the default value
        )

        result = config.to_dict()

        assert "threshold_entries" not in result  # Should be omitted as it's default

    def test_get_parsed_metadata(self):
        """Test parsing of custom_metadata."""
        config = RotateLogConfig(
            log_type="progress",
            custom_metadata='{"key": "value"}'
        )

        result = config.get_parsed_metadata()
        assert result == {"key": "value"}

    def test_get_parsed_metadata_none(self):
        """Test get_parsed_metadata returns None for no metadata."""
        config = RotateLogConfig(log_type="progress")

        result = config.get_parsed_metadata()
        assert result is None

    def test_get_parsed_metadata_invalid(self):
        """Test get_parsed_metadata raises error for invalid JSON."""
        # Don't test this case because the config would be invalid during initialization
        # Instead, test that validation works during creation
        with pytest.raises(ValueError, match="Invalid custom_metadata"):
            RotateLogConfig(
                log_type="progress",
                custom_metadata="invalid json"
            )

    def test_is_dry_run(self):
        """Test dry run detection."""
        config_dry = RotateLogConfig(
            log_type="progress",
            dry_run=True
        )
        assert config_dry.is_dry_run() is True

        config_wet = RotateLogConfig(
            log_type="progress",
            dry_run=False
        )
        assert config_wet.is_dry_run() is False

    def test_is_auto_threshold_mode(self):
        """Test auto-threshold mode detection."""
        config_auto = RotateLogConfig(
            log_type="progress",
            auto_threshold=True
        )
        assert config_auto.is_auto_threshold_mode() is True

        config_manual = RotateLogConfig(
            log_type="progress",
            auto_threshold=False
        )
        assert config_manual.is_auto_threshold_mode() is False

    def test_get_effective_threshold(self):
        """Test effective threshold calculation."""
        config_custom = RotateLogConfig(
            log_type="progress",
            threshold_entries=1000
        )
        assert config_custom.get_effective_threshold() == 1000

        config_default = RotateLogConfig(
            log_type="progress",
            threshold_entries=None
        )
        assert config_default.get_effective_threshold() == 500

    def test_create_validation_error(self):
        """Test validation error creation."""
        config = RotateLogConfig(log_type="progress")

        error = config.create_validation_error(
            "Test error",
            "Test suggestion"
        )

        assert error["ok"] is False
        assert error["error"] == "Test error"
        assert error["suggestion"] == "Test suggestion"

    def test_apply_response_defaults(self):
        """Test applying response defaults."""
        config = RotateLogConfig(log_type="progress")

        response = {"ok": False}
        defaults = {"suggestion": "Test suggestion"}

        result = config.apply_response_defaults(response, defaults)

        assert result["ok"] is False
        assert result["suggestion"] == "Test suggestion"


class TestRotateLogConfigFactoryMethods:
    """Test factory methods for common scenarios."""

    def test_from_legacy_params(self):
        """Test creation from legacy parameters."""
        config = RotateLogConfig.from_legacy_params(
            suffix="test",
            log_type="progress",
            confirm=True,
            auto_threshold=True,
            threshold_entries=1000
        )

        assert config.suffix == "test"
        assert config.log_type == "progress"
        assert config.confirm is True
        assert config.auto_threshold is True
        assert config.threshold_entries == 1000

    def test_create_for_auto_rotation(self):
        """Test factory method for auto-rotation scenarios."""
        config = RotateLogConfig.create_for_auto_rotation(
            threshold_entries=1000,
            log_type="progress"
        )

        assert config.auto_threshold is True
        assert config.threshold_entries == 1000
        assert config.confirm is True
        assert config.log_type == "progress"

    def test_create_for_manual_rotation(self):
        """Test factory method for manual rotation scenarios."""
        config = RotateLogConfig.create_for_manual_rotation(
            log_type="doc_updates",
            suffix="manual"
        )

        assert config.log_type == "doc_updates"
        assert config.suffix == "manual"
        assert config.confirm is True
        assert config.auto_threshold is False

    def test_create_for_dry_run(self):
        """Test factory method for dry-run scenarios."""
        config = RotateLogConfig.create_for_dry_run(
            dry_run_mode="precise",
            log_type="progress"
        )

        assert config.dry_run is True
        assert config.dry_run_mode == "precise"
        assert config.confirm is False
        assert config.log_type == "progress"


class TestRotateLogConfigBackwardCompatibility:
    """Test backward compatibility functions."""

    def test_create_rotate_log_config_function(self):
        """Test backward compatibility function."""
        config = create_rotate_log_config(
            log_type="progress",
            confirm=True,
            suffix="test"
        )

        assert isinstance(config, RotateLogConfig)
        assert config.log_type == "progress"
        assert config.confirm is True
        assert config.suffix == "test"

    def test_validate_rotate_log_params_success(self):
        """Test parameter validation function success case."""
        result = validate_rotate_log_params(
            log_type="progress",
            confirm=True
        )

        assert result["ok"] is True
        assert "config" in result
        assert isinstance(result["config"], RotateLogConfig)

    def test_validate_rotate_log_params_failure(self):
        """Test parameter validation function failure case."""
        result = validate_rotate_log_params(
            dry_run_mode="invalid_mode"
        )

        assert result["ok"] is False
        assert "error" in result
        assert "suggestion" in result


class TestRotateLogConfigEdgeCases:
    """Test edge cases and error scenarios."""

    def test_empty_log_types_list(self):
        """Test handling of empty log_types list."""
        config = RotateLogConfig(
            log_types=[],
            dry_run_mode="estimate"
        )
        # Empty list should be allowed (means no log types selected)
        assert config.log_types == []

    def test_large_threshold_value(self):
        """Test handling of very large threshold values."""
        config = RotateLogConfig(
            log_type="progress",
            threshold_entries=1000000
        )
        assert config.threshold_entries == 1000000

    def test_complex_custom_metadata(self):
        """Test parsing of complex JSON metadata."""
        complex_metadata = '''
        {
            "rotation_info": {
                "reason": "maintenance",
                "details": ["item1", "item2"],
                "count": 42
            },
            "timestamp": "2025-01-01T00:00:00Z"
        }
        '''
        config = RotateLogConfig(
            log_type="progress",
            custom_metadata=complex_metadata
        )

        parsed = config.get_parsed_metadata()
        assert parsed["rotation_info"]["reason"] == "maintenance"
        assert parsed["rotation_info"]["details"] == ["item1", "item2"]
        assert parsed["rotation_info"]["count"] == 42

    def test_rotate_all_with_custom_configuration(self):
        """Test rotate_all mode with custom configuration."""
        config = RotateLogConfig(
            rotate_all=True,
            confirm=True,
            custom_metadata='{"batch": true}',
            dry_run_mode="precise"
        )

        assert config.rotate_all is True
        assert config.confirm is True
        assert config.dry_run_mode == "precise"
        assert config.get_parsed_metadata()["batch"] is True


class TestRotateLogConfigIntegration:
    """Integration tests with Phase 1 utilities."""

    def test_phase_1_validator_integration(self):
        """Test integration with Phase 1 ToolValidator."""
        # Test enum validation
        config = RotateLogConfig(
            log_type="progress",
            dry_run_mode="precise"  # Valid enum value
        )
        assert config.dry_run_mode == "precise"

    def test_phase_1_config_manager_integration(self):
        """Test integration with Phase 1 ConfigManager."""
        config = RotateLogConfig(
            log_type="progress",
            threshold_entries=None  # Should get default from ConfigManager pattern
        )
        assert config.threshold_entries == 500  # Default value

    def test_phase_1_error_handler_integration(self):
        """Test integration with Phase 1 ErrorHandler."""
        config = RotateLogConfig(log_type="progress")

        error_response = config.create_validation_error(
            "Test validation error",
            "Use correct parameter values"
        )

        # Should follow ErrorHandler pattern
        assert "ok" in error_response
        assert "error" in error_response
        assert "suggestion" in error_response
        assert error_response["ok"] is False


if __name__ == "__main__":
    pytest.main([__file__])