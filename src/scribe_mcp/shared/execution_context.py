"""Router-owned execution context and session identity management."""

from __future__ import annotations

import asyncio
import contextvars
import os
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, Mapping, Optional, Set

from scribe_mcp.shared.session_scope import ResolvedScope, ScopeProvenance, build_resolved_scope


_CURRENT_CONTEXT: contextvars.ContextVar["ExecutionContext | None"] = contextvars.ContextVar(
    "scribe_execution_context",
    default=None,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentIdentity:
    agent_kind: str
    model: Optional[str]
    instance_id: str
    sub_id: Optional[str]
    display_name: Optional[str]


@dataclass(frozen=True)
class ExecutionContext:
    repo_root: str
    mode: str
    session_id: str
    execution_id: str
    agent_identity: AgentIdentity
    intent: str
    timestamp_utc: str
    affected_dev_projects: list[str]
    sentinel_day: Optional[str] = None
    transport_session_id: Optional[str] = None
    stable_session_id: Optional[str] = None  # NEW - from agent_sessions table
    resolved_scope: Optional[ResolvedScope] = None
    session_reuse_status: Optional[str] = None
    session_reuse_scope: Optional[str] = None
    bug_id: Optional[str] = None
    security_id: Optional[str] = None
    parent_execution_id: Optional[str] = None
    toolchain: Optional[str] = None
    authoritative_session_key: Optional[str] = None


class RouterContextManager:
    """Owns router-generated session/execution identity and current context."""

    def __init__(self, storage_backend=None) -> None:
        self._lock = asyncio.Lock()
        self._transport_sessions: Dict[str, str] = {}  # Keep as performance cache
        self._session_projects: Dict[str, str] = {}  # session_id -> project_name cache
        self._files_read_in_session: Dict[str, Set[str]] = defaultdict(set)  # session_id -> set of file paths
        self._stable_agent_sessions: Dict[str, str] = {}  # identity_key -> stable agent session_id cache
        self._process_instance_id = str(uuid.uuid4())
        self._storage_backend = storage_backend  # NEW: Injected dependency

    async def get_or_create_session_id(self, transport_session_id: str) -> str:
        """
        Get or create a stable session ID for the given transport session ID.

        Lookup order:
        1. In-memory cache (fast path)
        2. Database lookup (persistence layer)
        3. Create new session and persist

        Args:
            transport_session_id: Unstable ID from transport layer

        Returns:
            Stable session UUID that persists across restarts
        """
        if not transport_session_id:
            raise ValueError("ExecutionContext requires transport_session_id")

        async with self._lock:
            # TIER 1: Check in-memory cache (fast path)
            existing = self._transport_sessions.get(transport_session_id)
            if existing:
                return existing

            # TIER 2: Check database for existing session (persistence layer)
            if self._storage_backend and hasattr(self._storage_backend, "get_session_by_transport"):
                # NO SILENT ERRORS - let it fail loudly so we can see what's broken
                db_session = await self._storage_backend.get_session_by_transport(transport_session_id)
                if db_session and db_session.get("session_id"):
                    session_id = db_session["session_id"]
                    # Cache it for future requests (performance optimization)
                    self._transport_sessions[transport_session_id] = session_id
                    return session_id

            # TIER 3: Create new session (not found in cache or DB)
            session_id = str(uuid.uuid4())

            # Cache immediately
            self._transport_sessions[transport_session_id] = session_id

            # TIER 3b: Persist to database immediately
            if self._storage_backend and hasattr(self._storage_backend, "upsert_session"):
                # NO SILENT ERRORS - let it fail loudly so we can see what's broken
                await self._storage_backend.upsert_session(
                    session_id=session_id,
                    transport_session_id=transport_session_id,
                    repo_root=None,  # Will be set later by set_project
                    mode="sentinel",  # Default mode
                )

            return session_id

    @staticmethod
    def derive_scoped_reuse_key(repo_root: str, project_name: Optional[str]) -> str:
        normalized_repo_root = str(Path(repo_root).resolve())
        normalized_project = (project_name or "").strip() or "__prebinding__"
        return f"{normalized_repo_root}:{normalized_project}"

    async def cache_project_binding(self, session_id: str, project_name: str) -> None:
        """Cache project binding for this session.

        Args:
            session_id: The stable_session_id from ExecutionContext
            project_name: Project name to cache
        """
        if not session_id or not project_name:
            return
        async with self._lock:
            self._session_projects[session_id] = project_name

    async def get_cached_project(self, session_id: str) -> Optional[str]:
        """Get cached project for this session.

        Args:
            session_id: The stable_session_id from ExecutionContext

        Returns:
            Cached project name or None if not cached
        """
        if not session_id:
            return None
        async with self._lock:
            return self._session_projects.get(session_id)

    async def get_cached_agent_session_id(self, identity_key: str) -> Optional[str]:
        """Return cached stable agent session id for a runtime identity key."""
        if not identity_key:
            return None
        async with self._lock:
            return self._stable_agent_sessions.get(identity_key)

    async def cache_agent_session_id(self, identity_key: str, session_id: str) -> None:
        """Cache stable agent session id to avoid repeated DB lookups per tool call."""
        if not identity_key or not session_id:
            return
        async with self._lock:
            self._stable_agent_sessions[identity_key] = session_id

    async def record_file_read(self, session_id: str, file_path: str) -> None:
        """Record that a file was read in this session. Called by read_file."""
        if not session_id or not file_path:
            return
        async with self._lock:
            self._files_read_in_session[session_id].add(file_path)

    async def has_file_been_read(self, session_id: str, file_path: str) -> bool:
        """Check if a file was read in this session. Called by edit_file."""
        if not session_id or not file_path:
            return False
        async with self._lock:
            return file_path in self._files_read_in_session.get(session_id, set())

    async def cleanup_session(self, session_id: str) -> None:
        """Remove session from all caches. Called by session cleanup task."""
        if not session_id:
            return
        async with self._lock:
            stale_transport_ids = [
                transport_id
                for transport_id, stable_id in self._transport_sessions.items()
                if stable_id == session_id or transport_id == session_id
            ]
            for transport_id in stale_transport_ids:
                self._transport_sessions.pop(transport_id, None)
            self._session_projects.pop(session_id, None)
            self._files_read_in_session.pop(session_id, None)
            stale_identity_keys = [
                identity_key
                for identity_key, stable_id in self._stable_agent_sessions.items()
                if stable_id == session_id
            ]
            for identity_key in stale_identity_keys:
                self._stable_agent_sessions.pop(identity_key, None)

    def _build_agent_identity(self, payload: Dict[str, Any]) -> AgentIdentity:
        agent_kind = os.environ.get("SCRIBE_AGENT_KIND", "other")
        model = os.environ.get("SCRIBE_AGENT_MODEL") or os.environ.get("CODEX_MODEL")
        sub_id = None
        display_name = None
        raw_identity = payload.get("agent_identity")
        if isinstance(raw_identity, dict):
            sub_id = raw_identity.get("sub_id") or raw_identity.get("sub_id".lower())
            display_name = raw_identity.get("display_name")
        return AgentIdentity(
            agent_kind=agent_kind,
            model=model,
            instance_id=self._process_instance_id,
            sub_id=sub_id,
            display_name=display_name,
        )

    async def build_execution_context(self, payload: Dict[str, Any]) -> ExecutionContext:
        repo_root = payload.get("repo_root")
        mode = payload.get("mode")
        intent = payload.get("intent") or ""
        affected = payload.get("affected_dev_projects") or []
        public_release = bool(payload.get("public_release"))

        if not repo_root or not isinstance(repo_root, str):
            raise ValueError("ExecutionContext missing required field: repo_root")
        if not Path(repo_root).is_absolute():
            raise ValueError("ExecutionContext repo_root must be an absolute path")

        # Server-side path mapping for remote clients (Docker/SSE).
        # No-op when the path exists on this filesystem (local dev).
        from scribe_mcp.config.paths import map_client_root

        scribe_user = payload.get("_scribe_user")
        repo_root, _ = map_client_root(repo_root, user=scribe_user)
        if mode not in {"sentinel", "project"}:
            raise ValueError("ExecutionContext mode must be 'sentinel' or 'project'")
        if not intent:
            raise ValueError("ExecutionContext missing required field: intent")
        if not isinstance(affected, list):
            raise ValueError("ExecutionContext affected_dev_projects must be a list")

        session_id = payload.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            raise ValueError("ExecutionContext session_id must be a string")
        trusted_session_id = bool(payload.get("_server_derived_session_id"))
        transport_session_id = payload.get("transport_session_id")
        if transport_session_id is not None and not isinstance(transport_session_id, str):
            raise ValueError("ExecutionContext transport_session_id must be a string")
        if public_release and session_id and not trusted_session_id:
            raise ValueError("ExecutionContext session_id is server-owned in public_release")
        has_transport_session = bool(transport_session_id)
        has_stable_scope_identity = bool(payload.get("stable_session_id"))
        if has_transport_session and (
            not session_id or (not trusted_session_id and not has_stable_scope_identity)
        ):
            if public_release and not str(transport_session_id).startswith("process:"):
                raise ValueError(
                    "ExecutionContext requires trusted runtime-derived transport_session_id in public_release"
                )
            session_id = await self.get_or_create_session_id(transport_session_id)
        elif not session_id:
            raise ValueError("ExecutionContext requires transport_session_id or session_id")
        execution_id = str(uuid.uuid4())
        timestamp_utc = _utc_now_iso()

        sentinel_day = None
        if mode == "sentinel":
            sentinel_day = timestamp_utc.split("T", 1)[0]

        agent_identity = self._build_agent_identity(payload)

        resolved_scope = build_resolved_scope(payload)

        return ExecutionContext(
            repo_root=repo_root,
            mode=mode,
            session_id=session_id,
            execution_id=execution_id,
            agent_identity=agent_identity,
            intent=intent,
            timestamp_utc=timestamp_utc,
            affected_dev_projects=[str(item) for item in affected],
            sentinel_day=sentinel_day,
            transport_session_id=transport_session_id,
            stable_session_id=payload.get("stable_session_id"),  # NEW - pass through stable session
            resolved_scope=resolved_scope,
            session_reuse_status=payload.get("session_reuse_status"),
            session_reuse_scope=payload.get("session_reuse_scope")
            or payload.get("scoped_reuse_key")
            or self.derive_scoped_reuse_key(repo_root, payload.get("project_name")),
            bug_id=payload.get("bug_id"),
            security_id=payload.get("security_id"),
            parent_execution_id=payload.get("parent_execution_id"),
            toolchain=payload.get("toolchain"),
            authoritative_session_key=resolved_scope.authoritative_session_key,
        )

    def set_current(self, context: ExecutionContext) -> contextvars.Token:
        return _CURRENT_CONTEXT.set(context)

    def reset(self, token: contextvars.Token) -> None:
        _CURRENT_CONTEXT.reset(token)

    def get_current(self) -> Optional[ExecutionContext]:
        return _CURRENT_CONTEXT.get()


def get_current_execution_context() -> Optional[ExecutionContext]:
    """Return the request-local execution context bound via contextvar."""
    return _CURRENT_CONTEXT.get()


def resolve_bootstrap_execution_context(
    app_state: Any,
    *,
    recovery_mode: Optional[str] = None,
) -> tuple[Optional[ExecutionContext], Mapping[str, Any]]:
    """Resolve legacy app-state context only when explicitly requested.

    Ordinary runtime behavior must fail closed and avoid app-state fallback.
    """
    selected_mode = str(recovery_mode or "none").strip().lower()
    if selected_mode not in {"bootstrap_app_state", "compat_all"}:
        return None, {
            "resolution_source": "unresolved",
            "trust_level": "anonymous",
            "fallback_used": False,
            "fallback_chain": [],
        }

    candidate = getattr(app_state, "execution_context", None)
    if not isinstance(candidate, ExecutionContext):
        return None, {
            "resolution_source": "unresolved",
            "trust_level": "anonymous",
            "fallback_used": False,
            "fallback_chain": [],
        }

    fallback_chain = ["bootstrap_app_state"]
    downgraded_scope = candidate.resolved_scope
    if downgraded_scope is None:
        downgraded_scope = ResolvedScope(
            transport_session_id=candidate.transport_session_id,
            stable_session_id=candidate.stable_session_id,
            agent_session_id=getattr(candidate.resolved_scope, "agent_session_id", None)
            if candidate.resolved_scope
            else None,
            repo_root=candidate.repo_root,
            project_name=None,
            scoped_reuse_key=None,
            resolution_source="bootstrap_app_state",
            trust_level="inferred",
            provenance=ScopeProvenance(
                transport_session_id="inferred",
                stable_session_id="inferred",
                agent_session_id="inferred",
                repo_root="inferred",
                project_name="anonymous",
            ),
            authoritative_session_key=candidate.authoritative_session_key
            or candidate.stable_session_id
            or candidate.session_id,
        )
    else:
        downgraded_scope = replace(
            downgraded_scope,
            resolution_source="bootstrap_app_state",
            trust_level="inferred",
            provenance=ScopeProvenance(
                transport_session_id="inferred",
                stable_session_id="inferred",
                agent_session_id="inferred",
                repo_root="inferred",
                project_name="anonymous",
            ),
        )

    return replace(candidate, resolved_scope=downgraded_scope), {
        "resolution_source": "bootstrap_app_state",
        "trust_level": "inferred",
        "fallback_used": True,
        "fallback_chain": fallback_chain,
    }
