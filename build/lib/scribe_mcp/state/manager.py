"""Persistence of lightweight state for the MCP server."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.config.settings import settings
from scribe_mcp.utils.time import parse_utc, utcnow
from scribe_mcp.utils.slug import normalize_project_input


TOOL_HISTORY_LIMIT = 10


@dataclass
class State:
    current_project: Optional[str]
    projects: Dict[str, Dict[str, Any]]
    recent_projects: List[str]
    session_projects: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    session_modes: Dict[str, str] = field(default_factory=dict)
    recent_tools: List[Dict[str, str]] = field(default_factory=list)
    last_activity_at: Optional[str] = None
    session_started_at: Optional[str] = None
    version: int = 0
    last_updated_by: Optional[str] = None
    operation_timestamp: Optional[str] = None
    agent_state: Dict[str, Any] = field(default_factory=dict)

    def get_project(self, name: Optional[str]) -> Optional[Dict[str, Any]]:
        if not name:
            return None
        # Try exact match first
        if name in self.projects:
            return self.projects[name]

        # Try canonical match (flexible lookup for existing projects)
        canonical = normalize_project_input(name)
        if canonical and canonical != name and canonical in self.projects:
            return self.projects[canonical]

        return None

    def get_session_project(self, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None
        return self.session_projects.get(session_id)

    def get_session_mode(self, session_id: Optional[str]) -> Optional[str]:
        if not session_id:
            return None
        return self.session_modes.get(session_id)

    def with_project(self, name: Optional[str], data: Optional[Dict[str, Any]]) -> "State":
        projects = dict(self.projects)
        if name and data:
            projects[name] = data
        recent = list(self.recent_projects)
        if name:
            recent = [name] + [item for item in recent if item != name]
            limit = settings.recent_projects_limit
            recent = recent[:limit]
        return State(
            current_project=name,
            projects=projects,
            recent_projects=recent,
            session_projects=dict(self.session_projects),
            session_modes=dict(self.session_modes),
            recent_tools=list(self.recent_tools),
            last_activity_at=self.last_activity_at,
            session_started_at=self.session_started_at,
            version=self.version,
            last_updated_by=self.last_updated_by,
            operation_timestamp=self.operation_timestamp,
            agent_state=self.agent_state,
        )


class StateManager:
    """Load and persist the server's state file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path or settings.default_state_path)
        self._lock = asyncio.Lock()
        self._temp_suffix = ".tmp"

    async def load(self) -> State:
        """Read state from disk or return defaults."""
        async with self._lock:
            data = await asyncio.to_thread(self._read_json)
            return State(
                current_project=data.get("current_project"),
                projects=data.get("projects", {}),
                recent_projects=data.get("recent_projects", []),
                session_projects=data.get("session_projects", {}),
                session_modes=data.get("session_modes", {}),
                recent_tools=_normalise_tool_history(data.get("recent_tools", [])),
                last_activity_at=data.get("last_activity_at"),
                session_started_at=data.get("session_started_at"),
                version=data.get("version", 0),
                last_updated_by=data.get("last_updated_by"),
                operation_timestamp=data.get("operation_timestamp"),
                agent_state=data.get("agent_state", {}),
            )

    async def persist(self, state: State) -> None:
        """Write the full state to disk."""
        await self._write_state(state)

    async def record_tool(self, tool_name: str) -> State:
        """Track the most recent tool invocations.

        DATABASE-ONLY MODE (v2.2.0+):
        - Writes to database only (agent_sessions table)
        - state.json writes REMOVED (migration complete)
        - Falls back to state.json for read-only access to old data
        """
        async with self._lock:
            # Load state.json for non-activity fields (current_project, etc.)
            data = await asyncio.to_thread(self._read_json)
            now_utc = utcnow()
            now = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
            timestamp_iso = now_utc.isoformat()

            # Write to database (primary storage for session activity)
            session_id = None
            try:
                from scribe_mcp import server as server_module
                backend = getattr(server_module, 'storage_backend', None)
                router_ctx = getattr(server_module, 'router_context_manager', None)

                if backend and router_ctx and hasattr(backend, 'update_session_activity'):
                    exec_context = router_ctx.get_current()
                    if exec_context:
                        # Prefer stable_session_id for agent_sessions table, fallback to session_id
                        session_id = exec_context.stable_session_id or exec_context.session_id

                        await backend.update_session_activity(
                            session_id=session_id,
                            tool_name=tool_name,
                            timestamp=timestamp_iso
                        )
            except Exception as e:
                # Log but don't fail - fall back to state.json read for this call
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to write session activity to database: {e}")

            # Get session activity (database-first, with state.json fallback)
            activity = await self._get_session_activity_with_fallback(session_id, data)

            # NO LONGER WRITING TO STATE.JSON - database is source of truth
            # state.json is now read-only for migration period

            return State(
                current_project=data.get("current_project"),
                projects=data.get("projects", {}),
                recent_projects=data.get("recent_projects", []),
                session_projects=data.get("session_projects", {}),
                session_modes=data.get("session_modes", {}),
                recent_tools=activity.get("recent_tools", []),
                last_activity_at=activity.get("last_activity_at", now),
                session_started_at=activity.get("session_started_at", now),
            )

    async def _get_session_activity_with_fallback(
        self,
        session_id: Optional[str],
        state_json_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get session activity from database with state.json fallback.

        Migration helper that tries database first, falls back to state.json
        for old sessions that haven't been migrated yet.

        Args:
            session_id: Session ID to look up (may be None if context unavailable)
            state_json_data: Loaded state.json data for fallback

        Returns:
            Dict with keys: recent_tools (list), last_activity_at (str), session_started_at (str)
        """
        # Try database first (primary source)
        if session_id:
            try:
                from scribe_mcp import server as server_module
                backend = getattr(server_module, 'storage_backend', None)

                if backend and hasattr(backend, 'get_session_activity'):
                    activity = await backend.get_session_activity(session_id)
                    if activity:
                        # Convert tool names to the format State expects
                        # Database stores simple tool names, State uses [{name, ts}] format
                        tool_names = activity.get("recent_tools", [])
                        recent_tools = [{"name": name, "ts": "migration"} for name in tool_names]

                        return {
                            "recent_tools": recent_tools,
                            "last_activity_at": activity.get("last_activity_at"),
                            "session_started_at": activity.get("session_started_at"),
                        }
            except Exception as e:
                # Log and fall through to state.json fallback
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Database session activity lookup failed, using state.json fallback: {e}")

        # Fallback to state.json (read-only) for old sessions
        recent_tools = _normalise_tool_history(state_json_data.get("recent_tools", []))
        return {
            "recent_tools": recent_tools,
            "last_activity_at": state_json_data.get("last_activity_at"),
            "session_started_at": state_json_data.get("session_started_at"),
        }

    async def set_current_project(
        self,
        name: Optional[str],
        project_data: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        mirror_global: bool = True,
    ) -> State:
        """Persist the active project name and optional project metadata with atomic versioning."""
        async with self._lock:
            existing = await asyncio.to_thread(self._read_json)
            projects = existing.get("projects", {})
            recent = existing.get("recent_projects", [])
            session_projects = existing.get("session_projects", {})
            session_modes = existing.get("session_modes", {})
            recent_tools = _normalise_tool_history(existing.get("recent_tools", []))
            last_activity = existing.get("last_activity_at")
            session_started = existing.get("session_started_at")

            # Version tracking for concurrent operations
            current_version = existing.get("version", 0)
            new_version = current_version + 1

            if project_data:
                projects[name] = project_data  # type: ignore[index]
                if session_id:
                    session_projects[str(session_id)] = project_data
            if name:
                recent = [name] + [item for item in recent if item != name]
                recent = recent[: settings.recent_projects_limit]

            current_project = name if mirror_global else existing.get("current_project")
            data = {
                "current_project": current_project,
                "projects": projects,
                "recent_projects": recent,
                "session_projects": session_projects,
                "session_modes": session_modes,
                "recent_tools": recent_tools,
                "last_activity_at": last_activity,
                "session_started_at": session_started,
                "version": new_version,
                "last_updated_by": agent_id,
                "operation_timestamp": utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
            # Atomic write with temp file
            await asyncio.to_thread(self._write_json_atomic, data)
            return State(
                current_project=current_project,
                projects=projects,
                recent_projects=recent,
                session_projects=session_projects,
                session_modes=session_modes,
                recent_tools=list(recent_tools),
                last_activity_at=last_activity,
                session_started_at=session_started,
                version=new_version,
                last_updated_by=agent_id,
                operation_timestamp=data["operation_timestamp"],
                agent_state=data.get("agent_state", {}),
            )

    async def set_session_mode(self, session_id: Optional[str], mode: str) -> None:
        if not session_id or mode not in {"sentinel", "project"}:
            return
        async with self._lock:
            existing = await asyncio.to_thread(self._read_json)
            session_modes = existing.get("session_modes", {})
            session_modes[str(session_id)] = mode
            existing["session_modes"] = session_modes
            existing["operation_timestamp"] = utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            await asyncio.to_thread(self._write_json_atomic, existing)

    def _read_json(self) -> Dict[str, Any]:
        target = self._path
        if not target.exists():
            return self._read_backup()
        try:
            with target.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return self._read_backup()

    def _write_json(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(self._path.suffix + self._temp_suffix)
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        temp_path.replace(self._path)

    def _write_json_atomic(self, data: Dict[str, Any]) -> None:
        """Enhanced atomic write with version tracking and backup."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Create versioned temp file
        version = data.get("version", 0)
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp.{version}")

        # Write to temp file first
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())  # Force write to disk

        # Atomic rename
        temp_path.replace(self._path)

        # Cleanup old temp files
        self._cleanup_old_temp_files()

    def _cleanup_old_temp_files(self) -> None:
        """Clean up old versioned temp files."""
        try:
            state_dir = self._path.parent
            pattern = f"{self._path.name}.tmp.*"
            for temp_file in state_dir.glob(pattern):
                # Only clean up files older than current version
                if temp_file.stat().st_mtime < (utcnow().timestamp() - 300):  # 5 minutes old
                    temp_file.unlink()
        except Exception:
            pass  # Don't fail cleanup

    def _read_backup(self) -> Dict[str, Any]:
        backup = self._path.with_suffix(self._path.suffix + self._temp_suffix)
        if not backup.exists():
            return {}
        try:
            with backup.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return {}

    async def _write_state(self, state: State) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._write_json,
                {
                    "current_project": state.current_project,
                    "projects": state.projects,
                    "recent_projects": state.recent_projects,
                    "session_projects": state.session_projects,
                    "recent_tools": state.recent_tools,
                    "last_activity_at": state.last_activity_at,
                    "session_started_at": state.session_started_at,
                    "version": state.version,
                    "last_updated_by": state.last_updated_by,
                    "operation_timestamp": state.operation_timestamp,
                    "agent_state": state.agent_state,
                },
            )

    async def update_project_metadata(self, name: str, updates: Dict[str, Any]) -> State:
        """Merge metadata into a stored project entry."""
        async with self._lock:
            data = await asyncio.to_thread(self._read_json)
            projects = data.get("projects", {})
            project = projects.get(name, {})
            project.update(updates)
            projects[name] = project
            data["projects"] = projects
            await asyncio.to_thread(self._write_json, data)
            return State(
                current_project=data.get("current_project"),
                projects=projects,
                recent_projects=data.get("recent_projects", []),
                session_projects=data.get("session_projects", {}),
                recent_tools=_normalise_tool_history(data.get("recent_tools", [])),
                last_activity_at=data.get("last_activity_at"),
                session_started_at=data.get("session_started_at"),
            )


def _normalise_tool_history(raw: Any) -> List[Dict[str, str]]:
    history: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return history
    for item in raw:
        if isinstance(item, dict) and "name" in item:
            name = str(item.get("name"))
            ts = str(item.get("ts") or "")
        else:
            name = str(item)
            ts = ""
        history.append({"name": name, "ts": ts})
    return history[:TOOL_HISTORY_LIMIT]
