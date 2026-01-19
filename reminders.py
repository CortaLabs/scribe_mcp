# -*- coding: utf-8 -*-
"""
Configurable reminder engine for Scribe MCP - Backwards Compatibility Shim.

This module provides a drop-in replacement for the original reminders.py,
routing all calls to the new localization-based reminder system.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Import the new reminder engine
from scribe_mcp.utils.reminder_validator import validate_and_load_engine
from scribe_mcp.utils.reminder_engine import ReminderEngine, ReminderContext as NewReminderContext

# Global engine instance (singleton pattern)
_reminder_engine: Optional[ReminderEngine] = None

def _get_engine() -> ReminderEngine:
    """Get or create the reminder engine instance with DB storage backend."""
    global _reminder_engine
    if _reminder_engine is None:
        from scribe_mcp.storage.sqlite import SQLiteStorage
        from scribe_mcp.config.settings import settings

        # Create storage backend for DB-based cooldown tracking
        db_path = settings.project_root / ".scribe" / "data" / "scribe.db"
        storage = SQLiteStorage(str(db_path))

        # Create engine and inject storage
        _reminder_engine = validate_and_load_engine()
        _reminder_engine.storage = storage
    return _reminder_engine


def reset_reminder_cooldowns(*, project_root: str, agent_id: Optional[str] = None) -> int:
    """Clear reminder cooldown timestamps for a repo/project (and optionally agent)."""
    engine = _get_engine()
    return engine.reset_cooldowns(project_root=project_root, agent_id=agent_id)


# ---------------------------------------------------------------------------
# Legacy Compatibility API
# ---------------------------------------------------------------------------

async def get_reminders(
    project: Dict[str, Any],
    *,
    tool_name: str,
    state: Optional[object] = None,
    agent_id: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
    operation_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Legacy compatibility wrapper for the original get_reminders function.

    This maintains the exact same interface as the original while using
    the new reminder engine under the hood.

    Args:
        operation_status: Status of the tool operation ("success", "failure", or None for neutral)
                         Used to determine reminder priority (failures bypass cooldowns)
    """
    if not project:
        return []

    # Build the new reminder context from the old format
    context = await _build_legacy_context(
        project,
        tool_name,
        state,
        agent_id=agent_id,
        variables=variables,
        operation_status=operation_status,
    )

    # Use the new engine
    engine = _get_engine()
    reminder_instances = await engine.generate_reminders(context)

    # Convert to the old format
    return engine.to_dict_list(reminder_instances)


# ---------------------------------------------------------------------------
# Context Building Functions
# ---------------------------------------------------------------------------

