"""Tool for reading recent log entries."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tool_contracts import read_only_local_tool
from scribe_mcp.tools.constants import STATUS_EMOJI
from scribe_mcp.utils.files import read_tail
from scribe_mcp.utils.response import create_pagination_info, ResponseFormatter
from scribe_mcp.utils.tokens import token_estimator
from scribe_mcp.utils.estimator import ParameterTypeEstimator
from scribe_mcp.utils.config_manager import TokenBudgetManager
from scribe_mcp.utils.entry_limit import EntryLimitManager
from scribe_mcp.utils.error_handler import HealingErrorHandler
from scribe_mcp.config.settings import settings
from scribe_mcp.shared.logging_utils import (
    ProjectResolutionError,
    build_resolution_metadata,
    resolve_logging_context,
)
from scribe_mcp.shared.project_registry import get_runtime_project_registry
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin


class _ReadRecentHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module
        self.token_budget_manager = TokenBudgetManager()
        self.parameter_estimator = ParameterTypeEstimator()
        self.error_handler = HealingErrorHandler()
        self.formatter = ResponseFormatter()

    def heal_parameters_with_exception_handling(
        self,
        n: Optional[Any] = None,
        limit: Optional[Any] = None,
        page: int = 1,
        page_size: int = 50,
        compact: bool = False,
        fields: Optional[List[str]] = None,
        include_metadata: bool = True
    ) -> tuple[dict, bool]:
        """
        Heal parameters using Phase 1 exception handling utilities.

        Args:
            All read_recent parameters

        Returns:
            Tuple of (healed_params_dict, healing_applied_bool)
        """
        healing_applied = False
        healing_messages = []

        healed_params = {}

        # Heal n/limit parameter (limit is an alias)
        effective_n = n if n is not None else limit
        if effective_n is not None:
            healed_n, n_healed, n_message = self.parameter_estimator.heal_comparison_operator_bug(
                effective_n, "n"
            )
            if n_healed:
                healing_applied = True
                healing_messages.append(n_message)
                # Try to convert to int for page_size calculation
                try:
                    healed_n = int(healed_n)
                except (ValueError, TypeError):
                    healed_n = 50  # fallback
            healed_params["n"] = healed_n
        else:
            healed_params["n"] = None

        # Heal page parameter
        healed_page, page_healed, page_message = self.parameter_estimator.heal_comparison_operator_bug(
            page, "page"
        )
        if page_healed:
            healing_applied = True
            healing_messages.append(page_message)
            try:
                healed_page = max(1, int(healed_page))
            except (ValueError, TypeError):
                healed_page = 1
        else:
            try:
                healed_page = max(1, int(page))
            except (ValueError, TypeError):
                healed_page = 1
        healed_params["page"] = healed_page

        # Heal page_size parameter
        healed_page_size, page_size_healed, page_size_message = self.parameter_estimator.heal_comparison_operator_bug(
            page_size, "page_size"
        )
        if page_size_healed:
            healing_applied = True
            healing_messages.append(page_size_message)
            try:
                healed_page_size = max(1, min(int(healed_page_size), 200))
            except (ValueError, TypeError):
                healed_page_size = 50
        else:
            try:
                healed_page_size = max(1, min(int(page_size), 200))
            except (ValueError, TypeError):
                healed_page_size = 50
        healed_params["page_size"] = healed_page_size

        # Heal compact parameter
        if isinstance(compact, str):
            healed_compact = compact.lower() in ("true", "1", "yes")
            if healed_compact != compact:
                healing_applied = True
                healing_messages.append(f"Converted compact parameter from '{compact}' to boolean {healed_compact}")
        else:
            healed_compact = bool(compact)
        healed_params["compact"] = healed_compact

        # Heal fields parameter
        if fields is not None:
            if isinstance(fields, str):
                # Convert comma-separated string to list
                healed_fields = [field.strip() for field in fields.split(",") if field.strip()]
                healing_applied = True
                healing_messages.append(f"Converted fields from string to list: {healed_fields}")
            elif isinstance(fields, list):
                healed_fields = fields
            else:
                healed_fields = None
                healing_applied = True
                healing_messages.append(f"Invalid fields parameter type {type(fields)}, using None")
        else:
            healed_fields = None
        healed_params["fields"] = healed_fields

        # Heal include_metadata parameter
        if isinstance(include_metadata, str):
            healed_include_metadata = include_metadata.lower() in ("true", "1", "yes")
            if healed_include_metadata != include_metadata:
                healing_applied = True
                healing_messages.append(f"Converted include_metadata from '{include_metadata}' to boolean {healed_include_metadata}")
        else:
            healed_include_metadata = bool(include_metadata)
        healed_params["include_metadata"] = healed_include_metadata

        return healed_params, healing_applied, healing_messages


_READ_RECENT_HELPER = _ReadRecentHelper()
_PROJECT_REGISTRY = get_runtime_project_registry()


def _attach_resolution_metadata(response: Dict[str, Any], context: Any) -> None:
    """Attach readable project-resolution metadata to tool responses."""
    if not context:
        return
    resolution_payload = build_resolution_metadata(context)
    response["project"] = resolution_payload.get("project")
    response["project_resolution"] = {
        key: value for key, value in resolution_payload.items() if key != "project"
    }


def _entry_identity(entry: Dict[str, Any]) -> str:
    raw_line = str(entry.get("raw_line") or "").strip()
    if raw_line:
        return raw_line
    entry_id = str(entry.get("id") or "").strip()
    if entry_id:
        return f"id:{entry_id}"
    return "|".join(
        str(entry.get(key) or "").strip()
        for key in ("ts", "ts_iso", "agent", "message")
    )


async def _supplement_sparse_db_rows_from_progress_log(
    *,
    project: Dict[str, Any],
    rows: List[Dict[str, Any]],
    page: int,
    page_size: int,
    filters: Dict[str, Any],
    db_authoritative: bool = False,
) -> List[Dict[str, Any]]:
    # Skip supplementation when the DB is authoritative and returned rows.
    # Keep the fallback active when db_authoritative is True but the DB
    # returned nothing (e.g. mirror-lag window on a brand-new project).
    if db_authoritative and len(rows) > 0:
        return rows

    if page != 1 or len(rows) >= page_size:
        return rows

    progress_log = project.get("progress_log")
    if not progress_log or not Path(progress_log).exists():
        return rows

    fetch_limit = max(page_size * 3, page_size + len(rows))
    file_lines = await read_tail(
        _progress_log_path(project),
        fetch_limit,
        repo_root=Path(project.get("root") or settings.project_root).resolve(),
        context={"component": "logs", "project_name": project.get("name")},
    )
    file_lines = _apply_line_filters(file_lines, filters)

    from scribe_mcp.utils.logs import parse_log_line

    merged_rows = list(rows)
    seen = {_entry_identity(row) for row in merged_rows}
    for line in file_lines:
        parsed = parse_log_line(line)
        entry = parsed if parsed else {"raw_line": line, "message": line}
        identity = _entry_identity(entry)
        if identity in seen:
            continue
        merged_rows.append(entry)
        seen.add(identity)
        if len(merged_rows) >= page_size:
            break

    return merged_rows


@app.tool(**read_only_local_tool(title="Read Recent Entries", tags=("logs", "inspection", "read-only")))
async def read_recent(
    agent: str,
    project: Optional[str] = None,
    n: Optional[Any] = None,
    limit: Optional[Any] = None,
    filter: Optional[Dict[str, Any]] = None,
    page: int = 1,
    page_size: int = 10,
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_metadata: bool = True,
    format: str = "readable",
    priority: Optional[List[str]] = None,
    category: Optional[List[str]] = None,
    min_confidence: Optional[float] = None,
    priority_sort: bool = False,
) -> Dict[str, Any]:
    """Return recent log entries with pagination and formatting options.

    Args:
        project: Optional project name (uses active project if None)
        n: Legacy parameter for backward compatibility (max entries to return)
        limit: Alias for n (commonly used by agents)
        filter: Optional filters to apply (agent, status, emoji)
        page: Page number for pagination (1-based)
        page_size: Number of entries per page (default: 10)
        compact: Use compact response format with short field names
        fields: Specific fields to include in response
        include_metadata: Include metadata field in entries
        format: Output format - "readable" (default), "structured", or "compact"
        priority: Filter by priority levels (e.g., ["critical", "high"])
        category: Filter by categories (e.g., ["bug", "security"])
        min_confidence: Minimum confidence threshold (0.0-1.0)
        priority_sort: If True, sort by priority (critical first) then by time

    Returns:
        Paginated response with recent entries and metadata
    """
    _tool_started_perf_counter = time.perf_counter()
    state_snapshot = await server_module.state_manager.record_tool("read_recent")

    # Apply Phase 1 exception healing to all parameters
    try:
        healed_params, healing_applied, healing_messages = _READ_RECENT_HELPER.heal_parameters_with_exception_handling(
            n=n, limit=limit, page=page, page_size=page_size, compact=compact, fields=fields, include_metadata=include_metadata
        )

        # Update parameters with healed values
        n = healed_params["n"]
        page = healed_params["page"]
        page_size = healed_params["page_size"]
        compact = healed_params["compact"]
        fields = healed_params["fields"]
        include_metadata = healed_params["include_metadata"]

    except Exception as healing_error:
        # If healing fails completely, use safe defaults
        healed_params = {"n": None, "page": 1, "page_size": 50, "compact": False, "fields": None, "include_metadata": True}
        healing_applied = False
        healing_messages = [f"Parameter healing failed: {str(healing_error)}, using safe defaults"]
        n = None
        page = 1
        page_size = 50
        compact = False
        fields = None
        include_metadata = True

    exec_context = None
    if hasattr(server_module, "get_execution_context"):
        try:
            exec_context = server_module.get_execution_context()
        except Exception:
            exec_context = None

    if exec_context and getattr(exec_context, "mode", None) == "sentinel":
        context = await _READ_RECENT_HELPER.prepare_context(
            tool_name="read_recent",
            agent_id=None,
            explicit_project=None,
            require_project=False,
            state_snapshot=state_snapshot,
        )
        base_response = _READ_RECENT_HELPER.error_response(
            "Project resolution forbidden in sentinel mode.",
            suggestion="Invoke set_project before reading logs",
            context=context,
            extra={"warning": "sentinel_mode_no_project"},
        )
        _attach_resolution_metadata(base_response, context)
        # Add healing information if parameters were healed
        if healing_applied:
            base_response["parameter_healing"] = {
                "applied": True,
                "messages": healing_messages,
                "original_parameters": {"n": n, "page": page, "page_size": page_size},
            }
        return base_response

    # Preserve explicit project spelling; context resolver handles alias matching.
    if isinstance(project, str):
        project = project.strip() or None

    effective_recovery_mode = None
    if not project and not exec_context:
        try:
            state = await server_module.state_manager.load()
        except Exception:
            state = None
        if state and getattr(state, "current_project", None):
            effective_recovery_mode = "compat_active_project"

    try:
        context = await _READ_RECENT_HELPER.prepare_context(
            tool_name="read_recent",
            agent_id=None,
            explicit_project=project,
            require_project=True,
            state_snapshot=state_snapshot,
            recovery_mode=effective_recovery_mode,
        )
    except ProjectResolutionError as exc:
        base_response = _READ_RECENT_HELPER.translate_project_error(exc)
        base_response["suggestion"] = "Invoke set_project before reading logs"
        base_response.setdefault("reminders", [])
        _attach_resolution_metadata(base_response, context=None)

        # Add healing information if parameters were healed
        if healing_applied:
            base_response["parameter_healing"] = {
                "applied": True,
                "messages": healing_messages,
                "original_parameters": {"n": n, "page": page, "page_size": page_size}
            }

        return base_response

    project = context.project or {}

    # Resolve effective page_size.  n/limit is always an upper bound when
    # provided — the old guard `page_size == 50` only fired when page_size
    # happened to equal the healer default, silently ignoring `limit=1` when
    # the tool default was 10.  Correct fix: clamp page_size by n whenever n
    # is present, regardless of what page_size was set to.
    page_size = max(1, min(page_size, 200))
    if n is not None:
        limit_int = max(1, min(int(n), 200))
        page_size = min(page_size, limit_int)

    filters = filter or {}

    # Add new filters to the filters dict
    if priority:
        filters["priority"] = priority
    if category:
        filters["category"] = category
    if min_confidence is not None:
        filters["min_confidence"] = min_confidence
    if priority_sort:
        filters["priority_sort"] = priority_sort

    backend = server_module.storage_backend
    if backend:
        record = await backend.fetch_project(
            project["name"],
            repo_root=project.get("root"),
        )
        if record:
            # Use pagination if available
            if hasattr(backend, 'fetch_recent_entries_paginated'):
                rows, total_count = await backend.fetch_recent_entries_paginated(
                    project=record,
                    page=page,
                    page_size=page_size,
                    filters=_normalise_filters(filters),
                )
                pagination_info = create_pagination_info(page, page_size, total_count)
            else:
                # Fallback to legacy method with offset
                offset = (page - 1) * page_size
                rows = await backend.fetch_recent_entries(
                    project=record,
                    limit=page_size,
                    filters=_normalise_filters(filters),
                    offset=offset,
                )
                # Get total count
                total_count = await backend.count_entries(
                    project=record,
                    filters=_normalise_filters(filters)
                )
                pagination_info = create_pagination_info(page, page_size, total_count)

            rows = await _supplement_sparse_db_rows_from_progress_log(
                project=project,
                rows=rows,
                page=page,
                page_size=page_size,
                filters=filters,
                db_authoritative=True,
            )
            if len(rows) > total_count:
                total_count = len(rows)
                pagination_info = create_pagination_info(page, page_size, total_count)

            response = _READ_RECENT_HELPER.success_with_entries(
                entries=rows,
                context=context,
                compact=compact,
                fields=fields,
                include_metadata=include_metadata,
                pagination=pagination_info,
                extra_data={},
            )
            _attach_planning_advisories(response, project.get("name"), context=context)
            _attach_resolution_metadata(response, context)

            # For readable format, skip token budget truncation (full content needed)
            # Token budget only applies to structured/compact formats
            if format == "readable":
                if healing_applied:
                    response["parameter_healing"] = {
                        "applied": True,
                        "messages": healing_messages,
                        "original_parameters": {"n": healed_params["n"], "page": healed_params["page"], "page_size": healed_params["page_size"]}
                    }
                if context.reminders:
                    response["reminders"] = list(context.reminders)
                return await _READ_RECENT_HELPER.formatter.finalize_tool_response(
                    response,
                    format,
                    "read_recent",
                    telemetry={"started_perf_counter": _tool_started_perf_counter, "measurement_scope": "tool_only"},
                )

            # Apply EntryLimitManager for structured/compact formats
            # This preserves entry structure while limiting count intelligently
            entry_limiter = EntryLimitManager()
            limited_entries, limit_meta = entry_limiter.limit_entries(
                entries=response.get("entries", []),
                mode=format,
                sort_by_priority=True,  # Enable priority sorting
            )
            response["entries"] = limited_entries
            response["limit_metadata"] = limit_meta

            # Add healing information to response if parameters were healed
            if healing_applied:
                response["parameter_healing"] = {
                    "applied": True,
                    "messages": healing_messages,
                    "original_parameters": {"n": healed_params["n"], "page": healed_params["page"], "page_size": healed_params["page_size"]}
                }

            # Record token usage
            if token_estimator:
                token_estimator.record_operation(
                    operation="read_recent",
                    input_data={
                        "n": n,
                        "filter": filters,
                        "page": page,
                        "page_size": page_size,
                        "compact": compact,
                        "fields": fields,
                        "include_metadata": include_metadata,
                        "backend": "database"
                    },
                    response=response,
                    compact_mode=compact,
                    page_size=page_size
                )

            if context.reminders:
                response["reminders"] = list(context.reminders)
            return await _READ_RECENT_HELPER.formatter.finalize_tool_response(
                response,
                format,
                "read_recent",
                telemetry={"started_perf_counter": _tool_started_perf_counter, "measurement_scope": "tool_only"},
            )

    # File-based fallback with pagination
    # Read more lines than needed to account for filtering
    fetch_limit = page_size * 3  # Fetch 3x to account for filter reductions
    all_lines = await read_tail(
        _progress_log_path(project),
        fetch_limit,
        repo_root=Path(project.get("root") or settings.project_root).resolve(),
        context={"component": "logs", "project_name": project.get("name")},
    )
    all_lines = _apply_line_filters(all_lines, filters)

    # Apply pagination
    total_count = len(all_lines)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_lines = all_lines[start_idx:end_idx]

    pagination_info = create_pagination_info(page, page_size, total_count)

    # Convert lines to entry format for consistent response formatting
    from scribe_mcp.utils.logs import parse_log_line
    entries = []
    for line in paginated_lines:
        parsed = parse_log_line(line)
        if parsed:
            entries.append(parsed)
        else:
            # If parsing fails, include as raw line
            entries.append({"raw_line": line, "message": line})

    response = _READ_RECENT_HELPER.success_with_entries(
        entries=entries,
        context=context,
        compact=compact,
        fields=fields,
        include_metadata=include_metadata,
        pagination=pagination_info,
        extra_data={},
    )
    _attach_planning_advisories(response, project.get("name"), context=context)
    _attach_resolution_metadata(response, context)

    # For readable format, skip token budget truncation (full content needed)
    if format == "readable":
        if healing_applied:
            response["parameter_healing"] = {
                "applied": True,
                "messages": healing_messages,
                "original_parameters": {"n": healed_params["n"], "page": healed_params["page"], "page_size": healed_params["page_size"]}
            }
        if context.reminders:
            response["reminders"] = list(context.reminders)
        return await _READ_RECENT_HELPER.formatter.finalize_tool_response(
            response,
            format,
            "read_recent",
            telemetry={"started_perf_counter": _tool_started_perf_counter, "measurement_scope": "tool_only"},
        )

    # Apply EntryLimitManager for file-based fallback (structured/compact formats)
    # This preserves entry structure while limiting count intelligently
    entry_limiter = EntryLimitManager()
    limited_entries, limit_meta = entry_limiter.limit_entries(
        entries=response.get("entries", []),
        mode=format,
        sort_by_priority=True,  # Enable priority sorting
    )
    response["entries"] = limited_entries
    response["limit_metadata"] = limit_meta

    # Add healing information to response if parameters were healed
    if healing_applied:
        response["parameter_healing"] = {
            "applied": True,
            "messages": healing_messages,
            "original_parameters": {"n": healed_params["n"], "page": healed_params["page"], "page_size": healed_params["page_size"]}
        }

    # Record token usage
    if token_estimator:
        token_estimator.record_operation(
            operation="read_recent",
            input_data={
                "n": n,
                "filter": filters,
                "page": page,
                "page_size": page_size,
                "compact": compact,
                "fields": fields,
                "include_metadata": include_metadata,
                "backend": "file"
            },
            response=response,
            compact_mode=compact,
            page_size=page_size
        )

    if context.reminders:
        response["reminders"] = list(context.reminders)
    return await _READ_RECENT_HELPER.formatter.finalize_tool_response(
        response,
        format,
        "read_recent",
        telemetry={"started_perf_counter": _tool_started_perf_counter, "measurement_scope": "tool_only"},
    )


def _normalise_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    normalised: Dict[str, Any] = {}
    if "agent" in filters and filters["agent"]:
        normalised["agent"] = str(filters["agent"])
    if "status" in filters and filters["status"]:
        status = str(filters["status"])
        normalised["emoji"] = STATUS_EMOJI.get(status, status)
    if "emoji" in filters and filters["emoji"]:
        normalised["emoji"] = str(filters["emoji"])
    if "priority" in filters and filters["priority"]:
        normalised["priority"] = filters["priority"]
    if "category" in filters and filters["category"]:
        normalised["category"] = filters["category"]
    if "min_confidence" in filters and filters["min_confidence"] is not None:
        normalised["min_confidence"] = filters["min_confidence"]
    if "priority_sort" in filters:
        normalised["priority_sort"] = filters["priority_sort"]
    return normalised


def _attach_planning_advisories(
    response: Dict[str, Any],
    project_name: Optional[str],
    *,
    context: Optional[Any] = None,
) -> None:
    if not project_name:
        return
    if context is not None:
        resolution_source = str(getattr(context, "resolution_source", "") or "").strip().lower()
        if not resolution_source or resolution_source == "unresolved":
            return
    advisories = _PROJECT_REGISTRY.get_planning_advisories(project_name)
    if advisories:
        response["planning_advisories"] = advisories
        return
    get_context = getattr(_PROJECT_REGISTRY, "get_registry_advisory_context", None)
    if not callable(get_context):
        return
    try:
        registry_context = dict(get_context() or {})
    except Exception:
        return
    if registry_context and not registry_context.get("available", False):
        response["planning_advisories"] = {
            "available": False,
            "classification": registry_context.get("classification", "environment_mismatch"),
            "reason_code": registry_context.get("reason_code", "runtime_registry_unavailable"),
            "mode": registry_context.get("mode"),
            "storage_backend": registry_context.get("storage_backend"),
            "advisories": [
                {
                    "code": "planning_registry_unavailable",
                    "severity": "info",
                    "classification": registry_context.get("classification", "environment_mismatch"),
                    "message": registry_context.get(
                        "message",
                        "Planning-doc drift advisories are unavailable in this runtime.",
                    ),
                    "provenance": {
                        "source": "runtime.project_registry",
                        "fields": ["available", "reason_code", "classification", "mode", "storage_backend"],
                    },
                }
            ],
        }


def _apply_line_filters(lines: List[str], filters: Dict[str, Any]) -> List[str]:
    from scribe_mcp.utils.logs import parse_log_line
    from scribe_mcp.shared.log_enums import get_priority_sort_key

    agent = filters.get("agent")
    emoji = None
    if "emoji" in filters:
        emoji = filters["emoji"]
    elif "status" in filters:
        emoji = STATUS_EMOJI.get(filters["status"])

    priority_filter = filters.get("priority")
    category_filter = filters.get("category")
    min_confidence = filters.get("min_confidence")
    priority_sort = filters.get("priority_sort", False)

    # Parse lines and apply filters
    parsed_entries = []
    for line in lines:
        # Basic text filters (fast path)
        if agent and f"[Agent: {agent}]" not in line:
            continue
        if emoji and f"[{emoji}]" not in line:
            continue

        # Parse for advanced filters
        parsed = parse_log_line(line)
        if not parsed:
            continue

        # Filter by priority
        if priority_filter:
            entry_priority = parsed.get("meta", {}).get("priority", "medium")
            if entry_priority not in priority_filter:
                continue

        # Filter by category
        if category_filter:
            entry_category = parsed.get("meta", {}).get("category")
            if entry_category not in category_filter:
                continue

        # Filter by confidence
        if min_confidence is not None:
            entry_confidence = float(parsed.get("meta", {}).get("confidence", 1.0))
            if entry_confidence < min_confidence:
                continue

        parsed_entries.append((line, parsed))

    # Sort by priority if requested
    if priority_sort:
        # Sort by priority (critical=0 first) then by timestamp (DESC)
        # Negate timestamp for DESC sort since we're doing ASC sort on tuple
        parsed_entries.sort(
            key=lambda item: (
                get_priority_sort_key(item[1].get("meta", {}).get("priority", "medium")),
                -(ord(item[1].get("ts_iso", "")[0]) if item[1].get("ts_iso") else 0)  # Simple DESC approx
            )
        )

    return [line for line, _ in parsed_entries]


def _progress_log_path(project: Dict[str, Any]) -> Path:
    return Path(project["progress_log"])
