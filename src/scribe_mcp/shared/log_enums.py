#!/usr/bin/env python3
"""
Log Priority and Category Enums for Scribe MCP

Provides semantic classification for log entries:
- LogPriority: Determines retention and display order
- LogCategory: Semantic categorization for intelligent filtering

Part of scribe_tool_output_refinement project.
"""

from enum import Enum
from typing import Optional


class LogPriority(Enum):
    """Priority levels for log entries - determines retention and display order"""
    CRITICAL = "critical"  # Security issues, blocking bugs, architectural decisions
    HIGH = "high"          # Implementation milestones, test failures, major findings
    MEDIUM = "medium"      # Code changes, successful tests, investigation results
    LOW = "low"            # Debug info, minor updates, routine operations


class LogCategory(Enum):
    """Semantic categorization for intelligent filtering"""
    DECISION = "decision"              # Architectural or design decisions
    INVESTIGATION = "investigation"    # Research and analysis
    BUG = "bug"                        # Bug discovery and fixes
    IMPLEMENTATION = "implementation"  # Code changes
    TEST = "test"                      # Test results
    MILESTONE = "milestone"            # Project milestones
    CONFIG = "config"                  # Configuration changes
    SECURITY = "security"              # Security-related events
    PERFORMANCE = "performance"        # Performance analysis
    DOCUMENTATION = "documentation"    # Documentation updates


def validate_priority(value: Optional[str]) -> Optional[LogPriority]:
    """
    Validate and convert a priority value to LogPriority enum.

    Args:
        value: Priority string (case-insensitive) or LogPriority enum

    Returns:
        LogPriority enum value or None if value is None

    Raises:
        ValueError: If value is not a valid priority

    Examples:
        >>> validate_priority("high")
        <LogPriority.HIGH: 'high'>
        >>> validate_priority("HIGH")
        <LogPriority.HIGH: 'high'>
        >>> validate_priority(None)
        None
    """
    if value is None:
        return None

    if isinstance(value, LogPriority):
        return value

    if not isinstance(value, str):
        raise ValueError(f"Priority must be string or LogPriority enum, got {type(value)}")

    # Case-insensitive matching
    normalized = value.lower()
    try:
        return LogPriority(normalized)
    except ValueError:
        valid_values = [p.value for p in LogPriority]
        raise ValueError(f"Invalid priority '{value}'. Must be one of: {valid_values}")


def validate_category(value: Optional[str]) -> Optional[LogCategory]:
    """
    Validate and convert a category value to LogCategory enum.

    Args:
        value: Category string (case-insensitive) or LogCategory enum

    Returns:
        LogCategory enum value or None if value is None

    Raises:
        ValueError: If value is not a valid category

    Examples:
        >>> validate_category("bug")
        <LogCategory.BUG: 'bug'>
        >>> validate_category("BUG")
        <LogCategory.BUG: 'bug'>
        >>> validate_category(None)
        None
    """
    if value is None:
        return None

    if isinstance(value, LogCategory):
        return value

    if not isinstance(value, str):
        raise ValueError(f"Category must be string or LogCategory enum, got {type(value)}")

    # Case-insensitive matching
    normalized = value.lower()
    try:
        return LogCategory(normalized)
    except ValueError:
        valid_values = [c.value for c in LogCategory]
        raise ValueError(f"Invalid category '{value}'. Must be one of: {valid_values}")


def infer_priority_from_status(status: str) -> LogPriority:
    """
    Infer log priority from status emoji/keyword.

    Maps common status values to appropriate priority levels:
    - error, bug → HIGH (needs immediate attention)
    - warn → MEDIUM (should be reviewed)
    - success → MEDIUM (normal progress)
    - info → LOW (routine information)
    - plan → MEDIUM (planning activities)

    Args:
        status: Status keyword (error, bug, warn, success, info, plan)

    Returns:
        LogPriority enum value (defaults to MEDIUM for unknown status)

    Examples:
        >>> infer_priority_from_status("error")
        <LogPriority.HIGH: 'high'>
        >>> infer_priority_from_status("success")
        <LogPriority.MEDIUM: 'medium'>
        >>> infer_priority_from_status("unknown")
        <LogPriority.MEDIUM: 'medium'>
    """
    status_map = {
        "error": LogPriority.HIGH,
        "bug": LogPriority.HIGH,
        "warn": LogPriority.MEDIUM,
        "success": LogPriority.MEDIUM,
        "info": LogPriority.LOW,
        "plan": LogPriority.MEDIUM,
    }

    # Case-insensitive lookup with default to MEDIUM
    return status_map.get(status.lower() if isinstance(status, str) else status, LogPriority.MEDIUM)


def get_priority_sort_key(priority: str) -> int:
    """
    Get numeric sort key for priority level.

    Lower numbers = higher priority (for sorting).
    - critical = 0 (highest)
    - high = 1
    - medium = 2
    - low = 3 (lowest)

    Args:
        priority: Priority string or LogPriority enum

    Returns:
        Integer sort key (0-3)

    Raises:
        ValueError: If priority is invalid

    Examples:
        >>> get_priority_sort_key("critical")
        0
        >>> get_priority_sort_key("low")
        3
        >>> sorted(["low", "critical", "medium"], key=get_priority_sort_key)
        ['critical', 'medium', 'low']
    """
    # Validate and normalize
    priority_enum = validate_priority(priority)
    if priority_enum is None:
        raise ValueError("Priority cannot be None for sorting")

    sort_order = {
        LogPriority.CRITICAL: 0,
        LogPriority.HIGH: 1,
        LogPriority.MEDIUM: 2,
        LogPriority.LOW: 3,
    }

    return sort_order[priority_enum]
