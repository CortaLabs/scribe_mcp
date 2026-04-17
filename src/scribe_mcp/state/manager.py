"""Database-backed runtime state for the MCP server."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp.config.settings import settings
from scribe_mcp.storage import create_storage_backend
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.shared.session_scope import ResolvedScope
from scribe_mcp.utils.slug import normalize_project_input
from scribe_mcp.utils.time import utcnow

from .migration import migrate_legacy_state_file


logger = logging.getLogger(__name__)


def _float_env(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


TOOL_HISTORY_LIMIT = 10
_GLOBAL_AGENT_ID = "Scribe"
_PROJECT_CACHE_TTL_SECONDS = _float_env("SCRIBE_PROJECT_CACHE_TTL_SECONDS", 30.0, 1.0)


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
        if name in self.projects:
            return self.projects[name]

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
            recent = recent[: settings.recent_projects_limit]
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
            agent_state=dict(self.agent_state),
        )


class StateManager:
    """DB-backed state manager with one-time legacy file migration."""

    def __init__(
        self,
        path: Optional[Path] = None,
        storage_backend: Any = None,
    ) -> None:
        self._legacy_state_path = self._resolve_legacy_state_path(path)
        self._storage_backend = storage_backend or self._build_default_backend(path)
        self._lock = asyncio.Lock()
        self._backend_ready = False
        self._legacy_migration_checked = False

        # In-memory compatibility cache for low-risk legacy fields.
        self._agent_state_cache: Dict[str, Any] = {}
        self._session_projects_cache: Dict[str, Dict[str, Any]] = {}
        self._session_modes_cache: Dict[str, str] = {}
        self._recent_projects_cache: List[str] = []
        self._activity_cache: Dict[str, Any] = {
            "recent_tools": [],
            "last_activity_at": None,
            "session_started_at": None,
        }
        self._projects_cache: Dict[str, Dict[str, Any]] = {}
        self._projects_cache_at: float = 0.0

    async def load(self) -> State:
        """Read state snapshot from database and compatibility caches."""
        async with self._lock:
            return await self._load_locked()

    async def persist(self, state: State) -> None:
        """Persist cache-compatible state fields into database-backed storage.

        Project upsert loops have been intentionally removed.  All callers
        (set_project, append_entry, set_session_mode) already upsert the
        single project they touch at the time of the write.  Re-iterating
        every project in state.projects here was O(N) redundant work — the
        data is unchanged by the time persist() is called.

        For local backends: updates global project pointer, session project
        bindings, and session modes.  For remote backends: skips all DB
        writes and only updates in-memory caches.
        """
        async with self._lock:
            from scribe_mcp.storage.remote import RemoteStorageBackend
            is_remote = isinstance(self._storage_backend, RemoteStorageBackend)

            if not is_remote:
                await self._ensure_backend_ready()
                await self._run_legacy_migration_once()

                await self._set_global_project(
                    project_name=state.current_project,
                    updated_by=state.last_updated_by or _GLOBAL_AGENT_ID,
                    session_id=None,
                )

                for session_id, project_payload in state.session_projects.items():
                    project_name = self._resolve_project_name(project_payload)
                    if not project_name:
                        continue
                    if hasattr(self._storage_backend, "set_session_project"):
                        await self._storage_backend.set_session_project(session_id, project_name)

                for session_id, mode in state.session_modes.items():
                    if mode not in {"project", "sentinel"}:
                        continue
                    if hasattr(self._storage_backend, "upsert_session"):
                        await self._storage_backend.upsert_session(session_id=session_id, mode=mode)
                    if hasattr(self._storage_backend, "set_session_mode"):
                        await self._storage_backend.set_session_mode(session_id, mode)

            # Always update in-memory caches regardless of backend type
            self._agent_state_cache = dict(state.agent_state or {})
            self._recent_projects_cache = list(state.recent_projects or [])
            self._session_projects_cache.update(dict(state.session_projects or {}))
            self._session_modes_cache.update(dict(state.session_modes or {}))
            self._activity_cache = {
                "recent_tools": list(state.recent_tools or []),
                "last_activity_at": state.last_activity_at,
                "session_started_at": state.session_started_at,
            }

    async def record_tool(self, tool_name: str) -> State:
        """Track recent tool activity in the session database state."""
        async with self._lock:
            await self._ensure_backend_ready()
            await self._run_legacy_migration_once()

            now_utc = utcnow()
            timestamp_iso = now_utc.isoformat()
            timestamp_display = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
            session_id = self._resolve_session_id_from_context()

            if session_id and hasattr(self._storage_backend, "update_session_activity"):
                try:
                    await self._storage_backend.update_session_activity(
                        session_id=session_id,
                        tool_name=tool_name,
                        timestamp=timestamp_iso,
                    )
                except Exception as exc:
                    logger.warning("Failed to persist session activity for '%s': %s", session_id, exc)

            activity = await self._resolve_activity(session_id)
            if not activity.get("recent_tools"):
                recent_tools = _normalise_tool_history(self._activity_cache.get("recent_tools", []))
                recent_tools.insert(0, {"name": tool_name, "ts": timestamp_display})
                activity = {
                    "recent_tools": recent_tools,
                    "last_activity_at": timestamp_display,
                    "session_started_at": self._activity_cache.get("session_started_at") or timestamp_display,
                }

            self._activity_cache = {
                "recent_tools": list(activity.get("recent_tools", [])),
                "last_activity_at": activity.get("last_activity_at") or timestamp_display,
                "session_started_at": activity.get("session_started_at") or timestamp_display,
            }

            state = await self._load_locked()
            state.recent_tools = _normalise_tool_history(self._activity_cache["recent_tools"])
            state.last_activity_at = self._activity_cache["last_activity_at"]
            state.session_started_at = self._activity_cache["session_started_at"]
            return state

    async def set_current_project(
        self,
        name: Optional[str],
        project_data: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        resolved_scope: Optional[ResolvedScope] = None,
        mirror_global: bool = True,
        skip_upsert: bool = False,
    ) -> State:
        """Persist active project into DB-backed session/global state."""
        async with self._lock:
            await self._ensure_backend_ready()
            await self._run_legacy_migration_once()

            resolved_name = self._resolve_project_name(project_data) or name
            resolved_payload = dict(project_data or {})
            resolved_session_id = self._resolve_write_session_id(
                session_id=session_id,
                resolved_scope=resolved_scope,
            )
            if resolved_name:
                resolved_payload.setdefault("name", resolved_name)
                if not skip_upsert:
                    await self._upsert_project(resolved_name, resolved_payload)

                if resolved_session_id and hasattr(self._storage_backend, "set_session_project"):
                    await self._storage_backend.set_session_project(resolved_session_id, resolved_name)
                    self._session_projects_cache[resolved_session_id] = dict(resolved_payload)

                if agent_id and hasattr(self._storage_backend, "upsert_agent_recent_project"):
                    await self._storage_backend.upsert_agent_recent_project(agent_id, resolved_name)

                self._remember_recent_project(resolved_name)

            if mirror_global:
                await self._set_global_project(
                    project_name=resolved_name,
                    updated_by=agent_id or _GLOBAL_AGENT_ID,
                    session_id=resolved_session_id,
                )

            state = await self._load_locked()
            if resolved_session_id and resolved_name:
                state.session_projects[resolved_session_id] = (
                    state.get_project(resolved_name)
                    or {"name": resolved_name}
                )
            return state

    async def set_session_mode(self, session_id: Optional[str], mode: str) -> None:
        if not session_id or mode not in {"sentinel", "project"}:
            return
        async with self._lock:
            await self._ensure_backend_ready()
            await self._run_legacy_migration_once()

            if hasattr(self._storage_backend, "upsert_session"):
                await self._storage_backend.upsert_session(session_id=session_id, mode=mode)
            if hasattr(self._storage_backend, "set_session_mode"):
                await self._storage_backend.set_session_mode(session_id, mode)
            self._session_modes_cache[str(session_id)] = mode

    async def update_project_metadata(self, name: str, updates: Dict[str, Any]) -> State:
        """Merge metadata into a stored project entry."""
        async with self._lock:
            await self._ensure_backend_ready()
            await self._run_legacy_migration_once()

            current = await self._fetch_project(name) or {"name": name}
            current.update(updates)
            await self._upsert_project(name, current)
            return await self._load_locked()

    async def _load_locked(self) -> State:
        """Read state snapshot; caller must hold ``self._lock``."""
        await self._ensure_backend_ready()
        await self._run_legacy_migration_once()

        projects = await self._load_projects()
        session_id = self._resolve_session_id_from_context()
        current_project, session_projects = await self._resolve_current_project(session_id, projects)
        session_modes = await self._resolve_session_modes(session_id)
        activity = await self._resolve_activity(session_id)
        recent_projects = self._build_recent_projects(current_project, projects)

        return State(
            current_project=current_project,
            projects=projects,
            recent_projects=recent_projects,
            session_projects=session_projects,
            session_modes=session_modes,
            recent_tools=_normalise_tool_history(activity.get("recent_tools", [])),
            last_activity_at=activity.get("last_activity_at"),
            session_started_at=activity.get("session_started_at"),
            last_updated_by=self._agent_state_cache.get("last_agent_id"),
            operation_timestamp=utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            agent_state=dict(self._agent_state_cache),
        )

    def _resolve_legacy_state_path(self, path: Optional[Path]) -> Optional[Path]:
        if path is None:
            return settings.default_state_path
        candidate = Path(path).expanduser()
        if candidate.suffix.lower() == ".db":
            return None
        return candidate

    def _build_default_backend(self, path: Optional[Path]) -> Any:
        if path is not None:
            candidate = Path(path).expanduser()
            db_path = candidate if candidate.suffix.lower() == ".db" else candidate.with_suffix(".db")
            return SQLiteStorage(db_path)

        backend = create_storage_backend()
        if backend is not None:
            return backend
        raise RuntimeError(
            "Failed to build default storage backend for StateManager. "
            "Server/public-release runtime requires valid Postgres configuration unless "
            "standalone SQLite is explicitly selected."
        )

    async def _ensure_backend_ready(self) -> None:
        if self._backend_ready:
            return
        setup_fn = getattr(self._storage_backend, "setup", None)
        if callable(setup_fn):
            await setup_fn()
        self._backend_ready = True

    async def _run_legacy_migration_once(self) -> None:
        if self._legacy_migration_checked:
            return
        self._legacy_migration_checked = True

        if not self._legacy_state_path or not self._legacy_state_path.exists():
            return

        try:
            result = await migrate_legacy_state_file(
                storage_backend=self._storage_backend,
                state_path=self._legacy_state_path,
                rename_source=True,
            )
            if result.migrated:
                self._projects_cache = {}
                self._projects_cache_at = 0.0
                logger.info(
                    "Migrated legacy state file to DB (%s projects, %s session bindings)",
                    result.projects_migrated,
                    result.session_projects_migrated,
                )
        except Exception as exc:
            logger.warning("Legacy state migration failed: %s", exc)

    async def _load_projects(self) -> Dict[str, Dict[str, Any]]:
        now = time.monotonic()
        if (
            self._projects_cache
            and (now - self._projects_cache_at) < _PROJECT_CACHE_TTL_SECONDS
        ):
            projects = {name: dict(payload) for name, payload in self._projects_cache.items()}
        else:
            projects = {}
            if not hasattr(self._storage_backend, "list_projects"):
                return projects

            try:
                repo_root_filter: Optional[str] = None
                try:
                    from scribe_mcp import server as server_module

                    if hasattr(server_module, "get_execution_context"):
                        exec_context = server_module.get_execution_context()
                        if exec_context and getattr(exec_context, "repo_root", None):
                            repo_root_filter = str(
                                Path(str(exec_context.repo_root)).expanduser().resolve()
                            )
                except Exception:
                    repo_root_filter = None

                if not repo_root_filter or not hasattr(self._storage_backend, "list_projects_by_repo"):
                    return projects
                records = await self._storage_backend.list_projects_by_repo(repo_root_filter)
            except Exception as exc:
                logger.warning("Failed to load projects from backend: %s", exc)
                return projects

            for record in records:
                project_data = self._record_to_project_dict(record)
                projects[record.name] = project_data

            self._projects_cache = {name: dict(payload) for name, payload in projects.items()}
            self._projects_cache_at = now

        for name, payload in self._session_projects_cache.items():
            _ = name
            project_name = self._resolve_project_name(payload)
            if project_name and project_name not in projects:
                projects[project_name] = dict(payload)

        return projects

    async def _resolve_current_project(
        self,
        session_id: Optional[str],
        projects: Dict[str, Dict[str, Any]],
    ) -> Tuple[Optional[str], Dict[str, Dict[str, Any]]]:
        session_projects: Dict[str, Dict[str, Any]] = {}
        current_project: Optional[str] = None

        if session_id and hasattr(self._storage_backend, "get_session_project"):
            try:
                project_name = await self._storage_backend.get_session_project(session_id)
            except Exception:
                project_name = None

            if project_name:
                current_project = project_name
                session_projects[session_id] = (
                    projects.get(project_name)
                    or {"name": project_name}
                )

        if not current_project and session_id in self._session_projects_cache:
            cached = self._session_projects_cache[session_id]
            project_name = self._resolve_project_name(cached)
            if project_name:
                current_project = project_name
                session_projects[session_id] = dict(cached)

        return current_project, session_projects

    async def _resolve_session_modes(self, session_id: Optional[str]) -> Dict[str, str]:
        session_modes = dict(self._session_modes_cache)
        if not session_id:
            return session_modes

        if hasattr(self._storage_backend, "get_session_mode"):
            try:
                mode = await self._storage_backend.get_session_mode(session_id)
            except Exception:
                mode = None
            if mode in {"project", "sentinel"}:
                session_modes[session_id] = mode

        return session_modes

    async def _resolve_activity(self, session_id: Optional[str]) -> Dict[str, Any]:
        if session_id and hasattr(self._storage_backend, "get_session_activity"):
            try:
                activity = await self._storage_backend.get_session_activity(session_id)
            except Exception:
                activity = None
            if activity:
                normalized = {
                    "recent_tools": _normalise_tool_history(activity.get("recent_tools", [])),
                    "last_activity_at": activity.get("last_activity_at"),
                    "session_started_at": activity.get("session_started_at"),
                }
                self._activity_cache = dict(normalized)
                return normalized

        return dict(self._activity_cache)

    def _build_recent_projects(
        self,
        current_project: Optional[str],
        projects: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        recent = list(self._recent_projects_cache)
        if current_project:
            recent = [current_project] + [name for name in recent if name != current_project]
        for name in projects:
            if name not in recent:
                recent.append(name)
        return recent[: settings.recent_projects_limit]

    async def _set_global_project(
        self,
        project_name: Optional[str],
        updated_by: str,
        session_id: Optional[str],
    ) -> None:
        if not hasattr(self._storage_backend, "set_agent_project"):
            return

        stable_session_id = session_id or self._resolve_session_id_from_context() or "__global__"
        try:
            await self._storage_backend.set_agent_project(
                agent_id=_GLOBAL_AGENT_ID,
                project_name=project_name,
                expected_version=None,
                updated_by=updated_by,
                session_id=stable_session_id,
            )
        except Exception as exc:
            logger.warning("Failed to set global project '%s': %s", project_name, exc)

    async def _upsert_project(self, project_name: str, payload: Dict[str, Any]) -> None:
        if not project_name or not hasattr(self._storage_backend, "upsert_project"):
            return

        name = str(project_name)
        root_value = payload.get("root") or payload.get("repo_root")
        if root_value:
            repo_root = str(root_value)
        else:
            repo_root = str(settings.project_root)

        progress_log_value = payload.get("progress_log")
        if progress_log_value:
            progress_log = str(progress_log_value)
        else:
            progress_log = str(
                settings.project_root
                / settings.dev_plans_base
                / name
                / "PROGRESS_LOG.md"
            )

        docs_json = None
        docs = payload.get("docs")
        if isinstance(docs, dict):
            docs_json = json.dumps(docs)

        await self._storage_backend.upsert_project(
            name=name,
            repo_root=repo_root,
            progress_log_path=progress_log,
            docs_json=docs_json,
        )
        cache_payload = dict(payload)
        cache_payload["name"] = name
        cache_payload["root"] = repo_root
        cache_payload["progress_log"] = progress_log
        if "docs_dir" not in cache_payload:
            cache_payload["docs_dir"] = str(Path(progress_log).expanduser().resolve().parent)
        self._projects_cache[name] = cache_payload
        self._projects_cache_at = time.monotonic()

    async def _fetch_project(self, project_name: str) -> Optional[Dict[str, Any]]:
        if not project_name:
            return None

        if not hasattr(self._storage_backend, "fetch_project"):
            return None

        try:
            record = await self._storage_backend.fetch_project(project_name)
        except Exception:
            record = None

        if not record:
            return None
        return self._record_to_project_dict(record)

    def _record_to_project_dict(self, record: Any) -> Dict[str, Any]:
        progress_log_path = getattr(record, "progress_log_path", None)
        payload: Dict[str, Any] = {
            "name": getattr(record, "name", None),
            "root": getattr(record, "repo_root", None),
            "progress_log": progress_log_path,
        }
        if progress_log_path:
            payload["docs_dir"] = str(Path(progress_log_path).expanduser().resolve().parent)

        docs_json = getattr(record, "docs_json", None)
        if docs_json:
            try:
                docs = json.loads(docs_json)
            except (TypeError, json.JSONDecodeError):
                docs = None
            if isinstance(docs, dict):
                payload["docs"] = docs
                docs_progress = docs.get("progress_log")
                if docs_progress:
                    payload["docs_dir"] = str(Path(docs_progress).expanduser().resolve().parent)

        return payload

    def _resolve_project_name(self, payload: Optional[Dict[str, Any]]) -> Optional[str]:
        if not payload or not isinstance(payload, dict):
            return None
        name = payload.get("name")
        if name is None:
            return None
        candidate = str(name).strip()
        return candidate or None

    def _resolve_session_id_from_context(self) -> Optional[str]:
        try:
            from scribe_mcp import server as server_module

            router_ctx = getattr(server_module, "router_context_manager", None)
            if router_ctx is None:
                return None

            execution_context = router_ctx.get_current()
            if not execution_context:
                return None

            stable = getattr(execution_context, "stable_session_id", None)
            if stable:
                return str(stable)
            session_id = getattr(execution_context, "session_id", None)
            if session_id:
                return str(session_id)
            return None
        except Exception:
            return None

    def _resolve_write_session_id(
        self,
        *,
        session_id: Optional[str],
        resolved_scope: Optional[ResolvedScope],
    ) -> Optional[str]:
        if session_id:
            return str(session_id)
        if resolved_scope:
            for candidate in (
                resolved_scope.stable_session_id,
                resolved_scope.agent_session_id,
                resolved_scope.transport_session_id,
            ):
                if candidate:
                    return str(candidate)
        return self._resolve_session_id_from_context()

    def _remember_recent_project(self, project_name: str) -> None:
        self._recent_projects_cache = [
            project_name,
            *[name for name in self._recent_projects_cache if name != project_name],
        ][: settings.recent_projects_limit]


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
