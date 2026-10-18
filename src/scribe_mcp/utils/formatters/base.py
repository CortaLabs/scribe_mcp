"""Base formatting utilities, color detection, and common helpers.

This module provides foundational formatting utilities extracted from ResponseFormatter
as part of Phase 5 modularization (Task 5.2). Contains:
- BaseFormatter class: Common utilities for all formatters
- Color detection: get_use_ansi_colors()
- Pagination helpers: create_pagination_info()
- JSON compaction: format_compact_json()

Note: PaginationInfo is imported from utils.estimator (not duplicated here).
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

# Import PaginationInfo and PaginationCalculator from estimator (DRY - no duplication)
from ..estimator import PaginationInfo, PaginationCalculator, TokenEstimator


def get_use_ansi_colors() -> bool:
    """
    Get ANSI color setting from repo config.

    Phase 1.5/1.6: Load use_ansi_colors from .scribe/config/scribe.yaml
    Falls back to True (colors enabled by default) if config unavailable.

    Returns:
        bool: True if ANSI colors should be used, False otherwise.
    """
    try:
        from scribe_mcp.config.repo_config import get_current_repo_config
        _, config = get_current_repo_config()
        return config.use_ansi_colors
    except Exception:
        # Fallback: colors enabled by default
        return True


# Module-level instances for delegation
_PAGINATION_CALCULATOR = PaginationCalculator()
_TOKEN_ESTIMATOR = TokenEstimator()


def create_pagination_info(page: int, page_size: int, total_count: int) -> PaginationInfo:
    """Create pagination metadata using PaginationCalculator.

    Args:
        page: Current page number (1-based)
        page_size: Number of items per page
        total_count: Total number of items

    Returns:
        PaginationInfo: Pagination metadata object
    """
    return _PAGINATION_CALCULATOR.create_pagination_info(page, page_size, total_count)


def format_compact_json(
    data: dict,
    abbreviations: Optional[dict] = None
) -> str:
    """
    Format JSON with abbreviated keys for compact mode.

    This function implements Pattern 2 from SPEC-TOKEN-003: Verbose JSON Keys.
    Reduces JSON output size by 20-40% through key abbreviation.

    Args:
        data: Data dictionary to format
        abbreviations: Custom abbreviation mappings (optional, uses global defaults)

    Returns:
        Compact JSON string with abbreviated keys

    Examples:
        >>> data = {"projects": [{"name": "test", "status": "planning"}], "total_count": 1}
        >>> format_compact_json(data)
        '{"p":[{"n":"test","s":"planning"}],"tot":1}'
    """
    # Global abbreviation mappings (SPEC-TOKEN-003)
    default_abbreviations = {
        # Common metadata
        "ok": "ok",  # Already minimal
        "status": "s",
        "message": "msg",
        "error": "err",

        # Project fields
        "project": "proj",
        "projects": "p",
        "name": "n",
        "root": "r",
        "progress_log": "log",

        # Pagination
        "pagination": "pg",
        "page": "i",
        "page_size": "sz",
        "total_count": "tot",
        "has_next": "nx",
        "has_prev": "pv",

        # Timestamps
        "timestamp": "ts",
        "created_at": "cr",
        "updated_at": "up",
        "last_activity": "act",

        # Entries
        "entries": "e",
        "count": "c",
        "results": "r",

        # Metadata
        "metadata": "meta",
        "confidence": "conf",
        "priority": "pri",
        "category": "cat",
    }

    # Merge custom abbreviations if provided
    abbrev_map = default_abbreviations.copy()
    if abbreviations:
        abbrev_map.update(abbreviations)

    def abbreviate_dict(obj):
        """Recursively abbreviate dictionary keys."""
        if isinstance(obj, dict):
            return {
                abbrev_map.get(k, k): abbreviate_dict(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [abbreviate_dict(item) for item in obj]
        else:
            return obj

    abbreviated = abbreviate_dict(data)
    return json.dumps(abbreviated, separators=(',', ':'))


class BaseFormatter:
    """Base class for all formatters with common utilities.

    This class provides foundational formatting capabilities that are shared
    across all formatter types (UI, File, Entry, Project, etc.).

    Attributes:
        ANSI_*: Color codes for terminal output
        _use_colors: Whether to include ANSI color codes in output
        _token_warning_threshold: Token count threshold for warnings
    """

    # ANSI color codes for enhanced readability in Claude Code
    ANSI_CYAN = "\033[36m"
    ANSI_GREEN = "\033[32m"
    ANSI_YELLOW = "\033[33m"
    ANSI_BLUE = "\033[34m"
    ANSI_MAGENTA = "\033[35m"
    ANSI_BOLD = "\033[1m"
    ANSI_DIM = "\033[2m"
    ANSI_RESET = "\033[0m"

    def __init__(self, token_warning_threshold: int = 4000):
        """Initialize BaseFormatter.

        Args:
            token_warning_threshold: Token count threshold for warnings.
                                    Defaults to 4000.
        """
        self._token_warning_threshold = token_warning_threshold
        self._use_colors = get_use_ansi_colors()
        self._token_estimator = _TOKEN_ESTIMATOR

    @property
    def USE_COLORS(self) -> bool:
        """Check if ANSI colors are enabled.

        Returns:
            bool: True if colors should be used, False otherwise.
        """
        return self._use_colors

    @USE_COLORS.setter
    def USE_COLORS(self, value: bool) -> None:
        """Set color usage.

        Args:
            value: Whether to use colors.
        """
        self._use_colors = value

    def estimate_tokens(self, data: Union[Dict, List, str]) -> int:
        """
        Estimate token count for response data using TokenEstimator.

        Args:
            data: Data to estimate tokens for (dict, list, or string)

        Returns:
            int: Estimated token count
        """
        return self._token_estimator.estimate_tokens(data)

    def format_relative_time(self, timestamp: str) -> str:
        """
        Convert timestamp to relative time string.

        Examples:
            "2026-01-03T08:15:30Z" -> "2 hours ago" (if now is 10:15)
            "2026-01-02T10:00:00Z" -> "1 day ago"
            "2025-12-20T14:30:00Z" -> "2 weeks ago"

        Args:
            timestamp: ISO 8601 timestamp string (UTC)

        Returns:
            Relative time string or original timestamp if parsing fails
        """
        try:
            # Parse ISO 8601 formats: "YYYY-MM-DDTHH:MM:SSZ" or "YYYY-MM-DD HH:MM:SS UTC"
            # Check for UTC suffix first before checking for ISO T separator
            if timestamp.upper().endswith(' UTC'):
                # Space-separated format with UTC suffix (case-insensitive)
                # Remove the last 4 characters (' UTC' or ' utc')
                ts_clean = timestamp[:-4]
                ts_dt = datetime.strptime(ts_clean, '%Y-%m-%d %H:%M:%S')
            elif 'T' in timestamp:
                # ISO format with T separator (YYYY-MM-DDTHH:MM:SS)
                ts_clean = timestamp.replace('Z', '').replace('+00:00', '')
                ts_dt = datetime.fromisoformat(ts_clean)
            else:
                # Try generic ISO parsing
                ts_dt = datetime.fromisoformat(timestamp)

            # Calculate time delta from now
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            delta = now - ts_dt

            # Format based on magnitude
            total_seconds = delta.total_seconds()

            if total_seconds < 60:
                return "just now"
            elif total_seconds < 3600:  # < 60 minutes
                minutes = int(total_seconds / 60)
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            elif total_seconds < 7200:  # < 2 hours
                return "1 hour ago"
            elif total_seconds < 86400:  # < 24 hours
                hours = int(total_seconds / 3600)
                return f"{hours} hours ago"
            elif total_seconds < 172800:  # < 2 days
                return "1 day ago"
            elif total_seconds < 604800:  # < 7 days
                days = int(total_seconds / 86400)
                return f"{days} days ago"
            elif total_seconds < 1209600:  # < 14 days
                return "1 week ago"
            elif total_seconds < 2592000:  # < 30 days
                weeks = int(total_seconds / 604800)
                return f"{weeks} weeks ago"
            elif total_seconds < 5184000:  # < 60 days
                return "1 month ago"
            else:
                months = int(total_seconds / 2592000)
                return f"{months} months ago"
        except (ValueError, AttributeError, TypeError):
            # Return original timestamp on parsing failure
            return timestamp

    def format_readable_error(self, error: str, context: Dict[str, Any]) -> str:
        """
        Format error messages in readable format.

        Note: This method requires access to _create_header_box and _create_footer_box
        which are implemented in UIFormatter. Subclasses that need this functionality
        should inherit from UIFormatter or implement those methods.

        Args:
            error: Error message
            context: Error context data

        Returns:
            Formatted error string
        """
        # Build header
        header_meta = {
            'status': 'ERROR',
            'type': context.get('error_type', 'unknown')
        }

        parts = []
        # Use protected methods that should be overridden by subclasses
        parts.append(self._create_header_box("ERROR", header_meta))
        parts.append("")
        parts.append(f"\u274c {error}")
        parts.append("")

        # Add context if available
        if context:
            footer_meta = {k: v for k, v in context.items() if k != 'error_type'}
            parts.append(self._create_footer_box(footer_meta))

        return '\n'.join(parts)

    def _create_header_box(self, title: str, metadata: Dict[str, Any]) -> str:
        """Create header box - override in subclass or use UIFormatter."""
        # Basic fallback implementation without box drawing
        lines = [f"=== {title} ==="]
        for k, v in metadata.items():
            lines.append(f"  {k}: {v}")
        return '\n'.join(lines)

    def _create_footer_box(self, metadata: Dict[str, Any]) -> str:
        """Create footer box - override in subclass or use UIFormatter."""
        # Basic fallback implementation without box drawing
        lines = ["---"]
        for k, v in metadata.items():
            lines.append(f"  {k}: {v}")
        lines.append("---")
        return '\n'.join(lines)
