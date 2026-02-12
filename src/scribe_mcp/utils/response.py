#!/usr/bin/env python3
"""
Response optimization utilities for token reduction.

Provides compact/full response formatting, field selection,
and token estimation capabilities.
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
import json
from datetime import datetime
from pathlib import Path
import os

# Import token estimator for accurate token counting
try:
    from .tokens import token_estimator
except ImportError:
    # Fallback if tokens module not available
    token_estimator = None

# Import estimation utilities
from .estimator import PaginationInfo, PaginationCalculator, TokenEstimator

# Import formatters (Phase 5 modularization)
# Task 5.1: UI formatter
from .formatters.ui import UIFormatter, format_header, add_tip
# Task 5.2: Base formatter utilities
from .formatters.base import (
    BaseFormatter,
    get_use_ansi_colors,
    create_pagination_info as _create_pagination_info_base,
    format_compact_json as _format_compact_json_base,
)
# Task 5.3: File formatter
from .formatters.file import FileFormatter
# Task 5.4: Entry formatter
from .formatters.entry import EntryFormatter
# Task 5.5: Project formatter
from .formatters.project import ProjectFormatter
# Task 5.6: Dispatcher (central router for finalize_tool_response)
from .formatters.dispatcher import FormatterDispatcher

# PaginationInfo is now imported from estimator utilities

# MCP types for CallToolResult (Issue #9962 fix)
# When we return CallToolResult with TextContent only (no structuredContent),
# Claude Code displays text cleanly with actual newlines instead of escaped \n
try:
    from mcp.types import CallToolResult, TextContent
    MCP_TYPES_AVAILABLE = True
except ImportError:
    # Fallback for environments without MCP SDK
    CallToolResult = None
    TextContent = None
    MCP_TYPES_AVAILABLE = False


# _get_use_ansi_colors now delegates to base module (Phase 5 Task 5.2)
def _get_use_ansi_colors() -> bool:
    """
    Get ANSI color setting from repo config.

    Delegates to formatters.base.get_use_ansi_colors().
    Phase 1.5/1.6: Load use_ansi_colors from .scribe/config/scribe.yaml
    Falls back to True (colors enabled by default) if config unavailable.
    """
    return get_use_ansi_colors()


class ResponseFormatter:
    """Handles response formatting with compact/full modes and field selection."""

    # Format constants (Phase 0)
    FORMAT_READABLE = "readable"
    FORMAT_STRUCTURED = "structured"
    FORMAT_COMPACT = "compact"
    FORMAT_BOTH = "both"  # TextContent + structuredContent (for when Issue #9962 is fixed)

    # ANSI color codes for enhanced readability in Claude Code
    ANSI_CYAN = "\033[36m"
    ANSI_GREEN = "\033[32m"
    ANSI_YELLOW = "\033[33m"
    ANSI_BLUE = "\033[34m"
    ANSI_MAGENTA = "\033[35m"
    ANSI_BOLD = "\033[1m"
    ANSI_DIM = "\033[2m"
    ANSI_RESET = "\033[0m"

    @property
    def USE_COLORS(self) -> bool:
        """
        Check if ANSI colors are enabled via repo config.

        Phase 1.5/1.6: Colors loaded from .scribe/config/scribe.yaml
        (use_ansi_colors setting). Enabled by default.
        """
        return _get_use_ansi_colors()

    # Compact field mappings (short aliases for common fields)
    COMPACT_FIELD_MAP = {
        "id": "i",
        "message": "m",
        "timestamp": "t",
        "ts": "t",
        "emoji": "e",
        "agent": "a",
        "meta": "mt",
        "status": "s",
        "raw_line": "r"
    }

    # Default fields for compact mode
    COMPACT_DEFAULT_FIELDS = ["id", "message", "timestamp", "emoji", "agent"]

    def __init__(self, token_warning_threshold: int = 4000):
        self.token_warning_threshold = token_warning_threshold
        self._token_estimator = TokenEstimator()
        # UIFormatter instance for delegating UI methods (Phase 5 Task 5.1)
        self._ui = UIFormatter(use_colors=self.USE_COLORS)
        # BaseFormatter instance for delegating base methods (Phase 5 Task 5.2)
        self._base = BaseFormatter(token_warning_threshold)
        # FileFormatter instance for delegating file content methods (Phase 5 Task 5.3)
        self._file = FileFormatter(token_warning_threshold)
        # EntryFormatter instance for delegating entry methods (Phase 5 Task 5.4)
        self._entry = EntryFormatter(token_warning_threshold)
        # ProjectFormatter instance for delegating project methods (Phase 5 Task 5.5)
        self._project = ProjectFormatter(token_warning_threshold)
        # FormatterDispatcher instance for delegating finalize_tool_response (Phase 5 Task 5.6)
        # Pass existing formatters to dispatcher for consistent behavior
        self._dispatcher = FormatterDispatcher(
            token_warning_threshold=token_warning_threshold,
            base_formatter=self._base,
            ui_formatter=self._ui,
            file_formatter=self._file,
            entry_formatter=self._entry,
            project_formatter=self._project,
        )

    def estimate_tokens(self, data: Union[Dict, List, str]) -> int:
        """
        Estimate token count for response data using TokenEstimator.
        """
        return self._token_estimator.estimate_tokens(data)

    def format_entry(self, entry: Dict[str, Any], compact: bool = False,
                    fields: Optional[List[str]] = None,
                    include_metadata: bool = True) -> Dict[str, Any]:
        """
        Format a single log entry based on requested format.

        Delegates to EntryFormatter.format_entry() (Phase 5 Task 5.4).

        Args:
            entry: Raw entry data from storage
            compact: Use compact format with short field names
            fields: Specific fields to include (None = all fields)
            include_metadata: Whether to include metadata field
        """
        return self._entry.format_entry(entry, compact, fields, include_metadata)

    def _format_full_entry(self, entry: Dict[str, Any], fields: Optional[List[str]],
                          include_metadata: bool) -> Dict[str, Any]:
        """
        Format entry in full format with optional field selection.

        Delegates to EntryFormatter._format_full_entry() (Phase 5 Task 5.4).
        """
        return self._entry._format_full_entry(entry, fields, include_metadata)

    def _format_compact_entry(self, entry: Dict[str, Any], fields: Optional[List[str]],
                            include_metadata: bool) -> Dict[str, Any]:
        """
        Format entry in compact format with short field names.

        Delegates to EntryFormatter._format_compact_entry() (Phase 5 Task 5.4).
        """
        return self._entry._format_compact_entry(entry, fields, include_metadata)

    def format_response(self, entries: List[Dict[str, Any]],
                       compact: bool = False,
                       fields: Optional[List[str]] = None,
                       include_metadata: bool = True,
                       pagination: Optional[PaginationInfo] = None,
                       extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Format a complete response with entries and metadata.

        Delegates to EntryFormatter.format_response() (Phase 5 Task 5.4).

        Args:
            entries: List of log entries
            compact: Use compact format
            fields: Field selection
            include_metadata: Include metadata in entries
            pagination: Pagination information
            extra_data: Additional response data (reminders, etc.)
        """
        return self._entry.format_response(entries, compact, fields, include_metadata, pagination, extra_data)

    # ==================== Phase 0: Readable Format Helper Methods ====================

    def _add_line_numbers(self, content: str, start: int = 1) -> str:
        """
        Add line numbers to content with optional green coloring.

        Format: "     1. Line content" (with green line numbers if colors enabled)

        Args:
            content: Text content to number
            start: Starting line number (default: 1)

        Returns:
            Line-numbered string with consistent padding

        Note:
            Delegates to UIFormatter.add_line_numbers (Phase 5 Task 5.1)
        """
        # Ensure UIFormatter has current color setting
        self._ui.use_colors = self.USE_COLORS
        return self._ui.add_line_numbers(content, start)

    def _create_header_box(self, title: str, metadata: Dict[str, Any]) -> str:
        """
        Create ASCII box header with title and metadata.

        Format:
        ╔══════════════════════════════════════════════════════════╗
        ║ TITLE                                                    ║
        ╟──────────────────────────────────────────────────────────╢
        ║ key1: value1                                             ║
        ║ key2: value2                                             ║
        ╚══════════════════════════════════════════════════════════╝

        Args:
            title: Header title text
            metadata: Dictionary of metadata key-value pairs

        Returns:
            Formatted ASCII box as string

        Note:
            Delegates to UIFormatter.create_header_box (Phase 5 Task 5.1)
        """
        # Ensure UIFormatter has current color setting
        self._ui.use_colors = self.USE_COLORS
        return self._ui.create_header_box(title, metadata)

    def _create_footer_box(self, audit_data: Dict[str, Any],
                           reminders: Optional[List[Dict]] = None) -> str:
        """
        Create ASCII box footer with audit data and optional reminders.

        Format:
        ╔══════════════════════════════════════════════════════════╗
        ║ METADATA                                                 ║
        ╟──────────────────────────────────────────────────────────╢
        ║ audit_key1: value1                                       ║
        ║ audit_key2: value2                                       ║
        ╟──────────────────────────────────────────────────────────╢
        ║ REMINDERS                                                ║
        ║ • Reminder 1                                             ║
        ║ • Reminder 2                                             ║
        ╚══════════════════════════════════════════════════════════╝

        Args:
            audit_data: Dictionary of audit/metadata
            reminders: Optional list of reminder dictionaries

        Returns:
            Formatted ASCII box as string

        Note:
            Delegates to UIFormatter.create_footer_box (Phase 5 Task 5.1)
        """
        # Ensure UIFormatter has current color setting
        self._ui.use_colors = self.USE_COLORS
        return self._ui.create_footer_box(audit_data, reminders)

    def _format_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """
        Create aligned ASCII table.

        Format:
        ┌──────────┬──────────┬──────────┐
        │ Header1  │ Header2  │ Header3  │
        ├──────────┼──────────┼──────────┤
        │ value1   │ value2   │ value3   │
        │ value4   │ value5   │ value6   │
        └──────────┴──────────┴──────────┘

        Args:
            headers: List of column headers
            rows: List of row data (each row is list of strings)

        Returns:
            Formatted ASCII table as string

        Note:
            Delegates to UIFormatter.format_table (Phase 5 Task 5.1)
        """
        return self._ui.format_table(headers, rows)

    # ==================== Phase 0: Core Formatting Methods ====================

    def format_readable_file_content(self, data: Dict[str, Any]) -> str:
        """
        Format read_file output in readable format with simple header, content first, metadata at bottom.

        Delegates to FileFormatter (Phase 5 Task 5.3).

        Args:
            data: read_file response with 'scan', 'chunks', 'chunk', etc.

        Returns:
            Formatted string with one-line header, line-numbered content, metadata footer
        """
        return self._file.format_readable_file_content(data)

    def _format_readable_file_content_DEPRECATED(self, data: Dict[str, Any]) -> str:
        """
        DEPRECATED: Original implementation kept for reference during Phase 5 migration.
        Use format_readable_file_content() which delegates to FileFormatter.
        """
        # Extract scan metadata
        scan = data.get('scan', {})
        path = scan.get('repo_relative_path') or scan.get('absolute_path', 'unknown')
        mode = data.get('mode', 'unknown')

        # Get filename from path
        import os
        filename = os.path.basename(path)

        # Extract content based on mode and determine line range
        content = ''
        start_line = 1
        end_line = 1
        total_lines = scan.get('line_count', 0)

        if mode == 'scan_only':
            # No content for scan_only
            content = '[scan only - no content requested]'
            line_range = 'scan only'
        elif 'chunks' in data and data['chunks']:
            # Chunk mode - concatenate chunks
            chunks = data['chunks']
            content_parts = []
            for chunk in chunks:
                content_parts.append(chunk.get('content', ''))
            content = '\n'.join(content_parts)
            start_line = chunks[0].get('line_start', 1) if chunks else 1
            end_line = chunks[-1].get('line_end', start_line) if chunks else start_line
            line_range = f"{start_line}-{end_line}"
        elif 'chunk' in data:
            # Line range or page mode
            chunk = data['chunk']
            content = chunk.get('content', '')
            start_line = chunk.get('line_start', 1)
            end_line = chunk.get('line_end', start_line)
            line_range = f"{start_line}-{end_line}"
        elif 'matches' in data:
            # Search mode
            matches = data['matches']
            if matches:
                content_parts = []
                for match in matches[:10]:  # Limit to first 10 matches
                    line_num = match.get('line_number', '?')
                    line_text = match.get('line', '').rstrip()
                    content_parts.append(f"[Line {line_num}] {line_text}")
                content = '\n'.join(content_parts)
                line_range = f"{len(matches)} matches"
            else:
                content = '[no matches found]'
                line_range = '0 matches'
        else:
            line_range = 'unknown'

        # Build readable output with simple one-line header
        parts = []

        # ONE-LINE HEADER: "READ FILE filename.xyz | Lines read: 100-243"
        parts.append(f"READ FILE {filename} | Lines read: {line_range}")
        parts.append("")  # Blank line

        # CONTENT FIRST (with line numbers)
        if mode != 'scan_only' and content != '[no matches found]':
            parts.append(self._add_line_numbers(content, start_line))
        else:
            parts.append(content)

        # SPECIAL FILE WARNING (SKILL.md detection) - STERN, NOT SEIZURE
        special_file = data.get('special_file')
        if special_file:
            parts.append("")
            parts.append("─" * 63)
            parts.append(f"🚨 {special_file.get('reason', 'SPECIAL FILE DETECTED')}")
            parts.append("─" * 63)
            parts.append(f"Urgency: {special_file.get('urgency', 'HIGH')}")
            parts.append(f"Type: {special_file.get('type', 'unknown')}")
            parts.append(f"Action Required: {special_file.get('instruction', 'Read file immediately')}")
            if special_file.get('suggested_action'):
                parts.append(f"→ {special_file.get('suggested_action')}")
            parts.append("─" * 63)

        # STRUCTURE ANALYSIS (Python AST, Markdown headings, JS/TS functions)
        structure = data.get('structure')
        if structure and structure.get('ok'):
            parts.append("")
            parts.append("📋 File Structure:")
            parts.append("")

            file_type = structure.get('type', 'unknown')

            if file_type == 'python':
                # Python functions and classes
                functions = structure.get('functions', [])
                classes = structure.get('classes', [])
                total_funcs = structure.get('total_functions', len(functions))
                total_classes = structure.get('total_classes', len(classes))

                # Get pagination params
                pagination = data.get('structure_pagination', {})
                page = pagination.get('page', 1)
                page_size = pagination.get('page_size', 10)

                # Check if filtering is active
                is_filtered = structure.get('filtered', False)
                filter_pattern = structure.get('filter_pattern')
                filtered_func_count = structure.get('filtered_function_count', 0)
                filtered_class_count = structure.get('filtered_class_count', 0)

                if is_filtered:
                    total_matches = filtered_func_count + filtered_class_count
                    parts.append(f"  🔍 Filtered Results ({total_matches} matches for '{filter_pattern}'):")
                    if filtered_class_count > 0:
                        parts.append(f"     Classes: {filtered_class_count}")
                    if filtered_func_count > 0:
                        parts.append(f"     Functions: {filtered_func_count}")
                    parts.append("")

                # Helper function to format a signature
                def format_signature(params_list, return_type=None):
                    """Format function/method signature with types and defaults."""
                    if not params_list:
                        sig = "()"
                    else:
                        param_strs = []
                        for p in params_list:
                            param_str = p['name']
                            if 'type' in p and p['type']:
                                param_str += f": {p['type']}"
                            if 'default' in p and p['default']:
                                param_str += f" = {p['default']}"
                            param_strs.append(param_str)
                        sig = f"({', '.join(param_strs)})"

                    if return_type:
                        sig += f" -> {return_type}"
                    return sig

                if classes:
                    # Paginate classes list ONLY if not filtered (when filtered, show all matched classes but paginate their methods)
                    if is_filtered:
                        paginated_classes = classes
                        class_total_pages = 1
                    else:
                        class_start = (page - 1) * page_size
                        class_end = class_start + page_size
                        paginated_classes = classes[class_start:class_end]
                        class_total_pages = (total_classes + page_size - 1) // page_size

                    if total_classes > page_size and not is_filtered:
                        parts.append(f"  Classes (page {page} of {class_total_pages}, showing {class_start + 1}-{min(class_end, total_classes)} of {total_classes}):")
                    else:
                        parts.append(f"  Classes ({total_classes} total):")

                    for cls in paginated_classes:
                        # Format class header with line range
                        start_line = cls['line']
                        end_line = cls.get('end_line', start_line)
                        line_count = end_line - start_line + 1
                        line_info = f"lines {start_line}-{end_line} ({line_count} lines)" if end_line > start_line else f"line {start_line}"
                        parts.append(f"    • class {cls['name']} at {line_info}")

                        # Show methods if available (with pagination)
                        methods = cls.get('methods', [])
                        method_count = cls.get('method_count', len(methods))
                        if methods:
                            # Paginate methods
                            start_idx = (page - 1) * page_size
                            end_idx = start_idx + page_size
                            paginated_methods = methods[start_idx:end_idx]
                            total_pages = (method_count + page_size - 1) // page_size

                            # Show pagination header if multiple pages
                            if method_count > page_size:
                                parts.append(f"        Methods (page {page} of {total_pages}, showing {start_idx + 1}-{min(end_idx, method_count)} of {method_count}):")
                            else:
                                parts.append(f"        Methods ({method_count} total):")

                            for method in paginated_methods:
                                async_prefix = "async " if method.get('is_async') else ""
                                method_params = method.get('params', [])
                                method_return = method.get('return_type')
                                sig = format_signature(method_params, method_return)

                                # Format method line range
                                m_start = method['line']
                                m_end = method.get('end_line', m_start)
                                m_count = m_end - m_start + 1
                                m_line_info = f"{m_start}-{m_end} ({m_count})" if m_end > m_start else str(m_start)

                                parts.append(f"          {async_prefix}def {method['name']}{sig} (lines {m_line_info})")

                            # Navigation hint for next/previous pages
                            if total_pages > 1:
                                nav_hints = []
                                if page > 1:
                                    nav_hints.append(f"structure_page={page - 1} for previous")
                                if page < total_pages:
                                    nav_hints.append(f"structure_page={page + 1} for next")
                                if nav_hints:
                                    parts.append(f"        💡 Use {' or '.join(nav_hints)}")
                        parts.append("")

                    # Add pagination navigation for classes
                    if class_total_pages > 1 and not is_filtered:
                        nav_hints = []
                        if page > 1:
                            nav_hints.append(f"structure_page={page - 1}")
                        if page < class_total_pages:
                            nav_hints.append(f"structure_page={page + 1}")
                        if nav_hints:
                            parts.append(f"    💡 Use {' or '.join(nav_hints)} to navigate")
                        parts.append("")

                if functions:
                    # Paginate functions list ONLY if not filtered (when filtered, show all matched functions)
                    if is_filtered:
                        paginated_funcs = functions
                        func_total_pages = 1
                    else:
                        func_start = (page - 1) * page_size
                        func_end = func_start + page_size
                        paginated_funcs = functions[func_start:func_end]
                        func_total_pages = (total_funcs + page_size - 1) // page_size

                    if total_funcs > page_size and not is_filtered:
                        parts.append(f"  Functions (page {page} of {func_total_pages}, showing {func_start + 1}-{min(func_end, total_funcs)} of {total_funcs}):")
                    else:
                        parts.append(f"  Functions ({total_funcs} total):")

                    for func in paginated_funcs:
                        func_params = func.get('params', [])
                        func_return = func.get('return_type')

                        # Fallback to old args format if params not available
                        if not func_params and func.get('args'):
                            sig = f"({', '.join(func['args'])})"
                        else:
                            sig = format_signature(func_params, func_return)

                        # Format function line range
                        f_start = func['line']
                        f_end = func.get('end_line', f_start)
                        f_count = f_end - f_start + 1
                        f_line_info = f"lines {f_start}-{f_end} ({f_count})" if f_end > f_start else f"line {f_start}"

                        async_prefix = "async " if func.get('type') == 'async_function' else ""
                        parts.append(f"    • {async_prefix}def {func['name']}{sig} at {f_line_info}")

                    # Add pagination navigation for functions
                    if func_total_pages > 1 and not is_filtered:
                        nav_hints = []
                        if page > 1:
                            nav_hints.append(f"structure_page={page - 1}")
                        if page < func_total_pages:
                            nav_hints.append(f"structure_page={page + 1}")
                        if nav_hints:
                            parts.append(f"    💡 Use {' or '.join(nav_hints)} to navigate")

                if structure.get('truncated'):
                    parts.append("")
                    parts.append("  ⚠️  Structure truncated - use line_range/page mode for full details")

            elif file_type == 'markdown':
                # Markdown headings
                headings = structure.get('headings', [])
                total_headings = structure.get('total_headings', len(headings))

                parts.append(f"  Headings ({total_headings} total):")
                for heading in headings[:20]:  # Show first 20
                    indent = "  " * heading['level']
                    parts.append(f"    {indent}{'#' * heading['level']} {heading['text']} (line {heading['line']})")
                if total_headings > 20:
                    parts.append(f"    ... and {total_headings - 20} more headings")

                if structure.get('truncated'):
                    parts.append("")
                    parts.append("  ⚠️  Structure truncated - use line_range/page mode for full details")

            elif file_type in {'javascript', 'typescript'}:
                # JavaScript/TypeScript functions and classes
                functions = structure.get('functions', [])
                classes = structure.get('classes', [])
                total_funcs = structure.get('total_functions', len(functions))
                total_classes = structure.get('total_classes', len(classes))

                if classes:
                    parts.append(f"  Classes ({total_classes} total):")
                    for cls in classes[:10]:
                        parts.append(f"    • {cls['name']} at line {cls['line']}")
                    if total_classes > 10:
                        parts.append(f"    ... and {total_classes - 10} more classes")
                    parts.append("")

                if functions:
                    parts.append(f"  Functions ({total_funcs} total):")
                    for func in functions[:10]:
                        parts.append(f"    • {func['name']}() at line {func['line']}")
                    if total_funcs > 10:
                        parts.append(f"    ... and {total_funcs - 10} more functions")

                if structure.get('truncated'):
                    parts.append("")
                    parts.append("  ⚠️  Structure truncated - use line_range/page mode for full details")

        # DEPENDENCIES ANALYSIS (Phase 1+2: Import extraction + resolution)
        dependencies = data.get('dependencies')
        if dependencies and not dependencies.get('error'):
            imports = dependencies.get('imports', [])
            total_imports = dependencies.get('total_imports', 0)
            truncated = dependencies.get('truncated', False)

            if imports:
                parts.append("")
                parts.append("📦 Dependencies:")
                parts.append("")

                # Phase 2: Group imports by type for better readability
                # Check if we have Phase 2 resolution data (import_type field exists)
                has_resolution = any(imp.get('import_type') is not None for imp in imports)

                if has_resolution:
                    # Group imports by type
                    from collections import defaultdict
                    grouped = defaultdict(list)
                    for imp in imports:
                        import_type = imp.get('import_type', 'unresolved')
                        grouped[import_type].append(imp)

                    # Display in order: stdlib, third_party, local, unresolved
                    display_limit_per_type = 10
                    type_order = ['stdlib', 'third_party', 'local', 'unresolved']
                    type_labels = {
                        'stdlib': '📚 Standard Library',
                        'third_party': '📦 Third-Party Packages',
                        'local': '📁 Local Modules',
                        'unresolved': '❓ Unresolved'
                    }

                    for import_type in type_order:
                        type_imports = grouped.get(import_type, [])
                        if not type_imports:
                            continue

                        parts.append(f"  {type_labels[import_type]} ({len(type_imports)}):")
                        parts.append("")

                        for imp in type_imports[:display_limit_per_type]:
                            imp_syntax = imp.get('type')  # 'import' or 'from_import'
                            module = imp.get('module', '')
                            line = imp.get('line', '?')
                            names = imp.get('names')
                            alias = imp.get('alias')
                            level = imp.get('level', 0)
                            resolved_path = imp.get('resolved_path')
                            exists = imp.get('exists')

                            # Format relative imports with dots
                            if level > 0:
                                dots = '.' * level
                                if module:
                                    module_display = f"{dots}{module}"
                                else:
                                    module_display = dots
                            else:
                                module_display = module

                            # Build base import statement
                            if imp_syntax == 'import':
                                if alias:
                                    import_stmt = f"import {module_display} as {alias}"
                                else:
                                    import_stmt = f"import {module_display}"
                            elif imp_syntax == 'from_import' and names:
                                names_str = ', '.join(names[:5])  # Show first 5 names
                                if len(names) > 5:
                                    names_str += f", ... ({len(names)} total)"
                                import_stmt = f"from {module_display} import {names_str}"
                            else:
                                import_stmt = f"import {module_display}"

                            # Add resolution info based on type
                            if import_type == 'stdlib':
                                parts.append(f"    → {import_stmt} (line {line}) [stdlib]")
                            elif import_type == 'third_party':
                                parts.append(f"    → {import_stmt} (line {line}) [third-party]")
                            elif import_type == 'local':
                                if resolved_path and exists:
                                    # Show resolved path (make it relative to workspace for readability)
                                    parts.append(f"    → {import_stmt} (line {line})")
                                    parts.append(f"       ✓ {resolved_path}")
                                elif resolved_path and exists is False:
                                    # Missing local import
                                    parts.append(f"    → {import_stmt} (line {line})")
                                    parts.append(f"       ✗ MISSING: {resolved_path}")
                                else:
                                    # Local but couldn't resolve path
                                    parts.append(f"    → {import_stmt} (line {line}) [local - path unresolved]")
                            else:  # unresolved
                                parts.append(f"    → {import_stmt} (line {line}) [unresolved]")

                        if len(type_imports) > display_limit_per_type:
                            parts.append(f"       ... and {len(type_imports) - display_limit_per_type} more {import_type} imports")
                        parts.append("")  # Blank line between groups

                else:
                    # Phase 1 fallback: No resolution data, show simple list
                    display_limit = 20
                    for imp in imports[:display_limit]:
                        imp_type = imp.get('type')
                        module = imp.get('module', '')
                        line = imp.get('line', '?')
                        names = imp.get('names')
                        alias = imp.get('alias')
                        level = imp.get('level', 0)

                        # Format relative imports with dots
                        if level > 0:
                            dots = '.' * level
                            if module:
                                module_display = f"{dots}{module}"
                            else:
                                module_display = dots
                        else:
                            module_display = module

                        # Format display based on import type
                        if imp_type == 'import':
                            if alias:
                                parts.append(f"    → import {module_display} as {alias} (line {line})")
                            else:
                                parts.append(f"    → import {module_display} (line {line})")
                        elif imp_type == 'from_import' and names:
                            names_str = ', '.join(names[:5])  # Show first 5 names
                            if len(names) > 5:
                                names_str += f", ... ({len(names)} total)"
                            parts.append(f"    → from {module_display} import {names_str} (line {line})")

                    # Show truncation message if needed
                    if total_imports > display_limit:
                        parts.append("")
                        parts.append(f"    ... and {total_imports - display_limit} more imports")

                if truncated:
                    parts.append("  ⚠️  Import list truncated at 100 - file may have more imports")

        elif dependencies and dependencies.get('error'):
            # Show error but don't spam output
            parts.append("")
            parts.append(f"📦 Dependencies: Unable to parse imports ({dependencies.get('error', 'unknown error')})")

        # STATIC ANALYSIS DISCLAIMER (Phase 4: Honest framing of limitations)
        # Show disclaimer when dependencies or impact radius are displayed
        if (dependencies and not dependencies.get('error')) or (data.get('impact_radius') and not data.get('impact_radius', {}).get('error')):
            parts.append("")
            parts.append("ℹ️  Note: Dependencies shown reflect static import analysis only. Runtime dependencies, dynamic imports, and reflection patterns are not detected.")

        # IMPACT RADIUS ANALYSIS (Phase 3: Reverse lookup / cross-file graphing)
        impact_radius = data.get('impact_radius')
        if impact_radius and not impact_radius.get('error'):
            count = impact_radius.get('count', 0)
            level = impact_radius.get('level', 'low')
            importers = impact_radius.get('importers', [])
            truncated = impact_radius.get('truncated', False)
            perf_warning = impact_radius.get('performance_warning')

            # Only show impact section if file is actually imported somewhere
            if count > 0:
                parts.append("")

                # Impact level display with appropriate emoji
                if level == 'high':
                    parts.append(f"🚨 Impact Radius: This file is imported by {count} files [HIGH IMPACT]")
                elif level == 'medium':
                    parts.append(f"⚠️  Impact Radius: This file is imported by {count} files [MEDIUM IMPACT]")
                else:
                    parts.append(f"Impact Radius: This file is imported by {count} files")

                parts.append("")

                # Show importer list
                if importers:
                    parts.append("  Files that import this:")
                    for importer in importers:
                        parts.append(f"    • {importer}")

                    # Truncation message
                    if truncated:
                        remaining = count - len(importers)
                        parts.append(f"    ... and {remaining} more files")

                # Performance warning if scan was slow
                if perf_warning:
                    parts.append("")
                    parts.append(f"  ⚠️  {perf_warning}")

        elif impact_radius and impact_radius.get('error'):
            # Show error but don't spam output
            parts.append("")
            parts.append(f"Impact Radius: Unable to calculate ({impact_radius.get('error', 'unknown error')})")

        # BOUNDARY VIOLATIONS (Phase 4: Forbidden import pattern detection)
        boundary_violations = data.get('boundary_violations')
        if boundary_violations and boundary_violations.get('enabled'):
            violations = boundary_violations.get('violations', [])
            if violations:
                # Count violations by severity
                errors = [v for v in violations if v.get('severity') == 'error']
                warnings = [v for v in violations if v.get('severity') == 'warning']
                infos = [v for v in violations if v.get('severity') == 'info']

                # Build summary
                parts.append("")
                summary_parts = []
                if errors:
                    summary_parts.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}")
                if warnings:
                    summary_parts.append(f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}")
                if infos:
                    summary_parts.append(f"{len(infos)} info")

                parts.append(f"🚫 Boundary Violations: {', '.join(summary_parts)}")
                parts.append("")

                # Sort violations by severity (errors first, then warnings, then info)
                severity_order = {'error': 0, 'warning': 1, 'info': 2}
                sorted_violations = sorted(violations, key=lambda v: severity_order.get(v.get('severity', 'info'), 3))

                # Display each violation
                for violation in sorted_violations:
                    severity = violation.get('severity', 'info').upper()
                    rule_name = violation.get('rule_name', 'Unknown Rule')
                    violated_import = violation.get('violated_import', '?')
                    message = violation.get('message', '')
                    line = violation.get('line', 0)

                    # Severity tag with visual distinction
                    parts.append(f"  [{severity}] {rule_name}")
                    parts.append(f"    → {violated_import} (line {line})")
                    if message:
                        parts.append(f"    {message}")
                    parts.append("")  # Blank line between violations

        # METADATA AT BOTTOM
        parts.append("")  # Blank line before metadata
        parts.append("─" * 63)  # Separator line

        # Build metadata lines
        metadata_lines = []
        metadata_lines.append(f"Path: {path}")
        metadata_lines.append(f"Size: {scan.get('byte_size', 0)} bytes | Total lines: {total_lines} | Encoding: {scan.get('encoding', 'utf-8')}")

        # Add mode-specific metadata
        if 'chunks' in data and len(data['chunks']) > 1:
            metadata_lines.append(f"Chunks: {len(data['chunks'])} of {scan.get('estimated_chunk_count', '?')}")
        if data.get('page_number'):
            metadata_lines.append(f"Page: {data['page_number']} (size: {data.get('page_size', '?')})")
        if 'max_matches' in data:
            metadata_lines.append(f"Matches: {len(data.get('matches', []))} of {data.get('max_matches', '?')} max")

        # Add SHA256 (truncated)
        if scan.get('sha256'):
            metadata_lines.append(f"SHA256: {scan['sha256'][:16]}...")

        parts.extend(metadata_lines)

        # Add navigation hints if present (scan_only mode)
        nav_hints = data.get('navigation_hints')
        if nav_hints and mode == 'scan_only':
            parts.append("")
            parts.append("💡 Navigation Hints:")
            parts.append(f"   Chunks available: {nav_hints.get('total_chunks', 0)}")
            parts.append(f"   Suggested chunk size: {nav_hints.get('suggested_chunk_size', 1)}")
            examples = nav_hints.get('examples', {})
            if examples:
                parts.append("   Quick examples:")
                for mode_name, example in list(examples.items())[:3]:
                    parts.append(f"     • {example}")

        # Add advanced analysis hint if present (scan_only mode without dependencies)
        adv_hint = data.get('advanced_analysis_hint')
        if adv_hint and mode == 'scan_only':
            parts.append("")
            parts.append("🔬 Advanced Analysis:")
            parts.append(f"   {adv_hint.get('message', '')}")
            if adv_hint.get('example'):
                parts.append(f"   Example: {adv_hint['example']}")

        # Add reminders if present
        reminders = data.get('reminders', [])
        if reminders:
            parts.append("")
            parts.append("⏰ Reminders:")
            for reminder in reminders:
                parts.append(f"   • {reminder.get('message', '')}")

        return '\n'.join(parts)

    def format_readable_log_entries(self, entries: List[Dict], pagination: Dict, search_context: Optional[Dict] = None, project_name: Optional[str] = None) -> str:
        """
        Format log entries in readable format with reasoning blocks.

        Delegates to EntryFormatter.format_readable_log_entries() (Phase 5 Task 5.4).

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
        return self._entry.format_readable_log_entries(entries, pagination, search_context, project_name)

    def _truncate_message_smart(self, message: str, max_length: int = 100) -> str:
        """
        Truncate message at word boundary for better readability.

        Delegates to EntryFormatter._truncate_message_smart() (Phase 5 Task 5.4).

        Args:
            message: Message to truncate
            max_length: Maximum length before truncation

        Returns:
            Truncated message with ellipsis or original if short enough
        """
        return self._entry._truncate_message_smart(message, max_length)

    def format_readable_projects(self, projects: List[Dict], active: Optional[str] = None) -> str:
        """
        Format list_projects output in readable format.

        Delegates to ProjectFormatter.format_readable_projects() (Phase 5 Task 5.5).

        Args:
            projects: List of project dicts
            active: Name of active project (if any)

        Returns:
            Formatted string with header box, project table, footer
        """
        return self._project.format_readable_projects(projects, active)

    def format_readable_confirmation(self, operation: str, data: Dict[str, Any]) -> str:
        """
        Format operation confirmations (append_entry, etc) in readable format.

        Delegates to ProjectFormatter.format_readable_confirmation() (Phase 5 Task 5.5).

        Args:
            operation: Operation name (e.g., "append_entry")
            data: Operation result data

        Returns:
            Formatted confirmation string
        """
        return self._project.format_readable_confirmation(operation, data)

    def format_readable_error(self, error: str, context: Dict[str, Any]) -> str:
        """
        Format error messages in readable format.

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
        parts.append(self._create_header_box("ERROR", header_meta))
        parts.append("")
        parts.append(f"❌ {error}")
        parts.append("")

        # Add context if available
        if context:
            footer_meta = {k: v for k, v in context.items() if k != 'error_type'}
            parts.append(self._create_footer_box(footer_meta))

        return '\n'.join(parts)

    def _parse_reasoning_block(self, meta: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Parse reasoning block from meta.reasoning field.

        Delegates to EntryFormatter._parse_reasoning_block() (Phase 5 Task 5.4).

        Args:
            meta: Metadata dictionary that may contain reasoning field

        Returns:
            Dictionary with why/what/how keys or None if not parseable
        """
        return self._entry._parse_reasoning_block(meta)

    def _format_relative_time(self, timestamp: str) -> str:
        """
        Convert timestamp to relative time string.

        Delegates to BaseFormatter.format_relative_time() (Phase 5 Task 5.2).

        Examples:
            "2026-01-03T08:15:30Z" -> "2 hours ago" (if now is 10:15)
            "2026-01-02T10:00:00Z" -> "1 day ago"
            "2025-12-20T14:30:00Z" -> "2 weeks ago"

        Args:
            timestamp: ISO 8601 timestamp string (UTC)

        Returns:
            Relative time string or original timestamp if parsing fails
        """
        return self._base.format_relative_time(timestamp)

    def _get_doc_line_count(self, file_path: Union[str, Path]) -> int:
        """
        Get line count for a file using efficient method.

        Delegates to FileFormatter (Phase 5 Task 5.3).

        Args:
            file_path: Absolute or relative path to file

        Returns:
            Number of lines in file, or 0 if file doesn't exist
        """
        return self._file._get_doc_line_count(file_path)

    def _detect_custom_content(self, docs_dir: Union[str, Path]) -> Dict[str, Any]:
        """
        Detect custom documents in project dev plan directory.

        Delegates to FileFormatter (Phase 5 Task 5.3).

        Args:
            docs_dir: Path to project dev plan directory
                      (e.g., .scribe/docs/dev_plans/project_name/)

        Returns:
            Dictionary with custom content info
        """
        return self._file._detect_custom_content(docs_dir)

    def format_projects_table(
        self,
        projects: List[Dict[str, Any]],
        active_name: Optional[str],
        pagination: Dict[str, Any],
        filters: Dict[str, Any]
    ) -> str:
        """
        Format multiple projects as minimal table with pagination.

        Delegates to ProjectFormatter.format_projects_table() (Phase 5 Task 5.5).

        Used when filter results in 2+ projects.

        Args:
            projects: List of project dicts (from list_projects query)
            active_name: Name of currently active project (for star marker)
            pagination: Dict with page, page_size, total_count, total_pages
            filters: Dict with name, status, tags, order_by, direction

        Returns:
            Formatted table string (~200 tokens)
        """
        return self._project.format_projects_table(projects, active_name, pagination, filters)

    def format_project_detail(
        self,
        project: Dict[str, Any],
        registry_info: Optional[Any],
        docs_info: Dict[str, Any]
    ) -> str:
        """
        Format single project with full details (deep dive).

        Delegates to ProjectFormatter.format_project_detail() (Phase 5 Task 5.5).

        Used when filter results in exactly 1 project.

        Args:
            project: Project dict from list_projects
            registry_info: ProjectRecord from registry (or None)
            docs_info: Dict with document information

        Returns:
            Formatted detail view string (~400 tokens)
        """
        return self._project.format_project_detail(project, registry_info, docs_info)

    def format_no_projects_found(self, filters: Dict[str, Any]) -> str:
        """
        Format helpful empty state when no projects match filters.

        Delegates to ProjectFormatter.format_no_projects_found() (Phase 5 Task 5.5).

        Args:
            filters: Dict with name, status, tags filter values

        Returns:
            Formatted empty state string (~100 tokens)
        """
        return self._project.format_no_projects_found(filters)

    def format_project_context(
        self,
        project: Dict[str, Any],
        recent_entries: List[Dict[str, Any]],
        docs_info: Dict[str, Any],
        activity: Dict[str, Any]
    ) -> str:
        """
        Format current project context with recent activity.

        Delegates to ProjectFormatter.format_project_context() (Phase 5 Task 5.5).

        Shows "Where am I?" information: location, documents, recent work.

        Args:
            project: Project dict with name, root, progress_log
            recent_entries: Last 1-5 progress log entries (COMPLETE, no truncation!)
            docs_info: Dict with document information
            activity: Dict with activity summary

        Returns:
            Formatted context string (~300 tokens with 1-5 recent entries)
        """
        return self._project.format_project_context(project, recent_entries, docs_info, activity)

    def format_project_sitrep_new(
        self,
        project: Dict[str, Any],
        docs_created: Dict[str, str]
    ) -> str:
        """
        Format SITREP for newly created project.

        Delegates to ProjectFormatter.format_project_sitrep_new() (Phase 5 Task 5.5).

        Shows: location, created documents with template info, next steps.

        Args:
            project: Project dict with name, root, progress_log
            docs_created: Dict mapping doc type to path

        Returns:
            Formatted SITREP string (~150 tokens)
        """
        return self._project.format_project_sitrep_new(project, docs_created)

    def format_project_sitrep_existing(
        self,
        project: Dict[str, Any],
        inventory: Dict[str, Any],
        activity: Dict[str, Any]
    ) -> str:
        """
        Format SITREP for existing project activation.

        Delegates to ProjectFormatter.format_project_sitrep_existing() (Phase 5 Task 5.5).

        Shows: location, inventory (docs + custom content), activity, warnings.

        Args:
            project: Project dict with name, root, progress_log
            inventory: Dict with project inventory
            activity: Dict with activity summary

        Returns:
            Formatted SITREP string (~250 tokens)
        """
        return self._project.format_project_sitrep_existing(project, inventory, activity)

    def format_readable_append_entry(self, data: Dict[str, Any]) -> str:
        """
        Format append_entry output in concise readable format.

        Delegates to EntryFormatter.format_readable_append_entry() (Phase 5 Task 5.4).

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
        return self._entry.format_readable_append_entry(data)

    def _format_single_append_entry(self, data: Dict[str, Any], USE_COLORS: bool) -> str:
        """
        Format single append_entry in optimized readable format.

        Delegates to EntryFormatter._format_single_append_entry() (Phase 5 Task 5.4).
        """
        return self._entry._format_single_append_entry(data, USE_COLORS)

    def _format_bulk_append_entry(self, data: Dict[str, Any], USE_COLORS: bool) -> str:
        """
        Format bulk append_entry in summary format.

        Delegates to EntryFormatter._format_bulk_append_entry() (Phase 5 Task 5.4).
        """
        return self._entry._format_bulk_append_entry(data, USE_COLORS)

    def _extract_compact_log_line(self, full_line: str) -> str:
        """
        Extract compact version of log line for bulk display.

        Delegates to EntryFormatter._extract_compact_log_line() (Phase 5 Task 5.4).

        Args:
            full_line: Full log line with all metadata

        Returns:
            Compact version with emoji + message + key metadata
        """
        return self._entry._extract_compact_log_line(full_line)

    async def finalize_tool_response(
        self,
        data: Dict[str, Any],
        format: str = "readable",  # NOTE: readable is DEFAULT
        tool_name: str = ""
    ) -> Union[Dict[str, Any], "CallToolResult"]:
        """
        CRITICAL ROUTER: Logs tool call to JSONL and SQL, then formats response.

        Delegates to FormatterDispatcher.finalize_tool_response() (Phase 5 Task 5.6).

        This method ensures complete audit trail by logging structured data to:
        1. JSONL: .scribe/logs/TOOL_LOG.jsonl (via tool_logger.py - synchronous)
        2. SQL: tool_calls table (via storage.record_tool_call() - async fire-and-forget)

        Uses direct logging to prevent recursion (no append_entry calls).

        ISSUE #9962 FIX: When format="readable", we return CallToolResult with
        TextContent ONLY (no structuredContent). This forces Claude Code to
        display the text cleanly with actual newlines instead of escaped \\n.

        Args:
            data: Tool response data (always a dict)
            format: Output format - "readable", "structured", "compact", or "both"
            tool_name: Name of the tool being called

        Returns:
            - format="readable": CallToolResult with TextContent only (clean display)
            - format="both": CallToolResult with TextContent + structuredContent
            - format="structured"/"compact": Original data dict
            - Fallback to dict if MCP types unavailable
        """
        return await self._dispatcher.finalize_tool_response(data, format, tool_name)

    def format_projects_response(self, projects: List[Dict[str, Any]],
                               compact: bool = False,
                               fields: Optional[List[str]] = None,
                               extra_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format response for list_projects tool.

        Delegates to ProjectFormatter.format_projects_response() (Phase 5 Task 5.5).
        """
        return self._project.format_projects_response(projects, compact, fields, extra_data)


# Global pagination calculator instance
_PAGINATION_CALCULATOR = PaginationCalculator()

def create_pagination_info(page: int, page_size: int, total_count: int) -> PaginationInfo:
    """Create pagination metadata using PaginationCalculator.

    Delegates to formatters.base.create_pagination_info() (Phase 5 Task 5.2).
    Kept here for backward compatibility.
    """
    return _create_pagination_info_base(page, page_size, total_count)


# Default formatter instance
default_formatter = ResponseFormatter()


# ============================================================================
# SPEC-TOKEN-003: Global Optimization Utilities
# ============================================================================


def format_compact_json(
    data: dict,
    abbreviations: Optional[dict] = None
) -> str:
    """
    Format JSON with abbreviated keys for compact mode.

    Delegates to formatters.base.format_compact_json() (Phase 5 Task 5.2).
    Kept here for backward compatibility.

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
    return _format_compact_json_base(data, abbreviations)


# Note: format_header and add_tip are now imported from utils.formatters.ui
# at the top of this file (Phase 5 Task 5.1 modularization).
# They remain available from this module for backward compatibility.
# See: from .formatters.ui import UIFormatter, format_header, add_tip