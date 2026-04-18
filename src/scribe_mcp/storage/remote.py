"""RemoteStorageBackend -- HTTP proxy to a remote Scribe server.

Proxies persistent operations (projects, entries, dev plans) to a remote
Scribe server via REST API.  Session management stays in-memory locally
for zero-latency middleware operations.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from scribe_mcp.storage.base import ConflictError, RemoteUnavailableError, StorageBackend
from scribe_mcp.storage.models import (
    CaseRegistryRecord,
    ProjectRecord,
    RepoScopeGrantRecord,
    normalize_repo_root,
)
from scribe_mcp.state.agent_manager import SessionLeaseExpired

logger = logging.getLogger(__name__)


def _is_public_release_profile() -> bool:
    if os.environ.get("SCRIBE_PUBLIC_RELEASE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    release_profile = os.environ.get("SCRIBE_RELEASE_PROFILE", "internal").strip().lower()
    return release_profile == "public"


class RemoteStorageBackend(StorageBackend):
    """Storage backend that proxies DB operations to a remote Scribe server.

    Session operations (upsert_session, get_session_mode, etc.) are handled
    entirely in-memory with zero network overhead.  All persistent operations
    (projects, entries, dev plans, doc tracking) are forwarded to the remote
    server via ``POST /api/v1/backend/{operation}`` or ``POST /api/v1/batch``.
    """

    def __init__(
        self,
        server_url: str,
        timeout: float = 30.0,
        auth_token: Optional[str] = None,
    ) -> None:
        if _is_public_release_profile():
            raise ValueError(
                "RemoteStorageBackend is internal-only and unavailable in public release profile."
            )
        self._server_url = server_url.rstrip("/")
        self._timeout = timeout
        self._auth_token = auth_token.strip() if auth_token else None
        self._client: Optional[httpx.AsyncClient] = None

        # In-memory session cache (zero network for middleware)
        self._sessions: Dict[str, dict] = {}                # session_id -> session_data
        self._session_projects: Dict[str, str] = {}         # session_id -> project_name
        self._session_modes: Dict[str, str] = {}            # session_id -> mode
        self._transport_sessions: Dict[str, str] = {}       # transport_session_id -> session_id
        self._agent_sessions: Dict[str, Dict[str, str]] = {}  # identity_key -> allocation record
        self._last_agent_session_allocation: Dict[str, Dict[str, Any]] = {}
        self._agent_recent_projects: Dict[str, str] = {}    # agent_id -> project_name
        self._agent_projects: Dict[str, dict] = {}          # agent_id -> {project_name, version, ...}

        # Project record cache (short TTL to avoid stale data)
        self._project_cache: Dict[str, tuple] = {}           # name -> (record, monotonic_time)
        self._project_cache_ttl: float = 10.0               # seconds

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Create httpx client with connection pooling."""
        self._client = httpx.AsyncClient(
            base_url=self._server_url,
            timeout=self._timeout,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers=self._auth_headers(),
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

    def _auth_headers(self) -> Dict[str, str]:
        """Build auth headers for remote backend calls."""
        if not self._auth_token:
            return {}
        return {
            "Authorization": f"Bearer {self._auth_token}",
            "x-scribe-auth": self._auth_token,
        }

    def _auth_failure_message(self, context: str, response: httpx.Response) -> str:
        """Build a clear auth-failure message for 401/403 responses."""
        detail = ""
        try:
            data = response.json()
            detail = (
                str(
                    data.get("error")
                    or data.get("detail")
                    or data.get("message")
                    or data.get("type")
                    or ""
                )
                .strip()
            )
        except ValueError:
            detail = response.text.strip()

        status_label = "Unauthorized" if response.status_code == 401 else "Forbidden"
        message = (
            f"Remote authentication failed for {context}: "
            f"HTTP {response.status_code} {status_label}."
        )
        if detail:
            message += f" {detail}"
        message += (
            " Configure SCRIBE_REMOTE_AUTH_TOKEN "
            "(or compatibility aliases SCRIBE_TRANSPORT_AUTH_TOKEN / SCRIBE_AUTH_TOKEN)."
        )
        return message

    async def _post_json(self, path: str, payload: Dict[str, Any], *, context: str) -> Dict[str, Any]:
        """POST JSON to the remote backend with consistent auth/error handling."""
        if not self._client:
            raise RemoteUnavailableError("RemoteStorageBackend not initialized (call setup() first)")

        try:
            request_kwargs: Dict[str, Any] = {"json": payload}
            headers = self._auth_headers()
            if headers:
                request_kwargs["headers"] = headers
            resp = await self._client.post(path, **request_kwargs)
            if resp.status_code == 401:
                raise RuntimeError(self._auth_failure_message(context, resp))
            if resp.status_code == 403:
                response_type = ""
                response_error = ""
                try:
                    data = resp.json()
                    if isinstance(data, dict):
                        response_type = str(data.get("type") or "").strip()
                        response_error = str(data.get("error") or data.get("detail") or "").strip()
                except ValueError:
                    response_error = resp.text.strip()
                if response_type == "ForbiddenOperation":
                    message = f"Remote operation denied for {context}: HTTP 403 Forbidden."
                    if response_error:
                        message += f" {response_error}"
                    raise PermissionError(message)
                raise RuntimeError(self._auth_failure_message(context, resp))
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as exc:
            raise RemoteUnavailableError(f"Cannot reach remote server: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise RemoteUnavailableError(f"Remote server timeout: {exc}") from exc

    async def _call(self, operation: str, **kwargs: Any) -> Any:
        """Call a single operation on the remote server.

        Sends kwargs as a flat JSON body to
        ``POST /api/v1/backend/{operation}``.  The server unpacks them
        directly as ``method(**body)``.
        """
        data = await self._post_json(
            f"/api/v1/backend/{operation}",
            kwargs if kwargs else {},
            context=f"backend/{operation}",
        )
        if "error" in data:
            error_text = str(data.get("error") or "")
            error_type = str(data.get("type") or "")
            if error_type == "StaleSession":
                raise SessionLeaseExpired(
                    error_text or f"Remote stale session in operation {operation}",
                    reason=str(data.get("stale_session_reason") or "stale_session"),
                    agent_id=str(data.get("agent_id") or ""),
                    session_id=(str(data.get("session_id")) if data.get("session_id") is not None else None),
                )
            if error_type == "ForbiddenOperation":
                raise PermissionError(
                    f"Remote operation {operation} forbidden: {error_text or 'operation denied'}"
                )
            raise RuntimeError(f"Remote operation {operation} failed: {error_text}")
        return data.get("result")

    async def execute_batch(self, operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute multiple operations in a single HTTP request.

        Each item in *operations* must have ``{"op": "<name>", "args": {...}}``.
        Returns a list of ``{"ok": bool, "result"|"error": ...}`` dicts.
        """
        data = await self._post_json(
            "/api/v1/batch",
            {"operations": operations},
            context="batch",
        )
        return data.get("results", [])

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

    def _to_repo_scope_grant_record(self, data: Any) -> Optional[RepoScopeGrantRecord]:
        if data is None:
            return None
        if isinstance(data, RepoScopeGrantRecord):
            return data
        if not isinstance(data, dict):
            return None

        def _parse_time(value: Any) -> datetime:
            if isinstance(value, datetime):
                parsed = value
            else:
                text = str(value).strip()
                if text.endswith("Z"):
                    text = f"{text[:-1]}+00:00"
                parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed

        return RepoScopeGrantRecord(
            grant_id=str(data.get("grant_id", "")),
            authoritative_session_key=str(data.get("authoritative_session_key", "")),
            repo_root=str(data.get("repo_root", "")),
            repo_id=str(data.get("repo_id", "")),
            reason=str(data.get("reason", "")),
            expires_at=_parse_time(data.get("expires_at")),
            created_at=_parse_time(data.get("created_at")) if data.get("created_at") else None,
            updated_at=_parse_time(data.get("updated_at")) if data.get("updated_at") else None,
        )

    def _to_case_registry_record(self, data: Any) -> Optional[CaseRegistryRecord]:
        if data is None:
            return None
        if isinstance(data, CaseRegistryRecord):
            return data
        if not isinstance(data, dict):
            return None
        return CaseRegistryRecord(
            case_id=str(data.get("case_id", "")),
            case_type=str(data.get("case_type", "")),
            project_name=str(data.get("project_name", "")),
            repo_root=str(data.get("repo_root", "")),
            repo_id=str(data.get("repo_id", "")),
            project_key=str(data.get("project_key", "")),
            doc_type=str(data.get("doc_type", "")),
            doc_name=str(data.get("doc_name", "")),
            doc_path=str(data.get("doc_path", "")),
            title=data.get("title"),
            status=data.get("status"),
            severity=data.get("severity"),
            source_tool=data.get("source_tool"),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    # ------------------------------------------------------------------
    # Project record cache helpers
    # ------------------------------------------------------------------

    def _cache_project(self, record: ProjectRecord) -> None:
        """Cache a project record with TTL."""
        self._project_cache[record.name] = (record, time.monotonic())

    def _get_cached_project(self, name: str) -> Optional[ProjectRecord]:
        """Return cached project if TTL hasn't expired, else None."""
        entry = self._project_cache.get(name)
        if entry is None:
            return None
        record, cached_at = entry
        if time.monotonic() - cached_at > self._project_cache_ttl:
            del self._project_cache[name]
            return None
        return record

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

    async def create_repo_scope_grant(
        self,
        *,
        authoritative_session_key: str,
        repo_root: str,
        reason: str,
        ttl_minutes: int = 30,
    ) -> RepoScopeGrantRecord:
        result = await self._call(
            "create_repo_scope_grant",
            authoritative_session_key=authoritative_session_key,
            repo_root=normalize_repo_root(repo_root),
            reason=reason,
            ttl_minutes=ttl_minutes,
        )
        record = self._to_repo_scope_grant_record(result)
        if record is None:
            raise RuntimeError("Remote operation create_repo_scope_grant returned invalid payload")
        return record

    async def fetch_repo_scope_grant(self, grant_id: str) -> Optional[RepoScopeGrantRecord]:
        result = await self._call("fetch_repo_scope_grant", grant_id=grant_id)
        return self._to_repo_scope_grant_record(result)

    async def upsert_case_registry_record(
        self,
        *,
        case_id: str,
        case_type: str,
        project_name: str,
        repo_root: str,
        doc_type: str,
        doc_name: str,
        doc_path: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        source_tool: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CaseRegistryRecord:
        result = await self._call(
            "upsert_case_registry_record",
            case_id=case_id,
            case_type=case_type,
            project_name=project_name,
            repo_root=repo_root,
            doc_type=doc_type,
            doc_name=doc_name,
            doc_path=doc_path,
            title=title,
            status=status,
            severity=severity,
            source_tool=source_tool,
            metadata=metadata,
        )
        record = self._to_case_registry_record(result)
        if record is None:
            raise RuntimeError("Remote operation upsert_case_registry_record returned invalid payload")
        return record

    async def fetch_case_registry_record(
        self,
        case_id: str,
        *,
        repo_root: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Optional[CaseRegistryRecord]:
        result = await self._call(
            "fetch_case_registry_record",
            case_id=case_id,
            repo_root=repo_root,
            project_name=project_name,
        )
        return self._to_case_registry_record(result)

    async def query_case_registry_records(
        self,
        *,
        repo_root: Optional[str] = None,
        project_name: Optional[str] = None,
        case_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[CaseRegistryRecord]:
        result = await self._call(
            "query_case_registry_records",
            repo_root=repo_root,
            project_name=project_name,
            case_type=case_type,
            limit=limit,
            offset=offset,
        )
        return [self._to_case_registry_record(item) for item in (result or []) if item]

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
        self._session_projects.pop(session_id, None)
        self._session_modes.pop(session_id, None)
        self._transport_sessions = {
            transport_id: mapped_session
            for transport_id, mapped_session in self._transport_sessions.items()
            if mapped_session != session_id
        }
        self._agent_sessions = {
            identity_key: record
            for identity_key, record in self._agent_sessions.items()
            if record.get("session_id") != session_id
        }
        self._last_agent_session_allocation = {
            identity_key: allocation
            for identity_key, allocation in self._last_agent_session_allocation.items()
            if allocation.get("session_id") != session_id
        }
        self._agent_projects = {
            agent_id: record
            for agent_id, record in self._agent_projects.items()
            if record.get("session_id") != session_id
        }

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
        scoped_reuse_key = self._derive_scoped_reuse_key(repo_root=repo_root, scope_key=scope_key)
        existing = self._agent_sessions.get(identity_key)
        if (
            existing
            and existing.get("scoped_reuse_key") == scoped_reuse_key
            and existing.get("mode") == mode
        ):
            self._last_agent_session_allocation[identity_key] = {
                "status": "reused",
                "session_id": existing["session_id"],
                "scoped_reuse_key": scoped_reuse_key,
                "repo_root": existing.get("repo_root", ""),
                "scope_key": existing.get("scope_key", ""),
                "mode": existing.get("mode", ""),
            }
            return existing["session_id"]
        session_id = str(uuid.uuid4())
        normalized_repo_root = os.path.realpath(repo_root) if repo_root else ""
        normalized_scope_key = scope_key or "__prebinding__"
        self._agent_sessions[identity_key] = {
            "session_id": session_id,
            "scoped_reuse_key": scoped_reuse_key,
            "scope_key": normalized_scope_key,
            "repo_root": normalized_repo_root,
            "mode": mode,
        }
        self._last_agent_session_allocation[identity_key] = {
            "status": "allocated",
            "session_id": session_id,
            "scoped_reuse_key": scoped_reuse_key,
            "repo_root": normalized_repo_root,
            "scope_key": normalized_scope_key,
            "mode": mode,
        }
        self._sessions[session_id] = {
            "session_id": session_id,
            "identity_key": identity_key,
            "agent_name": agent_name,
            "agent_key": agent_key,
            "repo_root": normalized_repo_root,
            "mode": mode,
            "scope_key": normalized_scope_key,
            "scoped_reuse_key": scoped_reuse_key,
            "session_reuse_status": "allocated",
            "created_at": datetime.utcnow().isoformat(),
            "last_active_at": datetime.utcnow().isoformat(),
            "state": "active",
        }
        return session_id

    async def get_last_agent_session_allocation(self, identity_key: str) -> Optional[Dict[str, Any]]:
        return self._last_agent_session_allocation.get(identity_key)

    @staticmethod
    def _derive_scoped_reuse_key(*, repo_root: str, scope_key: str) -> str:
        normalized_repo_root = os.path.realpath(repo_root) if repo_root else ""
        normalized_scope_key = scope_key or "__prebinding__"
        return f"{normalized_repo_root}:{normalized_scope_key}"

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
        record = self._to_project_record(result)
        if record:
            self._cache_project(record)
        return record

    async def fetch_project(
        self,
        name: str,
        *,
        repo_root: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> Optional[ProjectRecord]:
        # Name-only lookups can reuse cache; scoped lookups should hit source of truth.
        if repo_root is None and project_key is None:
            cached = self._get_cached_project(name)
            if cached is not None:
                return cached
        result = await self._call(
            "fetch_project",
            name=name,
            repo_root=repo_root,
            project_key=project_key,
        )
        record = self._to_project_record(result)
        if record:
            self._cache_project(record)
        return record

    async def list_projects(self) -> List[ProjectRecord]:
        result = await self._call("list_projects")
        return [self._to_project_record(r) for r in (result or []) if r]

    async def list_projects_by_repo(self, repo_root: str) -> List[ProjectRecord]:
        result = await self._call("list_projects_by_repo", repo_root=repo_root)
        return [self._to_project_record(r) for r in (result or []) if r]

    async def delete_project(self, name: str) -> bool:
        self._project_cache.pop(name, None)
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

    async def fetch_project_sync(
        self,
        name: str,
        *,
        repo_root: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> Optional[ProjectRecord]:
        """Synchronous wrapper -- in remote mode, just calls async fetch_project."""
        return await self.fetch_project(name, repo_root=repo_root, project_key=project_key)