async def _build_legacy_context(
    project: Dict[str, Any],
    tool_name: str,
    state: Optional[object],
    *,
    agent_id: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
    operation_status: Optional[str] = None,
) -> NewReminderContext:
    """Convert legacy project/state format to new ReminderContext.

    Args:
        operation_status: Status of the tool operation ("success", "failure", or None)
    """

    # Extract project information
    project_name = project.get("name")
    project_root = project.get("root")
    log_path = Path(project.get("progress_log", ""))

    # Read log information (similar to original _build_context)
    last_log_time: Optional[datetime] = None
    total_entries = 0
    minutes_since_log: Optional[float] = None

    try:
        from scribe_mcp.utils.logs import read_all_lines, parse_log_line
        lines = await read_all_lines(log_path)

        for line in lines:
            if parse_log_line(line):
                total_entries += 1

        for line in reversed(lines):
            parsed = parse_log_line(line)
            if not parsed:
                continue
            ts_str = parsed.get("ts")
            if ts_str:
                try:
                    from scribe_mcp.utils.time import parse_utc, utcnow
                    last_log_time = parse_utc(ts_str)
                    delta = utcnow() - last_log_time
                    minutes_since_log = delta.total_seconds() / 60
                    break
                except Exception:
                    pass
    except Exception:
        # If we can't read logs, use defaults
        pass

    # Extract docs information
    docs_status = {}
    docs_changed = []

    try:
        if state:
            # Try to get docs information from state
            if hasattr(state, 'projects') and project_name in state.projects:
                state_project = state.projects[project_name]
                docs_status = state_project.get("docs_status", {})
                docs_changed = state_project.get("docs_changed", [])

        # Fall back to checking docs directly
        if not docs_status and "docs" in project:
            docs = project["docs"] or {}
            for doc_type, doc_path in docs.items():
                if doc_type == "progress_log":
                    continue
                path = Path(doc_path)
                if not path.exists():
                    docs_status[doc_type] = "missing"
                else:
                    try:
                        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
                        # Simple completion check
                        if "{{" in content and "}}" in content:
                            docs_status[doc_type] = "incomplete"
                        elif len(content.strip()) < 400:
                            docs_status[doc_type] = "incomplete"
                        else:
                            docs_status[doc_type] = "complete"
                    except Exception:
                        docs_status[doc_type] = "missing"

    except Exception:
        # If we can't check docs, use empty status
        pass

    # Get current phase
    current_phase = None
    try:
        phase_plan_path = project.get("docs", {}).get("phase_plan")
        if phase_plan_path:
            phase_path = Path(phase_plan_path)
            if phase_path.exists():
                import re
                content = await asyncio.to_thread(phase_path.read_text, encoding="utf-8")
                match = re.search(r"##\s+Phase\s+(.+?)\s*\(In Progress\)", content)
                if match:
                    current_phase = match.group(1).strip()
    except Exception:
        pass

    # Get session age information
    session_age_minutes = None
    try:
        if state and hasattr(state, 'session_started_at') and state.session_started_at:
            from scribe_mcp.utils.time import parse_utc, utcnow
            start_dt = parse_utc(state.session_started_at)
            if start_dt:
                age_delta = utcnow() - start_dt
                session_age_minutes = age_delta.total_seconds() / 60
    except Exception:
        pass

    # Extract session_id from state (separate try block for fault isolation)
    session_id = None
    try:
        if state and hasattr(state, 'session_id'):
            session_id = state.session_id
    except Exception:
        pass

    return NewReminderContext(
        tool_name=tool_name,
        project_name=project_name,
        project_root=str(project_root) if project_root else None,
        agent_id=agent_id,
        session_id=session_id,
        total_entries=total_entries,
        minutes_since_log=minutes_since_log,
        last_log_time=last_log_time,
        docs_status=docs_status,
        docs_changed=docs_changed,
        current_phase=current_phase,
        session_age_minutes=session_age_minutes,
        variables=variables or {},
        operation_status=operation_status,
    )


# ---------------------------------------------------------------------------
# Legacy Export API (for direct import compatibility)
# ---------------------------------------------------------------------------

# Export the old classes and functions that might be imported directly
DEFAULT_SEVERITY = {"info": 3, "warning": 6, "urgent": 9}
DEFAULT_SUPPRESS_PHASE_TOOLS: Sequence[str] = ("append_entry", "generate_doc_templates")

# Legacy dataclasses for compatibility
from dataclasses import dataclass

@dataclass
class ReminderConfig:
    """Legacy compatibility dataclass."""
    tone: str
    severity_weights: Dict[str, int]
    log_warning_minutes: int
    log_urgent_minutes: int
    doc_stale_days: int
    min_doc_length: int
    warmup_minutes: int
    idle_reset_minutes: int
    suppress_phase_on_tools: Sequence[str]

@dataclass
class Reminder:
    """Legacy compatibility dataclass."""
    level: str
    score: int
    message: str
    emoji: str = "ℹ️"
    context: Optional[str] = None
    category: str = "general"

@dataclass
class ReminderContext:
    """Legacy compatibility dataclass."""
    config: ReminderConfig
    project_name: str
    last_log_time: Optional[datetime]
    minutes_since_log: Optional[float]
    docs_status: Dict[str, str]
    doc_hashes: Dict[str, str]
    doc_changes: List[str]
    doc_paths: Dict[str, Path]
    current_phase: Optional[str]
    total_entries: int
    recent_actions: List[str]
    session_age_minutes: Optional[float]
    is_new_session: bool


# ---------------------------------------------------------------------------
# Configuration and Settings (Legacy Compatibility)
# ---------------------------------------------------------------------------

