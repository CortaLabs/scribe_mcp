"""Session-domain operations for the SQLite storage backend."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from scribe_mcp.storage.base import ConflictError


AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchOne = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncInitialise = Callable[[], Awaitable[None]]


async def upsert_agent_session(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    agent_id: str,
    session_id: str,
    metadata: Optional[Dict[str, Any]],
) -> None:
    await initialise_fn()
    _ = metadata
    identity_string = f"{agent_id}:{session_id}:legacy"
    identity_key = hashlib.sha256(identity_string.encode()).hexdigest()
    async with write_lock:
        await execute_fn(
            """
            INSERT INTO agent_sessions (session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key)
            VALUES (?, ?, ?, ?, 'legacy', 'project', 'legacy')
            ON CONFLICT(session_id) DO UPDATE SET
                last_active_at = CURRENT_TIMESTAMP;
            """,
            (session_id, identity_key, agent_id, agent_id),
        )


async def upsert_session(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    session_id: str,
    transport_session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    repo_root: Optional[str] = None,
    mode: Optional[str] = None,
) -> None:
    await initialise_fn()
    mode_value = mode if mode in ("sentinel", "project") else "sentinel"
    async with write_lock:
        try:
            await execute_fn(
                """
                INSERT INTO scribe_sessions (
                    session_id,
                    transport_session_id,
                    agent_id,
                    repo_root,
                    mode,
                    started_at,
                    last_active_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    transport_session_id = COALESCE(excluded.transport_session_id, scribe_sessions.transport_session_id),
                    agent_id = COALESCE(excluded.agent_id, scribe_sessions.agent_id),
                    repo_root = COALESCE(excluded.repo_root, scribe_sessions.repo_root),
                    mode = excluded.mode,
                    last_active_at = CURRENT_TIMESTAMP;
                """,
                (session_id, transport_session_id, agent_id, repo_root, mode_value),
            )
        except sqlite3.IntegrityError as exc:
            if "idx_scribe_sessions_transport" in str(exc) or "transport_session_id" in str(exc):
                raise ConflictError(
                    "transport_session_id collision detected; refusing ambiguous session binding"
                ) from exc
            raise


async def set_session_mode(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    session_id: str,
    mode: str,
) -> None:
    await initialise_fn()
    if mode not in ("sentinel", "project"):
        return
    async with write_lock:
        await execute_fn(
            "UPDATE scribe_sessions SET mode = ?, last_active_at = CURRENT_TIMESTAMP WHERE session_id = ?;",
            (mode, session_id),
        )


async def get_session_mode(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    session_id: str,
) -> Optional[str]:
    await initialise_fn()
    row = await fetchone_fn(
        "SELECT mode FROM scribe_sessions WHERE session_id = ?;",
        (session_id,),
    )
    if row and row["mode"]:
        return row["mode"]
    return None


async def set_session_project(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    session_id: str,
    project_name: Optional[str],
) -> None:
    await initialise_fn()
    async with write_lock:
        try:
            await execute_fn(
                """
                INSERT INTO session_projects (session_id, project_name, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    project_name = excluded.project_name,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                (session_id, project_name),
            )
        except sqlite3.IntegrityError as exc:
            if "session_projects.session_id requires a live scribe_sessions row" in str(exc):
                raise ConflictError(
                    f"Cannot bind project for unknown session_id={session_id!r}"
                ) from exc
            raise


async def get_session_project(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    session_id: str,
) -> Optional[str]:
    await initialise_fn()
    row = await fetchone_fn(
        "SELECT project_name FROM session_projects WHERE session_id = ?;",
        (session_id,),
    )
    if row and row["project_name"]:
        return row["project_name"]
    return None


async def get_session_by_transport(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    transport_session_id: str,
) -> Optional[Dict[str, Any]]:
    await initialise_fn()
    row = await fetchone_fn(
        """
        WITH matches AS (
            SELECT session_id, transport_session_id, agent_id, repo_root, mode
            FROM scribe_sessions
            WHERE transport_session_id = ?
              AND EXISTS (
                  SELECT 1
                  FROM agent_sessions
                  WHERE agent_sessions.session_id = scribe_sessions.session_id
                    AND (agent_sessions.expires_at IS NULL OR agent_sessions.expires_at > CURRENT_TIMESTAMP)
              )
            ORDER BY last_active_at DESC
            LIMIT 2
        )
        SELECT session_id, transport_session_id, agent_id, repo_root, mode
        FROM matches
        WHERE (SELECT COUNT(*) FROM matches) = 1
        LIMIT 1;
        """,
        (transport_session_id,),
    )
    if not row:
        return None
    return {
        "session_id": row["session_id"],
        "transport_session_id": row["transport_session_id"],
        "agent_id": row["agent_id"],
        "repo_root": row["repo_root"],
        "mode": row["mode"],
    }


async def upsert_agent_recent_project(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    agent_id: str,
    project_name: str,
) -> None:
    await initialise_fn()
    async with write_lock:
        await execute_fn(
            """
            INSERT INTO agent_recent_projects (agent_id, project_name, last_access_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(agent_id, project_name) DO UPDATE SET
                last_access_at = CURRENT_TIMESTAMP;
            """,
            (agent_id, project_name),
        )


async def heartbeat_session(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    session_id: str,
) -> None:
    await initialise_fn()
    async with write_lock:
        await execute_fn(
            """
            UPDATE agent_sessions
            SET last_active_at = CURRENT_TIMESTAMP
            WHERE session_id = ?;
            """,
            (session_id,),
        )


async def end_session(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    session_id: str,
) -> None:
    await initialise_fn()
    async with write_lock:
        await execute_fn(
            """
            UPDATE agent_sessions
            SET expires_at = CURRENT_TIMESTAMP, last_active_at = CURRENT_TIMESTAMP
            WHERE session_id = ?;
            """,
            (session_id,),
        )
        await execute_fn(
            """
            UPDATE scribe_sessions
            SET transport_session_id = NULL, last_active_at = CURRENT_TIMESTAMP
            WHERE session_id = ?;
            """,
            (session_id,),
        )


async def get_agent_project(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    agent_id: str,
) -> Optional[Dict[str, Any]]:
    await initialise_fn()
    return await _fetch_agent_project(fetchone_fn=fetchone_fn, agent_id=agent_id)


async def _fetch_agent_project(
    *,
    fetchone_fn: AsyncFetchOne,
    agent_id: str,
) -> Optional[Dict[str, Any]]:
    row = await fetchone_fn(
        """
        SELECT agent_id, project_name, version, updated_at, updated_by, session_id
        FROM agent_projects
        WHERE agent_id = ?;
        """,
        (agent_id,),
    )
    if not row:
        return None
    return {
        "agent_id": row["agent_id"],
        "project_name": row["project_name"],
        "version": row["version"],
        "updated_at": row["updated_at"],
        "updated_by": row["updated_by"],
        "session_id": row["session_id"],
    }


async def set_agent_project(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    agent_id: str,
    project_name: Optional[str],
    expected_version: Optional[int],
    updated_by: str,
    session_id: str,
) -> Dict[str, Any]:
    await initialise_fn()
    async with write_lock:
        if expected_version is not None:
            row = await fetchone_fn(
                """
                UPDATE agent_projects
                SET project_name = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP,
                    updated_by = ?, session_id = ?
                WHERE agent_id = ? AND version = ?
                RETURNING agent_id, project_name, version, updated_at, updated_by, session_id;
                """,
                (project_name, updated_by, session_id, agent_id, expected_version),
            )
            if not row:
                raise ConflictError(
                    f"Version conflict for agent {agent_id}: expected version {expected_version}"
                )
            return {
                "agent_id": row["agent_id"],
                "project_name": row["project_name"],
                "version": row["version"],
                "updated_at": row["updated_at"],
                "updated_by": row["updated_by"],
                "session_id": row["session_id"],
            }

        await execute_fn(
            """
            INSERT INTO agent_projects (agent_id, project_name, version, updated_by, session_id)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                project_name = excluded.project_name,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = excluded.updated_by,
                session_id = excluded.session_id;
            """,
            (agent_id, project_name, updated_by, session_id),
        )

    result = await _fetch_agent_project(fetchone_fn=fetchone_fn, agent_id=agent_id)
    return result or {}


async def update_session_activity(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    session_id: str,
    tool_name: str,
    timestamp: str,
) -> None:
    await initialise_fn()
    row = await fetchone_fn(
        "SELECT recent_tools, session_started_at FROM agent_sessions WHERE session_id = ?",
        (session_id,),
    )
    if not row:
        return

    recent_tools = json.loads(row["recent_tools"]) if row["recent_tools"] else []
    recent_tools.insert(0, tool_name)
    recent_tools = recent_tools[:10]
    session_started = row["session_started_at"] or timestamp

    async with write_lock:
        await execute_fn(
            """UPDATE agent_sessions
               SET recent_tools = ?, last_activity_at = ?, session_started_at = ?
               WHERE session_id = ?""",
            (json.dumps(recent_tools), timestamp, session_started, session_id),
        )


async def get_session_activity(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    await initialise_fn()
    row = await fetchone_fn(
        "SELECT recent_tools, session_started_at, last_activity_at FROM agent_sessions WHERE session_id = ?",
        (session_id,),
    )
    if not row:
        return None
    return {
        "recent_tools": json.loads(row["recent_tools"]) if row["recent_tools"] else [],
        "session_started_at": row["session_started_at"],
        "last_activity_at": row["last_activity_at"],
    }


async def get_or_create_agent_session(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    identity_key: str,
    agent_name: str,
    agent_key: str,
    repo_root: str,
    mode: str,
    scope_key: str,
    ttl_hours: int = 24,
) -> str:
    await initialise_fn()
    async with write_lock:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        # Fast path: session already exists for this identity key.
        existing = await fetchone_fn(
            "SELECT session_id FROM agent_sessions WHERE identity_key = ?",
            (identity_key,),
        )
        if existing and existing["session_id"]:
            await execute_fn(
                """
                UPDATE agent_sessions
                SET last_active_at = CURRENT_TIMESTAMP,
                    expires_at = ?
                WHERE identity_key = ?
                """,
                (expires_at, identity_key),
            )
            return existing["session_id"]

        # Preferred path: single-statement upsert with RETURNING guarantees read-after-write.
        try:
            upsert_row = await fetchone_fn(
                """
                INSERT INTO agent_sessions
                (session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    last_active_at = CURRENT_TIMESTAMP,
                    expires_at = excluded.expires_at
                RETURNING session_id;
                """,
                (
                    str(uuid.uuid4()),
                    identity_key,
                    agent_name,
                    agent_key,
                    repo_root,
                    mode,
                    scope_key,
                    expires_at,
                ),
            )
            if upsert_row and upsert_row["session_id"]:
                return upsert_row["session_id"]
        except sqlite3.OperationalError:
            # Older SQLite runtimes may not support RETURNING. Fall back below.
            pass

        # Compatibility fallback: insert/update/select triplet.
        new_session_id = str(uuid.uuid4())
        await execute_fn(
            """
            INSERT OR IGNORE INTO agent_sessions
            (session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (new_session_id, identity_key, agent_name, agent_key, repo_root, mode, scope_key, expires_at),
        )

        await execute_fn(
            """
            UPDATE agent_sessions
            SET last_active_at = CURRENT_TIMESTAMP,
                expires_at = ?
            WHERE identity_key = ?
            """,
            (expires_at, identity_key),
        )

        row = await fetchone_fn(
            "SELECT session_id FROM agent_sessions WHERE identity_key = ?",
            (identity_key,),
        )
        if row and row["session_id"]:
            return row["session_id"]

        # Last-resort recovery: identity row missing, so pick most recent session
        # with same agent/repo/scope tuple. This keeps tool calls alive even when
        # identity-key rows were pruned or partially migrated.
        recovery = await fetchone_fn(
            """
            SELECT session_id
            FROM agent_sessions
            WHERE agent_key = ? AND repo_root = ? AND mode = ? AND scope_key = ?
            ORDER BY last_active_at DESC
            LIMIT 1
            """,
            (agent_key, repo_root, mode, scope_key),
        )
        if recovery and recovery["session_id"]:
            return recovery["session_id"]

        raise RuntimeError(
            f"Failed to retrieve session for identity_key: {identity_key} "
            f"(agent_key={agent_key}, mode={mode}, scope_key={scope_key})"
        )


async def cleanup_expired_sessions(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    batch_size: int = 100,
) -> int:
    await initialise_fn()
    async with write_lock:
        cursor = await execute_fn(
            """
            DELETE FROM agent_sessions
            WHERE session_id IN (
                SELECT session_id FROM agent_sessions
                WHERE expires_at < CURRENT_TIMESTAMP
                LIMIT ?
            )
            """,
            (batch_size,),
        )
        return cursor.rowcount if cursor else 0
