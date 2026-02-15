"""UI formatting utilities for ASCII boxes, tables, and headers.

This module provides visual formatting utilities extracted from ResponseFormatter
as part of Phase 5 modularization (Task 5.1). Contains:
- UIFormatter class: ASCII boxes, tables, line numbers (inherits from BaseFormatter)
- Standalone functions: format_header, add_tip
"""

from typing import Any, Dict, List, Optional
import json

from .base import BaseFormatter


class UIFormatter(BaseFormatter):
    """Handles ASCII box drawing, tables, and visual elements.

    This class contains UI-related formatting methods extracted from
    ResponseFormatter to improve modularity and testability.

    Inherits ANSI color codes and common utilities from BaseFormatter.
    """

    def __init__(self, use_colors: bool = None, token_warning_threshold: int = 4000):
        """Initialize UIFormatter.

        Args:
            use_colors: Whether to include ANSI color codes in output.
                       None = auto-detect from config.
            token_warning_threshold: Token count threshold for warnings.
        """
        super().__init__(token_warning_threshold)
        if use_colors is not None:
            self._use_colors = use_colors

    @property
    def use_colors(self) -> bool:
        """Get current color setting."""
        return self._use_colors

    @use_colors.setter
    def use_colors(self, value: bool) -> None:
        """Set color setting."""
        self._use_colors = value

    def add_line_numbers(self, content: str, start: int = 1) -> str:
        """
        Add line numbers to content with optional green coloring.

        Format: "     1. Line content" (with green line numbers if colors enabled)

        Args:
            content: Text content to number
            start: Starting line number (default: 1)

        Returns:
            Line-numbered string with consistent padding
        """
        if not content:
            return ""

        lines = content.split('\n')
        if not lines:
            return ""

        # Calculate max line number for padding (minimum 5 chars to match Claude Read style)
        max_line = start + len(lines) - 1
        width = max(5, len(str(max_line)))  # Minimum 5 chars like Claude's "     1."

        # Color helpers (green line numbers)
        G = self.ANSI_GREEN if self._use_colors else ""
        R = self.ANSI_RESET if self._use_colors else ""

        # Format each line with right-aligned line number (green with dot separator)
        numbered_lines = []
        for i, line in enumerate(lines, start=start):
            line_num = str(i).rjust(width)
            numbered_lines.append(f"{G}{line_num}.{R} {line}")

        return '\n'.join(numbered_lines)

    def create_header_box(self, title: str, metadata: Dict[str, Any]) -> str:
        """
        Create ASCII box header with title and metadata.

        Format:
        +==============================================================+
        | TITLE                                                        |
        +--------------------------------------------------------------+
        | key1: value1                                                 |
        | key2: value2                                                 |
        +==============================================================+

        Args:
            title: Header title text
            metadata: Dictionary of metadata key-value pairs

        Returns:
            Formatted ASCII box as string
        """
        # Calculate box width (default 80 chars)
        box_width = 80
        inner_width = box_width - 4  # Account for borders

        lines = []

        # Color helpers
        C = self.ANSI_CYAN if self._use_colors else ""
        G = self.ANSI_GREEN if self._use_colors else ""
        Y = self.ANSI_YELLOW if self._use_colors else ""
        B = self.ANSI_BOLD if self._use_colors else ""
        R = self.ANSI_RESET if self._use_colors else ""

        # Top border
        lines.append(f"{C}\u2554" + "\u2550" * (box_width - 2) + f"\u2557{R}")

        # Title line (centered, bold)
        title_display = f"{B}{title}{R}"
        # Account for ANSI codes in centering
        title_padded = f" {title_display} ".center(inner_width + len(B) + len(R))
        lines.append(f"{C}\u2551{R} {title_padded} {C}\u2551{R}")

        # Separator
        lines.append(f"{C}\u255f" + "\u2500" * (box_width - 2) + f"\u2562{R}")

        # Metadata lines
        for key, value in metadata.items():
            # Format value
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            # Truncate if too long (account for color codes in calculation)
            raw_content = f"{key}: {value_str}"
            if len(raw_content) > inner_width:
                raw_content = raw_content[:inner_width - 3] + "..."
                # Also truncate value_str for colored output
                value_str = raw_content[len(key) + 2:]  # Skip "key: " part

            # Apply colors: key in green, value in default
            colored_content = f"{G}{key}:{R} {value_str}"
            # Calculate padding based on raw length (without ANSI codes)
            padding_needed = inner_width - len(raw_content)
            line_padded = f" {colored_content}{' ' * padding_needed} "
            lines.append(f"{C}\u2551{R}{line_padded}{C}\u2551{R}")

        # Bottom border
        lines.append(f"{C}\u255a" + "\u2550" * (box_width - 2) + f"\u255d{R}")

        return '\n'.join(lines)

    def create_footer_box(self, audit_data: Dict[str, Any],
                          reminders: Optional[List[Dict]] = None) -> str:
        """
        Create ASCII box footer with audit data and optional reminders.

        Format:
        +==============================================================+
        | METADATA                                                     |
        +--------------------------------------------------------------+
        | audit_key1: value1                                           |
        | audit_key2: value2                                           |
        +--------------------------------------------------------------+
        | REMINDERS                                                    |
        | * Reminder 1                                                 |
        | * Reminder 2                                                 |
        +==============================================================+

        Args:
            audit_data: Dictionary of audit/metadata
            reminders: Optional list of reminder dictionaries

        Returns:
            Formatted ASCII box as string
        """
        box_width = 80
        inner_width = box_width - 4

        # Color helpers
        C = self.ANSI_CYAN if self._use_colors else ""
        G = self.ANSI_GREEN if self._use_colors else ""
        Y = self.ANSI_YELLOW if self._use_colors else ""
        M = self.ANSI_MAGENTA if self._use_colors else ""
        B = self.ANSI_BOLD if self._use_colors else ""
        R = self.ANSI_RESET if self._use_colors else ""

        lines = []

        # Top border
        lines.append(f"{C}\u2554" + "\u2550" * (box_width - 2) + f"\u2557{R}")

        # Metadata section title
        title_display = f"{B}METADATA{R}"
        title_padded = f" {title_display} ".center(inner_width + len(B) + len(R))
        lines.append(f"{C}\u2551{R} {title_padded} {C}\u2551{R}")
        lines.append(f"{C}\u255f" + "\u2500" * (box_width - 2) + f"\u2562{R}")

        # Audit data lines
        for key, value in audit_data.items():
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            raw_content = f"{key}: {value_str}"
            if len(raw_content) > inner_width:
                raw_content = raw_content[:inner_width - 3] + "..."
                value_str = raw_content.split(": ", 1)[1] if ": " in raw_content else value_str

            # Apply colors: key in yellow
            colored_content = f"{Y}{key}:{R} {value_str}"
            padding_needed = inner_width - len(raw_content)
            line_padded = f" {colored_content}{' ' * padding_needed} "
            lines.append(f"{C}\u2551{R}{line_padded}{C}\u2551{R}")

        # Reminders section (if provided)
        if reminders:
            lines.append(f"{C}\u255f" + "\u2500" * (box_width - 2) + f"\u2562{R}")
            title_display = f"{B}REMINDERS{R}"
            title_padded = f" {title_display} ".center(inner_width + len(B) + len(R))
            lines.append(f"{C}\u2551{R} {title_padded} {C}\u2551{R}")

            for reminder in reminders:
                emoji = reminder.get('emoji', '\u2022')
                message = reminder.get('message', '')
                line_content = f"{emoji} {message}"

                if len(line_content) > inner_width:
                    line_content = line_content[:inner_width - 3] + "..."

                line_padded = f" {line_content} ".ljust(inner_width + 2)
                lines.append(f"{C}\u2551{R}{line_padded}{C}\u2551{R}")

        # Bottom border
        lines.append(f"{C}\u255a" + "\u2550" * (box_width - 2) + f"\u255d{R}")

        return '\n'.join(lines)

    def format_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """
        Create aligned ASCII table.

        Format:
        +----------+----------+----------+
        | Header1  | Header2  | Header3  |
        +----------+----------+----------+
        | value1   | value2   | value3   |
        | value4   | value5   | value6   |
        +----------+----------+----------+

        Args:
            headers: List of column headers
            rows: List of row data (each row is list of strings)

        Returns:
            Formatted ASCII table as string
        """
        if not headers or not rows:
            return ""

        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        lines = []

        # Top border
        top = "\u250c" + "\u252c".join("\u2500" * (w + 2) for w in col_widths) + "\u2510"
        lines.append(top)

        # Header row
        header_cells = [f" {h.ljust(col_widths[i])} " for i, h in enumerate(headers)]
        lines.append("\u2502" + "\u2502".join(header_cells) + "\u2502")

        # Separator
        sep = "\u251c" + "\u253c".join("\u2500" * (w + 2) for w in col_widths) + "\u2524"
        lines.append(sep)

        # Data rows
        for row in rows:
            cells = [f" {str(row[i] if i < len(row) else '').ljust(col_widths[i])} "
                    for i in range(len(headers))]
            lines.append("\u2502" + "\u2502".join(cells) + "\u2502")

        # Bottom border
        bottom = "\u2514" + "\u2534".join("\u2500" * (w + 2) for w in col_widths) + "\u2518"
        lines.append(bottom)

        return '\n'.join(lines)


