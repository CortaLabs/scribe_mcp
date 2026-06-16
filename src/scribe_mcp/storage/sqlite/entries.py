"""Entry-domain operations for the SQLite storage backend."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.utils.search import message_matches
from scribe_mcp.utils.time import format_utc, utcnow


AsyncExecute = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchOne = Callable[[str, tuple[Any, ...]], Awaitable[Any]]
AsyncFetchAll = Callable[[str, tuple[Any, ...] | tuple], Awaitable[List[Any]]]
AsyncInitialise = Callable[[], Awaitable[None]]


def _build_filtered_clauses(
    *,
    project_id: int,
    filters: Dict[str, Any],
) -> tuple[List[str], List[Any]]:
    clauses = ["project_id = ?"]
    params: List[Any] = [project_id]

    agent = filters.get("agent")
    if agent:
        clauses.append("agent = ?")
        params.append(agent)

    emoji = filters.get("emoji")
    if emoji:
        clauses.append("emoji = ?")
        params.append(emoji)

    priority = filters.get("priority")
    if priority:
        placeholders = ",".join("?" * len(priority))
        clauses.append(f"priority IN ({placeholders})")
        params.extend(priority)

    category = filters.get("category")
    if category:
        placeholders = ",".join("?" * len(category))
        clauses.append(f"category IN ({placeholders})")
        params.extend(category)

    min_confidence = filters.get("min_confidence")
    if min_confidence is not None:
        clauses.append("confidence >= ?")
        params.append(min_confidence)

    log_type = filters.get("log_type")
    if log_type:
        if isinstance(log_type, str):
            clauses.append("log_type = ?")
            params.append(log_type)
        elif isinstance(log_type, (list, tuple)):
            placeholders = ",".join("?" * len(log_type))
            clauses.append(f"log_type IN ({placeholders})")
            params.extend(log_type)

    return clauses, params


async def insert_entry(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
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
    await initialise_fn()
    ts_iso = ts.isoformat()
    meta_json = json.dumps(meta or {}, sort_keys=True)

    if priority is None and meta:
        priority = meta.get("priority", "medium")
    elif priority is None:
        priority = "medium"
    if category is None and meta:
        category = meta.get("category")
    if tags is None and meta:
        tags = meta.get("tags")
    if confidence is None and meta:
        confidence = meta.get("confidence", 1.0)
    elif confidence is None:
        confidence = 1.0
    if log_type is None and meta:
        log_type = meta.get("log_type", "progress")
    elif log_type is None:
        log_type = "progress"

    if log_type == "tool_logs":
        return

    async with write_lock:
        await execute_fn(
            """
            INSERT OR IGNORE INTO scribe_entries
                (id, project_id, ts, emoji, agent, message, meta, raw_line, sha256, ts_iso, priority, category, tags, confidence, log_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                entry_id,
                project.id,
                format_utc(ts),
                emoji,
                agent,
                message,
                meta_json,
                raw_line,
                sha256,
                ts_iso,
                priority,
                category,
                tags,
                confidence,
                log_type,
            ),
        )
        await execute_fn(
            """
            INSERT INTO scribe_metrics (project_id, total_entries, success_count, warn_count, error_count, last_update)
            VALUES (?, 1, ?, ?, ?, ?)
            ON CONFLICT(project_id)
            DO UPDATE SET total_entries = scribe_metrics.total_entries + 1,
                          success_count = scribe_metrics.success_count + excluded.success_count,
                          warn_count = scribe_metrics.warn_count + excluded.warn_count,
                          error_count = scribe_metrics.error_count + excluded.error_count,
                          last_update = excluded.last_update;
            """,
            (
                project.id,
                1 if emoji == "✅" else 0,
                1 if emoji == "⚠️" else 0,
                1 if emoji == "❌" else 0,
                utcnow().isoformat(),
            ),
        )


async def update_entry_meta(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    entry_id: str,
    project: ProjectRecord,
    meta: Dict[str, Any],
) -> bool:
    await initialise_fn()
    meta_json = json.dumps(meta or {}, sort_keys=True)
    async with write_lock:
        cursor = await execute_fn(
            """
            UPDATE scribe_entries
            SET meta = ?
            WHERE id = ? AND project_id = ?;
            """,
            (meta_json, entry_id, project.id),
        )
    return bool(getattr(cursor, "rowcount", 0))


