"""Query Entries Configuration Module for TOOL_AUDIT_1112025 Project.

This module contains the QueryEntriesConfig dataclass which encapsulates
all 26 parameters from the query_entries tool with comprehensive validation
and search-specific configuration management.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp.utils.parameter_validator import ToolValidator, BulletproofParameterCorrector
from scribe_mcp.utils.config_manager import ConfigManager
from scribe_mcp.utils.error_handler import ErrorHandler, HealingErrorHandler


# Valid enumerated values for query parameters
VALID_MESSAGE_MODES = {"substring", "regex", "exact"}
VALID_SEARCH_SCOPES = {"project", "global", "all_projects", "research", "bugs", "all"}
VALID_DOCUMENT_TYPES = {"progress", "research", "architecture", "bugs", "global"}


@dataclass
class QueryEntriesConfig:
    """Configuration class for query_entries tool parameters.

    Encapsulates all 26 parameters from the query_entries function with
    comprehensive validation, defaults management, and search-specific
    configuration handling.
    """

    # Core search parameters
    project: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    message: Optional[str] = None
    message_mode: str = "substring"
    case_sensitive: bool = False

    # Filter parameters
    emoji: Optional[List[str]] = None
    status: Optional[List[str]] = None
    agents: Optional[List[str]] = None
    meta_filters: Optional[Dict[str, Any]] = None

    # Pagination parameters
    limit: int = 50
    page: int = 1
    page_size: int = 50

    # Response formatting parameters
    compact: bool = False
    fields: Optional[List[str]] = None
    include_metadata: bool = True

    # Phase 4 Enhanced Search Parameters
    search_scope: str = "project"
    document_types: Optional[List[str]] = None
    include_outdated: bool = True
    verify_code_references: bool = False
    time_range: Optional[str] = None
    relevance_threshold: float = 0.0
    max_results: Optional[int] = None

    # Internal configuration
    _config_manager: ConfigManager = field(
        default_factory=lambda: ConfigManager("query_entries"),
        init=False
    )
    _is_pagination_mode: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Post-initialization validation and setup with Phase 1 exception healing."""
        # Auto-detect pagination mode vs legacy mode
        self._resolve_pagination_mode()

        # Normalize list parameters
        self._normalize_list_parameters()

        # Apply safe normalization + defaults.
        #
        # NOTE: Do not auto-heal invalid enums/ranges here; the unit tests expect
        # QueryEntriesConfig.validate() to detect invalid values rather than
        # silently correcting them.
        self.normalize()

    def _resolve_pagination_mode(self) -> None:
        """Resolve pagination vs legacy limit mode."""
        # Convert string parameters to integers if needed
        original_page_size = int(self.page_size) if isinstance(self.page_size, str) else self.page_size
        page = int(self.page) if isinstance(self.page, str) else self.page

        # For config objects, preserve the original values without overriding limit
        # The pagination logic will be applied in the query_entries function
        self.page = page
        self.page_size = original_page_size

        # Only apply limit normalization if we're in legacy mode (page=1 and page_size=50)
        if page == 1 and original_page_size == 50:
            # Legacy mode - normalize limit
            if self.limit is not None:
                self.limit = int(self.limit) if isinstance(self.limit, str) else self.limit
                self.limit = max(1, min(self.limit or 50, 500))
                self.page_size = self.limit
            self._is_pagination_mode = False
        else:
            # Pagination mode - preserve pagination parameters but disable legacy limit
            self._is_pagination_mode = True
            self.limit = None

    def _normalize_list_parameters(self) -> None:
        """Normalize list parameters using utility functions."""
        if self.emoji is not None:
            self.emoji = ToolValidator.validate_list_parameter(self.emoji)
        if self.status is not None:
            self.status = ToolValidator.validate_list_parameter(self.status)
        if self.agents is not None:
            # Preserve agent casing (log lines store agents case-sensitively).
            # Other list parameters can be lowercased safely.
            if isinstance(self.agents, str):
                candidates = self.agents.split(",")
            else:
                candidates = self.agents
            cleaned: List[str] = []
            for candidate in candidates:
                text = str(candidate).strip()
                if text:
                    cleaned.append(text)
            self.agents = cleaned
        if self.fields is not None:
            self.fields = ToolValidator.validate_list_parameter(self.fields)
        if self.document_types is not None:
            self.document_types = ToolValidator.validate_list_parameter(self.document_types)

    def heal_and_validate(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Heal and validate all configuration parameters using Phase 1 utilities.

        Returns:
            Tuple of (is_valid, error_response_dict)
        """
        all_healing_messages = []

        # Heal enum parameters (Phase 1 BulletproofParameterCorrector)
        enum_healed, enum_messages = self._heal_enum_parameters()
        if enum_healed and enum_messages:
            all_healing_messages.extend(enum_messages)

        # Heal array parameters (Phase 1 BulletproofParameterCorrector)
        array_healed, array_messages = self.heal_array_parameters()
        if array_healed and array_messages:
            all_healing_messages.extend(array_messages)

        # Heal range parameters (Phase 1 BulletproofParameterCorrector)
        range_healed, range_messages = self._heal_range_parameters()
        if range_healed and range_messages:
            all_healing_messages.extend(range_messages)

        # Validate remaining parameters (regex, pagination, time)
        # These use existing validation methods
        is_valid, error = self._validate_regex_pattern()
        if not is_valid:
            return False, error

        is_valid, error = self._validate_pagination_parameters()
        if not is_valid:
            return False, error

        is_valid, error = self._validate_time_parameters()
        if not is_valid:
            return False, error

        # Return success with healing information if any parameters were corrected
        if all_healing_messages:
            return True, {
                "healing_applied": True,
                "healing_messages": all_healing_messages,
                "message": "Parameters auto-corrected using Phase 1 exception healing"
            }

        return True, None

    def validate(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Strict validation used by tests (no auto-healing)."""
        # Validate enums
        if self.message_mode not in VALID_MESSAGE_MODES:
            return False, {
                "error_type": "enum_validation_error",
                "error_message": f"Invalid message_mode '{self.message_mode}'. Must be one of: {', '.join(sorted(VALID_MESSAGE_MODES))}",
                "context": {"parameter": "message_mode", "value": self.message_mode},
            }

        if self.search_scope not in VALID_SEARCH_SCOPES:
            return False, {
                "error_type": "enum_validation_error",
                "error_message": f"Invalid search_scope '{self.search_scope}'. Must be one of: {', '.join(sorted(VALID_SEARCH_SCOPES))}",
                "context": {"parameter": "search_scope", "value": self.search_scope},
            }

        if self.document_types:
            invalid = [dt for dt in self.document_types if dt not in VALID_DOCUMENT_TYPES]
            if invalid:
                return False, {
                    "error_type": "enum_validation_error",
                    "error_message": f"Invalid document_types {invalid}. Must be subset of: {', '.join(sorted(VALID_DOCUMENT_TYPES))}",
                    "context": {"parameter": "document_types", "value": self.document_types},
                }

        # Validate relevance threshold
        if self.relevance_threshold is not None and (self.relevance_threshold < 0.0 or self.relevance_threshold > 1.0):
            return False, {
                "error_type": "validation_error",
                "error_message": f"relevance_threshold must be between 0.0 and 1.0, got {self.relevance_threshold}",
                "context": {"parameter": "relevance_threshold", "value": self.relevance_threshold},
            }

        # Validate remaining parameters (regex, pagination, time)
        is_valid, error = self._validate_regex_pattern()
        if not is_valid:
            return False, error

        is_valid, error = self._validate_pagination_parameters()
        if not is_valid:
            return False, error

        is_valid, error = self._validate_time_parameters()
        if not is_valid:
            return False, error

        return True, None

    def _heal_enum_parameters(self) -> Tuple[bool, Optional[List[str]]]:
        """Heal enumeration parameters using Phase 1 BulletproofParameterCorrector."""
        healing_messages = []

        # Heal message_mode with auto-correction
        original_message_mode = self.message_mode
        healed_message_mode = BulletproofParameterCorrector.correct_enum_parameter(
            original_message_mode, VALID_MESSAGE_MODES, "message_mode", "substring"
        )
        if healed_message_mode != original_message_mode:
            self.message_mode = healed_message_mode
            healing_messages.append(f"Auto-corrected message_mode from '{original_message_mode}' to '{healed_message_mode}'")

        # Heal search_scope with auto-correction
        original_search_scope = self.search_scope
        healed_search_scope = BulletproofParameterCorrector.correct_enum_parameter(
            original_search_scope, VALID_SEARCH_SCOPES, "search_scope", "project"
        )
        if healed_search_scope != original_search_scope:
            self.search_scope = healed_search_scope
            healing_messages.append(f"Auto-corrected search_scope from '{original_search_scope}' to '{healed_search_scope}'")

        # Heal document_types if provided
        if self.document_types:
            original_document_types = self.document_types.copy()
            healed_document_types = []
            for doc_type in self.document_types:
                healed_type = BulletproofParameterCorrector.correct_enum_parameter(
                    doc_type, VALID_DOCUMENT_TYPES, "document_types", "progress"
                )
                healed_document_types.append(healed_type)
                if healed_type != doc_type:
                    healing_messages.append(f"Auto-corrected document_type from '{doc_type}' to '{healed_type}'")

            if healed_document_types != original_document_types:
                self.document_types = healed_document_types

        return len(healing_messages) > 0, healing_messages if healing_messages else None

    def heal_array_parameters(self) -> Tuple[bool, Optional[List[str]]]:
        """Heal array parameters using Phase 1 BulletproofParameterCorrector for list handling."""
        healing_messages = []

        # Heal emoji array parameter
        if self.emoji is not None:
            original_emoji = self.emoji
            healed_emoji = BulletproofParameterCorrector.correct_list_parameter(
                original_emoji, "emoji"
            )
            if healed_emoji != original_emoji:
                self.emoji = healed_emoji
                healing_messages.append(f"Auto-corrected emoji parameter from {original_emoji} to {healed_emoji}")

        # Heal status array parameter
        if self.status is not None:
            original_status = self.status
            healed_status = BulletproofParameterCorrector.correct_list_parameter(
                original_status, "status"
            )
            if healed_status != original_status:
                self.status = healed_status
                healing_messages.append(f"Auto-corrected status parameter from {original_status} to {healed_status}")

        # Heal agents array parameter
        if self.agents is not None:
            original_agents = self.agents
            healed_agents = BulletproofParameterCorrector.correct_list_parameter(
                original_agents, "agents"
            )
            if healed_agents != original_agents:
                self.agents = healed_agents
                healing_messages.append(f"Auto-corrected agents parameter from {original_agents} to {healed_agents}")

        # Heal fields array parameter
        if self.fields is not None:
            original_fields = self.fields
            healed_fields = BulletproofParameterCorrector.correct_list_parameter(
                original_fields, "fields"
            )
            if healed_fields != original_fields:
                self.fields = healed_fields
                healing_messages.append(f"Auto-corrected fields parameter from {original_fields} to {healed_fields}")

        # Heal document_types array parameter (in addition to enum healing)
        if self.document_types is not None:
            original_document_types = self.document_types
            healed_document_types = BulletproofParameterCorrector.correct_list_parameter(
                original_document_types, "document_types"
            )
            if healed_document_types != original_document_types:
                self.document_types = healed_document_types
                healing_messages.append(f"Auto-corrected document_types parameter from {original_document_types} to {healed_document_types}")

        return len(healing_messages) > 0, healing_messages if healing_messages else None

    def _heal_range_parameters(self) -> Tuple[bool, Optional[List[str]]]:
        """Heal range parameters using Phase 1 BulletproofParameterCorrector."""
        healing_messages = []

        # Heal relevance_threshold with auto-correction (0.0-1.0)
        original_relevance_threshold = self.relevance_threshold
        healed_relevance_threshold = BulletproofParameterCorrector.correct_numeric_parameter(
            original_relevance_threshold, 0.0, 1.0, "relevance_threshold", 0.0
        )
        if healed_relevance_threshold != original_relevance_threshold:
            self.relevance_threshold = healed_relevance_threshold
            healing_messages.append(f"Auto-corrected relevance_threshold from '{original_relevance_threshold}' to '{healed_relevance_threshold}'")

        return len(healing_messages) > 0, healing_messages if healing_messages else None

    def _validate_regex_pattern(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Validate regex pattern if message_mode is 'regex'."""
        if self.message and self.message_mode == "regex":
            error = ToolValidator.validate_regex_pattern(self.message)
            if error:
                error_response = {
                    "error_type": "regex_error",
                    "error_message": error,
                    "context": {
                        "parameter": "message",
                        "value": self.message,
                        "mode": "regex"
                    }
                }
                return False, error_response

        return True, None

    def _validate_pagination_parameters(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Validate pagination parameters."""
        # Validate page (must be >= 1) if provided
        if self.page is not None and self.page < 1:
            error_response = {
                "error_type": "validation_error",
                "error_message": f"page must be >= 1, got {self.page}",
                "context": {
                    "parameter": "page",
                    "value": self.page
                }
            }
            return False, error_response

        # Validate page_size (must be between 1 and 500) if provided
        if self.page_size is not None and (self.page_size < 1 or self.page_size > 500):
            error_response = {
                "error_type": "validation_error",
                "error_message": f"page_size must be between 1 and 500, got {self.page_size}",
                "context": {
                    "parameter": "page_size",
                    "value": self.page_size
                }
            }
            return False, error_response

        # Validate limit (must be between 1 and 500) if provided
        if self.limit is not None and (self.limit < 1 or self.limit > 500):
            error_response = {
                "error_type": "validation_error",
                "error_message": f"limit must be between 1 and 500, got {self.limit}",
                "context": {
                    "parameter": "limit",
                    "value": self.limit
                }
            }
            return False, error_response

        return True, None

    def _validate_time_parameters(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Validate time-related parameters."""
        # Validate time_range format if provided
        if self.time_range:
            valid_time_ranges = {
                "today", "yesterday", "last_7d", "last_30d", "last_90d",
                "this_week", "last_week", "this_month", "last_month"
            }
            if self.time_range not in valid_time_ranges:
                error_response = {
                    "error_type": "enum_validation_error",
                    "error_message": f"Invalid time_range '{self.time_range}'. Must be one of: {', '.join(sorted(valid_time_ranges))}",
                    "context": {
                        "parameter": "time_range",
                        "value": self.time_range
                    }
                }
                return False, error_response

        return True, None

    def normalize(self) -> None:
        """Normalize configuration parameters using utility functions."""
        # Normalize message_mode
        self.message_mode = (self.message_mode or "substring").lower()

        # Normalize search_scope
        self.search_scope = (self.search_scope or "project").lower()

        # Apply configuration manager defaults
        self._apply_config_defaults()

    def _apply_config_defaults(self) -> None:
        """Apply defaults from configuration manager."""
        # QueryEntriesConfig doesn't have an agent parameter,
        # but we keep the method for consistency with other config classes
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary representation."""
        result = {}
        for key, value in self.__dict__.items():
            if not key.startswith('_'):  # Skip private attributes
                result[key] = value
        return result

    def to_tool_params(self) -> Dict[str, Any]:
        """Convert to parameters suitable for query_entries tool call."""
        params = self.to_dict()

        # Handle legacy max_results parameter
        if self.max_results is not None:
            params['limit'] = self.max_results

        # Remove internal-only parameters
        params.pop('max_results', None)

        return params

    @classmethod
    def from_legacy_params(cls, **kwargs) -> QueryEntriesConfig:
        """Create configuration from legacy parameter dictionary.

        Args:
            **kwargs: Legacy parameters from query_entries function

        Returns:
            QueryEntriesConfig instance
        """
        # Filter out None values and apply defaults
        filtered_params = {}
        for key, value in kwargs.items():
            if hasattr(cls, key) or key in cls.__dataclass_fields__:
                filtered_params[key] = value

        return cls(**filtered_params)

    @classmethod
    def create_search_config(
        cls,
        query: Optional[str] = None,
        scope: str = "project",
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> QueryEntriesConfig:
        """Create a search-focused configuration.

        Args:
            query: Search query string
            scope: Search scope
            filters: Additional filters
            **kwargs: Additional parameters

        Returns:
            QueryEntriesConfig optimized for search
        """
        params = {
            "message": query,
            "search_scope": scope,
            "message_mode": "substring",
            "include_metadata": True,
            "compact": False
        }

        # Apply filters
        if filters:
            if "emoji" in filters:
                params["emoji"] = filters["emoji"]
            if "status" in filters:
                params["status"] = filters["status"]
            if "agents" in filters:
                params["agents"] = filters["agents"]
            if "document_types" in filters:
                params["document_types"] = filters["document_types"]

        # Override with any explicit parameters
        params.update(kwargs)

        return cls(**params)

    def get_effective_limit(self) -> int:
        """Get the effective limit based on pagination mode."""
        if self.limit is not None:
            return self.limit
        return self.page_size

    def is_pagination_mode(self) -> bool:
        """Check if configuration is using pagination mode."""
        return self._is_pagination_mode

    def get_search_description(self) -> str:
        """Get a human-readable description of the search configuration."""
        parts = []

        if self.message:
            parts.append(f"message='{self.message}' ({self.message_mode})")

        if self.search_scope != "project":
            parts.append(f"scope={self.search_scope}")

        if self.emoji:
            parts.append(f"emoji={self.emoji}")

        if self.status:
            parts.append(f"status={self.status}")

        if self.agents:
            parts.append(f"agents={self.agents}")

        if self.document_types:
            parts.append(f"document_types={self.document_types}")

        if self.relevance_threshold > 0.0:
            parts.append(f"relevance≥{self.relevance_threshold}")

        if self.time_range:
            parts.append(f"time={self.time_range}")

        return " | ".join(parts) if parts else "all entries"


# Convenience functions for backward compatibility
def create_query_config(**kwargs) -> QueryEntriesConfig:
    """Create QueryEntriesConfig from parameters.

    Args:
        **kwargs: Configuration parameters

    Returns:
        QueryEntriesConfig instance
    """
    return QueryEntriesConfig(**kwargs)


def create_search_config(
    query: Optional[str] = None,
    scope: str = "project",
    **kwargs
) -> QueryEntriesConfig:
    """Create a search-focused configuration.

    Args:
        query: Search query string
        scope: Search scope
        **kwargs: Additional parameters

    Returns:
        QueryEntriesConfig optimized for search
    """
    return QueryEntriesConfig.create_search_config(query, scope, **kwargs)
