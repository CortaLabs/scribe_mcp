# -*- coding: utf-8 -*-
"""
Configurable reminder engine for Scribe MCP - Backwards Compatibility Shim.

This module provides a drop-in replacement for the original reminders.py,
routing all calls to the new localization-based reminder system.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Import the new reminder engine
from scribe_mcp.utils.reminder_validator import validate_and_load_engine
from scribe_mcp.utils.reminder_engine import ReminderEngine, ReminderContext as NewReminderContext
from scribe_mcp.utils.reminder_engine import ReminderInstance
from scribe_mcp.readiness import build_readiness_summary, collect_managed_doc_quality_state

logger = logging.getLogger(__name__)

# Global engine instance (singleton pattern)
_reminder_engine: Optional[ReminderEngine] = None
_DOC_STATUS_CACHE: Dict[str, Tuple[int, int, str]] = {}
_PHASE_CACHE: Dict[str, Tuple[int, int, Optional[str]]] = {}
_LOG_STATS_CACHE: Dict[str, Tuple[int, int, float, Optional[datetime], int]] = {}
_REMINDER_LOG_CACHE_SECONDS = max(1.0, float(os.environ.get("SCRIBE_REMINDER_LOG_CACHE_SECONDS", "3")))
_IN_PROGRESS_PHASE_RE = re.compile(r"##\s+Phase\s+(.+?)\s*\(In Progress\)")


def _resolve_reminder_storage() -> Optional[Any]:
    """Resolve storage backend for reminder persistence."""
    try:
        from scribe_mcp import server as server_module

        backend = getattr(server_module, "storage_backend", None)
        if backend is not None:
            return backend
    except Exception:
        pass

    try:
        from scribe_mcp.storage import create_storage_backend

        backend = create_storage_backend()
        if backend is not None:
            return backend
    except Exception:
        pass

    try:
        from scribe_mcp.config.mode_detection import OperatingMode, resolve_configured_mode
        from scribe_mcp.config.settings import settings

        mode = resolve_configured_mode(settings)
        backend_name = str(getattr(settings, "storage_backend", "")).strip().lower()
        if mode != OperatingMode.STANDALONE or backend_name != "sqlite":
            return None
    except Exception:
        return None

    try:
        from scribe_mcp.config.paths import default_db_path
        from scribe_mcp.storage.sqlite import SQLiteStorage

        return SQLiteStorage(str(default_db_path()))
    except Exception:
        return None

def _get_engine() -> ReminderEngine:
    """Get or create the reminder engine instance with DB storage backend."""
    global _reminder_engine
    if _reminder_engine is None:
        storage = _resolve_reminder_storage()
        _reminder_engine = validate_and_load_engine()
        _reminder_engine.storage = storage
    return _reminder_engine


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse legacy or ISO timestamps into timezone-aware UTC datetimes."""
    if not value:
        return None
    try:
        from scribe_mcp.utils.time import parse_utc

        parsed = parse_utc(value)
        if parsed:
            return parsed
    except Exception:
        pass

    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _file_signature(path: Path) -> Optional[Tuple[int, int]]:
    try:
        stat = path.stat()
        return int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return None


def _scan_progress_log_sync(log_path: Path) -> Tuple[int, Optional[str]]:
    """Single-pass progress log scan: count entries + extract latest timestamp."""
    if not log_path.exists():
        return 0, None

    from scribe_mcp.utils.logs import parse_log_line

    total_entries = 0
    last_ts_str: Optional[str] = None
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                parsed = parse_log_line(raw_line.rstrip("\n"))
                if not parsed:
                    continue
                total_entries += 1
                ts_str = parsed.get("ts")
                if ts_str:
                    last_ts_str = ts_str
    except OSError:
        return 0, None

    return total_entries, last_ts_str


