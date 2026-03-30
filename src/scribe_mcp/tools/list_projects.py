"""Tool for enumerating known projects."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tool_contracts import read_only_local_tool
from scribe_mcp.tools.project_utils import load_active_project
from scribe_mcp.utils.tokens import token_estimator
from scribe_mcp.utils.context_safety import ContextManager
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError
from scribe_mcp.shared.project_registry import ProjectRegistry
from scribe_mcp.shared.project_utils import detect_project_state
from scribe_mcp.config.repo_config import get_current_repo_config


MINIMAL_FIELDS = ("name", "root", "progress_log")
COMPACT_FIELD_MAP = {
    "name": "n",
    "root": "r",
    "progress_log": "p",
    "docs": "d",
    "defaults": "df",
    # Registry-related fields
    "status": "s",
    "created_at": "c",
    "last_entry_at": "le",
    "last_access_at": "la",
    "last_status_change": "ls",
    "total_entries": "te",
    "total_files": "tf",
    "total_phases": "tp",
    "description": "desc",
    "tags": "tg",
    "meta": "m",
    # SITREP-related fields (Phase 4.3)
    "state": "st",
    "sitrep_message": "sm",
    "entry_count": "ec",
}

# State icons for readable format
STATE_ICONS = {
    "NEW": "🆕",
    "EXISTING_LEGACY": "📋",
    "UNCHANGED": "✓",
    "MODIFIED": "✏️"
}

logger = logging.getLogger(__name__)


def _compute_summary_stats(projects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute summary statistics for project states.

    Args:
        projects: List of project dicts with 'state' field

    Returns:
        Dict with state breakdown:
        {
            "total_projects": 47,
            "NEW": 5,
            "EXISTING_LEGACY": 3,
            "UNCHANGED": 20,
            "MODIFIED": 19
        }
    """
    stats = {
        "total_projects": len(projects),
        "NEW": 0,
        "EXISTING_LEGACY": 0,
        "UNCHANGED": 0,
        "MODIFIED": 0
    }

    for project in projects:
        state = project.get("state", "UNKNOWN")
        if state in stats:
            stats[state] += 1

    return stats


class _ListProjectsHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_LIST_PROJECTS_HELPER = _ListProjectsHelper()
_PROJECT_REGISTRY = ProjectRegistry()