def _build_config(project: Dict[str, Any]) -> ReminderConfig:
    """Legacy compatibility wrapper for building config."""
    # This is kept for backward compatibility but the new system handles config internally
    try:
        from scribe_mcp.config.settings import settings

        global_defaults = settings.reminder_defaults or {}
        project_defaults = (project.get("defaults", {}) or {}).get("reminder", {})

        severity = dict(DEFAULT_SEVERITY)
        severity.update(global_defaults.get("severity_weights", {}))
        severity.update(project_defaults.get("severity_weights", {}))

        tone = project_defaults.get("tone") or global_defaults.get("tone") or "neutral"

        default_warning = global_defaults.get("log_warning_minutes", settings.reminder_warmup_minutes + 5)
        log_warning = int(project_defaults.get("log_warning_minutes", default_warning))
        default_urgent = global_defaults.get("log_urgent_minutes", log_warning + 10)
        log_urgent = int(project_defaults.get("log_urgent_minutes", default_urgent))
        doc_stale = int(project_defaults.get("doc_stale_days", global_defaults.get("doc_stale_days", 7)))
        min_length = int(project_defaults.get("min_doc_length", global_defaults.get("min_doc_length", 400)))
        warmup = int(project_defaults.get("warmup_minutes", global_defaults.get("warmup_minutes", settings.reminder_warmup_minutes)))
        idle = int(project_defaults.get("idle_reset_minutes", global_defaults.get("idle_reset_minutes", settings.reminder_idle_minutes)))

        suppress_tools = list(DEFAULT_SUPPRESS_PHASE_TOOLS)
        suppress_tools.extend(global_defaults.get("suppress_phase_on_tools", []))
        suppress_tools.extend(project_defaults.get("suppress_phase_on_tools", []))

        return ReminderConfig(
            tone=str(tone),
            severity_weights={k: int(v) for k, v in severity.items()},
            log_warning_minutes=log_warning,
            log_urgent_minutes=log_urgent,
            doc_stale_days=doc_stale,
            min_doc_length=min_length,
            warmup_minutes=warmup,
            idle_reset_minutes=idle,
            suppress_phase_on_tools=tuple(dict.fromkeys(t.strip() for t in suppress_tools if t)),
        )
    except Exception:
        # Return default config if something goes wrong
        return ReminderConfig(
            tone="neutral",
            severity_weights=DEFAULT_SEVERITY,
            log_warning_minutes=20,
            log_urgent_minutes=60,
            doc_stale_days=7,
            min_doc_length=400,
            warmup_minutes=5,
            idle_reset_minutes=45,
            suppress_phase_on_tools=DEFAULT_SUPPRESS_PHASE_TOOLS,
        )


# ---------------------------------------------------------------------------
# Internal Helper Functions (Legacy Compatibility)
# ---------------------------------------------------------------------------

def _apply_tone(tone: str, message: str, level: str) -> str:
    """Legacy compatibility wrapper for tone application."""
    # The new system handles tone internally, so just return the message
    return message


def _make_reminder(
    level: str,
    emoji: str,
    message: str,
    context: Optional[str] = None,
    category: str = "general",
    ctx: ReminderContext | None = None,
) -> Reminder:
    """Legacy compatibility wrapper for creating reminders."""
    severity = DEFAULT_SEVERITY.get(level, 3)
    return Reminder(
        level=level,
        score=severity,
        message=message,
        emoji=emoji,
        context=context,
        category=category,
    )


# ---------------------------------------------------------------------------
# Engine Access for Advanced Usage
# ---------------------------------------------------------------------------

def get_reminder_engine() -> ReminderEngine:
    """
    Get access to the underlying reminder engine for advanced usage.

    This allows advanced users to access the new reminder system's features
    while maintaining backward compatibility.

    Example:
        engine = get_reminder_engine()
        # Use new features like language switching
        engine.language = "es-ES"
    """
    return _get_engine()


def reload_reminders() -> None:
    """
    Force reload of reminder configuration.

    Useful for development or when configuration files are updated.
    """
    global _reminder_engine
    _reminder_engine = None
    _get_engine()


# ---------------------------------------------------------------------------
# Module Information
# ---------------------------------------------------------------------------

__version__ = "2.0.0"
__description__ = "Scribe MCP Reminder Engine - Backwards Compatibility Shim"

# Initialize engine on import for early error detection
try:
    _get_engine()
except Exception as e:
    print(f"Warning: Failed to initialize reminder engine: {e}")
    print("The system will use fallback reminders if needed.")
