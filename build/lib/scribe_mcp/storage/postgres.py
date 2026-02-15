"""PostgreSQL storage backend."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import asyncpg

from scribe_mcp.config.paths import db_init_sql
from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.utils.search import message_matches

POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 10
COMMAND_TIMEOUT_SECONDS = 30

SCHEMA_PATH = db_init_sql()


class PostgresStorage(StorageBackend):
    """Asyncpg-backed persistence."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.pool.Pool] = None
        self._pool_lock = asyncio.Lock()

    async def setup(self) -> None:
        await self._ensure_pool()
        await self._ensure_schema()

    async def close(self) -> None:
        async with self._pool_lock:
            if self._pool:
                await self._pool.close()
                self._pool = None

    async def upsert_project(
        self,
        *,
        name: str,
        repo_root: str,
        progress_log_path: str,
    ) -> ProjectRecord:
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops

        return await ops.upsert_project(
            pool,
            name=name,
            repo_root=repo_root,
            progress_log_path=progress_log_path,
        )

    async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops

        return await ops.fetch_project_by_name(pool, name=name)

    async def list_projects(self) -> List[ProjectRecord]:
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops

        return await ops.list_projects(pool)

    async def delete_project(self, name: str) -> bool:
        """Delete a project and all associated data."""
        pool = await self._ensure_pool()

        # Check if project exists first
        project = await self.fetch_project(name)
        if not project:
            return False

        # The actual database operations should be implemented in scribe_mcp.db.ops
        # For now, we'll add a placeholder that raises NotImplementedError
        # TODO: Implement delete_project in scribe_mcp.db.ops module
        raise NotImplementedError(
            "delete_project not yet implemented for PostgreSQL backend. "
            "Add implementation to scribe_mcp.db.ops module."
        )

    async def insert_entry(
        self,
        *,
        entry_id: str,
        project: ProjectRecord,
        ts,
        emoji: str,
        agent: Optional[str],
        message: str,
        meta: Optional[Dict[str, Any]],
        raw_line: str,
        sha256: str,
    ) -> None:
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops

        await ops.insert_entry(
            pool,
            entry_id=entry_id,
            project_id=project.id,
            ts=ts,
            emoji=emoji,
            agent=agent,
            message=message,
            meta=meta,
            raw_line=raw_line,
            sha256=sha256,
        )

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
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops

        await ops.record_doc_change(
            pool,
            project_id=project.id,
            doc=doc,
            section=section,
            action=action,
            agent=agent,
            metadata=metadata,
            sha_before=sha_before,
            sha_after=sha_after,
        )

    async def fetch_recent_entries(
        self,
        *,
        project: ProjectRecord,
        limit: int,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops

        return await ops.fetch_recent_entries(
            pool,
            project_id=project.id,
            limit=limit,
            filters=filters,
        )

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
    ) -> List[Dict[str, Any]]:
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops

        rows = await ops.query_entries(
            pool,
            project_id=project.id,
            limit=limit,
            start=start,
            end=end,
            agents=agents,
            emojis=emojis,
            meta_filters=meta_filters,
        )

        results: List[Dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            if not message_matches(
                entry.get("message"),
                message,
                mode=message_mode,
                case_sensitive=case_sensitive,
            ):
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    async def _ensure_pool(self) -> asyncpg.pool.Pool:
        async with self._pool_lock:
            if not self._pool:
                self._pool = await asyncpg.create_pool(
                    dsn=self._dsn,
                    min_size=POOL_MIN_SIZE,
                    max_size=POOL_MAX_SIZE,
                    command_timeout=COMMAND_TIMEOUT_SECONDS,
                )
        assert self._pool is not None
        return self._pool

    async def _ensure_schema(self) -> None:
        pool = await self._ensure_pool()
        if not SCHEMA_PATH.exists():
            return
        sql_text = await asyncio.to_thread(SCHEMA_PATH.read_text, encoding="utf-8")
        statements = [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]
        async with pool.acquire() as conn:
            for statement in statements:
                await conn.execute(statement)

    # Agent session and project context management methods
    async def upsert_agent_session(self, agent_id: str, session_id: str, metadata: Optional[Dict[str, Any]]) -> None:
        """Create or update an agent session."""
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops
        await ops.upsert_agent_session(pool, agent_id=agent_id, session_id=session_id, metadata=metadata)

    async def heartbeat_session(self, session_id: str) -> None:
        """Update session last_active_at timestamp."""
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops
        await ops.heartbeat_session(pool, session_id=session_id)

    async def end_session(self, session_id: str) -> None:
        """Mark a session as expired."""
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops
        await ops.end_session(pool, session_id=session_id)

    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent's current project with version info."""
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops
        return await ops.get_agent_project(pool, agent_id=agent_id)

    async def set_agent_project(self, agent_id: str, project_name: Optional[str], expected_version: Optional[int], updated_by: str, session_id: str) -> Dict[str, Any]:
        """Set an agent's current project with optimistic concurrency control."""
        pool = await self._ensure_pool()
        from scribe_mcp.db import ops
        return await ops.set_agent_project(
            pool,
            agent_id=agent_id,
            project_name=project_name,
            expected_version=expected_version,
            updated_by=updated_by,
            session_id=session_id
        )
