"""Tool for returning the currently active project."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tools.project_utils import load_active_project, load_project_config
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError
from scribe_mcp.shared.project_registry import ProjectRegistry
from scribe_mcp.shared.logging_utils import resolve_log_definition
from scribe_mcp.shared.project_utils import detect_project_state
from scribe_mcp.config import log_config as log_config_module
from scribe_mcp.utils.logs import parse_log_line, read_all_lines
from datetime import datetime, timezone


class _GetProjectHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_GET_PROJECT_HELPER = _GetProjectHelper()
_PROJECT_REGISTRY = ProjectRegistry()


async def _compute_doc_status(project_name: str, project_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Compute comprehensive document status for SITREP enhancement.

    Args:
        project_name: Name of the project
        project_data: Optional project dict with live 'docs' mapping from state_manager

    Returns:
        Dict containing flags, hashes, counts, doc list with modification indicators
    """
    info = _PROJECT_REGISTRY.get_project(project_name)
    if not info:
        return {}
    docs_meta = (info.meta or {}).get("docs") or {}
    flags = docs_meta.get("flags") or {}
    baseline_hashes = docs_meta.get("baseline_hashes") or {}
    current_hashes = docs_meta.get("current_hashes") or {}

    # Merge docs from baseline_hashes with live project.docs registry
    # This ensures newly registered docs appear in the list
    # Filter out keys starting with '_' (metadata like _hashes)
    all_doc_keys = set(baseline_hashes.keys())
    if project_data:
        live_docs = project_data.get("docs") or {}
        # Exclude metadata keys (start with '_')
        all_doc_keys.update(k for k in live_docs.keys() if not k.startswith("_"))

    # Build doc list with modification flags
    base_docs = ["architecture", "phase_plan", "checklist", "progress_log"]
    custom_docs = [doc for doc in all_doc_keys if doc not in base_docs]

    doc_list = []
    for doc_key in sorted(all_doc_keys):
        is_modified = flags.get(f"{doc_key}_modified", False)
        # Use different indicator for docs only in live registry (not in baseline_hashes)
        if doc_key in baseline_hashes:
            flag = "✏️" if is_modified else "✓"
        else:
            flag = "📄"  # Registered but no baseline hash yet
        doc_list.append(f"{flag} {doc_key}")

    return {
        "flags": flags,
        "baseline_hashes": baseline_hashes,
        "current_hashes": current_hashes,
        "last_update_at": docs_meta.get("last_update_at"),
        "update_count": docs_meta.get("update_count"),
        # SITREP enhancements
        "total_docs": len(all_doc_keys),
        "base_docs": len([d for d in base_docs if d in all_doc_keys]),
        "custom_docs": len(custom_docs),
        "doc_list": doc_list,
    }


async def _count_log_entries(log_path) -> int:
    try:
        lines = await read_all_lines(log_path)
    except Exception:
        return 0
    count = 0
    for line in lines:
        if parse_log_line(line):
            count += 1
    return count


async def _compute_log_counts(project: Dict[str, Any]) -> Dict[str, Any]:
    counts: Dict[str, Any] = {}
    logs = log_config_module.load_log_config()
    for log_type in sorted(logs.keys()):
        try:
            path, _definition = resolve_log_definition(project, log_type)
            if not path.exists():
                counts[log_type] = 0
                continue
            counts[log_type] = await _count_log_entries(path)
        except Exception:
            continue
    return counts


