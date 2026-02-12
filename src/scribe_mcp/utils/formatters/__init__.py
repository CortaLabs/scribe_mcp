"""Formatter modules for Scribe MCP responses."""

from .base import (
    BaseFormatter,
    get_use_ansi_colors,
    create_pagination_info,
    format_compact_json,
)
from .ui import UIFormatter, format_header, add_tip
from .file import FileFormatter
from .entry import EntryFormatter
from .project import ProjectFormatter
from .dispatcher import FormatterDispatcher

# Re-export PaginationInfo from estimator for convenience
from ..estimator import PaginationInfo

__all__ = [
    # Base formatter utilities
    "BaseFormatter",
    "PaginationInfo",
    "get_use_ansi_colors",
    "create_pagination_info",
    "format_compact_json",
    # UI formatter utilities
    "UIFormatter",
    "format_header",
    "add_tip",
    # File formatter utilities
    "FileFormatter",
    # Entry formatter utilities
    "EntryFormatter",
    # Project formatter utilities
    "ProjectFormatter",
    # Dispatcher (central router)
    "FormatterDispatcher",
]
