"""Telemetry-domain operations for the SQLite storage backend."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from scribe_mcp.storage.models import ProjectRecord

from . import telemetry_support


AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchOne = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchAll = Callable[[str, tuple[Any, ...] | tuple], Awaitable[List[Any]]]
AsyncInitialise = Callable[[], Awaitable[None]]
ConnectFn = Callable[[], sqlite3.Connection]


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
    await telemetry_support.record_agent_report_card(
        initialise_fn=initialise_fn,
        write_lock=write_lock,
        execute_fn=execute_fn,
        project=project,
        file_path=file_path,
        agent_name=agent_name,
        stage=stage,
        overall_grade=overall_grade,
        performance_level=performance_level,
        metadata=metadata,
    )


async def record_reminder_shown(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    logger: Any,
    slow_query_threshold_ms: float,
    session_id: str,
    reminder_hash: str,
    project_root: Optional[str] = None,
    agent_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    reminder_key: Optional[str] = None,
    operation_status: str = "neutral",
    context_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    start_time = time.perf_counter()
    await initialise_fn()
    async with write_lock:
        context_json = json.dumps(context_metadata or {}, sort_keys=True)
        await execute_fn(
            """
            INSERT INTO reminder_history
            (session_id, reminder_hash, project_root, agent_id, tool_name,
             reminder_key, shown_at, operation_status, context_metadata)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?);
            """,
            (
                session_id,
                reminder_hash,
                project_root,
                agent_id,
                tool_name,
                reminder_key,
                operation_status,
                context_json,
            ),
        )

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    if elapsed_ms > slow_query_threshold_ms:
        logger.warning(
            f"Slow reminder query: record_reminder_shown took {elapsed_ms:.2f}ms "
            f"(threshold: {slow_query_threshold_ms}ms) [session={session_id[:16]}...]"
        )


async def check_reminder_cooldown(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    logger: Any,
    slow_query_threshold_ms: float,
    session_id: str,
    reminder_hash: str,
    cooldown_minutes: int = 15,
) -> bool:
    start_time = time.perf_counter()
    await initialise_fn()
    row = await fetchone_fn(
        """
        SELECT COUNT(*) as count
        FROM reminder_history
        WHERE session_id = ?
          AND reminder_hash = ?
          AND shown_at > datetime('now', ? || ' minutes');
        """,
        (session_id, reminder_hash, f"-{int(cooldown_minutes)}"),
    )
    result = (row["count"] if row else 0) > 0

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    if elapsed_ms > slow_query_threshold_ms:
        logger.warning(
            f"Slow reminder query: check_reminder_cooldown took {elapsed_ms:.2f}ms "
            f"(threshold: {slow_query_threshold_ms}ms) [session={session_id[:16]}...]"
        )
    return result


async def get_reminder_history(
    *,
    initialise_fn: AsyncInitialise,
    fetchall_fn: AsyncFetchAll,
    project_root: Optional[str] = None,
    agent_id: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    await initialise_fn()

    filters: List[str] = []
    params: List[Any] = []
    if project_root:
        filters.append("project_root = ?")
        params.append(project_root)
    if agent_id:
        filters.append("agent_id = ?")
        params.append(agent_id)
    if category:
        filters.append("reminder_key LIKE ?")
        params.append(f"{category}.%")

    where_clause = " AND ".join(filters) if filters else "1=1"
    normalized_limit = max(1, min(int(limit), 200))
    params.append(normalized_limit)

    rows = await fetchall_fn(
        f"""
        SELECT id, session_id, reminder_hash, project_root, agent_id, tool_name,
               reminder_key, shown_at, operation_status, context_metadata
        FROM reminder_history
        WHERE {where_clause}
        ORDER BY shown_at DESC
        LIMIT ?;
        """,
        tuple(params),
    )

    history: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        raw_context = item.get("context_metadata")
        if isinstance(raw_context, str) and raw_context:
            try:
                item["context_metadata"] = json.loads(raw_context)
            except json.JSONDecodeError:
                pass
        history.append(item)
    return history


async def clear_reminder_history(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    connect_fn: ConnectFn,
    project_root: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> int:
    await initialise_fn()

    clauses: List[str] = []
    params: List[Any] = []
    if project_root:
        clauses.append("project_root = ?")
        params.append(project_root)
    if agent_id:
        clauses.append("agent_id = ?")
        params.append(agent_id)
    where_clause = " AND ".join(clauses) if clauses else "1=1"

    async with write_lock:
        def _clear_sync() -> int:
            conn = connect_fn()
            try:
                cursor = conn.execute(
                    f"DELETE FROM reminder_history WHERE {where_clause};",
                    tuple(params),
                )
                deleted = int(cursor.rowcount or 0)
                conn.commit()
                return deleted
            finally:
                conn.close()

        return await asyncio.to_thread(_clear_sync)


async def cleanup_reminder_history(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    connect_fn: ConnectFn,
    logger: Any,
    cutoff_hours: int = 168,
) -> int:
    return await telemetry_support.cleanup_reminder_history(
        initialise_fn=initialise_fn,
        write_lock=write_lock,
        connect_fn=connect_fn,
        logger=logger,
        cutoff_hours=cutoff_hours,
    )


async def record_tool_call(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
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
    await initialise_fn()
    async with write_lock:
        try:
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
                try:
                    await execute_fn(f"ALTER TABLE tool_calls ADD COLUMN {column_name} {column_definition}", ())
                except Exception as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
            await execute_fn(
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
        except Exception as e:
            logger.error(f"Failed to record tool call: {e}")


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
    telemetry_support.record_tool_call_sync(
        db_path=db_path,
        logger=logger,
        session_id=session_id,
        tool_name=tool_name,
        duration_ms=duration_ms,
        status=status,
        format_requested=format_requested,
        project_name=project_name,
        agent_id=agent_id,
        error_message=error_message,
        response_size_bytes=response_size_bytes,
        repo_root=repo_root,
        correlation_id=correlation_id,
        measurement_scope=measurement_scope,
    )


async def get_session_tool_calls(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    fetchall_fn: AsyncFetchAll,
    session_id: str,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    await initialise_fn()
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
        try:
            await execute_fn(f"ALTER TABLE tool_calls ADD COLUMN {column_name} {column_definition}", ())
        except Exception as exc:
            if "duplicate column" not in str(exc).lower():
                raise
    query = """
        SELECT id, tool_name, timestamp, duration_ms, status,
               format_requested, project_name, agent_id, error_message, response_size_bytes,
               repo_root, correlation_id, measurement_scope
        FROM tool_calls
        WHERE session_id = ?
        ORDER BY timestamp DESC
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = await fetchall_fn(query, (session_id,))
    return [dict(row) for row in rows]