async def _read_progress_log_stats(
    project_name: Optional[str],
    log_path: Path,
) -> Tuple[int, Optional[datetime], Optional[float]]:
    """
    Fast path: use DB-backed project metrics.
    Fallback: single-pass file scan with mtime/size cache.
    """
    # DB-first lookup keeps reminder generation fast under large log files.
    if project_name:
        try:
            engine = _get_engine()
            storage = getattr(engine, "storage", None)
            if storage and hasattr(storage, "fetch_project"):
                project_record = await storage.fetch_project(project_name)
                if project_record:
                    try:
                        total_entries = await storage.count_entries(
                            project_record,
                            filters={"log_type": ["progress"]},
                        )
                    except TypeError:
                        total_entries = await storage.count_entries(project_record)

                    last_rows = await storage.fetch_recent_entries(
                        project=project_record,
                        limit=1,
                        filters={"log_type": ["progress"]},
                    )
                    last_ts = _parse_timestamp(
                        (last_rows[0].get("ts_iso") or last_rows[0].get("ts")) if last_rows else None
                    )
                    minutes_since_log = None
                    if last_ts:
                        from scribe_mcp.utils.time import utcnow

                        minutes_since_log = (utcnow() - last_ts).total_seconds() / 60
                    return int(total_entries or 0), last_ts, minutes_since_log
        except Exception:
            # Fall through to file scan to preserve behavior under any storage issue.
            pass

    # File scan fallback with small cache window.
    signature = _file_signature(log_path)
    cache_key = str(log_path)
    now_mono = time.monotonic()
    if signature is not None:
        cached = _LOG_STATS_CACHE.get(cache_key)
        if cached:
            cached_mtime, cached_size, cached_at, cached_last_dt, cached_count = cached
            if (
                cached_mtime == signature[0]
                and cached_size == signature[1]
                and (now_mono - cached_at) <= _REMINDER_LOG_CACHE_SECONDS
            ):
                minutes_since = None
                if cached_last_dt:
                    from scribe_mcp.utils.time import utcnow

                    minutes_since = (utcnow() - cached_last_dt).total_seconds() / 60
                return cached_count, cached_last_dt, minutes_since

    total_entries, last_ts_str = await asyncio.to_thread(_scan_progress_log_sync, log_path)
    last_log_time = _parse_timestamp(last_ts_str)
    minutes_since_log = None
    if last_log_time:
        from scribe_mcp.utils.time import utcnow

        minutes_since_log = (utcnow() - last_log_time).total_seconds() / 60

    if signature is not None:
        _LOG_STATS_CACHE[cache_key] = (
            signature[0],
            signature[1],
            now_mono,
            last_log_time,
            total_entries,
        )

    return total_entries, last_log_time, minutes_since_log


async def _get_doc_status(path: Path) -> str:
    """Return missing/incomplete/complete with mtime/size-based cache."""
    signature = _file_signature(path)
    if signature is None:
        return "missing"

    cache_key = str(path)
    cached = _DOC_STATUS_CACHE.get(cache_key)
    if cached and cached[0] == signature[0] and cached[1] == signature[1]:
        return cached[2]

    try:
        content = await asyncio.to_thread(path.read_text, encoding="utf-8")
        if "{{" in content and "}}" in content:
            status = "incomplete"
        elif len(content.strip()) < 400:
            status = "incomplete"
        else:
            status = "complete"
    except Exception:
        status = "missing"

    _DOC_STATUS_CACHE[cache_key] = (signature[0], signature[1], status)
    return status


