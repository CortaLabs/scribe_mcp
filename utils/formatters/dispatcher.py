#!/usr/bin/env python3
"""
Central dispatcher for tool response formatting (Phase 5 Task 5.6).

Extracted from ResponseFormatter.finalize_tool_response.
This is the CRITICAL ROUTER that ALL tool responses flow through.

Design:
- FormatterDispatcher routes tool responses to appropriate domain formatters
- Handles MCP SDK types (CallToolResult, TextContent) with fallback
- Logs tool calls to JSONL and SQL for audit trail
- Supports format parameters: readable, structured, compact, both
"""

import json
from typing import Dict, List, Any, Optional, Union

# Import domain formatters
from .base import BaseFormatter
from .ui import UIFormatter
from .file import FileFormatter
from .entry import EntryFormatter
from .project import ProjectFormatter

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


class FormatterDispatcher:
    """Central dispatcher that routes tool responses to domain formatters.

    This class contains the critical finalize_tool_response method that:
    1. Logs tool calls to JSONL and SQL (audit trail)
    2. Routes responses to appropriate formatters based on tool_name
    3. Handles MCP SDK types for clean display in Claude Code

    Attributes:
        _threshold: Token warning threshold for large responses
        _base: BaseFormatter instance for utility methods
        _ui: UIFormatter instance for UI elements
        _file: FileFormatter instance for file content formatting
        _entry: EntryFormatter instance for log entry formatting
        _project: ProjectFormatter instance for project formatting
    """

    # Format constants (same as ResponseFormatter)
    FORMAT_READABLE = "readable"
    FORMAT_STRUCTURED = "structured"
    FORMAT_COMPACT = "compact"
    FORMAT_BOTH = "both"

    def __init__(
        self,
        token_warning_threshold: int = 4000,
        base_formatter: Optional[BaseFormatter] = None,
        ui_formatter: Optional[UIFormatter] = None,
        file_formatter: Optional[FileFormatter] = None,
        entry_formatter: Optional[EntryFormatter] = None,
        project_formatter: Optional[ProjectFormatter] = None,
    ):
        """Initialize dispatcher with optional pre-configured formatters.

        Args:
            token_warning_threshold: Threshold for token estimation warnings
            base_formatter: Optional pre-configured BaseFormatter
            ui_formatter: Optional pre-configured UIFormatter
            file_formatter: Optional pre-configured FileFormatter
            entry_formatter: Optional pre-configured EntryFormatter
            project_formatter: Optional pre-configured ProjectFormatter
        """
        self._threshold = token_warning_threshold

        # Use provided formatters or create new ones
        self._base = base_formatter or BaseFormatter(token_warning_threshold)
        self._ui = ui_formatter or UIFormatter()
        self._file = file_formatter or FileFormatter(token_warning_threshold)
        self._entry = entry_formatter or EntryFormatter(token_warning_threshold)
        self._project = project_formatter or ProjectFormatter(token_warning_threshold)

    async def finalize_tool_response(
        self,
        data: Dict[str, Any],
        format: str = "readable",  # NOTE: readable is DEFAULT
        tool_name: str = ""
    ) -> Union[Dict[str, Any], "CallToolResult"]:
        """
        CRITICAL ROUTER: Logs tool call to JSONL and SQL, then formats response.

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
        # STEP 1: Log tool call directly to JSONL and SQL (no recursion)
        # JSONL: via tool_logger.py (synchronous file write)
        # SQL: via storage.record_tool_call() (async DB insert for analytics)
        try:
            from utils.tool_logger import log_tool_call

            # Extract session context from server module
            session_id = "unknown"
            project_name = None
            agent_id = None
            repo_root = None  # Will be resolved below

            try:
                import server as server_module
                if hasattr(server_module, "get_execution_context"):
                    exec_context = server_module.get_execution_context()
                    if exec_context:
                        session_id = getattr(exec_context, 'session_id', 'unknown')
                        # Get project name from affected_dev_projects list (first item if present)
                        affected_projects = getattr(exec_context, 'affected_dev_projects', [])
                        if affected_projects and len(affected_projects) > 0:
                            project_name = affected_projects[0]
                        # Get agent display name
                        agent_identity = getattr(exec_context, 'agent_identity', None)
                        if agent_identity:
                            agent_id = getattr(agent_identity, 'display_name', None)
            except Exception:
                # Context extraction failed, use defaults (session_id="unknown")
                pass

            # STEP 1.1: Resolve repo_root and progress_log_path for per-project tool logging
            # Priority: 1) Project's progress_log_path from DB (ensures correct slugification)
            #           2) Current repo root for sentinel mode
            #           3) None (falls back to SCRIBE_ROOT)
            progress_log_path = None
            try:
                import server as server_module
                storage = getattr(server_module, 'storage_backend', None)

                # Try to get project details from DB
                if project_name and storage and hasattr(storage, 'fetch_project_sync'):
                    try:
                        project_record = storage.fetch_project_sync(project_name)
                        if project_record:
                            if hasattr(project_record, 'repo_root') and project_record.repo_root:
                                repo_root = project_record.repo_root
                            if hasattr(project_record, 'progress_log_path') and project_record.progress_log_path:
                                progress_log_path = project_record.progress_log_path
                    except Exception:
                        pass  # Project lookup failed, continue to fallback

                # Fallback: use current repo root from repo_config
                if not repo_root:
                    try:
                        from config.repo_config import get_current_repo_config
                        current_repo_root, _ = get_current_repo_config()
                        if current_repo_root:
                            repo_root = str(current_repo_root)
                    except Exception:
                        pass  # Repo config failed, repo_root stays None (uses SCRIBE_ROOT)
            except Exception:
                pass  # resolution failed entirely, stays None

            # Calculate response size for metrics
            response_size = len(json.dumps(data)) if isinstance(data, dict) else 0

            # Log synchronously (tool_logger is sync function)
            log_tool_call(
                tool_name=tool_name,
                session_id=session_id,
                status="success" if data.get('ok', True) else "error",
                format_requested=format,
                project_name=project_name,
                agent_id=agent_id,
                error_message=data.get('error') if not data.get('ok', True) else None,
                response_size_bytes=response_size,
                repo_root=repo_root,
                progress_log_path=progress_log_path
            )

            # STEP 1.5: Write to SQL for cross-project analytics
            try:
                import server as server_module
                storage = getattr(server_module, 'storage_backend', None)
                if storage and hasattr(storage, 'record_tool_call_sync'):
                    import asyncio
                    # Fire-and-forget background task with proper GC protection
                    # Uses module-level background_tasks set to prevent garbage collection
                    # See: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
                    server_module.schedule_background_task(asyncio.to_thread(
                        storage.record_tool_call_sync,
                        session_id=session_id,
                        tool_name=tool_name,
                        duration_ms=None,  # Will add timing in future enhancement
                        status="success" if data.get('ok', True) else "error",
                        format_requested=format,
                        project_name=project_name,
                        agent_id=agent_id,
                        error_message=data.get('error') if not data.get('ok', True) else None,
                        response_size_bytes=response_size,
                        repo_root=repo_root
                    ))
            except Exception as e:
                # SQL logging is optional, never block tools
                import sys
                print(f"Warning: SQL tool logging failed: {e}", file=sys.stderr)
        except Exception as e:
            # Tool logging must never block tool execution
            import sys
            print(f"Warning: Tool logging failed: {e}", file=sys.stderr)

        # STEP 2: Format based on parameter
        if format == self.FORMAT_READABLE:
            # PRIORITY 1: Check if integration code already populated readable_content
            # (Used by list_projects, get_project, set_project with new formatters)
            if 'readable_content' in data:
                readable_content = data['readable_content']
            # PRIORITY 2: Check for errors
            elif data.get('ok') == False or 'error' in data:
                readable_content = self._format_readable_error(
                    data.get('error', 'Unknown error'),
                    data
                )
            # PRIORITY 3: Route to appropriate readable formatter based on tool
            elif tool_name == "read_file":
                readable_content = self._file.format_readable_file_content(data)
            elif tool_name in ["read_recent", "query_entries"]:
                # Pass search context for query_entries to show filters
                search_context = None
                if tool_name == "query_entries":
                    # Extract search parameters from data (prefixed with search_)
                    search_context = {}
                    if 'search_message' in data:
                        search_context['message'] = data['search_message']
                    if 'search_status' in data:
                        search_context['status'] = data['search_status']
                    if 'search_agents' in data:
                        search_context['agents'] = data['search_agents']
                    if 'search_emoji' in data:
                        search_context['emoji'] = data['search_emoji']
                    # Always show search header for query_entries even if no filters
                    if not search_context:
                        search_context = {'_is_search': True}

                readable_content = self._entry.format_readable_log_entries(
                    data.get('entries', []),
                    data.get('pagination', {}),
                    search_context=search_context if search_context else None,
                    project_name=data.get('project_name')
                )
            elif tool_name == "append_entry":
                readable_content = self._entry.format_readable_append_entry(data)
            else:
                # Generic readable format for unknown tools
                readable_content = json.dumps(data, indent=2)

            # ISSUE #9962 FIX: Return CallToolResult with TextContent ONLY
            # This forces Claude Code to display text cleanly (no escaped \n)
            if MCP_TYPES_AVAILABLE and CallToolResult and TextContent:
                return CallToolResult(
                    content=[TextContent(type="text", text=readable_content)]
                    # NO structuredContent = Claude Code renders text cleanly!
                )
            else:
                # Fallback for environments without MCP SDK
                return {
                    "ok": True,
                    "format": "readable",
                    "content": readable_content,
                    "tool": tool_name
                }

        elif format == self.FORMAT_BOTH:
            # Build readable content (same logic as above)
            # PRIORITY 1: Check if integration code already populated readable_content
            if 'readable_content' in data:
                readable_content = data['readable_content']
            # PRIORITY 2: Check for errors
            elif data.get('ok') == False or 'error' in data:
                readable_content = self._format_readable_error(
                    data.get('error', 'Unknown error'),
                    data
                )
            # PRIORITY 3: Route to appropriate readable formatter
            elif tool_name == "read_file":
                readable_content = self._file.format_readable_file_content(data)
            elif tool_name in ["read_recent", "query_entries"]:
                # Pass search context for query_entries to show filters
                search_context = None
                if tool_name == "query_entries":
                    # Extract search parameters from data (prefixed with search_)
                    search_context = {}
                    if 'search_message' in data:
                        search_context['message'] = data['search_message']
                    if 'search_status' in data:
                        search_context['status'] = data['search_status']
                    if 'search_agents' in data:
                        search_context['agents'] = data['search_agents']
                    if 'search_emoji' in data:
                        search_context['emoji'] = data['search_emoji']
                    # Always show search header for query_entries even if no filters
                    if not search_context:
                        search_context = {'_is_search': True}

                readable_content = self._entry.format_readable_log_entries(
                    data.get('entries', []),
                    data.get('pagination', {}),
                    search_context=search_context if search_context else None,
                    project_name=data.get('project_name')
                )
            elif tool_name == "append_entry":
                readable_content = self._entry.format_readable_append_entry(data)
            else:
                readable_content = json.dumps(data, indent=2)

            # Return BOTH TextContent and structuredContent
            # (For when Issue #9962 is fixed, or for programmatic consumers)
            if MCP_TYPES_AVAILABLE and CallToolResult and TextContent:
                return CallToolResult(
                    content=[TextContent(type="text", text=readable_content)],
                    structuredContent=data  # Machine-readable data
                )
            else:
                return {
                    "ok": True,
                    "format": "both",
                    "content": readable_content,
                    "structured": data,
                    "tool": tool_name
                }

        elif format == self.FORMAT_COMPACT:
            # Return compact format (use existing compact logic if available)
            return data

        else:  # structured (default JSON)
            return data

    def _format_readable_error(self, error: str, context: Dict[str, Any]) -> str:
        """Format error response in readable format.

        Delegates to UIFormatter for error box formatting.

        Args:
            error: Error message string
            context: Additional context data

        Returns:
            Formatted error string
        """
        # Use UIFormatter's error formatting if available
        # For now, simple error box format
        lines = []
        lines.append("\u2554" + "\u2550" * 78 + "\u2557")
        lines.append("\u2551" + " ERROR".ljust(78) + "\u2551")
        lines.append("\u255f" + "\u2500" * 78 + "\u2562")

        # Wrap error message
        error_lines = error.split('\n')
        for line in error_lines:
            # Truncate long lines
            if len(line) > 76:
                line = line[:73] + "..."
            lines.append("\u2551 " + line.ljust(77) + "\u2551")

        # Add context if available
        if context.get('details'):
            lines.append("\u255f" + "\u2500" * 78 + "\u2562")
            details = context['details']
            if isinstance(details, dict):
                for key, value in details.items():
                    detail_line = f"{key}: {value}"
                    if len(detail_line) > 76:
                        detail_line = detail_line[:73] + "..."
                    lines.append("\u2551 " + detail_line.ljust(77) + "\u2551")

        lines.append("\u255a" + "\u2550" * 78 + "\u255d")

        return '\n'.join(lines)