async def get_tool_metrics(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    tool_name: Optional[str] = None,
    project_name: Optional[str] = None,
    time_range_hours: Optional[int] = 24,
) -> Dict[str, Any]:
    await initialise_fn()
    where_clauses: List[str] = []
    params: List[Any] = []

    if tool_name:
        where_clauses.append("tool_name = ?")
        params.append(tool_name)
    if project_name:
        where_clauses.append("project_name = ?")
        params.append(project_name)
    if time_range_hours:
        where_clauses.append("timestamp >= datetime('now', ? || ' hours')")
        params.append(f"-{time_range_hours}")

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    row = await fetchone_fn(
        f"""
        SELECT
            COUNT(*) as total_calls,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
            AVG(duration_ms) as avg_duration_ms,
            SUM(response_size_bytes) as total_response_bytes
        FROM tool_calls
        WHERE {where_sql}
        """,
        tuple(params),
    )
    result = (
        dict(row)
        if row
        else {
            "total_calls": 0,
            "success_count": 0,
            "error_count": 0,
            "avg_duration_ms": None,
            "total_response_bytes": None,
        }
    )

    if result["total_calls"] > 0:
        p95_offset = int(result["total_calls"] * 0.05)
        p95_row = await fetchone_fn(
            f"""
            SELECT duration_ms
            FROM tool_calls
            WHERE {where_sql} AND duration_ms IS NOT NULL
            ORDER BY duration_ms DESC
            LIMIT 1 OFFSET ?
            """,
            tuple(params + [p95_offset]),
        )
        result["p95_duration_ms"] = p95_row["duration_ms"] if p95_row else None
    else:
        result["p95_duration_ms"] = None
    return result


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
    await telemetry_support.insert_bridge(
        initialise_fn=initialise_fn,
        execute_fn=execute_fn,
        bridge_id=bridge_id,
        name=name,
        version=version,
        manifest_json=manifest_json,
        state=state,
    )


async def update_bridge_state(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    bridge_id: str,
    state: str,
) -> None:
    await telemetry_support.update_bridge_state(
        initialise_fn=initialise_fn,
        execute_fn=execute_fn,
        bridge_id=bridge_id,
        state=state,
    )


async def update_bridge_health(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    bridge_id: str,
    health_json: str,
    error: Optional[str] = None,
) -> None:
    await telemetry_support.update_bridge_health(
        initialise_fn=initialise_fn,
        execute_fn=execute_fn,
        bridge_id=bridge_id,
        health_json=health_json,
        error=error,
    )


async def fetch_bridge(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    bridge_id: str,
) -> Optional[Dict[str, Any]]:
    return await telemetry_support.fetch_bridge(
        initialise_fn=initialise_fn,
        fetchone_fn=fetchone_fn,
        bridge_id=bridge_id,
    )


async def list_bridges(
    *,
    initialise_fn: AsyncInitialise,
    fetchall_fn: AsyncFetchAll,
    state: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return await telemetry_support.list_bridges(
        initialise_fn=initialise_fn,
        fetchall_fn=fetchall_fn,
        state=state,
    )


async def delete_bridge(
    *,
    initialise_fn: AsyncInitialise,
    execute_fn: AsyncExecute,
    bridge_id: str,
) -> None:
    await telemetry_support.delete_bridge(
        initialise_fn=initialise_fn,
        execute_fn=execute_fn,
        bridge_id=bridge_id,
    )