async def _gather_doc_info(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gather document information for a project (for detail view).

    Args:
        project: Project dict with name, root, progress_log, meta (with docs.flags)

    Returns:
        Dict with document information:
        {
            "architecture": {"exists": True, "lines": 1274, "modified": True},
            "phase_plan": {"exists": True, "lines": 542, "modified": False},
            "checklist": {"exists": True, "lines": 356, "modified": False},
            "progress": {"exists": True, "entries": 298},
            "custom": {
                "research_files": 3,
                "bugs_present": False,
                "jsonl_files": ["TOOL_LOG.jsonl"]
            }
        }
    """
    from scribe_mcp.utils.response import default_formatter

    # Extract dev plan directory from progress_log path
    progress_log = project.get('progress_log', '')
    if not progress_log or not Path(progress_log).exists():
        return {}

    # Get dev plan directory
    dev_plan_dir = Path(progress_log).parent

    # Extract modification flags from project meta
    meta = project.get("meta", {})
    docs_meta = meta.get("docs", {})
    flags = docs_meta.get("flags", {})

    result = {}

    # Check standard documents with actual modification status
    arch_file = dev_plan_dir / "ARCHITECTURE_GUIDE.md"
    if arch_file.exists():
        result["architecture"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(arch_file),
            "modified": flags.get("architecture_modified", False)
        }

    phase_file = dev_plan_dir / "PHASE_PLAN.md"
    if phase_file.exists():
        result["phase_plan"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(phase_file),
            "modified": flags.get("phase_plan_modified", False)
        }

    checklist_file = dev_plan_dir / "CHECKLIST.md"
    if checklist_file.exists():
        result["checklist"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(checklist_file),
            "modified": flags.get("checklist_modified", False)
        }

    # Progress log - count entries not lines
    prog_file = Path(progress_log)
    if prog_file.exists():
        # Count entries by looking for emoji markers
        try:
            with open(prog_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Count lines starting with '[' (emoji markers)
                entry_count = sum(1 for line in content.split('\n') if line.strip().startswith('['))
            result["progress"] = {
                "exists": True,
                "entries": entry_count
            }
        except (OSError, UnicodeError) as exc:
            logger.warning(
                "Failed to read progress log '%s' while building project docs status: %s",
                prog_file,
                exc,
            )
            result["progress"] = {"exists": True, "entries": 0}

    # Detect custom content
    result["custom"] = default_formatter._detect_custom_content(dev_plan_dir)

    return result


@app.tool(**read_only_local_tool(title="List Projects", tags=("projects", "discovery", "read-only")))
async def list_projects(
    agent: str = "Codex",
    limit: Optional[int] = 5,  # Changed default to 5 for context safety
    filter: Optional[str] = None,
    root: Optional[str] = None,  # Filter by repo root path (for bridge resolution)
    global_mode: bool = False,  # NEW: Set True to list projects across ALL repos
    compact: bool = False,
    fields: Optional[List[str]] = None,
    include_test: bool = False,  # New parameter to control test project visibility
    page: int = 1,  # New pagination parameter
    page_size: Optional[int] = None,  # New pagination size override
    status: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    order_by: Optional[str] = None,
    direction: str = "desc",
    format: str = "readable",  # New parameter for output format
) -> Dict[str, Any]:
    """Return projects registered in the database or state cache with intelligent filtering.

    By default, only returns projects scoped to the CURRENT REPOSITORY.
    Use global_mode=True to see projects across all repositories.

    Args:
        limit: Maximum number of projects to return (default: 5 for context safety)
        filter: Filter projects by name (case-insensitive substring match)
        root: Filter projects by repo root path (exact match, path-normalized)
        global_mode: If True, list ALL projects across all repos. Default False = current repo only.
        compact: Use compact response format with short field names
        fields: Specific fields to include in response
        include_test: Include test/temp projects (default: False)
        page: Page number for pagination (default: 1)
        page_size: Number of items per page (default: 5 or limit if specified)
        status: Optional list of lifecycle statuses to include (e.g., ['planning','in_progress'])
        tags: Optional list of tags; projects matching any tag are included
        order_by: Optional sort field: created_at|last_entry_at|last_access_at|total_entries
        direction: Sort direction ('asc' or 'desc') when order_by is provided
        format: Output format ('readable', 'structured', 'compact') (default: 'structured')

    Returns:
        Projects list with intelligent filtering, pagination, and context safety.
        For readable format: 3-way routing (0 matches → empty state, 1 → detail, multiple → table)
    """
    state_snapshot = await server_module.state_manager.record_tool("list_projects")
    agent_identity = server_module.get_agent_identity()
    agent_id = None
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

    try:
        context: LoggingContext = await _LIST_PROJECTS_HELPER.prepare_context(
            tool_name="list_projects",
            agent_id=agent_id,
            require_project=False,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _LIST_PROJECTS_HELPER.translate_project_error(exc)
        payload.setdefault("reminders", [])
        return payload

    state = await server_module.state_manager.load()
    projects_map: Dict[str, Dict[str, Any]] = {}

    # Determine repo scope for query
    # Priority: explicit root > auto-detect current repo > global if global_mode=True
    effective_repo_root: Optional[str] = None
    if root:
        # Explicit root filter takes precedence
        effective_repo_root = str(Path(root).resolve())
    elif not global_mode:
        # Default: scope to current repository
        try:
            current_repo_root, _ = get_current_repo_config()
            effective_repo_root = str(current_repo_root)
        except Exception:
            # If repo detection fails, fall back to global (with warning)
            pass

    backend = server_module.storage_backend
    if backend:
        if effective_repo_root and hasattr(backend, "list_projects_by_repo"):
            # Repo-scoped query (default behavior)
            records = await backend.list_projects_by_repo(effective_repo_root)
        else:
            # Global query (explicit global_mode=True or fallback)
            records = await backend.list_projects()
        for record in records:
            projects_map[record.name] = {
                "name": record.name,
                "root": record.repo_root,
                "progress_log": record.progress_log_path,
            }

    for name, data in state.projects.items():
        # Keep state cache merge global for backward compatibility with direct tool invocation.
        existing = projects_map.get(name, {"name": name})
        if data.get("root"):
            existing["root"] = data["root"]
        if data.get("progress_log"):
            existing["progress_log"] = data["progress_log"]
        if data.get("docs"):
            existing["docs"] = data["docs"]
        if data.get("defaults"):
            existing["defaults"] = data["defaults"]
        if data.get("description"):
            existing["description"] = data["description"]
        if data.get("tags"):
            existing["tags"] = data["tags"]
        projects_map[name] = existing

    active_project, current_name, recent = await load_active_project(server_module.state_manager)
    if active_project and active_project["name"] not in projects_map:
        projects_map[active_project["name"]] = {
            "name": active_project["name"],
            "root": active_project.get("root"),
            "progress_log": active_project.get("progress_log"),
            "docs": active_project.get("docs"),
            "defaults": active_project.get("defaults"),
            "description": active_project.get("description"),
            "tags": active_project.get("tags"),
        }

    # Enrich with Project Registry information (best-effort).
    for name, data in list(projects_map.items()):
        try:
            info = _PROJECT_REGISTRY.get_project(name)
        except Exception:
            info = None
        if not info:
            continue

        # Only set fields that aren't already present from state.
        data.setdefault("description", info.description)
        data.setdefault("status", info.status)
        data.setdefault("created_at", info.created_at.isoformat() if info.created_at else None)
        data.setdefault("last_entry_at", info.last_entry_at.isoformat() if info.last_entry_at else None)
        data.setdefault("last_access_at", info.last_access_at.isoformat() if info.last_access_at else None)
        data.setdefault(
            "last_status_change",
            info.last_status_change.isoformat() if info.last_status_change else None,
        )
        data.setdefault("total_entries", info.total_entries)
        data.setdefault("total_files", info.total_files)
        data.setdefault("total_phases", info.total_phases)
        if info.meta and "meta" not in data:
            data["meta"] = info.meta
        if info.tags and "tags" not in data:
            data["tags"] = info.tags

    # Integrate state detection for all projects (Phase 4.3)
    for name, data in projects_map.items():
        # Get entry count from backend
        entry_count = 0
        if backend:
            try:
                raw_count = await backend.count_entries(name)
                if isinstance(raw_count, (int, float)):
                    entry_count = int(raw_count)
                elif isinstance(raw_count, str) and raw_count.strip().isdigit():
                    entry_count = int(raw_count.strip())
                else:
                    entry_count = int(data.get("total_entries", 0) or 0)
            except Exception:
                # Fallback to total_entries from registry if count_entries fails
                entry_count = int(data.get("total_entries", 0) or 0)

        # Detect state using Phase 4.1 infrastructure
        state, sitrep_message = detect_project_state(data, entry_count)

        # Add state information to project data
        data["state"] = state
        data["sitrep_message"] = sitrep_message
        data["entry_count"] = entry_count

    # Convert to list and apply name/root/status/tag filters if provided
    projects_list = list(projects_map.values())
    if filter:
        filter_lower = filter.lower()
        projects_list = [
            project for project in projects_list
            if filter_lower in project.get("name", "").lower()
        ]

    # NEW: Filter by repo root path (exact match, path-normalized)
    if root:
        # Normalize the search path for consistent matching
        normalized_search = str(Path(root).resolve()) if root else None
        if normalized_search:
            projects_list = [
                project for project in projects_list
                if project.get("root") and str(Path(project["root"]).resolve()) == normalized_search
            ]

    if status:
        allowed_status = {s for s in status if isinstance(s, str)}

        def _effective_status(project: Dict[str, Any]) -> str:
            return (project.get("status") or "planning").lower()

        projects_list = [
            project
            for project in projects_list
            if _effective_status(project) in allowed_status
        ]

    if tags:
        wanted_tags = {t for t in tags if isinstance(t, str)}

        def _project_tags(project: Dict[str, Any]) -> set[str]:
            raw = project.get("tags") or []
            if isinstance(raw, str):
                return {raw}
            try:
                return {t for t in raw if isinstance(t, str)}
            except TypeError:
                return set()

        projects_list = [
            project
            for project in projects_list
            if _project_tags(project) & wanted_tags
        ]

    # Ordering: default by name; optional registry-aware sort when order_by is provided.
    if order_by:
        direction_norm = direction.lower()
        reverse = direction_norm != "asc"

        def _parse_ts(value: Optional[str]) -> datetime:
            if not value:
                # Use minimal datetime to push missing values to one end
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                # Fallback: try parsing legacy SQLite timestamps without offsets.
                try:
                    dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    return dt.replace(tzinfo=timezone.utc)
                except Exception:
                    return datetime.min.replace(tzinfo=timezone.utc)

        if order_by in ("created_at", "last_entry_at", "last_access_at"):
            projects_list.sort(
                key=lambda item: _parse_ts(item.get(order_by)), reverse=reverse
            )
        elif order_by == "total_entries":
            projects_list.sort(
                key=lambda item: int(item.get("total_entries") or 0),
                reverse=reverse,
            )
        else:
            # Fallback: keep name-based ordering if unsupported field requested.
            projects_list.sort(key=lambda item: item["name"].lower())
    else:
        # Sort by name for stable ordering when no explicit order_by is given.
        projects_list.sort(key=lambda item: item["name"].lower())

    # Initialize context manager for intelligent filtering and pagination
    context_manager = ContextManager()

    # Determine page size (use explicit page_size, then limit, then default) with type conversion
    try:
        limit_int = int(limit) if limit is not None else None
    except (ValueError, TypeError):
        limit_int = None

    try:
        page_size_int = int(page_size) if page_size is not None else None
    except (ValueError, TypeError):
        page_size_int = None

    effective_page_size = page_size_int or limit_int or context_manager.paginator.default_page_size

    context_response = context_manager.prepare_response(
        items=projects_list,
        response_type="projects",
        include_test=include_test,
        page=page,
        page_size=effective_page_size,
        compact=compact
    )

    # Include SITREP fields in default field set (Phase 4.3)
    default_fields = list(MINIMAL_FIELDS) + ["state", "sitrep_message", "entry_count"]
    selected_fields = fields or default_fields

    def _format_project(project: Dict[str, Any]) -> Dict[str, Any]:
        formatted: Dict[str, Any] = {}
        for field in selected_fields:
            if field not in project:
                continue
            key = COMPACT_FIELD_MAP.get(field, field) if compact else field
            formatted[key] = project[field]
        return formatted

    formatted_projects = [_format_project(project) for project in context_response["items"]]

    pagination_info = context_response["pagination"]
    total_available = context_response["total_available"]
    filtered_flag = context_response["filtered"]

    # 3-WAY ROUTING for readable format
    if format == "readable":
        from scribe_mcp.utils.response import default_formatter

        filtered_count = len(formatted_projects)

        if filtered_count == 0:
            # Route 1: No matches - helpful empty state
            filter_info = {
                "name": filter,
                "root": root,
                "status": status,
                "tags": tags
            }
            readable_content = default_formatter.format_no_projects_found(filter_info)

            # Return via finalize_tool_response for consistency
            response = {
                "ok": True,
                "projects": [],
                "count": 0,
                "readable_content": readable_content,
                "active_project": current_name
            }
            response = _LIST_PROJECTS_HELPER.apply_context_payload(response, context)
            if context.reminders:
                response["reminders"] = list(context.reminders)
            return response

        elif filtered_count == 1:
            # Route 2: Single match - deep dive detail view
            # Use original project from projects_list (before formatting)
            project = context_response["items"][0]

            # Gather detailed info
            registry_info = None
            try:
                registry_info = _PROJECT_REGISTRY.get_project(project["name"])
            except Exception:
                pass

            docs_info = await _gather_doc_info(project)

            readable_content = default_formatter.format_project_detail(project, registry_info, docs_info)

            response = {
                "ok": True,
                "projects": formatted_projects,
                "count": 1,
                "readable_content": readable_content,
                "active_project": current_name
            }
            response = _LIST_PROJECTS_HELPER.apply_context_payload(response, context)
            if context.reminders:
                response["reminders"] = list(context.reminders)
            return response

        else:
            # Route 3: Multiple matches - paginated table view
            # Calculate total_pages from pagination info
            total_pages = (pagination_info["total_count"] + pagination_info["page_size"] - 1) // pagination_info["page_size"]

            pagination_info_dict = {
                "page": pagination_info["page"],
                "page_size": pagination_info["page_size"],
                "total_count": pagination_info["total_count"],
                "total_pages": total_pages,
                "has_next": pagination_info.get("has_next", False),
                "has_prev": pagination_info.get("has_prev", False)
            }
            filter_info = {
                "name": filter,
                "root": root,
                "status": status,
                "tags": tags,
                "order_by": order_by,
                "direction": direction
            }

            # Pass original projects (before formatting) for richer table display
            readable_content = default_formatter.format_projects_table(
                context_response["items"],
                current_name,
                pagination_info_dict,
                filter_info
            )

            response = {
                "ok": True,
                "projects": formatted_projects,
                "count": filtered_count,
                "pagination": pagination_info,
                "readable_content": readable_content,
                "active_project": current_name
            }
            response = _LIST_PROJECTS_HELPER.apply_context_payload(response, context)
            if context.reminders:
                response["reminders"] = list(context.reminders)
            return response

    # For structured/compact formats, continue with existing logic

    # PHASE 2: Implement true compact mode (BUG-COMPACT-001 fix)
    if format == "compact":
        # Compact mode: abbreviated keys, minimal fields, omit nulls
        compact_projects = []
        for project in formatted_projects:
            compact_proj = {"n": project.get("name")}

            # Only include non-null values
            if project.get("status"):
                compact_proj["s"] = project["status"]
            if project.get("entry_count") or project.get("total_entries"):
                compact_proj["e"] = project.get("entry_count", project.get("total_entries", 0))
            if project.get("last_entry_at"):
                compact_proj["a"] = project["last_entry_at"]

            compact_projects.append(compact_proj)

        # Minimal pagination info
        compact_pagination = {
            "i": pagination_info["page"],
            "sz": pagination_info["page_size"],
            "nx": pagination_info.get("has_next", False),
            "pv": pagination_info.get("has_prev", False)
        }

        # Return minimal response with legacy keys for compatibility.
        return {
            "ok": True,
            "projects": compact_projects,
            "count": len(compact_projects),
            "compact": True,
            "pagination": {
                "page": pagination_info["page"],
                "page_size": pagination_info["page_size"],
                "total_count": pagination_info["total_count"],
                "has_next": pagination_info.get("has_next", False),
                "has_prev": pagination_info.get("has_prev", False),
            },
            "p": compact_projects,
            "tot": total_available,
            "pg": compact_pagination
        }

    if format == "structured":
        summary_stats = _compute_summary_stats(formatted_projects)
        response = {
            "ok": True,
            "projects": formatted_projects,
            "count": len(formatted_projects),
            "total": total_available,
            "pagination": {
                "page": pagination_info["page"],
                "page_size": pagination_info["page_size"],
                "total_count": pagination_info["total_count"],
                "has_next": pagination_info.get("has_next", False),
                "has_prev": pagination_info.get("has_prev", False),
            },
            "summary": summary_stats,
            "recent_projects": list(recent),
            "active_project": (
                current_name
                if current_name
                else (context.project.get("name") if context.project else None)
            ),
        }
        return _LIST_PROJECTS_HELPER.apply_context_payload(response, context)

    # Legacy fallback for backward compatibility (compact parameter, not format)
    token_check = context_manager.token_guard.check_limits(
        {"projects": formatted_projects, "count": len(formatted_projects)}
    )

    context_safety = {
        "estimated_tokens": token_check.get("estimated_tokens", 0),
        "pagination_used": pagination_info["total_count"] > pagination_info["page_size"],
        "filtered": filtered_flag,
    }
    if compact:
        context_safety["compact_mode"] = True

    # Compute summary statistics for all projects (Phase 4.3)
    summary_stats = _compute_summary_stats(context_response["items"])

    response = {
        "ok": True,
        "projects": formatted_projects,
        "count": len(formatted_projects),
        "pagination": pagination_info,
        "total_available": total_available,
        "filtered": filtered_flag,
        "recent_projects": list(recent),
        "active_project": (
            current_name
            if current_name
            else (context.project.get("name") if context.project else None)
        ),
        "context_safety": context_safety,
        "summary": summary_stats,  # Phase 4.3: State breakdown statistics
    }

    if token_check.get("warning"):
        response["token_warning"] = {
            "estimated_tokens": token_check["estimated_tokens"],
            "warning_threshold": context_manager.token_guard.warning_threshold,
            "message": token_check["message"],
            "suggestion": token_check["suggestion"],
        }
    elif token_check.get("critical"):
        response["token_critical"] = {
            "estimated_tokens": token_check["estimated_tokens"],
            "hard_limit": context_manager.token_guard.hard_limit,
            "message": token_check["message"],
            "suggestion": token_check["suggestion"],
        }

    if compact:
        response["compact"] = True

    # Record token usage
    if token_estimator:
        token_estimator.record_operation(
            operation="list_projects",
            input_data={
                "limit": limit,
                "filter": filter,
                "compact": compact,
                "fields": fields,
                "include_test": include_test,
                "page": page,
            "page_size": effective_page_size
        },
        response=response,
        compact_mode=compact,
        page_size=len(formatted_projects)
    )

    return _LIST_PROJECTS_HELPER.apply_context_payload(response, context)
