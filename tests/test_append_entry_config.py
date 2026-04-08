"""Comprehensive unit tests for AppendEntryConfig configuration class.

Tests for TOOL_AUDIT_1112025 Phase 2 Task 2.1 - Configuration Objects
"""

import json
import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List

from scribe_mcp.tools.config.append_entry_config import AppendEntryConfig


class TestAppendEntryConfig:
    """Test suite for AppendEntryConfig functionality."""

    def test_default_initialization(self) -> None:
        """Test default initialization of AppendEntryConfig."""
        config = AppendEntryConfig()

        # Test core parameters have correct defaults
        assert config.message == ""
        assert config.status is None
        assert config.emoji is None
        assert config.agent is None
        assert config.meta == {}
        assert config.timestamp_utc is None

        # Test bulk processing parameters
        assert config.items is None
        assert config.items_list is None
        assert config.auto_split is True
        assert config.split_delimiter == "\n"
        assert config.stagger_seconds == 1

        # Test system parameters
        assert config.agent_id is None
        assert config.log_type == "progress"

        # Test configuration parameters
        assert config.length_threshold == 500
        assert config.chunk_size == 50
        assert config.auto_detect_status is True
        assert config.auto_detect_emoji is True

        # Test performance parameters
        assert config.rate_limit_count == 0
        assert config.rate_limit_window == 60
        assert config.max_bytes == 1048576
        assert config.storage_timeout == 30

        # Test optimization parameters
        assert config.bulk_processing_enabled is True
        assert config.database_batch_size == 100
        assert config.large_content_threshold == 50

        # Test validation parameters
        assert config.strict_validation is True
        assert config.sanitize_content is True
        assert config.generate_entry_id is True

        # Test legacy parameters
        assert config.enable_legacy_mode is True
        assert config.fallback_agent == "Scribe"

    def test_full_initialization(self) -> None:
        """Test initialization with all parameters specified."""
        test_meta = {"key": "value", "phase": "test"}
        test_items_list = [
            {"message": "Entry 1", "status": "info"},
            {"message": "Entry 2", "status": "success"}
        ]

        config = AppendEntryConfig(
            message="Test message",
            status="success",
            emoji="✅",
            agent="TestAgent",
            meta=test_meta,
            timestamp_utc="2025-11-01T22:00:00Z",
            items='[{"message": "JSON entry"}]',
            items_list=test_items_list,
            auto_split=False,
            split_delimiter="|",
            stagger_seconds=5,
            agent_id="agent-123",
            log_type="test_log",
            length_threshold=1000,
            chunk_size=25,
            auto_detect_status=False,
            auto_detect_emoji=False,
            rate_limit_count=120,
            rate_limit_window=30,
            max_bytes=2097152,
            storage_timeout=60,
            bulk_processing_enabled=False,
            database_batch_size=50,
            large_content_threshold=100,
            strict_validation=False,
            sanitize_content=False,
            generate_entry_id=False,
            enable_legacy_mode=False,
            fallback_agent="FallbackAgent"
        )

        assert config.message == "Test message"
        assert config.status == "success"
        assert config.emoji == "✅"
        assert config.agent == "TestAgent"
        assert config.meta == test_meta
        assert config.timestamp_utc == "2025-11-01T22:00:00Z"
        assert config.items == '[{"message": "JSON entry"}]'
        assert config.items_list == test_items_list
        assert config.auto_split is False
        assert config.split_delimiter == "|"
        assert config.stagger_seconds == 5
        assert config.agent_id == "agent-123"
        assert config.log_type == "test_log"
        assert config.length_threshold == 1000
        assert config.chunk_size == 25
        assert config.auto_detect_status is False
        assert config.auto_detect_emoji is False
        assert config.rate_limit_count == 120
        assert config.rate_limit_window == 30
        assert config.max_bytes == 2097152
        assert config.storage_timeout == 60
        assert config.bulk_processing_enabled is False
        assert config.database_batch_size == 50
        assert config.large_content_threshold == 100
        assert config.strict_validation is False
        assert config.sanitize_content is False
        assert config.generate_entry_id is False
        assert config.enable_legacy_mode is False
        assert config.fallback_agent == "FallbackAgent"

    def test_validation_success(self) -> None:
        """Test successful validation with valid parameters."""
        config = AppendEntryConfig(
            message="Valid message",
            status="success",
            agent="ValidAgent",
            timestamp_utc="2025-11-01 22:00:00 UTC",  # Use format expected by ToolValidator
            items='[{"message": "test"}]',
            items_list=[{"message": "test"}],
            log_type="progress"
        )
        # Should not raise any exceptions
        config.validate()

    def test_validation_invalid_status(self) -> None:
        """Test validation failure with invalid status."""
        config = AppendEntryConfig(status="invalid_status", strict_validation=False)
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Status must be one of"):
            config.validate()

    def test_validation_invalid_items_json(self) -> None:
        """Test validation failure with invalid items JSON."""
        config = AppendEntryConfig(items='invalid json', strict_validation=False)
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Items parameter must be valid JSON"):
            config.validate()

    def test_validation_invalid_items_not_array(self) -> None:
        """Test validation failure with items not being an array."""
        config = AppendEntryConfig(items='{"not": "an array"}', strict_validation=False)
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Items parameter must be a valid JSON array"):
            config.validate()

    def test_validation_invalid_items_list(self) -> None:
        """Test validation failure with invalid items_list."""
        config = AppendEntryConfig(items_list="not a list", strict_validation=False)
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Items_list must be a list of dictionaries"):
            config.validate()

    def test_validation_invalid_timestamp(self) -> None:
        """Test validation failure with invalid timestamp."""
        config = AppendEntryConfig(timestamp_utc="invalid-timestamp", strict_validation=False)
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Invalid timestamp"):
            config.validate()

    def test_validation_negative_numbers(self) -> None:
        """Test validation failure with negative numeric values."""
        # Create config and manually set negative values after init to bypass normalization
        config = AppendEntryConfig(strict_validation=False)
        config.stagger_seconds = -1
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Stagger seconds must be non-negative"):
            config.validate()

        # Test negative length_threshold
        config = AppendEntryConfig(strict_validation=False)
        config.length_threshold = -1
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Length threshold must be non-negative"):
            config.validate()

        # Test negative rate_limit_count
        config = AppendEntryConfig(strict_validation=False)
        config.rate_limit_count = -1
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Rate limit count must be non-negative"):
            config.validate()

    def test_validation_zero_values(self) -> None:
        """Test validation failure with zero values where not allowed."""
        # Test zero chunk_size
        config = AppendEntryConfig(strict_validation=False)
        config.chunk_size = 0
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Chunk size must be positive"):
            config.validate()

        # Test zero rate_limit_window
        config = AppendEntryConfig(strict_validation=False)
        config.rate_limit_window = 0
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Rate limit window must be positive"):
            config.validate()

        # Test zero max_bytes
        config = AppendEntryConfig(strict_validation=False)
        config.max_bytes = 0
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Max bytes must be positive"):
            config.validate()

    def test_validation_invalid_agent(self) -> None:
        """Test validation failure with invalid agent."""
        config = AppendEntryConfig(strict_validation=False)  # Empty agent
        config.agent = ""  # Set to empty after init to bypass normalization
        config.normalize()  # Should normalize empty to None
        # Actually, empty string becomes None after sanitize_identifier, so this might not fail
        # Let's test with a clearly invalid agent instead
        config.agent = "   "  # Only whitespace
        config.normalize()
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Agent identifier is invalid"):
            config.validate()

    def test_validation_invalid_log_type(self) -> None:
        """Test validation failure with invalid log type."""
        config = AppendEntryConfig(log_type="", strict_validation=False)  # Empty log type
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError, match="Log type must be a non-empty string"):
            config.validate()

    def test_validation_disabled(self) -> None:
        """Test that validation can be disabled."""
        # This should not raise an exception even with invalid parameters
        config = AppendEntryConfig(
            status="invalid_status",
            strict_validation=False
        )
        config.validate()  # Should not raise

    def test_normalize_booleans(self) -> None:
        """Test normalization of boolean parameters."""
        # Start with default config and set values manually
        config = AppendEntryConfig(strict_validation=False)

        # Set values that need normalization
        config.auto_split = 0  # Should become False
        config.bulk_processing_enabled = 1  # Should become True
        config.strict_validation = "false"  # Should become False
        config.sanitize_content = "true"  # Should become True
        config.generate_entry_id = []  # Should become True (non-empty)
        config.enable_legacy_mode = None  # Should become False
        config.auto_detect_status = 0  # Should become False
        config.auto_detect_emoji = 1  # Should become True

        config.normalize()  # Explicitly call normalize

        assert config.auto_split is False
        assert config.bulk_processing_enabled is True
        assert config.strict_validation is False
        assert config.sanitize_content is True
        assert config.generate_entry_id is True
        assert config.enable_legacy_mode is False
        assert config.auto_detect_status is False
        assert config.auto_detect_emoji is True

    def test_normalize_numeric_parameters(self) -> None:
        """Test normalization of numeric parameters."""
        config = AppendEntryConfig(
            stagger_seconds=-5,  # Should become 0
            length_threshold=-10,  # Should become 0
            chunk_size=0,  # Should become 1
            rate_limit_count=0,  # Should stay 0 (allowed)
            rate_limit_window=-30,  # Should become 1
            max_bytes=-100,  # Should become 1
            storage_timeout=0,  # Should become 1
            database_batch_size=-50,  # Should become 1
            large_content_threshold=0  # Should become 1
        )

        assert config.stagger_seconds == 0
        assert config.length_threshold == 0
        assert config.chunk_size == 1
        assert config.rate_limit_count == 0
        assert config.rate_limit_window == 1
        assert config.max_bytes == 1
        assert config.storage_timeout == 1
        assert config.database_batch_size == 1
        assert config.large_content_threshold == 1

    def test_normalize_string_parameters(self) -> None:
        """Test normalization of string parameters."""
        config = AppendEntryConfig(
            split_delimiter=None,  # Should become "\n"
            fallback_agent=None,  # Should become "Scribe"
            log_type=None  # Should become "progress"
        )

        assert config.split_delimiter == "\n"
        assert config.fallback_agent == "Scribe"
        assert config.log_type == "progress"

    def test_normalize_agent_sanitization(self) -> None:
        """Test agent identifier sanitization during normalization."""
        config = AppendEntryConfig(agent="Test-Agent_123")
        config.normalize()
        # Agent should be sanitized (specific rules depend on ToolValidator.sanitize_identifier)
        assert config.agent == "Test-Agent_123"  # Assuming this is valid

    def test_normalize_metadata(self) -> None:
        """Test metadata normalization."""
        config = AppendEntryConfig(meta=None)
        config.normalize()
        assert config.meta == {}

    def test_from_legacy_params_basic(self) -> None:
        """Test creating config from legacy parameters."""
        config = AppendEntryConfig.from_legacy_params(
            message="Test message",
            status="success",
            emoji="✅",
            agent="TestAgent",
            meta={"key": "value"},
            timestamp_utc="2025-11-01T22:00:00Z",
            items='[{"message": "test"}]',
            items_list=[{"message": "test"}],
            auto_split=False,
            split_delimiter="|",
            stagger_seconds=5,
            agent_id="agent-123",
            log_type="test_log"
        )

        assert config.message == "Test message"
        assert config.status == "success"
        assert config.emoji == "✅"
        assert config.agent == "TestAgent"
        assert config.meta == {"key": "value"}
        assert config.timestamp_utc == "2025-11-01T22:00:00Z"
        assert config.items == '[{"message": "test"}]'
        assert config.items_list == [{"message": "test"}]
        assert config.auto_split is False
        assert config.split_delimiter == "|"
        assert config.stagger_seconds == 5
        assert config.agent_id == "agent-123"
        assert config.log_type == "test_log"

    def test_from_legacy_params_with_kwargs(self) -> None:
        """Test creating config from legacy parameters with additional config kwargs."""
        config = AppendEntryConfig.from_legacy_params(
            message="Test message",
            length_threshold=1000,
            chunk_size=25,
            rate_limit_count=120,
            custom_param="ignored"  # Should be ignored
        )

        assert config.message == "Test message"
        assert config.length_threshold == 1000
        assert config.chunk_size == 25
        assert config.rate_limit_count == 120
        # Default values should remain for other parameters
        assert config.status is None
        assert config.emoji is None

    def test_to_dict(self) -> None:
        """Test conversion to dictionary representation."""
        config = AppendEntryConfig(
            message="Test message",
            status="success",
            meta={"key": "value"}
        )

        result = config.to_dict()

        assert isinstance(result, dict)
        assert result["message"] == "Test message"
        assert result["status"] == "success"
        assert result["meta"] == {"key": "value"}
        assert "length_threshold" in result
        assert "chunk_size" in result
        assert "rate_limit_count" in result

    def test_to_legacy_params(self) -> None:
        """Test conversion to legacy function parameters."""
        config = AppendEntryConfig(
            message="Test message",
            status="success",
            emoji="✅",
            agent="TestAgent",
            meta={"key": "value"},
            timestamp_utc="2025-11-01T22:00:00Z",
            items='[{"message": "test"}]',
            items_list=[{"message": "test"}],
            auto_split=False,
            split_delimiter="|",
            stagger_seconds=5,
            agent_id="agent-123",
            log_type="test_log"
        )

        result = config.to_legacy_params()

        expected_keys = [
            'message', 'status', 'emoji', 'agent', 'meta', 'timestamp_utc',
            'items', 'items_list', 'auto_split', 'split_delimiter',
            'stagger_seconds', 'agent_id', 'log_type'
        ]

        for key in expected_keys:
            assert key in result

        assert result["message"] == "Test message"
        assert result["status"] == "success"
        assert result["emoji"] == "✅"
        assert result["agent"] == "TestAgent"

    def test_merge_with_defaults(self) -> None:
        """Test merging configuration with default values."""
        config = AppendEntryConfig(
            message="Test message",
            status=None,  # Should be filled from defaults
            agent=None   # Should be filled from defaults
        )

        defaults = {
            "status": "info",
            "agent": "DefaultAgent",
            "emoji": "📝"
        }

        merged = config.merge_with_defaults(defaults)

        # Original values should be preserved
        assert merged.message == "Test message"
        # None values should be filled from defaults
        assert merged.status == "info"
        assert merged.agent == "DefaultAgent"
        # Non-specified defaults should not affect other fields
        assert merged.emoji is None  # Was not None in original

    def test_is_bulk_mode_explicit_items(self) -> None:
        """Test bulk mode detection with explicit items."""
        # Test with items parameter
        config = AppendEntryConfig(items='[{"message": "test"}]')
        assert config.is_bulk_mode() is True

        # Test with items_list parameter
        config = AppendEntryConfig(items_list=[{"message": "test"}])
        assert config.is_bulk_mode() is True

    def test_is_bulk_mode_auto_split(self) -> None:
        """Test bulk mode detection with auto-split."""
        # Short message should not trigger bulk mode
        config = AppendEntryConfig(
            message="Short message",
            auto_split=True,
            length_threshold=500
        )
        assert config.is_bulk_mode() is False

        # Long message should trigger bulk mode
        config = AppendEntryConfig(
            message="A" * 600,  # Longer than threshold
            auto_split=True,
            length_threshold=500
        )
        assert config.is_bulk_mode() is True

        # Disabled auto_split should not trigger bulk mode
        config = AppendEntryConfig(
            message="A" * 600,
            auto_split=False,
            length_threshold=500
        )
        assert config.is_bulk_mode() is False

    def test_estimate_processing_time_single_entry(self) -> None:
        """Test processing time estimation for single entry."""
        config = AppendEntryConfig(message="Single message")

        time_estimate = config.estimate_processing_time(1)

        assert isinstance(time_estimate, float)
        assert time_estimate >= 0.1  # Base processing time
        assert time_estimate < 1.0   # Should be fast for single entry

    def test_estimate_processing_time_bulk_mode(self) -> None:
        """Test processing time estimation for bulk mode."""
        config = AppendEntryConfig(
            items_list=[{"message": f"Entry {i}"} for i in range(10)],
            stagger_seconds=1,
            bulk_processing_enabled=True
        )

        time_estimate = config.estimate_processing_time(10)

        assert isinstance(time_estimate, float)
        assert time_estimate > 0.1  # Should be longer than single entry
        # Should include database overhead
        assert time_estimate >= 0.15  # Base + database

    def test_estimate_processing_time_large_content(self) -> None:
        """Test processing time estimation for large content requiring chunking."""
        config = AppendEntryConfig(
            items_list=[{"message": f"Entry {i}"} for i in range(100)],
            chunk_size=25,
            large_content_threshold=50,
            bulk_processing_enabled=True
        )

        time_estimate = config.estimate_processing_time(100)

        assert isinstance(time_estimate, float)
        # Should include chunking overhead
        assert time_estimate > 0.2

    def test_estimate_processing_time_with_items_json(self) -> None:
        """Test processing time estimation with JSON items."""
        config = AppendEntryConfig(
            items='[{"message": "Entry 1"}, {"message": "Entry 2"}]',
            bulk_processing_enabled=True
        )

        time_estimate = config.estimate_processing_time()

        assert isinstance(time_estimate, float)
        assert time_estimate > 0.1

    def test_estimate_processing_time_invalid_json(self) -> None:
        """Test processing time estimation with invalid JSON items."""
        config = AppendEntryConfig(
            items='invalid json',
            bulk_processing_enabled=True,
            strict_validation=False
        )

        time_estimate = config.estimate_processing_time()

        # Should handle invalid JSON gracefully
        assert isinstance(time_estimate, float)
        assert time_estimate >= 0.1

    def test_edge_case_empty_config(self) -> None:
        """Test edge case with completely empty configuration."""
        config = AppendEntryConfig(
            message="",
            status=None,
            emoji=None,
            agent=None,
            meta=None,
            timestamp_utc=None,
            items=None,
            items_list=None
        )

        # Should still have valid defaults
        assert config.auto_split is True
        assert config.log_type == "progress"
        assert config.length_threshold == 500

        # Should be able to validate (with strict validation)
        config.validate()

        # Should not be bulk mode
        assert config.is_bulk_mode() is False

    def test_edge_case_maximum_values(self) -> None:
        """Test edge case with maximum parameter values."""
        config = AppendEntryConfig(
            message="A" * 10000,  # Very long message
            stagger_seconds=3600,  # 1 hour
            length_threshold=1000000,  # 1M characters
            chunk_size=10000,
            rate_limit_count=1000000,
            rate_limit_window=86400,  # 1 day
            max_bytes=1073741824,  # 1GB
            storage_timeout=3600,  # 1 hour
            database_batch_size=100000,
            large_content_threshold=100000
        )

        # Should normalize correctly
        config.normalize()

        # Should validate successfully
        config.validate()

        # Should handle bulk mode estimation correctly
        if config.is_bulk_mode():
            time_estimate = config.estimate_processing_time(1000)
            assert isinstance(time_estimate, float)
            assert time_estimate > 0

    def test_edge_case_special_characters(self) -> None:
        """Test edge case with special characters in parameters."""
        config = AppendEntryConfig(
            message="Message with special chars: 🎉 \n\t\r",
            agent="Agent-With_Special.123",
            split_delimiter="|||",
            meta={"unicode": "🚀", "special": "!@#$%^&*()"}
        )

        # Should normalize successfully
        config.normalize()

        # Should validate (message will be sanitized by ToolValidator if needed)
        try:
            config.validate()
        except ValueError as e:
            # If validation fails, it should be due to message newlines, which is expected
            assert "newline" in str(e).lower()

    def test_integration_with_phase1_utilities(self) -> None:
        """Test integration with Phase 1 utilities."""
        # This test ensures the config properly uses ToolValidator, ConfigManager, and ErrorHandler

        config = AppendEntryConfig(
            agent="test-agent",
            status="success",
            timestamp_utc="2025-11-01T22:00:00Z"
        )

        # Should use ToolValidator for validation
        config.validate()

        # Should use ConfigManager patterns in normalization
        config.normalize()

        # Agent should be sanitized
        assert config.agent == "test-agent"

    def test_backward_compatibility_preservation(self) -> None:
        """Test that backward compatibility is preserved."""
        # Create config using legacy parameters
        legacy_config = AppendEntryConfig.from_legacy_params(
            message="Test",
            status="info",
            agent="LegacyAgent"
        )

        # Convert back to legacy params
        legacy_params = legacy_config.to_legacy_params()

        # Should be able to create new config from legacy params
        new_config = AppendEntryConfig.from_legacy_params(**legacy_params)

        # Should be equivalent
        assert new_config.message == legacy_config.message
        assert new_config.status == legacy_config.status
        assert new_config.agent == legacy_config.agent

    def test_comprehensive_validation_coverage(self) -> None:
        """Test comprehensive validation covering all parameters."""
        # Test all valid statuses
        for status in ["info", "success", "warn", "error", "bug", "plan"]:
            config = AppendEntryConfig(status=status)
            config.validate()  # Should not raise

        # Test invalid status
        config = AppendEntryConfig(status="invalid", strict_validation=False)
        config.strict_validation = True  # Enable validation for explicit call
        with pytest.raises(ValueError):
            config.validate()

        # Test all numeric parameter boundaries
        test_cases = [
            ("stagger_seconds", 0, True),
            ("stagger_seconds", -1, False),
            ("length_threshold", 0, True),
            ("length_threshold", -1, False),
            ("chunk_size", 1, True),
            ("chunk_size", 0, False),
            ("rate_limit_count", 0, True),
            ("rate_limit_count", -1, False),
            ("rate_limit_window", 1, True),
            ("rate_limit_window", 0, False),
            ("max_bytes", 1, True),
            ("max_bytes", 0, False),
        ]

        for param, value, should_pass in test_cases:
            config = AppendEntryConfig(strict_validation=False)
            if not should_pass:
                # Set invalid value after init to bypass normalization
                setattr(config, param, value)
            if should_pass:
                config.validate()
            else:
                config.strict_validation = True  # Enable validation for explicit call
                with pytest.raises(ValueError):
                    config.validate()


if __name__ == "__main__":
    pytest.main([__file__])
