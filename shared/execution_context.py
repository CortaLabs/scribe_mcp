"""Router-owned execution context and session identity management."""

from __future__ import annotations

import asyncio
import contextvars
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


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
    bug_id: Optional[str] = None
    security_id: Optional[str] = None
    parent_execution_id: Optional[str] = None
    toolchain: Optional[str] = None


class RouterContextManager:
    """Owns router-generated session/execution identity and current context."""

    def __init__(self, storage_backend=None) -> None:
        self._lock = asyncio.Lock()
        self._transport_sessions: Dict[str, str] = {}  # Keep as performance cache
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

        if not repo_root or not isinstance(repo_root, str):
            raise ValueError("ExecutionContext missing required field: repo_root")
        if not Path(repo_root).is_absolute():
            raise ValueError("ExecutionContext repo_root must be an absolute path")
        if mode not in {"sentinel", "project"}:
            raise ValueError("ExecutionContext mode must be 'sentinel' or 'project'")
        if not intent:
            raise ValueError("ExecutionContext missing required field: intent")
        if not isinstance(affected, list):
            raise ValueError("ExecutionContext affected_dev_projects must be a list")

        session_id = payload.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            raise ValueError("ExecutionContext session_id must be a string")
        if not session_id:
            transport_session_id = payload.get("transport_session_id")
            if transport_session_id is not None and not isinstance(transport_session_id, str):
                raise ValueError("ExecutionContext transport_session_id must be a string")
            if not transport_session_id:
                raise ValueError("ExecutionContext requires transport_session_id or session_id")
            session_id = await self.get_or_create_session_id(transport_session_id)
        else:
            transport_session_id = payload.get("transport_session_id")
        execution_id = str(uuid.uuid4())
        timestamp_utc = _utc_now_iso()

        sentinel_day = None
        if mode == "sentinel":
            sentinel_day = timestamp_utc.split("T", 1)[0]

        agent_identity = self._build_agent_identity(payload)

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
            bug_id=payload.get("bug_id"),
            security_id=payload.get("security_id"),
            parent_execution_id=payload.get("parent_execution_id"),
            toolchain=payload.get("toolchain"),
        )

    def set_current(self, context: ExecutionContext) -> contextvars.Token:
        return _CURRENT_CONTEXT.set(context)

    def reset(self, token: contextvars.Token) -> None:
        _CURRENT_CONTEXT.reset(token)

    def get_current(self) -> Optional[ExecutionContext]:
        return _CURRENT_CONTEXT.get()
