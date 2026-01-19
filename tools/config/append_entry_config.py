"""Configuration objects for MCP tools.

This module contains dataclass configuration objects for various MCP tools
to improve parameter management, validation, and maintainability.

Created for TOOL_AUDIT_1112025 Phase 2 Task 2.1 - Configuration Objects
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from scribe_mcp.utils.parameter_validator import ToolValidator
from scribe_mcp.utils.config_manager import ConfigManager, resolve_fallback_chain
from scribe_mcp.utils.error_handler import ErrorHandler
from scribe_mcp.shared.logging_utils import coerce_metadata_mapping


def _normalize_boolean(value: Any) -> bool:
    """
    Normalize various boolean representations to proper boolean values.

    Handles string representations like "false", "true", numeric values,
    and other truthy/falsy values consistently.

    Args:
        value: Value to normalize to boolean

    Returns:
        Normalized boolean value
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in ("false", "0", "", "no", "off", "none", "null")
    # Collection types (lists, dicts, etc.) should be True if they exist, even if empty
    if hasattr(value, '__len__') and not isinstance(value, (str, bytes)):
        return True
    return bool(value)


@dataclass
class AppendEntryConfig:
    """
    Comprehensive configuration class for append_entry tool parameters.

    This dataclass encapsulates all 25+ parameters from the append_entry function
    with proper validation, normalization, and backward compatibility support.

    Created for TOOL_AUDIT_1112025 Phase 2 Task 2.1
    """

    # Core content parameters
    message: str = ""
    status: Optional[str] = None
    emoji: Optional[str] = None
    agent: Optional[str] = None
    meta: Optional[Any] = field(default_factory=dict)
    timestamp_utc: Optional[str] = None

    # NEW: Priority and categorization parameters
    priority: Optional[str] = None  # critical|high|medium|low
    category: Optional[str] = None  # decision|investigation|bug|implementation|test|milestone|config|security|performance|documentation
    tags: Optional[List[str]] = None
    confidence: Optional[float] = None  # 0.0-1.0

    # Bulk processing parameters
    items: Optional[str] = None  # JSON string array (legacy)
    items_list: Optional[List[Dict[str, Any]]] = None  # Direct list (new)
    auto_split: bool = True
    split_delimiter: str = "\n"
    stagger_seconds: int = 1

    # System parameters
    agent_id: Optional[str] = None  # Agent identification (auto-detected)
    log_type: Optional[str] = "progress"

    # Bulk processing configuration
    length_threshold: int = 500  # Auto-detect bulk mode threshold
    chunk_size: int = 50  # Large content chunking size
    auto_detect_status: bool = True  # Auto-detect status in split content
    auto_detect_emoji: bool = True  # Auto-detect emoji in split content

    # Performance and rate limiting
    rate_limit_count: int = 0  # Rate limit count per window (0 disables)
    rate_limit_window: int = 60  # Rate limit window in seconds
    max_bytes: int = 1048576  # Maximum log file size (1MB default)
    storage_timeout: int = 30  # Storage operation timeout in seconds

    # Database and bulk optimization
    bulk_processing_enabled: bool = True
    database_batch_size: int = 100  # Batch size for database operations
    large_content_threshold: int = 50  # Items count for chunked processing

    # Error handling and validation
    strict_validation: bool = True
    sanitize_content: bool = True
    generate_entry_id: bool = True

    # Legacy compatibility
    enable_legacy_mode: bool = True
    fallback_agent: str = "Scribe"

    def __post_init__(self) -> None:
        """Post-initialization validation and normalization."""
        # Convert None meta to empty dict
        if self.meta is None:
            self.meta = {}

        # Store original agent for validation purposes
        self._original_agent = self.agent

        # Track which fields were explicitly provided (not from class defaults)
        # We'll use this in merge_with_defaults to distinguish explicit None vs default None
        self._explicit_fields = set()

        # Validate and normalize core parameters
        self.normalize()

        # Validate configuration if strict mode is enabled
        if self.strict_validation:
            self.validate()

    def validate(self) -> None:
        """
        Validate all configuration parameters using Phase 1 utilities.

        When strict_validation=False, this method skips validation to allow
        testing and configuration flexibility. When strict_validation=True,
        it performs full validation and raises ValueError for any issues.

        Raises:
            ValueError: If any parameter is invalid and strict_validation is True
        """
        # If strict validation is disabled, skip validation
        if not self.strict_validation:
            return

        errors = []

        # Validate content parameters
        errors.extend(self._validate_content_parameters())

        # Validate status and timestamp
        errors.extend(self._validate_status_and_timestamp())

        # Validate numeric parameters
        errors.extend(self._validate_numeric_parameters())

        # Validate agent identifier
        errors.extend(self._validate_agent_identifier())

        # Validate log type
        errors.extend(self._validate_log_type())

        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")

    def _validate_content_parameters(self) -> List[str]:
        """Validate content-related parameters."""
        errors = []

        # Validate items JSON format
        if self.items is not None:
            try:
                parsed_items = json.loads(self.items)
                if not isinstance(parsed_items, list):
                    errors.append("Items parameter must be a valid JSON array")
            except json.JSONDecodeError:
                errors.append("Items parameter must be valid JSON")

        # Validate items_list format
        if self.items_list is not None and not isinstance(self.items_list, list):
            errors.append("Items_list must be a list of dictionaries")

        return errors

    def _validate_status_and_timestamp(self) -> List[str]:
        """Validate status and timestamp parameters."""
        errors = []

        # Validate status using ToolValidator
        if self.status is not None:
            valid_statuses = ["info", "success", "warn", "error", "bug", "plan"]
            if self.status not in valid_statuses:
                errors.append(f"Status must be one of {valid_statuses}")

        # Validate timestamp using ToolValidator (smart validation)
        if self.timestamp_utc is not None:
            parsed_timestamp, normalized_timestamp, warning = ToolValidator.validate_timestamp(self.timestamp_utc)

            if warning and self.strict_validation:
                # Check if this is a format mismatch (acceptable) vs completely invalid (unacceptable)
                # ISO format like "2025-11-01T22:00:00Z" gives format warning but should be accepted
                # Complete garbage like "invalid-timestamp" should be rejected
                if "format invalid" in warning.lower():
                    # Check if the original timestamp looks like a legitimate timestamp format
                    # Accept common timestamp patterns even if ToolValidator prefers a different format
                    legit_patterns = [
                        # ISO 8601 patterns
                        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?",
                        # RFC 3339 patterns
                        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC",
                        # Basic datetime patterns
                        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                    ]

                    import re
                    is_legit_format = any(re.search(pattern, self.timestamp_utc) for pattern in legit_patterns)

                    if not is_legit_format:
                        # This looks like genuinely invalid timestamp, not just format mismatch
                        errors.append(f"Invalid timestamp: {warning}")
                else:
                    # Other types of timestamp warnings should be treated as errors in strict mode
                    errors.append(f"Invalid timestamp: {warning}")

            # Don't modify the original timestamp - validation should only validate, not normalize

        return errors

    def _validate_numeric_parameters(self) -> List[str]:
        """Validate numeric parameter ranges."""
        errors = []

        if self.stagger_seconds < 0:
            errors.append("Stagger seconds must be non-negative")
        if self.length_threshold < 0:
            errors.append("Length threshold must be non-negative")
        if self.chunk_size <= 0:
            errors.append("Chunk size must be positive")
        if self.rate_limit_count < 0:
            errors.append("Rate limit count must be non-negative")
        if self.rate_limit_window <= 0:
            errors.append("Rate limit window must be positive")
        if self.max_bytes <= 0:
            errors.append("Max bytes must be positive")

        return errors

    def _validate_agent_identifier(self) -> List[str]:
        """Validate agent identifier using ToolValidator."""
        errors = []

        if self.agent is not None:
            # Check if the original agent (before sanitization) was effectively empty
            original_agent = getattr(self, '_original_agent', self.agent)
            if isinstance(original_agent, str) and not original_agent.strip():
                errors.append("Agent identifier is invalid")
            else:
                sanitized_agent = ToolValidator.sanitize_identifier(self.agent)
                if not sanitized_agent:
                    errors.append("Agent identifier is invalid after sanitization")

        return errors

    def _validate_log_type(self) -> List[str]:
        """Validate log type parameter."""
        errors = []

        if self.log_type is not None:
            if not isinstance(self.log_type, str) or not self.log_type.strip():
                errors.append("Log type must be a non-empty string")

        return errors

    def normalize(self) -> None:
        """
        Normalize configuration parameters using Phase 1 utilities.

        This method applies default values, type conversions, and standardization
        to ensure consistent parameter handling.
        """
        # Normalize boolean parameters
        self.auto_split = _normalize_boolean(self.auto_split)
        self.bulk_processing_enabled = _normalize_boolean(self.bulk_processing_enabled)
        self.strict_validation = _normalize_boolean(self.strict_validation)
        self.sanitize_content = _normalize_boolean(self.sanitize_content)
        self.generate_entry_id = _normalize_boolean(self.generate_entry_id)
        self.enable_legacy_mode = _normalize_boolean(self.enable_legacy_mode)
        self.auto_detect_status = _normalize_boolean(self.auto_detect_status)
        self.auto_detect_emoji = _normalize_boolean(self.auto_detect_emoji)

        # Normalize numeric parameters
        self.stagger_seconds = max(0, int(self.stagger_seconds))
        self.length_threshold = max(0, int(self.length_threshold))
        self.chunk_size = max(1, int(self.chunk_size))
        self.rate_limit_count = max(0, int(self.rate_limit_count))
        self.rate_limit_window = max(1, int(self.rate_limit_window))
        self.max_bytes = max(1, int(self.max_bytes))
        self.storage_timeout = max(1, int(self.storage_timeout))
        self.database_batch_size = max(1, int(self.database_batch_size))
        self.large_content_threshold = max(1, int(self.large_content_threshold))

        # Normalize string parameters
        if self.split_delimiter is None:
            self.split_delimiter = "\n"
        if self.fallback_agent is None:
            self.fallback_agent = "Scribe"
        if self.log_type is None:
            self.log_type = "progress"

        # Normalize using ConfigManager for complex parameters
        # Sanitize agent identifier
        if self.agent:
            # Store pre-sanitization value for validation if it's different from original
            current_original = getattr(self, '_original_agent', None)
            if current_original != self.agent:
                self._original_agent = self.agent
            self.agent = ToolValidator.sanitize_identifier(self.agent)

        # Normalize metadata using ConfigManager
        if self.meta:
            coerced_meta, error = coerce_metadata_mapping(self.meta)
            if error:
                coerced_meta.setdefault("meta_error", error)
            self.meta = coerced_meta

    @classmethod
    def from_legacy_params(
        cls,
        message: str = "",
        status: Optional[str] = None,
        emoji: Optional[str] = None,
        agent: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        timestamp_utc: Optional[str] = None,
        items: Optional[str] = None,
        items_list: Optional[List[Dict[str, Any]]] = None,
        auto_split: bool = True,
        split_delimiter: str = "\n",
        stagger_seconds: int = 1,
        agent_id: Optional[str] = None,
        log_type: Optional[str] = "progress",
        priority: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        **kwargs: Any
    ) -> AppendEntryConfig:
        """
        Create configuration from legacy append_entry function parameters.

        This class method provides backward compatibility by accepting the exact
        parameter signature from the original append_entry function and creating
        a configuration object.

        Args:
            message: Log message
            status: Status type
            emoji: Custom emoji override
            agent: Agent identifier
            meta: Metadata dictionary
            timestamp_utc: UTC timestamp string
            items: JSON string array for bulk mode
            items_list: Direct list of entry dictionaries
            auto_split: Automatically split multiline messages
            split_delimiter: Delimiter for splitting
            stagger_seconds: Seconds to stagger timestamps
            agent_id: Agent identification
            log_type: Target log identifier
            **kwargs: Additional parameters for future compatibility

        Returns:
            AppendEntryConfig: Configuration object with all parameters
        """
        # Extract configuration parameters from kwargs if provided
        config_params = {}

        # Map known configuration parameters
        config_mapping = {
            'length_threshold': 'length_threshold',
            'chunk_size': 'chunk_size',
            'rate_limit_count': 'rate_limit_count',
            'rate_limit_window': 'rate_limit_window',
            'max_bytes': 'max_bytes',
            'storage_timeout': 'storage_timeout',
            'bulk_processing_enabled': 'bulk_processing_enabled',
            'database_batch_size': 'database_batch_size',
            'large_content_threshold': 'large_content_threshold',
            'strict_validation': 'strict_validation',
            'sanitize_content': 'sanitize_content',
            'generate_entry_id': 'generate_entry_id',
            'enable_legacy_mode': 'enable_legacy_mode',
            'fallback_agent': 'fallback_agent',
            'auto_detect_status': 'auto_detect_status',
            'auto_detect_emoji': 'auto_detect_emoji',
        }

        for key, value in kwargs.items():
            if key in config_mapping:
                config_params[config_mapping[key]] = value

        # Create configuration object
        config = cls(
            message=message,
            status=status,
            emoji=emoji,
            agent=agent,
            meta=meta,
            timestamp_utc=timestamp_utc,
            items=items,
            items_list=items_list,
            auto_split=auto_split,
            split_delimiter=split_delimiter,
            stagger_seconds=stagger_seconds,
            agent_id=agent_id,
            log_type=log_type,
            priority=priority,
            category=category,
            tags=tags,
            confidence=confidence,
            **config_params
        )

        return config

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary representation.

        Returns:
            Dictionary containing all configuration parameters
        """
        return {
            # Core content parameters
            'message': self.message,
            'status': self.status,
            'emoji': self.emoji,
            'agent': self.agent,
            'meta': self.meta,
            'timestamp_utc': self.timestamp_utc,

            # Priority and categorization parameters
            'priority': self.priority,
            'category': self.category,
            'tags': self.tags,
            'confidence': self.confidence,

            # Bulk processing parameters
            'items': self.items,
            'items_list': self.items_list,
            'auto_split': self.auto_split,
            'split_delimiter': self.split_delimiter,
            'stagger_seconds': self.stagger_seconds,

            # System parameters
            'agent_id': self.agent_id,
            'log_type': self.log_type,

            # Configuration parameters
            'length_threshold': self.length_threshold,
            'chunk_size': self.chunk_size,
            'auto_detect_status': self.auto_detect_status,
            'auto_detect_emoji': self.auto_detect_emoji,
            'rate_limit_count': self.rate_limit_count,
            'rate_limit_window': self.rate_limit_window,
            'max_bytes': self.max_bytes,
            'storage_timeout': self.storage_timeout,
            'bulk_processing_enabled': self.bulk_processing_enabled,
            'database_batch_size': self.database_batch_size,
            'large_content_threshold': self.large_content_threshold,
            'strict_validation': self.strict_validation,
            'sanitize_content': self.sanitize_content,
            'generate_entry_id': self.generate_entry_id,
            'enable_legacy_mode': self.enable_legacy_mode,
            'fallback_agent': self.fallback_agent,
        }

    def to_legacy_params(self) -> Dict[str, Any]:
        """
        Convert configuration to legacy function parameters.

        Returns:
            Dictionary compatible with original append_entry function signature
        """
        return {
            'message': self.message,
            'status': self.status,
            'emoji': self.emoji,
            'agent': self.agent,
            'meta': self.meta,
            'timestamp_utc': self.timestamp_utc,
            'items': self.items,
            'items_list': self.items_list,
            'auto_split': self.auto_split,
            'split_delimiter': self.split_delimiter,
            'stagger_seconds': self.stagger_seconds,
            'agent_id': self.agent_id,
            'log_type': self.log_type,
            'priority': self.priority,
            'category': self.category,
            'tags': self.tags,
            'confidence': self.confidence,
        }

    def merge_with_defaults(self, defaults: Dict[str, Any]) -> AppendEntryConfig:
        """
        Merge configuration with default values from project configuration.

        This method applies defaults conservatively: only fields that are None
        and are commonly expected to be overridden will be filled from defaults.

        Args:
            defaults: Default values from project configuration

        Returns:
            New configuration object with merged values
        """
        current_dict = self.to_dict()

        # Fields that are commonly expected to be overridden via defaults
        # These are fields where None typically means "use default"
        # Note: emoji is excluded based on test expectations - it should remain None if not explicitly set
        overridable_fields = {
            'status', 'agent', 'log_type', 'agent_id'
        }

        # Merge with conservative fallback logic
        merged = {}
        for key, value in current_dict.items():
            if (value is None or value == "") and key in defaults and key in overridable_fields:
                # Apply fallback for overridable None fields
                merged[key] = defaults[key]
            else:
                merged[key] = value

        return AppendEntryConfig(**merged)

    def is_bulk_mode(self) -> bool:
        """
        Determine if this configuration represents bulk mode operation.

        Returns:
            True if bulk mode should be used
        """
        # Check explicit bulk indicators
        if self.items is not None or self.items_list is not None:
            return True

        # Check auto-split conditions
        if self.auto_split and self.message:
            return len(self.message) > self.length_threshold

        return False

    def estimate_processing_time(self, item_count: int = 1) -> float:
        """
        Estimate processing time for this configuration.

        Args:
            item_count: Number of items to process (for bulk mode)

        Returns:
            Estimated processing time in seconds
        """
        base_time = 0.1  # Base processing overhead

        if self.is_bulk_mode():
            # Bulk mode processing time estimation
            items_to_process = item_count
            if self.items_list:
                items_to_process = len(self.items_list)
            elif self.items:
                try:
                    parsed = json.loads(self.items)
                    items_to_process = len(parsed) if isinstance(parsed, list) else 1
                except:
                    items_to_process = 1

            # Add chunking overhead for large content
            if items_to_process > self.large_content_threshold:
                chunks = (items_to_process + self.chunk_size - 1) // self.chunk_size
                base_time += chunks * 0.05  # Chunk processing overhead

            # Add per-item processing time
            base_time += items_to_process * 0.01

            # Add stagger time for timestamp staggering
            if self.stagger_seconds > 0:
                base_time += items_to_process * self.stagger_seconds * 0.001  # Convert to seconds

        # Add database operations time
        if self.bulk_processing_enabled:
            base_time += 0.05  # Database overhead

        return base_time
