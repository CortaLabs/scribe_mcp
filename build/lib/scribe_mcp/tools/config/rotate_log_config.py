"""
Configuration objects for rotate_log tool parameters.

This module provides comprehensive configuration management for the rotate_log
tool, including parameter validation, normalization, and business logic
validation using Phase 1 utilities (ToolValidator, ConfigManager, ErrorHandler).

Key Design Principles:
- Centralized parameter management using dataclasses
- Leverages Phase 1 utilities for validation and error handling
- Comprehensive validation for rotation-specific scenarios
- Support for dry-run modes and threshold validation
- Legacy compatibility with existing parameter patterns
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from scribe_mcp.utils.parameter_validator import ToolValidator
from scribe_mcp.utils.config_manager import ConfigManager
from scribe_mcp.utils.error_handler import ErrorHandler


@dataclass
class RotateLogConfig:
    """
    Comprehensive configuration for rotate_log tool parameters.

    This configuration class manages all 11 parameters from the rotate_log function
    signature plus internal configuration constants for complete rotation management.

    Attributes:
        # Core Rotation Parameters
        suffix: Optional suffix for archive filenames
        custom_metadata: Optional JSON metadata appended to rotation record
        confirm: When True, perform actual rotation (required unless auto-threshold triggers)
        dry_run: If True, preview rotation without changing files
        dry_run_mode: Controls dry-run accuracy ("estimate" or "precise")

        # Log Selection Parameters
        log_type: Single log type to rotate (e.g., "progress", "doc_updates")
        log_types: List of log types to rotate
        rotate_all: When True, rotate every configured log type for the project

        # Threshold Parameters
        auto_threshold: When True, only rotate logs whose entry count exceeds threshold
        threshold_entries: Optional override for entry threshold

        # Internal Configuration Constants
        default_auto_threshold_entries: Default threshold for auto-rotation
        default_bytes_per_line: Default bytes-per-line for estimation
        min_bytes_per_line: Minimum bytes-per-line allowed
        max_bytes_per_line: Maximum bytes-per-line allowed
        estimation_band_ratio: Ratio for threshold band calculation
        estimation_band_min: Minimum threshold band size
    """

    # Core Rotation Parameters
    suffix: Optional[str] = None
    custom_metadata: Optional[str] = None
    confirm: Optional[bool] = False
    dry_run: Optional[bool] = None
    dry_run_mode: Optional[str] = None

    # Log Selection Parameters
    log_type: Optional[str] = None
    log_types: Optional[List[str]] = None
    rotate_all: bool = False

    # Threshold Parameters
    auto_threshold: bool = False
    threshold_entries: Optional[int] = None

    # Internal Configuration Constants
    default_auto_threshold_entries: int = 500
    default_bytes_per_line: float = 80.0
    min_bytes_per_line: float = 16.0
    max_bytes_per_line: float = 512.0
    estimation_band_ratio: float = 0.1
    estimation_band_min: int = 250

    # Validation utilities (class-level for shared use)
    _validator: ToolValidator = field(default_factory=ToolValidator, init=False)
    _config_manager: ConfigManager = field(default_factory=lambda: ConfigManager("rotate_log"), init=False)
    _error_handler: ErrorHandler = field(default_factory=ErrorHandler, init=False)

    # Valid values for enum parameters
    VALID_DRY_RUN_MODES = {"estimate", "precise"}

    def __post_init__(self) -> None:
        """Post-initialization validation and normalization."""
        self.normalize()
        self.validate()

    def normalize(self) -> None:
        """
        Normalize configuration parameters using Phase 1 utilities.

        This method applies standard normalization patterns from the Phase 1
        ConfigManager to ensure consistent parameter handling.
        """
        # Normalize dry_run_mode to lowercase and apply default
        if self.dry_run_mode:
            self.dry_run_mode = self.dry_run_mode.lower()
        else:
            # Default to "estimate" mode when not specified
            self.dry_run_mode = "estimate"

        # Normalize log_types list
        if self.log_types is not None:
            self.log_types = self._validator.validate_list_parameter(self.log_types, ",")

        # Set dry_run default based on confirm flag
        if self.dry_run is None:
            self.dry_run = not self.confirm

        # Apply default threshold if not provided
        if self.threshold_entries is None:
            self.threshold_entries = self.default_auto_threshold_entries

    def validate(self) -> None:
        """
        Validate configuration parameters using Phase 1 utilities.

        Raises:
            ValueError: If configuration validation fails
        """
        # Validate dry_run_mode enum value
        if self.dry_run_mode and self.dry_run_mode not in self.VALID_DRY_RUN_MODES:
            raise ValueError(
                f"Invalid dry_run_mode '{self.dry_run_mode}'. "
                f"Use {sorted(self.VALID_DRY_RUN_MODES)}."
            )

        # Validate custom_metadata JSON format
        if self.custom_metadata:
            _, error = self._validator.validate_json_metadata(self.custom_metadata, "custom_metadata")
            if error:
                raise ValueError(f"Invalid custom_metadata: {error}")

        # Validate suffix format (basic string validation)
        if self.suffix:
            if not isinstance(self.suffix, str) or not self.suffix.strip():
                raise ValueError("suffix must be a non-empty string")
            if len(self.suffix) > 64:
                raise ValueError("suffix cannot exceed 64 characters")

        # Validate threshold_entries range
        if self.threshold_entries is not None and self.threshold_entries <= 0:
            raise ValueError("threshold_entries must be greater than 0")

        # Validate numeric bounds
        if self.default_bytes_per_line < self.min_bytes_per_line:
            raise ValueError(
                f"default_bytes_per_line ({self.default_bytes_per_line}) "
                f"cannot be less than min_bytes_per_line ({self.min_bytes_per_line})"
            )

        if self.default_bytes_per_line > self.max_bytes_per_line:
            raise ValueError(
                f"default_bytes_per_line ({self.default_bytes_per_line}) "
                f"cannot be greater than max_bytes_per_line ({self.max_bytes_per_line})"
            )

        # Validate estimation_band_ratio
        if not 0.0 < self.estimation_band_ratio <= 1.0:
            raise ValueError("estimation_band_ratio must be between 0.0 and 1.0")

        # Validate estimation_band_min
        if self.estimation_band_min < 0:
            raise ValueError("estimation_band_min must be non-negative")

        # Validate log selection logic
        selection_count = sum([
            self.log_type is not None,
            self.log_types is not None,  # Empty list is valid (means no types selected)
            bool(self.rotate_all)  # Convert to boolean, handles None properly
        ])

        if selection_count == 0:
            raise ValueError(
                "Must specify one of: log_type, log_types, or rotate_all=True"
            )

        if selection_count > 1:
            raise ValueError(
                "Cannot specify multiple log selection options. "
                "Use only one of: log_type, log_types, or rotate_all=True"
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary format for tool calls.

        Returns:
            Dictionary with only non-None parameters for tool invocation
        """
        result = {}

        # Core parameters
        if self.suffix is not None:
            result["suffix"] = self.suffix
        if self.custom_metadata is not None:
            result["custom_metadata"] = self.custom_metadata
        if self.confirm is not None:
            result["confirm"] = self.confirm
        if self.dry_run is not None:
            result["dry_run"] = self.dry_run
        if self.dry_run_mode is not None:
            result["dry_run_mode"] = self.dry_run_mode

        # Log selection parameters
        if self.log_type is not None:
            result["log_type"] = self.log_type
        if self.log_types is not None:
            result["log_types"] = self.log_types
        if self.rotate_all:
            result["rotate_all"] = self.rotate_all

        # Threshold parameters
        if self.auto_threshold:
            result["auto_threshold"] = self.auto_threshold
        if self.threshold_entries is not None and self.threshold_entries != self.default_auto_threshold_entries:
            result["threshold_entries"] = self.threshold_entries

        return result

    def get_parsed_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Parse custom_metadata JSON string using Phase 1 utilities.

        Returns:
            Parsed metadata dictionary or None if no metadata
        """
        if not self.custom_metadata:
            return None

        parsed, error = self._validator.validate_json_metadata(self.custom_metadata, "custom_metadata")
        if error:
            raise ValueError(f"Invalid custom_metadata: {error}")

        return parsed

    def create_validation_error(self, message: str, suggestion: Optional[str] = None) -> Dict[str, Any]:
        """
        Create standardized error response using Phase 1 utilities.

        Args:
            message: Error message
            suggestion: Optional suggestion for fixing the error

        Returns:
            Standardized error response dictionary
        """
        return self._error_handler.create_validation_error(
            error_message=message,
            suggestion=suggestion
        )

    def apply_response_defaults(self, response: Dict[str, Any], defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Apply response defaults using Phase 1 utilities.

        Args:
            response: Base response dictionary
            defaults: Optional defaults to apply

        Returns:
            Response with defaults applied
        """
        from scribe_mcp.utils.config_manager import apply_response_defaults
        if defaults:
            return apply_response_defaults(response, defaults)
        return response

    def is_dry_run(self) -> bool:
        """
        Determine if this is a dry run operation.

        Returns:
            True if this is a dry run, False otherwise
        """
        return self.dry_run is True

    def is_auto_threshold_mode(self) -> bool:
        """
        Determine if auto-threshold mode is enabled.

        Returns:
            True if auto-threshold is enabled, False otherwise
        """
        return self.auto_threshold

    def get_effective_threshold(self) -> int:
        """
        Get the effective threshold value for rotation decisions.

        Returns:
            Effective threshold value (always positive)
        """
        return self.threshold_entries or self.default_auto_threshold_entries

    @classmethod
    def from_legacy_params(cls, **kwargs) -> RotateLogConfig:
        """
        Create configuration from legacy parameter format.

        This method provides backward compatibility with existing parameter
        patterns used in the current rotate_log implementation.

        Args:
            **kwargs: Legacy parameters from rotate_log function

        Returns:
            Configured RotateLogConfig instance
        """
        # Map legacy parameters to dataclass fields
        config_params = {}

        # Core parameters
        if "suffix" in kwargs:
            config_params["suffix"] = kwargs["suffix"]
        if "custom_metadata" in kwargs:
            config_params["custom_metadata"] = kwargs["custom_metadata"]
        if "confirm" in kwargs:
            config_params["confirm"] = kwargs["confirm"]
        if "dry_run" in kwargs:
            config_params["dry_run"] = kwargs["dry_run"]
        if "dry_run_mode" in kwargs:
            config_params["dry_run_mode"] = kwargs["dry_run_mode"]

        # Log selection parameters
        if "log_type" in kwargs:
            config_params["log_type"] = kwargs["log_type"]
        if "log_types" in kwargs:
            config_params["log_types"] = kwargs["log_types"]
        if "rotate_all" in kwargs:
            config_params["rotate_all"] = kwargs["rotate_all"]

        # Default behavior: if no log selection provided, default to "progress"
        # This maintains backward compatibility with original rotate_log behavior
        if (not kwargs.get("log_type") and
            not kwargs.get("log_types") and
            not kwargs.get("rotate_all")):
            config_params["log_type"] = "progress"

        # Threshold parameters
        if "auto_threshold" in kwargs:
            config_params["auto_threshold"] = kwargs["auto_threshold"]
        if "threshold_entries" in kwargs:
            config_params["threshold_entries"] = kwargs["threshold_entries"]

        return cls(**config_params)

    @classmethod
    def create_for_auto_rotation(cls, threshold_entries: Optional[int] = None, **kwargs) -> RotateLogConfig:
        """
        Create configuration optimized for automatic rotation scenarios.

        Args:
            threshold_entries: Custom threshold for auto-rotation
            **kwargs: Additional configuration parameters

        Returns:
            Configured RotateLogConfig for auto-rotation
        """
        return cls(
            auto_threshold=True,
            threshold_entries=threshold_entries,
            confirm=True,  # Auto-rotation should execute
            **kwargs
        )

    @classmethod
    def create_for_manual_rotation(cls, log_type: Optional[str] = None, **kwargs) -> RotateLogConfig:
        """
        Create configuration optimized for manual rotation scenarios.

        Args:
            log_type: Specific log type to rotate
            **kwargs: Additional configuration parameters

        Returns:
            Configured RotateLogConfig for manual rotation
        """
        return cls(
            log_type=log_type,
            confirm=True,  # Manual rotation should execute
            auto_threshold=False,  # Don't use auto-threshold for manual
            **kwargs
        )

    @classmethod
    def create_for_dry_run(cls, dry_run_mode: str = "estimate", **kwargs) -> RotateLogConfig:
        """
        Create configuration optimized for dry-run scenarios.

        Args:
            dry_run_mode: Dry run accuracy mode ("estimate" or "precise")
            **kwargs: Additional configuration parameters

        Returns:
            Configured RotateLogConfig for dry-run
        """
        return cls(
            dry_run=True,
            dry_run_mode=dry_run_mode,
            confirm=False,  # Dry run should not execute
            **kwargs
        )

    def copy_with(self, **kwargs) -> RotateLogConfig:
        """
        Create a copy of this configuration with specified parameters overridden.

        This method is essential for dual parameter support where legacy parameters
        take precedence over configuration object parameters.

        Args:
            **kwargs: Parameters to override in the copy

        Returns:
            New RotateLogConfig with overridden parameters
        """
        # Get current values as dictionary
        current_values = {
            'suffix': self.suffix,
            'custom_metadata': self.custom_metadata,
            'confirm': self.confirm,
            'dry_run': self.dry_run,
            'dry_run_mode': self.dry_run_mode,
            'log_type': self.log_type,
            'log_types': self.log_types,
            'rotate_all': self.rotate_all,
            'auto_threshold': self.auto_threshold,
            'threshold_entries': self.threshold_entries,
            # Include internal configuration constants
            'default_auto_threshold_entries': self.default_auto_threshold_entries,
            'default_bytes_per_line': self.default_bytes_per_line,
            'min_bytes_per_line': self.min_bytes_per_line,
            'max_bytes_per_line': self.max_bytes_per_line,
            'estimation_band_ratio': self.estimation_band_ratio,
            'estimation_band_min': self.estimation_band_min,
        }

        # Override with provided parameters
        current_values.update(kwargs)

        # Create new instance with overridden values
        return self.__class__(**current_values)


# Convenience functions for backward compatibility
def create_rotate_log_config(**kwargs) -> RotateLogConfig:
    """
    Create RotateLogConfig from legacy parameters.

    This function provides backward compatibility with existing parameter
    patterns while encouraging migration to the new configuration class.

    Args:
        **kwargs: Legacy rotate_log parameters

    Returns:
        Configured RotateLogConfig instance
    """
    return RotateLogConfig.from_legacy_params(**kwargs)


def validate_rotate_log_params(**kwargs) -> Dict[str, Any]:
    """
    Validate rotate_log parameters using the configuration class.

    This function provides parameter validation for legacy code while
    encouraging migration to the new configuration class.

    Args:
        **kwargs: Parameters to validate

    Returns:
        Validation result with error details if validation fails
    """
    try:
        config = RotateLogConfig.from_legacy_params(**kwargs)
        return {"ok": True, "config": config}
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "suggestion": "Check parameter values and types"
        }
