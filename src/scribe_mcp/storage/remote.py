"""RemoteStorageBackend -- HTTP proxy to a remote Scribe server.

Proxies persistent operations (projects, entries, dev plans) to a remote
Scribe server via REST API.  Session management stays in-memory locally
for zero-latency middleware operations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

from scribe_mcp.storage.base import ConflictError, RemoteUnavailableError, StorageBackend
from scribe_mcp.storage.models import ProjectRecord

logger = logging.getLogger(__name__)


class RemoteStorageBackend(StorageBackend):
    """Storage backend that proxies DB operations to a remote Scribe server.

    Session operations (upsert_session, get_session_mode, etc.) are handled
    entirely in-memory with zero network overhead.  All persistent operations
    (projects, entries, dev plans, doc tracking) are forwarded to the remote
    server via ``POST /api/v1/backend/{operation}`` or ``POST /api/v1/batch``.
    """

    def __init__(self, server_url: str, timeout: float = 30.0) -> None:
        self._server_url = server_url.rstrip("/")
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

        # In-memory session cache (zero network for middleware)
        self._sessions: Dict[str, dict] = {}                # session_id -> session_data
        self._session_projects: Dict[str, str] = {}         # session_id -> project_name
        self._session_modes: Dict[str, str] = {}            # session_id -> mode
        self._transport_sessions: Dict[str, str] = {}       # transport_session_id -> session_id
        self._agent_sessions: Dict[str, str] = {}           # identity_key -> session_id
        self._agent_recent_projects: Dict[str, str] = {}    # agent_id -> project_name
        self._agent_projects: Dict[str, dict] = {}          # agent_id -> {project_name, version, ...}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Create httpx client with connection pooling."""
        self._client = httpx.AsyncClient(
            base_url=self._server_url,
            timeout=self._timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        logger.info("RemoteStorageBackend connected to %s", self._server_url)

    async def close(self) -> None:
        """Close httpx client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _call(self, operation: str, **kwargs: Any) -> Any:
        """Call a single operation on the remote server.

        Sends kwargs as a flat JSON body to
        ``POST /api/v1/backend/{operation}``.  The server unpacks them
        directly as ``method(**body)``.
        """
        if not self._client:
            raise RemoteUnavailableError("RemoteStorageBackend not initialized (call setup() first)")
        try:
            resp = await self._client.post(
                f"/api/v1/backend/{operation}",
                json=kwargs if kwargs else {},
            )
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"Remote operation {operation} failed: {data['error']}")
            return data.get("result")
        except httpx.ConnectError as exc:
            raise RemoteUnavailableError(f"Cannot reach remote server: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RemoteUnavailableError(f"Remote server timeout: {exc}") from exc

    async def execute_batch(self, operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute multiple operations in a single HTTP request.

        Each item in *operations* must have ``{"op": "<name>", "args": {...}}``.
        Returns a list of ``{"ok": bool, "result"|"error": ...}`` dicts.
        """
        if not self._client:
            raise RemoteUnavailableError("RemoteStorageBackend not initialized")
        try:
            resp = await self._client.post(
                "/api/v1/batch",
                json={"operations": operations},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except httpx.ConnectError as exc:
            raise RemoteUnavailableError(f"Cannot reach remote server: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RemoteUnavailableError(f"Remote server timeout: {exc}") from exc

    # ------------------------------------------------------------------
    # ProjectRecord deserialization
    # ------------------------------------------------------------------

    def _to_project_record(self, data: Any) -> Optional[ProjectRecord]:
        """Convert a dict from the remote server to a ProjectRecord."""
        if data is None:
            return None
        if isinstance(data, dict):
            return ProjectRecord(
                id=data.get("id", 0),
                name=data.get("name", ""),
                repo_root=data.get("repo_root", ""),
                progress_log_path=data.get("progress_log_path", ""),
                docs_json=data.get("docs_json"),
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                bridge_id=data.get("bridge_id"),
                bridge_managed=data.get("bridge_managed", False),
            )
        return data  # Already a ProjectRecord

    # ==================================================================
    # Session methods (Task Package 4.2) -- in-memory, zero network
    # ==================================================================

    async def upsert_session(
        self,
        *,
        session_id: str,
        transport_session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        repo_root: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> None:
        self._sessions[session_id] = {
            "session_id": session_id,
            "transport_session_id": transport_session_id,
            "agent_id": agent_id,
            "repo_root": repo_root,
            "mode": mode,
            "created_at": datetime.utcnow().isoformat(),
            "last_active_at": datetime.utcnow().isoformat(),
        }
        if transport_session_id:
            self._transport_sessions[transport_session_id] = session_id

    async def get_session_by_transport(self, transport_session_id: str) -> Optional[dict]:
        session_id = self._transport_sessions.get(transport_session_id)
        if session_id:
            return self._sessions.get(session_id)
        return None

    async def set_session_mode(self, session_id: str, mode: str) -> None:
        self._session_modes[session_id] = mode

    async def get_session_mode(self, session_id: str) -> Optional[str]:
        return self._session_modes.get(session_id)

    async def set_session_project(self, session_id: str, project_name: str) -> None:
        self._session_projects[session_id] = project_name

    async def get_session_project(self, session_id: str) -> Optional[str]:
        return self._session_projects.get(session_id)

    async def upsert_agent_session(
        self, agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]
    ) -> None:
        self._sessions[session_id] = {
            "session_id": session_id,
            "agent_id": agent_id,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "last_active_at": datetime.utcnow().isoformat(),
            "state": "active",
        }

    async def heartbeat_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["last_active_at"] = datetime.utcnow().isoformat()

    async def end_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["state"] = "expired"

    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self._agent_projects.get(agent_id)

    async def set_agent_project(
        self,
        agent_id: str,
        project_name: Optional[str],
        expected_version: Optional[int],
        updated_by: str,
        session_id: str,
    ) -> Dict[str, Any]:
        current = self._agent_projects.get(agent_id, {})
        current_version = current.get("version", 0)
        if expected_version is not None and expected_version != current_version:
            raise ConflictError(
                f"Version conflict: expected {expected_version}, got {current_version}"
            )
        new_version = current_version + 1
        record: Dict[str, Any] = {
            "agent_id": agent_id,
            "project_name": project_name,
            "version": new_version,
            "updated_by": updated_by,
            "session_id": session_id,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._agent_projects[agent_id] = record
        return record

    async def update_session_activity(
        self, session_id: str, tool_name: str, timestamp: str
    ) -> None:
        """No-op in client mode -- session analytics not needed."""

    async def get_session_activity(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return minimal activity data from in-memory session."""
        session = self._sessions.get(session_id)
        if session:
            return {"last_activity_at": session.get("last_active_at"), "recent_tools": []}
        return None

    async def get_or_create_agent_session(
        self,
        *,
        identity_key: str,
        agent_name: str = "",
        agent_key: str = "",
        repo_root: str = "",
        mode: str = "",
        scope_key: str = "",
    ) -> str:
        if identity_key in self._agent_sessions:
            return self._agent_sessions[identity_key]
        session_id = str(uuid.uuid4())
        self._agent_sessions[identity_key] = session_id
        self._sessions[session_id] = {
            "session_id": session_id,
            "identity_key": identity_key,
            "agent_name": agent_name,
            "created_at": datetime.utcnow().isoformat(),
            "last_active_at": datetime.utcnow().isoformat(),
            "state": "active",
        }
        return session_id

    async def upsert_agent_recent_project(
        self, agent_id: str, project_name: str
    ) -> None:
        self._agent_recent_projects[agent_id] = project_name

    # ==================================================================
    # Remote methods (Task Package 4.3) -- HTTP proxy to server
    # ==================================================================

    # --- Project operations ---

    async def upsert_project(
        self,
        *,
        name: str,
        repo_root: str,
        progress_log_path: str,
        docs_json: Optional[str] = None,
        bridge_id: Optional[str] = None,
        bridge_managed: bool = False,
    ) -> ProjectRecord:
        result = await self._call(
            "upsert_project",
            name=name,
            repo_root=repo_root,
            progress_log_path=progress_log_path,
            docs_json=docs_json,
            bridge_id=bridge_id,
            bridge_managed=bridge_managed,
        )
        return self._to_project_record(result)

    async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
        result = await self._call("fetch_project", name=name)
        return self._to_project_record(result)

    async def list_projects(self) -> List[ProjectRecord]:
        result = await self._call("list_projects")
        return [self._to_project_record(r) for r in (result or []) if r]

    async def list_projects_by_repo(self, repo_root: str) -> List[ProjectRecord]:
        result = await self._call("list_projects_by_repo", repo_root=repo_root)
        return [self._to_project_record(r) for r in (result or []) if r]

    async def delete_project(self, name: str) -> bool:
        result = await self._call("delete_project", name=name)
        return bool(result)

    async def update_project_docs(self, name: str, docs_json: str) -> bool:
        result = await self._call("update_project_docs", name=name, docs_json=docs_json)
        return bool(result)

    # --- Entry operations ---

    async def insert_entry(
        self,
        *,
        entry_id: str,
        project: ProjectRecord,
        ts: datetime,
        emoji: str,
        agent: Optional[str],
        message: str,
        meta: Optional[Dict[str, Any]],
        raw_line: str,
        sha256: str,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[str] = None,
        confidence: Optional[float] = None,
        log_type: Optional[str] = None,
    ) -> None:
        kwargs: Dict[str, Any] = {
            "entry_id": entry_id,
            "project": {"name": project.name, "id": project.id},
            "ts": ts.isoformat() if isinstance(ts, datetime) else str(ts),
            "emoji": emoji,
            "agent": agent,
            "message": message,
            "meta": meta,
            "raw_line": raw_line,
            "sha256": sha256,
        }
        # Only send optional fields if provided
        if priority is not None:
            kwargs["priority"] = priority
        if category is not None:
            kwargs["category"] = category
        if tags is not None:
            kwargs["tags"] = tags
        if confidence is not None:
            kwargs["confidence"] = confidence
        if log_type is not None:
            kwargs["log_type"] = log_type
        await self._call("insert_entry", **kwargs)

    async def fetch_recent_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        result = await self._call(
            "fetch_recent_entries",
            project={"name": project.name, "id": project.id},
            limit=limit,
            filters=filters,
            offset=offset,
        )
        return result or []

    async def fetch_recent_entries_paginated(
        self,
        *,
        project: ProjectRecord,
        page: int = 1,
        page_size: int = 50,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        result = await self._call(
            "fetch_recent_entries_paginated",
            project={"name": project.name, "id": project.id},
            page=page,
            page_size=page_size,
            filters=filters,
        )
        # Server returns [entries, total_count] (tuple serialised to list)
        if isinstance(result, list) and len(result) == 2:
            return result[0], result[1]
        return result or [], 0

    async def count_entries(
        self,
        project: ProjectRecord,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        result = await self._call(
            "count_entries",
            project={"name": project.name, "id": project.id},
            filters=filters,
        )
        return int(result or 0)

    async def query_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        start: Optional[str] = None,
        end: Optional[str] = None,
        agents: Optional[List[str]] = None,
        emojis: Optional[List[str]] = None,
        message: Optional[str] = None,
        message_mode: str = "substring",
        case_sensitive: bool = False,
        meta_filters: Optional[Dict[str, str]] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        result = await self._call(
            "query_entries",
            project={"name": project.name, "id": project.id},
            limit=limit,
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_filters,
            offset=offset,
        )
        return result or []

    async def query_entries_paginated(
        self,
        *,
        project: ProjectRecord,
        page: int = 1,
        page_size: int = 50,
        start: Optional[str] = None,
        end: Optional[str] = None,
        agents: Optional[List[str]] = None,
        emojis: Optional[List[str]] = None,
        message: Optional[str] = None,
        message_mode: str = "substring",
        case_sensitive: bool = False,
        meta_filters: Optional[Dict[str, str]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        result = await self._call(
            "query_entries_paginated",
            project={"name": project.name, "id": project.id},
            page=page,
            page_size=page_size,
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_filters,
        )
        if isinstance(result, list) and len(result) == 2:
            return result[0], result[1]
        return result or [], 0

    async def count_query_entries(
        self,
        *,
        project: ProjectRecord,
        start: Optional[str] = None,
        end: Optional[str] = None,
        agents: Optional[List[str]] = None,
        emojis: Optional[List[str]] = None,
        message: Optional[str] = None,
        message_mode: str = "substring",
        case_sensitive: bool = False,
        meta_filters: Optional[Dict[str, str]] = None,
    ) -> int:
        result = await self._call(
            "count_query_entries",
            project={"name": project.name, "id": project.id},
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            message=message,
            message_mode=message_mode,
            case_sensitive=case_sensitive,
            meta_filters=meta_filters,
        )
        return int(result or 0)

    # --- Dev plan operations ---

    async def upsert_dev_plan(self, project_id: int, plan_type: str, **kwargs: Any) -> None:
        await self._call("upsert_dev_plan", project_id=project_id, plan_type=plan_type, **kwargs)

    # --- Doc tracking (fire-and-forget) ---

    async def record_doc_change(
        self,
        project: ProjectRecord,
        *,
        doc: str,
        section: Optional[str],
        action: str,
        agent: Optional[str],
        metadata: Optional[Dict[str, Any]],
        sha_before: str,
        sha_after: str,
    ) -> None:
        try:
            await self._call(
                "record_doc_change",
                project={"name": project.name, "id": project.id},
                doc=doc,
                section=section,
                action=action,
                agent=agent,
                metadata=metadata,
                sha_before=sha_before,
                sha_after=sha_after,
            )
        except Exception:
            logger.debug("record_doc_change fire-and-forget failed (non-critical)")

    async def record_agent_report_card(
        self,
        project: ProjectRecord,
        *,
        file_path: str,
        agent_name: str,
        stage: Optional[str],
        overall_grade: Optional[float],
        performance_level: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        try:
            await self._call(
                "record_agent_report_card",
                project={"name": project.name, "id": project.id},
                file_path=file_path,
                agent_name=agent_name,
                stage=stage,
                overall_grade=overall_grade,
                performance_level=performance_level,
                metadata=metadata,
            )
        except Exception:
            logger.debug("record_agent_report_card fire-and-forget failed (non-critical)")

    # --- Bridge methods (no-ops in client mode) ---

    async def insert_bridge(
        self, bridge_id: str, name: str, version: str, manifest_json: str, state: str
    ) -> None:
        pass  # Bridges are server-side only

    async def update_bridge_state(self, bridge_id: str, state: str) -> None:
        pass

    async def update_bridge_health(
        self, bridge_id: str, health_json: str, error: Optional[str] = None
    ) -> None:
        pass

    async def fetch_bridge(self, bridge_id: str) -> Optional[Dict[str, Any]]:
        return None

    async def list_bridges(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    async def delete_bridge(self, bridge_id: str) -> None:
        pass

    # --- Reminder methods (proxy to remote, graceful fallback) ---

    async def get_reminder_history(
        self,
        *,
        project_root: Optional[str] = None,
        agent_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        try:
            result = await self._call(
                "get_reminder_history",
                project_root=project_root,
                agent_id=agent_id,
                category=category,
                limit=limit,
            )
            return result or []
        except Exception:
            return []

    async def clear_reminder_history(
        self,
        *,
        project_root: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> int:
        try:
            result = await self._call(
                "clear_reminder_history",
                project_root=project_root,
                agent_id=agent_id,
            )
            return int(result or 0)
        except Exception:
            return 0

    # --- Data retention ---

    async def cleanup_old_entries(
        self,
        project_id: Optional[int] = None,
        retention_days: int = 90,
        archive: bool = True,
    ) -> int:
        result = await self._call(
            "cleanup_old_entries",
            project_id=project_id,
            retention_days=retention_days,
            archive=archive,
        )
        return int(result or 0)

    # --- Synchronous fetch fallback ---

    async def fetch_project_sync(self, name: str) -> Optional[ProjectRecord]:
        """Synchronous wrapper -- in remote mode, just calls async fetch_project."""
        return await self.fetch_project(name)
