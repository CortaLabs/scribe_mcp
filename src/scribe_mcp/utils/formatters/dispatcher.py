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
import logging
import inspect
import time
import uuid
from typing import Dict, List, Any, Optional, Union

logger = logging.getLogger(__name__)

# Import domain formatters
from .base import BaseFormatter
from .ui import UIFormatter
from .file import FileFormatter
from .entry import EntryFormatter
from .project import ProjectFormatter

# Tool logging import:
# Prefer package import, fall back to relative import for src-layout/runtime variance.
try:
    from scribe_mcp.utils.tool_logger import log_tool_call as _log_tool_call
except Exception:  # pragma: no cover - import fallback for unusual runtimes
    from ..tool_logger import log_tool_call as _log_tool_call

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

    @staticmethod
    def _safe_json_dumps(value: Any, **kwargs: Any) -> str:
        """Serialize formatter payloads safely for mixed runtime objects."""
        return json.dumps(value, default=str, **kwargs)

    async def finalize_tool_response(
        self,
        data: Dict[str, Any],
        format: str = "readable",  # NOTE: readable is DEFAULT
        tool_name: str = "",
        telemetry: Optional[Dict[str, Any]] = None,
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
            telemetry: Optional additive timing/correlation context

        Returns:
            - format="readable": CallToolResult with TextContent only (clean display)
            - format="both": CallToolResult with TextContent + structuredContent
            - format="structured"/"compact": Original data dict
            - Fallback to dict if MCP types unavailable
        """
        boundary_started = time.perf_counter()
        telemetry_context = telemetry if isinstance(telemetry, dict) else {}

        # STEP 1: Log tool call directly to JSONL and SQL (no recursion)
        # JSONL: via tool_logger.py (synchronous file write)
        # SQL: via storage.record_tool_call() (async DB insert for analytics)
        try:
            # Extract session context from server module
            session_id = "unknown"
            project_name = None
            agent_id = None
            repo_root = None  # Will be resolved below

            try:
                try:
                    from scribe_mcp import server as server_module
                except ImportError:
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
                try:
                    from scribe_mcp import server as server_module
                except ImportError:
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
                        try:
                            from scribe_mcp.config.repo_config import get_current_repo_config
                        except ImportError:
                            from config.repo_config import get_current_repo_config
                        current_repo_root, _ = get_current_repo_config()
                        if current_repo_root:
                            repo_root = str(current_repo_root)
                    except Exception:
                        pass  # Repo config failed, repo_root stays None (uses SCRIBE_ROOT)
            except Exception:
                pass  # resolution failed entirely, stays None

            # Calculate response size for metrics
            response_size = len(self._safe_json_dumps(data)) if isinstance(data, dict) else 0
            duration_ms = telemetry_context.get("duration_ms")
            started_at = telemetry_context.get("started_perf_counter")
            if not isinstance(duration_ms, (int, float)):
                if isinstance(started_at, (int, float)):
                    duration_ms = (time.perf_counter() - float(started_at)) * 1000.0
                else:
                    duration_ms = (time.perf_counter() - boundary_started) * 1000.0
            duration_ms = max(round(float(duration_ms), 3), 0.0)
            correlation_id = str(telemetry_context.get("correlation_id") or data.get("correlation_id") or uuid.uuid4())
            measurement_scope = str(telemetry_context.get("measurement_scope") or "tool_only")

            # Log synchronously (tool_logger is sync function)
            _log_tool_call(
                tool_name=tool_name,
                session_id=session_id,
                duration_ms=duration_ms,
                status="success" if data.get('ok', True) else "error",
                format_requested=format,
                project_name=project_name,
                agent_id=agent_id,
                error_message=data.get('error') if not data.get('ok', True) else None,
                response_size_bytes=response_size,
                repo_root=repo_root,
                progress_log_path=progress_log_path,
                correlation_id=correlation_id,
                measurement_scope=measurement_scope,
            )

            # STEP 1.5: Write to SQL for cross-project analytics
            try:
                try:
                    from scribe_mcp import server as server_module
                except ImportError:
                    import server as server_module
                storage = getattr(server_module, 'storage_backend', None)
                if storage:
                    import asyncio
                    call_kwargs = {
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "duration_ms": duration_ms,
                        "status": "success" if data.get('ok', True) else "error",
                        "format_requested": format,
                        "project_name": project_name,
                        "agent_id": agent_id,
                        "error_message": data.get('error') if not data.get('ok', True) else None,
                        "response_size_bytes": response_size,
                        "repo_root": repo_root,
                    }
                    try:
                        parameters = inspect.signature(storage.record_tool_call_sync).parameters
                        if "correlation_id" in parameters:
                            call_kwargs["correlation_id"] = correlation_id
                        if "measurement_scope" in parameters:
                            call_kwargs["measurement_scope"] = measurement_scope
                    except (TypeError, ValueError):
                        pass
                    if hasattr(storage, 'record_tool_call_sync'):
                        # Fire-and-forget background task with proper GC protection.
                        server_module.schedule_background_task(asyncio.to_thread(
                            storage.record_tool_call_sync,
                            **call_kwargs,
                        ))
                    else:
                        async_recorder = getattr(storage, "record_tool_call", None)
                        if callable(async_recorder):
                            server_module.schedule_background_task(async_recorder(**call_kwargs))
            except Exception as e:
                # SQL logging is optional, never block tools
                logger.warning("SQL tool logging failed: %s", e)
        except Exception as e:
            # Tool logging must never block tool execution
            logger.warning("Tool logging failed: %s", e)

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
                readable_content = self._safe_json_dumps(data, indent=2)

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
                readable_content = self._safe_json_dumps(data, indent=2)

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

        # Path context
        if context.get('absolute_path'):
            lines.append(f"\n  Path: {context['absolute_path']}")

        # Fuzzy suggestions (from path_suggestions enrichment)
        if context.get('suggestion'):
            lines.append(f"\n  {context['suggestion']}")
        if context.get('similar_files'):
            for sf in context['similar_files'][:5]:
                name = sf['name'] if isinstance(sf, dict) else sf
                score = f" ({int(sf['score']*100)}%)" if isinstance(sf, dict) and 'score' in sf else ""
                lines.append(f"    - {name}{score}")

        # Directory contents listing (from path_suggestions enrichment)
        if context.get('parent_listing'):
            listing = context['parent_listing']
            dirs = listing.get('directories', [])
            files = listing.get('files', [])
            total = len(dirs) + len(files)
            truncated = listing.get('truncated', False)
            lines.append(f"\n  Contents ({total} items):")
            # Always show ALL directories
            if dirs:
                for d in dirs:
                    lines.append(f"    {d}/")
            # Show files (capped at 20)
            if files:
                for f in files[:20]:
                    lines.append(f"    {f}")
                remaining = len(files) - 20
                if remaining > 0 or truncated:
                    extra = remaining if remaining > 0 else 0
                    lines.append(f"    ... and {extra} more files" if extra else "    (truncated)")

        # Cross-tool search suggestion
        if context.get('search_suggestion'):
            lines.append(f"\n  Tip: {context['search_suggestion']}")

        # Valid modes (for unsupported mode errors)
        if context.get('valid_modes'):
            lines.append(f"\n  Valid modes: {', '.join(context['valid_modes'])}")

        # Mode descriptions (for unsupported mode errors)
        if context.get('mode_descriptions'):
            lines.append("\n  Mode reference:")
            for mode_name, desc in context['mode_descriptions'].items():
                lines.append(f"    • {mode_name}: {desc}")

        # General suggestion (for unsupported mode errors)
        if context.get('suggestion') and not context.get('search_suggestion'):
            lines.append(f"\n  💡 {context['suggestion']}")

        return '\n'.join(lines)