# Standalone functions extracted from response.py

def format_header(
    title: str,
    emoji: Optional[str] = None,
    metadata: Optional[str] = None,
    verbosity: int = 1,
    box_drawing: Optional[bool] = None
) -> str:
    """
    Format header based on verbosity level.

    This function implements Pattern 3 from SPEC-TOKEN-003: Box Drawing Overhead.
    Reduces header token consumption by 15-30 tokens per output.

    Args:
        title: Header text
        emoji: Optional emoji prefix
        metadata: Optional metadata string (count, page info, etc.)
        verbosity: Output verbosity level
            - 0 (minimal): "{emoji} {title}"
            - 1 (standard): "{emoji} {title} ({metadata})"
            - 2 (verbose): Box drawing with full details
        box_drawing: Force enable/disable box drawing (overrides verbosity)

    Returns:
        Formatted header string

    Examples:
        >>> format_header("Projects", emoji="📋", metadata="3/109, page 1/37", verbosity=0)
        '📋 Projects'

        >>> format_header("Projects", emoji="📋", metadata="3/109, page 1/37", verbosity=1)
        '📋 Projects (3/109, page 1/37)'

        >>> format_header("Projects", emoji="📋", metadata="109 total (Page 1 of 37, showing 3)", verbosity=2)
        '╔══════════════════════════════════════════════════════════╗\\n║ 📋 PROJECTS - 109 total (Page 1 of 37, showing 3)         ║\\n╚══════════════════════════════════════════════════════════╝'
    """
    # Determine if box drawing should be used
    use_box = box_drawing if box_drawing is not None else (verbosity >= 2)

    # If box drawing explicitly requested, use it regardless of verbosity
    if use_box:
        # Build header text
        header_parts = []
        if emoji:
            header_parts.append(emoji)
        header_parts.append(title.upper())
        if metadata:
            header_parts.append("-")
            header_parts.append(metadata)

        header_text = " ".join(header_parts)

        # Create box with padding
        box_width = max(60, len(header_text) + 4)
        top_line = "\u2554" + "\u2550" * (box_width - 2) + "\u2557"
        middle_line = f"\u2551 {header_text:<{box_width - 4}} \u2551"
        bottom_line = "\u255a" + "\u2550" * (box_width - 2) + "\u255d"

        return f"{top_line}\n{middle_line}\n{bottom_line}"

    # Verbosity 0: Minimal format
    if verbosity == 0:
        parts = []
        if emoji:
            parts.append(emoji)
        parts.append(title)
        return " ".join(parts)

    # Verbosity 1: Standard format with metadata
    if verbosity == 1:
        parts = []
        if emoji:
            parts.append(emoji)
        parts.append(title)
        if metadata:
            parts.append(f"({metadata})")
        return " ".join(parts)

    # Fallback: Standard format (verbosity 2 without box_drawing, or other edge cases)
    parts = []
    if emoji:
        parts.append(emoji)
    parts.append(title)
    if metadata:
        parts.append(f"({metadata})")
    return " ".join(parts)


def add_tip(
    tip_text: str,
    category: str = "general",
    show_tips: Optional[bool] = None
) -> str:
    """
    Conditionally add tip based on configuration.

    This function implements Pattern 4 from SPEC-TOKEN-003: Unsolicited Tips.
    Reduces unnecessary tip output by making tips opt-in via configuration.

    Args:
        tip_text: Tip content to display
        category: Tip category (general, navigation, filtering, etc.)
        show_tips: Override config setting (None = use config default)

    Returns:
        Formatted tip string or empty string if tips disabled

    Examples:
        >>> add_tip("Add filter='scribe' to narrow results", show_tips=True)
        '💡 Tip: Add filter='scribe' to narrow results'

        >>> add_tip("Use verbosity=2 for more detail", show_tips=False)
        ''
    """
    # Determine if tips should be shown
    if show_tips is None:
        # Try to load from config
        try:
            from scribe_mcp.config.repo_config import get_current_repo_config
            _, config = get_current_repo_config()
            show_tips = config.get("display", {}).get("show_tips", False)
        except Exception:
            # Default to False (tips off by default per SPEC-TOKEN-003)
            show_tips = False

    if not show_tips:
        return ""

    # Format and return tip
    return f"\U0001f4a1 Tip: {tip_text}"