def _extract_current_phase_sync(phase_plan_path: Path) -> Optional[str]:
    """Extract in-progress phase with line-by-line scan to avoid full-file overhead."""
    try:
        with open(phase_plan_path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                match = _IN_PROGRESS_PHASE_RE.search(line)
                if match:
                    return match.group(1).strip()
    except OSError:
        return None
    return None


async def _get_current_phase(phase_plan_path: Optional[str]) -> Optional[str]:
    if not phase_plan_path:
        return None

    path = Path(phase_plan_path)
    signature = _file_signature(path)
    if signature is None:
        return None

    cache_key = str(path)
    cached = _PHASE_CACHE.get(cache_key)
    if cached and cached[0] == signature[0] and cached[1] == signature[1]:
        return cached[2]

    phase = await asyncio.to_thread(_extract_current_phase_sync, path)
    _PHASE_CACHE[cache_key] = (signature[0], signature[1], phase)
    return phase


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
    reminder_instances.extend(await _quality_state_reminders(engine, context))

    # Convert to the old format
    return engine.to_dict_list(reminder_instances)


async def _quality_state_reminders(engine: ReminderEngine, context: NewReminderContext) -> List[ReminderInstance]:
    readiness = context.variables.get("readiness_summary") if isinstance(context.variables, dict) else None
    if not isinstance(readiness, dict):
        return []

    reminders: List[ReminderInstance] = []
    default_cooldown = int(context.variables.get("quality_reminder_cooldown_minutes", 30) or 30)
    categories_cfg = context.variables.get("quality_reminder_categories") or {}

    def _cfg(name: str, fallback: str) -> str:
        if isinstance(categories_cfg, dict) and isinstance(categories_cfg.get(name), str):
            return str(categories_cfg.get(name))
        return fallback

    quality = readiness.get("managed_doc_quality") if isinstance(readiness.get("managed_doc_quality"), dict) else {}
    log_friction = readiness.get("log_friction") if isinstance(readiness.get("log_friction"), dict) else {}
    current_phase = str(readiness.get("current_phase") or "active phase")
    residue = int(quality.get("readiness_blocker_count", 0) or 0)
    mismatch = int(quality.get("frontmatter_mismatch_count", 0) or 0)
    stale = int(quality.get("stale_research_index_count", 0) or 0)
    runtime_budget_status = str((log_friction.get("runtime_efficiency") or {}).get("budget_status") or "")
    if not runtime_budget_status and isinstance(context.variables, dict):
        runtime_efficiency = context.variables.get("runtime_efficiency")
        if isinstance(runtime_efficiency, dict):
            runtime_budget_status = str(runtime_efficiency.get("budget_status") or "")

    suppressed = set(context.variables.get("quality_reminder_suppress_codes") or [])

    if residue > 0 and "SCF_READINESS_BLOCKERS" not in suppressed:
        reminders.append(
            ReminderInstance(
                key="quality.scaffold_residue",
                level="warning",
                emoji="⚠️",
                message=f"{current_phase}: {residue} readiness blocker(s) remain. Clear SCF_* blockers in active docs before claiming done.",
                category=_cfg("scaffold_residue", "scaffold_residue"),
                variables={"project_root": context.project_root or "", "agent_id": context.agent_id or "", "tool_name": context.tool_name, "session_id": context.session_id or ""},
                cooldown_minutes=default_cooldown,
            )
        )
    if mismatch > 0 and "SCF_FRONTMATTER_MISMATCH" not in suppressed:
        reminders.append(
            ReminderInstance(
                key="quality.frontmatter_mismatch",
                level="warning",
                emoji="🧭",
                message=f"{current_phase}: frontmatter/body readiness mismatch ({mismatch}). Re-run quality_check, then align frontmatter status with body state.",
                category=_cfg("frontmatter_mismatch", "frontmatter_mismatch"),
                variables={"project_root": context.project_root or "", "agent_id": context.agent_id or "", "tool_name": context.tool_name, "session_id": context.session_id or ""},
                cooldown_minutes=default_cooldown,
            )
        )
    if stale > 0 and "SCF_INDEX_HYGIENE" not in suppressed:
        reminders.append(
            ReminderInstance(
                key="quality.stale_research_index",
                level="info",
                emoji="📚",
                message=f"{current_phase}: research index hygiene signal ({stale}) in the active lane. Reconcile canonical research paths and refresh index references for this phase.",
                category=_cfg("stale_research_index", "stale_research_index"),
                variables={"project_root": context.project_root or "", "agent_id": context.agent_id or "", "tool_name": context.tool_name, "session_id": context.session_id or ""},
                cooldown_minutes=default_cooldown,
            )
        )
    if runtime_budget_status in {"near_budget", "over_budget"} and "RUNTIME_EFFICIENCY_BUDGET" not in suppressed:
        reminders.append(
            ReminderInstance(
                key="quality.runtime_efficiency_budget",
                level="warning" if runtime_budget_status == "over_budget" else "info",
                emoji="⏱️",
                message=f"Runtime-efficiency budget status is `{runtime_budget_status}` (runtime-efficiency-budget.v1). Use project_health/log_intelligence timing guidance before widening scope.",
                category=_cfg("runtime_efficiency_budget", "runtime_efficiency_budget"),
                variables={"project_root": context.project_root or "", "agent_id": context.agent_id or "", "tool_name": context.tool_name, "session_id": context.session_id or ""},
                cooldown_minutes=default_cooldown,
            )
        )

    emitted: List[ReminderInstance] = []
    for reminder in reminders:
        if await engine._should_show_reminder_async(reminder, context):
            reminder_hash = engine._get_reminder_hash(reminder.key, reminder.variables)
            engine.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc)
            emitted.append(reminder)
    return emitted


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

    # Read log information (DB-first with cached file fallback).
    total_entries, last_log_time, minutes_since_log = await _read_progress_log_stats(
        project_name=project_name,
        log_path=log_path,
    )

    # Extract docs information
    docs_status = {}
    docs_changed = []

    try:
        if state:
            # Try to get docs information from state.
            projects = getattr(state, "projects", None)
            if isinstance(projects, dict) and project_name in projects:
                state_project = projects.get(project_name) or {}
                if isinstance(state_project, dict):
                    docs_status = state_project.get("docs_status", {})
                    docs_changed = state_project.get("docs_changed", [])

        # Fall back to checking docs directly
        if not docs_status and "docs" in project:
            docs = project["docs"] or {}
            for doc_type, doc_path in docs.items():
                if doc_type == "progress_log":
                    continue
                path = Path(doc_path)
                docs_status[doc_type] = await _get_doc_status(path)

    except Exception:
        # If we can't check docs, use empty status
        pass

    # Get current phase (cached by file signature).
    current_phase = await _get_current_phase(project.get("docs", {}).get("phase_plan"))

    quality_state = await asyncio.to_thread(collect_managed_doc_quality_state, project)
    log_signals = list((variables or {}).get("log_signals") or []) if isinstance(variables, dict) else []
    runtime_efficiency = (variables or {}).get("runtime_efficiency") if isinstance(variables, dict) else None
    readiness_summary = build_readiness_summary(
        current_phase=current_phase,
        managed_doc_quality=quality_state,
        log_signals=log_signals,
    ).to_dict()
    if isinstance(runtime_efficiency, dict):
        readiness_summary.setdefault("log_friction", {}).setdefault("runtime_efficiency", runtime_efficiency)

    reminder_cfg = ((project.get("defaults") or {}).get("reminder") or {}) if isinstance(project, dict) else {}
    try:
        from scribe_mcp.config.settings import settings

        global_reminder_cfg = settings.reminder_defaults if isinstance(settings.reminder_defaults, dict) else {}
    except Exception:
        global_reminder_cfg = {}

    combined_cfg = {**global_reminder_cfg, **reminder_cfg}

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
        variables={
            **(variables or {}),
            "managed_doc_quality": quality_state,
            "readiness_summary": readiness_summary,
            "quality_reminder_cooldown_minutes": int(combined_cfg.get("quality_cooldown_minutes", 30) or 30),
            "quality_reminder_categories": {
                "scaffold_residue": str(combined_cfg.get("scaffold_residue_category", "scaffold_residue")),
                "frontmatter_mismatch": str(combined_cfg.get("frontmatter_mismatch_category", "frontmatter_mismatch")),
                "stale_research_index": str(combined_cfg.get("stale_research_index_category", "stale_research_index")),
                "runtime_efficiency_budget": str(combined_cfg.get("runtime_efficiency_budget_category", "runtime_efficiency_budget")),
            },
            "quality_reminder_suppress_codes": [str(code) for code in (combined_cfg.get("suppress_warning_codes") or []) if str(code).strip()],
        },
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


async def get_reminder_history(
    *,
    project_root: Optional[str] = None,
    agent_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch reminder history entries via the active reminder engine."""
    engine = _get_engine()
    return await engine.get_reminder_history(
        project_root=project_root,
        agent_id=agent_id,
        category=category,
        limit=limit,
    )


async def clear_reminder_history(
    *,
    project_root: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> int:
    """Clear reminder history entries via the active reminder engine."""
    engine = _get_engine()
    return await engine.reset_history(project_root=project_root, agent_id=agent_id)


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
