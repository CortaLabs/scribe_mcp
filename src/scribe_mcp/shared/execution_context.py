"""Router-owned execution context and session identity management."""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import hmac
import os
import secrets
import threading
import uuid
from dataclasses import dataclass, field as dataclass_field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, Mapping, Optional, Set

from scribe_mcp.mcp_adapter import ProtocolEra
from scribe_mcp.shared.session_scope import ResolvedScope, ScopeProvenance, build_resolved_scope
from scribe_mcp.storage.base import ConflictError


_CURRENT_CONTEXT: contextvars.ContextVar["ExecutionContext | None"] = contextvars.ContextVar(
    "scribe_execution_context",
    default=None,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_APPLICATION_IDENTITY_TTL = timedelta(hours=8)
_APPLICATION_IDENTITY_SECRET = secrets.token_bytes(32)
_PROCESS_START_NONCE = secrets.token_bytes(32)


@dataclass(frozen=True, slots=True)
class ApplicationIdentity:
    """Server-owned application identity, separate from MCP protocol sessions."""

    identity_key: str
    principal_id: str
    protocol_era: ProtocolEra
    transport: str
    expires_at: datetime
    revoked: bool = False
    application_handle: Optional[str] = dataclass_field(
        default=None,
        repr=False,
        compare=False,
    )


@dataclass(frozen=True, slots=True)
class _ApplicationIdentityRecord:
    identity: ApplicationIdentity


_APPLICATION_IDENTITIES: Dict[str, _ApplicationIdentityRecord] = {}
_STDIO_IDENTITIES: Dict[str, ApplicationIdentity] = {}
_APPLICATION_IDENTITIES_LOCK = threading.Lock()


def _identity_digest(value: str) -> str:
    return hmac.new(
        _APPLICATION_IDENTITY_SECRET,
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _application_identity_key(
    *,
    handle: str,
    principal_id: str,
    protocol_era: ProtocolEra,
    transport: str,
) -> str:
    material = "\0".join((handle, principal_id, protocol_era.value, transport))
    return _identity_digest(material)


def _validate_application_identity_inputs(
    *,
    principal_id: str,
    protocol_era: ProtocolEra,
    transport: str,
) -> tuple[str, ProtocolEra, str]:
    principal = str(principal_id or "").strip()
    if not principal:
        raise ValueError("authenticated principal_id is required")
    if not isinstance(protocol_era, ProtocolEra):
        raise TypeError("protocol_era must be ProtocolEra")
    normalized_transport = str(transport or "").strip()
    allowed = {
        ProtocolEra.MODERN: {"stdio", "streamable-http"},
        ProtocolEra.LEGACY: {"stdio", "http-sse"},
    }[protocol_era]
    if normalized_transport not in allowed:
        raise ValueError("transport is not valid for the selected protocol era")
    return principal, protocol_era, normalized_transport


def resolve_application_identity(
    *,
    principal_id: str,
    protocol_era: ProtocolEra,
    transport: str,
    supplied_handle: str | None,
    connection_id: str | None,
) -> ApplicationIdentity:
    """Mint or validate a principal-bound Scribe application identity.

    ``connection_id`` is a server-trusted minting signal, never identity
    material. Raw handles remain process-local and are absent from stored
    records and representations; only keyed one-way digests index the registry.
    """

    principal, era, normalized_transport = _validate_application_identity_inputs(
        principal_id=principal_id,
        protocol_era=protocol_era,
        transport=transport,
    )
    now = datetime.now(timezone.utc)

    if normalized_transport == "stdio":
        if supplied_handle:
            raise ValueError("stdio application identity does not accept a supplied handle")
        cache_key = _identity_digest(f"stdio\0{principal}\0{era.value}")
        with _APPLICATION_IDENTITIES_LOCK:
            existing = _STDIO_IDENTITIES.get(cache_key)
            if existing and not existing.revoked and existing.expires_at > now:
                return existing
            process_token = _PROCESS_START_NONCE.hex()
            identity = ApplicationIdentity(
                identity_key=_application_identity_key(
                    handle=process_token,
                    principal_id=principal,
                    protocol_era=era,
                    transport=normalized_transport,
                ),
                principal_id=principal,
                protocol_era=era,
                transport=normalized_transport,
                expires_at=now + _APPLICATION_IDENTITY_TTL,
            )
            _STDIO_IDENTITIES[cache_key] = identity
            return identity

    if supplied_handle is None:
        if not isinstance(connection_id, str) or not connection_id.strip():
            raise ValueError("missing Scribe application handle")
        raw_handle = secrets.token_urlsafe(32)
        identity = ApplicationIdentity(
            identity_key=_application_identity_key(
                handle=raw_handle,
                principal_id=principal,
                protocol_era=era,
                transport=normalized_transport,
            ),
            principal_id=principal,
            protocol_era=era,
            transport=normalized_transport,
            expires_at=now + _APPLICATION_IDENTITY_TTL,
            application_handle=raw_handle,
        )
        record_key = _identity_digest(f"handle\0{raw_handle}")
        with _APPLICATION_IDENTITIES_LOCK:
            _APPLICATION_IDENTITIES[record_key] = _ApplicationIdentityRecord(
                identity=replace(identity, application_handle=None)
            )
        return identity

    if not isinstance(supplied_handle, str) or not supplied_handle.strip():
        raise ValueError("missing Scribe application handle")
    record_key = _identity_digest(f"handle\0{supplied_handle}")
    with _APPLICATION_IDENTITIES_LOCK:
        record = _APPLICATION_IDENTITIES.get(record_key)
    if record is None:
        raise ValueError("unknown or caller-selected Scribe application handle")
    identity = record.identity
    if identity.revoked:
        raise ValueError("Scribe application handle is revoked")
    if identity.expires_at <= now:
        raise ValueError("Scribe application handle is expired")
    if not hmac.compare_digest(
        identity.principal_id.encode("utf-8"),
        principal.encode("utf-8"),
    ):
        raise ValueError("Scribe application handle principal mismatch")
    if identity.protocol_era is not era or identity.transport != normalized_transport:
        raise ValueError("Scribe application handle scope mismatch")
    return identity


def revoke_application_identity(identity_key: str) -> bool:
    """Revoke a process-local application identity by its one-way key."""

    normalized_key = str(identity_key or "").strip()
    if not normalized_key:
        return False
    with _APPLICATION_IDENTITIES_LOCK:
        for record_key, record in tuple(_APPLICATION_IDENTITIES.items()):
            if hmac.compare_digest(record.identity.identity_key, normalized_key):
                _APPLICATION_IDENTITIES[record_key] = _ApplicationIdentityRecord(
                    identity=replace(record.identity, revoked=True)
                )
                return True
        for cache_key, identity in tuple(_STDIO_IDENTITIES.items()):
            if hmac.compare_digest(identity.identity_key, normalized_key):
                _STDIO_IDENTITIES[cache_key] = replace(identity, revoked=True)
                return True
    return False


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
    application_identity: Optional[ApplicationIdentity] = None


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

            # TIER 3b: Persist to database immediately
            if self._storage_backend and hasattr(self._storage_backend, "upsert_session"):
                try:
                    await self._storage_backend.upsert_session(
                        session_id=session_id,
                        transport_session_id=transport_session_id,
                        repo_root=None,  # Will be set later by set_project
                        mode="sentinel",  # Default mode
                    )
                except ConflictError:
                    existing = await self._storage_backend.get_session_by_transport(transport_session_id)
                    if not existing or not existing.get("session_id"):
                        raise
                    session_id = str(existing["session_id"])

            self._transport_sessions[transport_session_id] = session_id

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
        application_identity_keys: list[str] = []
        async with self._lock:
            stale_transport_ids = [
                transport_id
                for transport_id, stable_id in self._transport_sessions.items()
                if stable_id == session_id or transport_id == session_id
            ]
            for transport_id in stale_transport_ids:
                self._transport_sessions.pop(transport_id, None)
                application_identity_keys.append(transport_id)
            self._session_projects.pop(session_id, None)
            self._files_read_in_session.pop(session_id, None)
            stale_identity_keys = [
                identity_key
                for identity_key, stable_id in self._stable_agent_sessions.items()
                if stable_id == session_id
            ]
            for identity_key in stale_identity_keys:
                self._stable_agent_sessions.pop(identity_key, None)
        for identity_key in application_identity_keys:
            revoke_application_identity(identity_key)

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
            application_identity=payload.get("application_identity")
            if isinstance(payload.get("application_identity"), ApplicationIdentity)
            else None,
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
