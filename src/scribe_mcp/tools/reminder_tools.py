"""Reminder query/configuration/reset MCP tools."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from scribe_mcp import reminders
from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tool_contracts import destructive_local_tool, read_only_local_tool, stateful_local_tool
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import ProjectResolutionError
from scribe_mcp.utils.response import default_formatter


class _ReminderToolHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module


_HELPER = _ReminderToolHelper()


def _normalize_project(value: Optional[str]) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _normalize_category(value: Optional[str]) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return cleaned or None
    return None


def _normalize_categories(value: Optional[Any]) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        raw_items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        raw_items = [str(part).strip() for part in value]
    else:
        raw_items = [str(value).strip()]

    categories: List[str] = []
    seen = set()
    for item in raw_items:
        lowered = item.lower()
        if lowered and lowered not in seen:
            categories.append(lowered)
            seen.add(lowered)
    return categories


def _normalize_limit(value: int) -> int:
    try:
        return max(1, min(int(value), 200))
    except (TypeError, ValueError):
        return 20


def _filter_active_reminders(
    reminders_payload: List[Dict[str, Any]],
    category: Optional[str],
) -> List[Dict[str, Any]]:
    if not category:
        return reminders_payload
    target = category.lower()
    filtered: List[Dict[str, Any]] = []
    for item in reminders_payload:
        item_category = str(item.get("category", "")).strip().lower()
        if item_category == target:
            filtered.append(item)
    return filtered


def _format_query_readable(data: Dict[str, Any]) -> str:
    history = data.get("history", [])
    active = data.get("active_reminders", [])
    filter_category = data.get("filters", {}).get("category", "all")
    lines = [
        f"REMINDERS | project={data.get('project_name', 'unknown')}",
        f"Filter: category={filter_category}, limit={data.get('filters', {}).get('limit', 20)}",
        f"History rows: {len(history)}",
        f"Active reminders: {len(active)}",
    ]

    if history:
        lines.append("")
        lines.append("Recent history:")
        for row in history[:5]:
            shown_at = row.get("shown_at", "unknown-time")
            reminder_key = row.get("reminder_key") or "<unknown>"
            operation_status = row.get("operation_status", "neutral")
            lines.append(f"- {shown_at} | {reminder_key} | status={operation_status}")

    if active:
        lines.append("")
        lines.append("Active reminders:")
        for item in active[:5]:
            emoji = item.get("emoji", "ℹ️")
            message = item.get("message", "")
            category = item.get("category", "general")
            lines.append(f"- {emoji} [{category}] {message}")

    return "\n".join(lines)


def _format_configure_readable(data: Dict[str, Any]) -> str:
    settings = data.get("reminder_settings", {})
    changed = data.get("updated_fields", [])
    lines = [
        f"REMINDER CONFIG UPDATED | project={data.get('project_name', 'unknown')}",
        f"Updated fields: {', '.join(changed) if changed else 'none'}",
        "",
        f"enabled={settings.get('enabled')}",
        f"cooldown_minutes={settings.get('cooldown_minutes')}",
        f"tone={settings.get('tone')}",
        f"categories={settings.get('categories')}",
    ]
    return "\n".join(lines)


def _format_reset_readable(data: Dict[str, Any]) -> str:
    lines = [
        f"REMINDERS RESET | project={data.get('project_name', 'unknown')}",
        f"cooldowns_cleared={data.get('cooldowns_cleared', 0)}",
        f"history_cleared={data.get('history_cleared', 0)}",
    ]
    return "\n".join(lines)


@app.tool(**read_only_local_tool(title="Query Reminders", tags=("reminders", "read-only")))
async def query_reminders(
    agent: str,
    project: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
    format: str = "readable",
) -> Dict[str, Any]:
    """Query reminder history and currently active reminders for a project."""
    state_snapshot = await server_module.state_manager.record_tool("query_reminders")
    explicit_project = _normalize_project(project)
    normalized_category = _normalize_category(category)
    normalized_limit = _normalize_limit(limit)

    try:
        context = await _HELPER.prepare_context(
            tool_name="query_reminders",
            agent_id=agent,
            explicit_project=explicit_project,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        return _HELPER.translate_project_error(exc)

    project_data = context.project or {}
    project_root = project_data.get("root")
    project_name = project_data.get("name")
    if not project_root:
        return _HELPER.error_response(
            "Project root is required to query reminder history.",
            context=context,
        )

    history = await reminders.get_reminder_history(
        project_root=str(project_root),
        agent_id=agent,
        category=normalized_category,
        limit=normalized_limit,
    )
    active_reminders = _filter_active_reminders(list(context.reminders), normalized_category)

    response: Dict[str, Any] = {
        "ok": True,
        "project_name": project_name,
        "history": history,
        "active_reminders": active_reminders,
        "filters": {
            "category": normalized_category or "all",
            "limit": normalized_limit,
        },
    }
    response = _HELPER.apply_context_payload(response, context)

    if format == "compact":
        return {
            "ok": True,
            "project_name": project_name,
            "history_count": len(history),
            "active_count": len(active_reminders),
            "active_reminders": active_reminders,
            "reminder_guidance": response.get("reminder_guidance", []),
            "category": normalized_category or "all",
        }
    if format == "readable":
        response["readable_content"] = _format_query_readable(response)
        return await default_formatter.finalize_tool_response(
            data=response,
            format="readable",
            tool_name="query_reminders",
        )
    return response


@app.tool(**stateful_local_tool(title="Configure Reminders", tags=("reminders", "write")))
async def configure_reminders(
    agent: str,
    project: Optional[str] = None,
    enabled: Optional[bool] = None,
    cooldown_minutes: Optional[int] = None,
    categories: Optional[Any] = None,
    tone: Optional[str] = None,
    format: str = "readable",
) -> Dict[str, Any]:
    """Configure reminder behavior for a project in active state metadata."""
    state_snapshot = await server_module.state_manager.record_tool("configure_reminders")
    explicit_project = _normalize_project(project)

    try:
        context = await _HELPER.prepare_context(
            tool_name="configure_reminders",
            agent_id=agent,
            explicit_project=explicit_project,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        return _HELPER.translate_project_error(exc)

    if (
        enabled is None
        and cooldown_minutes is None
        and categories is None
        and tone is None
    ):
        return _HELPER.error_response(
            "No reminder settings were provided.",
            suggestion="Pass one of enabled/cooldown_minutes/categories/tone.",
            context=context,
        )

    project_data = dict(context.project or {})
    project_name = project_data.get("name")
    if not project_name:
        return _HELPER.error_response("Project name is required.", context=context)

    defaults = project_data.get("defaults")
    if not isinstance(defaults, dict):
        defaults = {}
    reminder_defaults = defaults.get("reminder")
    if not isinstance(reminder_defaults, dict):
        reminder_defaults = {}
    updated = dict(reminder_defaults)

    changed_fields: List[str] = []
    if enabled is not None:
        updated["enabled"] = bool(enabled)
        changed_fields.append("enabled")
    if cooldown_minutes is not None:
        try:
            updated["cooldown_minutes"] = max(0, int(cooldown_minutes))
        except (TypeError, ValueError):
            updated["cooldown_minutes"] = 0
        changed_fields.append("cooldown_minutes")
    if categories is not None:
        updated["categories"] = _normalize_categories(categories) or []
        changed_fields.append("categories")
    if tone is not None:
        normalized_tone = str(tone).strip().lower()
        updated["tone"] = normalized_tone or "neutral"
        changed_fields.append("tone")

    merged_defaults = dict(defaults)
    merged_defaults["reminder"] = updated

    await server_module.state_manager.update_project_metadata(
        project_name,
        {"defaults": merged_defaults},
    )

    response: Dict[str, Any] = {
        "ok": True,
        "project_name": project_name,
        "updated_fields": changed_fields,
        "reminder_settings": updated,
    }
    response = _HELPER.apply_context_payload(response, context)

    if format == "compact":
        return {
            "ok": True,
            "project_name": project_name,
            "updated": changed_fields,
        }
    if format == "readable":
        response["readable_content"] = _format_configure_readable(response)
        return await default_formatter.finalize_tool_response(
            data=response,
            format="readable",
            tool_name="configure_reminders",
        )
    return response


@app.tool(**destructive_local_tool(title="Reset Reminders", tags=("reminders", "admin", "destructive")))
async def reset_reminders(
    agent: str,
    project: Optional[str] = None,
    reset_cooldowns: bool = True,
    reset_history: bool = False,
    format: str = "readable",
) -> Dict[str, Any]:
    """Reset reminder cooldowns and/or reminder history for a project."""
    state_snapshot = await server_module.state_manager.record_tool("reset_reminders")
    explicit_project = _normalize_project(project)

    try:
        context = await _HELPER.prepare_context(
            tool_name="reset_reminders",
            agent_id=agent,
            explicit_project=explicit_project,
            require_project=True,
            state_snapshot=state_snapshot,
        )
    except ProjectResolutionError as exc:
        return _HELPER.translate_project_error(exc)

    if not reset_cooldowns and not reset_history:
        return _HELPER.error_response(
            "Nothing to reset.",
            suggestion="Set reset_cooldowns and/or reset_history to true.",
            context=context,
        )

    project_data = context.project or {}
    project_root = project_data.get("root")
    project_name = project_data.get("name")
    if not project_root:
        return _HELPER.error_response(
            "Project root is required to reset reminders.",
            context=context,
        )

    cooldowns_cleared = 0
    history_cleared = 0

    if reset_cooldowns:
        cooldowns_cleared = reminders.reset_reminder_cooldowns(
            project_root=str(project_root),
            agent_id=agent,
        )
    if reset_history:
        history_cleared = await reminders.clear_reminder_history(
            project_root=str(project_root),
            agent_id=agent,
        )

    response: Dict[str, Any] = {
        "ok": True,
        "project_name": project_name,
        "cooldowns_cleared": cooldowns_cleared,
        "history_cleared": history_cleared,
    }
    response = _HELPER.apply_context_payload(response, context)

    if format == "compact":
        return {
            "ok": True,
            "project_name": project_name,
            "cooldowns_cleared": cooldowns_cleared,
            "history_cleared": history_cleared,
        }
    if format == "readable":
        response["readable_content"] = _format_reset_readable(response)
        return await default_formatter.finalize_tool_response(
            data=response,
            format="readable",
            tool_name="reset_reminders",
        )
    return response
