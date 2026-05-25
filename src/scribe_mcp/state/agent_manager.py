"""Agent-scoped project context manager with session lease management."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from scribe_mcp.state.manager import StateManager

logger = logging.getLogger(__name__)


STALE_SESSION_REASON_NO_ACTIVE = "no_active_session"
STALE_SESSION_REASON_MISMATCH = "session_mismatch"
STALE_SESSION_REASON_EXPIRED = "session_lease_expired"


class SessionLeaseExpired(Exception):
    """Raised when a session lease is stale for a typed reason."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        agent_id: str,
        session_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.agent_id = agent_id
        self.session_id = session_id


class AgentContextManager:
    """
    Coordinates agent-scoped project context between database (source of truth)
    and JSON state (fast cache for UI continuity).

    Features:
    - Session management with TTL (15 minute leases)
    - Optimistic concurrency control for project switching
    - JSON state mirroring for warm UI state
    - Conflict detection and resolution
    """

    def __init__(self, storage, state_manager: StateManager):
        self.storage = storage
        self.state_manager = state_manager
        self._session_leases: Dict[str, tuple[str, datetime]] = {}  # agent_id -> (session_id, expires_at)
        self._lease_lock = asyncio.Lock()
        self._session_ttl_minutes = 15  # 15 minute session leases

    def _is_postgres_storage(self) -> bool:
        return self.storage.__class__.__module__.startswith("scribe_mcp.storage.postgres")

    async def start_session(
        self,
        agent_id: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start a new agent session, optionally using provided stable session_id.

        Args:
            agent_id: Unique identifier for the agent
            session_id: Optional stable session ID (if not provided, generates UUID)
            metadata: Optional session metadata

        Returns:
            Session ID for tracking
        """
        # Backward compatibility: historical callsites passed metadata as the
        # second positional argument.
        if isinstance(session_id, dict) and metadata is None:
            metadata = session_id
            session_id = None

        # Use provided stable session if available, otherwise generate UUID
        if not session_id:
            session_id = str(uuid.uuid4())

        # Store session in database
        await self.storage.upsert_agent_session(agent_id, session_id, metadata)

        # Cache session lease
        expires_at = utcnow() + timedelta(minutes=self._session_ttl_minutes)
        async with self._lease_lock:
            self._session_leases[agent_id] = (session_id, expires_at)

        # Log session start
        await self.log_agent_event(
            agent_id=agent_id,
            session_id=session_id,
            event_type="session_started",
            to_project="",  # No project yet
            metadata={"session_ttl_minutes": self._session_ttl_minutes, "metadata": metadata}
        )

        # Mirror to JSON state for UI continuity
        await self._mirror_session_to_json_state(agent_id, session_id, metadata)

        return session_id

    async def set_current_project(
        self,
        agent_id: str,
        project_name: Optional[str],
        session_id: str,
        expected_version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Set the current project for an agent with optimistic concurrency control.

        Args:
            agent_id: Agent identifier
            project_name: Project name (None to clear)
            session_id: Valid session ID
            expected_version: Expected version for optimistic locking

        Returns:
            Updated agent project record

        Raises:
            SessionLeaseExpired: If session lease is expired
            ConflictError: If version conflict occurs
        """
        # Validate session lease
        await self._validate_session_lease(agent_id, session_id)

        # Get previous project for audit logging
        previous_project = None
        try:
            current = await self.storage.get_agent_project(agent_id)
            if current and current.get("project_name"):
                previous_project = current["project_name"]
        except Exception:
            pass

        # Set in database (source of truth)
        try:
            result_raw = await self.storage.set_agent_project(
                agent_id=agent_id,
                project_name=project_name,
                expected_version=expected_version,
                updated_by=agent_id,
                session_id=session_id
            )
            if isinstance(result_raw, dict):
                result = dict(result_raw)
            else:
                logger.warning(
                    "storage.set_agent_project returned non-dict result (%s) for agent '%s'; using fallback payload.",
                    type(result_raw).__name__,
                    agent_id,
                )
                result = {}

            result.setdefault("agent_id", agent_id)
            result.setdefault("project_name", project_name)
            result.setdefault("version", 1)
            result.setdefault("updated_by", agent_id)
            result.setdefault("session_id", session_id)

            # Log successful project change
            event_type = "project_switched" if previous_project and previous_project != project_name else "project_set"
            await self.log_agent_event(
                agent_id=agent_id,
                session_id=session_id,
                event_type=event_type,
                from_project=previous_project,
                to_project=project_name,
                expected_version=expected_version,
                actual_version=result.get("version"),
                success=True,
                metadata={"updated_by": agent_id}
            )

            # Mirror to JSON state (non-authoritative cache)
            await self._mirror_project_to_json_state(agent_id, result)

            return result

        except Exception as e:
            # Log failed project change
            await self.log_agent_event(
                agent_id=agent_id,
                session_id=session_id,
                event_type="conflict_detected",
                from_project=previous_project,
                to_project=project_name,
                expected_version=expected_version,
                success=False,
                error_message=str(e),
                metadata={"error_type": type(e).__name__}
            )
            raise

    async def get_current_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get an agent's current project from database (source of truth).

        Args:
            agent_id: Agent identifier

        Returns:
            Agent project record or None
        """
        return await self.storage.get_agent_project(agent_id)

    async def heartbeat_session(self, session_id: str) -> None:
        """
        Update session activity timestamp.

        Args:
            session_id: Session ID to update
        """
        await self.storage.heartbeat_session(session_id)

        # Update local lease cache
        async with self._lease_lock:
            for agent_id, (cached_session_id, expires_at) in self._session_leases.items():
                if cached_session_id == session_id:
                    # Extend lease
                    new_expires_at = utcnow() + timedelta(minutes=self._session_ttl_minutes)
                    self._session_leases[agent_id] = (session_id, new_expires_at)
                    break

    async def end_session(self, agent_id: str, session_id: str) -> None:
        """
        End an agent session.

        Args:
            agent_id: Agent identifier
            session_id: Session ID to end
        """
        # Get current project for audit logging
        current_project = None
        try:
            project = await self.storage.get_agent_project(agent_id)
            if project and project.get("project_name"):
                current_project = project["project_name"]
        except Exception:
            pass

        # Package 3.1 quality handoff preflight: block clean session close when managed-doc blockers remain.
        try:
            if project and project.get("docs"):
                from scribe_mcp.readiness import collect_managed_doc_quality_blockers

                blocker_result = collect_managed_doc_quality_blockers(project)
                total_blockers = int(blocker_result.get("total_blocker_count", 0))
                if total_blockers > 0:
                    raise ValueError(
                        f"SESSION_END_BLOCKED_BY_DOC_QUALITY: {total_blockers} blocking managed-doc warning(s) remain; resolve quality blockers before ending session."
                    )
        except ValueError:
            raise
        except Exception:
            logger.debug("Session teardown quality preflight skipped due to non-fatal check error", exc_info=True)

        # Mark session as expired in database.
        await self.storage.end_session(session_id)

        # Revoke persisted session-to-project bindings so reconnect cannot inherit context.
        try:
            if hasattr(self.storage, "set_session_project"):
                await self.storage.set_session_project(session_id, None)
        except Exception:
            logger.debug("Failed clearing session project binding for %s", session_id, exc_info=True)

        # Clear agent->project binding only when this session owns the persisted row.
        try:
            if hasattr(self.storage, "get_agent_project") and hasattr(self.storage, "set_agent_project"):
                agent_project = await self.storage.get_agent_project(agent_id)
                if (
                    isinstance(agent_project, dict)
                    and str(agent_project.get("session_id") or "") == str(session_id)
                    and agent_project.get("project_name")
                ):
                    await self.storage.set_agent_project(
                        agent_id,
                        None,
                        agent_project.get("version"),
                        "session_teardown",
                        session_id,
                    )
        except Exception:
            logger.debug("Failed clearing agent project binding for %s", agent_id, exc_info=True)

        # Log session end
        await self.log_agent_event(
            agent_id=agent_id,
            session_id=session_id,
            event_type="session_ended",
            to_project=current_project or "",
            metadata={"session_end_reason": "explicit_end"}
        )

        # Remove from local lease cache
        async with self._lease_lock:
            if agent_id in self._session_leases:
                cached_session_id, _ = self._session_leases[agent_id]
                if cached_session_id == session_id:
                    del self._session_leases[agent_id]

        # Remove stale runtime caches tied to this session.
        try:
            from scribe_mcp import server as server_module

            router_ctx = getattr(server_module, "router_context_manager", None)
            if router_ctx and hasattr(router_ctx, "cleanup_session"):
                await router_ctx.cleanup_session(session_id)
        except Exception:
            logger.debug("Failed clearing runtime session cache for %s", session_id, exc_info=True)

    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired sessions and leases.

        Returns:
            Number of sessions cleaned up
        """
        now = utcnow()
        cleaned_count = 0

        async with self._lease_lock:
            expired_agents = []
            for agent_id, (session_id, expires_at) in self._session_leases.items():
                if expires_at < now:
                    expired_agents.append((agent_id, session_id))

            for agent_id, session_id in expired_agents:
                await self.storage.end_session(session_id)
                del self._session_leases[agent_id]
                cleaned_count += 1

        return cleaned_count

    async def _validate_session_lease(self, agent_id: str, session_id: str) -> None:
        """
        Validate that a session lease is still active.

        Args:
            agent_id: Agent identifier
            session_id: Session ID to validate

        Raises:
            SessionLeaseExpired: If lease is expired or invalid
        """
        async with self._lease_lock:
            if agent_id not in self._session_leases:
                raise SessionLeaseExpired(
                    f"No active session for agent {agent_id}",
                    reason=STALE_SESSION_REASON_NO_ACTIVE,
                    agent_id=agent_id,
                    session_id=session_id,
                )

            cached_session_id, expires_at = self._session_leases[agent_id]
            if cached_session_id != session_id:
                raise SessionLeaseExpired(
                    f"Session ID mismatch for agent {agent_id}",
                    reason=STALE_SESSION_REASON_MISMATCH,
                    agent_id=agent_id,
                    session_id=session_id,
                )

            if expires_at < utcnow():
                raise SessionLeaseExpired(
                    f"Session lease expired for agent {agent_id}",
                    reason=STALE_SESSION_REASON_EXPIRED,
                    agent_id=agent_id,
                    session_id=session_id,
                )

    async def _mirror_session_to_json_state(self, agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]) -> None:
        """
        Mirror session information to JSON state for UI continuity.

        This is a no-op — session data is already persisted in the database
        by upsert_agent_session(). The previous implementation loaded all
        projects and re-persisted them unchanged, causing O(N) remote calls
        in CLIENT mode for zero benefit.
        """
        pass

    async def _mirror_project_to_json_state(self, agent_id: str, agent_project: Dict[str, Any]) -> None:
        """
        Mirror agent project to JSON state for UI continuity.

        Args:
            agent_id: Agent identifier
            agent_project: Agent project record
        """
        # Update JSON state with minimal information for UI continuity
        state = await self.state_manager.load()

        # Note: JSON state is now just a cache/warm-start mechanism
        # The authoritative source of truth is the database

        # Update version, timestamp, and tracking info
        # This keeps the existing UI working while transitioning to agent-scoped context

    async def log_agent_event(
        self,
        agent_id: str,
        session_id: str,
        event_type: str,
        to_project: str,
        from_project: Optional[str] = None,
        expected_version: Optional[int] = None,
        actual_version: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an agent project event to the audit trail.

        Args:
            agent_id: Agent identifier
            session_id: Session identifier
            event_type: Type of event ('project_set', 'project_switched', 'conflict_detected', etc.)
            to_project: Target project name
            from_project: Source project name (for switches)
            expected_version: Expected version for optimistic concurrency
            actual_version: Actual version after operation
            success: Whether the operation succeeded
            error_message: Error message if operation failed
            metadata: Additional event metadata
        """
        try:
            import json

            event_data = {
                "agent_id": agent_id,
                "session_id": session_id,
                "event_type": event_type,
                "from_project": from_project,
                "to_project": to_project,
                "expected_version": expected_version,
                "actual_version": actual_version,
                "success": success,
                "error_message": error_message,
                "metadata": json.dumps(metadata or {}),
                "created_at": utcnow(),
            }

            # Store in database if available
            try:
                if hasattr(self.storage, "_execute"):
                    if self._is_postgres_storage():
                        query = """
                            INSERT INTO agent_project_events (
                                agent_id, session_id, event_type, from_project, to_project,
                                expected_version, actual_version, success, error_message, metadata, created_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
                        """
                        await self.storage._execute(
                            query,
                            agent_id,
                            session_id,
                            event_type,
                            from_project,
                            to_project,
                            expected_version,
                            actual_version,
                            success,
                            error_message,
                            event_data["metadata"],
                            event_data["created_at"],
                        )
                    else:
                        query = """
                            INSERT INTO agent_project_events (
                                agent_id, session_id, event_type, from_project, to_project,
                                expected_version, actual_version, success, error_message, metadata, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """
                        await self.storage._execute(
                            query,
                            (
                                agent_id,
                                session_id,
                                event_type,
                                from_project,
                                to_project,
                                expected_version,
                                actual_version,
                                success,
                                error_message,
                                event_data["metadata"],
                                event_data["created_at"],
                            ),
                        )
            except Exception as db_error:
                # Database audit logging failed, but don't fail the operation
                logger.warning("Database audit logging failed: %s", db_error)

        except Exception as e:
            # Don't fail the operation if audit logging fails
            logger.warning("Failed to log agent event: %s", e)

    async def get_agent_events(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get agent project events from the audit trail.

        Args:
            agent_id: Filter by agent ID (optional)
            event_type: Filter by event type (optional)
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        try:
            where_clauses = []

            if self._is_postgres_storage() and hasattr(self.storage, "_fetch"):
                params: list[Any] = []

                if agent_id:
                    where_clauses.append(f"agent_id = ${len(params) + 1}")
                    params.append(agent_id)

                if event_type:
                    where_clauses.append(f"event_type = ${len(params) + 1}")
                    params.append(event_type)

                where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
                params.append(limit)
                query = f"""
                    SELECT id, agent_id, session_id, event_type, from_project, to_project,
                           expected_version, actual_version, success, error_message, metadata, created_at
                    FROM agent_project_events
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT ${len(params)}
                """
                rows = await self.storage._fetch(query, *params)
            else:
                params = []
                if agent_id:
                    where_clauses.append("agent_id = ?")
                    params.append(agent_id)

                if event_type:
                    where_clauses.append("event_type = ?")
                    params.append(event_type)

                where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
                query = f"""
                    SELECT id, agent_id, session_id, event_type, from_project, to_project,
                           expected_version, actual_version, success, error_message, metadata, created_at
                    FROM agent_project_events
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                params.append(limit)
                rows = await self.storage._fetchall(query, tuple(params))

            return [dict(row) for row in rows]

        except Exception as e:
            logger.warning("Failed to retrieve agent events: %s", e)
            return []


# Global instance for server integration
_agent_context_manager: Optional[AgentContextManager] = None


def get_agent_context_manager() -> AgentContextManager:
    """Get the global agent context manager instance."""
    global _agent_context_manager
    if _agent_context_manager is None:
        raise RuntimeError("AgentContextManager not initialized. Call init_agent_context_manager first.")
    return _agent_context_manager


def init_agent_context_manager(storage, state_manager: StateManager) -> AgentContextManager:
    """
    Initialize the global agent context manager.

    Args:
        storage: Storage backend instance
        state_manager: State manager instance

    Returns:
        AgentContextManager instance
    """
    global _agent_context_manager
    _agent_context_manager = AgentContextManager(storage, state_manager)
    return _agent_context_manager


async def migrate_legacy_state(state_manager: StateManager, storage) -> None:
    """
    One-time migration from global JSON state to agent-scoped DB context.

    Args:
        state_manager: JSON state manager
        storage: Database storage backend
    """
    # Best-effort check: if the Scribe agent already has a project record, treat migration as done.
    # Avoid direct SQL here; use the storage API surface so backends can vary.
    try:
        existing = await storage.get_agent_project("Scribe")
        if existing and existing.get("project_name"):
            return
    except Exception:
        # Table may not exist yet (first run) or backend may not support agent-scoped state.
        pass

    # Get legacy state
    legacy_state = await state_manager.load()
    if legacy_state.current_project:
        # Create default agent session for "Scribe"
        manager = init_agent_context_manager(storage, state_manager)

        session_id = await manager.start_session(
            "Scribe",
            metadata={
                "migrated": True,
                "legacy_project": legacy_state.current_project,
            },
        )

        # Create the legacy project in database if it doesn't exist
        try:
            # Try to get project data from legacy state
            project_data = legacy_state.projects.get(legacy_state.current_project)
            if project_data:
                await storage.upsert_project(
                    name=legacy_state.current_project,
                    repo_root=project_data.get("root", "/tmp/migrated"),
                    progress_log_path=project_data.get("progress_log", "/tmp/migrated/log.md")
                )
            else:
                # Create minimal project record
                await storage.upsert_project(
                    name=legacy_state.current_project,
                    repo_root="/tmp/migrated",
                    progress_log_path="/tmp/migrated/log.md"
                )
        except Exception as e:
            logger.warning("Failed to create legacy project in database: %s", e)

        # Migrate current project to Scribe agent
        try:
            await manager.set_current_project("Scribe", legacy_state.current_project, session_id)
        except Exception as e:
            logger.warning("Failed to migrate legacy project: %s", e)

        # Clear global current_project to avoid dual sources of truth
        await state_manager.set_current_project(None, None, agent_id="migration")

        logger.info("Migrated legacy project '%s' to agent 'Scribe'", legacy_state.current_project)


def utcnow() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)
