"""Log entry formatting for append_entry, read_recent, and query_entries.

Phase 5 Task 5.4: Extracted from ResponseFormatter for modularity.

This module provides:
- format_entry: Main entry point for single entry formatting
- format_response: Format list of entries with pagination
- format_readable_log_entries: Format log entries for display (~192 lines)
- format_readable_append_entry: Format append_entry response
- Helper methods for truncation, reasoning parsing, etc.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base import BaseFormatter
from .ui import UIFormatter
from ..estimator import PaginationInfo


logger = logging.getLogger(__name__)


class EntryFormatter(BaseFormatter):
    """Formats log entries for display.

    Handles formatting for:
    - read_recent tool output
    - query_entries tool output
    - append_entry tool output (single and bulk)
    """

    # Compact field name mapping
    COMPACT_FIELD_MAP = {
        "timestamp": "ts",
        "message": "m",
        "agent": "a",
        "emoji": "e",
        "status": "s",
        "meta": "meta",
        "id": "i",
        "project": "p"
    }

    # Default fields for compact mode
    COMPACT_DEFAULT_FIELDS = ["id", "timestamp", "agent", "emoji", "message", "meta"]

    def __init__(self, token_warning_threshold: int = 4000):
        super().__init__(token_warning_threshold)
        self._ui = UIFormatter()

    def format_entry(self, entry: Dict[str, Any], compact: bool = False,
                    fields: Optional[List[str]] = None,
                    include_metadata: bool = True) -> Dict[str, Any]:
        """
        Format a single log entry based on requested format.

        Args:
            entry: Raw entry data from storage
            compact: Use compact format with short field names
            fields: Specific fields to include (None = all fields)
            include_metadata: Whether to include metadata field
        """
        if compact:
            return self._format_compact_entry(entry, fields, include_metadata)
        else:
            return self._format_full_entry(entry, fields, include_metadata)

    def _format_full_entry(self, entry: Dict[str, Any], fields: Optional[List[str]],
                          include_metadata: bool) -> Dict[str, Any]:
        """Format entry in full format with optional field selection."""
        result = {}

        # Determine which fields to include
        if fields is None:
            fields_to_include = list(entry.keys())
        else:
            fields_to_include = fields

        # Copy requested fields
        for field in fields_to_include:
            if field in entry:
                if field == "meta" and not include_metadata:
                    continue
                result[field] = entry[field]

        return result

    def _format_compact_entry(self, entry: Dict[str, Any], fields: Optional[List[str]],
                            include_metadata: bool) -> Dict[str, Any]:
        """Format entry in compact format with short field names."""
        result = {}

        # Determine which fields to include
        if fields is None:
            fields_to_include = self.COMPACT_DEFAULT_FIELDS
        else:
            fields_to_include = fields

        # Map to compact field names
        for field in fields_to_include:
            if field not in entry:
                continue

            # Skip metadata if not requested
            if field == "meta" and not include_metadata:
                continue

            # Get compact field name
            compact_field = self.COMPACT_FIELD_MAP.get(field, field)

            # Format value for compact mode
            value = entry[field]
            if field == "timestamp" and isinstance(value, str):
                # Shorten timestamp format
                try:
                    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    value = dt.strftime("%Y-%m-%d")
                except (TypeError, ValueError) as exc:
                    logger.debug(
                        "Unable to normalize timestamp '%s' in compact formatter: %s",
                        value,
                        exc,
                    )
            elif field == "message" and isinstance(value, str) and len(value) > 100:
                # Truncate long messages in compact mode
                value = value[:97] + "..."

            result[compact_field] = value

        return result

    def format_response(self, entries: List[Dict[str, Any]],
                       compact: bool = False,
                       fields: Optional[List[str]] = None,
                       include_metadata: bool = True,
                       pagination: Optional[PaginationInfo] = None,
                       extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Format a complete response with entries and metadata.

        Args:
            entries: List of log entries
            compact: Use compact format
            fields: Field selection
            include_metadata: Include metadata in entries
            pagination: Pagination information
            extra_data: Additional response data (reminders, etc.)
        """
        # Format entries
        formatted_entries = [
            self.format_entry(entry, compact, fields, include_metadata)
            for entry in entries
        ]

        # Build response
        response = {
            "ok": True,
            "entries": formatted_entries,
            "count": len(formatted_entries)
        }

        # Add compact flag
        if compact:
            response["compact"] = True

        # Add pagination info
        if pagination:
            response["pagination"] = pagination.to_dict()

        # Add extra data
        if extra_data:
            response.update(extra_data)

        # Add token usage warning if needed
        estimated_tokens = self.estimate_tokens(response)
        if estimated_tokens > self._token_warning_threshold:
            response["token_warning"] = {
                "estimated_tokens": estimated_tokens,
                "threshold": self._token_warning_threshold,
                "suggestion": f"Use compact=True for ~70% token reduction"
            }

        return response

    def format_readable_log_entries(self, entries: List[Dict], pagination: Dict, search_context: Optional[Dict] = None, project_name: Optional[str] = None) -> str:
        """
        Format log entries in readable format with reasoning blocks.

        Phase 3a enhancements:
        - Parse and display meta.reasoning blocks as tree structure
        - Smarter message truncation with word boundaries
        - Compact timestamp format (HH:MM)
        - Better pagination display (Page X of Y)
        - ANSI colors enabled (config-driven, display-heavy tool)

        Phase 3b enhancements:
        - Optional search_context for query_entries (shows filters in header)
        - Different header for search results vs recent entries

        Args:
            entries: List of log entry dicts
            pagination: Pagination metadata
            search_context: Optional search filter context (for query_entries)

        Returns:
            Formatted string with header box, entries with reasoning, footer
        """
        if not entries:
            return "No log entries found."

        # Pagination info
        page = pagination.get('page', 1)
        page_size = pagination.get('page_size', len(entries))
        total_count = pagination.get('total_count', len(entries))
        total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 1

        # Build readable output
        parts = []

        # Header with pagination (different for search vs recent)
        use_colors = self.USE_COLORS
        is_search = search_context is not None

        if is_search:
            # Search results header with filter info
            if use_colors:
                header = f"{self.ANSI_BOLD}╔═══════════════════════════════════════════════════════════════╗{self.ANSI_RESET}\n"
                header += f"{self.ANSI_BOLD}║ 🔍 SEARCH RESULTS{self.ANSI_RESET}                   Found {len(entries)} of {total_count} matches {self.ANSI_BOLD}║{self.ANSI_RESET}\n"

                # Build filter summary
                filters = []
                if search_context.get('message'):
                    filters.append(f"message=\"{search_context['message']}\"")
                if search_context.get('status'):
                    filters.append(f"status={search_context['status']}")
                if search_context.get('agents'):
                    filters.append(f"agents={search_context['agents']}")
                if search_context.get('emoji'):
                    filters.append(f"emoji={search_context['emoji']}")

                if filters:
                    filter_str = " | ".join(filters)
                    # Truncate if too long
                    if len(filter_str) > 60:
                        filter_str = filter_str[:57] + "..."
                    header += f"{self.ANSI_BOLD}║{self.ANSI_RESET} {self.ANSI_DIM}Filter: {filter_str}{self.ANSI_RESET}\n"
                    header += f"{self.ANSI_BOLD}║{self.ANSI_RESET}                                                               {self.ANSI_BOLD}║{self.ANSI_RESET}\n"

                header += f"{self.ANSI_BOLD}╚═══════════════════════════════════════════════════════════════╝{self.ANSI_RESET}"
            else:
                header = "╔═══════════════════════════════════════════════════════════════╗\n"
                header += f"║ 🔍 SEARCH RESULTS                   Found {len(entries)} of {total_count} matches ║\n"

                # Build filter summary
                filters = []
                if search_context.get('message'):
                    filters.append(f"message=\"{search_context['message']}\"")
                if search_context.get('status'):
                    filters.append(f"status={search_context['status']}")
                if search_context.get('agents'):
                    filters.append(f"agents={search_context['agents']}")
                if search_context.get('emoji'):
                    filters.append(f"emoji={search_context['emoji']}")

                if filters:
                    filter_str = " | ".join(filters)
                    if len(filter_str) > 60:
                        filter_str = filter_str[:57] + "..."
                    header += f"║ Filter: {filter_str}\n"
                    header += "║                                                               ║\n"

                header += "╚═══════════════════════════════════════════════════════════════╝"
        else:
            # Recent entries header with project name
            if use_colors:
                header = f"{self.ANSI_BOLD}╔═══════════════════════════════════════════════════════════════╗{self.ANSI_RESET}\n"
                if project_name:
                    header += f"{self.ANSI_BOLD}║ 📋 RECENT LOG ENTRIES ({project_name}){self.ANSI_RESET} Page {page} of {total_pages} ({len(entries)}/{total_count}) {self.ANSI_BOLD}║{self.ANSI_RESET}\n"
                else:
                    header += f"{self.ANSI_BOLD}║ 📋 RECENT LOG ENTRIES{self.ANSI_RESET}                    Page {page} of {total_pages} ({len(entries)}/{total_count}) {self.ANSI_BOLD}║{self.ANSI_RESET}\n"
                header += f"{self.ANSI_BOLD}╚═══════════════════════════════════════════════════════════════╝{self.ANSI_RESET}"
            else:
                header = "╔═══════════════════════════════════════════════════════════════╗\n"
                if project_name:
                    # Calculate padding to right-align the page info
                    title_with_project = f"📋 RECENT LOG ENTRIES ({project_name})"
                    page_info = f"Page {page} of {total_pages} ({len(entries)}/{total_count})"
                    # Total width is 63 (between the ║ characters)
                    padding = 63 - len(title_with_project) - len(page_info) - 2  # -2 for spaces
                    if padding < 1:
                        padding = 1
                    header += f"║ {title_with_project}{' ' * padding}{page_info} ║\n"
                else:
                    header += f"║ 📋 RECENT LOG ENTRIES                    Page {page} of {total_pages} ({len(entries)}/{total_count}) ║\n"
                header += "╚═══════════════════════════════════════════════════════════════╝"

        parts.append(header)
        parts.append("")

        # Process entries - filter out tool_logs (audit entries, not for display)
        entries_with_reasoning = []
        for entry in entries:
            # Skip tool_logs entries - they're for audit, not display
            meta = entry.get('meta', {})
            if isinstance(meta, dict) and meta.get('log_type') == 'tool_logs':
                continue
            # Also skip by message pattern as fallback
            message_text = entry.get('message', '')
            if message_text.startswith('Tool call:'):
                continue

            # Support both 'timestamp' and 'ts' field names
            timestamp = entry.get('timestamp', '') or entry.get('ts', '')
            # Compact timestamp format (HH:MM)
            # Check UTC FIRST because 'UTC' contains 'T' which would match ISO check
            if 'UTC' in timestamp:
                # Handle "YYYY-MM-DD HH:MM:SS UTC" format
                ts_parts = timestamp.split(' ')
                if len(ts_parts) >= 3 and ts_parts[2] == 'UTC':
                    # Format: YYYY-MM-DD HH:MM:SS UTC
                    time_part = ts_parts[1]  # HH:MM:SS
                    timestamp = time_part.rsplit(':', 1)[0]  # Drop seconds -> HH:MM
            elif 'T' in timestamp and not timestamp.endswith('UTC'):
                # Handle ISO format: 2026-01-03T15:42:37.123456Z
                time_part = timestamp.split('T')[1].split('.')[0]  # HH:MM:SS
                timestamp = time_part.rsplit(':', 1)[0]  # Drop seconds -> HH:MM
            elif ' ' in timestamp:
                # Handle other space-separated formats
                ts_parts = timestamp.split(' ')
                if len(ts_parts) >= 2 and ':' in ts_parts[1]:
                    time_part = ts_parts[1]
                    timestamp = time_part.rsplit(':', 1)[0] if ':' in time_part else time_part

            agent = entry.get('agent', '')
            # Truncate UUID agents to first 8 chars
            if len(agent) > 15:
                agent = agent[:12] + '...'

            emoji = entry.get('emoji', '')
            status = entry.get('status', 'info')
            message = entry.get('message', '')
            # NO truncation - full messages for context rehydration

            # Format entry line
            if use_colors:
                entry_line = f"[{self.ANSI_CYAN}{emoji}{self.ANSI_RESET}] {self.ANSI_DIM}{timestamp}{self.ANSI_RESET} | {self.ANSI_BOLD}{agent}{self.ANSI_RESET} | {message}"
            else:
                entry_line = f"[{emoji}] {timestamp} | {agent} | {message}"

            parts.append(entry_line)

            # Check for reasoning block - display full content for context rehydration
            meta = entry.get('meta', {})
            reasoning = self._parse_reasoning_block(meta)
            if reasoning:
                entries_with_reasoning.append((timestamp, agent, message, reasoning))
                # Display reasoning tree inline - NO truncation
                if use_colors:
                    parts.append(f"    {self.ANSI_DIM}├─ Why: {reasoning.get('why', 'N/A')}{self.ANSI_RESET}")
                    parts.append(f"    {self.ANSI_DIM}├─ What: {reasoning.get('what', 'N/A')}{self.ANSI_RESET}")
                    parts.append(f"    {self.ANSI_DIM}└─ How: {reasoning.get('how', 'N/A')}{self.ANSI_RESET}")
                else:
                    parts.append(f"    ├─ Why: {reasoning.get('why', 'N/A')}")
                    parts.append(f"    ├─ What: {reasoning.get('what', 'N/A')}")
                    parts.append(f"    └─ How: {reasoning.get('how', 'N/A')}")

            parts.append("")  # Blank line between entries

        # Footer with file path
        parts.append("─" * 65)
        if use_colors:
            parts.append(f"{self.ANSI_DIM}📁 Progress log entries{self.ANSI_RESET}")
        else:
            parts.append("📁 Progress log entries")

        return '\n'.join(parts)

    def _truncate_message_smart(self, message: str, max_length: int = 100) -> str:
        """
        Truncate message at word boundary for better readability.

        Args:
            message: Message to truncate
            max_length: Maximum length before truncation

        Returns:
            Truncated message with ellipsis or original if short enough
        """
        if len(message) <= max_length:
            return message

        # Try to truncate at word boundary
        truncated = message[:max_length - 3]
        last_space = truncated.rfind(' ')

        # Only use word boundary if it's at least 70% of desired length
        if last_space > max_length * 0.7:
            truncated = truncated[:last_space]

        return truncated + "..."

    def _parse_reasoning_block(self, meta: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Parse reasoning block from meta.reasoning field.

        Args:
            meta: Metadata dictionary that may contain reasoning field

        Returns:
            Dictionary with why/what/how keys or None if not parseable
        """
        reasoning_raw = meta.get('reasoning')
        if not reasoning_raw:
            return None

        try:
            # Try parsing as JSON string
            if isinstance(reasoning_raw, str):
                reasoning = json.loads(reasoning_raw)
            elif isinstance(reasoning_raw, dict):
                reasoning = reasoning_raw
            else:
                return None

            # Validate it has the expected keys
            if isinstance(reasoning, dict) and any(k in reasoning for k in ['why', 'what', 'how']):
                return reasoning
        except (json.JSONDecodeError, TypeError):
            pass

        return None

    def format_readable_append_entry(self, data: Dict[str, Any]) -> str:
        """
        Format append_entry output in concise readable format.

        Design decisions (Phase 2 user-approved):
        - NO ANSI COLORS for this tool (USE_COLORS hardcoded to False)
        - Parse and display meta.reasoning block nicely
        - Show reminders only if present (conditional)
        - Single entry: Concise 4-5 line format
        - Bulk entry: Summary format with samples

        Args:
            data: append_entry response data

        Returns:
            Formatted string with concise or summary format
        """
        # CRITICAL: NO ANSI COLORS for append_entry (user-approved design)
        # Agents see ANSI codes as text clutter, humans don't need color for confirmations
        USE_COLORS = False

        # Detect mode: bulk or single entry
        is_bulk = "written_count" in data or "bulk_mode" in data

        if is_bulk:
            return self._format_bulk_append_entry(data, USE_COLORS)
        else:
            return self._format_single_append_entry(data, USE_COLORS)

    def _format_single_append_entry(self, data: Dict[str, Any], USE_COLORS: bool) -> str:
        """
        Format single append_entry in optimized readable format.

        SPEC-TOKEN-002 Optimization:
        - Removed redundant "Entry written to progress log" prefix
        - Removed redundant project name (already in context)
        - Shortened timestamp to HH:MM UTC format
        - Removed bracketed labels [info], [Agent:], [Project:]
        - Using relative path (PROGRESS_LOG.md instead of full path)
        - Filtering default metadata (priority=low, log_type=progress, content_type=log)

        New Format:
        info Investigation complete
           14:34 UTC | ResearchAgent | phase=research; confidence=0.95
        PROGRESS_LOG.md

           Reasoning:
           |- Why: Need to understand append_entry structure
           |- What: Analyzed return values, usage patterns
           |- How: Read source code, traced execution paths

        Reminders:
           * It's been 15 minutes since the last log entry.
        """
        parts = []

        # Parse the written_line to extract components
        written_line = data.get('written_line', '')
        meta = data.get('meta', {})

        if data.get('ok'):
            parts.append("✅ Entry written to progress log")
            # Extract components from written_line
            # Format: [emoji] [timestamp] [Agent: name] [Project: name] message | metadata
            emoji_symbol = "info"
            message = ""
            timestamp_short = ""
            agent_name = ""
            metadata_str = ""

            if written_line:
                # Extract emoji
                emoji_match = re.search(r'\[(.+?)\]', written_line)
                if emoji_match:
                    emoji_symbol = emoji_match.group(1)

                # Extract timestamp and convert to HH:MM UTC
                timestamp_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\]', written_line)
                if timestamp_match:
                    full_timestamp = timestamp_match.group(1)
                    # Extract just HH:MM
                    time_parts = full_timestamp.split(' ')[1]  # Get "HH:MM:SS"
                    timestamp_short = time_parts[:5]  # Get "HH:MM"

                # Extract agent name
                agent_match = re.search(r'\[Agent: ([^\]]+)\]', written_line)
                if agent_match:
                    agent_name = agent_match.group(1)

                # Extract message (everything after [Project: ...] and before |)
                # Pattern: after last ] before | or end of line
                project_match = re.search(r'\[Project: [^\]]+\]\s*(?:\[ID: [^\]]+\]\s*)?(.+?)(?:\s*\|\s*(.+))?$', written_line)
                if project_match:
                    message = project_match.group(1).strip()
                    metadata_str = project_match.group(2) if project_match.group(2) else ""

                # Filter default metadata
                if metadata_str:
                    # Remove default metadata: priority=low, log_type=progress, content_type=log
                    meta_pairs = [pair.strip() for pair in metadata_str.split(';')]
                    filtered_pairs = [
                        pair for pair in meta_pairs
                        if not any(default in pair for default in [
                            'priority=low',
                            'priority=medium',  # Filter medium too as it's default
                            'log_type=progress',
                            'content_type=log'
                        ])
                    ]
                    metadata_str = '; '.join(filtered_pairs) if filtered_pairs else ""

            # Line 2: compact line with emoji + message
            compact_line = self._extract_compact_log_line(written_line) if written_line else ""
            if compact_line:
                parts.append(compact_line)
            elif message:
                parts.append(f"[{emoji_symbol}] {message}")

            # Line 2: Compact metadata line with timestamp, agent, and custom metadata
            # Only show if there's custom metadata or reasoning block
            metadata_line_parts = []
            if timestamp_short:
                metadata_line_parts.append(f"{timestamp_short} UTC")
            if agent_name:
                metadata_line_parts.append(agent_name)
            if metadata_str:
                metadata_line_parts.append(metadata_str)

            # Only add metadata line if there's custom metadata beyond timestamp/agent
            # OR if there will be a reasoning block (to maintain context)
            has_reasoning = self._parse_reasoning_block(meta) is not None

            if metadata_line_parts and (metadata_str or has_reasoning):
                parts.append(f"   {' | '.join(metadata_line_parts)}")
        else:
            parts.append("❌ Entry write failed")
            if data.get("error"):
                parts.append(f"   {data.get('error')}")

        # Reasoning block (if present in metadata)
        reasoning = self._parse_reasoning_block(meta)
        if reasoning:
            parts.append("")  # Blank line before reasoning
            parts.append("   Reasoning:")
            if reasoning.get('why'):
                parts.append(f"   ├─ Why: {reasoning['why']}")
            if reasoning.get('what'):
                parts.append(f"   ├─ What: {reasoning['what']}")
            if reasoning.get('how'):
                parts.append(f"   └─ How: {reasoning['how']}")

        # Path - just filename (PROGRESS_LOG.md) for maximum conciseness
        path = data.get('path', '')
        if path:
            # Extract just the filename
            path_obj = Path(path)
            parts.append(f"📁 {path_obj.name}")

        # Reminders section (ONLY if reminders present)
        reminders = data.get('reminders', [])
        if reminders:
            parts.append("")
            parts.append("⏰ Reminders:")
            for reminder in reminders:
                emoji = reminder.get('emoji', '•')
                message = reminder.get('message', '')
                parts.append(f"   {emoji} {message}")

        return '\n'.join(parts)

    def _format_bulk_append_entry(self, data: Dict[str, Any], USE_COLORS: bool) -> str:
        """
        Format bulk append_entry in summary format.

        Format:
        +==============================================================+
        | BULK APPEND RESULT                                           |
        +--------------------------------------------------------------+
        | status: partial success                                      |
        | written: 15 / 18                                             |
        | failed: 3                                                    |
        | performance: 45.2 items/sec                                  |
        +==============================================================+

        Successfully Written (first 5 of 15):
             1. [info] Investigation started | phase=research
             2. [info] Found 14 tools in directory | count=14
             3. [success] Analysis complete | confidence=0.95
             4. [info] Creating research document
             5. [success] Research document created | size=15KB

        Failed Entries (3):
             7. Missing required field 'message'
            12. JSON parsing error in metadata
            15. Permission denied writing to log file

        +==============================================================+
        | METADATA                                                     |
        +--------------------------------------------------------------+
        | paths: 2 log files written                                   |
        | * /home/austin/.scribe/.../PROGRESS_LOG.md                   |
        | * /home/austin/.scribe/.../BUG_LOG.md                        |
        +==============================================================+
        """
        parts = []
        box_width = 80

        # Header box
        written_count = data.get('written_count', 0)
        failed_count = data.get('failed_count', 0)
        total = written_count + failed_count
        status_text = "success" if failed_count == 0 else "partial success" if written_count > 0 else "failed"

        parts.append("╔" + "═" * (box_width - 2) + "╗")
        parts.append("║ BULK APPEND RESULT" + " " * (box_width - 22) + "║")
        parts.append("╟" + "─" * (box_width - 2) + "╢")
        parts.append(f"║ status: {status_text}".ljust(box_width - 1) + "║")
        parts.append(f"║ written: {written_count} / {total}".ljust(box_width - 1) + "║")
        parts.append(f"║ failed: {failed_count}".ljust(box_width - 1) + "║")

        # Add performance if available
        performance = data.get('performance', {})
        if performance and 'items_per_second' in performance:
            items_per_sec = performance['items_per_second']
            parts.append(f"║ performance: {items_per_sec:.1f} items/sec".ljust(box_width - 1) + "║")

        parts.append("╚" + "═" * (box_width - 2) + "╝")
        parts.append("")

        # Successfully written entries (first 5)
        written_lines = data.get('written_lines', [])
        if written_lines:
            sample_count = min(5, len(written_lines))
            parts.append(f"✅ Successfully Written (first {sample_count} of {written_count}):")
            for i, line in enumerate(written_lines[:5], 1):
                # Extract just the core message part (emoji + message)
                line_compact = self._extract_compact_log_line(line)
                parts.append(f"     {i}. {line_compact}")
            parts.append("")

        # Failed entries (ALL failures)
        failed_items = data.get('failed_items', [])
        if failed_items:
            parts.append(f"❌ Failed Entries ({failed_count}):")
            for item in failed_items:
                index = item.get('index', '?')
                error = item.get('error', 'Unknown error')
                parts.append(f"    {index}. {error}")
            parts.append("")

        # Footer metadata box
        parts.append("╔" + "═" * (box_width - 2) + "╗")
        parts.append("║ METADATA" + " " * (box_width - 12) + "║")
        parts.append("╟" + "─" * (box_width - 2) + "╢")

        # Paths
        paths = data.get('paths', [])
        if paths:
            parts.append(f"║ paths: {len(paths)} log file{'s' if len(paths) > 1 else ''} written".ljust(box_width - 1) + "║")
            for path in paths:
                # Shorten path for display
                display_path = path
                if '/MCP_SPINE/scribe_mcp/' in display_path:
                    display_path = '...' + display_path.split('/MCP_SPINE/scribe_mcp/', 1)[1]
                if len(display_path) > box_width - 8:
                    display_path = display_path[-(box_width - 11):].strip('/')
                    display_path = '...' + display_path
                parts.append(f"║ • {display_path}".ljust(box_width - 1) + "║")

        parts.append("╚" + "═" * (box_width - 2) + "╝")

        return '\n'.join(parts)

    def _extract_compact_log_line(self, full_line: str) -> str:
        """
        Extract compact version of log line for bulk display.

        From: "[info] [2026-01-03 02:46:00 UTC] [Agent: ResearchAgent] [Project: xyz] Investigation complete | confidence=0.95"
        To: "[info] Investigation complete | confidence=0.95"

        Args:
            full_line: Full log line with all metadata

        Returns:
            Compact version with emoji + message + key metadata
        """
        # Try to extract emoji and message part
        # Format: [emoji] [timestamp] [Agent: X] [Project: Y] message | meta
        # We need to skip first 4 bracket groups to get to message
        parts = full_line.split('] ', 4)  # Split on '] ' up to 5 parts
        if len(parts) >= 5:
            # parts[0] = "[info"
            # parts[1] = "[timestamp"
            # parts[2] = "[Agent: X"
            # parts[3] = "[Project: Y"
            # parts[4] = "message | meta" (no leading bracket)
            emoji = parts[0] + ']'  # e.g., "[info]"
            message_part = parts[4]  # Everything after [Project: Y]
            return f"{emoji} {message_part}"
        else:
            # Fallback: return first 80 chars
            return full_line[:80] + ('...' if len(full_line) > 80 else '')