async def fetch_recent_entries(
    *,
    initialise_fn: AsyncInitialise,
    fetchall_fn: AsyncFetchAll,
    project: ProjectRecord,
    limit: int,
    filters: Optional[Dict[str, Any]] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    await initialise_fn()
    filters = filters or {}
    clauses, params = _build_filtered_clauses(project_id=project.id, filters=filters)
    where_clause = " AND ".join(clauses)

    priority_sort = filters.get("priority_sort", False)
    if priority_sort:
        order_by = """
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 3
                    ELSE 4
                END ASC,
                ts_iso DESC
        """
    else:
        order_by = "ORDER BY ts_iso DESC"

    rows = await fetchall_fn(
        f"""
        SELECT id, ts, emoji, agent, message, meta, raw_line, priority, category, confidence
        FROM scribe_entries
        WHERE {where_clause}
        {order_by}
        LIMIT ? OFFSET ?;
        """,
        (*params, limit, offset),
    )

    results: List[Dict[str, Any]] = []
    for row in rows:
        meta_value = json.loads(row["meta"]) if row["meta"] else {}
        results.append(
            {
                "id": row["id"],
                "ts": row["ts"],
                "emoji": row["emoji"],
                "agent": row["agent"],
                "message": row["message"],
                "meta": meta_value,
                "raw_line": row["raw_line"],
                "priority": row["priority"] if "priority" in row.keys() else "medium",
                "category": row["category"] if "category" in row.keys() else None,
                "confidence": row["confidence"] if "confidence" in row.keys() else 1.0,
            }
        )
    return results


async def fetch_entry_by_id(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    entry_id: str,
    repo_id: Optional[str] = None,
    project_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    await initialise_fn()
    clauses = ["e.id = ?"]
    params: List[Any] = [entry_id]
    if repo_id:
        clauses.append("p.repo_id = ?")
        params.append(repo_id)
    if project_name:
        clauses.append("p.name = ?")
        params.append(project_name)

    row = await fetchone_fn(
        f"""
        SELECT e.id AS entry_id, p.name AS project_name, p.repo_id, e.ts, e.agent, e.log_type
        FROM scribe_entries e
        JOIN scribe_projects p ON p.id = e.project_id
        WHERE {' AND '.join(clauses)}
        LIMIT 1;
        """,
        tuple(params),
    )
    if row is None:
        return None
    return {
        "entry_id": row["entry_id"],
        "project_name": row["project_name"],
        "repo_id": row["repo_id"],
        "timestamp": row["ts"],
        "agent": row["agent"],
        "log_type": row["log_type"],
    }


async def query_entries(
    *,
    initialise_fn: AsyncInitialise,
    fetchall_fn: AsyncFetchAll,
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
    await initialise_fn()
    limit = max(1, min(limit, 500))
    fetch_limit = min(max(limit * 3, limit), 1000)

    clauses = ["project_id = ?"]
    params: List[Any] = [project.id]

    if start:
        clauses.append("ts_iso >= ?")
        params.append(start)
    if end:
        clauses.append("ts_iso <= ?")
        params.append(end)

    if agents:
        placeholders = ", ".join("?" for _ in agents)
        clauses.append(f"agent IN ({placeholders})")
        params.extend(agents)

    if emojis:
        placeholders = ", ".join("?" for _ in emojis)
        clauses.append(f"emoji IN ({placeholders})")
        params.extend(emojis)

    if meta_filters:
        for key, value in sorted(meta_filters.items()):
            clauses.append("json_extract(meta, ?) = ?")
            params.append(f"$.{key}")
            params.append(value)

    where_clause = " AND ".join(clauses)
    rows = await fetchall_fn(
        f"""
        SELECT id, ts, ts_iso, emoji, agent, message, meta, raw_line
        FROM scribe_entries
        WHERE {where_clause}
        ORDER BY ts_iso DESC
        LIMIT ? OFFSET ?;
        """,
        (*params, fetch_limit, offset),
    )

    results: List[Dict[str, Any]] = []
    for row in rows:
        meta_value = json.loads(row["meta"]) if row["meta"] else {}
        entry = {
            "id": row["id"],
            "ts": row["ts"],
            "emoji": row["emoji"],
            "agent": row["agent"],
            "message": row["message"],
            "meta": meta_value,
            "raw_line": row["raw_line"],
        }
        if not message_matches(
            entry["message"],
            message,
            mode=message_mode,
            case_sensitive=case_sensitive,
        ):
            continue
        results.append(entry)
        if len(results) >= limit:
            break
    return results


def _metrics_counter_for_filters(filters: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return the scribe_metrics column name that satisfies *filters*, or None.

    Only the empty/None filter case is mapped to ``total_entries``.  All other
    filters (log_type, agent, priority, category, min_confidence, …) are NOT
    tracked in scribe_metrics and must fall through to the full COUNT(*) path.

    Q1 resolution: success_count/warn_count/error_count are maintained by
    emoji (✅/⚠️/❌), NOT by the ``status`` field used in _build_filtered_clauses,
    so no status→column mapping is safe here.
    """
    if not filters:
        return "total_entries"
    # Any non-empty filter dict — cannot use fast path
    return None


async def count_entries(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    project: ProjectRecord,
    filters: Optional[Dict[str, Any]] = None,
) -> int:
    await initialise_fn()

    # Fast path: O(1) read from scribe_metrics when no filters are applied.
    # Falls through to COUNT(*) when (a) filters are present, or (b) no
    # metrics row exists yet for this project.
    metric_col = _metrics_counter_for_filters(filters)
    if metric_col is not None:
        metrics_row = await fetchone_fn(
            f"SELECT {metric_col} AS count FROM scribe_metrics WHERE project_id = ?;",
            (project.id,),
        )
        if metrics_row is not None:
            return int(metrics_row["count"] or 0)
        # No metrics row yet — fall through to COUNT(*)

    clauses, params = _build_filtered_clauses(project_id=project.id, filters=filters or {})
    where_clause = " AND ".join(clauses)
    row = await fetchone_fn(
        f"""
        SELECT COUNT(*) as count
        FROM scribe_entries
        WHERE {where_clause};
        """,
        tuple(params),
    )
    return row["count"] if row else 0


async def count_query_entries(
    *,
    initialise_fn: AsyncInitialise,
    fetchone_fn: AsyncFetchOne,
    fetchall_fn: AsyncFetchAll,
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
    await initialise_fn()
    clauses = ["project_id = ?"]
    params: List[Any] = [project.id]

    if start:
        clauses.append("ts_iso >= ?")
        params.append(start)
    if end:
        clauses.append("ts_iso <= ?")
        params.append(end)

    if agents:
        placeholders = ", ".join("?" for _ in agents)
        clauses.append(f"agent IN ({placeholders})")
        params.extend(agents)

    if emojis:
        placeholders = ", ".join("?" for _ in emojis)
        clauses.append(f"emoji IN ({placeholders})")
        params.extend(emojis)

    if meta_filters:
        for key, value in sorted(meta_filters.items()):
            clauses.append("json_extract(meta, ?) = ?")
            params.append(f"$.{key}")
            params.append(value)

    where_clause = " AND ".join(clauses)
    row = await fetchone_fn(
        f"""
        SELECT COUNT(*) as count
        FROM scribe_entries
        WHERE {where_clause};
        """,
        tuple(params),
    )
    count = row["count"] if row else 0

    if message:
        fetch_limit = min(count, 10000)
        rows = await fetchall_fn(
            f"""
            SELECT message
            FROM scribe_entries
            WHERE {where_clause}
            LIMIT ?;
            """,
            (*params, fetch_limit),
        )
        matching_count = 0
        for row in rows:
            if message_matches(
                row["message"],
                message,
                mode=message_mode,
                case_sensitive=case_sensitive,
            ):
                matching_count += 1
        return matching_count

    return count


async def cleanup_old_entries(
    *,
    initialise_fn: AsyncInitialise,
    write_lock: Any,
    execute_fn: AsyncExecute,
    fetchone_fn: AsyncFetchOne,
    project_id: Optional[int] = None,
    retention_days: int = 90,
    archive: bool = True,
) -> int:
    await initialise_fn()
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()

    if project_id is not None:
        where_clause = "WHERE ts_iso < ? AND project_id = ?"
        params: tuple = (cutoff_date, project_id)
    else:
        where_clause = "WHERE ts_iso < ?"
        params = (cutoff_date,)

    async with write_lock:
        if archive:
            await execute_fn(
                f"""
                INSERT OR IGNORE INTO scribe_entries_archive
                    (id, project_id, ts, ts_iso, emoji, agent, message, meta,
                     raw_line, sha256, log_type, priority, category, confidence)
                SELECT
                    id, project_id, ts, ts_iso, emoji, agent, message, meta,
                    raw_line, sha256, log_type, priority, category, confidence
                FROM scribe_entries
                {where_clause}
                """,
                params,
            )

        row = await fetchone_fn(
            f"""
            SELECT COUNT(*) as count FROM scribe_entries {where_clause}
            """,
            params,
        )
        count = row["count"] if row else 0

        await execute_fn(
            f"""
            DELETE FROM scribe_entries {where_clause}
            """,
            params,
        )
    return count