async def _read_recent_progress_entries(progress_log_path: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Read last N entries from progress log.

    Args:
        progress_log_path: Path to PROGRESS_LOG.md file
        limit: Maximum number of recent entries to return (1-5)

    Returns:
        List of entry dicts with timestamp, emoji, agent, message
        (COMPLETE messages - NO truncation!)
    """
    if not progress_log_path or not Path(progress_log_path).exists():
        return []

    try:
        # Read the log file
        with open(progress_log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # Parse entries (lines starting with '[')
        entries = []
        for line in lines:
            line = line.strip()
            if not line.startswith('['):
                continue

            # Parse entry format: [emoji] [timestamp] [Agent: name] [Project: name] message
            # Example: [ℹ️] [2026-01-03 09:53:42 UTC] [Agent: Orchestrator] [Project: xyz] Message here

            try:
                parts = line.split('] ', 4)  # Split on '] ' up to 5 parts
                if len(parts) < 5:
                    continue

                emoji = parts[0].strip('[')
                timestamp = parts[1].strip('[')
                agent_part = parts[2].strip('[')  # "Agent: name"
                # Skip project part (parts[3])
                message = parts[4]

                # Extract agent name
                agent = agent_part.replace('Agent: ', '') if 'Agent:' in agent_part else 'unknown'

                entries.append({
                    "emoji": emoji,
                    "timestamp": timestamp,
                    "agent": agent,
                    "message": message  # COMPLETE message - NO truncation!
                })
            except:
                continue

        # Return last N entries
        return entries[-limit:] if len(entries) > limit else entries

    except Exception:
        return []


async def _read_recent_entries_from_db(
    project_name: str,
    limit: int = 5,
    log_types: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Read last N entries from database (preferred over file-based).

    Args:
        project_name: Name of the project
        limit: Maximum number of recent entries to return
        log_types: Filter by log types (default: progress, bugs, security)

    Returns:
        List of entry dicts with timestamp, emoji, agent, message
    """
    try:
        import server as server_module
        backend = server_module.storage_backend
        if not backend:
            return []

        project_record = await backend.fetch_project(project_name)
        if not project_record:
            return []

        # Default to meaningful log types (exclude tool_logs)
        # Include both singular and plural variants for compatibility
        if log_types is None:
            log_types = ["progress", "bugs", "bug", "security"]

        entries = await backend.fetch_recent_entries(
            project=project_record,
            limit=limit,
            filters={"log_type": log_types}
        )

        # Format entries for display
        result = []
        for entry in entries:
            result.append({
                "emoji": entry.get("emoji", "ℹ️"),
                "timestamp": entry.get("ts_iso") or entry.get("ts", ""),
                "agent": entry.get("agent", "unknown"),
                "message": entry.get("message", "")
            })

        return result

    except Exception:
        return []


async def _format_readable_sitrep(
    project_name: str,
    state: str,
    sitrep_message: str,
    entry_count: int,
    timestamps: Dict[str, Any],
    doc_status: Dict[str, Any],
    recent_entries: List[Dict[str, Any]]
) -> str:
    """
    Format project SITREP as compact list box (~150-200 tokens).

    Args:
        project_name: Project name
        state: Project state (NEW, EXISTING_LEGACY, UNCHANGED, MODIFIED)
        sitrep_message: Human-readable status message
        entry_count: Total number of progress log entries
        timestamps: Dict with created_at, last_entry_at, current_time
        doc_status: Doc status from _compute_doc_status
        recent_entries: List of recent log entries (2-5)

    Returns:
        Formatted readable box string
    """
    # Build header with state
    header = f"📋 {project_name} ({state})"

    # Build info lines
    lines = []
    lines.append("╔" + "═" * (len(header) + 2) + "╗")
    lines.append(f"║ {header} ║")
    lines.append("╠" + "═" * (len(header) + 2) + "╣")

    # Timestamps
    if timestamps.get("created_at"):
        created = timestamps["created_at"][:19] if isinstance(timestamps["created_at"], str) else str(timestamps["created_at"])[:19]
        lines.append(f"║ Created: {created} UTC")

    if timestamps.get("last_entry_at"):
        last_entry = timestamps["last_entry_at"][:19] if isinstance(timestamps["last_entry_at"], str) else str(timestamps["last_entry_at"])[:19]
        lines.append(f"║ Last Entry: {last_entry} UTC")

    # Entry count
    lines.append(f"║ Entries: {entry_count} total")

    # Doc counts
    total_docs = doc_status.get("total_docs", 0)
    base_docs = doc_status.get("base_docs", 0)
    custom_docs = doc_status.get("custom_docs", 0)
    if total_docs > 0:
        lines.append(f"║ Docs: {total_docs} ({base_docs} base + {custom_docs} custom)")

        # Doc list (2 per line for compact display)
        doc_list = doc_status.get("doc_list", [])
        for i in range(0, len(doc_list), 2):
            doc_line = "  ".join(doc_list[i:i+2])
            lines.append(f"║   {doc_line}")

    # Recent entries section
    if recent_entries:
        lines.append("╠" + "═" * (len(header) + 2) + "╣")
        lines.append(f"║ Recent Entries (last {len(recent_entries)}):")
        for entry in recent_entries:
            # Format: [emoji] Message (truncate if very long, but NO truncation per user requirement)
            emoji = entry.get("emoji", "ℹ️")
            message = entry.get("message", "")
            lines.append(f"║ [{emoji}] {message}")

    # Footer
    lines.append("╚" + "═" * (len(header) + 2) + "╝")

    return "\n".join(lines)


async def _gather_doc_info(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gather document information for a project.

    Returns dict with architecture/phase_plan/checklist/progress info.
    """
    from utils.response import default_formatter

    progress_log = project.get('progress_log', '')
    if not progress_log or not Path(progress_log).exists():
        return {}

    dev_plan_dir = Path(progress_log).parent
    result = {}

    # Check standard documents
    arch_file = dev_plan_dir / "ARCHITECTURE_GUIDE.md"
    if arch_file.exists():
        result["architecture"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(arch_file)
        }

    phase_file = dev_plan_dir / "PHASE_PLAN.md"
    if phase_file.exists():
        result["phase_plan"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(phase_file)
        }

    checklist_file = dev_plan_dir / "CHECKLIST.md"
    if checklist_file.exists():
        result["checklist"] = {
            "exists": True,
            "lines": default_formatter._get_doc_line_count(checklist_file)
        }

    # Progress log - count entries
    prog_file = Path(progress_log)
    if prog_file.exists():
        try:
            with open(prog_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                entry_count = sum(1 for line in content.split('\n') if line.strip().startswith('['))
            result["progress"] = {"exists": True, "entries": entry_count}
        except:
            result["progress"] = {"exists": True, "entries": 0}

    return result


@app.tool()
async def get_project(project: Optional[str] = None, format: str = "structured", verbose: bool = False) -> Dict[str, Any]:
    """Return the active project selection, resolving defaults when necessary.

    Args:
        project: Optional project name to retrieve
        format: Output format - "readable" (human-friendly), "structured" (full JSON), "compact" (minimal)
        verbose: If True, include recent log entries in readable format (default: False)
    """
    state_snapshot = await server_module.state_manager.record_tool("get_project")
    agent_identity = server_module.get_agent_identity()
    agent_id = None
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

    try:
        context: LoggingContext = await _GET_PROJECT_HELPER.prepare_context(
            tool_name="get_project",
            agent_id=agent_id,
            explicit_project=project,
            require_project=False,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        payload = _GET_PROJECT_HELPER.translate_project_error(exc)
        payload.setdefault(
            "suggestion",
            "Invoke set_project or add a config/projects/<name>.json entry",
        )
        payload.setdefault("reminders", [])
        return payload

    recent_projects = list(context.recent_projects)

    target_project = context.project if context.project else None
    current_name = target_project.get("name") if target_project else None

    exec_context = None
    if hasattr(server_module, "get_execution_context"):
        try:
            exec_context = server_module.get_execution_context()
        except Exception:
            exec_context = None

    if project:
        # Attempt to load explicit project request
        state = await server_module.state_manager.load()
        project_data = state.get_project(project)
        if not project_data and context.project and context.project.get("name") == project:
            project_data = context.project
        if not project_data:
            config_project = load_project_config(project)
            if config_project:
                project_data = config_project
        if not project_data:
            return _GET_PROJECT_HELPER.apply_context_payload(
                _GET_PROJECT_HELPER.error_response(
                    f"Project '{project}' not found.",
                    suggestion="Ensure the project is registered via set_project or exists in config/projects/",
                ),
                context,
            )
        target_project = dict(project_data)
        current_name = project
    else:
        if exec_context and getattr(exec_context, "mode", None) in {"project", "sentinel"}:
            if not target_project:
                return _GET_PROJECT_HELPER.apply_context_payload(
                    _GET_PROJECT_HELPER.error_response(
                        "No session-scoped project configured.",
                        suggestion="Invoke set_project before using this tool",
                    ),
                    context,
                )
        if not target_project and not exec_context:
            active_project, current_name, recent = await load_active_project(server_module.state_manager)
            if active_project:
                target_project = dict(active_project)
                recent_projects = list(recent)
        if not target_project:
            extra: Dict[str, Any] = {}
            try:
                last_known = _PROJECT_REGISTRY.get_last_known_project(candidates=recent_projects)
                if last_known and last_known.last_access_at:
                    from datetime import datetime, timezone

                    minutes_ago = int(
                        max(
                            0.0,
                            (datetime.now(timezone.utc) - last_known.last_access_at).total_seconds() / 60.0,
                        )
                    )
                    extra["last_known_project"] = last_known.project_name
                    extra["last_known_project_minutes_ago"] = minutes_ago
                    extra["last_known_project_last_access_at"] = last_known.last_access_at.isoformat()
            except Exception:
                extra = {}

            return _GET_PROJECT_HELPER.apply_context_payload(
                _GET_PROJECT_HELPER.error_response(
                    "No project configured.",
                    suggestion="Invoke set_project or add a config/projects/<name>.json entry",
                    extra=extra or None,
                ),
                context,
            )

    response = dict(target_project)
    response.setdefault("meta", {})
    if current_name:
        response["meta"]["current_project"] = current_name

    # Enrich with doc status + per-log entry counts for quick situational awareness.
    try:
        if current_name:
            response.setdefault("meta", {})
            response["meta"]["docs_status"] = await _compute_doc_status(current_name, target_project)
            response["meta"]["log_entry_counts"] = await _compute_log_counts(response)
    except Exception:
        pass

    # Integrate state detection and SITREP data (Phase 4.2)
    state = "UNKNOWN"
    sitrep_message = ""
    entry_count = 0
    timestamps = {}

    try:
        if current_name:
            # Get entry count from backend (Phase 4.2)
            # Only count meaningful log types: progress, bugs, security (NOT tool_logs)
            backend = server_module.storage_backend
            # Fetch project record first to get proper ProjectRecord object
            project_record = await backend.fetch_project(current_name) if backend else None
            entry_count = await backend.count_entries(
                project_record,
                filters={"log_type": ["progress", "bugs", "bug", "security"]}
            ) if project_record else 0

            # Detect project state (Phase 4.1 integration)
            state, sitrep_message = detect_project_state(response, entry_count)

            # Get timestamps from registry
            registry_info = _PROJECT_REGISTRY.get_project(current_name)
            timestamps = {
                "created_at": registry_info.created_at.isoformat() if registry_info and registry_info.created_at else None,
                "last_entry_at": registry_info.last_entry_at.isoformat() if registry_info and registry_info.last_entry_at else None,
                "current_time": datetime.now(timezone.utc).isoformat()
            }

            # Add to response metadata
            response["meta"]["state"] = state
            response["meta"]["sitrep_message"] = sitrep_message
            response["meta"]["entry_count"] = entry_count
            response["meta"]["timestamps"] = timestamps
    except Exception:
        pass

    # Handle readable format with enhanced SITREP (Phase 4.2)
    if format == "readable":
        from utils.response import default_formatter

        # Read recent entries from DB only if verbose=True
        recent_entries = []
        if verbose and current_name:
            recent_entries = await _read_recent_entries_from_db(
                current_name,
                limit=3  # Use 3 for compact display (~150-200 tokens)
            )

        # Get doc status with counts and list (pass target_project for live docs registry)
        doc_status = await _compute_doc_status(current_name, target_project) if current_name else {}

        # Format SITREP using new compact formatter
        readable_content = await _format_readable_sitrep(
            project_name=current_name or "unknown",
            state=state,
            sitrep_message=sitrep_message,
            entry_count=entry_count,
            timestamps=timestamps,
            doc_status=doc_status,
            recent_entries=recent_entries
        )

        payload = {
            "ok": True,
            "project": response,
            "state": state,
            "sitrep_message": sitrep_message,
            "entry_count": entry_count,
            "timestamps": timestamps,
            "recent_entries": recent_entries,
            "readable_content": readable_content
        }
        if context.reminders:
            payload["reminders"] = list(context.reminders)

        return await default_formatter.finalize_tool_response(
            payload,
            format="readable",
            tool_name="get_project"
        )

    # For structured/compact formats with enhanced SITREP (Phase 4.2)
    if format in ["structured", "json", "compact"]:
        # Get recent entries from DB for JSON format
        recent_entries = await _read_recent_entries_from_db(
            current_name,
            limit=5
        ) if current_name else []

        # Get doc status (pass target_project for live docs registry)
        doc_status = await _compute_doc_status(current_name, target_project) if current_name else {}

        # Build enhanced payload
        payload = {
            "ok": True,
            "project": response,
            "recent_projects": recent_projects,
            # SITREP enhancements
            "state": state,
            "sitrep_message": sitrep_message,
            "entry_count": entry_count,
            "timestamps": timestamps,
            "docs": {
                "total": doc_status.get("total_docs", 0),
                "base": doc_status.get("base_docs", 0),
                "custom": doc_status.get("custom_docs", 0),
                "list": doc_status.get("doc_list", [])
            },
            "recent_entries": recent_entries,
        }

        # Add pagination info for recent_entries
        from utils.estimator import PaginationCalculator
        calc = PaginationCalculator()
        page = 1  # Default to page 1
        page_size = 5
        pagination_info = calc.create_pagination_info(page, page_size, len(recent_entries))
        payload["pagination"] = pagination_info.to_dict() if hasattr(pagination_info, 'to_dict') else pagination_info

        return _GET_PROJECT_HELPER.apply_context_payload(payload, context)

    # Fallback for unknown formats
    payload = {
        "ok": True,
        "project": response,
        "recent_projects": recent_projects,
    }
    return _GET_PROJECT_HELPER.apply_context_payload(payload, context)
