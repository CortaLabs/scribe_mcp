"""Support helpers for telemetry SQL operations."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.utils.time import utcnow


AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchOne = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchAll = Callable[[str, tuple[Any, ...] | tuple], Awaitable[List[Any]]]
AsyncInitialise = Callable[[], Awaitable[None]]
ConnectFn = Callable[[], sqlite3.Connection]


def ensure_tool_call_metadata_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tool_calls)").fetchall()}
    column_definitions = {
        "duration_ms": "REAL",
        "status": "TEXT NOT NULL DEFAULT 'success'",
        "format_requested": "TEXT",
        "project_name": "TEXT",
        "agent_id": "TEXT",
        "error_message": "TEXT",
        "response_size_bytes": "INTEGER",
        "repo_root": "TEXT",
        "correlation_id": "TEXT",
        "measurement_scope": "TEXT",
    }
    for column_name, column_definition in column_definitions.items():
        if column_name not in existing:
            conn.execute(f"ALTER TABLE tool_calls ADD COLUMN {column_name} {column_definition}")


async def record_agent_report_card(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    project: ProjectRecord,
    file_path: str,
    agent_name: str,
    stage: Optional[str],
    overall_grade: Optional[float],
    performance_level: Optional[str],
    metadata: Optional[Dict[str, Any]],
) -> None:
    await initialise_fn()
    meta_json = json.dumps(metadata or {}, sort_keys=True)
    async with write_lock:
        await execute_fn(
            """
            INSERT INTO agent_report_cards
                (project_id, file_path, agent_name, stage, overall_grade, performance_level, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, file_path)
            DO UPDATE SET agent_name = excluded.agent_name,
                          stage = excluded.stage,
                          overall_grade = excluded.overall_grade,
                          performance_level = excluded.performance_level,
                          metadata = excluded.metadata,
                          updated_at = excluded.updated_at;
            """,
            (
                project.id,
                file_path,
                agent_name,
                stage,
                overall_grade,
                performance_level,
                meta_json,
                utcnow().isoformat(),
            ),
        )


async def cleanup_reminder_history(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    connect_fn: ConnectFn,
    logger: Any,
    cutoff_hours: int = 168,
) -> int:
    start_time = time.perf_counter()
    await initialise_fn()
    async with write_lock:

        def _cleanup_sync() -> int:
            conn = connect_fn()
            try:
                cursor = conn.execute(
                    """
                    DELETE FROM reminder_history
                    WHERE shown_at < datetime('now', ? || ' hours');
                    """,
                    (f"-{int(cutoff_hours)}",),
                )
                deleted = cursor.rowcount
                conn.commit()
                return deleted
            finally:
                conn.close()

        deleted = await asyncio.to_thread(_cleanup_sync)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    cleanup_threshold_ms = 100.0
    if elapsed_ms > cleanup_threshold_ms:
        logger.warning(
            f"Slow reminder query: cleanup_reminder_history took {elapsed_ms:.2f}ms "
            f"(threshold: {cleanup_threshold_ms}ms) [deleted={deleted} records]"
        )
    return deleted


def record_tool_call_sync(
    *,
    db_path: Path | str,
    logger: Any,
    session_id: str,
    tool_name: str,
    duration_ms: Optional[float] = None,
    status: str = "success",
    format_requested: Optional[str] = None,
    project_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    error_message: Optional[str] = None,
    response_size_bytes: Optional[int] = None,
    repo_root: Optional[str] = None,
    correlation_id: Optional[str] = None,
    measurement_scope: Optional[str] = None,
) -> None:
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        ensure_tool_call_metadata_columns(conn)
        conn.execute(
            """
            INSERT INTO tool_calls (
                session_id, tool_name, timestamp, duration_ms, status,
                format_requested, project_name, agent_id, error_message, response_size_bytes,
                repo_root, correlation_id, measurement_scope
            ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                tool_name,
                duration_ms,
                status,
                format_requested,
                project_name,
                agent_id,
                error_message,
                response_size_bytes,
                repo_root,
                correlation_id,
                measurement_scope,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("SQL tool logging failed in background thread: %s", e)


async def insert_bridge(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    bridge_id: str,
    name: str,
    version: str,
    manifest_json: str,
    state: str,
) -> None:
    await initialise_fn()
    await execute_fn(
        """
        INSERT INTO scribe_bridges (bridge_id, name, version, manifest_json, state)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(bridge_id) DO UPDATE SET
            name = excluded.name,
            version = excluded.version,
            manifest_json = excluded.manifest_json,
            state = excluded.state
        """,
        (bridge_id, name, version, manifest_json, state),
    )


async def update_bridge_state(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    bridge_id: str,
    state: str,
) -> None:
    await initialise_fn()
    await execute_fn(
        """
        UPDATE scribe_bridges
        SET state = ?
        WHERE bridge_id = ?
        """,
        (state, bridge_id),
    )


async def update_bridge_health(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    bridge_id: str,
    health_json: str,
    error: Optional[str] = None,
) -> None:
    await initialise_fn()
    await execute_fn(
        """
        UPDATE scribe_bridges
        SET health_json = ?,
            last_health_check = CURRENT_TIMESTAMP,
            last_error = ?
        WHERE bridge_id = ?
        """,
        (health_json, error, bridge_id),
    )


async def fetch_bridge(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    bridge_id: str,
) -> Optional[Dict[str, Any]]:
    await initialise_fn()
    row = await fetchone_fn(
        """
        SELECT bridge_id, name, version, manifest_json, state,
               health_json, registered_at, last_health_check, last_error
        FROM scribe_bridges
        WHERE bridge_id = ?
        """,
        (bridge_id,),
    )
    return dict(row) if row else None


async def list_bridges(
    *,
    initialise_fn: AsyncInitialise,
    fetchall_fn: AsyncFetchAll,
    state: Optional[str] = None,
) -> List[Dict[str, Any]]:
    await initialise_fn()
    if state:
        rows = await fetchall_fn(
            """
            SELECT bridge_id, name, version, manifest_json, state,
                   health_json, registered_at, last_health_check, last_error
            FROM scribe_bridges
            WHERE state = ?
            ORDER BY registered_at DESC
            """,
            (state,),
        )
    else:
        rows = await fetchall_fn(
            """
            SELECT bridge_id, name, version, manifest_json, state,
                   health_json, registered_at, last_health_check, last_error
            FROM scribe_bridges
            ORDER BY registered_at DESC
            """
        )
    return [dict(row) for row in rows]


async def delete_bridge(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    bridge_id: str,
) -> None:
    await initialise_fn()
    await execute_fn(
        """
        DELETE FROM scribe_bridges
        WHERE bridge_id = ?
        """,
        (bridge_id,),
    )
